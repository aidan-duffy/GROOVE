# GROOVE 1.0.7: Linux / WSL end-to-end validation

These commands are Bash, for your existing clone at
`/mnt/c/Users/aidan/TFM/GROOVE`. Use a fresh output folder for each demo.
The internal .py files are modules, so validate their functions with pytest and
run each public stage separately rather than executing every helper file.

## 1. Update the existing clone

Activate your existing environment and enter the clone:

```bash
conda activate groove-test
cd /mnt/c/Users/aidan/TFM/GROOVE
```

If GitHub already contains 1.0.7 and you have no conflicting local edits:

```bash
git pull --ff-only
python -m pip install -e '.[dev]'
```

The revised source has not been pushed to GitHub on your behalf. To use the
supplied release locally, download GROOVE_v1.0.7.zip into Windows Downloads,
then copy its source over the existing clone (existing data/results remain):

```bash
groove_release_dir=$(mktemp -d)
python -m zipfile -e /mnt/c/Users/aidan/Downloads/GROOVE_v1.0.7.zip "$groove_release_dir"
cp -a "$groove_release_dir/GROOVE/." /mnt/c/Users/aidan/TFM/GROOVE/
python -m pip install -e '.[dev]'
```

This modifies local source files; review `git diff` before committing them.
Do not run git pull over those edits expecting it to publish them. Make a
reviewed commit/push or update the source through GitHub when ready.

## 2. Check installation and tests

```bash
python -m pip check
python -m groove --version
python -m pytest -ra
python -m pip freeze > environment.txt
git rev-parse HEAD
```

Expected version: groove 1.0.7. The release has 56 tests. A seeded UMAP warning
about n_jobs=1 is expected. Stop and retain the traceback if tests fail.
After copying a release over a clone, its Git commit still identifies the old
committed source until you commit the edits; record the local diff as well.

Individual test groups:

```bash
python -m pytest -v tests/test_download.py
python -m pytest -v tests/test_pipeline.py
python -m pytest -v tests/test_integration.py
python -m pytest -v tests/test_period_review.py
```

The download group simulates the remote service; it verifies code paths, not
actual ATLAS authentication/coverage. The new review tests protect coherent
dips with competitive second peaks and retain weak-noise/alias/harmonic review.

## 3. Check the original 12-source demonstration

```bash
python -m groove demo demo_104
python -m groove run -c demo_104/run.yaml --skip-download
python -m groove demo-check demo_104
python tools/audit_outputs.py demo_104
```

Expected: 12 sources, 4 wavelike, 4 transit and 4 nonvar morphology labels.
All 8 periodic signals recover the input periods within 0.1%. Period-review
labels are 8 strong and 4 weak_or_ambiguous; morphology nonvar is a separate
judgment. A recommended numerical period for a quiet source is not a proven
periodic detection. The audit helper also exercises controlled cleaning cuts
and a separate injected BLS signal. Its report paths are printed by the tool.

## 4. Run each stage of the extended demonstration

```bash
python -m groove demo demo_extended_104 --extended
python -m groove clean -c demo_extended_104/run.yaml
python -m groove select -c demo_extended_104/run.yaml
python -m groove periods -c demo_extended_104/run.yaml
python -m groove morphology -c demo_extended_104/run.yaml
python -m groove demo-check demo_extended_104
```

Run one stage at a time and inspect its outputs. This has 24 artificial sources:
the original 12 plus a daily systematic mixed with a wave, nightly sampling of
an 84.5-day wave, unequal eclipses, repeated flares, irregular dips, an evolving
wave, noisy measurements, a cyan-only wave and an orange-only wave, a single isolated dip and an offset double-dip signal, and a stronger-secondary-peak alias-recovery case.
Read `CASE_GUIDE.md`, `truth.csv`, `demo_check.json` and `demo_source_review.csv`.
Input behaviours are not forced classifier labels. Inspect any classifier
mismatch rather than modifying thresholds simply to populate every category.
The flare/dip/evolving/noisy cases need visual and feature review; they are not
an unbiased performance benchmark.

Both one-day systematic cases should trigger automatic alias folds. In alias_promoted (ID 3216489845356186519), the rank-one daily peak is replaced by rank two near 8.3 days. The original weaker-secondary case stays flagged. The unequal
binary should trigger harmonic folds. Nightly sampling can produce competing
daily side peaks even when the true period is retained. Being near a daily
alias does not mean a real signal must be discarded. BLS is enabled as a
diagnostic, using demo-only limits 2–30 days, durations 0.2/0.4 days and three
samples per peak to keep this teaching run manageable. LS searches 0.5–120 days.

Do not run the fixed 12-source audit_outputs.py on the extended sample; use the
built-in demo-check for it.

## 5. Inspect tables and every plot family

