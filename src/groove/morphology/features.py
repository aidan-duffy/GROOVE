from __future__ import annotations
import logging
import math
import traceback
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
import joblib
import numpy as np
import pandas as pd
from . import settings as S
from . import utils as _utils




# ===========================================================================
# FEATURES
# ===========================================================================


def empty_profile(n_bins: int) -> Dict[str, Any]:
    return {
        "raw": np.full(n_bins, np.nan), "normalised": np.zeros(n_bins),
        "uncertainty": np.full(n_bins, np.nan), "counts": np.zeros(n_bins, dtype=int),
        "coverage": 0.0, "amplitude": np.nan, "residual_scatter": np.nan,
        "scatter_over_error": np.nan, "median_error": np.nan,
        "profile_chi2": np.nan, "profile_snr": np.nan,
        "amplitude_over_point_scatter": np.nan,
        "n_points": 0, "reliability": 0.0,
    }


def phase_profile(frame: pd.DataFrame, period: float, n_bins: int, origin: float) -> Dict[str, Any]:
    """
    Binned phase profile plus a CORRECT significance.

    FIX (defect A): the previous version divided the binned amplitude by the
    per-point scatter, discarding the sqrt(N_per_bin) averaging and understating
    a real detection by ~an order of magnitude.  Significance is now measured
    against the per-bin standard error.
    """
    profile = empty_profile(n_bins)
    if frame.empty:
        return profile
    values = frame["mag"].to_numpy(dtype=float)
    errors = frame["err"].to_numpy(dtype=float)
    times = frame["time"].to_numpy(dtype=float)
    valid = np.isfinite(values) & np.isfinite(errors) & (errors > 0) & np.isfinite(times)
    values, errors, times = values[valid], errors[valid], times[valid]
    if len(values) < 3:
        return profile

    median_error = float(np.median(errors))
    centred = values - float(np.median(values))
    # Phase folds contain many outliers. Clip hard before binning so a handful
    # of deviant points cannot define the profile shape; the clipped points are
    # still available to the event detector, which looks for them explicitly.
    clip_scale = _utils.spread_scale(centred)
    if np.isfinite(clip_scale) and clip_scale > 0:
        keep = np.abs(centred) <= 6.0 * clip_scale
        if keep.sum() >= max(20, int(0.5 * len(centred))):
            values, errors, times = values[keep], errors[keep], times[keep]
            centred = centred[keep]
    point_scatter = _utils.spread_scale(centred)
    profile.update({
        "n_points": int(len(values)),
        "median_error": median_error,
        "scatter_over_error": float(_utils.robust_scale(centred) / max(median_error, 1e-9)),
        "residual_scatter": point_scatter,
    })
    if not np.isfinite(period) or period <= 0:
        profile["amplitude"] = _utils.robust_amplitude(centred)
        return profile

    phases = np.mod((times - origin) / period, 1.0)
    indices = np.minimum((phases * n_bins).astype(int), n_bins - 1)
    raw = np.full(n_bins, np.nan)
    uncertainty = np.full(n_bins, np.nan)
    counts = np.zeros(n_bins, dtype=int)
    for index in range(n_bins):
        chosen = indices == index
        count = int(chosen.sum())
        counts[index] = count
        if not count:
            continue
        block = centred[chosen]
        raw[index] = float(np.median(block))
        scale = _utils.spread_scale(block) if count > 3 else np.nan
        scale = scale if np.isfinite(scale) and scale > 0 else float(np.median(errors[chosen]))
        uncertainty[index] = scale / math.sqrt(count)

    coverage = float((counts > 0).mean())
    filled = _utils.circular_fill(raw)
    filled = filled - float(np.median(filled))
    amplitude = _utils.robust_amplitude(filled)
    normalised = filled / amplitude if np.isfinite(amplitude) and amplitude > 1e-12\
        else np.zeros(n_bins, dtype=float)

    # --- significance against the per-bin standard error
    occupied = counts > 0
    # Per-bin floor: a bin with few points must not be credited with a small
    # error just because its own scatter happened to come out low.
    safe_counts = np.maximum(counts, 1)
    floor = point_scatter / np.sqrt(safe_counts.astype(float))
    sigma = np.where(np.isfinite(uncertainty) & (uncertainty > 0), uncertainty, floor)
    sigma = np.maximum(sigma, 0.5 * floor)
    if occupied.sum() >= 8:
        deviations = filled[occupied] / sigma[occupied]
        profile_chi2 = float(np.mean(deviations ** 2))
        profile_snr = float(amplitude / max(float(np.median(sigma[occupied])), 1e-9))
    else:
        profile_chi2 = np.nan
        profile_snr = np.nan

    residual = centred - filled[indices]
    reliability = float(np.clip((profile_chi2 - 1.0) / 24.0, 0.0, 1.0) *
                        np.clip(coverage / 0.65, 0.0, 1.0)) if np.isfinite(profile_chi2) else 0.0

    profile.update({
        "raw": filled, "normalised": normalised, "uncertainty": sigma, "counts": counts,
        "coverage": coverage, "amplitude": float(amplitude),
        "residual_scatter": _utils.spread_scale(residual),
        "profile_chi2": profile_chi2, "profile_snr": profile_snr,
        "amplitude_over_point_scatter": float(amplitude / max(point_scatter, 1e-9)),
        "reliability": reliability,
        "phases": phases, "bin_indices": indices, "residuals": residual,
    })
    return profile


def combine_band_profiles(profiles: Mapping[str, Mapping[str, Any]], n_bins: int,
                          align: bool = True) -> Tuple[Dict[str, Any], Dict[str, float], int]:
    """Inverse-variance style combination, weighted by per-band reliability."""
    present = [b for b in ("c", "o") if int(profiles[b].get("n_points", 0)) > 0]
    weights = {"c": 0.0, "o": 0.0}
    shift = 0
    if not present:
        return empty_profile(n_bins), weights, shift
    if len(present) == 1:
        band = present[0]
        weights[band] = 1.0
        return dict(profiles[band]), weights, shift

    for band in present:
        chi2 = _utils.finite_float(profiles[band].get("profile_chi2"), 0.0)
        n = float(profiles[band].get("n_points", 0))
        weights[band] = max(chi2, 0.1) * math.sqrt(max(n, 1.0))
    total = sum(weights.values()) or 1.0
    for band in weights:
        weights[band] = weights[band] / total

    a = _utils.circular_fill(np.asarray(profiles["c"].get("normalised"), dtype=float))
    b = _utils.circular_fill(np.asarray(profiles["o"].get("normalised"), dtype=float))
    if align and np.any(a) and np.any(b):
        shifts = [(float(np.sqrt(np.mean((a - np.roll(b, s)) ** 2))), s) for s in range(n_bins)]
        shift = min(shifts)[1]
        b = np.roll(b, shift)

    combined = dict(empty_profile(n_bins))
    raw = np.zeros(n_bins)
    unc2 = np.zeros(n_bins)
    for band, values in (("c", _utils.circular_fill(np.asarray(profiles["c"].get("raw"), dtype=float))),
                         ("o", _utils.circular_fill(np.asarray(profiles["o"].get("raw"), dtype=float)))):
        w = weights[band]
        if band == "o" and shift:
            values = np.roll(values, shift)
        raw += w * values
        u = np.asarray(profiles[band].get("uncertainty"), dtype=float)
        u = np.where(np.isfinite(u), u, np.nan)
        if band == "o" and shift:
            u = np.roll(u, shift)
        unc2 += (w * np.nan_to_num(u, nan=np.nanmedian(u) if np.any(np.isfinite(u)) else 0.0)) ** 2
    raw -= float(np.median(raw))
    amplitude = _utils.robust_amplitude(raw)
    uncertainty = np.sqrt(unc2)
    occupied = np.ones(n_bins, dtype=bool)
    sigma = np.where(uncertainty > 0, uncertainty, np.nanmedian(uncertainty[uncertainty > 0])
                     if np.any(uncertainty > 0) else 1e-6)

    combined.update({
        "raw": raw,
        "normalised": raw / amplitude if np.isfinite(amplitude) and amplitude > 1e-12
        else np.zeros(n_bins),
        "uncertainty": sigma,
        "counts": (np.asarray(profiles["c"]["counts"]) + np.asarray(profiles["o"]["counts"])),
        "coverage": float(max(_utils.finite_float(profiles[b].get("coverage"), 0.0) for b in present)),
        "amplitude": float(amplitude),
        "profile_chi2": float(np.mean((raw[occupied] / sigma[occupied]) ** 2)),
        "profile_snr": float(amplitude / max(float(np.median(sigma)), 1e-9)),
        "n_points": int(sum(int(profiles[b].get("n_points", 0)) for b in present)),
        "median_error": float(np.nansum([
            weights[b] * _utils.finite_float(profiles[b].get("median_error"), 0.0) for b in present])),
        "scatter_over_error": float(np.nansum([
            weights[b] * _utils.finite_float(profiles[b].get("scatter_over_error"), 0.0) for b in present])),
        "amplitude_over_point_scatter": float(np.nansum([
            weights[b] * _utils.finite_float(profiles[b].get("amplitude_over_point_scatter"), 0.0)
            for b in present])),
    })
    return combined, weights, shift


