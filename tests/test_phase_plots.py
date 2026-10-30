"""Phase display changes retain every plotted sample and its band marker."""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest

from groove import config, pipeline
from groove.core.plotstyle import phase_focus_mask
from groove.morphology import plots as morphology
from groove.periods import plots as periods
from groove.periods import settings


def assert_phase_colours(ax, expected_count, two_cycles=True):
    points = [line for line in ax.lines
              if line.get_marker() in {"o", "s", ".", "^"} and len(line.get_xdata())]
    assert sum(len(line.get_xdata()) for line in points) == expected_count
    grey_count = 0
    for line in points:
        phase = np.asarray(line.get_xdata())
        focus = phase_focus_mask(phase, two_cycles)
        if line.get_color() == "0.7":
            assert not focus.any()
            grey_count += len(phase)
        else:
            assert focus.all()
    assert (grey_count > 0) == two_cycles


def test_morphology_fold_retains_points_markers_and_median_values():
    time = np.arange(320, dtype=float) * 0.017
    frame = pd.DataFrame({"time": time, "mag": 14 + 0.2 * np.sin(2 * np.pi * time),
                          "filter": np.where(np.arange(len(time)) % 2, "o", "c")})
    original = frame.copy(deep=True)
    fig, ax = plt.subplots()
    try:
        morphology._fold_scatter(ax, frame, 1.0, 0.0)
        assert_phase_colours(ax, 2 * len(frame))
        assert ax.get_xlim() == (0.0, 2.0)
        assert ax.yaxis_inverted()
        points = [line for line in ax.lines if " Q" in line.get_label()]
        assert points and {line.get_marker() for line in points} == {"o"}
        assert all(line.get_markersize() == pytest.approx(
            2.0 if line.get_label().startswith("C") else 1.7) for line in points)
        assert all(line.get_markerfacecolor() == "none" for line in points if line.get_label().startswith("C"))
        assert all(line.get_markeredgewidth() == 0 for line in points if line.get_label().startswith("O"))
        for line in ax.lines:
            if line.get_color() not in {"0.65", "teal", "black"}:
                continue
            x, y = np.asarray(line.get_xdata()), np.asarray(line.get_ydata())
            finite = np.isfinite(y)
            focus = phase_focus_mask(x)
            assert finite.any()
            assert not (finite & (focus if line.get_color() == "0.65" else ~focus)).any()
        pd.testing.assert_frame_equal(frame, original)
    finally:
        plt.close(fig)


@pytest.mark.parametrize("two_cycles", [True, False])
def test_period_fold_preserves_errors_and_single_cycle_colours(monkeypatch, two_cycles):
    monkeypatch.setattr(settings, "PLOT_TWO_PHASE_CYCLES", two_cycles)
    monkeypatch.setattr(settings, "PLOT_SIGMA_LIMIT", None)
    time = np.arange(96, dtype=float) * 0.117
    prepared = {"time": time, "plot_signal": 14 + np.sin(time),
                "plot_error": np.full(len(time), 0.02),
                "band": np.where(np.arange(len(time)) % 2, "o", "c"),
                "plot_signal_type": "magnitude"}
    fig, ax = plt.subplots()
    try:
        periods.plot_diagnostic_fold_axis(ax, prepared, 1.0)
        assert_phase_colours(ax, len(time) * (2 if two_cycles else 1), two_cycles)
        assert sum(len(c.lines[2][0].get_segments()) for c in ax.containers) == len(time) * (2 if two_cycles else 1)
        assert ax.get_xlim() == (0.0, 2.0 if two_cycles else 1.0)
    finally:
        plt.close(fig)


def test_period_default_uses_four_time_intervals():
    assert settings.PLOT_TIME_SEGMENTS == 4
    assert len(settings.PLOT_TIME_SEGMENT_COLORS) == 4


@pytest.mark.parametrize("source,forced,series,expected,label", [
    (2.81508, None, 1.40754, 2.81508, "source recommended period"),
    (2.81508, 2.9, 1.40754, 2.9, "forced period"),
    (None, None, 1.40754, 1.40754, "series period"),
    (np.nan, None, 1.40754, 1.40754, "series period"),
    (-1.0, None, 1.40754, 1.40754, "series period"),
    (None, None, np.nan, 1.3, "raw LS period"),
])
def test_main_fold_period_precedence(monkeypatch, source, forced, series, expected, label):
    monkeypatch.setattr(settings, "FORCED_FOLD_PERIOD_DAYS", forced)
    row = {"raw_ls_best_period_days": 1.3, "recommended_series_period_days": series}
    assert periods.main_fold_period(row, source) == (expected, label)


