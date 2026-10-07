from __future__ import annotations
from typing import Any
import numpy as np
import pandas as pd
from . import settings as S
from . import aliases as _aliases
from . import classify as _classify
from . import folding as _folding
from . import loading as _loading
from . import periodograms as _periodograms
from . import validation as _validation




# =============================================================================
# ONE SERIES ANALYSIS WITHOUT FIELD ALIAS MEMORY
# =============================================================================
def analyse_one_series(metadata: dict[str, Any], prepared: dict[str, Any], catalogue_period: float) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any] | None]:
    n_points = int(prepared["n_points"])
    baseline = float(prepared["baseline_days"])
    base = {
        **metadata,
        "series": prepared["series_name"],
        "signal_type": prepared["signal_type"],
        "bands_present": prepared["bands_present"],
        "n_bands": prepared["n_bands"],
        "n_points": n_points,
        "mjd_min": prepared["mjd_min"],
        "mjd_max": prepared["mjd_max"],
        "baseline_days": baseline,
        "catalogue_period_days": catalogue_period,
    }
    if n_points < S.MIN_POINTS:
        return {**base, "status": "skipped", "skip_reason": f"fewer than {S.MIN_POINTS} usable points"}, [], None
    if not np.isfinite(baseline) or baseline < S.MIN_BASELINE_DAYS:
        return {**base, "status": "skipped", "skip_reason": f"baseline shorter than {S.MIN_BASELINE_DAYS:g} days"}, [], None
    pmin, pmax = _periodograms.effective_period_range(baseline)
    if pmax <= pmin * 1.05:
        return {**base, "status": "skipped", "skip_reason": "period range unsupported", "search_min_period_days": pmin, "search_max_period_days": pmax}, [], None

    result = _periodograms.run_lomb_scargle(prepared["time"], prepared["signal"], prepared["error"], pmin, pmax)
    raw_period = float(result["raw_best_period"])
    raw_peak_snr = _periodograms.periodogram_peak_snr(result["power"], result["raw_best_power"])
    raw_fold = _folding.fold_coherence_metrics(
        prepared["time"], prepared["signal"], prepared["error"], raw_period
    )
    peak_metrics = _folding.peak_strength_metrics(result["peaks"])
    raw_window_power = _periodograms.spectral_window_power(prepared["time"], 1.0 / raw_period) if raw_period > 0 else np.nan
    mh_test = _periodograms.multiharmonic_2p_test(
        prepared["time"], prepared["signal"], prepared["error"], raw_period, baseline
    )
    top_periods = ";".join(f"{p:.10g}" for p, _, _ in result["peaks"])
    top_powers = ";".join(f"{pw:.10g}" for _, pw, _ in result["peaks"])

    peak_rows: list[dict[str, Any]] = []
    best_period = result["peaks"][0][0] if result["peaks"] else np.nan
    for rank, (period, power, idx) in enumerate(result["peaks"], start=1):
        peak_rows.append(
            {
                **metadata,
                "series": prepared["series_name"],
                "rank": rank,
                "period_days": period,
                "frequency_per_day": 1.0 / period,
                "power": power,
                "power_fraction_of_best": power / result["raw_best_power"] if result["raw_best_power"] > 0 else np.nan,
                "harmonic_to_raw_best": _aliases.harmonic_relation(period, best_period),
                "catalogue_match": _validation.catalogue_match(period, catalogue_period),
            }
        )

    # Find first catalogue match among top-N for validation only.
    catalogue_searchable = bool(np.isfinite(catalogue_period) and pmin <= catalogue_period <= pmax)
    topn_match = "no_catalogue_period" if not np.isfinite(catalogue_period) else "outside_search_range"
    topn_rank = np.nan
    topn_period = np.nan
    if catalogue_searchable:
        topn_match = "mismatch"
        for row in peak_rows:
            match = str(row["catalogue_match"])
            if _validation.catalogue_match_is_success(match):
                topn_match = match
                topn_rank = int(row["rank"])
                topn_period = float(row["period_days"])
                break

    bls = _periodograms.run_bls(prepared["time"], prepared["signal"], prepared["error"], prepared["signal_type"], baseline)

    two_p = _folding.odd_even_2p_test(prepared["time"], prepared["signal"], prepared["error"], raw_period)

    row = {
        **base,
        "status": "ok",
        "skip_reason": "",
        "search_min_period_days": pmin,
        "search_max_period_days": pmax,
        "raw_ls_best_period_days": raw_period,
        "raw_ls_best_power": float(result["raw_best_power"]),
        "raw_ls_fap": _loading.safe_float(result["raw_best_fap"]),
        "ls_peak_snr": raw_peak_snr,
        **peak_metrics,
        "raw_sampling_window_power": raw_window_power,
        "raw_fold_valid_bins": raw_fold["fold_valid_bins"],
        "raw_fold_amplitude": raw_fold["fold_amplitude"],
        "raw_fold_amp_snr": raw_fold["fold_amp_snr"],
        "raw_fold_scatter_reduction": raw_fold["fold_scatter_reduction"],
        **mh_test,
        "raw_period_significant": bool(_classify.series_is_significant({
            "raw_ls_fap": _loading.safe_float(result["raw_best_fap"]),
            "ls_peak_snr": raw_peak_snr,
            "raw_fold_amp_snr": raw_fold["fold_amp_snr"],
            **peak_metrics,
        })),
        "raw_period_likely_nonvar": bool(_classify.series_is_likely_nonvar({
            "raw_ls_fap": _loading.safe_float(result["raw_best_fap"]),
            "ls_peak_snr": raw_peak_snr,
            "raw_fold_amp_snr": raw_fold["fold_amp_snr"],
            **peak_metrics,
        })),
        "ls_top_periods_days": top_periods,
        "ls_top_powers": top_powers,
        "raw_catalogue_match": _validation.catalogue_match(raw_period, catalogue_period),
        "catalogue_searchable": catalogue_searchable,
        "catalogue_recovery_type_top_n": topn_match,
        "catalogue_recovery_rank_top_n": topn_rank,
        "catalogue_recovery_period_top_n": topn_period,
        "catalogue_recovered_top_n": bool(_validation.catalogue_match_is_success(topn_match)),
        "bls_ran": bls is not None,
        "bls_best_period_days": bls["best_period"] if bls else np.nan,
        "bls_sde": bls["sde"] if bls else np.nan,
        **two_p,
        # Filled after alias memory is known.
        "alias_corrected_period_days": np.nan,
        "alias_correction_applied": False,
        "alias_correction_note": "pending alias memory",
        "recommended_series_period_days": raw_period,
        "series_confidence_class": "pending",
    }
    return row, peak_rows, {"prepared": prepared, "result": result, "bls": bls}

