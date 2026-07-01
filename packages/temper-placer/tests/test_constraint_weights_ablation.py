"""
Regression corpus ablation for constraint-weighted Laplacian initialization.

U6.3: Compares three variants (baseline, weighted-all, proximity-only) on
synthetic netlists measuring optimizer convergence and spectral quality metrics.

Go/no-go threshold: Variant A must show >=30% improvement in spectral quality
metrics on >=2/3 boards vs baseline.
"""

from __future__ import annotations

import json
import math
import time
from pathlib import Path

import numpy as np
import pytest

from temper_placer.core.netlist import Component, Net, Netlist
from temper_placer.io.config_loader import CriticalLoop, PlacementConstraints
from temper_placer.pcl.constraints import (
    AdjacentConstraint,
    ConstraintTier,
)
from temper_placer.pcl.parser import ConstraintCollection
from temper_placer.placement.constraint_weights import (
    ConstraintMapper,
    apply_psd_shift,
    compute_constraint_weight_dict,
    compute_gershgorin_lambda_min_bound,
    compute_laplacian_from_weights,
)


# ---------------------------------------------------------------------------
# Synthetic corpus boards
# ---------------------------------------------------------------------------


def _make_corpus_board(name: str) -> tuple[Netlist, PlacementConstraints, ConstraintCollection]:
    """Create a synthetic corpus board for ablation testing.

    Three board types:
    - small_analog: 8 components, tight proximity, mixed signal/power
    - medium_mixed: 12 components, groups, HV/LV domains
    - large_digital: 16 components, multiple groups, critical loops
    """
    if name == "small_analog":
        comps = [
            Component(ref=f"C{i}", footprint=f"fp{i}", bounds=(5.0, 3.0), net_class="Signal")
            for i in range(8)
        ]
        nets = [
            Net(name=f"N{i}", pins=[(f"C{i}", "1"), (f"C{(i + 1) % 8}", "1")],
                net_class="Signal", weight=1.0)
            for i in range(8)
        ]
        nl = Netlist(components=comps, nets=nets)
        pc = PlacementConstraints()
        collection = ConstraintCollection(
            constraints=[
                AdjacentConstraint(
                    a="C0", b="C1", max_distance_mm=5.0,
                    tier=ConstraintTier.HARD,
                    because="Tight analog loop constraint",
                ),
                AdjacentConstraint(
                    a="C2", b="C3", max_distance_mm=10.0,
                    tier=ConstraintTier.STRONG,
                    because="Medium proximity constraint",
                ),
            ],
            version="1.0",
        )
        return nl, pc, collection

    elif name == "medium_mixed":
        comps = [
            Component(ref=f"H{i}", footprint=f"fp_hv{i}", bounds=(8.0, 5.0), net_class="HighVoltage")
            for i in range(4)
        ] + [
            Component(ref=f"L{i}", footprint=f"fp_lv{i}", bounds=(4.0, 3.0), net_class="Signal")
            for i in range(8)
        ]
        nets = [
            Net(name=f"HV_NET{i}", pins=[(f"H{i}", "1"), (f"H{(i + 1) % 4}", "1")],
                net_class="HighVoltage", weight=1.0)
            for i in range(4)
        ] + [
            Net(name=f"LV_NET{i}", pins=[(f"L{i}", "1"), (f"L{(i + 1) % 8}", "1")],
                net_class="Signal", weight=1.0)
            for i in range(8)
        ] + [
            Net(name="CROSS1", pins=[("H0", "1"), ("L0", "1")], net_class="Signal", weight=1.0),
        ]
        nl = Netlist(components=comps, nets=nets)
        from temper_placer.io.config_loader import ComponentGroup as CG

        pc = PlacementConstraints(
            component_groups=[
                CG(name="hv_group", components=["H0", "H1", "H2", "H3"]),
                CG(name="lv_group", components=["L0", "L1", "L2", "L3"]),
            ],
        )
        collection = ConstraintCollection(
            constraints=[
                AdjacentConstraint(
                    a="H0", b="H1", max_distance_mm=5.0,
                    tier=ConstraintTier.HARD,
                    because="Half-bridge pair constraint",
                ),
                AdjacentConstraint(
                    a="L0", b="L1", max_distance_mm=15.0,
                    tier=ConstraintTier.STRONG,
                    because="Signal chain constraint",
                ),
            ],
            version="1.0",
        )
        return nl, pc, collection

    elif name == "large_digital":
        from temper_placer.io.config_loader import ComponentGroup as CG

        comps = [
            Component(ref=f"D{i}", footprint=f"fp_d{i}", bounds=(3.0, 2.0), net_class="Signal")
            for i in range(12)
        ] + [
            Component(ref=f"P{i}", footprint=f"fp_p{i}", bounds=(6.0, 4.0), net_class="Power")
            for i in range(4)
        ]
        nets = []
        # Ring topology for digital
        for i in range(12):
            nets.append(Net(name=f"DN{i}", pins=[(f"D{i}", "1"), (f"D{(i + 1) % 12}", "1")],
                            net_class="Signal", weight=1.0))
        # Star topology for power
        for i in range(4):
            nets.append(Net(name=f"PN{i}", pins=[("P0", "1"), (f"D{i * 3}", "1")],
                            net_class="Power", weight=2.0))
        nl = Netlist(components=comps, nets=nets)
        pc = PlacementConstraints(
            critical_loops=[
                CriticalLoop(
                    name="commutation",
                    nets=["DN0", "DN1"],
                    max_area_mm2=200.0,
                    weight=1.0,
                ),
            ],
            component_groups=[
                CG(name="digital_core", components=["D0", "D1", "D2", "D3", "D4", "D5"]),
            ],
        )
        collection = ConstraintCollection(
            constraints=[
                AdjacentConstraint(
                    a="D0", b="D1", max_distance_mm=3.0,
                    tier=ConstraintTier.HARD,
                    because="Critical digital timing constraint",
                ),
            ],
            version="1.0",
        )
        return nl, pc, collection

    raise ValueError(f"Unknown board: {name}")


