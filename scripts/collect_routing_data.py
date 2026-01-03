"""
Script to collect routing completion data for placement optimization.
Target: temper-u6m4.5.1
"""

import os
import time
import json
import logging
from pathlib import Path
from temper_placer.io import parse_kicad_pcb, load_constraints, export_placements
from temper_placer.losses import (
    BoundaryLoss, CompositeLoss, OverlapLoss, 
    RoutabilityLoss, SpreadLoss, WeightedLoss, WirelengthLoss,
    GroupClusterLoss, GroupConfig
)
from temper_placer.losses.base import LossContext
from temper_placer.optimizer import OptimizerConfig, train
from temper_placer.routing.routing_analyzer import RoutingAnalyzer, RoutingAnalyzerConfig
import jax.numpy as jnp

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_experiment(seed: int, epochs: int = 1000):
    input_pcb = Path("pcb/temper.kicad_pcb")
    config_path = Path("packages/temper-placer/configs/temper_constraints.yaml")
    output_dir = Path("experiments/routing_data")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. Setup
    res = parse_kicad_pcb(input_pcb)
    netlist = res.netlist
    board_from_pcb = res.board
    constraints = load_constraints(config_path)
    board = board_from_pcb # Use board from PCB for consistency
    ctx = LossContext.from_netlist_and_board(netlist, board)
    
    # 2. Simple Composite Loss (matching baseline)
    weights = {"overlap": 100.0, "boundary": 50.0, "wirelength": 10.0, "congestion": 5.0}
    
    def make_loss(w):
        losses = [
            WeightedLoss(OverlapLoss(margin=2.0), weight=w["overlap"]),
            WeightedLoss(BoundaryLoss(), weight=w["boundary"]),
            WeightedLoss(WirelengthLoss(), weight=w["wirelength"]),
            WeightedLoss(RoutabilityLoss(), weight=w["congestion"]),
        ]
        return CompositeLoss(losses)
    
    composite = make_loss(weights)
    cfg = OptimizerConfig(epochs=epochs, seed=seed, log_interval=epochs)
    
    # 3. Optimize
    logger.info(f"Seed {seed}: Starting placement...")
    result = train(netlist, board, composite, ctx, cfg)
    
    # 4. Export
    output_pcb = output_dir / f"temper_seed_{seed}.kicad_pcb"
    export_placements(input_pcb, output_pcb, result.best_state, [c.ref for c in netlist.components])
    
    # 5. Analyze Routing
    logger.info(f"Seed {seed}: Starting autorouter...")
    analyzer = RoutingAnalyzer(RoutingAnalyzerConfig(verbose=True))
    routing_res = analyzer.analyze(output_pcb)
    
    return {
        "seed": seed,
        "completion": routing_res.completion_rate,
        "wirelength": routing_res.total_wirelength_mm,
        "vias": routing_res.via_count,
        "success": routing_res.success,
        "unrouted": routing_res.unrouted_nets
    }

def main():
    results = []
    for i in range(5): # Start with 5 for quick baseline
        try:
            res = run_experiment(seed=42 + i)
            results.append(res)
            logger.info(f"Result: {res['completion']*100:.1f}% completion")
        except Exception as e:
            logger.error(f"Failed seed {42+i}: {e}")
            
    with open("experiments/routing_data/summary.json", "w") as f:
        json.dump(results, f, indent=2)

if __name__ == "__main__":
    main()
