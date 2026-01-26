.ONESHELL:

.PHONY: help build-experiments run-cascade-baseline run-cascade-orla connect setup-lambda sync-repo sync-experiments run-sglang run-sglang-tmux stop-sglang restart-sglang clean source-env check-env print-env

# Set default LAMBDA_HOST if not provided
LAMBDA_HOST ?= lambda1

# Model cascade experiment configuration
BACKEND_LARGE := http://localhost:30000
BACKEND_SMALL := http://localhost:30001
BACKEND_OLLAMA := http://localhost:11434
NUM_TASKS := 20

# Command to source .env file if it exists
SOURCE_ENV_CMD = if [ -f .env ]; then set -a && source .env && set +a; fi

# Source .env file if it exists (helper for targets that need env vars)
source-env:
	@$(SOURCE_ENV_CMD)

# Default target - Auto-generate help from comments
help:
	@echo "Available targets:"
	@echo ""
	@awk '/^# [A-Z]/ { \
		comment = substr($$0, 3); \
		getline; \
		if ($$0 ~ /^[a-zA-Z0-9_-]+:/ || $$0 ~ /^[a-zA-Z0-9_-]+ [a-zA-Z0-9_-]+:/) { \
			split($$0, targets, ":"); \
			for (i in targets) { \
				target = targets[i]; \
				gsub(/^[ \t]+/, "", target); \
				if (target != "" && target != ".PHONY") { \
					printf "  make %-15s - %s\n", target, comment; \
				} \
			} \
		} \
	}' $(MAKEFILE_LIST)
	@echo ""
	@echo "Environment variables for Lambda:"
	@echo "  JUMPER_PASSWORD   - Password for jumper host"
	@echo "  LAMBDA_PASSWORD   - Password for Lambda cluster"
	@echo "  LAMBDA_HOST       - Lambda hostname (default: lambda1)"
	@echo ""
	@echo "Example usage:"
	@echo "  export JUMPER_PASSWORD='your-password'"
	@echo "  export LAMBDA_PASSWORD='your-password'"
	@echo "  make setup-lambda LAMBDA_HOST=lambda1"

# Checks that the environment variables are set
check-env:
	@$(SOURCE_ENV_CMD); \
	if [ -z "$$JUMPER_PASSWORD" ]; then \
		echo "Error: JUMPER_PASSWORD environment variable is not set"; \
		exit 1; \
	fi; \
	if [ -z "$$LAMBDA_PASSWORD" ]; then \
		echo "Error: LAMBDA_PASSWORD environment variable is not set"; \
		exit 1; \
	fi; \
	if [ -z "$$SSH_KEY" ]; then \
		echo "Error: SSH_KEY environment variable is not set"; \
		exit 1; \
	fi; \
	echo "All required environment variables are set"

# Prints the environment variables
print-env:
	@$(SOURCE_ENV_CMD); \
	echo "SSH_KEY: $${SSH_KEY:-not set}"; \
	echo "JUMPER_PASSWORD: $${JUMPER_PASSWORD:-not set}"; \
	echo "LAMBDA_PASSWORD: $${LAMBDA_PASSWORD:-not set}"; \
	echo "LAMBDA_HOST: $${LAMBDA_HOST:-lambda1}"

# ==============================================================================
# MODEL CASCADE EXPERIMENT
# ==============================================================================
# This experiment demonstrates Orla's unique value: agent-level model routing.
# 
# Baseline: SGLang always uses large model (Mistral-7B) for all tasks
# Orla: Uses small model (Qwen2.5-0.5B) for routing, large model for synthesis
#
# Expected benefits:
# - Cost: 40-60% reduction (small model for routing)
# - Latency: 20-30% faster (fast routing decisions)
# - Throughput: 2-3x higher

# Build the model cascade experiment
build-experiments:
	@echo "Building model cascade experiment..."
	@mkdir -p bin
	@cd experiments/model_cascade && go build -o ../../bin/model_cascade .

