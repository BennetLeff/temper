"""MCU block native adapter (P1 U3). KiCad owns geometry and connectivity.

Thin profile adapter over :mod:`buck_native` primitives: same load/save,
staging canonicalization, and ``CONNECTIVITY_DATA`` measurement path, but
with the ten-instance MCU movable census and the six-layer P3 target
context. Tracks may sit on any supported copper layer within the physical
order; through-vias span exactly ``F.Cu-B.Cu`` with frozen dimensions.

Zone connectivity is measured, never estimated: the host reports native
clusters (zone UUIDs included) and the Rust judge admits an obligation only
through those clusters. There is no straight-line pad-distance metric here.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import buck_native
import pcbnew

# Ten physical instances in elec/src/modules.ato::MCU (U1 identity). This is
# the documented census for the real MCU trial; the adapter itself enforces
# the operator-sealed trial contract (same refs the Rust policy sees), so
# runner-machinery controls on other geometry exercise identical layers.
FUNCTIONAL_REFS = (
    "U1",
    "C1",
    "C2",
    "C3",
    "R1",
    "R2",
    "R3",
    "R4",
    "SW1",
    "SW2",
)

# P3 six-layer physical copper order. The KiCad *file* ordinals do NOT equal
# pcbnew's internal PCB_LAYER_ID values (KiCad 10: F.Cu=0, B.Cu=2, In1.Cu=4,
# In2.Cu=6, In3.Cu=8, In4.Cu=10), so layers are resolved by NAME through
# board.GetLayerID(), never by treating a file ordinal as a layer id. The
# earlier ORDINAL_LAYERS map did exactly that and failed on the real candidate
# board (`GetLayerName(3)` is B.Mask, not In3.Cu); fixed 2026-09-10 in U4.
PHYSICAL_COPPER_ORDER = ("F.Cu", "In3.Cu", "In1.Cu", "In2.Cu", "In4.Cu", "B.Cu")
VIA_SPAN = "F.Cu-B.Cu"
VIA_DIAMETER_MM = 0.8
VIA_DRILL_MM = 0.4


def normalize_angle(angle_deg: float) -> float:
    """Map any equivalent KiCad orientation into [0, 360).

    pcbnew may report an admitted pose as -90 where the contract says 270.
    The Rust judge normalizes the same way before its orthogonality check;
    the host uses this for consistent preflight reporting only. Native
    measurement stays authoritative.
    """
    return float(angle_deg) % 360.0


def copper_layer_id(board: pcbnew.BOARD, name: str) -> int:
    """Resolve a copper layer name to its live pcbnew layer id.

    The name must resolve to a copper layer whose canonical name matches;
    anything else is a board/context mismatch, not a guess.
    """
    if name not in PHYSICAL_COPPER_ORDER:
        raise ValueError(f"Unknown copper layer {name!r}")
    layer_id = board.GetLayerID(name)
    if layer_id < 0 or board.GetLayerName(layer_id) != name:
        raise ValueError(
            f"board does not expose copper layer {name!r} (resolved {layer_id})"
        )
    return layer_id


def copper_layer_names(board: pcbnew.BOARD) -> list[str]:
    """Live copper layer names in physical order (preflight/contract check)."""
    return [board.GetLayerName(board.GetLayerID(name)) for name in PHYSICAL_COPPER_ORDER]


def movable_refs(board_path: Path) -> tuple[str, ...]:
    """Operator-sealed movable census for this trial directory.

    Read from the sibling ``task-contract.json`` written by the operator-side
    prepare step — the same list the Rust policy enforces. Fails closed when
    the contract is absent or malformed; the adapter never invents it.
    """
    contract_path = board_path.parent / "task-contract.json"
    try:
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ValueError(f"trial task contract unavailable: {error}") from error
    refs = contract.get("movable_refs")
    if (
        not isinstance(refs, list)
        or not refs
        or any(not isinstance(r, str) or not r for r in refs)
    ):
        raise ValueError("trial task contract has no usable movable_refs")
    return tuple(refs)


def place(path: Path, reference: str, x: float, y: float, angle: int) -> None:
    allowed = movable_refs(path)
    if reference not in allowed:
        raise ValueError(f"Only {allowed} may move; {reference} is protected")
    if angle not in (0, 90, 180, 270):
        raise ValueError("Orientation must be 0, 90, 180, or 270")
    board = buck_native.load(path)
    names = buck_native.footprints(board)
    if reference not in names:
        raise ValueError(f"Unknown footprint {reference}")
    target = names[reference]
    target.SetOrientationDegrees(angle)
    target.SetPosition(buck_native.position(x, y))
    buck_native.save(board, path)


def replace_copper(
    path: Path, net: str, segments: list, vias: list, zones: list
) -> None:
    """Replace mutable copper for one net on an already staged board."""
    board = buck_native.load(path)
    if board.FindNet(net) is None:
        raise ValueError(f"Unknown net {net}")
    buck_native.clear_net(board, net)
    for segment in segments:
        track = pcbnew.PCB_TRACK(board)
        track.SetStart(buck_native.position(*segment["start_mm"]))
        track.SetEnd(buck_native.position(*segment["end_mm"]))
        track.SetWidth(pcbnew.FromMM(segment["width_mm"]))
        track.SetLayer(copper_layer_id(board, segment["layer"]))
        track.SetNet(board.FindNet(net))
        board.Add(track)
    for via in vias:
        item = pcbnew.PCB_VIA(board)
        item.SetPosition(buck_native.position(*via["position_mm"]))
        # The operation contract admits only through vias spanning F.Cu-B.Cu.
        item.SetViaType(pcbnew.VIATYPE_THROUGH)
        item.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        item.SetWidth(pcbnew.FromMM(via["diameter_mm"]))
        item.SetDrill(pcbnew.FromMM(via["drill_mm"]))
        item.SetNet(board.FindNet(net))
        board.Add(item)
    for zone_spec in zones:
        zone = pcbnew.ZONE(board)
        zone.SetLayer(copper_layer_id(board, zone_spec["layer"]))
        zone.SetNet(board.FindNet(net))
        # Build the zone through its native outline API. AddOutline expects a
        # SHAPE_LINE_CHAIN; passing a polygon set here silently produced an
        # empty/unfillable zone on KiCad 10.
        outline = zone.Outline()
        outline.NewOutline()
        for x, y in zone_spec["outline_mm"]:
            outline.Append(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)))
        zone.SetLocalClearance(pcbnew.FromMM(0.2))
        zone.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
        board.Add(zone)
    # Zone filling is deliberately left to KiCad's native reload/DRC path.
    # ZONE_FILLER requires a GUI wxApp and segfaults in KiCad's headless
    # Python runtime; invoking it here would turn a valid request into an
    # unreportable process crash. No host-side polygon approximation is used.
    buck_native.save(board, path)


def _electrical_census(result: dict) -> None:
    """Collapse repeated same-number pads to one electrical identity.

    A footprint may expose the same pad number on more than one physical pad
    (the EVQP7A switch: pads ``1,1,2,2``).  Those repeats are one electrical
    terminal, which is exactly how the strict U2 pin map and the block task
    contract census treat them.  The native measurement is per physical pad,
    so the Rust block judge would otherwise see ``SW1`` with 4 pads where the
    contract has 2 and report ``unexpected_pad_census`` / ``invalid_cluster``.

    The raw physical pad list is retained under ``pads_all`` for the
    construction apparatus, which must route every terminal; the judge reads
    only ``pads`` and ignores the extra key.
    """
    for footprint in result["footprints"]:
        merged: dict[str, dict] = {}
        for pad in footprint["pads"]:
            merged.setdefault(pad["number"], pad)
        if len(merged) != len(footprint["pads"]):
            footprint["pads_all"] = list(footprint["pads"])
            footprint["pads"] = list(merged.values())
    clusters = result["block"]["connectivity"]
    by_pad: dict[str, dict] = {}
    for cluster in clusters:
        existing = by_pad.get(cluster["pad"])
        if existing is None:
            by_pad[cluster["pad"]] = {
                "pad": cluster["pad"],
                "pads": sorted(set(cluster["pads"])),
                "tracks": sorted(set(cluster["tracks"])),
            }
        else:
            existing["pads"] = sorted(set(existing["pads"]) | set(cluster["pads"]))
            existing["tracks"] = sorted(set(existing["tracks"]) | set(cluster["tracks"]))
    result["block"]["connectivity"] = list(by_pad.values())


def measure(path: Path) -> dict:
    """Native measurement with the block-profile evidence key.

    The geometry/connectivity census is fully generic (every footprint, every
    track/zone, native clusters); only the evidence key differs from the buck
    adapter, matching the ``block`` measurement the Rust judge deserializes.
    Repeated same-number pads are collapsed to one electrical identity by
    :func:`_electrical_census`.
    """
    result = buck_native.measure(path)
    result["block"] = result.pop("buck")
    _electrical_census(result)
    return result


def main() -> None:
    command, path, *args = sys.argv[1:]
    target = Path(path)
    if command == "measure":
        print(json.dumps(measure(target), allow_nan=False))
    elif command == "place":
        place(target, args[0], float(args[1]), float(args[2]), int(args[3]))
    elif command == "replace_copper":
        replace_copper(
            target,
            args[0],
            json.loads(args[1]),
            json.loads(args[2]),
            json.loads(args[3]),
        )
    elif command == "copper_layers":
        board = buck_native.load(target)
        print(json.dumps(copper_layer_names(board), allow_nan=False))
    else:
        raise ValueError("Unknown block operation")


if __name__ == "__main__":
    main()
