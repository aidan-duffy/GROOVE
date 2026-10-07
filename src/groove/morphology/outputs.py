from __future__ import annotations
import logging
import os
import shutil
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
import numpy as np
import pandas as pd
from . import classify as _classify
from . import loading as _loading
from . import utils as _utils




# ===========================================================================
# OUTPUT FOLDERS
# ===========================================================================


def build_existing_plot_index(specs: Sequence[Mapping[str, Any]],
                              logger: logging.Logger) -> Dict[str, Path]:
    index: Dict[str, Path] = {}
    for spec in specs:
        for directory in spec.get("existing_plot_directories", []):
            path = Path(str(directory))
            if not path.exists():
                continue
            for image in path.rglob("*.png"):
                key = _loading.source_id_from_path(image)
                if key and key not in index:
                    index[key] = image
    logger.info("Indexed %d existing period plots", len(index))
    return index


def mark_sources_with_existing_plots(sources: Mapping[str, Dict[str, Any]],
                                     specs: Sequence[Mapping[str, Any]],
                                     logger: logging.Logger) -> Dict[str, Path]:
    """Use existing LS diagnostics only to avoid duplicating heavy feature caches.

    These paths are never used as morphology-output images.
    """
    index = build_existing_plot_index(specs, logger)
    for source in sources.values():
        source_id = str(source.get("source_id", ""))
        existing = index.get(source_id)
        source["existing_period_plot"] = str(existing) if existing is not None else ""
    logger.info("%d/%d loaded sources have external LS diagnostics; retaining compact caches",
                sum(bool(source.get("existing_period_plot")) for source in sources.values()),
                len(sources))
    return index


