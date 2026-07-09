"""AI-Slop Pattern Linter — Post-route detection of machine-routing artifacts.

Detects four artifact classes on routed PCB files:
- Hairpin turns: track segments reversing direction within a close distance.
- Zigzag patterns: 3+ consecutive alternating direction changes.
- Isolated vias: vias with only one connected track segment (stubs).
- Single-net detours: nets where path_length / direct_distance exceeds a
  threshold.

Each lint function returns a list of findings (dicts with location, type,
severity, and description).  Gate: ``lint_all`` returns 0 artifacts.

Based on R5 of the human-like-routing-quality plan.
"""

from __future__ import annotations

import math
from pathlib import Path


def lint_hairpin_turns(routed_pcb_path: Path) -> list[dict]:
    """Find track segments that reverse direction by >=160deg.

    Parses the routed PCB, groups traces by net, orders them into
    connected paths, and checks the turn angle at each junction.
    """
    traces_by_net = _load_traces_by_net(routed_pcb_path)
    findings: list[dict] = []

    for net_name, traces in traces_by_net.items():
        ordered = _order_traces(traces)
        for i in range(1, len(ordered)):
            prev = ordered[i - 1]
            curr = ordered[i]
            angle = _angle_between(
                (prev["end"], prev["start"]),  # reverse incoming
                (curr["start"], curr["end"]),  # outgoing
            )
            if angle >= 160.0:
                findings.append({
                    "type": "hairpin",
                    "net_name": net_name,
                    "position": prev["end"],
                    "severity": angle,
                    "description": (
                        f"Hairpin turn ({angle:.1f} deg) at "
                        f"({prev['end'][0]:.2f}, {prev['end'][1]:.2f}) mm"
                    ),
                })
    return findings


def lint_zigzag_patterns(routed_pcb_path: Path) -> list[dict]:
    """Find 3+ consecutive alternating direction changes.

    Excludes hairpin reversals (>=160 deg) from the alternation count.
    """
    traces_by_net = _load_traces_by_net(routed_pcb_path)
    findings: list[dict] = []

    for net_name, traces in traces_by_net.items():
        ordered = _order_traces(traces)
        if len(ordered) < 4:
            continue

        # Determine turn direction at each junction.
        # "left" = +delta_angle, "right" = -delta_angle.
        turns: list[tuple[int, float, str]] = []  # (idx, angle, dir)
        for i in range(1, len(ordered)):
            prev = ordered[i - 1]
            curr = ordered[i]
            angle = _angle_between(
                (prev["end"], prev["start"]),
                (curr["start"], curr["end"]),
            )
            if angle >= 160.0:
                continue  # exclude hairpins
            if angle < 5.0:
                continue  # almost-straight, not a meaningful turn
            # Determine left vs right via cross-product sign.
            v_in = _vector(prev["end"], prev["start"])
            v_out = _vector(curr["start"], curr["end"])
            cross = v_in[0] * v_out[1] - v_in[1] * v_out[0]
            direction = "left" if cross > 0 else "right" if cross < 0 else "straight"
            if direction == "straight":
                continue
            turns.append((i, angle, direction))

        # Scan for 3+ alternating turns.
        for start in range(len(turns) - 3 + 1):
            window = turns[start : start + 3]
            dirs = [t[2] for t in window]
            if len(set(dirs)) == 1:
                continue  # all same direction — not alternating
            alternating = all(dirs[j] != dirs[j + 1] for j in range(len(dirs) - 1))
            if alternating:
                mid_turn = turns[start + 1]
                junction = ordered[mid_turn[0] - 1]
                findings.append({
                    "type": "zigzag",
                    "net_name": net_name,
                    "position": junction["end"],
                    "severity": float(len(window)),
                    "description": (
                        f"Zigzag pattern ({len(window)} alternating turns) near "
                        f"({junction['end'][0]:.2f}, {junction['end'][1]:.2f}) mm"
                    ),
                })
    return findings


def lint_isolated_vias(routed_pcb_path: Path) -> list[dict]:
    """Find vias with only one connected track segment (stubs)."""
    parse_result = _parse_pcb(routed_pcb_path)
    vias = [
        {
            "position": v.position,
            "net": v.net,
            "layers": v.layers,
        }
        for v in parse_result.vias
    ]
    traces = [
        {
            "start": t.start,
            "end": t.end,
            "net": t.net,
        }
        for t in parse_result.traces
    ]

    findings: list[dict] = []
    for via in vias:
        via_pos = via["position"]
        via_net = via["net"]
        segment_count = 0
        for trace in traces:
            if trace["net"] != via_net:
                continue
            if _distance_mm(trace["start"], via_pos) < 0.2:
                segment_count += 1
            elif _distance_mm(trace["end"], via_pos) < 0.2:
                segment_count += 1
        if segment_count == 1:
            findings.append({
                "type": "isolated_via",
                "net_name": via_net or "?",
                "position": via_pos,
                "severity": 1.0,
                "description": (
                    f"Isolated via (stub) on net {via_net or '?'} at "
                    f"({via_pos[0]:.2f}, {via_pos[1]:.2f}) mm"
                ),
            })
    return findings


