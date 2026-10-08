"""Run the stages from one Config. Each function configures the stage's
settings module from the YAML and calls that stage's `run.main()`."""
from __future__ import annotations

import json
import importlib
from pathlib import Path

import yaml

from .config import Config, apply_overrides
from .resume import resumable, atomic_json

def _reset(settings):
    # One process can run several configs; no overrides may leak between them.
    importlib.reload(settings)


def _check_result(stage, code):
    if code:
        raise RuntimeError(f"{stage} stopped (exit {code}). Review its output and rerun to resume.")


STAGES = ("download", "clean", "select", "periods", "morphology")


def _banner(cfg: Config, stage: str) -> None:
    print(f"\n### groove {stage}  |  {cfg.name}  |  {cfg.output_folder}\n")


@resumable("download")
def run_download(cfg: Config, dry_run: bool = False, limit: int | None = None, rerun: bool = False) -> int:
    from .download import settings as S, run
    _reset(S)
    _banner(cfg, "download")
    if cfg.targets is None:
        raise ValueError("'targets' must point to a CSV of Gaia DR3 IDs and coordinates")
    S.INPUT_CSV = str(cfg.targets)
    S.OUTPUT_ROOT = str(cfg.raw_root)
    S.RUN_NAME = cfg.download_run_name
    S.GROUP_FILTER = cfg.group
    S.GROUP_COLUMN = cfg.group_column
    S.FILTERS = cfg.filters
    S.GAIA_ID_FILTER = cfg.gaia_id
    S.YEARS_TO_DOWNLOAD = cfg.years
    S.ATLAS_MODE = cfg.photometry
    apply_overrides(S, cfg.download, "download")
    if rerun:
        S.FORCE_REDOWNLOAD = True
    if dry_run:
        S.DRY_RUN = True
    if limit is not None:
        S.LIMIT_TARGETS = limit
    return run.main([])


@resumable("clean")
def run_clean(cfg: Config, rerun: bool = False) -> None:
    from .clean import settings as S, run
    _reset(S)
    _banner(cfg, "clean")
    S.INPUT_DIR = cfg.raw_lightcurves
    S.CLEANED_DIR = cfg.clean_dir
    S.PLOT_DIR = cfg.clean_plots
    apply_overrides(S, cfg.clean, "clean")
    S.FORCE_RERUN = rerun
    run.main()


@resumable("select")
def run_select(cfg: Config, rerun: bool = False) -> None:
    from .select import settings as S, run
    _reset(S)
    _banner(cfg, "select")
    S.CLEANED_DIR = cfg.clean_dir
    S.SELECTED_DIR = cfg.selected_dir
    apply_overrides(S, cfg.select, "select")
    S.FORCE_RERUN = rerun
    run.main()


@resumable("periods")
def run_periods(cfg: Config, rerun: bool = False) -> None:
    from .periods import settings as S, run
    _reset(S)
    _banner(cfg, "periods")
    S.INPUT_DIR = cfg.selected_dir
    S.OUTPUT_DIR = cfg.periods_dir
    S.PLOT_DIR = cfg.period_plots
    apply_overrides(S, cfg.periods, "periods")
    S.FORCE_RERUN = rerun
    if rerun:
        S.SKIP_ALREADY_PROCESSED = False
        S.SKIP_ALREADY_PLOTTED = False
    if S.ALIAS_LEARNING_SERIES not in {"auto", "o", "c", "combined"}:
        raise ValueError("periods.alias_learning_series must be auto, o, c or combined")
    for key in ("SERIES_TO_RUN", "PLOT_SERIES"):
        value = getattr(S, key)
        if not isinstance(value, (list, tuple)) or any(s not in {"o", "c", "combined"} for s in value):
            raise ValueError(f"periods.{key.lower()} must be a list containing o, c or combined")
        if key == "SERIES_TO_RUN" and not value:
            raise ValueError("periods.series_to_run must contain at least one series")
    overridden = {k.lower() for k in cfg.periods}
    if "plot_time_segment_colors" not in overridden:
        S.PLOT_TIME_SEGMENT_COLORS = S.PLOT_TIME_COLOR_PALETTE[:int(S.PLOT_TIME_SEGMENTS)]
    # derived settings that the original script computed at import time
    if "alias_memory_csv" not in {k.lower() for k in cfg.periods}:
        S.ALIAS_MEMORY_CSV = S.OUTPUT_DIR / "tables" / "field_alias_memory.csv"
    run.main()


def morphology_config(cfg: Config) -> dict:
    from .morphology import settings as S
    base = yaml.safe_load(Path(S.DEFAULT_CONFIG_PATH).read_text(encoding="utf-8")) or {}
    from .morphology.utils import deep_merge
    base = deep_merge(base, cfg.morphology)
    base["disable_hard_coded_settings"] = True
    base["output_root"] = str(base.get("output_root") or cfg.morphology_dir)
    if not base.get("manual_labels_file"):
        base["manual_labels_file"] = str(Path(base["output_root"]) / "manual_labels.csv")
    tables = cfg.periods_dir / "tables"
    base["datasets"] = [{
        "name": cfg.name,
        "priority": 0,
        "lightcurve_inputs": [str(cfg.selected_dir)],
        "period_tables": [str(tables / "source_period_recommendations.csv"),
                          str(tables / "ls_period_search_summary.csv")],
        "existing_plot_directories": [str(cfg.period_plots)],
    }]
    return base


@resumable("morphology")
def run_morphology(cfg: Config, extra_args: list[str] | None = None, rerun: bool = False) -> None:
    from .morphology import run
    _banner(cfg, "morphology")
    resolved = morphology_config(cfg)
    if rerun:
        resolved.update(force_recompute_features=True, overwrite_existing_model=True,
                        force_replot_phase_products=True, existing_id_policy="replace")
    cfg.morphology_dir.mkdir(parents=True, exist_ok=True)
    resolved_path = cfg.morphology_dir / f"morphology_config_{cfg.name}.yaml"
    resolved_path.write_text(yaml.safe_dump(resolved, sort_keys=False), encoding="utf-8")
    argv = ["--config", str(resolved_path)] + [a for a in (extra_args or []) if a != "--"]
    _check_result("morphology", run.main(argv))


def run_all(cfg: Config, skip_download: bool = False, skip_morphology: bool = False, rerun: bool = False) -> None:
    stages = []
    options = {"rerun": True} if rerun else {}
    manifest = cfg.output_folder / 'pipeline_run.json'
    def progress(status):
        atomic_json(manifest, {'name': cfg.name, 'config': str(cfg.source_path),
                              'stages': list(stages), 'status': status})
    progress('running')
    if not skip_download:
        if cfg.download.get("dry_run", False):
            raise ValueError("download.dry_run cannot be used with run; use groove download --dry-run")
        _check_result("download", run_download(cfg, **options))
        stages.append("download")
        progress("running")
    for stage, function in [('clean', run_clean), ('select', run_select), ('periods', run_periods)]:
        function(cfg, **options)
        stages.append(stage)
        progress('running')
    if not skip_morphology:
        run_morphology(cfg, **options)
        stages.append("morphology")
    progress('complete')
