from dataclasses import replace

import pandas as pd

from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Net, Netlist
from temper_placer.losses.base import CompositeLoss, LossContext, WeightedLoss
from temper_placer.losses.boundary import BoundaryLoss
from temper_placer.losses.overlap import OverlapLoss
from temper_placer.losses.wirelength import WirelengthLoss
from temper_placer.optimizer.config import AdaptiveOverlapConfig, OptimizerConfig
from temper_placer.optimizer.train import train


def run_tuning_trial(
    ramp_rate: float,
    max_cap: float,
    update_interval: int,
    threshold: float,
    seed: int = 0
):
    # Harder scenario: 5 component sandwich
    components = [
        Component(ref="C1", footprint="F", bounds=(10, 10), fixed=True, initial_position=(40.0, 50.0)),
        Component(ref="C2", footprint="F", bounds=(10, 10), fixed=False, initial_position=(45.0, 50.0)),
        Component(ref="C3", footprint="F", bounds=(10, 10), fixed=False, initial_position=(50.0, 50.0)),
        Component(ref="C4", footprint="F", bounds=(10, 10), fixed=False, initial_position=(55.0, 50.0)),
        Component(ref="C5", footprint="F", bounds=(10, 10), fixed=True, initial_position=(60.0, 50.0)),
    ]

    netlist = Netlist(components=components)
    board = Board(width=100, height=100)

    nets = [
        Net(name="SANDWICH", pins=[("C1", "1"), ("C2", "1"), ("C3", "1"), ("C4", "1"), ("C5", "1")]),
    ]
    netlist.nets = nets
    netlist.build_indices()

    composite = CompositeLoss([
        WeightedLoss(OverlapLoss(margin=0.5), weight=1.0), # Low baseline
        WeightedLoss(WirelengthLoss(), weight=1000.0), # Strong pull to center!
        WeightedLoss(BoundaryLoss(), weight=50.0),
    ])

    context = LossContext.from_netlist_and_board(netlist, board)

    config = OptimizerConfig(
        epochs=2000,
        seed=seed,
        adaptive_overlap=AdaptiveOverlapConfig(
            enabled=True,
            ramp_rate=ramp_rate,
            max_cap=max_cap,
            update_interval=update_interval,
            collision_threshold=threshold
        ),
        early_stopping=replace(OptimizerConfig().early_stopping, enabled=True, patience=200),
        checkpoint=replace(OptimizerConfig().checkpoint, enabled=False),
        validate_interval=2500
    )

    result = train(netlist, board, composite, context, config)

    last_overlap = result.history[-1].loss_breakdown.get("overlap", 0.0)
    resolved = last_overlap < 1e-3

    return {
        "ramp_rate": ramp_rate,
        "max_cap": max_cap,
        "resolved": resolved,
        "epochs": result.total_epochs,
        "final_weight": float(result.final_overlap_weights[1]) if result.final_overlap_weights is not None else 1.0
    }

def main():
    print("Starting Adaptive Weight Tuning Sweep...")
    results = []

    # Ramp Rate Sweep
    for rate in [1.02, 1.05, 1.10, 1.20]:
        print(f"  Testing ramp_rate={rate}...")
        for seed in range(3):
            res = run_tuning_trial(ramp_rate=rate, max_cap=50.0, update_interval=50, threshold=0.1, seed=seed)
            res["experiment"] = "ramp_rate"
            results.append(res)

    df = pd.DataFrame(results)
    print("\nSummary by Ramp Rate:")
    print(df.groupby("ramp_rate")[["epochs", "resolved", "final_weight"]].mean())

if __name__ == "__main__":
    main()
