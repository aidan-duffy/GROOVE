# Validation evidence and limitations

This page is updated as validation progresses. Release history belongs in
[the changelog](../CHANGELOG.md); tests are in [tests/](../tests/).

## Automated and platform checks

The pre-Windows-fix 1.0.9 suite passed 86 tests in the Linux development workflow.
The user's Conda environment also passed 86 tests. GitHub checks passed on
Ubuntu with Python 3.10 and 3.12. The Windows Python 3.10 run reported 82 passes
and four failures: token-lock contention handling and three tests reading UTF-8
HTML with the system encoding. Windows Python 3.12 was cancelled.

A targeted compatibility patch addresses those failures and adds a lock-release
regression test. Linux lock contention/release, an emulated Windows branch and
syntax were checked separately. Native Windows and full patched-suite results
remain pending; this page must not be read as confirmation that all platforms
have passed. The CI checks on the exact release commit are authoritative.

Wheel and source-distribution builds succeeded for the pre-patch 1.0.9 source.

## Real-data period comparison

A user's 200-curve cleaning test selected 196 sources. Saved-output comparisons
with the original thesis period script give:

| Check | O/C only | Combined plus O/C |
|---|---:|---:|
| Raw O/C LS periods matching original | 392/392 | 392/392 |
| Raw O/C BLS periods matching original | 392/392 | 392/392 |
| Ranked O/C peaks matching original | 4,704/4,704 | 4,704/4,704 |
| Recommended O/C periods matching original | 312/392 | 342/392 |

Period agreement uses 0.1% tolerance. Raw powers and false-alarm probabilities
match within tight numerical tolerances; point counts, time ranges and search
limits match. These summaries do not prove identical measurements or full
scientific correctness. They do not compare the final source recommendations,
cleaning measurements, morphology outputs or all plot appearances.

Combined analysis resolved 36 previous per-band recommendation discrepancies,
introduced six and left 44. Different field alias learning and memory inputs
can change recommendations despite identical raw searches. Closer agreement
with the original is not evidence of greater accuracy. The submitted combined
run had no catalogue-validation rows, so known-period accuracy is not measured.
Known-variable tests and realistic injection/recovery with separate direct and
harmonic recovery rates are still needed to compare recommendation methods.

## Synthetic demonstrations and regression evidence

Earlier checks exercised the 12-source demo and the 24-source extended demo,
including unequal eclipses, daily aliases, flares and single-filter inputs.
The 1.0.8 extended-period check recovered all ten coherent wave/dip/single-band
injections within 0.1%; both bands of the promoted-alias example recovered about
8.3 days. All 107 generated period PNGs passed integrity checks, and 14 extra
alias/harmonic figures had successful entries. This is historical evidence for
those tested versions and fixtures, not a measurement of survey completeness
or the accuracy of every current label.

Earlier map tests checked image links, dataset markers, comparison controls,
saved-coordinate redraws and frozen-model updates. Automated control checks do
not substitute for browser layout review.

## Restart checks

Meaningful restart checks include:

- Interrupt cleaning after one completed source, resume without re-cleaning it,
  then confirm --rerun processes every source again.
- Delete a cleaned file or alter its raw input, and reprocess only that source.
- Repeat selection while preserving unchanged selected-file timestamps.
- Interrupt a whole run before periods, then resume while preserving completed
  cleaning/selection; repeat completion and deliberately force recalculation.
- Interrupt period search before its first full CSV snapshot and recover the
  completed source's summary/peaks from its atomic journal.
- Interrupt after period tables are saved and preserve numerical search work
  and alias-inventory counts on restart.
- Change a visual-only period setting without repeating the search.
- Retry a failed period source without repeating successful sources.
- Recover an empty aggregate period CSV from the successful source journals.
- Interrupt cleaning's plot pass and retain an already saved compatible figure.
- Detect and repair changed plot bytes rather than trusting file existence.
- Run a real synthetic cleaning/selection/period/morphology workflow; damage a
  phase plot; repair it without feature extraction or UMAP fitting; check the
  saved fitted model bytes and unchanged source-plot timestamps.
- Interrupt projection of a new source onto that reference before finalisation;
  resume from its saved transform results without repeating projection or
  duplicating source IDs; then repeat the completed full command.
- Reuse a completed mocked download without authentication, and confirm a
  download --rerun submits fresh work.
- Parse --rerun for every stage and the full command, including the normal
  placement after -c before any morphology pass-through separator.

Live ATLAS downloads and 10,000-star performance were not tested in the automated
restart validation. The separate user-supplied real-data comparison is described
above. Interrupted UMAP optimisation restarts from cached source
features rather than from an optimiser iteration. Some aggregate rendering and
validation calculations can repeat during output repair. This release does not
add per-source timeouts or parallel LS/BLS workers.
