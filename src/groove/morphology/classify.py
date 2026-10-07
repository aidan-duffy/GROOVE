from __future__ import annotations
import warnings
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
import numpy as np
import pandas as pd
from . import settings as S
from . import utils as _utils




# ===========================================================================
# CLASSIFICATION
# ===========================================================================


def category_scores(row: Mapping[str, Any], config: Mapping[str, Any]) -> Dict[str, float]:
    """Continuous morphology evidence, independent of assigned labels."""
    t = config.get("thresholds", {})
    F = lambda key, default=np.nan: _utils.finite_float(row.get(key), default)
    clip = lambda value: float(np.clip(value, 0.0, 1.0))
    gate = float(t.get("periodic_chi2", 5.0))
    strong = float(t.get("periodic_chi2_strong", 25.0))
    periodic = clip((F("profile_chi2", 0.0) - gate) / max(strong - gate, 1e-9))
    periodic = clip(0.55 * periodic + 0.25 * clip(F("profile_snr", 0.0) / 12.0)
                    + 0.20 * clip(F("phase_coverage", 0.0) / 0.7))
    dimming = clip(F("coherent_dimming_score", 0.0))
    wave_fit = clip(F("wave_model_score", 0.0) / 0.65)
    ls_evidence = clip(F("ls_peak_ratio", 0.0) / 60.0)
    flare_events = clip(F("flare_event_count", 0.0) / max(float(t.get("flare_min_events", 2)), 1.0))
    flare_significance = clip(F("validated_flare_median_significance", 0.0) / 10.0)
    flare_support = clip(
        0.25 * flare_events
        + 0.15 * clip(F("validated_flare_independent_nights", 0.0) / 3.0)
        + 0.20 * flare_significance
        + 0.15 * clip(F("validated_flare_cross_filter_fraction", 0.0))
        + 0.15 * clip(F("validated_flare_multi_point_fraction", 0.0))
        + 0.10 * clip(F("flare_leave_one_event_out_persistent", 0.0)))
    flare_quality = clip(F("flare_asymmetry", 0.0)) * flare_support
    irregular = clip(0.65 * F("irregular_variability_score", 0.0)
                     + 0.35 * clip(F("evolution_raw_score", 0.0) / 2.0))
    scatter = clip((F("scatter_over_error", 0.0) - 1.5) / 5.0)
    reliability = clip(F("dip_point_quality_fraction", 1.0))
    nonvar = clip((1.0 - max(periodic, dimming, irregular, flare_events * flare_quality))
                  * (1.0 - scatter))
    noisy = clip(scatter * (1.0 - max(periodic, irregular, flare_events * flare_quality))
                 + (1.0 - reliability) * 0.25)
    localisation = clip((F("dip_dominance", 1.0) - 1.0) / 1.5)
    transit = clip(dimming * (0.65 + 0.35 * reliability) * localisation)
    wavelike = clip(periodic * (0.45 * wave_fit + 0.55 * ls_evidence)
                    * (1.0 - 0.35 * transit))
    flaring = clip(flare_quality * clip(F("flare_primary_validation_pass", 0.0))
                   * clip(1.0 - F("flare_point_fraction", 1.0) /
                          max(float(t.get("flare_max_point_fraction", 0.10)), 1e-9)))
    unresolved = clip(1.0 - max(transit, wavelike, flaring, irregular, nonvar, noisy))
    return {
        "score_transit": transit,
        "score_wavelike": wavelike,
        "score_flaring": flaring,
        "score_irregular_variable": irregular,
        "score_nonvar": nonvar,
        "score_noisy": noisy,
        "score_unknown": unresolved,
    }


