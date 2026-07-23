"""Internal: board geometry, stackup, and setup extraction from KiCad board objects."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from temper_placer.core.board import STANDARD_LAYER_ORDER, Board, MountingHole
from temper_placer.io._parse_zones import _extract_zones_from_pcb

if TYPE_CHECKING:
    from kiutils.board import Board as KiBoard

    from temper_placer.router_v6.stage0_data import StackupInfo


def _extract_board_geometry(ki_board: KiBoard, warnings: list[str]) -> Board:
    """
    Extract board dimensions and origin from Kiutils board object.

    Args:
        ki_board: Parsed kiutils Board instance.
        warnings: List to append any issues found.

    Returns:
        Board object with width, height, and origin.
    """
    edge_cuts = [g for g in ki_board.graphicItems if g.layer == "Edge.Cuts"]

    if not edge_cuts:
        warnings.append("No Edge.Cuts found in PCB. Using default 100x150mm.")
        return Board.temper_default()

    x_min, y_min = float("inf"), float("inf")
    x_max, y_max = float("-inf"), float("-inf")

    for item in edge_cuts:
        if hasattr(item, "start") and hasattr(item, "end"):
            for pt in [item.start, item.end]:
                if pt is not None:
                    x_min = min(x_min, pt.X)
                    y_min = min(y_min, pt.Y)
                    x_max = max(x_max, pt.X)
                    y_max = max(y_max, pt.Y)

        if hasattr(item, "coordinates") and item.coordinates:
            for pt in item.coordinates:
                x_min = min(x_min, pt.X)
                y_min = min(y_min, pt.Y)
                x_max = max(x_max, pt.X)
                y_max = max(y_max, pt.Y)

        if hasattr(item, "mid") and item.mid is not None:
            for pt in [item.start, item.mid, item.end]:
                if pt is not None:
                    x_min = min(x_min, pt.X)
                    y_min = min(y_min, pt.Y)
                    x_max = max(x_max, pt.X)
                    y_max = max(y_max, pt.Y)

    if not (
        math.isfinite(x_min)
        and math.isfinite(x_max)
        and math.isfinite(y_min)
        and math.isfinite(y_max)
    ):
        warnings.append(
            "Edge.Cuts geometry present but has no parseable coordinate data. "
            "Falling back to Board.temper_default()."
        )
        return Board.temper_default()

    mounting_holes = []
    for fp in ki_board.footprints:
        is_mounting_hole = False

        if hasattr(fp, "entryName") and "MountingHole" in fp.entryName:
            is_mounting_hole = True

        if not is_mounting_hole and fp.graphicItems:
            for item in fp.graphicItems:
                if hasattr(item, "text") and "MountingHole" in item.text:
                    is_mounting_hole = True
                    break

        if is_mounting_hole:
            mounting_holes.append(
                MountingHole(position=(fp.position.X - x_min, fp.position.Y - y_min), diameter=3.2)
            )

    zones = _extract_zones_from_pcb(ki_board, x_min, y_min, warnings)

    return Board(
        width=x_max - x_min,
        height=y_max - y_min,
        origin=(x_min, y_min),
        mounting_holes=mounting_holes,
        zones=zones,
    )


def _extract_stackup(ki_board: KiBoard, warnings: list[str]) -> StackupInfo:
    """
    Extract PCB layer stackup from KiCad board.

    Args:
        ki_board: Parsed KiCad board.
        warnings: List to append warnings.

    Returns:
        StackupInfo with layer definitions.
    """
    from temper_placer.router_v6.stage0_data import (
        DielectricInfo,
        LayerInfo,
        StackupInfo,
    )

    layers = []
    parsed_dielectrics = []

    plane_assignments = {}
    if hasattr(ki_board, "zones"):
        for zone in ki_board.zones:
            if (
                hasattr(zone, "layers")
                and zone.layers
                and hasattr(zone, "netName")
                and zone.netName
            ):
                for layer in zone.layers:
                    is_power = (
                        "GND" in zone.netName
                        or "VCC" in zone.netName
                        or "+" in zone.netName
                        or "PWR" in zone.netName
                    )
                    if is_power and ".Cu" in layer:
                        plane_assignments[layer] = zone.netName

    setup_stackup = None
    if hasattr(ki_board, "setup") and hasattr(ki_board.setup, "stackup") and ki_board.setup.stackup:
        setup_stackup = ki_board.setup.stackup

    if setup_stackup and hasattr(setup_stackup, "layers") and setup_stackup.layers:
        total_thickness = 0.0

        copper_layers = []
        raw_dielectrics = []

        for layer in setup_stackup.layers:
            if hasattr(layer, "thickness") and layer.thickness is not None:
                total_thickness += layer.thickness

            if layer.type == "copper":
                copper_layers.append(layer)
            elif layer.type in ["core", "prepreg", "dielectric"] or "dielectric" in layer.type:
                raw_dielectrics.append(layer)

        layer_count = len(copper_layers)

        for i, layer in enumerate(copper_layers):
            name = layer.name

            if name in plane_assignments:
                layer_type = "plane"
                plane_net = plane_assignments[name]
            elif i == 0 or i == layer_count - 1:
                layer_type = "signal"
                plane_net = None
            else:
                layer_type = "mixed"
                plane_net = None

            thickness_um = (
                (layer.thickness * 1000.0)
                if (hasattr(layer, "thickness") and layer.thickness)
                else 35.0
            )

            layers.append(
                LayerInfo(
                    index=i,
                    name=name,
                    layer_type=layer_type,
                    thickness_um=thickness_um,
                    plane_net=plane_net,
                )
            )

        for d in raw_dielectrics:
            epsilon_r = getattr(d, "epsilonR", None)
            if epsilon_r is None:
                epsilon_r = getattr(d, "epsilon_r", 4.5)

            loss_tangent = getattr(d, "lossTangent", None)
            if loss_tangent is None:
                loss_tangent = getattr(d, "loss_tangent", 0.02)

            parsed_dielectrics.append(
                DielectricInfo(
                    name=d.name,
                    material=getattr(d, "material", "FR4") or "FR4",
                    thickness_mm=d.thickness if hasattr(d, "thickness") and d.thickness else 0.0,
                    epsilon_r=epsilon_r or 4.5,
                    loss_tangent=loss_tangent or 0.02,
                )
            )

    else:
        layer_count = 2
        if hasattr(ki_board, "layers") and ki_board.layers:
            copper_layers = [ly for ly in ki_board.layers if ".Cu" in getattr(ly, "name", "")]
            layer_count = len(copper_layers)

        if layer_count == 2:
            layer_names = ["F.Cu", "B.Cu"]
        elif layer_count == 4:
            layer_names = [str(idx) for idx in STANDARD_LAYER_ORDER]
        elif layer_count == 6:
            layer_names = ["F.Cu", "In1.Cu", "In2.Cu", "In3.Cu", "In4.Cu", "B.Cu"]
        else:
            warnings.append(f"Unusual layer count: {layer_count}. Using generic naming.")
            layer_names = ["F.Cu"] + [f"In{i}.Cu" for i in range(1, layer_count - 1)] + ["B.Cu"]

        for i, name in enumerate(layer_names):
            if name in plane_assignments:
                layer_type = "plane"
                plane_net = plane_assignments[name]
            elif i == 0 or i == layer_count - 1:
                layer_type = "signal"
                plane_net = None
            else:
                layer_type = "mixed"
                plane_net = None

            thickness_um = 35.0

            layers.append(
                LayerInfo(
                    index=i,
                    name=name,
                    layer_type=layer_type,
                    thickness_um=thickness_um,
                    plane_net=plane_net,
                )
            )

        total_thickness = 1.6 if layer_count >= 4 else 0.8

        if (
            hasattr(ki_board, "general")
            and hasattr(ki_board.general, "thickness")
            and ki_board.general.thickness
        ):
            total_thickness = ki_board.general.thickness

    return StackupInfo(
        layers=layers,
        total_thickness_mm=total_thickness,
        layer_count=layer_count,
        dielectrics=parsed_dielectrics,
    )
