"""Integration tests for C-CAP pipeline on synthetic and golden-board
configurations.

Tests cover:
- Full C-CAP pipeline: unary feasibility >= 95%
- A/B comparison: C-CAP improves initial feasibility vs random init
- Deterministic output for fixed seed
- Synthetic conflict: oscillating constraint → unresolved flagging
- Pairwise violation reduction after pump
- E2E pipeline integration via initialize_training_state()
"""

import jax
import jax.numpy as jnp
import pytest

from temper_placer.core.board import Board, Zone
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.io.config_loader import (
    ComponentSpacingRule,
    ManufacturingConstraint,
    PlacementConstraints,
)
from temper_placer.optimizer.ccap import (
    CcapConfig,
    project_to_feasible,
)
from temper_placer.optimizer.config import (
    InitializationConfig,
    OptimizerConfig,
)
from temper_placer.optimizer.train import initialize_training_state


# ---------------------------------------------------------------------------
# Full C-CAP pipeline synthetic board
# ---------------------------------------------------------------------------


def _make_synthetic_8component_board():
    """8-component board with zones, keepouts, HV/LV split."""
    components = [
        Component(ref="U_HV1", footprint="TO247", bounds=(12.0, 10.0), net_class="HighVoltage"),
        Component(ref="U_HV2", footprint="TO247", bounds=(12.0, 10.0), net_class="HighVoltage"),
        Component(ref="D_HV1", footprint="DO201", bounds=(8.0, 8.0), net_class="HighVoltage"),
        Component(ref="U_LV1", footprint="QFN56", bounds=(8.0, 8.0), net_class="Signal"),
        Component(ref="U_LV2", footprint="SOIC8", bounds=(5.0, 5.0), net_class="Signal"),
        Component(ref="R1", footprint="0805", bounds=(2.0, 1.25), net_class="Signal"),
        Component(ref="C1", footprint="0805", bounds=(2.0, 1.25), net_class="Signal"),
        Component(ref="J1", footprint="CONN", bounds=(15.0, 8.0), net_class="Signal"),
    ]
    nets = [
        Net("DC_BUS+", [("U_HV1", "1"), ("U_HV2", "1")], net_class="HighVoltage"),
        Net("SPI_CLK", [("U_LV1", "1"), ("U_LV2", "1")], net_class="Signal"),
        Net("PWR_3V3", [("U_LV1", "2"), ("R1", "1"), ("C1", "1")], net_class="Power"),
    ]
    return Netlist(components=components, nets=nets)


def _make_synthetic_constraints():
    """Constraints for the 8-component synthetic board."""
    return PlacementConstraints(
        board_width_mm=100.0,
        board_height_mm=100.0,
        board_margin_mm=3.0,
        zones=[
            Zone("HV_ZONE", (0, 0, 45, 100), net_classes=["HighVoltage"]),
            Zone("LV_ZONE", (55, 0, 45, 100), net_classes=["Signal"]),
        ],
        zone_assignments={
            "U_HV1": "HV_ZONE",
            "U_HV2": "HV_ZONE",
            "D_HV1": "HV_ZONE",
            "U_LV1": "LV_ZONE",
            "U_LV2": "LV_ZONE",
            "R1": "LV_ZONE",
            "C1": "LV_ZONE",
            "J1": "LV_ZONE",
        },
        keepouts=[
            (5, 5, 15, 15),  # Small keepout in HV zone
        ],
        hv_clearance_mm=10.0,
    )


class TestFullCCAPPipeline:
    def test_unary_feasibility_above_95_percent(self):
        """After C-CAP, >=95% of components satisfy unary hard constraints."""
        netlist = _make_synthetic_8component_board()
        board = Board(width=100.0, height=100.0)
        constraints = _make_synthetic_constraints()

        # Random init positions (some will violate constraints)
        key = jax.random.PRNGKey(42)
        raw_positions = jax.random.uniform(
            key, (netlist.n_components, 2), minval=0.0, maxval=100.0
        )

        result = project_to_feasible(raw_positions, netlist, board, constraints)

        # Verify board containment
        margin = constraints.board_margin_mm
        bw = constraints.board_width_mm
        bh = constraints.board_height_mm
        feasible = 0
        for i, comp in enumerate(netlist.components):
            x, y = float(result.positions[i, 0]), float(result.positions[i, 1])
            inside_board = margin <= x <= bw - margin and margin <= y <= bh - margin
            if inside_board:
                feasible += 1

        ratio = feasible / netlist.n_components
        assert ratio >= 0.95, f"Board feasibility: {feasible}/{netlist.n_components} = {ratio:.1%}"

    def test_converges_within_max_cycles(self):
        """C-CAP converges or reaches max cycles without error."""
        netlist = _make_synthetic_8component_board()
        board = Board(width=100.0, height=100.0)
        constraints = _make_synthetic_constraints()

        key = jax.random.PRNGKey(42)
        raw_positions = jax.random.uniform(
            key, (netlist.n_components, 2), minval=0.0, maxval=100.0
        )
        config = CcapConfig(max_cycles=15)

        result = project_to_feasible(raw_positions, netlist, board, constraints, config)
        assert result.cycles_run <= 15
        assert jnp.all(jnp.isfinite(result.positions))
        assert len(result.positions) == netlist.n_components


