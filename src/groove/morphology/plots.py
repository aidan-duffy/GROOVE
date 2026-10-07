from __future__ import annotations
import argparse
import logging
import math
import shutil
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
import joblib
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np
import pandas as pd
from . import settings as S
from . import classify as _classify
from . import embedding as _embedding
from . import features as _features
from . import loading as _loading
from . import outputs as _outputs
from . import persistence as _persistence
from . import utils as _utils




def build_neighbour_review_pages(validation: pd.DataFrame, table: pd.DataFrame,
                                 fold_paths: Mapping[str, Path], version_dir: Path,
                                 logger: logging.Logger) -> None:
    if validation.empty:
        return
    maps = _persistence.figure_directory(version_dir) / "maps"
    lookup = table.set_index("source_key", drop=False)
    pages = 0
    for anchor_id, block in validation.groupby("anchor_source_id", sort=False):
        first = block.iloc[0]
        keys = [str(first["anchor_source_key"])] + block["neighbour_source_key"].astype(str).tolist()
        cols = 3
        rows = int(math.ceil(len(keys) / cols))
        fig, axes = plt.subplots(rows, cols, figsize=(15, 4.2 * rows), squeeze=False)
        for rank, (ax, key) in enumerate(zip(axes.ravel(), keys)):
            path = fold_paths.get(key)
            row = lookup.loc[key] if key in lookup.index else None
            if path is not None and Path(path).exists():
                ax.imshow(plt.imread(str(path)))
            else:
                ax.text(0.5, 0.5, "fold plot unavailable", ha="center", va="center",
                        transform=ax.transAxes)
            if row is not None:
                if rank == 0:
                    subtitle = "ANCHOR | %s | %s\n%s" % (
                        row.get("source_id", ""), row.get("final_primary_tag", ""),
                        row.get("interest_status", ""))
                else:
                    detail = block.iloc[rank - 1]
                    subtitle = ("NN %d | %s | %s\nfeature d=%.3g; UMAP d=%.3g; %s" % (
                        rank, row.get("source_id", ""), row.get("final_primary_tag", ""),
                        _utils.finite_float(detail.get("original_feature_distance"), np.nan),
                        _utils.finite_float(detail.get("umap_distance"), np.nan),
                        row.get("interest_status", "")))
                ax.set_title(subtitle, fontsize=8)
            ax.axis("off")
        for ax in axes.ravel()[len(keys):]:
            ax.axis("off")
        fig.suptitle("Nearest-neighbour morphology validation: %s" % anchor_id, fontsize=13)
        fig.tight_layout(rect=(0, 0, 1, 0.96))
        fig.savefig(maps / ("neighbour_validation_%s.png" % _utils.safe_name(anchor_id)), dpi=140)
        plt.close(fig)
        pages += 1
    logger.info("Nearest-neighbour morphology review pages written for %d anchors", pages)


def _fold_scatter(ax, frame: pd.DataFrame, period: float, origin: float,
                  n_sections: int = 4) -> None:
    """Show every accepted band, centring their magnitudes when both are present."""
    if not np.isfinite(period) or period <= 0 or frame.empty:
        ax.text(0.5, 0.5, "no usable photometry or recommended period",
                ha="center", va="center", transform=ax.transAxes)
        return
    times = frame["time"].to_numpy(dtype=float)
    sections = _features.chronological_sections(times, n_sections)
    bands = frame["filter"].astype(str).str.lower().to_numpy()
    multiple = len(set(bands)) > 1
    for band in sorted(set(bands)):
        selected = bands == band
        mags = frame.loc[selected, "mag"].to_numpy(dtype=float)
        if multiple:
            mags = mags - np.nanmedian(mags)
        phase = np.mod((times[selected] - origin) / period, 1.0)
        local_sections = sections[selected]
        for section in range(n_sections):
            mask = local_sections == section
            if not mask.any():
                continue
            ax.plot(np.r_[phase[mask], phase[mask] + 1.0], np.r_[mags[mask], mags[mask]],
                    marker="o" if band == "c" else "s", markersize=2.0,
                    linestyle="none", alpha=0.55,
                    color=S.SECTION_COLOURS[section % len(S.SECTION_COLOURS)],
                    rasterized=True, label="%s Q%d" % (band.upper(), section + 1))
        n_bins = 80
        bins = np.minimum((phase * n_bins).astype(int), n_bins - 1)
        centres = (np.arange(n_bins, dtype=float) + 0.5) / n_bins
        medians = np.full(n_bins, np.nan)
        for index in range(n_bins):
            values = mags[bins == index]
            if len(values) >= 2:
                medians[index] = np.median(values)
        if np.isfinite(medians).sum() >= 4:
            ax.plot(np.r_[centres, centres + 1.0], np.r_[medians, medians],
                    color="teal" if band == "c" else "black", linewidth=1.0,
                    alpha=0.8, label="%s bin median" % band.upper(), zorder=10)
    ax.invert_yaxis()
    ax.set_xlim(0, 2)
    ax.set_xlabel("Phase")
    ax.set_ylabel("Magnitude relative to band median" if multiple else "Magnitude")


def create_fold_plot(record: Mapping[str, Any], row: Mapping[str, Any], output: Path,
                     dpi: int = 110) -> None:
    """Accepted-band double-phase fold at the saved recommended period."""
    fig, ax = plt.subplots(figsize=(5.2, 3.6))
    period = _utils.finite_float(row.get("recommended_period_days"))
    _fold_scatter(ax, record["data"], period, record["origin"])
    ax.set_title("%s\n%s | recommended P=%.5g d | conf=%.2f" % (
        row.get("source_id", ""), row.get("final_primary_tag", ""),
        period, _utils.finite_float(row.get("final_confidence"), 0.0)), fontsize=8)
    ax.legend(fontsize=6, markerscale=3, loc="best", framealpha=0.7)
    fig.subplots_adjust(left=0.13, right=0.97, top=0.84, bottom=0.15)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=dpi)
    plt.close(fig)


