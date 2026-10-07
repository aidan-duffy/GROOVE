# Configuration options: where to start

Generate a commented starting file with `groove init configs/my_sample.yaml`.
Every command's -c/--config argument chooses this YAML. File paths are relative
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
[plot selection](release_1_0_5.md), [map controls](map_controls.md), and
[data workflows](data_workflows.md) explain effects and worked examples.
