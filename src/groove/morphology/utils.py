from __future__ import annotations
import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
import numpy as np
import pandas as pd



# ===========================================================================
# Small utilities
# ===========================================================================


def iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def finite_float(value: Any, default: float = np.nan) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out if np.isfinite(out) else default


def bool_value(value: Any) -> bool:
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if value is None or (isinstance(value, float) and not np.isfinite(value)):
        return False
    return str(value).strip().lower() in {"true", "1", "yes", "y", "t"}


def bool_series(series: pd.Series) -> pd.Series:
    return series.map(bool_value).astype(bool)


def split_tags(value: Any) -> List[str]:
    if value is None or (isinstance(value, float) and not np.isfinite(value)):
        return []
    return [part.strip() for part in str(value).replace(",", ";").split(";") if part.strip()]


def join_tags(values: Iterable[str]) -> str:
    seen, out = set(), []
    for value in values:
        value = str(value).strip()
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return ";".join(out)


def clean_source_id(value: Any) -> str:
    """Gaia IDs are 19 digits; never let them through a float."""
    if value is None:
        return ""
    if isinstance(value, float):
        if not np.isfinite(value):
            return ""
        value = "%d" % int(value)
    text = str(value).strip().strip("'\"")
    if not text or text.lower() in {"nan", "none", "<na>"}:
        return ""
    match = re.fullmatch(r"(\d+)\.0+", text)
    if match:
        text = match.group(1)
    if re.fullmatch(r"\d+(\.\d+)?[eE][+-]?\d+", text):
        try:
            text = "%d" % int(float(text))
        except (ValueError, OverflowError):
            pass
    return text


def robust_scale(values: Sequence[float]) -> float:
    array = np.asarray(values, dtype=float)
    array = array[np.isfinite(array)]
    if not len(array):
        return np.nan
    return float(1.4826 * np.median(np.abs(array - np.median(array))))


def spread_scale(values: Sequence[float]) -> float:
    """Percentile width. Honest about heavy tails where MAD is not."""
    array = np.asarray(values, dtype=float)
    array = array[np.isfinite(array)]
    if len(array) < 8:
        return robust_scale(array)
    return float(0.5 * (np.percentile(array, 84) - np.percentile(array, 16)))


def robust_amplitude(values: Sequence[float]) -> float:
    array = np.asarray(values, dtype=float)
    array = array[np.isfinite(array)]
    return float(np.percentile(array, 95) - np.percentile(array, 5)) if len(array) >= 2 else np.nan


def safe_corr(left: Sequence[float], right: Sequence[float], minimum: int = 4) -> float:
    a = np.asarray(left, dtype=float)
    b = np.asarray(right, dtype=float)
    valid = np.isfinite(a) & np.isfinite(b)
    if valid.sum() < minimum or np.nanstd(a[valid]) <= 0 or np.nanstd(b[valid]) <= 0:
        return np.nan
    return float(np.corrcoef(a[valid], b[valid])[0, 1])


def circular_fill(values: Sequence[float]) -> np.ndarray:
    array = np.asarray(values, dtype=float).copy()
    good = np.flatnonzero(np.isfinite(array))
    if len(good) == 0:
        return np.zeros(len(array), dtype=float)
    if len(good) == 1:
        return np.full(len(array), array[good[0]], dtype=float)
    n = len(array)
    xp = np.r_[good - n, good, good + n]
    fp = np.r_[array[good], array[good], array[good]]
    return np.interp(np.arange(n), xp, fp)


def longest_circular_run(mask: Sequence[bool]) -> int:
    values = np.asarray(mask, dtype=bool)
    if not values.any():
        return 0
    if values.all():
        return int(len(values))
    doubled = np.r_[values, values]
    best = current = 0
    for flag in doubled:
        current = current + 1 if flag else 0
        best = max(best, current)
    return int(min(best, len(values)))


def hash_json(payload: Any) -> str:
    import hashlib
    text = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def file_fingerprint(path: Path) -> str:
    try:
        info = path.stat()
        return "%d_%d" % (info.st_size, int(info.st_mtime))
    except OSError:
        return "missing"


def safe_name(value: Any, limit: int = 90) -> str:
    text = re.sub(r"[^A-Za-z0-9._+-]+", "_", str(value)).strip("_")
    return text[:limit] or "unnamed"


def atomic_write_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    frame.to_csv(tmp, index=False, encoding="utf-8")
    tmp.replace(path)


def atomic_write_json(payload: Mapping[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    tmp.replace(path)


def deep_merge(base: Mapping[str, Any], update: Mapping[str, Any]) -> Dict[str, Any]:
    out = dict(base)
    for key, value in update.items():
        if isinstance(value, Mapping) and isinstance(out.get(key), Mapping):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def setup_logging(version_dir: Optional[Path] = None, verbose: bool = False) -> logging.Logger:
    logger = logging.getLogger("morphology")
    logger.handlers = []
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%H:%M:%S"))
    logger.addHandler(console)
    if version_dir is not None:
        log_dir = Path(version_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(log_dir / ("run_%s.log" % stamp()), encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
    return logger


# ===========================================================================
# Input discovery and light-curve loading
# ===========================================================================


def first_column(frame: pd.DataFrame, aliases: Sequence[str]) -> Optional[str]:
    lookup = {str(c).strip().lower(): c for c in frame.columns}
    for alias in aliases:
        if alias.strip().lower() in lookup:
            return lookup[alias.strip().lower()]
    return None
