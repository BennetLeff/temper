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

        # Pad-centroid offset, computed BEFORE bounds so the symmetric
        # envelope below is centred on the SAME point `initial_position`
        # uses (`ox + rotated(center_offset)`, below) -- not the
        # footprint's raw KiCad anchor. This must be computed once, here,
        # and threaded through, rather than derived twice from two
        # different sources: see `_calculate_footprint_bounds`'s docstring
        # for why a mismatch here is a real soundness gap, not a style
        # nit. (The identical formula is repeated on `raw_pins` below only
        # for backward-compatible clarity of that block; both read the
        # same `fp.pads` positions and always agree.)
        if fp.pads:
            _pad_cx = [p.position.X for p in fp.pads]
            _pad_cy = [p.position.Y for p in fp.pads]
            center_offset_x = (min(_pad_cx) + max(_pad_cx)) / 2.0
            center_offset_y = (min(_pad_cy) + max(_pad_cy)) / 2.0
        else:
            center_offset_x, center_offset_y = 0.0, 0.0

        width, height = _calculate_footprint_bounds(fp, center_offset_x, center_offset_y)

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

        # center_offset_x/y already computed above (before bounds), from
        # the same `fp.pads` positions `raw_pins` was built from -- not
        # recomputed here, so there is exactly one source of truth for
        # the frame shift instead of two that could silently diverge.

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
        # Rotation sign: a KiCad footprint's `(at X Y ANGLE)` rotates each
        # pad's stored local offset *clockwise* by ANGLE to reach its
        # absolute board position -- R(-ANGLE) in the standard
        # (CCW-positive) trig convention below, not R(+ANGLE). Verified
        # directly against pcbnew (KiCad's own placement engine): see
        # `io/_write_board.py::write_placements_to_pcb`'s docstring for the
        # measurement this mirrors (this is that computation's exact
        # inverse -- anchor -> centre here, centre -> anchor there -- and
        # both must use the same sign for a read/write round-trip to
        # recover the original anchor). Previously used R(+ANGLE), which is
        # a no-op error whenever rot_deg is a multiple of 180 deg (sin=0)
        # but silently mis-locates `initial_position` for any footprint
        # parsed at a 90/270 rotation with a nonzero center_offset -- true
        # today for 18 components on pcb/temper.kicad_pcb (C1, C24, C25,
        # C4, C8, F1, K3, PS1, R1, R11, R12, R13, R60, RT1, T1, U1, U6).
        # `initial_position` only feeds CP-SAT's `AddHint` (a warm-start,
        # not a hard constraint) and is not consumed by the REQ-SAFE-01
        # validator (`Pin.position` is computed separately, in the
        # footprint's own unrotated local frame, and is unaffected by this
        # fix) -- see
        # docs/evidence/2026-07-30-generic-separation-writer-frame-fix.md.
        rotated_cx = cx_to_rotate * math.cos(rot_rad) + center_offset_y * math.sin(rot_rad)
        rotated_cy = -cx_to_rotate * math.sin(rot_rad) + center_offset_y * math.cos(rot_rad)

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


def _calculate_footprint_bounds(
    fp: Footprint, center_offset_x: float = 0.0, center_offset_y: float = 0.0
) -> tuple[float, float]:
    """
    Calculate footprint bounding box from courtyard graphics or pads.

    Priority:
    1. Courtyard layer (F.CrtYd, B.CrtYd) - most accurate
    2. Fabrication layer (F.Fab, B.Fab) - body outline
    3. Pads - minimum required area for DRC

    Args:
        fp: Kiutils Footprint item.
        center_offset_x: X of the point the returned box is symmetric
            *around*, in the footprint's own local (unrotated) coordinate
            frame -- i.e. the same ``center_offset_x`` computed in
            ``_extract_components_from_pcb`` from this footprint's pad
            centroid. Defaults to 0.0 (the footprint's raw KiCad anchor),
            which is the historical, pre-2026-07-30 behaviour.
        center_offset_y: Y counterpart of ``center_offset_x``.

    Returns:
        (width, height) in mm: a box symmetric around
        ``(center_offset_x, center_offset_y)`` that encloses every
        courtyard/fabrication-layer graphic and every pad's copper extent.

    **Why the offset argument exists (2026-07-30).** ``CpSatModel`` places
    this box centred at the component's ``x_center``/``y_center``, which is
    ``Component.initial_position`` -- and *that* point is the footprint's
    raw KiCad anchor shifted by the pad centroid
    (``_extract_components_from_pcb``: ``fp.position + rotated(center_offset)``),
    not the raw anchor itself. A box computed symmetric around the raw
    anchor (``center_offset=(0, 0)``, the old unconditional behaviour) is
    being drawn around the WRONG point once the placement position is
    shifted -- for a footprint whose pads are perfectly symmetric about
    their own centroid this is harmless (the shift is zero), but for one
    whose pad *sizes* are asymmetric enough that the centroid diverges
    from the extent's own midpoint, the old box could fail to cover real
    copper at the position the solver actually places it at -- silently
    reintroducing the exact "off-centre pad offset defeats centered
    component bounds" bug class this repo already fixed once (see
    ``docs/solutions/logic-errors/off-center-pad-offset-defeats-centered-bounds-2026-07-08.md``),
    just at a different origin than that fix addressed. See
    ``docs/evidence/2026-07-30-domain-clearance-copper-aware-fix.md`` for
    the synthetic counter-example, the proof this argument closes, and why
    it does not manifest as an actual violation on the real board's
    current footprints (measured directly: 0 of 168 components exhibit
    positive overhang either way -- this fix is precautionary/proof-
    restoring, not a reaction to an observed failure on this board).
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
        hw = max(abs(x_min - center_offset_x), abs(x_max - center_offset_x))
        hh = max(abs(y_min - center_offset_y), abs(y_max - center_offset_y))
        return (max(0.5, 2 * hw), max(0.5, 2 * hh))

    if gfx_bounds is not None:
        hw = max(abs(gfx_bounds[0] - center_offset_x), abs(gfx_bounds[2] - center_offset_x))
        hh = max(abs(gfx_bounds[1] - center_offset_y), abs(gfx_bounds[3] - center_offset_y))
        return (max(0.5, 2 * hw), max(0.5, 2 * hh))

    if pad_x_min != float("inf"):
        hw = max(abs(pad_x_min - center_offset_x), abs(pad_x_max - center_offset_x))
        hh = max(abs(pad_y_min - center_offset_y), abs(pad_y_max - center_offset_y))
        return (max(0.5, 2 * hw), max(0.5, 2 * hh))

    return (2.0, 2.0)
