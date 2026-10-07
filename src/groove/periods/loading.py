from __future__ import annotations
import re
from pathlib import Path
from typing import Any
import numpy as np
import pandas as pd
from . import settings as S




# =============================================================================
# GENERAL HELPERS
# =============================================================================
def safe_float(value: Any, default: float = np.nan) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out if np.isfinite(out) else default


def first_value(df: pd.DataFrame, columns: list[str], default: Any = "") -> Any:
    for col in columns:
        if col in df.columns:
            values = df[col].dropna()
            if len(values):
                return values.iloc[0]
    return default


def first_numeric(df: pd.DataFrame, columns: list[str], default: float = np.nan) -> float:
    for col in columns:
        if col in df.columns:
            values = pd.to_numeric(df[col], errors="coerce")
            values = values[np.isfinite(values)]
            if len(values):
                return float(values.iloc[0])
    return default


def sanitize_filename(text: Any, max_length: int = 120) -> str:
    value = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(text)).strip("_.")
    return (value or "unknown")[:max_length]


def robust_sigma(values: np.ndarray) -> float:
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if len(values) == 0:
        return np.nan
    median = np.median(values)
    mad = np.median(np.abs(values - median))
    sigma = 1.4826 * mad
    if not np.isfinite(sigma) or sigma <= 0:
        sigma = np.std(values)
    return float(sigma) if np.isfinite(sigma) and sigma > 0 else np.nan


