# Validation of GROOVE 1.0.3

44 automated tests passed on Linux/Python 3.12. The source distribution and wheel
built successfully. Both fresh demonstrations completed their full analysis
pipelines; demo-check passed. The original 12 raw demo sources are unchanged.

Standard demo: 12 sources; 8 known periods recovered within 0.1%; 8 strong and
4 weak-or-ambiguous period review labels; 4 wavelike, 4 transit and 4 nonvar
morphology labels. 118 PNGs decoded; four interactive maps present. The supplied
output audit's cut-boundary and independent BLS checks passed.

Extended demo: 23 sources and 225 decoded PNGs, four interactive maps, three
alias-candidate panels for the daily systematic and three harmonic-test panels
for the unequal binary. All seven primary morphology categories are represented.
The unequal binary's adopted full-cycle period is approximately 10.80 days
from an initial 5.40-day peak. The one-day systematic is kept and flagged because
the secondary stellar peak is below the configured replacement power fraction.
Its competing folds are generated automatically. All 14 extended extra-fold
figures were generated successfully. Representative alias and harmonic panels
were visually inspected.

The extended injected behaviours are inputs, not forced labels. Inspect the
source-by-source review CSV, including the evolving wave, single and double
dips. This small selected sample does not establish astrophysical completeness,
purity, reliable cluster recovery, or validation of all unseen input branches.
Interactive HTML browser actions and live authenticated ATLAS requests remain
local review gates. The user's uploaded log showed a successful 1.0.1 install,
27 tests and the offline synthetic run; it did not show a real ATLAS download.

The review-rule change accepts either dominance ratio with significance and
retains alias/harmonic warnings. It leaves periodogram calculations and numeric
recommendations unchanged for the standard demonstration. The new extended
configuration explicitly uses different demo-only search/BLS parameters.
