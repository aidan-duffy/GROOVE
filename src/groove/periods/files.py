from __future__ import annotations
import json
import hashlib
import gc
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import numpy as np
import pandas as pd
from . import settings as S
from . import loading as _loading
from . import recommend as _recommend
from . import validation as _validation




def plot_review_folders(row: dict[str, Any], primary_label: str) -> list[Path]:
    """Return best_per_star plus exactly one mutually exclusive primary folder."""
    primary = str(primary_label).strip().lower()
    if primary not in S.TAG_FOLDER_MAP:
        raise ValueError(f"Unknown primary classification: {primary_label!r}")
    return [Path(S.BEST_PER_STAR_DIRNAME), Path(S.TAG_FOLDER_MAP[primary])]


def normal_plot_output_name(
    metadata: pd.Series | dict[str, Any],
    series_name: str,
) -> str:
    """Return the deterministic filename used by every normal phase-fold plot."""
    file_stem = _loading.sanitize_filename(
        Path(str(metadata.get("file", ""))).stem,
        max_length=80,
    )
    object_stem = _loading.sanitize_filename(metadata.get("object_name", ""), max_length=80)
    unique_stem = _loading.sanitize_filename(
        f"{metadata.get('source_id', '')}_{object_stem or file_stem}_{series_name}",
        max_length=180,
    )
    return f"{unique_stem}_best_period.png"


def expected_normal_plot_paths(
    row: pd.Series | dict[str, Any],
) -> list[Path]:
    """Return every normal PNG required for one completed series plot."""
    primary = str(row.get("primary_classification", "")).strip().lower()
    folders = plot_review_folders(dict(row), primary)
    series_name = str(row.get("series", "")).strip()
    output_name = normal_plot_output_name(row, series_name)
    series_plot_root = S.plot_root() / _loading.sanitize_filename(series_name)
    return [series_plot_root / folder / output_name for folder in folders]


def normal_plot_outputs_are_complete(
    row: pd.Series | dict[str, Any],
) -> bool:
    """True only when all expected normal plot copies exist and are non-empty."""
    try:
        outputs = expected_normal_plot_paths(row)
    except (TypeError, ValueError):
        return False
    return bool(outputs) and all(output_file_is_complete(output) for output in outputs)


def output_file_is_complete(path: Path) -> bool:
    """Reject interrupted/corrupt PNGs rather than trusting a nonzero size."""
    if not path.is_file() or path.stat().st_size <= 0:
        return False
    if path.suffix.lower() == '.png' or path.name.lower().endswith('.png.tmp'):
        from PIL import Image
        try:
            with Image.open(path) as picture:
                picture.verify()
        except (OSError, SyntaxError, ValueError):
            return False
    return True


def save_figure(fig, path: Path, **kwargs) -> None:
    """Publish a PNG only after its complete temporary file validates."""
    import os
    import tempfile
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=path.stem + '_', suffix=path.suffix + '.tmp', dir=path.parent)
    os.close(descriptor)
    temporary = Path(name)
    try:
        fig.savefig(temporary, format=path.suffix.lstrip('.'), **kwargs)
        if not output_file_is_complete(temporary):
            raise OSError(f'Plot did not validate: {path}')
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def record_existing_normal_plot_paths(row: dict[str, Any]) -> None:
    """Record already-existing plot paths in the same fields used after saving."""
    outputs = expected_normal_plot_paths(row)
    folders = plot_review_folders(
        row,
        str(row.get("primary_classification", "")),
    )
    row["best_per_star_plot_path"] = str(outputs[0]) if outputs else ""
    row["plot_folders"] = ";".join(folder.as_posix() for folder in folders)
    row["plot_paths_all"] = ";".join(str(output) for output in outputs)
    row["plot_error"] = ""


# =============================================================================
# SAVE / CONFIG
# =============================================================================
def current_run_config() -> dict[str, Any]:
    config = {k: v for k, v in vars(S).items() if k.isupper() and k not in {"UNIVERSAL_ALIAS_PERIODS", "WINDOW_FREQUENCIES", "COLUMN_ALIASES"}}
    config["UNIVERSAL_ALIAS_PERIODS"] = S.UNIVERSAL_ALIAS_PERIODS
    config["WINDOW_FREQUENCIES"] = S.WINDOW_FREQUENCIES
    return {k: _loading.json_safe(v) for k, v in config.items()}


