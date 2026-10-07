"""Fast checks: package imports, config loading, selection criteria, and the
cleaning stage on a synthetic ATLAS-format light curve."""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from groove import config, pipeline
from groove.select import criteria, settings as sel_settings


def test_all_modules_import():
    import importlib, pkgutil, groove
    for stage in ("download", "clean", "select", "periods", "morphology"):
        pkg = importlib.import_module(f"groove.{stage}")
        for mod in pkgutil.iter_modules(pkg.__path__):
            importlib.import_module(f"groove.{stage}.{mod.name}")


def test_config_and_folder_contract(tmp_path):
    y = tmp_path / "c.yaml"
    y.write_text("name: X\noutput_folder: out\nyears: 4\ngroup: my_field\n")
    cfg = config.load(y)
    assert cfg.raw_lightcurves == tmp_path / "out" / "1_raw" / "atlas_4yr_reduced" / "all_lightcurves"
    assert cfg.selected_dir.parent == cfg.clean_dir.parent
    assert cfg.clean_plots == cfg.plots_root / "clean"
    assert cfg.period_plots == cfg.plots_root / "periods"
    m = pipeline.morphology_config(cfg)
    assert m["datasets"][0]["lightcurve_inputs"] == [str(cfg.selected_dir)]


def test_selection_criteria():
    summary = pd.DataFrame({
        "n_final_keep": [500, 80, 500, 500],
        "n_c_clean": [100, 20, 10, 100], "n_o_clean": [400, 60, 20, 400],
        "baseline_days_clean": [1500, 1500, 1500, 100],
        "fraction_kept": [0.9, 0.9, 0.9, 0.9],
        "median_dm_c_clean": [0.05, 0.05, 0.05, 0.05], "median_dm_o_clean": [0.03, 0.03, 0.03, 0.03],
        "status": ["ok"] * 4,
    })
    out = criteria.evaluate(summary)
    assert out["selected"].tolist() == [True, False, False, False]
    assert "baseline_under_365_days" in out["selection_reasons"][3]


def synthetic_raw(path: Path, gid="3216489845356186496", n=800, seed=0):
    rng = np.random.default_rng(seed)
    mjd = np.sort(rng.uniform(58000, 61500, n))
    F = rng.choice(["c", "o"], n)
    m = 14.5 + 0.3 * np.sin(2 * np.pi * mjd / 12.7) + rng.normal(0, 0.03, n)
    dm = np.full(n, 0.03)
    uJy = 3631e6 * 10 ** (-0.4 * m)
    df = pd.DataFrame({"target_GaiaDR3": gid, "target_group": "T", "###MJD": mjd, "m": m, "dm": dm,
                       "uJy": uJy, "duJy": uJy * dm / 1.0857, "F": F, "err": 0, "chi/N": 1.0,
                       "RA": 84.0, "Dec": -2.5, "x": 5000.0, "y": 5000.0, "maj": 3.0, "min": 3.0,
                       "phi": 0, "apfit": -0.5, "mag5sig": 19.0, "Sky": 19.0, "Obs": "o"})
    df.to_csv(path / f"T__GaiaDR3_{gid}__ATLAS_none__reduced_full_history.csv", index=False)


def test_clean_and_select_stages(tmp_path):
    y = tmp_path / "c.yaml"
    y.write_text("name: T\noutput_folder: out\nyears: full\n")
    cfg = config.load(y)
    cfg.raw_lightcurves.mkdir(parents=True)
    synthetic_raw(cfg.raw_lightcurves)
    pipeline.run_clean(cfg)
    assert len(list(cfg.clean_dir.glob("*_cleaned.csv"))) == 1
    pipeline.run_select(cfg)
    assert len(list(cfg.selected_dir.glob("*_cleaned.csv"))) == 1


def test_morphology_smoke():
    from groove.morphology import smoke
    assert smoke.smoke_test(False) == 0
