from __future__ import annotations
import numpy as np
import pandas as pd
from . import settings as S
from . import loading as _loading




def running_median_baseline(y: np.ndarray, window_pts: int) -> np.ndarray:
    """Return a centred running-median baseline."""
    return (
        pd.Series(y)
        .rolling(
            window=window_pts,
            center=True,
            min_periods=max(5, window_pts // 5),
        )
        .median()
        .to_numpy()
    )


# ============================================================================
# CORE CLEANER
# ============================================================================


def clean_atlas_df(df_raw: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Clean one ATLAS light curve and return all rows with audit flags."""
    df = _loading.normalise_columns(df_raw)

    numeric_cols = [
        "MJD", "m", "dm", "uJy", "duJy", "err", "chi/N", "RA", "Dec",
        "ra", "dec", "x", "y", "maj", "min", "phi", "apfit", "mag5sig",
        "Sky", "flags", "xmatch_fp_period", "xmatch_ls_pday",
        "atlas_object_period",
    ]
    for col in numeric_cols:
        _loading.safe_numeric(df, col)

    df["F"] = df["F"].astype(str).str.strip().str.lower()

    have_flux_input = "uJy" in df.columns and "duJy" in df.columns
    have_mag_input = "m" in df.columns and "dm" in df.columns

    if not have_flux_input:
        if not have_mag_input:
            raise ValueError("Need either (uJy, duJy) or (m, dm) columns.")
        m = df["m"].to_numpy(dtype=float)
        dm = df["dm"].to_numpy(dtype=float)
        df["uJy"] = _loading.abmag_to_uJy(m)
        df["duJy"] = _loading.dm_to_duJy(df["uJy"].to_numpy(dtype=float), dm)

    for col in ["uJy", "duJy", "m", "dm"]:
        _loading.safe_numeric(df, col)

    # Finite required values. Flux is the primary measurement; m/dm are
    # required only if REQUIRE_FINITE_MAG is enabled (see section 4).
    required_for_finite = ["MJD", "uJy", "duJy"]
    if S.REQUIRE_FINITE_MAG and "m" in df.columns and "dm" in df.columns:
        required_for_finite += ["m", "dm"]

    finite_required = np.ones(len(df), dtype=bool)
    for col in required_for_finite:
        finite_required &= np.isfinite(df[col].to_numpy(dtype=float))

    # Broad magnitude/error sanity. Rows with no defined magnitude (typically
    # negative or zero flux) are passed through here and judged on flux alone;
    # rows that DO carry a magnitude must still have a sensible one.
    mag_ok = np.ones(len(df), dtype=bool)
    if "m" in df.columns:
        values = df["m"].to_numpy(dtype=float)
        in_range = (values > S.MAG_MIN) & (values < S.MAG_MAX)
        mag_ok &= np.where(np.isfinite(values), in_range, True)
    if "dm" in df.columns:
        values = df["dm"].to_numpy(dtype=float)
        in_range = (values > S.DM_MIN) & (values < S.DM_MAX)
        mag_ok &= np.where(np.isfinite(values), in_range, True)

    hard_valid = (
        finite_required
        & mag_ok
        & (df["duJy"].to_numpy(dtype=float) > 0)
        & (np.abs(df["uJy"].to_numpy(dtype=float)) < S.ABS_UJY_HARD_MAX)
    )

    if S.DROP_OTHER_FILTERS:
        filt_ok = df["F"].isin(S.KEEP_FILTERS).to_numpy(dtype=bool)
    else:
        filt_ok = np.ones(len(df), dtype=bool)

    hard_reject = (~hard_valid) | (~filt_ok)
    if "mag5sig" in df.columns:
        mag5sig_values = df["mag5sig"].to_numpy(dtype=float)
        hard_reject |= np.isfinite(mag5sig_values) & (
            mag5sig_values < S.MAG5SIG_HARD_FAIL
        )

    # Soft/standard cuts. These are reported separately from hard failures.
    cuts: dict[str, np.ndarray] = {}

    if "err" in df.columns and S.REQUIRE_ERR_ZERO:
        cuts["err==0"] = (
            pd.to_numeric(df["err"], errors="coerce")
            .fillna(999)
            .astype(int)
            .to_numpy()
            == 0
        )

    cuts[f"duJy<{S.DUJY_MAX:g}"] = (
        df["duJy"].to_numpy(dtype=float) < S.DUJY_MAX
    )

    # Significance floor on flux. Mildly negative points are noise and are
    # kept; strongly negative points are subtraction failures and are cut.
    if np.isfinite(S.MIN_SNR):
        flux_values = df["uJy"].to_numpy(dtype=float)
        flux_errors = df["duJy"].to_numpy(dtype=float)
        with np.errstate(divide="ignore", invalid="ignore"):
            snr = np.where(flux_errors > 0, flux_values / flux_errors, np.nan)
        df["snr"] = snr
        # NaN SNR is already handled by the hard-validity duJy>0 requirement,
        # so it must not be double-counted as a failure of this cut.
        cuts[f"SNR>{S.MIN_SNR:g}"] = ~(np.isfinite(snr) & (snr < S.MIN_SNR))

    if "x" in df.columns:
        x = df["x"].to_numpy(dtype=float)
        cuts["x_in"] = (x > S.X_MIN) & (x < S.X_MAX)
    if "y" in df.columns:
        y = df["y"].to_numpy(dtype=float)
        cuts["y_in"] = (y > S.Y_MIN) & (y < S.Y_MAX)
    if "maj" in df.columns:
        maj = df["maj"].to_numpy(dtype=float)
        cuts["maj_in"] = (maj > S.MAJ_MIN) & (maj < S.MAJ_MAX)
    if "min" in df.columns:
        min_axis = df["min"].to_numpy(dtype=float)
        cuts["min_in"] = (min_axis > S.MIN_MIN) & (min_axis < S.MIN_MAX)
    if "apfit" in df.columns:
        apfit = df["apfit"].to_numpy(dtype=float)
        cuts["apfit_in"] = (apfit > S.APFIT_MIN) & (apfit < S.APFIT_MAX)
    if "mag5sig" in df.columns:
        mag5sig = df["mag5sig"].to_numpy(dtype=float)
        cuts[f"mag5sig>{S.MAG5SIG_MIN:g}"] = (
            np.isfinite(mag5sig) & (mag5sig > S.MAG5SIG_MIN)
        )
    if "Sky" in df.columns:
        sky = df["Sky"].to_numpy(dtype=float)
        cuts[f"Sky>{S.SKY_MIN:g}"] = np.isfinite(sky) & (sky > S.SKY_MIN)
    if "flags" in df.columns and S.REQUIRE_FLAGS_ZERO:
        cuts["flags==0"] = (
            pd.to_numeric(df["flags"], errors="coerce")
            .fillna(999)
            .astype(int)
            .to_numpy()
            == 0
        )

    standard_keep = hard_valid & filt_ok & (~hard_reject)
    for mask in cuts.values():
        standard_keep &= mask.astype(bool)

    # Sort data and all masks consistently by MJD.
    original_order = np.argsort(
        df["MJD"].to_numpy(dtype=float),
        kind="mergesort",
    )
    df = df.iloc[original_order].reset_index(drop=True)
    hard_valid = hard_valid[original_order]
    filt_ok = filt_ok[original_order]
    hard_reject = hard_reject[original_order]
    standard_keep = standard_keep[original_order]
    cuts = {name: mask[original_order] for name, mask in cuts.items()}

    baseline = np.full(len(df), np.nan, dtype=float)
    z_residual = np.full(len(df), np.nan, dtype=float)

    baseline_mask = hard_valid & filt_ok
    if np.sum(standard_keep) > 50:
        baseline_mask = standard_keep

    if S.RESCUE_ENABLE and len(df) > 0:
        for _, group in df.groupby("F", sort=False):
            indices = group.index.to_numpy()
            flux = group["uJy"].to_numpy(dtype=float)
            flux_error = group["duJy"].to_numpy(dtype=float)
            group_mask = baseline_mask[indices]

            if np.sum(group_mask) >= max(10, S.BASELINE_WINDOW_PTS // 2):
                working_flux = flux.copy()
                working_flux[~group_mask] = np.nan
                group_baseline = running_median_baseline(
                    working_flux,
                    S.BASELINE_WINDOW_PTS,
                )
                fallback = np.nanmedian(flux[group_mask])
                group_baseline = np.where(
                    np.isfinite(group_baseline),
                    group_baseline,
                    fallback,
                )
            else:
                finite_flux = flux[np.isfinite(flux)]
                fallback = np.nanmedian(finite_flux) if len(finite_flux) else np.nan
                group_baseline = np.full_like(flux, fallback, dtype=float)

            baseline[indices] = group_baseline
            good_error = np.isfinite(flux_error) & (flux_error > 0)
            group_z = np.full_like(flux, np.nan, dtype=float)
            np.divide(
                flux - group_baseline,
                flux_error,
                out=group_z,
                where=good_error,
            )
            z_residual[indices] = group_z

    df["baseline_uJy"] = baseline
    df["z_resid"] = z_residual

    dip_candidate = (
        np.isfinite(z_residual)
        & (z_residual < -S.RESCUE_Z)
    )
    rescued = (
        S.RESCUE_ENABLE
        & dip_candidate
        & (~standard_keep)
        & (~hard_reject)
    )
    final_keep = standard_keep | rescued

    # Human-readable rejection reasons.
    reasons: list[str] = []
    cut_names = list(cuts.keys())
    for index in range(len(df)):
        row_reasons: list[str] = []

        if hard_reject[index]:
            if not hard_valid[index]:
                row_reasons.append("HARD_invalid_nan_inf_or_bad_m_dm_flux")
            if not filt_ok[index]:
                row_reasons.append("HARD_filter")
            if "mag5sig" in df.columns:
                value = df.loc[index, "mag5sig"]
                if (
                    pd.notna(value)
                    and np.isfinite(value)
                    and value < S.MAG5SIG_HARD_FAIL
                ):
                    row_reasons.append(
                        f"HARD_mag5sig<{S.MAG5SIG_HARD_FAIL:g}"
                    )
        elif not standard_keep[index]:
            for name in cut_names:
                if not bool(cuts[name][index]):
                    row_reasons.append(f"fail_{name}")

        if rescued[index]:
            row_reasons.append("RESCUED_dip_candidate")

        reasons.append(";".join(row_reasons))

    df["standard_keep"] = standard_keep
    df["rescued"] = rescued
    df["final_keep"] = final_keep
    df["reject_reason"] = reasons

    clean = df.loc[final_keep]
    raw_mjd = pd.to_numeric(df["MJD"], errors="coerce")
    clean_mjd = pd.to_numeric(clean["MJD"], errors="coerce")

    def _count_filter(frame: pd.DataFrame, filter_name: str) -> int:
        return int(frame["F"].astype(str).eq(filter_name).sum())

    def _median_for_filter(
        frame: pd.DataFrame,
        filter_name: str,
        column: str,
    ) -> float:
        if column not in frame.columns:
            return np.nan
        values = pd.to_numeric(
            frame.loc[frame["F"].astype(str).eq(filter_name), column],
            errors="coerce",
        )
        values = values[np.isfinite(values)]
        return float(values.median()) if len(values) else np.nan

    summary = {
        "raw_rows": int(len(df)),
        "hard_reject": int(np.sum(hard_reject)),
        "standard_keep": int(np.sum(standard_keep)),
        "rescued": int(np.sum(rescued)),
        "final_keep": int(np.sum(final_keep)),
        "removed": int(len(df) - np.sum(final_keep)),
        "fraction_kept": (
            float(np.sum(final_keep) / len(df)) if len(df) else np.nan
        ),
        "cuts_applied": cut_names,
        "filters_present_raw": sorted(
            df["F"].dropna().astype(str).unique().tolist()
        ),
        "filters_present_clean": sorted(
            clean["F"].dropna().astype(str).unique().tolist()
        ),
        "n_c_raw": _count_filter(df, "c"),
        "n_o_raw": _count_filter(df, "o"),
        "n_c_clean": _count_filter(clean, "c"),
        "n_o_clean": _count_filter(clean, "o"),
        "median_dm_c_clean": _median_for_filter(clean, "c", "dm"),
        "median_dm_o_clean": _median_for_filter(clean, "o", "dm"),
        "median_duJy_c_clean": _median_for_filter(clean, "c", "duJy"),
        "median_duJy_o_clean": _median_for_filter(clean, "o", "duJy"),
        "mjd_min_raw": float(raw_mjd.min()) if raw_mjd.notna().any() else np.nan,
        "mjd_max_raw": float(raw_mjd.max()) if raw_mjd.notna().any() else np.nan,
        "baseline_days_raw": (
            float(raw_mjd.max() - raw_mjd.min())
            if raw_mjd.notna().sum() > 1
            else np.nan
        ),
        "mjd_min_clean": (
            float(clean_mjd.min()) if clean_mjd.notna().any() else np.nan
        ),
        "mjd_max_clean": (
            float(clean_mjd.max()) if clean_mjd.notna().any() else np.nan
        ),
        "baseline_days_clean": (
            float(clean_mjd.max() - clean_mjd.min())
            if clean_mjd.notna().sum() > 1
            else np.nan
        ),
    }
    return df, summary
