# GROOVE

GROOVE downloads, cleans and analyses ATLAS light curves, then assigns morphology
suggestions and builds interactive maps for reviewing unusual variability.
One configuration connects all five stages. Each stage can also run separately.

| Stage | Purpose | Main output |
|---|---|---|
| `download` | Retrieve forced photometry with your ATLAS token; resume saved jobs | One raw CSV per source |
| `clean` | Remove measurements failing photometric and image-quality checks | Cleaned CSVs, retention and rejection tables |
| `select` | Select sources with enough observations, baseline and usable precision | Selected light curves and rejection reasons |
| `periods` | Search with Lomb–Scargle; diagnose aliases and harmonics; optionally check BLS | One recommendation per source, diagnostic tables and plots |
| `morphology` | Measure light-curve shapes, suggest families, apply manual labels and optionally fit UMAP | Source catalogue, review plots and interactive maps |

The scientific routines originate from Aidan Duffy's MSc thesis, *The Search
for Exotic Transits* (Universidad Autónoma de Madrid, 2026). The package retains
the detailed analysis rather than reducing it to a single periodogram or
embedding. Automatic labels are review suggestions; a `transit` label describes
shape and does not establish a planetary interpretation.

## Install

Use Python **3.10–3.12**. Open a terminal in the extracted `GROOVE` folder:

```bash
python -m venv .venv
```

Activate it on macOS/Linux with `source .venv/bin/activate`, or in Windows
PowerShell with `.venv\Scripts\Activate.ps1`. Then:

```bash
python -m pip install --upgrade pip
python -m pip install -e .
groove --version
```

Alternatively, `conda env create -f environment.yml`, followed by
`conda activate groove`, installs the supplied Conda environment.
`python -m groove` can be used wherever these examples say `groove`.

## Try it without an ATLAS account

```bash
groove demo groove_demo
groove run -c groove_demo/run.yaml --skip-download
```

This creates 12 seeded synthetic stars with wavelike, dipping and constant
signals, a truth table, and a complete configuration. It runs cleaning,
selection, period searching, classification and UMAP. All observations are
artificial. This is an installation and integration demonstration, not a
survey completeness measurement. To repeat the fitted morphology stage, use
`groove morphology -c groove_demo/run.yaml -- --overwrite`.

## Analyse your targets

1. Create a CSV with a source ID and coordinates in degrees, for example:

   ```csv
   GaiaDR3,RAdeg,DEdeg,group
   YOUR_SOURCE_ID,YOUR_RA,YOUR_DEC,YOUR_GROUP
   ```

   Gaia IDs must be preserved as text. Common column names are detected
   automatically; see [target formats](data/targets/README.md).

2. Generate and edit a configuration:

   ```bash
   groove init run.yaml
   ```

   The essential fields are:

   ```yaml
   name: my_sample
   output_folder: results/my_sample
   targets: my_targets.csv
   years: full
   ```

   Paths are relative to the YAML file. Optional `group`, `group_column`,
   `filters` and `gaia_id` restrict which rows are downloaded.
   `groove targets my_targets.csv` lists columns and group counts.

