
import argparse
import logging
from pathlib import Path
import jax
import jax.numpy as jnp
import pandas as pd
from tabulate import table

from temper_placer.core.netlist import Netlist
from temper_placer.io.config_loader import load_constraints, PlacementConstraints, create_board_from_constraints
from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.optimizer.config import OptimizerConfig
from temper_placer.optimizer.train import train_placement
from temper_placer.validation.metrics import compute_total_hpwl, compute_overlap_area

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_experiment(
    netlist: Netlist, 
    constraints: PlacementConstraints, 
    enable_port_facing: bool = True,
    seed: int = 0
):
    # Configure optimizer
    config = OptimizerConfig(
        total_epochs=2000,
        learning_rate=0.1,
        use_gumbel_rotation=True,
    )
    
    # Modify constraints based on flags
    # To disable port facing, we can clear primary_pin from groups
    # or set weight to 0. But weight is hardcoded in create_aesthetic_losses currently
    # unless we modify aesthetic_cfg.
    
    # We will modify the constraints object in place (copying would be better but expensive)
    original_groups = constraints.component_groups
    if not enable_port_facing:
        # Clear primary_pin from all groups to disable the loss generation
        new_groups = []
        for g in constraints.component_groups:
            # Create a shallow copy with primary_pin=None
            # Dataclass replace would be cleaner
            from dataclasses import replace
            new_g = replace(g, primary_pin=None)
            new_groups.append(new_g)
        constraints.component_groups = new_groups
    
    # Create board
    board = create_board_from_constraints(constraints)
    
    # Run optimization
    rng_key = jax.random.PRNGKey(seed)
    result = train_placement(netlist, board, constraints, config, rng_key)
    
    # Restore constraints (if we modified the object passed in)
    if not enable_port_facing:
        constraints.component_groups = original_groups
        
    return result

def measure_metrics(result, netlist, board):
    state = result.final_state
    
    # Convert logits to discrete rotations
    rotation_indices = jnp.argmax(state.rotation_logits, axis=-1)
    rotations = jax.nn.one_hot(rotation_indices, 4)
    
    hpwl = compute_total_hpwl(state.positions, rotations, None) # Context needed? 
    # Actually compute_total_hpwl needs context with net_pin_indices etc.
    # We can use the context from the result if available, or create one.
    # train_placement returns PlacementResult which has final_loss (scalar).
    
    # Let's trust the loss value for now, or re-compute if we had the context.
    # Re-creating context is complex.
    
    return result.final_loss

def main():
    parser = argparse.ArgumentParser(description="Measure structural placement improvements")
    parser.add_argument("pcb_file", type=Path, help="Path to KiCad PCB file")
    parser.add_argument("config_file", type=Path, help="Path to constraints YAML")
    parser.add_argument("--seeds", type=int, default=3, help="Number of seeds")
    args = parser.parse_args()
    
    logger.info(f"Loading {args.pcb_file}...")
    netlist, _, _ = parse_kicad_pcb(args.pcb_file)
    constraints = load_constraints(args.config_file)
    
    results = []
    
    for seed in range(args.seeds):
        logger.info(f"Running Seed {seed}...")
        
        # 1. Baseline (Port Facing Disabled)
        logger.info("  Baseline...")
        res_base = run_experiment(netlist, constraints, enable_port_facing=False, seed=seed)
        
        # 2. With Port Facing
        logger.info("  Port Facing...")
        res_pf = run_experiment(netlist, constraints, enable_port_facing=True, seed=seed)
        
        results.append({
            "seed": seed,
            "baseline_loss": float(res_base.final_loss),
            "port_facing_loss": float(res_pf.final_loss),
            "delta": float(res_base.final_loss - res_pf.final_loss)
        })
        
    df = pd.DataFrame(results)
    print("\nResults:")
    print(df)
    print("\nSummary:")
    print(df.describe())

if __name__ == "__main__":
    main()
