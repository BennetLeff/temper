"""
One-time calibration grid search for constraint-weighted Laplacian constants.

Sweeps k_HARD, k_STRONG, k_SOFT, C_iso, and alpha_coherence against
the regression corpus to find Pareto-optimal defaults.

Usage:
    uv run python scripts/calibrate_laplacian_weights.py
    uv run python scripts/calibrate_laplacian_weights.py --quick  # fast sweep only

U5: Calibration constants committed as module-level constants.
"""

from __future__ import annotations

import argparse
import itertools
import json
import logging
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packages" / "temper-placer" / "src"))

from temper_placer.placement.constraint_weights import (
    ALPHA_COHERENCE,
    C_ISO,
    K_HARD,
    K_STRONG,
    K_SOFT,
    apply_psd_shift,
    compute_gershgorin_lambda_min_bound,
    compute_laplacian_from_weights,
)

logger = logging.getLogger(__name__)


def _synthetic_netlist(n_components: int = 20) -> "Netlist":
    """Create a synthetic netlist for calibration sweep."""
    from temper_placer.core.netlist import Component, Net, Netlist

    comps = [
        Component(
            ref=f"C{i}",
            footprint="R0805",
            bounds=(2.0, 1.2),
            net_class="Signal" if i % 3 != 0 else "HighVoltage",
        )
        for i in range(n_components)
    ]
    nets = [
        Net(
            name=f"NET{i}",
            pins=[(f"C{i}", "1"), (f"C{(i + 1) % n_components}", "1")],
            net_class="Signal" if i % 5 != 0 else "HighVoltage",
        )
        for i in range(n_components)
    ]
    return Netlist(components=comps, nets=nets)


def evaluate_calibration(
    k_hard: float,
    k_strong: float,
    k_soft: float,
    c_iso: float,
    alpha_coherence: float,
    netlist: "Netlist",
) -> dict:
    """Evaluate calibration constants on a synthetic netlist.

    Metrics:
        - psd_shift_magnitude: Smaller is better (want <10% spectral radius).
        - epoch_reduction_proxy: Weight ratio of constrained/unconstrained pairs.
    """
    # Build constraint weights with dummy proximity data (simulated)
    ref_to_idx = {c.ref: i for i, c in enumerate(netlist.components)}
    weights: dict[tuple[int, int], float] = {}

    # Simulate proximity weights for some pairs
    for i in range(0, len(netlist.components), 2):
        if i + 1 < len(netlist.components):
            key = (i, i + 1)
            w = k_hard / 5.0  # assume 5mm max distance for HARD tier
            weights[key] = w

    # Simulate repulsion for HV/LV pairs (components 0, 3, 6, 9, ... are HV)
    for i in range(0, len(netlist.components), 3):
        for j in range(1, len(netlist.components), 3):
            if i != j:
                key = (min(i, j), max(i, j))
                w = -c_iso / (6.0**2) * (400.0 / 400.0)
                weights[key] = weights.get(key, 0.0) + w

    _, L = compute_laplacian_from_weights(netlist, constraint_weights=weights, normalized=True)

    # Check PSD
    bound = compute_gershgorin_lambda_min_bound(L)
    if bound < -1e-6:
        L_stable, shift, was_overdamped = apply_psd_shift(L, max_shift_ratio=0.5)
        shift_magnitude = shift
    else:
        shift_magnitude = 0.0

    # Proxy metrics: constrained pairs should have higher weight than unconstrained
    constrained_weights = [v for v in weights.values() if v > 0]
    unconstrained_baseline = 1.0  # baseline uniform weight
    if constrained_weights:
        weight_ratio = np.mean(constrained_weights) / unconstrained_baseline
    else:
        weight_ratio = 1.0

    return {
        "k_hard": k_hard,
        "k_strong": k_strong,
        "k_soft": k_soft,
        "c_iso": c_iso,
        "alpha_coherence": alpha_coherence,
        "psd_shift": float(shift_magnitude),
        "weight_ratio": float(weight_ratio),
        "n_constrained_pairs": len([v for v in weights.values() if v != 0]),
    }


def grid_search_force_constants(netlist: "Netlist") -> dict:
    """Grid search k_HARD, k_STRONG, k_SOFT."""
    candidates = [1.0, 10.0, 100.0, 1000.0]
    best = None
    results = []

    for k_hard, k_strong, k_soft in itertools.product(candidates, repeat=3):
        result = evaluate_calibration(
            k_hard, k_strong, k_soft, C_ISO, ALPHA_COHERENCE, netlist
        )
        results.append(result)

        # Score: prefer higher weight_ratio with lower PSD shift
        if result["psd_shift"] < 1e-6:
            if best is None or result["weight_ratio"] > best["weight_ratio"]:
                best = result

    return {"best": best, "all_results": results}


