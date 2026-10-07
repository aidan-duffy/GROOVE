from __future__ import annotations
from pathlib import Path


try:
    from astropy.timeseries import BoxLeastSquares
except Exception:  # astropy versions/environments without BLS
    BoxLeastSquares = None


# =============================================================================
# 1. PATHS
# =============================================================================
INPUT_DIR: Path = Path("UNSET_INPUT")    # set by the pipeline config (selected cleaned light curves)
OUTPUT_DIR: Path = Path("UNSET_OUTPUT")  # set by the pipeline config
PLOT_DIR: Path | None = None             # set by the pipeline config; None = OUTPUT_DIR/"plots"


def plot_root() -> Path:
    """Folder that receives every figure this stage makes."""
    return Path(PLOT_DIR) if PLOT_DIR else OUTPUT_DIR / "plots"


FILE_GLOB = "*cleaned.csv"
# Optional previous/non-variable/control summaries. These should be summary CSVs
# produced by this script or compatible scripts. They are used only for alias
# learning, not for choosing an individual star's period directly.
REFERENCE_SUMMARY_CSVS: list[Path] = []

# Optional external catalogue for validation only.
CATALOG_CSV: Path | None = None
CATALOG_ID_COLUMN = "gaia_dr3"
CATALOG_PERIOD_COLUMN = "period_days"


# =============================================================================
# 2. RUN CONTROL
# =============================================================================
# Resume from the per-file checkpoint tables by default. A fully processed
# light-curve file is skipped before pd.read_csv, so interrupted large runs
# continue at the first unfinished file instead of loading earlier files again.
SKIP_ALREADY_PROCESSED = True
CHECKPOINT_EVERY_N_FILES = 500
MAX_FILES: int | None = None
SERIES_TO_RUN = ["combined", "o", "c"]
ALLOWED_BANDS = {"c", "o"}

MIN_POINTS = 50
MIN_BASELINE_DAYS = 20.0
MIN_POINTS_PER_INDIVIDUAL_BAND = 30


# =============================================================================
# 3. PERIOD SEARCH SETTINGS
# =============================================================================
MIN_PERIOD_DAYS = 0.5
MAX_PERIOD_DAYS = 200.0
MIN_CYCLES_AT_MAX_PERIOD = 3.0

LS_SAMPLES_PER_PEAK = 15
LS_NORMALIZATION = "standard"
LS_NTERMS = 1
LS_FAP_METHOD = "baluev"
N_TOP_PEAKS = 12
PEAK_MIN_SEPARATION_FRACTION = 0.02

# Optional BLS diagnostic. Disabled by default for ATLAS because BLS is very
# prone to 0.5/0.66/1/2-day cadence aliases in sparse ground-based data.
RUN_BLS = True
ALLOW_BLS_TO_SET_RECOMMENDED_PERIOD = False
BLS_MIN_PERIOD_DAYS = 0.5
BLS_MAX_PERIOD_DAYS = 50.0
BLS_DURATIONS_DAYS = [0.05, 0.10, 0.20, 0.40]
BLS_SAMPLES_PER_PEAK = 15


# =============================================================================
# 4. ALIAS MEMORY AND ALIAS SCORING
# =============================================================================
RUN_ALIAS_LEARNING = True
UPDATE_ALIAS_MEMORY = True
ALIAS_MEMORY_CSV = OUTPUT_DIR / "tables" / "field_alias_memory.csv"
ALIAS_LEARNING_SERIES = "combined"

FIELD_BIN_DEG = 5.0
FIELD_MIN_STARS = 8
FIELD_ALIAS_MIN_FRACTION = 0.30
FIELD_PERIOD_CLUSTER_TOLERANCE = 0.01
FIELD_ALIAS_MATCH_TOLERANCE = 0.02
MAX_PEAKS_FOR_FIELD_LEARNING = 12

# For replacing an alias-like top peak, only use a strong alternative. This is
# deliberately conservative: alias correction flags more often than it changes.
REPLACEMENT_MIN_POWER_FRACTION = 0.25
MAX_REPLACEMENT_RANK = 3

