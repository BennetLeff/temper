"""Differential test: ConstraintCompiler compute (temper-constraint-compiler)
vs the pinned Python oracle.

Wave 4, Phase 4 — the constraints surface migration. The Rust migration
(reproducing ``temper_placer/constraints/compiler.py`` bit-identically in the
``temper-constraint-compiler`` crate) is driven through the delegation shim
``temper_placer.constraints.compiler``; the pre-migration implementation is
pinned verbatim as the oracle (``_compiler_py_oracle.py``, commit aece7c372).

Every assertion drives IDENTICAL inputs through both sides and compares
bit-exactly: floats via ``float.hex()`` (never tolerance), the concrete type
carried in comparison keys (so int-vs-float cannot hide), and tuples/strings
compared as-is.

The module-scope reference to ``_rust.CompiledSlotFilter`` is the RED arm:
before the Rust surface lands this file fails to collect (AttributeError).
"""

from __future__ import annotations

import random

import pytest
import temper_constraint_compiler as _rust

import tests.constraints._compiler_py_oracle as _oracle

from temper_placer._constraint_types import (
    ComponentGroup,
    ComponentSpacingRule,
    EscapeClearance,
    PlacementConstraints,
    ProximityRule,
    RoutingCorridor,
    ThermalConstraint,
)
from temper_placer.constraints.compiler import ConstraintCompiler, ValidationError

# Module-scope RED arm: the Rust symbols must exist or collection fails.
assert hasattr(_rust, "CompiledSlotFilter")
assert hasattr(_rust, "CompiledSlotScorer")
assert hasattr(_rust, "constraint_distance")
assert hasattr(_rust, "constraint_centroid")
assert hasattr(_rust, "constraint_min_edge_distance")
assert hasattr(_rust, "constraint_point_to_segment_distance")
assert hasattr(_rust, "constraint_in_zone")
assert hasattr(_rust, "constraint_find_similar")
assert hasattr(_rust, "validate_constraints")


# ---------------------------------------------------------------------------
# Canonicalization helpers (bit-exact floats, concrete types).
# ---------------------------------------------------------------------------


def _f(value):
    """Bit-exact float key: None stays None, else float.hex()."""
    return None if value is None else float(value).hex()


def _pt(p):
    return None if p is None else (_f(p[0]), _f(p[1]))


def _err_key(e: ValidationError):
    """Canonical key for a ValidationError (all strings)."""
    return (
        e.constraint_type,
        e.message,
        e.component,
        e.suggestion,
        str(e),  # __str__ formatting must match too
    )


def _constraints(**kw) -> PlacementConstraints:
    return PlacementConstraints(**kw)


def _noisy_placements(rng: random.Random, refs: list[str], n: int) -> dict:
    out = {}
    for _ in range(n):
        ref = rng.choice(refs)
        out[ref] = (rng.uniform(-100.0, 100.0), rng.uniform(-100.0, 100.0))
    return out


