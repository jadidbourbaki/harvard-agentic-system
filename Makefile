.ONESHELL:

.PHONY: help experiments baseline preserve all-experiments plots connect setup-lambda sync-repo sync-experiments run-sglang clean source-env check-env print-env

# Set default LAMBDA_HOST if not provided
LAMBDA_HOST ?= lambda1

# Experiment configuration
K_VALUES := 1 2 4 8 16 32 64 128
TURNS := 100
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
	@echo "  make baseline        - Run aggressive_flush (baseline) for all k values"
	@echo "  make preserve        - Run preserve (optimized) for all k values"
	@echo "  make all-experiments - Run both policies"

# Run baseline experiments (aggressive_flush) for all k values
baseline:
	@mkdir -p experiments/output/aggressive_flush
	@cd experiments && \
	for k in $(K_VALUES); do \
		echo "Running baseline k=$$k..."; \
		go run . --policy aggressive_flush --turns $(TURNS) --k $$k --backend $(BACKEND) \
			--output output/aggressive_flush/results_k$$k.json; \
	done

# Run preserve experiments (optimized) for all k values
preserve:
	@mkdir -p experiments/output/preserve
	@cd experiments && \
	for k in $(K_VALUES); do \
		echo "Running preserve k=$$k..."; \
		go run . --policy preserve --turns $(TURNS) --k $$k --backend $(BACKEND) \
			--output output/preserve/results_k$$k.json; \
	done

# Run both baseline and preserve experiments
all-experiments: baseline preserve

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

# Sync experiments/output/ from Lambda cluster to local (requires LAMBDA_HOST, default: lambda1)
sync-experiments: check-env
	@$(SOURCE_ENV_CMD); \
	./infra/sync_experiments.sh $(LAMBDA_HOST)

# Start SGLang server using Docker (required before running experiments)
run-sglang:
	@echo "Starting SGLang server with Docker..."
	@echo "Model will be downloaded automatically on first run"
	@echo "Press Ctrl+C to stop the server"
	@echo ""
	sudo docker run --gpus all --shm-size 32g -p 30000:30000 \
		-v ~/.cache/huggingface:/root/.cache/huggingface \
		--ipc=host \
		lmsysorg/sglang:latest python -m sglang.launch_server \
		--model-path mistralai/Mistral-7B-Instruct-v0.3 --port 30000 --host 0.0.0.0

# Clean build artifacts and cache
clean:
	@rm -rf experiments/output/
	@echo "Clean complete"

