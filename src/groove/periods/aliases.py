from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import numpy as np
import pandas as pd
from . import settings as S
from . import folding as _folding
from . import loading as _loading
from . import periodograms as _periodograms
from . import validation as _validation




# =============================================================================
# PERIOD, HARMONIC AND ALIAS HELPERS
# =============================================================================
def harmonic_relation(period: float, reference: float, tolerance: float = S.HARMONIC_TOLERANCE_FRACTION) -> str:
    if not (np.isfinite(period) and np.isfinite(reference)) or period <= 0 or reference <= 0:
        return ""
    ratio = period / reference
    if abs(ratio - 1.0) <= tolerance:
        return "direct"
    for order in range(2, S.HARMONIC_MAX_ORDER + 1):
        short = 1.0 / order
        if abs(ratio - short) / short <= tolerance:
            return f"P/{order}"
        if abs(ratio - order) / order <= tolerance:
            return f"{order}P"
    return ""


def universal_alias_match(period: float) -> str:
    if not np.isfinite(period) or period <= 0:
        return ""
    for label, alias in S.UNIVERSAL_ALIAS_PERIODS.items():
        if abs(period - alias) / alias <= S.UNIVERSAL_ALIAS_TOLERANCE:
            return label
    return ""


def field_key_from_radec(ra_deg: float, dec_deg: float) -> tuple[int, int] | None:
    if not (np.isfinite(ra_deg) and np.isfinite(dec_deg)):
        return None
    return int(np.floor(float(ra_deg) / S.FIELD_BIN_DEG)), int(np.floor(float(dec_deg) / S.FIELD_BIN_DEG))


def field_key_text(ra_deg: float, dec_deg: float) -> str:
    key = field_key_from_radec(ra_deg, dec_deg)
    return "unknown" if key is None else f"{key[0]}_{key[1]}"


# =============================================================================
# ALIAS MEMORY LEARNING
# =============================================================================
def _cluster_periods_across_stars(star_periods: list[list[float]], n_stars: int) -> list[dict[str, Any]]:
    clusters: list[dict[str, Any]] = []
    for periods in star_periods:
        matched_cluster_indices: set[int] = set()
        for p in periods:
            if not np.isfinite(p) or p <= 0:
                continue
            placed = False
            for i, cl in enumerate(clusters):
                centre = float(cl["centre"])
                if abs(p - centre) / centre <= S.FIELD_PERIOD_CLUSTER_TOLERANCE:
                    if i not in matched_cluster_indices:
                        cl["stars"] = int(cl["stars"]) + 1
                        cl["members"].append(p)
                        cl["centre"] = float(np.median(cl["members"]))
                        matched_cluster_indices.add(i)
                    placed = True
                    break
            if not placed:
                clusters.append({"centre": float(p), "stars": 1, "members": [float(p)]})
                matched_cluster_indices.add(len(clusters) - 1)
    for cl in clusters:
        cl["hit_fraction"] = int(cl["stars"]) / max(n_stars, 1)
        cl["period_days"] = float(np.median(np.asarray(cl["members"], dtype=float)))
    return clusters


