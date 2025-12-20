# Harvard Agentic System

Baseline implementation for agentic systems with context sharing.

## Prerequisites

- Python 3.12.x
- CUDA-capable GPU (for Lambda cluster)
- `uv` package manager
- `sshpass` (for Lambda cluster access)

## Setup

### Lambda Cluster

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

## Usage

```bash
# Run the baseline story-finishing game
make run

# Or customize parameters
uv run h-agent-sys run \
    --model meta-llama/Llama-3.1-8B-Instruct \
    --k 1 \
    --c 1 \
    --turns 100 \
    --output results.json
```

See `make help` for all available targets.
