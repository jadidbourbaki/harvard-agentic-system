#!/usr/bin/env python3
"""Run experiments for multiple k values."""

import json
import logging
from pathlib import Path
from datetime import datetime

from harvard_agentic_system.game import StoryFinishingGame

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def run_experiment(
    k: int,
    model: str,
    turns: int,
    output_dir: Path,
) -> dict:
    """
    Run a single experiment with given parameters.

    Args:
        k: Number of inferences per turn (c will equal k)
        model: Model name to use
        turns: Number of turns
        output_dir: Directory to save results

    Returns:
        Dictionary with experiment results including k value
    """
    logger.info(f"\n{'=' * 60}")
    logger.info(f"Running experiment: k={k}, c={k}, turns={turns}")
    logger.info(f"{'=' * 60}")

    # Create and run game
    with StoryFinishingGame(
        model_name=model,
        k=k,
        c=k,  # For baseline, k should equal c
        num_turns=turns,
    ) as game:
        results = game.run()

    # Add experiment metadata
    results["experiment_params"] = {
        "k": k,
        "c": k,
        "turns": turns,
        "model": model,
        "timestamp": datetime.now().isoformat(),
    }

    # Save results to file
    output_file = output_dir / f"results_k{k}.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)

    logger.info(f"Results saved to: {output_file}")
    logger.info(
        f"Average TTFT: {results['metrics']['avg_ttft']:.4f}s, "
        f"Average TPOT: {results['metrics']['avg_tpot']:.4f}s"
    )

    return results


def main():
    """Run experiments for multiple k values."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Run experiments for multiple k values"
    )
    parser.add_argument(
        "--k-values",
        type=int,
        nargs="+",
        default=[1, 2, 4, 8, 16, 32, 64, 128],
        help="List of k values to test (default: 1 2 4 8 16 32 64 128)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="mistralai/Mistral-7B-Instruct-v0.3",
        help="Model name to use",
    )
    parser.add_argument(
        "--turns",
        type=int,
        default=100,
        help="Number of turns per experiment (default: 100)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("experiments/output"),
        help="Directory to save results (default: experiments/output/)",
    )

    args = parser.parse_args()

    # Create output directory
    args.output_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Output directory: {args.output_dir}")

    # Run experiments
    all_results = []
    for k in args.k_values:
        try:
            results = run_experiment(
                k=k,
                model=args.model,
                turns=args.turns,
                output_dir=args.output_dir,
            )
            all_results.append(results)
        except Exception as e:
            logger.error(f"Experiment failed for k={k}: {e}", exc_info=True)
            # Continue with next experiment
            continue

    # Create summary file
    summary = {
        "experiments": len(all_results),
        "k_values": args.k_values,
        "model": args.model,
        "turns": args.turns,
        "timestamp": datetime.now().isoformat(),
        "results": [
            {
                "k": r["experiment_params"]["k"],
                "avg_ttft": r["metrics"]["avg_ttft"],
                "ttft_p50": r["metrics"]["ttft_p50"],
                "ttft_p99": r["metrics"]["ttft_p99"],
                "avg_tpot": r["metrics"]["avg_tpot"],
                "tpot_p50": r["metrics"]["tpot_p50"],
                "tpot_p99": r["metrics"]["tpot_p99"],
                "total_time": r["total_time"],
                "file": f"results_k{r['experiment_params']['k']}.json",
            }
            for r in all_results
        ],
    }

    summary_file = args.output_dir / "summary.json"
    with open(summary_file, "w") as f:
        json.dump(summary, f, indent=2)

    logger.info("\n" + "=" * 60)
    logger.info("All experiments complete!")
    logger.info(f"Summary saved to: {summary_file}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
