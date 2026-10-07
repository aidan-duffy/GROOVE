from __future__ import annotations
import logging
import math
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.impute import SimpleImputer
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import RobustScaler
from . import settings as S
from . import classify as _classify
from . import persistence as _persistence
from . import utils as _utils




def feature_matrix(records: Sequence[Mapping[str, Any]], block: str) -> Tuple[np.ndarray, List[str]]:
    if block == "combined":
        # Join the two scientific views without counting shared descriptors
        # twice.  Labels and category scores are deliberately absent.
        periodic_names = list(records[0]["periodic_names"])
        transient_names = list(records[0]["transient_names"])
        keep_transient = [i for i, name in enumerate(transient_names)
                          if name not in set(periodic_names)]
        names = periodic_names + [transient_names[i] for i in keep_transient]
        rows = []
        for record in records:
            periodic = np.asarray(record["periodic_features"], dtype=float)
            transient = np.asarray(record["transient_features"], dtype=float)
            rows.append(np.concatenate([periodic, transient[keep_transient]]))
        return np.vstack(rows), names
    names = list(records[0]["%s_names" % block])
    matrix = np.vstack([np.asarray(r["%s_features" % block], dtype=float) for r in records])
    return matrix, names


def make_imputer() -> SimpleImputer:
    """SimpleImputer that works on both old and new scikit-learn.

    `keep_empty_features` was added in scikit-learn 1.2. Without it, a column
    that is entirely NaN is silently DROPPED, which would change the feature
    count between fit and transform and corrupt the frozen map. Where the
    argument is unavailable we instead guarantee no column is ever all-NaN
    (see sanitise_matrix), so nothing can be dropped.
    """
    try:
        import inspect
        if "keep_empty_features" in inspect.signature(SimpleImputer).parameters:
            return SimpleImputer(strategy="median", keep_empty_features=True)
    except (TypeError, ValueError):
        pass
    return SimpleImputer(strategy="median")


def sanitise_matrix(matrix: np.ndarray, empty_columns: Optional[np.ndarray] = None
                    ) -> Tuple[np.ndarray, np.ndarray]:
    """Force non-finite values to NaN and zero-fill columns with no data at all.

    Returns the cleaned matrix and the mask of all-empty columns, so transform
    can apply exactly the same fill the fit used.
    """
    work = np.array(matrix, dtype=float, copy=True)
    work[~np.isfinite(work)] = np.nan
    if empty_columns is None:
        empty_columns = np.all(np.isnan(work), axis=0)
    else:
        empty_columns = np.asarray(empty_columns, dtype=bool)
        if empty_columns.shape[0] != work.shape[1]:
            empty_columns = np.all(np.isnan(work), axis=0)
    if empty_columns.any():
        work[:, empty_columns] = 0.0
    # A column all-NaN only in THIS batch would still be dropped by an old
    # imputer, so fill those too.
    still_empty = np.all(np.isnan(work), axis=0)
    if still_empty.any():
        work[:, still_empty] = 0.0
    return work, empty_columns


def feature_group(name: str) -> str:
    """Return the explicit scientific block for one representation feature."""
    if name.startswith("aligned_phase_bin_"):
        return "aligned_phase_profile"
    if name.startswith("fourier_") or name in S.FOURIER_FEATURES:
        return "fourier_shape"
    if name in S.MORPHOLOGY_FEATURES or name.startswith("section"):
        return "morphology_descriptors"
    if name in S.PERIODIC_SIGNIFICANCE_FEATURES:
        return "periodic_significance"
    if "amplitude" in name:
        return "amplitude"
    if any(token in name for token in ("error", "scatter", "coverage", "quality", "point_fraction")):
        return "data_quality"
    if any(token in name for token in ("baseline_days", "n_observations")):
        return "observing_metadata"
    return "morphology_descriptors"


