# GROOVE 1.0.5 validation

Default extended demo: 24 artificial sources, 48 period-summary rows (24 O and
24 C, including skipped rows for single-band fixtures), no combined-search row.
All ten coherent wave/dip/single-band test signals recovered within 0.1% of
the injected period and labelled strong. The deliberately aliased example
promotes its alternative peak to about 8.3 days independently in O and C.

Combined opt-in integration: analysed O, C and combined for the alias fixture,
but selected only combined for saving. Its normal and automatic alias plots
were saved only for combined. Empty O/C folders can still be created by the
output-directory setup; they contain no saved plots in this configuration.

Map selection: three default overview maps (classification evidence, overall
similarity, periodic shape). Internal transient representation remains saved.
A separate test verifies that automatic alias plotting honours plot_series.

Validation uses artificial data and mocked download responses. It does not
establish live ATLAS service availability, real-sample scientific equivalence,
or classification completeness/purity. O/C-only changes the analysis inputs
relative to prior all-series releases, so real validation comparisons remain
necessary before treating the results as equivalent.

The final automated suite passed all 53 tests. The complete demo audit passed,
including decoding all 182 PNGs and verifying all three interactive overview
maps, four alias diagnostic images and two harmonic diagnostic images.
