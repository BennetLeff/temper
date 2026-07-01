"""
A/B comparison script for constraint-weighted vs uniform Laplacian initialization.

U6.4: Runs baseline and constraint-weighted variants side-by-side,
outputs per-design metrics for CI dashboard integration.

Usage:
    uv run python packages/temper-placer/scripts/ab_test_laplacian.py --board small_analog
    uv run python packages/temper-placer/scripts/ab_test_laplacian.py --board small_analog --output results.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from temper_placer.core.netlist import Component, Net, Netlist
from temper_placer.io.config_loader import ComponentGroup as CG
from temper_placer.io.config_loader import CriticalLoop, PlacementConstraints
from temper_placer.pcl.constraints import AdjacentConstraint, ConstraintTier
from temper_placer.pcl.parser import ConstraintCollection
from temper_placer.placement.constraint_weights import (
    ConstraintMapper,
    compute_constraint_weight_dict,
    compute_gershgorin_lambda_min_bound,
    compute_laplacian_from_weights,
)


# ---------------------------------------------------------------------------
# Known test boards (mirrors ablation test boards)
# ---------------------------------------------------------------------------


def _make_board(name: str) -> tuple[Netlist, PlacementConstraints, ConstraintCollection]:
    """Create a synthetic corpus board."""
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
                AdjacentConstraint(a="C0", b="C1", max_distance_mm=5.0,
                                   tier=ConstraintTier.HARD, because="Test tight loop"),
                AdjacentConstraint(a="C2", b="C3", max_distance_mm=10.0,
                                   tier=ConstraintTier.STRONG, because="Test medium"),
            ],
            version="1.0",
        )
        return nl, pc, collection

    elif name == "medium_mixed":
        comps = [
            Component(ref=f"H{i}", footprint="fp", bounds=(8, 5), net_class="HighVoltage")
            for i in range(4)
        ] + [
            Component(ref=f"L{i}", footprint="fp", bounds=(4, 3), net_class="Signal")
            for i in range(8)
        ]
        nets = [
            Net(name=f"HV_NET{i}", pins=[(f"H{i}", "1"), (f"H{(i + 1) % 4}", "1")],
                net_class="HighVoltage") for i in range(4)
        ] + [
            Net(name=f"LV_NET{i}", pins=[(f"L{i}", "1"), (f"L{(i + 1) % 8}", "1")],
                net_class="Signal") for i in range(8)
        ] + [
            Net(name="CROSS1", pins=[("H0", "1"), ("L0", "1")], net_class="Signal"),
        ]
        nl = Netlist(components=comps, nets=nets)
        pc = PlacementConstraints(
            component_groups=[
                CG(name="hv_group", components=["H0", "H1", "H2", "H3"]),
                CG(name="lv_group", components=["L0", "L1", "L2", "L3"]),
            ],
        )
        collection = ConstraintCollection(
            constraints=[
                AdjacentConstraint(a="H0", b="H1", max_distance_mm=5.0,
                                   tier=ConstraintTier.HARD, because="Half-bridge"),
                AdjacentConstraint(a="L0", b="L1", max_distance_mm=15.0,
                                   tier=ConstraintTier.STRONG, because="Signal chain"),
            ],
            version="1.0",
        )
        return nl, pc, collection

    elif name == "large_digital":
        comps = [
            Component(ref=f"D{i}", footprint="fp", bounds=(3, 2), net_class="Signal")
            for i in range(12)
        ] + [
            Component(ref=f"P{i}", footprint="fp", bounds=(6, 4), net_class="Power")
            for i in range(4)
        ]
        nets = [Net(name=f"DN{i}", pins=[(f"D{i}", "1"), (f"D{(i + 1) % 12}", "1")],
                    net_class="Signal") for i in range(12)]
        nets += [Net(name=f"PN{i}", pins=[("P0", "1"), (f"D{i * 3}", "1")],
                     net_class="Power", weight=2.0) for i in range(4)]
        nl = Netlist(components=comps, nets=nets)
        pc = PlacementConstraints(
            critical_loops=[
                CriticalLoop(name="commutation", nets=["DN0", "DN1"],
                             max_area_mm2=200.0, weight=1.0),
            ],
            component_groups=[
                CG(name="digital_core", components=["D0", "D1", "D2", "D3", "D4", "D5"]),
            ],
        )
        collection = ConstraintCollection(
            constraints=[
                AdjacentConstraint(a="D0", b="D1", max_distance_mm=3.0,
                                   tier=ConstraintTier.HARD, because="Critical timing"),
            ],
            version="1.0",
        )
        return nl, pc, collection

    raise ValueError(f"Unknown board: {name}")


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def compute_metrics(
    netlist: Netlist,
    constraint_weights: dict[tuple[int, int], float] | None,
    label: str,
) -> dict[str, Any]:
    """Compute spectral quality metrics for a variant."""
    adj, L = compute_laplacian_from_weights(
        netlist, constraint_weights=constraint_weights, normalized=True,
    )

    n = len(netlist.components)
    if n > 2:
        ev = np.linalg.eigvalsh(np.array(L, dtype=np.float64))
        eigengap = float(ev[2] - ev[1])
        lambda_min = float(ev[0])
    else:
        eigengap = 0.0
        lambda_min = 0.0

    n_constrained = len(constraint_weights or {})
    total_pairs = n * (n - 1) // 2
    constraint_cov = n_constrained / max(total_pairs, 1)

    mean_weight = float(np.mean([abs(v) for v in (constraint_weights or {}).values()])) if constraint_weights else 0.0

    return {
        "variant": label,
        "n_components": n,
        "eigengap": eigengap,
        "lambda_min": lambda_min,
        "n_constrained_pairs": n_constrained,
        "constraint_coverage": constraint_cov,
        "mean_constraint_weight": mean_weight,
        "needs_psd_shift": lambda_min < -1e-6,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="A/B compare constraint-weighted vs uniform Laplacian init",
    )
    parser.add_argument("--board", default="medium_mixed",
                        choices=["small_analog", "medium_mixed", "large_digital"],
                        help="Board to compare")
    parser.add_argument("--output", type=Path, help="Output CSV file")
    args = parser.parse_args()

    nl, pc, collection = _make_board(args.board)

    # Baseline: uniform
    mapper = ConstraintMapper.build(None, None, nl)
    baseline_weights = compute_constraint_weight_dict(
        mapper, None, nl, None,
        strategies={"proximity": False, "group_coherence": False,
                     "critical_loop": False, "hv_lv_repulsion": False,
                     "clearance": False},
    )
    baseline_metrics = compute_metrics(nl, baseline_weights, "baseline")

    # Weighted: all active (without repulsion by default)
    mapper_weighted = ConstraintMapper.build(collection, pc, nl)
    weighted_weights = compute_constraint_weight_dict(
        mapper_weighted, pc, nl, collection,
        strategies={"proximity": True, "group_coherence": True,
                     "critical_loop": True, "hv_lv_repulsion": False,
                     "clearance": False},
    )
    weighted_metrics = compute_metrics(nl, weighted_weights, "weighted")

    # Comparison
    import json
    report = {
        "board": args.board,
        "baseline": baseline_metrics,
        "weighted": weighted_metrics,
        "deltas": {
            "eigengap_delta": weighted_metrics["eigengap"] - baseline_metrics["eigengap"],
            "constraint_pairs": weighted_metrics["n_constrained_pairs"],
        },
    }
    print(json.dumps(report, indent=2))

    if args.output:
        fieldnames = sorted(baseline_metrics.keys())
        with open(args.output, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerow(baseline_metrics)
            writer.writerow(weighted_metrics)
        print(f"\nResults written to {args.output}")


if __name__ == "__main__":
    main()
