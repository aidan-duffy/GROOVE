# GROOVE 1.0.4 validation

49 automated tests passed on Linux/Python 3.12. Source and wheel distributions
built successfully. The full 24-source extended pipeline and demo-check passed.
Both daily-contamination cases and the unequal binary generated three automatic
extra-fold images each (combined, orange and cyan). The added alias_promoted
case has rank one 1.000046 d and rank two 8.301626 d; the existing correction
rule promotes rank two. The rank-one power remains larger than rank two's.
The combined alias-comparison image was visually inspected.

All morphology figures live under results/plots/ML/extended_demo. Numerical
models/tables/cache live under 4_morphology/saved_runs/extended_demo. New-layout
HTML-to-phase-image links and legacy-model resolution are covered by tests.
A full highlight-source run wrote its extra products in the new plot tree.
Plot-only passed its regression: eight UMAP products and saved labels/periods
were unchanged. The legacy path remains readable for older saved runs.

The updater passed bash syntax validation and an isolated local Git fixture:
failed tests blocked commit/push, user configs/targets were preserved, an
unrelated file stayed uncommitted and the successful commit reached a local
bare repository. pip/pytest commands were stubbed only in that script-control
fixture; the actual package tests above were run separately without stubs.
No commit has been pushed to the user's GitHub from this workspace. The supplied
script does that from their local authenticated checkout.

Live authenticated ATLAS downloads and browser interactions remain user-side
checks. This demonstration validates exercised software paths, not exhaustive
scientific completeness or purity. The daily examples inject instrumental
one-day contamination plus a stellar signal; the separate nightly-sampling case
illustrates cadence side peaks.