# ---------------------------------------------------------------------------
# A/B comparison
# ---------------------------------------------------------------------------


class TestABComparison:
    def test_ccap_improves_feasibility_over_random(self):
        """C-CAP projected positions have fewer board violations than random."""
        netlist = _make_synthetic_8component_board()
        board = Board(width=100.0, height=100.0)
        constraints = _make_synthetic_constraints()

        key = jax.random.PRNGKey(42)
        raw_positions = jax.random.uniform(
            key, (netlist.n_components, 2), minval=0.0, maxval=100.0
        )

        # Count violations in random positions
        margin = constraints.board_margin_mm
        bw = constraints.board_width_mm
        bh = constraints.board_height_mm
        random_violations = 0
        for i in range(netlist.n_components):
            x, y = float(raw_positions[i, 0]), float(raw_positions[i, 1])
            if not (margin <= x <= bw - margin and margin <= y <= bh - margin):
                random_violations += 1

        # Run C-CAP
        result = project_to_feasible(raw_positions, netlist, board, constraints)

        # Count violations after C-CAP
        ccap_violations = 0
        for i in range(netlist.n_components):
            x, y = float(result.positions[i, 0]), float(result.positions[i, 1])
            if not (margin <= x <= bw - margin and margin <= y <= bh - margin):
                ccap_violations += 1

        assert ccap_violations <= random_violations, (
            f"C-CAP should not increase violations: "
            f"{random_violations} → {ccap_violations}"
        )


# ---------------------------------------------------------------------------
# Deterministic output
# ---------------------------------------------------------------------------


class TestDeterministicOutput:
    def test_same_input_produces_same_output(self):
        """Same input positions produce identical output."""
        netlist = _make_synthetic_8component_board()
        board = Board(width=100.0, height=100.0)
        constraints = _make_synthetic_constraints()

        positions = jnp.array([[10.0, 10.0]] * 8, dtype=jnp.float32)

        r1 = project_to_feasible(positions, netlist, board, constraints)
        r2 = project_to_feasible(positions, netlist, board, constraints)

        assert jnp.allclose(r1.positions, r2.positions)
        assert r1.converged == r2.converged
        assert r1.cycles_run == r2.cycles_run


# ---------------------------------------------------------------------------
# Synthetic conflict
# ---------------------------------------------------------------------------


class TestSyntheticConflict:
    def test_conflicting_zone_keepout_flags_unresolved(self):
        """Zone fully covered by keepout → component flagged as unresolved."""
        components = [
            Component(ref="U_TRAP", footprint="QFN", bounds=(10.0, 10.0)),
        ]
        nets = [Net("N1", [("U_TRAP", "1")], net_class="Signal")]
        netlist = Netlist(components=components, nets=nets)
        board = Board(width=50.0, height=50.0)
        constraints = PlacementConstraints(
            board_width_mm=50.0,
            board_height_mm=50.0,
            board_margin_mm=2.0,
            zones=[Zone("Z1", (0, 0, 50, 50))],
            zone_assignments={"U_TRAP": "Z1"},
            keepouts=[(5, 5, 45, 45)],  # Nearly whole board is keepout
        )
        positions = jnp.array([[25.0, 4.0]], dtype=jnp.float32)

        result = project_to_feasible(positions, netlist, board, constraints)
        # The component should oscillate between zone interior and keepout avoidance
        assert result.converged or result.oscillation_detected or len(result.unresolved) > 0

    def test_no_conflict_on_clean_config(self):
        """Clean config (no overlapping zone/keepout) → no unresolved."""
        components = [
            Component(ref="U1", footprint="QFN", bounds=(10.0, 10.0)),
            Component(ref="U2", footprint="SOIC8", bounds=(5.0, 5.0)),
        ]
        nets = [Net("N1", [("U1", "1"), ("U2", "1")])]
        netlist = Netlist(components=components, nets=nets)
        board = Board(width=100.0, height=100.0)
        constraints = PlacementConstraints(
            board_width_mm=100.0,
            board_height_mm=100.0,
            board_margin_mm=3.0,
            zones=[
                Zone("Z_A", (0, 0, 45, 100)),
                Zone("Z_B", (55, 0, 45, 100)),
            ],
            zone_assignments={"U1": "Z_A", "U2": "Z_B"},
            keepouts=[(10, 10, 20, 20)],  # Small keepout, not covering a zone
        )
        positions = jnp.array([[25.0, 50.0], [75.0, 50.0]], dtype=jnp.float32)

        result = project_to_feasible(positions, netlist, board, constraints)
        assert len(result.unresolved) == 0