# Run baseline experiment (SGLang: always uses large model) - 4 runs (1 warmup + 3 for error bars)
run-cascade-baseline:
	@mkdir -p output/cascade
	@echo "=============================================="
	@echo "Running Baseline: SGLang (always large model)"
	@echo "Running 4 times (1 warmup + 3 for error bars)..."
	@echo "=============================================="
	@for i in 1 2 3 4; do \
		echo ""; \
		if [ $$i -eq 1 ]; then \
			echo "Run $$i/4 (WARMUP - will be discarded):"; \
		else \
			echo "Run $$i/4:"; \
		fi; \
		./bin/model_cascade --mode baseline \
			--backend-large $(BACKEND_LARGE) \
			--num-tasks $(NUM_TASKS) \
			--output output/cascade/baseline_$$i.json; \
		echo "Results saved to output/cascade/baseline_$$i.json"; \
	done
	@echo ""
	@echo "All 4 baseline runs complete! (Run 1 is warmup, runs 2-4 used for statistics)"

# Run Orla cascade experiment (small model for routing, large for synthesis) - 4 runs (1 warmup + 3 for error bars)
run-cascade-orla:
	@mkdir -p output/cascade
	@echo "=============================================="
	@echo "Running Orla: Model Cascade (small + large)"
	@echo "Running 4 times (1 warmup + 3 for error bars)..."
	@echo "=============================================="
	@for i in 1 2 3 4; do \
		echo ""; \
		if [ $$i -eq 1 ]; then \
			echo "Run $$i/4 (WARMUP - will be discarded):"; \
		else \
			echo "Run $$i/4:"; \
		fi; \
		./bin/model_cascade --mode cascade \
			--backend-small $(BACKEND_SMALL) \
			--backend-large $(BACKEND_LARGE) \
			--num-tasks $(NUM_TASKS) \
			--output output/cascade/orla_$$i.json; \
		echo "Results saved to output/cascade/orla_$$i.json"; \
	done
	@echo ""
	@echo "All 4 Orla cascade runs complete! (Run 1 is warmup, runs 2-4 used for statistics)"

# Run Ollama baseline experiment (all tasks use Mistral via Ollama) - 4 runs (1 warmup + 3 for error bars)
run-cascade-ollama-baseline:
	@mkdir -p output/cascade
	@echo "=============================================="
	@echo "Running Ollama Baseline: All tasks use Mistral-7B"
	@echo "Running 4 times (1 warmup + 3 for error bars)..."
	@echo "=============================================="
	@for i in 1 2 3 4; do \
		echo ""; \
		if [ $$i -eq 1 ]; then \
			echo "Run $$i/4 (WARMUP - will be discarded):"; \
		else \
			echo "Run $$i/4:"; \
		fi; \
		./bin/model_cascade --mode baseline-ollama \
			--backend-ollama $(BACKEND_OLLAMA) \
			--num-tasks $(NUM_TASKS) \
			--output output/cascade/ollama_baseline_$$i.json; \
		echo "Results saved to output/cascade/ollama_baseline_$$i.json"; \
	done
	@echo ""
	@echo "All 4 Ollama baseline runs complete! (Run 1 is warmup, runs 2-4 used for statistics)"

# Run Ollama cascade experiment (Qwen for analysis/summary, Mistral for code generation) - 4 runs (1 warmup + 3 for error bars)
run-cascade-ollama:
	@mkdir -p output/cascade
	@echo "=============================================="
	@echo "Running Ollama Cascade: Qwen (small) + Mistral (large)"
	@echo "Running 4 times (1 warmup + 3 for error bars)..."
	@echo "=============================================="
	@for i in 1 2 3 4; do \
		echo ""; \
		if [ $$i -eq 1 ]; then \
			echo "Run $$i/4 (WARMUP - will be discarded):"; \
		else \
			echo "Run $$i/4:"; \
		fi; \
		./bin/model_cascade --mode cascade-ollama \
			--backend-ollama $(BACKEND_OLLAMA) \
			--num-tasks $(NUM_TASKS) \
			--output output/cascade/ollama_$$i.json; \
		echo "Results saved to output/cascade/ollama_$$i.json"; \
	done
	@echo ""
	@echo "All 4 Ollama cascade runs complete! (Run 1 is warmup, runs 2-4 used for statistics)"