def post_scaling_feature_weights(names: Sequence[str], config: Mapping[str, Any]
                                 ) -> Tuple[np.ndarray, List[str]]:
    """Return effective multipliers applied after robust standardisation.

    The configured values are interpreted explicitly.  With
    ``distance_contribution`` (the default), square roots are applied because a
    dimension's contribution to squared Euclidean distance is the multiplier
    squared.  ``direct_multiplier`` retains the legacy interpretation.
    """
    configured = dict(S.DEFAULT_FEATURE_WEIGHTS)
    configured.update(config.get("feature_weights", {}) or {})
    groups = [feature_group(str(name)) for name in names]
    values = np.asarray([max(0.0, _utils.finite_float(configured.get(group), 1.0))
                         for group in groups], dtype=float)
    interpretation = str(config.get(
        "feature_weight_interpretation", "distance_contribution")).strip().lower()
    weights = np.sqrt(values) if interpretation == "distance_contribution" else values
    return weights, groups


def adaptive_umap_neighbors(n_sources: int) -> int:
    """Sample-size-aware default that does not use category counts."""
    return int(min(15, max(5, round(math.sqrt(max(1, n_sources))))))


def representation_settings(config: Mapping[str, Any], block: str,
                            n_sources: int) -> Dict[str, Any]:
    """Resolve independent settings for one saved map."""
    raw_neighbours = config.get("%s_umap_n_neighbors" % block)
    if raw_neighbours in (None, "", "adaptive"):
        neighbours = adaptive_umap_neighbors(n_sources)
        neighbour_reason = "adaptive_sqrt_n_capped_5_to_15"
    else:
        neighbours = int(raw_neighbours)
        neighbour_reason = "configured"
    neighbours = int(min(max(2, neighbours), max(2, n_sources - 1)))
    default_metric = "euclidean" if block == "evidence" else "cosine"
    return {
        "n_neighbors": neighbours,
        "min_dist": float(config.get("%s_umap_min_dist" % block, 0.08)),
        "metric": str(config.get("%s_umap_metric" % block, default_metric)),
        "neighbour_reason": neighbour_reason,
        "selection_reason": ("sample_size_adaptive_label_blind_default"
                             if neighbour_reason.startswith("adaptive")
                             else "explicit_per_map_configuration"),
    }


