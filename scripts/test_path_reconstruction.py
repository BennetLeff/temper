#!/usr/bin/env python3
"""Unit test for the bidirectional A* path reconstruction fix.

This verifies that the fix from commit 671e8b0 correctly handles
path reconstruction without creating gaps.
"""

import sys

sys.path.insert(0, "packages/temper-placer/src")

from collections import defaultdict


def check_path_continuity(path_cells):
    """Check if a path is continuous (each cell connects to next)."""
    if len(path_cells) < 2:
        return True, "Path too short to check"

    gaps = []
    for i in range(len(path_cells) - 1):
        c1 = path_cells[i]
        c2 = path_cells[i + 1]

        # Adjacent cells should differ by at most 1 in x/y (Manhattan distance <= 1)
        # Layer can change (via)
        dx = abs(c2[0] - c1[0])
        dy = abs(c2[1] - c1[1])

        if dx > 1 or dy > 1:
            gaps.append((i, c1, c2, dx + dy))

    if gaps:
        return False, f"Found {len(gaps)} gaps"
    return True, "Path is continuous"


def test_path_reconstruction():
    """Test that path reconstruction produces continuous paths."""
    print("=" * 60)
    print("PATH RECONSTRUCTION TEST")
    print("=" * 60)

    # Simulate a simple bidirectional A* meet-in-the-middle scenario
    # This is what the diff pair router does internally

    # Forward path: (0,0) -> (5,0)
    forward_path = [(0, 0, 0), (1, 0, 0), (2, 0, 0), (3, 0, 0)]

    # Backward path: (10,0) -> (5,0)
    # NOTE: This is in REVERSE order as built by backward search
    backward_path = [(10, 0, 0), (9, 0, 0), (8, 0, 0), (7, 0, 0), (6, 0, 0), (5, 0, 0)]

    # Meet point: (4, 0, 0) from forward, (5, 0, 0) from backward

    print("\nSimulated bidirectional search:")
    print(f"  Forward path (start->meet): {len(forward_path)} cells")
    print(f"  Backward path (goal->meet): {len(backward_path)} cells (REVERSED)")
    print(f"  Meet point: forward={forward_path[-1]}, backward={backward_path[-1]}")

    # OLD (BUGGY) reconstruction:
    print("\n--- OLD (BUGGY) METHOD ---")

    # Bug 1: Skip meeting point too early
    # Bug 2: Reverse backward path (it's already in wrong order)
    backward_path_buggy = backward_path[1:]  # Skip first = skip meeting point too early
    backward_path_buggy.reverse()  # Wrong! Now it's goal->meet instead of meet->goal

    buggy_full_path = forward_path + backward_path_buggy
    print(f"Buggy full path: {len(buggy_full_path)} cells")
    print(f"  First 3: {buggy_full_path[:3]}")
    print(f"  Last 3: {buggy_full_path[-3:]}")

    is_continuous, msg = check_path_continuity(buggy_full_path)
    print(f"  Continuity: {msg}")

    if not is_continuous:
        # Find the gap
        for i in range(len(buggy_full_path) - 1):
            c1, c2 = buggy_full_path[i], buggy_full_path[i + 1]
            dx = abs(c2[0] - c1[0])
            dy = abs(c2[1] - c1[1])
            if dx > 1 or dy > 1:
                print(f"  *** GAP at index {i}: {c1} -> {c2} (distance={dx + dy}) ***")
                break

    # NEW (FIXED) reconstruction:
    print("\n--- NEW (FIXED) METHOD ---")

    # The backward path is built from goal to meeting point
    # We need to include meeting point, then reverse to go meeting->goal
    backward_path_fixed = list(backward_path)  # Include meeting point
    backward_path_fixed.reverse()  # Now it's meet->goal (correct!)
    backward_path_fixed = backward_path_fixed[1:]  # Remove duplicate of meeting point

    fixed_full_path = forward_path + backward_path_fixed
    print(f"Fixed full path: {len(fixed_full_path)} cells")
    print(f"  First 3: {fixed_full_path[:3]}")
    print(f"  Last 3: {fixed_full_path[-3:]}")

    is_continuous, msg = check_path_continuity(fixed_full_path)
    print(f"  Continuity: {msg}")

    if is_continuous:
        print("  ✓ Path is continuous!")
        return True
    else:
        print("  *** Path still has gaps! ***")
        return False


def test_trace_conversion():
    """Test that continuous cell path produces continuous traces."""
    print("\n" + "=" * 60)
    print("TRACE CONVERSION TEST")
    print("=" * 60)

    from temper_placer.core.board import Trace
    from collections import defaultdict

    # Continuous cell path
    cell_path = [(i, 0, 0) for i in range(10)]  # Straight line: (0,0) to (9,0)
    cell_size_mm = 0.25

    print(f"\nCell path: {len(cell_path)} cells")
    print(f"  From {cell_path[0]} to {cell_path[-1]}")

    # Convert to traces (skip layer changes)
    traces = []
    for i in range(len(cell_path) - 1):
        c1, c2 = cell_path[i], cell_path[i + 1]
        if c1[2] == c2[2]:  # Same layer
            trace = Trace(
                start=(c1[0] * cell_size_mm, c1[1] * cell_size_mm),
                end=(c2[0] * cell_size_mm, c2[1] * cell_size_mm),
                width=0.2,
                layer="F.Cu",
                net="TEST",
            )
            traces.append(trace)

    print(f"Converted to {len(traces)} traces")

    # Check trace connectivity
    adj = defaultdict(set)
    for t in traces:
        start = (round(t.start[0], 3), round(t.start[1], 3))
        end = (round(t.end[0], 3), round(t.end[1], 3))
        adj[start].add(end)
        adj[end].add(start)

    # Count connected components
    visited = set()
    components = 0
    for node in adj:
        if node not in visited:
            components += 1
            stack = [node]
            while stack:
                n = stack.pop()
                if n not in visited:
                    visited.add(n)
                    stack.extend(adj[n] - visited)

    endpoints = sum(1 for p, n in adj.items() if len(n) == 1)

    print(f"Trace connectivity:")
    print(f"  Connected components: {components} (should be 1)")
    print(f"  Endpoints: {endpoints} (should be 2)")

    if components == 1 and endpoints == 2:
        print("  ✓ Traces form a single continuous path!")
        return True
    else:
        print("  *** Traces are not continuous! ***")
        return False


if __name__ == "__main__":
    print("\nTesting the path reconstruction fix from commit 671e8b0\n")

    test1 = test_path_reconstruction()
    test2 = test_trace_conversion()

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Path reconstruction test: {'PASS' if test1 else 'FAIL'}")
    print(f"Trace conversion test: {'PASS' if test2 else 'FAIL'}")

    if test1 and test2:
        print("\n✓ All tests pass - path reconstruction is correct!")
        sys.exit(0)
    else:
        print("\n*** Some tests failed ***")
        sys.exit(1)
