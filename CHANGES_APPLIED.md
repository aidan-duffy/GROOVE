# GROOVE 1.1.0 — changes applied and verification

Prepared 22 October 2026 against baseline commit
`429b32dee6c11fafe09796385e7bd8c7de85f977` (package version 1.0.9).
This is a local release candidate. No commit, tag, release or push was made.

## Applying this update

The ZIP contains the complete source tree, this report and `changes.patch`.
It excludes Git history, environments, caches and generated demonstration results.
The patch handles deletions as well as additions; copying files alone leaves the
obsolete root `REVIEW.md` behind.

From your existing checkout, use the extracted patch's absolute path:

```bash
git status --short
git apply --check /path/to/extracted/GROOVE/changes.patch
git apply /path/to/extracted/GROOVE/changes.patch
python -m pip install -e '.[dev]'
python -m pytest -q
groove --version
```

If the preflight fails, review overlapping local changes before applying anything.
Your configurations/data are not deleted by the patch. Review the resulting diff
and commit/push from your own terminal when ready. Source fingerprints change on
upgrade, so old analysis receipts can be invalidated; subsequent compatible 1.1.0
runs resume normally. Preserve earlier results if you need an independent comparison.

**Keep `changes.patch` local.** A deletion diff necessarily contains the old values
it removes. The patch is ignored by Git and should not be published or included in
release distributions. Current-source anonymisation does not erase earlier Git history.

## Verification summary

- Tier 1 mechanical changes and Tier 2 numerical tests: 102 passed under Python
  3.12 / NumPy 2 after fixture corrections. No scientific tolerance was loosened.
- Tier 3 logging conversion: complete suite run after each of 13 modules; each
  run passed 108 tests. Later per-module runs used four pytest workers for speed;
  the final compatibility runs below used the ordinary serial test runner.
- Final complete suite: **111 passed** on Python 3.12 / NumPy 2.3.5 and **111 passed**
  on Python 3.13 / NumPy 2.5.4. No skipped/xfail scientific expectations were used.
- Final focused numerical/execution suite: 24 passed.
- Extended offline demonstration: all 24 sources completed cleaning, selection,
  period search and morphology; `groove demo-check` passed without errors.
  It decoded 184 PNGs, found three interactive HTML maps and verified alias and
  harmonic diagnostic coverage. Representative double-dip, alias and UMAP plots
  were visually inspected.
- Repeating the identical demo command skipped all four analysis stages and kept
  all 190 PNG/PDF/HTML products byte-identical with unchanged modification times.
- Every one of 38 broad stage exception handlers reports its exception before
  fallback; an AST audit found no unreported handler or stage-level `print()` call.
- Touched/new Python files pass Ruff. Full-tree Ruff still reports **147 findings
  in 15 untouched files**; details are listed below. No repository-wide cleanup
  was performed.

Final environment versions:

| Component | Python 3.12 environment | Python 3.13 environment |
|---|---|---|
| python | 3.12.14 | 3.13.16 |
| numpy | 2.3.5 | 2.5.4 |
| pandas | 2.2.3 | 3.1.0 |
| scipy | 1.17.0 | 1.18.1 |
| astropy | 8.0.2 | 8.0.2 |
| scikit-learn | 1.8.0 | 1.9.1 |
| umap-learn | 0.5.12 | 0.5.12 |
| numba | 0.68.0 | 0.68.0 |
| matplotlib | 3.10.8 | 3.11.2 |
| joblib | 1.5.3 | 1.6.0 |
| plotly | 7.1.0 | 7.1.0 |
| pytest | 9.1.1 | 9.1.1 |
| ruff | 0.17.1 | 0.17.1 |

Warnings were non-fatal: chiefly deterministic UMAP worker warnings and pandas
future-compatibility warnings (17 in the final 3.12 run; 96 in the 3.13 run).
These checks do not establish catalogue completeness, purity or unchanged
recommendations for the full thesis sample. Native Windows, Conda installation,
live ATLAS authentication/downloads and manual browser interaction remain
unverified here. Downloader tests use simulated service responses.

