from __future__ import annotations
import logging
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
import joblib
import numpy as np
import pandas as pd
from . import settings as S
from . import persistence as _persistence
from . import utils as _utils




def likely_lightcurve_file(path: Path) -> bool:
    if path.suffix.lower() != ".csv":
        return False
    lowered = path.name.lower()
    return not any(word in lowered for word in S.SKIP_FILE_WORDS)


def discover_lightcurve_files(inputs: Sequence[Any]) -> Tuple[List[Path], List[Dict[str, Any]]]:
    found: List[Path] = []
    problems: List[Dict[str, Any]] = []
    for item in inputs:
        path = Path(str(item))
        if not path.exists():
            problems.append({"input": str(path), "reason": "path_not_found"})
            continue
        if path.is_dir():
            found.extend(sorted(p for p in path.rglob("*.csv") if likely_lightcurve_file(p)))
        elif path.suffix.lower() in {".txt", ".lst", ".manifest"}:
            for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                sub = Path(line)
                if sub.is_dir():
                    found.extend(sorted(p for p in sub.rglob("*.csv") if likely_lightcurve_file(p)))
                elif sub.exists():
                    found.append(sub)
                else:
                    problems.append({"input": str(sub), "reason": "manifest_entry_missing"})
        elif likely_lightcurve_file(path):
            found.append(path)
        else:
            problems.append({"input": str(path), "reason": "not_a_lightcurve_csv"})
    unique = list(dict.fromkeys(p.resolve() for p in found))
    return unique, problems


def source_id_from_path(path: Path) -> str:
    match = re.search(r"(?:GaiaDR3[_]*)(\d{5,25})", path.name)
    if match:
        return match.group(1)
    match = re.search(r"(\d{15,25})", path.name)
    return match.group(1) if match else path.stem.removesuffix("_cleaned")


def standardise_lightcurve_file(path: Path, dataset: str, bands: Sequence[str]) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype=str, low_memory=False)
    if frame.empty:
        return pd.DataFrame()
    time_col = _utils.first_column(frame, S.TIME_ALIASES)
    mag_col = _utils.first_column(frame, S.MAG_ALIASES)
    err_col = _utils.first_column(frame, S.MAG_ERR_ALIASES)
    if time_col is None or mag_col is None:
        return pd.DataFrame()
    id_col = _utils.first_column(frame, S.SOURCE_ID_ALIASES)
    filt_col = _utils.first_column(frame, S.FILTER_ALIASES)

    out = pd.DataFrame()
    out["time"] = pd.to_numeric(frame[time_col], errors="coerce")
    out["mag"] = pd.to_numeric(frame[mag_col], errors="coerce")
    out["err"] = pd.to_numeric(frame[err_col], errors="coerce") if err_col else np.nan
    flux_col = _utils.first_column(frame, S.FLUX_ALIASES)
    if flux_col is not None:
        out["flux"] = pd.to_numeric(frame[flux_col], errors="coerce")

    if id_col is not None:
        out["source_id"] = frame[id_col].map(_utils.clean_source_id)
    else:
        out["source_id"] = ""
    for candidate in S.SOURCE_ID_ALIASES:
        if candidate in frame.columns:
            out.loc[out["source_id"].eq(""), "source_id"] = frame.loc[out["source_id"].eq(""), candidate].map(_utils.clean_source_id)
    fallback_id = source_id_from_path(path)
    out.loc[out["source_id"].eq(""), "source_id"] = fallback_id

    if filt_col is not None:
        out["filter"] = frame[filt_col].astype(str).str.strip().str.lower()
    else:
        match = re.search(r"_([co])_", path.name)
        out["filter"] = match.group(1) if match else "o"

    out = out.loc[out["filter"].isin(list(bands))]
    out = out.loc[np.isfinite(out["time"]) & np.isfinite(out["mag"])]
    # Reject non-physical photometry. Negative or zero magnitudes, and anything
    # outside a plausible ATLAS range, are failed measurements rather than data.
    out = out.loc[(out["mag"] > 0) & (out["mag"] > S.MAGNITUDE_RANGE[0])
                  & (out["mag"] < S.MAGNITUDE_RANGE[1])]
    if "flux" in out.columns:
        # A negative ATLAS flux is a non-detection, not a faint measurement.
        out = out.loc[np.isfinite(out["flux"]) & (out["flux"] > 0)]
        out = out.drop(columns=["flux"])
    out = out.loc[out["source_id"].ne("")]
    if out.empty:
        return out
    # Missing or non-positive errors get the per-band median.
    med = out.groupby("filter")["err"].transform(lambda s: s[s > 0].median())
    out["err"] = out["err"].where(out["err"] > 0, med)
    out["err"] = out["err"].fillna(out.loc[out["err"] > 0, "err"].median())
    out["err"] = out["err"].fillna(0.02)
    out["dataset"] = dataset
    out["input_filename"] = path.name
    return out


