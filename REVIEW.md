# Release review — GROOVE 1.0.2

Reviewed 7 October 2026 against the supplied standalone cleaning, period-search,
download and morphology scripts. The original scripts are reference material;
they are not imported by the package or included in the distribution.

## Changes and scope

See `CHANGELOG.md` for the changes. The public workflow is one configuration,
`groove` commands, a serial ATLAS downloader, and explicit per-stage outputs.
The cleaning, period-search and morphology functions from the original scientific
scripts remain present. The download orchestration was simplified around a single
user-supplied token. The existing pipeline selection defaults are retained; both
morphology filters are enabled by default, and single-source classification is
available without fitting a UMAP model.

## Completed checks

| Check | Result |
|---|---|
| Automated suite | 31 tests passed on Linux / Python 3.12 |
| Importing every stage module | Passed |
| Build source distribution and wheel | Passed; wheel includes morphology defaults and command entry point |
| Fresh virtual environment, wheel install and full offline demo | Passed with newly resolved dependencies |
| Full 12-source synthetic run | All sources passed through clean, select, periods, morphology and maps |
| Injected shape suggestions | 4 wavelike, 4 transit-like and 4 constant sources matched their injected families |
| Injected periods | All 8 periodic demo sources recovered within 0.052% of their injected periods |
| Single-source run | Period recovery, classification catalogue and source phase plot passed |
| Cyan-only source plot | Observations displayed; no blank orange-only fallback |
| Actual incremental batch | One new source added to the existing map; all 12 reference coordinates preserved to CSV round-trip precision |
| Original cleaner at matched rescue settings | Cleaned dataframe, retention flags and summary matched on a synthetic ATLAS-format source |
| Original Lomb–Scargle calculation | Frequency grid, power, period and FAP matched on seeded synthetic observations |
| Simulated downloads | Completed-file reuse, interrupted polling, saved result resumption, ambiguous submissions and metadata transfer passed |
| Configuration handling | Relative paths, nested overrides, reset between runs, errors and checkpoint invalidation passed |

The original cleaner enables rescue; the supplied package disables it. The parity
check explicitly used the same rescue setting. This preserves a conservative
package default without claiming that different defaults produce identical data.

## Limits of this verification

The ATLAS API was tested using simulated responses. No live authenticated request
was submitted, and the package has not been revalidated on the complete thesis
sample. Synthetic checks establish tested software behavior, not catalogue purity,
completeness, scientific class probabilities or universal threshold performance.
GitHub CI is configured for Windows and Linux with Python 3.10 and 3.12; only the
Linux/Python 3.12 run was executed during this review. Conda installation was not
executed. No repository was published or code uploaded to GitHub by this validation run.

The supplied ATLAS website was inspected over HTTP. It contains reduced/difference
images, detection/classification files and manuals, so documentation links it as
an additional resource rather than an automated per-source light-curve endpoint.
GROOVE still requires time-series photometry; an image needs photometric extraction
before it can enter this pipeline.

## Development environment used for the automated suite

Python 3.12.14

```text
numpy==1.26.4
pandas==2.2.3
scipy==1.17.0
astropy==7.2.2
scikit-learn==1.8.0
umap-learn==0.5.12
numba==0.68.0
joblib==1.5.3
PyYAML==6.0.3
matplotlib==3.10.8
plotly==7.1.0
requests==2.34.2
tqdm==4.70.1
```

## Additional fresh-folder validation (1.0.2)

A new isolated Python 3.12 environment was installed from cached dependency wheels
because fetching dependencies over the network timed out. The final wheel was
installed and the full offline demo was rerun successfully. The expanded suite
passed 31 tests. A simulated API download now reaches final scientific outputs.

The independent audit matched cleaner outputs on 26 controlled observations and
all 12 demo sources with rescue both off/on; original LS and BLS arrays/results
matched exactly; six morphology feature/rule cases matched. All eight demo
periods recovered within 0.052%, all 12 shape families matched, 118 initial demo
PNGs decoded, and four self-contained interactive maps were generated.
A deliberately contaminated 360-row source lost its ten defective observations;
its remaining 350 rows completed selection, LS/BLS and classification.

Additional checks passed for classify, fit, transform, relabel, plot-only,
highlight-source, umap-families, and refit. Transform preserved all original UMAP
coordinates within 1e-12 while adding a thirteenth source. A manual override was
applied and restored. Empty detached-family tables now retain readable headers.

The audit found a damaged period PNG and that earlier documentation described
HTML maps which were not implemented. Version 1.0.2 validates/atomically publishes
period PNGs, rejects damaged images during resume, propagates plot failures,
and implements the documented HTML maps. Cyan-only highlighting now respects
configured filters. A headerless CSV output for zero detached families
was corrected to a header-bearing CSV. These output fixes do not change the
underlying LS/BLS or morphology rules.

Representative cleaning, period, source-fold and static-map plots were visually
inspected. HTML generation and link data were checked; interactive behaviour in
a user's actual browser remains a local review gate. Live ATLAS authentication,
Windows/Conda execution, real-data threshold assessment and full thesis catalogue
parity remain unverified. Do not describe this as complete scientific validation.
