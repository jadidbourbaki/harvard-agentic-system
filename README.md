# harvard agentic system

Baseline implementation for agentic systems with context sharing.

This implementation uses vLLM's OpenAI-compatible server for accurate TTFT (Time To First Token) and TPOT (Time Per Output Token) metrics collection.

## prerequisites

- Python 3.12.x
- CUDA-capable GPU (required for vLLM)
- `uv` package manager
- `sshpass` (for Lambda cluster access)

## setup

### lambda cluster

1. Create a `.env` file with your credentials:
   ```bash
   SSH_KEY=~/.ssh/id_rsa
   JUMPER_PASSWORD=your-zu-password
   LAMBDA_PASSWORD=your-lambda-password
   LAMBDA_HOST=lambda1  # optional
   ```

2. Sync and setup:
   ```bash
   make sync-repo       # Sync your code to Lambda
   make setup-lambda    # Install dependencies on Lambda
   ```

3. Connect:
   ```bash
   make connect        # Interactive shell
   ```

### Local Development

```bash
make install           # Install dependencies
```

## usage

The system automatically starts a vLLM OpenAI-compatible server, runs the experiment, and collects detailed metrics.

```bash
# Run the baseline story-finishing game
make run

# Or customize parameters
uv run h-agent-sys \
    --model mistralai/Mistral-7B-Instruct-v0.3 \
    --k 1 \
    --c 1 \
    --turns 100 \
    --output results.json
```

### server management

1. The game automatically starts a vLLM server for the specified model
2. Uses vLLM's internal metrics for precise TTFT/TPOT measurements
3. Server is stopped automatically when the game completes

### manual server management

If you want to manage the vLLM server separately:

```bash
# Terminal 1: Start vLLM server
vllm serve mistralai/Mistral-7B-Instruct-v0.3 --host localhost --port 8000

# Terminal 2: Run game (with --no-manage-server flag when we add it)
uv run h-agent-sys --model mistralai/Mistral-7B-Instruct-v0.3 --k 1 --c 1 --turns 10
```

## running experiments

Run experiments for multiple k values:

```bash
make experiments
```

This runs experiments for k values: 1, 2, 4, 8, 16, 32, 64, 128 (default).

Results are saved to `experiments/output/`:
- Individual experiment results: `results_k{k}.json`
- Summary with aggregated metrics: `summary.json`

Each experiment result includes:
- Per-turn metrics (TTFT, TPOT, percentiles)
- Machine information (GPU, CPU, system details)
- Experiment parameters (k, c, turns, model)

Customize experiment parameters:

```bash
uv run python experiments/run_experiments.py \
    --k-values 1 2 4 8 \
    --turns 50 \
    --model mistralai/Mistral-7B-Instruct-v0.3 \
    --output-dir experiments/output
```

### syncing experiments from lambda

If you run experiments on the Lambda cluster, sync the results back:

```bash
make sync-experiments
```

This syncs `experiments/output/` from the Lambda cluster to your local machine.

See `make help` for all available targets.
