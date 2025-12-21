import time
import jax
import jax.numpy as jnp
import pandas as pd
import numpy as np
from dataclasses import replace
from temper_placer.optimizer.train import train
from temper_placer.optimizer.config import OptimizerConfig, JiggleConfig
from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Netlist, Net
from temper_placer.losses.base import CompositeLoss, LossContext, WeightedLoss
from temper_placer.losses.overlap import OverlapLoss
from temper_placer.losses.boundary import BoundaryLoss
from temper_placer.losses.wirelength import WirelengthLoss

def run_jiggle_trial(
    threshold: float,
    sigma_fraction: float,
    min_epoch: int,
    seed: int = 0
):
    # Deadlock scenario: 3 components at same location
    # Pull them together with wirelength, force them apart with overlap
    c1 = Component(ref="C1", footprint="F", bounds=(10, 10), fixed=False, initial_position=(50.0, 50.0))
    c2 = Component(ref="C2", footprint="F", bounds=(10, 10), fixed=False, initial_position=(50.0, 50.0))
    c3 = Component(ref="C3", footprint="F", bounds=(10, 10), fixed=False, initial_position=(50.0, 50.0))
    
    netlist = Netlist(components=[c1, c2, c3])
    board = Board(width=100, height=100)
    
    # Net pulls them to center
    nets = [Net(name="S", pins=[("C1", "1"), ("C2", "1"), ("C3", "1")])]
    netlist.nets = nets
    netlist.build_indices()
    
    composite = CompositeLoss([
        WeightedLoss(OverlapLoss(margin=0.5), weight=10.0), # Low overlap weight
        WeightedLoss(WirelengthLoss(), weight=100.0),      # High wirelength pull
        WeightedLoss(BoundaryLoss(), weight=50.0),
    ])
    
    context = LossContext.from_netlist_and_board(netlist, board)
    
    config = OptimizerConfig(
        epochs=1000,
        seed=seed,
        jiggle=JiggleConfig(
            enabled=True,
            ema_threshold=threshold,
            sigma_fraction=sigma_fraction,
            min_epoch=min_epoch
        ),
        early_stopping=replace(OptimizerConfig().early_stopping, enabled=True, patience=100),
        checkpoint=replace(OptimizerConfig().checkpoint, enabled=False),
        validate_interval=1500
    )
    
    result = train(netlist, board, composite, context, config)
    
    # Measure success
    last_overlap = result.history[-1].loss_breakdown.get("overlap", 0.0)
    resolved = last_overlap < 1e-3
    
    return {
        "threshold": threshold,
        "sigma": sigma_fraction,
        "min_epoch": min_epoch,
        "resolved": resolved,
        "epochs": result.total_epochs,
        "final_overlap": last_overlap
    }

def main():
    print("Starting Jiggle Hyperparameter Tuning...")
    results = []
    
    # 1. Sigma Sweep
    for sigma in [0.05, 0.10, 0.15, 0.20]:
        print(f"  Testing sigma_fraction={sigma}...")
        for seed in range(10):
            res = run_jiggle_trial(threshold=1e-4, sigma_fraction=sigma, min_epoch=100, seed=seed)
            res["experiment"] = "sigma"
            results.append(res)
            
    # 2. Threshold Sweep
    for threshold in [1e-3, 1e-4, 1e-5]:
        print(f"  Testing threshold={threshold}...")
        for seed in range(10):
            res = run_jiggle_trial(threshold=threshold, sigma_fraction=0.15, min_epoch=100, seed=seed)
            res["experiment"] = "threshold"
            results.append(res)

    df = pd.DataFrame(results)
    
    print("\nSummary by Sigma:")
    print(df[df.experiment == "sigma"].groupby("sigma")[["epochs", "resolved", "final_overlap"]].mean())
    
    print("\nSummary by Threshold:")
    print(df[df.experiment == "threshold"].groupby("threshold")[["epochs", "resolved", "final_overlap"]].mean())
            
    df = pd.DataFrame(results)
    print("\nSummary by Sigma:")
    print(df.groupby("sigma")[["epochs", "resolved", "final_overlap"]].mean())

if __name__ == "__main__":
    main()
