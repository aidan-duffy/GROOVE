# GROOVE 1.0.9: resume across the pipeline and --rerun

Download GROOVE_v1.0.9.zip and update_GROOVE_and_push_v1.0.9.sh into Windows
Downloads. Stop any currently running GROOVE process before updating:

```bash
conda activate groove-test
cd /mnt/c/Users/aidan/TFM/GROOVE
bash /mnt/c/Users/aidan/Downloads/update_GROOVE_and_push_v1.0.9.sh \
  /mnt/c/Users/aidan/Downloads/GROOVE_v1.0.9.zip
```

The updater backs up replaced package files, preserves configuration and target
files, installs, tests, commits and pushes delivered source. Already staged
changes must be reviewed/committed or unstaged first. Your test data are not
included in the commit.

Resume the contained real-data full run:

```bash
groove run -c testing/full_pipeline_v108/run.yaml --skip-download
```

The folder name does not determine the installed code version. Check
`groove --version`. Older runs may require one rebuild to establish compatible
receipts, especially an already completed morphology model. To deliberately
rebuild in that same test folder:

```bash
groove run -c testing/full_pipeline_v108/run.yaml --skip-download --rerun
```

For an independent test, repeat the earlier raw-data setup in a fresh folder
and run once, interrupt it, then repeat its normal command. Confirm the console
shows completed stages/source checkpoints being reused. After completion,
repeat again: completed stages should be checked and skipped.

[Restart commands, scope and limitations](restarts.md) explain individual
stages, forced runs, plotting, reference models and old-run migration.
