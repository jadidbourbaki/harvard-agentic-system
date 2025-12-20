# Harvard Agentic System

## Setup

This project requires a Linux environment with CUDA support (e.g., Harvard Lambda clusters) as vLLM requires GPU support.

### Prerequisites

- Python 3.12.x
- CUDA-capable GPU
- `uv` package manager

### Installation

```bash
# Install dependencies
uv sync
```

## Usage

```bash
# Run the baseline story-finishing game
h-agent-sys run \
    --model meta-llama/Llama-3.1-8B-Instruct \
    --k 1 \
    --c 1 \
    --turns 100 \
    --output results.json
```

Use `h-agent-sys run --help` for all available options.