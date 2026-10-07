from __future__ import annotations
import argparse
import logging
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
import numpy as np
import yaml
from . import settings as S
from . import modes as _modes
from . import plots as _plots
from . import smoke as _smoke
from . import utils as _utils




# ===========================================================================
# CONFIG RESOLUTION AND CLI
# ===========================================================================


def load_configuration(path: Optional[Path]) -> Dict[str, Any]:
    config = dict(S.DEFAULTS)
    if path and not Path(path).is_file():
        raise FileNotFoundError(f"Morphology config not found: {path}")
    if path and Path(path).exists():
        loaded = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        config = _utils.deep_merge(config, loaded)
    use_hard_coded = S.USE_HARD_CODED_SETTINGS and not bool(
        config.get("disable_hard_coded_settings", False))
    if use_hard_coded:
        config = _utils.deep_merge(config, S.HARD_CODED_SETTINGS)
    return config


def apply_cli(config: Dict[str, Any], args: argparse.Namespace) -> Dict[str, Any]:
    for attribute, key in (("mode", "mode"), ("output_root", "output_root"),
                           ("model_version", "model_version"), ("batch_id", "batch_id"),
                           ("random_seed", "random_seed"), ("n_jobs", "n_jobs"),
                           ("existing_id_policy", "existing_id_policy")):
        value = getattr(args, attribute, None)
        if value is not None:
            config[key] = value
    if args.force_recompute_features:
        config["force_recompute_features"] = True
    if args.overwrite:
        config["overwrite_existing_model"] = True
    if args.no_review_plots:
        config["make_review_plots"] = False
    if args.input:
        config["datasets"] = [{
            "name": args.dataset_name or "cli_input",
            "priority": 0,
            "lightcurve_inputs": list(args.input),
            "period_tables": list(args.period_table or []),
            "existing_plot_directories": list(args.existing_plot_directory or []),
        }]
    return config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ATLAS morphology UMAP pipeline")
    parser.add_argument("--config", type=Path, default=S.DEFAULT_CONFIG_PATH)
    parser.add_argument("--mode", choices=[
        "classify", "fit", "transform", "refit", "relabel", "plot-only", "map-only",
        "highlight-source", "umap-families"])
    parser.add_argument("--output-root", dest="output_root")
    parser.add_argument("--model-version", dest="model_version")
    parser.add_argument("--batch-id", dest="batch_id")
    parser.add_argument("--random-seed", dest="random_seed", type=int)
    parser.add_argument("--n-jobs", dest="n_jobs", type=int)
    parser.add_argument("--existing-id-policy", dest="existing_id_policy",
                        choices=["skip", "replace"])
    parser.add_argument("--input", action="append")
    parser.add_argument("--period-table", action="append")
    parser.add_argument("--existing-plot-directory", action="append")
    parser.add_argument("--dataset-name")
    parser.add_argument("--force-recompute-features", action="store_true")
    parser.add_argument("--no-review-plots", action="store_true")
    parser.add_argument("--outline-new", action="store_true")
    parser.add_argument("--no-outline-new", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--source-id",
                        help="Saved source to highlight; required by highlight-source mode")
    parser.add_argument("--label", dest="source_label",
                        help="Display label for --source-id (for example J0538)")
    parser.add_argument("--map", dest="map_name", choices=sorted(S.ADDON_MAP_SPECS),
                        default="combined", help="Frozen UMAP to annotate")
    parser.add_argument("--nearest-neighbours", type=int, default=8,
                        help="High-dimensional neighbours; capped at 8 for a 3x3 grid")
    parser.add_argument("--diagnostic-folds", action="store_true",
                        help="Also write P/2 and 2P neighbour grids")
    parser.add_argument("--umap-cluster-eps", type=float,
                        help="DBSCAN radius; default is the 95th percentile local radius")
    parser.add_argument("--umap-cluster-min-samples", type=int, default=20,
                        help="Minimum local density for detached UMAP regions")
    parser.add_argument("--umap-cluster-min-size", type=int,
                        help="Retained island size; default=max(100, 2%% of sources)")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--smoke-test", action="store_true")
    return parser


def check_environment(logger: Optional[logging.Logger] = None) -> None:
    """Warn early if the interpreter is not the intended environment."""
    try:
        import sklearn
        parts = tuple(int(x) for x in sklearn.__version__.split(".")[:2])
        if parts < (1, 2):
            message = (
                "scikit-learn %s is older than 1.2. The pipeline compensates, but "
                "install the dependencies listed in pyproject.toml." % sklearn.__version__)
            (logger.warning if logger else print)(message)
    except Exception:
        pass


def execute(args: argparse.Namespace) -> Dict[str, Any]:
    check_environment()
    config = apply_cli(load_configuration(args.config), args)
    _plots.validate_dataset_markers(config.get("dataset_markers", {}))
    S.selected_maps(config)
    np.random.seed(int(config.get("random_seed", 42)))
    mode = str(config.get("mode", "fit"))
    if mode == "classify":
        return _modes.classify_only(config, args)
    if mode in ("fit", "refit"):
        return _modes.fit_or_refit(config, args, mode)
    if mode == "transform":
        return _modes.transform_mode(config, args)
    if mode == "relabel":
        return _modes.relabel_or_plot(config, args, mode)
    if mode == "map-only":
        return _plots.map_only(config, args)
    if mode == "plot-only":
        return _plots.phase_fold_plot_only(config, args)
    if mode == "highlight-source":
        return _modes.highlight_source_mode(config, args)
    if mode == "umap-families":
        return _modes.umap_families_mode(config, args)
    raise SystemExit("Unknown mode: %s" % mode)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.smoke_test:
        return _smoke.smoke_test(args.verbose)
    try:
        execute(args)
    except SystemExit as error:
        print("ERROR: %s" % error, file=sys.stderr)
        return 2
    return 0
