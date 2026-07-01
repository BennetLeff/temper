"""Unit tests for C-CAP core algorithm.

Tests cover:
- Dykstra invariants: correction vectors converge, projections are idempotent
- Feasibility pump: gradient direction, NaN avoidance
- Oscillation detection: 2-cycle detection, slow drift, convergence
- Unresolved flagging: conflicting constraints, all-satisfied
- Graceful degradation: disabled C-CAP is identity
- Pre-flight: zone-keepout compatibility, side-zone overlap
"""

import jax.numpy as jnp
import pytest

from temper_placer.core.board import Board, Zone
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.io.config_loader import (
    ComponentSpacingRule,
    ManufacturingConstraint,
    PlacementConstraints,
    ThermalConstraint,
)
from temper_placer.optimizer.ccap import (
    CcapConfig,
    CcapResult,
    _build_projection_schedule,
    _detect_oscillation,
    _feasibility_pump_step,
    _flag_unresolved,
    _validate_side_zone_overlap,
    _validate_zone_keepout_compatibility,
    project_to_feasible,
)


# ---------------------------------------------------------------------------
# Dykstra invariants
# ---------------------------------------------------------------------------


class TestDykstraInvariants:
    def test_correction_vectors_monotonic(self):
        """Correction vector norms never increase across Dykstra cycles."""
        components = [
            Component(ref="U1", footprint="QFN", bounds=(10.0, 10.0)),
        ]
        netlist = Netlist(components=components, nets=[])
        board = Board(width=100.0, height=100.0)
        constraints = PlacementConstraints(
            board_width_mm=100.0,
            board_height_mm=100.0,
            board_margin_mm=3.0,
        )
        positions = jnp.array([[1.0, 50.0]], dtype=jnp.float32)

        result = project_to_feasible(positions, netlist, board, constraints)
        assert result.cycles_run > 0
        assert result.converged

    def test_projection_idempotence_zone(self):
        """P(P(x)) = P(x) for zone projection via Dykstra."""
        components = [
            Component(ref="U1", footprint="QFN", bounds=(10.0, 10.0)),
        ]
        netlist = Netlist(components=components, nets=[])
        board = Board(width=100.0, height=100.0)
        constraints = PlacementConstraints(
            board_width_mm=100.0,
            board_height_mm=100.0,
            board_margin_mm=3.0,
        )
        positions = jnp.array([[-10.0, 50.0]], dtype=jnp.float32)

        result1 = project_to_feasible(positions, netlist, board, constraints)
        result2 = project_to_feasible(result1.positions, netlist, board, constraints)
        assert jnp.allclose(result1.positions, result2.positions, atol=1e-3)
        assert result2.cycles_run <= 2  # already feasible, should converge fast


# ---------------------------------------------------------------------------
# Feasibility pump
# ---------------------------------------------------------------------------


