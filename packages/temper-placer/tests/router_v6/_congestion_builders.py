"""Object builders for the cluster-E corpus.

``_congestion_cases.py`` is pure data on purpose (so the oracle arm and the
Rust arm can each build their own types from it).  This module is the
data -> object adapter for the *Python* arms -- the differential and the PBT
suites -- and it lives outside the corpus so the corpus stays importable
without ``temper_placer``.

Nothing here makes a decision the kernel could observe: every function is a
constructor call over corpus tuples.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.router_v6.routing_results import RoutingResults
from temper_placer.router_v6.stage0_data import ParsedPCB, StackupInfo

__all__ = [
    "RouteStub",
    "build_board",
    "build_grid",
    "build_netlist",
    "build_parsed_pcb",
    "build_routing_results",
]


def build_board(width: float, height: float, origin: tuple[float, float] = (0.0, 0.0)) -> Board:
    return Board(width=width, height=height, origin=origin)


def build_grid(mod, row_demand: list[float], row_supply: list[float]):
    """A 1 x N ``CongestionGrid`` from two equal-length rows.

    ``mod`` is the arm's module (the oracle here; the shim once Phase B
    lands), so the two arms build *their own* ``CongestionGrid`` type and a
    type divergence is visible to ``sig()``.
    """
    demand = np.array([row_demand], dtype=np.float64)
    supply = np.array([row_supply], dtype=np.float64)
    return mod.CongestionGrid(
        demand=demand,
        supply=supply,
        cell_size_mm=1.0,
        width_cells=len(row_demand),
        height_cells=1,
        num_layers=1,
        origin=(0.0, 0.0),
    )


def build_netlist(components: list, nets: list) -> Netlist:
    """``components``/``nets`` in the corpus's tuple shape -> a ``Netlist``.

    component: ``(ref, initial_position, rotation, [(pin_number, (px, py), net)])``
    net:       ``(name, [(comp_ref, pin_name), ...])``
    """
    def _comp(row):
        # 4-tuple keeps the historical shape; a 5th element carries
        # ``initial_side`` (bottom-side pads mirror X before rotation).
        ref, position, rotation, pins = row[:4]
        side = row[4] if len(row) > 4 else None
        kw = {} if side is None else {"initial_side": side}
        return Component(
            ref=ref,
            footprint="TEST",
            bounds=(1.0, 1.0),
            pins=[
                Pin(name=num, number=num, position=pos, net=net, width=0.4, height=0.4)
                for (num, pos, net) in pins
            ],
            initial_position=position,
            initial_rotation_quadrant=rotation,
            **kw,
        )

    comps = [_comp(row) for row in components]
    return Netlist(components=comps, nets=[Net(name=n, pins=list(p)) for (n, p) in nets])


def build_parsed_pcb(components: list, net_names: list[str], as_dict: bool = False) -> ParsedPCB:
    """A ``ParsedPCB`` carrying only what ``estimate_routing_demand`` reads.

    component: ``(ref, [(pin_number, net), ...])``.  ``as_dict`` builds
    ``nets`` as a mapping instead of a list -- the module explicitly handles
    both shapes, so both are exercised.
    """
    comps = [
        Component(
            ref=ref,
            footprint="TEST",
            bounds=(1.0, 1.0),
            pins=[Pin(name=num, number=num, position=(0.0, 0.0), net=net) for (num, net) in pins],
            initial_position=(0.0, 0.0),
        )
        for (ref, pins) in components
    ]
    nets: object
    if as_dict:
        nets = {n: Net(name=n, pins=[]) for n in net_names}
    else:
        nets = [Net(name=n, pins=[]) for n in net_names]
    return ParsedPCB(
        components=comps,
        nets=nets,  # type: ignore[arg-type]
        zones=[],
        board=Board(width=100.0, height=100.0),
        design_rules=None,
        stackup=StackupInfo(layers=[], total_thickness_mm=1.6, layer_count=2),
        source_path=Path("corpus.kicad_pcb"),
        tracks=[],
        vias=[],
        warnings=[],
    )


class RouteStub:
    """The duck type ``identify_congested_regions`` actually consumes.

    The module reaches for ``compiled_route.path.segments`` and falls back to
    ``compiled_route.path.coordinates``; it never touches anything else on a
    ``CompiledRoute``.  Using the real class here would pin an unrelated
    contract into this differential, so the stub is the honest boundary --
    and ``use_segments`` makes the ``hasattr`` branch itself testable.
    """

    __slots__ = ("path",)

    class _Path:
        __slots__ = ("coordinates", "segments")

        def __init__(self, coords, use_segments):
            if use_segments:
                self.segments = [(x, y, 0) for (x, y) in coords]
            else:
                self.coordinates = list(coords)

    def __init__(self, coords, use_segments: bool = False):
        self.path = RouteStub._Path(coords, use_segments)


def build_routing_results(
    failed_nets: list[str], routes: dict, use_segments: bool = False
) -> RoutingResults:
    return RoutingResults(
        compiled_routes={name: RouteStub(coords, use_segments) for name, coords in routes.items()},  # type: ignore[arg-type]
        failed_nets=list(failed_nets),
    )
