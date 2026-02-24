#!/usr/bin/env python3
"""
Plot main-agent TTFT vs turn index for flush vs preserve cache strategy.
Reads JSON outputs from output/story_finishing_many_agents/.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt  # type: ignore

from plot_scripts.common import PAPER_COLORS, paper_style, save_fig


def load_ttft_by_turn(path: Path) -> list[float]:
    """Load ttft_ms values (one per turn) from a story_finishing_many_agents JSON."""
    with open(path) as f:
        data = json.load(f)

    agent = data.get("agents").get("main_agent")
    raw = agent.get("ttft_ms")
    return [x.get("value") for x in raw]


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot main-agent TTFT vs turn (flush vs preserve)")
    parser.add_argument("--turns", type=int, required=True, help="Number of turns")
    parser.add_argument("--k", type=int, required=True, help="Maximum number of tokens per turn")
    parser.add_argument(
        "--background-agents",
        type=int,
        required=True,
        help="Number of background agents",
    )

    args = parser.parse_args()

    output_dir = Path("plots")
    if not output_dir.exists():
        output_dir.mkdir(parents=True)

    root = Path("output/story_finishing_many_agents")
    if not root.is_dir():
        raise SystemExit(f"Not a directory: {root}")

    # Exact filenames matching experiment output: turns{N}_k{K}_cache{strategy}_background_agents{B}.json
    flush_path = root / f"turns{args.turns}_k{args.k}_cacheflush_background_agents{args.background_agents}.json"
    preserve_path = root / f"turns{args.turns}_k{args.k}_cachepreserve_background_agents{args.background_agents}.json"

    if not flush_path.is_file():
        raise SystemExit(f"Missing: {flush_path}")

    if not preserve_path.is_file():
        raise SystemExit(f"Missing: {preserve_path}")

    turns_flush = load_ttft_by_turn(flush_path)
    turns_preserve = load_ttft_by_turn(preserve_path)

    # ignore the first turn to avoid cold start effects
    turns_flush = turns_flush[1:]
    turns_preserve = turns_preserve[1:]

    # convert to seconds
    turns_flush = [x / 1000 for x in turns_flush]
    turns_preserve = [x / 1000 for x in turns_preserve]

    assert len(turns_flush) == len(turns_preserve)

    x_flush = list(range(len(turns_flush)))
    x_preserve = list(range(len(turns_preserve)))

    paper_style()
    plt.plot(x_flush, turns_flush, label="flush", marker=".", color=PAPER_COLORS[0])
    plt.plot(x_preserve, turns_preserve, label="preserve", marker=".", color=PAPER_COLORS[1])
    plt.xlabel("Turn")
    plt.ylabel("TTFT (s)")
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()

    stem = f"story_finishing_many_agents_main_agent_ttft_turns{args.turns}_k{args.k}_background_agents{args.background_agents}"
    output_path = output_dir / stem
    save_fig(output_path)
    print(f"Saved to {output_path}.pdf and {output_path}.png")


if __name__ == "__main__":
    main()
