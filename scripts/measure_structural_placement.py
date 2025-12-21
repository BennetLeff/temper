
import argparse
import logging
import time
from pathlib import Path
from dataclasses import replace

import jax
import jax.numpy as jnp
import pandas as pd

from temper_placer.core.netlist import Netlist
from temper_placer.core.board import Board
from temper_placer.io.config_loader import (
    load_constraints, 
    PlacementConstraints, 
    create_board_from_constraints
)
from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.optimizer.config import OptimizerConfig
from temper_placer.optimizer.train import train_multiphase
from temper_placer.optimizer.postprocess import PostProcessConfig, postprocess
from temper_placer.losses.base import CompositeLoss, LossContext, WeightedLoss
from temper_placer.losses.aesthetic import create_aesthetic_losses
from temper_placer.losses.overlap import OverlapLoss
from temper_placer.losses.boundary import BoundaryLoss
from temper_placer.losses.wirelength import WirelengthLoss

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_experiment(
    netlist: Netlist, 
    constraints: PlacementConstraints, 
    config: OptimizerConfig,
    post_config: PostProcessConfig,
    seed: int = 0
):
    start_time = time.time()
    
    # Create board
    board = create_board_from_constraints(constraints)
    
    # Create Context
    context = LossContext.from_netlist_and_board(netlist, board)
    
    # Loss factory for curriculum
    def loss_factory(weights: dict[str, float]) -> CompositeLoss:
        losses = []
        if "overlap" in weights:
            losses.append(WeightedLoss(OverlapLoss(rotation_invariant=True), weight=weights["overlap"]))
        if "boundary" in weights:
            losses.append(WeightedLoss(BoundaryLoss(), weight=weights["boundary"]))
        if "wirelength" in weights:
            losses.append(WeightedLoss(WirelengthLoss(), weight=weights["wirelength"]))
            
        # Add aesthetic losses (structural)
        aesthetic_losses = create_aesthetic_losses(netlist, constraints)
        losses.extend(aesthetic_losses)
        
        return CompositeLoss(losses)
    
    # Run optimization
    result = train_multiphase(
        netlist=netlist,
        board=board,
        loss_factory=loss_factory,
        context=context,
        config=config,
    )
    
    duration = time.time() - start_time
    
    return {
        "final_loss": float(result.final_loss),
        "duration": duration,
        "converged": result.converged,
        "result": result
    }

def main():
    parser = argparse.ArgumentParser(description="Structural Placement Measurement Suite")
    parser.add_argument("pcb_file", type=Path, help="Path to KiCad PCB file")
    parser.add_argument("config_file", type=Path, help="Path to constraints YAML")
    parser.add_argument("--seeds", type=int, default=3, help="Number of seeds per experiment")
    parser.add_argument("--output", type=Path, default="structural_metrics.csv", help="CSV output path")
    args = parser.parse_args()
    
    logger.info(f"Loading {args.pcb_file}...")
    parse_res = parse_kicad_pcb(args.pcb_file)
    netlist = parse_res.netlist
    
    # Base Optimizer Config
    base_opt_config = OptimizerConfig(
        epochs=1000, # Faster for measurement
        seed=42,
        use_gumbel_rotation=True,
    )
    # Ensure some curriculum exists or use default
    base_opt_config = OptimizerConfig.default_curriculum()
    base_opt_config.epochs = 1000 # Override for speed
    
    # Base PostProcess Config
    base_post_config = PostProcessConfig(
        rotation_refinement_enabled=True,
        rotation_search_type="greedy"
    )
    
    experiments = [
        ("Baseline", {}),
        ("PortFacing", {"port_facing": True}),
        ("StackedRow", {"stacked_layout": True}),
        ("ForceDirected", {"force_directed": True}),
        ("SA_Refinement", {"search_type": "sa"}),
        ("Full_Structural", {
            "port_facing": True, 
            "stacked_layout": True,
            "force_directed": True,
            "search_type": "sa"
        })
    ]
    
    all_results = []
    
    for exp_name, flags in experiments:
        logger.info(f"=== Experiment: {exp_name} ===")
        
        # Setup Optimizer Config
        exp_opt_config = replace(base_opt_config)
        if flags.get("force_directed"):
            # Enable force-directed unfolding
            exp_opt_config.initialization = replace(exp_opt_config.initialization,
                force_directed=replace(exp_opt_config.initialization.force_directed, enabled=True)
            )
        
        # Setup PostProcess Config
        exp_post_config = replace(base_post_config, 
            rotation_search_type=flags.get("search_type", "greedy")
        )
        
        for seed in range(args.seeds):
            logger.info(f"  Seed {seed}...")
            
            # Setup constraints for this seed (clean copy)
            exp_constraints = load_constraints(args.config_file)
            
            if not flags.get("port_facing"):
                # Disable Port Facing
                for g in exp_constraints.component_groups:
                    g.primary_pin = None
            
            if not flags.get("stacked_layout"):
                # Disable Stacked Layout
                for g in exp_constraints.component_groups:
                    g.stacked_layout = False
            
            res = run_experiment(netlist, exp_constraints, exp_opt_config, exp_post_config, seed=seed)
            
            all_results.append({
                "experiment": exp_name,
                "seed": seed,
                "loss": res["final_loss"],
                "duration": res["duration"],
                "converged": res["converged"]
            })
            
    df = pd.DataFrame(all_results)
    df.to_csv(args.output, index=False)
    
    print("\nResults Summary:")
    summary = df.groupby("experiment")["loss"].agg(["mean", "std", "min"]).round(4)
    print(summary)
    
    logger.info(f"Full results saved to {args.output}")

if __name__ == "__main__":
    main()
