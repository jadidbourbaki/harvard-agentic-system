# Harvard Agentic System

Experiments comparing Orla's Agentic Serving Layer KV cache policies.

You need the following:

- Go 1.23+
- Orla
- Docker (for running SGLang - handles all dependencies automatically)
- SGLang server (must be started manually via Docker - Orla does not start it automatically)

## Setup

### Lambda Cluster

Note: this section is relevant *only* if you are running this on Harvard's infrastructure. Please feel free to skip 
if running anywhere else.

1. Create a `.env` file with your credentials:
   ```bash
   SSH_KEY=~/.ssh/id_rsa
   JUMPER_PASSWORD=your-zu-password
   LAMBDA_PASSWORD=your-lambda-password
   LAMBDA_HOST=lambda1  # optional
   ```

2. Sync and setup:
   ```bash
   make sync-repo       # Build orla for Linux, sync code and binary to Lambda
   make setup-lambda   # Install dependencies and set up environment
   ```
   
   The `sync-repo` target will:
   - Build orla for Linux (amd64) from your local orla repository
   - Sync your code and the orla binary to the Lambda cluster
   
   The `setup-lambda` target will:
   - Install Go 1.23
   - Install Docker (if not already installed)
   - Install the synced orla binary to `~/.local/bin`
   - Set up the environment for running experiments
   

3. Connect:
   ```bash
   make connect        # Interactive shell
   ```

## Running Experiments

Use the following to start SGLang:

```bash
make sglang-run
```

Then you can run the experiments in the `experiments/` directory using Go:

Run with cache flushed each turn:

```bash
go run . --policy aggressive_flush --turns 5 --k 8 --output outputs/results.json
```

Run with cache preserved:

```bash
go run . --policy preserve --turns 5 --k 8 --output outputs/results.json
```

Some notes:

- SGLang runs in Docker, which handles all dependencies and CUDA setup automatically
- The model will be downloaded automatically from HuggingFace on first run and cached in `~/.cache/huggingface`
- The `--shm-size 32g` and `--ipc=host` flags improve performance
- The experiment automatically starts the Orla daemon, but you can also run it manually for debugging

## Cache Policies

- `aggressive_flush` - Flush cache every turn (baseline)
- `preserve` - Keep cache across turns (optimized)
- `preserve_on_small_turns` - Conditional preservation
- `flush_under_pressure` - Memory-aware flushing

## Output Format

Results are JSON with per-turn metrics:

```json
{
  "turns": 100,
  "k": 8,
  "total_time_seconds": 45.2,
  "avg_turn_time_ms": 452.0,
  "per_turn_metrics": [
    {"turn": 1, "total_time_ms": 500.1, "context_size": 100},
    ...
  ]
}
```

## Generating Plots

Generate publication-quality plots from experiment results:

```bash
make plots
```

This will:
1. Install plot dependencies (matplotlib, numpy) - no GPU required
2. Generate all plots from `experiments/output/`

Plots are saved to `plots/output/` in both PDF and PNG formats.

**Note:** Plot dependencies are in a separate `pyproject.toml` in the `plots/` directory, so you can generate plots on a machine without GPU/CUDA.

## Available Commands

See `make help` for all available targets:

- `make sync-repo` - Build orla for Linux and sync code to Lambda
- `make setup-lambda` - Install dependencies on Lambda
- `make connect` - Connect to Lambda cluster
- `make sync-experiments` - Sync experiment results from Lambda
- `make plots` - Generate plots from results
