# Restart interrupted runs or deliberately recalculate

## Normal restart

Resume is the default. Press Ctrl+C, let the process exit, then repeat the same
command using the same configuration and output directory:

```bash
groove run -c run.yaml --skip-download
```

For a download-inclusive workflow, repeat `groove run -c run.yaml` instead.
Completed stages are checked using configuration, code and input content plus
output checksums. They are skipped when compatible. Missing or altered products
invalidate completion and trigger repair/reprocessing; saved products are not
accepted merely because their folders exist. Configuration paths remain
relative to the YAML file.

`pipeline_run.json` records `running` or `complete` and the stages completed in
the current invocation. Detailed stage receipts live under `.groove_state` in
the output folder. Keep these, the source checkpoints and model caches when
resuming. Do not edit them or start concurrent runs targeting the same outputs.

## Resume just one stage

```bash
groove download -c run.yaml
groove clean -c run.yaml
groove select -c run.yaml
groove periods -c run.yaml
groove morphology -c run.yaml
```

The whole-run command uses these same stage receipts. Work completed through
an individual command can therefore be reused by a later full run.

| Stage | Restart behaviour |
|---|---|
| Download | Resume saved task/result URLs. Reuse completed compatible stage outputs without contacting ATLAS. Validate existing CSV headers when the downloader runs. Ambiguous submissions still require queue reconciliation to avoid duplicate jobs. |
| Clean | Save a checkpoint after each successful source, including raw-input/settings identity, result metadata and cleaned-file checksum. Retry failed/incomplete sources; preserve unchanged cleaned files. Rebuild aggregate summaries from cached rows. |
| Select | Re-evaluate when necessary, preserve matching selected files and remove files no longer selected. An unchanged completed stage is skipped. |
| Periods | Save an atomic journal after each completed source, including summary and peaks. Keep the configurable large CSV snapshot interval, avoiding rewriting a growing table after every star. Retry failed sources. Changing display-only settings preserves compatible numerical searches. |
| Period plots | Reuse compatible checksummed normal/extra figures; repair missing or changed products. Some figure construction may repeat before a saved product is reused. |
| Morphology | Reuse source feature caches, keyed by source data, representation and period records. Retain completed fitting/classification checkpoints for figure repair without fitting UMAP again. Transform mode also checkpoints output finalisation. Phase plots have individual receipts, including data/period/DPI identity. |

Stopping during one source may require that source to run again. Successful
sources already checkpointed remain reusable. Interrupted UMAP fitting is
restarted from cached features; fitting is not checkpointed at every optimiser
iteration. Overview figures, neighbourhood validation and report assembly may
repeat when repairing an incomplete output pass. Content validation also costs
some disk I/O; resume is not instantaneous on a large dataset.

Errors do not become a successful completion receipt. Clean and period stages
save successful work and report failed sources; morphology feature extraction
saves successful feature caches and reports processing_failures.csv. Fix the
reported cause, then resume. Restart does not diagnose or solve a genuinely
stalled calculation, and this release adds neither per-source timeouts nor
parallel period-search workers.

## Deliberately recalculate: --rerun

```bash
# All analysis stages from existing raw photometry:
groove run -c run.yaml --skip-download --rerun

# Individual stages:
groove clean -c run.yaml --rerun
groove select -c run.yaml --rerun
groove periods -c run.yaml --rerun
groove morphology --rerun -c run.yaml

# Fresh downloads as well:
groove run -c run.yaml --rerun
```

`--rerun` bypasses stage/source/plot reuse for that invocation. It overwrites
managed analysis results and regenerates configured plots; raw input files
are preserved unless downloading is requested. It does not change scientific
cuts, automatically enable disabled plots, or delete unrelated user files.
Download reruns deliberately refetch completed targets but still respect
unresolved active submissions.

Morphology follows the configured mode: fit/refit rebuilds the reference;
transform recomputes this sample and replaces its IDs on the existing frozen
reference. A transform rerun does not retrain the reference. Map-only/plot-only
still perform their documented output-only operation. Use the `--rerun` flag
before the morphology `--` separator, e.g.:

```bash
groove morphology --rerun -c run.yaml -- --mode map-only
```

If a forced rerun stops, restart **without --rerun** to reuse the new checkpoints.
Repeating --rerun deliberately starts recalculating again.

## Changed inputs and older runs

Changed input content, scientific settings or relevant code invalidates affected
saved work. Changing a period figure's style should not repeat the LS/BLS
search. Changes to morphology representation, rules or embedding settings can
require a new fit. If an existing reference is incompatible, the code asks for
`--rerun` or a new model version rather than silently overwriting it. Repairing
an original fit after adding transformed sources must use map-only/plot-only;
a forced fit rebuild deliberately replaces that reference catalogue.

Runs created before 1.0.9 lack the new receipts/journals and may need one rebuild
to establish them. Saved progress that existed only in the old process's memory
cannot be recovered. If an older completed morphology reference blocks the
first resumed full run, use a fresh validation folder or a deliberate --rerun.
Once 1.0.9 establishes its state, subsequent interruptions use the new resume
mechanism. Stop the old process before installing a source update.
