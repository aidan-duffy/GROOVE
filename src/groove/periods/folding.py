from __future__ import annotations
import math
from typing import Any
import numpy as np
from . import settings as S
from . import loading as _loading




def fold_coherence_metrics(
    time: np.ndarray,
    signal: np.ndarray,
    error: np.ndarray,
    period: float,
    n_bins: int = S.FOLD_METRIC_N_BINS,
) -> dict[str, Any]:
    """Measure how strongly a light curve coherently folds at a chosen period.

    This is deliberately simple and robust. It is used for diagnostics such as
    "does c show anything when folded at the o-band period?" The metric is not
    a replacement for LS; it is a cross-filter sanity check.
    """
    out = {
        "fold_valid_bins": 0,
        "fold_amplitude": np.nan,
        "fold_amp_snr": np.nan,
        "fold_scatter_reduction": np.nan,
        "fold_note": "not evaluated",
    }
    if not np.isfinite(period) or period <= 0:
        return out
    t = np.asarray(time, dtype=float)
    y = np.asarray(signal, dtype=float)
    e = np.asarray(error, dtype=float)
    good = np.isfinite(t) & np.isfinite(y) & np.isfinite(e) & (e > 0)
    t, y, e = t[good], y[good], e[good]
    if len(t) < max(20, 2 * n_bins):
        out["fold_note"] = "too few points"
        return out

    phase = (t / period) % 1.0
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    medians: list[float] = []
    median_errors: list[float] = []
    counts: list[int] = []
    model = np.full(len(y), np.nan, dtype=float)

    for i, (lo, hi) in enumerate(zip(edges[:-1], edges[1:])):
        m = (phase >= lo) & (phase < hi)
        n = int(np.sum(m))
        if n < S.FOLD_METRIC_MIN_POINTS_PER_BIN:
            continue
        med = float(np.nanmedian(y[m]))
        sig = _loading.robust_sigma(y[m])
        if not np.isfinite(sig) or sig <= 0:
            sig = float(np.nanmedian(e[m]))
        med_err = sig / np.sqrt(n) if np.isfinite(sig) and sig > 0 else np.nan
        medians.append(med)
        median_errors.append(med_err)
        counts.append(n)
        model[m] = med

    if len(medians) < max(5, n_bins // 5):
        out["fold_valid_bins"] = len(medians)
        out["fold_note"] = "insufficient populated phase bins"
        return out

    med_arr = np.asarray(medians, dtype=float)
    err_arr = np.asarray(median_errors, dtype=float)
    amplitude = float(np.nanpercentile(med_arr, 95) - np.nanpercentile(med_arr, 5))
    typical_err = float(np.nanmedian(err_arr[np.isfinite(err_arr)])) if np.any(np.isfinite(err_arr)) else np.nan
    amp_snr = amplitude / typical_err if np.isfinite(typical_err) and typical_err > 0 else np.nan

    raw_sigma = _loading.robust_sigma(y)
    resid_sigma = _loading.robust_sigma(y[np.isfinite(model)] - model[np.isfinite(model)])
    scatter_reduction = (raw_sigma - resid_sigma) / raw_sigma if np.isfinite(raw_sigma) and raw_sigma > 0 and np.isfinite(resid_sigma) else np.nan
    out.update({
        "fold_valid_bins": int(len(medians)),
        "fold_amplitude": amplitude,
        "fold_amp_snr": float(amp_snr) if np.isfinite(amp_snr) else np.nan,
        "fold_scatter_reduction": float(scatter_reduction) if np.isfinite(scatter_reduction) else np.nan,
        "fold_note": "ok",
    })
    return out


def peak_strength_metrics(peaks: list[tuple[float, float, int]]) -> dict[str, Any]:
    """Return dominance metrics for the top periodogram peaks.

    The main strong-period rule is deliberately simple and close to the user's
    requested behaviour: if the best independent peak is much taller than the
    second or fourth peak, the periodogram contains a clean periodic signal.
    If the top four peaks are all very similar, the light curve may be variable
    but the period is not uniquely identified; later general samples can be
    marked likely_nonvar/weak from this.
    """
    powers = [float(pw) for _, pw, _ in peaks if np.isfinite(pw)]
    out = {
        "ls_second_power": np.nan,
        "ls_fourth_power": np.nan,
        "best_to_second_power_ratio": np.nan,
        "best_to_fourth_power_ratio": np.nan,
        "top4_flat": False,
        "peak_dominance_strong": False,
    }
    if not powers:
        return out
    best = powers[0]
    second = powers[1] if len(powers) >= 2 else np.nan
    fourth = powers[3] if len(powers) >= 4 else (powers[-1] if len(powers) >= 2 else np.nan)
    ratio2 = best / second if np.isfinite(second) and second > 0 else np.inf
    ratio4 = best / fourth if np.isfinite(fourth) and fourth > 0 else np.inf
    out.update({
        "ls_second_power": second,
        "ls_fourth_power": fourth,
        "best_to_second_power_ratio": float(ratio2) if np.isfinite(ratio2) else np.inf,
        "best_to_fourth_power_ratio": float(ratio4) if np.isfinite(ratio4) else np.inf,
        "top4_flat": bool(np.isfinite(ratio4) and ratio4 <= S.NONVAR_TOP4_MAX_RATIO and len(powers) >= 4),
        "peak_dominance_strong": bool(
            (np.isfinite(ratio2) and ratio2 >= S.STRONG_BEST_SECOND_RATIO)
            or (np.isfinite(ratio4) and ratio4 >= S.STRONG_BEST_FOURTH_RATIO)
        ),
    })
    return out


# =============================================================================
# PHASE / HARMONIC COHERENCE
# =============================================================================
def fold_phase(time: np.ndarray, period: float, two_cycles: bool = S.PLOT_TWO_PHASE_CYCLES) -> np.ndarray:
    phase = (np.asarray(time, dtype=float) / period) % 1.0
    return np.concatenate([phase, phase + 1.0]) if two_cycles else phase


def repeated(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values)
    return np.concatenate([values, values]) if S.PLOT_TWO_PHASE_CYCLES else values


def plot_sigma_mask(values: np.ndarray, bands: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    bands = np.asarray(bands).astype(str)
    keep = np.isfinite(values)
    if S.PLOT_SIGMA_LIMIT is None:
        return keep
    for band in np.unique(bands):
        use = (bands == band) & np.isfinite(values)
        if not np.any(use):
            continue
        centre = float(np.nanmean(values[use]))
        sigma = float(np.nanstd(values[use]))
        keep[use] = np.abs(values[use] - centre) <= float(S.PLOT_SIGMA_LIMIT) * sigma if np.isfinite(sigma) and sigma > 0 else True
    return keep


def odd_even_2p_test(time: np.ndarray, signal: np.ndarray, error: np.ndarray, photometric_period: float) -> dict[str, Any]:
    out = {
        "tested_2p_days": np.nan,
        "odd_even_valid_bins": 0,
        "odd_even_median_abs_z": np.nan,
        "odd_even_significant_bin_fraction": np.nan,
        "two_p_supported": False,
        "two_p_note": "not tested",
    }
    if not S.RUN_ODD_EVEN_2P_TEST or not np.isfinite(photometric_period) or photometric_period <= 0:
        return out
    p2 = 2.0 * photometric_period
    out["tested_2p_days"] = p2
    phase2 = (np.asarray(time, dtype=float) / p2) % 1.0
    # Map first half and second half of the 2P fold onto the same 0--1 subphase.
    first = phase2 < 0.5
    subphase = np.where(first, phase2 * 2.0, (phase2 - 0.5) * 2.0)
    bins = np.linspace(0, 1, S.ODD_EVEN_N_PHASE_BINS + 1)
    z_values: list[float] = []
    for lo, hi in zip(bins[:-1], bins[1:]):
        m1 = first & (subphase >= lo) & (subphase < hi) & np.isfinite(signal) & np.isfinite(error) & (error > 0)
        m2 = (~first) & (subphase >= lo) & (subphase < hi) & np.isfinite(signal) & np.isfinite(error) & (error > 0)
        if int(np.sum(m1)) < S.ODD_EVEN_MIN_POINTS_PER_BIN or int(np.sum(m2)) < S.ODD_EVEN_MIN_POINTS_PER_BIN:
            continue
        y1 = np.asarray(signal)[m1]
        y2 = np.asarray(signal)[m2]
        e1 = np.asarray(error)[m1]
        e2 = np.asarray(error)[m2]
        med1 = float(np.median(y1))
        med2 = float(np.median(y2))
        # Conservative uncertainty of the medians, with robust fallback.
        s1 = _loading.robust_sigma(y1) / math.sqrt(len(y1)) if len(y1) else np.nan
        s2 = _loading.robust_sigma(y2) / math.sqrt(len(y2)) if len(y2) else np.nan
        emed1 = float(np.median(e1)) / math.sqrt(len(e1)) if len(e1) else np.nan
        emed2 = float(np.median(e2)) / math.sqrt(len(e2)) if len(e2) else np.nan
        err = np.sqrt(np.nanmax([s1, emed1, 0.0]) ** 2 + np.nanmax([s2, emed2, 0.0]) ** 2)
        if np.isfinite(err) and err > 0:
            z_values.append(abs(med1 - med2) / err)
    if len(z_values) < S.ODD_EVEN_MIN_VALID_BINS:
        out["odd_even_valid_bins"] = len(z_values)
        out["two_p_note"] = "insufficient matched phase bins"
        return out
    z = np.asarray(z_values, dtype=float)
    medz = float(np.median(z))
    sigfrac = float(np.mean(z >= S.ODD_EVEN_MIN_MEDIAN_ABS_Z))
    supported = bool(medz >= S.ODD_EVEN_MIN_MEDIAN_ABS_Z and sigfrac >= S.ODD_EVEN_MIN_SIGNIFICANT_BIN_FRACTION)
    out.update(
        {
            "odd_even_valid_bins": int(len(z)),
            "odd_even_median_abs_z": medz,
            "odd_even_significant_bin_fraction": sigfrac,
            "two_p_supported": supported,
            "two_p_note": "2P supported by unequal consecutive cycles" if supported else "2P not required by fold",
        }
    )
    return out
