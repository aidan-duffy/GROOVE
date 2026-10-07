from __future__ import annotations
import argparse
import json
import logging
import math
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
import joblib
import numpy as np
import pandas as pd
from sklearn.cluster import DBSCAN
from sklearn.neighbors import NearestNeighbors
from . import settings as S
from . import classify as _classify
from . import embedding as _embedding
from . import features as _features
from . import loading as _loading
from . import outputs as _outputs
from . import persistence as _persistence
from . import plots as _plots
from . import utils as _utils




def finalise(table: pd.DataFrame, version_dir: Path, config: Mapping[str, Any],
             specs: Sequence[Mapping[str, Any]], records: Sequence[Mapping[str, Any]],
             extra: Dict[str, pd.DataFrame], outline_new: bool,
             logger: logging.Logger,
             combined_space: Optional[np.ndarray] = None,
             combined_keys: Optional[Sequence[str]] = None,
             sources: Optional[Mapping[str, Mapping[str, Any]]] = None) -> None:
    """Shared output stage: plots, maps, folders, appendix, tables."""
    colours = dict(S.CATEGORY_COLOURS)
    colours.update(config.get("category_colours", {}) or {})
    table = _outputs.add_traceability_columns(table, config)
    flare_events = _classify.flare_event_validation_table(records, table, version_dir)
    extra["flare_event_validation"] = flare_events
    table, neighbour_details, category_validation = _embedding.nearest_neighbour_validation(
        table, config, combined_space, combined_keys, logger)
    if not neighbour_details.empty:
        extra["umap_neighbour_anchor_details"] = neighbour_details
    if not category_validation.empty:
        extra["umap_category_validation_summary"] = category_validation
    validation_columns = [name for name in (
        "source_id", "source_key", "dataset", "final_primary_tag",
        "nearest_original_feature_source_id", "nearest_original_feature_distance",
        "nearest_umap_source_id", "nearest_umap_distance",
        "original_5_category_agreement", "original_10_category_agreement",
        "umap_5_category_agreement", "original_5_mean_score_similarity",
        "original_10_mean_score_similarity", "umap_5_mean_score_similarity",
        "nearest_original_neighbour_preserved_in_2d",
        "original_space_silhouette_contribution", "umap_silhouette_contribution",
        "classification_score_margin", "distance_to_category_typical_example")
        if name in table.columns]
    extra["umap_neighbour_validation"] = table[validation_columns].copy()

    combined_neighbours = int(config.get(
        "_selected_combined_n_neighbors",
        _embedding.representation_settings(config, "combined", len(table))["n_neighbors"]))
    for category, count in table["final_primary_tag"].value_counts().items():
        if int(count) <= int(combined_neighbours):
            logger.warning(
                "%s contains only %d source%s while n_neighbors=%d; a fully %s-dominated "
                "neighbourhood is impossible.", str(category).replace("_", " ").title(),
                int(count), "" if int(count) == 1 else "s", int(combined_neighbours),
                str(category).replace("_", " "))

    # Every morphology visual uses one compact accepted-band, double-phase image
    # at the already-saved recommended period.  Existing LS/BLS figures belong
    # to the period-search pipeline and are intentionally never embedded here.
    output_config = dict(config)
    output_config["_phase_fold_products_only"] = True
    plot_sources: Dict[str, Mapping[str, Any]] = dict(sources or {})
    # Synthetic/integration callers may supply full records rather than the
    # production raw-source mapping.  Compact feature records do not enter this
    # fallback because they intentionally omit the observations.
    for record in records:
        summary = record.get("summary", {})
        key = str(summary.get("source_key", ""))
        if key and isinstance(record.get("data"), pd.DataFrame):
            plot_sources.setdefault(key, record)
    fold_paths, missing_phase = _plots.generate_phase_fold_products(
        plot_sources, table, version_dir, output_config, logger,
        force=bool(config.get("force_replot_phase_products", False)))
    extra["missing_phase_fold_plots"] = missing_phase

    _plots.build_neighbour_review_pages(
        neighbour_details, table, fold_paths, version_dir, logger)

    _plots.draw_overview_maps(table, version_dir, config, colours, outline_new)
    if bool(config.get("make_maps", True)):
        _plots.build_family_maps(records, table, version_dir, output_config, logger, fold_paths)

    if bool(config.get("make_category_folds", True)):
        memberships, missing = _outputs.build_category_folders(
            table, fold_paths, {}, version_dir, output_config, logger)
        extra["category_memberships"] = memberships
        extra["missing_phase_fold_plot_links"] = missing

    if bool(config.get("make_category_appendix", True)):
        _plots.build_category_appendix(table, fold_paths, version_dir, output_config, logger)

    _outputs.write_tables(table, version_dir, extra, config)
    counts = table["final_primary_tag"].value_counts().to_dict()
    logger.info("Category counts: %s", json.dumps(counts))
    logger.info("Morphology plots: %s", _persistence.figure_directory(version_dir))


