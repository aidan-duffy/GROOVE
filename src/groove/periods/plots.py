from __future__ import annotations
import math
import gc
from pathlib import Path
from typing import Any
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from . import settings as S
from . import aliases as _aliases
from . import classify as _classify
from . import files as _files
from . import folding as _folding
from . import loading as _loading
from . import periodograms as _periodograms




def create_master_review_plot(recommendations: pd.DataFrame) -> str:
    """Save one overview image with all recommended periods colour-coded by tag."""
    if recommendations is None or recommendations.empty or S.PLOT_MODE.strip().lower() == "none":
        return ""
    plot_dir = S.plot_root()
    plot_dir.mkdir(parents=True, exist_ok=True)
    output = plot_dir / "000_master_review_all_stars.png"

    rec = recommendations.copy()
    rec["recommended_period_days"] = pd.to_numeric(rec["recommended_period_days"], errors="coerce")
    rec = rec.sort_values(["recommendation_label", "recommended_period_days"], na_position="last").reset_index(drop=True)
    if rec.empty:
        return ""

    fig_height = max(8, min(40, 0.18 * len(rec) + 3))
    fig, ax = plt.subplots(figsize=(13, fig_height), constrained_layout=True)
    y = np.arange(len(rec))
    for label in S.RECOMMENDATION_LABELS:
        m = rec["recommendation_label"].astype(str).eq(label)
        if not np.any(m):
            continue
        ax.scatter(
            rec.loc[m, "recommended_period_days"],
            y[m],
            s=26,
            alpha=0.85,
            label=f"{label} ({int(np.sum(m))})",
            color=S.TAG_COLORS.get(label),
        )
    ax.set_xscale("log")
    ax.set_xlabel("Recommended period (days)")
    ax.set_ylabel("Source index")
    ax.set_title("ATLAS period-search master review: all sources")
    ax.grid(alpha=0.25, which="both")
    ax.legend(loc="best", fontsize=9)

    if len(rec) <= S.MASTER_REVIEW_MAX_LABELS:
        for i, row in rec.iterrows():
            period = _loading.safe_float(row.get("recommended_period_days"), np.nan)
            if not np.isfinite(period) or period <= 0:
                continue
            label_text = str(row.get("source_id", ""))[-6:]
            ax.text(period, i, f"  {label_text}", va="center", fontsize=6, alpha=0.7)

    _files.save_figure(fig, output, dpi=S.PLOT_DPI, bbox_inches="tight")
    plt.close(fig)
    return str(output)