## 1.1 — Remove identifying benchmark values

**Applied; full suites and extended demo passed.**

Files: `src/groove/demo.py`, `src/groove/morphology/run.py`,
`README.md`, `docs/linux_validation.md`, `tests/conftest.py`,
`tests/test_download.py`, `tests/test_integration.py`,
`tests/test_morphology_layout.py`, `tests/test_pipeline.py`,
`tests/test_resume.py`, `tests/test_period_review.py`,
`tests/test_field_alias_learning.py`.

Added `DEMO_SOURCE_ID_BASE = 9_900_000_000_000_000_000`; both generators use it.
Shared fixture IDs A/B remain distinct. The nightly-sampling example uses 73.6 d;
the retained synthetic double dip uses 61.3 d and a 6.5-day secondary offset.
Generic target-label help replaces the real-object example. Updated generated
guides and examples, including derived demo IDs missed by the brief's initial
occurrence list. The transform-resume fixture now reads its actual first demo ID
rather than assuming its ID matches the unrelated A fixture. Those were test
fixture corrections; recovery tolerances were retained.

Current `.py`, `.md`, `.yaml` and `.cff` files were scanned for the specified real
identifier, period literal and name; none remain. The required patch and existing
Git history necessarily retain deleted historical lines, as explained above.

Observed adopted periods in the completed extended demo:

| Synthetic scenario | Injected period (d) | Adopted period (d) |
|---|---:|---:|
| Nightly sampling | 73.6 | 73.556915 |
| Double dip | 61.3 | 61.349568 |
| Alias promoted | 8.3 | 8.305573 |

All three are within 0.1% of their injected values. The double-dip source is
classified as transit-like; both filters' alias-promoted cases retain rank-two
candidate-fold diagnostics.

The brief's demo command omitted `--skip-download`. Used the existing documented
command below, so artificial IDs are never submitted for photometry:

```bash
groove demo --extended /path/to/new/demo
groove run -c /path/to/new/demo/run.yaml --skip-download
groove demo-check /path/to/new/demo
```

## 1.2 — Shared alias-score weights

**Applied; full suites and numerical score-agreement tests passed.**

Files: `src/groove/periods/settings.py`, `src/groove/periods/aliases.py`,
`tests/test_period_logic.py`, `docs/configuration.md`.

Both scoring sites use settings weights 0.50 / 0.50 / 0.35, preserving adoption
weights and aligning diagnostics. Removed the unused `ALIAS_PENALTY_WEIGHT`.
Tests straddle the suspect threshold using the same stored rank-one window.
Non-leading adoption peaks still lack full time-array window values and retain
their documented universal/field-only input information; coefficient sharing
does not manufacture missing diagnostics.

## 1.3 — Single-filter SNR settings

**Applied (preferred soft gate); full suites and all threshold tests passed.**

Files: `src/groove/periods/recommend.py`, `tests/test_single_filter.py`,
`docs/configuration.md`, `CHANGELOG.md`.

Supported single-filter provenance requires fold SNR >=3 and peak SNR >=4.
Candidates below either threshold remain in the catalogue with low-support
provenance and `single_filter_below_snr_thresholds`; missing SNR is not treated as
passing. Disabling `ALLOW_SINGLE_FILTER_RECOMMENDATION` retains the candidate
with `single_filter_recommendation_disabled`. Significant below-threshold
single-filter results get weak source confidence; existing non-variable labels
are not promoted by this gate. Numeric candidate periods are retained.
Thresholds use the existing raw-series SNR diagnostics, not a newly evaluated
SNR at an alias-corrected period. This is an intentional provenance/confidence
behaviour change, not a new periodogram or physical classification method.

## 1.4 — Python and NumPy compatibility

**Applied; complete suites passed in both environments above.**

