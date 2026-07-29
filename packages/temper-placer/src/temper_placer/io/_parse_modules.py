"""Internal: footprint/module parsing, pad extraction, and bounds calculation."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from temper_placer.core.netlist import Component, Pin
from temper_placer.io._kicad_types import PadData

if TYPE_CHECKING:
    from kiutils.board import Board as KiBoard
    from kiutils.footprint import Footprint


def _extract_components_from_pcb(
    ki_board: KiBoard,
    _warnings: list[str],
    board_origin: tuple[float, float],
) -> list[Component]:
    """
    Extract components from Kiutils board object.

    Args:
        ki_board: Parsed board.
        warnings: List for warning messages.
        board_origin: (ox, oy) to normalize positions.

    Returns:
        List of Component instances.
    """
    components = []
    ox, oy = board_origin

    for fp in ki_board.footprints:
        ref = _get_footprint_reference(fp)
        if not ref or ref.startswith("REF**"):
            continue

        rot_deg = fp.position.angle or 0.0
        rot_idx = round(rot_deg / 90.0) % 4

        width, height = _calculate_footprint_bounds(fp)

        side = 1 if fp.layer in ["B.Cu", "Back", "Bottom"] else 0

        raw_pins: list[dict[str, Any]] = []
        for pad in fp.pads:
            local_x = pad.position.X
            local_y = pad.position.Y

            pad_layers = pad.layers if hasattr(pad, "layers") and pad.layers else ["F.Cu"]
            is_through_hole = any("*.Cu" in layer or layer == "*.Cu" for layer in pad_layers)

            if is_through_hole:
                layer = "all"
            else:
                copper_layers = [ly for ly in pad_layers if ".Cu" in ly and "*" not in ly]
                layer = copper_layers[0] if copper_layers else "F.Cu"

            pad_width = pad.size.X if hasattr(pad, "size") and pad.size else 1.0
            pad_height = pad.size.Y if hasattr(pad, "size") and pad.size else 1.0
            pad_drill = getattr(pad, "drill", 0.0) or 0.0

            pad_shape = pad.shape or "rect"
            if is_through_hole and pad_shape == "circle":
                pad_shape = "thru_hole"

            # Exact per-pad roundrect corner ratio, when the shape carries
            # one (kiutils exposes it as `roundrectRatio`); KiCad's own
            # 0.25 default otherwise.
            pad_roundrect_ratio = getattr(pad, "roundrectRatio", None)
            if pad_roundrect_ratio is None:
                pad_roundrect_ratio = 0.25
            # A pad's `(at x y angle)` angle in a .kicad_pcb is its ABSOLUTE
            # world orientation, not an offset from the parent footprint's
            # angle -- verified against KiCad-authored boards and by
            # measurement (docs/evidence/2026-07-29-intra-component-shorts-
            # root-cause.md). `Pin.pad_rotation_deg` is the pad's intrinsic
            # rotation *relative to its footprint*, which every consumer adds
            # to the component rotation, so recover it by subtracting the
            # footprint angle here. Getting this backwards double-counts the
            # footprint rotation on every rotated part.
            pad_abs_rotation_deg = getattr(pad.position, "angle", None) or 0.0
            pad_rotation_deg = (pad_abs_rotation_deg - rot_deg) % 360.0

            raw_pins.append(
                {
                    "name": pad.number or "",
                    "number": pad.number or "",
                    "position": (local_x, local_y),
                    "net": pad.net.name
                    if pad.net and hasattr(pad.net, "name")
                    else str(pad.net)
                    if pad.net
                    else None,
                    "width": pad_width,
                    "height": pad_height,
                    "shape": pad_shape,
                    "layer": layer,
                    "drill": pad_drill,
                    "is_pth": is_through_hole,
                    "roundrect_ratio": pad_roundrect_ratio,
                    "pad_rotation_deg": pad_rotation_deg,
                }
            )

        if raw_pins:
            pad_xs = [p["position"][0] for p in raw_pins]
            pad_ys = [p["position"][1] for p in raw_pins]
            center_offset_x = (min(pad_xs) + max(pad_xs)) / 2.0
            center_offset_y = (min(pad_ys) + max(pad_ys)) / 2.0
        else:
            center_offset_x, center_offset_y = 0.0, 0.0

        pins = []
        for p in raw_pins:
            pins.append(
                Pin(
                    name=p["name"],
                    number=p["number"],
                    position=(
                        p["position"][0] - center_offset_x,
                        p["position"][1] - center_offset_y,
                    ),
                    net=p["net"],
                    width=p.get("width", 1.0),
                    height=p.get("height", 1.0),
                    shape=p.get("shape", "rect"),
                    layer=p.get("layer", "F.Cu"),
                    drill=p.get("drill", 0.0),
                    is_pth=p.get("is_pth", False),
                    roundrect_ratio=p.get("roundrect_ratio", 0.25),
                    pad_rotation_deg=p.get("pad_rotation_deg", 0.0),
                )
            )

        cx_to_rotate = -center_offset_x if side == 1 else center_offset_x
        rot_rad = math.radians(rot_deg)
        rotated_cx = cx_to_rotate * math.cos(rot_rad) - center_offset_y * math.sin(rot_rad)
        rotated_cy = cx_to_rotate * math.sin(rot_rad) + center_offset_y * math.cos(rot_rad)

        comp = Component(
            ref=ref,
            footprint=fp.libId or "",
            bounds=(width, height),
            pins=pins,
            initial_position=(
                float(fp.position.X) - float(board_origin[0]) + float(rotated_cx),
                float(fp.position.Y) - float(board_origin[1]) + float(rotated_cy),
            ),
            fixed=fp.locked,
            initial_rotation=rot_idx,
            initial_side=side,
            attributes={
                "_center_offset_x": str(center_offset_x),
                "_center_offset_y": str(center_offset_y),
                # The footprint's EXACT board rotation in degrees. `initial_rotation`
                # above is quantized to a 0-3 quadrant index, which silently loses any
                # non-multiple-of-90 angle -- fine for the placer (it only ever emits
                # quadrant rotations) but not for consumers that must reconstruct a
                # pad's true world position/orientation, e.g. the REQ-SAFE-01
                # copper-to-copper clearance check. Kept as a raw attribute rather
                # than a new Component field so nothing downstream of the dataclass
                # shape changes.
                "_rotation_deg": str(rot_deg),
            },
            sheetpath=(fp.properties.get("Sheetpath") if hasattr(fp, "properties") else None)
            or None,
        )

        components.append(comp)

    return components


def _extract_pads_from_pcb(ki_board: KiBoard, _warnings: list[str]) -> list[PadData]:
    """
    Extract pad positions and layers for visualization.

    Args:
        ki_board: Parsed board.
        warnings: List for warning messages.

    Returns:
        List of PadData.
    """
    pads = []
    for fp in ki_board.footprints:
        ref = _get_footprint_reference(fp)
        fp_x = float(fp.position.X) if fp.position else 0.0
        fp_y = float(fp.position.Y) if fp.position else 0.0

        for pad in fp.pads:
            abs_x = fp_x + float(pad.position.X)
            abs_y = fp_y + float(pad.position.Y)
            pads.append(
                PadData(
                    position=(abs_x, abs_y),
                    size=(pad.size.X, pad.size.Y),
                    shape=pad.shape or "rect",
                    drill=getattr(pad, "drill", 0.0) or 0.0,
                    rotation=pad.position.angle or 0.0,
                    layer=pad.layers[0] if pad.layers else "F.Cu",
                    number=pad.number or "",
                    net=pad.net.name
                    if pad.net and hasattr(pad.net, "name")
                    else str(pad.net)
                    if pad.net
                    else None,
                    component_ref=ref,
                )
            )
    return pads


def _get_footprint_reference(fp: Footprint) -> str | None:
    """
    Extract reference designator from a footprint item.

    Args:
        fp: Kiutils Footprint item.

    Returns:
        Reference string (e.g., "U1") or None.
    """
    if hasattr(fp, "properties"):
        props = fp.properties
        if isinstance(props, dict):
            if "Reference" in props:
                return props["Reference"]
        elif isinstance(props, list):
            for p in props:
                if getattr(p, "name", "") == "Reference":
                    return getattr(p, "value", None)

    if fp.graphicItems:
        for item in fp.graphicItems:
            if hasattr(item, "text") and getattr(item, "layer", "") in [
                "F.SilkS",
                "B.SilkS",
                "F.Fab",
                "B.Fab",
            ]:
                ref_candidate = item.text.strip()
                if ref_candidate and not ref_candidate.startswith("REF**"):
                    return ref_candidate

    for item in fp.graphicItems:
        if hasattr(item, "text") and getattr(item, "layer", "") in [
            "F.SilkS",
            "B.SilkS",
            "F.Fab",
            "B.Fab",
        ]:
            ref_candidate = item.text.strip()
            if ref_candidate and not ref_candidate.startswith("REF**"):
                return ref_candidate

    ename = getattr(fp, "entryName", None)
    if ename and not ename.startswith("REF**") and ":" not in ename and len(ename) < 10:
        return ename

    return None


def _get_footprint_bounds(fp: Footprint) -> tuple[float, float]:
    """
    Estimate footprint bounding box from its graphic items.

    Args:
        fp: Kiutils Footprint item.

    Returns:
        (width, height) in mm.
    """
    return _calculate_footprint_bounds(fp)


def _calculate_footprint_bounds(fp: Footprint) -> tuple[float, float]:
    """
    Calculate footprint bounding box from courtyard graphics or pads.

    Priority:
    1. Courtyard layer (F.CrtYd, B.CrtYd) - most accurate
    2. Fabrication layer (F.Fab, B.Fab) - body outline
    3. Pads - minimum required area for DRC

    Args:
        fp: Kiutils Footprint item.

    Returns:
        (width, height) in mm.
    """
    if fp.graphicItems:
        layers_priority = ["F.CrtYd", "B.CrtYd", "F.Fab", "B.Fab"]

        items_to_use = [
            g for g in fp.graphicItems if hasattr(g, "layer") and g.layer in layers_priority
        ]

        if not items_to_use:
            items_to_use = [
                g for g in fp.graphicItems if hasattr(g, "layer") and "Silk" not in g.layer
            ]

        if items_to_use:
            x_min, y_min = float("inf"), float("inf")
            x_max, y_max = float("-inf"), float("-inf")
            has_valid_items = False

            for item in items_to_use:
                if hasattr(item, "start") and hasattr(item, "end"):
                    for pt in [item.start, item.end]:
                        x_min = min(x_min, pt.X)
                        y_min = min(y_min, pt.Y)
                        x_max = max(x_max, pt.X)
                        y_max = max(y_max, pt.Y)
                    has_valid_items = True

                if hasattr(item, "center") and hasattr(item, "radius"):
                    cx, cy, r = item.center.X, item.center.Y, item.radius
                    x_min = min(x_min, cx - r)
                    y_min = min(y_min, cy - r)
                    x_max = max(x_max, cx + r)
                    y_max = max(y_max, cy + r)
                    has_valid_items = True

            gfx_bounds = (x_min, y_min, x_max, y_max) if has_valid_items else None
        else:
            gfx_bounds = None
    else:
        gfx_bounds = None

    pad_x_min, pad_y_min = float("inf"), float("inf")
    pad_x_max, pad_y_max = float("-inf"), float("-inf")

    if fp.pads:
        for pad in fp.pads:
            px, py = pad.position.X, pad.position.Y
            pw, ph = pad.size.X, pad.size.Y
            pad_x_min = min(pad_x_min, px - pw / 2)
            pad_y_min = min(pad_y_min, py - ph / 2)
            pad_x_max = max(pad_x_max, px + pw / 2)
            pad_y_max = max(pad_y_max, py + ph / 2)

    if gfx_bounds is not None and pad_x_min != float("inf"):
        x_min = min(gfx_bounds[0], pad_x_min)
        y_min = min(gfx_bounds[1], pad_y_min)
        x_max = max(gfx_bounds[2], pad_x_max)
        y_max = max(gfx_bounds[3], pad_y_max)
        hw = max(abs(x_min), abs(x_max))
        hh = max(abs(y_min), abs(y_max))
        return (max(0.5, 2 * hw), max(0.5, 2 * hh))

    if gfx_bounds is not None:
        hw = max(abs(gfx_bounds[0]), abs(gfx_bounds[2]))
        hh = max(abs(gfx_bounds[1]), abs(gfx_bounds[3]))
        return (max(0.5, 2 * hw), max(0.5, 2 * hh))

    if pad_x_min != float("inf"):
        hw = max(abs(pad_x_min), abs(pad_x_max))
        hh = max(abs(pad_y_min), abs(pad_y_max))
        return (max(0.5, 2 * hw), max(0.5, 2 * hh))

    return (2.0, 2.0)
