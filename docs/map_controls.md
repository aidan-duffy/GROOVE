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
reset and lasso/box selection. Click a legend entry to hide or show its group; double-click a legend entry
to isolate that group or restore the others. Double-click inside the map resets
the axes. Zoom changes only
the view. Switch back to zoom in the toolbar after selecting points.

## Compare several sources

Click multiple points to keep phase-image previews below an interactive map.
Cards are capped at 420 pixels wide with a 320-pixel image area; they wrap into
rows and fit narrow screens. A single selection does not expand across the page.
Click the same point again to remove its preview; click once more to add it
back. Lasso or box selection adds several points without removing existing
previews. Use Remove on an individual card or Clear selection for all.
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

## Export one source in one band

To export one source in the morphology style with only O-band observations,
run this from the repository root after its morphology stage has completed:

```bash
python tools/plot_source_fold.py -c run.yaml --source-id YOUR_GAIA_DR3_ID --band o
```

The separate PNG is written to `<output_folder>/plots/individual/`. It retains
the saved morphology period and the phase origin of the complete accepted
source. Only the displayed bands change; ML features, labels, saved maps and
the usual two-band phase images are untouched. One band is shown in its
original magnitude scale, rather than relative to a band median. Use `--band c`
or `--band both` for other displays, or `--output path/to/fold.pdf` for PDF.
Chronological Q1--Q4 groups are calculated from the displayed observations.
The YAML is the original pipeline config, not the resolved morphology-only
configuration. Use `--catalogue path/to/all_sources.csv` to select a saved
morphology catalogue explicitly if necessary.
Use `--point-size 2.5 --point-alpha 0.8` to change this export's marker diameter
and opacity only. Without these overrides it uses the morphology marker
settings in the YAML.

## Redraw phase folds without a periodogram

Morphology writes standalone phase folds to
`results/plots/ML/<model_version>/source_plots/phase_folded/` for the default
output layout. Their recommended periods come from the saved catalogue;
LS/BLS periodograms are separate products of the period stage.

After updating GROOVE, regenerate those images from the original configuration
and accepted light curves, then rebuild the HTML controls:

```bash
groove morphology -c run.yaml -- --mode plot-only --overwrite
groove morphology -c run.yaml -- --mode map-only
```

Use the same `morphology.model_version` as the existing saved run (or pass
`--model-version YOUR_SAVED_RUN` after `--` in both commands). Plot-only needs
the configured light curves and saved catalogue. These commands retain saved
periods, labels, models and UMAP coordinates; they do not run a period search.
The phase images are PNGs. Single-source classification also creates phase
folds without fitting UMAP: use `groove morphology -c run.yaml -- --mode classify`
after cleaning, selection and period searching (see [stages](stages.md)).

Double-phase plots span 0--2: phases 0.5--1.5 retain the chronological colours,
while the repeated observations and binned-median curves outside that interval
are grey. This also applies to period-stage folds, including alias/harmonic
panels. Single-cycle period plots keep their colours across 0--1. The display
change does not alter the folding origin, period or photometry.
