#!/usr/bin/env python3
"""
Generate ACM SOSP-style plots for story_finishing experiment results.

Reads JSON from output/story_finishing/ and produces, for each noise value:
1. Turn (1–64) vs TTFT — one figure per k, lines for flush/preserve × SGLang/vLLM
2. Turn (1–64) vs TPOT — one figure per k, lines for flush/preserve × SGLang/vLLM
3. k (tokens per turn) vs TTFT — median/p99 for flush and preserve (per backend)
4. k vs TPOT — median/p99 for flush and preserve (per backend)
5. Noise vs Story Finishing TTFT — one figure per k, X=noise rate, Y=median story TTFT
6. Turn/request index vs Background Noise TTFT — one figure per (noise, k), X=background request index, Y=TTFT (ms)

Figures are sized for ACM double-column (small single-column or half-column).
Filenames may include _flush, _preserve, _sglang, _vllm; backend_type is also
read from experiment_params.backend_type when present.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
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
    "lines.linewidth": 1,
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

        backend_type = (params.get("backend_type") or "sglang").lower()
        if "_vllm" in path.stem.lower():
            backend_type = "vllm"
        elif "_sglang" in path.stem.lower():
            backend_type = "sglang"

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

        rec = {
            "noise": noise,
            "k": k,
            "strategy": strategy,
            "backend_type": backend_type,
            "ttft_per_turn": ttft,
            "tpot_per_turn": tpot,
            "path": str(path),
        }
        if "ttft_background_ms" in data:
            rec["ttft_background_ms"] = list(data["ttft_background_ms"])
        records.append(rec)
    return records


# Order and style for (strategy, backend). Each of the 4 series gets a distinct grayscale color and linestyle for print.
STRATEGY_BACKEND_ORDER = [
    ("flush", "sglang"),
    ("preserve", "sglang"),
    ("flush", "vllm"),
    ("preserve", "vllm"),
]

# Grayscale + linestyle: one per (strategy, backend) for print-friendly, B&W-safe plots.
_SERIES_STYLES = [
    {"color": "0.5", "linestyle": "-"},   # Flush (SGLang): black, solid
    {"color": "0.5", "linestyle": "--"},  # Preserve (SGLang): dark gray, dashed
    {"color": "0", "linestyle": "-"},   # Flush (vLLM): medium gray, dotted
    {"color": "0", "linestyle": ":"},  # Preserve (vLLM): light gray, dash-dot
]


def _series_style(strategy: str, backend_type: str) -> dict[str, Any]:
    """Distinct grayscale color and linestyle per series for printing."""
    key = (strategy, backend_type)
    for i, (s, b) in enumerate(STRATEGY_BACKEND_ORDER):
        if (s, b) == key:
            return dict(_SERIES_STYLES[i])
    return {"color": "0.5", "linestyle": "-"}


def _series_label(strategy: str, backend_type: str) -> str:
    backend_label = "SGLang" if backend_type == "sglang" else "vLLM"
    strat_label = strategy.capitalize()
    return f"{strat_label} ({backend_label})"


def group_by_noise_k_strategy_backend(
    records: list[dict[str, Any]],
) -> dict[float, dict[int, dict[tuple[str, str], list[dict[str, Any]]]]]:
    """Group records by noise -> k -> (strategy, backend_type) -> list of runs."""
    out: dict[float, dict[int, dict[tuple[str, str], list[dict[str, Any]]]]] = {}
    for r in records:
        n = r["noise"]
        k = r["k"]
        key = (r["strategy"], r["backend_type"])
        if n not in out:
            out[n] = {}
        if k not in out[n]:
            out[n][k] = {}
        if key not in out[n][k]:
            out[n][k][key] = []
        out[n][k][key].append(r)
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
    grouped: dict[float, dict[int, dict[tuple[str, str], list[dict[str, Any]]]]],
    out_dir: Path,
) -> None:
    """Turn vs TTFT, one figure per (noise, k), lines for flush/preserve × SGLang/vLLM. Cold-start excluded."""
    _apply_style()
    for noise, by_k in sorted(grouped.items()):
        for k, by_sb in sorted(by_k.items()):
            fig, ax = plt.subplots(figsize=FIG_SMALL)
            turns = np.arange(COLD_START_TURNS + 1, 65, dtype=float)
            for strategy, backend in STRATEGY_BACKEND_ORDER:
                runs = by_sb.get((strategy, backend), [])
                if not runs:
                    continue
                raw = runs[0]["ttft_per_turn"][:64]
                ttft = np.array(raw[COLD_START_TURNS:] if len(raw) > COLD_START_TURNS else raw)
                if len(ttft) < len(turns):
                    ttft = np.resize(ttft, len(turns))
                ax.plot(turns, ttft[: len(turns)], label=_series_label(strategy, backend), **_series_style(strategy, backend))
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
    grouped: dict[float, dict[int, dict[tuple[str, str], list[dict[str, Any]]]]],
    out_dir: Path,
) -> None:
    """Turn vs TPOT, one figure per (noise, k), lines for flush/preserve × SGLang/vLLM. Cold-start excluded."""
    _apply_style()
    for noise, by_k in sorted(grouped.items()):
        for k, by_sb in sorted(by_k.items()):
            fig, ax = plt.subplots(figsize=FIG_SMALL)
            turns = np.arange(COLD_START_TURNS + 1, 65, dtype=float)
            for strategy, backend in STRATEGY_BACKEND_ORDER:
                runs = by_sb.get((strategy, backend), [])
                if not runs:
                    continue
                raw = runs[0]["tpot_per_turn"][:64]
                tpot = np.array(raw[COLD_START_TURNS:] if len(raw) > COLD_START_TURNS else raw)
                if len(tpot) < len(turns):
                    tpot = np.resize(tpot, len(turns))
                ax.plot(turns, tpot[: len(turns)], label=_series_label(strategy, backend), **_series_style(strategy, backend))
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
    grouped: dict[float, dict[int, dict[tuple[str, str], list[dict[str, Any]]]]],
    out_dir: Path,
) -> None:
    """k (x) vs TTFT (y): Median/p99 for Flush/Preserve × SGLang/vLLM. One figure per noise."""
    _apply_style()
    for noise, by_k in sorted(grouped.items()):
        k_vals = sorted(by_k.keys())
        if not k_vals:
            continue
        x = np.array(k_vals, dtype=float)
        fig, ax = plt.subplots(figsize=FIG_TWO_LINES)
        for strategy, backend in STRATEGY_BACKEND_ORDER:
            med_list, p99_list = [], []
            for k in k_vals:
                runs = by_k[k].get((strategy, backend), [])
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
            style = _series_style(strategy, backend)
            lbl = _series_label(strategy, backend)
            ax.plot(x, med_list, "o", color=style["color"], linestyle=style["linestyle"], linewidth=1.5, markersize=4, label=f"Median {lbl}")
            ax.plot(x, p99_list, "s", color=style["color"], linestyle="--", linewidth=1, markersize=3, alpha=0.8, label=f"p99 {lbl}")
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
    grouped: dict[float, dict[int, dict[tuple[str, str], list[dict[str, Any]]]]],
    out_dir: Path,
) -> None:
    """k (x) vs TPOT (y): Median/p99 for Flush/Preserve × SGLang/vLLM. One figure per noise."""
    _apply_style()
    for noise, by_k in sorted(grouped.items()):
        k_vals = sorted(by_k.keys())
        if not k_vals:
            continue
        x = np.array(k_vals, dtype=float)
        fig, ax = plt.subplots(figsize=FIG_TWO_LINES)
        for strategy, backend in STRATEGY_BACKEND_ORDER:
            med_list, p99_list = [], []
            for k in k_vals:
                runs = by_k[k].get((strategy, backend), [])
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
            style = _series_style(strategy, backend)
            lbl = _series_label(strategy, backend)
            ax.plot(x, med_list, "o", color=style["color"], linestyle=style["linestyle"], linewidth=1.5, markersize=4, label=f"Median {lbl}")
            ax.plot(x, p99_list, "s", color=style["color"], linestyle="--", linewidth=1, markersize=3, alpha=0.8, label=f"p99 {lbl}")
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


def plot_noise_vs_avg_background_ttft(
    records: list[dict[str, Any]],
    out_dir: Path,
) -> None:
    """Noise rate (x) vs avg background TTFT (y). One line per (strategy, backend)."""
    has_bg = [r for r in records if r.get("ttft_background_ms")]
    if not has_bg:
        return
    _apply_style()
    by_sb: dict[tuple[str, str], list[tuple[float, float]]] = defaultdict(list)
    for r in has_bg:
        key = (r["strategy"], r["backend_type"])
        by_sb[key].append((r["noise"], float(np.mean(r["ttft_background_ms"]))))
    fig, ax = plt.subplots(figsize=FIG_SMALL)
    for strategy, backend in STRATEGY_BACKEND_ORDER:
        key = (strategy, backend)
        if key not in by_sb:
            continue
        points = by_sb[key]
        by_noise: dict[float, list[float]] = defaultdict(list)
        for n, v in points:
            by_noise[n].append(v)
        x_noise = np.array(sorted(by_noise.keys()), dtype=float)
        y_mean = np.array([np.mean(by_noise[n]) for n in x_noise])
        ax.plot(x_noise, y_mean, label=_series_label(strategy, backend), **_series_style(strategy, backend))
    ax.set_xlabel("Noise rate (req/s)")
    ax.set_ylabel("Avg background TTFT (ms)")
    ax.set_title("Noise vs avg background TTFT")
    ax.legend(loc="best")
    _set_ylim_from_data(ax)
    _clean_axis(ax)
    plt.tight_layout()
    plt.savefig(out_dir / "story_finishing_noise_vs_avg_background_ttft.pdf", **SAVEFIG_KW)
    plt.savefig(out_dir / "story_finishing_noise_vs_avg_background_ttft.png", **SAVEFIG_KW)
    plt.close()
    print("  Saved Noise vs avg background TTFT")


def plot_noise_vs_story_ttft(
    grouped: dict[float, dict[int, dict[tuple[str, str], list[dict[str, Any]]]]],
    out_dir: Path,
) -> None:
    """Noise rate (x) vs median Story Finishing TTFT (y). One figure per k, lines for flush/preserve × SGLang/vLLM."""
    _apply_style()
    all_k = set()
    for by_k in grouped.values():
        all_k.update(by_k.keys())
    for k in sorted(all_k):
        fig, ax = plt.subplots(figsize=FIG_SMALL)
        noise_vals = sorted(grouped.keys())
        for strategy, backend in STRATEGY_BACKEND_ORDER:
            x_noise, y_med = [], []
            for noise in noise_vals:
                by_k = grouped.get(noise, {})
                runs = by_k.get(k, {}).get((strategy, backend), [])
                if not runs:
                    continue
                all_ttft = []
                for r in runs:
                    raw = r["ttft_per_turn"][:64]
                    all_ttft.extend(raw[COLD_START_TURNS:] if len(raw) > COLD_START_TURNS else raw)
                if not all_ttft:
                    continue
                med, _ = _median_and_p99(all_ttft)
                x_noise.append(noise)
                y_med.append(med)
            if x_noise:
                ax.plot(x_noise, y_med, label=_series_label(strategy, backend), **_series_style(strategy, backend))
        ax.set_xlabel("Noise rate (req/s)")
        ax.set_ylabel("Story Finishing TTFT (ms, median)")
        ax.set_title(f"Noise vs Story Finishing TTFT (k={k})")
        ax.legend(loc="best")
        _set_ylim_from_data(ax)
        _clean_axis(ax)
        plt.tight_layout()
        safe = re.sub(r"[^\w\-.]", "_", f"k_{k}")
        plt.savefig(out_dir / f"story_finishing_noise_vs_story_ttft_{safe}.pdf", **SAVEFIG_KW)
        plt.savefig(out_dir / f"story_finishing_noise_vs_story_ttft_{safe}.png", **SAVEFIG_KW)
        plt.close()
        print(f"  Saved Noise vs Story Finishing TTFT k={k}")


def plot_turn_vs_background_ttft(
    grouped: dict[float, dict[int, dict[tuple[str, str], list[dict[str, Any]]]]],
    out_dir: Path,
) -> None:
    """Background request index (x) vs Background Noise TTFT (y). One figure per (noise, k), lines for flush/preserve × SGLang/vLLM."""
    _apply_style()
    for noise, by_k in sorted(grouped.items()):
        for k, by_sb in sorted(by_k.items()):
            has_any = any(
                r.get("ttft_background_ms") for runs in by_sb.values() for r in runs
            )
            if not has_any:
                continue
            fig, ax = plt.subplots(figsize=FIG_SMALL)
            for strategy, backend in STRATEGY_BACKEND_ORDER:
                runs = by_sb.get((strategy, backend), [])
                if not runs:
                    continue
                samples = runs[0].get("ttft_background_ms") or []
                if not samples:
                    continue
                # Downsample if huge for smaller PDFs (plot every nth point, max ~2000)
                max_pts = 2000
                step = max(1, len(samples) // max_pts) if len(samples) > max_pts else 1
                x = np.arange(1, len(samples) + 1, step, dtype=float)
                y = np.array(samples[::step], dtype=float)
                if len(x) > len(y):
                    x = x[: len(y)]
                ax.plot(x, y, label=_series_label(strategy, backend), **_series_style(strategy, backend))
            ax.set_xlabel("Background request index")
            ax.set_ylabel("Background TTFT (ms)")
            ax.set_title(f"Turn / request index vs Background Noise TTFT (noise={noise}, k={k})")
            ax.legend(loc="best")
            _set_ylim_from_data(ax)
            _clean_axis(ax)
            plt.tight_layout()
            safe = re.sub(r"[^\w\-.]", "_", f"noise_{noise}_k_{k}")
            plt.savefig(out_dir / f"story_finishing_turn_vs_background_ttft_{safe}.pdf", **SAVEFIG_KW)
            plt.savefig(out_dir / f"story_finishing_turn_vs_background_ttft_{safe}.png", **SAVEFIG_KW)
            plt.close()
            print(f"  Saved Turn vs Background TTFT noise={noise} k={k}")


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

    grouped = group_by_noise_k_strategy_backend(records)
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
    print("Generating Noise vs Story Finishing TTFT (one per k)...")
    plot_noise_vs_story_ttft(grouped, plots_dir)
    print("Generating Turn / request index vs Background Noise TTFT...")
    plot_turn_vs_background_ttft(grouped, plots_dir)
    if any(r.get("ttft_background_ms") for r in records):
        print("Generating Noise vs avg background TTFT...")
        plot_noise_vs_avg_background_ttft(records, plots_dir)
    print("Done. Plots saved to", plots_dir)


if __name__ == "__main__":
    main()