Files: `pyproject.toml`, `environment.yml`, `.github/workflows/tests.yml`,
`README.md`.

Requires Python >=3.10,<3.14 and NumPy >=1.24 without the former <2 cap.
Conda constraints mirror this, and CI now includes Python 3.13 on Linux/Windows.
No removed NumPy aliases were found in the initial scan. Compatibility was
actually tested under NumPy 2.3.5 and 2.5.4; Python 3.10/native Windows coverage
is configured for CI, not claimed as locally executed.

Optional dependency splitting was **deferred**. UMAP, numba and Plotly remain
installed by default, preserving the existing full-pipeline installation.
No unimplemented `maps` extra or misleading optional-install message was added.

## 1.5 — Metadata and release records

**Applied; complete suites passed; build/patch checks recorded below.**

Files: `pyproject.toml`, `src/groove/__init__.py`, `CITATION.cff`,
`CHANGELOG.md`, `MANIFEST.in`, `README.md`, `docs/README.md`,
`docs/validation.md`, `docs/history/review_1.0.2.md`.
Deleted obsolete root `REVIEW.md`.

Moved the historical review with an explicit historical notice. Updated version
metadata to 1.1.0 and documented all applied changes. Baseline 429b32d already has
GPL-3.0-only in its licence and metadata; **the repository has no 1.0.9 tag**, so
there is no tagged release licence to assert. Earlier untagged changes are
labelled as such instead of presented as pending current-source changes.