def lomb_scargle_power(times: Sequence[float], values: Sequence[float],
                       min_period: float = 0.5, max_period: float = 200.0,
                       n_frequencies: int = 3000) -> Dict[str, Any]:
    """The single Lomb-Scargle diagnostic used by this pipeline.

    The period-search pipeline stays authoritative: nothing here ever sets or
    overrides recommended_period_days. This provides (a) the periodogram panel on
    each review plot and (b) ls_peak_ratio, which separates nonvar from a real
    periodic detection -- a flat star has no strong peak.
    """
    from scipy.signal import lombscargle
    t = np.asarray(times, dtype=float)
    v = np.asarray(values, dtype=float)
    good = np.isfinite(t) & np.isfinite(v)
    t, v = t[good], v[good]
    empty = {"periods": np.array([]), "power": np.array([]),
             "ls_peak_power": np.nan, "ls_peak_period": np.nan, "ls_peak_ratio": np.nan}
    if len(t) < 20:
        return empty
    span = float(t.max() - t.min())
    if span <= 0:
        return empty
    v = v - float(np.median(v))
    scale = _utils.spread_scale(v)
    if not np.isfinite(scale) or scale <= 0:
        return empty
    upper = min(max_period, max(span / 2.0, min_period * 2.0))
    periods = np.geomspace(min_period, upper, int(n_frequencies))
    try:
        power = np.asarray(lombscargle(t, v, 2.0 * np.pi / periods, normalize=True),
                           dtype=float)
    except Exception:
        return empty
    if not np.any(np.isfinite(power)):
        return empty
    peak = int(np.nanargmax(power))
    baseline = float(np.nanmedian(power))
    return {"periods": periods, "power": power,
            "ls_peak_power": float(power[peak]),
            "ls_peak_period": float(periods[peak]),
            "ls_peak_ratio": float(power[peak] / max(baseline, 1e-12))}


def align_profile(values: Sequence[float], n_smooth: int = 3) -> Tuple[np.ndarray, int]:
    """Rotate a phase profile to a canonical origin.

    THE FIX FOR THE UMAP GROUPING FAILURE.  Phase is measured from the first
    observation, which is an arbitrary epoch, so two identical stars observed on
    different nights produced completely different 64-bin vectors: measured
    correlation -0.998 and a euclidean distance 30x larger than between two
    genuinely different stars.  UMAP was therefore clustering on epoch, not
    morphology.

    Rotating each profile so its faintest credible (deepest) point sits at bin
    zero makes the block epoch-invariant.  A three-bin circular kernel is used
    only to break noisy near-ties; the unsmoothed depth remains dominant, so a
    narrow eclipse is not averaged away.  In a double-dip profile the deeper
    credible dip therefore defines the origin consistently.
    """
    v = _utils.circular_fill(np.asarray(values, dtype=float))
    n = len(v)
    if n == 0 or not np.any(np.isfinite(v)) or np.nanstd(v) <= 0:
        return np.zeros(n, dtype=float), 0
    width = max(1, min(int(n_smooth), n if n % 2 else max(1, n - 1)))
    if width <= 1:
        smooth = v.copy()
    else:
        radius = width // 2
        smooth = np.mean([np.roll(v, offset)
                          for offset in range(-radius, radius + 1)], axis=0)
    # Magnitudes: larger values are fainter.  Raw depth carries 80% of the
    # decision so even a one- or two-bin eclipse stays eligible as the anchor.
    score = 0.80 * v + 0.20 * smooth
    shift = int(np.argmax(score))
    return np.roll(v, -shift), shift


def fourier_descriptors(values: Sequence[float], n_harmonics: int = 4) -> Dict[str, float]:
    """Phase-origin-invariant Fourier parameters.

    Amplitude ratios R21/R31/R41 and relative phases phi21/phi31/phi41 are the
    standard variable-star descriptors and are invariant to the epoch, so they
    describe shape alone.
    """
    v = _utils.circular_fill(np.asarray(values, dtype=float))
    out: Dict[str, float] = {}
    n = len(v)
    if n == 0 or not np.any(np.isfinite(v)) or np.nanstd(v) <= 0:
        for h in range(2, n_harmonics + 1):
            out["fourier_R%d1" % h] = np.nan
            out["fourier_phi%d1" % h] = np.nan
        return out
    v = v - float(np.mean(v))
    phase = np.arange(n, dtype=float) / n
    amps, phis = [], []
    for h in range(1, n_harmonics + 1):
        a = float(2.0 * np.mean(v * np.cos(2 * np.pi * h * phase)))
        b = float(2.0 * np.mean(v * np.sin(2 * np.pi * h * phase)))
        amps.append(math.hypot(a, b))
        phis.append(math.atan2(b, a))
    for h in range(2, n_harmonics + 1):
        out["fourier_R%d1" % h] = float(amps[h - 1] / max(amps[0], 1e-12))
        delta = phis[h - 1] - h * phis[0]
        out["fourier_phi%d1" % h] = float(np.mod(delta + np.pi, 2 * np.pi) - np.pi)
    return out


def mirror_symmetry(profile: Sequence[float], noise_level: float = 0.0,
                    n_harmonics: int = 4) -> float:
    """Fraction of harmonic power in the EVEN (cosine) terms about the extremum.

    NEW (defect: sine vs asymmetric).  Replaces sinusoid_residual_ratio as the
    decision input.  A profile that is mirror-symmetric about its extremum is
    purely cosine once re-referenced to that phase, so the odd (sine) power
    vanishes and this returns ~1.  A sinusoid AND a triangular or sawtooth-ish
    wave both score high, which is the behaviour asked for; a wave with a
    leading/trailing shoulder scores low.

    A direct mirror correlation was tried first and is not usable: the
    reflection axis is only defined to within one bin, and for a noisy profile
    the argmax can land on either the peak or the trough, so a pure sine scored
    0.73 while an asymmetric profile scored 0.87.
    """
    v = _utils.circular_fill(np.asarray(profile, dtype=float))
    if not np.any(np.isfinite(v)) or np.nanstd(v) <= 0:
        return np.nan
    n = len(v)
    v = v - float(np.mean(v))
    # Only harmonics detected above the noise may contribute. Without this an
    # undetected harmonic contributes pure noise, which splits evenly between
    # the even and odd sums and drags a clean sinusoid down towards 0.5.
    floor = 3.0 * _utils.finite_float(noise_level, 0.0) * math.sqrt(2.0 / n)
    phase = np.arange(n, dtype=float) / n
    harmonics = []
    for h in range(1, n_harmonics + 1):
        a = float(2.0 * np.mean(v * np.cos(2 * np.pi * h * phase)))
        b = float(2.0 * np.mean(v * np.sin(2 * np.pi * h * phase)))
        if math.hypot(a, b) >= floor:
            harmonics.append((h, a, b))
    if not harmonics:
        return np.nan
    # Search for the BEST symmetry axis rather than assuming the profile
    # extremum.  On a noisy sinusoid argmax lands 2-3 bins off the true peak,
    # and a 3-bin error alone costs ~0.08 of symmetry, which made clean sines
    # plateau below the gate and made the measure non-monotonic.
    offsets = np.arange(0.0, 1.0, 1.0 / (4 * n))
    best = 0.0
    for shift in offsets:
        even = odd = 0.0
        for h, a, b in harmonics:
            angle = 2.0 * np.pi * h * shift
            # rotate the harmonic phase to the trial axis
            ar = a * math.cos(angle) + b * math.sin(angle)
            br = -a * math.sin(angle) + b * math.cos(angle)
            even += ar * ar
            odd += br * br
        score = even / max(even + odd, 1e-12)
        if score > best:
            best = score
    return float(best)