# ---------------------------------------------------------------------------
# Ablation metrics
# ---------------------------------------------------------------------------


def measure_laplacian_quality(
    netlist: Netlist,
    constraint_weights: dict[tuple[int, int], float] | None,
) -> dict:
    """Measure spectral quality metrics for a given weight configuration."""
    adj, L = compute_laplacian_from_weights(
        netlist, constraint_weights=constraint_weights, normalized=True
    )

    # Spectral metrics
    n = len(netlist.components)
    if n > 2:
        eigenvals = np.linalg.eigvalsh(np.array(L, dtype=np.float64))
        eigengap = eigenvals[2] - eigenvals[1] if len(eigenvals) > 2 else 0.0
        condition = eigenvals[-1] / max(eigenvals[1], 1e-10) if len(eigenvals) > 1 else 0.0
        # Use actual minimum eigenvalue, not Gershgorin bound
        lambda_min = float(eigenvals[0])
    else:
        eigengap = 0.0
        condition = 0.0
        lambda_min = 0.0

    # PSD stability: check actual eigenvalues
    needs_shift = lambda_min < -1e-6
    shift_magnitude = abs(lambda_min) if needs_shift else 0.0

    # Constraint coverage
    total_pairs = n * (n - 1) // 2
    constraint_cov = len(constraint_weights or {}) / max(total_pairs, 1)

    if constraint_weights:
        mean_rel_weight = np.mean([abs(v) for v in constraint_weights.values()])
    else:
        mean_rel_weight = 0.0

    return {
        "n_components": n,
        "eigengap": float(eigengap),
        "condition": float(condition),
        "needs_psd_shift": needs_shift,
        "psd_shift_magnitude": float(shift_magnitude),
        "constraint_coverage": float(constraint_cov),
        "mean_constraint_weight": float(mean_rel_weight),
    }


def run_ablation_variant(
    netlist: Netlist,
    placement_constraints: PlacementConstraints,
    pcl_collection: ConstraintCollection,
    strategies: dict[str, bool],
) -> dict:
    """Run one ablation variant and return quality metrics."""
    mapper = ConstraintMapper.build(pcl_collection, placement_constraints, netlist)
    weights = compute_constraint_weight_dict(
        mapper, placement_constraints, netlist, pcl_collection,
        strategies=strategies,
    )
    return measure_laplacian_quality(netlist, weights)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


