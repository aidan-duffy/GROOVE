"""Export a band-selected phase fold at a saved morphology period.

Run from the repository root after installing GROOVE. This reads saved
catalogue values and selected photometry without recomputing any analysis.
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from groove.config import load
from groove.core.plotstyle import LIGHTCURVE_ALPHA, LIGHTCURVE_POINT_SIZE
from groove.morphology import loading, persistence, plots, utils
from groove.pipeline import morphology_config


def export_fold(config_path: Path, source_id: str, band: str = "o",
                output: Path | None = None, catalogue: Path | None = None,
                dpi: int = 180, point_size: float | None = None,
                point_alpha: float | None = None) -> Path:
    """Filter only the display, retaining the saved period and full-data origin."""
    if band not in {"o", "c", "both"}:
        raise ValueError("band must be o, c or both")
    if dpi <= 0:
        raise ValueError("dpi must be positive")
    cfg = load(config_path)
    config = morphology_config(cfg)
    root = Path(config["output_root"])
    if catalogue is None:
        state = (root / "classification" if config.get("mode") == "classify" else
                 persistence.resolve_version_dir(root, config.get("model_version"))[1])
        catalogue = state / "tables" / "all_sources.csv"
    catalogue = Path(catalogue)
    if not catalogue.is_file():
        raise FileNotFoundError(f"Saved morphology catalogue not found: {catalogue}")
    table = pd.read_csv(catalogue, dtype=str)
    if not {"source_id", "recommended_period_days"}.issubset(table.columns):
        raise ValueError("Catalogue requires source_id and recommended_period_days")
    source_id = utils.clean_source_id(source_id)
    selected = table.loc[table["source_id"].map(utils.clean_source_id).eq(source_id)]
    if len(selected) != 1:
        raise ValueError(f"Expected one saved catalogue row for {source_id}; found {len(selected)}")
    row = selected.iloc[0].to_dict()
    period = utils.finite_float(row.get("recommended_period_days"))
    if not np.isfinite(period) or period <= 0:
        raise ValueError("The saved recommended period must be positive and finite")

    sources = loading.load_selected_lightcurves(
        config["datasets"], config, [source_id], logging.getLogger(__name__))
    if source_id not in sources:
        raise ValueError(f"Accepted selected photometry unavailable for {source_id}")
    record = dict(sources[source_id])
    data = record["data"].copy()
    if band != "both":
        data = data.loc[data["filter"].eq(band)].copy()
    if data.empty:
        raise ValueError(f"No accepted {band}-band observations for {source_id}")
    record["data"] = data
    # The complete accepted source supplied the origin before display filtering.
    # This keeps eclipse phases aligned with the existing morphology fold.
    row["final_primary_tag"] = f"{row.get('final_primary_tag', '')} | {band.upper()} band"
    output = Path(output) if output is not None else (
        cfg.plots_root / "individual" / f"{utils.safe_name(source_id)}__{band}_phase_fold.png")
    if output.suffix.lower() not in {".png", ".pdf"}:
        raise ValueError("Output must end in .png or .pdf")
    size = float(config.get("review_plot_marker_size", LIGHTCURVE_POINT_SIZE)) if point_size is None else point_size
    alpha = float(config.get("review_plot_marker_alpha", LIGHTCURVE_ALPHA)) if point_alpha is None else point_alpha
    plots.create_fold_plot(record, row, output, dpi=dpi, point_size=size, point_alpha=alpha)
    print(f"Saved {output} | saved recommended P={period:.10g} d | display={band}")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-c", "--config", type=Path, required=True)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--band", choices=["o", "c", "both"], default="o")
    parser.add_argument("--output", type=Path, help="Separate PNG/PDF output; default: plots/individual")
    parser.add_argument("--catalogue", type=Path, help="Explicit saved morphology all_sources.csv")
    parser.add_argument("--dpi", type=int, default=180)
    parser.add_argument("--point-size", type=float, help="Marker diameter in points; overrides the export display only")
    parser.add_argument("--point-alpha", type=float, help="Marker opacity in (0, 1]; overrides the export display only")
    args = parser.parse_args()
    export_fold(args.config, args.source_id, args.band, args.output, args.catalogue, args.dpi,
                args.point_size, args.point_alpha)


if __name__ == "__main__":
    main()
