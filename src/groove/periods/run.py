from __future__ import annotations

import gc
import shutil
import traceback
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .. import execution as _execution
from .. import resume as R
from . import aliases as _aliases
from . import classify as _classify
from . import files as _files
from . import loading as _loading
from . import plots as _plots
from . import recommend as _recommend
from . import settings as S
from . import validation as _validation


# =============================================================================
# MAIN
# =============================================================================
def validate_configuration() -> None:
    if S.FORCED_FOLD_PERIOD_DAYS is not None:
        forced_period = float(S.FORCED_FOLD_PERIOD_DAYS)
        if not np.isfinite(forced_period) or forced_period <= 0:
            raise ValueError("FORCED_FOLD_PERIOD_DAYS must be a positive finite number or None")
    if int(S.PLOT_TIME_SEGMENTS) < 1:
        raise ValueError("PLOT_TIME_SEGMENTS must be at least 1")
    if int(S.PLOT_TIME_SEGMENTS) > len(S.PLOT_TIME_COLOR_PALETTE):
        raise ValueError(
            "PLOT_TIME_SEGMENTS exceeds the number of colours in "
            "PLOT_TIME_COLOR_PALETTE"
        )
    if len(S.PLOT_TIME_SEGMENT_COLORS) != int(S.PLOT_TIME_SEGMENTS):
        raise ValueError(
            "PLOT_TIME_SEGMENT_COLORS must contain exactly one colour for each timeline segment"
        )
    if str(S.EXTRA_FOLD_SERIES_MODE).strip().lower() not in {"recommended", "all"}:
        raise ValueError("EXTRA_FOLD_SERIES_MODE must be 'recommended' or 'all'")
    if int(S.ALIAS_N_PEAKS_TO_PLOT) < 1:
        raise ValueError("ALIAS_N_PEAKS_TO_PLOT must be at least 1")


def run_classification_regression_checks() -> None:
    """Small dependency-free regression checks for classification/routing."""
    base = {
        "raw_ls_fap": 1e-5,
        "ls_peak_snr": 8.0,
        "raw_fold_amp_snr": 8.0,
        "best_to_second_power_ratio": 1.7,
        "best_to_fourth_power_ratio": 2.0,
        "raw_alias_score": 0.0,
        "alias_correction_applied": False,
        "two_p_supported": False,
        "mh_2p_supported": False,
        "top_peak_2p_present": False,
    }

    strong_primary, strong_secondary = _classify.classify_series_detection(base)
    assert strong_primary == "strong" and strong_secondary == "none"
    assert _files.plot_review_folders(
        {"secondary_classification": strong_secondary}, strong_primary
    ) == [Path("best_per_star"), Path("strong")]

    weak_alias = {
        **base,
        "source_id": "3216097354064705920",
        "best_to_second_power_ratio": 1.03,
        "best_to_fourth_power_ratio": 1.05,
        "raw_alias_score": max(S.ALIAS_SCORE_THRESHOLD, 0.5),
    }
    weak_primary, weak_secondary = _classify.classify_series_detection(
        weak_alias, filter_disagreement=True
    )
    assert weak_primary == "weak_or_ambiguous"
    assert weak_secondary == "alias_possible;filter_disagreement"
    assert _files.plot_review_folders(
        {"secondary_classification": weak_secondary}, weak_primary
    ) == [Path("best_per_star"), Path("weak_or_ambiguous")]

    nonvar_alias = {
        **weak_alias,
        "raw_ls_fap": 0.5,
        "ls_peak_snr": 1.0,
        "raw_fold_amp_snr": 1.0,
    }
    nonvar_primary, nonvar_secondary = _classify.classify_series_detection(nonvar_alias)
    assert nonvar_primary == "nonvar"
    assert _files.plot_review_folders(
        {"secondary_classification": nonvar_secondary}, nonvar_primary
    ) == [Path("best_per_star"), Path("nonvar")]

    dominant_alias = {**base, "raw_alias_score": max(S.ALIAS_SCORE_THRESHOLD, 0.5)}
    alias_primary, alias_secondary = _classify.classify_series_detection(dominant_alias)
    assert alias_primary == "alias_possible" and alias_secondary == "alias_possible"
    assert _files.plot_review_folders(
        {"secondary_classification": alias_secondary}, alias_primary
    ) == [Path("best_per_star"), Path("alias")]

    harmonic_row = {**base, "top_peak_2p_present": True}
    harmonic_primary, harmonic_secondary = _classify.classify_series_detection(harmonic_row)
    assert harmonic_primary == "harmonic_possible" and harmonic_secondary == "harmonic_possible"
    assert _files.plot_review_folders(
        {"secondary_classification": harmonic_secondary}, harmonic_primary
    ) == [Path("best_per_star"), Path("harmonic")]

    crowded = {
        **base,
        "alias_correction_applied": True,
        "raw_alias_score": 1.0,
        "top_peak_2p_present": True,
    }
    _, crowded_secondary = _classify.classify_series_detection(
        crowded, filter_disagreement=True, single_filter_only=True
    )
    assert crowded_secondary == "alias_corrected;harmonic_possible"
    assert len(crowded_secondary.split(";")) <= 2

    combined = {**base, "alias_correction_applied": True}
    o_series = {**base, "raw_alias_score": max(S.ALIAS_SCORE_THRESHOLD, 0.5)}
    _, combined_secondary = _classify.classify_series_detection(combined)
    _, o_secondary = _classify.classify_series_detection(o_series)
    assert "alias_corrected" in combined_secondary
    assert "alias_corrected" not in o_secondary
    assert all(
        "secondary_label" not in folder.as_posix()
        for folder in _files.plot_review_folders(
            {"secondary_classification": weak_secondary}, weak_primary
        )
    )


