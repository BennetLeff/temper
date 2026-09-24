"""Generate and audit the SELV service coupon PCB from its compiled netlist.

Requires ``kiutils`` and KICAD10_FOOTPRINT_DIR. The Tag-Connect footprint uses
KiCad's ``connect`` pad type; the shared strict candidate builder only assigns
``smd`` and ``thru_hole`` pads, so this adapter assigns those six spring-contact
pads explicitly after the base board is constructed.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

from kiutils.board import Board


ROOT = Path(__file__).resolve().parents[4]
SOURCE = ROOT / "zapote/programming-ui/source-build-01"
OUTPUT = Path(__file__).resolve().parent / "native"
sys.path.insert(0, str(ROOT / "scripts"))
import gen_pcb_skeleton as pcb  # noqa: E402


EXPECTED = {
    "service_txd0": {("J1", "1"), ("R1", "1"), ("D1", "1")},
    "target_txd0": {("J2", "1"), ("R1", "2")},
    "rxd0": {("J1", "2"), ("J2", "2"), ("D2", "1")},
    "en_n": {("J1", "3"), ("J2", "3"), ("D3", "1")},
    "io0": {("J1", "4"), ("J2", "4"), ("D4", "1")},
    "target_3v3_sense": {("J1", "5"), ("J2", "5")},
    "selv_return": {
        ("J1", "6"), ("J2", "6"), ("D1", "2"), ("D2", "2"),
        ("D3", "2"), ("D4", "2"),
    },
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    footprint_root = os.environ.get("KICAD10_FOOTPRINT_DIR")
    if not footprint_root or not Path(footprint_root).is_dir():
        raise RuntimeError("set KICAD10_FOOTPRINT_DIR to the official KiCad footprint root")
    net_path = SOURCE / "build/default.net"
    netlist = pcb.parse_netlist(net_path)
    observed = {net.name: set(net.nodes) for net in netlist.nets.values()}
    if observed != EXPECTED:
        raise ValueError(f"compiled pin map drifted: {observed!r}")
    if set(netlist.components) != {"J1", "J2", "R1", "D1", "D2", "D3", "D4"}:
        raise ValueError("compiled component census drifted")
    pin_map = {(ref, pin): pin for nodes in EXPECTED.values() for ref, pin in nodes}
    placements = {
        "J1": (22.0, 25.0, 0.0),
        "J2": (56.0, 19.0, 0.0),
        "R1": (44.0, 16.0, 0.0),
        "D1": (34.0, 15.0, 0.0),
        "D2": (35.0, 20.0, 0.0),
        "D3": (36.0, 25.0, 0.0),
        "D4": (37.0, 30.0, 0.0),
    }
    board_path = OUTPUT / "service_coupon.kicad_pcb"
    outline = (10.0, 10.0, 66.0, 42.0)
    result = pcb.generate_candidate_board(
        netlist,
        pin_map,
        set(),
        OUTPUT / "fp-lib-table",
        outline,
        placements,
        board_path,
        values={
            "J1": "TC2030-IDC-NL-FP",
            "J2": "TSW-106-07-G-S",
            "R1": "RC0603FR-07499RL",
            **{f"D{i}": "TPD1E05U06DYAR" for i in range(1, 5)},
        },
    )
    board = Board.from_file(str(board_path))
    connector = next(fp for fp in board.footprints if fp.properties["Reference"] == "J1")
    net_by_name = {net.name: net for net in board.nets}
    for pad in connector.pads:
        if pad.number in {"1", "2", "3", "4", "5", "6"}:
            name = next(name for name, nodes in EXPECTED.items() if ("J1", pad.number) in nodes)
            pad.net = net_by_name[name]
    board.to_file(str(board_path))
    loaded = Board.from_file(str(board_path))
    actual = {
        (fp.properties["Reference"], pad.number): pad.net.name
        for fp in loaded.footprints
        for pad in fp.pads
        if pad.number and pad.net is not None
    }
    expected = {(ref, pin): name for name, nodes in EXPECTED.items() for ref, pin in nodes}
    if actual != expected:
        raise ValueError(f"board pad-net mapping differs from Atopile: {actual!r}")
    receipt = {
        "status": "placed-unrouted-coupon",
        "source_sha256": sha256(SOURCE / "elec/src/service_coupon.ato"),
        "netlist_sha256": sha256(net_path),
        "board_sha256": sha256(board_path),
        "pin_map": {name: sorted(f"{ref}.{pin}" for ref, pin in nodes) for name, nodes in EXPECTED.items()},
        "outline_mm": outline,
        "placement_mm": placements,
        "generator_summary": result,
        "product_service_accepted": False,
    }
    (OUTPUT.parent / "placed-board-receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