def profile_peak_count(profile: Sequence[float], noise_level: float = 0.0,
                       prominence: float = 0.35) -> int:
    """Number of distinct significant extrema; >=2 means 'bumps'.

    The prominence floor is raised in proportion to the noise, otherwise a
    weakly detected sinusoid grows spurious bumps out of bin-to-bin scatter and
    is wrongly routed to asymmetric_periodic.
    """
    prominence = max(prominence, 4.0 * _utils.finite_float(noise_level, 0.0))
    v = _utils.circular_fill(np.asarray(profile, dtype=float))
    if not np.any(np.isfinite(v)):
        return 0
    v = v - np.median(v)
    scale = np.max(np.abs(v))
    if scale <= 1e-12:
        return 0
    v = v / scale
    n = len(v)
    smooth = np.convolve(np.r_[v[-3:], v, v[:3]], np.ones(5) / 5.0, mode="same")[3:3 + n]
    peaks = 0
    for i in range(n):
        left, right = smooth[(i - 1) % n], smooth[(i + 1) % n]
        if smooth[i] >= left and smooth[i] >= right and smooth[i] >= prominence:
            if smooth[i] > smooth[(i - 2) % n] and smooth[i] > smooth[(i + 2) % n]:
                peaks += 1
    return int(peaks)


