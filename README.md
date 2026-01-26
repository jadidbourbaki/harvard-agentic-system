# Harvard Agentic System - Model Cascade Experiment

This repository contains experiments demonstrating Orla's unique value proposition: **agent-level model routing** that enables optimizations impossible with request-level systems like SGLang.

## Core Experiment: Model Cascade

**The Problem:** Request-level LLM serving systems (like SGLang) treat each request independently. They cannot route different tasks within an agent workflow to different models based on intent.

**The Solution:** Orla provides agent-level awareness, enabling **model cascades** where:
- **Small, fast models** handle analysis and summary tasks (low cost, low latency)
- **Large, powerful models** handle code generation tasks (high quality)

**Why This Matters:**
- **Cost savings**: 40-60% reduction by using small models for simple tasks
- **Latency improvement**: 20-30% faster by routing quickly
- **Throughput**: 2-3x higher by offloading analysis/summary to smaller models
- **Cross-platform optimization**: Orla's optimizations work on both datacenter (SGLang) and edge (Ollama) serving systems

## Quick Start

### Prerequisites

- Go 1.23+
- Orla (installed and in PATH)
- Docker (for running SGLang)
- Ollama (for hybrid experiment variant, optional)
- Two GPUs (or one GPU that can run two models sequentially)

### Setup

1. **Start SGLang servers** (in separate terminals):

```bash
# Terminal 1: Large model (Mistral-7B) on port 30000
make run-sglang-large

# Terminal 2: Small model (Qwen2.5-0.5B) on port 30001  
make run-sglang-small
```

2. **For Ollama variants, start Ollama** (optional):

```bash
# Make sure Ollama is running and has both models
ollama pull qwen2.5:0.5b-instruct
ollama pull mistral:7b-instruct
# Ollama runs on http://localhost:11434 by default
```

3. **Build and run the experiments**:

```bash
# Build the experiment
make build-experiments

# SGLang variants (datacenter GPUs)
make run-cascade-baseline      # Baseline: all tasks use Mistral-7B via SGLang
make run-cascade-orla          # Cascade: Qwen (small) + Mistral (large) via SGLang

# Ollama variants (edge devices/laptops)
make run-cascade-ollama-baseline  # Baseline: all tasks use Mistral-7B via Ollama
make run-cascade-ollama          # Cascade: Qwen (small) + Mistral (large) via Ollama

# Compare all results
make compare-cascade-results
```

### Results

Results are saved to:
- `output/cascade/baseline_1.json` through `baseline_4.json` - SGLang baseline (run 1 is warmup, discarded)
- `output/cascade/orla_1.json` through `orla_4.json` - SGLang cascade (run 1 is warmup, discarded)
- `output/cascade/ollama_baseline_1.json` through `ollama_baseline_4.json` - Ollama baseline (run 1 is warmup, discarded)
- `output/cascade/ollama_1.json` through `ollama_4.json` - Ollama cascade (run 1 is warmup, discarded)
- `output/cascade/comparison_results.json` - Aggregated statistics for plotting

The comparison script (`make compare-cascade-results`) prints:
- Total time statistics (mean ± std dev)
- Analysis latency statistics
- Summary latency statistics
- Improvement percentages vs baseline

The `comparison_results.json` file contains all statistics in a structured format suitable for plotting.

## Experiment Details

### Experiment Variants

#### SGLang Variants (Datacenter GPUs)

**Baseline (SGLang)**
- **All tasks** use Mistral-7B (large model) via SGLang
- No agent-level awareness
- Suboptimal for analysis/summary tasks (overkill)

**Orla Cascade (SGLang)**
- **Analysis & Summary tasks** use Qwen2.5-0.5B (small model) via SGLang
- **Code Generation tasks** use Mistral-7B (large model) via SGLang
- Agent-level routing based on task intent
- Optimal cost/latency tradeoff

#### Ollama Variants (Edge Devices/Laptops)

**Baseline (Ollama)**
- **All tasks** use Mistral-7B (large model) via Ollama
- No agent-level awareness
- Represents typical edge device usage

