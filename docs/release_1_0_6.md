# GROOVE 1.0.6: identify datasets and compare light curves

This release adds optional dataset shapes to static and interactive overview
maps, stronger latest-batch outlines, grouped interactive dataset legends, and
map-only redraws of saved coordinates. Clicking several points or using lasso/
box selection keeps phase-image previews side by side below an interactive map.
Previews can be removed individually or cleared. Shapes default to all circles.
O/C-only period analysis and three-map defaults from 1.0.5 are retained.

README's Find your workflow section links to stage-by-stage commands, existing
photometry and skipping completed stages, frozen-map updates, highlights,
configuration defaults, and the adaptations/validation required for other surveys.
No new other-survey compatibility is claimed.

## Update locally and on GitHub (WSL)

Save the archive and updater in Windows Downloads. Then:

```bash
conda activate groove-test
cd /mnt/c/Users/aidan/TFM/GROOVE
bash /mnt/c/Users/aidan/Downloads/update_GROOVE_and_push_v1.0.6.sh \
  /mnt/c/Users/aidan/Downloads/GROOVE_v1.0.6.zip
```

The updater preserves existing configurations/results, backs up overwritten
source, installs, checks dependencies/tests, stages delivered files only, commits
and pushes the current branch. If it stops for already staged changes, inspect
`git diff --cached --stat`; `git restore --staged .` unstages without deleting edits.

## Apply to the existing 200 + demo test

Edit testing/cleaning_test_200/demo_transform.yaml. Keep its existing output_root,
model_version and morphology feature settings. Add under its morphology section:

```yaml
  dataset_markers:
    cleaning_test_200: circle
    synthetic_extended: diamond
  outline_new_sources: true
```

Names must match the saved dataset names; map-only prints these names and counts.
Then:

```bash
groove morphology -c testing/cleaning_test_200/demo_transform.yaml -- --mode map-only
```

Reopen shared reference maps under testing/cleaning_test_200/results/plots/ML/.
This does not rerun period searches, classification or UMAP. The existing saved
catalogue, coordinates and models remain unchanged. All regenerated interactive
maps include the comparison panel. Keep their source_plots folders with them.
