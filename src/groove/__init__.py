"""groove: find periodic variability and deep occultations in ATLAS light curves.

Pipeline stages (each is a sub-package with the same layout):

    download   -> raw ATLAS forced-photometry CSVs, one per star
    clean      -> point-level quality cuts
    select     -> source-level usability cuts (thesis criteria)
    periods    -> Lomb-Scargle / BLS period search with alias handling
    morphology -> folded-profile features, family rules and UMAP maps

`groove.pipeline` wires them together from a single YAML config;
`groove.cli` exposes the `groove` command.
"""
__version__ = "1.0.1"