# =============================================================================
# SOURCE-LEVEL RECOMMENDATION
# =============================================================================
def choose_source_recommendations(summary_rows: list[dict[str, Any]]) -> pd.DataFrame:
    """Create one source-level recommendation row.

    The logic is intentionally split into two layers:
      1. detection strength: strong/weak/non-variable evidence;
      2. warning flags: alias, harmonic, single-filter, filter-disagreement.

    Alias/harmonic warnings no longer automatically erase a strong periodic
    detection.  They alter confidence and are reported as flags, while the
    source can still be a strong_period.
    """
    summary = pd.DataFrame(summary_rows)
    if summary.empty or "status" not in summary.columns:
        return pd.DataFrame()
    ok = summary.loc[summary["status"].astype(str).eq("ok")].copy()
    if ok.empty:
        return pd.DataFrame()

    def select_series(group: pd.DataFrame, name: str) -> pd.Series | None:
        sub = group.loc[group["series"].astype(str).eq(name)].copy()
        if sub.empty:
            return None
        # If duplicate source+series rows exist, keep the most defensible one
        # explicitly rather than letting a dictionary overwrite rows silently.
        sub["_sig"] = sub.apply(lambda r: _classify.series_is_significant(r), axis=1).astype(int)
        sub["_ratio"] = pd.to_numeric(sub.get("best_to_second_power_ratio", np.nan), errors="coerce")
        sub["_fold"] = pd.to_numeric(sub.get("raw_fold_amp_snr", np.nan), errors="coerce")
        sub["_power"] = pd.to_numeric(sub.get("raw_ls_best_power", np.nan), errors="coerce")
        sub = sub.sort_values(["_sig", "_ratio", "_fold", "_power"], ascending=[False, False, False, False])
        return sub.iloc[0]

    def p_from(r: pd.Series | None, col: str = "recommended_series_period_days") -> float:
        return _loading.safe_float(r.get(col), np.nan) if r is not None else np.nan

    def is_sig(r: pd.Series | None) -> bool:
        return _classify.series_is_significant(r)

    def is_nonvar(r: pd.Series | None) -> bool:
        return _classify.series_is_likely_nonvar(r)

    def series_score(r: pd.Series | None) -> float:
        if r is None:
            return -np.inf
        score = 0.0
        if is_sig(r):
            score += 3.0
        if bool(r.get("peak_dominance_strong", False)):
            score += 1.0
        ratio2 = _loading.safe_float(r.get("best_to_second_power_ratio"), np.nan)
        ratio4 = _loading.safe_float(r.get("best_to_fourth_power_ratio"), np.nan)
        peak_snr = _loading.safe_float(r.get("ls_peak_snr"), np.nan)
        fold_snr = _loading.safe_float(r.get("raw_fold_amp_snr"), np.nan)
        scatter = _loading.safe_float(r.get("raw_fold_scatter_reduction"), np.nan)
        fap = _loading.safe_float(r.get("raw_ls_fap"), np.nan)
        if np.isfinite(ratio2):
            score += min(max((ratio2 - 1.0) / max(S.STRONG_BEST_SECOND_RATIO - 1.0, 1e-6), 0.0), 2.0)
        if np.isfinite(ratio4):
            score += min(max((ratio4 - 1.0) / max(S.STRONG_BEST_FOURTH_RATIO - 1.0, 1e-6), 0.0), 2.0)
        if np.isfinite(peak_snr):
            score += min(peak_snr / 6.0, 1.5)
        if np.isfinite(fold_snr):
            score += min(fold_snr / 6.0, 1.5)
        if np.isfinite(scatter) and scatter > 0:
            score += min(scatter * 3.0, 1.0)
        if np.isfinite(fap) and fap <= S.FAP_THRESHOLD:
            score += 0.5
        if bool(r.get("raw_is_alias_suspect", False)):
            score -= 0.75
        if bool(r.get("alias_correction_applied", False)):
            score += 0.25
        if bool(r.get("top4_flat", False)):
            score -= 0.75
        return float(score)

    def bls_relation_to_period(rows_for_source: list[pd.Series | None], period: float) -> tuple[str, str]:
        if not np.isfinite(period) or period <= 0:
            return "none", ""
        matches: list[str] = []
        for r in rows_for_source:
            if r is None:
                continue
            bls_p = _loading.safe_float(r.get("bls_best_period_days"), np.nan)
            if np.isfinite(bls_p) and bls_p > 0:
                rel = _aliases.harmonic_relation(bls_p, period)
                if rel:
                    matches.append(f"{r.get('series')}:{rel}@{bls_p:.6g}d")
        if matches:
            return "supports_recommended", ";".join(matches)
        return "no_bls_support", ""

    rows: list[dict[str, Any]] = []
    for source_id, group in ok.groupby("source_id", dropna=False):
        combined = select_series(group, "combined")
        o = select_series(group, "o")
        c = select_series(group, "c")
        source_rows = [combined, o, c]

        p_comb = p_from(combined)
        p_o = p_from(o)
        p_c = p_from(c)
        raw_comb = p_from(combined, "raw_ls_best_period_days")
        sig_comb = is_sig(combined)
        sig_o = is_sig(o)
        sig_c = is_sig(c)
        any_sig = bool(sig_comb or sig_o or sig_c)
        all_nonvar = bool(all(is_nonvar(r) for r in source_rows if r is not None))

        xf_relation = ""
        xf_status = "insufficient"
        xf_anchor = np.nan
        if np.isfinite(p_o) and np.isfinite(p_c):
            xf_relation = _aliases.harmonic_relation(p_o, p_c)
            if xf_relation:
                xf_status = "agree"
                xf_anchor = p_o if xf_relation == "direct" else min(p_o, p_c)
            else:
                xf_status = "disagree"

        if sig_o and sig_c:
            band_detection_status = "both_filters_significant"
        elif sig_o and not sig_c:
            band_detection_status = "o_only_significant"
        elif sig_c and not sig_o:
            band_detection_status = "c_only_significant"
        elif sig_comb:
            band_detection_status = "combined_only_significant"
        else:
            band_detection_status = "no_significant_series"

        # Choose the strongest supported photometric period.  o/c agreement is
        # preferred, but a clean o-only or c-only signal is retained.
        period_source = "none"
        photometric_period = np.nan
        if xf_status == "agree" and np.isfinite(xf_anchor) and (sig_o or sig_c):
            photometric_period = xf_anchor
            period_source = "o_c_consensus"
        else:
            candidates = [("combined", combined, p_comb), ("o", o, p_o), ("c", c, p_c)]
            scored = [(series_score(r), name, r, pp) for name, r, pp in candidates if r is not None and np.isfinite(pp) and pp > 0]
            scored.sort(reverse=True, key=lambda x: x[0])
            if scored:
                _, period_source, _, photometric_period = scored[0]
                if period_source in {"o", "c"} and not is_sig(scored[0][2]):
                    period_source += "_low_support"
                elif period_source in {"o", "c"}:
                    period_source += "_single_filter"

        if xf_status == "agree" and np.isfinite(xf_anchor) and np.isfinite(p_comb) and not _aliases.harmonic_relation(p_comb, xf_anchor):
            photometric_period = xf_anchor
            period_source = "o_c_consensus_over_combined"

        # Choose the row closest to the photometric period for harmonic tests.
        test_row = None
        if np.isfinite(photometric_period):
            best_sep = np.inf
            for r, pp in [(combined, p_comb), (o, p_o), (c, p_c)]:
                if r is None or not np.isfinite(pp) or pp <= 0:
                    continue
                rel = abs(pp - photometric_period) / photometric_period
                if rel < best_sep:
                    best_sep = rel
                    test_row = r
        if test_row is None:
            test_row = combined if combined is not None else (o if o is not None else c)

        two_p_period = _loading.safe_float(test_row.get("tested_2p_days"), np.nan) if test_row is not None else np.nan
        if np.isfinite(photometric_period):
            if not np.isfinite(two_p_period) or abs(two_p_period - 2 * photometric_period) / (2 * photometric_period) > 0.05:
                two_p_period = 2 * photometric_period

        odd_even_2p = bool(test_row.get("two_p_supported", False)) if test_row is not None else False
        mh_2p = bool(test_row.get("mh_2p_supported", False)) if test_row is not None else False
        top_peak_2p_present = any(bool(r.get("top_peak_2p_present", False)) for r in source_rows if r is not None)
        validation_catalogue_is_2p = any(bool(r.get("validation_catalogue_is_2p_of_series", False)) for r in source_rows if r is not None)
        harmonic_review_needed = bool(odd_even_2p or mh_2p or top_peak_2p_present or validation_catalogue_is_2p)

        # Only choose 2P as the final blind period when the light curve itself
        # supports it. A weak/top-N 2P peak or a validation catalogue relation
        # triggers harmonic review but does not automatically change the blind
        # period.
        final_period = photometric_period
        if odd_even_2p and np.isfinite(two_p_period):
            final_period = two_p_period
            harmonic_status = "2P_supported_by_odd_even_difference"
        elif mh_2p and np.isfinite(two_p_period):
            final_period = two_p_period
            harmonic_status = "2P_supported_by_multiharmonic"
        elif top_peak_2p_present and np.isfinite(two_p_period):
            harmonic_status = "P_vs_2P_competitive"
        elif validation_catalogue_is_2p and np.isfinite(two_p_period):
            harmonic_status = "P_vs_2P_validation_flag"
        else:
            harmonic_status = "photometric_period"

        alias_flags: list[str] = []
        alias_like_rows = 0
        correction_rows = 0
        for r in source_rows:
            if r is None:
                continue
            if bool(r.get("raw_is_alias_suspect", False)):
                alias_like_rows += 1
                alias_flags.append(f"{r.get('series')}:raw_alias")
            if bool(r.get("alias_correction_applied", False)):
                correction_rows += 1
                alias_flags.append(f"{r.get('series')}:corrected")

        bls_support_status, bls_support_detail = bls_relation_to_period(source_rows, final_period)

        warning_flags: list[str] = []
        if alias_like_rows:
            warning_flags.append("alias_warning")
        if correction_rows:
            warning_flags.append("alias_corrected")
        if harmonic_status in {"P_vs_2P_competitive", "P_vs_2P_validation_flag"}:
            warning_flags.append("harmonic_review")
        if harmonic_status.startswith("2P_supported"):
            warning_flags.append("2P_selected")
        if band_detection_status in {"o_only_significant", "c_only_significant", "combined_only_significant"}:
            warning_flags.append("single_filter_or_combined_only")
        if xf_status == "disagree":
            warning_flags.append("filter_disagreement")
        if bls_support_status == "supports_recommended":
            warning_flags.append("BLS_support")

        if not any_sig and all_nonvar:
            detection_label = "likely_nonvar"
            confidence = "likely_nonvar_low_significance_flat_peaks"
        elif not any_sig:
            detection_label = "weak_period"
            confidence = "weak_or_low_support_period"
        elif xf_status == "agree" and correction_rows == 0 and alias_like_rows == 0 and not harmonic_status.startswith("2P_supported"):
            detection_label = "strong_period"
            confidence = "secure_non_alias"
        elif harmonic_status.startswith("2P_supported"):
            detection_label = "strong_period"
            confidence = "secure_2P_full_cycle"
        elif correction_rows:
            detection_label = "strong_period" if any_sig else "weak_period"
            confidence = "alias_corrected_needs_review"
        elif alias_like_rows and xf_status != "agree":
            detection_label = "strong_period" if any_sig else "weak_period"
            confidence = "alias_period_not_filter_confirmed"
        elif band_detection_status == "o_only_significant":
            detection_label = "strong_period"
            confidence = "single_filter_o_supported_check_colour_or_snr"
        elif band_detection_status == "c_only_significant":
            detection_label = "strong_period"
            confidence = "single_filter_c_supported_check_colour_or_snr"
        elif xf_status == "disagree":
            detection_label = "strong_period" if any_sig else "weak_period"
            confidence = "filter_disagreement"
        else:
            detection_label = "strong_period" if any_sig else "weak_period"
            confidence = "single_series_or_low_support"

        alias_text = ";".join(alias_flags)
        per_series_classes: dict[int, tuple[str, str]] = {}
        single_filter_warning = band_detection_status in {
            "o_only_significant", "c_only_significant", "combined_only_significant"
        }
        for summary_index in group.index:
            primary, secondary = _classify.classify_series_detection(
                summary.loc[summary_index],
                filter_disagreement=(xf_status == "disagree"),
                single_filter_only=single_filter_warning,
            )
            per_series_classes[int(summary_index)] = (primary, secondary)
            summary.at[summary_index, "primary_classification"] = primary
            summary.at[summary_index, "secondary_classification"] = secondary
            summary_rows[int(summary_index)]["primary_classification"] = primary
            summary_rows[int(summary_index)]["secondary_classification"] = secondary

        preferred_index = int(test_row.name) if test_row is not None and test_row.name in group.index else int(group.index[0])
        source_primary_classification = per_series_classes[preferred_index][0]
        source_warning_set = {
            tag
            for _, secondary in per_series_classes.values()
            for tag in secondary.split(";")
            if tag != "none"
        }
        source_secondary_tags = [
            tag for tag in S.SECONDARY_WARNING_PRIORITY if tag in source_warning_set
        ][:2]
        source_secondary_classification = ";".join(source_secondary_tags) if source_secondary_tags else "none"
        recommendation_label = source_primary_classification

        notes: list[str] = []
        if band_detection_status == "o_only_significant":
            notes.append("o-band-only detection: combined/c may dilute the signal; inspect forced c fold before physical interpretation")
        if band_detection_status == "c_only_significant":
            notes.append("c-band-only detection: inspect forced o fold and image/systematics")
        if alias_text:
            notes.append(f"alias flags: {alias_text}")
        if harmonic_status == "P_vs_2P_competitive":
            notes.append("P and 2P both have periodogram support; 2P not selected automatically")
        if harmonic_status == "P_vs_2P_validation_flag":
            notes.append("validation catalogue is near 2P of the selected photometric period; review harmonic choice")
        if harmonic_status == "2P_supported_by_multiharmonic":
            notes.append("2P selected because multi-harmonic LS supports the full-cycle period")
        if not any_sig:
            notes.append("no robust LS/fold evidence")

        first = group.iloc[0]
        cat = _loading.safe_float(first.get("catalogue_period_days"), np.nan)
        rows.append(
            {
                "source_id": source_id,
                "object_name": first.get("object_name", ""),
                "cluster_name": first.get("cluster_name", ""),
                "ra_deg": first.get("ra_deg", np.nan),
                "dec_deg": first.get("dec_deg", np.nan),
                "field_key": _aliases.field_key_text(_loading.safe_float(first.get("ra_deg"), np.nan), _loading.safe_float(first.get("dec_deg"), np.nan)),
                "catalogue_period_days": cat,
                "combined_period_days": p_comb,
                "o_period_days": p_o,
                "c_period_days": p_c,
                "raw_combined_ls_period_days": raw_comb,
                "combined_significant": sig_comb,
                "o_significant": sig_o,
                "c_significant": sig_c,
                "combined_score": series_score(combined),
                "o_score": series_score(o),
                "c_score": series_score(c),
                "band_detection_status": band_detection_status,
                "cross_filter_status": xf_status,
                "cross_filter_relation": xf_relation,
                "cross_filter_anchor_period_days": xf_anchor,
                "photometric_period_days": photometric_period,
                "possible_2p_period_days": two_p_period,
                "two_p_supported": bool(odd_even_2p or mh_2p),
                "odd_even_2p_supported": odd_even_2p,
                "multiharmonic_2p_supported": mh_2p,
                "top_peak_2p_present": top_peak_2p_present,
                "top_peak_2p_period_days": _loading.safe_float(test_row.get("top_peak_2p_period_days"), np.nan) if test_row is not None else np.nan,
                "top_peak_2p_rank": _loading.safe_float(test_row.get("top_peak_2p_rank"), np.nan) if test_row is not None else np.nan,
                "top_peak_2p_power_fraction": _loading.safe_float(test_row.get("top_peak_2p_power_fraction"), np.nan) if test_row is not None else np.nan,
                "validation_catalogue_is_2p": validation_catalogue_is_2p,
                "harmonic_review_needed": harmonic_review_needed,
                "recommended_period_days": final_period,
                "recommended_period_source": period_source,
                "harmonic_status": harmonic_status,
                "alias_flags": alias_text,
                "warning_flags": ";".join(warning_flags),
                "detection_label": detection_label,
                "confidence_class": confidence,
                "source_primary_classification": source_primary_classification,
                "source_secondary_classification": source_secondary_classification,
                "recommendation_label": recommendation_label,
                "plot_folder_tag": _classify.tag_folder(recommendation_label),
                "bls_support_status": bls_support_status,
                "bls_support_detail": bls_support_detail,
                "confidence_note": "; ".join(notes),
                "recommended_catalogue_match": _validation.catalogue_match(final_period, cat),
                "photometric_catalogue_match": _validation.catalogue_match(photometric_period, cat),
            }
        )
    return pd.DataFrame(rows)