def _analyse_file(
    path: Path, catalogue: dict[str, float], settings_snapshot: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list]:
    """Analyse one file without progress, journal writes or shared parent state."""
    missing = object()
    previous = {key: getattr(S, key, missing) for key in settings_snapshot}
    summary_rows, peak_rows, payloads = [], [], []
    try:
        for key, value in settings_snapshot.items():
            setattr(S, key, value)
        with _execution.error_policy(bool(S.STRICT_ERRORS)):
            try:
                raw = pd.read_csv(path, dtype=str, low_memory=False)
                frame = _loading.normalise_columns(raw)
                metadata = _loading.extract_metadata(frame, path)
                catalogue_period = _loading.safe_float(metadata['embedded_catalogue_period_days'], np.nan)
                external = catalogue.get(str(metadata['source_id']))
                if external is not None and np.isfinite(external):
                    catalogue_period = float(external)
                for series in S.SERIES_TO_RUN:
                    prepared = _loading.prepare_series(frame, series)
                    if prepared is None:
                        summary_rows.append({**metadata, 'series': series, 'status': 'skipped',
                            'skip_reason': 'series/filter unavailable or insufficient points',
                            'catalogue_period_days': catalogue_period})
                        continue
                    row, peaks, payload = _recommend.analyse_one_series(metadata, prepared, catalogue_period)
                    summary_rows.append(row)
                    peak_rows.extend(peaks)
                    if payload is not None and S.KEEP_PLOT_PAYLOADS_IN_MEMORY:
                        payloads.append((metadata, prepared, row, payload, catalogue_period))
            except Exception as exc:
                _execution.report_exception(exc, __name__)
                summary_rows.append({'file': path.name, 'source_id': path.stem, 'object_name': path.stem,
                    'series': '', 'status': 'failed', 'error': repr(exc),
                    'traceback': traceback.format_exc(limit=8)})
    finally:
        for key, value in previous.items():
            if value is missing:
                delattr(S, key)
            else:
                setattr(S, key, value)
    return summary_rows, peak_rows, payloads


def _pending_jobs(files: list[Path], processed_keys: set) -> list[tuple[int, Path, dict]]:
    """Resolve skips/source caps in the parent before submitting any workers."""
    jobs = []
    sources: set[str] = set()
    for index, path in enumerate(files, start=1):
        remaining = [series for series in S.SERIES_TO_RUN
                     if not (S.SKIP_ALREADY_PROCESSED and (path.name, series) in processed_keys)]
        if not remaining:
            _execution.log_info(__name__, f'[{index:,}/{len(files):,}] skip completed file: {path.name}')
            continue
        if S.MAX_SOURCES is not None:
            # Only the ID is needed here; all scientific rows are loaded by the worker.
            try:
                first = _loading.normalise_columns(pd.read_csv(path, dtype=str, nrows=1))
                source_id = str(_loading.extract_metadata(first, path)['source_id'])
            except Exception as exc:
                _execution.report_exception(exc, __name__)
                source_id = path.stem  # let the worker produce the normal failed row
            if source_id not in sources and len(sources) >= int(S.MAX_SOURCES):
                continue
            sources.add(source_id)
        snapshot = R.settings_dict(S)
        snapshot['SERIES_TO_RUN'] = remaining
        snapshot['STRICT_ERRORS'] = _execution.is_strict()
        jobs.append((index, path, snapshot))
    return jobs


