"""Unified ATLAS period-search pipeline with persistent field-alias learning,
source-level recommendation labels and cross-filter diagnostics.

Purpose
-------
The period stage combines the LS/BLS period-search workflow with
universal + field-local alias correction. It is designed for two use cases:

1. Validation stars with catalogue periods:
   - catalogue values are used only AFTER the blind search, to measure recovery.

2. Unknown stars:
   - the code reports a recommended period, alias risk, harmonic ambiguity,
     possible 2P full-cycle period, cross-filter agreement and confidence class.

Key design choice
-----------------
Cadence aliases are not simply deleted. A true ~1 day astrophysical period is
possible, so alias periods are penalised only when there is evidence that the
period is shared by many unrelated stars in the same sky field or by the window
function, and when an alternative peak has comparable support. If a period is
near a cadence alias but is independently supported by the source itself
(o/c agreement, strong fold coherence, no good non-alias replacement), it is
kept and flagged as an alias-period possible true signal.

Main outputs
------------
OUTPUT_DIR/tables/
    ls_period_search_summary.csv        per source/per series LS/BLS results
    ls_period_search_peaks.csv          top LS peaks with alias diagnostics
    ls_source_consensus.csv             compact one-row-per-source consensus
    source_period_recommendations.csv   one final recommendation row per source
    ls_validation_summary.csv           catalogue-validation metrics, if present
    field_alias_inventory_current.csv   field aliases learned in this run
    field_alias_memory.csv              persistent accumulated alias memory
    extra_phase_fold_diagnostics.csv    optional alias/harmonic plot manifest

OUTPUT_DIR/plots/<series>/<tag>/
    one diagnostic plot per successful source/series, organised into:
    best_per_star and exactly one of strong, alias, harmonic or nonvar.

OUTPUT_DIR/plots/<series>/<alias-or-harmonic>/extra_phase_folds/
    optional alias-candidate and harmonic-test phase-fold comparison figures.

OUTPUT_DIR/plots/000_master_review_all_stars.png
    a single overview plot of all source-level recommendations.

Important interpretation
------------------------
A single-filter detection, especially an o-band-only double-dip recovery, is not
thrown away. It is retained with explicit band-detection and forced-fold metrics
so the combined light curve cannot erase a genuine colour-dependent or low-S/N
signal. The code does not claim that an o-only signal proves dust; it flags the
case for colour/SNR/systematics interpretation.

How alias memory improves over time
-----------------------------------
Every run can load an existing field_alias_memory.csv and update it with alias
clusters found in the current run. New stars in a known sky field therefore
inherit the field's known cadence aliases, while their own top peaks can update
that knowledge for future runs."""
