from __future__ import annotations
import json
import logging
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
import joblib
import numpy as np
import pandas as pd
from . import settings as S
from . import features as _features
from . import utils as _utils




# ===========================================================================
# TABLES AND MODEL IO
# ===========================================================================


def ensure_structure(version_dir: Path) -> None:
    for name in ("tables", "cache", "models"):
        (Path(version_dir) / name).mkdir(parents=True, exist_ok=True)
    for name in ("maps", "source_plots", "category_folds", "appendix", "interest"):
        (figure_directory(version_dir) / name).mkdir(parents=True, exist_ok=True)


def figure_directory(version_dir: Path) -> Path:
    """Keep every visual product in results/plots/ML/<run>, beside other plots."""
    path = Path(version_dir)
    if path.parent.name in {"saved_runs", "model_versions"}:
        root = path.parent.parent
        name = path.name.removeprefix("model_") if path.parent.name == "model_versions" else path.name
    elif path.name == "model_versions":
        root, name = path.parent, "default"
    elif path.name == "classification":
        root, name = path.parent, "classification"
    else:
        # Standalone plotting helpers may intentionally use an arbitrary folder.
        return path
    plot_base = root.parent if root.name == "4_morphology" else root
    return plot_base / "plots" / "ML" / name


def save_models(version_dir: Path, block: str, models: Mapping[str, Any]) -> None:
    path = Path(version_dir) / "models"
    path.mkdir(parents=True, exist_ok=True)
    keys = ("imputer", "scaler", "pca", "umap", "empty_columns",
            "post_scale_weights", "feature_groups", "configured_feature_weights",
            "feature_weight_interpretation", "selected_settings",
            "category_score_columns")
    joblib.dump({k: models[k] for k in keys if k in models},
                path / ("%s_representation.joblib" % block))
    if "ood" in models:
        joblib.dump(models["ood"], path / ("%s_ood.joblib" % block))


def load_models(version_dir: Path, block: str) -> Dict[str, Any]:
    path = Path(version_dir) / "models"
    models = joblib.load(path / ("%s_representation.joblib" % block))
    ood_path = path / ("%s_ood.joblib" % block)
    if ood_path.exists():
        models["ood"] = joblib.load(ood_path)
    return models


def save_combined_validation_space(version_dir: Path, keys: Sequence[str],
                                   model_space: np.ndarray) -> None:
    joblib.dump({"source_keys": [str(key) for key in keys],
                 "model_space": np.asarray(model_space, dtype=float)},
                Path(version_dir) / "models" / "combined_validation_space.joblib")


def load_combined_validation_space(version_dir: Path) -> Tuple[List[str], Optional[np.ndarray]]:
    path = Path(version_dir) / "models" / "combined_validation_space.joblib"
    if not path.exists():
        return [], None
    payload = joblib.load(path)
    return list(payload.get("source_keys", [])), np.asarray(payload.get("model_space"), dtype=float)


def merge_validation_space(old_keys: Sequence[str], old_space: Optional[np.ndarray],
                           new_keys: Sequence[str], new_space: np.ndarray
                           ) -> Tuple[List[str], np.ndarray]:
    replacements = {str(key): np.asarray(new_space[index], dtype=float)
                    for index, key in enumerate(new_keys)}
    keys: List[str] = []
    rows: List[np.ndarray] = []
    if old_space is not None:
        for index, key in enumerate(old_keys):
            token = str(key)
            keys.append(token)
            rows.append(replacements.pop(token, np.asarray(old_space[index], dtype=float)))
    for key in new_keys:
        token = str(key)
        if token in keys:
            continue
        keys.append(token)
        rows.append(replacements[token])
    return keys, np.vstack(rows)


def finalisation_checkpoint_path(version_dir: Path) -> Path:
    return Path(version_dir) / "cache" / "finalisation_checkpoint.joblib"


def source_key_digest(records: Sequence[Mapping[str, Any]]) -> str:
    identities = sorted((
        str(record.get("summary", {}).get("source_key", "")),
        str(record.get("summary", {}).get("file_fingerprint", "")),
        _utils.finite_float(record.get("summary", {}).get("recommended_period_days"), np.nan),
    ) for record in records)
    return _utils.hash_json(identities)


def manual_labels_fingerprint(config: Mapping[str, Any]) -> str:
    configured = config.get("manual_labels_file")
    path = Path(configured) if configured else Path(config["output_root"]) / "manual_labels.csv"
    return _utils.file_fingerprint(path)


