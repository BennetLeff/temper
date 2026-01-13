#!/usr/bin/env python3.11
"""Test Numba optimization for _heuristic_3d."""

import sys
import time

sys.path.insert(0, "packages/temper-placer/src")

from temper_placer.deterministic.stages.multilayer_astar import _heuristic_3d_numba


def test_heuristic_numba():
    """Test that _heuristic_3d_numba works correctly."""
    print("Testing _heuristic_3d_numba optimization...")

    # Test 1: Basic functionality
    print("\n=== Test 1: Basic functionality ===")

    # Same layer - should have no via cost
    h1 = _heuristic_3d_numba(0, 0, 0, 10, 10, 0, 5.0)
    expected1 = max(10, 10) + 0.414 * min(10, 10)  # 10 + 4.14 = 14.14
    print(f"Same layer (0,0,0) -> (10,10,0): h={h1:.2f}, expected={expected1:.2f}")
    assert abs(h1 - expected1) < 0.01, f"Expected {expected1}, got {h1}"

    # Different layer - should add via cost
    h2 = _heuristic_3d_numba(0, 0, 0, 10, 10, 1, 5.0)
    expected2 = max(10, 10) + 0.414 * min(10, 10) + 5.0  # 14.14 + 5.0 = 19.14
    print(f"Different layer (0,0,0) -> (10,10,1): h={h2:.2f}, expected={expected2:.2f}")
    assert abs(h2 - expected2) < 0.01, f"Expected {expected2}, got {h2}"

    # Cardinal move (no diagonal)
    h3 = _heuristic_3d_numba(0, 0, 0, 10, 0, 0, 5.0)
    expected3 = 10.0  # Straight line
    print(f"Cardinal move (0,0,0) -> (10,0,0): h={h3:.2f}, expected={expected3:.2f}")
    assert abs(h3 - expected3) < 0.01, f"Expected {expected3}, got {h3}"

    # Test 2: Benchmark performance
    print("\n=== Test 2: Benchmark (1 million calls) ===")

    iterations = 1_000_000
    start = time.time()
    total = 0.0
    for i in range(iterations):
        # Vary the parameters to prevent optimization
        total += _heuristic_3d_numba(
            i % 100, i % 100, i % 2, (i + 50) % 100, (i + 50) % 100, (i + 1) % 2, 5.0
        )
    elapsed = time.time() - start

    print(f"Time for {iterations:,} calls: {elapsed:.4f}s")
    print(f"Average per call: {elapsed / iterations * 1e6:.3f}µs")
    print(f"Calls per second: {iterations / elapsed:,.0f}")
    print(f"Total sum (sanity check): {total:.0f}")

    # Expected: ~10-100ns per call with Numba (100-1000x faster than Python)
    if elapsed / iterations < 1e-6:  # Less than 1µs per call
        print("✅ Excellent performance (< 1µs per call)")
    elif elapsed / iterations < 10e-6:  # Less than 10µs per call
        print("✅ Good performance (< 10µs per call)")
    else:
        print("⚠️  Performance not as fast as expected")

    print("\n✅ All tests passed!")
    return True


if __name__ == "__main__":
    success = test_heuristic_numba()
    sys.exit(0 if success else 1)
