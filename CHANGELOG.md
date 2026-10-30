# Changelog

## Unreleased

- Use round photometry markers with light borders in individual, morphology, period and cleaning light-curve plots; distinguish mixed-band C points with open circles.
- Use four chronological colours by default in period-search folds.
- Add a standalone band-selected source-fold export using the saved morphology period, without altering analysis bands or saved products.
- Fold the main period-review panel at the adopted source period, including supported 2P corrections; retain raw/per-series peaks and explicit display overrides.
- Mention the optional 24-source extended demo in the README.
- Toggle interactive-map previews on repeated point clicks; retain legend and zoom double-click controls.
- Emphasise phase 0.5--1.5 in double-phase plots and grey the repeated sections, including median curves.
- Honour the configured single-cycle display when constructing period-plot phase arrays.
- Document regeneration of phase-only morphology images and map controls without refitting.

## 1.1.1

Documentation, comments and metadata only; calculations and thresholds are unchanged.

- Refresh public workflow guides, command examples, morphology output paths and CLI options.
- Align bundled and generated configuration options while retaining their relative path bases.
- Use the full GROOVE title in citation metadata and describe its general ATLAS target scope.
- Clarify scientific comments and defaults without changing calculations or thresholds.
- Remove the obsolete version-specific ZIP updater; use explicit source-update commands.
- Limit source-distribution templates to public example files, excluding local configurations and target lists.
- Put current validation results first, followed by clearly labelled historical results.
- Correct the documented BLS default (enabled, diagnostic only).

## 1.1.0

- Opt-in process-parallel period searches (`--n-jobs`, default 1), with deterministic parent-owned journals, source caps and ordered result merging; serial fallback for small batches.
- Fix journal reconstruction order so repaired tables retain deterministic input order.
- Route stage progress through logging; reserve console setup for the CLI.
- Remove unused process-global NumPy seeding; stochastic algorithms retain their own explicit seeds.
- Log caught stage exception types/messages and add scoped `--strict` fail-fast execution.
- Add numerical tests for recovery, odd/even and multiharmonic doubling, alias replacement/retention, shared alias scores, cross-filter anchoring and single-filter SNR boundaries.
- Use artificial demo/fixture IDs and distinct synthetic periods; retain double dips.
- Unify alias diagnostics with adoption weights (0.50/0.50/0.35); remove unused penalty setting.
- Gate supported single-filter provenance on fold/peak SNR; preserve low-support candidate periods with explicit warnings.
- Support NumPy 2 and allow Python 3.13; extend CI; add non-blocking Ruff diagnostics.
- Modernise SPDX licence metadata and require setuptools >=77 for its build support.
- Synchronise package and citation versions.

## Changes after 1.0.9 (included in 1.1.0)

- Change the current source licence from MIT to GNU GPL version 3 only (`GPL-3.0-only`); align the README and package/citation metadata. Permissions previously granted for MIT-distributed copies remain unaffected.
- Reorder README around installation, demonstration and common workflows; add citation and feedback guidance.
- Consolidate documentation into stable guides, one validation page and this changelog.
- Windows compatibility: acquire the token lock before accessing its byte range; explicitly read generated HTML as UTF-8 in tests; test lock release after errors.

## 1.0.9

- Automatic, content-checked completion receipts for all CLI stages and full-pipeline resume.
- Added --rerun to every stage and the full run command, including forced output regeneration.
- Atomic cleaning-source checkpoints; unchanged selected files retain timestamps.
- Atomic period-source journals before the full-table checkpoint, with retry of failed sources.
- Separate scientific period-cache identity from visual settings; checked plot reuse and repair.
- Freeze alias-memory inputs per analysis instead of merging a resumed run into its own output.
- Retain fitted morphology science for output repair; add transform-output checkpoints and period-aware feature cache keys.
- Validate downloaded CSV headers before reuse and reuse completed stage receipts without re-authenticating.
- Report unsuccessful cleaning/period/morphology feature stages as incomplete instead of recording success.
- Added interruption, complete-run repeat, damaged/missing output, forced rerun and parser regressions.

## 1.0.8