# Universal cadence aliases. These are penalised but not deleted.
UNIVERSAL_ALIAS_PERIODS: dict[str, float] = {
    "third_day": 1.0 / 3.0,
    "half_day": 0.5,
    "two_thirds_day": 2.0 / 3.0,
    "sidereal_day": 0.99726957,
    "one_day": 1.0,
    "one_and_half_day": 1.5,
    "two_day": 2.0,
    "half_lunar": 29.53059 / 2.0,
    "lunar": 29.53059,
    "half_year": 365.25 / 2.0,
    "year": 365.25,
}
UNIVERSAL_ALIAS_TOLERANCE = 0.015

WINDOW_FREQUENCIES = {
    "daily": 1.0,
    "sesquidaily": 1.5,   # 2/3 day
    "lunar": 1.0 / 29.53059,
    "yearly": 1.0 / 365.25,
}
WINDOW_POWER_WARNING = 0.40

# Candidate scoring. Alias penalty cannot by itself reject a period if the
# source gives strong support for it.
ALIAS_SCORE_THRESHOLD = 0.50
ALIAS_PENALTY_WEIGHT = 0.55
CROSS_FILTER_REWARD = 0.25
SOURCE_COHERENCE_REWARD = 0.20


# =============================================================================
# 5. HARMONIC / 2P SETTINGS
# =============================================================================
HARMONIC_MAX_ORDER = 6
HARMONIC_TOLERANCE_FRACTION = 0.02
CATALOG_MATCH_TOLERANCE_FRACTION = 0.03

# Odd/even test: fold at 2P and compare the first and second P-long cycles.
# If they differ, the longer 2P period is more physically meaningful.
RUN_ODD_EVEN_2P_TEST = True
ODD_EVEN_N_PHASE_BINS = 30
ODD_EVEN_MIN_POINTS_PER_BIN = 5
ODD_EVEN_MIN_VALID_BINS = 8
ODD_EVEN_MIN_MEDIAN_ABS_Z = 2.8
ODD_EVEN_MIN_SIGNIFICANT_BIN_FRACTION = 0.20


# =============================================================================
# 6. PLOTTING
# =============================================================================
PLOT_MODE = "all"  # all | none

# Force the main phase-fold panels to use this period in days. This changes
# only the visual fold: LS/BLS searches, alias handling and recommended periods
# are still calculated normally. Set to None to restore automatic folding.
FORCED_FOLD_PERIOD_DAYS: float | None = None

# For large runs, do NOT keep full light-curve arrays and periodogram grids in
# memory until the end. This was the cause of crashes on large batches. The code
# now streams raw results to disk, then re-runs only the plotting step at the end.
KEEP_PLOT_PAYLOADS_IN_MEMORY = False
MAKE_PLOTS_AFTER_FINAL = True
# Resume an interrupted second plotting pass by reusing normal plots only when
# every file expected for that series already exists and is non-empty. Set this
# to False when plot styling/settings have changed and every plot must be redrawn.
SKIP_ALREADY_PLOTTED = False
PLOT_PERIOD_AXIS_LOG = True
PLOT_CATALOGUE_PERIOD_IN_LEGEND = True
PLOT_DPI = 250
PLOT_SIGMA_LIMIT: float | None = 6.0
PLOT_TWO_PHASE_CYCLES = True
# Colour the phase-folded data by equal parts of the observed baseline.
# Band identity is still shown by the existing circle/square markers.
PLOT_TIME_SEGMENTS = 6
# The first four retain the original four-segment colour scheme. Increasing the
# segment count adds colours from the remainder of this stable palette.
PLOT_TIME_COLOR_PALETTE = [
    "tab:blue", "tab:orange", "tab:green", "tab:red",
    "tab:purple", "tab:brown", "tab:pink", "tab:gray",
    "tab:olive", "tab:cyan",
]
PLOT_TIME_SEGMENT_COLORS = PLOT_TIME_COLOR_PALETTE[:PLOT_TIME_SEGMENTS]
BEST_PER_STAR_DIRNAME = "best_per_star"
BAND_MARKERS = {"c": "o", "o": "s", "single": "o"}

