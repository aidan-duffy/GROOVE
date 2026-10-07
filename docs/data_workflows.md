# Run individual stages or use existing data

## Normal folders

Keep configurations in configs/, target ID/coordinate tables in data/targets/,
and each run's data and outputs under results/<sample>/. Raw photometry is not
a target list. Paths within YAML are resolved relative to that YAML file.

```yaml
# configs/my_sample.yaml
name: my_sample
targets: ../data/targets/my_sample.csv
output_folder: ../results/my_sample
years: full
photometry: reduced
periods:
  series_to_run: [o, c]
  plot_series: [o, c]
morphology:
  mode: fit
  model_version: reference_v1
```

The downloader uses your ATLAS_TOKEN environment variable. O/C analysis is the
default; add combined to series_to_run and/or plot_series as appropriate. Only
analysed series can be plotted. Morphology's combined map joins feature sets,
not photometric bands.

## Run stage by stage

From the repository folder:

```bash
groove download -c configs/my_sample.yaml --dry-run
groove download -c configs/my_sample.yaml
groove clean -c configs/my_sample.yaml
groove select -c configs/my_sample.yaml
groove periods -c configs/my_sample.yaml
groove morphology -c configs/my_sample.yaml
```

-c is short for --config. Download saves 1_raw/<download_run>/all_lightcurves;
clean saves 2_clean/lightcurves; select stages passing files in 2_clean/selected;
periods reads selected files and writes 3_periods/tables; morphology reads those
same selected files plus their period recommendations. State is under
4_morphology/saved_runs/<version>; all plots are under plots/{clean,periods,ML}.
Use the same configuration throughout. Fit requires at least five usable sources;
for individual stars/small samples use morphology.mode: classify.

## Existing raw ATLAS photometry: skip downloading

Replace targets with input_folder in the example:

```yaml
input_folder: ../existing_photometry
```

Do not set ATLAS_TOKEN; no token is needed to analyse existing data. Run:

```bash
groove run -c configs/my_sample.yaml --skip-download
```

Or run clean, select, periods and morphology individually. The input_folder is
the directory containing per-source raw CSVs, not a single CSV. Original files
are read; cleaned outputs are written separately. Files must supply time, band
and photometry with uncertainties. See README's accepted column conventions.

## Resume at a later stage

If cleaning has completed, run select next; if selection has completed, run
periods; if periods has completed, run morphology. There is no general
--skip-clean flag: individual commands are how to skip completed earlier stages.

For externally cleaned photometry, place/copy compatible per-source cleaned
CSVs in this run's 2_clean/selected/ and invoke periods, then morphology.
This explicitly bypasses GROOVE cleaning and source selection; you are responsible
for those quality/usability checks. Do not point clean.input_dir to cleaned data
and call the full run unless you intend to clean it again. Existing period tables
must follow GROOVE's schemas and correspond to the selected sources; arbitrary
external period tables are not automatically interchangeable.

## Add another sample to a frozen map

Process the new sample's cleaning/selection/periods in its own output folder.
Use the same morphology feature settings as the reference:

```yaml
morphology:
  mode: transform
  output_root: ../results/my_sample/4_morphology
  model_version: reference_v1
  batch_id: second_sample
  outline_new_sources: true
  dataset_markers:
    my_sample: circle
    second_sample: diamond
```

Here second_sample should also be the new configuration's top-level name.
Run morphology for the second config. Reference coordinates are kept, and new
sources are added to shared tables/maps. Existing IDs are skipped by default.
[Map controls](map_controls.md) explains styling and multi-source comparison.

## Other surveys: adaptation, not currently validated support

GROOVE is developed and tested for ATLAS. Column renaming alone does not establish
correct analysis of other surveys. A future input adapter should define time
units/reference system, magnitude or flux convention, uncertainty units, filter
mapping and handling of missing/flagged observations. Never disguise another
survey's filters as O/C merely to make the files load.

Adapt image/photometry quality cuts, instrumental detrending, source-selection
limits, and cadence/window alias assumptions. Review period ranges and feature
normalisation; handle available bands explicitly. Fit a suitable reference and
validate morphology rules against known variables from the new survey. A frozen
ATLAS UMAP reference is not automatically valid for another instrument.
Lomb–Scargle/BLS and much of the feature machinery can be reused, but survey-specific
preprocessing and recovery/classification tests are required. No other-survey
downloader or generic validated input mode is claimed in this release.