# =============================================================================
# PLOTTING
# =============================================================================
def plot_best_per_star(
    metadata: dict[str, Any],
    prepared: dict[str, Any],
    result: dict[str, Any],
    row: dict[str, Any],
    catalogue_period: float,
    bls: dict[str, Any] | None = None,
    recommendation_label: str = "",
) -> str:
    if S.PLOT_MODE.strip().lower() == "none" or prepared["series_name"] not in S.PLOT_SERIES:
        return ""
    nrows = 3 if bls is not None else 2
    fig, axes = plt.subplots(
        nrows, 1,
        figsize=(12, 10 if bls is not None else 8),
        gridspec_kw={"height_ratios": [1.0, 0.8, 1.5] if bls is not None else [1.0, 1.5]},
        constrained_layout=True,
    )
    if nrows == 2:
        ax_ls, ax_fold = axes
    else:
        ax_ls, ax_bls, ax_fold = axes

    order = np.argsort(result["period"])
    ax_ls.plot(np.asarray(result["period"])[order], np.asarray(result["power"])[order], linewidth=0.7, color="k")
    if S.PLOT_PERIOD_AXIS_LOG:
        ax_ls.set_xscale("log")
    ax_ls.set_xlabel("Period (days)")
    ax_ls.set_ylabel("LS power")
    ax_ls.grid(alpha=0.25, which="both")

    raw = _loading.safe_float(row.get("raw_ls_best_period_days"), np.nan)
    rec = _loading.safe_float(row.get("recommended_series_period_days"), np.nan)
    p2 = _loading.safe_float(row.get("tested_2p_days"), np.nan)
    for label, period, style in [
        ("raw LS", raw, "--"),
        ("alias-aware series", rec, "-"),
        ("2P candidate", p2, ":"),
    ]:
        if np.isfinite(period) and period > 0:
            ax_ls.axvline(period, linestyle=style, linewidth=1.3, label=f"{label}={period:.6g} d")

    # Mark the actual top LS peaks with symbols so it is obvious which peak is
    # rank 1. This removes the visual ambiguity where vertical lines can hide a
    # nearby peak on a log x-axis.
    for rank, (peak_period, peak_power, _idx) in enumerate(result.get("peaks", [])[:3], start=1):
        if np.isfinite(peak_period) and np.isfinite(peak_power):
            ax_ls.scatter([peak_period], [peak_power], s=42, zorder=5)
            ax_ls.text(peak_period, peak_power, f" r{rank}", fontsize=8, va="bottom", ha="left")
            ax_ls.plot([], [], linestyle="none", marker="o", label=f"LS rank {rank}={peak_period:.6g} d")

    if np.isfinite(catalogue_period) and catalogue_period > 0 and S.PLOT_CATALOGUE_PERIOD_IN_LEGEND:
        ax_ls.axvline(catalogue_period, linestyle=":", linewidth=1.5, label=f"catalogue={catalogue_period:.6g} d")
    ax_ls.legend(fontsize=8, loc="best")
    ax_ls.set_title(f"LS periodogram — {metadata['object_name']} / {prepared['series_name']}")

    if bls is not None and nrows == 3:
        ax_bls.plot(bls["period_grid"], bls["power"], linewidth=0.7, color="k")
        if S.PLOT_PERIOD_AXIS_LOG:
            ax_bls.set_xscale("log")
        ax_bls.axvline(bls["best_period"], linestyle="--", linewidth=1.2, label=f"BLS={bls['best_period']:.6g} d, SDE={bls['sde']:.1f}")
        ax_bls.set_xlabel("Period (days)")
        ax_bls.set_ylabel("BLS SNR")
        ax_bls.grid(alpha=0.25, which="both")
        ax_bls.legend(fontsize=8, loc="best")

    automatic_fold_period = rec if np.isfinite(rec) and rec > 0 else raw
    fold_period = (
        float(S.FORCED_FOLD_PERIOD_DAYS)
        if S.FORCED_FOLD_PERIOD_DAYS is not None
        else automatic_fold_period
    )
    phase = _folding.fold_phase(prepared["time"], fold_period)
    plot_signal = _folding.repeated(prepared["plot_signal"])
    plot_error = _folding.repeated(prepared["plot_error"])
    bands = _folding.repeated(prepared["band"])
    original_time = np.asarray(prepared["time"], dtype=float)
    time_min = float(np.nanmin(original_time))
    time_max = float(np.nanmax(original_time))
    time_span = time_max - time_min
    if np.isfinite(time_span) and time_span > 0:
        original_time_segment = np.floor(
            (original_time - time_min) / time_span * S.PLOT_TIME_SEGMENTS
        ).astype(int)
        original_time_segment = np.clip(original_time_segment, 0, S.PLOT_TIME_SEGMENTS - 1)
    else:
        original_time_segment = np.zeros(len(original_time), dtype=int)
    time_segment = _folding.repeated(original_time_segment)
    keep = _folding.plot_sigma_mask(plot_signal, bands)
    segment_edges_years = np.linspace(0.0, time_span / 365.25, S.PLOT_TIME_SEGMENTS + 1)
    for segment in range(S.PLOT_TIME_SEGMENTS):
        for band in sorted(set(bands.astype(str))):
            use = (time_segment == segment) & (bands.astype(str) == band) & keep
            if not np.any(use):
                continue
            ax_fold.errorbar(
                phase[use], plot_signal[use], yerr=plot_error[use],
                ms=2.5, alpha=0.55, elinewidth=0.5, capsize=0,
                marker=S.BAND_MARKERS.get(band, "."), linestyle="none",
                color=S.PLOT_TIME_SEGMENT_COLORS[segment],
            )

    # Keep time colours and filter markers in separate legends so that both
    # meanings stay clear on combined c/o plots.
    timeline_handles = []
    for segment in range(S.PLOT_TIME_SEGMENTS):
        fraction_start = 100.0 * segment / S.PLOT_TIME_SEGMENTS
        fraction_end = 100.0 * (segment + 1) / S.PLOT_TIME_SEGMENTS
        handle = ax_fold.plot(
            [], [], color=S.PLOT_TIME_SEGMENT_COLORS[segment], alpha=0.55,
            marker="o", linestyle="none",
            label=(
                f"{fraction_start:.0f}--{fraction_end:.0f}%: "
                f"{segment_edges_years[segment]:.2f}--"
                f"{segment_edges_years[segment + 1]:.2f} yr"
            ),
        )[0]
        timeline_handles.append(handle)

    band_handles = []
    for band in sorted(set(bands.astype(str))):
        handle = ax_fold.plot(
            [], [], color="0.35", alpha=0.55,
            marker=S.BAND_MARKERS.get(band, "."), linestyle="none",
            label=f"{band}-band marker" if band != "single" else "data marker",
        )[0]
        band_handles.append(handle)
    if prepared["invert_y"]:
        ax_fold.invert_yaxis()
    ax_fold.set_xlabel("Phase")
    ax_fold.set_ylabel("Magnitude" if prepared["plot_signal_type"] == "magnitude" else r"Flux ($\mu$Jy)")
    ax_fold.grid(alpha=0.25)
    timeline_legend = ax_fold.legend(
        handles=timeline_handles, title="Fraction of observed timeline",
        fontsize=8, title_fontsize=8, loc="upper right",
    )
    ax_fold.add_artist(timeline_legend)
    ax_fold.legend(
        handles=band_handles, title="Band marker",
        fontsize=8, title_fontsize=8, loc="upper left",
    )
    fold_period_label = (
        "forced period" if S.FORCED_FOLD_PERIOD_DAYS is not None else "series period"
    )
    ax_fold.set_title(
        f"Folded at {fold_period_label} P={fold_period:.4f} d | "
        f"alias: {row.get('alias_correction_note', '')} | 2P: {row.get('two_p_note', '')}"
    )

    fig.suptitle(
        f"source={metadata['source_id']} | N={prepared['n_points']} | baseline={prepared['baseline_days']:.1f} d | "
        f"primary={row.get('primary_classification', 'unknown')} | "
        f"secondary={_classify.secondary_classification_from_row(row)} | "
        f"peak ratios P1/P2={_loading.safe_float(row.get('best_to_second_power_ratio'), np.nan):.2f}, "
        f"P1/P4={_loading.safe_float(row.get('best_to_fourth_power_ratio'), np.nan):.2f} | "
        f"series class={row.get('series_confidence_class', 'unknown')}",
        fontsize=11,
    )
    primary_label = row.get("primary_classification", "unknown")
    folders = _files.plot_review_folders(row, str(primary_label))

    output_name = _files.normal_plot_output_name(metadata, prepared["series_name"])
    # A rerun may change a classification. Remove only this normal plot's old
    # copies so obsolete strength/review folders do not retain it.
    normal_folder_names = set(S.TAG_FOLDER_MAP.values()) | {
        S.BEST_PER_STAR_DIRNAME, "alias", "harmonic"
    }
    series_plot_root = S.plot_root() / _loading.sanitize_filename(prepared["series_name"])
    for old_folder_name in normal_folder_names:
        old_output = series_plot_root / old_folder_name / output_name
        if old_output.is_file():
            old_output.unlink()

    outputs: list[Path] = []
    for folder in folders:
        plot_dir = series_plot_root / folder
        plot_dir.mkdir(parents=True, exist_ok=True)
        output = plot_dir / output_name
        _files.save_figure(fig, output, dpi=S.PLOT_DPI, bbox_inches="tight")
        if not output.is_file() or output.stat().st_size <= 0:
            raise OSError(f"Plot was not written correctly: {output}")
        outputs.append(output)
    plt.close(fig)
    row["plot_folders"] = ";".join(folder.as_posix() for folder in folders)
    row["plot_paths_all"] = ";".join(str(output) for output in outputs)
    row["plot_error"] = ""
    return str(outputs[0]) if outputs else ""