def json_safe(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return None if not np.isfinite(value) else float(value)
    if isinstance(value, float):
        return None if not np.isfinite(value) else value
    if isinstance(value, set):
        return sorted(value)
    return value


def parse_float_list(cell: object) -> list[float]:
    if cell is None or (isinstance(cell, float) and np.isnan(cell)):
        return []
    if isinstance(cell, (list, tuple, np.ndarray)):
        return [float(x) for x in cell if np.isfinite(float(x))]
    out: list[float] = []
    for token in str(cell).split(";"):
        token = token.strip()
        if not token:
            continue
        try:
            val = float(token)
            if np.isfinite(val):
                out.append(val)
        except ValueError:
            continue
    return out


# =============================================================================
# INPUT NORMALISATION
# =============================================================================
def normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [str(col).strip() for col in out.columns]

    rename: dict[str, str] = {}
    for standard, aliases in S.COLUMN_ALIASES.items():
        if standard in out.columns:
            continue
        for alias in aliases:
            if alias in out.columns:
                rename[alias] = standard
                break
    out = out.rename(columns=rename)

    if "MJD" not in out.columns:
        raise ValueError(f"No time/MJD column found. Columns: {list(out.columns)}")
    if "F" not in out.columns:
        out["F"] = "single"

    for col in ["MJD", "m", "dm", "uJy", "duJy"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")

    out["F"] = out["F"].astype(str).str.strip().str.lower()

    if "final_keep" in out.columns:
        keep = out["final_keep"]
        if keep.dtype == bool:
            out = out.loc[keep].copy()
        else:
            keep_text = keep.astype(str).str.strip().str.lower()
            out = out.loc[keep_text.isin({"true", "1", "yes", "y"})].copy()

    return out


def extract_source_id(df: pd.DataFrame, stem: str) -> str:
    value = first_value(df, S.SOURCE_ID_COLUMNS, default="")
    if str(value).strip():
        return str(value).strip()
    match = re.search(r"(?<!\d)(\d{15,22})(?!\d)", stem)
    return match.group(1) if match else stem.removesuffix("_cleaned")


def extract_metadata(df: pd.DataFrame, path: Path) -> dict[str, Any]:
    return {
        "file": path.name,
        "source_id": str(extract_source_id(df, path.stem)),
        "object_name": str(first_value(df, S.OBJECT_NAME_COLUMNS, default=path.stem)),
        "cluster_name": str(first_value(df, S.CLUSTER_COLUMNS, default="")),
        "catalogue_class": str(first_value(df, S.CLASS_COLUMNS, default="")),
        "embedded_catalogue_period_days": first_numeric(df, S.PERIOD_COLUMNS, default=np.nan),
        "ra_deg": first_numeric(df, S.RA_COLUMNS, default=np.nan),
        "dec_deg": first_numeric(df, S.DEC_COLUMNS, default=np.nan),
    }


# =============================================================================
# LIGHT CURVE PREPARATION
# =============================================================================
def magnitude_series(sub: pd.DataFrame) -> dict[str, np.ndarray] | None:
    if not {"MJD", "m", "dm", "F"}.issubset(sub.columns):
        return None
    work = sub.copy()
    good = np.isfinite(work["MJD"]) & np.isfinite(work["m"]) & np.isfinite(work["dm"]) & (work["dm"] > 0)
    work = work.loc[good].copy()
    if len(work) == 0:
        return None
    medians = work.groupby("F")["m"].transform("median")
    return {
        "time_mjd": work["MJD"].to_numpy(dtype=float),
        "band": work["F"].astype(str).to_numpy(),
        "signal": work["m"].to_numpy(dtype=float) - medians.to_numpy(dtype=float),
        "error": work["dm"].to_numpy(dtype=float),
        "plot_signal": work["m"].to_numpy(dtype=float),
        "plot_error": work["dm"].to_numpy(dtype=float),
        "signal_type": "magnitude",
        "plot_signal_type": "magnitude",
        "invert_y": True,
    }


def flux_series(sub: pd.DataFrame) -> dict[str, np.ndarray] | None:
    if not {"MJD", "uJy", "duJy", "F"}.issubset(sub.columns):
        return None
    work = sub.copy()
    good = np.isfinite(work["MJD"]) & np.isfinite(work["uJy"]) & np.isfinite(work["duJy"]) & (work["duJy"] > 0)
    work = work.loc[good].reset_index(drop=True).copy()
    if len(work) == 0:
        return None
    signal = np.full(len(work), np.nan, dtype=float)
    error = np.full(len(work), np.nan, dtype=float)
    for _, positions in work.groupby("F").groups.items():
        pos = np.asarray(list(positions), dtype=int)
        y = work.loc[pos, "uJy"].to_numpy(dtype=float)
        e = work.loc[pos, "duJy"].to_numpy(dtype=float)
        median = float(np.median(y))
        scale = abs(median) if np.isfinite(median) and median != 0 else robust_sigma(y)
        if not np.isfinite(scale) or scale <= 0:
            scale = float(np.median(e))
        if not np.isfinite(scale) or scale <= 0:
            continue
        signal[pos] = (y - median) / scale
        error[pos] = e / scale
    good_out = np.isfinite(signal) & np.isfinite(error) & (error > 0)
    return {
        "time_mjd": work["MJD"].to_numpy(dtype=float)[good_out],
        "band": work["F"].astype(str).to_numpy()[good_out],
        "signal": signal[good_out],
        "error": error[good_out],
        "plot_signal": work["uJy"].to_numpy(dtype=float)[good_out],
        "plot_error": work["duJy"].to_numpy(dtype=float)[good_out],
        "signal_type": "flux",
        "plot_signal_type": "flux",
        "invert_y": False,
    }


def prepare_series(df: pd.DataFrame, series_name: str) -> dict[str, Any] | None:
    if series_name == "combined":
        sub = df.copy()
        if S.ALLOWED_BANDS:
            available = set(sub["F"].astype(str).unique())
            if available.intersection(S.ALLOWED_BANDS):
                sub = sub.loc[sub["F"].isin(S.ALLOWED_BANDS)].copy()
    else:
        sub = df.loc[df["F"].eq(series_name)].copy()
        if len(sub) < S.MIN_POINTS_PER_INDIVIDUAL_BAND:
            return None

    prepared = magnitude_series(sub) or flux_series(sub)
    if prepared is None:
        return None

    order = np.argsort(prepared["time_mjd"], kind="mergesort")
    for key in ["time_mjd", "band", "signal", "error", "plot_signal", "plot_error"]:
        prepared[key] = np.asarray(prepared[key])[order]

    prepared["series_name"] = series_name
    prepared["n_points"] = int(len(prepared["time_mjd"]))
    prepared["n_bands"] = int(len(np.unique(prepared["band"])))
    prepared["bands_present"] = ",".join(sorted(set(prepared["band"].astype(str))))
    if prepared["n_points"]:
        prepared["mjd_min"] = float(np.min(prepared["time_mjd"]))
        prepared["mjd_max"] = float(np.max(prepared["time_mjd"]))
        prepared["baseline_days"] = prepared["mjd_max"] - prepared["mjd_min"]
        prepared["time"] = prepared["time_mjd"] - prepared["mjd_min"]
    else:
        prepared["mjd_min"] = np.nan
        prepared["mjd_max"] = np.nan
        prepared["baseline_days"] = np.nan
        prepared["time"] = np.array([], dtype=float)
    return prepared
