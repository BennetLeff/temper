"""``_write_routes_to_content`` must never emit a zero-length ``(segment ...)``.

A track whose ``start`` equals its ``end`` is copper joining a node to itself.
It carries no connectivity, and having no direction it leaves KiCad DRC's
``tracks_crossing`` test without a defined crossing point.

The committed board carried 48 of them -- exactly one per via, every one
landing on a via position -- because the path-emission loop treated a via
crossing as a copper run. The 3D A* records a via as the *same* ``(x, y)`` on
two layers and deliberately never merges that pair, so the loop read
``(x, y, F.Cu) -> (x, y, B.Cu)`` as a run on ``F.Cu`` of length zero.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from temper_placer.router_v6.adapter import _write_routes_to_content
from temper_placer.router_v6.astar_core import RoutePath3D

_SEG = re.compile(
    r"\(segment \(start ([-\d.]+) ([-\d.]+)\) \(end ([-\d.]+) ([-\d.]+)\)"
    r' \(width ([\d.]+)\) \(layer "([^"]+)"\)'
)


@dataclass
class _StubVia:
    position: tuple[float, float]
    from_layer: str
    to_layer: str
    diameter: float
    drill: float
    net_name: str


def _emit(path, vias, pads):
    """Run the writer over one net and return its ``(segment ...)`` tuples."""
    compiled = {"NET": SimpleNamespace(net_name="NET", path=path, width_mm=0.25, vias=vias)}
    comps = []
    for idx, pos in enumerate(pads):
        c = SimpleNamespace(ref=f"C{idx}", initial_position=pos)
        c.get_pin = lambda _name: SimpleNamespace(position=(0.0, 0.0))
        comps.append(c)
    result = SimpleNamespace(
        stage4=SimpleNamespace(
            routing_results=SimpleNamespace(
                compiled_routes=compiled,
                partial_routes={},
                tree_routes={},
                partial_tree_routes={},
            )
        ),
        pcb=SimpleNamespace(
            components=comps,
            nets=[SimpleNamespace(name="NET", pins=[(c.ref, "1") for c in comps])],
        ),
    )
    content = _write_routes_to_content('(kicad_pcb\n  (net 1 "NET")\n)\n', result)[0]
    return [
        (float(a), float(b), float(c), float(d), float(w), lyr)
        for a, b, c, d, w, lyr in (m.groups() for m in _SEG.finditer(content))
    ]


def _via_path():
    """East on F.Cu, down through a via, east again on B.Cu.

    The via is the same ``(x, y)`` on both layers -- the shape
    ``astar_core._route_segment_3d`` documents it never merges.
    """
    return RoutePath3D(
        net_name="NET",
        segments=[
            (10.0, 5.0, "F.Cu"),
            (10.1, 5.0, "F.Cu"),
            (10.2, 5.0, "F.Cu"),
            (10.2, 5.0, "B.Cu"),
            (10.3, 5.0, "B.Cu"),
            (10.4, 5.0, "B.Cu"),
        ],
        via_positions=[(10.2, 5.0)],
        path_length=0.4,
        via_count=1,
    )


def test_layer_transition_emits_no_zero_length_segment():
    segs = _emit(
        _via_path(),
        [_StubVia((10.2, 5.0), "F.Cu", "B.Cu", 0.6, 0.3, "NET")],
        [(10.0, 5.0), (10.4, 5.0)],
    )
    assert segs, "writer emitted no segments at all"
    degenerate = [s for s in segs if (s[0], s[1]) == (s[2], s[3])]
    assert not degenerate, f"zero-length segment(s) emitted: {degenerate}"


def test_layer_transition_still_emits_the_copper_on_both_layers():
    """The guard must drop only the via crossing, never real copper."""
    segs = _emit(
        _via_path(),
        [_StubVia((10.2, 5.0), "F.Cu", "B.Cu", 0.6, 0.3, "NET")],
        [(10.0, 5.0), (10.4, 5.0)],
    )
    by_layer = {}
    for x1, y1, x2, y2, _w, lyr in segs:
        by_layer.setdefault(lyr, []).append((x1, y1, x2, y2))
    assert by_layer["F.Cu"] == [(10.0, 5.0, 10.2, 5.0)]
    assert by_layer["B.Cu"] == [(10.2, 5.0, 10.4, 5.0)]


def test_via_at_first_step_emits_no_zero_length_segment():
    """A route that drops layer immediately -- 20 of the board's 48 were these.

    There is no preceding same-layer copper, so the degenerate segment was the
    only F.Cu object the writer produced at that point.
    """
    path = RoutePath3D(
        net_name="NET",
        segments=[
            (10.0, 5.0, "F.Cu"),
            (10.0, 5.0, "B.Cu"),
            (10.1, 5.0, "B.Cu"),
            (10.2, 5.0, "B.Cu"),
        ],
        via_positions=[(10.0, 5.0)],
        path_length=0.2,
        via_count=1,
    )
    segs = _emit(
        path,
        [_StubVia((10.0, 5.0), "F.Cu", "B.Cu", 0.6, 0.3, "NET")],
        [(10.0, 5.0), (10.2, 5.0)],
    )
    assert not [s for s in segs if (s[0], s[1]) == (s[2], s[3])]
    assert [(s[0], s[1], s[2], s[3]) for s in segs] == [(10.0, 5.0, 10.2, 5.0)]
    assert {s[5] for s in segs} == {"B.Cu"}


@pytest.mark.parametrize("dup_at", [0, 2, 4])
def test_duplicated_same_layer_point_emits_no_zero_length_segment(dup_at):
    """The other route to the same defect: a repeated point on one layer."""
    pts = [(10.0, 5.0), (10.1, 5.0), (10.2, 5.0), (10.3, 5.0), (10.4, 5.0)]
    seq = [(x, y, "F.Cu") for x, y in pts]
    seq.insert(dup_at, seq[dup_at])
    path = RoutePath3D(
        net_name="NET",
        segments=seq,
        via_positions=[],
        path_length=0.4,
        via_count=0,
    )
    segs = _emit(path, [], [(10.0, 5.0), (10.4, 5.0)])
    degenerate = [s for s in segs if (s[0], s[1]) == (s[2], s[3])]
    assert not degenerate, f"zero-length segment(s) emitted: {degenerate}"
    # The full run must still be covered end to end.
    assert min(s[0] for s in segs) == 10.0
    assert max(s[2] for s in segs) == 10.4
