# Identify samples and compare light curves

Colours always describe morphology. Optional shapes describe datasets. Dataset
names match the top-level `name` in each sample's run.yaml, and the `dataset`
column in the shared saved catalogue; they are not folder or batch names.

```yaml
morphology:
  dataset_markers:
    cleaning_test_200: circle
    synthetic_extended: diamond
  outline_new_sources: true
```

Leave dataset_markers empty (`{}`), or omit it, for all circles. Unlisted datasets
also use circles. Shapes: circle, square, diamond, triangle-up, triangle-down,
cross, x, star, hexagon. Static maps include a dataset legend. Interactive maps
group their legend by dataset when shapes are configured: click a legend item
to toggle that dataset group. Dataset names are also shown on hover. Black
outlines mark the most recently added batch, not every non-reference sample.
Shapes remain associated with the dataset when later batches are added.

## Apply styling after sources have already been added

Edit the configuration that points to the shared morphology output_root and
model_version. Then run:

```bash
groove morphology -c configs/sample_two.yaml -- --mode map-only
```

For the contained test from the walkthrough:

```bash
groove morphology -c testing/cleaning_test_200/demo_transform.yaml -- --mode map-only
```

This reads saved coordinates and redraws PNG/PDF/HTML overview maps. It does not
fit/transform UMAP, extract features, relabel stars, change periods, or write the
scientific catalogue/models. It also updates the interactive comparison panel.
Open the shared reference's plots/ML/<version>/maps directory, and refresh or
reopen the newly generated HTML. Running transform again skips existing sources
and is not the way to update plot styling. `plot-only` is a different mode: it
rebuilds phase/source/category plots, not the overview maps.

## Zoom and navigate

Drag a rectangle or use the mouse wheel over the map to zoom. The always-visible
toolbar also offers zoom in/out, pan, reset, and lasso/box selection. Double-click
to reset the axes. Zoom only changes the view; it never changes UMAP coordinates
or classifications. Switch back to zoom in the toolbar after using selection.

## Compare several sources

In an interactive HTML map, click multiple points to keep their phase-plot
previews below the map. Cards are capped at 420 pixels wide, with a 320-pixel image area; they
wrap into additional rows and shrink to fit narrow screens. A single selection
does not expand across the page. Repeated clicks do not duplicate a source. Use the lasso or box selection
tool to add several points at once. Each preview has a Remove button; Clear
selection empties the panel. Click a preview image to open the full-size PNG.
Selection is local to that browser page and does not change your data or labels.

The HTML includes Plotly and can be used offline. Phase images are relative file
links, so keep the HTML under maps/ alongside its surrounding ML run folders.
A missing image gives a visible unavailable-preview message.

## Highlight one source

```bash
groove morphology -c configs/sample_two.yaml -- \
  --mode highlight-source --source-id YOUR_GAIA_ID --label My_star --map combined
```

An additional *_highlighted map marks the saved position with a large gold star
and black outline. This does not fit a new embedding. Available --map names are
shown by `groove morphology -c configs/sample_two.yaml -- --help`.
