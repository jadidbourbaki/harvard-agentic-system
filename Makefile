.ONESHELL:

.PHONY: help experiments baseline preserve preserve-on-small-turns all-experiments plots connect setup-lambda sync-repo sync-experiments run-sglang run-sglang-tmux stop-sglang restart-sglang clean source-env check-env print-env

# Set default LAMBDA_HOST if not provided
LAMBDA_HOST ?= lambda1

# Experiment configuration
K_VALUES := 1 10 20 80 90 100
TURNS := 20
BACKEND := http://localhost:30000

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
	echo "LAMBDA_HOST: $${LAMBDA_HOST:-$(LAMBDA_HOST)}"

# Run Orla experiments (see experiments/README.md)
experiments:
	@echo "Orla experiments are in experiments/"
	@echo "See experiments/README.md for instructions"
	@echo ""
	@echo "Available experiment targets:"
	@echo "  make baseline              - Run aggressive_flush (baseline) for all k values"
	@echo "  make preserve              - Run preserve (optimized) for all k values"
	@echo "  make preserve-on-small-turns - Run preserve_on_small_turns (conditional) for all k values"
	@echo "  make all-experiments       - Run all three policies"

# Run baseline experiments (aggressive_flush) for all k values
# Restarts SGLang between each k value to ensure clean cache state
# Set BACKGROUND_NOISE_RATE to override default (default: 2 req/s, set to 0 to disable)
baseline:
	@mkdir -p experiments/output/aggressive_flush
	@BACKGROUND_NOISE_RATE=$${BACKGROUND_NOISE_RATE:-2}; \
	if [ "$$BACKGROUND_NOISE_RATE" != "0" ]; then \
		NOISE_LOG=experiments/output/background_noise_$$(date +%s).log; \
		echo "Starting background noise at $$BACKGROUND_NOISE_RATE req/s (logs: $$NOISE_LOG)..."; \
		./bin/background_noise --backend $(BACKEND) --rate $$BACKGROUND_NOISE_RATE > $$NOISE_LOG 2>&1 & \
		NOISE_PID=$$!; \
		sleep 2; \
	fi; \
	for k in $(K_VALUES); do \
		echo "========================================="; \
		echo "Running baseline k=$$k..."; \
		echo "========================================="; \
		$(MAKE) restart-sglang; \
		./bin/story_finishing --policy aggressive_flush --turns $(TURNS) --k $$k --backend $(BACKEND) \
			--output output/aggressive_flush/results_k$$k.json; \
		$(MAKE) stop-sglang; \
		echo "Completed k=$$k, restarting SGLang for next experiment..."; \
		sleep 2; \
	done; \
	if [ "$$BACKGROUND_NOISE_RATE" != "0" ]; then \
		kill $$NOISE_PID 2>/dev/null || true; \
		echo "Stopped background noise generator"; \
	fi

# Run preserve experiments (optimized) for all k values
# Restarts SGLang between each k value to ensure clean cache state
# Set BACKGROUND_NOISE_RATE to override default (default: 2 req/s, set to 0 to disable)
preserve:
	@mkdir -p experiments/output/preserve
	@BACKGROUND_NOISE_RATE=$${BACKGROUND_NOISE_RATE:-2}; \
	if [ "$$BACKGROUND_NOISE_RATE" != "0" ]; then \
		NOISE_LOG=experiments/output/background_noise_$$(date +%s).log; \
		echo "Starting background noise at $$BACKGROUND_NOISE_RATE req/s (logs: $$NOISE_LOG)..."; \
		./bin/background_noise --backend $(BACKEND) --rate $$BACKGROUND_NOISE_RATE > $$NOISE_LOG 2>&1 & \
		NOISE_PID=$$!; \
		sleep 2; \
	fi; \
	for k in $(K_VALUES); do \
		echo "========================================="; \
		echo "Running preserve k=$$k..."; \
		echo "========================================="; \
		$(MAKE) restart-sglang; \
		./bin/story_finishing --policy preserve --turns $(TURNS) --k $$k --backend $(BACKEND) \
			--output output/preserve/results_k$$k.json; \
		$(MAKE) stop-sglang; \
		echo "Completed k=$$k, restarting SGLang for next experiment..."; \
		sleep 2; \
	done; \
	if [ "$$BACKGROUND_NOISE_RATE" != "0" ]; then \
		kill $$NOISE_PID 2>/dev/null || true; \
		echo "Stopped background noise generator"; \
	fi

# Run preserve_on_small_turns experiments (conditional preservation) for all k values
# Restarts SGLang between each k value to ensure clean cache state
# Uses small-turn-threshold=32 (k <= 32 preserves cache, k > 32 flushes)
# Set BACKGROUND_NOISE_RATE to override default (default: 2 req/s, set to 0 to disable)
preserve-on-small-turns:
	@mkdir -p experiments/output/preserve_on_small_turns
	@BACKGROUND_NOISE_RATE=$${BACKGROUND_NOISE_RATE:-2}; \
	if [ "$$BACKGROUND_NOISE_RATE" != "0" ]; then \
		NOISE_LOG=experiments/output/background_noise_$$(date +%s).log; \
		echo "Starting background noise at $$BACKGROUND_NOISE_RATE req/s (logs: $$NOISE_LOG)..."; \
		./bin/background_noise --backend $(BACKEND) --rate $$BACKGROUND_NOISE_RATE > $$NOISE_LOG 2>&1 & \
		NOISE_PID=$$!; \
		sleep 2; \
	fi; \
	for k in $(K_VALUES); do \
		echo "========================================="; \
		echo "Running preserve_on_small_turns k=$$k..."; \
		echo "========================================="; \
		$(MAKE) restart-sglang; \
		./bin/story_finishing --policy preserve_on_small_turns --turns $(TURNS) --k $$k --backend $(BACKEND) \
			--small-turn-threshold 32 --output output/preserve_on_small_turns/results_k$$k.json; \
		$(MAKE) stop-sglang; \
		echo "Completed k=$$k, restarting SGLang for next experiment..."; \
		sleep 2; \
	done; \
	if [ "$$BACKGROUND_NOISE_RATE" != "0" ]; then \
		kill $$NOISE_PID 2>/dev/null || true; \
		echo "Stopped background noise generator"; \
	fi