def create_review_plot(record: Mapping[str, Any], row: Mapping[str, Any], output: Path,
                       config: Mapping[str, Any]) -> None:
    """Backward-compatible name for the phase-only morphology image.

    Morphology output products never embed a Lomb--Scargle periodogram.  The
    independent period-search pipeline remains the place to inspect LS/BLS
    evidence in detail.
    """
    create_fold_plot(record, row, output,
                     dpi=int(config.get("review_plot_dpi", 110)))


def build_family_maps(records: Sequence[Mapping[str, Any]], table: pd.DataFrame,
                      version_dir: Path, config: Mapping[str, Any],
                      logger: logging.Logger,
                      fold_paths: Optional[Mapping[str, Path]] = None) -> pd.DataFrame:
    """Typical, strongest, and ambiguous examples plus category maps."""
    from sklearn.metrics import pairwise_distances

    colours = dict(S.CATEGORY_COLOURS)
    colours.update(config.get("category_colours", {}) or {})
    if "final_primary_tag" not in table.columns:
        return pd.DataFrame()
    work = table.copy()
    work["_strength"] = [_classify.strength_score(row) for _, row in work.iterrows()]
    feature_space, _ = _embedding.validation_feature_space(work)

    present = [c for c in S.PRIMARY_CATEGORIES
               if (work["final_primary_tag"] == c).any()]
    maps = _persistence.figure_directory(version_dir) / "maps"
    maps.mkdir(parents=True, exist_ok=True)

    typical_example_rows: Dict[str, int] = {}
    representative_dir = maps / "representative_families"
    if representative_dir.exists():
        shutil.rmtree(representative_dir)
    representative_dir.mkdir(parents=True, exist_ok=True)
    strongest_categories = (
        "transit", "wavelike", "flaring", "irregular_variable", "nonvar", "noisy")
    strongest_fig, strongest_axes = plt.subplots(2, 3, figsize=(15, 8.8), squeeze=False)
    strongest_lookup = {category: strongest_axes.ravel()[index]
                        for index, category in enumerate(strongest_categories)}
    representative_fig, representative_axes = plt.subplots(
        2, 3, figsize=(15, 8.8), squeeze=False)
    representative_lookup = {category: representative_axes.ravel()[index]
                             for index, category in enumerate(strongest_categories)}
    for category in present:
        indices = np.flatnonzero(work["final_primary_tag"].to_numpy() == category)
        candidate_indices = []
        for index in indices:
            row = work.iloc[index]
            tags = set(_utils.split_tags(row.get("final_secondary_tags", "")))
            eligible = _utils.finite_float(row.get("final_confidence"), 0.0) >= 0.60
            eligible &= not bool(tags & {
                "alias_period", "alias_possible", "harmonic_possible",
                "poor_point_driven", "single_section_dimming",
                "seasonal_phase_coupling", "gappy_phase_coverage",
                "single_point_bright_excursions"})
            eligible &= str(row.get("interest_status", "")) not in {
                "exotic_candidate", "manually_confirmed_exotic"}
            if category == "flaring":
                eligible &= _utils.bool_value(row.get("flare_primary_validation_pass", False))
            if eligible:
                candidate_indices.append(int(index))
        central_pool = np.asarray(candidate_indices or indices.tolist(), dtype=int)
        block_space = feature_space[central_pool]
        if len(central_pool) == 1:
            typical_local = 0
        elif bool(config.get("_phase_fold_products_only", False)):
            centre = np.nanmedian(block_space, axis=0, keepdims=True)
            typical_local = int(np.argmin(pairwise_distances(
                block_space, centre, metric="cosine").ravel()))
        else:
            totals = np.zeros(len(central_pool), dtype=float)
            for start in range(0, len(central_pool), 128):
                stop = min(start + 128, len(central_pool))
                totals[start:stop] = pairwise_distances(
                    block_space[start:stop], block_space, metric="cosine").sum(axis=1)
            typical_local = int(np.argmin(totals))
        typical_example = int(central_pool[typical_local])
        strongest = int(indices[int(np.argmax(work.iloc[indices]["_strength"].to_numpy()))])
        score_matrix = work.iloc[indices][list(S.CATEGORY_SCORE_COLUMNS)].to_numpy(dtype=float)
        sorted_scores = np.sort(np.nan_to_num(score_matrix, nan=0.0), axis=1)
        margins = sorted_scores[:, -1] - sorted_scores[:, -2]
        boundary = int(indices[int(np.argmin(margins))])
        selected = list(dict.fromkeys([typical_example, strongest, boundary]))
        while len(selected) < 3:
            selected.append(selected[-1])
        typical_example_rows[category] = typical_example
        fig, axes = plt.subplots(1, 3, figsize=(15, 4.2), squeeze=False)
        roles = ("representative example", "strongest example", "ambiguous example")
        for ax, row_index, role in zip(axes.ravel(), selected, roles):
            row = work.iloc[row_index]
            path = fold_paths.get(str(row["source_key"])) if fold_paths else None
            if path is not None and Path(path).exists():
                ax.imshow(plt.imread(str(path)))
            else:
                ax.text(0.5, 0.5, "fold plot unavailable", ha="center", va="center",
                        transform=ax.transAxes)
            ax.set_title("%s - %s" % (
                category.replace("_", " ").title(), role), fontsize=9)
            ax.axis("off")
        fig.suptitle("Representative %s examples (N=%d)" % (category, len(indices)), fontsize=13)
        fig.tight_layout(rect=(0, 0, 1, 0.93))
        fig.savefig(representative_dir /
                    ("%s_representative_examples.png" % _utils.safe_name(category)), dpi=150)
        plt.close(fig)

        if category in strongest_lookup:
            ax = strongest_lookup[category]
            row = work.iloc[strongest]
            path = fold_paths.get(str(row["source_key"])) if fold_paths else None
            if path is not None and Path(path).exists():
                ax.imshow(plt.imread(str(path)))
            else:
                ax.text(0.5, 0.5, "fold plot unavailable", ha="center", va="center",
                        transform=ax.transAxes)
            ax.set_title("%s (N=%d)\nstrongest validated evidence" % (
                category.replace("_", " ").title(), len(indices)), fontsize=9)
            ax.axis("off")
        if category in representative_lookup:
            ax = representative_lookup[category]
            row = work.iloc[typical_example]
            path = fold_paths.get(str(row["source_key"])) if fold_paths else None
            if path is not None and Path(path).exists():
                ax.imshow(plt.imread(str(path)))
            else:
                ax.text(0.5, 0.5, "fold plot unavailable", ha="center", va="center",
                        transform=ax.transAxes)
            ax.set_title("%s (N=%d)\ncentral high-confidence real source" % (
                category.replace("_", " ").title(), len(indices)), fontsize=9)
            ax.axis("off")
    for category, ax in strongest_lookup.items():
        if category not in present:
            ax.text(0.5, 0.5, "%s\nno sources" % category, ha="center", va="center",
                    transform=ax.transAxes)
            ax.axis("off")
    for category, ax in representative_lookup.items():
        if category not in present:
            ax.text(0.5, 0.5, "%s\nno sources" % category, ha="center", va="center",
                    transform=ax.transAxes)
            ax.axis("off")
    representative_fig.suptitle(
        "Representative high-confidence source in each morphology family "
        "(unknown excluded)", fontsize=13)
    representative_fig.tight_layout(rect=(0, 0, 1, 0.95))
    representative_fig.savefig(maps / "representative_family_examples.png", dpi=150)
    plt.close(representative_fig)
    strongest_fig.suptitle(
        "Strongest example in each classified morphology family (unknown excluded)", fontsize=13)
    strongest_fig.tight_layout(rect=(0, 0, 1, 0.95))
    strongest_fig.savefig(maps / "strongest_family_examples.png", dpi=150)
    plt.close(strongest_fig)
    misleading_old_name = maps / "family_centroids.png"
    if misleading_old_name.exists():
        misleading_old_name.unlink()

    exotic = work.loc[work["interest_status"].eq("exotic_candidate")].sort_values(
        "exotic_candidate_score", ascending=False).head(9)
    if not exotic.empty:
        fig, axes = plt.subplots(3, 3, figsize=(13.5, 12), squeeze=False)
        for ax, (_, row) in zip(axes.ravel(), exotic.iterrows()):
            path = fold_paths.get(str(row["source_key"])) if fold_paths else None
            if path is not None and Path(path).exists():
                ax.imshow(plt.imread(str(path)))
            else:
                ax.text(0.5, 0.5, "fold plot unavailable", ha="center", va="center",
                        transform=ax.transAxes)
            ax.set_title("%s | %s | %.2f\n%s" % (
                row.get("source_id", ""), row.get("final_primary_tag", ""),
                _utils.finite_float(row.get("exotic_candidate_score"), 0.0),
                row.get("interest_reasons", "")), fontsize=8)
            ax.axis("off")
        for ax in axes.ravel()[len(exotic):]:
            ax.axis("off")
        fig.suptitle("Exotic candidates ranked by validated-interest evidence", fontsize=13)
        fig.tight_layout(rect=(0, 0, 1, 0.96))
        fig.savefig(maps / "exotic_candidate_examples.png", dpi=150)
        plt.close(fig)

    logger.info("Representative-family plots written for %d categories", len(present))
    return pd.DataFrame({"source_key": work["source_key"].astype(str),
                         "family": work["final_primary_tag"].astype(str)})


