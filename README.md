# Harvard Agentic System – Story Finishing

Reproducible **story finishing** experiment: two agents alternate turns; each turn adds **k** tokens to the story. Uses [Orla](https://github.com/dorcha-inc/orla)’s **agent API**, **vLLM**, and **Docker Compose**.

## Prerequisites

- **Docker** and **Docker Compose** (Compose V2), with GPU support (NVIDIA Container Toolkit)
- **Go 1.25+**
- **Orla repo** (sibling directory `../orla` by default, or set `ORLA_REPO_PATH`) for building the Orla image. The experiment’s `experiments/go.mod` uses `replace github.com/dorcha-inc/orla => ../../orla` so the story_finishing binary uses your local Orla; adjust the path if your layout differs.

## Quick start

1. **Start vLLM and Orla**

   From this repo root:

   ```bash
   make up
   ```

   This brings up vLLM and Orla via Docker Compose. Wait until Orla is ready (about 30–60 seconds after the vLLM healthcheck passes).

2. **Run the story finishing test**

   ```bash
   make run-story-finishing
   ```

   Results are written to `output/story_finishing/run.json` (turns, k, TTFT/TPOT per turn, story text).

3. **Stop the stack**

   ```bash
   make down
   ```

## One-shot reproducible test

To bring up the stack, run the experiment, and tear down in one go:

```bash
make test
```

This runs `make build`, `docker compose up -d`, waits 60s, runs story finishing, then `docker compose down`. Results in `output/story_finishing/run.json`.

## Options

- **Turns and k:**  
  `make run-story-finishing STORY_TURNS=10 STORY_K=16`
- **Output file:**  
  `make run-story-finishing STORY_OUTPUT=output/my_run.json`
- **Orla repo path:**  
  `make up ORLA_REPO_PATH=/path/to/orla`

## How it works

1. **Docker Compose** starts:
   - **vLLM** (OpenAI-compatible) on port 8000
   - **Orla** on port 8081 with a minimal config (no backends; they are registered via API)

2. The **story_finishing** binary:
   - Waits for Orla health at `http://localhost:8081`
   - Registers the vLLM backend with Orla (endpoint `http://vllm:8000/v1` so the Orla container can reach vLLM)
   - Uses Orla’s **agent API**: `NewOrlaClient`, `RegisterBackend`, `NewAgent`, `SetMaxTokens`, `SetPrompt`, `Execute`
   - Runs **turns** iterations; each turn sends a prompt (“story so far, give next k tokens”), gets the response, appends to the story, and records TTFT/TPOT from the response metrics

3. Output JSON includes `turns`, `k`, `total_time_sec`, `avg_ttft_ms`, `avg_tpot_ms`, per-turn arrays, and the final `story`.

## Makefile targets

| Target                  | Description                                      |
|-------------------------|--------------------------------------------------|
| `make help`             | Show targets and overrides                       |
| `make build`            | Build `bin/story_finishing`                      |
| `make up`               | Start vLLM + Orla (docker compose up -d)         |
| `make down`             | Stop stack (docker compose down)                |
| `make run-story-finishing` | Run experiment (expects stack already up)    |
| `make test`             | Build, up, wait, run experiment, down            |
| `make clean`            | Remove `bin/` and `output/`                      |

## Files

- `docker-compose.yaml` – vLLM + Orla services
- `deploy/orla.yaml` – Minimal Orla server config (listen only; backends via API)
- `experiments/story_finishing/main.go` – Story finishing using Orla agent API
- `Makefile` – Build, compose, and run targets
