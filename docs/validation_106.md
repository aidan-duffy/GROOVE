# GROOVE 1.0.6 validation

The automated suite passed 56 tests. Targeted map/layout regressions passed
again after the final legend and highlight changes. map-only snapshots verified
that saved catalogue/model bytes remain identical and deselected overview maps
are removed. Scientific-fit/classification functions were forbidden in that test.

Static mixed-dataset maps were generated from saved demo coordinates and
visually inspected for optional circle/diamond shapes, latest-batch outlines and
separate morphology/dataset legend entries. Three offline interactive maps were
generated with linked source phase plots. JavaScript comparison controls were
executed against a jsdom DOM: adding multiple sources, preventing duplicates,
removing cards, lasso selection, clearing, missing links and image-error states
passed; phase-image paths resolve to actual files. Full browser rendering was
not tested: Chromium download was unavailable in this environment.

Source and wheel builds passed. Installation into a separate dependency
verified environment succeeded with no broken requirements. Documentation
relative-file links were checked. The updater passed bash syntax validation;
its source update/install/test/commit/push workflow is unchanged from earlier
releases, with the new version and commit description. No remote GitHub push
was performed here; the supplied updater runs in the user's checkout.

No scientific thresholds, period calculations or feature/label algorithms were
changed. ATLAS remains the validated input; other-survey guidance describes
required adaptation and testing rather than claiming compatibility.