def build_field_alias_inventory(summary: pd.DataFrame, series: str | None = None) -> pd.DataFrame:
    """Learn per field, counting unique stars rather than filter measurements.

    Auto uses a star's combined peaks when available (including references),
    otherwise pools its O/C peaks. A star can hit a cluster only once.
    Explicit o/c/combined retains the original single-series algorithm.
    """
    series = S.ALIAS_LEARNING_SERIES if series is None else series
    if series not in {"auto", "o", "c", "combined"}:
        raise ValueError("alias_learning_series must be auto, o, c or combined")
    needed = {"series", "source_id", "ra_deg", "dec_deg", "ls_top_periods_days"}
    if summary.empty or not needed.issubset(summary.columns):
        return pd.DataFrame()
    bands = ["o", "c", "combined"] if series == "auto" else [series]
    work = summary.loc[summary["series"].astype(str).isin(bands)].copy()
    work = work.dropna(subset=["source_id"])
    # Current-run rows precede reference rows: retain current measurements when
    # the same source and band appears in both, without counting it twice.
    work = work.drop_duplicates(["source_id", "series"])
    work = work.dropna(subset=["ra_deg", "dec_deg"])
    if work.empty:
        if series != "auto":
            print(f"  [warning] No {series} rows available for field alias learning; "
                  "use alias_learning_series: auto for O/C-only runs.")
        return pd.DataFrame()

    stars: list[dict[str, Any]] = []
    for source_id, group in work.groupby("source_id", sort=False):
        combined = group.loc[group["series"].eq("combined")]
        chosen = combined if series == "auto" and not combined.empty else group
        metadata = chosen.iloc[0]
        peaks = []
        for value in chosen["ls_top_periods_days"]:
            peaks.extend(_loading.parse_float_list(value)[:S.MAX_PEAKS_FOR_FIELD_LEARNING])
        stars.append({"source_id": source_id, "ra_deg": metadata["ra_deg"],
                      "dec_deg": metadata["dec_deg"], "learning_peaks": peaks})
    work = pd.DataFrame(stars)

    work["ra_bin"] = np.floor(work["ra_deg"].astype(float) / S.FIELD_BIN_DEG).astype(int)
    work["dec_bin"] = np.floor(work["dec_deg"].astype(float) / S.FIELD_BIN_DEG).astype(int)

    rows: list[dict[str, Any]] = []
    for (ra_bin, dec_bin), group in work.groupby(["ra_bin", "dec_bin"]):
        n_stars = len(group)
        if n_stars < S.FIELD_MIN_STARS:
            continue
        star_periods: list[list[float]] = []
        for _, row in group.iterrows():
            peaks = row["learning_peaks"]
            # Universal aliases are already universal; field inventory focuses on
            # additional local pile-ups. Keep non-universal only.
            peaks = [p for p in peaks if p > 0 and not universal_alias_match(p)]
            star_periods.append(peaks)
        clusters = _cluster_periods_across_stars(star_periods, n_stars)
        for cl in clusters:
            if float(cl["hit_fraction"]) >= S.FIELD_ALIAS_MIN_FRACTION:
                rows.append(
                    {
                        "ra_bin": int(ra_bin),
                        "dec_bin": int(dec_bin),
                        "field_key": f"{int(ra_bin)}_{int(dec_bin)}",
                        "field_bin_deg": S.FIELD_BIN_DEG,
                        "alias_period_days": float(cl["period_days"]),
                        "n_stars_in_field": int(n_stars),
                        "n_stars_hit": int(cl["stars"]),
                        "hit_fraction": float(cl["hit_fraction"]),
                        "source": "current_run",
                        "updated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    }
                )
    return pd.DataFrame(rows)


def load_reference_summaries() -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for path in S.REFERENCE_SUMMARY_CSVS:
        try:
            p = Path(path)
            if p.exists():
                frames.append(pd.read_csv(p, dtype={"source_id": str}, low_memory=False))
        except Exception as exc:
            print(f"  [warning] Could not read reference summary {path}: {exc}")
    return pd.concat(frames, ignore_index=True, sort=False) if frames else pd.DataFrame()


def load_alias_memory() -> pd.DataFrame:
    path = Path(S.ALIAS_MEMORY_CSV)
    if path.exists():
        try:
            return pd.read_csv(path, dtype=str, low_memory=False)
        except Exception as exc:
            print(f"  [warning] Could not read alias memory {path}: {exc}")
    return pd.DataFrame()


def merge_alias_inventories(*inventories: pd.DataFrame) -> pd.DataFrame:
    frames = [df.copy() for df in inventories if df is not None and not df.empty]
    if not frames:
        return pd.DataFrame()
    all_rows = pd.concat(frames, ignore_index=True, sort=False)
    needed = {"ra_bin", "dec_bin", "alias_period_days"}
    if not needed.issubset(all_rows.columns):
        return all_rows

    merged_rows: list[dict[str, Any]] = []
    for (ra_bin, dec_bin), group in all_rows.groupby(["ra_bin", "dec_bin"], dropna=False):
        periods = pd.to_numeric(group["alias_period_days"], errors="coerce").dropna().sort_values().to_numpy(float)
        used = np.zeros(len(periods), dtype=bool)
        for i, p0 in enumerate(periods):
            if used[i] or p0 <= 0:
                continue
            mask = np.array([abs(p - p0) / p0 <= S.FIELD_ALIAS_MATCH_TOLERANCE for p in periods]) & ~used
            used[mask] = True
            members = periods[mask]
            sub = group.iloc[np.flatnonzero(mask)] if len(group) == len(periods) else group
            n_stars = pd.to_numeric(sub.get("n_stars_in_field", pd.Series(dtype=float)), errors="coerce").fillna(0).sum()
            n_hit = pd.to_numeric(sub.get("n_stars_hit", pd.Series(dtype=float)), errors="coerce").fillna(0).sum()
            frac = float(n_hit / n_stars) if n_stars > 0 else np.nan
            merged_rows.append(
                {
                    "ra_bin": int(ra_bin),
                    "dec_bin": int(dec_bin),
                    "field_key": f"{int(ra_bin)}_{int(dec_bin)}",
                    "field_bin_deg": S.FIELD_BIN_DEG,
                    "alias_period_days": float(np.median(members)),
                    "n_stars_in_field": int(n_stars) if n_stars > 0 else np.nan,
                    "n_stars_hit": int(n_hit) if n_hit > 0 else np.nan,
                    "hit_fraction": frac,
                    "source": "merged_memory",
                    "updated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                }
            )
    return pd.DataFrame(merged_rows)


def field_alias_match(period: float, ra_deg: float, dec_deg: float, inventory: pd.DataFrame) -> dict[str, Any]:
    if inventory is None or inventory.empty or not np.isfinite(period) or period <= 0:
        return {"field_alias_period": np.nan, "field_alias_fraction": np.nan, "field_alias_hit": False}
    key = field_key_from_radec(ra_deg, dec_deg)
    if key is None:
        return {"field_alias_period": np.nan, "field_alias_fraction": np.nan, "field_alias_hit": False}
    ra_bin, dec_bin = key
    sub = inventory.loc[(inventory["ra_bin"].astype(float) == ra_bin) & (inventory["dec_bin"].astype(float) == dec_bin)]
    if sub.empty:
        return {"field_alias_period": np.nan, "field_alias_fraction": np.nan, "field_alias_hit": False}
    best_period = np.nan
    best_frac = np.nan
    for _, row in sub.iterrows():
        alias = _loading.safe_float(row.get("alias_period_days"), np.nan)
        if np.isfinite(alias) and alias > 0 and abs(period - alias) / alias <= S.FIELD_ALIAS_MATCH_TOLERANCE:
            frac = _loading.safe_float(row.get("hit_fraction"), np.nan)
            if not np.isfinite(best_frac) or (np.isfinite(frac) and frac > best_frac):
                best_period = alias
                best_frac = frac
    return {
        "field_alias_period": float(best_period) if np.isfinite(best_period) else np.nan,
        "field_alias_fraction": float(best_frac) if np.isfinite(best_frac) else np.nan,
        "field_alias_hit": bool(np.isfinite(best_period)),
    }


def alias_diagnostics(period: float, time: np.ndarray, ra_deg: float, dec_deg: float, inventory: pd.DataFrame) -> dict[str, Any]:
    universal = universal_alias_match(period)
    field = field_alias_match(period, ra_deg, dec_deg, inventory)
    window = _periodograms.spectral_window_power(time, 1.0 / period) if np.isfinite(period) and period > 0 else np.nan
    universal_score = 1.0 if universal else 0.0
    field_score = 1.0 if field["field_alias_hit"] else 0.0
    window_score = min(max(window if np.isfinite(window) else 0.0, 0.0), 1.0)
    score = min(1.0, 0.55 * universal_score + 0.55 * field_score + 0.35 * window_score)
    labels = []
    if universal:
        labels.append(f"universal:{universal}")
    if field["field_alias_hit"]:
        labels.append(f"field:{field['field_alias_period']:.6g}d")
    if np.isfinite(window) and window >= S.WINDOW_POWER_WARNING:
        labels.append("window")
    return {
        "alias_score": float(score),
        "alias_labels": ";".join(labels),
        "is_alias_suspect": bool(score >= S.ALIAS_SCORE_THRESHOLD),
        "universal_alias": universal,
        "sampling_window_power": window,
        "window_power_warning": bool(np.isfinite(window) and window >= S.WINDOW_POWER_WARNING),
        **field,
    }


# =============================================================================
# APPLY ALIAS MEMORY TO ROWS / PEAKS
# =============================================================================
def annotate_aliases_and_choose_series_period(summary_rows: list[dict[str, Any]], peak_rows_all: list[dict[str, Any]], inventory: pd.DataFrame) -> None:
    peaks_df = pd.DataFrame(peak_rows_all)
    if peaks_df.empty:
        return
    by_key = {
        (str(r.get("file")), str(r.get("source_id")), str(r.get("series"))): r
        for r in summary_rows
        if str(r.get("status")) == "ok"
    }

    group_cols = ["file", "source_id", "series"] if "file" in peaks_df.columns else ["source_id", "series"]
    for key_values, group in peaks_df.groupby(group_cols, dropna=False):
        if len(group_cols) == 3:
            file_name, source_id, series = key_values
            row = by_key.get((str(file_name), str(source_id), str(series)))
        else:
            source_id, series = key_values
            row = next((r for (f, sid, ser), r in by_key.items() if sid == str(source_id) and ser == str(series)), None)
        if row is None:
            continue
        ra = _loading.safe_float(row.get("ra_deg"), np.nan)
        dec = _loading.safe_float(row.get("dec_deg"), np.nan)
        # We do not have the full time array at this stage, so use previously
        # saved window if available only for raw. Peak rows get universal+field.
        peaks = group.sort_values("rank").copy()
        scored_peaks: list[dict[str, Any]] = []
        top_power = _loading.safe_float(row.get("raw_ls_best_power"), np.nan)
        for _, prow in peaks.iterrows():
            p = _loading.safe_float(prow.get("period_days"), np.nan)
            field = field_alias_match(p, ra, dec, inventory)
            universal = universal_alias_match(p)
            window_score = 0.0
            if int(prow.get("rank", 0)) == 1:
                raw_win = _loading.safe_float(row.get("raw_sampling_window_power"), np.nan)
                window_score = min(max(raw_win if np.isfinite(raw_win) else 0.0, 0.0), 1.0)
            score = min(
                1.0,
                0.50 * (1.0 if universal else 0.0)
                + 0.50 * (1.0 if field["field_alias_hit"] else 0.0)
                + 0.35 * window_score,
            )
            scored_peaks.append(
                {
                    "rank": int(prow.get("rank", 0)),
                    "period": p,
                    "power": _loading.safe_float(prow.get("power"), np.nan),
                    "power_fraction": _loading.safe_float(prow.get("power_fraction_of_best"), np.nan),
                    "alias_score": score,
                    "alias_labels": ";".join([x for x in [f"universal:{universal}" if universal else "", f"field:{field['field_alias_period']:.6g}d" if field["field_alias_hit"] else "", "window" if window_score >= S.WINDOW_POWER_WARNING else ""] if x]),
                    "is_alias": bool(score >= S.ALIAS_SCORE_THRESHOLD),
                }
            )

        if not scored_peaks:
            continue
        original = scored_peaks[0]
        replacement = None
        if original["is_alias"]:
            for cand in scored_peaks[1:]:
                if cand["rank"] > S.MAX_REPLACEMENT_RANK:
                    break
                if cand["is_alias"]:
                    continue
                if cand["power_fraction"] < S.REPLACEMENT_MIN_POWER_FRACTION:
                    continue
                if harmonic_relation(cand["period"], original["period"]):
                    continue
                replacement = cand
                break

        if original["is_alias"] and replacement is not None:
            chosen = replacement
            row["alias_correction_applied"] = True
            row["alias_correction_note"] = f"promoted rank-{replacement['rank']} non-alias peak over alias-like raw peak ({original['alias_labels']})"
        else:
            chosen = original
            row["alias_correction_applied"] = False
            if original["is_alias"]:
                row["alias_correction_note"] = "raw peak alias-like but no strong non-alias replacement; kept and flagged"
            else:
                row["alias_correction_note"] = "raw peak not alias-like; kept"
        row["raw_alias_score"] = original["alias_score"]
        row["raw_alias_labels"] = original["alias_labels"]
        row["raw_is_alias_suspect"] = bool(original["is_alias"])
        row["alias_corrected_period_days"] = chosen["period"]
        row["alias_corrected_rank"] = chosen["rank"]
        row["alias_corrected_power_fraction"] = chosen["power_fraction"]
        row["recommended_series_period_days"] = chosen["period"]
        if chosen["is_alias"]:
            row["series_confidence_class"] = "alias_period_possible_true_or_artifact"
        elif row.get("alias_correction_applied"):
            row["series_confidence_class"] = "alias_corrected"
        else:
            row["series_confidence_class"] = "non_alias_period"


# =============================================================================
# POST-ALIAS HARMONIC RECOMPUTATION
# =============================================================================
def find_2p_peak_support(
    peak_rows_all: list[dict[str, Any]],
    file_name: str,
    source_id: str,
    series: str,
    period: float,
) -> dict[str, Any]:
    """Look for a real LS top-N peak near 2*period after alias correction.

    This fixes the case where the raw peak is an alias near 1 d, a non-alias
    peak is promoted later, and the old 2P candidate still points to ~2 d.
    """
    out = {
        "top_peak_2p_period_days": np.nan,
        "top_peak_2p_rank": np.nan,
        "top_peak_2p_power_fraction": np.nan,
        "top_peak_2p_present": False,
    }
    if not np.isfinite(period) or period <= 0:
        return out
    target = 2.0 * float(period)
    best: dict[str, Any] | None = None
    for row in peak_rows_all:
        if str(row.get("source_id")) != str(source_id) or str(row.get("series")) != str(series):
            continue
        if "file" in row and str(row.get("file")) != str(file_name):
            continue
        p = _loading.safe_float(row.get("period_days"), np.nan)
        rank = _loading.safe_float(row.get("rank"), np.nan)
        if not np.isfinite(p) or p <= 0 or not np.isfinite(rank):
            continue
        if int(rank) > S.HARMONIC_2P_PEAK_MAX_RANK:
            continue
        if abs(p - target) / target <= S.HARMONIC_TOLERANCE_FRACTION:
            frac = _loading.safe_float(row.get("power_fraction_of_best"), np.nan)
            if best is None or _loading.safe_float(best.get("power_fraction_of_best"), -np.inf) < frac:
                best = row
    if best is not None:
        frac = _loading.safe_float(best.get("power_fraction_of_best"), np.nan)
        out.update({
            "top_peak_2p_period_days": _loading.safe_float(best.get("period_days"), np.nan),
            "top_peak_2p_rank": int(_loading.safe_float(best.get("rank"), np.nan)),
            "top_peak_2p_power_fraction": frac,
            "top_peak_2p_present": bool(np.isfinite(frac) and frac >= S.HARMONIC_2P_PEAK_MIN_POWER_FRACTION),
        })
    return out


def update_post_alias_harmonics(
    summary_rows: list[dict[str, Any]],
    peak_rows_all: list[dict[str, Any]],
    plot_payloads: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any] | None, float]],
) -> None:
    """Recompute P-vs-2P tests after alias correction has chosen the series period.

    Earlier versions ran the 2P test only on the raw LS period. That fails when
    the raw period is an alias and the useful non-alias period is promoted later.
    This updates tested_2p_days, odd/even metrics and multi-harmonic metrics for
    the alias-aware recommended_series_period_days.
    """
    row_lookup = {
        (str(r.get("file")), str(r.get("source_id")), str(r.get("series"))): r
        for r in summary_rows
        if str(r.get("status")) == "ok"
    }
    for metadata, prepared, _old_row, payload, catalogue_period in plot_payloads:
        key = (str(metadata.get("file")), str(metadata.get("source_id")), str(prepared.get("series_name")))
        row = row_lookup.get(key)
        if row is None:
            continue
        period = _loading.safe_float(row.get("recommended_series_period_days"), np.nan)
        if not np.isfinite(period) or period <= 0:
            continue
        baseline = _loading.safe_float(row.get("baseline_days"), np.nan)
        if not np.isfinite(baseline):
            baseline = float(np.max(prepared["time"]) - np.min(prepared["time"]))

        fold = _folding.fold_coherence_metrics(prepared["time"], prepared["signal"], prepared["error"], period)
        oe = _folding.odd_even_2p_test(prepared["time"], prepared["signal"], prepared["error"], period)
        mh = _periodograms.multiharmonic_2p_test(prepared["time"], prepared["signal"], prepared["error"], period, baseline)
        peak2p = find_2p_peak_support(peak_rows_all, key[0], key[1], key[2], period)
        cat_match_series = _validation.catalogue_match(period, _loading.safe_float(catalogue_period, np.nan))
        cat_match_2p = _validation.catalogue_match(2.0 * period if np.isfinite(period) else np.nan, _loading.safe_float(catalogue_period, np.nan))
        validation_catalogue_is_2p = bool(
            S.USE_CATALOGUE_FOR_VALIDATION_REVIEW_FLAGS
            and cat_match_series == "P/2"
            and cat_match_2p == "direct"
        )

        row.update({
            "post_alias_fold_valid_bins": fold["fold_valid_bins"],
            "post_alias_fold_amplitude": fold["fold_amplitude"],
            "post_alias_fold_amp_snr": fold["fold_amp_snr"],
            "post_alias_fold_scatter_reduction": fold["fold_scatter_reduction"],
            **oe,
            **mh,
            **peak2p,
            "series_catalogue_match_after_alias": cat_match_series,
            "series_2p_catalogue_match_after_alias": cat_match_2p,
            "validation_catalogue_is_2p_of_series": validation_catalogue_is_2p,
            "series_harmonic_review_needed": bool(
                oe.get("two_p_supported", False)
                or mh.get("mh_2p_supported", False)
                or peak2p.get("top_peak_2p_present", False)
                or validation_catalogue_is_2p
            ),
        })





