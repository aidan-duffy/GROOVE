# Offline examples

Run `groove demo groove_demo` to generate the bundled, deterministic synthetic
example, then `groove run -c groove_demo/run.yaml --skip-download`.

For existing photometry, save one source per CSV into a local folder, set
`input_folder` to that folder in a run configuration, and use `--skip-download`.

The [ATLAS data directory](http://dtn-itc.ifa.hawaii.edu/atlas/atclass/) is also
linked as a resource. Its images and detection-classification products are not
per-source time-series CSVs; images need photometric extraction before analysis.

Use `MJD` (or `###MJD`), `F` (`c`/`o`), magnitude/error (`m`,`dm`) or flux/error
(`uJy`,`duJy`), plus a source ID where possible. Available image-quality columns
are checked during cleaning; missing columns mean those checks cannot be made.
For magnitude-based morphology, usable finite magnitudes are required.