def write_run_config() -> None:
    S.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (S.OUTPUT_DIR / "tables").mkdir(parents=True, exist_ok=True)
    with open(S.OUTPUT_DIR / "run_config.json", "w", encoding="utf-8") as handle:
        json.dump(current_run_config(), handle, indent=2)


def completed_run_signature(files: list[Path]) -> str:
    """Fingerprint code, settings, and input-file state for no-op reruns."""
    script_path = Path(__file__).resolve()
    input_state = []
    for path in files:
        stat = path.stat()
        input_state.append(
            {
                "path": str(path.resolve()).casefold(),
                "size": int(stat.st_size),
                "mtime_ns": int(stat.st_mtime_ns),
            }
        )
    payload = {
        "script_sha256": hashlib.sha256(b"".join(p.read_bytes() for p in sorted(script_path.parent.glob("*.py")))).hexdigest(),
        "config": current_run_config(),
        "inputs": input_state,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def completed_run_is_unchanged(signature: str) -> bool:
    """Return True only when the last run completed and all its outputs remain."""
    marker = S.OUTPUT_DIR / "tables" / "run_complete.json"
    if not marker.is_file():
        return False
    try:
        state = json.loads(marker.read_text(encoding="utf-8"))
        if state.get("signature") != signature:
            return False
        outputs = [Path(value) for value in state.get("output_files", [])]
        return bool(outputs) and all(output_file_is_complete(path) for path in outputs)
    except Exception:
        return False


def mark_run_complete(signature: str) -> None:
    """Atomically record a successful run and every output it produced."""
    table_dir = S.OUTPUT_DIR / "tables"
    marker = table_dir / "run_complete.json"
    tmp = marker.with_suffix(".json.tmp")
    output_files = sorted(
        str(path.resolve())
        for root in [table_dir, S.plot_root()]
        if root.is_dir()
        for path in root.rglob("*")
        if path.is_file() and not path.name.endswith('.tmp')
        and path.resolve() not in {marker.resolve(), tmp.resolve()}
    )
    state = {
        "signature": signature,
        "completed_utc": datetime.now(timezone.utc).isoformat(),
        "output_files": output_files,
    }
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    tmp.replace(marker)




def clean_for_csv(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return rows containing only CSV-safe scalar/list-as-text values.

    This prevents accidental arrays, models, or nested payloads from being put
    into pandas, which can otherwise cause memory spikes during checkpointing.
    """
    cleaned: list[dict[str, Any]] = []
    for row in rows:
        out: dict[str, Any] = {}
        for key, value in row.items():
            if isinstance(value, (np.ndarray, list, tuple, set)):
                # Most intended list columns are already semicolon-separated.
                # If a list slips through, store a compact semicolon string.
                try:
                    out[key] = ";".join(str(_loading.json_safe(v)) for v in value)
                except Exception:
                    out[key] = str(type(value).__name__)
            elif isinstance(value, dict):
                # Avoid writing large nested objects to CSV.
                out[key] = json.dumps({k: _loading.json_safe(v) for k, v in value.items()}, ensure_ascii=False)
            else:
                out[key] = _loading.json_safe(value)
        cleaned.append(out)
    return cleaned


def safe_write_csv(rows_or_df: Any, path: Path, index: bool = False) -> None:
    """Write a CSV atomically and with a garbage-collection retry.

    The earlier version sometimes crashed during checkpoint writing after many
    files because large plot payloads were still held in memory. This helper is
    deliberately defensive so partial CSV files are not left behind.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        if isinstance(rows_or_df, pd.DataFrame):
            df = rows_or_df.copy()
        else:
            df = pd.DataFrame(clean_for_csv(list(rows_or_df)))
        df.to_csv(tmp, index=index)
        tmp.replace(path)
    except MemoryError:
        gc.collect()
        if isinstance(rows_or_df, pd.DataFrame):
            df = rows_or_df.copy()
        else:
            df = pd.DataFrame(clean_for_csv(list(rows_or_df)))
        df.to_csv(tmp, index=index)
        tmp.replace(path)
    finally:
        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass


def save_raw_checkpoint(summary_rows: list[dict[str, Any]], peak_rows_all: list[dict[str, Any]]) -> None:
    """Save raw per-series and peak tables during the run.

    This is intentionally done before final alias/harmonic decisions so that a
    crash still leaves restartable results on disk.
    """
    table_dir = S.OUTPUT_DIR / "tables"
    table_dir.mkdir(parents=True, exist_ok=True)
    safe_write_csv(summary_rows, table_dir / "ls_period_search_summary.csv")
    safe_write_csv(peak_rows_all, table_dir / "ls_period_search_peaks.csv")


def build_processed_keys_from_rows(summary_rows: list[dict[str, Any]]) -> set[tuple[str, str]]:
    return {
        (str(r.get("file", "")), str(r.get("series", "")))
        for r in summary_rows
        if str(r.get("status", "")).lower() in {"ok", "skipped", "failed"}
    }


def cache_schema_missing(
    summary_columns: set[str],
    peak_columns: set[str],
) -> tuple[set[str], set[str]]:
    """Return fields missing from cached tables required by this pipeline."""
    return (
        S.SUMMARY_CACHE_REQUIRED_COLUMNS - summary_columns,
        S.PEAK_CACHE_REQUIRED_COLUMNS - peak_columns,
    )


def manual_target_tokens(values: list[str | Path]) -> set[str]:
    """Normalise full paths, Windows paths, basenames, stems and source IDs."""
    tokens: set[str] = set()
    for value in values:
        raw = str(value).strip()
        if not raw:
            continue
        normalised = raw.replace("\\", "/")
        basename = normalised.rsplit("/", 1)[-1]
        stem = Path(basename).stem
        for token in [raw, normalised, basename, stem]:
            token = token.strip().casefold()
            if token:
                tokens.add(token)
    return tokens


def manual_target_matches(path: Path, metadata: dict[str, Any], tokens: set[str]) -> bool:
    if not tokens:
        return False
    identifiers = {
        str(path).replace("\\", "/").casefold(),
        path.name.casefold(),
        path.stem.casefold(),
        str(metadata.get("file", "")).casefold(),
        Path(str(metadata.get("file", ""))).stem.casefold(),
        str(metadata.get("source_id", "")).strip().casefold(),
        str(metadata.get("object_name", "")).strip().casefold(),
    }
    return bool(tokens.intersection(x for x in identifiers if x))


def add_explicit_diagnostic_files(files: list[Path]) -> list[Path]:
    """Add selected diagnostic files that live outside INPUT_DIR.

    Entries that are source IDs, basenames, or nonexistent paths remain useful
    for matching files already discovered under INPUT_DIR. Existing explicit
    file paths are appended so they can be searched, checkpointed, and plotted.
    """
    combined = list(files)
    known = {str(path.resolve()).casefold() for path in combined}
    for value in [*S.ALIAS_SELECTED_FILES, *S.HARMONIC_SELECTED_FILES]:
        candidate = Path(str(value).strip()).expanduser()
        if not candidate.is_file():
            continue
        resolved_key = str(candidate.resolve()).casefold()
        if resolved_key not in known:
            combined.append(candidate)
            known.add(resolved_key)
    return combined

def save_all_tables(summary_rows: list[dict[str, Any]], peak_rows_all: list[dict[str, Any]], current_inventory: pd.DataFrame, memory_inventory: pd.DataFrame, recommendations: pd.DataFrame) -> None:
    table_dir = S.OUTPUT_DIR / "tables"
    table_dir.mkdir(parents=True, exist_ok=True)
    safe_write_csv(summary_rows, table_dir / "ls_period_search_summary.csv")
    safe_write_csv(peak_rows_all, table_dir / "ls_period_search_peaks.csv")
    safe_write_csv(recommendations if recommendations is not None else pd.DataFrame(), table_dir / "source_period_recommendations.csv")
    safe_write_csv(_recommend.source_consensus_table(summary_rows, recommendations), table_dir / "ls_source_consensus.csv")
    safe_write_csv(_validation.validation_summary_table(summary_rows, recommendations), table_dir / "ls_validation_summary.csv")
    if current_inventory is not None and not current_inventory.empty:
        safe_write_csv(current_inventory, table_dir / "field_alias_inventory_current.csv")
    if memory_inventory is not None and not memory_inventory.empty:
        safe_write_csv(memory_inventory, table_dir / "field_alias_memory.csv")
