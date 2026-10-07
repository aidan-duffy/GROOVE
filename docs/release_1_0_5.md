# GROOVE 1.0.5: fewer default plots and O/C-only period searches

New demo runs and configurations that do not override these settings search O
and C separately. Combined photometry is neither searched nor saved as a separate
period plot by default. Both bands are still downloaded, cleaned and used by
morphology feature extraction. Morphology consensus profiles can use information
from both bands; these are not an additional combined-photometry period search.

The three default overview maps are classification evidence, overall light-curve
similarity, and periodic shape. The optional transient/evolution overview is not
saved by default. Internal representations are still computed and saved because
neighbour diagnostics and frozen-model workflows depend on them. Thus this map
change reduces exported outputs, not the number of internal UMAP fits.
Classification evidence is a UMAP of the rule scores, not an independent accuracy
validation. Colours in the three feature-based maps do not determine positions.

## Configuration

```yaml
periods:
  series_to_run: [o, c]
  plot_series: [o, c]
morphology:
  maps_to_plot: [classification_evidence, combined, periodic]
```

To enable combined photometry analysis and plots:

```yaml
periods:
  series_to_run: [o, c, combined]
  plot_series: [o, c, combined]
```

To analyse all three but save only separate-band plots, add combined only to
series_to_run. A plotted series must also have been analysed. plot_mode: none
turns off all period-stage plotting. plot_series: [] disables individual-series
plots but allows the master review overview. Extra alias/harmonic folds respect
plot_series too.

For two overview maps, use maps_to_plot: [classification_evidence, combined].
To restore all four, add transient. In morphology, combined means combining
periodic and transient feature sets, not the O/C period-search series.
PNG/PDF behaviour otherwise remains as in 1.0.4; this release does not introduce
a universal output-format switch.

## Updating and rerunning

Run the supplied updater inside the Git checkout with your GROOVE environment
active. It backs up overwritten source, preserves existing configuration files,
installs the update, runs tests, commits only delivered files, and pushes your
current branch to origin. It does not rerun real downloads or overwrite results.

```bash
conda activate groove-test
cd /mnt/c/Users/aidan/TFM/GROOVE
bash /mnt/c/Users/aidan/Downloads/update_GROOVE_and_push_v1.0.5.sh \
  /mnt/c/Users/aidan/Downloads/GROOVE_v1.0.5.zip
```

If your existing run.yaml explicitly requests combined, edit the two period
lists above; the updater intentionally preserves your YAML overrides. Use a
new output folder/model version when comparing O/C-only with earlier runs.
Existing results are not scientifically interchangeable: removing combined
photometry can change significance, adopted periods and morphology labels.

```bash
groove demo demo_105 --extended
groove run -c demo_105/run.yaml --skip-download
groove demo-check demo_105
```

Open results/plots/ML/extended_demo/maps inside demo_105. It should contain
three all_families_*_interactive.html overview maps, with PNG/PDF variants.
Representative example panels and source plots are separate review products.
On regeneration of the same saved run, deselected overview map variants are
removed so obsolete fourth maps do not remain visible.