def lint_single_net_detours(
    routed_pcb_path: Path, max_ratio: float = 1.5
) -> list[dict]:
    """Find nets where path_length / direct_distance > max_ratio."""
    traces_by_net = _load_traces_by_net(routed_pcb_path)
    findings: list[dict] = []

    for net_name, traces in traces_by_net.items():
        if len(traces) < 2:
            continue

        ordered = _order_traces(traces)
        if len(ordered) < 2:
            continue

        start_pos = ordered[0]["start"]
        end_pos = ordered[-1]["end"]
        direct_dist = _distance_mm(start_pos, end_pos)
        if direct_dist < 0.001:
            continue  # avoid division by zero

        path_length = sum(_distance_mm(s["start"], s["end"]) for s in ordered)
        ratio = path_length / direct_dist
        if ratio > max_ratio:
            midpoint = (
                (start_pos[0] + end_pos[0]) / 2,
                (start_pos[1] + end_pos[1]) / 2,
            )
            findings.append({
                "type": "single_net_detour",
                "net_name": net_name,
                "position": midpoint,
                "severity": ratio,
                "description": (
                    f"Net {net_name} detour ratio {ratio:.2f} "
                    f"(path {path_length:.2f} mm / direct {direct_dist:.2f} mm) > {max_ratio}"
                ),
            })
    return findings


def lint_all(routed_pcb_path: Path) -> list[dict]:
    """Run all slop linters, return combined list of artifacts."""
    findings: list[dict] = []
    findings.extend(lint_hairpin_turns(routed_pcb_path))
    findings.extend(lint_zigzag_patterns(routed_pcb_path))
    findings.extend(lint_isolated_vias(routed_pcb_path))
    findings.extend(lint_single_net_detours(routed_pcb_path))
    return findings


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------


def _parse_pcb(pcb_path: Path):
    """Parse a KiCad PCB file and return the ParseResult."""
    from temper_placer.io.kicad_parser import parse_kicad_pcb

    return parse_kicad_pcb(pcb_path)


def _load_traces_by_net(pcb_path: Path) -> dict[str, list[dict]]:
    """Load traces grouped by net name.

    Returns ``{net_name: [{"start": (x,y), "end": (x,y), "width": ..., "layer": ...}, ...]}``.
    """
    parse_result = _parse_pcb(pcb_path)
    by_net: dict[str, list[dict]] = {}
    for trace in parse_result.traces:
        net_name = trace.net or "_unnamed"
        by_net.setdefault(net_name, []).append({
            "start": trace.start,
            "end": trace.end,
            "width": trace.width,
            "layer": trace.layer,
        })
    return by_net


def _order_traces(traces: list[dict]) -> list[dict]:
    """Order a set of trace segments into a connected path by endpoint matching.

    Uses a greedy chain-building approach: start with the first segment, then
    repeatedly find the next segment whose start or end matches the current
    chain end.
    """
    if len(traces) <= 1:
        return traces

    remaining = list(traces)
    ordered: list[dict] = [remaining.pop(0)]
    eps = 0.1  # mm tolerance for endpoint matching

    while remaining:
        tail = ordered[-1]["end"]
        best_idx = -1
        best_dist = float("inf")
        best_reversed = False

        for idx, seg in enumerate(remaining):
            d_start = _distance_mm(tail, seg["start"])
            d_end = _distance_mm(tail, seg["end"])
            if d_start < best_dist and d_start < eps:
                best_idx = idx
                best_dist = d_start
                best_reversed = False
            if d_end < best_dist and d_end < eps:
                best_idx = idx
                best_dist = d_end
                best_reversed = True

        if best_idx < 0:
            # No adjacent segment found; append the nearest remaining segment
            # as a disconnected sub-path.
            nearest_idx = 0
            nearest_dist = _distance_mm(tail, remaining[0]["start"])
            for idx, seg in enumerate(remaining):
                d = _distance_mm(tail, seg["start"])
                if d < nearest_dist:
                    nearest_dist = d
                    nearest_idx = idx
            ordered.append(remaining.pop(nearest_idx))
            continue

        seg = remaining.pop(best_idx)
        if best_reversed:
            seg = {**seg, "start": seg["end"], "end": seg["start"]}
        ordered.append(seg)

    return ordered


def _vector(start: tuple[float, float], end: tuple[float, float]) -> tuple[float, float]:
    """Compute direction vector from start to end."""
    return (end[0] - start[0], end[1] - start[1])


def _angle_between(
    incoming: tuple[tuple[float, float], tuple[float, float]],
    outgoing: tuple[tuple[float, float], tuple[float, float]],
) -> float:
    """Compute the signed turn angle (0--180 deg) between two directed segments.

    Incoming: earlier segment end -> start (reversed direction for junction
    computation).  Outgoing: current segment start -> end.
    """
    v1 = _vector(incoming[0], incoming[1])
    v2 = _vector(outgoing[0], outgoing[1])
    m1 = math.hypot(v1[0], v1[1])
    m2 = math.hypot(v2[0], v2[1])
    if m1 < 1e-9 or m2 < 1e-9:
        return 0.0
    dot = v1[0] * v2[0] + v1[1] * v2[1]
    cos_angle = max(-1.0, min(1.0, dot / (m1 * m2)))
    return math.degrees(math.acos(cos_angle))


def _distance_mm(
    a: tuple[float, float], b: tuple[float, float]
) -> float:
    """Euclidean distance between two points in mm."""
    return math.hypot(a[0] - b[0], a[1] - b[1])
