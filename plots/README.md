# Orla Evaluation Plots

This directory contains scripts to generate SOSP-style plots from the evaluation results.

## Setup

Using `uv` (recommended):

```bash
cd plots
uv sync
```

Or using `pip`:

```bash
cd plots
pip install -e .
```

## Usage

```bash
python generate_plots.py
```

This will generate three plots in the `plots` directory:

1. **end_to_end_comparison.pdf/png**: Bar chart comparing end-to-end times for Datacenter Serving (SGLang vs Orla) and Edge Serving (Ollama vs Orla)

2. **sglang_cumulative.pdf/png**: Line plot showing cumulative time per task for SGLang baseline vs Orla

3. **ollama_cumulative.pdf/png**: Line plot showing cumulative time per task for Ollama baseline vs Orla

All plots are saved in both PDF (for paper) and PNG (for preview) formats.

## Dependencies

- matplotlib >= 3.7.0
- numpy >= 1.24.0
- scipy >= 1.10.0
