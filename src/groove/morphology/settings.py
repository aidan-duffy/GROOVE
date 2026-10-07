from __future__ import annotations
import math
import warnings
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
import matplotlib
from . import utils as _utils



matplotlib.use("Agg")

warnings.filterwarnings("ignore", category=RuntimeWarning)

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = SCRIPT_DIR / "defaults.yaml"
FEATURE_SCHEMA_VERSION = "atlas-umap-morphology-v3.2"

PRIMARY_CATEGORIES = (
    "transit", "wavelike", "flaring", "irregular_variable",
    "nonvar", "noisy", "unknown",
)

INTEREST_STATUSES = (
    "routine", "review", "exotic_candidate", "manually_confirmed_exotic",
)

# Continuous 0-1 morphology evidence. These scores are diagnostics and rule
# inputs; they are never passed to the unsupervised UMAP as target labels.
CATEGORY_SCORE_COLUMNS = (
    "score_transit", "score_wavelike", "score_flaring",
    "score_irregular_variable", "score_nonvar", "score_noisy", "score_unknown",
)

CATEGORY_COLOURS = {
    "transit": "#0072B2",
    "wavelike": "#56B4E9",
    "flaring": "#E69F00",
    "irregular_variable": "#CC79A7",
    "nonvar": "#009E73",
    "noisy": "#999999",
    "unknown": "#6F4E7C",
}

DEFAULT_FEATURE_WEIGHTS = {
    "aligned_phase_profile": 1.00,
    "fourier_shape": 0.50,
    "morphology_descriptors": 0.50,
    "periodic_significance": 0.15,
    "amplitude": 0.10,
    "data_quality": 0.05,
    "observing_metadata": 0.05,
}

# ===========================================================================
# USER SETTINGS
# ===========================================================================

USE_HARD_CODED_SETTINGS = False  # all configuration comes from YAML / the pipeline

HARD_CODED_DATASETS: list = []

HARD_CODED_SETTINGS: Dict[str, Any] = {}

# ===========================================================================
# DEFAULTS
# ===========================================================================

