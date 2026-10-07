"""Small, reproducible ATLAS-format demonstration; no real observations or token."""
from pathlib import Path
import numpy as np
import pandas as pd
import yaml


def create(directory: str | Path) -> Path:
    directory = Path(directory).expanduser().resolve()
    if directory.exists() and any(directory.iterdir()):
        raise ValueError(f"Demo folder is not empty: {directory}. Choose a new folder.")
    raw = directory / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(42)
    truth = []
    for index in range(12):
        gid = str(3216489845356186496 + index)
        period = 8.3 + 1.7 * index
        time = np.sort(rng.uniform(58000, 59100, 360))
        phase = (time / period) % 1
        band = rng.choice(["c", "o"], len(time))
        kind = ("wavelike", "dipping", "nonvar")[index % 3]
        if kind == "wavelike":
            signal = 0.25 * np.sin(2 * np.pi * phase)
        elif kind == "dipping":
            signal = 0.9 * np.exp(-0.5 * (((phase + 0.5) % 1 - 0.5) / 0.045) ** 2)
        else:
            signal = np.zeros(len(time))
        mag = 14.5 + np.where(band == "c", 0.4, 0) + signal + rng.normal(0, 0.025, len(time))
        flux = 3631e6 * 10 ** (-0.4 * mag)
        frame = pd.DataFrame({"target_GaiaDR3": gid, "target_group": "synthetic", "MJD": time,
                              "F": band, "m": mag, "dm": 0.025, "uJy": flux,
                              "duJy": flux * 0.025 / 1.0857, "err": 0,
                              "RA": 84.0, "Dec": -2.5, "x": 5000., "y": 5000.,
                              "maj": 3., "min": 3., "apfit": -0.5, "mag5sig": 19., "Sky": 19.})
        frame.to_csv(raw / f"synthetic__GaiaDR3_{gid}.csv", index=False)
        truth.append({"source_id": gid, "injected_period_days": period if kind != "nonvar" else None, "injected_shape": kind})
    pd.DataFrame(truth).to_csv(directory / "truth.csv", index=False)
    cfg = {"name": "synthetic_demo", "input_folder": "raw", "output_folder": "results",
           "clean": {"save_pdf": False, "n_example_plots": 2},
           "periods": {"max_period_days": 50, "run_bls": False, "plot_time_segments": 4},
           "morphology": {"mode": "fit", "model_version": "demo", "n_jobs": 1}}
    path = directory / "run.yaml"
    path.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
    return path
