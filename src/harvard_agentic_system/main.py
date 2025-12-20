"""Main entry point for the baseline agentic system."""

import json
from pathlib import Path

import typer

from .game import StoryFinishingGame
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = typer.Typer(
    name="h-agent-sys",
    help="Harvard Agentic System - Baseline implementation for agentic systems with context sharing",
)


@app.command()
def run(
    model: str = typer.Option(
        "meta-llama/Llama-3.1-8B-Instruct",
        "--model",
        "-m",
        help="Model name to use",
    ),
    k: int = typer.Option(
        50,
        "--k",
        "-k",
        help="Number of inferences per turn",
    ),
    c: int = typer.Option(
        50,
        "--c",
        "-c",
        help="Number of tokens to generate per turn",
    ),
    turns: int = typer.Option(
        10,
        "--turns",
        "-t",
        help="Total number of turns",
    ),
    output: Path = typer.Option(
        "results.json",
        "--output",
        "-o",
        help="Output file for results JSON",
    ),
):
    """Run the baseline story-finishing game."""
    # Validate arguments
    if k != c:
        logger.warning(
            f"k ({k}) != c ({c}). For baseline, k should equal c.",
        )

    # Create and run game
    # Use context manager to automatically start/stop vLLM server
    with StoryFinishingGame(
        model_name=model,
        k=k,
        c=c,
        num_turns=turns,
    ) as game:
        results = game.run()

    # Save results
    with open(output, "w") as f:
        json.dump(results, f, indent=2)

    logger.info(f"Total time: {results['total_time']:.2f}s")
    logger.info(f"Average TTFT: {results['metrics']['avg_ttft']:.4f}s")
    logger.info(f"Average TPOT: {results['metrics']['avg_tpot']:.4f}s")
    logger.info(f"Results saved to: {output}")
    logger.info(f"Full story length: {len(results['full_story'])} characters")
    logger.info(f"Final context length: {results['final_context_length']} characters")


def main():
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