The citation has a **commented** `doi: ""` reminder, to uncomment only when a real
archive DOI exists. An active blank DOI would fail the citation schema; none was
invented. The release date is also left for actual publication. Windows CI is
configured, but the connector returned no workflow run for baseline 429b32d;
local Linux tests do not prove a native Windows pass. The current report states
that limit explicitly. The manifest follows the relocated review and includes
this report in the source distribution. The first build exposed setuptools' deprecated
licence-table warning; replaced the table with the equivalent SPDX expression and
explicit licence-file declaration, requiring setuptools >=77 for PEP 639 support.
This changes metadata formatting, not the licence. The rebuilt wheel/source archive
were checked after this metadata-only adjustment. See the
[setuptools configuration documentation](https://setuptools.pypa.io/en/latest/userguide/pyproject_config.html).

## 1.6 — Ruff diagnostics

**Applied; touched/new files pass. Full suites passed.**

Files: `pyproject.toml`, `.github/workflows/tests.yml`, touched Python files.

Added the requested rule families, py310 target and line length 120; added
`ruff>=0.6` to the dev extra. Mechanical lint corrections are confined to files
already changed for the requested work. This includes binding a downloader
polling callback to its current row rather than leaving a loop closure.
The CI full-tree Ruff step runs before tests with **continue-on-error**, because
making existing untouched lint debt a hard gate would deliberately break CI
while the brief forbids cleaning those files. This is a deliberate deviation
from an unconditional lint gate, not a claim that the entire tree is lint-clean.

Remaining findings by untouched file:

| File | Count |
|---|---:|
| `src/groove/clean/cuts.py` | 1 |
| `src/groove/clean/loading.py` | 1 |
| `src/groove/clean/settings.py` | 1 |
| `src/groove/download/settings.py` | 5 |
| `src/groove/download/storage.py` | 9 |
| `src/groove/download/targets.py` | 17 |
| `src/groove/morphology/embedding.py` | 53 |
| `src/groove/morphology/outputs.py` | 37 |
| `src/groove/morphology/settings.py` | 13 |
| `src/groove/periods/classify.py` | 1 |
| `src/groove/periods/folding.py` | 4 |
| `src/groove/periods/loading.py` | 1 |
| `src/groove/periods/validation.py` | 2 |
| `tests/test_map_controls.py` | 1 |
| `tests/test_output_options.py` | 1 |

## 2.1 — Scientific-core tests

**Applied; all new numerical cases and both complete suites passed.**

Files: `tests/test_period_logic.py`, `tests/test_single_filter.py`.

Seeded ATLAS-format data cover clean adopted-period recovery, unequal-minimum
odd/even doubling, no false sinusoidal doubling, real rank-two alias promotion,
retaining an alias without credible alternatives, scoring agreement around the
threshold, and direct/harmonic cross-filter anchors. An additional regression
isolates the three-term multiharmonic doubling route with odd/even disabled.
Direct agreement anchors O; harmonic agreement anchors the shorter period.
Tests assert final adoption/provenance, not just intermediate peak properties.
Threshold tests cover both sides and equality at each SNR boundary, missing
values and the single-filter switch. No expectation was loosened or marked
xfail to conceal an algorithm/documentation mismatch.

## 3.1 — Optional parallel period searches

**Applied; serial/parallel equality and interruption/recovery regressions passed.**

Files: `src/groove/periods/run.py`, `src/groove/periods/settings.py`,
`src/groove/periods/files.py`, `src/groove/cli.py`, `tests/test_execution.py`,
`README.md`, `docs/configuration.md`, `docs/restarts.md`.

Added `PERIOD_N_JOBS=1`, YAML `period_n_jobs` and `--n-jobs` for periods/full run.
Workers receive a complete settings snapshot, restore their module state and
return only per-file results. Resume skips, source caps, ordered merges,
checkpoint journals and plots stay in the parent. `loky` is used for at least
eight unfinished files when requested; smaller batches use serial execution.
In-memory plot payload retention is disabled whenever jobs !=1; plots use the
existing streaming pass. Changing worker count does not invalidate scientific
period-cache identity. Work still in flight can repeat after interruption;
completed ordered journals are retained. This does not resume an individual
Lomb–Scargle calculation partway through its frequency grid.

Tests compare serial and two-worker summary/peak CSVs byte for byte, rebuild
lost aggregates from completed journals without running a worker, honour source
caps, and retry only a transiently failed file after a parallel run. The audit
found and fixed a real journal-ordering defect: glob order could change table
row order after repair. Restored rows now follow original file/series/rank order.
The downloader remains serial and uses one user-supplied token.

## 3.2 — Logging instead of stage prints

**Applied; full suite passed after every converted module, then both final suites passed.**

Files: `src/groove/execution.py`, `src/groove/__init__.py`,
`src/groove/cli.py`, `src/groove/pipeline.py`, `src/groove/resume.py`,
`src/groove/clean/{run,plots}.py`, `src/groove/select/run.py`,
`src/groove/download/run.py`, `src/groove/periods/{run,files,plots,aliases}.py`,
`src/groove/morphology/{run,plots,smoke,utils}.py`,
`tests/test_field_alias_learning.py`, `tests/test_execution.py`.

The shared adapter converts multi-argument progress messages into logger.info
messages; CLI setup installs the console handler. Embedded use receives a
NullHandler and can configure the `groove` hierarchy. Morphology no longer
installs its own console handler during library calls; its owned file handlers
are closed/replaced without removing application handlers. Standalone module
execution still configures console output. Updated stdout-capture tests to use
caplog, and added a quiet-library/file-log regression. Third-party warnings
retain their own warning controls.

Per-module complete-suite checkpoints (108 passes at each checkpoint):

| Module | Result |
|---|---|
| `src/groove/periods/aliases.py` | 108 passed, 13 warnings in 102.07s (0:01:42) |
| `src/groove/pipeline.py` | 108 passed, 13 warnings in 116.03s (0:01:56) |
| `src/groove/resume.py` | 108 passed, 13 warnings in 129.50s (0:02:09) |
| `src/groove/clean/run.py` | 108 passed, 13 warnings in 118.09s (0:01:58) |
| `src/groove/clean/plots.py` | 108 passed, 13 warnings in 84.39s (0:01:24) |
| `src/groove/select/run.py` | 108 passed, 13 warnings in 72.73s (0:01:12) |
| `src/groove/download/run.py` | 108 passed, 13 warnings in 73.11s (0:01:13) |
| `src/groove/periods/run.py` | 108 passed, 13 warnings in 78.04s (0:01:18) |
| `src/groove/periods/files.py` | 108 passed, 13 warnings in 73.10s (0:01:13) |
| `src/groove/periods/plots.py` | 108 passed, 13 warnings in 73.63s (0:01:13) |
| `src/groove/morphology/run.py` | 108 passed, 13 warnings in 72.63s (0:01:12) |
| `src/groove/morphology/plots.py` | 108 passed, 13 warnings in 74.47s (0:01:14) |
| `src/groove/morphology/smoke.py` | 108 passed, 13 warnings in 75.39s (0:01:15) |

The final logger-ownership change and extra execution cases were then validated
in the final 111-test suites on both interpreters.

## 3.3 — Process-global random state

**Applied; global-state and morphology regressions passed in both full suites.**

Files: `src/groove/morphology/run.py`, `tests/test_execution.py`.

Removed the unused `np.random.seed` call. The source audit found no stochastic
consumer needing a newly threaded Generator: demo/smoke generators already use
local `default_rng`, and PCA/UMAP receive explicit integer random states.
Creating an unused Generator would add no protection. The new test verifies
that executing morphology does not reseed NumPy's legacy global state. No
stored scientific fixtures were regenerated.

## 3.4 — Exception visibility and strict mode

**Applied; broad-catch audit and strict-error regressions passed.**

Files: `src/groove/execution.py`, `src/groove/cli.py`,
`src/groove/clean/{run,plots}.py`, `src/groove/download/client.py`,
`src/groove/periods/{settings,run,files,plots,aliases,periodograms}.py`,
`src/groove/morphology/{run,loading,features,classify,persistence,modes,plots,smoke}.py`,
`tests/test_execution.py`, `README.md`, `docs/configuration.md`.

All 38 broad handlers now report exception type/message before their existing
fallback. `--strict` on stages/full run propagates caught errors, including
worker/diagnostic errors, instead of silently continuing; programmatic callers
can use the scoped `error_policy(True)` context. It resets after errors and
propagates through nested calls. Workers receive the policy in their snapshot.
Normal-mode failed workers also report their saved error in parent progress.
No individual exception class was narrowed speculatively.

## Behaviour that does not match the documentation

No failing scientific expectation was found against the documented adoption,
harmonic or alias behaviour, and no xfail was needed. Resolved discrepancies
were the dead single-filter settings, different diagnostic alias weights,
stale review/licence placement and non-deterministic repaired journal ordering.
The brief's demo command required the existing `--skip-download` flag, and its
blank DOI request was implemented as a valid commented reminder. The optional
maps-extra split was deferred; full-tree lint is explicitly advisory until the
remaining untouched debt is addressed.

## Build and patch verification

The completion record below is appended only after building the distributions
and applying the patch to a clean archive of baseline 429b32d.


- Built `groove-1.1.0.tar.gz` and `groove-1.1.0-py3-none-any.whl` successfully.
- Checked the wheel includes `execution.py`, morphology defaults and
  `License-Expression: GPL-3.0-only`. Imported the built wheel from a separate
  installation target using the tested dependencies and checked its version,
  bundled YAML and `--n-jobs` / `--strict` parser support.
- Checked the source archive includes this report and the historical review,
  excludes obsolete root `REVIEW.md`, and excludes `changes.patch`.
- Applied `changes.patch` to a clean archive of baseline 429b32d and compared every
  resulting file byte for byte with the delivered source, including removals.
- `git diff --check` passed. Re-scanned current source/docs/test/citation files
  for the identifying benchmark values; no matches. Verified all changed/new
  Python files pass Ruff (147 findings remain only in untouched files).
- Final archive integrity and source/patch equivalence checks passed. Git HEAD
  remains baseline 429b32d; no commit or push was made.