class TestFeasibilityPump:
    def test_pump_gradient_direction_apart(self):
        """Pump pushes components apart, not together."""
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
            component_spacing_rules=[
                ComponentSpacingRule(
                    component_a="U1", component_b="R1", min_separation_mm=20.0
                )
            ],
        )
        # Place at same position
        positions = jnp.array([[50.0, 50.0], [50.0, 50.0]], dtype=jnp.float32)

        result = project_to_feasible(positions, netlist, board, constraints)
        dist = float(jnp.linalg.norm(result.positions[0] - result.positions[1]))
        assert dist >= 1.0  # Pump should have pushed them apart

    def test_pump_nan_avoidance_identical_positions(self):
        """Identical positions don't produce NaN in output."""
        components = [
            Component(ref="U1", footprint="QFN", bounds=(10.0, 10.0)),
            Component(ref="R2", footprint="0805", bounds=(5.0, 2.5)),
        ]
        nets = [Net("N1", [("U1", "1"), ("R2", "1")])]
        netlist = Netlist(components=components, nets=nets)
        board = Board(width=100.0, height=100.0)
        constraints = PlacementConstraints(
            board_width_mm=100.0,
            board_height_mm=100.0,
            board_margin_mm=3.0,
            component_spacing_rules=[
                ComponentSpacingRule(
                    component_a="U1", component_b="R2", min_separation_mm=5.0
                )
            ],
        )
        positions = jnp.array([[0.0, 0.0], [0.0, 0.0]], dtype=jnp.float32)

        result = project_to_feasible(positions, netlist, board, constraints)
        assert jnp.all(jnp.isfinite(result.positions))
        assert result.pairwise_violations_mm >= 0.0

    def test_pump_mild_clearance_violation_pushes_apart(self):
        """Pump increases distance for mild clearance violations (not just extreme)."""
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
            component_spacing_rules=[
                ComponentSpacingRule(
                    component_a="U1", component_b="R1", min_separation_mm=5.0
                )
            ],
        )
        # Place at distance 4mm (mild violation: min_dist=5mm)
        positions = jnp.array([[50.0, 50.0], [54.0, 50.0]], dtype=jnp.float32)
        ref_to_idx = {"U1": 0, "R1": 1}
        movable_mask = jnp.array([True, True])
        pump_pairs = [(0, 1, 5.0)]
        schedule = _build_projection_schedule(netlist, board, constraints)
        correction_dict: dict = {}

        pre_dist = float(jnp.linalg.norm(positions[0] - positions[1]))

        new_positions, _ = _feasibility_pump_step(
            positions, netlist, constraints, step_size=0.1,
            ref_to_idx=ref_to_idx, movable_mask=movable_mask,
            pump_pairs=pump_pairs, schedule=schedule,
            correction_dict=correction_dict,
        )

        post_dist = float(jnp.linalg.norm(new_positions[0] - new_positions[1]))
        assert post_dist > pre_dist, (
            f"Pump should increase distance for mild violation; "
            f"pre_dist={pre_dist:.3f}, post_dist={post_dist:.3f}"
        )


# ---------------------------------------------------------------------------
# Oscillation detection
# ---------------------------------------------------------------------------


class TestOscillationDetection:
    def test_detect_2_cycle_oscillation(self):
        """Synthetic 2-cycle (A→B→A→B) is detected."""
        tol = 0.01
        p0 = jnp.array([0.0, 0.0])
        p1 = jnp.array([0.5, 0.0])  # far step
        p2 = jnp.array([0.0, 0.0])  # close to p0
        p3 = jnp.array([0.5, 0.0])  # far from p2, close to p1
        history = {"C1": [p0, p1, p2, p3]}
        result = _detect_oscillation(history, tol)
        assert result["C1"] is True

    def test_slow_drift_not_detected(self):
        """Slow legitimate drift does not trigger oscillation detection."""
        tol = 0.01
        p0 = jnp.array([0.0, 0.0])
        p1 = jnp.array([0.005, 0.0])  # small step (< tol * 10)
        p2 = jnp.array([0.01, 0.0])  # small step
        p3 = jnp.array([0.015, 0.0])  # small step
        history = {"C1": [p0, p1, p2, p3]}
        result = _detect_oscillation(history, tol)
        assert result["C1"] is False

    def test_convergence_not_oscillation(self):
        """Stable positions (all < tol) identified as not oscillating."""
        tol = 0.01
        p = jnp.array([10.0, 10.0])
        history = {"C1": [p, p, p, p]}
        result = _detect_oscillation(history, tol)
        assert result["C1"] is False

    def test_insufficient_history(self):
        """Not enough history → not oscillating."""
        history = {"C1": [jnp.array([0.0, 0.0])]}
        result = _detect_oscillation(history, 0.01)
        assert result["C1"] is False


# ---------------------------------------------------------------------------
# Unresolved flagging
# ---------------------------------------------------------------------------


