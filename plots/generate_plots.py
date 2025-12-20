#!/usr/bin/env python3
"""Generate publication-quality plots from experiment results."""

import json
import logging
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt

# Use non-interactive backend
matplotlib.use("Agg")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# NeurIPS/NSDI style settings
plt.style.use("seaborn-v0_8-paper")
matplotlib.rcParams.update(
    {
        "font.size": 10,
        "axes.labelsize": 11,
        "axes.titlesize": 12,
        "xtick.labelsize": 10,
        "ytick.labelsize": 10,
        "legend.fontsize": 9,
        "figure.titlesize": 13,
        "font.family": "serif",
        "font.serif": [
            "Times",
            "Palatino",
            "New Century Schoolbook",
            "Bookman",
            "Computer Modern Roman",
        ],
        "text.usetex": True,  # Set to True if you have LaTeX installed
        "figure.dpi": 300,
        "savefig.dpi": 300,
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.1,
    }
)


def load_summary(summary_path: Path) -> dict:
    """Load summary.json file."""
    with open(summary_path, "r") as f:
        return json.load(f)


def load_result(result_path: Path) -> dict:
    """Load individual result JSON file."""
    with open(result_path, "r") as f:
        return json.load(f)


def plot_ttft_vs_k(summary: dict, output_dir: Path):
    """Plot TTFT vs k for average, median (p50), and p99."""
    results = summary["results"]
    k_values = sorted([r["k"] for r in results])

    # Create a dict for quick lookup
    results_by_k = {r["k"]: r for r in results}

    avg_ttft = [results_by_k[k]["avg_ttft"] for k in k_values]
    p50_ttft = [results_by_k[k]["ttft_p50"] for k in k_values]
    p99_ttft = [results_by_k[k]["ttft_p99"] for k in k_values]

    fig, ax = plt.subplots(figsize=(6, 4))

    ax.plot(k_values, avg_ttft, marker="o", label="Average", linewidth=2, markersize=6)
    ax.plot(
        k_values, p50_ttft, marker="s", label="Median (p50)", linewidth=2, markersize=6
    )
    ax.plot(k_values, p99_ttft, marker="^", label="p99", linewidth=2, markersize=6)

    ax.set_xlabel("k (tokens per turn)", fontweight="bold")
    ax.set_ylabel("TTFT (seconds)", fontweight="bold")
    ax.set_title("Time To First Token vs k", fontweight="bold")
    ax.legend(frameon=True, fancybox=True, shadow=True)
    ax.grid(True, alpha=0.3, linestyle="--")
    ax.set_xscale("log", base=2)

    plt.tight_layout()
    plt.savefig(output_dir / "ttft_vs_k.pdf")
    plt.savefig(output_dir / "ttft_vs_k.png")
    plt.close()
    logger.info(f"Saved: {output_dir / 'ttft_vs_k.pdf'}")


def plot_tpot_vs_k(summary: dict, output_dir: Path):
    """Plot TPOT vs k for average, median (p50), and p99."""
    results = summary["results"]
    k_values = sorted([r["k"] for r in results])

    # Create a dict for quick lookup
    results_by_k = {r["k"]: r for r in results}

    avg_tpot = [results_by_k[k]["avg_tpot"] for k in k_values]
    p50_tpot = [results_by_k[k]["tpot_p50"] for k in k_values]
    p99_tpot = [results_by_k[k]["tpot_p99"] for k in k_values]

    fig, ax = plt.subplots(figsize=(6, 4))

    ax.plot(k_values, avg_tpot, marker="o", label="Average", linewidth=2, markersize=6)
    ax.plot(
        k_values, p50_tpot, marker="s", label="Median (p50)", linewidth=2, markersize=6
    )
    ax.plot(k_values, p99_tpot, marker="^", label="p99", linewidth=2, markersize=6)

    ax.set_xlabel("k (tokens per turn)", fontweight="bold")
    ax.set_ylabel("TPOT (seconds)", fontweight="bold")
    ax.set_title("Time Per Output Token vs k", fontweight="bold")
    ax.legend(frameon=True, fancybox=True, shadow=True)
    ax.grid(True, alpha=0.3, linestyle="--")
    ax.set_xscale("log", base=2)

    plt.tight_layout()
    plt.savefig(output_dir / "tpot_vs_k.pdf")
    plt.savefig(output_dir / "tpot_vs_k.png")
    plt.close()
    logger.info(f"Saved: {output_dir / 'tpot_vs_k.pdf'}")