def update_post_alias_harmonics_from_peaks(summary_rows: list[dict[str, Any]], peak_rows_all: list[dict[str, Any]]) -> None:
    """Lightweight post-alias harmonic review using only saved top peaks.

    This is used in large-run mode where full arrays are not kept in memory.
    It cannot run odd/even tests, but it can still flag cases where a strong top
    peak exists near 2 times the alias-aware period.
    """
    peaks = pd.DataFrame(peak_rows_all)
    if peaks.empty:
        return
    peak_lookup = {
        (str(source_id), str(series)): group.sort_values("rank")
        for (source_id, series), group in peaks.groupby(["source_id", "series"], dropna=False)
    }
    for row in summary_rows:
        if str(row.get("status")) != "ok":
            continue
        p = _loading.safe_float(row.get("recommended_series_period_days"), np.nan)
        if not np.isfinite(p) or p <= 0:
            continue
        p2 = 2.0 * p
        row["post_alias_tested_2p_days"] = p2
        group = peak_lookup.get((str(row.get("source_id")), str(row.get("series"))))
        topn_support = False
        topn_rank = np.nan
        if group is not None and not group.empty:
            for _, prow in group.iterrows():
                q = _loading.safe_float(prow.get("period_days"), np.nan)
                if np.isfinite(q) and q > 0 and abs(q - p2) / p2 <= S.HARMONIC_TOLERANCE_FRACTION:
                    topn_support = True
                    topn_rank = _loading.safe_float(prow.get("rank"), np.nan)
                    break
        row["post_alias_2p_topn_support"] = bool(topn_support)
        row["post_alias_2p_topn_rank"] = topn_rank
        old_status = str(row.get("harmonic_status", ""))
        if topn_support:
            row["harmonic_status"] = "2P_top_peak_review"
            row["harmonic_review"] = True
        elif not old_status:
            row["harmonic_status"] = "2P_not_tested_in_large_run"
            row["harmonic_review"] = False


