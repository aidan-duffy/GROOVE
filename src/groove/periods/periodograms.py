from __future__ import annotations
from typing import Any
import numpy as np
from astropy.timeseries import LombScargle
from . import settings as S
from . import loading as _loading




def periodogram_peak_snr(power: np.ndarray, peak_power: float) -> float:
    """Robust SNR-like measure of how isolated the strongest periodogram peak is."""
    values = np.asarray(power, dtype=float)
    values = values[np.isfinite(values)]
    if len(values) < 10 or not np.isfinite(peak_power):
        return np.nan
    centre = float(np.nanmedian(values))
    sigma = _loading.robust_sigma(values)
    if not np.isfinite(sigma) or sigma <= 0:
        return np.nan
    return float((peak_power - centre) / sigma)


def multiharmonic_power_at_period(
    time: np.ndarray,
    signal: np.ndarray,
    error: np.ndarray,
    period: float,
    nterms: int | None = None,
) -> float:
    """Multi-harmonic LS power at one trial period.

    This is a diagnostic only.  Single-term LS remains the primary periodogram,
    but this helps decide whether the true full cycle is 2P when the strongest
    single-sine peak occurs at the half-period.
    """
    if not S.RUN_MULTIHARMONIC_DIAGNOSTIC or not np.isfinite(period) or period <= 0:
        return np.nan
    try:
        model = LombScargle(
            time,
            signal,
            error,
            fit_mean=True,
            center_data=True,
            nterms=int(S.MULTIHARMONIC_NTERMS if nterms is None else nterms),
            normalization=S.LS_NORMALIZATION,
        )
        return float(model.power(1.0 / period, method="auto"))
    except Exception:
        return np.nan


def multiharmonic_2p_test(
    time: np.ndarray,
    signal: np.ndarray,
    error: np.ndarray,
    period: float,
    baseline_days: float,
) -> dict[str, Any]:
    """Compare multi-harmonic support for P and 2P."""
    out = {
        "mh_raw_power": np.nan,
        "mh_2p_power": np.nan,
        "mh_2p_gain": np.nan,
        "mh_2p_supported": False,
        "mh_2p_note": "not tested",
    }
    if not S.RUN_MULTIHARMONIC_DIAGNOSTIC or not np.isfinite(period) or period <= 0:
        return out
    p2 = 2.0 * float(period)
    raw_power = multiharmonic_power_at_period(time, signal, error, period)
    out["mh_raw_power"] = raw_power
    if p2 > baseline_days / S.MIN_CYCLES_AT_MAX_PERIOD:
        out["mh_2p_note"] = "2P unsupported by baseline"
        return out
    p2_power = multiharmonic_power_at_period(time, signal, error, p2)
    out["mh_2p_power"] = p2_power
    gain = p2_power / raw_power if np.isfinite(p2_power) and np.isfinite(raw_power) and raw_power > 0 else np.nan
    supported = bool(
        np.isfinite(gain)
        and gain >= S.MULTIHARMONIC_2P_MIN_GAIN
        and np.isfinite(p2_power)
        and p2_power >= S.MULTIHARMONIC_2P_MIN_POWER
    )
    out.update({
        "mh_2p_gain": float(gain) if np.isfinite(gain) else np.nan,
        "mh_2p_supported": supported,
        "mh_2p_note": (
            f"multi-harmonic LS favours 2P (gain={gain:.3f})"
            if supported
            else "multi-harmonic LS does not require 2P"
        ),
    })
    return out


def effective_period_range(baseline_days: float) -> tuple[float, float]:
    return float(S.MIN_PERIOD_DAYS), float(min(S.MAX_PERIOD_DAYS, baseline_days / S.MIN_CYCLES_AT_MAX_PERIOD))


def spectral_window_power(time: np.ndarray, frequency: float) -> float:
    if not np.isfinite(frequency) or frequency <= 0 or len(time) == 0:
        return np.nan
    centred = np.asarray(time, dtype=float) - float(np.min(time))
    value = np.mean(np.exp(-2j * np.pi * frequency * centred))
    return float(np.abs(value) ** 2)