def link_or_copy(source: Path, destination: Path, allow_copy: bool = False) -> bool:
    """Create a zero-duplication hard link, optionally copying across volumes.

    A full disk must never trigger a second attempt to copy the image: that was
    the cause of the previous failed large run.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        return True
    try:
        os.link(str(source), str(destination))
        return True
    except (OSError, NotImplementedError):
        if not allow_copy:
            return False
    try:
        shutil.copy2(str(source), str(destination))
        return True
    except OSError:
        return False


def build_category_folders(table: pd.DataFrame, fold_paths: Mapping[str, Path],
                           plot_index: Mapping[str, Path], version_dir: Path,
                           config: Mapping[str, Any], logger: logging.Logger
                           ) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Keep one viewable source image in its primary family folder.

    Secondary tags and review groupings are table-only.  In the normal
    morphology workflow ``fold_paths`` contains accepted-band phase folds; reruns
    preserve correct hard links and fill only missing entries.
    """
    root = Path(version_dir) / "category_folds"
    interest_root = Path(version_dir) / "interest"
    allow_copy = bool(config.get("allow_plot_copy_fallback", False))
    missing: List[Dict[str, Any]] = []
    memberships: List[Dict[str, Any]] = []
    linked = 0
    existing_primary: Dict[str, List[Path]] = {}
    existing_interest: Dict[str, List[Path]] = {}
    primary_root = root / "primary"
    if primary_root.exists():
        for path in primary_root.glob("*/*.png"):
            source_token = path.name.split("__", 1)[0]
            existing_primary.setdefault(source_token, []).append(path)
    for active_interest_dir in (interest_root / "exotic_candidates",
                                interest_root / "manually_confirmed_exotic"):
        if active_interest_dir.exists():
            for path in active_interest_dir.glob("*.png"):
                source_token = path.name.split("__", 1)[0]
                existing_interest.setdefault(source_token, []).append(path)

    for _, row in table.iterrows():
        key = str(row["source_key"])
        source_id = str(row["source_id"])
        source_token = _utils.safe_name(source_id)
        primary = str(row["final_primary_tag"])
        # Category and interest folders are morphology products, so their one
        # per-source image is always the generated accepted-band phase fold.  The
        # ``plot_index`` argument remains only for call compatibility and can
        # never supply an LS-periodogram image here.
        canonical = fold_paths.get(key)
        suffix = "phase_fold"
        destination = primary_root / _utils.safe_name(primary) / (
            "%s__%s.png" % (source_token, suffix))
        for stale in existing_primary.get(source_token, []):
            if stale != destination and stale.exists():
                try:
                    stale.unlink()
                except OSError:
                    pass
        linked_ok = bool(canonical is not None and Path(canonical).exists()
                         and link_or_copy(Path(canonical), destination, allow_copy))
        if linked_ok:
            linked += 1
        else:
            missing.append({"source_id": source_id, "dataset": row["dataset"],
                            "reason": "no_generated_phase_fold"})
        memberships.append({
            "source_id": source_id, "source_key": key, "dataset": row["dataset"],
            "group_type": "primary", "group_name": primary,
            "plot_path": str(destination) if linked_ok else "",
        })
        for tag in _utils.split_tags(row.get("final_secondary_tags", "")):
            memberships.append({
                "source_id": source_id, "source_key": key, "dataset": row["dataset"],
                "group_type": "secondary", "group_name": tag,
                "plot_path": str(destination) if linked_ok else "",
            })
        interest_name = {
            "exotic_candidate": "exotic_candidates",
            "manually_confirmed_exotic": "manually_confirmed_exotic",
        }.get(str(row.get("interest_status", "")))
        intended_interest_destination = None
        if interest_name:
            interest_destination = interest_root / interest_name / (
                "%s__%s.png" % (source_token, suffix))
            intended_interest_destination = interest_destination
            if canonical is not None and Path(canonical).exists():
                link_or_copy(Path(canonical), interest_destination, allow_copy)
            memberships.append({
                "source_id": source_id, "source_key": key, "dataset": row["dataset"],
                "group_type": "interest", "group_name": interest_name,
                "plot_path": str(interest_destination) if interest_destination.exists() else "",
            })
        for stale in existing_interest.get(source_token, []):
            if stale != intended_interest_destination and stale.exists():
                try:
                    stale.unlink()
                except OSError:
                    pass

        tags = set(_utils.split_tags(row.get("final_secondary_tags", "")))
        reasons = set(_utils.split_tags(row.get("review_reason", "")))
        review_groups: List[str] = []
        if (row.get("final_primary_tag") == "transit"
                and _utils.finite_float(row.get("final_confidence"), 0.0) >= 0.75):
            review_groups.append("transit_high_confidence")
        mappings = {
            "transit_wave_ambiguous": "transit_wave_ambiguous",
            "alias_possible": "transit_alias_sensitive",
            "alias_period": "period_alias_sensitive",
            "seasonal_phase_coupling": "transit_rejected_seasonal",
            "broad_occultation": "broad_occultation_candidates",
            "double_dip": "double_dip_candidates",
            "single_section_dimming": "single_section_dimming",
            "gappy_phase_coverage": "gappy_phase_coverage",
            "poor_point_driven": "poor_point_driven",
            "temporally_evolving": "temporally_evolving",
            "out_of_distribution_shape": "out_of_distribution",
        }
        for marker, folder_name in mappings.items():
            if marker in tags or marker in reasons:
                review_groups.append(folder_name)
        for folder_name in dict.fromkeys(review_groups):
            memberships.append({
                "source_id": source_id, "source_key": key, "dataset": row["dataset"],
                "group_type": "review", "group_name": folder_name,
                "plot_path": str(destination) if linked_ok else "",
            })
    logger.info("Primary category folders contain %d source links under %s", linked, root)
    return (pd.DataFrame(memberships),
            pd.DataFrame(missing, columns=["source_id", "dataset", "reason"]))


def add_traceability_columns(table: pd.DataFrame,
                             config: Mapping[str, Any]) -> pd.DataFrame:
    """Add diagnostics that do not participate in classification or UMAP."""
    table = table.copy()
    table["strength_raw"] = [_classify.strength_score(row) for _, row in table.iterrows()]
    table["strength_percentile_within_family"] = (
        table.groupby("final_primary_tag")["strength_raw"]
        .rank(method="average", pct=True).fillna(0.0))
    filters = table.get("filters_used", pd.Series("", index=table.index)).fillna("")
    table["single_band_source"] = filters.map(lambda value: len(_utils.split_tags(value)) <= 1)
    coverage = pd.to_numeric(
        table.get("phase_coverage", pd.Series(np.nan, index=table.index)),
        errors="coerce")
    table["low_phase_coverage"] = coverage.lt(
        float(config.get("minimum_phase_coverage", 0.30)))
    return table


