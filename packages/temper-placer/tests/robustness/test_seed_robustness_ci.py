
from pathlib import Path

import jax
import numpy as np
import pytest

from temper_placer.core.board import Board
from temper_placer.geometry.transform import sample_rotation_batch
from temper_placer.losses.base import CompositeLoss, LossContext, WeightedLoss
from temper_placer.losses.boundary import BoundaryLoss
from temper_placer.losses.overlap import OverlapLoss
from temper_placer.losses.wirelength import WirelengthLoss
from temper_placer.optimizer import (
    CheckpointConfig,
    EarlyStoppingConfig,
    OptimizerConfig,
    train,
)


def create_test_netlist(n_components: int = 17):
    """Create a fixed test netlist for robustness analysis."""
    import importlib.util
    fixtures_path = (
        Path(__file__).parent.parent / "fixtures" / "generators" / "synthetic_netlist.py"
    )
    spec = importlib.util.spec_from_file_location("synthetic_netlist", fixtures_path)
    synthetic_netlist = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(synthetic_netlist)
    return synthetic_netlist.generate_netlist(n_components=n_components, seed=12345)

@pytest.mark.ci
@pytest.mark.robustness
def test_seed_robustness_ci():
    """
    Fast CI test to catch robustness regressions.
    Runs 20 seeds with 200 epochs each.
    """
    n_components = 17
    n_seeds = 20
    epochs = 200
    board = Board(width=100.0, height=100.0)
    netlist = create_test_netlist(n_components)

    # Create loss context
    context = LossContext.from_netlist_and_board(netlist, board)

    # Use inflation_ramp in OverlapLoss
    composite = CompositeLoss([
        WeightedLoss(OverlapLoss(inflation_ramp=0.3), weight=100.0),
        WeightedLoss(BoundaryLoss(), weight=50.0),
        WeightedLoss(WirelengthLoss(), weight=1.0),
    ])

    results = []

    print(f"\nRunning robustness CI test with {n_seeds} seeds...")

    for seed in range(n_seeds):
        config = OptimizerConfig(
            epochs=epochs,
            seed=seed,
            # Enable robustness features via correct flags
            adaptive_overlap_enabled=True,
            jiggle_enabled=True,
            log_interval=epochs,
            checkpoint=CheckpointConfig(enabled=False),
            early_stopping=EarlyStoppingConfig(enabled=False)
        )

        res = train(netlist, board, composite, context, config)

        # Get final metrics
        positions = res.final_state.positions
        rotation_logits = res.final_state.rotation_logits
        key = jax.random.PRNGKey(0)
        rotations = sample_rotation_batch(rotation_logits, key, temperature=0.01)

        overlap_val = float(OverlapLoss()(positions, rotations, context).value)
        boundary_val = float(BoundaryLoss()(positions, rotations, context).value)

        results.append({
            "seed": seed,
            "loss": float(res.final_loss),
            "overlap": overlap_val,
            "boundary": boundary_val,
            "converged": overlap_val < 1.0 and boundary_val < 1.0
        })

    # Assert 100% convergence
    failed_seeds = [r["seed"] for r in results if not r["converged"]]
    assert len(failed_seeds) == 0, f"Seeds failed to converge: {failed_seeds}"

    # Check mean violations
    mean_overlap = np.mean([r["overlap"] for r in results])
    mean_boundary = np.mean([r["boundary"] for r in results])

    assert mean_overlap < 0.1, f"Mean overlap {mean_overlap:.4f} exceeds 0.1"
    assert mean_boundary < 0.1, f"Mean boundary {mean_boundary:.4f} exceeds 0.1"

    # Check CV of final loss
    losses = [r["loss"] for r in results]
    cv = np.std(losses) / np.mean(losses)
    assert cv < 0.3, f"Loss CV {cv:.4f} exceeds 0.3"

    print(f"Robustness CI passed! Mean overlap: {mean_overlap:.4f}, CV: {cv:.4f}")