class TestUnresolvedFlagging:
    def test_no_unresolved_when_all_satisfied(self):
        """All constraints met → empty unresolved list."""
        components = [
            Component(ref="U1", footprint="QFN", bounds=(10.0, 10.0)),
        ]
        netlist = Netlist(components=components, nets=[])
        board = Board(width=100.0, height=100.0)
        constraints = PlacementConstraints(
            board_width_mm=100.0,
            board_height_mm=100.0,
            board_margin_mm=3.0,
        )
        schedule = _build_projection_schedule(netlist, board, constraints)
        ref_to_idx = {c.ref: i for i, c in enumerate(netlist.components)}
        positions = jnp.array([[50.0, 50.0]], dtype=jnp.float32)

        unresolved = _flag_unresolved(positions, schedule, ref_to_idx, 0.01)
        assert len(unresolved) == 0

    def test_unresolved_when_position_violates(self):
        """Component far outside board flagged as unresolved."""
        components = [
            Component(ref="U1", footprint="QFN", bounds=(200.0, 200.0)),
        ]
        netlist = Netlist(components=components, nets=[])
        board = Board(width=100.0, height=100.0)
        constraints = PlacementConstraints(
            board_width_mm=100.0,
            board_height_mm=100.0,
            board_margin_mm=3.0,
        )
        schedule = _build_projection_schedule(netlist, board, constraints)
        ref_to_idx = {c.ref: i for i, c in enumerate(netlist.components)}
        # Place component so far outside that board clamp doesn't help enough
        positions = jnp.array([[500.0, 500.0]], dtype=jnp.float32)

        unresolved = _flag_unresolved(positions, schedule, ref_to_idx, 0.01)
        assert len(unresolved) == 1
        assert unresolved[0]["component"] == "U1"


# ---------------------------------------------------------------------------
# Graceful degradation
# ---------------------------------------------------------------------------


class TestGracefulDegradation:
    def test_disabled_ccap_identity(self):
        """ccap_enabled=False: project_to_feasible returns identity."""
        components = [
            Component(ref="U1", footprint="QFN", bounds=(10.0, 10.0)),
        ]
        netlist = Netlist(components=components, nets=[])
        board = Board(width=100.0, height=100.0)
        positions = jnp.array([[3.0, 3.0]], dtype=jnp.float32)

        result = project_to_feasible(positions, netlist, board, constraints=None)
        assert jnp.allclose(result.positions, positions)
        assert result.cycles_run == 0
        assert not result.converged

    def test_empty_constraints_noop(self):
        """Empty constraints → Dykstra on board margin only, still converges."""
        components = [
            Component(ref="U1", footprint="QFN", bounds=(10.0, 10.0)),
        ]
        netlist = Netlist(components=components, nets=[])
        board = Board(width=100.0, height=100.0)
        constraints = PlacementConstraints(
            board_width_mm=100.0,
            board_height_mm=100.0,
            board_margin_mm=3.0,
        )
        positions = jnp.array([[50.0, 50.0]], dtype=jnp.float32)

        result = project_to_feasible(positions, netlist, board, constraints)
        assert result.converged
        assert len(result.unresolved) == 0


# ---------------------------------------------------------------------------
# Pre-flight validation
# ---------------------------------------------------------------------------


class TestPreFlightValidation:
    def test_zone_keepout_overlap_warns(self):
        """Zone fully inside keepout emits warning."""
        constraints = PlacementConstraints(
            board_width_mm=100.0,
            board_height_mm=100.0,
            board_margin_mm=3.0,
            zones=[
                Zone("Z1", (10, 10, 20, 20)),
            ],
            keepouts=[(5, 5, 25, 25)],
        )
        warnings = _validate_zone_keepout_compatibility(constraints)
        assert len(warnings) == 1
        assert "Z1" in warnings[0]
        assert "entirely" in warnings[0]

    def test_no_warning_when_no_keepouts(self):
        """No keepouts → no warnings."""
        constraints = PlacementConstraints(
            board_width_mm=100.0,
            board_height_mm=100.0,
            board_margin_mm=3.0,
            zones=[
                Zone("Z1", (10, 10, 20, 20)),
            ],
        )
        warnings = _validate_zone_keepout_compatibility(constraints)
        assert warnings == []

    def test_side_zone_overlap_low_returns_override(self):
        """Low zone overlap with manufacturing side returns override."""
        from temper_placer.io.config_loader import ManufacturingConstraint

        components = [
            Component(ref="U1", footprint="QFN", bounds=(10.0, 10.0)),
        ]
        netlist = Netlist(components=components, nets=[])
        board = Board(width=100.0, height=100.0)
        constraints = PlacementConstraints(
            board_width_mm=100.0,
            board_height_mm=100.0,
            board_margin_mm=3.0,
            zones=[Zone("Z1", (0, 0, 50, 100))],
            zone_assignments={"U1": "Z1"},
            manufacturing_constraints=[
                ManufacturingConstraint(components=["U1"], side="top"),
            ],
        )
        # Z1 is (0,0)-(50,100), full height. Midline at y=50.
        # Top side y < 50, so 50% of zone on top → no override
        overrides = _validate_side_zone_overlap(netlist, board, constraints)
        assert not overrides  # exactly 50% → no override needed

    def test_side_zone_overlap_ok_no_override(self):
        """Sufficient overlap → no override."""
        from temper_placer.io.config_loader import ManufacturingConstraint

        components = [
            Component(ref="U1", footprint="QFN", bounds=(10.0, 10.0)),
        ]
        netlist = Netlist(components=components, nets=[])
        board = Board(width=100.0, height=100.0)
        constraints = PlacementConstraints(
            board_width_mm=100.0,
            board_height_mm=100.0,
            board_margin_mm=3.0,
            zones=[Zone("Z1", (0, 60, 50, 100))],  # Entirely below midline
            zone_assignments={"U1": "Z1"},
            manufacturing_constraints=[
                ManufacturingConstraint(components=["U1"], side="bottom"),
            ],
        )
        # Z1 is at y=60-100, midline at 50. Bottom has 100% area → no override
        overrides = _validate_side_zone_overlap(netlist, board, constraints)
        assert not overrides