def fit_or_refit(config: Dict[str, Any], args: argparse.Namespace, mode: str) -> Dict[str, Any]:
    output_root = Path(config["output_root"])
    version = config.get("model_version") or ""
    version_dir = _persistence.version_directory(output_root, version)
    if (version_dir.exists() and (version_dir / "models" / "model_metadata.json").exists()
            and not bool(config.get("overwrite_existing_model", False))
            and not (bool(config.get("resume_finalisation", True))
                     and _persistence.finalisation_checkpoint_path(version_dir).exists())):
        raise SystemExit(
            "A completed model already exists at %s.\n"
            "Use --mode transform to add data to it, --overwrite to rebuild it in place, "
            "or --model-version NAME to build a separate one." % version_dir)
    _persistence.ensure_structure(version_dir)
    logger = _utils.setup_logging(version_dir, args.verbose)
    logger.info("Mode=%s  version=%s", mode, version)

    specs = [d for d in config.get("datasets", []) if bool(d.get("process", True))]
    skipped = [str(d.get("name", "?")) for d in config.get("datasets", [])
               if not bool(d.get("process", True))]
    if skipped:
        logger.info("process=False, not re-extracted: %s", ", ".join(skipped))
    if not specs:
        raise SystemExit("No datasets have process=True.")
    sources, load_problems = _loading.load_lightcurves(specs, config, logger)
    if len(sources) < 5:
        raise SystemExit("Only %d usable sources; need at least 5 to fit a map." % len(sources))
    _outputs.mark_sources_with_existing_plots(sources, specs, logger)
    periods, conflicts = _loading.read_period_tables(specs, config, logger)
    records, failures = _features.extract_all_features(sources, periods, config, version_dir, logger)
    if len(records) < 5:
        raise SystemExit("Only %d sources produced features." % len(records))

    checkpoint = _persistence.load_finalisation_checkpoint(
        version_dir, records, config, mode, logger)
    if checkpoint is not None:
        table = checkpoint["table"]
        metadata = dict(checkpoint["metadata"])
        combined_settings = metadata.get("combined_umap_settings", {}) or {}
        config["_selected_combined_n_neighbors"] = int(combined_settings.get(
            "n_neighbors", _embedding.representation_settings(config, "combined", len(table))["n_neighbors"]))
        config["_selected_combined_metric"] = str(combined_settings.get(
            "metric", config.get("combined_umap_metric", "cosine")))
        finalise(
            table, version_dir, config, specs, records,
            dict(checkpoint.get("extra", {})), bool(checkpoint.get("outline_new", False)),
            logger, checkpoint.get("combined_space"), checkpoint.get("combined_keys"),
            sources)
        _utils.atomic_write_json(metadata, version_dir / "models" / "model_metadata.json")
        _utils.atomic_write_json(config, version_dir / "models" / "resolved_config.json")
        _persistence.update_current_pointer(output_root, version, version_dir)
        _persistence.clear_finalisation_checkpoint(version_dir)
        if bool(config.get("clean_full_feature_cache_after_success", True)):
            _persistence.clean_full_feature_cache(version_dir, logger)
        logger.info("Done after resumed finalisation. Outputs under %s", version_dir)
        return {"version_dir": str(version_dir), "n_sources": len(table),
                "resumed_finalisation": True}

    table = _classify.assemble_table(records, config, {})

    metadata: Dict[str, Any] = {
        "model_version": version, "mode": mode, "created": _utils.iso_now(),
        "feature_config_hash": _features.feature_config_hash(config),
        "schema": S.FEATURE_SCHEMA_VERSION,
        "n_reference_sources": len(records),
        "primary_maps_supervised": False,
        "fit_sample_policy": "all_accepted_sources_unbalanced",
    }

    block_models: Dict[str, Any] = {}
    for block, prefix in (("periodic", "periodic_umap"), ("transient", "transient_umap")):
        matrix, names = _embedding.feature_matrix(records, block)
        models = _embedding.fit_representation(matrix, config, logger, names=names, block=block)
        block_models[block] = models
        models["ood"] = _embedding.fit_ood_model(models["model_space"], config)
        table["%s_1" % prefix] = models["embedding"][:, 0]
        table["%s_2" % prefix] = models["embedding"][:, 1]
        if block == "periodic":
            table["out_of_distribution_score"] = _embedding.ood_scores(models["ood"], models["model_space"])
        _persistence.save_models(version_dir, block, models)
        metadata["%s_feature_names" % block] = names
        metadata["%s_umap_settings" % block] = models["selected_settings"]

    metadata["evolution_threshold"] = _embedding.calibrated_threshold(
        table["evolution_raw_score"], float(config.get("evolution_quantile", 0.95)))
    logger.info("Frozen evolution threshold: %.3f", metadata["evolution_threshold"])

    table = _classify.classify_table(table, metadata, config)
    regression_columns = list((
        "suggested_primary_tag", "suggested_secondary_tags", "morphology_confidence",
        "suggestion_confidence", "suggested_interest_status", "interest_status",
        "interest_reasons", "interest_confidence", "exotic_candidate_score",
        "rule_fired", "needs_review", "review_reason") + S.CATEGORY_SCORE_COLUMNS)
    classification_before_mapping = table[regression_columns].copy(deep=True)

    # The principal scientific map combines both feature blocks.  The score
    # table above is supplied only to the optional evaluator for diagnostics;
    # neither discrete nor continuous category evidence enters a UMAP fit.
    combined_matrix, combined_names = _embedding.feature_matrix(records, "combined")
    parameter_comparison, selected_combined = _embedding.umap_parameter_comparison(
        combined_matrix, combined_names, table, config, logger)
    combined_models = _embedding.fit_representation(
        combined_matrix, config, logger, names=combined_names, block="combined",
        selected=selected_combined)
    config["_selected_combined_n_neighbors"] = int(
        combined_models["selected_settings"]["n_neighbors"])
    config["_selected_combined_metric"] = str(
        combined_models["selected_settings"]["metric"])
    combined_models["ood"] = _embedding.fit_ood_model(combined_models["model_space"], config)
    block_models["combined"] = combined_models
    table["combined_umap_1"] = combined_models["embedding"][:, 0]
    table["combined_umap_2"] = combined_models["embedding"][:, 1]
    _persistence.save_models(version_dir, "combined", combined_models)

    evidence_models = _embedding.fit_evidence_representation(table, config, logger)
    table["classification_evidence_umap_1"] = evidence_models["embedding"][:, 0]
    table["classification_evidence_umap_2"] = evidence_models["embedding"][:, 1]
    _persistence.save_models(version_dir, "classification_evidence", evidence_models)

    if not table[regression_columns].equals(classification_before_mapping):
        raise AssertionError(
            "Classification regression: UMAP fitting changed classification outputs")
    logger.info("Classification regression passed: all labels, tags, confidence, interest, "
                "and score values are unchanged by map fitting")

    metadata["combined_feature_names"] = combined_names
    metadata["category_score_order"] = list(S.CATEGORY_SCORE_COLUMNS)
    metadata["combined_umap_settings"] = combined_models["selected_settings"]
    metadata["classification_evidence_umap_settings"] = evidence_models["selected_settings"]
    metadata["feature_weight_interpretation"] = str(config.get(
        "feature_weight_interpretation", "distance_contribution"))
    configured_weights = dict(S.DEFAULT_FEATURE_WEIGHTS)
    configured_weights.update(config.get("feature_weights", {}) or {})
    effective_weights = {
        group: (math.sqrt(max(0.0, float(value)))
                if metadata["feature_weight_interpretation"] == "distance_contribution"
                else float(value))
        for group, value in configured_weights.items()}
    metadata["configured_feature_weights"] = configured_weights
    metadata["effective_feature_multipliers"] = effective_weights
    weight_summary = pd.DataFrame([
        {"feature_group": group, "configured_weight": configured_weights[group],
         "effective_multiplier": effective_weights[group],
         "interpretation": metadata["feature_weight_interpretation"]}
        for group in configured_weights])
    combined_keys = table["source_key"].astype(str).tolist()
    _persistence.save_combined_validation_space(
        version_dir, combined_keys, combined_models["model_space"])

    manual_path = Path(config.get("manual_labels_file") or (output_root / "manual_labels.csv"))
    _classify.ensure_manual_labels_file(manual_path)
    table = _classify.apply_labels(table, _classify.load_manual_labels(manual_path))

    batch = config.get("batch_id") or ("reference_%s" % version)
    table["batch_id"] = batch
    table["is_reference"] = True
    table["is_latest_batch"] = True
    table["first_seen"] = _utils.iso_now()

    outline = bool(config.get("outline_new_sources") or False)
    final_extra = {
        "processing_failures": failures, "load_problems": load_problems,
        "period_table_conflicts": conflicts,
        "umap_parameter_comparison": parameter_comparison,
        "umap_feature_weights": weight_summary,
    }
    if bool(config.get("resume_finalisation", True)):
        _persistence.save_finalisation_checkpoint(version_dir, {
            "schema": S.FEATURE_SCHEMA_VERSION,
            "feature_config_hash": _features.feature_config_hash(config),
            "mode": mode,
            "source_key_digest": _persistence.source_key_digest(records),
            "manual_labels_fingerprint": _persistence.manual_labels_fingerprint(config),
            "table": table,
            "metadata": metadata,
            "extra": final_extra,
            "outline_new": outline,
            "combined_space": combined_models["model_space"],
            "combined_keys": combined_keys,
        })
        logger.info("Saved finalisation checkpoint before generating output products")
    finalise(table, version_dir, config, specs, records, final_extra, outline, logger,
             combined_models["model_space"], combined_keys, sources)

    _utils.atomic_write_json(metadata, version_dir / "models" / "model_metadata.json")
    _utils.atomic_write_json(config, version_dir / "models" / "resolved_config.json")
    _persistence.update_current_pointer(output_root, version, version_dir)
    _persistence.clear_finalisation_checkpoint(version_dir)
    if bool(config.get("clean_full_feature_cache_after_success", True)):
        _persistence.clean_full_feature_cache(version_dir, logger)
    logger.info("Done. Outputs under %s", version_dir)
    return {"version_dir": str(version_dir), "n_sources": len(table)}