| Stage | Location under demo_extended_104/results | Review |
|---|---|---|
| Cleaning | 2_clean/lightcurves | summary, removal reasons, retained measurements |
| Selection | 2_clean/selected | selected_sources.csv; IDs and rejection reasons |
| Periods | 3_periods/tables | recommendations, per-series results, candidate peaks and BLS columns |
| Cleaning plots | plots/clean | before/after examples and counts |
| Period plots | plots/periods | c/o best_per_star (combined optional) and review folders |
| Extra folds | plots/periods/*/alias/extra_phase_folds and */harmonic/extra_phase_folds | competing periods and P/2, P, 2P |
| Morphology | plots/ML/extended_demo | all_sources.csv, phase images, maps, category_folds and appendix |

Read `3_periods/tables/extra_phase_fold_diagnostics.csv`: check the source,
trigger reason, plotted periods, completed status and existing image path.
Look for failed/skipped rows and nonempty plot_error fields in period tables.
A completed run should have `pipeline_run.json` listing all four analysis stages.

For WSL, open the results in Windows Explorer:

```bash
explorer.exe "$(wslpath -w "$PWD/demo_extended_104/results")"
```

For desktop Linux use `xdg-open demo_extended_104/results` if installed.
Inspect PNGs at full resolution for clipping, readable labels and consistent
filter/time colours. Open each *interactive.html map in a browser: test hover,
zoom and clicking a source. Keep source_plots alongside maps for relative links.
A programmatic PNG/HTML check does not replace these visual/browser checks.

## 6. Test additional saved-model modes

Use the same reference configuration. Its model version is extended_demo.

```bash
python -m groove morphology -c demo_extended_104/run.yaml -- --mode classify
python -m groove morphology -c demo_extended_104/run.yaml -- --mode plot-only
python -m groove morphology -c demo_extended_104/run.yaml -- \
  --mode highlight-source --source-id 3216489845356186515 \
  --label cyan_demo --diagnostic-folds
python -m groove morphology -c demo_extended_104/run.yaml -- \
  --mode refit --model-version refit_review
python -m groove morphology -c demo_extended_104/run.yaml -- \
  --mode umap-families --umap-cluster-min-samples 5 \
  --umap-cluster-min-size 2 --umap-cluster-eps 100
```

Numerical tables/models now live under `4_morphology/saved_runs/<run>/`; all plots live under `plots/ML/<run>/`. Check new products exist, cyan-only plots contain observations, and refitting
creates saved_runs/refit_review without replacing saved_runs/extended_demo. Family
settings above exercise the add-on on a tiny sample; no detached families is a
valid outcome and the output is not evidence of physical clusters.

For relabel, back up the manual-label file, edit a source using template columns
from data/manual_labels_template.csv, then relabel:

```bash
cp demo_extended_104/results/4_morphology/manual_labels.csv /tmp/groove_manual_labels_backup.csv
nano demo_extended_104/results/4_morphology/manual_labels.csv
python -m groove morphology -c demo_extended_104/run.yaml -- --mode relabel
```

Verify the intended label changes while source map coordinates remain fixed.
Restore the backup and relabel again to undo the test.

## 7. Test transform with distinct artificial source IDs

Copy 4_morphology/saved_runs/extended_demo/tables/reference_sources.csv before the transformation so you can compare its
coordinates by source ID. Create another artificial batch:

```bash
python -m groove demo demo_batch_104
python - <<'PY'
from pathlib import Path
import re
import yaml
batch = Path('demo_batch_104')
for file in sorted((batch / 'raw').glob('*.csv')):
    old = re.search(r'GaiaDR3_(\d+)', file.name).group(1)
    new = str(int(old) + 10000)
    file.with_name(file.name.replace(old, new)).write_text(file.read_text().replace(old, new))
    file.unlink()
p = batch / 'run.yaml'
cfg = yaml.safe_load(p.read_text())
cfg['name'] = 'transform_test'
cfg['morphology'].update(mode='transform', model_version='extended_demo',
    output_root=str(Path('demo_extended_104/results/4_morphology').resolve()))
p.write_text(yaml.safe_dump(cfg, sort_keys=False))
PY
python -m groove clean -c demo_batch_104/run.yaml
python -m groove select -c demo_batch_104/run.yaml
python -m groove periods -c demo_batch_104/run.yaml
python -m groove morphology -c demo_batch_104/run.yaml
```

Check new IDs appear in the merged reference products and original reference
coordinates stay fixed. IDs are artificial. truth.csv was not rewritten, so do
not run the demo truth checker on this deliberately modified batch.

## 8. Prepare one real source

The source archive includes configs/real_test.yaml and data/targets/validation.csv.

```bash
nano data/targets/validation.csv
```

Replace placeholders with a genuine source ID and RA/Dec in decimal degrees.
Start with a known source with ATLAS coverage; preserve long IDs as text.
Then inspect selection without submitting work:

