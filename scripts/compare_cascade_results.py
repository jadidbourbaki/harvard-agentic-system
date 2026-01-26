#!/usr/bin/env python3
"""Compare baseline and Orla cascade experiment results with statistics from multiple runs."""

import json
import sys
import statistics
from pathlib import Path

def load_runs(pattern):
    """Load all JSON files matching the pattern and return list of data.
    Skips run 1 (warmup) and only loads runs 2-4 for statistics."""
    results = []
    base_dir = Path('output/cascade')
    # Load runs 2, 3, 4 (skip run 1 as warmup)
    for i in range(2, 5):
        file_path = base_dir / pattern.format(i)
        if file_path.exists():
            try:
                with open(file_path) as f:
                    results.append(json.load(f))
            except Exception as e:
                print(f"Warning: Could not load {file_path}: {e}", file=sys.stderr)
    return results

def calculate_stats(values):
    """Calculate mean and std dev for a list of values."""
    if not values:
        return 0, 0
    if len(values) == 1:
        return values[0], 0
    return statistics.mean(values), statistics.stdev(values) if len(values) > 1 else 0

def main():
    baseline_runs = load_runs('baseline_{}.json')
    orla_runs = load_runs('orla_{}.json')
    ollama_baseline_runs = load_runs('ollama_baseline_{}.json')
    ollama_runs = load_runs('ollama_{}.json')
    
    if not baseline_runs or not orla_runs:
        print("Error: Could not find all required result files.", file=sys.stderr)
        print("Expected: baseline_2.json, baseline_3.json, baseline_4.json (runs 2-4, skipping warmup run 1)", file=sys.stderr)
        print("          orla_2.json, orla_3.json, orla_4.json (runs 2-4, skipping warmup run 1)", file=sys.stderr)
        if ollama_baseline_runs:
            print("          ollama_baseline_2.json, ollama_baseline_3.json, ollama_baseline_4.json (optional)", file=sys.stderr)
        if ollama_runs:
            print("          ollama_2.json, ollama_3.json, ollama_4.json (optional)", file=sys.stderr)
        sys.exit(1)
    
    # Extract metrics from all runs
    baseline_totals = [r.get('total_time_seconds', 0) for r in baseline_runs]
    orla_totals = [r.get('total_time_seconds', 0) for r in orla_runs]
    ollama_baseline_totals = [r.get('total_time_seconds', 0) for r in ollama_baseline_runs] if ollama_baseline_runs else []
    ollama_totals = [r.get('total_time_seconds', 0) for r in ollama_runs] if ollama_runs else []
    baseline_analysis = [r.get('avg_analysis_ms', 0) for r in baseline_runs]
    orla_analysis = [r.get('avg_analysis_ms', 0) for r in orla_runs]
    ollama_baseline_analysis = [r.get('avg_analysis_ms', 0) for r in ollama_baseline_runs] if ollama_baseline_runs else []
    ollama_analysis = [r.get('avg_analysis_ms', 0) for r in ollama_runs] if ollama_runs else []
    baseline_summary = [r.get('avg_summary_ms', 0) for r in baseline_runs]
    orla_summary = [r.get('avg_summary_ms', 0) for r in orla_runs]
    ollama_baseline_summary = [r.get('avg_summary_ms', 0) for r in ollama_baseline_runs] if ollama_baseline_runs else []
    ollama_summary = [r.get('avg_summary_ms', 0) for r in ollama_runs] if ollama_runs else []
    
    # Calculate statistics
    bl_total_mean, bl_total_std = calculate_stats(baseline_totals)
    orla_total_mean, orla_total_std = calculate_stats(orla_totals)
    ollama_bl_total_mean, ollama_bl_total_std = calculate_stats(ollama_baseline_totals) if ollama_baseline_totals else (0, 0)
    ollama_total_mean, ollama_total_std = calculate_stats(ollama_totals) if ollama_totals else (0, 0)
    bl_analysis_mean, bl_analysis_std = calculate_stats(baseline_analysis)
    orla_analysis_mean, orla_analysis_std = calculate_stats(orla_analysis)
    ollama_bl_analysis_mean, ollama_bl_analysis_std = calculate_stats(ollama_baseline_analysis) if ollama_baseline_analysis else (0, 0)
    ollama_analysis_mean, ollama_analysis_std = calculate_stats(ollama_analysis) if ollama_analysis else (0, 0)
    bl_summary_mean, bl_summary_std = calculate_stats(baseline_summary)
    orla_summary_mean, orla_summary_std = calculate_stats(orla_summary)
    ollama_bl_summary_mean, ollama_bl_summary_std = calculate_stats(ollama_baseline_summary) if ollama_baseline_summary else (0, 0)
    ollama_summary_mean, ollama_summary_std = calculate_stats(ollama_summary) if ollama_summary else (0, 0)
    
    if bl_total_mean > 0:
        orla_improvement = ((bl_total_mean - orla_total_mean) / bl_total_mean * 100)
        ollama_improvement = ((ollama_bl_total_mean - ollama_total_mean) / ollama_bl_total_mean * 100) if ollama_bl_total_mean > 0 and ollama_total_mean > 0 else 0
        orla_analysis_improvement = ((bl_analysis_mean - orla_analysis_mean) / bl_analysis_mean * 100) if bl_analysis_mean > 0 else 0
        ollama_analysis_improvement = ((ollama_bl_analysis_mean - ollama_analysis_mean) / ollama_bl_analysis_mean * 100) if ollama_bl_analysis_mean > 0 and ollama_analysis_mean > 0 else 0
        orla_summary_improvement = ((bl_summary_mean - orla_summary_mean) / bl_summary_mean * 100) if bl_summary_mean > 0 else 0
        ollama_summary_improvement = ((ollama_bl_summary_mean - ollama_summary_mean) / ollama_bl_summary_mean * 100) if ollama_bl_summary_mean > 0 and ollama_summary_mean > 0 else 0
        
        print('=' * 60)
        print('SGLANG RESULTS')
        print('=' * 60)
        print(f'  Baseline (SGLang) total time: {bl_total_mean:.2f}s ± {bl_total_std:.2f}s (n={len(baseline_runs)})')
        print(f'  Orla Cascade (SGLang) total time: {orla_total_mean:.2f}s ± {orla_total_std:.2f}s (n={len(orla_runs)})')
        print(f'  Orla improvement:    {orla_improvement:.1f}%')
        print('')
        print(f'  Baseline analysis:   {bl_analysis_mean:.0f}ms ± {bl_analysis_std:.0f}ms')
        print(f'  Orla analysis:       {orla_analysis_mean:.0f}ms ± {orla_analysis_std:.0f}ms')
        print(f'  Orla analysis improvement: {orla_analysis_improvement:.1f}%')
        print('')
        print(f'  Baseline summary:    {bl_summary_mean:.0f}ms ± {bl_summary_std:.0f}ms')
        print(f'  Orla summary:        {orla_summary_mean:.0f}ms ± {orla_summary_std:.0f}ms')
        print(f'  Orla summary improvement: {orla_summary_improvement:.1f}%')
        
        if ollama_bl_total_mean > 0:
            print('')
            print('=' * 60)
            print('OLLAMA RESULTS')
            print('=' * 60)
            print(f'  Baseline (Ollama) total time: {ollama_bl_total_mean:.2f}s ± {ollama_bl_total_std:.2f}s (n={len(ollama_baseline_runs)})')
            if ollama_total_mean > 0:
                print(f'  Orla Cascade (Ollama) total time: {ollama_total_mean:.2f}s ± {ollama_total_std:.2f}s (n={len(ollama_runs)})')
                print(f'  Orla improvement:    {ollama_improvement:.1f}%')
            print('')
            print(f'  Baseline analysis:   {ollama_bl_analysis_mean:.0f}ms ± {ollama_bl_analysis_std:.0f}ms')
            if ollama_analysis_mean > 0:
                print(f'  Orla analysis:       {ollama_analysis_mean:.0f}ms ± {ollama_analysis_std:.0f}ms')
                print(f'  Orla analysis improvement: {ollama_analysis_improvement:.1f}%')
            print('')
            print(f'  Baseline summary:    {ollama_bl_summary_mean:.0f}ms ± {ollama_bl_summary_std:.0f}ms')
            if ollama_summary_mean > 0:
                print(f'  Orla summary:        {ollama_summary_mean:.0f}ms ± {ollama_summary_std:.0f}ms')
                print(f'  Orla summary improvement: {ollama_summary_improvement:.1f}%')
        
        # Save results to JSON file for plotting
        output_dir = Path('output/cascade')
        output_file = output_dir / 'comparison_results.json'
        
        results_data = {
            'sglang': {
                'baseline': {
                    'total_time': {'mean': bl_total_mean, 'std': bl_total_std, 'n': len(baseline_runs)},
                    'analysis': {'mean': bl_analysis_mean, 'std': bl_analysis_std, 'n': len(baseline_runs)},
                    'summary': {'mean': bl_summary_mean, 'std': bl_summary_std, 'n': len(baseline_runs)},
                },
                'cascade': {
                    'total_time': {'mean': orla_total_mean, 'std': orla_total_std, 'n': len(orla_runs)},
                    'analysis': {'mean': orla_analysis_mean, 'std': orla_analysis_std, 'n': len(orla_runs)},
                    'summary': {'mean': orla_summary_mean, 'std': orla_summary_std, 'n': len(orla_runs)},
                    'improvements': {
                        'total_time': orla_improvement,
                        'analysis': orla_analysis_improvement,
                        'summary': orla_summary_improvement,
                    }
                }
            }
        }
        
        if ollama_bl_total_mean > 0:
            results_data['ollama'] = {
                'baseline': {
                    'total_time': {'mean': ollama_bl_total_mean, 'std': ollama_bl_total_std, 'n': len(ollama_baseline_runs)},
                    'analysis': {'mean': ollama_bl_analysis_mean, 'std': ollama_bl_analysis_std, 'n': len(ollama_baseline_runs)},
                    'summary': {'mean': ollama_bl_summary_mean, 'std': ollama_bl_summary_std, 'n': len(ollama_baseline_runs)},
                }
            }
            if ollama_total_mean > 0:
                results_data['ollama']['cascade'] = {
                    'total_time': {'mean': ollama_total_mean, 'std': ollama_total_std, 'n': len(ollama_runs)},
                    'analysis': {'mean': ollama_analysis_mean, 'std': ollama_analysis_std, 'n': len(ollama_runs)},
                    'summary': {'mean': ollama_summary_mean, 'std': ollama_summary_std, 'n': len(ollama_runs)},
                    'improvements': {
                        'total_time': ollama_improvement,
                        'analysis': ollama_analysis_improvement,
                        'summary': ollama_summary_improvement,
                    }
                }
        
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            with open(output_file, 'w') as f:
                json.dump(results_data, f, indent=2)
            print('')
            print(f'Results saved to {output_file} for plotting')
        except Exception as e:
            print(f'Warning: Could not save results to {output_file}: {e}', file=sys.stderr)

if __name__ == '__main__':
    main()