- Fixed field alias learning for the default O/C-only period search. Auto learning pools O/C peaks per star, preferring combined peaks when available, without counting a star twice.
- Retained explicit single-band/combined learning for reproducible reference comparisons, and warn when the requested series is absent.
- Preserve long source IDs as text in reference summaries.
- Document fresh, contained period-stage retesting and original-reference comparison.
- Raw LS/BLS computations and classification thresholds are unchanged by this release.

## 1.0.7

- Bound interactive comparison-card sizes, wrap previews into rows and enable map zoom/pan/reset controls.
- Preserve saved map coordinates and scientific results when redrawing.

## 1.0.6

- Add optional dataset shapes, new-batch outlines and side-by-side phase-image comparison.
- Document stage-by-stage, existing-data and frozen-map workflows.

## 1.0.5

- Default to O/C-only period searches and independently selectable plot series; combined analysis remains optional.
- Export three default overview maps while retaining internal representations.
- Removing combined analysis can change alias learning and adopted periods; it is not merely an output-saving change.

## 1.0.4

- Added a synthetic daily-contamination example whose strongest LS peak is near one day and whose rank-two 8.3-day stellar peak is automatically promoted using the existing alias rule.
- Kept the weaker-secondary-peak example to demonstrate conservative flagging without replacement.
- Moved all morphology figures to results/plots/ML/<run>/ and numerical model/table/cache state to 4_morphology/saved_runs/<run>/.
- Preserved loading of older model layouts; replotting older saved runs writes figures to the new plot folder.
- Added layout, HTML-link, legacy-loading and numerical alias-recovery regressions.

## 1.0.3

- Added an opt-in 23-source extended synthetic demonstration with automatic alias folds, BLS and known eclipse/flare/irregular/evolving/noisy/single-filter inputs.
- Added demo-check reporting for injected period recovery, review labels, diagnostic figures and PNG integrity.
- Bundled Linux/WSL validation instructions and download/output audit helpers.

- Corrected period-review dominance routing to accept either P1/P2 >= 1.5 or P1/P4 >= 1.8, consistently with the existing significance rule.
- Required significance before routing any dominant series to a strong/alias/harmonic folder.
- Preserved alias and harmonic warnings and all numerical period-search settings/results.
- Added regressions for all four demo dips, competitive noise peaks, absent significance and alias/harmonic warnings.

## 1.0.2

- Added the documented self-contained interactive HTML maps, with hover details and clickable phase plots.
- Made source-highlight neighbour plots respect the configured cyan/orange filters.
- Validated saved period PNGs before publishing or reusing them; incomplete images trigger regeneration.
- Made period-plot failures stop the pipeline with a clear error rather than mark the run complete.
- Corrected misleading comments about cleaning/rescue defaults and filter fixtures.
- Kept empty detached-family CSVs readable with stable headers.
- Added a simulated-download-through-analysis integration test.
- Added regression checks for cyan-only highlighting, damaged PNG recovery and HTML map links.

## 1.0.1

- Unified package metadata, command, imports, examples and documentation as GROOVE.
- Simplified downloads to one `ATLAS_TOKEN`, serial requests and one progress table.
- Retained task/result resumption, frozen time limits, atomic saves and completed-file reuse.
- Added a same-token process lock and prevented new submissions while remote work is unresolved.
- Propagated download/morphology failures and added readable CLI error handling.
- Corrected metadata transfer for Gaia IDs, grouping, catalogue periods and coordinates.
- Preserved long source IDs while reading CSVs.
- Corrected the path passed to morphology for period-search figures.
- Reset stage settings between Python calls and merged nested morphology overrides.
- Resolved nullable and list-valued file settings relative to the YAML file.
- Recomputed derived period-plot colours after timeline-segment overrides.
- Invalidated period checkpoints when code, settings or inputs change.
- Required source-selection precision and point-count criteria in the same usable band.
- Enabled both morphology filters by default and removed forced orange-only output folds.
- Added classification without UMAP for single sources and small samples.
- Added an offline 12-source synthetic demo, integration/download tests and CI builds.
- Rewrote installation, usage, stage and morphology documentation.
- Linked the ATLAS data directory with a distinction between images,
  detection products and per-source photometry.

Source-selection cuts are distinct from the less restrictive internal period-search
minimums. Dip rescue is off by default; comparisons with earlier scripts explicitly
matched that setting before assessing numerical parity.
