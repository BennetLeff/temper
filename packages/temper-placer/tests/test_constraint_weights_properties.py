"""
Property-based tests for constraint-weighted Laplacian (Hypothesis).

U6.1: Tests invariants — symmetry, non-negativity, monotonicity,
PSD preservation, baseline equivalence, idempotency, determinism.
"""

from __future__ import annotations

import numpy as np
import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from temper_placer.core.netlist import Component, Net, Netlist
from temper_placer.io.config_loader import ComponentGroup, PlacementConstraints
from temper_placer.pcl.constraints import (
    AdjacentConstraint,
    ConstraintTier,
)
from temper_placer.pcl.parser import ConstraintCollection
from temper_placer.placement.constraint_weights import (
    ConstraintMapper,
    apply_psd_shift,
    clearance_weight,
    compute_constraint_weight_dict,
    compute_gershgorin_lambda_min_bound,
    compute_laplacian_from_weights,
    critical_loop_weight,
    group_coherence_weight,
    hv_lv_repulsion_weight,
    proximity_weight,
)


# ---------------------------------------------------------------------------
# Strategy generators for Hypothesis
# ---------------------------------------------------------------------------


@st.composite
def netlist_strategy(draw, max_comps: int = 12, max_nets: int = 15):
    """Generate a random netlist."""
    n_comps = draw(st.integers(2, max_comps))
    n_nets = draw(st.integers(1, min(max_nets, n_comps * 2)))

    comps = [
        Component(
            ref=f"C{i}",
            footprint="R0805",
            bounds=(draw(st.floats(1.0, 20.0)), draw(st.floats(1.0, 20.0))),
            net_class=draw(st.sampled_from(["Signal", "HighVoltage", "Power"])),
        )
        for i in range(n_comps)
    ]

    nets = []
    for j in range(n_nets):
        n_pins = draw(st.integers(2, min(4, n_comps)))
        # Generate unique component indices to avoid self-loops
        comp_idxs = draw(st.lists(
            st.integers(0, n_comps - 1),
            min_size=2, max_size=n_pins, unique=True,
        ))
        pins = [(f"C{idx}", "1") for idx in comp_idxs]
        nets.append(
            Net(
                name=f"NET{j}",
                pins=pins,
                net_class=draw(st.sampled_from(["Signal", "HighVoltage", "Power"])),
                weight=draw(st.floats(0.1, 10.0)),
            )
        )

    return Netlist(components=comps, nets=nets)


# ---------------------------------------------------------------------------
# Invariant tests
# ---------------------------------------------------------------------------


class TestSymmetry:
    @given(nl=netlist_strategy(max_comps=8, max_nets=10))
    @settings(deadline=5000, max_examples=50)
    def test_proximity_weight_symmetry(self, nl):
        """Constraint weight dict should be symmetric for all strategies."""
        # Create minimal proximity constraints
        constraints = []
        comp_refs = [c.ref for c in nl.components[:4]]
        for i in range(0, len(comp_refs) - 1, 2):
            constraints.append(
                AdjacentConstraint(
                    a=comp_refs[i],
                    b=comp_refs[i + 1],
                    max_distance_mm=10.0,
                    tier=ConstraintTier.HARD,
                    because="Test symmetry constraint",
                )
            )

        collection = ConstraintCollection(constraints=constraints, version="1.0") if constraints else None
        mapper = ConstraintMapper.build(collection, None, nl)
        weights = compute_constraint_weight_dict(
            mapper, None, nl, collection,
            strategies={"proximity": True, "group_coherence": False,
                         "critical_loop": False, "hv_lv_repulsion": False,
                         "clearance": False},
        )

        for (i, j), w in weights.items():
            # Weights are stored with canonical (min, max) keys
            key = (min(i, j), max(i, j))
            assert key in weights, f"Missing canonical key {key}"
            assert weights[key] == w, f"Weight mismatch for {key}"


class TestNonNegativity:
    def test_proximity_always_positive(self):
        assert proximity_weight(10.0, tier=1) > 0
        assert proximity_weight(10.0, tier=2) > 0
        assert proximity_weight(10.0, tier=3) > 0

    def test_group_coherence_always_positive(self):
        assert group_coherence_weight(1.0, 0.5) > 0

    def test_critical_loop_always_positive(self):
        assert critical_loop_weight(1.0, 100.0) > 0

    def test_no_negative_for_positive_strategies(self):
        """Proximity, coherence, loop strategies produce no negative weights."""
        nl = Netlist(
            components=[
                Component(ref="C0", footprint="fp", bounds=(10, 10)),
                Component(ref="C1", footprint="fp", bounds=(10, 10)),
            ],
            nets=[Net(name="N0", pins=[("C0", "1"), ("C1", "1")])],
        )
        collection = ConstraintCollection(
            constraints=[
                AdjacentConstraint(
                    a="C0", b="C1", max_distance_mm=10.0,
                    tier=ConstraintTier.HARD,
                    because="Test non-negativity constraint",
                ),
            ],
            version="1.0",
        )
        mapper = ConstraintMapper.build(collection, None, nl)
        weights = compute_constraint_weight_dict(
            mapper, None, nl, collection,
            strategies={"proximity": True, "group_coherence": True,
                         "critical_loop": False, "hv_lv_repulsion": False,
                         "clearance": False},
        )
        assert all(w >= 0 for w in weights.values())


