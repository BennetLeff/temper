"""
Reproduction test for the 250M boundary loss bug.

Mirrors the corpus runner's exact initialization path for the temper
board, asserting invariants at each step to locate the source of the
boundary violation.
"""

from __future__ import annotations

from pathlib import Path

import jax
import jax.numpy as jnp
import numpy as np
import pytest

from temper_placer.core.board import Board
from temper_placer.core.state import PlacementState
from temper_placer.heuristics import create_default_pipeline
from temper_placer.io.config_loader import (
    create_board_from_constraints,
    load_constraints,
)
from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.losses.base import (
    CompositeLoss,
    LossContext,
    WeightedLoss,
)
from temper_placer.losses.boundary import BoundaryLoss
from temper_placer.losses.overlap import OverlapLoss
from temper_placer.losses.regularization import SpreadLoss
from temper_placer.losses.wirelength import WirelengthLoss
from temper_placer.optimizer.config import OptimizerConfig

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent


def _temper_pcb_path() -> Path:
    p = REPO_ROOT / "power_pcb_dataset" / "corpus" / "temper" / "temper.kicad_pcb"
    if not p.exists():
        p = REPO_ROOT / "pcb" / "temper.kicad_pcb"
    return p


def _temper_constraints_path() -> Path:
    return (
        REPO_ROOT
        / "power_pcb_dataset"
        / "corpus"
        / "temper"
        / "constraints.yaml"
    )


def _minimal_corpus_constraints_path() -> Path:
    return (
        REPO_ROOT
        / "power_pcb_dataset"
        / "corpus"
        / "minimal"
        / "constraints_minimal.yaml"
    )


