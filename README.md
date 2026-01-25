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


The Makefile automatically handles SGLang restarts between experiments to ensure clean cache state. **SGLang runs in a separate tmux window so you can monitor its output in parallel.**

```bash
# Start a tmux session (if not already in one)
tmux new-session -d -s experiments
tmux attach-session -t experiments

# Build the experiment binaries
make build-experiments

# Run experiments for all k values (automatically restarts SGLang in tmux between each)
make baseline              # Run aggressive_flush for all k values
make preserve              # Run preserve for all k values
make preserve-on-small-turns  # Run preserve_on_small_turns for all k values (threshold=32)
make all-experiments       # Run all three policies
```

**Important**: 
- The automated targets restart SGLang between each k value to ensure fair comparisons with clean cache state
- SGLang runs in a tmux window named `sglang` - switch to it with `tmux select-window -t sglang` to view its output
- You must be running inside a tmux session for automated experiments to work

### Background Noise (Realistic Load Simulation)

To simulate a real-world agentic serving environment with concurrent load, you can enable background noise:

```bash
# Run with 2 requests/second background noise
BACKGROUND_NOISE_RATE=2 make baseline

# Run with 5 requests/second background noise
BACKGROUND_NOISE_RATE=5 make preserve
```

The background noise generator sends concurrent requests to SGLang to simulate cache contention and realistic serving conditions. By default, all experiment targets use 2 req/s background noise. Set `BACKGROUND_NOISE_RATE=0` to disable.

### Manual Experiment Execution

For manual control, you can start SGLang and run individual experiments:

```bash
# Start SGLang (in a separate terminal)
make run-sglang

# Build experiments
make build-experiments

# Run a single experiment
./bin/story_finishing --policy aggressive_flush --turns 50 --k 1 --output outputs/flush_results.json
./bin/story_finishing --policy preserve --turns 50 --k 1 --output outputs/preserve_results.json
./bin/story_finishing --policy preserve_on_small_turns --turns 50 --k 1 --small-turn-threshold 32 --output outputs/preserve_small_results.json

# Stop SGLang when done
make stop-sglang
```

**Note**: For accurate comparisons, restart SGLang between different policy experiments to ensure clean cache state.

Some notes:

- SGLang runs in Docker, which handles all dependencies and CUDA setup automatically
- The model will be downloaded automatically from HuggingFace on first run and cached in `~/.cache/huggingface`
- The `--shm-size 32g` and `--ipc=host` flags improve performance
- The experiment automatically starts the Orla daemon, but you can also run it manually for debugging
- The binary is built for Linux (amd64) - use `make build-experiments` to rebuild
- **For accurate experiments**: The automated Makefile targets restart SGLang between each k value to ensure clean cache state
- **For realistic load**: Use `BACKGROUND_NOISE_RATE` to simulate concurrent requests and cache contention
- **tmux integration**: SGLang runs in a separate tmux window (`sglang`) so you can monitor its output in parallel - use `tmux select-window -t sglang` to view it

## Cache Policies

- `aggressive_flush` - Flush cache every turn (baseline)
- `preserve` - Keep cache across turns (optimized)
- `preserve_on_small_turns` - Conditional preservation: preserves cache when turn size (tokens) ≤ threshold, flushes when > threshold. Default threshold is 100 tokens. Use `--small-turn-threshold` to customize (Makefile uses 32 for experiments).
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

- `make build-experiments` - Build experiment binaries for Linux
- `make run-sglang` - Start SGLang server (interactive, blocks)
- `make run-sglang-tmux` - Start SGLang server in tmux window (for automated experiments)
- `make stop-sglang` - Stop SGLang server and close tmux window
- `make restart-sglang` - Restart SGLang server in tmux (clears cache state)
- `make baseline` - Run aggressive_flush experiments for all k values (auto-restarts SGLang)
- `make preserve` - Run preserve experiments for all k values (auto-restarts SGLang)
- `make preserve-on-small-turns` - Run preserve_on_small_turns experiments for all k values (threshold=32, auto-restarts SGLang)
- `make all-experiments` - Run all three policies (baseline, preserve, preserve-on-small-turns)
- `make sync-repo` - Build orla for Linux and sync code to Lambda
- `make setup-lambda` - Install dependencies on Lambda
- `make connect` - Connect to Lambda cluster
- `make sync-experiments` - Sync experiment results from Lambda
- `make plots` - Generate plots from results