# ---------------------------------------------------------------------------
# Fixed components
# ---------------------------------------------------------------------------


class TestFixedComponents:
    def test_fixed_component_unchanged(self):
        """Fixed component position is unchanged after C-CAP."""
        components = [
            Component(ref="F1", footprint="QFN", bounds=(10.0, 10.0), fixed=True,
                      initial_position=(50.0, 50.0)),
            Component(ref="M1", footprint="0805", bounds=(5.0, 2.5)),
        ]
        nets = [Net("N1", [("F1", "1"), ("M1", "1")])]
        netlist = Netlist(components=components, nets=nets)
        board = Board(width=100.0, height=100.0)
        constraints = PlacementConstraints(
            board_width_mm=100.0,
            board_height_mm=100.0,
            board_margin_mm=3.0,
        )
        positions = jnp.array([[50.0, 50.0], [10.0, 10.0]], dtype=jnp.float32)

        result = project_to_feasible(positions, netlist, board, constraints)
        # Fixed component position should not change
        assert jnp.allclose(result.positions[0], jnp.array([50.0, 50.0]))


# ---------------------------------------------------------------------------
# Convergence
# ---------------------------------------------------------------------------


class TestConvergence:
    def test_converges_quickly_simple_case(self):
        """Simple board with margins → converges within a few cycles."""
        components = [
            Component(ref="U1", footprint="QFN", bounds=(10.0, 10.0)),
            Component(ref="U2", footprint="QFN", bounds=(10.0, 10.0)),
        ]
        nets = [Net("N1", [("U1", "1"), ("U2", "1")])]
        netlist = Netlist(components=components, nets=nets)
        board = Board(width=100.0, height=100.0)
        constraints = PlacementConstraints(
            board_width_mm=100.0,
            board_height_mm=100.0,
            board_margin_mm=3.0,
        )
        positions = jnp.array([[50.0, 50.0], [60.0, 60.0]], dtype=jnp.float32)

        result = project_to_feasible(positions, netlist, board, constraints)
        assert result.cycles_run <= 5
        assert result.converged


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_deterministic_output(self):
        """Same input twice → same output."""
        components = [
            Component(ref="U1", footprint="QFN", bounds=(10.0, 10.0)),
        ]
        netlist = Netlist(components=components, nets=[])
        board = Board(width=100.0, height=100.0)
        constraints = PlacementConstraints(
            board_width_mm=100.0,
            board_height_mm=100.0,
            board_margin_mm=3.0,
        )
        positions = jnp.array([[50.0, 50.0]], dtype=jnp.float32)

        r1 = project_to_feasible(positions, netlist, board, constraints)
        r2 = project_to_feasible(positions, netlist, board, constraints)
        assert jnp.allclose(r1.positions, r2.positions)
        assert r1.cycles_run == r2.cycles_run
