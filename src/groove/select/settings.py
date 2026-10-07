"""Defaults for the selection stage. All values from thesis Section 2.3."""
from __future__ import annotations

from pathlib import Path

CLEANED_DIR: Path | None = None      # folder of *_cleaned.csv + cleaning summary
SELECTED_DIR: Path | None = None     # where passing light curves are placed
SUMMARY_NAME = "cleaning_summary.csv"

MIN_POINTS = 100                     # measurements remaining after cleaning
MIN_POINTS_PER_BAND = 30             # in at least one filter
MIN_BASELINE_DAYS = 365.0            # span of post-QC data
MAX_REMOVED_FRACTION = 0.5           # stars losing more than this are dropped
MAX_MEDIAN_UNCERTAINTY_MAG = 0.2     # must be met in at least one filter

LINK_INSTEAD_OF_COPY = True          # hard-link selected files (falls back to copy)
