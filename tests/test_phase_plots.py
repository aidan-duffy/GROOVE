"""Phase display changes retain every plotted sample and its band marker."""

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest

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
        assert {line.get_marker() for line in ax.lines} >= {"o", "s"}
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
