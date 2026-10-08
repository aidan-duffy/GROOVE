# GROOVE 1.0.7: bounded comparison previews and map zoom

Comparison cards now have a maximum width of 420 pixels and a 320-pixel image
area with contain scaling. They fit narrow screens and wrap into additional
rows. A single selected image no longer expands across the page. Clicking a
preview still opens the full-resolution image.

Map zoom is explicitly enabled: drag a rectangle or use the mouse wheel over
the map; double-click to reset. The visible toolbar offers zoom, pan, reset and
selection tools. Zoom changes only the display, not coordinates or scientific
results. Click/lasso multi-source previews, remove/clear and dataset shapes remain.

Save GROOVE_v1.0.7.zip and update_GROOVE_and_push_v1.0.7.sh in Windows Downloads:

```bash
conda activate groove-test
cd /mnt/c/Users/aidan/TFM/GROOVE
bash /mnt/c/Users/aidan/Downloads/update_GROOVE_and_push_v1.0.7.sh \
  /mnt/c/Users/aidan/Downloads/GROOVE_v1.0.7.zip
```

Then regenerate the shared maps (no refit):

```bash
groove morphology -c testing/cleaning_test_200/demo_transform.yaml -- --mode map-only
```

Reopen or refresh the regenerated HTML in the shared reference's plots/ML folder.
Already-generated HTML keeps its old controls until it is regenerated.
