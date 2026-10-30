"""Individual exports select display bands without modifying scientific state."""

import hashlib
import runpy
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from groove.config import load
from groove.morphology import plots

export_fold = runpy.run_path(str(Path(__file__).parents[1] / "tools/plot_source_fold.py"))["export_fold"]
SOURCE_ID = "9900000000000000001"


def saved_source(tmp_path):
    config = tmp_path / "run.yaml"
    config.write_text("name: export_test\noutput_folder: results\nmorphology:\n  mode: classify\n")
    cfg = load(config)
    cfg.selected_dir.mkdir(parents=True)
    time = np.arange(160, dtype=float) * 0.11
    photometry = cfg.selected_dir / f"synthetic__GaiaDR3_{SOURCE_ID}_cleaned.csv"
    pd.DataFrame({"MJD": time, "m": 14 + 0.2 * np.cos(time), "dm": 0.02,
                  "F": np.where(np.arange(len(time)) % 2, "o", "c"),
                  "target_GaiaDR3": SOURCE_ID}).to_csv(photometry, index=False)
    catalogue = cfg.morphology_dir / "classification/tables/all_sources.csv"
    catalogue.parent.mkdir(parents=True)
    pd.DataFrame({"source_id": [SOURCE_ID], "recommended_period_days": [2.81508],
                  "final_primary_tag": ["transit"], "final_confidence": [0.76]}).to_csv(catalogue, index=False)
    return config, cfg, photometry, catalogue


@pytest.mark.parametrize("band", ["o", "c", "both"])
def test_export_retains_saved_period_origin_and_inputs(tmp_path, monkeypatch, band):
    config, cfg, photometry, catalogue = saved_source(tmp_path)
    files = [config, photometry, catalogue]
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    captured = []
    create = plots.create_fold_plot

    def capture(record, row, output, dpi):
        captured.append((record, row))
        create(record, row, output, dpi)

    monkeypatch.setattr(plots, "create_fold_plot", capture)
    output = export_fold(config, SOURCE_ID, band, dpi=60)
    assert output.is_file() and output.stat().st_size > 0
    assert output.parent == cfg.plots_root / "individual"
    record, row = captured[0]
    assert record["origin"] == 0.0  # First observation is cyan, also for the O-only display.
    assert set(record["data"]["filter"]) == ({"o", "c"} if band == "both" else {band})
    assert len(record["data"]) == (160 if band == "both" else 80)
    assert float(row["recommended_period_days"]) == 2.81508
    assert before == {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in files}


def test_export_checks_missing_band_and_bad_period(tmp_path):
    config, _, photometry, catalogue = saved_source(tmp_path)
    frame = pd.read_csv(photometry)
    frame.loc[frame.F.eq("o")].to_csv(photometry, index=False)
    with pytest.raises(ValueError, match="No accepted c-band"):
        export_fold(config, SOURCE_ID, "c")
    frame = pd.read_csv(catalogue, dtype=str)
    frame["recommended_period_days"] = "-1"
    frame.to_csv(catalogue, index=False)
    with pytest.raises(ValueError, match="positive and finite"):
        export_fold(config, SOURCE_ID)