def _random_constraints(rng: random.Random, seed_for: int) -> PlacementConstraints:
    """Random but deterministic constraint set (fixed seed per index)."""
    r = random.Random(seed_for)
    refs = ["A", "B", "C", "D", "E", "U1", "U2", "Q1", "Q2", "R5"]
    spacing = []
    for _ in range(r.randint(0, 4)):
        spacing.append(
            ComponentSpacingRule(
                component_a=r.choice(refs),
                component_b=r.choice(refs),
                min_separation_mm=r.uniform(1.0, 40.0),
                tier=r.choice(["hard", "soft"]),
                weight=r.uniform(0.1, 5.0),
                description=r.choice(["", "keep apart", "thermal pair"]),
            )
        )
    groups = []
    for _ in range(r.randint(0, 3)):
        comps = r.sample(refs, r.randint(2, 3))
        prox = []
        for _ in range(r.randint(0, 2)):
            a, b = r.sample(comps, 2)
            prox.append(
                ProximityRule(
                    component_a=a,
                    component_b=b,
                    max_distance_mm=r.uniform(5.0, 50.0),
                    tier=r.choice(["hard", "soft"]),
                )
            )
        groups.append(
            ComponentGroup(
                name=f"g{r.randint(1, 99)}",
                components=comps,
                max_spread_mm=r.uniform(10.0, 60.0),
                zone=r.choice([None, None, "Zone1"]),
                weight=r.uniform(0.5, 3.0),
                proximity_rules=prox,
            )
        )
    escapes = [
        EscapeClearance(
            component=r.choice(refs),
            clearance_mm=r.choice([None, r.uniform(2.0, 15.0)]),
            priority_sides=r.sample(["top", "bottom", "left", "right"], r.randint(0, 2)),
            tier=r.choice(["hard", "soft"]),
        )
        for _ in range(r.randint(0, 3))
    ]
    corridors = [
        RoutingCorridor(
            name=f"c{i}",
            from_component=r.choice(refs),
            to_component=r.choice(refs),
            width_mm=r.uniform(1.0, 10.0),
            keep_clear=r.choice([True, False]),
            nets=r.sample(["N1", "N2", "N3"], r.randint(0, 2)),
            tier=r.choice(["hard", "soft"]),
        )
        for i in range(r.randint(0, 2))
    ]
    thermals = [
        ThermalConstraint(
            components=r.sample(refs, r.randint(1, 2)),
            prefer_edge=r.choice([True, False]),
            max_distance_from_edge_mm=r.uniform(5.0, 30.0),
        )
        for _ in range(r.randint(0, 2))
    ]
    zones = []
    if r.random() < 0.5:
        zones.append(type("Z", (), {"name": "Zone1", "bounds": (0.0, 0.0, 100.0, 80.0)}))
    assignments = {}
    if zones:
        assignments[r.choice(refs)] = "Zone1"
    return PlacementConstraints(
        board_width_mm=100.0,
        board_height_mm=80.0,
        component_spacing_rules=spacing,
        component_groups=groups,
        escape_clearances=escapes,
        routing_corridors=corridors,
        thermal_constraints=thermals,
        zones=zones,
        zone_assignments=assignments,
    )


def _both(constraints, board_bounds=None):
    """Build oracle and shim compilers on identical inputs."""
    o = _oracle.ConstraintCompiler(constraints, board_bounds)
    s = ConstraintCompiler(constraints, board_bounds)
    return o, s


# ---------------------------------------------------------------------------
# R1a — behavioural A/B: slot filter (hard constraints), bit-identical.
# ---------------------------------------------------------------------------


class TestSlotFilterDifferential:
    def test_empty_constraints_filter_always_true(self):
        o, s = _both(PlacementConstraints())
        of, sf = o.compile_to_slot_filter(), s.compile_to_slot_filter()
        for slot in [(0.0, 0.0), (50.0, 50.0), (-3.5, 12.25)]:
            for comp in ["U_MCU", "A", "X1"]:
                for placements in [{}, {"A": (1.0, 2.0)}, {"A": (1.0, 2.0), "B": (3.0, 4.0)}]:
                    assert of(slot, comp, placements) == sf(slot, comp, placements)

    def test_random_differential(self):
        rng = random.Random(0xC0FFEE)
        for case in range(120):
            constraints = _random_constraints(rng, case)
            bounds = None if case % 3 == 0 else (0.0, 0.0, 100.0, 80.0)
            o, s = _both(constraints, bounds)
            of, sf = o.compile_to_slot_filter(), s.compile_to_slot_filter()
            refs = ["A", "B", "C", "D", "E", "U1", "U2", "Q1", "Q2", "R5"]
            for _ in range(8):
                slot = (rng.uniform(-20.0, 120.0), rng.uniform(-20.0, 100.0))
                comp = rng.choice(refs)
                placements = _noisy_placements(rng, refs, rng.randint(0, 6))
                assert of(slot, comp, placements) == sf(
                    slot, comp, placements
                ), f"filter mismatch case={case} slot={slot} comp={comp}"

    def test_nan_inf_placements(self):
        """NaN/inf positions must not crash and must agree bit-for-bit."""
        o, s = _both(
            _constraints(
                component_spacing_rules=[
                    ComponentSpacingRule(component_a="A", component_b="B", min_separation_mm=10.0, tier="hard")
                ]
            )
        )
        of, sf = o.compile_to_slot_filter(), s.compile_to_slot_filter()
        for slot in [(float("nan"), 0.0), (0.0, float("inf")), (float("-inf"), 5.0)]:
            for placements in [{"A": (float("nan"), 0.0)}, {"A": (0.0, 0.0), "B": (float("inf"), 0.0)}]:
                assert of(slot, "B", placements) == sf(slot, "B", placements)


