# GROOVE

**Author:** Aidan Duffy

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)

GROOVE is a Python package for finding and reviewing unusual variability in
ATLAS light curves. It connects downloading, cleaning, source selection, period
searching and morphology analysis in one workflow, with diagnostic plots and
interactive maps. Each stage can also run separately. Other photometric
datasets can be adapted by formatting them to the required input schema and
checking that the quality cuts and analysis settings suit the data.

The accompanying paper is **in preparation**. If you use GROOVE, please cite
this software using [CITATION.cff](https://github.com/aidan-duffy/GROOVE/blob/main/CITATION.cff)
and record the version or commit used.

All feedback, bug reports and suggestions are welcome. Contact
[Aidan Duffy](mailto:aidan.duffy@estudiante.uam.es).

## Find your workflow

- [Install GROOVE](#install)
- [Try the synthetic demo](#try-it-without-an-atlas-account)
- [Download ATLAS photometry](#download-atlas-photometry)
- [Run the full pipeline](#run-the-full-pipeline)
- [Run individual stages](#run-individual-stages)
- [Use existing photometry](#use-existing-photometry)
- [Find your results](#results)
- [Restart or recalculate](#restart-or-recalculate)
- [Add targets to an existing map](#add-targets-to-an-existing-map)
- [Configure plots and analysis](#settings-and-scientific-interpretation)
- [Read all configuration options](docs/configuration.md)
- [Browse the documentation](docs/README.md)
- [Validation evidence and limitations](docs/validation.md)
- [Adapt data from other surveys](docs/data_workflows.md#other-surveys-adaptation-not-currently-validated-support)

## Install

Use Python **3.10–3.12**. Download and extract the repository ZIP from GitHub,
or clone it:

```bash
git clone https://github.com/aidan-duffy/GROOVE.git
cd GROOVE
```

Open a terminal in the `GROOVE` folder and create an environment:

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
groove demo-check groove_demo
```

This creates 12 seeded synthetic stars with wavelike, dipping and constant
signals, a truth table, and a complete configuration. It runs cleaning,
selection, period searching, classification and UMAP. All observations are
artificial. This is an installation and integration demonstration, not a
survey completeness measurement. To repeat the fitted morphology stage, use
`groove morphology -c groove_demo/run.yaml -- --overwrite`.

## Download ATLAS photometry

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

4. Preview the target selection, then download:

   ```bash
   groove download -c run.yaml --dry-run
   groove download -c run.yaml
   ```

   Dry runs make no requests and do not change files. Downloads process one
   source at a time and save progress after each state change. Repeat the same
   command after an interruption to resume saved tasks. Service time depends
   on the ATLAS queue.

## Run the full pipeline

After downloading, run cleaning, selection, period searching and morphology:

```bash
groove run -c run.yaml --skip-download
```

To download and analyse in one command instead:

```bash
groove run -c run.yaml
```

A nonzero download result stops the full pipeline before analysis begins.
`-c` selects the configuration file. Paths inside it are relative to that file.
See [Results](#results) for the output folders.

## Run individual stages

Use the same configuration for each stage, in this order:

```bash
groove download -c run.yaml
groove clean -c run.yaml
groove select -c run.yaml
groove periods -c run.yaml
groove morphology -c run.yaml
```

Skip `download` when using existing photometry. Each later stage needs the
appropriate inputs from the preceding stage or explicit input paths in the
configuration. The period stage normally reads the selected light curves;
morphology uses them together with the period recommendations.

For starting from cleaned or selected data, see
[existing-data workflows](docs/data_workflows.md#resume-at-a-later-stage).
Read [stage details](docs/stages.md) for each stage's inputs and outputs.

To see available commands and options:

```bash
groove --help
groove periods --help
```

Replace `periods` with any stage name for its help. Analysis commands require a
YAML configuration; `-c` and `--config` are equivalent. Utility commands such as
`init`, `demo` and `targets` do not require one. Most scientific and plotting
settings belong in the YAML; see [configuration options](docs/configuration.md).

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

## Results

| Path under `output_folder` | Contents |
|---|---|
| `1_raw/atlas_full_reduced/all_lightcurves/` | Downloaded photometry; numeric baselines use their own run folder |
| `1_raw/<run>/download_progress.csv` | Saved status, task/result URLs and failures |
| `2_clean/lightcurves/` | Cleaned CSVs, cleaning summary and source-selection tables |
| `2_clean/selected/` | Passing light curves and `selected_sources.csv` |
| `3_periods/tables/source_period_recommendations.csv` | Adopted period and diagnostics per source |
| `plots/clean/`, `plots/periods/` | Cleaning and period-search figures |
| `4_morphology/saved_runs/<run>/` | Fitted models, tables and caches |
| `4_morphology/classification/` | Tables and source plots for `mode: classify` |

Morphology figures live in `plots/ML/<run>/`, including maps, phase folds, category folders and appendix figures. An unnamed run uses `default`; classification-only plots use `plots/ML/classification/`. Older saved models can still be loaded.
Start with the period recommendation table and morphology `tables/all_sources.csv`.
Open `maps/*interactive.html` in a browser. Keep the surrounding output tree
with the HTML so linked images remain accessible.

## Pipeline overview

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

## Restart or recalculate

Resume is automatic: rerun the same command with the same configuration and
output folder. Completed stages are checked and skipped; interrupted stages
reuse compatible source and plot checkpoints.

```bash
groove run -c run.yaml --skip-download           # resume existing photometry workflow
groove periods -c run.yaml                      # resume just the period stage
groove run -c run.yaml --skip-download --rerun   # deliberately recalculate all analysis stages
groove morphology --rerun -c run.yaml           # recalculate morphology and its outputs
```

Keep `--skip-download` when using existing raw data. A full `--rerun` without it
also requests fresh downloads. If a forced rerun is interrupted, omit `--rerun`
on the next invocation to resume the newly saved work. See
[restart details and limitations](docs/restarts.md).

## One star or a small sample

A reference UMAP fit needs at least **five usable sources**. For fewer sources,
use `morphology: {mode: classify}`. It measures the same features, assigns the
same rules and writes tables and phase plots without fitting a map. You can
also stop after period searching with `groove run -c run.yaml --skip-morphology`.

`configs/single_target.yaml` illustrates the classification route. Its target
CSV and Gaia ID must be replaced with your real values.

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

## Find a new sample and compare individual light curves

```yaml
morphology:
  dataset_markers:
    my_sample: circle
    new_batch: diamond
  outline_new_sources: true
```

Dataset names match each configuration's top-level `name`. Omit dataset_markers
for identical circles. Colours remain morphology labels; shapes identify samples.
To update maps after a batch has already been added:

```bash
groove morphology -c configs/new_batch.yaml -- --mode map-only
```

This redraws saved maps without recomputing scientific results. In the interactive
map, click several stars (or use lasso/box selection) to compare phase images in fixed-width cards that wrap into rows below it. Drag or scroll to zoom
the map; double-click to reset. Remove individual previews or clear the selection. See
[map controls](docs/map_controls.md) for shapes, legends and single-star highlighting.

## Settings and scientific interpretation

Period searches and saved period plots default to O and C. To also analyse
combined photometry while keeping only O/C plots:

```yaml
periods:
  series_to_run: [combined, o, c]
  plot_series: [o, c]
  alias_learning_series: combined
```

Combined analysis can change field alias learning and source recommendations;
disabling only its plots preserves that analysis. The default alias-learning
mode is `auto`: it uses combined peaks when available, otherwise pools O/C
peaks while counting each star once. These approaches are not equivalent.

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

## Extended demonstration and Linux validation

For alias, harmonic, flare, irregular/evolving and single-filter examples:

```bash
python -m groove demo demo_extended --extended
python -m groove run -c demo_extended/run.yaml --skip-download
python -m groove demo-check demo_extended
```

This contains 24 artificial sources. Read `demo_extended/CASE_GUIDE.md` and
inspect `demo_source_review.csv`; injected behaviours are not forced labels.
Automatic alias folds and BLS are enabled for this demonstration. The default
12-source demo and its seeded raw observations remain unchanged.

Follow [the Linux/WSL validation guide](docs/linux_validation.md) to test each
stage, saved-model operations and one authenticated real download. The tools
folder includes download-integrity and original-function comparison helpers.

The extended source `3216489845356186519` has a dominant daily systematic and
an injected 8.3-day stellar wave. Its rank-two stellar peak clears the existing
replacement threshold, so the automatic alias-candidate figure shows the true
period being recommended over rank one. This differs from the original daily
example, which remains flagged because its stellar peak is too weak to promote.

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
by the ATLAS service when publishing analyses. Licence: GNU GPL version 3 only (`GPL-3.0-only`); see [LICENSE](LICENSE).
