#!/usr/bin/env python3
"""Transport the audited Atopile fixture netlist into a routed KiCad coupon.

The Rust rail-order audit owns the connectivity contract. This adapter has a
fixed placement and copper drawing for that exact 13-footprint netlist; it
fails closed if the source topology changes. It does not model a power supply.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pcbnew

REPO = Path(__file__).resolve().parents[4]
FIXTURE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
from gen_pcb_skeleton import parse_netlist  # noqa: E402


def xy(x_mm: float, y_mm: float) -> pcbnew.VECTOR2I:
    return pcbnew.VECTOR2I(pcbnew.FromMM(x_mm), pcbnew.FromMM(y_mm))


def add_track(
    board: pcbnew.BOARD,
    net: pcbnew.NETINFO_ITEM,
    layer: int,
    points: list[pcbnew.VECTOR2I],
    width_mm: float = 0.3,
) -> None:
    for start, end in zip(points, points[1:]):
        if start == end:
            continue
        segment = pcbnew.PCB_TRACK(board)
        segment.SetStart(start)
        segment.SetEnd(end)
        segment.SetWidth(pcbnew.FromMM(width_mm))
        segment.SetLayer(layer)
        segment.SetNet(net)
        board.Add(segment)


def build() -> None:
    native = FIXTURE / "candidate"
    netlist = parse_netlist(FIXTURE / "build/default.net")
    expected_refs = {"J1", "J2", "J3", *(f"TP{i}" for i in range(1, 11))}
    expected_nets = {
        "aux_protected", "hot_logic5", "hot0", "driver_permission", "ena_node",
        "en_shunt_base", "pfc_pwm", "stw_gate", "hot_run_q", "hot_session_q",
    }
    if set(netlist.components) != expected_refs:
        raise ValueError("fixture component set changed; review placement and routing")
    nets_by_name = {net.name: net for net in netlist.nets.values()}
    if set(nets_by_name) != expected_nets:
        raise ValueError("fixture net set changed; review placement and routing")
    expected_nodes = {
        "aux_protected": {("J1", "1"), ("J3", "1"), ("TP1", "1")},
        "hot_logic5": {("J2", "1"), ("J3", "2"), ("TP2", "1")},
        "hot0": {("J1", "2"), ("J2", "2"), ("J3", "3"), ("TP3", "1")},
        "driver_permission": {("J3", "4"), ("TP4", "1")},
        "ena_node": {("J3", "5"), ("TP5", "1")},
        "en_shunt_base": {("J3", "6"), ("TP6", "1")},
        "pfc_pwm": {("J3", "7"), ("TP7", "1")},
        "stw_gate": {("J3", "8"), ("TP8", "1")},
        "hot_run_q": {("J3", "9"), ("TP9", "1")},
        "hot_session_q": {("J3", "10"), ("TP10", "1")},
    }
    for name, nodes in expected_nodes.items():
        if set(nets_by_name[name].nodes) != nodes:
            raise ValueError(f"fixture net {name} changed; refuse stale copper")

    board = pcbnew.BOARD()
    board_nets: dict[str, pcbnew.NETINFO_ITEM] = {}
    for name in sorted(expected_nets):
        net = pcbnew.NETINFO_ITEM(board, name)
        board.Add(net)
        board_nets[name] = net
    pad_nets = {
        node: name for name, net in nets_by_name.items() for node in net.nodes
    }

    poses = {"J1": (15, 15), "J2": (15, 32), "J3": (85, 15)}
    poses.update({f"TP{i}": (62, 15 + 2.54 * (i - 1)) for i in range(1, 11)})
    pad_positions: dict[tuple[str, str], pcbnew.VECTOR2I] = {}
    for ref in sorted(expected_refs):
        nickname, item = netlist.components[ref].footprint.split(":", 1)
        lib = native / "candidate-libs" / f"{nickname}.pretty"
        fp = pcbnew.FootprintLoad(str(lib), item)
        if fp is None:
            raise ValueError(f"missing pinned footprint {nickname}:{item}")
        fp.SetFPIDAsString(f"{nickname}:{item}")
        fp.SetReference(ref)
        fp.SetValue("?")
        fp.SetPosition(xy(*poses[ref]))
        # Dense 2.54 mm probe rows make the library's default reference text
        # overlap adjacent copper. The pad map remains in the schematic and
        # fixture README; hide these default labels on the candidate copper.
        fp.Reference().SetVisible(False)
        board.Add(fp)
        found: set[str] = set()
        for pad in fp.Pads():
            pin = pad.GetNumber()
            if pin in found or (ref, pin) not in pad_nets:
                raise ValueError(f"unexpected or duplicate pad {ref}.{pin}")
            found.add(pin)
            pad.SetNet(board_nets[pad_nets[(ref, pin)]])
            pad_positions[(ref, pin)] = pad.GetPosition()
        expected_pins = {pin for node_ref, pin in pad_nets if node_ref == ref}
        if found != expected_pins:
            raise ValueError(f"footprint pads for {ref} differ from source pins")

    for i, name in enumerate(
        ("aux_protected", "hot_logic5", "hot0", "driver_permission", "ena_node",
         "en_shunt_base", "pfc_pwm", "stw_gate", "hot_run_q", "hot_session_q"),
        start=1,
    ):
        add_track(
            board, board_nets[name], pcbnew.F_Cu,
            [pad_positions[("J3", str(i))], pad_positions[(f"TP{i}", "1")]],
        )

    # Supply leads run on the back. J1 and J2 share only the HOT0 return.
    add_track(board, board_nets["aux_protected"], pcbnew.B_Cu, [
        pad_positions[("J1", "1")], xy(15, 10), xy(85, 10), pad_positions[("J3", "1")],
    ])
    add_track(board, board_nets["hot_logic5"], pcbnew.B_Cu, [
        pad_positions[("J2", "1")], xy(20, 32), xy(20, 50), xy(92, 50),
        xy(92, 17.54), pad_positions[("J3", "2")],
    ])
    add_track(board, board_nets["hot0"], pcbnew.B_Cu, [
        pad_positions[("J1", "2")], xy(12, 17.54), xy(12, 55),
        xy(98, 55), xy(98, 20.08),
    ])
    add_track(board, board_nets["hot0"], pcbnew.B_Cu, [
        pad_positions[("J2", "2")], xy(12, 34.54),
    ])
    via = pcbnew.PCB_VIA(board)
    via.SetPosition(xy(98, 20.08))
    via.SetWidth(pcbnew.FromMM(0.8))
    via.SetDrill(pcbnew.FromMM(0.4))
    via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    via.SetNet(board_nets["hot0"])
    board.Add(via)
    add_track(board, board_nets["hot0"], pcbnew.F_Cu, [
        xy(98, 20.08), pad_positions[("J3", "3")],
    ])

    outline = [xy(5, 5), xy(105, 5), xy(105, 60), xy(5, 60)]
    for start, end in zip(outline, outline[1:] + outline[:1]):
        edge = pcbnew.PCB_SHAPE(board)
        edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetStart(start)
        edge.SetEnd(end)
        edge.SetLayer(pcbnew.Edge_Cuts)
        edge.SetWidth(pcbnew.FromMM(0.05))
        board.Add(edge)
    def silk(text: str, x: float, y: float, size: float = 0.8) -> None:
        label = pcbnew.PCB_TEXT(board)
        label.SetText(text)
        label.SetPosition(xy(x, y))
        label.SetLayer(pcbnew.F_SilkS)
        label.SetTextSize(xy(size, size))
        label.SetTextThickness(pcbnew.FromMM(0.12))
        board.Add(label)

    silk("LAB ONLY - ISOLATED LV", 52, 7, 1.0)
    silk("J1 AUX_PROTECTED", 31, 16)
    silk("J2 HOT_LOGIC5", 31, 33)
    silk("J3 DUT", 93, 43)
    for i in range(1, 11):
        silk(f"TP{i}", 55, 15 + 2.54 * (i - 1))

    output = native / "rail-order-fixture.kicad_pcb"
    pcbnew.SaveBoard(str(output), board)
    print(f"wrote {output}: {len(expected_refs)} footprints, {len(expected_nets)} nets")


if __name__ == "__main__":
    build()