def suggest_morphology(row: Mapping[str, Any], metadata: Mapping[str, Any],
                       config: Mapping[str, Any]) -> Dict[str, Any]:
    """Assign morphology first, then independently assess scientific interest."""
    t = config.get("thresholds", {})
    tags: List[str] = list(_utils.split_tags(row.get("diagnostic_tags", "")))
    review: List[str] = []

    def F(key, default=np.nan):
        return _utils.finite_float(row.get(key), default)

    scores = category_scores(row, config)
    chi2, psnr = F("profile_chi2", 0.0), F("profile_snr", 0.0)
    med_err, scat_err = F("median_quoted_error", 0.0), F("scatter_over_error", np.inf)
    coverage, period = F("phase_coverage", 0.0), F("recommended_period_days")
    alias_like = bool(np.isfinite(period) and any(
        abs(period - value) / value < float(t.get("alias_relative_tolerance", 0.01))
        for value in (0.5, 2.0 / 3.0, 1.0, 2.0)))
    if alias_like:
        tags.append("alias_period")
        review.append("period_on_one_day_alias")
    symmetry, peaks = F("mirror_symmetry", 0.0), int(F("profile_peak_count", 1))
    dip_sig, dip_dom = F("dip_significance", 0.0), F("dip_dominance", 1.0)
    duty, dim_score = F("dip_duty_cycle", 1.0), scores["score_transit"]
    support_cycles = int(F("dip_supporting_cycles", 0.0))
    support_fraction = F("dip_cycle_support_fraction", 0.0)
    support_sections = int(F("dip_supporting_time_sections", 0.0))
    support_nights = int(F("dip_independent_nights", 0.0))
    sec_depth, sec_sep = F("secondary_dip_depth_norm", 0.0), F("secondary_dip_phase_separation", 0.0)
    dip_depth = F("dip_depth_norm", 0.0)
    n_flare, flare_sig = int(F("flare_event_count", 0)), F("strongest_flare_sigma", 0.0)
    flare_asym, flare_frac = F("flare_asymmetry", 0.0), F("flare_point_fraction", 1.0)
    n_dim, dim_sig = int(F("dimming_event_count", 0)), F("strongest_dimming_sigma", 0.0)
    evolution, temporal = F("evolution_raw_score", 0.0), F("temporal_coherence_score", 0.0)
    ls_ratio, ood = F("ls_peak_ratio", 0.0), F("out_of_distribution_score", 0.0)
    chi2_gate = float(t.get("periodic_chi2", 5.0))
    chi2_strong = float(t.get("periodic_chi2_strong", 25.0))
    snr_gate = float(t.get("periodic_snr", 6.0))
    min_coverage = float(config.get("minimum_phase_coverage", 0.30))
    periodic = (np.isfinite(period) and chi2 >= chi2_gate and psnr >= snr_gate
                and coverage >= min_coverage)
    amplitude = F("robust_amplitude_mag", 0.0)
    poor = (med_err > float(t.get("poor_photometry_error", 0.25))
            and amplitude < float(t.get("poor_photometry_amplitude_ratio", 3.0)) * med_err)
    if poor:
        tags.append("poor_photometry")
        review.append("median_error_above_limit")
    if not np.isfinite(period):
        tags.append("missing_recommended_period")
        review.append("missing_recommended_period")
    if _utils.bool_value(row.get("filter_disagreement", False)):
        tags.append("filter_disagreement")
        review.append("significant_filters_disagree")

    dimming_claim = (F("coherent_dimming_score", 0.0) >= 0.15
                     or dim_score >= 0.25 or n_dim >= 1 or dip_sig >= 3.0
                     or support_cycles > 0)
    seasonal = dimming_claim and (F("phase_time_section_dependence", 0.0) > 0.25
                                  or F("dip_single_section_fraction", 0.0) > 0.70)
    gappy = dimming_claim and (F("phase_coverage_near_dip", 0.0) < 0.45
                               or F("phase_coverage_outside_dip", 0.0) < 0.30)
    poor_point_driven = dimming_claim and F("dip_point_quality_fraction", 1.0) < 0.65
    minimum_sections = int(t.get("transit_min_supporting_sections", 2))
    single_section = (dimming_claim and support_cycles > 0
                      and (support_sections < minimum_sections
                           or F("dip_single_section_fraction", 0.0) > 0.70))
    if seasonal:
        tags.append("seasonal_phase_coupling")
        review.append("transit_rejected_seasonal")
    if gappy:
        tags.append("gappy_phase_coverage")
        review.append("gappy_phase_coverage")
    if poor_point_driven:
        tags.append("poor_point_driven")
        review.append("poor_point_driven")
    if single_section:
        tags.append("single_section_dimming")
        review.append("single_section_dimming")

    # Stellar flaring is defined in raw time after subtracting any stable fold.
    flaring_ok = (
        n_flare >= int(t.get("flare_min_events", 2))
        and bool(F("flare_primary_validation_pass", 0.0))
        and bool(F("flare_leave_one_event_out_persistent", 0.0))
        and flare_sig >= float(t.get("flare_min_event_snr", 5.0))
        and flare_asym >= float(t.get("flare_min_asymmetry", 0.75))
        and flare_frac <= float(t.get("flare_max_point_fraction", 0.10))
        # grouped flares must also cover a meaningful share of epochs, so a
        # couple of stray excursions cannot define the class
        and F("flare_duty_fraction", 0.0) >= float(t.get("flare_min_duty_fraction", 0.002))
        and not poor
    )
    isolated_brightenings = int(F("single_point_flare_event_count", 0.0))
    if isolated_brightenings:
        tags.append("single_point_bright_excursions")
        review.append("single_point_bright_excursions")
    if (n_flare == 1 and F("validated_flare_well_sampled_event_count", 0.0) >= 1
            and not flaring_ok):
        tags.append("single_flare_candidate")
        review.append("single_flare_candidate")

    enough_cycles = support_cycles >= int(t.get("transit_min_cycles", 3))
    exceptional_two = (support_cycles >= 2
                       and dim_score >= float(t.get("transit_exceptional_two_cycle_score", 0.88))
                       and support_nights >= 2)
    transit_repeatable = ((enough_cycles or exceptional_two)
                          and support_fraction >= float(t.get("transit_min_cycle_support_fraction", 0.45)))
    transit_eligible = (dim_score >= float(t.get("transit_score_threshold", 0.52))
                        and 0.02 <= duty <= float(t.get("transit_max_duty_cycle", 0.65))
                        and transit_repeatable and not poor_point_driven
                        and not seasonal and not gappy and not single_section)
    double_dip = (sec_depth >= float(t.get("double_dip_fraction", 0.80)) * max(dip_depth, 1e-9)
                  and abs(sec_sep - 0.5) > float(t.get("eclipse_phase_tolerance", 0.08))
                  and dip_sig >= float(t.get("transit_min_dip_significance", 6.0))
                  and sec_depth * dip_sig / max(dip_depth, 1e-9)
                  >= float(t.get("transit_min_dip_significance", 6.0)))

    wave_like = periodic and scores["score_wavelike"] >= 0.35
    periodic_brightening = (
        periodic and F("flare_dominance", 1.0) >= float(t.get("flare_min_dominance", 1.6))
        and F("flare_duty_cycle", 1.0) <= float(t.get("flare_max_duty_cycle", 0.35))
        and F("out_of_flare_variation", np.inf)
        <= float(t.get("flare_max_baseline_variation", 0.40)))
    evolved = (periodic and ls_ratio >= 20.0
               and evolution >= float(t.get("evolving_min_section_distance", 0.65))
               and F("minimum_section_correlation", 1.0)
               <= float(t.get("evolving_max_section_correlation", 0.25)))
    irregular = (scat_err >= float(t.get("irregular_min_scatter_over_error", 2.0))
                 and temporal >= float(t.get("irregular_min_temporal_coherence", 0.42))) or evolved
    ambiguous = (periodic and dim_score >= 0.30 and scores["score_wavelike"] >= 0.30
                 and abs(F("wave_dimming_score_margin", 0.0))
                 <= float(t.get("wave_dimming_ambiguity_margin", 0.10)))
    if ambiguous:
        tags.append("transit_wave_ambiguous")
        review.append("transit_wave_ambiguous")

    if poor:
        primary, rule = "noisy", "median err %.2f mag with amplitude %.2f: cannot support a shape" % (
            med_err, amplitude)
        tags.append("low_snr_photometry")
    elif transit_eligible and (not ambiguous or scores["score_transit"] >= scores["score_wavelike"]):
        primary = "transit"
        rule = "coherent dimming score=%.2f; %d/%d cycles; %d sections" % (
            dim_score, support_cycles, int(F("dip_covered_cycles", 0)), support_sections)
        if duty <= 0.16:
            tags.append("narrow_eclipse")
        else:
            tags.extend(["broad_occultation", "dust_occultation_like"])
        if symmetry < 0.98:
            tags.append("asymmetric_occultation")
        if double_dip:
            tags.extend(["double_dip", "complex_occultation"])
        if F("dip_cycle_contrast_scatter", 0.0) >= 0.45 and support_cycles >= 3:
            tags.append("variable_depth_occultation")
        if (sec_depth >= float(t.get("secondary_eclipse_fraction", 0.25)) * max(dip_depth, 1e-9)
                and abs(sec_sep - 0.5) <= float(t.get("eclipse_phase_tolerance", 0.08))):
            tags.append("eclipsing_binary_like")
        if "two_p_eclipse_preferred" in tags:
            tags.extend(["harmonic_possible", "eclipsing_binary_like"])
    elif evolved:
        primary = "irregular_variable"
        rule = "stable periodic morphology changes between chronological sections"
        tags.extend(["temporally_evolving", "evolving_periodic"])
    elif ambiguous:
        primary = "transit" if scores["score_transit"] >= scores["score_wavelike"] else "wavelike"
        rule = "wave and dimming held-out scores are similarly supported"
    elif wave_like or periodic_brightening:
        primary = "wavelike"
        rule = "coherent wave: chi2=%.1f LS ratio=%.1f" % (chi2, ls_ratio)
        if periodic_brightening:
            tags.append("periodic_brightening")
        if np.isfinite(symmetry) and symmetry < float(t.get("symmetry_min_correlation", 0.97)):
            tags.append("asymmetric")
        else:
            tags.append("symmetric")
        if peaks >= 2:
            tags.append("multi_bump")
    elif flaring_ok:
        primary, rule = "flaring", "validated grouped raw-time brightenings"
        tags.append("transient_flares")
    elif irregular:
        primary, rule = "irregular_variable", "significant coherent non-periodic variability"
        tags.append("aperiodic_variable")
        if periodic or ls_ratio >= 20.0:
            tags.append("quasi_periodic")
        if F("section_median_range_sigma", 0.0) >= 3.0:
            tags.extend(["long_term_trend", "state_change"])
        if F("same_direction_excursion_groups", 0.0) >= 2:
            tags.append("intermittent_variability")
        if n_dim:
            tags.append("irregular_dimming")
    elif dim_score >= 0.30 or n_dim >= 1:
        primary, rule = "unknown", "credible dimming is not independently repeatable"
        tags.append("unresolved_dimming")
        review.append("dimming_without_repeatability")
    elif scat_err > float(t.get("noisy_min_scatter_over_error", 4.0)):
        primary, rule = "noisy", "no coherent shape and extreme scatter: scatter/err=%.1f" % scat_err
    elif chi2 < chi2_gate and temporal < 0.25:
        primary, rule = "nonvar", "no significant periodic or time-domain variability"
    else:
        primary, rule = "unknown", "measured variability is genuinely unresolved"
        review.append("unresolved_morphology")

    ordered_scores = sorted(scores.values(), reverse=True)
    margin = ordered_scores[0] - ordered_scores[1] if len(ordered_scores) > 1 else ordered_scores[0]
    primary_score = scores.get("score_%s" % primary, 0.0)
    conf = 0.35 + 0.35 * primary_score + 0.30 * np.clip(margin / 0.5, 0.0, 1.0)
    if primary == "transit":
        conf = 0.30 + 0.35 * dim_score + 0.15 * np.clip(support_cycles / 5.0, 0, 1)\
            + 0.10 * np.clip(support_sections / 3.0, 0, 1)\
            + 0.10 * np.clip(F("dip_point_quality_fraction", 0.0), 0, 1)
    if poor:
        conf = min(conf, 0.50)
    if gappy or seasonal:
        conf *= 0.75
    if "alias_possible" in tags:
        conf *= 0.85
    if alias_like:
        conf = min(conf, 0.60)
    if ambiguous:
        conf *= 0.85
    if not np.isfinite(period) and primary in ("transit", "wavelike"):
        conf = min(conf, 0.40)
    if conf < float(t.get("low_confidence", 0.60)):
        review.append("low_confidence")

    # Scientific interest is a separate decision. Every exotic reason below
    # requires positive astrophysical structure plus quality/repeatability.
    exotic_reasons: List[str] = []
    exotic_components: List[float] = []
    credible_quality = not poor and not poor_point_driven and not seasonal and not gappy
    if primary == "transit" and double_dip and credible_quality and transit_repeatable:
        exotic_reasons.append("unusual_repeating_double_dip")
        exotic_components.append(dim_score)
    if primary == "transit" and "complex_occultation" in tags and credible_quality:
        exotic_reasons.append("complex_occultation")
        exotic_components.append(0.85 * dim_score)
    if (primary == "transit" and duty >= 0.25 and dip_sig >= 10.0
            and credible_quality and support_cycles >= 3):
        exotic_reasons.append("deep_dust_occultation")
        exotic_components.append(dim_score)
    evolving_interest_score = float(
        0.30 * scores["score_irregular_variable"]
        + 0.20 * np.clip(temporal, 0.0, 1.0)
        + 0.20 * np.clip(evolution / 1.2, 0.0, 1.0)
        + 0.15 * np.clip(F("maximum_section_distance", 0.0) / 0.6, 0.0, 1.0)
        + 0.15 * np.clip(conf, 0.0, 1.0))
    strict_evolving = (
        primary == "irregular_variable" and evolved and not poor
        and scores["score_irregular_variable"] >= 0.55
        and temporal >= 0.55 and evolution >= 1.00
        and F("maximum_section_distance", 0.0) >= 0.55
        and F("minimum_section_correlation", 1.0) <= 0.15
        and int(F("sections_with_shape", 0.0)) >= 2
        and conf >= 0.60)
    if strict_evolving:
        exotic_reasons.append("temporally_evolving_morphology")
        exotic_components.append(evolving_interest_score)
    elif primary == "irregular_variable" and evolved:
        review.append("interesting_evolving_morphology")

    periodic_shape_score = max(scores.get("score_transit", 0.0),
                               scores.get("score_wavelike", 0.0))
    periodic_flare_interest_score = float(
        0.45 * scores.get("score_flaring", 0.0)
        + 0.35 * periodic_shape_score + 0.20 * np.clip(conf, 0.0, 1.0))
    strict_periodic_flaring = (
        flaring_ok and not periodic_brightening
        and primary in ("transit", "wavelike") and periodic and not poor
        and scores.get("score_flaring", 0.0) >= 0.80
        and periodic_shape_score >= 0.65 and conf >= 0.65
        and n_flare >= max(int(t.get("flare_min_events", 2)), 4)
        and flare_asym >= 0.90 and flare_frac <= 0.05)
    if strict_periodic_flaring:
        tags.append("transient_flares")
        exotic_reasons.append("periodic_plus_validated_flaring")
        exotic_components.append(periodic_flare_interest_score)
    elif flaring_ok and primary in ("transit", "wavelike") and not periodic_brightening:
        tags.append("transient_flares")
        review.append("periodic_with_possible_flares")

    possible_single = (n_dim >= 1 and dim_sig >= 7.0
                       and F("dimming_point_fraction", 1.0) <= 0.08
                       and not periodic and credible_quality)
    credible_single = (
        possible_single and n_dim == 1 and dim_sig >= 10.0
        and F("dimming_point_fraction", 1.0) <= 0.005
        and med_err <= 0.10 and scat_err <= 2.5 and conf >= 0.50)
    if credible_single:
        single_interest_score = float(
            0.45 * np.clip(dim_sig / 15.0, 0.0, 1.0)
            + 0.20 * np.clip(1.0 - med_err / 0.10, 0.0, 1.0)
            + 0.20 * np.clip(1.0 - F("dimming_point_fraction", 1.0) / 0.005, 0.0, 1.0)
            + 0.15 * np.clip(temporal, 0.0, 1.0))
        exotic_reasons.append("credible_single_epoch_dimming")
        exotic_components.append(single_interest_score)
    elif possible_single:
        review.append("single_epoch_dimming_review")
    exotic_score = float(np.clip(max(exotic_components) if exotic_components else 0.0, 0.0, 1.0))
    exotic_minimum = float(t.get("exotic_candidate_min_score", 0.70))
    if exotic_reasons and exotic_score >= exotic_minimum and conf >= 0.60:
        interest_status = "exotic_candidate"
        interest_confidence = exotic_score
    elif exotic_reasons:
        review.append("interesting_but_below_exotic_threshold")
        interest_status = "review"
        interest_confidence = exotic_score
    elif review:
        interest_status = "review"
        interest_confidence = float(np.clip(0.45 + 0.35 * (1.0 - conf), 0.0, 1.0))
    else:
        interest_status = "routine"
        interest_confidence = float(np.clip(conf, 0.0, 1.0))

    if ood > 1.0:
        tags.append("out_of_distribution_shape")
        review.append("out_of_distribution")
    if any(tag in tags for tag in ("alias_period", "alias_possible", "harmonic_possible",
                                   "period_weak_or_ambiguous")):
        review.append("alias_or_harmonic")
    if interest_status == "routine" and review:
        interest_status = "review"

    return {
        "suggested_primary_tag": primary,
        "suggested_secondary_tags": _utils.join_tags(tags),
        "morphology_confidence": float(np.clip(conf, 0.0, 1.0)),
        "suggestion_confidence": float(np.clip(conf, 0.0, 1.0)),
        "suggested_interest_status": interest_status,
        "interest_status": interest_status,
        "interest_reasons": _utils.join_tags(exotic_reasons),
        "interest_confidence": interest_confidence,
        "exotic_candidate_score": exotic_score,
        **scores,
        "rule_fired": rule,
        "needs_review": bool(review),
        "review_reason": _utils.join_tags(review),
    }