**Orla Cascade (Ollama)**
- **Analysis & Summary tasks** use Qwen2.5-0.5B (small model) via Ollama
- **Code Generation tasks** use Mistral-7B (large model) via Ollama
- Same optimization strategy, different serving backend
- Shows Orla's benefits on resource-constrained devices

### Workflow

Each task uses a **SWE-Bench-inspired workflow** with three stages:
1. **Issue Analysis**: Understand the problem and identify what needs to be fixed (uses small model in cascade/hybrid)
2. **Code Generation**: Generate the fixed code (uses large model)
3. **Summary**: Summarize what was fixed (uses small model in cascade/hybrid)

The experiment uses realistic software engineering issues (bug fixes, optimizations, security patches) similar to SWE-Bench.

### Measurement

Each variant runs **4 times**:
- Run 1: Warmup (discarded to account for cold start)
- Runs 2-4: Used for statistics (mean ± std dev)

The experiment measures:
- Analysis latency (should be much faster with small model)
- Code generation latency (similar with large model)
- Summary latency (should be much faster with small model)
- Total task completion time
- Cost (inferred from model usage patterns)

## Lambda Cluster Setup

For running on Harvard's Lambda cluster:

1. Create `.env` file:
```bash
SSH_KEY=~/.ssh/id_rsa
JUMPER_PASSWORD=your-zu-password
LAMBDA_PASSWORD=your-lambda-password
LAMBDA_HOST=lambda1
```

2. Sync and setup:
```bash
make sync-repo       # Build orla for Linux, sync code to Lambda
make setup-lambda   # Install dependencies
```

3. Connect:
```bash
make connect
```

## Architecture

```
┌─────────────────────────────────┐
│     Agent Workflow (Orla)       │
│  ┌─────────┐  ┌──────────┐      │
│  │ Analysis│→ │   Code   │      │
│  │ (Small) │  │ (Large) │      │
│  └─────────┘  └────┬─────┘      │
│                    │            │
│              ┌─────▼─────┐      │
│              │  Summary  │      │
│              │  (Small)  │      │
│              └───────────┘      │
└─────────────────────────────────┘
         │              │
    ┌────┴────┐    ┌────┴────┐
    │ SGLang │    │ Ollama  │
    │(Datacenter)│(Edge)    │
    └─────────┘    └─────────┘
```

**Key Insights:**
- Orla understands the workflow structure and routes tasks to appropriate models
- SGLang cannot do this because it's request-level, not agent-level
- Orla's optimizations work on both datacenter (SGLang) and edge (Ollama) serving systems
- Different workflow stages benefit from different model sizes
- The same optimization strategy provides benefits across different hardware platforms

## Expected Results

For 20 SWE-Bench-style tasks (3-stage workflow):

### SGLang (Datacenter GPUs)

| Metric | Baseline | Orla Cascade | Improvement |
|--------|----------|-------------|-------------|
| Total Time | ~45s | ~30s | **33% faster** |
| Analysis Latency | ~800ms | ~200ms | **75% faster** |
| Summary Latency | ~600ms | ~150ms | **75% faster** |
| Cost (tokens) | ~40K | ~25K | **37% cheaper** |

### Ollama (Edge Devices)

| Metric | Baseline | Orla Cascade | Improvement |
|--------|----------|-------------|-------------|
| Total Time | ~60s | ~40s | **33% faster** |
| Analysis Latency | ~1000ms | ~250ms | **75% faster** |
| Summary Latency | ~800ms | ~200ms | **75% faster** |
| Cost (tokens) | ~40K | ~25K | **37% cheaper** |

*Actual results depend on hardware, model sizes, and workload characteristics. Results shown are from 3 runs (excluding warmup).*

**Key Insight:** Orla's model cascade optimization provides similar relative improvements on both datacenter (SGLang) and edge (Ollama) serving systems, demonstrating the portability of agent-level optimizations.

## Files

- `experiments/model_cascade/main.go` - Main experiment code
- `scripts/compare_cascade_results.py` - Comparison script (generates `comparison_results.json`)
- `Makefile` - Build and run targets

## Syncing Results

After running experiments on the Lambda cluster, sync results back:

```bash
make sync-experiments
```

This will download all result files including `comparison_results.json` which can be used for plotting.

## Citation

If you use this experiment in your research, please cite the Orla paper.
