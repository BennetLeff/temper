"""VERBATIM pin of the two geometry kernels in
``temper_placer/io/kicad_exporter.py`` at origin/main ``71790a0e5``
(the ``kicad_exporter.py`` file itself was last touched at ``550cab2a3``).

This file is the pre-migration oracle for the Wave-4 Phase-3 KiCad-exporter
geometry migration. ``snap_to_nearest_pad`` and ``_generate_connector_segments``
are copied byte-for-byte from the shipped module and MUST NOT be "improved",
reformatted, or kept in sync with the post-migration source: their whole value
is that they are frozen. ``test_kicad_exporter_geometry_rust_differential.py``
asserts the migrated Rust implementation
(``temper_design_bundle_python.kicad_exporter_geometry``) reproduces this
file's output bit-for-bit.

Only the two GEOMETRY kernels are pinned here -- not the whole module. See
``packages/temper-design-bundle/src/kicad_exporter_geometry.rs`` module
docstring for the full triage of what was and was not ported from
``kicad_exporter.py``, and why.

No import redirection was needed: both functions depend only on the stdlib
``math`` module and their own parameters (``TraceSegment`` inputs are
accepted structurally, not imported), so there is nothing upstream that a
redirect could accidentally point at the code under test.
"""

from __future__ import annotations

import math

from temper_placer.io.export_types import TraceSegment


def snap_to_nearest_pad(
    x: float,
    y: float,
    pad_centers: list[tuple[float, float]],
    tolerance: float = 0.15,  # Sufficient for 0.25mm grid half-cell
) -> tuple[float, float]:
    """Snap coordinate to nearest pad center if within tolerance."""
    import math

    best_dist = tolerance
    best_pos = (x, y)

    for px, py in pad_centers:
        dist = math.sqrt((x - px) ** 2 + (y - py) ** 2)
        if dist < best_dist:
            best_dist = dist
            best_pos = (px, py)

    return best_pos


def _generate_connector_segments(
    segments: list,
    pad_centers: dict[str, list[tuple[float, float]]],
    max_dist: float = 2.0,
) -> list:
    """
    Generate connector segments to bridge gaps between track endpoints and pads.

    The skeleton router stops at the medial axis, which may be 1-2mm away from
    the actual pad center. This function detects 'dangling' track ends near pads
    and adds a straight segment to connect them.

    Args:
        segments: List of existing trace segments
        pad_centers: Dict mapping net name to list of pad coordinates (x, y)
        max_dist: Maximum distance to bridge (mm)

    Returns:
        List of NEW connector segments
    """
    connectors = []

    # Organize segments by net for faster lookup
    segs_by_net: dict[str, list] = {}
    for seg in segments:
        if seg.net not in segs_by_net:
            segs_by_net[seg.net] = []
        segs_by_net[seg.net].append(seg)

    for net, pads in pad_centers.items():
        if net not in segs_by_net:
            continue

        net_segs = segs_by_net[net]

        # Collect all unique endpoints of existing segments
        endpoints = set()
        for seg in net_segs:
            endpoints.add(seg.start)
            endpoints.add(seg.end)

        # Check each pad
        for px, py in pads:
            # Is this pad already connected? (Exact match)
            is_connected = False
            for ex, ey in endpoints:
                if abs(ex - px) < 0.01 and abs(ey - py) < 0.01:
                    is_connected = True
                    break

            if is_connected:
                continue

            # Find nearest endpoint
            nearest_ep = None
            min_dist = float("inf")

            for ex, ey in endpoints:
                dist = math.sqrt((ex - px) ** 2 + (ey - py) ** 2)
                if dist < min_dist:
                    min_dist = dist
                    nearest_ep = (ex, ey)

            # If nearest endpoint is close enough, bridge it!
            if nearest_ep and min_dist < max_dist:
                # Use attributes from nearest segment to match width/layer
                # Need to find which segment has this endpoint
                ref_seg = None
                for seg in net_segs:
                    if seg.start == nearest_ep or seg.end == nearest_ep:
                        ref_seg = seg
                        break

                if ref_seg:
                    connectors.append(
                        TraceSegment(
                            net=net,
                            start=nearest_ep,
                            end=(px, py),
                            width=ref_seg.width,
                            layer=ref_seg.layer,
                        )
                    )
                    # Add to endpoints so we don't try to connect again
                    endpoints.add((px, py))

    return connectors