def fit_representation(matrix: np.ndarray, config: Mapping[str, Any],
                       logger: logging.Logger,
                       names: Optional[Sequence[str]] = None,
                       block: str = "combined",
                       selected: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    import umap
    matrix, empty_columns = sanitise_matrix(matrix)
    imputer = make_imputer()
    scaler = RobustScaler()
    base = imputer.fit_transform(matrix)
    if base.shape[1] != matrix.shape[1]:
        raise SystemExit(
            "Imputer dropped %d feature column(s); scikit-learn is too old and the "
            "empty-column guard failed. Install scikit-learn>=1.2."
            % (matrix.shape[1] - base.shape[1]))
    work = scaler.fit_transform(base)
    weights, groups = post_scaling_feature_weights(names or [], config) if names is not None\
        else (np.ones(work.shape[1], dtype=float), ["morphology_descriptors"] * work.shape[1])
    if weights.shape[0] != work.shape[1]:
        weights = np.ones(work.shape[1], dtype=float)
        groups = ["morphology_descriptors"] * work.shape[1]
    work = work * weights
    pca = None
    selected = dict(selected or {})
    pca_mode = str(selected.get(
        "pca_mode", "variance_95" if bool(config.get("use_pca", False)) else "none"))
    if pca_mode != "none" and work.shape[0] > 3:
        if pca_mode == "variance_95":
            retained = float(config.get("pca_variance_retained", 0.95))
            pca = PCA(n_components=retained, svd_solver="full",
                      random_state=int(config.get("random_seed", 42)))
            work = pca.fit_transform(work)
            keep = int(work.shape[1])
        else:
            components = min(20, int(config.get("pca_max_components", 50)),
                             work.shape[0] - 1, work.shape[1])
            if components < 2:
                components = 0
            if components:
                pca = PCA(n_components=components,
                          random_state=int(config.get("random_seed", 42)))
                work = pca.fit_transform(work)
                keep = int(work.shape[1])
        if pca is not None:
            logger.info("PCA retained %d components (%.3f variance)",
                        keep, float(np.sum(pca.explained_variance_ratio_)))
    settings = representation_settings(config, block, work.shape[0])
    settings.update({key: selected[key] for key in ("n_neighbors", "min_dist", "metric")
                     if key in selected})
    if "selection_reason" in selected:
        settings["selection_reason"] = str(selected["selection_reason"])
        settings["neighbour_reason"] = "selected_by_optional_parameter_comparison"
    n_neighbors = int(min(int(settings["n_neighbors"]), max(2, work.shape[0] - 1)))
    reducer = umap.UMAP(
        n_neighbors=n_neighbors, min_dist=float(settings["min_dist"]),
        metric=str(settings["metric"]), n_components=2,
        random_state=int(config.get("random_seed", 42)), verbose=False)
    embedding = reducer.fit_transform(work)
    settings["n_neighbors"] = n_neighbors
    settings["pca_mode"] = pca_mode
    return {"imputer": imputer, "scaler": scaler, "pca": pca, "umap": reducer,
            "empty_columns": empty_columns, "post_scale_weights": weights,
            "feature_groups": groups,
            "configured_feature_weights": dict(config.get("feature_weights", {}) or {}),
            "feature_weight_interpretation": str(config.get(
                "feature_weight_interpretation", "distance_contribution")),
            "selected_settings": settings,
            "model_space": work, "embedding": np.asarray(embedding, dtype=float)}


def transform_representation(models: Mapping[str, Any], matrix: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    matrix, _ = sanitise_matrix(matrix, models.get("empty_columns"))
    work = models["scaler"].transform(models["imputer"].transform(matrix))
    weights = models.get("post_scale_weights", models.get("emphasis"))
    if weights is not None and np.shape(weights)[0] == work.shape[1]:
        work = work * weights
    if models.get("pca") is not None:
        work = models["pca"].transform(work)
    return np.asarray(models["umap"].transform(work), dtype=float), work


def fit_evidence_representation(table: pd.DataFrame, config: Mapping[str, Any],
                                logger: logging.Logger) -> Dict[str, Any]:
    """Fit a transformable UMAP of continuous classifier evidence.

    This is intentionally separate from every label-blind morphology reducer.
    It receives neither discrete family labels nor supervised UMAP targets.
    """
    import umap
    work = _classify.classification_evidence_matrix(table)
    settings = representation_settings(config, "evidence", len(work))
    settings["metric"] = "euclidean"
    reducer = umap.UMAP(
        n_neighbors=int(settings["n_neighbors"]),
        min_dist=float(settings["min_dist"]), metric="euclidean",
        n_components=2, random_state=int(config.get("random_seed", 42)), verbose=False)
    embedding = np.asarray(reducer.fit_transform(work), dtype=float)
    logger.info("Classification-evidence UMAP fitted from continuous scores only")
    return {"umap": reducer, "model_space": work, "embedding": embedding,
            "category_score_columns": list(S.CATEGORY_SCORE_COLUMNS),
            "selected_settings": settings}


def transform_evidence_representation(models: Mapping[str, Any],
                                      table: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
    expected = tuple(models.get("category_score_columns", S.CATEGORY_SCORE_COLUMNS))
    if expected != tuple(S.CATEGORY_SCORE_COLUMNS):
        raise SystemExit("Saved classification-evidence score ordering is incompatible.")
    work = _classify.classification_evidence_matrix(table)
    return np.asarray(models["umap"].transform(work), dtype=float), work


def calibrated_threshold(values: Sequence[float], quantile: float, minimum: float = 0.0) -> float:
    array = np.asarray([v for v in values if np.isfinite(v)], dtype=float)
    if not len(array):
        return float("inf")
    return float(max(np.quantile(array, float(np.clip(quantile, 0.5, 0.999))), minimum))


def fit_ood_model(model_space: np.ndarray, config: Mapping[str, Any]) -> Dict[str, Any]:
    k = int(min(6, max(2, model_space.shape[0] - 1)))
    nn = NearestNeighbors(n_neighbors=k).fit(model_space)
    distances, _ = nn.kneighbors(model_space)
    typical = distances[:, 1:].mean(axis=1)
    scale = calibrated_threshold(typical, float(config.get("ood_quantile", 0.99)), 1e-9)
    return {"model": nn, "scale": float(scale)}


def ood_scores(ood: Mapping[str, Any], model_space: np.ndarray) -> np.ndarray:
    distances, _ = ood["model"].kneighbors(model_space)
    typical = distances[:, 1:].mean(axis=1) if distances.shape[1] > 1 else distances[:, 0]
    return np.asarray(typical / max(ood["scale"], 1e-9), dtype=float)


def comparison_model_spaces(matrix: np.ndarray, names: Sequence[str],
                            config: Mapping[str, Any]) -> Dict[str, np.ndarray]:
    """Prepare the three requested PCA alternatives for an optional sweep."""
    clean, _ = sanitise_matrix(matrix)
    imputed = make_imputer().fit_transform(clean)
    scaled = RobustScaler().fit_transform(imputed)
    weights, _ = post_scaling_feature_weights(names, config)
    base = scaled * weights
    spaces = {"none": np.asarray(base, dtype=float)}
    if min(base.shape) >= 3:
        try:
            spaces["variance_95"] = PCA(
                n_components=0.95, svd_solver="full",
                random_state=int(config.get("random_seed", 42))).fit_transform(base)
        except ValueError:
            spaces["variance_95"] = base
        components = min(20, base.shape[0] - 1, base.shape[1])
        spaces["max_20"] = PCA(
            n_components=max(2, components),
            random_state=int(config.get("random_seed", 42))).fit_transform(base)
    return spaces


def mean_score_similarity(scores: np.ndarray, neighbour_indices: np.ndarray) -> float:
    norms = np.linalg.norm(scores, axis=1)
    values: List[float] = []
    for index, neighbours in enumerate(neighbour_indices):
        denominator = norms[index] * norms[neighbours]
        similarities = np.divide(
            scores[neighbours].dot(scores[index]), denominator,
            out=np.zeros_like(denominator), where=denominator > 0)
        values.extend(similarities.tolist())
    return float(np.mean(values)) if values else np.nan


def umap_parameter_comparison(matrix: np.ndarray, names: Sequence[str],
                              table: pd.DataFrame, config: Mapping[str, Any],
                              logger: logging.Logger
                              ) -> Tuple[pd.DataFrame, Optional[Dict[str, Any]]]:
    """Optional label-blind sweep selected by geometry-preservation metrics.

    Discrete labels are used only for reported diagnostic silhouettes and
    neighbour agreement.  They are never passed to PCA or UMAP and do not enter
    the selection score.
    """
    if not bool(config.get("run_umap_parameter_comparison", False)):
        return pd.DataFrame(), None
    import umap
    from scipy.sparse.csgraph import connected_components
    from sklearn.manifold import trustworthiness
    from sklearn.metrics import silhouette_score

    spaces = comparison_model_spaces(matrix, names, config)
    labels = table["suggested_primary_tag"].astype(str).to_numpy()
    scores = _classify.classification_evidence_matrix(table) ** 2
    seed = int(config.get("random_seed", 42))
    rows: List[Dict[str, Any]] = []
    for pca_mode, model_space in spaces.items():
        for neighbours in (5, 8, 10, 13, 15, 30):
            k = int(min(neighbours, max(2, len(model_space) - 1)))
            for min_dist in (0.00, 0.03, 0.08, 0.15):
                for metric in ("euclidean", "cosine"):
                    original_nn = NearestNeighbors(
                        n_neighbors=min(6, len(model_space)), metric=metric).fit(model_space)
                    original_indices = original_nn.kneighbors(
                        model_space, return_distance=False)[:, 1:]
                    reducers, embeddings = [], []
                    for trial_seed in (seed, seed + 1, seed + 2):
                        reducer = umap.UMAP(
                            n_neighbors=k, min_dist=min_dist, metric=metric,
                            n_components=2, random_state=trial_seed, verbose=False)
                        embeddings.append(np.asarray(
                            reducer.fit_transform(model_space), dtype=float))
                        reducers.append(reducer)
                    embedded_indices = NearestNeighbors(
                        n_neighbors=min(6, len(model_space))).fit(embeddings[0]).kneighbors(
                            embeddings[0], return_distance=False)[:, 1:]
                    preservation = float(np.mean([
                        len(set(original_indices[i]) & set(embedded_indices[i])) /
                        max(1, len(original_indices[i]))
                        for i in range(len(model_space))]))
                    category_agreement = float(np.mean([
                        np.mean(labels[row_indices] == labels[i])
                        for i, row_indices in enumerate(embedded_indices)]))
                    sample = np.linspace(0, len(model_space) - 1,
                                         min(len(model_space), 500), dtype=int)
                    upper = np.triu_indices(len(sample), 1)
                    pairwise_distances_2d = [
                        np.linalg.norm(embedding[sample, None, :] -
                                       embedding[None, sample, :], axis=2)[upper]
                        for embedding in embeddings]
                    stability_values = [
                        _utils.safe_corr(pairwise_distances_2d[i], pairwise_distances_2d[j],
                                  minimum=10)
                        for i in range(3) for j in range(i + 1, 3)]
                    stability = float(np.nanmean(stability_values))
                    graph = reducers[0].graph_
                    components = int(connected_components(
                        graph.maximum(graph.T), directed=False)[0])
                    trust_k = min(10, max(1, len(model_space) // 2 - 1))
                    try:
                        original_silhouette = float(silhouette_score(
                            model_space, labels, metric=metric))
                        embedded_silhouette = float(silhouette_score(
                            embeddings[0], labels, metric="euclidean"))
                    except ValueError:
                        original_silhouette = embedded_silhouette = np.nan
                    trust = float(trustworthiness(
                        model_space, embeddings[0], n_neighbors=trust_k,
                        metric=metric))
                    score_similarity = mean_score_similarity(scores, embedded_indices)
                    selection_score = (0.35 * trust + 0.30 * max(0.0, stability)
                                       + 0.25 * preservation
                                       + 0.10 * max(0.0, score_similarity)
                                       - 0.03 * max(0, components - 1))
                    rows.append({
                        "pca_mode": pca_mode,
                        "n_neighbors": neighbours, "effective_n_neighbors": k,
                        "min_dist": min_dist, "metric": metric,
                        "trustworthiness": trust,
                        "original_to_2d_neighbour_preservation": preservation,
                        "nearest_neighbour_score_similarity": score_similarity,
                        "nearest_neighbour_category_agreement_diagnostic": category_agreement,
                        "original_space_silhouette_diagnostic": original_silhouette,
                        "embedding_silhouette_diagnostic": embedded_silhouette,
                        "embedding_stability_across_three_seeds": stability,
                        "number_of_disconnected_components": components,
                        "selection_score_without_category_separation": selection_score,
                    })
    result = pd.DataFrame(rows)
    if result.empty:
        return result, None
    best_index = int(result["selection_score_without_category_separation"].idxmax())
    best = result.loc[best_index]
    if str(best["pca_mode"]) != "none":
        no_pca_index = int(result.loc[result["pca_mode"].eq("none"),
                                      "selection_score_without_category_separation"].idxmax())
        no_pca = result.loc[no_pca_index]
        pca_is_justified = (
            best["trustworthiness"] > no_pca["trustworthiness"] + 0.005
            and best["embedding_stability_across_three_seeds"] >=
            no_pca["embedding_stability_across_three_seeds"] - 0.02
            and best["nearest_neighbour_score_similarity"] >=
            no_pca["nearest_neighbour_score_similarity"] - 0.03)
        if not pca_is_justified:
            best_index, best = no_pca_index, no_pca
    result["selected"] = False
    result.loc[best_index, "selected"] = True
    reason = ("maximised trustworthiness, seed stability, and original-neighbour "
              "preservation; category agreement was diagnostic only")
    result["selection_reason"] = ""
    result.loc[best_index, "selection_reason"] = reason
    selected = {
        "pca_mode": str(best["pca_mode"]),
        "n_neighbors": int(best["effective_n_neighbors"]),
        "min_dist": float(best["min_dist"]),
        "metric": str(best["metric"]),
        "selection_reason": reason,
    }
    logger.info("UMAP parameter comparison completed for %d label-blind settings; selected %s",
                len(result), selected)
    return result, selected


def validation_feature_space(table: pd.DataFrame) -> Tuple[np.ndarray, List[str]]:
    names = [name for name in S.VALIDATION_FEATURES if name in table.columns]
    if not names:
        return np.zeros((len(table), 1), dtype=float), ["constant"]
    matrix = table[names].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
    matrix, _ = sanitise_matrix(matrix)
    matrix = make_imputer().fit_transform(matrix)
    matrix = RobustScaler().fit_transform(matrix)
    return np.asarray(matrix, dtype=float), names


def nearest_neighbour_validation(
        table: pd.DataFrame, config: Mapping[str, Any],
        combined_space: Optional[np.ndarray] = None,
        combined_keys: Optional[Sequence[str]] = None,
        logger: Optional[logging.Logger] = None,
        ) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Validate whether the combined morphology neighbours survive projection."""
    work = table.copy()
    if len(work) < 2:
        return work, pd.DataFrame(), pd.DataFrame()
    feature_space: np.ndarray
    if combined_space is not None and combined_keys is not None:
        lookup = {str(key): index for index, key in enumerate(combined_keys)}
        ordered = [lookup.get(str(key)) for key in work["source_key"]]
        if all(index is not None for index in ordered):
            feature_space = np.asarray(combined_space, dtype=float)[ordered]
        else:
            feature_space, _ = validation_feature_space(work)
            if logger:
                logger.warning("Combined validation space was incomplete; using saved scalar features")
    else:
        feature_space, _ = validation_feature_space(work)
    original_metric = str(config.get(
        "_selected_combined_metric", config.get("combined_umap_metric", "cosine")))
    max_k = min(11, len(work))
    feature_nn = NearestNeighbors(
        n_neighbors=max_k, metric=original_metric).fit(feature_space)
    feature_dist, feature_idx = feature_nn.kneighbors(feature_space)
    embedding_columns = ["combined_umap_1", "combined_umap_2"]
    if not set(embedding_columns).issubset(work.columns):
        embedding_columns = ["periodic_umap_1", "periodic_umap_2"]
    embedding = work[embedding_columns].to_numpy(dtype=float)
    embedding_nn = NearestNeighbors(n_neighbors=max_k).fit(embedding)
    umap_dist, umap_idx = embedding_nn.kneighbors(embedding)
    ids = work["source_id"].astype(str).to_numpy()
    labels = work["final_primary_tag"].astype(str).to_numpy()
    scores = _classify.classification_evidence_matrix(work) ** 2
    work["nearest_original_feature_source_id"] = ids[feature_idx[:, 1]]
    work["nearest_original_feature_distance"] = feature_dist[:, 1]
    work["nearest_umap_source_id"] = ids[umap_idx[:, 1]]
    work["nearest_umap_distance"] = umap_dist[:, 1]
    for count in (5, 10):
        effective = min(count, len(work) - 1)
        original_neighbours = feature_idx[:, 1:effective + 1]
        work["original_%d_category_agreement" % count] = [
            float(np.mean(labels[row_indices] == labels[i]))
            for i, row_indices in enumerate(original_neighbours)]
        work["original_%d_mean_score_similarity" % count] = [
            mean_score_similarity(scores[[i] + row_indices.tolist()],
                                  np.asarray([np.arange(1, effective + 1)]))
            for i, row_indices in enumerate(original_neighbours)]
    umap_five = umap_idx[:, 1:min(6, len(work))]
    work["umap_5_category_agreement"] = [
        float(np.mean(labels[row_indices] == labels[i]))
        for i, row_indices in enumerate(umap_five)]
    work["umap_5_mean_score_similarity"] = [
        mean_score_similarity(scores[[i] + row_indices.tolist()],
                              np.asarray([np.arange(1, len(row_indices) + 1)]))
        for i, row_indices in enumerate(umap_five)]
    work["nearest_original_neighbour_preserved_in_2d"] = [
        bool(feature_idx[i, 1] in set(umap_five[i])) for i in range(len(work))]
    # Compatibility name retained for downstream notebooks.
    work["nearest_neighbour_category_agreement"] = work["original_5_category_agreement"]

    from sklearn.metrics import pairwise_distances, silhouette_samples
    lightweight = bool(config.get("_plot_only_lightweight_validation", False))
    try:
        if lightweight:
            raise ValueError("expensive validation metrics skipped for plot-only mode")
        work["original_space_silhouette_contribution"] = silhouette_samples(
            feature_space, labels, metric=original_metric)
        work["umap_silhouette_contribution"] = silhouette_samples(
            embedding, labels, metric="euclidean")
    except ValueError:
        work["original_space_silhouette_contribution"] = np.nan
        work["umap_silhouette_contribution"] = np.nan
    sorted_scores = np.sort(scores, axis=1)
    work["classification_score_margin"] = sorted_scores[:, -1] - sorted_scores[:, -2]
    work["distance_to_category_typical_example"] = np.nan
    if not lightweight:
        for category in S.PRIMARY_CATEGORIES:
            indices = np.flatnonzero(labels == category)
            if not len(indices):
                continue
            distances = pairwise_distances(
                feature_space[indices], feature_space[indices], metric=original_metric)
            typical = int(indices[int(np.argmin(distances.sum(axis=1)))])
            work.loc[work.index[indices], "distance_to_category_typical_example"] =\
                pairwise_distances(feature_space[indices], feature_space[[typical]],
                                   metric=original_metric).ravel()

    anchor_indices: List[int] = []
    desired = ("transit", "wavelike", "irregular_variable", "flaring", "nonvar", "noisy")
    for category in desired:
        candidates = np.flatnonzero(labels == category)
        if len(candidates):
            strengths = np.asarray([_classify.strength_score(work.iloc[i]) for i in candidates])
            anchor_indices.append(int(candidates[int(np.argmax(strengths))]))
    requested = [_utils.clean_source_id(value) for value in config.get("neighbour_anchor_sources", [])]
    for source_id in requested:
        found = np.flatnonzero(ids == source_id)
        if len(found):
            anchor_indices.append(int(found[0]))
    anchor_indices = list(dict.fromkeys(anchor_indices))

    rows: List[Dict[str, Any]] = []
    count = int(min(int(config.get("nearest_reference_neighbours", 5)), len(work) - 1))
    for anchor in anchor_indices:
        for rank, neighbour in enumerate(feature_idx[anchor, 1:count + 1], start=1):
            rows.append({
                "anchor_source_id": ids[anchor],
                "anchor_source_key": str(work.iloc[anchor]["source_key"]),
                "anchor_primary_category": labels[anchor],
                "anchor_secondary_tags": work.iloc[anchor].get("final_secondary_tags", ""),
                "anchor_interest_status": work.iloc[anchor].get("interest_status", ""),
                "neighbour_rank": rank,
                "neighbour_source_id": ids[neighbour],
                "neighbour_source_key": str(work.iloc[neighbour]["source_key"]),
                "original_feature_distance": float(feature_dist[anchor, rank]),
                "umap_distance": float(np.linalg.norm(embedding[anchor] - embedding[neighbour])),
                "neighbour_primary_category": labels[neighbour],
                "neighbour_secondary_tags": work.iloc[neighbour].get("final_secondary_tags", ""),
                "neighbour_interest_status": work.iloc[neighbour].get("interest_status", ""),
                "same_primary_category": bool(labels[anchor] == labels[neighbour]),
            })
    category_summary = (
        work.groupby("final_primary_tag", sort=False)
        .agg(n_sources=("source_key", "count"),
             original_space_neighbour_agreement=("original_5_category_agreement", "mean"),
             umap_neighbour_agreement=("umap_5_category_agreement", "mean"),
             original_space_silhouette_contribution=(
                 "original_space_silhouette_contribution", "mean"),
             umap_silhouette_contribution=("umap_silhouette_contribution", "mean"),
             median_score_margin=("classification_score_margin", "median"),
             median_distance_to_typical_example=(
                 "distance_to_category_typical_example", "median"))
        .reset_index())
    return work, pd.DataFrame(rows), category_summary


def merge_transformed_sources(old: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    """Append transformed rows while preserving every non-replaced coordinate."""
    if old.empty:
        return new.copy()
    replacement_keys = set(new["source_key"].astype(str))
    carried = old.loc[~old["source_key"].astype(str).isin(replacement_keys)].copy()
    coordinate_columns = [name for name in (
        "periodic_umap_1", "periodic_umap_2", "transient_umap_1", "transient_umap_2")
        if name in carried.columns]
    before = carried[["source_key"] + coordinate_columns].copy()
    carried["is_latest_batch"] = False
    combined = pd.concat([carried, new], ignore_index=True, sort=False)
    after = combined.loc[combined["source_key"].astype(str).isin(
        set(before["source_key"].astype(str))), ["source_key"] + coordinate_columns]
    after = after.set_index("source_key").loc[before["source_key"].astype(str)].reset_index()
    if coordinate_columns and not np.allclose(
            before[coordinate_columns].to_numpy(dtype=float),
            after[coordinate_columns].to_numpy(dtype=float), equal_nan=True):
        raise RuntimeError("Existing UMAP coordinates changed while appending transformed sources")
    return combined


def frozen_source_neighbours(table: pd.DataFrame, version_dir: Path,
                             source_id: str, count: int) -> Tuple[pd.DataFrame, List[str]]:
    """Return high-dimensional and 2-D neighbours without fitting any map."""
    validation_keys, model_space = _persistence.load_combined_validation_space(version_dir)
    if model_space is None or not validation_keys:
        raise SystemExit("Saved combined_validation_space.joblib is required.")
    source_id = _utils.clean_source_id(source_id)
    work = table.copy()
    work["source_key"] = work["source_key"].astype(str)
    source_rows = work.loc[work["source_id"].astype(str).map(_utils.clean_source_id).eq(source_id)]
    if source_rows.empty:
        raise SystemExit("Source %s is not present in all_sources.csv." % source_id)
    source_key = str(source_rows.iloc[0]["source_key"])
    key_to_model_index = {str(key): index for index, key in enumerate(validation_keys)}
    if source_key not in key_to_model_index:
        raise SystemExit("Source %s is absent from the saved validation feature space." % source_id)
    table_lookup = work.set_index("source_key", drop=False)
    target_index = key_to_model_index[source_key]
    count = max(1, min(int(count), len(validation_keys) - 1))
    try:
        combined_models = _persistence.load_models(version_dir, "combined")
        metric = str(combined_models.get("selected_settings", {}).get("metric", "cosine"))
    except FileNotFoundError:
        metric = "cosine"
    high_model = NearestNeighbors(n_neighbors=count + 1, metric=metric, algorithm="brute")
    high_model.fit(model_space)
    high_distances, high_indices = high_model.kneighbors(model_space[[target_index]])

    rows: List[Dict[str, Any]] = []
    high_keys: List[str] = []
    for rank, (distance, index) in enumerate(
            zip(high_distances[0, 1:], high_indices[0, 1:]), start=1):
        key = str(validation_keys[int(index)])
        high_keys.append(key)
        row = table_lookup.loc[key]
        rows.append({
            "space": "standardised_combined_feature_space",
            "rank": rank,
            "source_key": key,
            "source_id": row.get("source_id", ""),
            "distance": float(distance),
            "distance_metric": metric,
            "final_primary_tag": row.get("final_primary_tag", ""),
            "recommended_period_days": row.get("recommended_period_days", np.nan),
            "final_secondary_tags": row.get("final_secondary_tags", ""),
            "selected_for_phase_grid": True,
        })

    finite = work.loc[np.isfinite(work["combined_umap_1"]) &
                      np.isfinite(work["combined_umap_2"])].copy()
    coordinates = finite[["combined_umap_1", "combined_umap_2"]].to_numpy(dtype=float)
    target_position = np.flatnonzero(finite["source_key"].astype(str).eq(source_key).to_numpy())
    if len(target_position):
        umap_model = NearestNeighbors(
            n_neighbors=min(count + 1, len(finite)), metric="euclidean")
        umap_model.fit(coordinates)
        map_distances, map_indices = umap_model.kneighbors(
            coordinates[[int(target_position[0])]])
        for rank, (distance, index) in enumerate(
                zip(map_distances[0, 1:], map_indices[0, 1:]), start=1):
            row = finite.iloc[int(index)]
            rows.append({
                "space": "combined_umap_2d_comparison_only",
                "rank": rank,
                "source_key": str(row["source_key"]),
                "source_id": row.get("source_id", ""),
                "distance": float(distance),
                "distance_metric": "euclidean",
                "final_primary_tag": row.get("final_primary_tag", ""),
                "recommended_period_days": row.get("recommended_period_days", np.nan),
                "final_secondary_tags": row.get("final_secondary_tags", ""),
                "selected_for_phase_grid": False,
            })
    return pd.DataFrame(rows), [source_key] + high_keys