DATASET_MARKERS = {
    "circle": "o", "square": "s", "diamond": "D", "triangle-up": "^",
    "triangle-down": "v", "cross": "P", "x": "X", "star": "*", "hexagon": "h",
}


def validate_dataset_markers(value):
    markers = {} if value is None else value
    if not isinstance(markers, Mapping) or any(
            not isinstance(name, str) or not isinstance(symbol, str) or symbol not in DATASET_MARKERS
            for name, symbol in markers.items()):
        raise ValueError("dataset_markers must map dataset names to: " + ", ".join(DATASET_MARKERS))
    return dict(markers)


def draw_overview_maps(table, version_dir, config, colours, outline_new):
    markers = validate_dataset_markers(config.get("dataset_markers", {}))
    selected = S.selected_maps(config) if bool(config.get("make_maps", True)) else []
    map_dir = _persistence.figure_directory(version_dir) / "maps"
    for name, (prefix, title, basename) in S.MAP_DEFINITIONS.items():
        if name in selected:
            make_static_map(table, prefix + "_1", prefix + "_2", title,
                            basename, version_dir, colours, outline_new,
                            dataset_markers=markers)
        else:
            for suffix in (".png", ".pdf", "_interactive.html"):
                (map_dir / (basename + suffix)).unlink(missing_ok=True)


def map_only(config, args):
    """Redraw saved overview coordinates without recomputing scientific state."""
    validate_dataset_markers(config.get("dataset_markers", {}))
    S.selected_maps(config)
    _, state = _persistence.resolve_version_dir(
        Path(config["output_root"]), config.get("model_version"))
    catalogue = state / "tables/all_sources.csv"
    if not catalogue.is_file():
        raise SystemExit("Saved catalogue not found: " + str(catalogue))
    table = _loading.read_table(catalogue)
    if "dataset" in table:
        print("Saved dataset names/counts: " + str(table["dataset"].value_counts().to_dict()))
    colours = dict(S.CATEGORY_COLOURS)
    colours.update(config.get("category_colours", {}) or {})
    outline = bool(config.get("outline_new_sources", False))
    if args.outline_new:
        outline = True
    if args.no_outline_new:
        outline = False
    draw_overview_maps(table, state, config, colours, outline)
    print("Redrawn saved overview maps: " + str(_persistence.figure_directory(state) / "maps"))
    return {"version_dir": str(state), "n_sources": len(table)}


