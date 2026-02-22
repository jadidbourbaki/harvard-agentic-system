#!/bin/bash
# Story finishing grid: for each (k, turns, cache-strategy, noise-rate) run up -> run-story-finishing -> down.

set -e

# Grid dimensions (same as experiment defaults)
K_VALS="8 16 32 64 128"
TURNS_VALS="50"
CACHE_STRATEGY_VALS="preserve flush"
NOISE_RATE_VALS="10 20 30 40 50"
OUT_DIR="output/story_finishing"

# Safe filename segment for noise rate (e.g. 0.5 -> 0_5)
noise_rate_to_suffix() { echo "$1" | tr '.' '_'; }

single_experiment() {
    local k=$1
    local turns=$2
    local cache=$3
    local noise_rate=$4
    local noise_suffix
    noise_suffix=$(noise_rate_to_suffix "$noise_rate")
    local out="${OUT_DIR}/run_k${k}_turns${turns}_${cache}_noise${noise_suffix}.json"
    echo "=============================================="
    echo "Story finishing: k=$k turns=$turns cache=$cache noise_rate=$noise_rate -> $out"
    echo "=============================================="
    make up
    STORY_K=$k STORY_TURNS=$turns STORY_CACHE_STRATEGY=$cache STORY_NOISE_RATE=$noise_rate STORY_OUTPUT="$out" make run-story-finishing
    make down
}

mkdir -p "$OUT_DIR"
echo "Grid: K_VALS=$K_VALS  TURNS_VALS=$TURNS_VALS  CACHE_STRATEGY_VALS=$CACHE_STRATEGY_VALS  NOISE_RATE_VALS=$NOISE_RATE_VALS  OUT_DIR=$OUT_DIR"

for k in $K_VALS; do
    for turns in $TURNS_VALS; do
        for cache in $CACHE_STRATEGY_VALS; do
            for noise_rate in $NOISE_RATE_VALS; do
                single_experiment "$k" "$turns" "$cache" "$noise_rate"
            done
        done
    done
done

echo "Grid complete. Results in $OUT_DIR"
