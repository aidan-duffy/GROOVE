# GROOVE 1.0.9 restart validation

Final full suite: **86 passed**, with 13 non-failing existing seeded-UMAP/pandas
warnings. Wheel and source distribution built successfully; the wheel contains
groove/resume.py and 1.0.9 distribution metadata. Linux updater passed bash
syntax validation. ZIP integrity was checked after packaging.

Meaningful restart checks include:

- Interrupt cleaning after one completed source, resume without re-cleaning it,
  then confirm --rerun processes every source again.
- Delete a cleaned file or alter its raw input, and reprocess only that source.
- Repeat selection while preserving unchanged selected-file timestamps.
- Interrupt a whole run before periods, then resume while preserving completed
  cleaning/selection; repeat completion and deliberately force recalculation.
- Interrupt period search before its first full CSV snapshot and recover the
  completed source's summary/peaks from its atomic journal.
- Interrupt after period tables are saved and preserve numerical search work
  and alias-inventory counts on restart.
- Change a visual-only period setting without repeating the search.
- Retry a failed period source without repeating successful sources.
- Recover an empty aggregate period CSV from the successful source journals.
- Interrupt cleaning's plot pass and retain an already saved compatible figure.
- Detect and repair changed plot bytes rather than trusting file existence.
- Run a real synthetic cleaning/selection/period/morphology workflow; damage a
  phase plot; repair it without feature extraction or UMAP fitting; check the
  saved fitted model bytes and unchanged source-plot timestamps.
- Interrupt projection of a new source onto that reference before finalisation;
  resume from its saved transform results without repeating projection or
  duplicating source IDs; then repeat the completed full command.
- Reuse a completed mocked download without authentication, and confirm a
  download --rerun submits fresh work.
- Parse --rerun for every stage and the full command, including the normal
  placement after -c before any morphology pass-through separator.

Live ATLAS download, the user's real 200-curve sample and 10,000-star performance
were not tested here. Interrupted UMAP optimisation restarts from cached source
features rather than from an optimiser iteration. Some aggregate rendering and
validation calculations can repeat during output repair. This release does not
add per-source timeouts or parallel LS/BLS workers.
