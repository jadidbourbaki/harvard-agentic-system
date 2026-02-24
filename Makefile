.ONESHELL:

.PHONY: help build up down test run-story-finishing run-story-finishing-many-agents clean source-env check-env print-env connect setup-lambda sync-repo sync-orla sync-experiments

# Story finishing defaults
STORY_TURNS ?= 20
STORY_K ?= 32
STORY_OUTPUT ?= output/story_finishing/run.json
STORY_CACHE_STRATEGY ?= preserve
STORY_NOISE_RATE ?= 0
STORY_BACKGROUND_AGENTS ?= 0

# Orla repo path for building the Orla image (sibling repo by default)
ORLA_REPO_PATH ?= ../orla

# Lambda cluster (infra targets)
LAMBDA_HOST ?= lambda1
SOURCE_ENV_CMD = if [ -f .env ]; then set -a && source .env && set +a; fi

## Show this help (extracted from comments above targets)
help:
	@awk -F'## ' '/^## / {d=$$2} /^[a-zA-Z0-9_-]+:/ {t=$$1; sub(/:.*/,"",t); if(d) printf "  make %-22s %s\n", t, d; d=""}' $(MAKEFILE_LIST)
	@echo ""
	@echo "Lambda (set in .env or env): JUMPER_PASSWORD, LAMBDA_PASSWORD, SSH_KEY, LAMBDA_HOST (default: lambda1)"
	@echo "  e.g. make setup-lambda LAMBDA_HOST=lambda1"

## Build the story_finishing binary
build:
	@echo "Building story_finishing..."
	@mkdir -p bin
	@go build -o bin/story_finishing ./experiments/story_finishing

DOCKER := sudo docker

## Start vLLM + Orla (docker compose up -d --wait)
up:
	@echo "Starting vLLM + Orla (docker compose)..."
	@$(DOCKER) compose up -d --wait
	@echo "Stack ready (vLLM healthy; Orla starts after vLLM)."

## Stop docker compose
down:
	@$(DOCKER) compose down

## Run story finishing (requires: make up already done)
run-story-finishing: build
	@mkdir -p output/story_finishing
	@./bin/story_finishing --turns $(STORY_TURNS) --k $(STORY_K) --output $(STORY_OUTPUT) --cache-strategy $(STORY_CACHE_STRATEGY) --noise-rate $(STORY_NOISE_RATE)

## Build and run story finishing many agents (writes to output/story_finishing_many_agents/<unique>.json)
run-story-finishing-many-agents:
	@echo "Building story_finishing_many_agents..."
	@mkdir -p bin output/story_finishing_many_agents
	@go build -o bin/story_finishing_many_agents ./experiments/story_finishing_many_agents
	@./bin/story_finishing_many_agents --turns $(STORY_TURNS) --k $(STORY_K) --cache-strategy $(STORY_CACHE_STRATEGY) --background-agents $(STORY_BACKGROUND_AGENTS)

## Remove bin/ and output/
clean:
	@rm -rf bin/ output/
	@echo "Clean complete"

# ==============================================================================
# Lambda / infra
# ==============================================================================

## Source .env if present (helper for targets that need env vars)
source-env:
	@$(SOURCE_ENV_CMD)

## Check Lambda env vars are set (JUMPER_PASSWORD, LAMBDA_PASSWORD, SSH_KEY)
check-env:
	@$(SOURCE_ENV_CMD); \
	if [ -z "$$JUMPER_PASSWORD" ]; then echo "Error: JUMPER_PASSWORD not set"; exit 1; fi; \
	if [ -z "$$LAMBDA_PASSWORD" ]; then echo "Error: LAMBDA_PASSWORD not set"; exit 1; fi; \
	if [ -z "$$SSH_KEY" ]; then echo "Error: SSH_KEY not set"; exit 1; fi; \
	echo "Lambda env OK"

## Print Lambda-related env vars
print-env:
	@$(SOURCE_ENV_CMD); \
	echo "SSH_KEY: $${SSH_KEY:-not set}"; \
	echo "JUMPER_PASSWORD: $${JUMPER_PASSWORD:-not set}"; \
	echo "LAMBDA_PASSWORD: $${LAMBDA_PASSWORD:-not set}"; \
	echo "LAMBDA_HOST: $${LAMBDA_HOST:-lambda1}"

## SSH to Lambda cluster
connect: check-env
	@$(SOURCE_ENV_CMD); \
	./infra/connect_lambda.sh $(LAMBDA_HOST)

## One-time setup on Lambda (install deps)
setup-lambda: check-env
	@$(SOURCE_ENV_CMD); \
	./infra/setup_lambda.sh $(LAMBDA_HOST)

## Sync repo to Lambda
sync-repo: check-env
	@$(SOURCE_ENV_CMD); \
	./infra/sync_repo.sh $(LAMBDA_HOST)

## Sync Orla binary to Lambda
sync-orla: check-env
	@$(SOURCE_ENV_CMD); \
	./infra/sync_orla.sh $(LAMBDA_HOST)

## Sync output/ from Lambda to local
sync-experiments: check-env
	@$(SOURCE_ENV_CMD); \
	./infra/sync_experiments.sh $(LAMBDA_HOST)
