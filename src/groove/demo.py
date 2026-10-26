"""Small, reproducible ATLAS-format demonstration; no real observations or token."""

from pathlib import Path

import numpy as np
import pandas as pd
import yaml

# Obviously synthetic identifiers; never use these to request photometry.
DEMO_SOURCE_ID_BASE = 9_900_000_000_000_000_000


def create(directory: str | Path, *, extended: bool = False) -> Path:
    directory = Path(directory).expanduser().resolve()
    if directory.exists() and any(directory.iterdir()):
        raise ValueError(f"Demo folder is not empty: {directory}. Choose a new folder.")
    raw = directory / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(42)
    truth = []
    for index in range(12):
        gid = str(DEMO_SOURCE_ID_BASE + index)
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
        frame = pd.DataFrame(
            {
                "target_GaiaDR3": gid,
                "target_group": "synthetic",
                "MJD": time,
                "F": band,
                "m": mag,
                "dm": 0.025,
                "uJy": flux,
                "duJy": flux * 0.025 / 1.0857,
                "err": 0,
                "RA": 84.0,
                "Dec": -2.5,
                "x": 5000.0,
                "y": 5000.0,
                "maj": 3.0,
                "min": 3.0,
                "apfit": -0.5,
                "mag5sig": 19.0,
                "Sky": 19.0,
            }
        )
        frame.to_csv(raw / f"synthetic__GaiaDR3_{gid}.csv", index=False)
        truth.append(
            {"source_id": gid, "injected_period_days": period if kind != "nonvar" else None, "injected_shape": kind}
        )
    if extended:
        _add_extended_cases(raw, truth)
    pd.DataFrame(truth).to_csv(directory / "truth.csv", index=False)
    cfg = {
        "name": "synthetic_demo",
        "input_folder": "raw",
        "output_folder": "results",
        "clean": {"save_pdf": False, "n_example_plots": 2},
        "periods": {
            "series_to_run": ["o", "c"],
            "plot_series": ["o", "c"],
            "max_period_days": 50,
            "run_bls": False,
            "plot_time_segments": 4,
        },
        "morphology": {"mode": "fit", "model_version": "demo", "n_jobs": 1},
    }
    if extended:
        cfg["name"] = "synthetic_extended"
        cfg["periods"].update(
            {
                "max_period_days": 120,
                "run_bls": True,
                "auto_plot_alias_suspects": True,
                "extra_fold_series_mode": "all",
                "ls_samples_per_peak": 30,
                "bls_min_period_days": 2,
                "bls_max_period_days": 30,
                "bls_samples_per_peak": 3,
                "bls_durations_days": [0.2, 0.4],
            }
        )
        cfg["morphology"]["model_version"] = "extended_demo"
        (directory / "CASE_GUIDE.md").write_text(
            "# Extended synthetic demonstration\n\n"
            "All identifiers and observations are artificial; do not download these IDs.\n"
            "The original 12 sources remain unchanged. truth.csv records the new inputs.\n"
            "daily_systematic combines an injected 1-day instrumental term with an\n"
            "8.3-day stellar wave; the daily peak should trigger automatic alias review.\n"
            "alias_promoted strengthens the 8.3-day stellar term so LS rank 2 clears\n"
            "the replacement threshold and is adopted over the rank-1 daily alias.\n"
            "nightly_sampling samples a 73.6-day wave near the same time each night;\n"
            "inspect its daily side peaks even if the true period remains strongest.\n"
            "unequal_eclipses tests P versus P/2 and 2P diagnostics. Repeated flares,\n"
            "irregular dips, evolving waves, noisy measurements and single-filter\n"
            "sources, an isolated dip and offset double dips exercise review paths.\n"
            "These inputs are not\n"
            "forced output labels or a survey completeness/purity estimate.\n"
            "Run groove demo-check DIRECTORY after the pipeline for a coverage report.\n",
            encoding="utf-8",
        )
    path = directory / "run.yaml"
    path.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
    return path