class TestSlotScorerDifferential:
    def test_empty_constraints_scorer_zero(self):
        o, s = _both(PlacementConstraints())
        os_, ss = o.compile_to_slot_scorer(), s.compile_to_slot_scorer()
        for slot in [(0.0, 0.0), (50.0, 50.0)]:
            for placements in [{}, {"A": (1.0, 2.0)}]:
                assert _f(os_(slot, "U_MCU", placements)) == _f(ss(slot, "U_MCU", placements))

    def test_random_differential(self):
        rng = random.Random(0xBEEF)
        for case in range(120):
            constraints = _random_constraints(rng, case)
            bounds = None if case % 3 == 0 else (0.0, 0.0, 100.0, 80.0)
            o, s = _both(constraints, bounds)
            os_, ss = o.compile_to_slot_scorer(), s.compile_to_slot_scorer()
            refs = ["A", "B", "C", "D", "E", "U1", "U2", "Q1", "Q2", "R5"]
            for _ in range(8):
                slot = (rng.uniform(-20.0, 120.0), rng.uniform(-20.0, 100.0))
                comp = rng.choice(refs)
                placements = _noisy_placements(rng, refs, rng.randint(0, 6))
                assert _f(os_(slot, comp, placements)) == _f(
                    ss(slot, comp, placements)
                ), f"scorer mismatch case={case}"

    def test_default_board_bounds_from_constraints(self):
        """board_bounds=None must resolve to (0,0,w,h) identically."""
        constraints = _constraints(
            board_width_mm=100.0,
            board_height_mm=100.0,
            thermal_constraints=[
                ThermalConstraint(components=["MOSFET"], prefer_edge=True, max_distance_from_edge_mm=10.0)
            ],
        )
        o, s = _both(constraints, None)
        os_, ss = o.compile_to_slot_scorer(), s.compile_to_slot_scorer()
        for slot in [(5.0, 50.0), (50.0, 50.0), (98.0, 2.0)]:
            assert _f(os_(slot, "MOSFET", {})) == _f(ss(slot, "MOSFET", {}))


class TestValidateDifferential:
    def _netlist(self, refs):
        class NL:
            pass

        nl = NL()
        nl.components = [type("C", (), {"ref": ref})() for ref in refs]
        return nl

    def test_random_differential(self):
        rng = random.Random(0x5EED)
        for case in range(60):
            constraints = _random_constraints(rng, case)
            o, s = _both(constraints)
            refs = rng.sample(["A", "B", "C", "D", "E", "U1", "U2", "Q1", "Q2", "R5", "X_MISSING"], rng.randint(0, 8))
            nl = self._netlist(refs)
            oe, se = o.validate(None, nl), s.validate(None, nl)
            assert [_err_key(e) for e in oe] == [_err_key(e) for e in se], f"validate mismatch case={case}"

    def test_suggestion_and_zone_errors(self):
        """Typo suggestion (set-order dependent — same process ⇒ same order) + zone errors."""
        from temper_placer.core.board import Zone

        constraints = _constraints(
            zones=[Zone(name="Signal", bounds=(0, 0, 100, 100))],
            escape_clearances=[EscapeClearance(component="U_MC")],
            zone_assignments={"U_MCU": "UNDEFINED", "TYPO2": "Signal"},
        )
        o, s = _both(constraints)
        nl = self._netlist(["U_MCU", "U_GATE"])
        oe, se = o.validate(None, nl), s.validate(None, nl)
        assert [_err_key(e) for e in oe] == [_err_key(e) for e in se]
        # The suggestion must be non-empty somewhere (not vacuous)
        assert any(e.suggestion for e in se)


