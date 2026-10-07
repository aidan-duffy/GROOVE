# Morphology and reference maps

Morphology measurements and rule-based suggestions are separate from UMAP.
Fitting an embedding does not change the classifications; the fitting workflow
checks this explicitly. Coordinates describe a feature neighbourhood, not a
physical parameter or a probability of a source being exotic.

## Inputs and periods

The pipeline passes its selected light curves and source-level period table
into morphology. The adopted period comes from `recommended_period_days`.
The per-series search table supplies diagnostics and cannot replace a
source-level recommendation. The default does not perform a fallback period
search when a recommendation is missing.

Both `c` and `o` are enabled by default. Set `use_c_band` or `use_o_band` to false
under `morphology` to restrict the analysis. At least 50 usable observations
are required by default. The magnitude-based feature loader requires finite
magnitudes and, when measured flux exists, positive measured flux. Consequently,
cleaning retention and morphology retention are different quantities. Review
`load_problems` and processing-failure tables when sources are absent.

## Measurements

The code measures phase profiles at the adopted period and diagnostic half/double
periods. The defaults use 64 phase bins and four chronological sections. A
robustly scaled, aligned 32-bin profile contributes to the UMAP representation;
the original measurement profile remains available for morphology rules.
Fourier shape, symmetry, dip localisation, phase coverage, scatter, filter
agreement, event structure, and temporal coherence contribute complementary
information. Absolute amplitude receives relatively low weight in the map.

Flare rules examine grouped events, independent nights, multi-point support,
cross-filter evidence and leave-one-event-out persistence. A few isolated
bright outliers should therefore not alone establish a flaring morphology.
Dimming rules use shape, localisation and coherence rather than calling every
sinusoid with a minimum a transit.

Nested `thresholds` overrides merge with the defaults. For example, changing
`flare_min_events` leaves the other configured thresholds intact. The complete
options live in `defaults.yaml`; source code supplies additional internal rule
settings. These choices need validation on labelled observations before their
scientific performance can be claimed for a new population.

## Labels

| Primary suggestion | Interpretation |
|---|---|
| `transit` | Localised dimming/occultation morphology |
| `wavelike` | Broad coherent modulation |
| `flaring` | Supported brightening events |
| `irregular_variable` | Time-variable structure without a clean persistent shape |
| `nonvar` | Little supported variability relative to the data quality |
| `noisy` | Scatter with insufficient coherent/event evidence |
| `unknown` | Insufficient or unresolved morphology evidence |

Scientific interest is recorded separately: `routine`, `review`,
`exotic_candidate` or `manually_confirmed_exotic`. An exotic candidate is a
review target, not a confirmed physical class. Period alias/harmonic warnings,
filter disagreements, evolution and confidence remain visible in the tables.

Manual labels take precedence. Edit the automatically created
`manual_labels.csv` under the morphology output root. Use source IDs as text,
with `dataset` matching the run's `name`, and use the columns in the supplied
manual-label template. For a fitted model, rerun in `relabel` mode. For
classification-only results, rerun `classify`.

## Fit, transform and small samples

`fit` needs at least five usable sources and freezes imputation, scaling,
feature weighting, optional PCA and UMAP. It writes combined, periodic,
transient and classification-evidence representations. The evidence map uses
continuous category scores and should be interpreted separately from the
unsupervised shape maps.

Later batches use `transform` with the same morphology `output_root` and model
version. A configuration/schema mismatch raises an error; create a new reference
with `refit` when representation choices change. Existing IDs are skipped by
default. Reference-source changes require a refit because those sources helped
fit the model. A completed reference is protected against accidental rebuilding;
`--overwrite` explicitly rebuilds it, while a new `model_version` keeps both.

`classify` uses the feature and rule workflow without fitting any map. It works
for one star or larger samples and does not create a reference pointer that
could be mistaken for a fitted model.

## Outputs and review

| Product | Location within a fitted model version |
|---|---|
| Full feature/label catalogue | `tables/all_sources.csv` |
| Review targets | `tables/review_queue.csv` |
| Interactive maps | `maps/*interactive.html` |
| Compact source phase plots | `source_plots/phase_folded/` |
| Primary morphology folders | `category_folds/primary/` |
| Fitted representations and configuration | `models/` |
| Feature checkpoints | `cache/` |

Classification-only outputs use the same table/plot names beneath
`classification/`, without fitted model files. Keep the complete output tree
when moving interactive maps. Source plots use the accepted filters and the
saved adopted period. The detailed periodograms remain in the period-stage
output folder.

Seeded runs are reproducible within a fixed dependency environment. Seeds
alone do not guarantee identical coordinates across library versions. Record
and retain the environment used for any published reference map.
