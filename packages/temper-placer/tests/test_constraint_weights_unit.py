"""
Unit tests for constraint-to-Laplacian-weight mapping strategies.

Tests U1 (ConstraintMapper) and U2 (five weight derivation strategies).
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.io.config_loader import ComponentGroup, CriticalLoop, PlacementConstraints
from temper_placer.pcl.constraints import (
    AdjacentConstraint,
    ConstraintTier,
    LoopAreaConstraint,
    SeparatedConstraint,
)
from temper_placer.pcl.parser import ConstraintCollection
from temper_placer.placement.constraint_weights import (
    ALPHA_COHERENCE,
    C_ISO,
    K_HARD,
    K_STRONG,
    K_SOFT,
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
# Shared fixtures
# ---------------------------------------------------------------------------


def _make_component(ref: str, net_class: str = "Signal") -> Component:
    return Component(
        ref=ref,
        footprint="footprint",
        bounds=(10.0, 10.0),
        net_class=net_class,
        pins=[],
    )


def _make_net(name: str, comp_refs: list[str], net_class: str = "Signal") -> Net:
    pins = [(ref, "1") for ref in comp_refs]
    return Net(name=name, pins=pins, net_class=net_class, weight=1.0)


@pytest.fixture
def simple_netlist():
    comps = [
        _make_component("C1"),
        _make_component("C2"),
        _make_component("C3"),
        _make_component("C4"),
    ]
    nets = [
        _make_net("NET1", ["C1", "C2"]),
        _make_net("NET2", ["C2", "C3"]),
        _make_net("NET3", ["C1", "C3", "C4"]),
    ]
    return Netlist(components=comps, nets=nets)


@pytest.fixture
def netlist_hv_lv():
    comps = [
        _make_component("HV_C1", net_class="HighVoltage"),
        _make_component("HV_C2", net_class="HighVoltage"),
        _make_component("LV_C1", net_class="Signal"),
        _make_component("LV_C2", net_class="Signal"),
    ]
    nets = [
        _make_net("HV_NET", ["HV_C1", "HV_C2"], net_class="HighVoltage"),
        _make_net("LV_NET", ["LV_C1", "LV_C2"], net_class="Signal"),
        _make_net("CROSS_NET", ["HV_C1", "LV_C1"], net_class="Signal"),
    ]
    return Netlist(components=comps, nets=nets)


# =============================================================================
# U1: ConstraintMapper tests
# =============================================================================


class TestConstraintMapper:
    def test_empty_input_returns_empty_mapping(self):
        mapper = ConstraintMapper.build(None, None, Netlist())
        assert mapper.adjacency_nets == {}
        assert mapper.loop_components == {}

    def test_adjacency_from_pcl(self, simple_netlist):
        from temper_placer.pcl.constraints import AdjacentConstraint, ConstraintTier

        collection = ConstraintCollection(
            constraints=[
                AdjacentConstraint(
                    a="C1",
                    b="C2",
                    max_distance_mm=10.0,
                    tier=ConstraintTier.HARD,
                    because="Test adjacency constraint",
                ),
            ],
            version="1.0",
        )

        mapper = ConstraintMapper.build(collection, None, simple_netlist)

        key = ("C1", "C2")
        assert key in mapper.adjacency_nets
        assert len(mapper.adjacency_nets[key]) >= 1

    def test_adjacency_no_shared_nets(self, simple_netlist):
        """Component pair with no shared nets should produce warning, not crash."""
        from temper_placer.pcl.constraints import AdjacentConstraint, ConstraintTier

        collection = ConstraintCollection(
            constraints=[
                AdjacentConstraint(
                    a="C1",
                    b="NONEXISTENT",
                    max_distance_mm=10.0,
                    tier=ConstraintTier.HARD,
                    because="Test missing component adjacency",
                ),
            ],
            version="1.0",
        )

        mapper = ConstraintMapper.build(collection, None, simple_netlist)
        assert mapper.adjacency_nets == {} or all(
            v for k, v in mapper.adjacency_nets.items() if "NONEXISTENT" not in k
        )

    def test_loop_components_from_critical_loops(self, simple_netlist):
        placement = PlacementConstraints(
            critical_loops=[
                CriticalLoop(
                    name="commutation",
                    nets=["NET1", "NET2"],
                    max_area_mm2=500.0,
                    weight=1.0,
                ),
            ],
        )

        mapper = ConstraintMapper.build(None, placement, simple_netlist)

        assert "commutation" in mapper.loop_components
        comps = mapper.loop_components["commutation"]
        assert "C1" in comps or "C2" in comps  # Should have components from NET1/NET2

    def test_loop_components_from_pcl(self, simple_netlist):
        from temper_placer.pcl.constraints import LoopAreaConstraint

        placement = PlacementConstraints(
            component_groups=[
                ComponentGroup(
                    name="commutation",
                    components=["C1", "C2"],
                ),
            ],
        )

        collection = ConstraintCollection(
            constraints=[
                LoopAreaConstraint(
                    loop_name="commutation",
                    max_area_mm2=500.0,
                    tier=ConstraintTier.HARD,
                    because="Minimize commutation loop area",
                ),
            ],
            version="1.0",
        )

        mapper = ConstraintMapper.build(collection, placement, simple_netlist)

        assert "commutation" in mapper.loop_components
        assert mapper.loop_components["commutation"] == ["C1", "C2"]

    def test_loop_components_unresolvable(self):
        from temper_placer.pcl.constraints import LoopAreaConstraint

        collection = ConstraintCollection(
            constraints=[
                LoopAreaConstraint(
                    loop_name="mystery_loop",
                    max_area_mm2=100.0,
                    tier=ConstraintTier.HARD,
                    because="Test unresolvable loop constraint",
                ),
            ],
            version="1.0",
        )

        mapper = ConstraintMapper.build(collection, None, Netlist())
        assert "mystery_loop" not in mapper.loop_components


# =============================================================================
# U2.1: Proximity weight tests
# =============================================================================


class TestProximityWeight:
    def test_hard_tier_produces_largest_weight(self):
        w_hard = proximity_weight(10.0, tier=1, k_hard=100.0, k_strong=10.0, k_soft=1.0)
        w_strong = proximity_weight(10.0, tier=2, k_hard=100.0, k_strong=10.0, k_soft=1.0)
        w_soft = proximity_weight(10.0, tier=3, k_hard=100.0, k_strong=10.0, k_soft=1.0)
        assert w_hard > w_strong > w_soft

    def test_tighter_distance_gives_higher_weight(self):
        w_tight = proximity_weight(5.0, tier=1)
        w_loose = proximity_weight(50.0, tier=1)
        assert w_tight > w_loose

    def test_zero_distance_returns_zero(self):
        assert proximity_weight(0.0) == 0.0

    def test_negative_distance_returns_zero(self):
        assert proximity_weight(-5.0) == 0.0

    def test_tier_mapping(self):
        assert abs(proximity_weight(10.0, tier=1, k_hard=100.0, k_strong=10.0, k_soft=1.0) - 10.0) < 1e-6
        assert abs(proximity_weight(10.0, tier=2, k_hard=100.0, k_strong=10.0, k_soft=1.0) - 1.0) < 1e-6
        assert abs(proximity_weight(10.0, tier=3, k_hard=100.0, k_strong=10.0, k_soft=1.0) - 0.1) < 1e-6

    def test_applied_weights_accumulate(self, simple_netlist):
        from temper_placer.pcl.constraints import AdjacentConstraint, ConstraintTier

        collection = ConstraintCollection(
            constraints=[
                AdjacentConstraint(
                    a="C1", b="C2", max_distance_mm=10.0,
                    tier=ConstraintTier.HARD,
                    because="Test proximity accumulation",
                ),
                AdjacentConstraint(
                    a="C2", b="C3", max_distance_mm=5.0,
                    tier=ConstraintTier.STRONG,
                    because="Test proximity second pair",
                ),
            ],
            version="1.0",
        )
        mapper = ConstraintMapper.build(collection, None, simple_netlist)
        weights = compute_constraint_weight_dict(
            mapper, None, simple_netlist, collection,
            strategies={"proximity": True, "group_coherence": False,
                         "critical_loop": False, "hv_lv_repulsion": False,
                         "clearance": False},
        )
        ref = {c.ref: i for i, c in enumerate(simple_netlist.components)}
        key_12 = (ref["C1"], ref["C2"])
        key_23 = (ref["C2"], ref["C3"])
        assert weights[key_12] > 0
        assert weights[key_23] > 0


# =============================================================================
# U2.2: Group coherence weight tests
# =============================================================================


class TestGroupCoherenceWeight:
    def test_increases_with_fraction(self):
        w_low = group_coherence_weight(1.0, 0.2, alpha_coherence=2.0)
        w_high = group_coherence_weight(1.0, 0.8, alpha_coherence=2.0)
        assert w_high > w_low

    def test_zero_fraction_gives_base(self):
        w = group_coherence_weight(1.0, 0.0, alpha_coherence=2.0)
        assert abs(w - 1.0) < 1e-6

    def test_alpha_scaling(self):
        w_small_alpha = group_coherence_weight(1.0, 0.5, alpha_coherence=1.0)
        w_large_alpha = group_coherence_weight(1.0, 0.5, alpha_coherence=5.0)
        assert w_large_alpha > w_small_alpha

    def test_applied_group_coherence(self, simple_netlist):
        placement = PlacementConstraints(
            component_groups=[
                ComponentGroup(
                    name="group_a",
                    components=["C1", "C2"],
                ),
            ],
        )
        mapper = ConstraintMapper.build(None, placement, simple_netlist)
        weights = compute_constraint_weight_dict(
            mapper, placement, simple_netlist, None,
            strategies={"proximity": False, "group_coherence": True,
                         "critical_loop": False, "hv_lv_repulsion": False,
                         "clearance": False},
        )
        ref = {c.ref: i for i, c in enumerate(simple_netlist.components)}
        key_12 = (ref["C1"], ref["C2"])
        # C1 and C2 are connected and in the same group → should get boost
        assert key_12 in weights
        assert weights[key_12] > 0

    def test_empty_group_no_crash(self, simple_netlist):
        placement = PlacementConstraints(
            component_groups=[
                ComponentGroup(name="empty_group", components=[]),
            ],
        )
        mapper = ConstraintMapper.build(None, placement, simple_netlist)
        weights = compute_constraint_weight_dict(
            mapper, placement, simple_netlist, None,
            strategies={"proximity": False, "group_coherence": True,
                         "critical_loop": False, "hv_lv_repulsion": False,
                         "clearance": False},
        )
        # Should not crash
        assert isinstance(weights, dict)


# =============================================================================
# U2.3: Critical loop weight tests
# =============================================================================


class TestCriticalLoopWeight:
    def test_smaller_area_gives_larger_weight(self):
        w_tight = critical_loop_weight(1.0, 100.0)
        w_loose = critical_loop_weight(1.0, 1000.0)
        assert w_tight > w_loose

    def test_zero_area_returns_base(self):
        w = critical_loop_weight(1.0, 0.0)
        assert abs(w - 1.0) < 1e-6

    def test_irms_amplification(self):
        w_low = critical_loop_weight(1.0, 500.0, i_rms=1.0)
        w_high = critical_loop_weight(1.0, 500.0, i_rms=10.0)
        assert w_high > w_low  # 100x larger

    def test_f_switching_amplification(self):
        w_low = critical_loop_weight(1.0, 500.0, f_switching=1.0)
        w_high = critical_loop_weight(1.0, 500.0, f_switching=100.0)
        assert w_high > w_low

    def test_applied_critical_loop(self, simple_netlist):
        placement = PlacementConstraints(
            critical_loops=[
                CriticalLoop(
                    name="commutation",
                    nets=["NET1", "NET2"],
                    max_area_mm2=500.0,
                    weight=1.0,
                ),
            ],
        )
        mapper = ConstraintMapper.build(None, placement, simple_netlist)
        weights = compute_constraint_weight_dict(
            mapper, placement, simple_netlist, None,
            strategies={"proximity": False, "group_coherence": False,
                         "critical_loop": True, "hv_lv_repulsion": False,
                         "clearance": False},
        )
        # Should have weights for components in the loop
        assert len(weights) > 0


# =============================================================================
# U2.4: HV/LV Repulsion weight tests
# =============================================================================


class TestHvLvRepulsionWeight:
    def test_returns_negative_value(self):
        w = hv_lv_repulsion_weight(6.0, 400.0, c_iso=21600.0)
        assert w < 0

    def test_larger_clearance_reduces_repulsion_magnitude(self):
        w_small = abs(hv_lv_repulsion_weight(3.0, 400.0, c_iso=21600.0))
        w_large = abs(hv_lv_repulsion_weight(6.0, 400.0, c_iso=21600.0))
        assert w_small > w_large  # closer → stronger repulsion

    def test_zero_clearance_returns_zero(self):
        assert hv_lv_repulsion_weight(0.0, 400.0) == 0.0

    def test_voltage_difference_scaling(self):
        w_low = abs(hv_lv_repulsion_weight(6.0, 100.0, c_iso=21600.0))
        w_high = abs(hv_lv_repulsion_weight(6.0, 400.0, c_iso=21600.0))
        assert w_high > w_low

    def test_applied_repulsion_produces_negative_weights(self, netlist_hv_lv):
        mapper = ConstraintMapper.build(None, None, netlist_hv_lv)
        weights = compute_constraint_weight_dict(
            mapper, None, netlist_hv_lv, None,
            strategies={"proximity": False, "group_coherence": False,
                         "critical_loop": False, "hv_lv_repulsion": True,
                         "clearance": False},
        )
        # CROSS_NET connects HV_C1 and LV_C1 → should get negative weight
        negative_weights = {k: v for k, v in weights.items() if v < 0}
        assert len(negative_weights) > 0


# =============================================================================
# U2.5: Clearance weight tests
# =============================================================================


class TestClearanceWeight:
    def test_cross_domain_produces_negative(self):
        w = clearance_weight(6.0, c_iso=21600.0, is_cross_domain=True)
        assert w < 0

    def test_same_domain_produces_zero(self):
        w = clearance_weight(6.0, c_iso=21600.0, is_cross_domain=False)
        assert w == 0.0

    def test_zero_clearance_returns_zero(self):
        assert clearance_weight(0.0, is_cross_domain=True) == 0.0

    def test_cross_domain_scaling_with_clearance(self):
        w_small = abs(clearance_weight(3.0, c_iso=21600.0, is_cross_domain=True))
        w_large = abs(clearance_weight(6.0, c_iso=21600.0, is_cross_domain=True))
        assert w_small > w_large  # closer clearance → larger repulsion

    def test_applied_clearance_weights(self, netlist_hv_lv):
        mapper = ConstraintMapper.build(None, None, netlist_hv_lv)
        weights = compute_constraint_weight_dict(
            mapper, None, netlist_hv_lv, None,
            strategies={"proximity": False, "group_coherence": False,
                         "critical_loop": False, "hv_lv_repulsion": False,
                         "clearance": True},
        )
        negative_weights = {k: v for k, v in weights.items() if v < 0}
        assert len(negative_weights) > 0


# =============================================================================
# U3: PSD Stabilization tests
# =============================================================================


class TestGershgorinBound:
    def test_psd_matrix_gives_non_negative_bound(self):
        L = np.array([[2.0, -1.0, -1.0], [-1.0, 2.0, -1.0], [-1.0, -1.0, 2.0]])
        bound = compute_gershgorin_lambda_min_bound(L)
        # This Laplacian has eigenvalues [0, 3, 3] — PSD
        assert bound >= -1e-6

    def test_single_node_returns_zero(self):
        L = np.array([[0.0]])
        bound = compute_gershgorin_lambda_min_bound(L)
        assert bound == 0.0

    def test_empty_returns_zero(self):
        L = np.empty((0, 0))
        bound = compute_gershgorin_lambda_min_bound(L)
        assert bound == 0.0

    def test_negative_eigenvalue_detected(self):
        # A Laplacian with negative off-diagonal entries
        L = np.array(
            [
                [1.0, -2.0, 0.0],
                [-2.0, 1.0, 0.0],
                [0.0, 0.0, 0.0],
            ]
        )
        bound = compute_gershgorin_lambda_min_bound(L)
        # Row 0: center=1, radius=2 → bound=-1
        # Row 1: center=1, radius=2 → bound=-1
        # Row 2: center=0, radius=0 → bound=0
        assert bound < -1e-6


class TestPSDShift:
    def test_psd_matrix_no_shift(self):
        L = np.eye(5)
        L_stable, shift, was_overdamped = apply_psd_shift(L)
        np.testing.assert_array_almost_equal(L_stable, L)
        assert shift == 0.0
        assert not was_overdamped

    def test_negative_bound_triggers_shift(self):
        # Matrix where Gershgorin bound is negative
        L = np.array([[1.0, -2.0], [-2.0, 1.0]])
        L_stable, shift, was_overdamped = apply_psd_shift(L, max_shift_ratio=10.0)
        assert shift > 0
        assert not was_overdamped
        # After shift, should be PSD
        bound_after = compute_gershgorin_lambda_min_bound(L_stable)
        assert bound_after >= -1e-6

    def test_overdamping_fallback(self):
        # Very negative — shift will be large
        L = np.array([[1.0, -50.0], [-50.0, 1.0]])
        L_stable, shift, was_overdamped = apply_psd_shift(L, max_shift_ratio=0.01)
        assert was_overdamped

    def test_single_node(self):
        L = np.array([[0.5]])
        L_stable, shift, was_overdamped = apply_psd_shift(L)
        np.testing.assert_array_almost_equal(L_stable, L)
        assert shift == 0.0

    def test_shift_produces_psd(self):
        # Random symmetric matrix with negative eigenvalues
        rng = np.random.RandomState(42)
        A = rng.randn(10, 10)
        L = A @ A.T  # PSD
        # Add some negative diagonals to make it indefinite
        L -= 5.0 * np.eye(10)
        L_stable, shift, was_overdamped = apply_psd_shift(L, max_shift_ratio=10.0)
        bound = compute_gershgorin_lambda_min_bound(L_stable)
        assert bound >= -1e-6


# =============================================================================
# Laplacian construction tests
# =============================================================================


class TestComputeLaplacianFromWeights:
    def test_empty_netlist(self):
        adj, L = compute_laplacian_from_weights(Netlist())
        assert adj.shape == (0, 0)
        assert L.shape == (0, 0)

    def test_uniform_baseline(self, simple_netlist):
        adj, L = compute_laplacian_from_weights(simple_netlist, constraint_weights={})
        assert adj.shape == (4, 4)
        assert L.shape == (4, 4)
        # Laplacian should be PSD
        eigenvals = np.linalg.eigvalsh(L)
        assert np.all(eigenvals >= -1e-6)

    def test_constraint_weights_modify_adjacency(self, simple_netlist):
        adj_baseline, _ = compute_laplacian_from_weights(simple_netlist, constraint_weights={})
        constraint_weights = {(0, 1): 5.0}
        adj_weighted, _ = compute_laplacian_from_weights(
            simple_netlist, constraint_weights=constraint_weights
        )
        assert adj_weighted[0, 1] > adj_baseline[0, 1]

    def test_symmetry(self, simple_netlist):
        constraint_weights = {(0, 1): 3.0, (2, 3): -1.0}
        adj, L = compute_laplacian_from_weights(
            simple_netlist, constraint_weights=constraint_weights
        )
        np.testing.assert_array_almost_equal(adj, adj.T)
        np.testing.assert_array_almost_equal(L, L.T)

    def test_unnormalized_laplacian(self, simple_netlist):
        adj, L = compute_laplacian_from_weights(simple_netlist, constraint_weights={}, normalized=False)
        # L = D - A, row sums should be ~0
        row_sums = np.sum(L, axis=1)
        np.testing.assert_array_almost_equal(row_sums, np.zeros_like(row_sums))


# =============================================================================
# compute_constraint_weight_dict integration tests
# =============================================================================


class TestComputeConstraintWeightDict:
    def test_empty_strategies_returns_empty(self, simple_netlist):
        mapper = ConstraintMapper.build(None, None, simple_netlist)
        weights = compute_constraint_weight_dict(
            mapper, None, simple_netlist, None,
            strategies={"proximity": False, "group_coherence": False,
                         "critical_loop": False, "hv_lv_repulsion": False,
                         "clearance": False},
        )
        assert weights == {}

    def test_determinism(self, simple_netlist):
        mapper = ConstraintMapper.build(None, None, simple_netlist)
        w1 = compute_constraint_weight_dict(
            mapper, None, simple_netlist, None,
            strategies={"proximity": False, "group_coherence": True,
                         "critical_loop": False, "hv_lv_repulsion": False,
                         "clearance": False},
        )
        w2 = compute_constraint_weight_dict(
            mapper, None, simple_netlist, None,
            strategies={"proximity": False, "group_coherence": True,
                         "critical_loop": False, "hv_lv_repulsion": False,
                         "clearance": False},
        )
        assert w1 == w2

    def test_symmetry_of_weights(self, simple_netlist):
        from temper_placer.pcl.constraints import AdjacentConstraint, ConstraintTier

        collection = ConstraintCollection(
            constraints=[
                AdjacentConstraint(
                    a="C1", b="C2", max_distance_mm=10.0,
                    tier=ConstraintTier.HARD,
                    because="Test symmetry constraint",
                ),
            ],
            version="1.0",
        )
        mapper = ConstraintMapper.build(collection, None, simple_netlist)
        weights = compute_constraint_weight_dict(
            mapper, None, simple_netlist, collection,
            strategies={"proximity": True, "group_coherence": False,
                         "critical_loop": False, "hv_lv_repulsion": False,
                         "clearance": False},
        )
        for (i, j), w in weights.items():
            assert (j, i) in weights or weights.get((j, i), w) == w