# =============================================================================
# FORCED CROSS-FILTER METRICS
# =============================================================================
def add_forced_cross_filter_metrics(
    recommendations: pd.DataFrame,
    plot_payloads: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any] | None, float]],
) -> pd.DataFrame:
    """Add diagnostics such as "c folded at the o-band period".

    This is the main safeguard for colour-dependent signals. It does not force
    c to recover the period by LS; it asks whether the c data show coherent
    modulation when folded at the period recovered in o, and vice versa.
    """
    if recommendations is None or recommendations.empty:
        return recommendations

    payload_lookup: dict[tuple[str, str], dict[str, Any]] = {}
    for metadata, prepared, row, payload, catalogue_period in plot_payloads:
        payload_lookup[(str(metadata.get("source_id")), str(prepared.get("series_name")))] = prepared

    rec = recommendations.copy()
    metric_cols = [
        "o_forced_at_recommended_amp", "o_forced_at_recommended_snr", "o_forced_at_recommended_scatter_reduction",
        "c_forced_at_recommended_amp", "c_forced_at_recommended_snr", "c_forced_at_recommended_scatter_reduction",
        "c_forced_at_o_period_amp", "c_forced_at_o_period_snr",
        "o_forced_at_c_period_amp", "o_forced_at_c_period_snr",
        "o_over_c_forced_amp_ratio", "colour_recovery_status",
    ]
    for col in metric_cols:
        if col not in rec.columns:
            rec[col] = np.nan if col != "colour_recovery_status" else ""

    for idx, row in rec.iterrows():
        source_id = str(row.get("source_id"))
        p_rec = _loading.safe_float(row.get("recommended_period_days"), np.nan)
        p_o = _loading.safe_float(row.get("o_period_days"), np.nan)
        p_c = _loading.safe_float(row.get("c_period_days"), np.nan)

        o_prep = payload_lookup.get((source_id, "o"))
        c_prep = payload_lookup.get((source_id, "c"))

        if o_prep is not None and np.isfinite(p_rec) and p_rec > 0:
            m = _folding.fold_coherence_metrics(o_prep["time"], o_prep["signal"], o_prep["error"], p_rec)
            rec.at[idx, "o_forced_at_recommended_amp"] = m["fold_amplitude"]
            rec.at[idx, "o_forced_at_recommended_snr"] = m["fold_amp_snr"]
            rec.at[idx, "o_forced_at_recommended_scatter_reduction"] = m["fold_scatter_reduction"]
        if c_prep is not None and np.isfinite(p_rec) and p_rec > 0:
            m = _folding.fold_coherence_metrics(c_prep["time"], c_prep["signal"], c_prep["error"], p_rec)
            rec.at[idx, "c_forced_at_recommended_amp"] = m["fold_amplitude"]
            rec.at[idx, "c_forced_at_recommended_snr"] = m["fold_amp_snr"]
            rec.at[idx, "c_forced_at_recommended_scatter_reduction"] = m["fold_scatter_reduction"]
        if c_prep is not None and np.isfinite(p_o) and p_o > 0:
            m = _folding.fold_coherence_metrics(c_prep["time"], c_prep["signal"], c_prep["error"], p_o)
            rec.at[idx, "c_forced_at_o_period_amp"] = m["fold_amplitude"]
            rec.at[idx, "c_forced_at_o_period_snr"] = m["fold_amp_snr"]
        if o_prep is not None and np.isfinite(p_c) and p_c > 0:
            m = _folding.fold_coherence_metrics(o_prep["time"], o_prep["signal"], o_prep["error"], p_c)
            rec.at[idx, "o_forced_at_c_period_amp"] = m["fold_amplitude"]
            rec.at[idx, "o_forced_at_c_period_snr"] = m["fold_amp_snr"]

        o_amp = _loading.safe_float(rec.at[idx, "o_forced_at_recommended_amp"], np.nan)
        c_amp = _loading.safe_float(rec.at[idx, "c_forced_at_recommended_amp"], np.nan)
        if np.isfinite(o_amp) and np.isfinite(c_amp) and c_amp > 0:
            rec.at[idx, "o_over_c_forced_amp_ratio"] = o_amp / c_amp

        o_snr = _loading.safe_float(rec.at[idx, "o_forced_at_recommended_snr"], np.nan)
        c_snr = _loading.safe_float(rec.at[idx, "c_forced_at_recommended_snr"], np.nan)
        if np.isfinite(o_snr) and o_snr >= S.FOLD_SNR_THRESHOLD and (not np.isfinite(c_snr) or c_snr < S.FOLD_SNR_THRESHOLD):
            status = "o_only_at_recommended_period"
        elif np.isfinite(c_snr) and c_snr >= S.FOLD_SNR_THRESHOLD and (not np.isfinite(o_snr) or o_snr < S.FOLD_SNR_THRESHOLD):
            status = "c_only_at_recommended_period"
        elif np.isfinite(o_snr) and np.isfinite(c_snr) and o_snr >= S.FOLD_SNR_THRESHOLD and c_snr >= S.FOLD_SNR_THRESHOLD:
            status = "both_filters_show_forced_signal"
        else:
            status = "forced_fold_weak_or_unavailable"
        rec.at[idx, "colour_recovery_status"] = status

        # Make the note explicit, but do not change the period solely because of colour.
        old_note = str(rec.at[idx, "confidence_note"]) if "confidence_note" in rec.columns else ""
        if status == "o_only_at_recommended_period" and "o-only" not in old_note:
            rec.at[idx, "confidence_note"] = (old_note + "; " if old_note else "") + "forced-fold check: signal is stronger in o than c; this may be S/N, colour dependence, dust/spot physics or contamination"
        elif status == "both_filters_show_forced_signal" and "forced-fold check" not in old_note:
            rec.at[idx, "confidence_note"] = (old_note + "; " if old_note else "") + "forced-fold check: both filters support the recommended period"

    return rec


