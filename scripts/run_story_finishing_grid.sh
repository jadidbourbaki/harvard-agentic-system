#!/usr/bin/env bash
# Run story_finishing over a grid: turns x k x noise x cache_strategy.
# With BACKEND_TYPE=sglang (default): each run uses --start-sglang (SGLang in tmux).
# With BACKEND_TYPE=vllm: use --backend-type vllm and optional --start-vllm (set START_VLLM=1).
# Outputs in output/story_finishing/. Invoke from repo root (or set BIN and OUT_DIR).
#
# Usage: ./scripts/run_story_finishing_grid.sh [backend_url]
#   backend_url  optional; default depends on BACKEND_TYPE (30000 for sglang, 8000/v1 for vllm)
#
# Env:
#   BACKEND_TYPE   sglang (default) or vllm
#   START_VLLM     1 to start vLLM in tmux per run (only when BACKEND_TYPE=vllm)
#   CACHE_STRATEGIES  default "flush preserve"

set -e

BACKEND_TYPE="${BACKEND_TYPE:-sglang}"
if [ "$BACKEND_TYPE" = "vllm" ]; then
	BACKEND="${1:-http://localhost:8000/v1}"
else
	BACKEND="${1:-http://localhost:30000}"
fi

BIN="${BIN:-./bin/story_finishing}"
OUT_DIR="${OUT_DIR:-output/story_finishing}"
CACHE_STRATEGIES="${CACHE_STRATEGIES:-flush preserve}"
START_VLLM="${START_VLLM:-0}"

TURNS="64"
K_VALS="2 4 8 16 32 64 128"
NOISE_RATES="0.5 1 2"

mkdir -p "$OUT_DIR"
echo "=============================================="
echo "Story Finishing grid: turns x k x noise x cache_strategy"
echo "Backend type: $BACKEND_TYPE  Backend: $BACKEND  Out: $OUT_DIR"
echo "Strategies: $CACHE_STRATEGIES"
if [ "$BACKEND_TYPE" = "sglang" ]; then
	echo "Each run uses --start-sglang (SGLang started/stopped per experiment)"
else
	echo "Each run uses --backend-type vllm; START_VLLM=$START_VLLM (start vLLM in tmux per run)"
fi
echo "=============================================="

for strategy in $CACHE_STRATEGIES; do
	for turns in $TURNS; do
		for k in $K_VALS; do
			for noise in $NOISE_RATES; do
				out="$OUT_DIR/turns_${turns}_k_${k}_noise_${noise}_${strategy}_${BACKEND_TYPE}.json"
				echo "Running turns=$turns k=$k noise=$noise strategy=$strategy -> $out"
				EXTRA=""
				if [ "$BACKEND_TYPE" = "vllm" ]; then
					EXTRA="--backend-type vllm"
					[ "$START_VLLM" = "1" ] && EXTRA="$EXTRA --start-vllm"
				else
					EXTRA="--start-sglang"
				fi
				"$BIN" --turns "$turns" --k "$k" --cache-strategy "$strategy" \
					--noise-rate "$noise" --backend "$BACKEND" --output "$out" \
					"$EXTRA"
			done
		done
	done
done

echo "Grid complete. Outputs in $OUT_DIR/"