DEFAULTS: Dict[str, Any] = {
    "mode": "fit",
    "output_root": str(Path.home() / "UMAP_Morphology"),
    "model_version": None,
    "batch_id": None,
    "random_seed": 42,
    "datasets": [],
    "use_c_band": True,   # o band only
    "use_o_band": True,
    "minimum_observations": 50,
    "minimum_phase_coverage": 0.30,
    "allow_period_fallback": False,
    "period_conflict_relative_tolerance": 0.001,
    "number_of_phase_bins": 64,
    "umap_phase_bins": 32,
    "number_of_time_sections": 4,
    "feature_weights": dict(DEFAULT_FEATURE_WEIGHTS),
    "feature_weight_interpretation": "distance_contribution",
    "use_pca": False,
    "pca_variance_retained": 0.95,
    "pca_max_components": 50,
    "combined_umap_n_neighbors": None,
    "combined_umap_min_dist": 0.08,
    "combined_umap_metric": "cosine",
    "periodic_umap_n_neighbors": None,
    "periodic_umap_min_dist": 0.08,
    "periodic_umap_metric": "cosine",
    "transient_umap_n_neighbors": None,
    "transient_umap_min_dist": 0.08,
    "transient_umap_metric": "cosine",
    "evidence_umap_n_neighbors": None,
    "evidence_umap_min_dist": 0.08,
    "evidence_umap_metric": "euclidean",
    "ood_quantile": 0.99,
    "evolution_quantile": 0.95,
    "make_maps": True,
    "run_umap_parameter_comparison": False,
    "neighbour_anchor_sources": [],
    "nearest_reference_neighbours": 5,
    "make_review_plots": False,
    "make_category_folds": True,
    "make_category_appendix": True,
    "prefer_existing_period_plots": True,
    "generate_missing_source_plots": True,
    "allow_plot_copy_fallback": False,
    "clean_full_feature_cache_after_success": True,
    "cache_full_records_with_existing_period_plot": False,
    "resume_finalisation": True,
    "write_validation_sample": True,
    "validation_sample_size": 200,
    "appendix_per_page": 9,
    "appendix_max_pages": 0,
    "review_plot_dpi": 110,
    "n_jobs": -1,
    "existing_id_policy": "skip",
    "outline_new_sources": None,
    "force_recompute_features": False,
    "overwrite_existing_model": False,
    "manual_labels_file": None,
    "category_colours": CATEGORY_COLOURS,
    "thresholds": {
        # --- periodicity, in the recalibrated units of Section 2
        "periodic_chi2": 5.0,
        "periodic_chi2_strong": 25.0,
        "periodic_snr": 6.0,
        # --- data quality
        "poor_photometry_error": 0.25,
        "poor_photometry_amplitude_ratio": 3.0,
        # --- flares
        "event_sigma": 5.0,
        "flare_min_events": 4,
        "flare_min_points_per_event": 2,
        "flare_event_window_days": 1.0,
        "flare_min_event_snr": 5.0,
        "flare_min_asymmetry": 0.85,
        "flare_max_point_fraction": 0.10,
        "alias_relative_tolerance": 0.01,
        # --- transits
        "transit_min_dip_significance": 6.0,
        "dipper_min_dip_significance": 5.0,
        "eclipse_min_dip_dominance": 2.5,
        "dipper_min_dip_dominance": 1.8,
        "eclipse_max_duty_cycle": 0.25,
        "dipper_min_duty_cycle": 0.15,
        "dipper_max_duty_cycle": 0.60,
        "transit_min_cycles": 3,
        "transit_exceptional_two_cycle_score": 0.88,
        "transit_min_cycle_support_fraction": 0.45,
        "transit_min_supporting_sections": 2,
        "transit_max_duty_cycle": 0.65,
        "transit_score_threshold": 0.52,
        "transit_high_confidence_score": 0.72,
        "secondary_eclipse_fraction": 0.25,
        "eclipse_phase_tolerance": 0.08,
        "dip_like_dominance": 1.4,
        "transit_dominance_over_sinusoid": 3.0,
        "weak_shape_min_correlation": 0.70,
        "transit_max_baseline_variation": 0.35,
        "transit_min_dip_width_bins": 3.0,
        "dipper_max_baseline_variation": 0.55,
        "shape_min_section_correlation": 0.55,
        "flare_min_dominance": 3.0,
        "flare_max_duty_cycle": 0.35,
        "flare_max_baseline_variation": 0.25,
        "ls_strong_ratio": 40.0,
        "double_dip_fraction": 0.80,
        "flare_min_duty_fraction": 0.002,
        # --- shape
        "symmetry_min_correlation": 0.97,
        "filter_disagreement_correlation": 0.10,
        # --- flat / junk
        "ls_peak_ratio_coherent": 12.0,
        "nonvar_max_ls_peak_ratio": 40.0,
        "noisy_min_scatter_over_error": 4.0,
        "noisy_min_scatter_ratio": 3.0,
        "low_confidence": 0.60,
        # --- irregular time-domain variability
        "irregular_min_scatter_over_error": 2.0,
        "irregular_min_temporal_coherence": 0.42,
        "evolving_min_section_distance": 0.65,
        "evolving_max_section_correlation": 0.25,
        # --- wave/dimming model ambiguity
        "wave_dimming_ambiguity_margin": 0.10,
        # --- exotic-interest evidence (never an OOD/uncertainty threshold)
        "exotic_candidate_min_score": 0.70,
    },
}

# Settings that define the frozen representation.  Any change invalidates a
# saved model and requires an explicit refit.
FEATURE_CONFIG_KEYS = (
    "number_of_phase_bins", "umap_phase_bins", "number_of_time_sections",
    "feature_weights", "feature_weight_interpretation",
    "use_c_band", "use_o_band", "minimum_observations", "minimum_phase_coverage",
    "use_pca", "pca_variance_retained", "pca_max_components",
    "combined_umap_n_neighbors", "combined_umap_min_dist", "combined_umap_metric",
    "periodic_umap_n_neighbors", "periodic_umap_min_dist", "periodic_umap_metric",
    "transient_umap_n_neighbors", "transient_umap_min_dist", "transient_umap_metric",
    "evidence_umap_n_neighbors", "evidence_umap_min_dist", "evidence_umap_metric",
    "thresholds",
)

TIME_ALIASES = ("MJD", "###MJD", "mjd", "mjd_obs", "time", "time_mjd", "t", "jd")
FILTER_ALIASES = ("F", "filter", "Filter", "filt", "band", "passband")
MAG_ALIASES = ("m", "mag", "magnitude", "m_mag")
MAG_ERR_ALIASES = ("dm", "mag_err", "m_err", "emag", "magnitude_error", "e_mag", "magerr")
SOURCE_ID_ALIASES = (
    "target_GaiaDR3", "gaia_dr3", "GaiaDR3", "source_id", "gaia_source_id",
    "Gaia DR3 source_id", "target_id", "sourceid", "object_id", "atoid", "ATOID",
)
RECOMMENDED_PERIOD_ALIASES = (
    "recommended_period_days", "photometric_period_days", "consensus_period_days",
)
MAGNITUDE_RANGE = (2.0, 25.0)
FLUX_ALIASES = ("uJy", "ujy", "flux", "Flux")