# =============================================================================
# OPTIONAL EXPANDED PHASE-FOLD DIAGNOSTICS
# =============================================================================
def plot_diagnostic_fold_axis(ax: Any, prepared: dict[str, Any], period: float) -> None:
    """Plot one phase fold using the same time colours and band markers."""
    phase = _folding.fold_phase(prepared["time"], period)
    plot_signal = _folding.repeated(prepared["plot_signal"])
    plot_error = _folding.repeated(prepared["plot_error"])
    bands = _folding.repeated(prepared["band"]).astype(str)

    original_time = np.asarray(prepared["time"], dtype=float)
    time_min = float(np.nanmin(original_time))
    time_max = float(np.nanmax(original_time))
    time_span = time_max - time_min
    if np.isfinite(time_span) and time_span > 0:
        original_segment = np.floor(
            (original_time - time_min) / time_span * S.PLOT_TIME_SEGMENTS
        ).astype(int)
        original_segment = np.clip(original_segment, 0, S.PLOT_TIME_SEGMENTS - 1)
    else:
        original_segment = np.zeros(len(original_time), dtype=int)
    time_segment = _folding.repeated(original_segment)
    keep = _folding.plot_sigma_mask(plot_signal, bands)

    for segment in range(S.PLOT_TIME_SEGMENTS):
        for band in sorted(set(bands)):
            use = (time_segment == segment) & (bands == band) & keep
            if not np.any(use):
                continue
            ax.errorbar(
                phase[use], plot_signal[use], yerr=plot_error[use],
                ms=2.3, alpha=0.55, elinewidth=0.45, capsize=0,
                marker=S.BAND_MARKERS.get(band, "."), linestyle="none",
                color=S.PLOT_TIME_SEGMENT_COLORS[segment],
            )

    ax.set_xlim(0.0, 2.0 if S.PLOT_TWO_PHASE_CYCLES else 1.0)
    ax.set_xlabel("Phase")
    ax.set_ylabel("Magnitude" if prepared["plot_signal_type"] == "magnitude" else r"Flux ($\mu$Jy)")
    ax.grid(alpha=0.25)


def diagnostic_legend_handles(ax: Any, prepared: dict[str, Any]) -> tuple[list[Any], list[Any]]:
    """Create separate timeline-colour and band-marker legend handles."""
    time_span_years = _loading.safe_float(prepared.get("baseline_days"), 0.0) / 365.25
    segment_edges_years = np.linspace(0.0, time_span_years, S.PLOT_TIME_SEGMENTS + 1)
    timeline_handles: list[Any] = []
    for segment in range(S.PLOT_TIME_SEGMENTS):
        fraction_start = 100.0 * segment / S.PLOT_TIME_SEGMENTS
        fraction_end = 100.0 * (segment + 1) / S.PLOT_TIME_SEGMENTS
        timeline_handles.append(
            ax.plot(
                [], [], color=S.PLOT_TIME_SEGMENT_COLORS[segment], alpha=0.55,
                marker="o", linestyle="none",
                label=(
                    f"{fraction_start:.0f}--{fraction_end:.0f}%: "
                    f"{segment_edges_years[segment]:.2f}--"
                    f"{segment_edges_years[segment + 1]:.2f} yr"
                ),
            )[0]
        )

    band_handles: list[Any] = []
    for band in sorted(set(np.asarray(prepared["band"]).astype(str))):
        band_handles.append(
            ax.plot(
                [], [], color="0.35", alpha=0.55,
                marker=S.BAND_MARKERS.get(band, "."), linestyle="none",
                label=f"{band}-band" if band != "single" else "data",
            )[0]
        )
    return timeline_handles, band_handles


def make_diagnostic_axes(n_panels: int) -> tuple[Any, list[Any]]:
    ncols = min(max(int(S.EXTRA_FOLD_MAX_COLUMNS), 1), max(n_panels, 1))
    nrows = int(math.ceil(max(n_panels, 1) / ncols))
    fig, axes = plt.subplots(
        nrows, ncols,
        figsize=(5.2 * ncols, 4.0 * nrows + 1.8),
        sharey=True,
        squeeze=False,
    )
    return fig, list(np.asarray(axes, dtype=object).ravel())