def load_manual_labels(path: Optional[Path]) -> pd.DataFrame:
    empty = pd.DataFrame(columns=list(S.MANUAL_LABEL_COLUMNS))
    if path is None or not Path(path).exists():
        return empty
    frame = pd.read_csv(path, dtype=str).fillna("")
    if "source_id" not in frame.columns:
        return empty
    frame["source_id"] = frame["source_id"].map(_utils.clean_source_id)
    for column in S.MANUAL_LABEL_COLUMNS:
        if column not in frame.columns:
            frame[column] = ""
    return frame[list(S.MANUAL_LABEL_COLUMNS)]


def ensure_manual_labels_file(path: Path) -> None:
    """Create/extend the manual schema without changing any entered value."""
    path = Path(path)
    if not path.exists():
        _utils.atomic_write_csv(pd.DataFrame(columns=list(S.MANUAL_LABEL_COLUMNS)), path)
        return
    frame = pd.read_csv(path, dtype=str).fillna("")
    missing = [column for column in S.MANUAL_LABEL_COLUMNS if column not in frame.columns]
    if not missing:
        return
    for column in missing:
        frame[column] = ""
    ordered = list(S.MANUAL_LABEL_COLUMNS) + [
        column for column in frame.columns if column not in S.MANUAL_LABEL_COLUMNS]
    _utils.atomic_write_csv(frame[ordered], path)


