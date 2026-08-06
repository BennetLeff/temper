"""Duck-typed ``ParseResult`` stand-ins for the cluster-F quality-metric gates.

``_quality_metrics_cases`` is pure data by design, so that the oracle arm and
the Rust arm can each build their own object types from it.  This module is
the **oracle arm's** builder: it turns a ``SCENARIOS`` dict into the smallest
object graph the pinned kernels actually touch.

The kernels read exactly these attributes and nothing else, which is why a
stand-in is sufficient (and why it is preferable to a real parse -- it lets the
differential reach NaN/inf/degenerate boards that no ``.kicad_pcb`` file can
express):

============================================  ==============================
Kernel                                        Attributes read
============================================  ==============================
``_load_traces_by_net``                       ``result.traces[].net``,
                                              ``.start``, ``.end``,
                                              ``.width``, ``.layer``
``lint_isolated_vias``                        ``result.vias[].position``,
                                              ``.net``, ``.layers``;
                                              ``result.traces[].start``,
                                              ``.end``, ``.net``
``_classify_vias``                            ``result.vias``,
                                              ``result.netlist.components``,
                                              ``result.board``
``_get_component_bboxes`` /                   ``comp.ref``,
``_compute_courtyards``                       ``comp.initial_position``,
                                              ``comp.width``, ``comp.height``
``_get_board_bbox``                           ``board.width``,
                                              ``board.height``
``_assign_tracks_to_channels``                ``result.traces``
============================================  ==============================

The Rust arm must NOT use this module -- it builds its own inputs from the
same ``_quality_metrics_cases`` data.  That is the whole point of keeping the
corpus type-free.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FakeTrace:
    start: tuple[float, float]
    end: tuple[float, float]
    width: float
    layer: str
    net: str | None


@dataclass
class FakeVia:
    position: tuple[float, float]
    net: str | None
    layers: tuple[str, str]


@dataclass
class FakeComponent:
    ref: str
    initial_position: tuple[float, float] | None
    width: float
    height: float


@dataclass
class FakeBoard:
    width: float
    height: float


@dataclass
class FakeNetlist:
    components: list[FakeComponent] = field(default_factory=list)


@dataclass
class FakeParseResult:
    traces: list[FakeTrace] = field(default_factory=list)
    vias: list[FakeVia] = field(default_factory=list)
    netlist: FakeNetlist = field(default_factory=FakeNetlist)
    board: FakeBoard | None = None


def build(scenario: dict[str, Any]) -> FakeParseResult:
    """Build a ``FakeParseResult`` from a ``_quality_metrics_cases`` scenario."""
    return FakeParseResult(
        traces=[
            FakeTrace(start=(sx, sy), end=(ex, ey), width=w, layer=layer, net=net)
            for (sx, sy, ex, ey, w, layer, net) in scenario["traces"]
        ],
        vias=[
            FakeVia(position=pos, net=net, layers=layers) for (pos, net, layers) in scenario["vias"]
        ],
        netlist=FakeNetlist(
            components=[
                FakeComponent(ref=ref, initial_position=pos, width=w, height=h)
                for (ref, pos, w, h) in scenario["components"]
            ]
        ),
        board=None if scenario["board"] is None else FakeBoard(*scenario["board"]),
    )


def as_trace_dicts(
    segments: list[tuple[float, float, float, float]],
    net: str = "NET1",
    width: float = 0.25,
    layer: str = "F.Cu",
) -> list[dict]:
    """Turn ``(sx, sy, ex, ey)`` tuples into the dict shape ``_order_traces`` takes.

    ``_load_traces_by_net`` produces exactly this shape, so feeding it directly
    to ``_order_traces`` exercises the real contract without a parse.
    """
    return [
        {"start": (sx, sy), "end": (ex, ey), "width": width, "layer": layer}
        for (sx, sy, ex, ey) in segments
    ]


def patched_parse(monkeypatch, module, result: FakeParseResult) -> None:
    """Point ``module._parse_pcb`` at a prebuilt ``FakeParseResult``.

    ``lint_*`` take a path and reach the parser through ``_parse_pcb``.  Since
    ``_parse_pcb`` is I/O (and is the one function the three modules do NOT
    genuinely share -- see the oracle header), redirecting it is how the
    synthetic scenarios reach the lint kernels.  The path argument becomes
    inert.
    """
    monkeypatch.setattr(module, "_parse_pcb", lambda _path: result)
