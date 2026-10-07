from __future__ import annotations
import re
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from . import settings as S
from . import cuts as _cuts




# ============================================================================
# PLOTTING HELPERS
# ============================================================================


def save_figure(fig: plt.Figure, basename: str) -> None:
    """Save a figure to PLOT_DIR using the selected file formats."""
    S.PLOT_DIR.mkdir(parents=True, exist_ok=True)
    if S.SAVE_PNG:
        fig.savefig(
            S.PLOT_DIR / f"{basename}.png",
            dpi=S.PLOT_DPI,
            bbox_inches="tight",
        )
    if S.SAVE_PDF:
        fig.savefig(S.PLOT_DIR / f"{basename}.pdf", bbox_inches="tight")
    plt.close(fig)


def make_summary_figure(summary_df: pd.DataFrame) -> None:
    """Create one compact six-panel overview of the cleaning run."""
    ok = summary_df.loc[summary_df["status"].eq("ok")].copy()
    if ok.empty:
        print("No successfully cleaned files available for summary plots.")
        return

    numeric_columns = [
        "n_raw",
        "n_final_keep",
        "fraction_kept",
        "baseline_days_clean",
        "n_c_clean",
        "n_o_clean",
        "ra_deg",
        "dec_deg",
    ]
    for column in numeric_columns:
        if column in ok.columns:
            ok[column] = pd.to_numeric(ok[column], errors="coerce")

    ok["fraction_removed"] = 1.0 - ok["fraction_kept"]

    fig, axes = plt.subplots(2, 3, figsize=(14, 8), constrained_layout=True)

    # 1. Raw and retained point-count distributions.
    ax = axes[0, 0]
    ax.hist(ok["n_raw"].dropna(), bins=40, alpha=0.65, label="Raw")
    ax.hist(ok["n_final_keep"].dropna(), bins=40, alpha=0.65, label="Cleaned")
    ax.set_xlabel("Points per star")
    ax.set_ylabel("Stars")
    ax.set_title("Raw and cleaned point counts")
    ax.legend(frameon=False)

    # 2. Fraction removed.
    ax = axes[0, 1]
    values = ok["fraction_removed"].replace([np.inf, -np.inf], np.nan).dropna()
    ax.hist(values, bins=40)
    if len(values):
        median_value = float(values.median())
        ax.axvline(
            median_value,
            linestyle="--",
            label=f"Median = {median_value:.3f}",
        )
        ax.legend(frameon=False)
    ax.set_xlabel("Fraction of points removed")
    ax.set_ylabel("Stars")
    ax.set_title("Cleaning strength per star")

    # 3. Retained baseline.
    ax = axes[0, 2]
    ax.hist(ok["baseline_days_clean"].dropna(), bins=40)
    ax.set_xlabel("Cleaned baseline (days)")
    ax.set_ylabel("Stars")
    ax.set_title("Time baseline after cleaning")

    # 4. Retained versus raw points.
    ax = axes[1, 0]
    ax.scatter(ok["n_raw"], ok["n_final_keep"], s=12, alpha=0.65)
    maximum = np.nanmax(
        np.concatenate(
            [
                ok["n_raw"].to_numpy(dtype=float),
                ok["n_final_keep"].to_numpy(dtype=float),
            ]
        )
    )
    if np.isfinite(maximum):
        ax.plot([0, maximum], [0, maximum], linestyle="--", linewidth=1)
    ax.set_xlabel("Raw points")
    ax.set_ylabel("Retained points")
    ax.set_title("Retained versus raw")

    # 5. Remaining c/o filter coverage.
    ax = axes[1, 1]
    ax.scatter(ok["n_c_clean"], ok["n_o_clean"], s=12, alpha=0.65)
    filter_maximum = np.nanmax(
        np.concatenate(
            [
                ok["n_c_clean"].to_numpy(dtype=float),
                ok["n_o_clean"].to_numpy(dtype=float),
            ]
        )
    )
    if np.isfinite(filter_maximum):
        ax.plot(
            [0, filter_maximum],
            [0, filter_maximum],
            linestyle="--",
            linewidth=1,
        )
    ax.set_xlabel("Clean c-band points")
    ax.set_ylabel("Clean o-band points")
    ax.set_title("Filter coverage after cleaning")

    # 6. Sky map when coordinates exist; otherwise baseline versus point count.
    ax = axes[1, 2]
    coordinate_mask = np.isfinite(ok["ra_deg"]) & np.isfinite(ok["dec_deg"])
    if coordinate_mask.sum() >= 3:
        scatter = ax.scatter(
            ok.loc[coordinate_mask, "ra_deg"],
            ok.loc[coordinate_mask, "dec_deg"],
            c=ok.loc[coordinate_mask, "fraction_removed"],
            s=16,
        )
        colorbar = fig.colorbar(scatter, ax=ax)
        colorbar.set_label("Fraction removed")
        ax.set_xlabel("RA (deg)")
        ax.set_ylabel("Dec (deg)")
        ax.set_title("Spatial cleaning check")
    else:
        scatter = ax.scatter(
            ok["baseline_days_clean"],
            ok["n_final_keep"],
            c=ok["fraction_removed"],
            s=16,
        )
        colorbar = fig.colorbar(scatter, ax=ax)
        colorbar.set_label("Fraction removed")
        ax.set_xlabel("Cleaned baseline (days)")
        ax.set_ylabel("Retained points")
        ax.set_title("Coverage after cleaning")

    fig.suptitle(
        f"ATLAS light-curve cleaning summary ({len(ok):,} stars)",
        fontsize=14,
    )
    save_figure(fig, "cleaning_summary_6panel")


