"""Run the stages from one Config. Each function configures the stage's
settings module from the YAML and calls that stage's `run.main()`."""
from __future__ import annotations

import json
import importlib
from pathlib import Path

import yaml

from .config import Config, apply_overrides

def _reset(settings):
    # One process can run several configs; no overrides may leak between them.
    importlib.reload(settings)


def _check_result(stage, code):
    if code:
        raise RuntimeError(f"{stage} stopped (exit {code}). Review its output and rerun to resume.")


STAGES = ("download", "clean", "select", "periods", "morphology")


def _banner(cfg: Config, stage: str) -> None:
    print(f"\n### groove {stage}  |  {cfg.name}  |  {cfg.output_folder}\n")


def run_download(cfg: Config, dry_run: bool = False, limit: int | None = None) -> int:
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
    if dry_run:
        S.DRY_RUN = True
    if limit is not None:
        S.LIMIT_TARGETS = limit
    return run.main([])


def run_clean(cfg: Config) -> None:
    from .clean import settings as S, run
    _reset(S)
    _banner(cfg, "clean")
    S.INPUT_DIR = cfg.raw_lightcurves
    S.CLEANED_DIR = cfg.clean_dir
    S.PLOT_DIR = cfg.clean_plots
    apply_overrides(S, cfg.clean, "clean")
    run.main()


def run_select(cfg: Config) -> None:
    from .select import settings as S, run
    _reset(S)
    _banner(cfg, "select")
    S.CLEANED_DIR = cfg.clean_dir
    S.SELECTED_DIR = cfg.selected_dir
    apply_overrides(S, cfg.select, "select")
    run.main()


def run_periods(cfg: Config) -> None:
    from .periods import settings as S, run
    _reset(S)
    _banner(cfg, "periods")
    S.INPUT_DIR = cfg.selected_dir
    S.OUTPUT_DIR = cfg.periods_dir
    S.PLOT_DIR = cfg.period_plots
    apply_overrides(S, cfg.periods, "periods")
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


def run_morphology(cfg: Config, extra_args: list[str] | None = None) -> None:
    from .morphology import run
    _banner(cfg, "morphology")
    resolved = morphology_config(cfg)
    cfg.morphology_dir.mkdir(parents=True, exist_ok=True)
    resolved_path = cfg.morphology_dir / f"morphology_config_{cfg.name}.yaml"
    resolved_path.write_text(yaml.safe_dump(resolved, sort_keys=False), encoding="utf-8")
    argv = ["--config", str(resolved_path)] + [a for a in (extra_args or []) if a != "--"]
    _check_result("morphology", run.main(argv))


def run_all(cfg: Config, skip_download: bool = False, skip_morphology: bool = False) -> None:
    stages = []
    if not skip_download:
        if cfg.download.get("dry_run", False):
            raise ValueError("download.dry_run cannot be used with run; use groove download --dry-run")
        _check_result("download", run_download(cfg))
        stages.append("download")
    run_clean(cfg)
    run_select(cfg)
    run_periods(cfg)
    stages.extend(["clean", "select", "periods"])
    if not skip_morphology:
        run_morphology(cfg)
        stages.append("morphology")
    (cfg.output_folder / "pipeline_run.json").write_text(json.dumps(
        {"name": cfg.name, "config": str(cfg.source_path), "stages": stages}, indent=2))