def summary_tables(table: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    out: Dict[str, pd.DataFrame] = {}
    out["category_summary"] = (
        table.groupby("final_primary_tag")
        .agg(n_sources=("source_key", "count"),
             median_confidence=("final_confidence", "median"),
             median_period_days=("recommended_period_days", "median"),
             median_profile_chi2=("profile_chi2", "median"),
             n_needing_review=("needs_review", "sum"))
        .reset_index().sort_values("n_sources", ascending=False))
    out["dataset_summary"] = (
        table.groupby(["dataset", "final_primary_tag"])
        .size().rename("n_sources").reset_index())
    tags: Dict[str, int] = {}
    for value in table["final_secondary_tags"]:
        for tag in _utils.split_tags(value):
            tags[tag] = tags.get(tag, 0) + 1
    out["tag_summary"] = pd.DataFrame(
        sorted(tags.items(), key=lambda kv: -kv[1]), columns=["tag", "n_sources"])
    family_tag_rows = [
        {"final_primary_tag": row["final_primary_tag"], "tag": tag}
        for _, row in table.iterrows()
        for tag in _utils.split_tags(row.get("final_secondary_tags", ""))]
    if family_tag_rows:
        out["family_tag_crosstab"] = pd.crosstab(
            pd.DataFrame(family_tag_rows)["final_primary_tag"],
            pd.DataFrame(family_tag_rows)["tag"]).reset_index()
    else:
        out["family_tag_crosstab"] = pd.DataFrame(columns=["final_primary_tag"])
    unknown_reasons: Dict[str, int] = {}
    unknown = table.loc[table["final_primary_tag"].eq("unknown")]
    for _, row in unknown.iterrows():
        reasons = set(_utils.split_tags(row.get("final_secondary_tags", "")))
        reasons.update(_utils.split_tags(row.get("review_reason", "")))
        if not reasons:
            reasons.add("untagged_unknown")
        for reason in reasons:
            unknown_reasons[reason] = unknown_reasons.get(reason, 0) + 1
    out["unknown_reason_breakdown"] = pd.DataFrame(
        sorted(unknown_reasons.items(), key=lambda item: -item[1]),
        columns=["reason", "n_unknown_sources"])
    alias_mask = table.get(
        "alias_period", pd.Series(False, index=table.index)).fillna(False).astype(bool)
    alias_rows = []
    for category, block in table.groupby("final_primary_tag", sort=False):
        block_alias = alias_mask.loc[block.index]
        alias_rows.append({
            "final_primary_tag": category,
            "n_sources": int(len(block)),
            "n_alias_period": int(block_alias.sum()),
            "alias_fraction": float(block_alias.mean()) if len(block) else 0.0,
        })
    out["alias_period_summary"] = pd.DataFrame(alias_rows).sort_values(
        "n_alias_period", ascending=False)
    quality_columns = [column for column in (
        "source_id", "source_key", "dataset", "final_primary_tag", "filters_used",
        "single_band_source", "phase_coverage", "low_phase_coverage",
        "period_search_period_days", "morphology_period_days", "period_ratio_used",
        "period_choice_reason", "harmonic_ambiguous", "alias_period")
        if column in table.columns]
    quality_mask = pd.Series(False, index=table.index)
    for column in ("single_band_source", "low_phase_coverage", "harmonic_ambiguous",
                   "alias_period"):
        if column in table.columns:
            quality_mask |= table[column].fillna(False).astype(bool)
    out["coverage_and_period_flags"] = table.loc[quality_mask, quality_columns]
    out["review_queue"] = table.loc[_utils.bool_series(table["needs_review"])][
        ["source_id", "dataset", "final_primary_tag", "final_confidence",
         "interest_status", "interest_reasons", "review_reason", "rule_fired"]]
    out["interest_summary"] = (
        table.groupby("interest_status")
        .agg(n_sources=("source_key", "count"),
             median_interest_confidence=("interest_confidence", "median"),
             median_exotic_candidate_score=("exotic_candidate_score", "median"))
        .reset_index().sort_values("n_sources", ascending=False))
    exotic_columns = [name for name in (
        "source_id", "dataset", "final_primary_tag", "final_secondary_tags",
        "interest_status", "interest_reasons", "interest_confidence",
        "exotic_candidate_score", "morphology_confidence", "review_reason")
        if name in table.columns]
    out["exotic_candidates"] = table.loc[
        table["interest_status"].eq("exotic_candidate"), exotic_columns].sort_values(
            "exotic_candidate_score", ascending=False)
    transit_columns = [name for name in (
        "source_id", "dataset", "final_primary_tag", "final_secondary_tags",
        "morphology_confidence", "coherent_dimming_score", "dip_significance",
        "dip_duty_cycle", "dip_supporting_cycles", "dip_covered_cycles",
        "dip_cycle_support_fraction", "dip_independent_nights",
        "dip_supporting_time_sections", "dip_local_contrast_sigma",
        "phase_time_section_dependence", "dip_section_concentration",
        "dip_single_section_fraction", "phase_coverage_near_dip",
        "phase_coverage_outside_dip", "dip_point_quality_fraction",
        "dip_cycle_contrast_scatter",
        "wave_model_score", "dimming_model_score", "wave_dimming_score_margin",
        "review_reason") if name in table.columns]
    out["transit_diagnostics"] = table.loc[
        table["final_primary_tag"].eq("transit"), transit_columns].sort_values(
            "coherent_dimming_score", ascending=False)
    tag_text = table["final_secondary_tags"].fillna("").astype(str)
    out["transit_ambiguous"] = table.loc[
        tag_text.str.contains(r"(?:^|;)transit_wave_ambiguous(?:;|$)", regex=True), transit_columns]
    seasonal_mask = (tag_text.str.contains("seasonal_phase_coupling", regex=False)
                     | tag_text.str.contains("single_section_dimming", regex=False)
                     | tag_text.str.contains("gappy_phase_coverage", regex=False)
                     | tag_text.str.contains("poor_point_driven", regex=False))
    out["seasonal_false_positive_candidates"] = table.loc[seasonal_mask, transit_columns]
    irregular_columns = [name for name in (
        "source_id", "dataset", "final_secondary_tags", "morphology_confidence",
        "irregular_variability_score", "temporal_coherence_score", "von_neumann_ratio",
        "raw_time_lag1_correlation", "same_direction_excursion_groups",
        "section_median_range_sigma", "evolution_raw_score",
        "minimum_section_correlation", "maximum_section_distance", "interest_status",
        "interest_reasons", "review_reason") if name in table.columns]
    out["irregular_variable_summary"] = table.loc[
        table["final_primary_tag"].eq("irregular_variable"), irregular_columns]
    neighbour_columns = [name for name in (
        "source_id", "dataset", "final_primary_tag", "nearest_original_feature_source_id",
        "nearest_original_feature_distance", "nearest_umap_source_id",
        "nearest_umap_distance", "nearest_neighbour_category_agreement")
        if name in table.columns]
    out["umap_neighbour_validation"] = table[neighbour_columns].copy()
    return out


def write_membership_manifests(table: pd.DataFrame, memberships: pd.DataFrame,
                               tables: Path) -> None:
    if memberships is None or memberships.empty:
        return
    detail_columns = [column for column in (
        "source_key", "final_primary_tag", "final_secondary_tags", "final_confidence",
        "interest_status", "interest_reasons", "needs_review", "review_reason",
        "strength_raw", "strength_percentile_within_family") if column in table.columns]
    details = table[detail_columns].drop_duplicates("source_key")
    enriched = memberships.merge(details, on="source_key", how="left")
    directory_names = {
        "secondary": "secondary_tags",
        "review": "review_groups",
        "interest": "interest_groups",
    }
    index_rows: List[Dict[str, Any]] = []
    for group_type, directory_name in directory_names.items():
        directory = tables / directory_name
        directory.mkdir(parents=True, exist_ok=True)
        active_files = set()
        subset = enriched.loc[enriched["group_type"].eq(group_type)]
        for group_name, block in subset.groupby("group_name", sort=True):
            filename = "%s.csv" % _utils.safe_name(group_name)
            active_files.add(filename)
            _utils.atomic_write_csv(block, directory / filename)
            index_rows.append({"group_type": group_type, "group_name": group_name,
                               "n_sources": int(len(block)),
                               "table_path": str(directory / filename)})
        for stale in directory.glob("*.csv"):
            if stale.name not in active_files:
                try:
                    stale.unlink()
                except OSError:
                    pass
    _utils.atomic_write_csv(pd.DataFrame(index_rows, columns=[
        "group_type", "group_name", "n_sources", "table_path"]),
        tables / "membership_table_index.csv")


def write_blind_validation_sample(table: pd.DataFrame, memberships: Optional[pd.DataFrame],
                                  version_dir: Path,
                                  config: Mapping[str, Any]) -> None:
    if not bool(config.get("write_validation_sample", True)) or table.empty:
        return
    tables = Path(version_dir) / "tables"
    sample_path = tables / "blind_validation_sample.csv"
    key_path = tables / "blind_validation_key.csv"
    desired = min(int(config.get("validation_sample_size", 200)), len(table))
    previous = _loading.read_table(sample_path)
    retained_keys = [key for key in previous.get(
        "source_key", pd.Series(dtype=str)).astype(str).tolist()
        if key in set(table["source_key"].astype(str))][:desired]
    remaining = table.loc[~table["source_key"].astype(str).isin(retained_keys)]
    needed = desired - len(retained_keys)
    if needed > 0:
        chosen = remaining.sample(
            n=min(needed, len(remaining)),
            random_state=int(config.get("random_seed", 42)))["source_key"].astype(str).tolist()
        retained_keys.extend(chosen)
    lookup = table.set_index(table["source_key"].astype(str), drop=False)
    selected = lookup.loc[retained_keys].copy().reset_index(drop=True)
    paths: Dict[str, str] = {}
    if memberships is not None and not memberships.empty:
        primary = memberships.loc[memberships["group_type"].eq("primary")]
        paths = dict(zip(primary["source_key"].astype(str), primary["plot_path"].astype(str)))
    sample = selected[["source_id", "source_key", "dataset"]].copy()
    sample["plot_path"] = sample["source_key"].astype(str).map(paths).fillna("")
    annotation_columns = ("reviewer_label", "reviewer_confidence", "reviewer_notes")
    previous_annotations = previous.set_index("source_key") if not previous.empty\
        and "source_key" in previous.columns else pd.DataFrame()
    for column in annotation_columns:
        if not previous_annotations.empty and column in previous_annotations.columns:
            sample[column] = sample["source_key"].map(previous_annotations[column]).fillna("")
        else:
            sample[column] = ""
    _utils.atomic_write_csv(sample, sample_path)
    key_columns = [column for column in (
        "source_id", "source_key", "dataset", "final_primary_tag",
        "final_secondary_tags", "final_confidence", "interest_status",
        "review_reason", "rule_fired") if column in selected.columns]
    _utils.atomic_write_csv(selected[key_columns], key_path)


def write_tables(table: pd.DataFrame, version_dir: Path, extra: Mapping[str, pd.DataFrame],
                 config: Mapping[str, Any]) -> None:
    tables = Path(version_dir) / "tables"
    tables.mkdir(parents=True, exist_ok=True)
    _utils.atomic_write_csv(table, tables / "all_sources.csv")
    if "is_reference" in table.columns:
        _utils.atomic_write_csv(table.loc[_utils.bool_series(table["is_reference"])],
                         tables / "reference_sources.csv")
        _utils.atomic_write_csv(table.loc[_utils.bool_series(table["is_latest_batch"])],
                         tables / "latest_batch.csv")
    for name, frame in summary_tables(table).items():
        _utils.atomic_write_csv(frame, tables / ("%s.csv" % name))
    for name, frame in extra.items():
        if frame is not None and (len(frame) or name in {
                "missing_period_plots", "flare_event_validation"}):
            _utils.atomic_write_csv(frame, tables / ("%s.csv" % name))
    memberships = extra.get("category_memberships")
    if isinstance(memberships, pd.DataFrame):
        write_membership_manifests(table, memberships, tables)
    write_blind_validation_sample(
        table, memberships if isinstance(memberships, pd.DataFrame) else None,
        version_dir, config)