def make_reason_figure(reason_df: pd.DataFrame) -> None:
    """Plot the most common point-rejection reasons."""
    if reason_df.empty:
        print("No rejection reasons available for the reason plot.")
        return

    top = reason_df.head(max(1, S.TOP_N_REASONS)).iloc[::-1]

    fig, ax = plt.subplots(figsize=(10, 6), constrained_layout=True)
    ax.barh(top["reject_reason"], top["n_points"])
    ax.set_xlabel("Rejected points")
    ax.set_ylabel("Reason")
    ax.set_title(f"Top {len(top)} ATLAS cleaning rejection reasons")
    save_figure(fig, "cleaning_rejection_reasons")


def _plot_values(frame: pd.DataFrame) -> tuple[str, str, bool]:
    """Choose magnitude where possible; otherwise use flux."""
    if "m" in frame.columns:
        values = pd.to_numeric(frame["m"], errors="coerce")
        if np.isfinite(values).any():
            return "m", "Magnitude", True
    return "uJy", "Flux (microJy)", False


def make_example_before_after_plot(
    input_file: Path,
    row: pd.Series,
) -> None:
    """Show raw and cleaned measurements for one selected star."""
    try:
        raw = pd.read_csv(input_file, dtype=str)
        all_rows, _ = _cuts.clean_atlas_df(raw)
    except Exception as error:
        print(f"Could not make example plot for {input_file.name}: {error}")
        return

    value_column, y_label, invert_axis = _plot_values(all_rows)
    time = pd.to_numeric(all_rows["MJD"], errors="coerce")
    values = pd.to_numeric(all_rows[value_column], errors="coerce")
    keep = all_rows["final_keep"].astype(bool).to_numpy()

    fig, axes = plt.subplots(2, 1, figsize=(11, 7), sharex=True, constrained_layout=True)

    # Raw measurements, separated by filter.
    for filter_name in sorted(all_rows["F"].dropna().astype(str).unique()):
        mask = all_rows["F"].astype(str).eq(filter_name).to_numpy()
        axes[0].scatter(
            time[mask],
            values[mask],
            s=8,
            alpha=0.6,
            label=f"{filter_name}-band",
        )
    axes[0].set_ylabel(y_label)
    axes[0].set_title("Before cleaning: all input measurements")
    axes[0].legend(frameon=False, ncol=2)

    # Accepted and rejected measurements.
    axes[1].scatter(
        time[keep],
        values[keep],
        s=8,
        alpha=0.65,
        label="Retained",
    )
    axes[1].scatter(
        time[~keep],
        values[~keep],
        s=14,
        marker="x",
        alpha=0.75,
        label="Rejected",
    )
    axes[1].set_xlabel("MJD")
    axes[1].set_ylabel(y_label)
    axes[1].set_title("After cleaning: retained and rejected measurements")
    axes[1].legend(frameon=False)

    if invert_axis:
        axes[0].invert_yaxis()
        axes[1].invert_yaxis()

    object_name = str(row.get("object_name", input_file.stem))
    removed_fraction = 1.0 - float(row.get("fraction_kept", np.nan))
    fig.suptitle(
        f"{object_name}: cleaning example "
        f"(removed fraction = {removed_fraction:.3f})",
        fontsize=13,
    )

    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", object_name).strip("_")
    save_figure(fig, f"example_{safe_name}_before_after")


def make_example_plots(summary_df: pd.DataFrame) -> None:
    """Select a small number of stars and make before/after plots."""
    ok = summary_df.loc[summary_df["status"].eq("ok")].copy()
    if ok.empty or S.N_EXAMPLE_PLOTS <= 0:
        return

    ok["fraction_kept"] = pd.to_numeric(ok["fraction_kept"], errors="coerce")
    ok["fraction_removed"] = 1.0 - ok["fraction_kept"]

    if S.EXAMPLE_SELECTION == "highest_removed_fraction":
        selected = ok.sort_values("fraction_removed", ascending=False)
    elif S.EXAMPLE_SELECTION == "lowest_removed_fraction":
        selected = ok.sort_values("fraction_removed", ascending=True)
    elif S.EXAMPLE_SELECTION == "first":
        selected = ok
    else:
        raise ValueError(
            "EXAMPLE_SELECTION must be 'highest_removed_fraction', "
            "'lowest_removed_fraction', or 'first'."
        )

    selected = selected.head(S.N_EXAMPLE_PLOTS)
    for _, row in selected.iterrows():
        input_file = S.INPUT_DIR / str(row["file"])
        if input_file.exists():
            make_example_before_after_plot(input_file, row)