def make_static_map(table: pd.DataFrame, x_col: str, y_col: str, title: str,
                    base_name: str, version_dir: Path, colours: Mapping[str, str],
                    outline_new: bool,
                    highlights: Optional[Mapping[str, str]] = None,
                    dataset_markers: Optional[Mapping[str, str]] = None) -> None:
    if x_col not in table.columns or y_col not in table.columns:
        return
    plot_table = table.loc[np.isfinite(table[x_col]) & np.isfinite(table[y_col])]
    if plot_table.empty:
        return
    markers = validate_dataset_markers(dataset_markers)
    fig, ax = plt.subplots(figsize=(11, 9))
    counts = plot_table["final_primary_tag"].value_counts().to_dict()
    handles = []
    # Dense populations are drawn first; rare categories remain visible above
    # them without altering, balancing, or supervising the embedding.
    plot_order = sorted(
        [category for category in S.PRIMARY_CATEGORIES if counts.get(category, 0)],
        key=lambda category: counts.get(category, 0), reverse=True)
    total = max(1, len(plot_table))
    for zorder, category in enumerate(plot_order, start=2):
        block = plot_table.loc[plot_table["final_primary_tag"].eq(category)]
        if block.empty:
            continue
        latest = _utils.bool_series(block["is_latest_batch"]) if "is_latest_batch" in block else\
            pd.Series(False, index=block.index)
        colour = colours.get(category, "#333333")
        count = int(len(block))
        marker_size = 22 if count > 1000 else (30 if count > 300 else 48)
        marker_alpha = 0.42 if count > 1000 else (0.62 if count > 300 else 0.88)
        # Two draws with SCALAR edge colours. matplotlib's scatter ignores an
        # ARRAY of edgecolors when `c` is a single colour, so a per-point edge
        # array silently does nothing; and `color=` would override edgecolors
        # entirely. Both were verified against rendered output.
        for mask, edgecolour, width in ((~latest, "none", 0.0), (latest, "black", 0.9)):
            part = block.loc[mask.to_numpy()]
            if part.empty:
                continue
            use_edge = edgecolour if outline_new else "none"
            groups = part.groupby("dataset", sort=True, dropna=False) if markers and "dataset" in part else [("", part)]
            for dataset, group in groups:
                ax.scatter(group[x_col], group[y_col], s=marker_size,
                           marker=DATASET_MARKERS[markers.get(str(dataset), "circle")],
                           alpha=marker_alpha, c=colour, edgecolors=use_edge,
                           linewidths=1.8 if (outline_new and use_edge != "none") else 0.0,
                           zorder=zorder + (20 if outline_new and use_edge != "none" else 0))
    for category in S.PRIMARY_CATEGORIES:
        if not counts.get(category, 0):
            continue
        handles.append(Line2D([0], [0], marker="o", linestyle="none",
                              color=colours.get(category, "#333333"),
                              label="%s (N=%d; %.1f%%)" % (
                                  category.replace("_", " ").title(),
                                  int(counts.get(category, 0)),
                                  100.0 * float(counts.get(category, 0)) / total)))
    if markers and "dataset" in plot_table:
        for dataset, count in plot_table["dataset"].astype(str).value_counts().sort_index().items():
            handles.append(Line2D([0], [0], linestyle="none",
                marker=DATASET_MARKERS[markers.get(dataset, "circle")],
                markerfacecolor="white", markeredgecolor="black", color="black",
                label="Dataset: %s (N=%d)" % (dataset, count)))
    if outline_new and "is_latest_batch" in plot_table and _utils.bool_series(plot_table["is_latest_batch"]).any():
        handles.append(Line2D([0], [0], linestyle="none", marker="o",
            markerfacecolor="white", markeredgecolor="black", markeredgewidth=1.8,
            label="Black outline: latest batch"))
    # Optional additive annotation.  The source's already-saved coordinates are
    # used verbatim: this does not call UMAP.transform or change the embedding.
    for source_id, label in (highlights or {}).items():
        source = plot_table.loc[
            plot_table["source_id"].astype(str).map(_utils.clean_source_id).eq(
                _utils.clean_source_id(source_id))]
        if source.empty:
            continue
        row = source.iloc[0]
        ax.scatter([row[x_col]], [row[y_col]], marker="*", s=330,
                   c="#FFD54F", edgecolors="black", linewidths=1.4,
                   zorder=100)
        ax.annotate(str(label), (float(row[x_col]), float(row[y_col])),
                    xytext=(8, 8), textcoords="offset points", fontsize=10,
                    fontweight="bold", color="black", zorder=101,
                    bbox={"boxstyle": "round,pad=0.2", "facecolor": "white",
                          "edgecolor": "#555555", "alpha": 0.86})
        handles.append(Line2D([0], [0], marker="*", linestyle="none",
                              markerfacecolor="#FFD54F", markeredgecolor="black",
                              markersize=12, label=str(label)))
    ax.set_xlabel("UMAP 1")
    ax.set_ylabel("UMAP 2")
    ax.set_title(title)
    ax.grid(alpha=0.25)
    if handles:
        ax.legend(handles=handles, loc="best", fontsize=9)
    fig.tight_layout()
    maps = _persistence.figure_directory(version_dir) / "maps"
    maps.mkdir(parents=True, exist_ok=True)
    fig.savefig(maps / (base_name + ".png"), dpi=170)
    fig.savefig(maps / (base_name + ".pdf"))
    plt.close(fig)
    make_interactive_map(plot_table, x_col, y_col, title, base_name,
                         version_dir, colours, outline_new, highlights, markers)


