from __future__ import annotations
from typing import Any
import numpy as np
import pandas as pd
from . import settings as S
from . import loading as _loading


def series_has_peak_dominance(row: pd.Series | dict[str, Any]) -> bool:
    """Accept either dominance diagnostic, retaining competing-peak warnings.

    A non-sinusoidal signal can have a competitive second peak while its
    leading peaks remain clearly separated from the broader peak background.
    """
    ratio2 = _loading.safe_float(row.get("best_to_second_power_ratio"), np.nan)
    ratio4 = _loading.safe_float(row.get("best_to_fourth_power_ratio"), np.nan)
    return bool(
        (np.isfinite(ratio2) and ratio2 >= S.STRONG_BEST_SECOND_RATIO)
        or (np.isfinite(ratio4) and ratio4 >= S.STRONG_BEST_FOURTH_RATIO)
    )



def series_is_significant(row: pd.Series | dict[str, Any] | None) -> bool:
    """Robust significance decision for one series.

    FAP alone is not allowed to make every ATLAS light curve significant.  A
    source passes when significance is accompanied by peak dominance or fold
    coherence.  This keeps the 456 known-variable sample mostly significant,
    while allowing a later general/non-periodic sample to produce likely_nonvar.
    """
    if row is None:
        return False
    fap = _loading.safe_float(row.get("raw_ls_fap"), np.nan)
    peak_snr = _loading.safe_float(row.get("ls_peak_snr"), np.nan)
    fold_snr = _loading.safe_float(row.get("raw_fold_amp_snr"), np.nan)

    fap_ok = np.isfinite(fap) and fap <= S.FAP_THRESHOLD
    peak_ok = np.isfinite(peak_snr) and peak_snr >= S.PERIODOGRAM_SNR_THRESHOLD
    fold_ok = np.isfinite(fold_snr) and fold_snr >= S.FOLD_SNR_THRESHOLD
    dominance_ok = series_has_peak_dominance(row)

    # Accept either a statistically significant dominant peak, or a coherent
    # folded signal with periodogram support.
    return bool(
        (fap_ok and (dominance_ok or fold_ok or peak_ok))
        or (dominance_ok and (fold_ok or peak_ok))
        or (peak_ok and fold_ok)
    )


def series_is_likely_nonvar(row: pd.Series | dict[str, Any] | None) -> bool:
    if row is None:
        return False
    fap = _loading.safe_float(row.get("raw_ls_fap"), np.nan)
    peak_snr = _loading.safe_float(row.get("ls_peak_snr"), np.nan)
    fold_snr = _loading.safe_float(row.get("raw_fold_amp_snr"), np.nan)
    ratio4 = _loading.safe_float(row.get("best_to_fourth_power_ratio"), np.nan)
    flat = np.isfinite(ratio4) and ratio4 <= S.NONVAR_TOP4_MAX_RATIO
    fap_bad = (not np.isfinite(fap)) or fap > S.NONVAR_FAP_THRESHOLD
    peak_bad = (not np.isfinite(peak_snr)) or peak_snr < S.PERIODOGRAM_SNR_THRESHOLD
    fold_bad = (not np.isfinite(fold_snr)) or fold_snr < S.FOLD_SNR_THRESHOLD
    return bool(flat and fap_bad and peak_bad and fold_bad)


def classify_series_detection(
    row: pd.Series | dict[str, Any],
    *,
    filter_disagreement: bool = False,
    single_filter_only: bool = False,
) -> tuple[str, str]:
    """Return independent detection strength and at most two series warnings."""
    ratio4 = _loading.safe_float(row.get("best_to_fourth_power_ratio"), np.nan)
    significant = series_is_significant(row)
    dominant = series_has_peak_dominance(row)
    flat_periodogram = bool(np.isfinite(ratio4) and ratio4 <= S.NONVAR_TOP4_MAX_RATIO)
    alias_flag = bool(
        _loading.safe_float(row.get("raw_alias_score"), np.nan) >= S.ALIAS_SCORE_THRESHOLD
        or row.get("alias_correction_applied", False)
    )
    harmonic_flag = bool(
        row.get("two_p_supported", False)
        or row.get("mh_2p_supported", False)
        or row.get("top_peak_2p_present", False)
    )
    if not significant and flat_periodogram:
        primary = "nonvar"
    elif not significant or flat_periodogram or not dominant:
        primary = "weak_or_ambiguous"
    elif alias_flag:
        primary = "alias_possible"
    elif harmonic_flag:
        primary = "harmonic_possible"
    elif significant and dominant:
        primary = "strong"
    else:
        primary = "weak_or_ambiguous"

    possible: set[str] = set()
    if bool(row.get("alias_correction_applied", False)):
        possible.add("alias_corrected")
    elif _loading.safe_float(row.get("raw_alias_score"), np.nan) >= S.ALIAS_SCORE_THRESHOLD:
        possible.add("alias_possible")
    if bool(
        row.get("two_p_supported", False)
        or row.get("mh_2p_supported", False)
        or row.get("top_peak_2p_present", False)
    ):
        possible.add("harmonic_possible")
    if filter_disagreement:
        possible.add("filter_disagreement")
    if single_filter_only:
        possible.add("single_filter_only")
    warnings = [tag for tag in S.SECONDARY_WARNING_PRIORITY if tag in possible][:2]
    return primary, ";".join(warnings) if warnings else "none"


def recommendation_label_from_status(
    confidence_class: str,
    any_significant: bool,
    harmonic_status: str,
    alias_flags: str,
) -> str:
    """Map detailed confidence classes to the four simple review labels.

    The label is now driven by detection strength first.  Alias/harmonic issues
    are warnings unless they actively changed the recommended period or are
    genuinely supported by the data.  This prevents every strong real variable
    from being swallowed by alias_possible/harmonic_possible.
    """
    if not any_significant:
        return "nonvar"
    confidence = str(confidence_class)
    harmonic = str(harmonic_status)
    aliases = str(alias_flags)

    if "alias_corrected" in confidence or ":corrected" in aliases:
        return "alias"
    if "alias_period_source_supported" in confidence:
        return "alias"
    if harmonic in {"2P_supported_by_odd_even_difference", "2P_supported_by_multiharmonic", "P_vs_2P_competitive"}:
        return "harmonic"
    if "secure_2P_full_cycle" in confidence:
        return "harmonic"
    return "strong"


def tag_folder(label: str) -> str:
    return S.TAG_FOLDER_MAP.get(str(label), _loading.sanitize_filename(str(label) or "unknown"))


def series_period_from_row(row: pd.Series | dict[str, Any] | None) -> float:
    """Read the best available series period from current or legacy tables."""
    if row is None:
        return np.nan
    for column in [
        "recommended_series_period_days",
        "final_best_period_days",
        "adopted_period_days",
        "raw_ls_best_period_days",
    ]:
        period = _loading.safe_float(row.get(column), np.nan)
        if np.isfinite(period) and period > 0:
            return float(period)
    return np.nan


def secondary_classification_from_row(row: pd.Series | dict[str, Any] | None) -> str:
    """Return the per-series warning metadata (never a detection class/folder)."""
    if row is None:
        return "unlabelled"
    for column in [
        "secondary_classification",
    ]:
        value = str(row.get(column, "")).strip()
        if value and value.lower() not in {"nan", "none", "pending"}:
            return value
    return "none"


def period_is_same(period_a: float, period_b: float, tolerance: float = 1e-6) -> bool:
    return bool(
        np.isfinite(period_a) and np.isfinite(period_b)
        and period_a > 0 and period_b > 0
        and abs(period_a - period_b) / period_b <= tolerance
    )