def apply_labels(table: pd.DataFrame, manual: pd.DataFrame) -> pd.DataFrame:
    table = table.copy()
    for column in S.MANUAL_LABEL_COLUMNS[2:]:
        table[column] = ""
    if "interest_reasons" not in table:
        table["interest_reasons"] = ""
    table["suggested_interest_reasons"] = table["interest_reasons"].fillna("").astype(str)
    if not manual.empty:
        lookup = {(r["source_id"], r["dataset"]): r for _, r in manual.iterrows()}
        loose = {r["source_id"]: r for _, r in manual.iterrows()}
        for index, row in table.iterrows():
            # Explicit None checks: these values are pandas Series, so `a or b`
            # raises "truth value of a Series is ambiguous".
            entry = lookup.get((row["source_id"], row["dataset"]))
            if entry is None:
                entry = loose.get(row["source_id"])
            if entry is None:
                continue
            raw_primary = str(entry.get("manual_primary_tag", "")).strip()
            primary_tokens = _utils.split_tags(raw_primary)
            primary = next((value for value in primary_tokens
                            if value in S.PRIMARY_CATEGORIES), "")
            legacy_exotic = any(value.lower() == "exotic" for value in primary_tokens)
            if legacy_exotic:
                warnings.warn(
                    "Legacy manual primary label 'exotic' for source %s was converted "
                    "to manual_interest_status=manually_confirmed_exotic; primary "
                    "morphology is %s." % (row["source_id"], primary or "unknown"),
                    UserWarning)
                table.at[index, "manual_interest_status"] = "manually_confirmed_exotic"
                if not primary:
                    primary = "unknown"
            if primary:
                table.at[index, "manual_primary_tag"] = primary
            for column in S.MANUAL_LABEL_COLUMNS[3:]:
                value = str(entry.get(column, "")).strip()
                if column == "manual_interest_status" and legacy_exotic:
                    continue
                table.at[index, column] = value
    table["final_primary_tag"] = np.where(
        table["manual_primary_tag"].astype(str).str.len() > 0,
        table["manual_primary_tag"], table["suggested_primary_tag"])
    table["final_secondary_tags"] = [
        _utils.join_tags(_utils.split_tags(a) + _utils.split_tags(b))
        for a, b in zip(table["suggested_secondary_tags"], table["manual_secondary_tags"])]
    table["label_source"] = np.where(
        table["manual_primary_tag"].astype(str).str.len() > 0, "manual", "automatic")
    table["final_confidence"] = np.where(
        table["label_source"].eq("manual"), 1.0, table["morphology_confidence"])
    valid_manual_interest = table["manual_interest_status"].isin(S.INTEREST_STATUSES)
    table["interest_status"] = np.where(
        valid_manual_interest, table["manual_interest_status"],
        table["suggested_interest_status"])
    table["interest_reasons"] = np.where(
        table["manual_interest_reasons"].astype(str).str.len() > 0,
        table["manual_interest_reasons"], table["suggested_interest_reasons"])
    table["interest_label_source"] = np.where(
        valid_manual_interest | table["manual_interest_reasons"].astype(str).str.len().gt(0),
        "manual", "automatic")
    table["interest_confidence"] = np.where(
        valid_manual_interest, 1.0, table["interest_confidence"])
    return table


