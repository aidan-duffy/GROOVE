# Linux and WSL validation guide

This Bash guide checks GROOVE 1.1.1 from a source checkout. The commands work on
Linux and WSL; they do not depend on a particular username or Windows drive.
Run public stages through `groove` or `python -m groove`. Internal Python files
are modules, exercised through the test suite rather than run individually.

## Install and record the environment

For a new checkout:

```bash
git clone https://github.com/aidan-duffy/GROOVE.git
cd GROOVE
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
```

For an existing checkout, first enter its directory and activate its environment.
`cd /path/to/GROOVE` is an example path: replace it with the actual location.
Conda users can instead run `conda env create -f environment.yml` from the
repository root, then `conda activate groove` and install the development extra.

```bash
python -m pip check
groove --version
python -m pytest -q
python -m build
git rev-parse HEAD
git status --short
```

The expected package version is `groove 1.1.1`. Consult [validation evidence](validation.md)
for recorded test results; the test command above reports the actual result for
this checkout and environment. Do not interpret a successful build as a successful
live ATLAS download. Download tests simulate the service. Seeded UMAP can warn
that it uses one worker to preserve reproducibility.

Create an isolated output tree and record dependencies:

```bash
validation_root="$PWD/results/validation_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$validation_root"
python -m pip freeze > "$validation_root/environment.txt"
```

Keep this variable set for the remaining commands. All generated data and
reports in this guide stay under that ignored `results/` tree.

## Run the standard demonstration

```bash
groove demo "$validation_root/demo"
groove run -c "$validation_root/demo/run.yaml" --skip-download
groove demo-check "$validation_root/demo"
python tools/audit_outputs.py "$validation_root/demo"
```

The 12 artificial sources contain four wavelike, four dipping and four constant
signals. The audit checks all eight injected periodic signals within 0.1%, the
expected morphology families, controlled cleaning boundaries and a separate BLS
injection. `cut_audit.csv` and `output_audit.json` are written beside the demo,
inside `validation_root`. Numerical periods for quiet sources are not evidence
of a periodic detection.

## Run the extended demonstration stage by stage

```bash
groove demo "$validation_root/extended" --extended
groove clean -c "$validation_root/extended/run.yaml"
groove select -c "$validation_root/extended/run.yaml"
groove periods -c "$validation_root/extended/run.yaml" --n-jobs 2
groove morphology -c "$validation_root/extended/run.yaml"
groove demo-check "$validation_root/extended"
```

Read the generated `CASE_GUIDE.md`, `truth.csv`, `demo_check.json` and
`demo_source_review.csv`. The 24 artificial sources include daily-systematic,
nightly-sampling, unequal-eclipse, flare, irregular, evolving, noisy, single-band,
isolated-dip and double-dip cases. Injected behaviours are not forced labels.
The `alias_promoted` source has a stronger daily peak and a rank-two stellar
peak near 8.3 days; extra folds expose the replacement. The weaker-secondary
example remains flagged. Harmonic diagnostics compare P/2, P and 2P.

The extended configuration enables BLS with demo-specific limits of 2–30 days,
durations 0.2/0.4 days and three samples per peak; LS searches 0.5–120 days.
The standard demo disables BLS for speed. Neither configuration changes the
package's default `run_bls: true`. Use `demo-check`, rather than the fixed
12-source audit helper, for the extended sample.

## Inspect the outputs

All paths below are relative to `$validation_root/extended/results`.

| Product | Location |
|---|---|
| Cleaning and selection reports | `2_clean/lightcurves/` |
| Selected light curves | `2_clean/selected/` |
| Period recommendations and candidate peaks | `3_periods/tables/` |
| Cleaning figures | `plots/clean/` |
| Period figures | `plots/periods/<series>/best_per_star/` and primary review folders |
| Alias/harmonic extra folds | `plots/periods/<series>/{alias,harmonic}/extra_phase_folds/` |
| Morphology tables | `4_morphology/saved_runs/extended_demo/tables/` |
| Fitted models and caches | `4_morphology/saved_runs/extended_demo/{models,cache}/` |
| Source phase images | `plots/ML/extended_demo/source_plots/phase_folded/` |
| Interactive and static maps | `plots/ML/extended_demo/maps/` |
| Primary families and contact sheets | `plots/ML/extended_demo/{category_folds,appendix}/` |

Inspect `extra_phase_fold_diagnostics.csv` for trigger reasons, periods, status
and image paths. Check tables for failed/skipped rows and nonempty `plot_error`
values. A full completed run writes `pipeline_run.json` with all requested stages.

For WSL, open the results in Explorer:

```bash
explorer.exe "$(wslpath -w "$validation_root/extended/results")"
```

On desktop Linux, use `xdg-open "$validation_root/extended/results"` when
available. Inspect PNG labels and clipping. Open `*interactive.html` maps in a
browser and test hover, zoom and multi-selection. Keep the surrounding ML tree
with the HTML: phase previews are relative image links. Automated integrity
checks do not replace visual or browser testing.

## Check saved-model operations and another sample