def main() -> None:
    validate_configuration()

    files = sorted(S.INPUT_DIR.glob(S.FILE_GLOB))
    if S.MAX_FILES is not None:
        files = files[: int(S.MAX_FILES)]
    # Explicit alias/harmonic paths must be available to both the period-search
    # pass and the later saved-results plotting pass, even if outside INPUT_DIR.
    files = _files.add_explicit_diagnostic_files(files)
    if not files:
        raise FileNotFoundError(f"No files found in {S.INPUT_DIR} matching {S.FILE_GLOB}")

    run_signature = _files.completed_run_signature(files)
    # A completion marker is written only after every table and plot succeeds.
    # With unchanged code/config/inputs and intact outputs, a rerun is a true
    # no-op: no files are loaded, printed, plotted, or rewritten.
    if R.ACTIVE_PRODUCTS is None and not getattr(S, "FORCE_RERUN", False) and _files.completed_run_is_unchanged(run_signature):
        return

    S.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (S.OUTPUT_DIR / "tables").mkdir(parents=True, exist_ok=True)
    # Older runs created this metadata as a plot folder. It is deliberately
    # removed so secondary classification exists only in plot/table text.
    stale_secondary_dir = S.plot_root().resolve() / "secondary_label"
    if stale_secondary_dir.is_dir() and stale_secondary_dir.parent == S.plot_root().resolve():
        shutil.rmtree(stale_secondary_dir)
    for series in S.SERIES_TO_RUN:
        stale_series_secondary_dir = (
            S.plot_root() / _loading.sanitize_filename(series) / "secondary_label"
        ).resolve()
        expected_series_plot_dir = (S.plot_root() / _loading.sanitize_filename(series)).resolve()
        if stale_series_secondary_dir.is_dir() and stale_series_secondary_dir.parent == expected_series_plot_dir:
            shutil.rmtree(stale_series_secondary_dir)
        for folder in set(S.TAG_FOLDER_MAP.values()) | {S.BEST_PER_STAR_DIRNAME}:
            (S.plot_root() / _loading.sanitize_filename(series) / folder).mkdir(parents=True, exist_ok=True)
        (S.plot_root() / _loading.sanitize_filename(series) / "alias" / S.EXTRA_FOLD_SUBDIR).mkdir(parents=True, exist_ok=True)
        (S.plot_root() / _loading.sanitize_filename(series) / "harmonic" / S.EXTRA_FOLD_SUBDIR).mkdir(parents=True, exist_ok=True)
    signature_path = S.OUTPUT_DIR / "tables" / "analysis_signature.json"
    analysis_signature = _files.analysis_run_signature(files)
    previous_signature = ""
    if signature_path.exists():
        import json
        previous_signature = json.loads(signature_path.read_text()).get("signature", "")
    use_cache = S.SKIP_ALREADY_PROCESSED and previous_signature == analysis_signature
    if not use_cache and (S.OUTPUT_DIR / "tables" / "ls_period_search_summary.csv").exists():
        _execution.log_info(__name__, "[cache reset] Inputs, settings or code changed; recomputing scientific results.")
    _files.write_run_config()
    import json
    signature_path.write_text(json.dumps({"signature": analysis_signature}))

    summary_path = S.OUTPUT_DIR / "tables" / "ls_period_search_summary.csv"
    peaks_path = S.OUTPUT_DIR / "tables" / "ls_period_search_peaks.csv"
    summary_rows: list[dict[str, Any]] = []
    peak_rows_all: list[dict[str, Any]] = []
    if use_cache and summary_path.exists() and peaks_path.exists():
        try:
            cached_summary = pd.read_csv(summary_path, dtype={"source_id": str}, low_memory=False)
            cached_peaks = pd.read_csv(peaks_path, dtype={"source_id": str}, low_memory=False)
        except (OSError, ValueError, pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
            _execution.log_info(__name__, f'[cache repair] Unreadable aggregate period tables: {exc}; recovering source journals.')
            cached_summary, cached_peaks = pd.DataFrame(), pd.DataFrame()
        missing_summary, missing_peaks = _files.cache_schema_missing(
            set(cached_summary.columns), set(cached_peaks.columns)
        )
        if missing_summary or missing_peaks:
            message = (
                "Cached result tables are from an incompatible pipeline schema. "
                f"Missing summary fields={sorted(missing_summary)}; "
                f"missing peak fields={sorted(missing_peaks)}."
            )
            if not S.RESTART_IF_CACHE_SCHEMA_INCOMPATIBLE:
                raise RuntimeError(
                    message
                    + " Use a new OUTPUT_DIR, disable SKIP_ALREADY_PROCESSED, or enable "
                    "RESTART_IF_CACHE_SCHEMA_INCOMPATIBLE."
                )
            _execution.log_info(__name__, f"[cache reset] {message}")
            _execution.log_info(__name__, "[cache reset] Reprocessing this OUTPUT_DIR with the current pipeline; old tables will be replaced.")
        else:
            summary_rows = cached_summary.to_dict("records")
            peak_rows_all = cached_peaks.to_dict("records")
            _execution.log_info(__name__,
                f"Loaded compatible cached results: {len(summary_rows):,} summary rows, "
                f"{len(peak_rows_all):,} peak rows"
            )
    elif use_cache and (summary_path.exists() or peaks_path.exists()):
        _execution.log_info(__name__, "[cache reset] Only one cached result table exists; reprocessing to keep summary and peaks consistent.")
    if use_cache:
        summary_rows, peak_rows_all = _files.restore_source_checkpoints(analysis_signature, summary_rows, peak_rows_all, files=files)
    # Freeze the alias-memory input for this analysis. Our own output must not
    # be merged back into itself after an interrupted plotting pass.
    base_path = S.OUTPUT_DIR / 'tables' / 'alias_memory_input.json'
    baseline = R.read_json(base_path)
    if baseline.get('signature') != analysis_signature or getattr(S, 'FORCE_RERUN', False):
        explicit_memory = Path(S.ALIAS_MEMORY_CSV).resolve() != (S.OUTPUT_DIR / 'tables/field_alias_memory.csv').resolve()
        base = _aliases.load_alias_memory() if explicit_memory else pd.DataFrame()
        baseline = {'signature': analysis_signature, 'rows': base.to_dict('records')}
        R.atomic_json(base_path, baseline)
    processed_keys = _files.build_processed_keys_from_rows(summary_rows)
    external_catalogue = _validation.load_external_catalogue()

    # In large runs, keeping all prepared arrays and periodograms in memory can
    # crash the script. By default this stays empty and plots are generated in a
    # second streaming pass after final alias/harmonic decisions are known.
    plot_payloads: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any] | None, float]] = []

    _execution.log_info(__name__, "=" * 88)
    _execution.log_info(__name__, "ADAPTIVE ATLAS LS PERIOD SEARCH WITH FIELD-ALIAS MEMORY")
    _execution.log_info(__name__, "=" * 88)
    _execution.log_info(__name__, f"Input folder:  {S.INPUT_DIR}")
    _execution.log_info(__name__, f"Output folder: {S.OUTPUT_DIR}")
    _execution.log_info(__name__, f"Files found:   {len(files):,}")
    _execution.log_info(__name__, f"Series:        {S.SERIES_TO_RUN}")
    _execution.log_info(__name__, f"Period range:  {S.MIN_PERIOD_DAYS:g}--{S.MAX_PERIOD_DAYS:g} d, baseline-limited")
    _execution.log_info(__name__,
        "Main plot fold: "
        + (
            f"forced to {float(S.FORCED_FOLD_PERIOD_DAYS):g} d"
            if S.FORCED_FOLD_PERIOD_DAYS is not None
            else "automatic recommended series period"
        )
    )
    _execution.log_info(__name__, f"Alias memory:  {S.ALIAS_MEMORY_CSV}")
    _execution.log_info(__name__, "=" * 88)

    jobs = _pending_jobs(files, processed_keys)
    n_jobs = int(S.PERIOD_N_JOBS)
    if n_jobs == 0:
        raise ValueError('periods.period_n_jobs must be a non-zero integer')
    parallel = n_jobs != 1 and len(jobs) >= 8
    if n_jobs != 1:
        for _, _, snapshot in jobs:
            snapshot['KEEP_PLOT_PAYLOADS_IN_MEMORY'] = False
    if parallel:
        from joblib import Parallel, delayed
        executor = Parallel(n_jobs=n_jobs, backend='loky', return_as='generator',
                            batch_size=1, pre_dispatch='2*n_jobs')
        results = executor(delayed(_analyse_file)(path, external_catalogue, snapshot)
                           for _, path, snapshot in jobs)
    else:
        results = (_analyse_file(path, external_catalogue, snapshot) for _, path, snapshot in jobs)
    try:
        for completed, ((file_index, path, _snapshot), result) in enumerate(zip(jobs, results, strict=True), start=1):
            new_summary, new_peaks, new_payloads = result
            summary_rows.extend(new_summary)
            peak_rows_all.extend(new_peaks)
            plot_payloads.extend(new_payloads)
            for row in new_summary:
                if row.get('status') == 'failed':
                    _execution.log_info(__name__, f'{path.name}: {row.get("error", "unknown error")}')
                _execution.log_info(__name__, f'[{file_index:,}/{len(files):,}] {path.name} / '
                    f'{row.get("series")}: status={row.get("status")}, '
                    f'raw={row.get("raw_ls_best_period_days", np.nan):.6g} d')
            _files.save_source_checkpoint(analysis_signature, path, new_summary, new_peaks)
            if completed % S.CHECKPOINT_EVERY_N_FILES == 0:
                _files.save_raw_checkpoint(summary_rows, peak_rows_all)
                _execution.log_info(__name__, f'  checkpoint saved after {completed:,} files')
                gc.collect()
    finally:
        if parallel:
            results.close()
            executor.__exit__(None, None, None)

    # Build/update alias memory after all stars are searched.
    summary_df = pd.DataFrame(summary_rows)
    reference_df = _aliases.load_reference_summaries()
    learning_df = pd.concat([summary_df, reference_df], ignore_index=True, sort=False) if not reference_df.empty else summary_df
    current_inventory = _aliases.build_field_alias_inventory(learning_df, series=S.ALIAS_LEARNING_SERIES) if S.RUN_ALIAS_LEARNING else pd.DataFrame()
    old_memory = pd.DataFrame(baseline['rows'])
    memory_inventory = _aliases.merge_alias_inventories(old_memory, current_inventory) if S.UPDATE_ALIAS_MEMORY else _aliases.merge_alias_inventories(old_memory, current_inventory)

    # Apply alias memory, then recompute harmonic tests around the alias-aware
    # period. This order is important: otherwise a corrected 21.6 d period would
    # still show the old raw 1 d -> 2 d harmonic candidate.
    _aliases.annotate_aliases_and_choose_series_period(summary_rows, peak_rows_all, memory_inventory)
    if plot_payloads:
        _aliases.update_post_alias_harmonics(summary_rows, peak_rows_all, plot_payloads)
    else:
        # No in-memory light-curve arrays are kept in large-run mode, so use the
        # peak table only for harmonic-review flags after alias correction.
        _aliases.update_post_alias_harmonics_from_peaks(summary_rows, peak_rows_all)
    recommendations = _recommend.choose_source_recommendations(summary_rows)
    if plot_payloads:
        recommendations = _recommend.add_forced_cross_filter_metrics(recommendations, plot_payloads)

    # Save the final no-plot tables before any slow second-pass plotting.
    _files.save_all_tables(summary_rows, peak_rows_all, current_inventory, memory_inventory, recommendations)

    # Save plots after alias-aware periods, post-alias harmonic flags and source
    # labels are known. Each plot is saved to best_per_star plus duplicate tag
    # folders such as strong/, alias/ and harmonic/ when relevant.
    source_info_lookup: dict[str, dict[str, Any]] = {}
    if recommendations is not None and not recommendations.empty:
        source_info_lookup = {
            str(row.get("source_id")): row.to_dict()
            for _, row in recommendations.iterrows()
        }
    row_lookup = {
        (str(r.get("file")), str(r.get("source_id")), str(r.get("series"))): r
        for r in summary_rows
        if str(r.get("status")) == "ok"
    }
    for metadata, prepared, old_row, payload, catalogue_period in plot_payloads:
        row = row_lookup.get((str(metadata.get("file")), str(metadata.get("source_id")), str(prepared.get("series_name"))), old_row)
        source_info = source_info_lookup.get(str(metadata.get("source_id")), {})
        source_label = str(source_info.get("recommendation_label", "nonvar"))
        row["recommendation_label"] = source_label
        row["source_warning_flags"] = str(source_info.get("warning_flags", ""))
        row["source_harmonic_status"] = str(source_info.get("harmonic_status", ""))
        row["source_detection_label"] = str(source_info.get("detection_label", ""))
        row["source_confidence_class"] = str(source_info.get("confidence_class", ""))
        try:
            row["best_per_star_plot_path"] = _plots.plot_best_per_star(
                metadata, prepared, payload["result"], row, catalogue_period, payload.get("bls"), source_label
            )
        except Exception as exc:
            _execution.report_exception(exc, __name__)
            row["best_per_star_plot_path"] = ""
            row["plot_error"] = str(exc)

    # If large-run mode was used, make plots in a streaming second pass. If
    # in-memory payloads were kept, the loop above has already made them.
    if not plot_payloads:
        _plots.plot_from_saved_results(files, summary_rows, recommendations, external_catalogue)

    # Rebuild recommendations so plot paths written into summary rows are retained;
    # then re-add forced metrics only when the in-memory arrays exist.
    recommendations = _recommend.choose_source_recommendations(summary_rows)
    if plot_payloads:
        recommendations = _recommend.add_forced_cross_filter_metrics(recommendations, plot_payloads)

    # Optional visual-only candidate folds. This is deliberately separate from
    # the main selection logic and can run from the saved summary/peak tables on
    # a later SKIP_ALREADY_PROCESSED=True diagnostic pass.
    extra_fold_manifest = _plots.generate_extra_phase_fold_diagnostics(
        files,
        summary_rows,
        peak_rows_all,
        recommendations,
        memory_inventory,
    )
    master_plot_path = _plots.create_master_review_plot(recommendations)
    if recommendations is not None and not recommendations.empty:
        recommendations["master_review_plot_path"] = master_plot_path
    _files.save_all_tables(summary_rows, peak_rows_all, current_inventory, memory_inventory, recommendations)
    if not any(row.get("status") == "ok" for row in summary_rows):
        raise RuntimeError("No usable period-search results. See ls_period_search_summary.csv for failures and skipped sources.")
    if any(row.get('status') == 'failed' for row in summary_rows):
        raise RuntimeError('Period-search sources failed; saved successful sources will be reused on restart.')
    if not extra_fold_manifest.empty and extra_fold_manifest.status.eq('failed').any():
        raise RuntimeError('Extra phase folds failed; restart to repair missing diagnostics.')
    plot_failures = [row for row in summary_rows if row.get("plot_error")]
    if plot_failures:
        raise RuntimeError(f"{len(plot_failures)} period plot(s) failed. Review plot_error in ls_period_search_summary.csv and rerun.")
    if not any(row.get("status") == "failed" for row in summary_rows):
        _files.mark_run_complete(run_signature)

    _execution.log_info(__name__, "=" * 88)
    _execution.log_info(__name__, "DONE")
    _execution.log_info(__name__, f"Summary:         {S.OUTPUT_DIR / 'tables' / 'ls_period_search_summary.csv'}")
    _execution.log_info(__name__, f"Peaks:           {S.OUTPUT_DIR / 'tables' / 'ls_period_search_peaks.csv'}")
    _execution.log_info(__name__, f"Consensus:       {S.OUTPUT_DIR / 'tables' / 'ls_source_consensus.csv'}")
    _execution.log_info(__name__, f"Recommendations: {S.OUTPUT_DIR / 'tables' / 'source_period_recommendations.csv'}")
    _execution.log_info(__name__, f"Alias memory:    {S.OUTPUT_DIR / 'tables' / 'field_alias_memory.csv'}")
    if not recommendations.empty and "recommendation_label" in recommendations.columns:
        _execution.log_info(__name__, "Recommendation labels:")
        _execution.log_info(__name__, recommendations["recommendation_label"].fillna("unknown").value_counts().to_string())
    if not recommendations.empty and "confidence_class" in recommendations.columns:
        _execution.log_info(__name__, "Confidence classes:")
        _execution.log_info(__name__, recommendations["confidence_class"].fillna("unknown").value_counts().to_string())
    if 'master_plot_path' in locals() and master_plot_path:
        _execution.log_info(__name__, f"Master review plot: {master_plot_path}")
    if 'extra_fold_manifest' in locals() and not extra_fold_manifest.empty:
        made = int(extra_fold_manifest.get("status", pd.Series(dtype=str)).astype(str).eq("made").sum())
        _execution.log_info(__name__, f"Extra phase-fold figures: {made:,}")
    _execution.log_info(__name__, "=" * 88)
