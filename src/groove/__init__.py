"""GROOVE: Grouping of Rare and Odd Objects via Variability Exploration.

Pipeline stages (each is a sub-package with the same layout):

    download   -> raw ATLAS forced-photometry CSVs, one per star
    clean      -> point-level quality cuts
    select     -> source-level usability cuts
    periods    -> Lomb-Scargle / BLS period search with alias handling
    morphology -> folded-profile features, family rules and UMAP maps

`groove.pipeline` wires them together from a single YAML config;
`groove.cli` exposes the `groove` command.
"""

__version__ = "1.1.1"

import logging

logging.getLogger(__name__).addHandler(logging.NullHandler())