```bash
groove morphology -c "$validation_root/extended/run.yaml" -- --mode map-only
groove morphology -c "$validation_root/extended/run.yaml" -- --mode plot-only
groove morphology -c "$validation_root/extended/run.yaml" -- \
  --mode highlight-source --source-id 9900000000000000019 \
  --label cyan_demo --diagnostic-folds
```

`map-only` redraws overview maps; `plot-only` rebuilds source/category figures.
Neither changes saved classifications, periods or map coordinates. Additional
modes are listed in [stage contracts](stages.md#morphology).

For a complete second-sample projection with distinct artificial IDs, follow
[the map-controls example](map_controls.md#complete-two-sample-example).
For manual review, edit the output-root `manual_labels.csv` using the columns
in [the template](../data/manual_labels_template.csv), then run `--mode relabel`.
Back up the label file before experimenting; rerun relabel after restoring it.

## Generate a one-source real-data configuration

The following creates new files under the isolated output tree. It does not
read or overwrite any existing `configs/real_test.yaml`, target lists or data.

```bash
mkdir -p "$validation_root/real"
cat > "$validation_root/real/targets.csv" <<'CSV'
GaiaDR3,RAdeg,DEdeg,group
YOUR_REAL_SOURCE_ID,YOUR_RA_DEGREES,YOUR_DEC_DEGREES,validation
CSV
cat > "$validation_root/real/run.yaml" <<'YAML'
name: real_validation
output_folder: results
targets: targets.csv
years: full
photometry: reduced
download:
  limit_targets: 1
clean:
  rescue_enable: false
  n_example_plots: 3
periods:
  max_period_days: 200
  run_bls: true
  plot_time_segments: 4
morphology:
  mode: classify
  use_c_band: true
  use_o_band: true
  n_jobs: 1
YAML
```

Edit `"$validation_root/real/targets.csv"` in a text editor. Replace every
placeholder with one real source ID and valid decimal-degree coordinates.
Preserve long IDs as text. Choose a source with known ATLAS coverage and record
its expected behaviour before inspecting the result. Never submit synthetic IDs.

```bash
groove targets "$validation_root/real/targets.csv"
groove download -c "$validation_root/real/run.yaml" --dry-run
```

The dry run validates coordinates and lists the selected source without requests
or output writes. Invalid placeholders must be replaced before proceeding.

## Download, audit and analyse the real source

Obtain your token from your [ATLAS account](https://fallingstar-data.com/forcedphot/).
Enter it privately in the same terminal:

```bash
read -r -s -p 'ATLAS token: ' ATLAS_TOKEN
printf '\n'
export ATLAS_TOKEN
groove download -c "$validation_root/real/run.yaml"
python tools/audit_downloads.py "$validation_root/real/run.yaml"
python tools/audit_downloads.py "$validation_root/real/run.yaml" --compare-api
groove download -c "$validation_root/real/run.yaml"
```

The repeated download should reuse completed compatible work. The optional API
comparison reads the saved result URL without submitting a new job; that URL
must still be available. A `no_data` response can be valid but does not validate
a successful photometry download. Inspect the progress CSV and reported errors.

Raw files are under `real/results/1_raw/atlas_full_reduced/all_lightcurves/`
within the validation tree. Run the remaining stages:

```bash
groove clean -c "$validation_root/real/run.yaml"
groove select -c "$validation_root/real/run.yaml"
groove periods -c "$validation_root/real/run.yaml"
groove morphology -c "$validation_root/real/run.yaml"
unset ATLAS_TOKEN
```

Check raw count = retained + removed, rejection reasons, epochs, period flags
and morphology's adopted period. Selection requires 100 points, 30 in a band
with median magnitude error <=0.2, a 365-day baseline and <=50% removed.
Classification-only tables are under `4_morphology/classification/tables/`;
figures are under `plots/ML/classification/`. A source failing usability cuts
may legitimately produce no downstream result; inspect the reasons first.

For a larger sample, remove `download.limit_targets: 1` and add valid target rows.
At least five usable morphology sources are needed for `mode: fit` and a map.
For existing raw photometry, use [the existing-data workflow](data_workflows.md#existing-raw-atlas-photometry-skip-downloading).

## Resume and optional original-script comparison

Repeat the same full or individual-stage command to resume. A completed
compatible run should skip saved work. Use `--rerun` only for deliberate
recalculation and `--strict` to expose caught errors. See [restart limits](restarts.md).
Do not interrupt the initial ATLAS submission POST for a test; ambiguous
submissions need queue reconciliation as described in [downloads](stages.md#downloads).

If the original research scripts are available locally, the standard-demo helper
can compare them using the filenames specified in `tools/audit_outputs.py`:

```bash
python tools/audit_outputs.py "$validation_root/demo" \
  --originals /path/to/original_science_scripts
```

That directory is an example path and is not bundled. The comparison executes
those scripts; use trusted scientific copies without credentials. Match inputs,
filters, rescue settings and parameters before drawing parity conclusions.
Retain evidence and limitations with published analyses. Synthetic checks do
not measure real-catalogue completeness, purity or universal accuracy.