def transform_mode(config: Dict[str, Any], args: argparse.Namespace) -> Dict[str, Any]:
    output_root = Path(config["output_root"])
    version, version_dir = _persistence.resolve_version_dir(output_root, config.get("model_version"))
    if not version_dir.exists():
        raise SystemExit("Model version directory not found: %s" % version_dir)
    logger = _utils.setup_logging(version_dir, args.verbose)
    metadata = json.loads((version_dir / "models" / "model_metadata.json").read_text("utf-8"))
    if metadata.get("feature_config_hash") != _features.feature_config_hash(config):
        raise SystemExit(
            "Feature/configuration hash mismatch: the saved model was built with different "
            "representation settings. Use --mode refit with a new --model-version.")

    # Only datasets flagged process=True are read from disk; the rest are
    # already on the map and are simply carried over and re-plotted.
    specs = [d for d in config.get("datasets", []) if bool(d.get("process", True))]
    carried = [str(d.get("name", "?")) for d in config.get("datasets", [])
               if not bool(d.get("process", True))]
    if carried:
        logger.info("Carried over without re-processing: %s", ", ".join(carried))
    if not specs:
        raise SystemExit("No datasets have process=True; nothing to transform.")
    sources, load_problems = _loading.load_lightcurves(specs, config, logger)
    _outputs.mark_sources_with_existing_plots(sources, specs, logger)
    periods, conflicts = _loading.read_period_tables(specs, config, logger)

    old = _loading.read_table(version_dir / "tables" / "all_sources.csv")
    known = set(old["source_key"].astype(str)) if not old.empty else set()
    policy = str(config.get("existing_id_policy", "skip"))
    if policy == "skip":
        new_keys = [k for k in sources if k not in known]
        logger.info("%d new sources (%d already on the map, skipped)",
                    len(new_keys), len(sources) - len(new_keys))
    else:
        new_keys = list(sources.keys())
    if not new_keys:
        logger.info("Nothing to transform.")
        return {"version_dir": str(version_dir), "n_sources": 0}

    subset = {k: sources[k] for k in new_keys}
    records, failures = _features.extract_all_features(subset, periods, config, version_dir, logger)
    table = _classify.assemble_table(records, config, metadata)

    new_combined_space: Optional[np.ndarray] = None
    for block, prefix in (("periodic", "periodic_umap"),
                          ("transient", "transient_umap"),
                          ("combined", "combined_umap")):
        matrix, _ = _embedding.feature_matrix(records, block)
        models = _persistence.load_models(version_dir, block)
        embedding, model_space = _embedding.transform_representation(models, matrix)
        table["%s_1" % prefix] = embedding[:, 0]
        table["%s_2" % prefix] = embedding[:, 1]
        if block == "periodic":
            table["out_of_distribution_score"] = _embedding.ood_scores(models["ood"], model_space)
        elif block == "combined":
            new_combined_space = model_space
            config["_selected_combined_n_neighbors"] = int(
                models.get("selected_settings", {}).get(
                    "n_neighbors", _embedding.representation_settings(
                        config, "combined", len(old) + len(table))["n_neighbors"]))
            config["_selected_combined_metric"] = str(
                models.get("selected_settings", {}).get(
                    "metric", config.get("combined_umap_metric", "cosine")))

    table = _classify.classify_table(table, metadata, config)
    evidence_models = _persistence.load_models(version_dir, "classification_evidence")
    evidence_embedding, _ = _embedding.transform_evidence_representation(evidence_models, table)
    table["classification_evidence_umap_1"] = evidence_embedding[:, 0]
    table["classification_evidence_umap_2"] = evidence_embedding[:, 1]
    manual_path = Path(config.get("manual_labels_file") or (output_root / "manual_labels.csv"))
    _classify.ensure_manual_labels_file(manual_path)
    table = _classify.apply_labels(table, _classify.load_manual_labels(manual_path))
    batch = config.get("batch_id") or ("batch_%s" % _utils.stamp())
    table["batch_id"] = batch
    table["is_reference"] = False
    table["is_latest_batch"] = True
    table["first_seen"] = _utils.iso_now()

    if not old.empty:
        combined = _embedding.merge_transformed_sources(old, table)
    else:
        combined = table

    old_validation_keys, old_validation_space = _persistence.load_combined_validation_space(version_dir)
    if new_combined_space is None:
        raise AssertionError("Combined morphology representation was not transformed")
    validation_keys, validation_space = _persistence.merge_validation_space(
        old_validation_keys, old_validation_space,
        table["source_key"].astype(str).tolist(), new_combined_space)
    _persistence.save_combined_validation_space(version_dir, validation_keys, validation_space)

    outline = config.get("outline_new_sources")
    outline = True if outline is None else bool(outline)
    if args.no_outline_new:
        outline = False
    finalise(combined, version_dir, config, specs, records,
             {"processing_failures": failures, "load_problems": load_problems,
              "period_table_conflicts": conflicts}, outline, logger,
             validation_space, validation_keys, subset)
    logger.info("Transformed %d new sources into %s", len(table), version_dir)
    return {"version_dir": str(version_dir), "n_sources": len(table)}