SKIP_FILE_WORDS = (
    "cleaning_summary", "reason_counts", "period_search", "recommendation",
    "audit", "manifest_output", "processing_fail", "duplicate_sources",
    "selected_sources", "source_selection", "download_progress", "all_sources", "latest_batch", "category_summary", "review_queue",
)

MANUAL_LABEL_COLUMNS = (
    "source_id", "dataset", "manual_primary_tag", "manual_secondary_tags",
    "manual_interest_status", "manual_interest_reasons", "notes", "reviewer",
)


# Per-category strength score used to rank the appendix contact sheets.
STRENGTH_SCORES = {
    "transit": lambda r: _utils.finite_float(r.get("coherent_dimming_score"), 0.0),
    "wavelike": lambda r: _utils.finite_float(r.get("profile_chi2"), 0.0),
    "flaring": lambda r: min(_utils.finite_float(r.get("strongest_flare_sigma"), 0.0), 20.0)
    * math.log10(1.0 + _utils.finite_float(r.get("flare_event_count"), 0.0))
    * max(_utils.finite_float(r.get("flare_asymmetry"), 0.0), 0.0)
    * max(_utils.finite_float(r.get("flare_leave_one_event_out_persistent"), 0.0), 0.25),
    "irregular_variable": lambda r: _utils.finite_float(r.get("irregular_variability_score"), 0.0),
    "noisy": lambda r: _utils.finite_float(r.get("scatter_over_error"), 0.0),
    "nonvar": lambda r: -_utils.finite_float(r.get("scatter_over_error"), 9.9),
    "unknown": lambda r: _utils.finite_float(r.get("score_unknown"), 0.0),
}


FOURIER_FEATURES = {
    "mirror_symmetry", "profile_peak_count", "harmonic_energy_ratio", "skewness",
    "sinusoid_residual_ratio", "fourier_R21", "fourier_R31", "fourier_R41",
    "fourier_phi21", "fourier_phi31", "fourier_phi41",
}
MORPHOLOGY_FEATURES = {
    "dip_depth_norm", "flare_depth_norm", "dip_duty_cycle", "dip_width_bins",
    "dip_dominance", "secondary_dip_depth_norm", "secondary_dip_phase_separation",
    "out_of_dip_variation", "out_of_flare_variation", "flare_dominance",
    "flare_duty_cycle", "coherent_dimming_score", "dip_cycle_support_fraction",
    "dip_supporting_cycles", "dip_independent_nights", "dip_supporting_time_sections",
    "dip_local_contrast_sigma", "wave_model_score", "dimming_model_score",
    "dip_cycle_contrast_scatter",
    "wave_dimming_score_margin", "evolution_raw_score", "minimum_section_correlation",
    "maximum_section_distance", "section_amplitude_log_range", "temporal_coherence_score",
    "irregular_variability_score", "raw_time_lag1_correlation", "von_neumann_ratio",
    "same_direction_excursion_groups", "section_median_range_sigma",
}
PERIODIC_SIGNIFICANCE_FEATURES = {
    "profile_chi2", "profile_snr", "ls_peak_ratio", "dip_significance",
    "half_period_profile_distance", "double_period_profile_distance",
    "double_period_odd_even_difference", "maximum_section_correlation",
    "sections_with_shape",
}


VALIDATION_FEATURES = (
    "profile_chi2", "profile_snr", "dip_duty_cycle", "dip_dominance",
    "secondary_dip_depth_norm", "secondary_dip_phase_separation",
    "out_of_dip_variation", "mirror_symmetry", "harmonic_energy_ratio",
    "coherent_dimming_score", "dip_cycle_support_fraction",
    "wave_model_score", "dimming_model_score", "flare_event_count",
    "flare_asymmetry", "irregular_variability_score", "temporal_coherence_score",
    "scatter_over_error", "phase_coverage",
)


# ===========================================================================
# PLOTS
# ===========================================================================

SECTION_COLOURS = ("#4C72B0", "#DD8452", "#55A868", "#C44E52")


# ===========================================================================
# ADDITIVE, FROZEN-MAP ANALYSES
# ===========================================================================

ADDON_MAP_SPECS = {
    "combined": (
        "combined_umap_1", "combined_umap_2",
        "Combined morphology UMAP - unsupervised and label-blind",
        "all_families_combined_unsupervised_umap"),
    "periodic": (
        "periodic_umap_1", "periodic_umap_2",
        "Periodic morphology UMAP", "all_families_periodic_umap"),
    "transient": (
        "transient_umap_1", "transient_umap_2",
        "Transient/evolution UMAP", "all_families_transient_umap"),
    "evidence": (
        "classification_evidence_umap_1", "classification_evidence_umap_2",
        "Classification-evidence UMAP - continuous morphology scores",
        "all_families_classification_evidence_umap"),
}