class TestCorpusParity:
    """Mirror the corpus runner's initialization and check invariants."""

    def test_parsed_positions_within_board_bounds(self):
        """Step 1: All KiCad positions are within [0,w]×[0,h]."""
        pcb_path = _temper_pcb_path()
        if not pcb_path.exists():
            pytest.skip("temper PCB not found")
        constraints_path = _temper_constraints_path()
        if not constraints_path.exists():
            pytest.skip("temper constraints not found")

        result = parse_kicad_pcb(pcb_path)
        netlist = result.netlist
        constraints = load_constraints(constraints_path)
        board = create_board_from_constraints(constraints)

        assert board.width > 0 and board.height > 0
        assert len(netlist.components) > 0

        out_of_bounds = []
        for comp in netlist.components:
            if comp.initial_position is not None:
                x, y = comp.initial_position
                if not (0 <= x <= board.width and 0 <= y <= board.height):
                    out_of_bounds.append(
                        f"{comp.ref}: ({x:.1f}, {y:.1f}) "
                        f"outside [{0},{board.width}]×[{0},{board.height}]"
                    )
        assert not out_of_bounds, (
            f"Components outside board bounds:\n" + "\n".join(out_of_bounds)
        )

    def test_heuristic_pipeline_positions_in_bounds(self):
        """Step 2: After pipeline.run(), all placements are in bounds."""
        pcb_path = _temper_pcb_path()
        if not pcb_path.exists():
            pytest.skip("temper PCB not found")
        constraints_path = _temper_constraints_path()
        if not constraints_path.exists():
            pytest.skip("temper constraints not found")

        result = parse_kicad_pcb(pcb_path)
        netlist = result.netlist
        constraints = load_constraints(constraints_path)
        board = create_board_from_constraints(constraints)

        pipeline = create_default_pipeline()
        rng = jax.random.PRNGKey(42)
        pipeline_result = pipeline.run(board, netlist, constraints, rng)

        state: PlacementState = pipeline_result.state
        positions = np.array(state.positions)

        # Every component must have a position
        assert positions.shape[0] == len(netlist.components), (
            f"Pipeline produced {positions.shape[0]} positions "
            f"for {len(netlist.components)} components"
        )

        # All positions must be within board bounds
        out_of_bounds = []
        for i, comp in enumerate(netlist.components):
            x, y = float(positions[i, 0]), float(positions[i, 1])
            if not (0 <= x <= board.width and 0 <= y <= board.height):
                out_of_bounds.append(
                    f"{comp.ref}: ({x:.1f}, {y:.1f})"
                )
        assert not out_of_bounds, (
            f"Heuristic pipeline placed components outside board:\n"
            + "\n".join(out_of_bounds[:10])
        )

    def test_loss_context_bounds_match_component_sizes(self):
        """Step 3: LossContext.bounds reflects actual component dimensions."""
        pcb_path = _temper_pcb_path()
        if not pcb_path.exists():
            pytest.skip("temper PCB not found")
        constraints_path = _temper_constraints_path()
        if not constraints_path.exists():
            pytest.skip("temper constraints not found")

        result = parse_kicad_pcb(pcb_path)
        netlist = result.netlist
        constraints = load_constraints(constraints_path)
        board = create_board_from_constraints(constraints)

        context = LossContext.from_netlist_and_board(netlist, board)

        # bounds should be (N, 2)
        assert context.bounds.shape == (len(netlist.components), 2)

        # All bounds must be positive and finite
        np_bounds = np.array(context.bounds)
        assert np.all(np_bounds > 0), f"Non-positive bounds: {np_bounds[np_bounds <= 0]}"
        assert np.all(np.isfinite(np_bounds)), "Infinite bounds found"

        # Bounds should be in mm (not nm, not meters)
        # Typical component sizes: 1-50mm range
        assert np.all(np_bounds < 500), (
            f"Bounds exceed 500mm — coordinate system broken: "
            f"max={np_bounds.max():.0f}"
        )

    def test_boundary_loss_after_pipeline_is_reasonable(self):
        """Step 4: Boundary loss on pipeline output should be near zero."""
        pcb_path = _temper_pcb_path()
        if not pcb_path.exists():
            pytest.skip("temper PCB not found")
        constraints_path = _temper_constraints_path()
        if not constraints_path.exists():
            pytest.skip("temper constraints not found")

        result = parse_kicad_pcb(pcb_path)
        netlist = result.netlist
        constraints = load_constraints(constraints_path)
        board = create_board_from_constraints(constraints)
        context = LossContext.from_netlist_and_board(netlist, board)

        pipeline = create_default_pipeline()
        rng = jax.random.PRNGKey(42)
        pipeline_result = pipeline.run(board, netlist, constraints, rng)

        pos = pipeline_result.state.positions
        n = len(netlist.components)
        rotations = jax.nn.softmax(
            pipeline_result.state.rotation_logits, axis=-1
        )

        loss_fn = BoundaryLoss(edge_margin=0.0)
        boundary_result = loss_fn(pos, rotations, context)
        boundary_loss = float(boundary_result.value)

        # With meaningful heuristics, boundary loss after pipeline
        # should be near zero (all components placed within board)
        max_expected = len(netlist.components) * 500  # generous per-component
        assert boundary_loss < max_expected, (
            f"Boundary loss {boundary_loss:.0f} after heuristic pipeline "
            f"exceeds max expected {max_expected:.0f} "
            f"({len(netlist.components)} components)"
        )

    def test_boundary_loss_after_one_epoch_is_reasonable(self):
        """Step 5: After one training epoch, boundary loss should shrink."""
        pcb_path = _temper_pcb_path()
        if not pcb_path.exists():
            pytest.skip("temper PCB not found")
        constraints_path = _temper_constraints_path()
        if not constraints_path.exists():
            pytest.skip("temper constraints not found")

        result = parse_kicad_pcb(pcb_path)
        netlist = result.netlist
        constraints = load_constraints(constraints_path)
        board = create_board_from_constraints(constraints)
        context = LossContext.from_netlist_and_board(netlist, board)

        pipeline = create_default_pipeline()
        rng = jax.random.PRNGKey(42)
        pipeline_result = pipeline.run(board, netlist, constraints, rng)
        initial_state: PlacementState = pipeline_result.state

        def make_loss(weights):
            return CompositeLoss([
                WeightedLoss(BoundaryLoss(), weight=weights.get("boundary", 100.0)),
                WeightedLoss(OverlapLoss(), weight=weights.get("overlap", 100.0)),
                WeightedLoss(WirelengthLoss(), weight=weights.get("wirelength", 5.0)),
                WeightedLoss(SpreadLoss(), weight=weights.get("spread", 1.0)),
            ])

        from temper_placer.optimizer.train import train_multiphase
        config = OptimizerConfig(epochs=10, seed=42, log_interval=100)
        config.early_stopping.enabled = False
        config.jiggle.enabled = False
        config.use_centrality_weighting = False

        training_result = train_multiphase(
            netlist, board, make_loss, context,
            config=config, initial_state=initial_state,
        )

        # Check boundary loss on final state
        n = len(netlist.components)
        final_pos = training_result.final_state.positions
        # Sample rotations from final logits
        key = jax.random.PRNGKey(99)
        rotations = jax.nn.softmax(
            training_result.final_state.rotation_logits, axis=-1
        )
        loss_fn = BoundaryLoss(edge_margin=0.0)
        boundary_result = loss_fn(final_pos, rotations, context)
        boundary_loss = float(boundary_result.value)

        max_expected = n * 500
        assert boundary_loss < max_expected, (
            f"AFTER 10 EPOCHS — boundary loss {boundary_loss:.0f} "
            f"exceeds max {max_expected:.0f}. "
            f"Without clamping, this would grow to 250M over 8000 epochs."
        )

    @pytest.mark.slow
    def test_corpus_temper_full_8000_epochs(self):
        """Step 6: Full 8000-epoch run.  If this produces 250M boundary loss,
        we've reproduced the CI bug locally."""
        pcb_path = _temper_pcb_path()
        if not pcb_path.exists():
            pytest.skip("temper PCB not found")
        constraints_path = _temper_constraints_path()
        if not constraints_path.exists():
            pytest.skip("temper constraints not found")

        result = parse_kicad_pcb(pcb_path)
        netlist = result.netlist
        constraints = load_constraints(constraints_path)
        board = create_board_from_constraints(constraints)
        context = LossContext.from_netlist_and_board(netlist, board)

        pipeline = create_default_pipeline()
        rng = jax.random.PRNGKey(42)
        pipeline_result = pipeline.run(board, netlist, constraints, rng)
        initial_state: PlacementState = pipeline_result.state

        def make_loss(weights):
            return CompositeLoss([
                WeightedLoss(BoundaryLoss(), weight=weights.get("boundary", 100.0)),
                WeightedLoss(OverlapLoss(), weight=weights.get("overlap", 200.0)),
                WeightedLoss(WirelengthLoss(), weight=weights.get("wirelength", 20.0)),
                WeightedLoss(SpreadLoss(), weight=weights.get("spread", 5.0)),
            ])

        from temper_placer.optimizer.train import train_multiphase
        config = OptimizerConfig(epochs=8000, seed=42, log_interval=1000)
        config.use_centrality_weighting = False

        print(f"\n  Board: {board.width}x{board.height}mm, "
              f"{len(netlist.components)} components")
        print(f"  Initial positions from heuristic pipeline: "
              f"{initial_state.positions.shape}")

        result = train_multiphase(
            netlist, board, make_loss, context,
            config=config, initial_state=initial_state,
        )

        n = len(netlist.components)
        final_pos = result.final_state.positions
        rotations = jax.nn.softmax(
            result.final_state.rotation_logits, axis=-1
        )
        loss_fn = BoundaryLoss(edge_margin=0.0)
        boundary_result = loss_fn(final_pos, rotations, context)
        boundary_loss = float(boundary_result.value)

        print(f"  Boundary loss after 8000 epochs: {boundary_loss:.0f}")
        print(f"  Final loss: {result.final_loss:.2f}")

        # Theoretical max for TEMPER board (33 components, 100x150mm board):
        # With clamping, max boundary loss < 33 * 4 * 500 = 66,000
        max_theoretical = len(netlist.components) * 4 * 500
        assert boundary_loss < max_theoretical, (
            f"CORPUS REPRODUCTION: boundary loss {boundary_loss:.0f} "
            f"exceeds theoretical max {max_theoretical:.0f} "
            f"(components={len(netlist.components)}). "
            f"This reproduces the 250M CI bug."
        )

        # Stronger check: after 8000 epochs, boundary loss should be
        # essentially zero.  If it's above 1000, something is wrong.
        assert boundary_loss < 1000, (
            f"Boundary loss {boundary_loss:.0f} after 8000 epochs is "
            f"excessive. Expected near-zero with boundary_weight=100."
        )