def relabel_or_plot(config: Dict[str, Any], args: argparse.Namespace,
                    mode: str) -> Dict[str, Any]:
    output_root = Path(config["output_root"])
    version, version_dir = _persistence.resolve_version_dir(output_root, config.get("model_version"))
    logger = _utils.setup_logging(version_dir, args.verbose)
    metadata = json.loads((version_dir / "models" / "model_metadata.json").read_text("utf-8"))
    table = _loading.read_table(version_dir / "tables" / "all_sources.csv")
    if table.empty:
        raise SystemExit("No saved all_sources.csv to work from.")

    if mode == "relabel":
        table = _classify.classify_table(table, metadata, config)
        evidence_models = _persistence.load_models(version_dir, "classification_evidence")
        evidence_embedding, _ = _embedding.transform_evidence_representation(evidence_models, table)
        table["classification_evidence_umap_1"] = evidence_embedding[:, 0]
        table["classification_evidence_umap_2"] = evidence_embedding[:, 1]
        manual_path = Path(config.get("manual_labels_file") or (output_root / "manual_labels.csv"))
        _classify.ensure_manual_labels_file(manual_path)
        table = _classify.apply_labels(table, _classify.load_manual_labels(manual_path))
        logger.info("Rebuilt labels for %d sources", len(table))

    outline = bool(config.get("outline_new_sources") or False)
    if args.outline_new:
        outline = True
    if args.no_outline_new:
        outline = False
    local = dict(config)
    local["make_review_plots"] = bool(config.get("make_review_plots", True)) and mode == "relabel"
    try:
        combined_models = _persistence.load_models(version_dir, "combined")
        local["_selected_combined_n_neighbors"] = int(
            combined_models.get("selected_settings", {}).get(
                "n_neighbors", _embedding.representation_settings(local, "combined", len(table))["n_neighbors"]))
        local["_selected_combined_metric"] = str(
            combined_models.get("selected_settings", {}).get(
                "metric", local.get("combined_umap_metric", "cosine")))
    except FileNotFoundError:
        pass
    validation_keys, validation_space = _persistence.load_combined_validation_space(version_dir)
    finalise(table, version_dir, local, config.get("datasets", []), [], {}, outline, logger,
             validation_space, validation_keys)
    return {"version_dir": str(version_dir), "n_sources": len(table)}


