"""
Golden fixture serialization functions for pipeline stage boundaries.

Provides deterministic DSN, SES, and JSON serialization from BoardState.
All serializers MUST produce byte-identical output on the same machine
given the same BoardState. Float formatting pinned to f"{val:.6f}",
dict/set iteration uses sorted(), JSON uses sort_keys=True.

Format version: 1
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from temper_placer.deterministic.state import BoardState

CURRENT_FORMAT_VERSION = 1


def _format_float(val: float) -> str:
    return f"{val:.6f}"


def serialize_boardstate_to_dsn(state: BoardState) -> str:
    from temper_placer.io.dsn_exporter import DSNExporter

    if state.board is None:
        raise ValueError("BoardState.board is None; cannot serialize to DSN")
    if state.netlist is None:
        raise ValueError("BoardState.netlist is None; cannot serialize to DSN")

    exporter = DSNExporter(board=state.board, netlist=state.netlist)
    dsn_expr = exporter.export_pcb(pcb_name="temper")
    return str(dsn_expr)


def serialize_boardstate_to_ses(state: BoardState) -> str:
    lines = ["(session", "(resolution um 10)", "(unit mm)", ""]
    routes = state.routes or frozenset()
    vias = state.vias or frozenset()

    if not routes:
        lines.append("(routes)")
        lines.append(")")
        return "\n".join(lines)

    sorted_routes = sorted(
        routes,
        key=lambda r: (getattr(r, 'net_name', ''), getattr(r, 'layer', 0)),
    )

    route_lines = []
    for route in sorted_routes:
        net_name = getattr(route, 'net_name', 'unnamed')
        layer = getattr(route, 'layer', 0)
        start = getattr(route, 'start', (0.0, 0.0))
        end = getattr(route, 'end', (0.0, 0.0))
        width = getattr(route, 'width', 0.25)

        route_lines.append(
            f'(wire {net_name} '
            f'(path {layer} {_format_float(width)} '
            f'{_format_float(start[0])} {_format_float(start[1])} '
            f'{_format_float(end[0])} {_format_float(end[1])}))'
        )

    sorted_vias = sorted(
        vias,
        key=lambda v: (
            getattr(v, 'net_name', ''),
            getattr(v, 'center', (0.0, 0.0))[0],
            getattr(v, 'center', (0.0, 0.0))[1],
        ),
    )

    via_lines = []
    for via in sorted_vias:
        net_name = getattr(via, 'net_name', 'unnamed')
        center = getattr(via, 'center', (0.0, 0.0))
        via_lines.append(
            f'(via {net_name} '
            f'{_format_float(center[0])} {_format_float(center[1])})'
        )

    lines.append("(routes)")
    for rl in sorted(route_lines):
        lines.append(rl)

    if via_lines:
        lines.append("(vias)")
        for vl in sorted(via_lines):
            lines.append(vl)

    lines.append(")")
    return "\n".join(lines)


def serialize_violations_to_json(state: BoardState) -> str:
    violations = state.drc_violations or ()

    sorted_violations = sorted(
        violations,
        key=lambda v: (
            getattr(v, 'net_a', '') or '',
            getattr(v, 'net_b', '') or '',
            getattr(v, 'type', '') or '',
        ),
    )

    entries = []
    for v in sorted_violations:
        loc = getattr(v, 'location', None)
        loc_dict = None
        if loc is not None:
            loc_dict = {
                'x': round(getattr(loc, 'x', 0.0), 6),
                'y': round(getattr(loc, 'y', 0.0), 6),
            }
        entries.append({
            'type': getattr(v, 'type', ''),
            'net_a': getattr(v, 'net_a', ''),
            'net_b': getattr(v, 'net_b', ''),
            'geometry_a_id': getattr(v, 'geometry_a_id', ''),
            'geometry_b_id': getattr(v, 'geometry_b_id', ''),
            'clearance_actual': round(getattr(v, 'clearance_actual', 0.0), 6),
            'clearance_required': round(getattr(v, 'clearance_required', 0.0), 6),
            'location': loc_dict,
            'severity': round(getattr(v, 'severity', 0.0), 6),
        })

    return json.dumps(
        {'format_version': CURRENT_FORMAT_VERSION, 'violations': entries},
        indent=2,
        sort_keys=True,
    )


def serialize_connectivity_to_json(state: BoardState) -> str:
    violations = state.connectivity_violations or ()

    sorted_violations = sorted(
        violations,
        key=lambda v: (
            getattr(v, 'net', '') or '',
            getattr(v, 'type', '') or '',
        ),
    )

    entries = []
    for v in sorted_violations:
        loc = getattr(v, 'location', None)
        loc_dict = None
        if loc is not None:
            loc_dict = {
                'x': round(getattr(loc, 'x', 0.0), 6),
                'y': round(getattr(loc, 'y', 0.0), 6),
            }
        entries.append({
            'type': getattr(v, 'type', ''),
            'net': getattr(v, 'net', ''),
            'description': getattr(v, 'description', ''),
            'location': loc_dict,
        })

    return json.dumps(
        {'format_version': CURRENT_FORMAT_VERSION, 'violations': entries},
        indent=2,
        sort_keys=True,
    )


SERIALIZER_REGISTRY = {
    'serialize_boardstate_to_dsn': serialize_boardstate_to_dsn,
    'serialize_boardstate_to_ses': serialize_boardstate_to_ses,
    'serialize_violations_to_json': serialize_violations_to_json,
    'serialize_connectivity_to_json': serialize_connectivity_to_json,
}