def make_interactive_map(table: pd.DataFrame, x_col: str, y_col: str, title: str,
                         base_name: str, version_dir: Path, colours: Mapping[str, str],
                         outline_new: bool,
                         highlights: Optional[Mapping[str, str]] = None,
                    dataset_markers: Optional[Mapping[str, str]] = None) -> None:
    """Self-contained Plotly map with source details and linked phase images."""
    import os
    import html
    from urllib.parse import quote
    import plotly.graph_objects as go
    maps = _persistence.figure_directory(version_dir) / 'maps'
    maps.mkdir(parents=True, exist_ok=True)
    markers = validate_dataset_markers(dataset_markers)
    chart = go.Figure()
    total = len(table)
    for category in S.PRIMARY_CATEGORIES:
        block = table.loc[table.final_primary_tag.eq(category)]
        if block.empty:
            continue
        groups = block.groupby("dataset", sort=True, dropna=False) if markers and "dataset" in block else [("", block)]
        for dataset, subset in groups:
            dataset = str(dataset)
            details = []
            for _, row in subset.iterrows():
                source_id = _utils.clean_source_id(row.get('source_id', ''))
                picture = _source_phase_plot_path(version_dir, source_id)
                link = quote(os.path.relpath(picture, maps).replace(os.sep, '/'), safe='/') if picture else ''
                details.append([html.escape(source_id), html.escape(str(row.get('dataset', ''))),
                                html.escape(str(row.get('final_primary_tag', ''))),
                                _utils.finite_float(row.get('recommended_period_days'), np.nan),
                                html.escape(str(row.get('final_secondary_tags', ''))), link])
            latest = _utils.bool_series(subset['is_latest_batch']) if 'is_latest_batch' in subset else pd.Series(False, index=subset.index)
            chart.add_trace(go.Scatter(x=subset[x_col], y=subset[y_col], mode='markers',
                name='%s (N=%d; %.1f%%)' % (category.replace('_', ' ').title(), len(subset), 100 * len(subset) / total),
                legendgroup=dataset if markers else category,
                legendgrouptitle_text=("Dataset: " + dataset) if markers else None,
                customdata=details,
                marker={'size': 10, 'symbol': markers.get(dataset, 'circle'), 'color': colours.get(category, '#333333'), 'opacity': .85,
                        'line': {'color': 'black', 'width': [2.5 if outline_new and value else 0 for value in latest]}},
                hovertemplate='Source: %{customdata[0]}<br>Dataset: %{customdata[1]}<br>Class: %{customdata[2]}<br>Recommended P: %{customdata[3]:.6g} d<br>Tags: %{customdata[4]}<extra></extra>'))
    for source_id, label in (highlights or {}).items():
        block = table.loc[table.source_id.astype(str).map(_utils.clean_source_id).eq(_utils.clean_source_id(source_id))]
        if not block.empty:
            point_details = []
            for _, row in block.iterrows():
                sid = _utils.clean_source_id(row.get('source_id', ''))
                picture = _source_phase_plot_path(version_dir, sid)
                link = quote(os.path.relpath(picture, maps).replace(os.sep, '/'), safe='/') if picture else ''
                point_details.append([html.escape(sid), html.escape(str(row.get('dataset', ''))),
                    html.escape(str(row.get('final_primary_tag', ''))),
                    _utils.finite_float(row.get('recommended_period_days'), np.nan),
                    html.escape(str(row.get('final_secondary_tags', ''))), link])
            chart.add_trace(go.Scatter(x=block[x_col], y=block[y_col], mode='markers',
                customdata=point_details, name=str(label), marker={'size': 18, 'symbol': 'star', 'color': '#FFD54F',
                                         'line': {'color': 'black', 'width': 1.5}}, hoverinfo='skip'))
    chart.update_layout(title=title, xaxis_title='UMAP 1', yaxis_title='UMAP 2',
                        template='plotly_white', height=750, legend={'groupclick': 'togglegroup'},
                        margin={'l': 60, 'r': 30, 't': 90, 'b': 50})
    script = """
const graph = document.getElementById('{plot_id}');
const panel = document.createElement('section');
panel.id = graph.id + '-comparison';
panel.style.cssText = 'font:15px sans-serif;margin:20px';
const heading = document.createElement('h2');
heading.textContent = 'Compare selected light curves';
const help = document.createElement('p');
help.textContent = 'Click points to add previews below, or select several with the lasso/box tool. Click an image to open it at full size.';
const clear = document.createElement('button');
clear.textContent = 'Clear selection';
clear.disabled = true;
const status = document.createElement('span');
status.style.marginLeft = '12px';
status.setAttribute('aria-live', 'polite');
const board = document.createElement('div');
board.style.cssText = 'display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,420px),1fr));gap:16px;margin-top:16px';
const selected = new Map();
function updateCount() {
    status.textContent = selected.size + ' selected';
    clear.disabled = selected.size === 0;
}
clear.addEventListener('click', function() {
    selected.clear(); board.replaceChildren(); updateCount();
});
panel.append(heading, help, clear, status, board);
graph.after(panel);
function addPreview(detail) {
    if (!detail) return;
    const key = JSON.stringify([detail[1], detail[0]]);
    if (selected.has(key)) return;
    const card = document.createElement('article');
    card.className = 'groove-preview-card';
    card.style.cssText = 'border:1px solid #aaa;border-radius:6px;padding:12px;min-width:0;background:white';
    const caption = document.createElement('p');
    caption.textContent = 'Source ' + detail[0] + ' | ' + detail[1] + ' | ' + detail[2] + ' | P = ' + detail[3] + ' d';
    const remove = document.createElement('button');
    remove.textContent = 'Remove';
    remove.setAttribute('aria-label', 'Remove source ' + detail[0]);
    remove.addEventListener('click', function() {
        selected.delete(key); card.remove(); updateCount();
    });
    card.append(caption, remove);
    if (detail[5]) {
        const link = document.createElement('a');
        link.href = detail[5]; link.target = '_blank'; link.rel = 'noopener';
        const picture = document.createElement('img');
        picture.src = detail[5]; picture.alt = 'Phase plot for ' + detail[0];
        picture.style.cssText = 'display:block;width:100%;height:auto;margin-top:8px';
        picture.addEventListener('error', function() {
            picture.style.display = 'none';
            const missing = document.createElement('p');
            missing.textContent = 'Preview unavailable. Keep this HTML with its source_plots folder.';
            link.after(missing);
        }, {once:true});
        link.appendChild(picture); card.appendChild(link);
    } else {
        const missing = document.createElement('p');
        missing.textContent = 'No saved phase plot is available for this source.';
        card.appendChild(missing);
    }
    selected.set(key, card); board.appendChild(card); updateCount();
}
graph.on('plotly_click', function(event) {
    (event.points || []).forEach(point => addPreview(point.customdata));
});
graph.on('plotly_selected', function(event) {
    if (event) (event.points || []).forEach(point => addPreview(point.customdata));
});
updateCount();
"""
    output = maps / (base_name + '_interactive.html')
    temporary = output.with_suffix('.html.tmp')
    try:
        chart.write_html(str(temporary), include_plotlyjs=True, full_html=True, post_script=script)
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)