def highlight_source_mode(config: Dict[str, Any], args: argparse.Namespace) -> Dict[str, Any]:
    """Create source-highlight and neighbour products from a frozen model."""
    output_root = Path(config["output_root"])
    _, version_dir = _persistence.resolve_version_dir(output_root, config.get("model_version"))
    logger = _utils.setup_logging(version_dir, args.verbose)
    table = _loading.read_table(version_dir / "tables" / "all_sources.csv")
    if table.empty:
        raise SystemExit("No saved all_sources.csv to work from.")
    source_id = _utils.clean_source_id(args.source_id)
    if not source_id:
        raise SystemExit("--source-id is required for --mode highlight-source.")
    label = str(args.source_label or source_id)
    source = table.loc[table["source_id"].astype(str).map(_utils.clean_source_id).eq(source_id)]
    if source.empty:
        raise SystemExit("Source %s is not present in the frozen catalogue." % source_id)
    map_name = str(args.map_name or "combined")
    x_col, y_col, title, original_base = S.ADDON_MAP_SPECS[map_name]
    colours = dict(S.CATEGORY_COLOURS)
    colours.update(config.get("category_colours", {}) or {})
    addon_base = "%s_%s_highlighted" % (original_base, _utils.safe_name(label))
    _plots.make_static_map(
        table, x_col, y_col, "%s - %s highlighted" % (title, label),
        addon_base, version_dir, colours, False, {source_id: label}, config.get("dataset_markers", {}))

    neighbour_count = max(1, min(int(args.nearest_neighbours or 8), 8))
    neighbours, panel_keys = _embedding.frozen_source_neighbours(
        table, version_dir, source_id, neighbour_count)
    table_dir = version_dir / "tables" / "additions"
    table_dir.mkdir(parents=True, exist_ok=True)
    neighbour_path = table_dir / ("%s_nearest_neighbours.csv" % _utils.safe_name(label))
    _utils.atomic_write_csv(neighbours, neighbour_path)

    panel_rows = table.set_index(table["source_key"].astype(str), drop=False).loc[panel_keys]
    selected_ids = panel_rows["source_id"].astype(str).map(_utils.clean_source_id).tolist()
    plot_config = dict(config)
    records = _loading.load_selected_lightcurves(
        [spec for spec in config.get("datasets", []) if bool(spec.get("process", True))],
        plot_config, selected_ids, logger)
    addition_dir = _persistence.figure_directory(version_dir) / "maps" / "additions" / _utils.safe_name(label)
    _plots.make_neighbour_phase_grid(
        table, panel_keys, neighbours, records, version_dir,
        addition_dir / ("%s_nearest_neighbours_9panel.png" % _utils.safe_name(label)),
        label, 1.0)
    if bool(args.diagnostic_folds):
        for factor, suffix in ((0.5, "half_period"), (2.0, "double_period")):
            _plots.make_neighbour_phase_grid(
                table, panel_keys, neighbours, records, version_dir,
                addition_dir / ("%s_nearest_neighbours_9panel_%s.png" % (
                    _utils.safe_name(label), suffix)), label, factor)
    logger.info("Frozen-map highlight written for %s; existing maps were not changed", label)
    return {
        "version_dir": str(version_dir),
        "highlight_map": str(_persistence.figure_directory(version_dir) / "maps" / (addon_base + ".png")),
        "neighbour_table": str(neighbour_path),
        "n_neighbours": neighbour_count,
    }


