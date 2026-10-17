#!/usr/bin/env python3
"""Extend the approved FlashLayer-aware power export to the D1 gate nets.

This wrapper imports tools/export_power_copper.py unchanged. KiCad Python is
required. The companion barrel and pad catalogue preserves physical terminals
that a planar copper-only export cannot represent.
"""
from __future__ import annotations

import gzip
import hashlib
import importlib.util
import json
from pathlib import Path

import pcbnew as pcb

HERE = Path(__file__).resolve().parent
UNIT = HERE.parents[3]
BOARD = UNIT / "native-17/section.kicad_pcb"
EXPORTER = UNIT / "tools/export_power_copper.py"
BOARD_SHA = "16e8b70bb7f2bc9020ea574022c13661cd09640ca3a52db1ff43f9f6db976162"
GATE_NETS = {
    "leg_a-out_h", "leg_a-gate_h", "leg_a-out_l", "leg_a-gate_l",
    "leg_b-out_h", "leg_b-gate_h", "leg_b-out_l", "leg_b-gate_l",
}
BRANCHES = {
    "A": (
        ("P_BUS_C38", "C38.1", "Q2.2", "bus_p"),
        ("P_BUS_C39", "C39.1", "Q2.2", "bus_p"),
        ("P_SW", "Q2.3", "Q3.2", "sw_a"),
        ("P_SOURCE", "Q3.3", "R5.1", "leg_ret"),
        ("P_RETURN_C38", "R5.4", "C38.2", "hv_ret"),
        ("P_RETURN_C39", "R5.4", "C39.2", "hv_ret"),
        ("GH_OUT", "U1.15", "R10.1", "leg_a-out_h"),
        ("GH_GATE", "R10.2", "Q2.1", "leg_a-gate_h"),
        ("GH_RETURN", "Q2.3", "U1.14", "sw_a"),
        ("GL_OUT", "U1.10", "R12.1", "leg_a-out_l"),
        ("GL_GATE", "R12.2", "Q3.1", "leg_a-gate_l"),
        ("GL_RETURN", "Q3.3", "U1.9", "leg_ret"),
    ),
    "B": (
        ("P_BUS_C40", "C40.1", "Q5.2", "bus_p"),
        ("P_BUS_C41", "C41.1", "Q5.2", "bus_p"),
        ("P_SW", "Q5.3", "Q6.2", "sw_b"),
        ("P_SOURCE", "Q6.3", "R5.1", "leg_ret"),
        ("P_RETURN_C40", "R5.4", "C40.2", "hv_ret"),
        ("P_RETURN_C41", "R5.4", "C41.2", "hv_ret"),
        ("GH_OUT", "U2.15", "R18.1", "leg_b-out_h"),
        ("GH_GATE", "R18.2", "Q5.1", "leg_b-gate_h"),
        ("GH_RETURN", "Q5.3", "U2.14", "sw_b"),
        ("GL_OUT", "U2.10", "R20.1", "leg_b-out_l"),
        ("GL_GATE", "R20.2", "Q6.1", "leg_b-gate_l"),
        ("GL_RETURN", "Q6.3", "U2.9", "leg_ret"),
    ),
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    if sha(BOARD) != BOARD_SHA:
        raise ValueError("native-17 board hash changed")
    spec = importlib.util.spec_from_file_location("power_export", EXPORTER)
    if spec is None or spec.loader is None:
        raise ValueError("cannot import approved exporter")
    power_export = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(power_export)
    power_export.NETS.update(GATE_NETS)
    data = power_export.export(BOARD)
    if data["board_sha256"] != BOARD_SHA:
        raise ValueError("exporter read a different board")
    board = pcb.LoadBoard(str(BOARD))
    layers = (pcb.F_Cu, pcb.In1_Cu, pcb.In2_Cu, pcb.B_Cu)
    pads = {}
    barrels = []
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            net = pad.GetNetname()
            if net not in power_export.NETS:
                continue
            ref = f"{fp.GetReference()}.{pad.GetNumber()}"
            xy = [pcb.ToMM(pad.GetPosition().x), pcb.ToMM(pad.GetPosition().y)]
            drill = [pcb.ToMM(pad.GetDrillSize().x), pcb.ToMM(pad.GetDrillSize().y)]
            flashes = [board.GetLayerName(lid) for lid in layers if pad.IsOnLayer(lid) and pad.FlashLayer(lid)]
            pads[ref] = {"net": net, "xy_mm": xy, "flashed_layers": flashes,
                         "component_layer": board.GetLayerName(fp.GetLayer()),
                         "drill_mm": drill}
            if pad.GetAttribute() == pcb.PAD_ATTRIB_PTH and min(drill) > 0:
                barrels.append({"kind": "pad", "ref": ref, "net": net,
                                "centre": xy, "drill_mm": drill,
                                "flashed_layers": flashes,
                                "physical_span_layers": ["F.Cu", "B.Cu"],
                                "component_side": board.GetLayerName(fp.GetLayer())})
    for item in board.GetTracks():
        if item.Type() != pcb.PCB_VIA_T or item.GetNetname() not in power_export.NETS:
            continue
        via = pcb.Cast_to_PCB_VIA(item)
        barrels.append({"kind": "via", "net": via.GetNetname(),
                        "centre": [pcb.ToMM(via.GetPosition().x), pcb.ToMM(via.GetPosition().y)],
                        "drill_mm": pcb.ToMM(via.GetDrillValue()),
                        "flashed_layers": [board.GetLayerName(lid) for lid in layers if via.IsOnLayer(lid) and via.FlashLayer(lid)],
                        "physical_span_layers": [board.GetLayerName(via.TopLayer()), board.GetLayerName(via.BottomLayer())]})
    port_map = {"board_sha256": BOARD_SHA,
                "note": "Native copper branches, before any six/eight-port circuit reduction; positive current from first_ref to second_ref; no external component shorted.",
                "legs": {}}
    for leg, branches in BRANCHES.items():
        rows = []
        for name, first, second, net in branches:
            a, b = pads[first], pads[second]
            if a["net"] != net or b["net"] != net or not a["flashed_layers"] or not b["flashed_layers"]:
                raise ValueError(f"{leg}/{name}: endpoint net or flash mismatch")
            for ref, pad in ((first, a), (second, b)):
                for layer in pad["flashed_layers"]:
                    if not any(item["kind"] == "pad" and item.get("ref") == ref
                               and item["net"] == net and item["layer"] == layer
                               for item in data["primitives"]):
                        raise ValueError(f"{leg}/{name}: {ref}/{layer} flashed in KiCad but absent from exporter")
            rows.append({"name": name, "from_ref": first, "to_ref": second,
                         "net": net, "from_xy_mm": a["xy_mm"], "to_xy_mm": b["xy_mm"],
                         "from_layers": a["flashed_layers"], "to_layers": b["flashed_layers"],
                         "from_terminal_layer": a["component_layer"],
                         "to_terminal_layer": b["component_layer"]})
        port_map["legs"][leg] = rows
    data.update(kicad_version=pcb.Version(), approved_exporter_sha256=sha(EXPORTER),
                included_gate_nets=sorted(GATE_NETS), barrels=barrels)
    raw = json.dumps(data, separators=(",", ":"), allow_nan=False).encode()
    out = HERE / "extraction" / "native17-power-and-gates.json.gz"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("wb") as handle:
        with gzip.GzipFile(fileobj=handle, mode="wb", filename="", mtime=0) as stream:
            stream.write(raw)
    port_map["copper_export_sha256"] = sha(out)
    (HERE / "port-map.json").write_text(json.dumps(port_map, indent=2) + "\n")
    (HERE / "export-summary.json").write_text(json.dumps({
        "board_sha256": BOARD_SHA, "approved_exporter_sha256": sha(EXPORTER),
        "extended_exporter_sha256": sha(Path(__file__)),
        "output_sha256": sha(out), "kicad_version": pcb.Version(),
        "primitive_count": len(data["primitives"]),
        "barrel_count": len(barrels), "suppressed_pad_layers": data["suppressed_pad_layers"],
        "included_gate_nets": sorted(GATE_NETS), "mapped_branch_count_per_leg": 12,
    }, indent=2) + "\n")
    print((HERE / "export-summary.json").read_text())


if __name__ == "__main__":
    main()
