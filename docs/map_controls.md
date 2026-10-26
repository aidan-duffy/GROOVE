# Identify samples and compare light curves

Colours describe morphology. Optional shapes identify datasets using each
configuration's top-level `name`, also stored in the saved catalogue's `dataset`
column. They do not use folder names or `batch_id`.

```yaml
morphology:
  dataset_markers:
    reference_sample: circle
    new_sample: diamond
  outline_new_sources: true
```

Merge these keys into the existing `morphology` section. Omit `dataset_markers`
or set it to `{}` for identical circles. Unlisted datasets also use circles.
Supported shapes are circle, square, diamond, triangle-up, triangle-down, cross,
x, star and hexagon. Static maps include a dataset legend. Interactive legends
group traces by dataset when shapes are configured; click a legend item to
toggle that group. Hover details also identify the dataset. Black outlines mark
the latest transform batch. Shapes persist when further batches are added.

## Complete two-sample example

Run these Bash commands from the installed repository root. They generate two
artificial samples inside a fresh ignored output tree; no ATLAS token is needed.
The second sample deliberately has new IDs but the same seeded signal shapes,
so this demonstrates projection mechanics rather than an independent population.

```bash
map_root="$PWD/results/map_example_$(date +%Y%m%d_%H%M%S)"
groove demo "$map_root/reference"
groove demo "$map_root/batch"
python - "$map_root" <<'PY'
from pathlib import Path
import sys
import yaml

root = Path(sys.argv[1]).resolve()
ref_path = root / 'reference/run.yaml'
ref = yaml.safe_load(ref_path.read_text())
ref['name'] = 'reference_sample'
ref['morphology']['model_version'] = 'reference_v1'
ref_path.write_text(yaml.safe_dump(ref, sort_keys=False))

batch = root / 'batch'
truth_path = batch / 'truth.csv'
truth = truth_path.read_text()
for path in sorted((batch / 'raw').glob('*.csv')):
    old = path.stem.split('GaiaDR3_')[1]
    new = str(int(old) + 10000)
    path.with_name(path.name.replace(old, new)).write_text(
        path.read_text().replace(old, new))
    path.unlink()
    truth = truth.replace(old, new)
truth_path.write_text(truth)

cfg_path = batch / 'run.yaml'
cfg = yaml.safe_load(cfg_path.read_text())
cfg['name'] = 'new_sample'
cfg['morphology'].update(
    mode='transform', model_version='reference_v1',
    output_root=str(root / 'reference/results/4_morphology'),
    dataset_markers={'reference_sample': 'circle', 'new_sample': 'diamond'},
    outline_new_sources=True)
cfg_path.write_text(yaml.safe_dump(cfg, sort_keys=False))
PY
groove run -c "$map_root/reference/run.yaml" --skip-download
cp "$map_root/reference/results/4_morphology/saved_runs/reference_v1/tables/reference_sources.csv" \
   "$map_root/reference_before_transform.csv"
groove run -c "$map_root/batch/run.yaml" --skip-download
```

The new batch's cleaning, selection and periods are under `batch/results/`.
Shared morphology tables remain under
`reference/results/4_morphology/saved_runs/reference_v1/tables/`.
Open `reference/results/plots/ML/reference_v1/maps/*interactive.html` beneath
`map_root`: circles identify the reference and outlined diamonds the new sample.
The original coordinates must stay fixed. Check them explicitly:

```bash
python - "$map_root" <<'PY'
from pathlib import Path
import sys
import pandas as pd

root = Path(sys.argv[1])
before = pd.read_csv(root / 'reference_before_transform.csv', dtype={'source_id': str})
after = pd.read_csv(root / 'reference/results/4_morphology/saved_runs/reference_v1/tables/all_sources.csv',
                    dtype={'source_id': str})
cols = [c for c in before if c.endswith(('_umap_1', '_umap_2'))]
old = before.set_index('source_id')[cols].sort_index()
new = after.set_index('source_id').loc[old.index, cols].sort_index()
pd.testing.assert_frame_equal(old, new)
print(after['dataset'].value_counts().to_string())
print('Reference coordinates preserved.')
PY
```

For real samples, use their existing configurations and raw data instead of
`groove demo`. Keep new-source IDs distinct and use the reference's frozen
feature settings. At least five usable sources are required for the initial
fit; transform skips existing IDs by default. See [data workflows](data_workflows.md#add-another-sample-to-a-frozen-map).

## Apply styling after sources have already been added

Edit the configuration that points to the shared morphology `output_root` and
`model_version`. After the complete example above, run:

```bash
groove morphology -c "$map_root/batch/run.yaml" -- --mode map-only
```

This redraws saved PNG/PDF/HTML overview maps without fitting or transforming
UMAP, extracting features, relabelling stars or changing periods/catalogues.
Refresh the newly generated HTML in the reference's ML figure directory.
`transform` normally skips existing sources; use `map-only` for style changes.
`plot-only` rebuilds phase/source/category products and their output manifests,
while preserving classifications, periods, coordinates and overview maps.

## Zoom and navigate

Drag a rectangle or use the mouse wheel to zoom. The toolbar offers zoom, pan,
reset and lasso/box selection. Double-click resets the axes. Zoom changes only
the view. Switch back to zoom in the toolbar after selecting points.

## Compare several sources

Click multiple points to keep phase-image previews below an interactive map.
Cards are capped at 420 pixels wide with a 320-pixel image area; they wrap into
rows and fit narrow screens. A single selection does not expand across the page.
Repeated clicks do not duplicate a source. Lasso or box selection adds several
points at once. Use Remove on an individual card or Clear selection for all.
Click a preview to open its full-size PNG. Selection is local to the page.

Plotly is embedded for offline use. Images use relative links: preserve the
surrounding ML run tree when moving the HTML. Missing images display an
unavailable-preview message. Browser checks remain necessary for local layout.

## Highlight one source

After the example above:

```bash
groove morphology -c "$map_root/batch/run.yaml" -- \
  --mode highlight-source --source-id 9900000000000000000 \
  --label Example_source --map combined
```

An additional highlighted map marks the saved position with a gold star and
black outline; it does not fit a new embedding. Use an actual saved source ID
for your own data. Inspect options with:

```bash
groove morphology -c "$map_root/batch/run.yaml" -- --help
```
