from __future__ import annotations
from pathlib import Path
import matplotlib


matplotlib.use("Agg")  # Safe for scripts run without an interactive display.


# ============================================================================
# 1. PATHS — filled in from the YAML config by groove.pipeline
# ============================================================================

# Folder containing one raw ATLAS CSV per star.
INPUT_DIR: Path | None = None   # set by the pipeline config (raw light-curve folder)

# Folder for cleaned light-curve CSV files and cleaning tables.
CLEANED_DIR: Path | None = None # set by the pipeline config

# Folder for all cleaning plots. Kept separate from the light-curve files.
PLOT_DIR: Path | None = None    # set by the pipeline config


# ============================================================================
# 2. FILE HANDLING — USUALLY LEAVE AS BELOW
# ============================================================================

FILE_GLOB = "*.csv"             # Recommended: all split per-star CSV files.
OVERWRITE_CLEANED_FILES = True  # Recommended: False; existing cleaned files stay unchanged.
PROGRESS_EVERY = 100             # Print progress every N files.


# ============================================================================
# 3. FILTER SELECTION
# ============================================================================

KEEP_FILTERS = {"c", "o"}       # Recommended: both ATLAS cyan (c) and orange (o).
DROP_OTHER_FILTERS = True        # Recommended: True; ignore unexpected filter labels.


# ============================================================================
# 4. BASIC HARD-VALIDITY LIMITS
# These remove impossible/catastrophic values rather than defining variability.
# ============================================================================

MAG_MIN = -5.0                   # Hard sanity floor; recommended -5 mag.
MAG_MAX = 30.0                   # Hard sanity ceiling; recommended 30 mag.
DM_MIN = 0.0                     # Magnitude errors must be positive.
DM_MAX = 5.0                     # Broad hard limit; use stricter science cuts later if validated.
DUJY_MAX = 10000.0               # Broad uncertainty ceiling; recommended 10000 microJy.
ABS_UJY_HARD_MAX = 1.0e9         # Reject numerically catastrophic flux values.

# Magnitude columns are optional evidence, not a requirement.
# Forced photometry has no defined magnitude when the measured flux is <= 0,
# so demanding a finite m/dm silently deletes every negative-flux epoch. With
# this False, the m/dm range checks are applied only to rows that actually
# have a finite magnitude, and flux-space rows are judged on uJy/duJy alone.
REQUIRE_FINITE_MAG = False       # Recommended: False; keeps negative-flux epochs.


# ============================================================================
# 4b. NEGATIVE FLUX HANDLING
# Negative flux is not unphysical: forced photometry measures true_flux+noise
# at a fixed position, so a source consistent with zero scatters symmetrically
# about zero. Cutting on sign truncates the noise distribution and biases the
# mean flux high, which flattens real minima. Cut on SIGNIFICANCE instead: a
# strongly negative point indicates a subtraction failure, a ghost, a trail,
# or a variable present in the reference image, and is a genuine defect.
# ============================================================================

MIN_SNR = -5.0                   # Reject uJy/duJy below this; recommended -5.
                                 # Set to -np.inf to disable the cut entirely.


# ============================================================================
# 5. ATLAS POINT-QUALITY CUTS
# Each cut is applied only when its column exists in the input file.
# ============================================================================

REQUIRE_ERR_ZERO = True          # err==0: ATLAS says the measurement completed normally.
REQUIRE_FLAGS_ZERO = False       # Recommended False unless the meaning of flags is confirmed.

MAG5SIG_MIN = 17.0               # Depth-quality cut; recommended >17 for clean photometry.
MAG5SIG_HARD_FAIL = 10.0         # Catastrophic depth value; always reject below 10.
SKY_MIN = 17.0                   # Reject unusually bright sky/background; recommended >17.

MAJ_MIN = 1.6                    # PSF major-axis lower bound; recommended 1.6 pixels.
MAJ_MAX = 5.0                    # PSF major-axis upper bound; recommended 5.0 pixels.
MIN_MIN = 1.6                    # PSF minor-axis lower bound; recommended 1.6 pixels.
MIN_MAX = 5.0                    # PSF minor-axis upper bound; recommended 5.0 pixels.

APFIT_MIN = -1.0                 # Aperture-fit lower bound; recommended -1.0.
APFIT_MAX = -0.1                 # Aperture-fit upper bound; recommended -0.1.

X_MIN = 100.0                    # Keep away from detector x edge; recommended 100.
X_MAX = 10460.0                  # Keep away from detector x edge; recommended 10460.
Y_MIN = 100.0                    # Keep away from detector y edge; recommended 100.
Y_MAX = 10460.0                  # Keep away from detector y edge; recommended 10460.


# ============================================================================
# 6. OPTIONAL DIP RESCUE
# Recommended OFF for ATLAS-VAR DR1. The normal cleaner already keeps low-flux
# points. Enable only after checking forced-photometry quality flags carefully,
# because rescue can restore a point that failed a soft image-quality cut.
# ============================================================================

RESCUE_ENABLE = False           # Thesis default: off. Restores dip points that only failed soft cuts.
BASELINE_WINDOW_PTS = 41         # Running-median window; recommended odd value near 41.
RESCUE_Z = 5.0                   # Candidate dip significance; recommended 5 sigma.


# ============================================================================
# 7. PLOTTING SETTINGS
# ============================================================================

MAKE_SUMMARY_PLOTS = True        # Recommended: True; produces the 6-panel overview.
MAKE_REASON_PLOT = True          # Recommended: True; plots common rejection reasons.
MAKE_EXAMPLE_PLOTS = True        # Recommended: True for a small number of examples.
N_EXAMPLE_PLOTS = 6              # Recommended: 4–8; avoids producing thousands of plots.
EXAMPLE_SELECTION = "highest_removed_fraction"
# Options: "highest_removed_fraction", "lowest_removed_fraction", or "first".

TOP_N_REASONS = 15               # Recommended: 10–20 reasons on the bar chart.
SAVE_PNG = True                  # PNG for quick viewing.
SAVE_PDF = True                  # PDF for thesis-quality vector output.
PLOT_DPI = 250                   # Recommended: 200–300 dpi for PNG files.