def source_is_alias_suspect(source_info: dict[str, Any]) -> bool:
    primary = str(source_info.get(
        "primary_classification", source_info.get("source_primary_classification", "")
    )).lower()
    secondary = str(source_info.get(
        "secondary_classification", source_info.get("source_secondary_classification", "")
    )).lower()
    warnings = str(source_info.get("warning_flags", "")).lower()
    alias_flags = str(source_info.get("alias_flags", "")).lower()
    return bool(
        primary == "alias_possible"
        or "alias_possible" in secondary
        or "alias_corrected" in secondary
        or "alias_warning" in warnings
        or "alias_corrected" in warnings
        or bool(alias_flags.strip())
    )


def source_is_harmonic_suspect(source_info: dict[str, Any]) -> bool:
    primary = str(source_info.get(
        "primary_classification", source_info.get("source_primary_classification", "")
    )).lower()
    secondary = str(source_info.get(
        "secondary_classification", source_info.get("source_secondary_classification", "")
    )).lower()
    warnings = str(source_info.get("warning_flags", "")).lower()
    status = str(source_info.get("harmonic_status", "")).lower()
    return bool(
        primary == "harmonic_possible"
        or "harmonic_possible" in secondary
        or "harmonic_review" in warnings
        or "2p_selected" in warnings
        or "p_vs_2p" in status
        or status.startswith("2p_supported")
    )
