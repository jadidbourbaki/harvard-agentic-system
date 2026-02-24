#!/bin/bash
# Story finishing many agents grid: for each (k, turns, cache-strategy, background-agents) run up -> run-story-finishing-many-agents -> down.
# Run from repo root: ./experiments/story_finishing_many_agents/run.bash (or from anywhere; script cd's to root).
# Each run writes to output/story_finishing_many_agents/turns{N}_k{N}_cache{strategy}_background_agents{N}.json (unique per config).

set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

# Grid dimensions
K_VALS="128"
TURNS_VALS="50"
CACHE_STRATEGY_VALS="preserve flush"
BACKGROUND_AGENTS_VALS="5"
OUT_DIR="output/story_finishing_many_agents"

single_experiment() {
    local k=$1
    local turns=$2
    local cache=$3
    local bg=$4
    local out="${OUT_DIR}/turns${turns}_k${k}_cache${cache}_background_agents${bg}.json"
    echo "=============================================="
    echo "Story finishing many agents: k=$k turns=$turns cache=$cache background_agents=$bg -> $out"
    echo "=============================================="
    make up
    STORY_K=$k STORY_TURNS=$turns STORY_CACHE_STRATEGY=$cache STORY_BACKGROUND_AGENTS=$bg make run-story-finishing-many-agents
    make down
}

mkdir -p "$OUT_DIR"
echo "Grid: K_VALS=$K_VALS  TURNS_VALS=$TURNS_VALS  CACHE_STRATEGY_VALS=$CACHE_STRATEGY_VALS  BACKGROUND_AGENTS_VALS=$BACKGROUND_AGENTS_VALS  OUT_DIR=$OUT_DIR"

for k in $K_VALS; do
    for turns in $TURNS_VALS; do
        for cache in $CACHE_STRATEGY_VALS; do
            for bg in $BACKGROUND_AGENTS_VALS; do
                single_experiment "$k" "$turns" "$cache" "$bg"
            done
        done
    done
done

echo "Grid complete. Results in $OUT_DIR"