@pytest.mark.parametrize("forced", [None, 2.9])
def test_main_panel_renders_adopted_2p_or_labelled_override(tmp_path, monkeypatch, forced):
    monkeypatch.setattr(settings, "FORCED_FOLD_PERIOD_DAYS", forced)
    monkeypatch.setattr(settings, "PLOT_DIR", tmp_path)
    monkeypatch.setattr(settings, "PLOT_DPI", 50)
    monkeypatch.setattr(settings, "PLOT_SIGMA_LIMIT", None)
    monkeypatch.setattr(settings, "PLOT_SERIES", ["o"])
    monkeypatch.setattr(settings, "PLOT_MODE", "all")
    monkeypatch.setattr(settings, "PLOT_TWO_PHASE_CYCLES", True)
    time = np.linspace(58000, 58020, 120)
    prepared = {"time": time, "series_name": "o", "n_points": len(time),
                "baseline_days": 20.0, "plot_signal": 14 + 0.2 * np.cos(time),
                "plot_error": np.full(len(time), 0.02), "band": np.full(len(time), "o"),
                "plot_signal_type": "magnitude", "invert_y": True}
    row = {"raw_ls_best_period_days": 1.40754, "recommended_series_period_days": 1.40754,
           "tested_2p_days": 2.81508, "primary_classification": "harmonic_possible",
           "two_p_note": "2P supported by unequal consecutive cycles"}
    original = row.copy()
    metadata = {"source_id": "synthetic", "object_name": "synthetic", "file": "synthetic.csv"}
    result = {"period": np.array([1.40754, 2.81508]), "power": np.array([0.3, 0.1]),
              "peaks": [(1.40754, 0.3, 0)]}
    figures = []
    save = periods._files.save_figure

    def capture(fig, path, **kwargs):
        figures.append(fig)
        save(fig, path, **kwargs)

    monkeypatch.setattr(periods._files, "save_figure", capture)
    output = periods.plot_best_per_star(metadata, prepared, result, row, np.nan,
                                       source_period_days=2.81508)
    assert tmp_path in Path(output).parents
    ax = figures[0].axes[-1]
    expected_period = forced if forced is not None else 2.81508
    expected_label = "forced period" if forced is not None else "source recommended period"
    assert f"Folded at {expected_label} P={expected_period:.4f}" in ax.get_title()
    observed = np.concatenate([line.get_xdata() for line in ax.lines
                               if len(line.get_xdata()) and line.get_marker() == settings.BAND_MARKERS["o"]])
    expected = periods._folding.fold_phase(time, expected_period, True)
    np.testing.assert_allclose(np.sort(observed), np.sort(expected))
    assert len(ax.artists[0].get_texts()) == 4
    assert all(row[key] == value for key, value in original.items())


@pytest.mark.parametrize("in_memory", [False, True])
def test_period_pipeline_passes_adopted_2p_to_both_plotting_paths(tmp_path, monkeypatch, in_memory):
    path = tmp_path / "run.yaml"
    path.write_text(f"""name: binary_plot
output_folder: results
periods:
  max_period_days: 30
  run_bls: false
  run_alias_learning: false
  keep_plot_payloads_in_memory: {str(in_memory).lower()}
  skip_already_plotted: false
  auto_plot_alias_suspects: false
  auto_plot_harmonic_suspects: false
  plot_dpi: 40
""")
    cfg = config.load(path)
    cfg.selected_dir.mkdir(parents=True)
    rng = np.random.default_rng(42)
    time = np.sort(rng.uniform(58000, 58400, 2400))
    angle = 2 * np.pi * time / 14.2
    pd.DataFrame({"MJD": time, "m": 14.5 + 0.5 * np.cos(2 * angle) + 0.22 * np.cos(angle)
                  + rng.normal(0, 0.015, len(time)), "dm": 0.015, "F": "o",
                  "target_GaiaDR3": "9900000000000000001", "RA": 84.0, "Dec": -2.5}).to_csv(
                      cfg.selected_dir / "synthetic__GaiaDR3_9900000000000000001_cleaned.csv", index=False)
    periods_received = []
    plot = periods.plot_best_per_star

    def capture(*args, **kwargs):
        periods_received.append(kwargs.get("source_period_days"))
        return plot(*args, **kwargs)

    monkeypatch.setattr(periods, "plot_best_per_star", capture)
    pipeline.run_periods(cfg)
    adopted = pd.read_csv(cfg.periods_dir / "tables/source_period_recommendations.csv").iloc[0]
    assert adopted.harmonic_status == "2P_supported_by_odd_even_difference"
    assert abs(adopted.recommended_period_days / 14.2 - 1) < 0.01
    assert periods_received == [adopted.recommended_period_days]
