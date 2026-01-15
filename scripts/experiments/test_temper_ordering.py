from pathlib import Path
from temper_placer.router_v6.pipeline import RouterV6Pipeline

def run_temper_with_ordering():
    pcb_path = Path("pre_routed_v5.kicad_pcb")
    
    # 1. Baseline: Standard Heuristic Ordering
    print("\n=== Running Baseline (Heuristic Ordering) ===")
    pipeline_base = RouterV6Pipeline(
        verbose=True,
        enable_topological_ordering=False,
        enable_legalization=True,
        max_nets=None
    )
    result_base = pipeline_base.run(pcb_path)
    
    # 2. Optimized: Topological Ordering
    print("\n=== Running Optimized (Topological Ordering) ===")
    pipeline_opt = RouterV6Pipeline(
        verbose=True,
        enable_topological_ordering=True,
        enable_legalization=True,
        max_nets=None
    )
    result_opt = pipeline_opt.run(pcb_path)
    
    # Compare Results
    print("\n=== Final Comparison ===")
    print(f"Baseline Completion: {result_base.completion_rate*100:.1f}% ({result_base.success_count}/{result_base.success_count + result_base.failure_count})")
    print(f"Optimized Completion: {result_opt.completion_rate*100:.1f}% ({result_opt.success_count}/{result_opt.success_count + result_opt.failure_count})")

if __name__ == "__main__":
    run_temper_with_ordering()