```bash
python -m groove targets data/targets/validation.csv
python -m groove download -c configs/real_test.yaml --dry-run
```

Do not submit the artificial demo IDs. This config limits downloads to one
source and uses classification-only morphology, suitable for a single source.

## 9. Authenticate, download, compare and test completed-file reuse

Obtain your own token from https://fallingstar-data.com/forcedphot/.
Read it privately into your shell:

```bash
read -r -s -p 'ATLAS token: ' ATLAS_TOKEN
echo
export ATLAS_TOKEN
python -m groove download -c configs/real_test.yaml
python tools/audit_downloads.py configs/real_test.yaml
python tools/audit_downloads.py configs/real_test.yaml --compare-api
python -m groove download -c configs/real_test.yaml
```

The final command should reuse the completed source rather than submit it again.
Files land under results/real_test/1_raw/atlas_full_reduced/all_lightcurves.
Check download_progress.csv, run_config.json and download_audit.json. The API
comparison reads the completed result URL and submits no new job; URLs must
still be available. no_data can be a valid service outcome; it cannot validate
a photometry download, so test a source known to have coverage.

To test interrupted polling, stop while waiting on a known saved task and rerun
the same command. Do not deliberately interrupt the initial submission POST.
If status is submission_unknown, check the service queue as described in
stages.md before retrying; do not delete progress and blindly resubmit.

## 10. Run real cleaning, selection, periods and morphology

```bash
python -m groove clean -c configs/real_test.yaml
python -m groove select -c configs/real_test.yaml
python -m groove periods -c configs/real_test.yaml
python -m groove morphology -c configs/real_test.yaml
explorer.exe "$(wslpath -w "$PWD/results/real_test")"
```

Check raw count = retained + removed, removal reasons, retained epochs,
recommended periods and morphology's adopted period. Default source selection
requires 100 points total, 30 in a qualifying band with median magnitude error
<=0.2, 365-day baseline and <=50% removed. These differ from internal period
minimums. Review failure reasons before changing cuts.

Compare a known period against the output, allowing for a reviewed P/2 or 2P
harmonic. Classification-only tables are under 4_morphology/classification; their figures are under plots/ML/classification.
For an 8–12-source representative sample, remove download.limit_targets: 1,
then repeat the download/audits and analysis. At least five usable morphology
sources are needed for fitting a UMAP reference. Document source expectations
before seeing the outputs.

## 11. Compare original science functions and real thesis outputs

For the standard demo only:

```bash
python tools/audit_outputs.py demo_104 --originals /path/to/original_science_scripts
```

Use only the three science scripts in this comparison directory; do not include
credential scripts. For real data, use identical raw files, inputs, filters,
alias references/manual labels and parameters. Original cleaner rescue was on;
GROOVE defaults off. Original morphology was orange-only; GROOVE defaults both
filters on. Match these settings before assessing numerical parity.
The new 1.0.7 review-label rule deliberately differs from the original routing,
while leaving numerical period searches unchanged.

## 12. Record evidence and finish

Keep a table: check, expected, actual, pass/fail, evidence file, unresolved issue.
A complete validation needs passing software tests, checked real service results,
correct stage handoffs, readable plots/browser interactions and explained
original-workflow differences. Finite tests cannot prove every input correct.
Do not treat this small demo as publication completeness/purity validation.
Do not commit environments, tokens or bulk results simply to record testing.

```bash
unset ATLAS_TOKEN
```

## Update, test and push your source to GitHub

Download GROOVE_v1.0.7.zip and update_GROOVE_and_push_v1.0.7.sh to Windows Downloads.
From the existing authenticated clone, with groove-test active:

```bash
cd /mnt/c/Users/aidan/TFM/GROOVE
conda activate groove-test
bash /mnt/c/Users/aidan/Downloads/update_GROOVE_and_push_v1.0.7.sh \
  /mnt/c/Users/aidan/Downloads/GROOVE_v1.0.7.zip
```

The script backs up overwritten files, preserves existing configs and target
lists, installs/tests the new source, commits only delivered package files,
and pushes your current branch to origin. It stops on failed tests, staged
unrelated changes, an unexpected remote or detached HEAD. It does not force push.
Previously edited source will be overwritten but has a printed backup path.
Your old results are not moved; run a fresh demo or plot-only to populate the
new plot layout. Existing saved model directories remain readable.

If Git needs a commit identity, set it for this repository before running:

```bash
git config user.name 'Aidan Duffy'
git config user.email 'YOUR_GITHUB_EMAIL_OR_NOREPLY_ADDRESS'
```

Replace the email placeholder with the actual address you choose for commits.
SSH may ask for your key passphrase when pushing. If the remote is ahead, the
push can be rejected; retain the local commit and resolve normally, without
force pushing. Once successful, check the latest commit on GitHub.