def _add_extended_cases(raw: Path, truth: list[dict]) -> None:
    """Independent seed preserves the original 12-source regression fixture."""
    rng = np.random.default_rng(20261007)
    cases = [
        ("daily_systematic", 8.3),
        ("nightly_sampling", 73.6),
        ("unequal_eclipses", 10.8),
        ("repeated_flares", None),
        ("irregular_dips", None),
        ("evolving_wave", 17.3),
        ("noisy", None),
        ("cyan_only", 11.4),
        ("orange_only", 19.7),
        ("single_dip", None),
        ("double_dip", 61.3),
        ("alias_promoted", 8.3),
    ]
    for index, (kind, period) in enumerate(cases, start=12):
        gid = str(DEMO_SOURCE_ID_BASE + index)
        n = 1200 if kind == "unequal_eclipses" else 720
        time = np.sort(rng.uniform(58000, 59100, n))
        if kind == "nightly_sampling":
            time = 58000 + np.sort(rng.choice(1100, n, replace=False)) + rng.uniform(0.18, 0.22, n)
        band = rng.choice(["c", "o"], n)
        error = 0.025
        phase = (time / period) % 1 if period else np.zeros(n)

        def distance(centre: float, phases: np.ndarray = phase) -> np.ndarray:
            return (phases - centre + 0.5) % 1 - 0.5

        if kind in {"daily_systematic", "alias_promoted"}:
            stellar_amplitude = 0.30 if kind == "alias_promoted" else 0.18
            signal = 0.4 * np.sin(2 * np.pi * time) + stellar_amplitude * np.sin(2 * np.pi * phase)
        elif kind == "unequal_eclipses":
            signal = 0.9 * np.exp(-0.5 * (distance(0) / 0.11) ** 2)
            signal += 0.6 * np.exp(-0.5 * (distance(0.5) / 0.11) ** 2)
        elif kind == "repeated_flares":
            signal = np.zeros(n)
            for event in np.linspace(58020, 59080, 35) + rng.normal(0, 3, 35):
                elapsed = time - event
                signal -= 0.9 * np.exp(-np.maximum(elapsed, 0) / 1.2) * (elapsed >= 0)
        elif kind == "irregular_dips":
            signal = np.zeros(n)
            for event, width in zip(rng.uniform(58010, 59090, 18), rng.uniform(3, 9, 18), strict=True):
                signal += 0.8 * np.exp(-0.5 * ((time - event) / width) ** 2)
        elif kind == "single_dip":
            signal = 1.2 * np.exp(-0.5 * ((time - 58550) / 5) ** 2)
        elif kind == "double_dip":
            secondary_offset_days = 6.5
            signal = 1.2 * np.exp(-0.5 * (distance(0) / 0.025) ** 2)
            signal += 1.1 * np.exp(-0.5 * (distance(secondary_offset_days / period) / 0.025) ** 2)
        elif kind == "evolving_wave":
            phase_drift = 0.7 * ((time - 58000) / 1100) ** 2
            signal = 0.3 * np.sin(2 * np.pi * (phase + phase_drift))
        elif kind == "noisy":
            signal = rng.normal(0, 0.25, n)  # underestimated errors: intentionally noisy
        else:
            signal = 0.3 * np.sin(2 * np.pi * phase)
            if kind == "cyan_only":
                band[:] = "c"
            elif kind == "orange_only":
                band[:] = "o"
        mag = 14.5 + np.where(band == "c", 0.4, 0) + signal + rng.normal(0, error, n)
        flux = 3631e6 * 10 ** (-0.4 * mag)
        frame = pd.DataFrame(
            {
                "target_GaiaDR3": gid,
                "target_group": "synthetic_extended",
                "MJD": time,
                "F": band,
                "m": mag,
                "dm": error,
                "uJy": flux,
                "duJy": flux * error / 1.0857,
                "err": 0,
                "RA": 84.0,
                "Dec": -2.5,
                "x": 5000.0,
                "y": 5000.0,
                "maj": 3.0,
                "min": 3.0,
                "apfit": -0.5,
                "mag5sig": 19.0,
                "Sky": 19.0,
            }
        )
        frame.to_csv(raw / f"synthetic__GaiaDR3_{gid}.csv", index=False)
        truth.append({"source_id": gid, "injected_period_days": period, "injected_shape": kind})
