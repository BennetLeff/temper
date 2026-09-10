"""P1 U4 apparatus-only scripted construction (run-local, NON-LIVE).

The live model transport is blocked (`FreeUsageLimitError`), so no autonomous
model constructed this board. This script executes a deterministic, bounded
construction through the SAME admitted :class:`run_block.BlockSession`
operations the live catalog exposes (``place`` / ``replace_copper`` /
``inspect`` / ``check``) under the same 200-mutation, 1200-second budget, and
freezes + delivers the P2 memory selection before the first board call.

It is explicitly **apparatus-only / non-live**: it is NOT a model result and
does NOT satisfy U4's live-delivery requirement. It is an operator-authored
placement and an explicit-graph route (MST + grid A*), not a harness
capability; no placer/router is added to the harness. Every artifact produced
by this path is labelled ``apparatus-only``.
"""

from __future__ import annotations

import argparse
import heapq
import json
import math
import sys
from pathlib import Path

RUN = Path(__file__).resolve().parent
sys.path.insert(0, str(RUN))

import run_block  # noqa: E402
import runlib  # noqa: E402
import workspace  # noqa: E402

# Ten movable instances: module centred; the EN/boot/I2C cluster on the left,
# the I2C/io0 cluster on the right, all below the antenna keepout.
PLACEMENT = {
    "U1": (35.0, 50.0, 0),
    "C1": (20.0, 38.0, 90),
    "C2": (20.0, 42.0, 90),
    "R1": (20.0, 46.0, 90),
    "C3": (20.0, 50.0, 90),
    "SW1": (20.0, 54.0, 90),
    "R2": (49.0, 44.0, 90),
    "R3": (49.0, 48.0, 90),
    "R4": (49.0, 52.0, 90),
    "SW2": (49.0, 56.0, 90),
}

# Net -> dedicated copper layer for the via/grid routes (ground is a hand-
# laid F.Cu bus, because the zone path segfaults KiCad's headless teardown).
NET_LAYER = {
    "vcc": "In3.Cu",
    "en": "In1.Cu",
    "io0": "In2.Cu",
    "sda": "In4.Cu",
    "scl": "B.Cu",
}
SIGNAL_WIDTH = 0.3
POWER_WIDTH = 0.6  # vcc is a power net: MIN_POWER_WIDTH_MM is 0.6
GND_WIDTH = 0.5  # gnd is classified signal (min signal width)
GND_BUS_X = 21.5
GND_RIGHT_X = 51.5
GND_BOTTOM_Y = 67.0
REGION = (16.0, 32.6, 54.0, 70.0)
GRID = 0.25
VIA_RADIUS = 0.4
CLEARANCE = 0.2
VIA_OFFSET = 1.4  # pad centre -> via centre, along the outward normal


def outward_via(pad_mm: list[float], side: str) -> tuple[float, float]:
    x, y = pad_mm
    if side == "left":
        return (x - VIA_OFFSET, y)
    if side == "right":
        return (x + VIA_OFFSET, y)
    if side == "up":
        return (x, y - VIA_OFFSET)
    return (x, y + VIA_OFFSET)


def _free(px: float, py: float, obstacles: list[tuple[float, float]], margin: float) -> bool:
    for ox, oy in obstacles:
        if (px - ox) ** 2 + (py - oy) ** 2 < margin * margin:
            return False
    return True