def source_consensus_table(
    summary_rows: list[dict[str, Any]],
    recommendations: pd.DataFrame,
) -> pd.DataFrame:
    """Write the compact source-level table: one row per source.

    The full source diagnostics remain in source_period_recommendations.csv;
    this compact table preserves the familiar ls_source_consensus.csv layout.
    """
    columns = [
        "source_id",
        "object_name",
        "cluster_name",
        "catalogue_period_days",
        "combined_adopted_period_days",
        "o_adopted_period_days",
        "c_adopted_period_days",
        "n_successful_series",
        "series_agreement",
        "pairwise_relations",
        "consensus_period_days",
        "consensus_catalogue_match",
    ]
    summary = pd.DataFrame(summary_rows)
    if summary.empty or "status" not in summary.columns:
        return pd.DataFrame(columns=columns)
    ok = summary.loc[summary["status"].astype(str).eq("ok")].copy()
    if ok.empty:
        return pd.DataFrame(columns=columns)

    recommendation_lookup: dict[str, dict[str, Any]] = {}
    if recommendations is not None and not recommendations.empty:
        recommendation_lookup = {
            str(row.get("source_id")): row.to_dict()
            for _, row in recommendations.iterrows()
        }

    output_rows: list[dict[str, Any]] = []
    for source_id, group in ok.groupby("source_id", dropna=False):
        by_series: dict[str, pd.Series] = {}
        for series in S.SERIES_TO_RUN:
            candidates = group.loc[group["series"].astype(str).eq(series)]
            if not candidates.empty:
                by_series[series] = candidates.iloc[0]

        periods = {series: _classify.series_period_from_row(row) for series, row in by_series.items()}
        pairwise: list[str] = []
        relations: list[str] = []
        for left, right in [("combined", "o"), ("combined", "c"), ("o", "c")]:
            p_left = periods.get(left, np.nan)
            p_right = periods.get(right, np.nan)
            if not (np.isfinite(p_left) and np.isfinite(p_right)):
                continue
            relation = _aliases.harmonic_relation(p_left, p_right) or "mismatch"
            pairwise.append(f"{left}-{right}:{relation}")
            relations.append(relation)

        if relations and all(relation != "mismatch" for relation in relations):
            agreement = "agree"
        elif relations:
            agreement = "disagree"
        else:
            agreement = "insufficient"

        first = group.iloc[0]
        source_info = recommendation_lookup.get(str(source_id), {})
        consensus_period = _loading.safe_float(source_info.get("recommended_period_days"), np.nan)
        if not np.isfinite(consensus_period) or consensus_period <= 0:
            for series in ["combined", "o", "c"]:
                candidate = periods.get(series, np.nan)
                if np.isfinite(candidate) and candidate > 0:
                    consensus_period = candidate
                    break
        catalogue_period = _loading.safe_float(first.get("catalogue_period_days"), np.nan)
        output_rows.append(
            {
                "source_id": str(source_id),
                "object_name": first.get("object_name", ""),
                "cluster_name": first.get("cluster_name", ""),
                "catalogue_period_days": catalogue_period,
                "combined_adopted_period_days": periods.get("combined", np.nan),
                "o_adopted_period_days": periods.get("o", np.nan),
                "c_adopted_period_days": periods.get("c", np.nan),
                "n_successful_series": int(len(by_series)),
                "series_agreement": source_info.get("cross_filter_status", agreement),
                "pairwise_relations": ";".join(pairwise),
                "consensus_period_days": consensus_period,
                "consensus_catalogue_match": _validation.catalogue_match(consensus_period, catalogue_period),
            }
        )
    return pd.DataFrame(output_rows, columns=columns)