def build_category_appendix(table: pd.DataFrame, fold_paths: Mapping[str, Path],
                            version_dir: Path, config: Mapping[str, Any],
                            logger: logging.Logger) -> None:
    """3x3 contact sheets per category, ranked by strength, strongest page first."""
    out = _persistence.figure_directory(version_dir) / "appendix"
    out.mkdir(parents=True, exist_ok=True)
    per_page = int(config.get("appendix_per_page", 9))
    max_pages = int(config.get("appendix_max_pages", 0))
    rows, cols = 3, 3
    for category, block in table.groupby("final_primary_tag"):
        ordered = block.assign(_strength=[_classify.strength_score(r) for _, r in block.iterrows()])
        ordered = ordered.sort_values("_strength", ascending=False)
        total_pages = int(math.ceil(len(ordered) / per_page))
        pages = list(range(0, len(ordered), per_page))
        if max_pages:
            pages = pages[:max_pages]
        written = 0
        skipped = 0
        for page, start in enumerate(pages, start=1):
            chunk = ordered.iloc[start:start + per_page]
            destination = out / ("%s_page%02d.png" % (_utils.safe_name(category), page))
            if bool(config.get("_phase_fold_products_only", False))\
                    and destination.exists()\
                    and not bool(config.get("overwrite_existing_model", False)):
                inputs = [fold_paths.get(str(row["source_key"]))
                          for _, row in chunk.iterrows()]
                inputs = [Path(path) for path in inputs
                          if path is not None and Path(path).exists()]
                if inputs and destination.stat().st_mtime_ns >= max(
                        path.stat().st_mtime_ns for path in inputs):
                    skipped += 1
                    continue
            fig, axes = plt.subplots(rows, cols, figsize=(13.5, 12))
            for ax, (_, row) in zip(axes.ravel(), chunk.iterrows()):
                path = fold_paths.get(str(row["source_key"]))
                if path is not None and Path(path).exists():
                    ax.imshow(plt.imread(str(path)))
                else:
                    ax.text(0.5, 0.5, "fold plot missing", ha="center", va="center",
                            transform=ax.transAxes, fontsize=8)
                ax.axis("off")
            for ax in axes.ravel()[len(chunk):]:
                ax.axis("off")
            fig.suptitle("%s - page %d of %d (ranked by strength)" % (
                category, page, total_pages), fontsize=13)
            fig.tight_layout(rect=(0, 0, 1, 0.97))
            fig.savefig(destination, dpi=130)
            plt.close(fig)
            written += 1
        logger.info("Appendix: %s -> %d written, %d already current over %d sources",
                    category, written, skipped, len(ordered))


def _plot_worker(cache_file: str, row: Mapping[str, Any], config: Mapping[str, Any],
                 fold_path: str) -> Tuple[str, Optional[str]]:
    """Generate the sole fallback source plot when no LS plot exists."""
    if Path(fold_path).exists():
        return str(row.get("source_key", "")), fold_path
    try:
        record = joblib.load(cache_file)
    except Exception:
        return str(row.get("source_key", "")), None
    try:
        create_fold_plot(record, row, Path(fold_path),
                         dpi=int(config.get("review_plot_dpi", 110)))
    except Exception:
        return str(row.get("source_key", "")), None
    return str(row.get("source_key", "")), fold_path


def generate_plots(records: Sequence[Mapping[str, Any]], table: pd.DataFrame,
                   version_dir: Path, config: Mapping[str, Any],
                   logger: logging.Logger,
                   plot_index: Optional[Mapping[str, Path]] = None) -> Dict[str, Path]:
    """Legacy cache-based phase renderer; never returns LS-periodogram paths.

    Normal production runs use :func:`generate_phase_fold_products` with raw
    O-band observations.  This compatibility path is retained for callers that
    still have full feature caches.
    """
    cache_by_key = {str(r["summary"]["source_key"]): r.get("cache_path") for r in records}
    phase_dir = _persistence.figure_directory(version_dir) / "source_plots" / "phase_folded"
    phase_dir.mkdir(parents=True, exist_ok=True)
    n_jobs = int(config.get("n_jobs", -1))

    jobs = []
    resolved: Dict[str, Path] = {}
    for _, row in table.iterrows():
        key = str(row["source_key"])
        source_id = str(row.get("source_id", key))
        phase_plot = phase_dir / ("%s__phase_fold.png" % _utils.safe_name(source_id, 50))
        if phase_plot.exists():
            resolved[key] = phase_plot
            continue
        if not bool(config.get("generate_missing_source_plots", True)):
            continue
        cache_file = cache_by_key.get(key)
        if not cache_file or not Path(cache_file).exists():
            continue
        jobs.append((cache_file, row.to_dict(), str(phase_plot)))

    logger.info("Using %d existing phase plots; generating %d missing phase folds from cache",
                len(resolved), len(jobs))
    if n_jobs == 1 or len(jobs) < 8:
        results = [_plot_worker(c, r, config, f) for c, r, f in jobs]
    else:
        results = joblib.Parallel(n_jobs=n_jobs, backend="loky", verbose=0,
                                  batch_size=8, max_nbytes="50M")(
            joblib.delayed(_plot_worker)(c, r, config, f) for c, r, f in jobs)
    resolved.update({k: Path(v) for k, v in results if v})
    return resolved


def _phase_fold_plot_worker(source: Mapping[str, Any], row: Mapping[str, Any],
                            output_path: str, dpi: int, force: bool
                            ) -> Tuple[str, Optional[str], Optional[str]]:
    """Write a phase fold from the accepted filters without reclassification."""
    output = Path(output_path)
    key = str(row.get("source_key", ""))
    if output.exists() and output.stat().st_size > 0 and not force:
        return key, str(output), None
    data = source.get("data")
    if not isinstance(data, pd.DataFrame) or data.empty:
        return key, None, "raw_light_curve_unavailable"
    o_data = data.copy()
    if o_data.empty:
        return key, None, "no_usable_band_rows"
    period = _utils.finite_float(row.get("recommended_period_days"))
    if not np.isfinite(period) or period <= 0:
        return key, None, "missing_saved_recommended_period"
    record = {"data": o_data, "origin": float(o_data["time"].min())}
    temporary = output.with_name(output.stem + ".tmp.png")
    try:
        create_fold_plot(record, row, temporary, dpi=dpi)
        temporary.replace(output)
    except Exception as error:
        if temporary.exists():
            try:
                temporary.unlink()
            except OSError:
                pass
        return key, None, "phase_plot_failed: %s" % error
    return key, str(output), None


