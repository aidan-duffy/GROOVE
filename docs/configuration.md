# Configuration options: where to start

Generate a commented starting file with `groove init configs/my_sample.yaml`.
Analysis commands use -c/--config to choose this YAML. File paths are relative
to the YAML file, not the terminal's current directory. Keep stage overrides in
one section each; duplicate YAML sections can silently replace earlier settings.

## Common options

| Section/key | Default or purpose |
|---|---|
| name | Dataset name recorded in tables and map hover; use this name for shapes |
| targets | ID/RA/Dec CSV for download; optional when analysing existing data |
| input_folder | Existing raw per-source photometry directory; skips no stages by itself |
| output_folder | Root containing this sample's numbered stage outputs and plots |
| years | full by default; download baseline, not a command to extend existing observations |
| clean.rescue_enable | false; opt-in rescue of dimming measurements failing only soft cuts |
| clean.make_summary_plots | true; aggregate six-panel review |
| clean.make_reason_plot | true; rejection-reason plot when available |
| clean.make_example_plots | true; individual before/after examples |
| clean.n_example_plots | Limit on saved examples; does not limit cleaning |
| clean.example_selection | highest_removed_fraction, lowest_removed_fraction, or first |
| clean.save_png / save_pdf | true / true; independent cleaning output-format switches |
| select.min_points | 100 |
| select.min_points_per_band | 30 in at least one usable band |
| select.min_baseline_days | 365 |
| select.max_removed_fraction | 0.5 |
| select.max_median_uncertainty_mag | 0.2 |
| periods.series_to_run | [o, c]; add combined to analyse combined photometry |
| periods.plot_series | [o, c]; selects saved series, including alias/harmonic extras |
| periods.alias_learning_series | auto; use each star's combined peaks if available, otherwise pool O/C peaks, counting the star once |
| periods.reference_summary_csvs | []; optional existing full-sample period summaries for field alias learning |
| periods.plot_mode | all or none |
| periods.extra_fold_series_mode | recommended or all; automatic suspects can also get diagnostics, within plot_series |
| morphology.mode | fit, transform, refit, classify, relabel, plot-only, map-only, highlight-source, umap-families |
| morphology.output_root | This run's 4_morphology; set the reference's root for transform |
| morphology.model_version | Reference identifier; omitted uses the current reference or default run |
| morphology.batch_id | Batch label; optional |
| morphology.existing_id_policy | skip by default when transforming |
| morphology.maps_to_plot | [classification_evidence, combined, periodic]; transient optional |
| morphology.dataset_markers | {}; map dataset names to supported shapes, otherwise circles |
| morphology.outline_new_sources | true to outline latest batch; map-only can apply it retrospectively |

## Detailed settings

The table covers common user choices. Full stage defaults and threshold comments
are available in these authoritative files:

- [Download](../src/groove/download/settings.py)
- [Cleaning](../src/groove/clean/settings.py)
- [Source selection](../src/groove/select/settings.py)
- [Period search](../src/groove/periods/settings.py)
- [Morphology commented YAML](../src/groove/morphology/defaults.yaml)

For settings-based stages, supported uppercase settings become lowercase YAML
keys under their stage, e.g. N_EXAMPLE_PLOTS becomes clean.n_example_plots.
Morphology options use their existing lowercase YAML names. Derived paths are
normally supplied by the pipeline; prefer top-level input_folder/output_folder.
Scientific cut and rule thresholds require sample-specific validation.

[Stage details](stages.md), [morphology details](morphology_details.md),
[plot selection](configuration.md#plot-and-filter-selection), [map controls](map_controls.md), and
[data workflows](data_workflows.md) explain effects and worked examples.

## Restart controls

Resume is automatic for the full pipeline and individual stages. `--rerun`
forces recalculation for the requested command; it is a CLI flag, not a YAML
key. Source journals supplement the period full-table checkpoint interval.
See [restart behaviour](restarts.md) for scope, plotting and migration details.

## Plot and filter selection

Period analysis and saved plots are independent choices:

```yaml
periods:
  series_to_run: [o, c]
  plot_series: [o, c]
morphology:
  maps_to_plot: [classification_evidence, combined, periodic]
```

Add `combined` to `series_to_run` to analyse combined photometry. Add it to
`plot_series` only if you also want its period figures. Every plotted series
must have been analysed. For original-style combined field alias learning:

```yaml
periods:
  series_to_run: [combined, o, c]
  plot_series: [o, c]
  alias_learning_series: combined
```

Removing combined analysis can change alias inventories, recommended periods
and downstream morphology. Removing only combined plots preserves its analysis.
The default `auto` field learner pools O/C peaks when combined is unavailable;
that is not equivalent to learning from combined peaks alone.

`plot_mode: none` disables all period-stage plotting. `plot_series: []` disables
individual-series plots while allowing the master review overview. Automatic
alias/harmonic figures respect `plot_series`.

Morphology's `combined` map combines periodic and transient feature families;
it does not refer to combined O/C photometry. Add `transient` to `maps_to_plot`
for that optional overview, or use `[classification_evidence, combined]` for two
maps. Internal representations remain available for saved-model and neighbour
operations; selecting fewer maps reduces exported figures rather than all fits.
Classification evidence maps embed rule scores and do not independently validate
classification accuracy. Dataset shapes and zoom are covered in
[map controls](map_controls.md). Existing HTML needs regeneration to gain new
controls.

Cleaning supports independent `save_png` and `save_pdf` settings. Output-format
options differ by stage; there is no universal format switch. See the stage
settings linked above for supported plotting options.
