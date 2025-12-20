# Experimental Results Analysis

This document explains the results of the experiments measuring Time To First Token (TTFT) and Time Per Output Token (TPOT) for an agentic story-finishing game with varying values of k (tokens per turn).

**Note:** All aggregate metrics exclude turn 1 (warm-up) to measure steady-state performance. The first request incurs cold start overhead from CUDA kernel initialization, memory allocation, and cache warming (~86ms vs ~14ms for subsequent requests).

## Key Findings

### 1. TTFT Scaling with k

From the TTFT vs k plot, we observe:

- **k=1**: Average TTFT ≈ 14.4 ms (median: 13.6 ms, p99: 16.3 ms)
- **k=2**: Average TTFT ≈ 16.7 ms (median: 16.0 ms, p99: 19.9 ms)
- **k=4**: Average TTFT ≈ 16.7 ms (median: 16.0 ms, p99: 19.9 ms)
- **k=8**: Average TTFT ≈ 16.0 ms (median: 16.0 ms, p99: 17.0 ms)
- **k=16**: Average TTFT ≈ 16.9 ms (median: 16.0 ms, p99: 19.0 ms)
- **k=32**: Average TTFT ≈ 17.6 ms (median: 17.0 ms, p99: 19.9 ms)
- **k=64**: Average TTFT ≈ 18.1 ms (median: 18.0 ms, p99: 19.9 ms)
- **k=128**: Average TTFT ≈ 20.7 ms (median: 20.0 ms, p99: 26.0 ms)

**Analysis**: TTFT grows slowly (sub-linear) with k, increasing from ~14ms to ~21ms as k increases from 1 to 128 (only ~1.5× increase for 128× more tokens). This is because TTFT measures prefill latency, which depends on the *input context length* that grows across turns, not the requested output length k. The small increase reflects the modest growth in context size (from a few tokens to ~500 tokens over 100 turns).

### 2. TPOT Scaling with k

From the TPOT vs k plot (excluding k=1, as TPOT requires k > 1):

- **k=2**: Average TPOT ≈ 11.9 ms (median: 10.0 ms, p99: 17.0 ms)
- **k=4**: Average TPOT ≈ 11.0 ms (median: 10.0 ms, p99: 17.0 ms)
- **k=8**: Average TPOT ≈ 10.6 ms (median: 10.0 ms, p99: 14.0 ms)
- **k=16**: Average TPOT ≈ 10.2 ms (median: 10.0 ms, p99: 13.0 ms)
- **k=32**: Average TPOT ≈ 10.5 ms (median: 10.0 ms, p99: 13.0 ms)
- **k=64**: Average TPOT ≈ 10.5 ms (median: 10.0 ms, p99: 13.0 ms)
- **k=128**: Average TPOT ≈ 10.6 ms (median: 10.0 ms, p99: 13.0 ms)

**Analysis**: TPOT remains remarkably constant at ~10-12ms per token across all k values. This demonstrates excellent autoregressive decode efficiency in vLLM: each token takes the same time to generate regardless of the total number of tokens in the request. The slight decrease from k=2 to k=8-128 (~11.9ms → ~10.5ms) suggests minor amortization of fixed per-request overhead across more tokens.

### 3. Per-Turn TTFT Patterns

From the TTFT vs Turn plots (for various k values, excluding warm-up):

- TTFT remains relatively constant across turns (~13-20ms) for all k values
- No significant upward trend as context grows from turn 2 to turn 100
- Low variance between turns (p99 - median typically < 10ms)

**Analysis**: Despite context growing from a few tokens to ~500 tokens over 100 turns, TTFT shows minimal growth. For small contexts (< 500 tokens), prefill time is dominated by **fixed overhead** (kernel launch, memory access patterns) rather than actual attention computation. This indicates that for short-context agentic interactions, prefill latency is effectively constant.

### 4. Per-Turn TPOT Patterns

From the TPOT vs Turn plots (for k > 1, excluding warm-up):

- TPOT remains constant across all turns (~10-12ms per token)
- No dependence on turn number or growing context
- Very stable performance with low variance

**Analysis**: TPOT is determined by the autoregressive decode process, which generates one token at a time attending to the full context. The constant TPOT across turns confirms that vLLM efficiently handles the growing KV cache without decode latency degradation for contexts up to ~500 tokens.

## Performance Characteristics

1. **Prefill Efficiency**: Sub-linear scaling of TTFT with context size for small contexts (< 500 tokens)
2. **Decode Efficiency**: Constant TPOT (~10-12ms/token) independent of output length or context size
3. **Predictable Latency**: Low variance in both TTFT and TPOT across turns, enabling reliable latency SLOs
4. **Cold Start Overhead**: First request adds ~72ms overhead (86ms vs 14ms), important for real-world deployments

## Implications for Agentic Systems

1. **Context Sharing**: For small contexts (< 500 tokens), agents can share substantial context with minimal prefill overhead
2. **Output Length**: Agents can generate longer outputs (larger k) with predictable linear cost (10-12ms per token)
3. **Turn Latency**: Per-turn latency = TTFT + (k × TPOT) ≈ 15ms + (k × 10ms) for steady-state
4. **Warm-up Strategy**: Systems should implement a warm-up request to avoid cold start penalties in latency-critical paths

## Units and Conventions

- **Milliseconds**: All TTFT/TPOT values are in milliseconds for better readability
- **Warm-up Exclusion**: Turn 1 excluded from aggregates to focus on steady-state performance
- **k=1 TPOT**: Excluded from TPOT plots as TPOT is not meaningful for single-token outputs