3. Set your ATLAS forced-photometry token in the same terminal:

   ```powershell
   $env:ATLAS_TOKEN = "your-token"  # Windows PowerShell
   ```

   ```bash
   export ATLAS_TOKEN="your-token" # macOS / Linux
   ```

   Obtain a token through your [ATLAS account](https://fallingstar-data.com/forcedphot/).
   A token is needed only for downloads. It is never written to configuration,
   progress or output files.

4. Check the selection, then run:

   ```bash
   groove download -c run.yaml --dry-run
   groove run -c run.yaml
   ```

   Dry runs make no requests and do not change files. Downloads process one
   source at a time and save progress after each state change. Rerun the same
   command after an interruption to resume saved task or result URLs. Service
   time depends on the ATLAS queue; the displayed estimate is configurable.

Stages can be run independently with `groove download`, `groove clean`,
`groove select`, `groove periods` or `groove morphology`, each with `-c run.yaml`.
A nonzero download result stops the full pipeline before analysis begins.

## Other ATLAS data access

The [ATLAS data directory](http://dtn-itc.ifa.hawaii.edu/atlas/atclass/)
is included as an additional resource. The directory inspected on 7 October
2026 lists reduced/difference images, detection-classification products and
`dclass`/`nnc` manuals. It is not a drop-in per-star light-curve download endpoint.

GROOVE analyses photometry tables, not image pixels or individual detection
classification vectors. FITS images need photometric extraction first; renaming
or converting an image file to CSV does not create a light curve. If you obtain
per-source time-series photometry from an archive or a separate extraction
workflow, prepare it as the CSV format below, then use `input_folder` and
`--skip-download`. Check the data's baseline and provenance; archive products
are not automatically equivalent to a fresh forced-photometry request.

## Use existing photometry

Set `input_folder` to a directory of raw per-source ATLAS CSVs:

```yaml
name: archive_sample
input_folder: existing_lightcurves
output_folder: results/archive_sample
morphology:
  mode: fit
```

Run `groove run -c run.yaml --skip-download`. This requires no token.
Inputs should include time (`MJD` or `###MJD`), filter (`F`), and magnitude/error
(`m`, `dm`) or flux/error (`uJy`, `duJy`). Include an ID column such as
`target_GaiaDR3` or `source_id` where possible. Image-quality checks are applied
when their columns exist; missing quality columns cannot provide those checks.

The cleaner retains noise-consistent negative forced fluxes. Magnitude-based
morphology uses finite magnitudes and positive measured fluxes; such rows may
therefore be retained by cleaning but unavailable to morphology.

## One star or a small sample

A reference UMAP fit needs at least **five usable sources**. For fewer sources,
use `morphology: {mode: classify}`. It measures the same features, assigns the
same rules and writes tables and phase plots without fitting a map. You can
also stop after period searching with `groove run -c run.yaml --skip-morphology`.

`configs/single_target.yaml` illustrates the classification route. Its target
CSV and Gaia ID must be replaced with your real values.

## Results

| Path under `output_folder` | Contents |
|---|---|
| `1_raw/atlas_full_reduced/all_lightcurves/` | Downloaded photometry; numeric baselines use their own run folder |
| `1_raw/<run>/download_progress.csv` | Saved status, task/result URLs and failures |
| `2_clean/lightcurves/` | Cleaned CSVs, cleaning summary and source-selection tables |
| `2_clean/selected/` | Passing light curves and `selected_sources.csv` |
| `3_periods/tables/source_period_recommendations.csv` | Adopted period and diagnostics per source |
| `plots/clean/`, `plots/periods/` | Cleaning and period-search figures |
| `4_morphology/model_versions/model_<version>/` | Fitted models, tables, maps and source plots |
| `4_morphology/classification/` | Tables and source plots for `mode: classify` |

An unnamed model lives directly under `4_morphology/model_versions/`.
Start with the period recommendation table and morphology `tables/all_sources.csv`.
Open `maps/*interactive.html` in a browser. Keep the surrounding output tree
with the HTML so linked images remain accessible.

## Add targets to an existing map

Use `transform` and point `output_root` to the **same morphology directory**
that holds the reference model. The new batch can have its own analysis folder:

```yaml
name: new_batch
output_folder: results/new_batch
targets: new_targets.csv
morphology:
  mode: transform
  output_root: results/reference/4_morphology
  model_version: reference_v1
  n_jobs: 1
```

Fit the reference with `model_version: reference_v1` first. Frozen preprocessing
and UMAP are reused; changing representation settings requires a new fit.
Existing source IDs are skipped by default. `current_model.json` identifies the
current reference when no version is specified.

## Settings and scientific interpretation

Override defaults under `download`, `clean`, `select`, `periods` or `morphology`.
For example:

```yaml
periods:
  max_period_days: 100
  run_bls: false
  plot_time_segments: 4
morphology:
  use_c_band: true
  use_o_band: true
  thresholds:
    flare_min_events: 4
```

The packaged source-selection defaults are 100 measurements, 30 in one usable
band, 365 days of baseline, at most 50% removed and median magnitude uncertainty
at most 0.2 in a band meeting the point-count requirement. These are stricter
than the period search's internal minimums of 50 points and 20 days. Choose cuts
for your sample explicitly; this release does not newly validate those thresholds.

Both filters are enabled for morphology by default. Cadence aliases remain
flags rather than automatic exclusions. UMAP coordinates describe local feature
similarity and are not physical axes or a classifier. Read
[stage details](docs/stages.md) and [morphology notes](docs/morphology_details.md).

## Development and citation

```bash
python -m pip install -e ".[dev]"
python -m pytest
python -m build
```

The tests cover stage integration, seeded period recovery, download resumption,
configuration, cleaning and morphology regressions. The downloadable demo runs
the full map workflow. The original thesis scripts and credentials are not
required for installation and are not included in this distribution.

`CITATION.cff` supplies citation metadata. Include the acknowledgements required
by the ATLAS service when publishing analyses. Licence: MIT.
