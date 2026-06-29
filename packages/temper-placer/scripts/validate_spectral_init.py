#!/usr/bin/env python3
"""
Validation script for spectral initialization (temper-1my.7.5).

Compares random vs spectral initialization on libresolar_bms (209 components).

Usage:
    python scripts/validate_spectral_init.py

Expected outcomes:
    - Spectral init should achieve <1.5x baseline wirelength (vs 2.26x with random)
    - Initial wirelength should be <50% of random init
    - Convergence in <1500 epochs (vs >2000 with random)
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import jax
import jax.numpy as jnp

from temper_placer.core.state import PlacementState
from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.optimizer.initialization import SpectralInitializer


def load_libresolar_bms():
    """Load libresolar_bms PCB and constraints."""
    pcb_path = Path("tests/fixtures/external/.cache/libresolar_bms/libresolar_bms_unrouted.kicad_pcb")
    Path("tests/fixtures/external/.cache/libresolar_bms/libresolar_bms_constraints.yaml")
    Path("tests/fixtures/external/.cache/libresolar_bms/libresolar_bms_baseline.yaml")

    print(f"Loading PCB from {pcb_path}")
    result = parse_kicad_pcb(pcb_path)

    netlist = result.netlist
    board = result.board

    print(f"  - Components: {len(netlist.components)}")
    print(f"  - Nets: {len(netlist.nets)}")
    print(f"  - Board: {board.width:.1f}mm x {board.height:.1f}mm")

    return netlist, board


def compute_wirelength(positions, netlist):
    """Compute total wirelength for given positions."""
    # Create minimal context for wirelength computation
    ref_to_idx = {comp.ref: i for i, comp in enumerate(netlist.components)}

    total_wl = 0.0
    for net in netlist.nets:
        # Get component indices for this net
        indices = []
        for comp_ref, _ in net.pins:
            if comp_ref in ref_to_idx:
                indices.append(ref_to_idx[comp_ref])

        # Remove duplicates
        indices = list(set(indices))

        if len(indices) < 2:
            continue

        # Compute bounding box wirelength (HPWL)
        net_positions = positions[jnp.array(indices)]
        min_pos = jnp.min(net_positions, axis=0)
        max_pos = jnp.max(net_positions, axis=0)
        wl = jnp.sum(max_pos - min_pos)
        total_wl += wl

    return total_wl


def main():
    print("=" * 80)
    print("Spectral Initialization Validation (temper-1my.7.5)")
    print("=" * 80)
    print()

    # Load board
    netlist, board = load_libresolar_bms()
    print()

    # Test 1: Random initialization
    print("Test 1: Random Initialization")
    print("-" * 80)
    key = jax.random.PRNGKey(42)

    state_random = PlacementState.random_init(
        n_components=len(netlist.components),
        board_width=board.width,
        board_height=board.height,
        key=key,
        margin=10.0,
        origin=board.origin,
    )

    wl_random = compute_wirelength(state_random.positions, netlist)
    print(f"Initial wirelength (random): {wl_random:.1f} mm")
    print()

    # Test 2: Spectral initialization
    print("Test 2: Spectral Initialization")
    print("-" * 80)

    spectral_init = SpectralInitializer(normalized_laplacian=True, margin_fraction=0.1)
    positions_spectral = spectral_init.initialize(netlist, board)

    wl_spectral = compute_wirelength(positions_spectral, netlist)
    print(f"Initial wirelength (spectral): {wl_spectral:.1f} mm")
    print()

    # Comparison
    print("Comparison")
    print("-" * 80)
    improvement = (wl_random - wl_spectral) / wl_random * 100
    ratio = wl_spectral / wl_random

    print(f"Wirelength reduction: {improvement:+.1f}%")
    print(f"Spectral / Random ratio: {ratio:.2f}x")
    print()

    # Success criteria
    print("Success Criteria")
    print("-" * 80)

    target_improvement = 50.0  # Expect at least 50% better initial wirelength
    success = improvement >= target_improvement

    if success:
        print(f"✅ PASS: Spectral init achieved {improvement:.1f}% improvement")
        print(f"   (target: >={target_improvement:.1f}%)")
    else:
        print(f"❌ FAIL: Spectral init achieved only {improvement:.1f}% improvement")
        print(f"   (target: >={target_improvement:.1f}%)")

    print()
    print("Next Steps:")
    print("  1. Run full optimization with both initializations")
    print("  2. Compare final wirelength after 2000 epochs")
    print("  3. Target: Spectral achieves <1.5x baseline (vs 2.26x with random)")
    print()

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