def load_lightcurves(specs: Sequence[Mapping[str, Any]], config: Mapping[str, Any],
                     logger: logging.Logger) -> Tuple[Dict[str, Dict[str, Any]], pd.DataFrame]:
    bands = [b for b, on in (("c", config.get("use_c_band", False)),
                             ("o", config.get("use_o_band", True))) if on]
    minimum = int(config.get("minimum_observations", 50))
    sources: Dict[str, Dict[str, Any]] = {}
    problems: List[Dict[str, Any]] = []

    for spec in specs:
        dataset = str(spec.get("name", "dataset"))
        priority = int(spec.get("priority", 0))
        files, issues = discover_lightcurve_files(spec.get("lightcurve_inputs", []))
        problems.extend(dict(issue, dataset=dataset) for issue in issues)
        logger.info("%s: %d candidate light-curve files", dataset, len(files))
        for path in files:
            try:
                frame = standardise_lightcurve_file(path, dataset, bands)
            except Exception as error:
                problems.append({"dataset": dataset, "input": str(path),
                                 "reason": "read_failed: %s" % error})
                continue
            if frame.empty:
                problems.append({"dataset": dataset, "input": str(path),
                                 "reason": "no_usable_rows"})
                continue
            for source_id, block in frame.groupby("source_id", sort=False):
                key = str(source_id)
                record = sources.setdefault(key, {
                    "source_id": key, "dataset": dataset, "priority": priority,
                    "frames": [], "files": [], "fingerprints": [],
                })
                if priority < record["priority"]:
                    record["dataset"], record["priority"] = dataset, priority
                record["frames"].append(block)
                record["files"].append(path.name)
                record["fingerprints"].append(_utils.file_fingerprint(path))

    out: Dict[str, Dict[str, Any]] = {}
    for key, record in sources.items():
        data = pd.concat(record["frames"], ignore_index=True)
        data = data.drop_duplicates(subset=["time", "filter"]).sort_values("time")
        data = data.reset_index(drop=True)
        if len(data) < minimum:
            problems.append({"dataset": record["dataset"], "source_id": key,
                             "reason": "below_minimum_observations_%d" % len(data)})
            continue
        out[key] = {
            "source_key": key, "source_id": key, "dataset": record["dataset"],
            "data": data[["time", "mag", "err", "filter"]].copy(),
            "input_filename": ";".join(sorted(set(record["files"]))[:3]),
            "file_fingerprint": _utils.hash_json(sorted(set(record["fingerprints"]))),
        }
    logger.info("Loaded %d usable sources (%d problems)", len(out), len(problems))
    return out, pd.DataFrame(problems)


def load_selected_lightcurves(specs: Sequence[Mapping[str, Any]],
                              config: Mapping[str, Any],
                              source_ids: Sequence[str],
                              logger: logging.Logger) -> Dict[str, Dict[str, Any]]:
    """Load a small named subset through the normal production standardiser.

    This is used only by additive diagnostic plots.  It deliberately applies
    the same band selection, cleaning, dataset priority, and duplicate removal
    as :func:`load_lightcurves`, while avoiding reads of thousands of unrelated
    CSV files.
    """
    requested = {_utils.clean_source_id(value) for value in source_ids}
    requested.discard("")
    bands = [band for band, enabled in (
        ("c", config.get("use_c_band", False)),
        ("o", config.get("use_o_band", True))) if enabled]
    collected: Dict[str, Dict[str, Any]] = {}
    for spec in specs:
        dataset = str(spec.get("name", "dataset"))
        priority = int(spec.get("priority", 0))
        files, _ = discover_lightcurve_files(spec.get("lightcurve_inputs", []))
        candidates = [path for path in files if source_id_from_path(path) in requested]
        for path in candidates:
            try:
                frame = standardise_lightcurve_file(path, dataset, bands)
            except Exception as error:
                logger.warning("Could not read selected light curve %s: %s", path, error)
                continue
            for source_id, block in frame.groupby("source_id", sort=False):
                source_id = _utils.clean_source_id(source_id)
                if source_id not in requested:
                    continue
                record = collected.setdefault(source_id, {
                    "source_id": source_id, "priority": priority,
                    "dataset": dataset, "frames": [], "files": [],
                })
                if priority < int(record["priority"]):
                    record["priority"] = priority
                    record["dataset"] = dataset
                record["frames"].append(block)
                record["files"].append(str(path))
    result: Dict[str, Dict[str, Any]] = {}
    for source_id, record in collected.items():
        data = pd.concat(record["frames"], ignore_index=True)
        data = data.drop_duplicates(subset=["time", "filter"]).sort_values("time")
        data = data.reset_index(drop=True)
        if data.empty:
            continue
        result[source_id] = {
            "source_key": source_id,
            "source_id": source_id,
            "dataset": record["dataset"],
            "data": data[["time", "mag", "err", "filter"]].copy(),
            "origin": float(data["time"].min()),
            "input_filename": ";".join(record["files"][:3]),
        }
    missing = sorted(requested.difference(result))
    if missing:
        logger.warning("Selected light curves not found for: %s", ", ".join(missing))
    return result


