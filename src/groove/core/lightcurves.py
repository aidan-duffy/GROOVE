"""File-naming contract shared by all stages.

The downloader writes  <cluster>__GaiaDR3_<id>__...csv,
the cleaner appends    _cleaned.csv,
and every later stage recovers the Gaia DR3 ID from either the filename or the
`target_GaiaDR3` column that the downloader stores in each file.
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

GAIA_ID_IN_NAME = re.compile(r"GaiaDR3_(\d{5,25})")
CLEANED_SUFFIX = "_cleaned.csv"
SUMMARY_FILENAMES = {
    "cleaning_summary.csv",
    "cleaning_reason_counts.csv",
}


def gaia_id_from_name(path: str | Path) -> str:
    match = GAIA_ID_IN_NAME.search(Path(path).name)
    return match.group(1) if match else ""


def gaia_id_from_frame(df: pd.DataFrame) -> str:
    for column in ("target_GaiaDR3", "GaiaDR3", "gaia_dr3", "source_id"):
        if column in df.columns:
            values = df[column].dropna().astype(str)
            if len(values):
                return values.iloc[0].strip()
    return ""


def source_id(path: str | Path, df: pd.DataFrame | None = None) -> str:
    """Gaia DR3 ID for a light-curve file, from its contents or its name."""
    if df is not None:
        found = gaia_id_from_frame(df)
        if found:
            return found
    return gaia_id_from_name(path) or Path(path).stem


def find_lightcurve_files(folder: Path, cleaned: bool | None = None) -> list[Path]:
    files = []
    for path in sorted(Path(folder).rglob("*.csv")):
        if path.name in SUMMARY_FILENAMES:
            continue
        is_cleaned = path.name.endswith(CLEANED_SUFFIX)
        if cleaned is None or cleaned == is_cleaned:
            files.append(path)
    return files
