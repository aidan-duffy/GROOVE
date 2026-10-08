"""Atomic download files and metadata shared with later stages."""
from __future__ import annotations
import hashlib
import json
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Optional
import pandas as pd
from . import settings as S
from . import targets as _targets

def safe_component(value: object, max_len: int = 80) -> str:
    text = _targets.clean_cell(value)
    text = re.sub(r"[^A-Za-z0-9_.+\-]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_.")
    if not text:
        text = "unknown"
    if len(text) <= max_len:
        return text
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]
    return f"{text[: max(1, max_len - 10)]}__{digest}"

def replace_file_with_retry(temp_path: Path, destination: Path) -> None:
    """Atomically replace destination, retrying transient Windows file locks."""
    delay = S.FILE_REPLACE_INITIAL_DELAY_SECONDS
    last_error: Optional[OSError] = None

    for attempt in range(1, S.FILE_REPLACE_MAX_ATTEMPTS + 1):
        try:
            os.replace(temp_path, destination)
            return
        except PermissionError as exc:
            last_error = exc
        except OSError as exc:
            # Windows sharing violations are commonly WinError 5 or 32. Other
            # operating systems may expose EACCES/EPERM instead. Retry only these
            # lock-like errors; propagate unrelated filesystem failures.
            winerror = getattr(exc, "winerror", None)
            if winerror not in (5, 32) and getattr(exc, "errno", None) not in (1, 13):
                raise
            last_error = exc

        if attempt < S.FILE_REPLACE_MAX_ATTEMPTS:
            time.sleep(delay)
            delay = min(S.FILE_REPLACE_MAX_DELAY_SECONDS, delay * 1.5)

    raise PermissionError(
        f"Could not replace {destination} after {S.FILE_REPLACE_MAX_ATTEMPTS} "
        "attempts. Close this CSV in Excel and disable any Explorer preview pane "
        "that has it open, then rerun the same job."
    ) from last_error

def atomic_write_dataframe(df: pd.DataFrame, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            suffix=".tmp",
            prefix=f".{destination.stem}_",
            dir=destination.parent,
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            df.to_csv(handle, index=False)
            handle.flush()
            os.fsync(handle.fileno())
        replace_file_with_retry(temp_path, destination)
    finally:
        if temp_path is not None and temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass

def atomic_write_json(data: Dict[str, Any], destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".tmp",
            prefix=f".{destination.stem}_",
            dir=destination.parent,
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            json.dump(data, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        replace_file_with_retry(temp_path, destination)
    finally:
        if temp_path is not None and temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass

def mode_to_use_reduced(mode: str) -> str:
    return "true" if mode == "reduced" else "false"

def add_target_metadata(df: pd.DataFrame, row: Dict[str, Any]) -> pd.DataFrame:
    output = df.copy()
    metadata = [
        ("target_id", row.get("target_id", "")),
        ("target_GaiaDR3", row.get("gaia_dr3_id", "")),
        ("target_ATLAS_ID", row.get("atlas_id", "")),
        ("target_group", row.get("group", "")),
        ("target_variability_class", row.get("variability_class", "")),
        ("target_catalogue_period_days", row.get("catalogue_period_days", "")),
        ("target_ra_used", row.get("ra", "")),
        ("target_dec_used", row.get("dec", "")),
    ]
    for position, (name, value) in enumerate(metadata):
        if name in output.columns:
            output[name] = value
        else:
            output.insert(position, name, value)
    return output


def valid_download_file(path: Path) -> bool:
    """Reject truncated/non-photometry files before declaring a resumed target done."""
    if not path.is_file() or path.stat().st_size == 0:
        return False
    try:
        frame = pd.read_csv(path, nrows=1)
        return not frame.empty and {'MJD', 'F'}.issubset(frame.columns)
    except (OSError, ValueError, pd.errors.ParserError, pd.errors.EmptyDataError):
        return False
