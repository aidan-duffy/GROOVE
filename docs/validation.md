# Validation evidence and limitations

Release history is in [the changelog](../CHANGELOG.md); reproducible software
checks are in [tests/](../tests/). [The Linux/WSL guide](linux_validation.md)
provides commands for repeating the stages and checking a real download.

## Current source: GROOVE 1.1.1

### Automated checks

Version 1.1.1 changes documentation, comments and metadata only; calculations
and thresholds are the same as in 1.1.0. The suite passed **111 tests** on
Linux with Python 3.12, using the dependency versions below. The non-fatal
warnings are UMAP worker notices and pandas future-compatibility notices; the
warning count depends on the dependency environment.

| Dependency | Version used |
|---|---|
| Python | 3.12.14 |
| NumPy | 2.5.4 |
| pandas | 3.1.0 |
| SciPy | 1.18.1 |
| Astropy | 8.0.2 |
| scikit-learn | 1.9.1 |
| umap-learn | 0.5.12 |
| numba | 0.68.0 |
| matplotlib | 3.11.2 |
| Plotly | 7.1.0 |
| joblib | 1.6.0 |
| pytest | 9.1.1 |
| Ruff | 0.17.2 |

The tests cover period recovery, alias replacement/retention, harmonic tests,
cross-filter recommendations, single-filter support boundaries, logging,
strict errors, worker-state isolation and serial/parallel equality. They also
exercise interrupted runs and output repair.

Ruff currently reports 147 findings. Lint is advisory in CI and does not block
the tests or build.

### Demonstration, documentation and build checks

The 12-source demo passed `demo-check` and `tools/audit_outputs.py`: all eight
periodic injections were recovered within 0.052%, all 26 cleaning cut cases
passed, and the separate 5.3-day BLS injection was recovered at 5.300353 days.
All 92 generated PNGs decoded, and three interactive maps were written.

The 24-source extended demo, run stage by stage, also passed `demo-check`:
184 PNGs decoded, three interactive maps were written, and the diagnostic
manifest listed four alias-candidate and two harmonic-test entries. Map-only,
plot-only and cyan-only highlighting completed. Plot-only left the six UMAP
image products and all saved classifications and periods unchanged.

The two-sample example in [map controls](map_controls.md) adds 12 artificial
IDs to a 12-source reference while preserving every original UMAP coordinate.
Neighbour identities can change after adding sources, so coordinate checks
compare the coordinate columns, not the neighbour-ID columns.

The bundled and generated configuration files agree once their different path
bases are taken into account. The generated real-data template passes a dry run
(no token, no requests) with artificial coordinates; this does not validate a
real ATLAS download. Internal Markdown links and the Bash/Python examples were
checked.

Wheel and source-distribution builds pass. The wheel's import, bundled
morphology YAML and CLI `--n-jobs`/`--strict` flags were checked separately.
The source distribution contains only the public example configurations and
target lists. A successful build does not guarantee that dependencies resolve
on every supported platform.

### Scope and limitations

The suite's downloader uses simulated responses. These checks do not establish
live authenticated ATLAS availability, real-catalogue completeness, purity or
unchanged results for every historical research sample. The CI matrix includes
Linux and Windows with Python 3.10, 3.12 and 3.13; these checks used only
the Linux/Python 3.12 environment above. Conda, native Windows,
manual browser interaction and large-catalogue performance are not covered.

GROOVE supports opt-in process-parallel period calculations using
`--n-jobs`. The default is one worker; fewer than eight unfinished files use a
serial fallback. Checkpoint merging and plots stay in the parent process.
There are no per-source timeouts or partial-frequency-grid LS/BLS checkpoints.
Interrupted UMAP fitting restarts from cached features, not an optimiser step.
Some aggregate rendering and validation may repeat during output repair.

### Restart regression coverage

The regression suite exercises these restart contracts:

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
- Run a synthetic cleaning/selection/period/morphology workflow; damage a
  phase plot; repair it without feature extraction or UMAP fitting; check the
  saved fitted model bytes and unchanged source-plot timestamps.
- Interrupt projection of a new source onto that reference before finalisation;
  resume from its saved transform results without repeating projection or
  duplicating source IDs; then repeat the completed full command.
- Reuse a completed mocked download without authentication, and confirm a
  download --rerun submits fresh work.
- Parse --rerun for every stage and the full command, including the normal
  placement after -c before any morphology pass-through separator.


## Historical validation records

The following results come from earlier versions and are kept with their
original sample sizes and limits. The real-data and platform runs below have
not been repeated for the current version.

### Version 1.0.9 platform and build checks

The 1.0.9 suite (before the Windows fix) passed 86 tests in the Linux development workflow.
A separate Conda environment also passed 86 tests. GitHub checks passed on
Ubuntu with Python 3.10 and 3.12. The Windows Python 3.10 run reported 82 passes
and four failures: token-lock contention handling and three tests reading UTF-8
HTML with the system encoding. Windows Python 3.12 was cancelled.

A Windows compatibility fix addresses those failures and adds a lock-release
regression test. Linux lock contention/release and an emulated Windows branch
were checked separately; a full native Windows run of the fixed suite is not
recorded here. Check CI on the exact commit used for an analysis.

Wheel and source-distribution builds succeeded for 1.0.9.

### Real-data period comparison: earlier research workflow

A 200-light-curve real ATLAS cleaning test selected 196 sources. Comparing the
saved outputs with the original thesis period script gives:

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
with the original is not evidence of greater accuracy. The combined
run had no catalogue-validation rows, so known-period accuracy is not measured.
Known-variable tests and realistic injection/recovery with separate direct and
harmonic recovery rates are still needed to compare recommendation methods.

### Synthetic demonstrations and map checks: earlier versions

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