# Optional expanded phase-fold diagnostics. These are visual review products
# only: they do not change the alias correction, harmonic tests or recommended
# period selected by the main pipeline.
# For a fast diagnostics-only rerun, keep SKIP_ALREADY_PROCESSED=True and set
# MAKE_PLOTS_AFTER_FINAL=False; the selections below will still be processed.
AUTO_PLOT_ALIAS_SUSPECTS = False
ALIAS_SELECTED_FILES: list[str | Path] = []
ALIAS_N_PEAKS_TO_PLOT = 3
ALIAS_INCLUDE_RECOMMENDED_IF_OUTSIDE_TOP_N = True

AUTO_PLOT_HARMONIC_SUSPECTS = True
HARMONIC_SELECTED_FILES: list[str | Path] = []
HARMONIC_PERIOD_FACTORS = [0.5, 1.0, 2.0]

# "recommended" makes one diagnostic figure using the series that supplied the
# source period. "all" makes one figure for every successful series.
EXTRA_FOLD_SERIES_MODE = "recommended"  # recommended | all
EXTRA_FOLD_MAX_COLUMNS = 3

# Extra diagnostic figures live inside the same alias/harmonic review folders
# as the normal plots.  This keeps every product for one review reason together.
EXTRA_FOLD_SUBDIR = "extra_phase_folds"

# Cached tables from another pipeline/version must never be silently reused.
# If the required analysis fields are absent, the current pipeline starts a
# clean analysis in this OUTPUT_DIR and overwrites the incompatible tables.
RESTART_IF_CACHE_SCHEMA_INCOMPATIBLE = True

# =============================================================================
# 6B. SOURCE-LEVEL LABELS, NON-VARIABLE DETECTION AND CROSS-FILTER DIAGNOSTICS
# =============================================================================
# These are recommendation labels, not hard truth labels. They are designed to
# keep the science sample usable while making ambiguity explicit.
RECOMMENDATION_LABELS = [
    "strong", "alias_possible", "harmonic_possible", "weak_or_ambiguous", "nonvar"
]
TAG_FOLDER_MAP = {
    "strong": "strong",
    "alias_possible": "alias",
    "harmonic_possible": "harmonic",
    "weak_or_ambiguous": "weak_or_ambiguous",
    "nonvar": "nonvar",
}
TAG_COLORS = {
    "strong": "#2ecc71",
    "alias_possible": "#f39c12",
    "harmonic_possible": "#9b59b6",
    "weak_or_ambiguous": "#f39c12",
    "nonvar": "#e74c3c",
}

# A source/series is treated as a significant periodic detection if the LS FAP
# is good OR the peak/fold SNR is good. The OR is intentional: long-baseline
# survey light curves can have conservative/unstable FAP behaviour, while real
# dip-like or colour-dependent signals may be clearer in the folded curve.
FAP_THRESHOLD = 0.01
PERIODOGRAM_SNR_THRESHOLD = 3.0
FOLD_SNR_THRESHOLD = 3.0

# Peak-dominance tests.  These are the first pass for deciding whether the
# light curve has one clean periodic signal before alias/harmonic warnings are
# considered.
STRONG_BEST_SECOND_RATIO = 1.5
STRONG_BEST_FOURTH_RATIO = 1.8

# Non-variable / no-clean-period logic.  In a known-variable validation sample
# this may rarely trigger, which is fine.  It becomes important for the later
# general sample.
NONVAR_TOP4_MAX_RATIO = 1.20
NONVAR_FAP_THRESHOLD = 0.05

# Multi-harmonic LS diagnostic.  The primary LS stays nterms=1 for a clean
# periodogram/FAP, but nterms>1 is used to decide whether a single-term P is
# actually the half-period of a two-feature/full-cycle signal.
RUN_MULTIHARMONIC_DIAGNOSTIC = True
MULTIHARMONIC_NTERMS = 3
MULTIHARMONIC_2P_MIN_GAIN = 1.08
MULTIHARMONIC_2P_MIN_POWER = 0.05

