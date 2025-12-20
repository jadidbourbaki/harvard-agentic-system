.ONESHELL:

.PHONY: help install sync run connect setup-lambda sync-repo lint clean source-env

# Set default LAMBDA_HOST if not provided
LAMBDA_HOST ?= lambda1

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

# Install/sync dependencies with uv
install sync:
	uv sync

# Run the baseline story-finishing game (example - users should customize parameters)
run:
	@echo "Running baseline story-finishing game..."
	@echo "Customize parameters as needed:"
	@echo "  uv run h-agent-sys --model <model> --k <k> --c <c> --turns <turns> --output <output>"
	@echo ""
	uv run h-agent-sys \
		--model mistralai/Mistral-7B-Instruct-v0.3 \
		--k 1 \
		--c 1 \
		--turns 100 \
		--output results.json

# Run experiments for multiple k values
experiments:
	@echo "Running experiments for multiple k values..."
	uv run python experiments/run_experiments.py

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

# Lint Python code using ruff
lint:
	@if ! command -v ruff &> /dev/null; then \
		echo "Installing ruff..."; \
		uv pip install ruff; \
	fi
	ruff check src/
	@echo "Linting complete"

# Clean build artifacts and cache
clean:
	rm -rf .venv
	rm -rf __pycache__
	rm -rf .pytest_cache
	rm -rf .mypy_cache
	find . -type d -name "__pycache__" -exec rm -r {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	@echo "Clean complete"

