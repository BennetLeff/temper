"""
Steiner vs HPWL Analysis Script (temper-eao)

Correlates HPWL and Steiner Tree wirelength estimations with actual
maze-routed wirelength to determine which is a better predictor of 
final routing outcomes.
"""

from __future__ import annotations

import jax
import jax.numpy as jnp
import numpy as np
from pathlib import Path
import sys
import time

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "packages" / "temper-placer" / "src"))

from temper_placer.core.netlist import build_adjacency_matrix
from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.losses.wirelength import WirelengthLoss, SteinerTreeLoss
from temper_placer.routing.verifier import RoutingVerifier, RoutingVerifierConfig, VerificationLevel
from temper_placer.losses.base import LossContext
from temper_placer.core.loop import LoopCollection

def run_analysis(pcb_path: Path, n_samples: int = 10):
    print(f"Loading PCB: {pcb_path}")
    parse_result = parse_kicad_pcb(pcb_path)
    netlist = parse_result.netlist
    board = parse_result.board
    
    context = LossContext.from_netlist_and_board(netlist, board)
    loops = LoopCollection(loops=[])
    
    hpwl_fn = WirelengthLoss()
    steiner_fn = SteinerTreeLoss()
    
    verifier_config = RoutingVerifierConfig(
        level=VerificationLevel.MAZE,
        cell_size_mm=1.0
    )
    verifier = RoutingVerifier(verifier_config)
    
    data = {
        "hpwl": [],
        "steiner": [],
        "actual": [],
        "completion": []
    }
    
    rng = np.random.default_rng(42)
    
    print(f"Running {n_samples} random placements...")
    for i in range(n_samples):
        # Generate random placement
        pos = rng.uniform(
            low=[board.origin[0], board.origin[1]],
            high=[board.origin[0] + board.width, board.origin[1] + board.height],
            size=(netlist.n_components, 2)
        )
        pos_jax = jnp.array(pos)
        rot_jax = jnp.zeros((netlist.n_components, 4)) # Standard rotation
        
        # 1. Compute HPWL
        hpwl = float(hpwl_fn(pos_jax, rot_jax, context).value)
        
        # 2. Compute Steiner
        steiner = float(steiner_fn(pos_jax, rot_jax, context).value)
        
        # 3. Compute Actual (Maze)
        print(f"  [{i+1}/{n_samples}] Routing...", end="", flush=True)
        t0 = time.time()
        result = verifier.verify(netlist, pos_jax, board, loops)
        t1 = time.time()
        print(f" done ({t1-t0:.1f}s)")
        
        data["hpwl"].append(hpwl)
        data["steiner"].append(steiner)
        data["actual"].append(result.total_wirelength)
        data["completion"].append(result.completion_rate)
        
    # Correlation Analysis
    hpwl_corr = np.corrcoef(data["hpwl"], data["actual"])[0, 1]
    steiner_corr = np.corrcoef(data["steiner"], data["actual"])[0, 1]
    
    print("\n" + "="*40)
    print("WIRELENGTH ESTIMATION ANALYSIS")
    print("="*40)
    print(f"HPWL vs Actual Correlation:    {hpwl_corr:.4f}")
    print(f"Steiner vs Actual Correlation: {steiner_corr:.4f}")
    print("-" * 40)
    
    if steiner_corr > hpwl_corr:
        improvement = (steiner_corr - hpwl_corr) / abs(hpwl_corr) * 100
        print(f"Steiner is BETTER by {improvement:.1f}%")
    else:
        print("HPWL is surprisingly better (or tied).")
        
    # Save results
    report_path = Path("STEINER_ANALYSIS_REPORT.md")
    with open(report_path, "w") as f:
        f.write("# Steiner vs HPWL Correlation Analysis\n\n")
        f.write(f"**PCB**: {pcb_path.name}\n")
        f.write(f"**Samples**: {n_samples}\n\n")
        f.write("## Results\n")
        f.write(f"- **HPWL Correlation**: {hpwl_corr:.4f}\n")
        f.write(f"- **Steiner Correlation**: {steiner_corr:.4f}\n\n")
        f.write("## Conclusion\n")
        if steiner_corr > hpwl_corr:
            f.write("Steiner Tree models provide a significantly higher fidelity estimation of actual routed length compared to HPWL. It is recommended to use SteinerTreeLoss for performance-critical layouts.\n")
        else:
            f.write("HPWL performed well on this specific design. Further investigation on larger designs is recommended.\n")

    print(f"\nReport saved to {report_path}")

if __name__ == "__main__":
    test_pcb = Path("kicad-tutorials-a/07_Transistor_Switch/07_Transistor_Switch.kicad_pcb")
    if not test_pcb.exists():
        print(f"Error: {test_pcb} not found")
        sys.exit(1)
    run_analysis(test_pcb, n_samples=5)
