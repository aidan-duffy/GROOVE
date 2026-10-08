# GROOVE 1.0.8: field aliases with O/C-only searches

The O/C-only default previously left field alias learning looking for absent
combined rows. This release fixes that mismatch. Universal cadence aliases and
sampling-window checks were already active; this fixes the additional local
field inventory. It does not change raw Lomb–Scargle/BLS computations or the
classification thresholds introduced in earlier releases.

## Learning options

```yaml
periods:
  series_to_run: [o, c]
  plot_series: [o, c]
  alias_learning_series: auto
```

Auto prefers a star's combined-series peaks when present in this run or its
reference tables. Otherwise it pools the first MAX_PEAKS_FOR_FIELD_LEARNING
peaks from each available O/C band. Each star counts once in a field and can
hit each candidate alias cluster only once. Duplicate source/band reference
rows are ignored, with current-run measurements preferred for that band.
The existing minimum of eight stars per field, universal-alias exclusions and
hit-fraction thresholds still apply. Not every small sample produces a field
inventory. Pooling two bands can identify aliases that occur in either band;
it is not numerically equivalent to searching combined photometry.

Explicit `o`, `c` and `combined` retain single-series learning. If an explicitly
requested series has no rows, the code prints a warning rather than silently
leaving the inventory empty. Reference source IDs are loaded as text.

## Update on Linux/WSL

Download the ZIP and updater into Windows Downloads, then:

```bash
conda activate groove-test
cd /mnt/c/Users/aidan/TFM/GROOVE
bash /mnt/c/Users/aidan/Downloads/update_GROOVE_and_push_v1.0.8.sh \
  /mnt/c/Users/aidan/Downloads/GROOVE_v1.0.8.zip
```

The updater backs up replaced source files, preserves existing configuration
and target files, installs, runs tests, then commits and pushes delivered source
files. It stops if there are already staged changes. Existing YAML overrides
are preserved: change any old `alias_learning_series: combined` to `auto` for
O/C-only learning, unless you deliberately supply combined reference tables.

## Retest the 200 selected curves in a new contained folder

These commands reuse your already cleaned/selected photometry, keep your old
results, and avoid inheriting old alias memory. Run from the repository root.
The destination must not already exist.

```bash
python - <<'PY'
from pathlib import Path
import shutil
import yaml
base = Path('testing/cleaning_test_200')
source = base / 'run.yaml'
destination = base / 'period_retest_v108'
raw = yaml.safe_load(source.read_text())
# Resolve paths using GROOVE's normal configuration loader.
from groove.config import load
old = load(source)
if not old.selected_dir.is_dir():
    raise SystemExit(f'Selected light curves not found: {old.selected_dir}')
if destination.exists():
    raise SystemExit(f'Destination already exists: {destination}; choose a new name.')
destination.mkdir()
new_results = destination.resolve() / 'results'
shutil.copytree(old.selected_dir, new_results / '2_clean' / 'selected')
raw['output_folder'] = 'results'
raw['input_folder'] = str(old.raw_lightcurves)
if old.targets is not None:
    raw['targets'] = str(old.targets)
periods = raw.setdefault('periods', {})
# Config overrides are resolved relative to this new YAML, so retain resolved
# scientific/reference settings before changing the output locations.
periods.update(old.periods)
for key in list(periods):
    if key.lower() in {'input_dir', 'output_dir', 'plot_dir', 'alias_memory_csv'}:
        del periods[key]
periods.update(series_to_run=['o', 'c'], plot_series=['o', 'c'],
               alias_learning_series='auto')
(destination / 'run.yaml').write_text(yaml.safe_dump(raw, sort_keys=False))
print(destination / 'run.yaml')
PY

groove periods -c testing/cleaning_test_200/period_retest_v108/run.yaml
```

Tables are under `period_retest_v108/results/3_periods/tables`; plots are under
`period_retest_v108/results/plots/periods`. Inspect the alias example folds,
`field_alias_inventory_current.csv` if any fields meet the learning criteria,
and `source_period_recommendations.csv`. The console warns about absent
explicit learning bands. A fresh run can legitimately have no local aliases.
The original morphology maps still refer to the original period results.
To build an independent morphology comparison for these new periods, edit the
new YAML's morphology section to `mode: fit`, remove any existing-reference
`output_root` override, then run `groove morphology -c` with the new YAML.

## Compare against the original thesis tables

If you kept the previous comparison helper:

```bash
python testing/cleaning_test_200/compare_period_results.py \
  --old-summary /mnt/c/Users/aidan/TFM/Outputs/ls_period_search/tables/ls_period_search_summary.csv \
  --old-peaks /mnt/c/Users/aidan/TFM/Outputs/ls_period_search/tables/ls_period_search_peaks.csv \
  --new-summary testing/cleaning_test_200/period_retest_v108/results/3_periods/tables/ls_period_search_summary.csv \
  --new-peaks testing/cleaning_test_200/period_retest_v108/results/3_periods/tables/ls_period_search_peaks.csv \
  --output testing/cleaning_test_200/period_retest_v108/comparison
```

Raw LS periods/powers/peaks should remain unchanged for identical inputs and
search settings. Alias-aware periods can differ because a 196-star sample and
a larger original sample supply different field context. Review labels also
include the intentional earlier dominance-rule change. This fix alone does
not guarantee every previously different recommendation becomes identical.

For a controlled original-context comparison, use a second fresh output folder
and add to its existing periods section:

```yaml
  alias_learning_series: combined
  reference_summary_csvs:
    - /mnt/c/Users/aidan/TFM/Outputs/ls_period_search/tables/ls_period_search_summary.csv
```

This learns from the original combined rows without performing a combined
search or saving combined plots. It requires the original summary to contain
combined rows and coordinates. Matching historical decisions may also require
the original saved alias memory and identical scientific settings. Keep any
original memory as a copied input: do not let validation overwrite it. Compare
tables before claiming thesis parity; real-data results cannot be rerun here
without your selected photometry and original reference tables.
