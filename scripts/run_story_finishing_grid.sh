#!/usr/bin/env bash
# Run story_finishing over a grid: turns x k x noise.
# Each run uses --start-sglang so the Go binary starts SGLang in tmux, runs the experiment, then stops it (self-contained; works on Lambda).
# Outputs in output/story_finishing/. Invoke from repo root (or set BIN and OUT_DIR).
#
# Usage: ./scripts/run_story_finishing_grid.sh [backend_url]
#   backend_url  optional; default http://localhost:30000

set -e

BACKEND="${1:-http://localhost:30000}"
BIN="${BIN:-./bin/story_finishing}"
OUT_DIR="${OUT_DIR:-output/story_finishing}"
CACHE_STRATEGY="${CACHE_STRATEGY:-flush}"

TURNS="64"
K_VALS="1 2 4 8 16 32 64 128"
NOISE_RATES="0.5 1 2"

mkdir -p "$OUT_DIR"
echo "=============================================="
echo "Story Finishing grid: turns x k x noise"
echo "Each run uses --start-sglang (SGLang started/stopped per experiment)"
echo "Backend: $BACKEND  Out: $OUT_DIR"
echo "=============================================="

for turns in $TURNS; do
	for k in $K_VALS; do
		for noise in $NOISE_RATES; do
			out="$OUT_DIR/turns_${turns}_k_${k}_noise_${noise}.json"
			echo "Running turns=$turns k=$k noise=$noise -> $out"
			"$BIN" --turns "$turns" --k "$k" --cache-strategy "$CACHE_STRATEGY" \
				--noise-rate "$noise" --backend "$BACKEND" --output "$out" \
				--start-sglang
		done
	done
done

echo "Grid complete. Outputs in $OUT_DIR/"
