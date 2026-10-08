# Changes in 1.0.9

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

# Changes in 1.0.8

- Fixed field alias learning for the default O/C-only period search. Auto learning pools O/C peaks per star, preferring combined peaks when available, without counting a star twice.
- Retained explicit single-band/combined learning for reproducible reference comparisons, and warn when the requested series is absent.
- Preserve long source IDs as text in reference summaries.
- Document fresh, contained period-stage retesting and original-reference comparison.
- Raw LS/BLS computations and classification thresholds are unchanged by this release.

# Changes in 1.0.4

- Added a synthetic daily-contamination example whose strongest LS peak is near one day and whose rank-two 8.3-day stellar peak is automatically promoted using the existing alias rule.
- Kept the weaker-secondary-peak example to demonstrate conservative flagging without replacement.
- Moved all morphology figures to results/plots/ML/<run>/ and numerical model/table/cache state to 4_morphology/saved_runs/<run>/.
- Preserved loading of older model layouts; replotting older saved runs writes figures to the new plot folder.
- Added layout, HTML-link, legacy-loading and numerical alias-recovery regressions.
- Added a Linux updater that backs up overwritten source, preserves existing configuration/target files, tests the installation and commits/pushes only release files.

# Changes in 1.0.3

- Added an opt-in 23-source extended synthetic demonstration with automatic alias folds, BLS and known eclipse/flare/irregular/evolving/noisy/single-filter inputs.
- Added demo-check reporting for injected period recovery, review labels, diagnostic figures and PNG integrity.
- Bundled Linux/WSL validation instructions and download/output audit helpers.

- Corrected period-review dominance routing to accept either P1/P2 >= 1.5 or P1/P4 >= 1.8, consistently with the existing significance rule.
- Required significance before routing any dominant series to a strong/alias/harmonic folder.
- Preserved alias and harmonic warnings and all numerical period-search settings/results.
- Added regressions for all four demo dips, competitive noise peaks, absent significance and alias/harmonic warnings.

# Changes in 1.0.2

- Added the documented self-contained interactive HTML maps, with hover details and clickable phase plots.
- Made source-highlight neighbour plots respect the configured cyan/orange filters.
- Validated saved period PNGs before publishing or reusing them; incomplete images trigger regeneration.
- Made period-plot failures stop the pipeline with a clear error rather than mark the run complete.
- Corrected misleading comments about cleaning/rescue defaults and filter fixtures.
- Kept empty detached-family CSVs readable with stable headers.
- Added a simulated-download-through-analysis integration test.
- Added regression checks for cyan-only highlighting, damaged PNG recovery and HTML map links.

# Changes in 1.0.1

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
- Linked the requested ATLAS data directory with an accurate distinction between images,
  detection products and per-source photometry.

The original analysis remains split into modules for maintenance. The redundant download
progress module was merged into the serial downloader. No standalone credential script
is needed or included. Default source-selection cuts remain those of the supplied package;
these are distinct from the less restrictive internal period-search cuts. Dip rescue remains
off by default; the supplied original cleaner had it enabled, so equivalent numerical checks
explicitly matched that setting before comparison.