def generate_phase_fold_products(sources: Mapping[str, Mapping[str, Any]],
                                 table: pd.DataFrame, version_dir: Path,
                                 config: Mapping[str, Any], logger: logging.Logger,
                                 force: bool = False
                                 ) -> Tuple[Dict[str, Path], pd.DataFrame]:
    """Generate/resume one accepted-band double-phase image per catalogue row."""
    output_dir = _persistence.figure_directory(version_dir) / "source_plots" / "phase_folded"
    output_dir.mkdir(parents=True, exist_ok=True)
    by_source_id = {str(source.get("source_id", key)): source
                    for key, source in sources.items()}
    jobs = []
    resolved: Dict[str, Path] = {}
    missing: List[Dict[str, Any]] = []
    for _, row in table.iterrows():
        key = str(row.get("source_key", ""))
        source_id = str(row.get("source_id", key))
        output = output_dir / ("%s__phase_fold.png" % _utils.safe_name(source_id, 50))
        # A completed source image is the per-source checkpoint.  Resolve it
        # before requiring raw data so interrupted and transform runs only
        # generate genuinely missing phase folds.
        if output.exists() and output.stat().st_size > 0 and not force:
            resolved[key] = output
            continue
        source = sources.get(key) or by_source_id.get(source_id)
        if source is None:
            missing.append({"source_id": source_id, "source_key": key,
                            "dataset": row.get("dataset", ""),
                            "reason": "raw_light_curve_not_found"})
            continue
        jobs.append((source, row.to_dict(), str(output)))
    logger.info("Phase-only replot: %d existing, %d to generate, %d raw sources missing",
                len(resolved), len(jobs), len(missing))
    n_jobs = int(config.get("n_jobs", -1))
    dpi = int(config.get("review_plot_dpi", 110))
    if n_jobs == 1 or len(jobs) < 8:
        results = [_phase_fold_plot_worker(source, row, path, dpi, force)
                   for source, row, path in jobs]
    else:
        results = joblib.Parallel(n_jobs=n_jobs, backend="loky", verbose=0,
                                  batch_size=8, max_nbytes="50M")(
            joblib.delayed(_phase_fold_plot_worker)(source, row, path, dpi, force)
            for source, row, path in jobs)
    for key, path, error in results:
        if path:
            resolved[key] = Path(path)
        elif error:
            row = table.loc[table["source_key"].astype(str).eq(str(key))].iloc[0]
            missing.append({"source_id": row.get("source_id", ""),
                            "source_key": key, "dataset": row.get("dataset", ""),
                            "reason": error})
    logger.info("Phase-only replot resolved %d/%d saved sources", len(resolved), len(table))
    return resolved, pd.DataFrame(missing, columns=[
        "source_id", "source_key", "dataset", "reason"])


def phase_fold_plot_only(config: Dict[str, Any], args: argparse.Namespace) -> Dict[str, Any]:
    """Rebuild phase-based visual products while leaving every UMAP untouched."""
    output_root = Path(config["output_root"])
    _, version_dir = _persistence.resolve_version_dir(output_root, config.get("model_version"))
    if not version_dir.exists():
        raise SystemExit("Model version directory not found: %s" % version_dir)
    logger = _utils.setup_logging(version_dir, args.verbose)
    table, catalogue_source = _loading.load_catalogue_for_plot_only(version_dir, logger)
    required = {"source_key", "source_id", "dataset", "final_primary_tag",
                "recommended_period_days"}
    missing_columns = sorted(required - set(table.columns))
    if missing_columns:
        raise SystemExit("Saved catalogue lacks plotting columns: %s" %
                         ", ".join(missing_columns))

    # Record immutable UMAP product signatures before doing any plotting.
    umap_products = list((_persistence.figure_directory(version_dir) / "maps").glob("all_families_*umap.*"))
    umap_signatures = {path: (path.stat().st_size, path.stat().st_mtime_ns)
                       for path in umap_products}
    protected_columns = [column for column in (
        "source_key", "final_primary_tag", "final_secondary_tags",
        "recommended_period_days", "periodic_umap_1", "periodic_umap_2",
        "transient_umap_1", "transient_umap_2", "combined_umap_1",
        "combined_umap_2", "classification_evidence_umap_1",
        "classification_evidence_umap_2") if column in table.columns]
    protected = table[protected_columns].copy(deep=True)

    # Plotting explicitly reloads O-band observations only. No feature
    # extraction, classifier, UMAP fit/transform, or period search is called.
    local = dict(config)
    local["_phase_fold_products_only"] = True
    local["_plot_only_lightweight_validation"] = True
    specs = [dataset for dataset in config.get("datasets", [])
             if dataset.get("lightcurve_inputs")]
    if not specs:
        raise SystemExit("No configured light-curve inputs are available for phase replotting.")
    sources, load_problems = _loading.load_lightcurves(specs, local, logger)
    fold_paths, missing_phase = generate_phase_fold_products(
        sources, table, version_dir, local, logger,
        force=bool(config.get("overwrite_existing_model", False)))

    # Use saved neighbours when available; otherwise reproduce the validation
    # lookup without changing or saving any UMAP coordinate.
    neighbour_path = Path(version_dir) / "tables" / "umap_neighbour_anchor_details.csv"
    neighbour_details = _loading.read_table(neighbour_path)
    display_table = table
    if neighbour_details.empty:
        combined_keys, combined_space = _persistence.load_combined_validation_space(version_dir)
        display_table, neighbour_details, _ = _embedding.nearest_neighbour_validation(
            table, local, combined_space, combined_keys, logger)
    build_neighbour_review_pages(
        neighbour_details, display_table, fold_paths, version_dir, logger)
    build_family_maps([], display_table, version_dir, local, logger, fold_paths)
    build_category_appendix(display_table, fold_paths, version_dir, local, logger)
    memberships, missing_links = _outputs.build_category_folders(
        display_table, fold_paths, {}, version_dir, local, logger)

    tables_dir = Path(version_dir) / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)
    if catalogue_source == "finalisation_checkpoint":
        _utils.atomic_write_csv(table, tables_dir / "all_sources.csv")
    _utils.atomic_write_csv(memberships, tables_dir / "category_memberships.csv")
    _utils.atomic_write_csv(missing_phase, tables_dir / "missing_phase_fold_plots.csv")
    _utils.atomic_write_csv(missing_links, tables_dir / "missing_category_plot_links.csv")
    if not load_problems.empty:
        _utils.atomic_write_csv(load_problems, tables_dir / "phase_replot_load_problems.csv")
    _outputs.write_membership_manifests(display_table, memberships, tables_dir)
    _outputs.write_blind_validation_sample(display_table, memberships, version_dir, local)

    if not display_table[protected_columns].equals(protected):
        raise AssertionError("Plot-only mode changed saved labels, periods, or UMAP coordinates")
    changed_umaps = [path for path, signature in umap_signatures.items()
                     if not path.exists()
                     or (path.stat().st_size, path.stat().st_mtime_ns) != signature]
    if changed_umaps:
        raise AssertionError("Plot-only mode altered UMAP products: %s" %
                             ", ".join(path.name for path in changed_umaps))
    logger.info("Plot-only regression passed: %d UMAP products and all saved labels/periods "
                "are unchanged", len(umap_signatures))
    return {"version_dir": str(version_dir), "n_sources": len(table),
            "phase_plots": len(fold_paths), "umap_products_changed": 0}


