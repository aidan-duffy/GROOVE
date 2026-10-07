"""Shared figure style so every stage's plots look alike.

Stages keep their own `plots.py` (each needs its stage's data structures);
only the look and the saving are shared.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt

# Colour-blind-safe palette (Okabe & Ito), used for filters and categories.
FILTER_COLOURS = {"c": "#56B4E9", "o": "#E69F00"}
ACCENT = "#0072B2"
MUTED = "#999999"
GOOD = "#009E73"
BAD = "#CC79A7"

DEFAULT_DPI = 150
FIGURE_SIZES = {"single": (8, 5), "wide": (12, 5), "panel": (12, 8)}


def use_house_style(dpi: int = DEFAULT_DPI) -> None:
    matplotlib.rcParams.update({
        "figure.dpi": dpi,
        "savefig.dpi": dpi,
        "savefig.bbox": "tight",
        "font.size": 10,
        "axes.titlesize": 11,
        "axes.grid": True,
        "grid.alpha": 0.25,
        "legend.frameon": False,
    })


def save_figure(fig, path: Path, formats=("png",), dpi: int | None = None, close: bool = True) -> list[Path]:
    """Save one figure in each requested format; returns the paths written."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    written = []
    for suffix in formats:
        target = path.with_suffix(f".{suffix.lstrip('.')}")
        fig.savefig(target, dpi=dpi or DEFAULT_DPI)
        written.append(target)
    if close:
        plt.close(fig)
    return written