def strength_score(row: Mapping[str, Any]) -> float:
    fn = S.STRENGTH_SCORES.get(str(row.get("final_primary_tag", "")), lambda r: 0.0)
    return _utils.finite_float(fn(row), 0.0)


def classification_evidence_matrix(table: pd.DataFrame) -> np.ndarray:
    """Seven-score Hellinger representation used only for the evidence map."""
    scores = table.reindex(columns=list(S.CATEGORY_SCORE_COLUMNS)).apply(
        pd.to_numeric, errors="coerce").to_numpy(dtype=float)
    scores = np.nan_to_num(scores, nan=0.0, posinf=0.0, neginf=0.0)
    scores = np.clip(scores, 0.0, None) + 1e-12
    scores /= scores.sum(axis=1, keepdims=True)
    return np.sqrt(scores)


def flare_event_validation_table(records: Sequence[Mapping[str, Any]], table: pd.DataFrame,
                                 version_dir: Path) -> pd.DataFrame:
    """Merge per-event audit rows, preserving carried transform sources."""
    rows: List[Dict[str, Any]] = []
    replacement_keys: set = set()
    for record in records:
        summary = record.get("summary", {})
        key = str(summary.get("source_key", ""))
        replacement_keys.add(key)
        for event in record.get("event_rows", []) or []:
            payload = dict(event)
            payload.setdefault("source_key", key)
            payload.setdefault("source_id", summary.get("source_id", ""))
            payload.setdefault("dataset", summary.get("dataset", ""))
            rows.append(payload)
    current = pd.DataFrame(rows)
    previous_path = Path(version_dir) / "tables" / "flare_event_validation.csv"
    if previous_path.exists():
        try:
            previous = pd.read_csv(
                previous_path, dtype={"source_id": str, "source_key": str}, low_memory=False)
            if "source_key" in previous.columns:
                previous = previous.loc[
                    ~previous["source_key"].astype(str).isin(replacement_keys)]
                current = pd.concat([previous, current], ignore_index=True, sort=False)
        except Exception:
            pass
    if current.empty:
        return pd.DataFrame(columns=[
            "source_key", "source_id", "dataset", "event_type", "event_number",
            "event_time", "independent_observing_night", "n_measurements",
            "event_duration_days", "represented_filters",
            "peak_residual_significance", "median_residual_significance",
            "median_quoted_uncertainty", "minimum_quoted_uncertainty",
            "maximum_quoted_uncertainty", "is_multi_point",
            "has_cross_filter_support", "passes_quality_validation",
            "rejection_reason", "final_primary_tag", "final_confidence"])
    labels = table[["source_key", "final_primary_tag", "final_confidence"]].copy()
    labels["source_key"] = labels["source_key"].astype(str)
    current["source_key"] = current["source_key"].astype(str)
    for column in ("final_primary_tag", "final_confidence"):
        if column in current.columns:
            current = current.drop(columns=[column])
    return current.merge(labels, on="source_key", how="left")


def assemble_table(records: Sequence[Mapping[str, Any]], config: Mapping[str, Any],
                   metadata: Mapping[str, Any]) -> pd.DataFrame:
    rows = []
    for record in records:
        summary = dict(record["summary"])
        rows.append(summary)
    table = pd.DataFrame(rows)
    return table


def classify_table(table: pd.DataFrame, metadata: Mapping[str, Any],
                   config: Mapping[str, Any]) -> pd.DataFrame:
    suggestions = [suggest_morphology(row, metadata, config)
                   for _, row in table.iterrows()]
    for column in (("suggested_primary_tag", "suggested_secondary_tags",
                    "morphology_confidence", "suggestion_confidence",
                    "suggested_interest_status", "interest_status",
                    "interest_reasons", "interest_confidence",
                    "exotic_candidate_score", "rule_fired", "needs_review",
                    "review_reason") + S.CATEGORY_SCORE_COLUMNS):
        table[column] = [s[column] for s in suggestions]
    return table
