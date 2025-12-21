
import time
import jax
import jax.numpy as jnp
import pandas as pd
from pathlib import Path
from dataclasses import replace

from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.io.config_loader import load_constraints, create_board_from_constraints
from temper_placer.optimizer.config import OptimizerConfig
from temper_placer.optimizer.train import train_multiphase
from temper_placer.optimizer.nsga2 import NSGAOptimizer
from temper_placer.losses.base import CompositeLoss, LossContext, WeightedLoss
from temper_placer.losses.wirelength import WirelengthLoss
from temper_placer.losses.thermal import EdgePreferenceLoss
from temper_placer.losses.overlap import OverlapLoss

def run_gd(netlist, board, constraints, context, weights, seed=42):
    def loss_factory(w):
        return CompositeLoss([
            WeightedLoss(OverlapLoss(), weight=w.get("overlap", 100.0)),
            WeightedLoss(WirelengthLoss(), weight=w.get("wirelength", 10.0)),
            WeightedLoss(EdgePreferenceLoss(
                thermal_pad_indices=jnp.array([0]), # Assume U1
                board_width=board.width,
                board_height=board.height
            ), weight=w.get("thermal", 1.0))
        ])
    
    config = OptimizerConfig(epochs=500, seed=seed)
    return train_multiphase(netlist, board, loss_factory, context, config)

def run_nsga(netlist, board, constraints, context, seed=42):
    objectives = [
        OverlapLoss(),
        WirelengthLoss(),
        EdgePreferenceLoss(
            thermal_pad_indices=jnp.array([0]),
            board_width=board.width,
            board_height=board.height
        )
    ]
    
    optimizer = NSGAOptimizer(population_size=40)
    return optimizer.evolve(netlist, board, objectives, context, generations=50, seed=seed)

def main():
    pcb_path = Path("packages/temper-placer/tests/fixtures/minimal_board.kicad_pcb")
    parse_res = parse_kicad_pcb(pcb_path)
    netlist = parse_res.netlist
    board = parse_res.board
    constraints = load_constraints(Path("packages/temper-placer/tests/fixtures/constraints_minimal.yaml"))
    context = LossContext.from_netlist_and_board(netlist, board)
    
    print("Running Baseline GD (Manual weights: wl=10, thermal=1)...")
    res_gd = run_gd(netlist, board, constraints, context, {"wirelength": 10.0, "thermal": 1.0})
    
    print("Running NSGA-II (No weights)...")
    res_nsga = run_nsga(netlist, board, constraints, context)
    
    # 1. Compare best wl solution from NSGA vs GD
    # 2. Compare best thermal solution from NSGA vs GD
    
    nsga_objs = res_nsga.objectives[jnp.array(res_nsga.best_indices)]
    
    # NSGA best WL
    best_wl_idx = jnp.argmin(nsga_objs[:, 1])
    nsga_best_wl = nsga_objs[best_wl_idx, 1]
    
    # NSGA best thermal
    best_th_idx = jnp.argmin(nsga_objs[:, 2])
    nsga_best_th = nsga_objs[best_th_idx, 2]
    
    print(f"\nGD (manual): WL={res_gd.history[-1].loss_breakdown.get('wirelength', 0):.2f}, "
          f"Thermal={res_gd.history[-1].loss_breakdown.get('edge_preference', 0):.2f}")
    
    print(f"NSGA (best WL): WL={nsga_best_wl:.2f}, Thermal={nsga_objs[best_wl_idx, 2]:.2f}")
    print(f"NSGA (best Thermal): WL={nsga_objs[best_th_idx, 1]:.2f}, Thermal={nsga_best_th:.2f}")
    
    print(f"\nPareto front found {len(res_nsga.best_indices)} distinct solutions.")
    
    # Improvement verification:
    # NSGA should find at least one solution that is better than GD in at least one objective
    # without being much worse in the others.
    
    # Check if any NSGA solution dominates GD result
    gd_vals = jnp.array([
        res_gd.history[-1].loss_breakdown.get('overlap', 0),
        res_gd.history[-1].loss_breakdown.get('wirelength', 0),
        res_gd.history[-1].loss_breakdown.get('edge_preference', 0)
    ])
    
    better_count = 0
    for i in range(len(nsga_objs)):
        diff = nsga_objs[i] - gd_vals
        if jnp.all(diff <= 0) and jnp.any(diff < 0):
            better_count += 1
            
    print(f"\n{better_count} NSGA solutions strictly dominate the manual GD solution!")

if __name__ == "__main__":
    main()
