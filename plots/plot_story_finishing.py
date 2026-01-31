#!/usr/bin/env python3
"""
Generate ACM SOSP-style plots for story_finishing experiment results.

Reads JSON from output/story_finishing/ and produces, for each noise value:
1. Turn (1–64) vs TTFT — one figure per k, lines for flush and preserve
2. Turn (1–64) vs TPOT — one figure per k, lines for flush and preserve
3. k (tokens per turn) vs TTFT — median/p99 for flush and preserve
4. k vs TPOT — median/p99 for flush and preserve

Figures are sized for ACM double-column (small single-column or half-column).
To get both flush and preserve, run the grid twice with different cache strategy
and different output filenames (e.g. suffix _flush.json and _preserve.json),
or set CACHE_STRATEGY and write to a path that includes the strategy.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np

# ACM double-column: single column width ~3.33 in; use small plots for inline figures
COLUMN_WIDTH_IN = 3.33
FIG_SMALL = (COLUMN_WIDTH_IN, 2.0)  # one small plot
FIG_TWO_LINES = (COLUMN_WIDTH_IN, 2.2)

SOSP_SMALL = {
    "figure.figsize": FIG_SMALL,
    "font.size": 8,
    "font.family": "sans-serif",
    "font.sans-serif": ["Arial", "DejaVu Sans", "Helvetica", "Liberation Sans"],
    "axes.labelsize": 9,
    "axes.titlesize": 9,
    "xtick.labelsize": 8,
    "ytick.labelsize": 8,
    "legend.fontsize": 7,
    "legend.frameon": False,
    "lines.linewidth": 1.5,
    "lines.markersize": 4,
    "axes.linewidth": 0.8,
    "xtick.major.width": 0.8,
    "ytick.major.width": 0.8,
    "xtick.major.size": 3,
    "ytick.major.size": 3,
    "savefig.dpi": 300,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.05,
}

SAVEFIG_KW = {"dpi": 300, "bbox_inches": "tight", "pad_inches": 0.05}

# Exclude first N turns as cold start (cache warmup, etc.)
COLD_START_TURNS = 1


def load_story_finishing_results(output_dir: Path) -> list[dict[str, Any]]:
    """Load all story_finishing JSON files and return list of records with parsed fields."""
    records = []
    for path in sorted(output_dir.glob("*.json")):
        if not path.is_file():
            continue
        try:
            with open(path, "r") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"Warning: skip {path}: {e}")
            continue

        params = data.get("experiment_params") or {}
        strategy = (params.get("cache_strategy") or "flush").lower()
        # Optional: infer strategy from filename (e.g. ..._preserve.json)
        if "_preserve" in path.stem.lower():
            strategy = "preserve"
        elif "_flush" in path.stem.lower():
            strategy = "flush"

        noise = float(params.get("noise_rate", 0))
        k = int(data.get("k", params.get("k", 0)))
        ttft = data.get("ttft_per_turn") or []
        tpot = data.get("tpot_per_turn") or []

        # Trim/pad to 64 turns
        turns = min(64, len(ttft) or 0, len(tpot) or 0)
        if not turns and (ttft or tpot):
            turns = min(64, len(ttft) or 64, len(tpot) or 64)
        if not turns:
            turns = 64
        ttft = (ttft or [0.0] * 64)[:turns]
        tpot = (tpot or [0.0] * 64)[:turns]
        if len(ttft) < turns:
            ttft = ttft + [0.0] * (turns - len(ttft))
        if len(tpot) < turns:
            tpot = tpot + [0.0] * (turns - len(tpot))

        records.append({
            "noise": noise,
            "k": k,
            "strategy": strategy,
            "ttft_per_turn": ttft,
            "tpot_per_turn": tpot,
            "path": str(path),
        })
    return records


def group_by_noise_k_strategy(
    records: list[dict[str, Any]],
) -> dict[float, dict[int, dict[str, list[dict[str, Any]]]]]:
    """Group records by noise -> k -> strategy -> list of runs (usually one)."""
    out: dict[float, dict[int, dict[str, list[dict[str, Any]]]]] = {}
    for r in records:
        n = r["noise"]
        k = r["k"]
        s = r["strategy"]
        if n not in out:
            out[n] = {}
        if k not in out[n]:
            out[n][k] = {}
        if s not in out[n][k]:
            out[n][k][s] = []
        out[n][k][s].append(r)
    return out


def _apply_style() -> None:
    plt.style.use("default")
    plt.rcParams.update(SOSP_SMALL)


def _clean_axis(ax: plt.Axes) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.set_axisbelow(True)


def _set_ylim_from_data(ax: plt.Axes, margin: float = 1.08, min_top: float = 1.0) -> None:
    """Set ylim to (0, data_max * margin) so the data is visible; min_top only when all data is zero."""
    ymax = 0.0
    for line in ax.get_lines():
        yd = np.asarray(line.get_ydata(), dtype=float)
        if yd.size and np.any(np.isfinite(yd)):
            m = np.nanmax(yd)
            if np.isfinite(m):
                ymax = max(ymax, m)
    # Scale to data so small values (e.g. TPOT < 1 ms) are visible; min_top only for all-zero
    top = ymax * margin if ymax > 0 else min_top
    ax.set_ylim(0, top)


def plot_turn_vs_ttft(
    grouped: dict[float, dict[int, dict[str, list[dict[str, Any]]]]],
    out_dir: Path,
) -> None:
    """Turn vs TTFT, one figure per (noise, k), lines for flush and preserve. Cold-start turns excluded."""
    _apply_style()
    for noise, by_k in sorted(grouped.items()):
        for k, by_strategy in sorted(by_k.items()):
            fig, ax = plt.subplots(figsize=FIG_SMALL)
            # Exclude cold-start turns from plot
            turns = np.arange(COLD_START_TURNS + 1, 65, dtype=float)
            for strategy, label, style in [
                ("flush", "Flush", {"color": "C0", "linestyle": "-"}),
                ("preserve", "Preserve", {"color": "C1", "linestyle": "-"}),
            ]:
                runs = by_strategy.get(strategy, [])
                if not runs:
                    continue
                raw = runs[0]["ttft_per_turn"][:64]
                ttft = np.array(raw[COLD_START_TURNS:] if len(raw) > COLD_START_TURNS else raw)
                if len(ttft) < len(turns):
                    ttft = np.resize(ttft, len(turns))
                ax.plot(turns, ttft[: len(turns)], label=label, **style)
            ax.set_xlim(COLD_START_TURNS + 1, 64)
            _set_ylim_from_data(ax)
            ax.set_xlabel("Turn")
            ax.set_ylabel("TTFT (ms)")
            ax.set_title(f"Noise={noise}, k={k}")
            ax.legend(loc="best")
            _clean_axis(ax)
            plt.tight_layout()
            safe = re.sub(r"[^\w\-.]", "_", f"noise_{noise}_k_{k}")
            plt.savefig(out_dir / f"story_finishing_ttft_vs_turn_{safe}.pdf", **SAVEFIG_KW)
            plt.savefig(out_dir / f"story_finishing_ttft_vs_turn_{safe}.png", **SAVEFIG_KW)
            plt.close()
            print(f"  Saved TTFT vs turn noise={noise} k={k}")


def plot_turn_vs_tpot(
    grouped: dict[float, dict[int, dict[str, list[dict[str, Any]]]]],
    out_dir: Path,
) -> None:
    """Turn vs TPOT, one figure per (noise, k), lines for flush and preserve. Cold-start turns excluded."""
    _apply_style()
    for noise, by_k in sorted(grouped.items()):
        for k, by_strategy in sorted(by_k.items()):
            fig, ax = plt.subplots(figsize=FIG_SMALL)
            turns = np.arange(COLD_START_TURNS + 1, 65, dtype=float)
            for strategy, label, style in [
                ("flush", "Flush", {"color": "C0", "linestyle": "-"}),
                ("preserve", "Preserve", {"color": "C1", "linestyle": "-"}),
            ]:
                runs = by_strategy.get(strategy, [])
                if not runs:
                    continue
                raw = runs[0]["tpot_per_turn"][:64]
                tpot = np.array(raw[COLD_START_TURNS:] if len(raw) > COLD_START_TURNS else raw)
                if len(tpot) < len(turns):
                    tpot = np.resize(tpot, len(turns))
                ax.plot(turns, tpot[: len(turns)], label=label, **style)
            ax.set_xlim(COLD_START_TURNS + 1, 64)
            _set_ylim_from_data(ax)
            ax.set_xlabel("Turn")
            ax.set_ylabel("TPOT (ms)")
            ax.set_title(f"Noise={noise}, k={k}")
            ax.legend(loc="best")
            _clean_axis(ax)
            plt.tight_layout()
            safe = re.sub(r"[^\w\-.]", "_", f"noise_{noise}_k_{k}")
            plt.savefig(out_dir / f"story_finishing_tpot_vs_turn_{safe}.pdf", **SAVEFIG_KW)
            plt.savefig(out_dir / f"story_finishing_tpot_vs_turn_{safe}.png", **SAVEFIG_KW)
            plt.close()
            print(f"  Saved TPOT vs turn noise={noise} k={k}")


def _median_and_p99(values: list[float]) -> tuple[float, float]:
    a = np.array(values, dtype=float)
    a = a[np.isfinite(a)]
    if a.size == 0:
        return 0.0, 0.0
    return float(np.median(a)), float(np.percentile(a, 99))


def plot_k_vs_ttft_summary(
    grouped: dict[float, dict[int, dict[str, list[dict[str, Any]]]]],
    out_dir: Path,
) -> None:
    """k (x) vs TTFT (y): Median Flush, p99 Flush, Median Preserve, p99 Preserve. One figure per noise."""
    _apply_style()
    for noise, by_k in sorted(grouped.items()):
        k_vals = sorted(by_k.keys())
        if not k_vals:
            continue
        # Collect median and p99 per (k, strategy)
        flush_med, flush_p99 = [], []
        preserve_med, preserve_p99 = [], []
        for k in k_vals:
            by_strategy = by_k[k]
            for strategy, med_list, p99_list in [
                ("flush", flush_med, flush_p99),
                ("preserve", preserve_med, preserve_p99),
            ]:
                runs = by_strategy.get(strategy, [])
                if not runs:
                    med_list.append(np.nan)
                    p99_list.append(np.nan)
                    continue
                all_ttft = []
                for r in runs:
                    raw = r["ttft_per_turn"][:64]
                    all_ttft.extend(raw[COLD_START_TURNS:] if len(raw) > COLD_START_TURNS else raw)
                med, p99 = _median_and_p99(all_ttft)
                med_list.append(med)
                p99_list.append(p99)

        fig, ax = plt.subplots(figsize=FIG_TWO_LINES)
        x = np.array(k_vals, dtype=float)
        ax.plot(x, flush_med, "o-", color="C0", linewidth=1.5, markersize=4, label="Median Flush")
        ax.plot(x, flush_p99, "s--", color="C0", linewidth=1, markersize=3, alpha=0.8, label="p99 Flush")
        ax.plot(x, preserve_med, "o-", color="C1", linewidth=1.5, markersize=4, label="Median Preserve")
        ax.plot(x, preserve_p99, "s--", color="C1", linewidth=1, markersize=3, alpha=0.8, label="p99 Preserve")
        ax.set_xlabel("Tokens per turn (k)")
        ax.set_ylabel("TTFT (ms)")
        ax.set_title(f"Noise = {noise}")
        ax.legend(loc="best")
        _set_ylim_from_data(ax)
        _clean_axis(ax)
        plt.tight_layout()
        safe = re.sub(r"[^\w\-.]", "_", f"noise_{noise}")
        plt.savefig(out_dir / f"story_finishing_ttft_vs_k_{safe}.pdf", **SAVEFIG_KW)
        plt.savefig(out_dir / f"story_finishing_ttft_vs_k_{safe}.png", **SAVEFIG_KW)
        plt.close()
        print(f"  Saved TTFT vs k noise={noise}")


def plot_k_vs_tpot_summary(
    grouped: dict[float, dict[int, dict[str, list[dict[str, Any]]]]],
    out_dir: Path,
) -> None:
    """k (x) vs TPOT (y): Median Flush, p99 Flush, Median Preserve, p99 Preserve. One figure per noise."""
    _apply_style()
    for noise, by_k in sorted(grouped.items()):
        k_vals = sorted(by_k.keys())
        if not k_vals:
            continue
        flush_med, flush_p99 = [], []
        preserve_med, preserve_p99 = [], []
        for k in k_vals:
            by_strategy = by_k[k]
            for strategy, med_list, p99_list in [
                ("flush", flush_med, flush_p99),
                ("preserve", preserve_med, preserve_p99),
            ]:
                runs = by_strategy.get(strategy, [])
                if not runs:
                    med_list.append(np.nan)
                    p99_list.append(np.nan)
                    continue
                all_tpot = []
                for r in runs:
                    raw = r["tpot_per_turn"][:64]
                    all_tpot.extend(raw[COLD_START_TURNS:] if len(raw) > COLD_START_TURNS else raw)
                med, p99 = _median_and_p99(all_tpot)
                med_list.append(med)
                p99_list.append(p99)

        fig, ax = plt.subplots(figsize=FIG_TWO_LINES)
        x = np.array(k_vals, dtype=float)
        ax.plot(x, flush_med, "o-", color="C0", linewidth=1.5, markersize=4, label="Median Flush")
        ax.plot(x, flush_p99, "s--", color="C0", linewidth=1, markersize=3, alpha=0.8, label="p99 Flush")
        ax.plot(x, preserve_med, "o-", color="C1", linewidth=1.5, markersize=4, label="Median Preserve")
        ax.plot(x, preserve_p99, "s--", color="C1", linewidth=1, markersize=3, alpha=0.8, label="p99 Preserve")
        ax.set_xlabel("Tokens per turn (k)")
        ax.set_ylabel("TPOT (ms)")
        ax.set_title(f"Noise = {noise}")
        ax.legend(loc="best")
        _set_ylim_from_data(ax)
        _clean_axis(ax)
        plt.tight_layout()
        safe = re.sub(r"[^\w\-.]", "_", f"noise_{noise}")
        plt.savefig(out_dir / f"story_finishing_tpot_vs_k_{safe}.pdf", **SAVEFIG_KW)
        plt.savefig(out_dir / f"story_finishing_tpot_vs_k_{safe}.png", **SAVEFIG_KW)
        plt.close()
        print(f"  Saved TPOT vs k noise={noise}")


def main() -> None:
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent
    output_dir = project_root / "output" / "story_finishing"
    plots_dir = script_dir

    if not output_dir.exists():
        print(f"Error: output directory not found: {output_dir}")
        return

    print("Loading story_finishing results...")
    records = load_story_finishing_results(output_dir)
    if not records:
        print("No JSON records found.")
        return

    grouped = group_by_noise_k_strategy(records)
    n_noise = len(grouped)
    n_k = sum(len(by_k) for by_k in grouped.values())
    print(f"Loaded {len(records)} runs, {n_noise} noise value(s), {n_k} (noise,k) configs.")

    print("Generating Turn vs TTFT figures (one per k per noise)...")
    plot_turn_vs_ttft(grouped, plots_dir)
    print("Generating Turn vs TPOT figures (one per k per noise)...")
    plot_turn_vs_tpot(grouped, plots_dir)
    print("Generating k vs TTFT summary (median/p99) per noise...")
    plot_k_vs_ttft_summary(grouped, plots_dir)
    print("Generating k vs TPOT summary (median/p99) per noise...")
    plot_k_vs_tpot_summary(grouped, plots_dir)
    print("Done. Plots saved to", plots_dir)


if __name__ == "__main__":
    main()
