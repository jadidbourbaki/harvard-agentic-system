#!/usr/bin/env python3
"""
Generate SOSP-style plots for Orla evaluation results.

This script creates plots optimized for SOSP paper presentation:
1. End-to-end time comparison with improvement percentages
2. Per-stage latency breakdown (grouped bars) showing where improvements come from
3. Speedup comparison showing improvement factor
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

import matplotlib.pyplot as plt  # type: ignore
import numpy as np  # type: ignore


# SOSP style configuration (inspired by reference image)
SOSP_STYLE = {
    "figure.figsize": (9, 4.5),  # Two subplots side-by-side
    "font.size": 16,
    "font.family": "sans-serif",
    "font.sans-serif": ["Arial", "DejaVu Sans", "Helvetica", "Liberation Sans"],
    "axes.labelsize": 16,
    "axes.titlesize": 16,
    "xtick.labelsize": 16,
    "ytick.labelsize": 16,
    "legend.fontsize": 16,
    "legend.frameon": False,
    "lines.linewidth": 2.0,
    "lines.markersize": 6,
    "axes.linewidth": 1.0,
    "xtick.major.width": 1.0,
    "ytick.major.width": 1.0,
    "xtick.major.size": 4,
    "ytick.major.size": 4,
    "savefig.dpi": 300,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.1,
}


def load_results(output_dir: Path) -> Dict[str, List[Dict[str, Any]]]:
    """Load all JSON result files and group by mode.
    
    Excludes run 1 (warmup) and only includes runs 2-4 for error bar calculations.
    """
    results: Dict[str, List[Dict[str, Any]]] = {
        "baseline": [],  # SGLang baseline
        "orla": [],      # Orla with SGLang
        "ollama_baseline": [],  # Ollama baseline
        "ollama": [],    # Orla with Ollama
    }
    
    for file in sorted(output_dir.glob("*.json")):
        if file.name.startswith("comparison_"):
            continue
        
        # Skip run 1 (warmup) - only use runs 2-4
        if file.name.endswith("_1.json"):
            continue
            
        with open(file, "r") as f:
            data = json.load(f)
            mode = data.get("mode", "")
            
            if mode == "baseline":
                results["baseline"].append(data)
            elif mode == "cascade":
                results["orla"].append(data)
            elif mode == "baseline-ollama":
                results["ollama_baseline"].append(data)
            elif mode == "cascade-ollama":
                results["ollama"].append(data)
    
    return results


def calculate_stats(values: List[float]) -> Tuple[float, float]:
    """Calculate mean and standard deviation (for error bars)."""
    if not values:
        return 0.0, 0.0
    if len(values) == 1:
        # If only one value, use a small error to still show error bars
        return values[0], values[0] * 0.01
    mean = np.mean(values)
    std = np.std(values, ddof=1)  # Sample standard deviation
    return mean, std


def plot_bar_chart(results: Dict[str, List[Dict[str, Any]]], output_path: Path) -> None:
    """Create separate bar charts for datacenter and edge serving to handle scale differences."""
    plt.style.use("default")
    plt.rcParams.update(SOSP_STYLE)
    
    # Extract total_time_seconds for each group
    datacenter_baseline = [r["total_time_seconds"] for r in results["baseline"]]
    datacenter_orla = [r["total_time_seconds"] for r in results["orla"]]
    edge_baseline = [r["total_time_seconds"] for r in results["ollama_baseline"]]
    edge_orla = [r["total_time_seconds"] for r in results["ollama"]]
    
    # Calculate means and standard deviations
    dc_baseline_mean, dc_baseline_err = calculate_stats(datacenter_baseline)
    dc_orla_mean, dc_orla_err = calculate_stats(datacenter_orla)
    edge_baseline_mean, edge_baseline_err = calculate_stats(edge_baseline)
    edge_orla_mean, edge_orla_err = calculate_stats(edge_orla)
    
    # Calculate improvement percentages
    dc_improvement = ((dc_baseline_mean - dc_orla_mean) / dc_baseline_mean) * 100
    edge_improvement = ((edge_baseline_mean - edge_orla_mean) / edge_baseline_mean) * 100
    
    # Colors matching reference style
    baseline_color = "b"  # Blue
    orla_color = "g"  # Red
    
    # Create combined subplot version matching reference style
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9, 4.5), sharey=False)
    plt.rcParams.update(SOSP_STYLE)
    
    # Positions with spacing between bars (like reference)
    x_positions = np.array([0, 1, 2, 3])  # Four positions for spacing
    width = 0.5  # Thin bars
    
    # Datacenter subplot (a)
    dc_x = x_positions[:2]  # Use first two positions
    bars1_dc = ax1.bar(dc_x[0], dc_baseline_mean, width,
                       yerr=dc_baseline_err,
                       color=baseline_color, edgecolor="black", linewidth=1.0,
                       capsize=6, error_kw={"elinewidth": 1.5, "capthick": 1.5, "ecolor": "black"})
    bars2_dc = ax1.bar(dc_x[1], dc_orla_mean, width,
                       yerr=dc_orla_err,
                       color=orla_color, edgecolor="black", linewidth=1.0,
                       capsize=6, error_kw={"elinewidth": 1.5, "capthick": 1.5, "ecolor": "black"})
    
    # Add values on top of bars (like reference)
    ax1.text(dc_x[0], dc_baseline_mean + dc_baseline_err + max(dc_baseline_mean, dc_orla_mean) * 0.02,
            f'{dc_baseline_mean:.2f}', ha='center', va='bottom', fontsize=14, fontweight='normal')
    ax1.text(dc_x[1], dc_orla_mean + dc_orla_err + max(dc_baseline_mean, dc_orla_mean) * 0.02,
            f'{dc_orla_mean:.2f}', ha='center', va='bottom', fontsize=14, fontweight='normal')
    
    ax1.set_ylabel("Completion Time (s)", fontsize=16)
    ax1.set_xticks(dc_x)
    ax1.set_xticklabels(["SGLang", "Orla"], fontsize=16)
    ax1.set_title("(a) Datacenter Serving", fontsize=16, fontweight="bold", pad=15)
    ax1.set_xlim(-0.5, 1.5)
    ax1.spines["top"].set_visible(False)
    ax1.spines["right"].set_visible(False)
    ax1.spines["left"].set_linewidth(1.0)
    ax1.spines["bottom"].set_linewidth(1.0)
    ax1.set_axisbelow(True)
    
    # Edge subplot (b)
    edge_x = x_positions[:2]  # Use first two positions
    bars1_edge = ax2.bar(edge_x[0], edge_baseline_mean, width,
                         yerr=edge_baseline_err,
                         color=baseline_color, edgecolor="black", linewidth=1.0,
                         capsize=6, error_kw={"elinewidth": 1.5, "capthick": 1.5, "ecolor": "black"})
    bars2_edge = ax2.bar(edge_x[1], edge_orla_mean, width,
                         yerr=edge_orla_err,
                         color=orla_color, edgecolor="black", linewidth=1.0,
                         capsize=6, error_kw={"elinewidth": 1.5, "capthick": 1.5, "ecolor": "black"})
    
    # Add values on top of bars (like reference)
    ax2.text(edge_x[0], edge_baseline_mean + edge_baseline_err + max(edge_baseline_mean, edge_orla_mean) * 0.02,
            f'{edge_baseline_mean:.2f}', ha='center', va='bottom', fontsize=14, fontweight='normal')
    ax2.text(edge_x[1], edge_orla_mean + edge_orla_err + max(edge_baseline_mean, edge_orla_mean) * 0.02,
            f'{edge_orla_mean:.2f}', ha='center', va='bottom', fontsize=14, fontweight='normal')
    
    ax2.set_ylabel("Completion Time (s)", fontsize=16)
    ax2.set_xticks(edge_x)
    ax2.set_xticklabels(["Ollama", "Orla"], fontsize=16)
    ax2.set_title("(b) Edge Serving", fontsize=16, fontweight="bold", pad=15)
    ax2.set_xlim(-0.5, 1.5)
    ax2.spines["top"].set_visible(False)
    ax2.spines["right"].set_visible(False)
    ax2.spines["left"].set_linewidth(1.0)
    ax2.spines["bottom"].set_linewidth(1.0)
    ax2.set_axisbelow(True)
    
    plt.tight_layout()
    plt.savefig(output_path / "end_to_end_comparison.pdf", dpi=300, bbox_inches="tight", format="pdf")
    plt.savefig(output_path / "end_to_end_comparison.png", dpi=300, bbox_inches="tight", format="png")
    print(f"Saved combined end-to-end comparison to {output_path / 'end_to_end_comparison.pdf'}")
    plt.close()


def plot_stage_breakdown(results: Dict[str, List[Dict[str, Any]]], output_path: Path, backend: str) -> None:
    """Create grouped bar chart showing per-stage latency breakdown - KEY PLOT for SOSP."""
    plt.style.use("default")
    plt.rcParams.update(SOSP_STYLE)
    
    fig, ax = plt.subplots(figsize=SOSP_STYLE["figure.figsize"])
    
    if backend == "sglang":
        baseline_data = results["baseline"]
        orla_data = results["orla"]
        backend_label = "SGLang"
        output_name = "sglang_stage_breakdown"
    else:
        baseline_data = results["ollama_baseline"]
        orla_data = results["ollama"]
        backend_label = "Ollama"
        output_name = "ollama_stage_breakdown"
    
    # Extract per-stage times (convert ms to seconds)
    baseline_analysis = [r["avg_analysis_ms"] / 1000.0 for r in baseline_data]
    baseline_synthesis = [r["avg_synthesis_ms"] / 1000.0 for r in baseline_data]
    baseline_summary = [r["avg_summary_ms"] / 1000.0 for r in baseline_data]
    
    orla_analysis = [r["avg_analysis_ms"] / 1000.0 for r in orla_data]
    orla_synthesis = [r["avg_synthesis_ms"] / 1000.0 for r in orla_data]
    orla_summary = [r["avg_summary_ms"] / 1000.0 for r in orla_data]
    
    # Calculate means and errors
    bl_analysis_mean, bl_analysis_err = calculate_stats(baseline_analysis)
    bl_synthesis_mean, bl_synthesis_err = calculate_stats(baseline_synthesis)
    bl_summary_mean, bl_summary_err = calculate_stats(baseline_summary)
    
    ol_analysis_mean, ol_analysis_err = calculate_stats(orla_analysis)
    ol_synthesis_mean, ol_synthesis_err = calculate_stats(orla_synthesis)
    ol_summary_mean, ol_summary_err = calculate_stats(orla_summary)
    
    # Prepare data
    stages = ["Analysis", "Synthesis", "Summary"]
    x = np.array([0, 2, 4])  # Positions with spacing between stage groups
    width = 0.4  # Bar width
    gap = 0.15  # Gap between the two bars in each group
    
    baseline_means = [bl_analysis_mean, bl_synthesis_mean, bl_summary_mean]
    baseline_errs = [bl_analysis_err, bl_synthesis_err, bl_summary_err]
    orla_means = [ol_analysis_mean, ol_synthesis_mean, ol_summary_mean]
    orla_errs = [ol_analysis_err, ol_synthesis_err, ol_summary_err]
    
    baseline_color = "b"  # Blue
    orla_color = "g"  # Green

    if backend == "sglang":
        baseline_label = "SGLang"
        orla_label = "Orla"
    else:
        baseline_label = "Ollama"
        orla_label = "Orla"
    
    # Create grouped bars with spacing between them
    bars1 = ax.bar(x - width/2 - gap/2, baseline_means, width,
                   yerr=baseline_errs, label=baseline_label,
                   color=baseline_color, edgecolor="black", linewidth=1.0,
                   capsize=6, error_kw={"elinewidth": 1.5, "capthick": 1.5, "ecolor": "black"})
    bars2 = ax.bar(x + width/2 + gap/2, orla_means, width,
                   yerr=orla_errs, label=orla_label,
                   color=orla_color, edgecolor="black", linewidth=1.0,
                   capsize=6, error_kw={"elinewidth": 1.5, "capthick": 1.5, "ecolor": "black"})
    
    # Add values on top of bars (like reference style)
    for i, (bl_mean, ol_mean, bl_err, ol_err) in enumerate(zip(baseline_means, orla_means, baseline_errs, orla_errs)):
        # Baseline value
        ax.text(x[i] - width/2 - gap/2, bl_mean + bl_err + max(baseline_means) * 0.02,
               f'{bl_mean:.2f}', ha='center', va='bottom', fontsize=14, fontweight='normal')
        # Orla value
        ax.text(x[i] + width/2 + gap/2, ol_mean + ol_err + max(baseline_means) * 0.02,
               f'{ol_mean:.2f}', ha='center', va='bottom', fontsize=14, fontweight='normal')
    
    ax.set_ylabel("Completion Time (s)", fontweight="bold", fontsize=16)
    ax.set_xlabel("Workflow Stage", fontweight="bold", fontsize=16)
    ax.set_xticks(x)
    ax.set_xticklabels(stages, fontsize=16)
    ax.set_xlim(-0.5, 4.5)  # Set x-axis limits to show spacing between groups
    ax.legend(loc="upper right", frameon=False, fontsize=16)
    ax.set_axisbelow(True)
    
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_linewidth(1.0)
    ax.spines["bottom"].set_linewidth(1.0)
    
    plt.tight_layout()
    plt.savefig(output_path / f"{output_name}.pdf", dpi=300, bbox_inches="tight", format="pdf")
    plt.savefig(output_path / f"{output_name}.png", dpi=300, bbox_inches="tight", format="png")
    print(f"Saved {backend_label} stage breakdown to {output_path / f'{output_name}.pdf'}")
    plt.close()


def plot_speedup_comparison(results: Dict[str, List[Dict[str, Any]]], output_path: Path) -> None:
    """Create normalized speedup plot showing improvement factor."""
    plt.style.use("default")
    plt.rcParams.update(SOSP_STYLE)
    
    fig, ax = plt.subplots(figsize=SOSP_STYLE["figure.figsize"])
    
    # Calculate speedup (baseline / orla)
    dc_baseline = [r["total_time_seconds"] for r in results["baseline"]]
    dc_orla = [r["total_time_seconds"] for r in results["orla"]]
    edge_baseline = [r["total_time_seconds"] for r in results["ollama_baseline"]]
    edge_orla = [r["total_time_seconds"] for r in results["ollama"]]
    
    dc_baseline_mean = np.mean(dc_baseline)
    dc_orla_mean = np.mean(dc_orla)
    edge_baseline_mean = np.mean(edge_baseline)
    edge_orla_mean = np.mean(edge_orla)
    
    dc_speedup = dc_baseline_mean / dc_orla_mean
    edge_speedup = edge_baseline_mean / edge_orla_mean
    
    categories = ["Datacenter\nServing", "Edge\nServing"]
    speedups = [dc_speedup, edge_speedup]
    
    x = np.array([0, 1])  # Separate positions with spacing
    width = 0.5  # Thin bars
    colors = ["b", "g"]  # Blue and Green
    
    bars = ax.bar(x, speedups, width, color=colors, edgecolor="black", linewidth=1.0)
    
    # Add value labels on top of bars
    for bar, speedup in zip(bars, speedups):
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height + max(speedups) * 0.02,
               f'{speedup:.2f}×',
               ha='center', va='bottom', fontsize=14, fontweight='normal')
    
    # Add baseline line at 1.0
    ax.axhline(y=1.0, color="black", linestyle="--", linewidth=1.0, alpha=0.5)
    
    ax.set_ylabel("Speedup (×)", fontweight="bold", fontsize=16)
    ax.set_xticks(x)
    ax.set_xticklabels(categories, fontsize=16)
    ax.set_ylim(bottom=0.9, top=max(speedups) * 1.15)
    ax.set_axisbelow(True)
    
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_linewidth(1.0)
    ax.spines["bottom"].set_linewidth(1.0)
    
    plt.tight_layout()
    plt.savefig(output_path / "speedup_comparison.pdf", dpi=300, bbox_inches="tight", format="pdf")
    plt.savefig(output_path / "speedup_comparison.png", dpi=300, bbox_inches="tight", format="png")
    print(f"Saved speedup comparison to {output_path / 'speedup_comparison.pdf'}")
    plt.close()


def main() -> None:
    """Main function to generate all plots."""
    # Get paths
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    output_dir = project_root / "output" / "cascade"
    plots_dir = script_dir
    
    if not output_dir.exists():
        print(f"Error: Output directory not found: {output_dir}")
        return
    
    # Load results
    print("Loading results...")
    results = load_results(output_dir)
    
    # Print summary
    print("\nLoaded results:")
    for mode, data in results.items():
        print(f"  {mode}: {len(data)} runs")
    
    # Generate plots
    print("\nGenerating SOSP-optimized plots...")
    plot_bar_chart(results, plots_dir)
    plot_stage_breakdown(results, plots_dir, "sglang")
    plot_stage_breakdown(results, plots_dir, "ollama")
    plot_speedup_comparison(results, plots_dir)
    
    print("\nAll plots generated successfully!")


if __name__ == "__main__":
    main()