def finish_diagnostic_figure(
    fig: Any,
    axes: list[Any],
    used_panels: int,
    prepared: dict[str, Any],
    title: str,
    subtitle: str,
) -> None:
    for ax in axes[used_panels:]:
        ax.set_visible(False)
    if prepared.get("invert_y", False) and used_panels:
        # With shared y axes this must only be called once, otherwise repeated
        # calls toggle the direction back and forth.
        axes[0].invert_yaxis()

    timeline_handles, band_handles = diagnostic_legend_handles(axes[0], prepared)
    fig.suptitle(title, fontsize=12, y=0.985)
    fig.text(0.5, 0.945, subtitle, ha="center", va="top", fontsize=9)
    timeline_legend = fig.legend(
        handles=timeline_handles,
        title="Fraction of observed timeline",
        loc="lower center", bbox_to_anchor=(0.43, 0.012),
        fontsize=8, title_fontsize=8,
        ncol=min(S.PLOT_TIME_SEGMENTS, 4),
    )
    fig.add_artist(timeline_legend)
    fig.legend(
        handles=band_handles,
        title="Band marker",
        loc="lower right", bbox_to_anchor=(0.985, 0.012),
        fontsize=8, title_fontsize=8,
        ncol=max(1, len(band_handles)),
    )
    fig.tight_layout(rect=[0.02, 0.13, 0.98, 0.90])