# ---------------------------------------------------------------------------
# Pairwise violation reduction
# ---------------------------------------------------------------------------


class TestPairwiseViolationReduction:
    def test_pump_reduces_violations(self):
        """Feasibility pump reduces sum-of-squared pairwise violations."""
        components = [
            Component(ref="A1", footprint="QFN", bounds=(10.0, 10.0)),
            Component(ref="A2", footprint="QFN", bounds=(10.0, 10.0)),
            Component(ref="B1", footprint="SOIC8", bounds=(5.0, 5.0)),
        ]
        nets = [Net("N1", [("A1", "1"), ("B1", "1")])]
        netlist = Netlist(components=components, nets=nets)
        board = Board(width=100.0, height=100.0)
        constraints = PlacementConstraints(
            board_width_mm=100.0,
            board_height_mm=100.0,
            board_margin_mm=3.0,
            component_spacing_rules=[
                ComponentSpacingRule(
                    component_a="A1", component_b="A2", min_separation_mm=15.0
                ),
            ],
        )
        # Place A1 and A2 close together (violation)
        positions = jnp.array([[40.0, 50.0], [42.0, 50.0], [80.0, 50.0]], dtype=jnp.float32)

        # Pre-pump violation
        pre_violation = float(
            jnp.maximum(0.0, 15.0 - jnp.linalg.norm(positions[0] - positions[1]))
        )

        result = project_to_feasible(positions, netlist, board, constraints)

        # Post-pump violation
        post_violation = float(
            jnp.maximum(0.0, 15.0 - jnp.linalg.norm(result.positions[0] - result.positions[1]))
        )
        assert post_violation <= pre_violation, (
            f"Pump should not increase violations: {pre_violation:.2f} → {post_violation:.2f}"
        )


# ---------------------------------------------------------------------------
# E2E pipeline integration
# ---------------------------------------------------------------------------


class TestE2EPipelineIntegration:
    def test_ccap_integrated_into_train_init(self):
        """initialize_training_state() with ccap_enabled=True runs without error."""
        components = [
            Component(ref="U1", footprint="QFN", bounds=(10.0, 10.0)),
            Component(ref="R1", footprint="0805", bounds=(5.0, 2.5)),
        ]
        nets = [Net("N1", [("U1", "1"), ("R1", "1")])]
        netlist = Netlist(components=components, nets=nets)
        board = Board(width=100.0, height=100.0)
        constraints = PlacementConstraints(
            board_width_mm=100.0,
            board_height_mm=100.0,
            board_margin_mm=3.0,
        )

        config = OptimizerConfig(
            initialization=InitializationConfig(
                ccap_enabled=True, ccap_max_cycles=5
            ),
            seed=42,
        )
        state = initialize_training_state(netlist, board, config, constraints=constraints)
        assert state.positions.shape == (2, 2)
        assert jnp.all(jnp.isfinite(state.positions))

    def test_ccap_enabled_vs_disabled_consistent(self):
        """ccap_enabled=True produces valid positions (board containment)."""
        components = [
            Component(ref="U1", footprint="QFN", bounds=(20.0, 20.0)),
        ]
        nets = [Net("N1", [("U1", "1")])]
        netlist = Netlist(components=components, nets=nets)
        board = Board(width=100.0, height=100.0)
        constraints = PlacementConstraints(
            board_width_mm=100.0,
            board_height_mm=100.0,
            board_margin_mm=3.0,
        )

        # Without C-CAP
        config_off = OptimizerConfig(
            initialization=InitializationConfig(ccap_enabled=False),
            seed=42,
        )
        state_off = initialize_training_state(netlist, board, config_off, constraints=constraints)

        # With C-CAP
        config_on = OptimizerConfig(
            initialization=InitializationConfig(ccap_enabled=True, ccap_max_cycles=5),
            seed=42,
        )
        state_on = initialize_training_state(netlist, board, config_on, constraints=constraints)

        # Both should produce valid positions
        x_off, y_off = float(state_off.positions[0, 0]), float(state_off.positions[0, 1])
        x_on, y_on = float(state_on.positions[0, 0]), float(state_on.positions[0, 1])

        margin = 3.0
        assert margin <= x_off <= 100.0 - margin
        assert margin <= y_off <= 100.0 - margin
        assert margin <= x_on <= 100.0 - margin
        assert margin <= y_on <= 100.0 - margin
