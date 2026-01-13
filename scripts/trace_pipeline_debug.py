#!/usr/bin/env python3
"""Debug script to trace USB segment counts through the pipeline."""

import sys

sys.path.insert(0, "packages/temper-placer/src")

from collections import defaultdict
from temper_placer.core.board import Trace


def count_usb_traces(routes, label=""):
    """Count USB D+/D- traces and check connectivity."""
    usb_dp = [t for t in routes if isinstance(t, Trace) and t.net == "USB_D+"]
    usb_dm = [t for t in routes if isinstance(t, Trace) and t.net == "USB_D-"]

    print(f"\n=== {label} ===")
    print(f"USB_D+ traces: {len(usb_dp)}")
    print(f"USB_D- traces: {len(usb_dm)}")

    # Check connectivity for USB_D+
    if usb_dp:
        adj = defaultdict(set)
        for t in usb_dp:
            start = (round(t.start[0], 3), round(t.start[1], 3))
            end = (round(t.end[0], 3), round(t.end[1], 3))
            adj[start].add(end)
            adj[end].add(start)

        # Count connected components via DFS
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

        endpoints = [p for p, n in adj.items() if len(n) == 1]
        print(f"USB_D+ connected components: {components} (should be 1)")
        print(f"USB_D+ endpoints: {len(endpoints)} (should be 2)")

        if usb_dp:
            xs = [t.start[0] for t in usb_dp] + [t.end[0] for t in usb_dp]
            print(f"USB_D+ X span: {min(xs):.2f} to {max(xs):.2f} mm")

    return len(usb_dp), len(usb_dm)


def test_dedup_collision():
    """Test if deduplication causes false collisions on adjacent segments."""
    print("\n" + "=" * 60)
    print("Testing deduplication collision on adjacent segments")
    print("=" * 60)

    # Create a chain of 10 adjacent segments (simulating USB trace)
    # Each segment is 0.25mm long (cell size)
    segments = []
    for i in range(10):
        x_start = 70.0 + i * 0.25
        x_end = 70.0 + (i + 1) * 0.25
        y = 50.0
        segments.append(
            Trace(start=(x_start, y), end=(x_end, y), width=0.2, layer="F.Cu", net="USB_D+")
        )

    print(f"\nInput: {len(segments)} adjacent segments")
    for i, s in enumerate(segments[:3]):
        print(
            f"  Segment {i}: ({s.start[0]:.3f}, {s.start[1]:.3f}) -> ({s.end[0]:.3f}, {s.end[1]:.3f})"
        )
    print(f"  ...")

    # Run through deduplication logic
    tolerance = 0.05  # Same as TrackDeduplicationStage
    seen = set()
    unique = []
    duplicates = 0

    for trace in segments:
        start, end = trace.start, trace.end
        if (start[0], start[1]) > (end[0], end[1]):
            start, end = end, start

        key = (
            round(start[0] / tolerance) * tolerance,
            round(start[1] / tolerance) * tolerance,
            round(end[0] / tolerance) * tolerance,
            round(end[1] / tolerance) * tolerance,
            trace.layer,
        )

        if key in seen:
            duplicates += 1
            print(f"  COLLISION: Segment {len(unique) + duplicates - 1} key={key}")
            continue

        seen.add(key)
        unique.append(trace)

    print(f"\nResult: {len(unique)} unique, {duplicates} duplicates")

    if duplicates > 0:
        print("\n*** BUG FOUND: Adjacent segments incorrectly deduplicated! ***")
        return False
    else:
        print("\n✓ No collisions - deduplication logic is correct")
        return True


def test_frozenset_dedup():
    """Test if frozenset causes deduplication of distinct Trace objects."""
    print("\n" + "=" * 60)
    print("Testing frozenset behavior with Trace objects")
    print("=" * 60)

    # Create distinct trace objects
    traces = [
        Trace(start=(70.0, 50.0), end=(70.25, 50.0), width=0.2, layer="F.Cu", net="USB_D+"),
        Trace(start=(70.25, 50.0), end=(70.5, 50.0), width=0.2, layer="F.Cu", net="USB_D+"),
        Trace(start=(70.5, 50.0), end=(70.75, 50.0), width=0.2, layer="F.Cu", net="USB_D+"),
    ]

    print(f"\nInput: {len(traces)} traces")
    for i, t in enumerate(traces):
        print(f"  Trace {i}: hash={hash(t)}, start={t.start}, end={t.end}")

    # Check if hashes are unique
    hashes = [hash(t) for t in traces]
    unique_hashes = len(set(hashes))
    print(f"\nUnique hashes: {unique_hashes}/{len(traces)}")

    # Check frozenset
    fs = frozenset(traces)
    print(f"frozenset size: {len(fs)}")

    if len(fs) != len(traces):
        print("\n*** BUG FOUND: frozenset deduplicated distinct Trace objects! ***")
        return False
    else:
        print("\n✓ frozenset correctly preserves all traces")
        return True


def test_key_precision():
    """Test if key computation has precision issues."""
    print("\n" + "=" * 60)
    print("Testing key precision with various coordinate values")
    print("=" * 60)

    tolerance = 0.05

    # Test coordinates that might have precision issues
    test_coords = [
        (70.0, 70.25),  # Clean values
        (70.125, 70.375),  # Values that might round
        (70.024, 70.026),  # Values near tolerance boundary
        (70.049, 70.051),  # Values at tolerance boundary
    ]

    keys = []
    for x1, x2 in test_coords:
        key1 = round(x1 / tolerance) * tolerance
        key2 = round(x2 / tolerance) * tolerance
        keys.append((key1, key2))
        print(f"  ({x1:.3f}, {x2:.3f}) -> keys ({key1:.3f}, {key2:.3f})")

    # Check if any distinct coordinates map to same key
    collisions = 0
    for i, (x1a, x2a) in enumerate(test_coords):
        for j, (x1b, x2b) in enumerate(test_coords):
            if i < j:
                if keys[i] == keys[j]:
                    print(f"\n  COLLISION: coords {i} and {j} have same key!")
                    collisions += 1

    if collisions > 0:
        print(f"\n*** WARNING: {collisions} potential precision collisions ***")
    else:
        print("\n✓ No precision collisions detected")

    return collisions == 0


if __name__ == "__main__":
    print("=" * 60)
    print("USB TRACE PIPELINE DEBUG")
    print("=" * 60)

    # Run unit tests first
    ok1 = test_dedup_collision()
    ok2 = test_frozenset_dedup()
    ok3 = test_key_precision()

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Dedup collision test: {'PASS' if ok1 else 'FAIL'}")
    print(f"Frozenset test: {'PASS' if ok2 else 'FAIL'}")
    print(f"Key precision test: {'PASS' if ok3 else 'FAIL'}")

    if all([ok1, ok2, ok3]):
        print("\n✓ All basic tests pass - issue is likely elsewhere in pipeline")
        print("\nNext step: Add instrumentation to actual pipeline stages")
    else:
        print("\n*** Bug identified in basic tests! ***")
