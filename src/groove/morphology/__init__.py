"""ATLAS light-curve morphology: two unsupervised UMAP maps plus documented rules.

Primary labels describe observed morphology. Scientific interest is an
independent axis, so an unusual transit remains a transit while its interest
status records why it deserves follow-up. The authoritative period always comes
from the period-search tables; the diagnostics here never replace it.

Modes: fit | transform | refit | relabel | plot-only | highlight-source |
       umap-families"""
