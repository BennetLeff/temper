#!/usr/bin/env python3.11
import json
import numpy as np
from scipy import stats

def main():
    with open("experiments/temper-a98v/full_metrics.json") as f:
        data = json.load(f)
        
    baseline = [m["routing_completion_pct"] for m in data if m["condition"] == "baseline"]
    option_a = [m["routing_completion_pct"] for m in data if m["condition"] == "option_a"]
    option_c = [m["routing_completion_pct"] for m in data if m["condition"] == "option_c"]
    
    f_stat, p_val = stats.f_oneway(baseline, option_a, option_c)
    
    print(f"One-way ANOVA for routing completion:")
    print(f"  F-statistic: {f_stat:.4f}")
    print(f"  p-value: {p_val:.4f}")
    
    # Min Edge Distance ANOVA
    baseline_dist = [m["min_edge_distance_mm"] for m in data if m["condition"] == "baseline"]
    option_a_dist = [m["min_edge_distance_mm"] for m in data if m["condition"] == "option_a"]
    option_c_dist = [m["min_edge_distance_mm"] for m in data if m["condition"] == "option_c"]
    
    f_stat_dist, p_val_dist = stats.f_oneway(baseline_dist, option_a_dist, option_c_dist)
    
    print(f"\nOne-way ANOVA for min edge distance:")
    print(f"  F-statistic: {f_stat_dist:.4f}")
    print(f"  p-value: {p_val_dist:.4f}")
    
    if p_val_dist < 0.05:
        print(">>> Significant difference detected between conditions (p < 0.05)")
    else:
        print(">>> No significant difference detected (p >= 0.05)")

if __name__ == "__main__":
    main()