def read_period_tables(specs: Sequence[Mapping[str, Any]], config: Mapping[str, Any],
                       logger: logging.Logger) -> Tuple[Dict[str, Dict[str, Any]], pd.DataFrame]:
    """Source-level recommendations are authoritative; summaries are diagnostics."""
    tolerance = float(config.get("period_conflict_relative_tolerance", 0.001))
    chosen: Dict[str, Dict[str, Any]] = {}
    conflicts: List[Dict[str, Any]] = []

    for spec in specs:
        dataset = str(spec.get("name", "dataset"))
        priority = int(spec.get("priority", 0))
        for table_path in spec.get("period_tables", []):
            path = Path(str(table_path))
            if not path.exists():
                logger.warning("Period table missing: %s", path)
                continue
            authoritative = "recommendation" in path.name.lower()
            frame = pd.read_csv(path, dtype=str, low_memory=False)
            id_col = _utils.first_column(frame, S.SOURCE_ID_ALIASES)
            per_col = _utils.first_column(frame, S.RECOMMENDED_PERIOD_ALIASES)
            if per_col is None and not authoritative and "recommended_series_period_days" in frame.columns:
                # Per-series rows are diagnostics, never an adopted-period fallback.
                continue
            if id_col is None or per_col is None:
                logger.warning("Period table lacks id/period columns: %s", path)
                continue
            for _, row in frame.iterrows():
                key = _utils.clean_source_id(row.get(id_col))
                period = _utils.finite_float(row.get(per_col))
                if not key or not np.isfinite(period) or period <= 0:
                    continue
                record = {
                    "recommended_period_days": period,
                    "period_table": path.name,
                    "period_dataset": dataset,
                    "priority": priority,
                    "authoritative": authoritative,
                    "flags": _utils.join_tags(
                        _utils.split_tags(row.get(c)) for c in
                        ("alias_flags", "warning_flags", "harmonic_status",
                         "confidence_note", "series_class", "primary")
                        if c in frame.columns
                    ) if False else _utils.join_tags(sum(
                        (_utils.split_tags(row.get(c)) for c in
                         ("alias_flags", "warning_flags", "harmonic_status",
                          "confidence_note", "series_class", "primary",
                          "secondary")
                         if c in frame.columns), [])),
                }
                existing = chosen.get(key)
                if existing is None:
                    chosen[key] = record
                    continue
                same = abs(existing["recommended_period_days"] - period) <=\
                    tolerance * max(existing["recommended_period_days"], period)
                better = (record["authoritative"], -record["priority"]) >\
                         (existing["authoritative"], -existing["priority"])
                if not same:
                    conflicts.append({
                        "source_id": key,
                        "kept_period_days": (record if better else existing)["recommended_period_days"],
                        "other_period_days": (existing if better else record)["recommended_period_days"],
                        "kept_table": (record if better else existing)["period_table"],
                        "other_table": (existing if better else record)["period_table"],
                    })
                if better:
                    chosen[key] = record
    logger.info("Period recommendations for %d sources (%d conflicts)", len(chosen), len(conflicts))
    return chosen, pd.DataFrame(conflicts)


def read_table(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    frame = pd.read_csv(path, dtype={"source_id": str, "source_key": str}, low_memory=False)
    for column in ("source_id", "source_key"):
        if column in frame.columns:
            frame[column] = frame[column].map(_utils.clean_source_id)
    return frame


def load_catalogue_for_plot_only(version_dir: Path,
                                 logger: logging.Logger) -> Tuple[pd.DataFrame, str]:
    table_path = Path(version_dir) / "tables" / "all_sources.csv"
    try:
        table = read_table(table_path)
    except (pd.errors.EmptyDataError, OSError):
        table = pd.DataFrame()
    if not table.empty:
        return table, "all_sources.csv"
    checkpoint_path = _persistence.finalisation_checkpoint_path(version_dir)
    if checkpoint_path.exists():
        payload = joblib.load(checkpoint_path)
        table = payload.get("table")
        if isinstance(table, pd.DataFrame) and not table.empty:
            logger.info("Using the saved finalisation checkpoint catalogue for replotting")
            return table.copy(), "finalisation_checkpoint"
    raise SystemExit(
        "No saved catalogue is available in tables/all_sources.csv or the finalisation checkpoint.")
