# Stage contracts

`groove.pipeline` sets stage inputs and outputs from a single configuration.
Relative configuration paths are resolved against the YAML file. Defaults are
reset before each stage, so calling several runs in one Python process does not
carry earlier overrides into a later run.

| Stage | Input | Output |
|---|---|---|
| Download | `targets` CSV, filters, coordinates, `ATLAS_TOKEN` | `1_raw/<run>/all_lightcurves/*.csv` |
| Clean | Downloaded files or `input_folder` | `2_clean/lightcurves/*_cleaned.csv`, `cleaning_summary.csv` |
| Select | Cleaning summary and cleaned files | `2_clean/selected/*_cleaned.csv`, `selected_sources.csv` |
| Periods | Selected cleaned files | `3_periods/tables/`, `plots/periods/` |
| Morphology | Selected files and source-level period recommendations | `4_morphology/`, or the configured morphology `output_root` |

## Downloads

`targets.py` selects and deduplicates targets without converting source IDs
through floating point. Coordinates must be RA in [0,360] and Dec in [-90,90].
`client.py` handles the ATLAS API. `storage.py` supplies atomic CSV/JSON saves;
`run.py` handles the single serial download and checkpoint state.

Set `ATLAS_TOKEN` in your shell. Existing completed files are kept unless
`download.force_redownload` is true. The downloader freezes numeric-baseline
MJD limits at the first real run, so a restart requests the same interval.
`years: full` explicitly requests unrestricted history. It saves:

| File | Purpose |
|---|---|
| `run_config.json` | Frozen time range and photometry mode |
| `selected_targets.csv` | Selected input rows |
| `download_progress.csv` | Status, metadata, remote task/result URLs, errors and output paths |
| `all_lightcurves/*.csv` | Photometry with source metadata for later stages |

One pending job is polled and saved before the next target is submitted. A
polling/network/save failure pauses the run and returns a nonzero exit code;
authentication failures also stop it. Resuming an unfinished job takes precedence
over forcing a new download or changing target filters. A local OS lock prevents
two GROOVE processes from downloading with the same token at once.

If submission times out before a task URL is received, the server may still
have accepted it. Progress records `submission_unknown`. Check your ATLAS queue:
put the accepted job's `task_url` in that row and change its status to `submitted`,
or set the status to `pending` after confirming no job exists. Then rerun. This
avoids silently submitting the same request again. HTTP throttling uses the
server's reported wait when available.

Useful `download:` settings include `limit_targets`, `poll_seconds`,
`max_retries`, `retry_delay_seconds`, `max_poll_hours`, `retry_failed_targets`,
`force_redownload` and `end_date_utc`. A dry run reads targets but no token and
writes nothing. Cross-baseline reuse is deliberately explicit: use an existing
photometry folder through `input_folder`; a file from another run is not silently
substituted for the requested baseline.

## Cleaning

`cuts.py` normalises photometry and applies hard validity and optional image
quality cuts. Available checks include S/N, depth, sky, PSF axes, aperture fit,
detector position and ATLAS error flags. A missing quality column does not
reject everything; that check is absent and reported in the summary.

Noise-consistent negative forced fluxes are retained; highly negative S/N and
invalid uncertainties are rejected. `clean.rescue_enable` defaults to false.
Rescue can restore dimming points failing only soft quality cuts; inspect those
measurements before enabling it for a science sample.

Outputs include the cleaned photometry, retained/removed counts per source and
band, baselines, precision, reasons, and the full `cleaning_summary.csv`.
Cleaning figures live under `plots/clean/`.

## Source selection

The packaged defaults are:

| Setting | Default |
|---|---:|
| `min_points` | 100 |
| `min_points_per_band` | 30 |
| `min_baseline_days` | 365 |
| `max_removed_fraction` | 0.5 |
| `max_median_uncertainty_mag` | 0.2 |

At least one band must meet both the point-count and precision cuts. These are
sample-selection choices, distinct from the period-search minimums.
`source_selection.csv` and `source_selection_reason_counts.csv` explain rejections.
Passing files are staged by hard link with a copy fallback. Missing selected
files produce an error rather than a misleading selected-source count.

## Periods

The main search defaults to weighted Lomb–Scargle periodograms for orange
and cyan separately. Combined photometry is opt-in through `series_to_run`;
its centring remains per band. `plot_series` independently selects saved series
plots (see [output options](release_1_0_5.md)). The
upper period is restricted by the observed baseline and minimum cycle count.
BLS is an optional diagnostic and does not set the recommendation by default.

The code evaluates universal and field-local cadence aliases, spectral-window
support, relative peak strength, fold coherence, inter-band agreement, odd/even
cycles, and multiharmonic support for a doubled period. An alias is retained
when source evidence supports it; ambiguity is recorded in the output.
Catalogue periods are used for validation/review, not as the blind-search input.

Important tables are `source_period_recommendations.csv` (one row per source),
`ls_period_search_summary.csv` (one row per series), `ls_period_search_peaks.csv`,
`ls_validation_summary.csv`, and field-alias inventories/memory. Figures live
under `plots/periods/`, with a best-per-star view and review category folders.

Checkpoints resume the same inputs/configuration. Changes to inputs, settings
or period-stage code invalidate cached scientific results. Tables should always
be inspected for failed/skipped series; a run with no successful analysis raises
an error. Partially failed runs do not receive a completion marker.

## Morphology

`features.py` measures shapes and time variation; `classify.py` assigns rules
and manual labels; `embedding.py` fits or transforms frozen representations;
`persistence.py` saves models/checkpoints; `plots.py` and `outputs.py` create
review products. `modes.py` coordinates these operations.

| Mode | Use |
|---|---|
| `classify` | Tables, rules and phase plots for any sample size; no UMAP |
| `fit` / `refit` | Fit a reference with at least five usable feature records |
| `transform` | Add sources to an existing reference without refitting |
| `relabel` | Apply changed manual labels to saved results |
| `plot-only` | Regenerate saved phase-fold products |
| `highlight-source` | Inspect a saved source and its neighbours |
| `umap-families` | Additional density-region review of a saved map |

Extra morphology flags follow `--`, e.g.
`groove morphology -c run.yaml -- --mode relabel`.
The source-level period recommendation is authoritative. Both filters are
accepted by default. Manual labels use `manual_primary_tag` and
`manual_secondary_tags`, as shown in `data/manual_labels_template.csv`.
See [morphology notes](morphology_details.md) for interpretation and persistence.

### Period-review strength

A strong review detection requires the significance check and either
P1/P2 >= 1.5 or P1/P4 >= 1.8. The latter allows a coherent non-sinusoidal signal
with a competitive second peak to pass. Alias and harmonic evidence still
route it to their review folders. These ratios compare peak powers, not period
values. A strong detection label does not prove that a unique physical period
or a planetary transit has been identified. This review-rule change does not
change the computed periodogram, candidate periods or adopted period.