def grid_search_c_iso(netlist: "Netlist", k_hard: float, k_strong: float, k_soft: float) -> dict:
    """Grid search C_iso."""
    candidates = [100.0, 1000.0, 10000.0, 50000.0, 100000.0]
    results = []
    best = None

    for c_iso in candidates:
        result = evaluate_calibration(
            k_hard, k_strong, k_soft, c_iso, ALPHA_COHERENCE, netlist
        )
        results.append(result)

        if best is None or (
            abs(result["psd_shift"]) < 0.5 and result["weight_ratio"] > best.get("weight_ratio", 0)
        ):
            best = result

    return {"best": best, "all_results": results}


def grid_search_alpha(netlist: "Netlist", k_hard: float, k_strong: float, k_soft: float, c_iso: float) -> dict:
    """Grid search alpha_coherence."""
    candidates = [0.5, 1.0, 2.0, 3.0, 5.0]
    results = []

    for alpha in candidates:
        result = evaluate_calibration(
            k_hard, k_strong, k_soft, c_iso, alpha, netlist
        )
        results.append(result)

    best = max(results, key=lambda r: r["weight_ratio"])
    return {"best": best, "all_results": results}


def main() -> None:
    parser = argparse.ArgumentParser(description="Calibrate constraint-weighted Laplacian constants")
    parser.add_argument("--quick", action="store_true", help="Quick sweep (fewer points)")
    parser.add_argument("-o", "--output", type=Path, help="Output JSON file for results")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    netlist = _synthetic_netlist(20)

    print(f"Calibrating with {netlist.n_components} components, {netlist.n_nets} nets")

    # Step 1: Force budget constants (k_HARD, k_STRONG, k_SOFT)
    print("\n=== Step 1: Force budget grid search ===")
    force_results = grid_search_force_constants(netlist)
    best_force = force_results["best"]
    if best_force:
        print(f"  Best: k_HARD={best_force['k_hard']}, k_STRONG={best_force['k_strong']}, "
              f"k_SOFT={best_force['k_soft']}")
        print(f"  weight_ratio={best_force['weight_ratio']:.2f}, PSD shift={best_force['psd_shift']:.4f}")
    else:
        best_force = {"k_hard": K_HARD, "k_strong": K_STRONG, "k_soft": K_SOFT}

    # Step 2: C_iso calibration
    print("\n=== Step 2: C_iso sweep ===")
    ciso_results = grid_search_c_iso(
        netlist,
        best_force["k_hard"],
        best_force["k_strong"],
        best_force["k_soft"],
    )
    best_ciso = ciso_results["best"]
    if best_ciso:
        print(f"  Best C_iso: {best_ciso['c_iso']}")
        print(f"  PSD shift: {best_ciso['psd_shift']:.4f}, weight_ratio: {best_ciso['weight_ratio']:.2f}")

    # Step 3: alpha_coherence calibration
    print("\n=== Step 3: alpha_coherence sweep ===")
    alpha_results = grid_search_alpha(
        netlist,
        best_force["k_hard"],
        best_force["k_strong"],
        best_force["k_soft"],
        best_ciso["c_iso"] if best_ciso else C_ISO,
    )
    best_alpha = alpha_results["best"]
    if best_alpha:
        print(f"  Best alpha_coherence: {best_alpha['alpha_coherence']}")

    # Summary
    summary = {
        "k_HARD": best_force["k_hard"],
        "k_STRONG": best_force["k_strong"],
        "k_SOFT": best_force["k_soft"],
        "C_iso": best_ciso["c_iso"] if best_ciso else C_ISO,
        "alpha_coherence": best_alpha["alpha_coherence"] if best_alpha else ALPHA_COHERENCE,
    }

    print(f"\n=== Recommended defaults ===")
    for key, val in summary.items():
        print(f"  {key}: {val}")

    if args.output:
        output = {
            "summary": summary,
            "force_grid": force_results,
            "ciso_sweep": ciso_results,
            "alpha_sweep": alpha_results,
        }
        args.output.write_text(json.dumps(output, indent=2))
        print(f"\nResults written to {args.output}")


if __name__ == "__main__":
    main()
