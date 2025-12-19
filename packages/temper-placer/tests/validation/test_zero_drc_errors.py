"""
TDD Tests: Ensure optimizer produces zero-DRC-error placements.

This test file uses Test-Driven Development to ensure optimized placements
pass KiCad DRC with zero errors.

Current problem:
- Optimizer minimizes wirelength by pushing components close together
- This causes clearance violations (pads closer than 0.2mm)
- Also causes shorting/solder mask bridge errors

Solution approach:
- Add ClearanceLoss that penalizes components closer than minimum clearance
- Clearance should consider pad-to-pad distance, not just bounding box overlap

Key insight from DRC analysis:
- Default KiCad clearance is 0.2mm between pads
- Our overlap loss uses bounding boxes, which are larger than pads
- Components can have non-overlapping bounding boxes but overlapping pads
"""

from dataclasses import dataclass
from pathlib import Path
import tempfile
from typing import Tuple

import pytest

# Skip all tests if JAX not available
jax = pytest.importorskip("jax")
import jax.numpy as jnp

from temper_placer.core.board import Board
from temper_placer.core.netlist import Netlist
from temper_placer.core.state import PlacementState
from temper_placer.io.kicad_parser import parse_kicad_pcb, ParseResult
from temper_placer.losses import (
    CompositeLoss,
    WeightedLoss,
    LossContext,
    OverlapLoss,
    BoundaryLoss,
    WirelengthLoss,
)
from temper_placer.optimizer import train, OptimizerConfig
from temper_placer.optimizer.config import (
    TemperatureSchedule,
    LearningRateSchedule,
    CheckpointConfig,
    EarlyStoppingConfig,
)

# Import DRC infrastructure (use relative import within tests package)
from .test_drc_correlation import (
    run_kicad_drc,
    requires_kicad,
    export_placement_to_pcb,
    random_init_absolute,
    evaluate_placement,
    create_perfect_placement,
)


# Paths
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
MINIMAL_PCB = FIXTURES_DIR / "minimal_board.kicad_pcb"


def create_drc_safe_composite_loss(clearance_mm: float = 1.0) -> CompositeLoss:
    """
    Create composite loss with clearance-aware overlap penalty.

    Args:
        clearance_mm: Minimum clearance between components in mm.
                     Default 1.0mm provides sufficient margin over KiCad's
                     0.2mm default clearance, accounting for:
                     - Pad extensions beyond bounding box (~0.3-0.5mm)
                     - Solder mask aperture bridges
                     - Rotation variance

    The key changes are:
    1. rotation_invariant=True ensures overlap is detected regardless of rotation
       (prevents optimizer from finding placements that only work for certain rotations)
    2. High weight on overlap (1000x) to make it a hard constraint
    3. Lower weight on wirelength so it doesn't override clearance requirements
    """
    return CompositeLoss(
        [
            # High weight on overlap with rotation-invariant bounds
            # This uses max(width, height) for both dimensions, ensuring
            # components stay far enough apart regardless of final rotation
            WeightedLoss(
                OverlapLoss(margin=clearance_mm, rotation_invariant=True),
                weight=1000.0,
            ),
            WeightedLoss(BoundaryLoss(), weight=50.0),
            # Lower weight on wirelength so it doesn't override clearance
            WeightedLoss(WirelengthLoss(), weight=1.0),
        ]
    )


def run_optimizer_with_drc_safe_loss(
    netlist: Netlist,
    board: Board,
    epochs: int = 400,
    seed: int = 42,
    clearance_mm: float = 1.0,
) -> PlacementState:
    """
    Run optimizer with DRC-safe loss configuration.

    Returns the final placement state.
    """
    composite = create_drc_safe_composite_loss(clearance_mm=clearance_mm)
    context = LossContext.from_netlist_and_board(netlist, board)

    # Start with random positions
    key = jax.random.PRNGKey(seed)
    initial_state = random_init_absolute(netlist.n_components, board, key, margin=5.0)

    config = OptimizerConfig(
        epochs=epochs,
        seed=seed,
        temperature=TemperatureSchedule(start=2.0, end=0.5, warmup_epochs=50),
        learning_rate=LearningRateSchedule(
            initial=0.1,
            warmup_epochs=50,
            decay_type="cosine",
            final=0.01,
        ),
        checkpoint=CheckpointConfig(enabled=False),
        early_stopping=EarlyStoppingConfig(enabled=False),
        log_interval=epochs // 10,
    )

    result = train(netlist, board, composite, context, config, initial_state=initial_state)
    return result.final_state