class TestMonotonicity:
    def test_tighter_proximity_gives_higher_weight(self):
        """Smaller max_distance_mm → larger weight."""
        w1 = proximity_weight(5.0, tier=1)
        w2 = proximity_weight(50.0, tier=1)
        assert w1 > w2

    def test_tighter_loop_gives_higher_weight(self):
        """Smaller max_area_mm2 → larger weight."""
        w1 = critical_loop_weight(1.0, 100.0)
        w2 = critical_loop_weight(1.0, 10000.0)
        assert w1 > w2

    def test_higher_tier_gives_higher_weight(self):
        """HARD > STRONG > SOFT for same distance."""
        w_hard = proximity_weight(10.0, tier=1)
        w_strong = proximity_weight(10.0, tier=2)
        w_soft = proximity_weight(10.0, tier=3)
        assert w_hard > w_strong > w_soft


class TestPSDPreservation:
    @given(
        n=st.integers(3, 10),
    )
    @settings(deadline=5000, max_examples=50)
    def test_shift_produces_psd(self, n):
        """After PSD shift, Laplacian should have non-negative eigenvalue bound."""
        rng = np.random.RandomState(42 + n)
        A = rng.randn(n, n)
        L = A @ A.T  # PSD matrix
        # Add negative diagonal entries to create negative eigenvalues
        L -= 2.0 * np.eye(n)
        bound_before = compute_gershgorin_lambda_min_bound(L)
        if bound_before >= -1e-6:
            return  # Already PSD, nothing to test

        L_stable, shift, was_overdamped = apply_psd_shift(L, max_shift_ratio=10.0)
        bound_after = compute_gershgorin_lambda_min_bound(L_stable)
        assert bound_after >= -1e-6, f"After shift: bound={bound_after}, shift={shift}"


class TestBaselineEquivalence:
    def test_empty_constraints_produces_empty_weights(self):
        """No constraints → empty weight dict."""
        nl = Netlist(
            components=[
                Component(ref="C0", footprint="fp", bounds=(10, 10)),
                Component(ref="C1", footprint="fp", bounds=(10, 10)),
            ],
            nets=[Net(name="N0", pins=[("C0", "1"), ("C1", "1")])],
        )
        mapper = ConstraintMapper.build(None, None, nl)
        weights = compute_constraint_weight_dict(
            mapper, None, nl, None,
            strategies={"proximity": False, "group_coherence": False,
                         "critical_loop": False, "hv_lv_repulsion": False,
                         "clearance": False},
        )
        assert weights == {}

    def test_empty_constraints_laplacian_matches_baseline(self):
        """Empty constraint weights → L = baseline uniform Laplacian."""
        nl = Netlist(
            components=[
                Component(ref="C0", footprint="fp", bounds=(10, 10)),
                Component(ref="C1", footprint="fp", bounds=(10, 10)),
                Component(ref="C2", footprint="fp", bounds=(10, 10)),
            ],
            nets=[
                Net(name="N0", pins=[("C0", "1"), ("C1", "1")]),
                Net(name="N1", pins=[("C1", "1"), ("C2", "1")]),
            ],
        )
        adj1, L1 = compute_laplacian_from_weights(nl, constraint_weights={})
        adj2, L2 = compute_laplacian_from_weights(nl, constraint_weights=None)
        np.testing.assert_array_almost_equal(adj1, adj2)
        np.testing.assert_array_almost_equal(L1, L2)


class TestIdempotency:
    def test_double_computation_produces_same_weights(self):
        """Running weight computation twice on same input produces identical output."""
        nl = Netlist(
            components=[
                Component(ref="C0", footprint="fp", bounds=(10, 10)),
                Component(ref="C1", footprint="fp", bounds=(10, 10)),
            ],
            nets=[Net(name="N0", pins=[("C0", "1"), ("C1", "1")])],
        )
        collection = ConstraintCollection(
            constraints=[
                AdjacentConstraint(
                    a="C0", b="C1", max_distance_mm=10.0,
                    tier=ConstraintTier.HARD,
                    because="Test idempotency constraint",
                ),
            ],
            version="1.0",
        )
        mapper = ConstraintMapper.build(collection, None, nl)
        w1 = compute_constraint_weight_dict(
            mapper, None, nl, collection,
            strategies={"proximity": True, "group_coherence": False,
                         "critical_loop": False, "hv_lv_repulsion": False,
                         "clearance": False},
        )
        w2 = compute_constraint_weight_dict(
            mapper, None, nl, collection,
            strategies={"proximity": True, "group_coherence": False,
                         "critical_loop": False, "hv_lv_repulsion": False,
                         "clearance": False},
        )
        assert w1 == w2


class TestDeterminism:
    def test_no_random_seed_in_weight_computation(self):
        """Weight computation is deterministic — no random generator involved."""
        nl = Netlist(
            components=[
                Component(ref="C0", footprint="fp", bounds=(10, 10)),
                Component(ref="C1", footprint="fp", bounds=(10, 10)),
                Component(ref="C2", footprint="fp", bounds=(10, 10)),
            ],
            nets=[
                Net(name="N0", pins=[("C0", "1"), ("C1", "1")]),
                Net(name="N1", pins=[("C1", "1"), ("C2", "1")]),
            ],
        )
        # Run 10 times, should always get the same result
        mapper = ConstraintMapper.build(None, None, nl)
        results = []
        for _ in range(10):
            w = compute_constraint_weight_dict(
                mapper, None, nl, None,
                strategies={"proximity": False, "group_coherence": True,
                             "critical_loop": False, "hv_lv_repulsion": False,
                             "clearance": False},
            )
            results.append(w)
        assert all(r == results[0] for r in results)