compare-cascade-results:
	@echo "Comparing cascade results..."
	@python3 scripts/compare_cascade_results.py

# ==============================================================================
# SGLANG SERVER MANAGEMENT
# ==============================================================================

# Start SGLang server with large model (Mistral-7B) on port 30000
run-sglang-large:
	@echo "Starting SGLang server with Mistral-7B on port 30000..."
	@echo "Model will be downloaded automatically on first run"
	@echo "Press Ctrl+C to stop the server"
	@echo ""
	@echo "$$SUDO_PASSWORD" | sudo -S docker run --rm --name sglang-large --gpus all --shm-size 32g -p 30000:30000 \
		-v ~/.cache/huggingface:/root/.cache/huggingface \
		--ipc=host \
		lmsysorg/sglang:latest python -m sglang.launch_server \
		--model-path mistralai/Mistral-7B-Instruct-v0.3 --port 30000 --host 0.0.0.0 \
		--mem-fraction-static 0.5

# Start SGLang server with small model (Qwen2.5-0.5B) on port 30001
run-sglang-small:
	@echo "Starting SGLang server with Qwen2.5-0.5B on port 30001..."
	@echo "Model will be downloaded automatically on first run"
	@echo "Press Ctrl+C to stop the server"
	@echo ""
	@echo "$$SUDO_PASSWORD" | sudo -S docker run --rm --name sglang-small --gpus all --shm-size 32g -p 30001:30000 \
		-v ~/.cache/huggingface:/root/.cache/huggingface \
		--ipc=host \
		lmsysorg/sglang:latest python -m sglang.launch_server \
		--model-path Qwen/Qwen2.5-0.5B-Instruct --port 30000 --host 0.0.0.0 \
		--mem-fraction-static 0.5

# Stop SGLang servers
stop-sglang:
	@echo "Stopping SGLang servers..."
	@echo "$$SUDO_PASSWORD" | sudo -S docker stop sglang-large sglang-small 2>/dev/null || true
	@echo "$$SUDO_PASSWORD" | sudo -S docker rm sglang-large sglang-small 2>/dev/null || true
	@echo "SGLang servers stopped"

# Restart SGLang servers (stop then start in tmux)
restart-sglang: stop-sglang run-sglang-tmux

# ==============================================================================
# LAMBDA CLUSTER MANAGEMENT
# ==============================================================================

# Connect to Lambda cluster (requires LAMBDA_HOST, default: lambda1)
connect: check-env
	@$(SOURCE_ENV_CMD); \
	./infra/connect_lambda.sh $(LAMBDA_HOST)

# Setup environment on Lambda cluster (requires LAMBDA_HOST, default: lambda1)
setup-lambda: check-env
	@$(SOURCE_ENV_CMD); \
	./infra/setup_lambda.sh $(LAMBDA_HOST)

# Sync git repository to Lambda cluster (requires LAMBDA_HOST, default: lambda1)
sync-repo: check-env
	@$(SOURCE_ENV_CMD); \
	./infra/sync_repo.sh $(LAMBDA_HOST)

# Sync orla binary to Lambda cluster (requires LAMBDA_HOST, default: lambda1)
sync-orla: check-env
	@$(SOURCE_ENV_CMD); \
	./infra/sync_orla.sh $(LAMBDA_HOST)

# Sync output/ from Lambda cluster to local (requires LAMBDA_HOST, default: lambda1)
sync-experiments: check-env
	@$(SOURCE_ENV_CMD); \
	./infra/sync_experiments.sh $(LAMBDA_HOST)

# Clean build artifacts and output
clean:
	@echo "Cleaning build artifacts..."
	@rm -rf bin/
	@rm -rf output/
	@echo "Clean complete"
