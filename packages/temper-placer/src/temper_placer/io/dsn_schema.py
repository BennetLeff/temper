from __future__ import annotations

from typing import TYPE_CHECKING

import temper_dsn as _td

if TYPE_CHECKING:
    from temper_placer.core.board import Board
    from temper_placer.core.netlist import Netlist


def compute_dsn_schema_hash(board: Board, netlist: Netlist) -> str:
    layer_names: list[str] = []
    layer_types: dict[str, str] = {}
    if board.layer_stackup:
        for ly in board.layer_stackup.layers:
            layer_names.append(ly.name)
            layer_types[ly.name] = ly.layer_type
    else:
        layer_names = ["F.Cu", "B.Cu"]
        layer_types = {"F.Cu": "signal", "B.Cu": "signal"}

    footprints: dict[str, int] = {}
    for comp in netlist.components:
        pin_count = len(comp.pins)
        fp_name = comp.footprint
        footprints[fp_name] = max(footprints.get(fp_name, 0), pin_count)

    nets = [n.name for n in netlist.nets]

    return _td.compute_dsn_schema_hash(layer_names, layer_types, footprints, nets)


def embed_schema_header(dsn_text: str, schema_hash: str) -> str:
    return _td.embed_schema_header(dsn_text, schema_hash)


def extract_schema_hash(dsn_text: str) -> str | None:
    return _td.extract_schema_hash(dsn_text)
