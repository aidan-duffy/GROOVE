from __future__ import annotations
import tempfile
import warnings
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
import joblib
import numpy as np
import pandas as pd
from . import settings as S
from . import classify as _classify
from . import embedding as _embedding
from . import features as _features
from . import modes as _modes
from . import persistence as _persistence
from . import utils as _utils




# ===========================================================================
# SMOKE TEST
# ===========================================================================


def synthetic_lightcurve(kind: str, period: float, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    # ATLAS-like sampling: several exposures per night, nights spread over years
    nights = 58000.0 + np.sort(rng.uniform(0.0, 3000.0, 380))
    t = np.sort(np.concatenate([
        night + rng.uniform(0.0, 0.03, 4) for night in nights]))
    n = len(t)
    noise = 0.02
    phase = np.mod(t / period, 1.0)
    m = np.full(n, 14.0)
    err = np.full(n, noise)
    if kind == "smooth_sine":
        m += 0.20 * np.sin(2 * np.pi * phase)
    elif kind == "asymmetric_wave":
        m += 0.20 * np.sin(2 * np.pi * phase) + 0.12 * np.sin(4 * np.pi * phase + 0.9)
    elif kind == "clean_eclipse":
        d = np.minimum(np.abs(phase - 0.5), 1 - np.abs(phase - 0.5))
        m += 0.9 * np.exp(-(d / 0.05) ** 2)
    elif kind == "broad_dust_occultation":
        d = np.minimum(np.abs(phase - 0.5), 1 - np.abs(phase - 0.5))
        m += 0.45 * np.exp(-(d / 0.16) ** 2)
    elif kind == "asymmetric_broad_occultation":
        signed = (phase - 0.5 + 0.5) % 1.0 - 0.5
        width = np.where(signed < 0, 0.08, 0.22)
        m += 0.55 * np.exp(-(signed / width) ** 2)
    elif kind == "unusual_double_dip":
        d1 = _features._circular_phase_distance(phase, 0.42)
        d2 = _features._circular_phase_distance(phase, 0.62)
        m += 0.85 * np.exp(-(d1 / 0.035) ** 2)
        m += 0.72 * np.exp(-(d2 / 0.045) ** 2)
    elif kind == "ambiguous_wave_dip":
        d = _features._circular_phase_distance(phase, 0.55)
        m += (0.14 * np.sin(2 * np.pi * (phase - 0.30))
              + 0.22 * np.exp(-(d / 0.20) ** 2))
    elif kind == "periodic_brightening":
        d = np.minimum(np.abs(phase - 0.35), 1 - np.abs(phase - 0.35))
        m -= 0.55 * np.exp(-(d / 0.05) ** 2)
    elif kind == "grouped_raw_time_flares":
        for _ in range(8):
            night_index = int(rng.integers(0, len(nights)))
            start = 4 * night_index
            m[start:start + 3] -= rng.uniform(0.5, 1.2)
    elif kind == "seasonal_gaps_bad_points":
        section = _features.chronological_sections(t, 4)
        candidate = (section == 3) & (_features._circular_phase_distance(phase, 0.5) < 0.06)
        chosen = np.flatnonzero(candidate)[:6]
        m[chosen] += 0.8
        err[chosen] = 0.35
        # Couple phase and season by retaining only a broad phase interval in
        # each chronological quarter.
        keep = np.array([_features._circular_phase_distance(np.asarray([p]), 0.2 * s)[0] < 0.20
                         for p, s in zip(phase, section)])
        t, m, err, phase = t[keep], m[keep], err[keep], phase[keep]
        n = len(t)
    elif kind == "single_section_dimming":
        section = _features.chronological_sections(t, 4)
        candidate = (section == 3) & (_features._circular_phase_distance(phase, 0.5) < 0.08)
        m[candidate] += 0.65
    elif kind == "random_isolated_outliers":
        chosen = rng.choice(n, size=10, replace=False)
        m[chosen] += rng.choice([-1.0, 1.0], size=len(chosen)) * rng.uniform(0.6, 1.2, len(chosen))
    elif kind == "irregular_correlated":
        states = np.zeros(len(nights))
        for i in range(1, len(states)):
            states[i] = 0.92 * states[i - 1] + rng.normal(0, 0.08)
        m += np.repeat(states, 4)[:n]
    elif kind == "evolving_sine":
        section = _features.chronological_sections(t, 4)
        m += np.where(section < 2,
                      0.20 * np.sin(2 * np.pi * phase),
                      0.18 * np.sin(2 * np.pi * phase + 1.6))
        late_dip = (section >= 3) & (_features._circular_phase_distance(phase, 0.55) < 0.08)
        m[late_dip] += 0.35
    elif kind == "nonvar":
        pass
    elif kind == "incoherent_noisy":
        m += rng.standard_t(2, n) * 0.35
    m = m + rng.normal(0, noise, n)
    # These fixtures use one band; the separate demo exercises both bands.
    band = np.full(n, "o")
    return pd.DataFrame({"time": t, "mag": m, "err": err, "filter": band})


def smoke_test(verbose: bool = False) -> int:
    logger = _utils.setup_logging(None, verbose)
    config = dict(S.DEFAULTS)
    config["thresholds"] = dict(S.DEFAULTS["thresholds"])
    cases = [
        ("clean_eclipse", 1.7, {"transit"}, {"narrow_eclipse"}, None),
        ("broad_dust_occultation", 5.5, {"transit"}, {"broad_occultation"}, None),
        ("asymmetric_broad_occultation", 7.2, {"transit"},
         {"broad_occultation", "asymmetric_occultation"}, None),
        ("unusual_double_dip", 3.8, {"transit"},
         {"double_dip", "complex_occultation"}, "exotic_candidate"),
        ("smooth_sine", 3.1, {"wavelike"}, set(), None),
        ("asymmetric_wave", 4.3, {"wavelike"}, {"asymmetric"}, None),
        ("ambiguous_wave_dip", 6.1, {"transit", "wavelike"},
         {"transit_wave_ambiguous"}, None),
        ("seasonal_gaps_bad_points", 1.0, {"unknown", "noisy", "irregular_variable"},
         {"seasonal_phase_coupling", "gappy_phase_coverage", "poor_point_driven",
          "single_section_dimming"}, "review"),
        ("single_section_dimming", 4.8, {"unknown", "irregular_variable"},
         {"single_section_dimming"}, "review"),
        ("random_isolated_outliers", 2.7, {"nonvar", "noisy", "unknown"}, set(), None),
        ("grouped_raw_time_flares", 2.6, {"flaring"}, {"transient_flares"}, None),
        ("periodic_brightening", 3.3, {"wavelike"}, {"periodic_brightening"}, None),
        ("irregular_correlated", 8.0, {"irregular_variable"}, {"aperiodic_variable"}, None),
        ("evolving_sine", 4.0, {"irregular_variable"},
         {"temporally_evolving", "evolving_periodic"}, "review"),
        ("nonvar", 2.9, {"nonvar"}, set(), None),
        ("incoherent_noisy", 2.2, {"noisy"}, set(), None),
    ]
    metadata = {"evolution_threshold": 1.5}
    failures = 0
    records: List[Dict[str, Any]] = []
    results: List[Dict[str, Any]] = []
    print("%-30s %-23s %-23s %s" % ("case", "expected", "got", "why"))
    print("-" * 125)
    for index, (kind, period, expected, required_tags, expected_interest) in enumerate(cases):
        frame = synthetic_lightcurve(kind, period, seed=index)
        source = {"source_key": kind, "source_id": kind, "dataset": "smoke",
                  "data": frame, "input_filename": kind, "file_fingerprint": "0"}
        record = _features.extract_source_features(source, {"recommended_period_days": period}, config)
        row = dict(record["summary"])
        row["out_of_distribution_score"] = 0.0
        result = _classify.suggest_morphology(row, metadata, config)
        record["summary"] = row
        records.append(record)
        results.append(result)
        got = result["suggested_primary_tag"]
        tags = set(_utils.split_tags(result["suggested_secondary_tags"]))
        # Review artefacts may express one of several related sampling defects;
        # all other cases require every listed tag.
        tag_ok = bool(tags & required_tags) if kind == "seasonal_gaps_bad_points"\
            else required_tags.issubset(tags)
        interest_ok = expected_interest is None or result["interest_status"] == expected_interest
        ok = got in expected and tag_ok and interest_ok
        if not ok:
            failures += 1
        print("%-30s %-23s %-23s %s" % (
            kind, "/".join(sorted(expected)), ("OK  " if ok else "FAIL") + " " + got,
            result["rule_fired"][:55]))

    # Methodological regression checks.
    checks: List[Tuple[str, bool]] = []
    checks.append(("both filters enabled by default", config["use_c_band"] and config["use_o_band"]))
    weighted_config = dict(config)
    weighted_config["feature_weights"] = dict(S.DEFAULT_FEATURE_WEIGHTS)
    weights, groups = _embedding.post_scaling_feature_weights(
        ["aligned_phase_bin_00", "log_amplitude"], weighted_config)
    unweighted_delta = np.asarray([1.0, 1.0])
    checks.append(("post-scaling block weights reduce distance",
                   np.linalg.norm(unweighted_delta * weights) < np.linalg.norm(unweighted_delta)
                   and weights[0] > weights[1] and groups == ["aligned_phase_profile", "amplitude"]))
    checks.append(("primary UMAP has no label input",
                   "targets" not in _embedding.fit_representation.__code__.co_varnames
                   and "targets" not in _embedding.fit_evidence_representation.__code__.co_varnames))

    matrix, names = _embedding.feature_matrix(records, "periodic")
    try:
        models = _embedding.fit_representation(matrix, config, logger, names=names, block="periodic")
        transformed, _ = _embedding.transform_representation(models, matrix[:3])
        checks.append(("all accepted sources remain in UMAP", len(models["embedding"]) == len(records)))
        checks.append(("saved-model transform returns every future source", transformed.shape == (3, 2)))
    except Exception as error:
        logger.error("Representation smoke check failed: %s", error)
        checks.extend([("all accepted sources remain in UMAP", False),
                       ("saved-model transform returns every future source", False)])
    labels = [r["suggested_primary_tag"] for r in results]
    checks.append(("nonvar/noisy are neither balanced nor removed",
                   len(labels) == len(cases) and "nonvar" in labels and "noisy" in labels))
    result_by_case = {case[0]: result for case, result in zip(cases, results)}
    record_by_case = {case[0]: record for case, record in zip(cases, records)}
    isolated_summary = record_by_case["random_isolated_outliers"]["summary"]
    grouped_record = record_by_case["grouped_raw_time_flares"]
    checks.append(("isolated excursions cannot create the flare family",
                   int(_utils.finite_float(isolated_summary.get("flare_event_count"), 0.0)) == 0
                   and result_by_case["random_isolated_outliers"][
                       "suggested_primary_tag"] != "flaring"))
    checks.append(("flare events retain an auditable validation table",
                   bool(grouped_record.get("event_rows"))
                   and any(_utils.bool_value(row.get("passes_quality_validation", False))
                           for row in grouped_record["event_rows"])))
    alias_result = result_by_case["seasonal_gaps_bad_points"]
    checks.append(("one-day aliases are tagged without automatic demotion",
                   "alias_period" in _utils.split_tags(alias_result["suggested_secondary_tags"])
                   and _utils.finite_float(alias_result["morphology_confidence"], 1.0) <= 0.60))
    changed = dict(config)
    changed["number_of_phase_bins"] = int(config["number_of_phase_bins"]) + 1
    checks.append(("feature-schema change requires refit",
                   _features.feature_config_hash(config) != _features.feature_config_hash(changed)))
    manual_table = pd.DataFrame([{
        "source_id": "manual", "source_key": "manual", "dataset": "smoke",
        "suggested_primary_tag": "nonvar", "suggested_secondary_tags": "",
        "suggested_interest_status": "routine", "interest_reasons": "",
        "interest_confidence": 0.5, "morphology_confidence": 0.5,
    }])
    manual = pd.DataFrame([{
        "source_id": "manual", "dataset": "smoke", "manual_primary_tag": "transit",
        "manual_secondary_tags": "reviewed", "manual_interest_status": "exotic_candidate",
        "manual_interest_reasons": "complex_occultation", "notes": "keep", "reviewer": "test",
    }])
    labelled = _classify.apply_labels(manual_table, manual)
    checks.append(("manual morphology and interest survive relabelling",
                   labelled.iloc[0]["final_primary_tag"] == "transit"
                   and labelled.iloc[0]["interest_status"] == "exotic_candidate"
                   and labelled.iloc[0]["manual_interest_reasons"] == "complex_occultation"))
    legacy_manual = manual.copy()
    legacy_manual.loc[0, "manual_primary_tag"] = "exotic"
    legacy_manual.loc[0, "manual_interest_status"] = ""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        legacy_labelled = _classify.apply_labels(manual_table, legacy_manual)
    checks.append(("legacy manual exotic conversion",
                   legacy_labelled.iloc[0]["final_primary_tag"] == "unknown"
                   and legacy_labelled.iloc[0]["interest_status"] == "manually_confirmed_exotic"
                   and bool(caught)))
    old_coordinates = pd.DataFrame({
        "source_key": ["old_a", "old_b"], "periodic_umap_1": [1.0, 2.0],
        "periodic_umap_2": [3.0, 4.0], "transient_umap_1": [5.0, 6.0],
        "transient_umap_2": [7.0, 8.0], "combined_umap_1": [9.0, 10.0],
        "combined_umap_2": [11.0, 12.0],
        "classification_evidence_umap_1": [13.0, 14.0],
        "classification_evidence_umap_2": [15.0, 16.0],
        "is_latest_batch": [True, True]})
    new_coordinates = pd.DataFrame({
        "source_key": ["new_c"], "periodic_umap_1": [17.0], "periodic_umap_2": [18.0],
        "transient_umap_1": [19.0], "transient_umap_2": [20.0],
        "combined_umap_1": [21.0], "combined_umap_2": [22.0],
        "classification_evidence_umap_1": [23.0],
        "classification_evidence_umap_2": [24.0],
        "is_latest_batch": [True]})
    merged = _embedding.merge_transformed_sources(old_coordinates, new_coordinates)
    coordinate_columns = [
        "periodic_umap_1", "periodic_umap_2", "transient_umap_1",
        "transient_umap_2", "combined_umap_1", "combined_umap_2",
        "classification_evidence_umap_1", "classification_evidence_umap_2"]
    checks.append(("transform preserves old coordinates", np.array_equal(
        merged.iloc[:2][coordinate_columns].to_numpy(),
        old_coordinates[coordinate_columns].to_numpy())))

    # End-to-end output/model integration in an isolated temporary version. No
    # completed user model or raw input is touched.
    try:
        with tempfile.TemporaryDirectory(prefix="morphology_v3_smoke_") as directory:
            version_dir = Path(directory) / "model_smoke_v3"
            _persistence.ensure_structure(version_dir)
            integration_config = dict(config)
            integration_config.update({"n_jobs": 1,
                                       "allow_plot_copy_fallback": False,
                                       "generate_missing_source_plots": True})
            integration_table = _classify.assemble_table(records, integration_config, metadata)
            fitted: Dict[str, Dict[str, Any]] = {}
            for block, prefix in (("periodic", "periodic_umap"),
                                  ("transient", "transient_umap")):
                block_matrix, block_names = _embedding.feature_matrix(records, block)
                fitted[block] = _embedding.fit_representation(
                    block_matrix, integration_config, logger, names=block_names,
                    block=block)
                fitted[block]["ood"] = _embedding.fit_ood_model(fitted[block]["model_space"], integration_config)
                integration_table["%s_1" % prefix] = fitted[block]["embedding"][:, 0]
                integration_table["%s_2" % prefix] = fitted[block]["embedding"][:, 1]
                if block == "periodic":
                    integration_table["out_of_distribution_score"] = _embedding.ood_scores(
                        fitted[block]["ood"], fitted[block]["model_space"])
                _persistence.save_models(version_dir, block, fitted[block])
            integration_table = _classify.classify_table(integration_table, metadata, integration_config)
            regression_columns = list((
                "suggested_primary_tag", "suggested_secondary_tags",
                "morphology_confidence", "suggestion_confidence",
                "suggested_interest_status", "interest_status", "interest_reasons",
                "interest_confidence", "exotic_candidate_score", "rule_fired",
                "needs_review", "review_reason") + S.CATEGORY_SCORE_COLUMNS)
            before_maps = integration_table[regression_columns].copy(deep=True)

            combined_matrix, combined_names = _embedding.feature_matrix(records, "combined")
            fitted["combined"] = _embedding.fit_representation(
                combined_matrix, integration_config, logger, names=combined_names,
                block="combined")
            fitted["combined"]["ood"] = _embedding.fit_ood_model(
                fitted["combined"]["model_space"], integration_config)
            integration_table["combined_umap_1"] = fitted["combined"]["embedding"][:, 0]
            integration_table["combined_umap_2"] = fitted["combined"]["embedding"][:, 1]
            _persistence.save_models(version_dir, "combined", fitted["combined"])

            fitted["classification_evidence"] = _embedding.fit_evidence_representation(
                integration_table, integration_config, logger)
            integration_table["classification_evidence_umap_1"] =\
                fitted["classification_evidence"]["embedding"][:, 0]
            integration_table["classification_evidence_umap_2"] =\
                fitted["classification_evidence"]["embedding"][:, 1]
            _persistence.save_models(version_dir, "classification_evidence",
                        fitted["classification_evidence"])
            checks.append(("classification unchanged by every UMAP fit",
                           integration_table[regression_columns].equals(before_maps)))

            transform_ok = True
            for block in ("periodic", "transient", "combined"):
                block_matrix, _ = _embedding.feature_matrix(records, block)
                loaded = _persistence.load_models(version_dir, block)
                transformed, _ = _embedding.transform_representation(loaded, block_matrix[:3])
                transform_ok = transform_ok and transformed.shape == (3, 2)
            loaded_evidence = _persistence.load_models(version_dir, "classification_evidence")
            transformed_evidence, _ = _embedding.transform_evidence_representation(
                loaded_evidence, integration_table.iloc[:3])
            transform_ok = transform_ok and transformed_evidence.shape == (3, 2)
            checks.append(("all four frozen UMAP models transform new sources", transform_ok))

            integration_table = _classify.apply_labels(integration_table, pd.DataFrame(
                columns=list(S.MANUAL_LABEL_COLUMNS)))
            integration_table["batch_id"] = "smoke"
            integration_table["is_reference"] = True
            integration_table["is_latest_batch"] = True
            integration_table["first_seen"] = _utils.iso_now()
            for index, record in enumerate(records):
                cache_file = version_dir / "cache" / ("integration_%02d.joblib" % index)
                joblib.dump(record, cache_file, compress=1)
                record["cache_path"] = str(cache_file)
            validation_keys = integration_table["source_key"].astype(str).tolist()
            _persistence.save_combined_validation_space(
                version_dir, validation_keys, fitted["combined"]["model_space"])
            _modes.finalise(integration_table, version_dir, integration_config, [], records,
                     {}, False, logger, fitted["combined"]["model_space"], validation_keys)
            required_outputs = [
                version_dir / "tables" / "all_sources.csv",
                version_dir / "tables" / "interest_summary.csv",
                version_dir / "tables" / "transit_diagnostics.csv",
                version_dir / "tables" / "irregular_variable_summary.csv",
                version_dir / "tables" / "umap_neighbour_validation.csv",
                version_dir / "tables" / "umap_category_validation_summary.csv",
                version_dir / "tables" / "flare_event_validation.csv",
                version_dir / "tables" / "family_tag_crosstab.csv",
                version_dir / "tables" / "coverage_and_period_flags.csv",
                version_dir / "tables" / "blind_validation_sample.csv",
                version_dir / "tables" / "blind_validation_key.csv",
                version_dir / "tables" / "membership_table_index.csv",
                _persistence.figure_directory(version_dir) / "maps" / "all_families_combined_unsupervised_umap.png",
                _persistence.figure_directory(version_dir) / "maps" / "all_families_combined_unsupervised_umap.pdf",
                _persistence.figure_directory(version_dir) / "maps" / "all_families_periodic_umap.png",
                _persistence.figure_directory(version_dir) / "maps" / "all_families_classification_evidence_umap.png",
                _persistence.figure_directory(version_dir) / "maps" / "strongest_family_examples.png",
                _persistence.figure_directory(version_dir) / "maps" / "representative_family_examples.png",
                _persistence.figure_directory(version_dir) / "maps" / "representative_families" /
                "transit_representative_examples.png",
                version_dir / "models" / "periodic_representation.joblib",
                version_dir / "models" / "combined_representation.joblib",
                version_dir / "models" / "classification_evidence_representation.joblib",
                version_dir / "models" / "combined_validation_space.joblib",
            ]
            source_images = list((_persistence.figure_directory(version_dir) / "source_plots").rglob("*.png"))
            primary_images = list((_persistence.figure_directory(version_dir) / "category_folds" / "primary").rglob("*.png"))
            blind_columns = pd.read_csv(
                version_dir / "tables" / "blind_validation_sample.csv", nrows=1).columns
            checks.append(("end-to-end outputs and saved models", all(
                path.exists() for path in required_outputs)
                and len(source_images) <= len(records)
                and len(primary_images) == len(records)
                and "final_primary_tag" not in blind_columns
                and not (_persistence.figure_directory(version_dir) / "review_plots").exists()
                and not (_persistence.figure_directory(version_dir) / "review_folders").exists()
                and not (_persistence.figure_directory(version_dir) / "maps" / "family_centroids.png").exists()))
    except Exception as error:
        logger.error("End-to-end smoke check failed: %s", error, exc_info=verbose)
        checks.append(("end-to-end outputs and saved models", False))
    for name, ok in checks:
        if not ok:
            failures += 1
        print("%-54s %s" % (name, "OK" if ok else "FAIL"))
    print("-" * 125)
    total = len(cases) + len(checks)
    print("%d/%d passed" % (total - failures, total))
    return 1 if failures else 0