def umap_families_mode(config: Dict[str, Any], args: argparse.Namespace) -> Dict[str, Any]:
    """Label only robustly detached 2-D islands; keep the main body unassigned."""
    output_root = Path(config["output_root"])
    _, version_dir = _persistence.resolve_version_dir(output_root, config.get("model_version"))
    logger = _utils.setup_logging(version_dir, args.verbose)
    table = _loading.read_table(version_dir / "tables" / "all_sources.csv")
    if table.empty:
        raise SystemExit("No saved all_sources.csv to work from.")
    finite_mask = np.isfinite(table["combined_umap_1"]) & np.isfinite(table["combined_umap_2"])
    coordinates = table.loc[finite_mask, [
        "combined_umap_1", "combined_umap_2"]].to_numpy(dtype=float)
    min_samples = max(5, int(args.umap_cluster_min_samples or 20))
    if len(coordinates) <= min_samples:
        raise SystemExit("Not enough saved UMAP points for detached-family analysis.")
    if args.umap_cluster_eps is None:
        local = NearestNeighbors(n_neighbors=min_samples, metric="euclidean")
        local.fit(coordinates)
        local_distances, _ = local.kneighbors(coordinates)
        eps = float(np.percentile(local_distances[:, -1], 95.0))
    else:
        eps = float(args.umap_cluster_eps)
    if not np.isfinite(eps) or eps <= 0:
        raise SystemExit("--umap-cluster-eps must be positive.")
    minimum_family_size = int(args.umap_cluster_min_size or max(
        100, int(math.ceil(0.02 * len(coordinates)))))
    model = DBSCAN(eps=eps, min_samples=min_samples, metric="euclidean")
    raw_labels = model.fit_predict(coordinates)
    non_noise = raw_labels[raw_labels >= 0]
    if not len(non_noise):
        raise SystemExit("No density components were found with the requested settings.")
    labels, sizes = np.unique(non_noise, return_counts=True)
    size_by_label = {int(label): int(size) for label, size in zip(labels, sizes)}
    main_label = max(size_by_label, key=size_by_label.get)
    selected_labels = [label for label, size in size_by_label.items()
                       if label != main_label and size >= minimum_family_size]
    selected_labels.sort(key=lambda label: tuple(np.mean(
        coordinates[raw_labels == label], axis=0)))
    family_by_raw = {label: "detached_family_%02d" % (index + 1)
                     for index, label in enumerate(selected_labels)}

    membership = table[[
        "source_key", "source_id", "dataset", "final_primary_tag",
        "final_secondary_tags", "recommended_period_days",
        "combined_umap_1", "combined_umap_2"]].copy()
    membership["umap_density_component"] = -999
    membership.loc[finite_mask, "umap_density_component"] = raw_labels
    membership["umap_detached_family"] = "unassigned"
    membership["umap_region_type"] = "missing_coordinates"
    membership.loc[finite_mask, "umap_region_type"] = "density_noise_or_small_component"
    main_rows = finite_mask.copy()
    main_rows.loc[finite_mask] = raw_labels == main_label
    membership.loc[main_rows, "umap_region_type"] = "connected_main_body"
    core_local = np.zeros(len(coordinates), dtype=bool)
    core_local[np.asarray(model.core_sample_indices_, dtype=int)] = True
    membership["umap_density_core_point"] = False
    membership.loc[finite_mask, "umap_density_core_point"] = core_local
    for raw_label, family in family_by_raw.items():
        selected = finite_mask.copy()
        selected.loc[finite_mask] = raw_labels == raw_label
        membership.loc[selected, "umap_detached_family"] = family
        membership.loc[selected, "umap_region_type"] = "detached_density_family"
    membership["phase_fold_plot"] = membership["source_id"].astype(str).map(
        lambda value: _plots._source_phase_plot_path(version_dir, _utils.clean_source_id(value)))
    membership["detached_family_plot_link"] = ""
    membership["detached_family_plot_status"] = "not_in_retained_family"

    summaries: List[Dict[str, Any]] = []
    for raw_label, family in family_by_raw.items():
        selected_local = raw_labels == raw_label
        selected_global = membership["umap_detached_family"].eq(family)
        block = coordinates[selected_local]
        summaries.append({
            "umap_detached_family": family,
            "n_sources": int(selected_local.sum()),
            "n_core_sources": int(core_local[selected_local].sum()),
            "centroid_umap_1": float(block[:, 0].mean()),
            "centroid_umap_2": float(block[:, 1].mean()),
            "minimum_umap_1": float(block[:, 0].min()),
            "maximum_umap_1": float(block[:, 0].max()),
            "minimum_umap_2": float(block[:, 1].min()),
            "maximum_umap_2": float(block[:, 1].max()),
            "dominant_existing_category": str(membership.loc[
                selected_global, "final_primary_tag"].value_counts().index[0]),
            "dbscan_eps": eps,
            "dbscan_min_samples": min_samples,
            "minimum_retained_family_size": minimum_family_size,
        })
    summary = pd.DataFrame(summaries, columns=[
        'umap_detached_family', 'n_sources', 'n_core_sources',
        'centroid_umap_1', 'centroid_umap_2', 'minimum_umap_1',
        'maximum_umap_1', 'minimum_umap_2', 'maximum_umap_2',
        'dominant_existing_category', 'dbscan_eps', 'dbscan_min_samples',
        'minimum_retained_family_size'])
    cross = pd.crosstab(
        membership["umap_detached_family"], membership["final_primary_tag"],
        margins=True).reset_index()
    tables = version_dir / "tables"
    _utils.atomic_write_csv(cross, tables / "umap_detached_family_vs_morphology.csv")

    family_root = _persistence.figure_directory(version_dir) / "umap_detached_families"
    family_root.mkdir(parents=True, exist_ok=True)
    for family in family_by_raw.values():
        directory = family_root / family
        directory.mkdir(parents=True, exist_ok=True)
        plot_directory = directory / "plots"
        plot_directory.mkdir(parents=True, exist_ok=True)
        family_indices = membership.index[
            membership["umap_detached_family"].eq(family)].tolist()
        linked = 0
        missing = 0
        failed = 0
        for row_index in family_indices:
            source = Path(str(membership.at[row_index, "phase_fold_plot"]))
            if not source.is_file():
                membership.at[row_index, "detached_family_plot_status"] =\
                    "source_phase_plot_missing"
                missing += 1
                continue
            destination = plot_directory / source.name
            status = ""
            if destination.exists():
                try:
                    status = "existing_hardlink" if os.path.samefile(
                        str(source), str(destination)) else "destination_already_exists"
                except OSError:
                    status = "destination_already_exists"
            else:
                try:
                    # Hard links expose the image in the family folder without
                    # allocating a second copy of its pixel data.
                    os.link(str(source), str(destination))
                    status = "hardlinked"
                except OSError:
                    # Never fall back to copying thousands of images: that was
                    # the cause of the earlier disk-space failure.
                    status = "hardlink_failed_no_copy_made"
            membership.at[row_index, "detached_family_plot_status"] = status
            if status in {"hardlinked", "existing_hardlink"}:
                membership.at[row_index, "detached_family_plot_link"] = str(destination)
                linked += 1
            else:
                failed += 1
        family_members = membership.loc[family_indices].copy()
        _utils.atomic_write_csv(family_members, directory / "members.csv")
        if not summary.empty:
            summary.loc[summary["umap_detached_family"].eq(family),
                        "n_linked_phase_plots"] = linked
            summary.loc[summary["umap_detached_family"].eq(family),
                        "n_missing_phase_plots"] = missing
            summary.loc[summary["umap_detached_family"].eq(family),
                        "n_failed_phase_plot_links"] = failed
        logger.info("%s: %d phase plots hardlinked, %d missing, %d failed",
                    family, linked, missing, failed)
    _utils.atomic_write_csv(membership, tables / "umap_detached_family_membership.csv")
    _utils.atomic_write_csv(summary, tables / "umap_detached_family_summary.csv")
    _utils.atomic_write_csv(summary, family_root / "active_family_index.csv")
    addon_models = version_dir / "models" / "additions"
    addon_models.mkdir(parents=True, exist_ok=True)
    joblib.dump({
        "model": model,
        "coordinate_columns": ["combined_umap_1", "combined_umap_2"],
        "eps": eps,
        "min_samples": min_samples,
        "minimum_family_size": minimum_family_size,
        "main_component": int(main_label),
        "retained_family_by_component": family_by_raw,
        "scientific_scope": (
            "Detached 2-D UMAP density regions only; not a replacement morphology classifier."),
    }, addon_models / "detached_umap_density_families.joblib", compress=3)
    _plots.make_detached_family_map(
        membership, version_dir, "umap_detached_family",
        "all_families_combined_detached_umap_families")
    logger.info(
        "Saved %d detached UMAP families (eps=%.4g, min_samples=%d, min_size=%d); "
        "the existing UMAP and classifications were not changed",
        len(family_by_raw), eps, min_samples, minimum_family_size)
    return {
        "version_dir": str(version_dir),
        "n_detached_families": len(family_by_raw),
        "eps": eps,
        "minimum_family_size": minimum_family_size,
    }