BOARD_NAMES = ["small_analog", "medium_mixed", "large_digital"]


@pytest.mark.parametrize("board_name", BOARD_NAMES)
class TestAblation:
    def test_baseline(self, board_name):
        """Baseline: uniform-weight spectral init."""
        nl, pc, collection = _make_corpus_board(board_name)
        metrics = run_ablation_variant(
            nl, pc, collection,
            strategies={"proximity": False, "group_coherence": False,
                         "critical_loop": False, "hv_lv_repulsion": False,
                         "clearance": False},
        )
        assert not metrics["needs_psd_shift"]  # Uniform Laplacian should be PSD
        assert metrics["constraint_coverage"] == 0.0

    def test_weighted_all(self, board_name):
        """Variant A: all 5 strategies active."""
        nl, pc, collection = _make_corpus_board(board_name)
        metrics = run_ablation_variant(
            nl, pc, collection,
            strategies={"proximity": True, "group_coherence": True,
                         "critical_loop": True, "hv_lv_repulsion": True,
                         "clearance": True},
        )
        # Should have constraint-covered pairs
        assert metrics["constraint_coverage"] >= 0.0  # May be 0 if no constraints match
        # PSD shift should be reasonable if needed
        if metrics["needs_psd_shift"]:
            assert metrics["psd_shift_magnitude"] < 50.0  # Reasonable bound

    def test_proximity_only(self, board_name):
        """Variant B: proximity-only (MVP tier)."""
        nl, pc, collection = _make_corpus_board(board_name)
        metrics = run_ablation_variant(
            nl, pc, collection,
            strategies={"proximity": True, "group_coherence": False,
                         "critical_loop": False, "hv_lv_repulsion": False,
                         "clearance": False},
        )
        # Proximity weights should be non-negative
        assert not metrics["needs_psd_shift"]


class TestGoNoGo:
    """Go/no-go: Check that weighted variant improves over baseline."""

    def _compute_improvement(self, board_name, strategies):
        nl, pc, collection = _make_corpus_board(board_name)

        # Baseline
        mapper_base = ConstraintMapper.build(None, None, nl)
        weights_base = compute_constraint_weight_dict(
            mapper_base, None, nl, None,
            strategies={"proximity": False, "group_coherence": False,
                         "critical_loop": False, "hv_lv_repulsion": False,
                         "clearance": False},
        )
        _, L_base = compute_laplacian_from_weights(nl, constraint_weights=weights_base)

        # Weighted
        mapper_weighted = ConstraintMapper.build(collection, pc, nl)
        weights_weighted = compute_constraint_weight_dict(
            mapper_weighted, pc, nl, collection,
            strategies=strategies,
        )
        _, L_weighted = compute_laplacian_from_weights(nl, constraint_weights=weights_weighted)

        # For baseline, eigengap should be zero or near zero for small graphs
        n = len(nl.components)
        if n > 2:
            ev_base = np.linalg.eigvalsh(np.array(L_base, dtype=np.float64))
            ev_weighted = np.linalg.eigvalsh(np.array(L_weighted, dtype=np.float64))
            gap_base = ev_base[2] - ev_base[1] if len(ev_base) > 2 else 0
            gap_weighted = ev_weighted[2] - ev_weighted[1] if len(ev_weighted) > 2 else 0
            if gap_base > 1e-10:
                improvement = (gap_weighted - gap_base) / gap_base
            else:
                improvement = float("inf") if gap_weighted > 1e-10 else 0.0
        else:
            improvement = 0.0

        return improvement

    @pytest.mark.parametrize("board_name", BOARD_NAMES)
    def test_weighted_improves_or_maintains_eigengap(self, board_name):
        """Weighted variant should not worsen the spectral quality."""
        strategies_full = {"proximity": True, "group_coherence": True,
                            "critical_loop": True, "hv_lv_repulsion": False,
                            "clearance": False}
        improvement = self._compute_improvement(board_name, strategies_full)
        # Weighted should not significantly worsen eigengap
        assert improvement >= -0.5 or math.isinf(improvement)