def plot_ttft_vs_turn(result: dict, k: int, output_dir: Path):
    """Plot TTFT vs Turn for a given k value (average, median, p99)."""
    per_turn = result["metrics"]["per_turn_metrics"]
    turns = [m["turn"] for m in per_turn]
    avg_ttft = [m["ttft"] for m in per_turn]
    p50_ttft = [m["ttft_p50"] for m in per_turn]
    p99_ttft = [m["ttft_p99"] for m in per_turn]

    fig, ax = plt.subplots(figsize=(8, 5))

    ax.plot(
        turns,
        avg_ttft,
        marker="o",
        label="Average",
        linewidth=1.5,
        markersize=4,
        alpha=0.7,
    )
    ax.plot(
        turns,
        p50_ttft,
        marker="s",
        label="Median (p50)",
        linewidth=1.5,
        markersize=4,
        alpha=0.7,
    )
    ax.plot(
        turns, p99_ttft, marker="^", label="p99", linewidth=1.5, markersize=4, alpha=0.7
    )

    ax.set_xlabel("Turn", fontweight="bold")
    ax.set_ylabel("TTFT (seconds)", fontweight="bold")
    ax.set_title(f"Time To First Token vs Turn (k={k})", fontweight="bold")
    ax.legend(frameon=True, fancybox=True, shadow=True)
    ax.grid(True, alpha=0.3, linestyle="--")

    plt.tight_layout()
    plt.savefig(output_dir / f"ttft_vs_turn_k{k}.pdf")
    plt.savefig(output_dir / f"ttft_vs_turn_k{k}.png")
    plt.close()
    logger.info(f"Saved: {output_dir / f'ttft_vs_turn_k{k}.pdf'}")


def plot_tpot_vs_turn(result: dict, k: int, output_dir: Path):
    """Plot TPOT vs Turn for a given k value (average, median, p99)."""
    per_turn = result["metrics"]["per_turn_metrics"]
    turns = [m["turn"] for m in per_turn]
    avg_tpot = [m["tpot"] for m in per_turn]
    p50_tpot = [m["tpot_p50"] for m in per_turn]
    p99_tpot = [m["tpot_p99"] for m in per_turn]

    fig, ax = plt.subplots(figsize=(8, 5))

    ax.plot(
        turns,
        avg_tpot,
        marker="o",
        label="Average",
        linewidth=1.5,
        markersize=4,
        alpha=0.7,
    )
    ax.plot(
        turns,
        p50_tpot,
        marker="s",
        label="Median (p50)",
        linewidth=1.5,
        markersize=4,
        alpha=0.7,
    )
    ax.plot(
        turns, p99_tpot, marker="^", label="p99", linewidth=1.5, markersize=4, alpha=0.7
    )

    ax.set_xlabel("Turn", fontweight="bold")
    ax.set_ylabel("TPOT (seconds)", fontweight="bold")
    ax.set_title(f"Time Per Output Token vs Turn (k={k})", fontweight="bold")
    ax.legend(frameon=True, fancybox=True, shadow=True)
    ax.grid(True, alpha=0.3, linestyle="--")

    plt.tight_layout()
    plt.savefig(output_dir / f"tpot_vs_turn_k{k}.pdf")
    plt.savefig(output_dir / f"tpot_vs_turn_k{k}.png")
    plt.close()
    logger.info(f"Saved: {output_dir / f'tpot_vs_turn_k{k}.pdf'}")


def main():
    """Generate all plots from experiment results."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate plots from experiment results"
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path("../experiments/output"),
        help="Directory containing experiment results (default: ../experiments/output)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output"),
        help="Directory to save plots (default: output)",
    )

    args = parser.parse_args()

    # Create output directory
    args.output_dir.mkdir(parents=True, exist_ok=True)

    # Load summary
    summary_path = args.input_dir / "summary.json"
    if not summary_path.exists():
        logger.error(f"Summary file not found: {summary_path}")
        return

    summary = load_summary(summary_path)
    logger.info(f"Loaded summary with {summary['experiments']} experiments")

    # Generate aggregate plots (TTFT/TPOT vs k)
    logger.info("Generating aggregate plots...")
    plot_ttft_vs_k(summary, args.output_dir)
    plot_tpot_vs_k(summary, args.output_dir)

    # Generate per-turn plots for each k value
    logger.info("Generating per-turn plots...")
    for result_entry in summary["results"]:
        k = result_entry["k"]
        result_file = args.input_dir / result_entry["file"]

        if not result_file.exists():
            logger.warning(f"Result file not found: {result_file}, skipping k={k}")
            continue

        result = load_result(result_file)
        plot_ttft_vs_turn(result, k, args.output_dir)
        plot_tpot_vs_turn(result, k, args.output_dir)

    logger.info(f"\nAll plots saved to: {args.output_dir}")
    logger.info("Generated plots:")
    logger.info("  - ttft_vs_k.pdf/png")
    logger.info("  - tpot_vs_k.pdf/png")
    logger.info("  - ttft_vs_turn_k{k}.pdf/png (for each k)")
    logger.info("  - tpot_vs_turn_k{k}.pdf/png (for each k)")


if __name__ == "__main__":
    main()
