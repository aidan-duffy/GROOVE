"""Download defaults. Authentication uses only the ATLAS_TOKEN environment variable."""
from __future__ import annotations
import threading
from typing import Any, Dict, Sequence

INPUT_CSV = ""
OUTPUT_ROOT = ""
GAIA_ID_FILTER = ""
GROUP_FILTER = ""
FILTERS: Dict[str, Any] = {}
GROUP_COLUMN = ""
YEARS_TO_DOWNLOAD = "full"
ATLAS_MODE = "reduced"
DRY_RUN = False
LIMIT_TARGETS = None
START_INDEX = 0
RETRY_FAILED_TARGETS = True
FORCE_REDOWNLOAD = False
MINUTES_PER_TARGET_ESTIMATE = 20.0
POLL_SECONDS = 10.0
MAX_RETRIES = 8
RETRY_DELAY_SECONDS = 20.0
MAX_POLL_HOURS = 0.0
RUN_NAME = "full_reduced"
END_DATE_UTC = None
MATCH_RADIUS_ARCSEC = None
BASEURL = "https://fallingstar-data.com/forcedphot"
CONNECT_TIMEOUT_SECONDS = 20
READ_TIMEOUT_SECONDS = 180
FILE_REPLACE_MAX_ATTEMPTS = 30
FILE_REPLACE_INITIAL_DELAY_SECONDS = 0.10
FILE_REPLACE_MAX_DELAY_SECONDS = 2.0
COLUMN_CANDIDATES: Dict[str, Sequence[str]] = {
    "gaia": (
        "GaiaDR3", "Gaia_DR3", "Gaia DR3", "gaia_dr3", "gaia_source_id",
        "source_id", "SOURCE_ID", "DR3_source_id", "dr3_source_id",
    ),
    # Optional grouping column: used for sub-folders and for --group.
    "group": (
        "group", "Group", "field", "Field", "sample", "Sample",
        "cluster_name", "Cluster", "cluster", "Name", "association",
    ),
    "ra": (
        "pull_ra", "RAdeg", "ra", "RA", "RA_ICRS", "RAJ2000", "_RAJ2000",
        "ra_deg", "RA_deg",
    ),
    "dec": (
        "pull_dec", "DEdeg", "dec", "Dec", "DEC", "DE_ICRS", "DEJ2000",
        "_DEJ2000", "dec_deg", "DEC_deg",
    ),
    "atlas_id": (
        "ATOID", "ATLAS_ID", "atlas_id", "ATLASID", "atlas_object_id",
        "object_id",
    ),
    "var_class": (
        "Class", "class", "variability_class", "var_class", "VarClass",
        "classification", "type",
    ),
    "period": (
        "best_period_days", "fp-period", "ls-Pday", "period", "Period",
        "period_days", "catalogue_period", "fp-lngfitper", "fp-LSper",
        "fp_LSperiod",
    ),
    "angdist": (
        "angDist", "angdist", "separation", "separation_arcsec", "sep_arcsec",
    ),
}
STOP_EVENT = threading.Event()