def classify_only(config: Dict[str, Any], args: argparse.Namespace) -> Dict[str, Any]:
    """Extract and classify any sample size without fitting an embedding."""
    directory = Path(config["output_root"]) / "classification"
    _persistence.ensure_structure(directory)
    logger = _utils.setup_logging(directory, args.verbose)
    specs = [d for d in config.get("datasets", []) if d.get("process", True)]
    sources, problems = _loading.load_lightcurves(specs, config, logger)
    periods, conflicts = _loading.read_period_tables(specs, config, logger)
    records, failures = _features.extract_all_features(sources, periods, config, directory, logger)
    if not records:
        raise SystemExit("No usable sources produced morphology features. See input and period tables.")
    table = _classify.classify_table(_classify.assemble_table(records, config, {}), {}, config)
    manual = Path(config.get("manual_labels_file") or Path(config["output_root"]) / "manual_labels.csv")
    _classify.ensure_manual_labels_file(manual)
    table = _classify.apply_labels(table, _classify.load_manual_labels(manual))
    table = _outputs.add_traceability_columns(table, config)
    folds, missing = _plots.generate_phase_fold_products(sources, table, directory, config, logger, force=True)
    memberships, missing_links = _outputs.build_category_folders(table, folds, {}, directory, config, logger)
    _outputs.write_tables(table, directory, {
        "load_problems": problems, "processing_failures": failures,
        "period_table_conflicts": conflicts, "missing_phase_fold_plots": missing,
        "missing_phase_fold_plot_links": missing_links, "category_memberships": memberships,
        "flare_event_validation": _classify.flare_event_validation_table(records, table, directory),
    }, config)
    _utils.atomic_write_json(config, directory / "resolved_config.json")
    logger.info("Morphology plots: %s", _persistence.figure_directory(directory))
    logger.info("Classified %d sources without fitting UMAP; outputs under %s", len(table), directory)
    return {"n_sources": len(table), "output_dir": str(directory)}