def profile_shape_metrics(normalised: Sequence[float], amplitude: float,
                          bin_sigma: float) -> Dict[str, float]:
    keys = ("dip_depth_norm", "flare_depth_norm", "dip_duty_cycle", "dip_width_bins",
            "secondary_dip_depth_norm", "secondary_dip_phase_separation",
            "out_of_dip_variation", "out_of_flare_variation",
            "flare_dominance", "flare_duty_cycle",
            "dip_dominance", "dip_significance",
            "mirror_symmetry", "profile_peak_count", "sinusoid_residual_ratio",
            "harmonic_energy_ratio", "skewness")
    values = np.asarray(normalised, dtype=float)
    if not len(values) or not np.any(np.isfinite(values)) or np.nanstd(values) <= 0:
        return {k: np.nan for k in keys}
    values = _utils.circular_fill(values)
    n_bins = len(values)
    median = float(np.median(values))
    # Percentiles, not min/max. A phase fold contains many outliers by
    # construction, and a single bad bin must not define the shape.
    dip_depth = float(np.percentile(values, 98) - median)
    flare_depth = float(median - np.percentile(values, 2))
    threshold = median + max(0.5 * dip_depth, 1e-12)
    width = _utils.longest_circular_run(values >= threshold)

    primary = int(np.argmax(values))
    # Cap the exclusion window. For a broad dip, 2x the half-max width covered
    # almost the whole profile, leaving no baseline to measure flatness against,
    # so out_of_dip_variation came back NaN and every broad dipper was rejected.
    exclusion = int(min(max(2, 2 * width + 1), max(2, n_bins // 5)))
    allowed = np.ones(n_bins, dtype=bool)
    allowed[(np.arange(primary - exclusion, primary + exclusion + 1) % n_bins)] = False
    if allowed.any():
        candidates = np.flatnonzero(allowed)
        best = candidates[int(np.argmax(values[allowed]))]
        secondary = float(values[best] - median)
        separation = abs(best - primary) / float(n_bins)
        separation = float(min(separation, 1.0 - separation))
    else:
        secondary, separation = 0.0, 0.0

    # Fourier descriptors, retained as UMAP features only.
    x = np.arange(n_bins, dtype=float) / n_bins
    design = [np.ones(n_bins)]
    for h in range(1, 5):
        design.extend([np.sin(2 * np.pi * h * x), np.cos(2 * np.pi * h * x)])
    matrix = np.column_stack(design)
    beta, _, _, _ = np.linalg.lstsq(matrix, values, rcond=None)
    fundamental = matrix[:, :3].dot(beta[:3])
    residual_ratio = _utils.robust_scale(values - fundamental) / max(_utils.robust_scale(values), 1e-9)
    coefficients = [math.hypot(float(beta[2 * h - 1]), float(beta[2 * h])) for h in range(1, 5)]
    harmonic_ratio = float(sum(c ** 2 for c in coefficients[1:]) /
                           max(sum(c ** 2 for c in coefficients), 1e-12))

    amp = _utils.finite_float(amplitude, 0.0)
    sig = max(_utils.finite_float(bin_sigma, np.nan), 1e-9)
    # Flatness of the profile OUTSIDE the deepest feature. This is what
    # separates a transit (flat baseline, one dip) from a wave (varies
    # everywhere), and a flare (flat baseline, one brightening) from a wave.
    outside = np.ones(n_bins, dtype=bool)
    outside[(np.arange(primary - exclusion, primary + exclusion + 1) % n_bins)] = False
    if outside.sum() >= 8 and dip_depth > 1e-9:
        baseline_spread = float(np.percentile(values[outside], 90)
                                - np.percentile(values[outside], 10))
        out_of_dip_variation = float(baseline_spread / dip_depth)
    else:
        out_of_dip_variation = np.nan
    bright = int(np.argmin(values))
    bright_threshold = median - max(0.5 * flare_depth, 1e-12)
    flare_width = _utils.longest_circular_run(values <= bright_threshold)
    # Flatness outside the brightening. A wave with a sharp peak has a varying
    # baseline; a coherent burst sits on a flat one.
    bright_exclusion = int(min(max(2, 2 * flare_width + 1), max(2, n_bins // 5)))
    outside_bright = np.ones(n_bins, dtype=bool)
    outside_bright[(np.arange(bright - bright_exclusion,
                              bright + bright_exclusion + 1) % n_bins)] = False
    if outside_bright.sum() >= 8 and flare_depth > 1e-9:
        out_of_flare_variation = float(
            (np.percentile(values[outside_bright], 90)
             - np.percentile(values[outside_bright], 10)) / flare_depth)
    else:
        out_of_flare_variation = np.nan

    out = {
        "out_of_dip_variation": out_of_dip_variation,
        "out_of_flare_variation": out_of_flare_variation,
        "flare_dominance": float(flare_depth / max(dip_depth, 1e-9)),
        "flare_duty_cycle": float(flare_width / n_bins),
        "dip_depth_norm": dip_depth,
        "flare_depth_norm": flare_depth,
        "dip_duty_cycle": float(width / n_bins),
        "dip_width_bins": float(width),
        "secondary_dip_depth_norm": secondary,
        "secondary_dip_phase_separation": separation,
        # NEW: separates a dip-shaped fold (>>1) from a sinusoid (~1)
        "dip_dominance": float(dip_depth / max(flare_depth, 1e-9)),
        # NEW: dip depth in units of the per-bin error, in magnitudes
        "dip_significance": float(dip_depth * amp / sig) if np.isfinite(amp) else np.nan,
        "mirror_symmetry": mirror_symmetry(values, noise_level=sig / max(abs(amp), 1e-9)),
        "profile_peak_count": float(profile_peak_count(
            values, noise_level=sig / max(abs(amp), 1e-9))),
        "sinusoid_residual_ratio": float(residual_ratio),
        "harmonic_energy_ratio": harmonic_ratio,
        "skewness": float(pd.Series(values).skew()),
    }
    for i, c in enumerate(coefficients):
        out["fourier_h%d_amplitude" % (i + 1)] = float(c)
    return out


def grouped_excursion_events(frame: pd.DataFrame, z: np.ndarray, mask: np.ndarray,
                             event_type: str, min_points: int,
                             window_days: float) -> List[Dict[str, Any]]:
    """Return auditable raw-time excursion groups, including rejected groups."""
    times = frame["time"].to_numpy(dtype=float)
    idx = np.flatnonzero(np.asarray(mask, dtype=bool))
    if not len(idx):
        return []
    order = np.argsort(times[idx])
    idx = idx[order]
    t = times[idx]
    different_night = np.floor(t[1:]).astype(np.int64) != np.floor(t[:-1]).astype(np.int64)
    breaks = np.flatnonzero((np.diff(t) > window_days) | different_night) + 1
    groups = np.split(np.arange(len(idx)), breaks) if len(breaks) else [np.arange(len(idx))]
    filters = frame["filter"].astype(str).to_numpy()
    errors = frame["err"].to_numpy(dtype=float)
    rows: List[Dict[str, Any]] = []
    for event_number, group in enumerate(groups, start=1):
        points = idx[group]
        event_times = times[points]
        event_filters = sorted(set(filters[points]))
        significance = np.abs(z[points])
        multi_point = len(points) >= max(2, min_points)
        cross_filter = len(event_filters) >= 2 and len(points) >= 2
        passes = bool(multi_point or cross_filter)
        rows.append({
            "event_type": event_type,
            "event_number": event_number,
            "event_time": float(np.median(event_times)),
            "independent_observing_night": int(math.floor(float(np.median(event_times)))),
            "n_measurements": int(len(points)),
            "event_duration_days": float(np.max(event_times) - np.min(event_times)),
            "represented_filters": _utils.join_tags(event_filters),
            "peak_residual_significance": float(np.max(significance)),
            "median_residual_significance": float(np.median(significance)),
            "median_quoted_uncertainty": float(np.median(errors[points])),
            "minimum_quoted_uncertainty": float(np.min(errors[points])),
            "maximum_quoted_uncertainty": float(np.max(errors[points])),
            "is_multi_point": bool(multi_point),
            "has_cross_filter_support": bool(cross_filter),
            "passes_quality_validation": passes,
            "rejection_reason": "" if passes else "single_point_excursion",
        })
    return rows


def residual_event_metrics(frame: pd.DataFrame, profiles: Mapping[str, Mapping[str, Any]],
                           period: float, origin: float, n_bins: int,
                           thresholds: Mapping[str, Any]
                           ) -> Tuple[Dict[str, float], np.ndarray, List[Dict[str, Any]]]:
    sigma_threshold = float(thresholds.get("event_sigma", 5.0))
    min_points = int(thresholds.get("flare_min_points_per_event", 2))
    window = float(thresholds.get("flare_event_window_days", 1.0))

    residuals = np.full(len(frame), np.nan)
    filters = frame["filter"].to_numpy()
    mags = frame["mag"].to_numpy(dtype=float)
    times = frame["time"].to_numpy(dtype=float)
    for band in ("c", "o"):
        where = np.flatnonzero(filters == band)
        if not len(where):
            continue
        centred = mags[where] - np.median(mags[where])
        raw = np.asarray(profiles[band].get("raw"), dtype=float)
        if np.isfinite(period) and period > 0 and np.any(np.isfinite(raw)):
            phases = np.mod((times[where] - origin) / period, 1.0)
            bins = np.minimum((phases * n_bins).astype(int), n_bins - 1)
            residuals[where] = centred - _utils.circular_fill(raw)[bins]
        else:
            residuals[where] = centred

    finite = np.isfinite(residuals)
    empty = {
        "flare_event_count": 0.0, "dimming_event_count": 0.0,
        "flare_asymmetry": 0.0, "flare_point_fraction": 0.0,
        "dimming_point_fraction": 0.0, "strongest_flare_sigma": 0.0,
        "strongest_dimming_sigma": 0.0, "flare_duty_fraction": 0.0,
        "validated_flare_independent_nights": 0.0,
        "validated_flare_median_significance": 0.0,
        "validated_flare_cross_filter_fraction": 0.0,
        "validated_flare_multi_point_fraction": 0.0,
        "validated_flare_well_sampled_event_count": 0.0,
        "validated_flare_cross_filter_event_count": 0.0,
        "single_point_flare_event_count": 0.0,
        "flare_leave_one_event_out_persistent": 0.0,
        "flare_primary_validation_pass": 0.0,
    }
    if not finite.any():
        return empty, residuals, []

    quoted = frame["err"].to_numpy(dtype=float)
    # percentile scale, not MAD: MAD understates heavy photometric tails
    spread = _utils.spread_scale(residuals[finite])
    noise = np.maximum(quoted, max(_utils.finite_float(spread, 0.0), 1e-6))
    z = residuals / noise
    z_safe = np.where(np.isfinite(z), z, 0.0)

    flare_rows = grouped_excursion_events(
        frame, z_safe, (z_safe < -sigma_threshold) & finite,
        "brightening", min_points, window)
    dim_rows = grouped_excursion_events(
        frame, z_safe, (z_safe > sigma_threshold) & finite,
        "dimming", min_points, window)
    validated_flare = [row for row in flare_rows if row["passes_quality_validation"]]
    validated_dim = [row for row in dim_rows if row["passes_quality_validation"]]
    n_flare, n_dim = len(validated_flare), len(validated_dim)
    peak_flare = max((row["peak_residual_significance"] for row in validated_flare), default=0.0)
    peak_dim = max((row["peak_residual_significance"] for row in validated_dim), default=0.0)
    pts_flare = sum(int(row["n_measurements"]) for row in validated_flare)
    pts_dim = sum(int(row["n_measurements"]) for row in validated_dim)
    well_sampled = sum(int(row["n_measurements"] >= 3) for row in validated_flare)
    cross_filter = sum(int(row["has_cross_filter_support"]) for row in validated_flare)
    single_point = sum(int(row["n_measurements"] == 1) for row in flare_rows)
    flare_nights = len({row["independent_observing_night"] for row in validated_flare})
    median_flare_significance = float(np.median([
        row["median_residual_significance"] for row in validated_flare
    ])) if validated_flare else 0.0
    primary_validation = bool(n_flare >= 2 or well_sampled >= 1 or cross_filter >= 1)
    minimum_primary_events = int(thresholds.get("flare_min_events", 2))
    leave_one_out = bool(
        n_flare - 1 >= max(2, minimum_primary_events - 1))
    total = n_flare + n_dim
    n_finite = int(finite.sum())
    metrics = {
        "flare_event_count": float(n_flare),
        "dimming_event_count": float(n_dim),
        # NEW: noise gives ~0.5, real flares ~1.0
        "flare_asymmetry": float(n_flare / total) if total else 0.0,
        "flare_point_fraction": float(np.mean((z_safe < -sigma_threshold)[finite])),
        "dimming_point_fraction": float(np.mean((z_safe > sigma_threshold)[finite])),
        "strongest_flare_sigma": float(peak_flare),
        "strongest_dimming_sigma": float(peak_dim),
        "flare_duty_fraction": float(pts_flare / max(n_finite, 1)),
        "validated_flare_independent_nights": float(flare_nights),
        "validated_flare_median_significance": median_flare_significance,
        "validated_flare_cross_filter_fraction": float(cross_filter / n_flare)
        if n_flare else 0.0,
        "validated_flare_multi_point_fraction": float(sum(
            int(row["is_multi_point"]) for row in validated_flare) / n_flare)
        if n_flare else 0.0,
        "validated_flare_well_sampled_event_count": float(well_sampled),
        "validated_flare_cross_filter_event_count": float(cross_filter),
        "single_point_flare_event_count": float(single_point),
        "flare_leave_one_event_out_persistent": float(leave_one_out),
        "flare_primary_validation_pass": float(primary_validation),
    }
    return metrics, residuals, flare_rows + dim_rows


def cycles_with_dip(times: np.ndarray, mags: np.ndarray, period: float, origin: float,
                    dip_phase: float, half_width_phase: float) -> int:
    """Distinct integer phase cycles containing an in-dip point.

    FIX: replaces coherent_dip_sections, which counted chronological quarters and
    so rejected any dipper whose eclipses fall in one part of the baseline.
    """
    if not np.isfinite(period) or period <= 0 or not len(times):
        return 0
    phase = np.mod((times - origin) / period, 1.0)
    distance = np.abs(phase - dip_phase)
    distance = np.minimum(distance, 1.0 - distance)
    in_dip = distance <= max(half_width_phase, 1.0 / 64.0)
    if not in_dip.any():
        return 0
    level = np.median(mags)
    scale = max(_utils.spread_scale(mags), 1e-9)
    deep = in_dip & (mags > level + 0.5 * scale)
    use = deep if deep.sum() >= 3 else in_dip
    cycles = np.floor((times[use] - origin) / period).astype(np.int64)
    return int(len(np.unique(cycles)))


def chronological_sections(times: Sequence[float], n_sections: int) -> np.ndarray:
    values = np.asarray(times, dtype=float)
    order = np.argsort(values, kind="mergesort")
    sections = np.zeros(len(values), dtype=int)
    for section, indices in enumerate(np.array_split(order, n_sections)):
        sections[indices] = section
    return sections


def _circular_phase_distance(phases: np.ndarray, centre: float) -> np.ndarray:
    distance = np.abs(np.asarray(phases, dtype=float) - float(centre))
    return np.minimum(distance, 1.0 - distance)


def coherent_dimming_metrics(frame: pd.DataFrame, period: float, origin: float,
                             dip_phase: float, duty_cycle: float,
                             dip_significance: float, out_of_dip_variation: float,
                             section_ids: np.ndarray, alias_possible: bool,
                             n_bins: int = 64) -> Dict[str, float]:
    """Independent evidence for a phase-localised dimming.

    Each covered cycle must contain usable in-dip data and, where the cadence
    permits, a nearby baseline. Supporting cycles are counted once regardless
    of the number of same-night exposures. The final score is a transparent
    weighted combination; every component is returned to the source table.
    """
    names = (
        "dip_supporting_cycles", "dip_covered_cycles", "dip_cycle_support_fraction",
        "dip_independent_nights", "dip_supporting_time_sections",
        "phase_time_section_dependence", "dip_section_concentration",
        "dip_single_section_fraction", "phase_coverage_near_dip",
        "phase_coverage_outside_dip", "dip_local_contrast_sigma",
        "dip_cycle_contrast_scatter", "dip_point_quality_fraction",
        "coherent_dimming_folded_significance_component",
        "coherent_dimming_phase_concentration_component",
        "coherent_dimming_cycle_support_component",
        "coherent_dimming_cycle_fraction_component",
        "coherent_dimming_night_support_component",
        "coherent_dimming_section_support_component",
        "coherent_dimming_local_contrast_component",
        "coherent_dimming_outside_stability_component",
        "coherent_dimming_coverage_component",
        "coherent_dimming_point_quality_component",
        "coherent_dimming_seasonal_penalty_component",
        "coherent_dimming_alias_penalty_component", "coherent_dimming_score",
    )
    empty = {name: 0.0 for name in names}
    if not np.isfinite(period) or period <= 0 or len(frame) < 8:
        return empty

    times = frame["time"].to_numpy(dtype=float)
    mags = frame["mag"].to_numpy(dtype=float)
    errors = frame["err"].to_numpy(dtype=float)
    good = np.isfinite(times) & np.isfinite(mags) & np.isfinite(errors) & (errors > 0)
    if good.sum() < 8:
        return empty
    times, mags, errors = times[good], mags[good], errors[good]
    sections = np.asarray(section_ids, dtype=int)[good]
    phases = np.mod((times - origin) / period, 1.0)
    cycles = np.floor((times - origin) / period).astype(np.int64)
    width = float(np.clip(duty_cycle, 0.02, 0.65))
    distance = _circular_phase_distance(phases, dip_phase)
    in_dip = distance <= width / 2.0
    near = (distance > width / 2.0) & (distance <= min(0.49, 1.5 * width))
    outside = distance > min(0.49, 1.5 * width)
    if in_dip.sum() < 2:
        return empty

    global_scale = max(_utils.spread_scale(mags), float(np.median(errors)), 1e-6)
    global_baseline = float(np.median(mags[~in_dip])) if (~in_dip).any() else float(np.median(mags))
    contrasts: List[float] = []
    supporting_cycles: List[int] = []
    supporting_points = np.zeros(len(times), dtype=bool)
    covered = 0
    for cycle in np.unique(cycles[in_dip]):
        same = cycles == cycle
        inside = same & in_dip
        baseline = same & (near | outside)
        if inside.sum() == 0:
            continue
        # A cycle is covered only when a baseline exists in that cycle, except
        # for very broad occultations where the global baseline is the only
        # practical comparison.
        if baseline.sum() < 1 and width < 0.40:
            continue
        covered += 1
        base_level = float(np.median(mags[baseline])) if baseline.any() else global_baseline
        contrast = float(np.median(mags[inside]) - base_level)
        uncertainty = max(global_scale / math.sqrt(max(int(inside.sum()), 1)),
                          float(np.median(errors[inside])))
        contrast_sigma = contrast / max(uncertainty, 1e-9)
        contrasts.append(contrast_sigma)
        if contrast_sigma >= 1.5 and contrast > 0:
            supporting_cycles.append(int(cycle))
            supporting_points |= inside & (mags > base_level)

    supporting = len(set(supporting_cycles))
    fraction = float(supporting / covered) if covered else 0.0
    nights = int(len(np.unique(np.floor(times[supporting_points]).astype(np.int64))))
    supporting_sections = int(len(np.unique(sections[supporting_points])))
    section_basis = supporting_points if supporting_points.any() else in_dip
    section_counts = np.bincount(sections[section_basis],
                                 minlength=max(int(sections.max()) + 1, 1))
    single_section_fraction = float(section_counts.max() / max(section_counts.sum(), 1))

    occupied = np.unique(np.minimum((phases * n_bins).astype(int), n_bins - 1))
    inside_bins = max(1, int(math.ceil(width * n_bins)))
    near_bins = max(1, int(math.ceil(min(1.0, 3.0 * width) * n_bins)))
    phase_coverage_near = float(min(1.0, len(occupied) / near_bins))
    outside_expected = max(1, n_bins - inside_bins)
    outside_occupied = len(np.unique(np.minimum((phases[~in_dip] * n_bins).astype(int), n_bins - 1)))
    phase_coverage_outside = float(min(1.0, outside_occupied / outside_expected))

    # Normalised mutual information between coarse phase and chronological
    # section identifies folds whose apparent shape is created by seasons.
    phase_groups = np.minimum((phases * 8).astype(int), 7)
    joint = np.zeros((8, max(int(sections.max()) + 1, 1)), dtype=float)
    for p, s in zip(phase_groups, sections):
        joint[p, s] += 1.0
    joint /= max(joint.sum(), 1.0)
    pp = joint.sum(axis=1, keepdims=True)
    ps = joint.sum(axis=0, keepdims=True)
    expected = pp @ ps
    valid = (joint > 0) & (expected > 0)
    mutual = float(np.sum(joint[valid] * np.log(joint[valid] / expected[valid])))
    entropy = -float(np.sum(pp[pp > 0] * np.log(pp[pp > 0])))
    phase_section_dependence = float(np.clip(mutual / max(entropy, 1e-9), 0.0, 1.0))

    median_error = max(float(np.median(errors)), 1e-9)
    quality = float(np.mean(errors[in_dip] <= 2.0 * median_error))
    dim_points = mags > global_baseline + 0.5 * global_scale
    concentration = float(np.mean(in_dip[dim_points])) if dim_points.any() else 0.0
    local_contrast = float(np.median(contrasts)) if contrasts else 0.0
    contrast_scatter = (_utils.spread_scale(contrasts) / max(abs(local_contrast), 1e-9)
                        if len(contrasts) >= 3 else 0.0)

    clip = lambda value: float(np.clip(value, 0.0, 1.0))
    components = {
        "coherent_dimming_folded_significance_component": clip(dip_significance / 12.0),
        "coherent_dimming_phase_concentration_component": clip(
            (concentration - width) / max(1.0 - width, 1e-9)),
        "coherent_dimming_cycle_support_component": clip(supporting / 3.0),
        "coherent_dimming_cycle_fraction_component": clip(fraction),
        "coherent_dimming_night_support_component": clip(nights / 3.0),
        "coherent_dimming_section_support_component": clip(supporting_sections / 2.0),
        "coherent_dimming_local_contrast_component": clip(local_contrast / 5.0),
        "coherent_dimming_outside_stability_component": clip(
            1.0 - _utils.finite_float(out_of_dip_variation, 1.0) / 1.2),
        "coherent_dimming_coverage_component": clip(
            0.5 * phase_coverage_near + 0.5 * phase_coverage_outside),
        "coherent_dimming_point_quality_component": clip(quality),
        "coherent_dimming_seasonal_penalty_component": clip(
            0.55 * phase_section_dependence + 0.45 * max(0.0, single_section_fraction - 0.5) / 0.5),
        "coherent_dimming_alias_penalty_component": 0.20 if alias_possible else 0.0,
    }
    positive_names = [name for name in components if "penalty" not in name]
    positive = float(np.mean([components[name] for name in positive_names]))
    score = clip(positive - 0.35 * components["coherent_dimming_seasonal_penalty_component"]
                 - components["coherent_dimming_alias_penalty_component"])
    return {
        "dip_supporting_cycles": float(supporting),
        "dip_covered_cycles": float(covered),
        "dip_cycle_support_fraction": fraction,
        "dip_independent_nights": float(nights),
        "dip_supporting_time_sections": float(supporting_sections),
        "phase_time_section_dependence": phase_section_dependence,
        "dip_section_concentration": single_section_fraction,
        "dip_single_section_fraction": single_section_fraction,
        "phase_coverage_near_dip": phase_coverage_near,
        "phase_coverage_outside_dip": phase_coverage_outside,
        "dip_local_contrast_sigma": local_contrast,
        "dip_cycle_contrast_scatter": float(contrast_scatter),
        "dip_point_quality_fraction": quality,
        **components,
        "coherent_dimming_score": score,
    }


def temporal_coherence_metrics(frame: pd.DataFrame, section_ids: np.ndarray) -> Dict[str, float]:
    """Raw-time coherence diagnostics, deliberately independent of phase."""
    ordered = frame.assign(_section=np.asarray(section_ids, dtype=int)).sort_values("time")
    values = ordered["mag"].to_numpy(dtype=float)
    errors = ordered["err"].to_numpy(dtype=float)
    if len(values) < 6:
        return {"von_neumann_ratio": np.nan, "raw_time_lag1_correlation": np.nan,
                "same_direction_excursion_groups": 0.0, "section_median_range_sigma": 0.0,
                "temporal_coherence_score": 0.0, "irregular_variability_score": 0.0}
    centred = values - float(np.median(values))
    variance = max(float(np.var(centred)), 1e-12)
    eta = float(np.mean(np.diff(centred) ** 2) / variance)
    lag = _utils.safe_corr(centred[:-1], centred[1:], minimum=4)
    scale = max(_utils.spread_scale(centred), float(np.median(errors)), 1e-9)
    signs = np.sign(centred)
    extreme = np.abs(centred) >= 2.0 * scale
    groups = 0
    run = 0
    last_sign = 0.0
    for is_extreme, sign in zip(extreme, signs):
        if is_extreme and sign == last_sign:
            run += 1
        elif is_extreme:
            if run >= 2:
                groups += 1
            run, last_sign = 1, sign
        else:
            if run >= 2:
                groups += 1
            run, last_sign = 0, 0.0
    if run >= 2:
        groups += 1
    medians = ordered.groupby("_section")["mag"].median().to_numpy(dtype=float)
    section_range = float((np.max(medians) - np.min(medians)) / scale) if len(medians) > 1 else 0.0
    coherence = float(np.clip(
        0.35 * np.clip((2.0 - eta) / 1.5, 0.0, 1.0)
        + 0.30 * np.clip(_utils.finite_float(lag, 0.0), 0.0, 1.0)
        + 0.20 * np.clip(groups / 3.0, 0.0, 1.0)
        + 0.15 * np.clip(section_range / 4.0, 0.0, 1.0), 0.0, 1.0))
    scatter_excess = float(np.clip((_utils.robust_scale(centred) / max(np.median(errors), 1e-9) - 1.5) / 4.0,
                                   0.0, 1.0))
    return {"von_neumann_ratio": eta, "raw_time_lag1_correlation": lag,
            "same_direction_excursion_groups": float(groups),
            "section_median_range_sigma": section_range,
            "temporal_coherence_score": coherence,
            "irregular_variability_score": float(coherence * scatter_excess)}


def compare_wave_dimming_models(frame: pd.DataFrame, period: float, origin: float,
                                dip_phase: float, duty_cycle: float) -> Dict[str, float]:
    """Three-fold held-out comparison of a Fourier wave and localised dip.

    Scores are inverse robust prediction errors with a small complexity penalty;
    their signed margin is dimming minus wave. It is evidence, not a claim that
    broad waves and occultations are perfectly separable.
    """
    empty = {"wave_model_score": 0.0, "dimming_model_score": 0.0,
             "wave_dimming_score_margin": 0.0}
    if not np.isfinite(period) or period <= 0 or len(frame) < 24:
        return empty
    ordered = frame.sort_values("time")
    phase = np.mod((ordered["time"].to_numpy(dtype=float) - origin) / period, 1.0)
    values = ordered["mag"].to_numpy(dtype=float)
    errors = ordered["err"].to_numpy(dtype=float)
    distance = _circular_phase_distance(phase, dip_phase)
    width = float(np.clip(duty_cycle, 0.02, 0.65))
    wave_x = np.column_stack([
        np.ones(len(phase)), np.sin(2 * np.pi * phase), np.cos(2 * np.pi * phase),
        np.sin(4 * np.pi * phase), np.cos(4 * np.pi * phase)])
    sigma = max(width / 2.355, 1.0 / 64.0)
    dim_x = np.column_stack([
        np.ones(len(phase)), np.exp(-0.5 * (distance / sigma) ** 2),
        np.exp(-0.5 * (distance / (2.0 * sigma)) ** 2)])
    errors_by_model: Dict[str, List[float]] = {"wave": [], "dimming": []}
    fold_id = np.arange(len(values)) % 3
    for fold in range(3):
        train, test = fold_id != fold, fold_id == fold
        for name, design in (("wave", wave_x), ("dimming", dim_x)):
            try:
                beta, _, _, _ = np.linalg.lstsq(design[train], values[train], rcond=None)
                residual = (values[test] - design[test].dot(beta)) / np.maximum(errors[test], 1e-6)
                errors_by_model[name].append(float(np.median(np.abs(residual))))
            except np.linalg.LinAlgError:
                errors_by_model[name].append(float("inf"))
    wave_error = float(np.median(errors_by_model["wave"])) + 5.0 * math.log(len(values)) / len(values)
    dim_error = float(np.median(errors_by_model["dimming"])) + 3.0 * math.log(len(values)) / len(values)
    wave_score = float(1.0 / (1.0 + max(wave_error, 0.0)))
    dim_score = float(1.0 / (1.0 + max(dim_error, 0.0)))
    return {"wave_model_score": wave_score, "dimming_model_score": dim_score,
            "wave_dimming_score_margin": dim_score - wave_score}


def extract_source_features(source: Mapping[str, Any], period_record: Optional[Mapping[str, Any]],
                            config: Mapping[str, Any]) -> Dict[str, Any]:
    thresholds = config.get("thresholds", {})
    n_bins = int(config.get("number_of_phase_bins", 64))
    n_sections = int(config.get("number_of_time_sections", 4))
    frame = source["data"]
    origin = float(frame["time"].min())
    period = _utils.finite_float((period_record or {}).get("recommended_period_days"))
    period_flags = _utils.split_tags((period_record or {}).get("flags"))
    lowered = " ".join(period_flags).lower()
    alias_possible = "alias" in lowered and "correct" not in lowered

    band_frames = {b: frame.loc[frame["filter"].eq(b)].copy() for b in ("c", "o")}
    band_profiles = {b: phase_profile(band_frames[b], period, n_bins, origin) for b in ("c", "o")}
    consensus, weights, shift = combine_band_profiles(band_profiles, n_bins)

    bin_sigma = float(np.median(np.asarray(consensus.get("uncertainty"), dtype=float)))
    shape = profile_shape_metrics(consensus["normalised"], consensus.get("amplitude"), bin_sigma)

    c_chi2 = _utils.finite_float(band_profiles["c"].get("profile_chi2"), 0.0)
    o_chi2 = _utils.finite_float(band_profiles["o"].get("profile_chi2"), 0.0)
    chi2_gate = float(thresholds.get("periodic_chi2", 5.0))
    c_sig, o_sig = c_chi2 >= chi2_gate, o_chi2 >= chi2_gate
    filter_corr = _utils.safe_corr(band_profiles["c"]["normalised"], band_profiles["o"]["normalised"])
    filter_disagreement = bool(
        c_sig and o_sig and np.isfinite(filter_corr) and
        filter_corr < float(thresholds.get("filter_disagreement_correlation", 0.10)))

    if c_sig and o_sig and not filter_disagreement:
        selected = "consensus"
    elif c_sig and not o_sig:
        selected = "c"
    elif o_sig and not c_sig:
        selected = "o"
    else:
        selected = "consensus_weak"

    # half / double folds: harmonic diagnostics only
    half_distance = double_distance = odd_even = np.nan
    if np.isfinite(period):
        half = combine_band_profiles(
            {b: phase_profile(band_frames[b], period / 2.0, n_bins, origin) for b in ("c", "o")},
            n_bins)[0]
        double = combine_band_profiles(
            {b: phase_profile(band_frames[b], period * 2.0, n_bins, origin) for b in ("c", "o")},
            n_bins)[0]
        a = _utils.circular_fill(np.asarray(consensus["normalised"], dtype=float))
        for other, name in ((half, "half"), (double, "double")):
            b = _utils.circular_fill(np.asarray(other["normalised"], dtype=float))
            d = min(float(np.sqrt(np.mean((a - np.roll(b, s)) ** 2))) for s in range(n_bins))\
                if np.any(a) and np.any(b) else np.nan
            if name == "half":
                half_distance = d
            else:
                double_distance = d
        dv = np.asarray(double["normalised"], dtype=float)
        if np.any(np.isfinite(dv)):
            odd_even = abs(float(np.nanmax(dv[:n_bins // 2])) - float(np.nanmax(dv[n_bins // 2:])))

    events, residuals, event_rows = residual_event_metrics(
        frame, band_profiles, period, origin, n_bins, thresholds)
    for event_row in event_rows:
        event_row.update({
            "source_key": source["source_key"],
            "source_id": source["source_id"],
            "dataset": source["dataset"],
        })

    # One diagnostic implementation only. It never changes the recommended
    # period and is not required for transit eligibility.
    periodogram = lomb_scargle_power(frame["time"].to_numpy(dtype=float),
                                     frame["mag"].to_numpy(dtype=float))

    # --- section evolution
    section_ids = chronological_sections(frame["time"].to_numpy(dtype=float), n_sections)
    section_profiles, section_rows = [], []
    for section in range(n_sections):
        sub = frame.loc[section_ids == section]
        sub_bands = {b: sub.loc[sub["filter"].eq(b)].copy() for b in ("c", "o")}
        combined = combine_band_profiles(
            {b: phase_profile(sub_bands[b], period, n_bins, origin) for b in ("c", "o")},
            n_bins, align=False)[0]
        section_profiles.append(combined)
        section_rows.append({
            "amplitude": _utils.finite_float(combined.get("amplitude")),
            "correlation_full": _utils.safe_corr(combined["normalised"], consensus["normalised"]),
        })

    correlations = [r["correlation_full"] for r in section_rows if np.isfinite(r["correlation_full"])]
    max_section_correlation = max(correlations) if correlations else np.nan
    sections_with_shape = int(sum(1 for c in correlations if c >= 0.55))
    amplitudes = [r["amplitude"] for r in section_rows if np.isfinite(r["amplitude"]) and r["amplitude"] > 0]
    distances = []
    for i in range(len(section_profiles)):
        for j in range(i + 1, len(section_profiles)):
            a = _utils.circular_fill(np.asarray(section_profiles[i]["normalised"], dtype=float))
            b = _utils.circular_fill(np.asarray(section_profiles[j]["normalised"], dtype=float))
            if np.any(a) and np.any(b):
                distances.append(float(np.sqrt(np.mean((a - b) ** 2))))
    amplitude_change = float(np.log(max(amplitudes) / max(min(amplitudes), 1e-9)))\
        if len(amplitudes) >= 2 else 0.0
    min_corr = min(correlations) if correlations else np.nan
    max_distance = max(distances) if distances else 0.0
    evolution = float(max_distance + 0.5 * max(0.0, 1.0 - _utils.finite_float(min_corr, 1.0))
                      + 0.25 * amplitude_change)

    temporal = temporal_coherence_metrics(frame, section_ids)

    # --- dip repetition in CYCLES, not chronological sections
    dip_phase = float(np.argmax(_utils.circular_fill(np.asarray(consensus["normalised"])))) / n_bins
    half_width = 0.5 * _utils.finite_float(shape.get("dip_duty_cycle"), 0.1)
    n_cycles = cycles_with_dip(frame["time"].to_numpy(dtype=float),
                               frame["mag"].to_numpy(dtype=float),
                               period, origin, dip_phase, half_width)
    dimming = coherent_dimming_metrics(
        frame, period, origin, dip_phase,
        _utils.finite_float(shape.get("dip_duty_cycle"), 0.1),
        _utils.finite_float(shape.get("dip_significance"), 0.0),
        _utils.finite_float(shape.get("out_of_dip_variation"), 1.0),
        section_ids, alias_possible, n_bins)
    model_comparison = compare_wave_dimming_models(
        frame, period, origin, dip_phase,
        _utils.finite_float(shape.get("dip_duty_cycle"), 0.1))

    diagnostic: List[str] = []
    if "alias" in lowered:
        diagnostic.append("alias_corrected" if "correct" in lowered else "alias_possible")
    if "harmonic" in lowered or (np.isfinite(half_distance) and half_distance < 0.15):
        diagnostic.append("harmonic_possible")
    if np.isfinite(odd_even) and odd_even > 0.25:
        diagnostic.append("two_p_eclipse_preferred")
    if not np.isfinite(period) or any(w in lowered for w in ("weak", "ambiguous", "uncertain")):
        diagnostic.append("period_weak_or_ambiguous")

    summary: Dict[str, Any] = {
        "source_key": source["source_key"], "source_id": source["source_id"],
        "dataset": source["dataset"], "input_filename": source.get("input_filename", ""),
        "file_fingerprint": source.get("file_fingerprint", ""),
        "recommended_period_days": period,
        "period_search_period_days": period,
        "morphology_period_days": period,
        "period_ratio_used": 1.0,
        "period_choice_reason": "original_recommendation_retained",
        "period_solution_confidence": np.nan,
        "period_promoted_to_2p": False,
        "period_demoted_to_half_p": False,
        "harmonic_ambiguous": bool("ambiguous" in lowered or "harmonic" in lowered),
        "manual_period_override_applied": False,
        "period_table": (period_record or {}).get("period_table", ""),
        "period_flags": _utils.join_tags(period_flags),
        "diagnostic_tags": _utils.join_tags(diagnostic),
        "n_observations": int(len(frame)),
        "n_observations_c": int(len(band_frames["c"])),
        "n_observations_o": int(len(band_frames["o"])),
        "baseline_days": float(frame["time"].max() - frame["time"].min()),
        "filters_used": _utils.join_tags(b for b in ("c", "o") if len(band_frames[b])),
        "selected_filter_or_consensus": selected,
        "c_band_weight": weights["c"], "o_band_weight": weights["o"],
        # --- the corrected significance
        "profile_chi2": _utils.finite_float(consensus.get("profile_chi2"), 0.0),
        "profile_snr": _utils.finite_float(consensus.get("profile_snr"), 0.0),
        "c_profile_chi2": c_chi2, "o_profile_chi2": o_chi2,
        "amplitude_over_point_scatter": _utils.finite_float(consensus.get("amplitude_over_point_scatter")),
        "phase_coverage": _utils.finite_float(consensus.get("coverage"), 0.0),
        "robust_amplitude_mag": _utils.finite_float(consensus.get("amplitude")),
        "median_quoted_error": _utils.finite_float(consensus.get("median_error")),
        "scatter_over_error": _utils.finite_float(consensus.get("scatter_over_error")),
        "bin_sigma_mag": bin_sigma,
        "filter_profile_correlation": filter_corr,
        "filter_disagreement": filter_disagreement,
        "half_period_profile_distance": half_distance,
        "double_period_profile_distance": double_distance,
        "double_period_odd_even_difference": odd_even,
        "ls_peak_power": _utils.finite_float(periodogram.get("ls_peak_power")),
        "ls_peak_period_days": _utils.finite_float(periodogram.get("ls_peak_period")),
        "ls_peak_ratio": _utils.finite_float(periodogram.get("ls_peak_ratio")),
        "evolution_raw_score": evolution,
        "minimum_section_correlation": min_corr,
        "maximum_section_correlation": max_section_correlation,
        "sections_with_shape": float(sections_with_shape),
        "maximum_section_distance": max_distance,
        "section_amplitude_log_range": amplitude_change,
        "cycles_with_dip": float(n_cycles),
        "dip_phase": dip_phase,
    }
    summary.update(shape)
    summary.update(events)
    summary.update(temporal)
    summary.update(dimming)
    summary.update(model_comparison)

    # ---- PERIODIC FEATURE BLOCK ------------------------------------------
    # Aligned bins (epoch-invariant) + phase-invariant Fourier descriptors.
    aligned, align_shift = align_profile(consensus["normalised"])
    summary["profile_align_shift_bins"] = float(align_shift)
    summary.update(fourier_descriptors(consensus["normalised"]))

    periodic_scalars = (
        "profile_chi2", "profile_snr", "dip_depth_norm", "flare_depth_norm",
        "dip_duty_cycle", "dip_dominance", "secondary_dip_depth_norm",
        "secondary_dip_phase_separation", "mirror_symmetry",
        "out_of_dip_variation", "out_of_flare_variation",
        "flare_dominance", "flare_duty_cycle",
        "profile_peak_count", "harmonic_energy_ratio", "skewness",
        "phase_coverage", "scatter_over_error", "ls_peak_ratio",
        "half_period_profile_distance", "double_period_profile_distance",
        "double_period_odd_even_difference",
        "coherent_dimming_score", "dip_cycle_support_fraction",
        "dip_supporting_cycles", "dip_independent_nights",
        "dip_supporting_time_sections", "phase_time_section_dependence",
        "dip_single_section_fraction", "phase_coverage_near_dip",
        "phase_coverage_outside_dip", "dip_local_contrast_sigma",
        "dip_cycle_contrast_scatter",
        "wave_model_score", "dimming_model_score", "wave_dimming_score_margin",
        "fourier_R21", "fourier_R31", "fourier_R41",
        "fourier_phi21", "fourier_phi31", "fourier_phi41",
    )
    # The classifier and measurements retain the full 64-bin profile.  Only the
    # mapping representation is reduced to 32 bins so narrow dips retain twice
    # the former resolution.  Weak/poorly covered profiles contribute no
    # phase-anchored shape, preventing arbitrary noise alignment from becoming
    # apparent morphology; their scalar quality descriptors remain present.
    map_bins = int(config.get("umap_phase_bins", 32))
    map_bins = max(4, min(map_bins, len(aligned)))
    aligned_for_map = np.asarray(aligned, dtype=float)
    profile_reliability = float(np.clip(
        (_utils.finite_float(summary.get("profile_snr"), 0.0) - 1.5) / 2.5, 0.0, 1.0)
        * np.clip((_utils.finite_float(summary.get("phase_coverage"), 0.0) - 0.20) / 0.40,
                  0.0, 1.0))
    if profile_reliability <= 0.0:
        aligned_for_map = np.zeros_like(aligned_for_map)
    else:
        aligned_for_map = aligned_for_map * profile_reliability
    if len(aligned_for_map) % map_bins == 0:
        coarse = aligned_for_map.reshape(map_bins, -1).mean(axis=1)
    else:
        sample_at = np.linspace(0, len(aligned_for_map), map_bins, endpoint=False)
        coarse = np.interp(sample_at, np.arange(len(aligned_for_map)), aligned_for_map,
                           period=len(aligned_for_map))
    periodic_block = np.concatenate([
        coarse,
        [np.log10(1.0 + max(_utils.finite_float(consensus.get("amplitude"), 0.0), 0.0))],
        [summary.get(k, np.nan) for k in periodic_scalars],
    ])
    periodic_names = (["aligned_phase_bin_%02d" % i for i in range(len(coarse))]
                      + ["log_amplitude"] + list(periodic_scalars))

    # ---- TRANSIENT / EVOLUTION FEATURE BLOCK ------------------------------
    # Raw per-section bins are NOT used: sections with no coverage became zero
    # vectors, and those produced tight artificial clusters unrelated to
    # morphology. Descriptors below are defined regardless of coverage.
    amplitude_reference = max(_utils.finite_float(consensus.get("amplitude"), 0.0), 1e-9)
    section_amplitudes, section_levels, section_correlations = [], [], []
    for index, profile in enumerate(section_profiles):
        section_amplitudes.append(_utils.finite_float(profile.get("amplitude"), np.nan)
                                  / amplitude_reference)
        raw_section = np.asarray(profile.get("raw"), dtype=float)
        section_levels.append(float(np.nanmedian(raw_section))
                              if np.any(np.isfinite(raw_section)) else np.nan)
        section_correlations.append(section_rows[index]["correlation_full"])
    level_drift = (float(np.nanmax(section_levels) - np.nanmin(section_levels))
                   / amplitude_reference) if np.any(np.isfinite(section_levels)) else np.nan

    transient_scalars = (
        "evolution_raw_score", "minimum_section_correlation",
        "maximum_section_distance", "section_amplitude_log_range",
        "flare_event_count", "dimming_event_count", "flare_asymmetry",
        "flare_point_fraction", "dimming_point_fraction",
        "flare_duty_fraction", "strongest_flare_sigma", "strongest_dimming_sigma",
        "scatter_over_error", "profile_chi2", "phase_coverage", "ls_peak_ratio",
        "maximum_section_correlation", "sections_with_shape",
        "von_neumann_ratio", "raw_time_lag1_correlation",
        "same_direction_excursion_groups", "section_median_range_sigma",
        "temporal_coherence_score", "irregular_variability_score",
    )
    transient_block = np.concatenate([
        np.asarray(section_amplitudes, dtype=float),
        np.asarray(section_correlations, dtype=float),
        [level_drift,
         np.log10(1.0 + max(_utils.finite_float(summary.get("robust_amplitude_mag"), 0.0), 0.0)),
         np.log10(max(_utils.finite_float(summary.get("baseline_days"), 1.0), 1.0)),
         np.log10(max(float(summary.get("n_observations", 1)), 1.0))],
        [summary.get(k, np.nan) for k in transient_scalars],
    ])
    transient_names = (
        ["section%d_relative_amplitude" % i for i in range(n_sections)]
        + ["section%d_correlation" % i for i in range(n_sections)]
        + ["section_level_drift", "log_amplitude", "log_baseline_days",
           "log_n_observations"]
        + list(transient_scalars))

    return {
        "summary": summary,
        "periodic_features": np.asarray(periodic_block, dtype=float),
        "periodic_names": periodic_names,
        "transient_features": np.asarray(transient_block, dtype=float),
        "transient_names": transient_names,
        # kept for plotting
        "periodogram": {k: periodogram[k] for k in ("periods", "power")},
        "consensus": {k: consensus[k] for k in ("raw", "normalised", "counts")},
        "aligned_profile": np.asarray(aligned, dtype=float),
        "ls_periods": periodogram.get("periods"), "ls_power": periodogram.get("power"),
        "band_profiles": {b: {"raw": band_profiles[b]["raw"],
                              "normalised": band_profiles[b]["normalised"]}
                          for b in ("c", "o")},
        "section_profiles": [np.asarray(p["normalised"], dtype=float) for p in section_profiles],
        "residuals": residuals,
        "event_rows": event_rows,
        "data": frame,
        "origin": origin,
    }


# ===========================================================================
# REPRESENTATION
# ===========================================================================


def feature_config_hash(config: Mapping[str, Any]) -> str:
    payload = {k: config.get(k) for k in S.FEATURE_CONFIG_KEYS}
    payload["schema"] = S.FEATURE_SCHEMA_VERSION
    return _utils.hash_json(payload)


def cache_path(version_dir: Path, source_key: str, cache_key: str) -> Path:
    return Path(version_dir) / "cache" / ("%s_%s.joblib" % (_utils.safe_name(source_key, 40),
                                                                    cache_key[:12]))


def _feature_worker(source: Mapping[str, Any], period_record: Optional[Mapping[str, Any]],
                    config: Mapping[str, Any], path: str, force: bool
                    ) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """Module-level so joblib pickles only ONE source per task, not the whole set.

    Only the compact summary and feature vectors travel back to the parent. A
    heavy record (light curve, profiles, residuals) is cached only when an
    external detailed diagnostic is unavailable; production morphology plots
    are rendered directly from the already-loaded raw O-band source mapping.
    """
    cache = Path(path)
    light_cache = cache.with_suffix(".light.joblib")
    if not force and light_cache.exists():
        try:
            light = joblib.load(light_cache)
            light["cache_path"] = str(cache)
            return light, None
        except Exception:
            pass
    try:
        record = extract_source_features(source, period_record, config)
    except Exception as error:
        return None, {"source_id": source.get("source_id", ""),
                      "dataset": source.get("dataset", ""),
                      "reason": "feature_extraction_failed: %s" % error,
                      "traceback": traceback.format_exc(limit=3)}
    light = {
        "summary": record["summary"],
        "aligned_profile": np.asarray(record.get("aligned_profile"), dtype=float),
        "periodic_features": record["periodic_features"],
        "periodic_names": record["periodic_names"],
        "transient_features": record["transient_features"],
        "transient_names": record["transient_names"],
        "event_rows": list(record.get("event_rows", [])),
        "cache_path": str(cache),
    }
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        retain_full = (not bool(source.get("existing_period_plot"))
                       or bool(config.get(
                           "cache_full_records_with_existing_period_plot", False)))
        if retain_full:
            joblib.dump(record, cache, compress=3)
        joblib.dump({k: light[k] for k in light if k != "cache_path"},
                    light_cache, compress=3)
    except Exception:
        pass
    return light, None


def extract_all_features(sources: Mapping[str, Mapping[str, Any]],
                         periods: Mapping[str, Mapping[str, Any]],
                         config: Mapping[str, Any], version_dir: Path,
                         logger: logging.Logger) -> Tuple[List[Dict[str, Any]], pd.DataFrame]:
    cache_key = feature_config_hash(config)
    force = bool(config.get("force_recompute_features", False))
    n_jobs = int(config.get("n_jobs", -1))
    keys = list(sources.keys())
    logger.info("Extracting features for %d sources (n_jobs=%d)", len(keys), n_jobs)

    jobs = []
    for key in keys:
        source = sources[key]
        path = cache_path(version_dir, key, cache_key + _utils.hash_json([str(source.get("file_fingerprint", "")), periods.get(key)]))
        jobs.append((source, periods.get(key), path))

    if n_jobs == 1 or len(keys) < 8:
        results = [_feature_worker(src, per, config, str(path), force)
                   for src, per, path in jobs]
    else:
        results = joblib.Parallel(n_jobs=n_jobs, backend="loky", verbose=0,
                                  batch_size=8, max_nbytes="50M")(
            joblib.delayed(_feature_worker)(src, per, config, str(path), force)
            for src, per, path in jobs)
    records = [r for r, _ in results if r is not None]
    failures = [f for _, f in results if f is not None]
    if failures:
        logger.warning("%d sources failed feature extraction", len(failures))
        _utils.atomic_write_csv(pd.DataFrame(failures), Path(version_dir) / 'tables/processing_failures.csv')
        raise RuntimeError(f'{len(failures)} morphology sources failed feature extraction; '
                           'successful feature caches are saved. Review processing_failures.csv and resume.')
    return records, pd.DataFrame(failures)