# Run both baseline and preserve experiments
all-experiments: baseline preserve preserve-on-small-turns

# Install plot dependencies (separate from main dependencies, no GPU required)
install-plots:
	@echo "Installing plot dependencies..."
	cd plots && uv sync

# Clean plots output directory
clean-plots:
	rm -rf plots/output

# Generate plots from experiment results (requires plot dependencies)
plots: install-plots
	@echo "Generating plots from experiment results..."
	cd plots && uv run python generate_plots.py

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

# Sync experiments/output/ from Lambda cluster to local (requires LAMBDA_HOST, default: lambda1)
sync-experiments: check-env
	@$(SOURCE_ENV_CMD); \
	./infra/sync_experiments.sh $(LAMBDA_HOST)

# Start SGLang server using Docker (required before running experiments)
# Use --rm to auto-remove container when stopped
# Requires SUDO_PASSWORD environment variable
run-sglang:
	@echo "Starting SGLang server with Docker..."
	@echo "Model will be downloaded automatically on first run"
	@echo "Press Ctrl+C to stop the server"
	@echo ""
	@echo "$$SUDO_PASSWORD" | sudo -S docker run --rm --name sglang-server --gpus all --shm-size 32g -p 30000:30000 \
		-v ~/.cache/huggingface:/root/.cache/huggingface \
		--ipc=host \
		lmsysorg/sglang:latest python -m sglang.launch_server \
		--model-path mistralai/Mistral-7B-Instruct-v0.3 --port 30000 --host 0.0.0.0

# Start SGLang server in a new tmux window (for automated experiments)
# Assumes you're running inside a tmux session
# Requires SUDO_PASSWORD environment variable
run-sglang-tmux:
	@echo "Starting SGLang server in tmux window 'sglang'..."
	@if ! tmux has-session 2>/dev/null; then \
		echo "Error: Not running inside a tmux session. Please start tmux first."; \
		exit 1; \
	fi
	@tmux kill-window -t sglang 2>/dev/null || true
	@tmux new-window -d -n sglang "echo '$$SUDO_PASSWORD' | sudo -S docker run --rm --name sglang-server --gpus all --shm-size 32g -p 30000:30000 -v ~/.cache/huggingface:/root/.cache/huggingface --ipc=host lmsysorg/sglang:latest python -m sglang.launch_server --model-path mistralai/Mistral-7B-Instruct-v0.3 --port 30000 --host 0.0.0.0"
	@echo "Waiting for SGLang to be ready..."
	@max_attempts=120; \
	attempt=0; \
	while [ $$attempt -lt $$max_attempts ]; do \
		if curl -s -f http://localhost:30000/model_info >/dev/null 2>&1; then \
			echo "SGLang server is ready!"; \
			break; \
		fi; \
		attempt=$$((attempt + 1)); \
		if [ $$((attempt % 10)) -eq 0 ]; then \
			echo "Still waiting... ($$attempt/$$max_attempts attempts)"; \
		fi; \
		sleep 1; \
	done; \
	if [ $$attempt -eq $$max_attempts ]; then \
		echo "Warning: SGLang may not be fully ready after $$max_attempts seconds"; \
		exit 1; \
	fi
	@echo "SGLang server is ready! Sleeping for 15 seconds to ensure it's fully ready..."; \
	sleep 15; \
	echo "SGLang server started in tmux window 'sglang'"; \
	echo "View it with: tmux select-window -t sglang"

# Stop SGLang server (stops Docker container and tmux window)
# Requires SUDO_PASSWORD environment variable
stop-sglang:
	@echo "Stopping SGLang server..."
	@echo "$$SUDO_PASSWORD" | sudo -S docker stop sglang-server 2>/dev/null || echo "SGLang container not running"
	@echo "$$SUDO_PASSWORD" | sudo -S docker rm sglang-server 2>/dev/null || echo "SGLang container not found"
	@echo "SGLang server stopped"
	@echo "Sleeping for 10 seconds to ensure the server is fully stopped..."; \
	sleep 10; \
	echo "SGLang server fully stopped"

# Restart SGLang server (stops and starts fresh in tmux, clears cache state)
restart-sglang: stop-sglang run-sglang-tmux

# Clean build artifacts and cache
clean:
	@rm -rf experiments/output/
	@echo "Clean complete"

# Build experiments for Linux
build-experiments:
	mkdir -p bin/
	@echo "Building experiments..."
	@(cd experiments/story_finishing && GOOS=linux GOARCH=amd64 CGO_ENABLED=0 go build -o ../../bin/story_finishing .)
	@(cd experiments/background_noise && GOOS=linux GOARCH=amd64 CGO_ENABLED=0 go build -o ../../bin/background_noise .)

# Clean build artifacts and cache
clean-experiments:
	@rm -rf bin/
	@echo "Clean complete"