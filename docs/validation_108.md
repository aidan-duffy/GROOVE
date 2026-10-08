# GROOVE 1.0.8 validation

- Full suite: 67 passed (5 existing seeded-UMAP warnings).
- Final targeted alias/output-options checks: 15 passed.
- Regression coverage: O/C-only and single-band learning, unique-star minimum,
  pooling without duplicate hits, combined-reference compatibility, duplicate
  reference rows, universal-alias exclusions, missing-band warning, invalid
  learning option, and preservation of long IDs with missing reference IDs.
- Fresh extended-demo period stage completed for all 24 selected synthetic
  sources using O/C only, with no inherited alias memory.
- All 46 available raw LS and BLS periods agree with the previous demo within
  0.1%; the two unavailable per-band periods belong to single-filter examples.
- All 552 ranked peaks agree; available raw LS powers agree tightly.
- All ten coherent wave/dip/single-filter injections recover within 0.1%, and
  none is labelled weak_or_ambiguous.
- Both daily-alias demonstration bands promote rank two to approximately
  8.3 days (O: 8.305573; C: 8.297963).
- Two per-band alias-aware periods differ from the prior run, both from
  non-variable synthetic examples, after local field learning becomes active.
- All 107 generated period PNGs passed decoding/integrity checks; all 14 extra
  alias/harmonic figures exist and have successful manifest entries. The
  alias-promotion three-panel figure was visually inspected.
- The generated starting YAML includes alias_learning_series: auto.
- Linux updater passed bash syntax validation; archive excluded build/cache
  files and passed ZIP integrity validation. No GitHub push was executed here.

The real 200-curve run and historical full-sample alias context were not
available here. The release documentation describes separate fresh-output
comparisons. Raw numerical agreement does not establish astrophysical truth
or full cleaning/morphology parity with the thesis.
