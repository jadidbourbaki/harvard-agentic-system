"""
Shared plotting setup for publication-quality figures (e.g. USENIX print).
Apply paper_style() at the start of a script; use save_fig() for consistent output.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt  # type: ignore

# Single-column and double-column widths (inches), common for USENIX/ACM/IEEE.
SINGLE_COLUMN_INCH = 3.5
DOUBLE_COLUMN_INCH = 7.0


def paper_style() -> None:
    plt.rcParams.update({
        "figure.figsize": (SINGLE_COLUMN_INCH, SINGLE_COLUMN_INCH * 0.6),
        "figure.dpi": 100,
        "savefig.dpi": 300,
        "savefig.bbox": "tight",
        "font.size": 9,
        "axes.labelsize": 9,
        "axes.titlesize": 9,
        "xtick.labelsize": 9,
        "ytick.labelsize": 9,
        "legend.fontsize": 9,
        "lines.linewidth": 1.5,
        "lines.markersize": 5,
        "axes.linewidth": 1.0,
        "grid.linewidth": 0.5,
    })


def save_fig(
    path: str | Path,
) -> None:
    """
    Save the current figure for print: PDF (vector) and optionally PNG at high DPI.
    PDF is preferred for submission; PNG is useful for previews and slides.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    base = path.with_suffix("")
    plt.savefig(f"{base}.pdf", bbox_inches="tight")
    plt.savefig(f"{base}.png", dpi=300, bbox_inches="tight")
    plt.close()


PAPER_COLORS = [
    'blue',
    'magenta',
    'green',
    'red',
    'yellow',
]