def find_top_peaks(periods: np.ndarray, power: np.ndarray) -> list[tuple[float, float, int]]:
    periods = np.asarray(periods, dtype=float)
    power = np.asarray(power, dtype=float)
    good = np.isfinite(periods) & (periods > 0) & np.isfinite(power)
    p = periods[good]
    pw = power[good]
    original_indices = np.flatnonzero(good)
    if len(pw) == 0:
        return []
    if len(pw) >= 3:
        local = np.flatnonzero((pw[1:-1] > pw[:-2]) & (pw[1:-1] >= pw[2:])) + 1
    else:
        local = np.arange(len(pw))
    if len(local) == 0:
        local = np.arange(len(pw))
    order = local[np.argsort(pw[local])[::-1]]
    selected: list[tuple[float, float, int]] = []
    for idx in order:
        period = float(p[idx])
        peak_power = float(pw[idx])
        if all(abs(period - old) / old > S.PEAK_MIN_SEPARATION_FRACTION for old, _, _ in selected):
            selected.append((period, peak_power, int(original_indices[idx])))
        if len(selected) >= S.N_TOP_PEAKS:
            break
    return selected


# =============================================================================
# LOMB-SCARGLE / BLS
# =============================================================================
def run_lomb_scargle(time: np.ndarray, signal: np.ndarray, error: np.ndarray, min_period: float, max_period: float) -> dict[str, Any]:
    model = LombScargle(
        time, signal, error,
        fit_mean=True, center_data=True,
        nterms=S.LS_NTERMS, normalization=S.LS_NORMALIZATION,
    )
    min_frequency = 1.0 / max_period
    max_frequency = 1.0 / min_period
    frequency, power = model.autopower(
        minimum_frequency=min_frequency,
        maximum_frequency=max_frequency,
        samples_per_peak=S.LS_SAMPLES_PER_PEAK,
        normalization=S.LS_NORMALIZATION,
        method="auto",
    )
    frequency = np.asarray(frequency, dtype=float)
    power = np.asarray(power, dtype=float)
    periods = 1.0 / frequency
    best_idx = int(np.nanargmax(power))
    raw_period = float(periods[best_idx])
    raw_power = float(power[best_idx])
    try:
        raw_fap = float(model.false_alarm_probability(raw_power, method=S.LS_FAP_METHOD, maximum_frequency=max_frequency))
    except Exception:
        raw_fap = np.nan
    peaks = find_top_peaks(periods, power)
    return {
        "object": model,
        "frequency": frequency,
        "period": periods,
        "power": power,
        "raw_best_period": raw_period,
        "raw_best_power": raw_power,
        "raw_best_fap": raw_fap,
        "peaks": peaks,
    }


def run_bls(time: np.ndarray, signal: np.ndarray, error: np.ndarray, signal_type: str, baseline_days: float) -> dict[str, Any] | None:
    if not S.RUN_BLS or S.BoxLeastSquares is None:
        return None
    min_period = float(S.BLS_MIN_PERIOD_DAYS)
    max_period = min(float(S.BLS_MAX_PERIOD_DAYS), baseline_days / S.MIN_CYCLES_AT_MAX_PERIOD)
    if max_period <= min_period * 1.05:
        return None
    durations = np.asarray(S.BLS_DURATIONS_DAYS, dtype=float)
    durations = durations[(durations > 0) & (durations < min_period)]
    if len(durations) == 0:
        return None
    flux_like = -np.asarray(signal, dtype=float) if signal_type == "magnitude" else np.asarray(signal, dtype=float)
    df = 1.0 / (float(S.BLS_SAMPLES_PER_PEAK) * baseline_days)
    frequency = np.arange(1.0 / max_period, 1.0 / min_period, df)
    if len(frequency) < 10:
        return None
    periods = 1.0 / frequency[::-1]
    model = S.BoxLeastSquares(time, flux_like, dy=error)
    try:
        result = model.power(periods, durations, objective="snr")
    except Exception:
        return None
    power = np.asarray(result.power, dtype=float)
    if not np.any(np.isfinite(power)):
        return None
    best = int(np.nanargmax(power))
    finite = power[np.isfinite(power)]
    sde_sigma = _loading.robust_sigma(finite)
    sde = (float(power[best]) - float(np.median(finite))) / sde_sigma if np.isfinite(sde_sigma) and sde_sigma > 0 else np.nan
    return {
        "period_grid": np.asarray(result.period, dtype=float),
        "power": power,
        "best_period": float(result.period[best]),
        "best_duration": float(result.duration[best]),
        "best_t0": float(result.transit_time[best]),
        "best_depth": float(result.depth[best]),
        "best_power": float(power[best]),
        "sde": float(sde) if np.isfinite(sde) else np.nan,
    }