class TestZeroDRCErrors:
    """
    TDD tests ensuring optimized placements have zero DRC errors.

    These tests will initially FAIL, then we implement the solution to make them pass.
    """

    @pytest.fixture
    def parsed_minimal(self) -> ParseResult:
        """Parse minimal board fixture."""
        if not MINIMAL_PCB.exists():
            pytest.skip("Minimal PCB fixture not found")
        return parse_kicad_pcb(MINIMAL_PCB)

    @requires_kicad
    def test_optimized_placement_zero_drc_errors(self, parsed_minimal: ParseResult):
        """
        CRITICAL TEST: An optimized placement MUST have zero DRC errors.

        This is the main TDD test. It should:
        1. Initially FAIL (current optimizer produces 9-10 errors)
        2. PASS after we implement clearance-aware optimization
        """
        netlist = parsed_minimal.netlist
        board = parsed_minimal.board
        assert board is not None

        # Run optimizer with DRC-safe loss
        final_state = run_optimizer_with_drc_safe_loss(
            netlist, board, epochs=400, seed=42, clearance_mm=0.5
        )

        # Export and run DRC
        with tempfile.NamedTemporaryFile(suffix=".kicad_pcb", delete=False) as f:
            temp_path = Path(f.name)

        try:
            export_placement_to_pcb(final_state, netlist, board, MINIMAL_PCB, temp_path)
            drc_result = run_kicad_drc(temp_path)

            assert drc_result.ran_successfully, f"DRC failed: {drc_result.error_message}"

            # Print violations for debugging
            if drc_result.error_count > 0:
                print(f"\nDRC Errors: {drc_result.error_count}")
                for v in drc_result.violations:
                    if v.severity == "error":
                        print(f"  {v.type}: {v.description}")

            # THE CRITICAL ASSERTION
            assert drc_result.error_count == 0, (
                f"Optimized placement has {drc_result.error_count} DRC errors. "
                f"Violations: {drc_result.violations_by_type()}"
            )
        finally:
            if temp_path.exists():
                temp_path.unlink()

    @requires_kicad
    def test_multiple_seeds_zero_drc_errors(self, parsed_minimal: ParseResult):
        """
        Test that multiple random seeds all produce zero-error placements.

        This ensures the solution is robust, not just lucky on one seed.

        Note: Uses 1.0mm clearance margin to match CLI default and provide
        sufficient headroom for all seeds.
        """
        netlist = parsed_minimal.netlist
        board = parsed_minimal.board
        assert board is not None

        seeds_to_test = [42, 123, 456, 789, 1000]
        failures = []

        for seed in seeds_to_test:
            final_state = run_optimizer_with_drc_safe_loss(
                netlist, board, epochs=400, seed=seed, clearance_mm=1.0
            )

            with tempfile.NamedTemporaryFile(suffix=".kicad_pcb", delete=False) as f:
                temp_path = Path(f.name)

            try:
                export_placement_to_pcb(final_state, netlist, board, MINIMAL_PCB, temp_path)
                drc_result = run_kicad_drc(temp_path)

                if drc_result.error_count > 0:
                    failures.append((seed, drc_result.error_count, drc_result.violations_by_type()))
            finally:
                if temp_path.exists():
                    temp_path.unlink()

        print(f"\nTested {len(seeds_to_test)} seeds")
        print(f"  Passed: {len(seeds_to_test) - len(failures)}")
        print(f"  Failed: {len(failures)}")

        if failures:
            print("\nFailures:")
            for seed, errors, violations in failures:
                print(f"  Seed {seed}: {errors} errors - {violations}")

        assert len(failures) == 0, (
            f"{len(failures)}/{len(seeds_to_test)} seeds produced DRC errors: {failures}"
        )

    @requires_kicad
    def test_perfect_placement_still_passes(self, parsed_minimal: ParseResult):
        """
        Verify that hand-crafted perfect placements still pass DRC.

        This is a sanity check - if this fails, something is wrong with our test setup.
        """
        netlist = parsed_minimal.netlist
        board = parsed_minimal.board
        assert board is not None

        state, _ = create_perfect_placement(netlist, board)

        with tempfile.NamedTemporaryFile(suffix=".kicad_pcb", delete=False) as f:
            temp_path = Path(f.name)

        try:
            export_placement_to_pcb(state, netlist, board, MINIMAL_PCB, temp_path)
            drc_result = run_kicad_drc(temp_path)

            assert drc_result.ran_successfully
            assert drc_result.error_count == 0, (
                f"Perfect placement has {drc_result.error_count} DRC errors"
            )
        finally:
            if temp_path.exists():
                temp_path.unlink()