def astar(
    start: tuple[float, float],
    goal: tuple[float, float],
    obstacles: list[tuple[float, float]],
    width: float,
) -> list[list[float]]:
    """8-connected grid A* between two points avoiding via discs.

    ``obstacles`` are other nets' through-vias (present on every layer).
    """
    x0, y0, x1, y1 = REGION
    nx = int((x1 - x0) / GRID) + 1
    ny = int((y1 - y0) / GRID) + 1
    margin = VIA_RADIUS + CLEARANCE + width / 2.0

    def to_cell(p):
        return (
            int(round((p[0] - x0) / GRID)),
            int(round((p[1] - y0) / GRID)),
        )

    def to_mm(c):
        return (x0 + c[0] * GRID, y0 + c[1] * GRID)

    sc, gc = to_cell(start), to_cell(goal)
    for cell in (sc, gc):
        if not (0 <= cell[0] < nx and 0 <= cell[1] < ny):
            raise ValueError("route endpoint outside the routing region")

    def blocked(cell):
        px, py = to_mm(cell)
        return not _free(px, py, obstacles, margin)

    if blocked(sc) or blocked(gc):
        raise ValueError(f"route endpoint blocked start={start} goal={goal}")

    open_heap = [(math.dist(sc, gc), 0.0, sc)]
    came: dict[tuple[int, int], tuple[int, int]] = {}
    best: dict[tuple[int, int], float] = {sc: 0.0}
    neighbours = [
        (dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if (dx, dy) != (0, 0)
    ]
    found = False
    while open_heap:
        _, cost, cell = heapq.heappop(open_heap)
        if cell == gc:
            found = True
            break
        if cost > best.get(cell, math.inf) + 1e-9:
            continue
        for dx, dy in neighbours:
            nxt = (cell[0] + dx, cell[1] + dy)
            if not (0 <= nxt[0] < nx and 0 <= nxt[1] < ny) or blocked(nxt):
                continue
            step = GRID * (math.sqrt(2) if dx and dy else 1.0)
            new = cost + step
            if new + 1e-9 < best.get(nxt, math.inf):
                best[nxt] = new
                came[nxt] = cell
                heapq.heappush(
                    open_heap, (new + math.dist(nxt, gc), new, nxt)
                )
    if not found:
        raise ValueError(f"no route start={start} goal={goal}")
    path = [gc]
    while path[-1] != sc:
        path.append(came[path[-1]])
    path.reverse()
    points = [list(start)]
    for cell in path[1:-1]:
        points.append(list(to_mm(cell)))
    points.append(list(goal))
    return simplify(points)


def simplify(points: list[list[float]]) -> list[list[float]]:
    """Keep only direction changes (collinear runs collapse to endpoints)."""
    if len(points) <= 2:
        return points
    out = [points[0]]
    for i in range(1, len(points) - 1):
        ax, ay = out[-1]
        bx, by = points[i]
        cx, cy = points[i + 1]
        if abs((bx - ax) * (cy - by) - (by - ay) * (cx - bx)) > 1e-9:
            out.append(points[i])
    out.append(points[-1])
    return out


def mst_edges(points: list[list[float]]) -> list[tuple[int, int]]:
    remaining = set(range(1, len(points)))
    connected = [0]
    edges = []
    while remaining:
        best = None
        for a in connected:
            for b in remaining:
                d = math.dist(points[a], points[b])
                if best is None or d < best[0]:
                    best = (d, a, b)
        _, a, b = best
        edges.append((a, b))
        connected.append(b)
        remaining.discard(b)
    return edges


def build_copper(measurement: dict):
    """Return net -> (segments, vias, zones) from measured pad positions."""
    pads: dict[str, dict[tuple[str, str], list[float]]] = {}
    for fp in measurement["footprints"]:
        for pad in fp["pads"]:
            pads.setdefault(fp["reference"], {})[pad["number"]] = pad["position_mm"]

    # vcc: U1.2 + C1.1/C2.1/R1.1 (left) + R2.1/R3.1/R4.1 (right)
    # en:  U1.3 + C3.1 + R1.2 + SW1.1 (all left)
    # io0: U1.27 + R2.2 + SW2.1 (all right)
    # sda: U1.31 + R3.2 (right)
    # scl: U1.32 + R4.2 (right)
    # gnd: C1.2/C2.2/C3.2/SW1.2 (left) + SW2.2 (right) + U1.1 (left) via zone
    net_pads: dict[str, list[tuple[str, str, str]]] = {
        "vcc": [
            ("U1", "2", "left"),
            ("C1", "1", "left"),
            ("C2", "1", "left"),
            ("R1", "1", "left"),
            ("R2", "1", "right"),
            ("R3", "1", "right"),
            ("R4", "1", "right"),
        ],
        "en": [
            ("U1", "3", "left"),
            ("C3", "1", "left"),
            ("R1", "2", "left"),
            ("SW1", "1", "left"),
        ],
        "io0": [
            ("U1", "27", "right"),
            ("R2", "2", "right"),
            ("SW2", "1", "right"),
        ],
        "sda": [("U1", "31", "right"), ("R3", "2", "right")],
        "scl": [("U1", "32", "right"), ("R4", "2", "right")],
    }
    positions: dict[str, list[tuple[float, float]]] = {}
    stubs: dict[str, list[dict]] = {net: [] for net in net_pads}
    vias: dict[str, list[dict]] = {net: [] for net in net_pads}
    for net, entries in net_pads.items():
        points = []
        for ref, pad, side in entries:
            pad_mm = pads[ref][pad]
            via = outward_via(pad_mm, side)
            points.append(via)
            width = POWER_WIDTH if net == "vcc" else SIGNAL_WIDTH
            stubs[net].append(
                {
                    "start_mm": pad_mm,
                    "end_mm": list(via),
                    "layer": "F.Cu",
                    "width_mm": width,
                }
            )
            vias[net].append(
                {
                    "position_mm": list(via),
                    "diameter_mm": 0.8,
                    "drill_mm": 0.4,
                }
            )
        positions[net] = points

    segments: dict[str, list[dict]] = {net: [] for net in net_pads}
    for net, points in positions.items():
        layer = NET_LAYER[net]
        width = POWER_WIDTH if net == "vcc" else SIGNAL_WIDTH
        obstacles = [
            p for other, pts in positions.items() if other != net for p in pts
        ]
        for a, b in mst_edges(points):
            path = astar(tuple(points[a]), tuple(points[b]), obstacles, width)
            for start, end in zip(path, path[1:]):
                segments[net].append(
                    {
                        "start_mm": list(start),
                        "end_mm": list(end),
                        "layer": layer,
                        "width_mm": width,
                    }
                )
    copper = {}
    for net in net_pads:
        copper[net] = (segments[net] + stubs[net], vias[net], [])
    copper["gnd"] = (build_gnd(pads), [], [])
    return copper


def build_gnd(pads: dict[str, dict[str, list[float]]]) -> list[dict]:
    """Hand-laid F.Cu ground bus in the clear channel left of U1 and below it.

    Left gnd pads join a vertical bus at ``GND_BUS_X``; SW2.2 returns along the
    bottom channel; U1.1 taps the bus. All other nets' F.Cu stubs run outward
    (left of the left cluster, right of the right cluster, or toward U1 from
    the outside), so this bus never crosses them.
    """
    left = [
        pads[ref][pad]
        for ref, pad in (
            ("C1", "2"),
            ("C2", "2"),
            ("C3", "2"),
            ("SW1", "2"),
            ("U1", "1"),
        )
    ]
    u1_gnd = pads["U1"]["1"]
    sw2_gnd = pads["SW2"]["2"]
    y_bottom = GND_BOTTOM_Y
    y_top = min(y for _, y in left)

    def seg(a, b):
        return {
            "start_mm": list(a),
            "end_mm": list(b),
            "layer": "F.Cu",
            "width_mm": GND_WIDTH,
        }

    segments = [
        seg((GND_BUS_X, y_top), (GND_BUS_X, y_bottom)),
    ]
    for x, y in left:
        if (x, y) == tuple(u1_gnd):
            continue
        segments.append(seg((x, y), (GND_BUS_X, y)))
    segments.append(seg(u1_gnd, (GND_BUS_X, u1_gnd[1])))
    # SW2's gnd pad is in the right column; leave outward along its own y so
    # the return never passes through its partner (io0) pad, then drop in the
    # outer channel and cross below U1.
    segments.append(seg(sw2_gnd, (GND_RIGHT_X, sw2_gnd[1])))
    segments.append(seg((GND_RIGHT_X, sw2_gnd[1]), (GND_RIGHT_X, y_bottom)))
    segments.append(seg((GND_RIGHT_X, y_bottom), (GND_BUS_X, y_bottom)))
    return segments


def construct(session: run_block.BlockSession, *, dry: bool = False) -> list[dict]:
    results = []
    for ref, (x, y, angle) in PLACEMENT.items():
        results.append(
            session.call(
                "place",
                {"reference": ref, "x_mm": x, "y_mm": y, "angle_deg": angle},
            )
        )
    inspection = session.call("inspect", {})
    if inspection["status"] != "pass":
        raise RuntimeError(f"inspection failed: {inspection}")
    copper = build_copper(inspection["measurement"])
    for net, (segments, vias, zones) in copper.items():
        if dry:
            results.append(
                {
                    "operation": "replace_copper",
                    "net": net,
                    "segments": len(segments),
                    "vias": len(vias),
                    "zones": len(zones),
                }
            )
            continue
        results.append(
            session.call(
                "replace_copper",
                {"net": net, "segments": segments, "vias": vias, "zones": zones},
            )
        )
    if not dry:
        results.append(session.call("check", {}))
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trial", required=True, type=Path)
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--attempt-id", required=True)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--label", default="apparatus-only")
    parser.add_argument("--budget", type=float, default=1200.0)
    parser.add_argument("--store", type=Path, default=RUN / "store")
    parser.add_argument("--dry", action="store_true")
    args = parser.parse_args()

    import time

    store_root = args.store.resolve()
    session = run_block.BlockSession(
        args.trial.resolve(), deadline=time.monotonic() + args.budget
    )
    worker = workspace.Workspace(session=session)
    try:
        frozen = runlib.freeze_selection(
            store_root, candidate=args.candidate.resolve()
        )
        delivery = runlib.deliver(
            frozen,
            worker,
            attempt_id=args.attempt_id,
            attempt_dir=args.trial.resolve(),
            store_root=store_root,
        )
        results = construct(session, dry=args.dry)
        final = results[-1] if results else {}
        summary = {
            "schema": "temper.mcu-apparatus-attempt.v1",
            "attempt_id": args.attempt_id,
            "label": args.label,
            "live": False,
            "reason": "live model transport unavailable (Zen FreeUsageLimitError)",
            "budget": {"max_actions": 200, "max_seconds": args.budget},
            "operations": len(results),
            "committed_actions": session.actions,
            "memory": runlib.compact_delivery_report(delivery),
            "final_status": final.get("status"),
            "final_revision": session.revision,
            "final_findings": [
                f.get("id")
                for f in final.get("rust", {}).get("findings", [])
            ],
            "final_verdict": final.get("native_verdict"),
        }
        runlib.write_json(args.out, summary)
        print(json.dumps(summary, sort_keys=True))
    finally:
        worker.close()
        session.close()


if __name__ == "__main__":
    main()
