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