def peak_candidates_from_saved_rows(
    series_row: dict[str, Any],
    saved_peak_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return ranked peaks, falling back to the semicolon columns if needed."""
    candidates: list[dict[str, Any]] = []
    ordered_peaks = sorted(saved_peak_rows, key=lambda r: _loading.safe_float(r.get("rank"), np.inf))
    best_power = _loading.safe_float(ordered_peaks[0].get("power"), np.nan) if ordered_peaks else np.nan
    for peak in ordered_peaks:
        period = _loading.safe_float(peak.get("period_days"), np.nan)
        if not np.isfinite(period) or period <= 0:
            continue
        power = _loading.safe_float(peak.get("power"), np.nan)
        power_fraction = _loading.safe_float(peak.get("power_fraction_of_best"), np.nan)
        if not np.isfinite(power_fraction) and np.isfinite(power) and np.isfinite(best_power) and best_power > 0:
            power_fraction = power / best_power
        candidates.append(
            {
                "rank": int(_loading.safe_float(peak.get("rank"), len(candidates) + 1)),
                "period_days": period,
                "power": power,
                "power_fraction": power_fraction,
            }
        )
    if candidates:
        return candidates

    periods = _loading.parse_float_list(series_row.get("ls_top_periods_days"))
    powers = _loading.parse_float_list(series_row.get("ls_top_powers"))
    for index, period in enumerate(periods):
        power = powers[index] if index < len(powers) else np.nan
        candidates.append(
            {
                "rank": index + 1,
                "period_days": period,
                "power": power,
                "power_fraction": power / powers[0] if powers and powers[0] > 0 else np.nan,
            }
        )
    return candidates


def plot_alias_candidate_folds(
    metadata: dict[str, Any],
    prepared: dict[str, Any],
    series_row: dict[str, Any],
    saved_peak_rows: list[dict[str, Any]],
    source_info: dict[str, Any],
    trigger_reason: str,
    alias_inventory: pd.DataFrame,
) -> dict[str, Any] | None:
    requested_n = max(int(S.ALIAS_N_PEAKS_TO_PLOT), 1)
    candidates = peak_candidates_from_saved_rows(series_row, saved_peak_rows)[:requested_n]
    if not candidates:
        return None

    recommended = _classify.series_period_from_row(series_row)
    if (
        S.ALIAS_INCLUDE_RECOMMENDED_IF_OUTSIDE_TOP_N
        and np.isfinite(recommended) and recommended > 0
        and not any(_classify.period_is_same(c["period_days"], recommended) for c in candidates)
    ):
        candidates.append(
            {
                "rank": "recommended",
                "period_days": recommended,
                "power": np.nan,
                "power_fraction": _loading.safe_float(series_row.get("alias_corrected_power_fraction"), np.nan),
            }
        )

    fig, axes = make_diagnostic_axes(len(candidates))
    candidate_periods: list[float] = []
    for ax, candidate in zip(axes, candidates):
        period = _loading.safe_float(candidate.get("period_days"), np.nan)
        candidate_periods.append(period)
        plot_diagnostic_fold_axis(ax, prepared, period)
        fold = _folding.fold_coherence_metrics(prepared["time"], prepared["signal"], prepared["error"], period)
        alias = _aliases.alias_diagnostics(
            period,
            prepared["time"],
            _loading.safe_float(metadata.get("ra_deg"), np.nan),
            _loading.safe_float(metadata.get("dec_deg"), np.nan),
            alias_inventory,
        )
        rank = candidate.get("rank", "?")
        power = _loading.safe_float(candidate.get("power"), np.nan)
        selected_text = " | RECOMMENDED" if _classify.period_is_same(period, recommended) else ""
        power_text = f"{power:.3g}" if np.isfinite(power) else "n/a"
        fold_snr = _loading.safe_float(fold.get("fold_amp_snr"), np.nan)
        fold_text = f"{fold_snr:.2f}" if np.isfinite(fold_snr) else "n/a"
        alias_text = str(alias.get("alias_labels", "")) or "none"
        ax.set_title(
            f"LS rank {rank} | P={period:.7g} d | power={power_text}{selected_text}\n"
            f"fold S/N={fold_text} | diagnostic alias score={alias['alias_score']:.2f} | {alias_text}",
            fontsize=9,
        )

    title = (
        f"Alias-candidate phase folds | {metadata.get('object_name', '')} | "
        f"source={metadata.get('source_id', '')} | series={prepared['series_name']}"
    )
    subtitle = (
        f"file={metadata.get('file', '')} | trigger={trigger_reason} | "
        f"alias-aware series period={recommended:.7g} d | "
        f"correction={series_row.get('alias_correction_note', '')}"
    )
    finish_diagnostic_figure(fig, axes, len(candidates), prepared, title, subtitle)

    output_dir = (
        S.plot_root() / _loading.sanitize_filename(prepared["series_name"])
        / "alias" / S.EXTRA_FOLD_SUBDIR
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    unique_stem = _loading.sanitize_filename(
        f"{metadata.get('source_id', '')}_{metadata.get('object_name', '')}_{prepared['series_name']}",
        max_length=180,
    )
    output = output_dir / f"{unique_stem}_alias_top{requested_n}_folds.png"
    _files.save_figure(fig, output, dpi=S.PLOT_DPI, bbox_inches="tight")
    plt.close(fig)
    if not output.is_file() or output.stat().st_size <= 0:
        raise OSError(f"Alias diagnostic was not written correctly: {output}")
    return {
        "file": metadata.get("file", ""),
        "source_id": metadata.get("source_id", ""),
        "object_name": metadata.get("object_name", ""),
        "series": prepared["series_name"],
        "diagnostic_type": "alias_candidates",
        "trigger_reason": trigger_reason,
        "requested_top_n": requested_n,
        "periods_plotted_days": ";".join(f"{p:.10g}" for p in candidate_periods),
        "recommended_period_days": recommended,
        "recommendation_label": source_info.get("recommendation_label", ""),
        "destination_folder": "alias",
        "output_path": str(output),
        "output_size_bytes": int(output.stat().st_size),
        "status": "made",
    }


def plot_harmonic_candidate_folds(
    metadata: dict[str, Any],
    prepared: dict[str, Any],
    series_row: dict[str, Any],
    source_info: dict[str, Any],
    trigger_reason: str,
) -> dict[str, Any] | None:
    base_period = _loading.safe_float(source_info.get("recommended_period_days"), np.nan)
    if not np.isfinite(base_period) or base_period <= 0:
        base_period = _loading.safe_float(source_info.get("consensus_period_days"), np.nan)
    if not np.isfinite(base_period) or base_period <= 0:
        base_period = _classify.series_period_from_row(series_row)
    if not np.isfinite(base_period) or base_period <= 0:
        return None

    factors: list[float] = []
    for raw_factor in S.HARMONIC_PERIOD_FACTORS:
        factor = _loading.safe_float(raw_factor, np.nan)
        if not np.isfinite(factor) or factor <= 0:
            continue
        if not any(abs(factor - old) <= 1e-12 for old in factors):
            factors.append(factor)
    if not factors:
        return None

    fig, axes = make_diagnostic_axes(len(factors))
    periods: list[float] = []
    search_min = _loading.safe_float(series_row.get("search_min_period_days"), np.nan)
    search_max = _loading.safe_float(series_row.get("search_max_period_days"), np.nan)
    for ax, factor in zip(axes, factors):
        period = base_period * factor
        periods.append(period)
        plot_diagnostic_fold_axis(ax, prepared, period)
        fold = _folding.fold_coherence_metrics(prepared["time"], prepared["signal"], prepared["error"], period)
        fold_snr = _loading.safe_float(fold.get("fold_amp_snr"), np.nan)
        scatter = _loading.safe_float(fold.get("fold_scatter_reduction"), np.nan)
        fold_text = f"{fold_snr:.2f}" if np.isfinite(fold_snr) else "n/a"
        scatter_text = f"{scatter:.3f}" if np.isfinite(scatter) else "n/a"
        range_note = ""
        if np.isfinite(search_min) and np.isfinite(search_max) and not (search_min <= period <= search_max):
            range_note = " | outside LS range"
        ax.set_title(
            f"{factor:g} x P | trial period={period:.7g} d{range_note}\n"
            f"fold S/N={fold_text} | scatter reduction={scatter_text}",
            fontsize=9,
        )

    title = (
        f"Harmonic phase-fold test | {metadata.get('object_name', '')} | "
        f"source={metadata.get('source_id', '')} | series={prepared['series_name']}"
    )
    subtitle = (
        f"file={metadata.get('file', '')} | trigger={trigger_reason} | "
        f"final recommended P={base_period:.7g} d | "
        f"status={source_info.get('harmonic_status', series_row.get('harmonic_status', ''))}"
    )
    finish_diagnostic_figure(fig, axes, len(factors), prepared, title, subtitle)

    output_dir = (
        S.plot_root() / _loading.sanitize_filename(prepared["series_name"])
        / "harmonic" / S.EXTRA_FOLD_SUBDIR
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    unique_stem = _loading.sanitize_filename(
        f"{metadata.get('source_id', '')}_{metadata.get('object_name', '')}_{prepared['series_name']}",
        max_length=180,
    )
    output = output_dir / f"{unique_stem}_harmonic_folds.png"
    _files.save_figure(fig, output, dpi=S.PLOT_DPI, bbox_inches="tight")
    plt.close(fig)
    if not output.is_file() or output.stat().st_size <= 0:
        raise OSError(f"Harmonic diagnostic was not written correctly: {output}")
    return {
        "file": metadata.get("file", ""),
        "source_id": metadata.get("source_id", ""),
        "object_name": metadata.get("object_name", ""),
        "series": prepared["series_name"],
        "diagnostic_type": "harmonic_tests",
        "trigger_reason": trigger_reason,
        "harmonic_factors": ";".join(f"{f:g}" for f in factors),
        "periods_plotted_days": ";".join(f"{p:.10g}" for p in periods),
        "recommended_period_days": base_period,
        "recommendation_label": source_info.get("recommendation_label", ""),
        "destination_folder": "harmonic",
        "output_path": str(output),
        "output_size_bytes": int(output.stat().st_size),
        "status": "made",
    }


def plot_from_saved_results(
    files: list[Path],
    summary_rows: list[dict[str, Any]],
    recommendations: pd.DataFrame,
    external_catalogue: dict[str, float],
) -> None:
    """Second-pass plotting without keeping all periodograms in memory.

    This reruns LS/BLS only for plotting and immediately frees arrays after each
    plot. It makes large runs much safer. It also means best_per_star can contain
    every successful plot without making the first pass run out of memory.
    """
    if S.PLOT_MODE.strip().lower() == "none" or not S.MAKE_PLOTS_AFTER_FINAL:
        return

    row_lookup: dict[tuple[str, str, str], dict[str, Any]] = {
        (str(r.get("file")), str(r.get("source_id")), str(r.get("series"))): r
        for r in summary_rows
        if str(r.get("status")) == "ok"
    }
    rows_by_file: dict[str, list[dict[str, Any]]] = {}
    for row in summary_rows:
        if str(row.get("status")) != "ok" or str(row.get("series")) not in S.PLOT_SERIES:
            continue
        rows_by_file.setdefault(str(row.get("file")), []).append(row)
    source_info_lookup: dict[str, dict[str, Any]] = {}
    if recommendations is not None and not recommendations.empty:
        source_info_lookup = {
            str(row.get("source_id")): row.to_dict()
            for _, row in recommendations.iterrows()
        }

    print("=" * 88)
    print("SECOND PASS: creating plots without storing all periodograms in memory")
    print("=" * 88)
    made = 0
    reused = 0
    for file_index, path in enumerate(files, start=1):
        cached_file_rows = rows_by_file.get(path.name, [])
        if not cached_file_rows:
            continue

        # A normal ATLAS input can create combined, o and c plots. Check all
        # successful series before reopening the CSV or recalculating LS/BLS.
        if (
            S.SKIP_ALREADY_PLOTTED
            and all(_files.normal_plot_outputs_are_complete(row) for row in cached_file_rows)
        ):
            for row in cached_file_rows:
                _files.record_existing_normal_plot_paths(row)
            reused += len(cached_file_rows)
            if file_index % max(S.CHECKPOINT_EVERY_N_FILES, 1) == 0:
                _files.safe_write_csv(summary_rows, S.OUTPUT_DIR / "tables" / "ls_period_search_summary.csv")
                print(
                    f"  plot checkpoint: {file_index:,}/{len(files):,} files, "
                    f"new plots made={made:,}, existing plots reused={reused:,}"
                )
            continue

        try:
            raw = pd.read_csv(path, dtype=str, low_memory=False)
            df = _loading.normalise_columns(raw)
            metadata = _loading.extract_metadata(df, path)
            catalogue_period = _loading.safe_float(metadata["embedded_catalogue_period_days"], np.nan)
            ext_period = external_catalogue.get(str(metadata["source_id"]))
            if ext_period is not None and np.isfinite(ext_period):
                catalogue_period = float(ext_period)

            for series in S.SERIES_TO_RUN:
                if series not in S.PLOT_SERIES:
                    continue
                key = (str(metadata.get("file")), str(metadata.get("source_id")), str(series))
                row = row_lookup.get(key)
                if row is None:
                    continue
                if S.SKIP_ALREADY_PLOTTED and _files.normal_plot_outputs_are_complete(row):
                    _files.record_existing_normal_plot_paths(row)
                    reused += 1
                    continue
                prepared = _loading.prepare_series(df, series)
                if prepared is None:
                    continue
                pmin, pmax = _periodograms.effective_period_range(float(prepared["baseline_days"]))
                if pmax <= pmin * 1.05:
                    continue
                result = _periodograms.run_lomb_scargle(prepared["time"], prepared["signal"], prepared["error"], pmin, pmax)
                bls = _periodograms.run_bls(prepared["time"], prepared["signal"], prepared["error"], prepared["signal_type"], float(prepared["baseline_days"]))
                source_info = source_info_lookup.get(str(metadata.get("source_id")), {})
                source_label = str(source_info.get("recommendation_label", row.get("recommendation_label", "nonvar")))
                row["recommendation_label"] = source_label
                row["source_warning_flags"] = str(source_info.get("warning_flags", row.get("source_warning_flags", "")))
                row["source_harmonic_status"] = str(source_info.get("harmonic_status", row.get("source_harmonic_status", "")))
                row["source_detection_label"] = str(source_info.get("detection_label", row.get("source_detection_label", "")))
                row["source_confidence_class"] = str(source_info.get("confidence_class", row.get("source_confidence_class", "")))
                try:
                    row["best_per_star_plot_path"] = plot_best_per_star(metadata, prepared, result, row, catalogue_period, bls, source_label)
                    made += 1
                except Exception as exc:
                    row["best_per_star_plot_path"] = ""
                    row["plot_error"] = repr(exc)
                del result, bls, prepared
                gc.collect()
        except Exception as exc:
            print(f"  [plot warning] {path.name}: {repr(exc)}")
        if file_index % max(S.CHECKPOINT_EVERY_N_FILES, 1) == 0:
            _files.safe_write_csv(summary_rows, S.OUTPUT_DIR / "tables" / "ls_period_search_summary.csv")
            print(
                f"  plot checkpoint: {file_index:,}/{len(files):,} files, "
                f"new plots made={made:,}, existing plots reused={reused:,}"
            )
    _files.safe_write_csv(summary_rows, S.OUTPUT_DIR / "tables" / "ls_period_search_summary.csv")
    print(
        f"Plotting complete: {made:,} new plots made, "
        f"{reused:,} existing plots reused"
    )


def choose_extra_fold_series_rows(
    source_rows: list[dict[str, Any]],
    source_info: dict[str, Any],
) -> list[dict[str, Any]]:
    """Select the period-supplying series, or all successful series on request."""
    by_series: dict[str, dict[str, Any]] = {}
    for row in source_rows:
        series = str(row.get("series", ""))
        if series in S.SERIES_TO_RUN and series in S.PLOT_SERIES and series not in by_series:
            by_series[series] = row
    if not by_series:
        return []

    mode = str(S.EXTRA_FOLD_SERIES_MODE).strip().lower()
    if mode == "all":
        return [by_series[s] for s in S.SERIES_TO_RUN if s in by_series]
    if mode != "recommended":
        raise ValueError("EXTRA_FOLD_SERIES_MODE must be 'recommended' or 'all'")

    period_source = str(source_info.get("recommended_period_source", "")).lower()
    if period_source.startswith("combined") and "combined" in by_series:
        return [by_series["combined"]]
    if period_source.startswith("o") and "o" in by_series:
        return [by_series["o"]]
    if period_source.startswith("c") and "c" in by_series:
        return [by_series["c"]]

    target_period = _loading.safe_float(
        source_info.get("photometric_period_days"),
        _loading.safe_float(
            source_info.get("recommended_period_days"),
            _loading.safe_float(source_info.get("consensus_period_days"), np.nan),
        ),
    )
    ranked: list[tuple[float, float, int, dict[str, Any]]] = []
    for priority, series in enumerate(S.SERIES_TO_RUN):
        row = by_series.get(series)
        if row is None:
            continue
        series_period = _classify.series_period_from_row(row)
        if np.isfinite(target_period) and target_period > 0 and np.isfinite(series_period):
            separation = abs(series_period - target_period) / target_period
        else:
            separation = np.inf
        source_score = _loading.safe_float(source_info.get(f"{series}_score"), -np.inf)
        ranked.append((separation, -source_score, priority, row))
    ranked.sort(key=lambda item: (item[0], item[1], item[2]))
    return [ranked[0][3]] if ranked else []


def extra_trigger_reason(automatic: bool, manual: bool, diagnostic: str) -> str:
    reasons: list[str] = []
    if automatic:
        reasons.append(f"automatic {diagnostic} suspect")
    if manual:
        reasons.append("manual file selection")
    return " + ".join(reasons)


def generate_extra_phase_fold_diagnostics(
    files: list[Path],
    summary_rows: list[dict[str, Any]],
    peak_rows_all: list[dict[str, Any]],
    recommendations: pd.DataFrame,
    alias_inventory: pd.DataFrame,
) -> pd.DataFrame:
    """Generate only requested extra folds from saved results and light curves.

    No LS search, alias replacement or harmonic recommendation is changed here.
    This stage also runs when SKIP_ALREADY_PROCESSED=True and normal plot
    regeneration is disabled with MAKE_PLOTS_AFTER_FINAL=False.
    """
    diagnostics_requested = bool(
        S.AUTO_PLOT_ALIAS_SUSPECTS
        or S.AUTO_PLOT_HARMONIC_SUSPECTS
        or S.ALIAS_SELECTED_FILES
        or S.HARMONIC_SELECTED_FILES
    )
    if not diagnostics_requested or S.PLOT_MODE.strip().lower() == "none":
        return pd.DataFrame()

    alias_tokens = _files.manual_target_tokens(S.ALIAS_SELECTED_FILES)
    harmonic_tokens = _files.manual_target_tokens(S.HARMONIC_SELECTED_FILES)
    source_info_lookup: dict[str, dict[str, Any]] = {}
    if recommendations is not None and not recommendations.empty:
        source_info_lookup = {
            str(row.get("source_id")): row.to_dict()
            for _, row in recommendations.iterrows()
        }

    rows_by_file: dict[str, list[dict[str, Any]]] = {}
    for row in summary_rows:
        if str(row.get("status")) != "ok":
            continue
        rows_by_file.setdefault(str(row.get("file", "")), []).append(row)

    peaks_by_key: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for peak in peak_rows_all:
        key = (
            str(peak.get("file", "")),
            str(peak.get("source_id", "")),
            str(peak.get("series", "")),
        )
        peaks_by_key.setdefault(key, []).append(peak)

    print("=" * 88)
    print("EXTRA PHASE-FOLD DIAGNOSTICS")
    print("=" * 88)
    manifest_rows: list[dict[str, Any]] = []
    files_opened = 0

    for path in files:
        source_rows = rows_by_file.get(path.name, [])
        if not source_rows:
            continue
        summary_metadata = source_rows[0]
        source_id = str(summary_metadata.get("source_id", ""))
        source_info = source_info_lookup.get(source_id, {})

        alias_manual = _files.manual_target_matches(path, summary_metadata, alias_tokens)
        harmonic_manual = _files.manual_target_matches(path, summary_metadata, harmonic_tokens)
        alias_auto = bool(S.AUTO_PLOT_ALIAS_SUSPECTS and any(
            _aliases.source_is_alias_suspect(series_row) for series_row in source_rows
        ))
        harmonic_auto = bool(S.AUTO_PLOT_HARMONIC_SUSPECTS and any(
            _aliases.source_is_harmonic_suspect(series_row) for series_row in source_rows
        ))
        if not (alias_manual or harmonic_manual or alias_auto or harmonic_auto):
            continue

        try:
            raw = pd.read_csv(path, dtype=str, low_memory=False)
            df = _loading.normalise_columns(raw)
            metadata = _loading.extract_metadata(df, path)
            files_opened += 1
            selected_rows = choose_extra_fold_series_rows(source_rows, source_info)
            if alias_auto or harmonic_auto:
                automatic_rows = [
                    series_row for series_row in source_rows
                    if (alias_auto and _aliases.source_is_alias_suspect(series_row))
                    or (harmonic_auto and _aliases.source_is_harmonic_suspect(series_row))
                ]
                selected_by_series = {
                    str(series_row.get("series", "")): series_row
                    for series_row in selected_rows + automatic_rows
                }
                selected_rows = list(selected_by_series.values())
            for series_row in selected_rows:
                series = str(series_row.get("series", ""))
                if series not in S.PLOT_SERIES or series not in S.SERIES_TO_RUN:
                    continue
                prepared = _loading.prepare_series(df, series)
                if prepared is None:
                    manifest_rows.append(
                        {
                            "file": path.name,
                            "source_id": source_id,
                            "object_name": summary_metadata.get("object_name", ""),
                            "series": series,
                            "diagnostic_type": "selected_series",
                            "trigger_reason": "selected series unavailable",
                            "output_path": "",
                            "status": "skipped",
                            "error": "prepare_series returned no usable data",
                        }
                    )
                    continue
                series_alias_auto = bool(alias_auto and _aliases.source_is_alias_suspect(series_row))
                series_harmonic_auto = bool(harmonic_auto and _aliases.source_is_harmonic_suspect(series_row))
                if alias_manual or series_alias_auto:
                    trigger = extra_trigger_reason(series_alias_auto, alias_manual, "alias")
                    key = (path.name, source_id, series)
                    try:
                        result = plot_alias_candidate_folds(
                            metadata,
                            prepared,
                            series_row,
                            peaks_by_key.get(key, []),
                            source_info,
                            trigger,
                            alias_inventory,
                        )
                        if result is None:
                            manifest_rows.append(
                                {
                                    "file": path.name,
                                    "source_id": source_id,
                                    "object_name": metadata.get("object_name", ""),
                                    "series": series,
                                    "diagnostic_type": "alias_candidates",
                                    "trigger_reason": trigger,
                                    "destination_folder": "alias",
                                    "output_path": "",
                                    "status": "skipped",
                                    "error": "no valid saved LS peak candidates",
                                }
                            )
                        else:
                            manifest_rows.append(result)
                            print(f"  [extra-fold made] alias: {result['output_path']}")
                    except Exception as exc:
                        manifest_rows.append(
                            {
                                "file": path.name,
                                "source_id": source_id,
                                "object_name": metadata.get("object_name", ""),
                                "series": series,
                                "diagnostic_type": "alias_candidates",
                                "trigger_reason": trigger,
                                "destination_folder": "alias",
                                "output_path": "",
                                "status": "failed",
                                "error": repr(exc),
                            }
                        )
                        print(f"  [extra-fold warning] alias / {path.name} / {series}: {repr(exc)}")
                if harmonic_manual or series_harmonic_auto:
                    trigger = extra_trigger_reason(series_harmonic_auto, harmonic_manual, "harmonic")
                    try:
                        result = plot_harmonic_candidate_folds(
                            metadata,
                            prepared,
                            series_row,
                            source_info,
                            trigger,
                        )
                        if result is None:
                            manifest_rows.append(
                                {
                                    "file": path.name,
                                    "source_id": source_id,
                                    "object_name": metadata.get("object_name", ""),
                                    "series": series,
                                    "diagnostic_type": "harmonic_tests",
                                    "trigger_reason": trigger,
                                    "destination_folder": "harmonic",
                                    "output_path": "",
                                    "status": "skipped",
                                    "error": "no valid recommended period or harmonic factors",
                                }
                            )
                        else:
                            manifest_rows.append(result)
                            print(f"  [extra-fold made] harmonic: {result['output_path']}")
                    except Exception as exc:
                        manifest_rows.append(
                            {
                                "file": path.name,
                                "source_id": source_id,
                                "object_name": metadata.get("object_name", ""),
                                "series": series,
                                "diagnostic_type": "harmonic_tests",
                                "trigger_reason": trigger,
                                "destination_folder": "harmonic",
                                "output_path": "",
                                "status": "failed",
                                "error": repr(exc),
                            }
                        )
                        print(f"  [extra-fold warning] harmonic / {path.name} / {series}: {repr(exc)}")
                del prepared
                gc.collect()
        except Exception as exc:
            manifest_rows.append(
                {
                    "file": path.name,
                    "source_id": source_id,
                    "object_name": summary_metadata.get("object_name", ""),
                    "series": "",
                    "diagnostic_type": "extra_phase_folds",
                    "trigger_reason": extra_trigger_reason(
                        alias_auto or harmonic_auto,
                        alias_manual or harmonic_manual,
                        "selected",
                    ),
                    "output_path": "",
                    "status": "failed",
                    "error": repr(exc),
                }
            )
            print(f"  [extra-fold warning] {path.name}: {repr(exc)}")

    manifest = pd.DataFrame(manifest_rows)
    manifest_path = S.OUTPUT_DIR / "tables" / "extra_phase_fold_diagnostics.csv"
    _files.safe_write_csv(manifest, manifest_path)
    if not manifest.empty and "status" in manifest.columns:
        made_rows = manifest.loc[manifest["status"].astype(str).eq("made")]
        figures_made = int(len(made_rows))
        by_type = made_rows.get("diagnostic_type", pd.Series(dtype=str)).astype(str).value_counts().to_dict()
    else:
        figures_made = 0
        by_type = {}
    print(
        f"Extra folds complete: opened {files_opened:,} selected files; "
        f"verified {figures_made:,} figures "
        f"(alias={by_type.get('alias_candidates', 0):,}, harmonic={by_type.get('harmonic_tests', 0):,})"
    )
    print(f"Extra-fold manifest: {manifest_path}")
    return manifest