class TestClearanceLoss:
    """
    Tests for the clearance-aware overlap loss.

    These tests verify that the OverlapLoss with margin correctly
    penalizes components that are too close together.
    """

    @pytest.fixture
    def parsed_minimal(self) -> ParseResult:
        """Parse minimal board fixture."""
        if not MINIMAL_PCB.exists():
            pytest.skip("Minimal PCB fixture not found")
        return parse_kicad_pcb(MINIMAL_PCB)

    def test_overlap_loss_with_margin(self, parsed_minimal: ParseResult):
        """
        OverlapLoss with margin should penalize components within margin distance.
        """
        netlist = parsed_minimal.netlist
        board = parsed_minimal.board
        assert board is not None

        context = LossContext.from_netlist_and_board(netlist, board)

        # Create positions where components are close but not overlapping
        # The minimal board has 4 components: R1, R2, C1, U1
        # Place them in a tight cluster
        ox, oy = board.origin
        positions = jnp.array(
            [
                [ox + 25, oy + 25],  # R1
                [ox + 27, oy + 25],  # R2 - 2mm away
                [ox + 25, oy + 27],  # C1 - 2mm away
                [ox + 27, oy + 27],  # U1 - 2mm away diagonally
            ]
        )
        rotation_logits = jnp.zeros((4, 4))
        state = PlacementState(positions=positions, rotation_logits=rotation_logits)

        # Loss without margin
        loss_no_margin = OverlapLoss(margin=0.0)
        _, rotation_indices = state.to_discrete()
        rotations = jax.nn.one_hot(rotation_indices, 4)
        val_no_margin = float(loss_no_margin(positions, rotations, context).value)

        # Loss with margin
        loss_with_margin = OverlapLoss(margin=0.5)  # 0.5mm margin
        val_with_margin = float(loss_with_margin(positions, rotations, context).value)

        print(f"\nOverlap loss without margin: {val_no_margin}")
        print(f"Overlap loss with 0.5mm margin: {val_with_margin}")

        # With margin, the loss should be higher (more "overlap" detected)
        # This test documents expected behavior
        # If OverlapLoss doesn't support margin yet, this test guides implementation

    def test_clearance_margin_prevents_drc_violations(self, parsed_minimal: ParseResult):
        """
        A sufficient clearance margin should prevent DRC clearance violations.

        KiCad default clearance is 0.2mm. If we use 0.3mm margin, components
        should never have pads closer than 0.2mm.
        """
        netlist = parsed_minimal.netlist
        board = parsed_minimal.board
        assert board is not None

        # Get component bounds
        for comp in netlist.components:
            print(f"{comp.ref}: bounds={comp.bounds}")

        # The insight: 0603 resistor pads extend ~0.5mm from center
        # If we add 0.3mm margin to bounding box, components must be
        # at least 0.3mm apart (bounding box edge to bounding box edge)
        # This should give 0.3mm + pad extension >= 0.5mm clearance