def _source_phase_plot_path(version_dir: Path, source_id: str) -> str:
    path = (_persistence.figure_directory(version_dir) / "source_plots" / "phase_folded" /
            ("%s__phase_fold.png" % _utils.safe_name(source_id)))
    return str(path) if path.exists() else ""


def make_neighbour_phase_grid(table: pd.DataFrame, source_keys: Sequence[str],
                              neighbour_table: pd.DataFrame,
                              records: Mapping[str, Mapping[str, Any]],
                              version_dir: Path, output: Path,
                              source_label: str, period_factor: float = 1.0) -> None:
    """Make a 3x3 grid of accepted bands at each source's recommended period."""
    lookup = table.set_index(table["source_key"].astype(str), drop=False)
    high = neighbour_table.loc[
        neighbour_table["space"].eq("standardised_combined_feature_space")]
    details = {str(row["source_key"]): row for _, row in high.iterrows()}
    fig, axes = plt.subplots(3, 3, figsize=(15, 11.5), squeeze=False)
    for panel, (ax, key) in enumerate(zip(axes.ravel(), source_keys[:9])):
        if key not in lookup.index:
            ax.axis("off")
            continue
        row = lookup.loc[key]
        source_id = _utils.clean_source_id(row.get("source_id", ""))
        record = records.get(source_id)
        period = _utils.finite_float(row.get("recommended_period_days"), np.nan) * period_factor
        if record is not None:
            _fold_scatter(ax, record["data"], period, float(record["origin"]))
        elif period_factor == 1.0:
            saved = _source_phase_plot_path(version_dir, source_id)
            if saved:
                ax.imshow(plt.imread(saved))
                ax.axis("off")
            else:
                ax.text(0.5, 0.5, "phase fold unavailable", ha="center", va="center",
                        transform=ax.transAxes)
        else:
            ax.text(0.5, 0.5, "light curve unavailable", ha="center", va="center",
                    transform=ax.transAxes)
        if panel == 0:
            heading = "TARGET | %s | %s" % (source_id, row.get("final_primary_tag", ""))
        else:
            detail = details.get(key, {})
            heading = "NN %d | %s | %s | feature d=%.3g" % (
                panel, source_id, row.get("final_primary_tag", ""),
                _utils.finite_float(detail.get("distance"), np.nan))
        ax.set_title("%s\nP%s = %.6g d" % (
            heading,
            "" if period_factor == 1.0 else ("/2" if period_factor == 0.5 else "x2"),
            period), fontsize=8)
    for ax in axes.ravel()[len(source_keys[:9]):]:
        ax.axis("off")
    handles, labels = axes.ravel()[0].get_legend_handles_labels()
    if handles:
        fig.legend(handles, labels, loc="lower center", ncol=min(5, len(handles)), fontsize=7)
    factor_title = {0.5: "P/2", 1.0: "recommended P", 2.0: "2P"}.get(
        period_factor, "%.3gP" % period_factor)
    fig.suptitle("%s and nearest morphology neighbours - folded at %s" % (
        source_label, factor_title), fontsize=14)
    fig.tight_layout(rect=(0, 0.04, 1, 0.96))
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=150)
    plt.close(fig)


def make_detached_family_map(table: pd.DataFrame, version_dir: Path,
                             family_column: str, output_base: str) -> None:
    work = table.loc[np.isfinite(table["combined_umap_1"]) &
                     np.isfinite(table["combined_umap_2"])].copy()
    fig, ax = plt.subplots(figsize=(11, 9))
    assigned = work[family_column].astype(str).str.startswith("detached_family_")
    background = work.loc[~assigned]
    ax.scatter(background["combined_umap_1"], background["combined_umap_2"],
               s=18, c="#B8B8B8", alpha=0.22, edgecolors="none", zorder=1)
    handles = [Line2D([0], [0], marker="o", linestyle="none", color="#B8B8B8",
                      label="Unassigned connected/uncertain body (N=%d)" % len(background))]
    palette = plt.get_cmap("tab10")
    families = sorted(work.loc[assigned, family_column].unique())
    for index, family in enumerate(families):
        block = work.loc[work[family_column].eq(family)]
        colour = palette(index % 10)
        ax.scatter(block["combined_umap_1"], block["combined_umap_2"],
                   s=27, c=[colour], alpha=0.82, edgecolors="none", zorder=3 + index)
        handles.append(Line2D([0], [0], marker="o", linestyle="none", color=colour,
                              label="%s (N=%d)" % (
                                  family.replace("_", " ").title(), len(block))))
    ax.set_xlabel("UMAP 1")
    ax.set_ylabel("UMAP 2")
    ax.set_title("Detached density families in the frozen combined UMAP")
    ax.grid(alpha=0.25)
    ax.legend(handles=handles, loc="best", fontsize=9)
    fig.tight_layout()
    maps = _persistence.figure_directory(version_dir) / "maps"
    maps.mkdir(parents=True, exist_ok=True)
    fig.savefig(maps / (output_base + ".png"), dpi=170)
    fig.savefig(maps / (output_base + ".pdf"))
    plt.close(fig)