# A single filter can be trusted when the signal is strong and not dominated by
# a known/field alias. This is important for objects visible in o but not in c.
ALLOW_SINGLE_FILTER_RECOMMENDATION = True
SINGLE_FILTER_MIN_FOLD_SNR = 3.0
SINGLE_FILTER_MIN_PEAK_SNR = 4.0

# Fold metrics are used for colour/filter diagnostics, including forced folding
# c at the o-band period and o at the c-band period.
FOLD_METRIC_N_BINS = 40
FOLD_METRIC_MIN_POINTS_PER_BIN = 3
MASTER_REVIEW_MAX_LABELS = 120  # annotate at most this many labels on overview plot

# Normal plots have exactly two destinations: best_per_star and the one mutually
# exclusive primary category. Warning metadata only controls diagnostics.

# A 2P alternative becomes a real harmonic-review warning only when there is
# some evidence for that longer period, not merely because 2*P mathematically
# exists. The catalogue flag is validation-only and does not change blind period
# selection.
HARMONIC_2P_PEAK_MIN_POWER_FRACTION = 0.05
HARMONIC_2P_PEAK_MAX_RANK = 12
USE_CATALOGUE_FOR_VALIDATION_REVIEW_FLAGS = True

# Optional source-based limit for tests. MAX_FILES counts files; MAX_SOURCES
# counts unique Gaia/source IDs after reading metadata. Keep None for full runs.
MAX_SOURCES: int | None = None


# =============================================================================
# 7. COLUMN ALIASES
# =============================================================================
COLUMN_ALIASES = {
    "MJD": ["MJD", "###MJD", "mjd", "time", "jd"],
    "F": ["F", "filter", "Filter", "band", "passband"],
    "m": ["m", "mag", "magnitude", "m_mag"],
    "dm": ["dm", "mag_err", "m_err", "emag", "magnitude_error"],
    "uJy": ["uJy", "ujy", "flux", "Flux"],
    "duJy": ["duJy", "dujy", "flux_err", "Flux_err", "flux_error"],
}

SOURCE_ID_COLUMNS = ["target_GaiaDR3", "gaia_dr3", "GaiaDR3", "source_id", "gaia_source_id", "target_id"]
OBJECT_NAME_COLUMNS = ["object_name", "name", "Name", "target_name"]
CLUSTER_COLUMNS = ["target_group", "target_cluster", "cluster_name", "cluster", "Cluster"]
CLASS_COLUMNS = ["target_variability_class", "target_Class", "atlas_class", "xmatch_class", "best_class_name", "Class", "class"]
PERIOD_COLUMNS = [
    "target_catalogue_period_days", "target_best_period_days", "period_days", "catalogue_period", "catalog_period",
    "xmatch_fp_period", "atlas_object_period", "fp_period", "xmatch_ls_pday", "ls_pday",
]
RA_COLUMNS = ["target_ra_used", "ra_deg", "ra", "RA", "atlas_ra"]
DEC_COLUMNS = ["target_dec_used", "dec_deg", "dec", "Dec", "DEC", "atlas_dec"]


SECONDARY_WARNING_PRIORITY = [
    "alias_corrected",
    "alias_possible",
    "harmonic_possible",
    "filter_disagreement",
    "single_filter_only",
]


SUMMARY_CACHE_REQUIRED_COLUMNS = {
    "file",
    "source_id",
    "series",
    "status",
    "raw_ls_best_period_days",
    "raw_ls_best_power",
    "raw_ls_fap",
    "ls_peak_snr",
    "best_to_second_power_ratio",
    "best_to_fourth_power_ratio",
    "raw_fold_amp_snr",
    "recommended_series_period_days",
}
PEAK_CACHE_REQUIRED_COLUMNS = {
    "file",
    "source_id",
    "series",
    "rank",
    "period_days",
    "power",
    "power_fraction_of_best",
}