def save_finalisation_checkpoint(version_dir: Path, payload: Mapping[str, Any]) -> None:
    """Atomically save the completed scientific stage before output generation."""
    destination = finalisation_checkpoint_path(version_dir)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".tmp.joblib")
    joblib.dump(dict(payload), temporary, compress=3)
    temporary.replace(destination)


def load_finalisation_checkpoint(version_dir: Path, records: Sequence[Mapping[str, Any]],
                                 config: Mapping[str, Any], mode: str,
                                 logger: logging.Logger) -> Optional[Dict[str, Any]]:
    path = finalisation_checkpoint_path(version_dir)
    if (not bool(config.get("resume_finalisation", True))
            or bool(config.get("force_recompute_features", False))
            or not path.exists()):
        return None
    try:
        payload = joblib.load(path)
    except Exception as error:
        logger.warning("Ignoring unreadable finalisation checkpoint: %s", error)
        return None
    expected = {
        "schema": S.FEATURE_SCHEMA_VERSION,
        "science_config_hash": science_config_hash(config),
        "feature_config_hash": _features.feature_config_hash(config),
        "mode": mode,
        "source_key_digest": source_key_digest(records),
        "manual_labels_fingerprint": manual_labels_fingerprint(config),
    }
    if any(payload.get(key) != value for key, value in expected.items()):
        logger.warning("Ignoring incompatible finalisation checkpoint at %s", path)
        return None
    table = payload.get("table")
    if not isinstance(table, pd.DataFrame) or len(table) != len(records):
        logger.warning("Ignoring incomplete finalisation checkpoint at %s", path)
        return None
    logger.info("Resuming from completed UMAP/classification checkpoint (%d sources)",
                len(table))
    return payload


def clear_finalisation_checkpoint(version_dir: Path) -> None:
    path = finalisation_checkpoint_path(version_dir)
    if path.exists():
        try:
            path.unlink()
        except OSError:
            pass


def clean_full_feature_cache(version_dir: Path, logger: logging.Logger) -> None:
    """Retain small resumable summaries but remove full light-curve cache copies."""
    if not Path(version_dir, "cache").exists():
        return
    removed = 0
    for path in Path(version_dir, "cache").glob("*.joblib"):
        if path.name.endswith(".light.joblib") or path.name == "finalisation_checkpoint.joblib":
            continue
        try:
            path.unlink()
            removed += 1
        except OSError:
            pass
    logger.info("Removed %d full feature-cache files; compact .light caches retained", removed)


# ===========================================================================
# MODES
# ===========================================================================


def version_directory(output_root: Path, version: Optional[str]) -> Path:
    """Saved numerical state is separate from the user-facing plot folder."""
    return Path(output_root) / "saved_runs" / (_utils.safe_name(str(version)) if version else "default")


def resolve_version_dir(output_root: Path, requested: Optional[str]) -> Tuple[str, Path]:
    version = str(requested) if requested else ""
    if not version:
        pointer = Path(output_root) / "current_model.json"
        if pointer.exists():
            version = json.loads(pointer.read_text(encoding="utf-8")).get("model_version", "") or ""
    directory = version_directory(output_root, version)
    legacy = Path(output_root) / "model_versions"
    if version:
        legacy = legacy / ("model_%s" % version)
    if not directory.exists() and legacy.exists():
        directory = legacy
    return version, directory


def update_current_pointer(output_root: Path, version: str, version_dir: Path) -> None:
    _utils.atomic_write_json({"model_version": version, "model_directory": str(version_dir),
                       "updated": _utils.iso_now()}, Path(output_root) / "current_model.json")


def science_config_hash(config):
    """Fitted embeddings/rules invalidate independently of display choices."""
    from .. import resume as R
    ignored = {'output_root', 'datasets', 'mode', 'model_version', 'batch_id',
        'maps_to_plot', 'dataset_markers', 'outline_new_sources', 'n_jobs',
        'force_recompute_features', 'overwrite_existing_model', 'resume_finalisation',
        'force_replot_phase_products', 'existing_id_policy', 'clean_full_feature_cache_after_success'}
    return R.hash_value({k: v for k, v in config.items() if k not in ignored
                        and not k.startswith(('_', 'make_', 'review_plot_', 'appendix_'))})