class TestHelperMethodsDifferential:
    def test_distance_centroid_edge_segment_zone(self):
        o, s = _both(PlacementConstraints())
        rng = random.Random(42)
        for _ in range(200):
            p1 = (rng.uniform(-1e6, 1e6), rng.uniform(-1e6, 1e6))
            p2 = (rng.uniform(-1e6, 1e6), rng.uniform(-1e6, 1e6))
            assert _f(o._distance(p1, p2)) == _f(s._distance(p1, p2))
        for _ in range(80):
            pts = [(rng.uniform(-100, 100), rng.uniform(-100, 100)) for _ in range(rng.randint(0, 8))]
            assert _pt(o._centroid(pts)) == _pt(s._centroid(pts))
        for _ in range(100):
            slot = (rng.uniform(-50, 150), rng.uniform(-50, 150))
            bounds = (0.0, 0.0, 100.0, 80.0)
            assert _f(o._min_edge_distance(slot)) == _f(s._min_edge_distance(slot))
            p = (rng.uniform(-50, 150), rng.uniform(-50, 150))
            a = (rng.uniform(-50, 150), rng.uniform(-50, 150))
            b = (rng.uniform(-50, 150), rng.uniform(-50, 150))
            assert _f(o._point_to_segment_distance(p, a, b)) == _f(s._point_to_segment_distance(p, a, b))
        # degenerate segment + NaN projection input
        assert _f(o._point_to_segment_distance((5.0, 5.0), (0.0, 0.0), (0.0, 0.0))) == _f(
            s._point_to_segment_distance((5.0, 5.0), (0.0, 0.0), (0.0, 0.0))
        )

    def test_zone_membership(self):
        o, s = _both(PlacementConstraints())
        zone = type("Z", (), {"bounds": (10.0, 20.0, 30.0, 40.0)})()
        for slot in [(10.0, 20.0), (30.0, 40.0), (15.0, 25.0), (9.0, 25.0), (35.0, 45.0), (float("nan"), 25.0)]:
            assert o._in_zone(slot, zone) == s._in_zone(slot, zone)

    def test_find_similar_set_order(self):
        """_find_similar iterates a set — pass the same set's iteration order to both."""
        o, s = _both(PlacementConstraints())
        options = {"U_MCU", "U_GATE", "C1", "R5", "U_MCUX", "X_GATE"}
        for name in ["U_MC", "X_GATE", "MISSING", "C", "", "U_MCU", "C12"]:
            assert o._find_similar(name, options) == s._find_similar(name, options)


class TestValidationErrorFormatting:
    def test_str_formatting(self):
        """__str__ of ValidationError must match the oracle exactly."""
        for kwargs in [
            dict(constraint_type="Test", message="Something went wrong"),
            dict(constraint_type="Test", message="Invalid component", component="U_MCU"),
            dict(
                constraint_type="Test",
                message="Component not found",
                component="U_MC",
                suggestion="Did you mean: U_MCU?",
            ),
        ]:
            o = _oracle.ValidationError(**kwargs)
            s = ValidationError(**kwargs)
            assert str(o) == str(s)
            assert o.constraint_type == s.constraint_type
            assert o.message == s.message
            assert o.component == s.component
            assert o.suggestion == s.suggestion
