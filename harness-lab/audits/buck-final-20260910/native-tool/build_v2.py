"""Reproduce v2 from the reviewed v5 board using KiCad's own transforms.

Run with the isolated KiCad 10.0.6 Python interpreter. Refuse existing output;
the original frozen fixtures and production board are read-only inputs.
"""

import hashlib
import json
import shutil
import sys
from pathlib import Path

import pcbnew

LAB = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(LAB))
import build_buck


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def point(x, y):
    return pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y))


def build():
    assert pcbnew.GetBuildVersion() == "10.0.6"
    source = LAB / "audits/buck-20260910-followup/layout/candidate-v5"
    assert sha(source / "candidate.kicad_pcb") == "1d1ae546a0e78fe4c923b5cee736bc0811ca13a7cca33853274052f556d13ac3"
    destination = LAB / "fixtures/buck-v2"
    destination.mkdir(exist_ok=False)
    component_contract = json.loads((LAB / "engineering/circuit-contract.json").read_text())
    bom = {v["pcb_reference"]: v["mpn"] for v in component_contract["components"].values()}
    for vid, variant in build_buck.VARIANTS.items():
        directory = destination / vid
        directory.mkdir()
        for name in ("candidate.kicad_pro", "candidate.kicad_dru", "fp-lib-table"):
            shutil.copyfile(source / name, directory / name)
        shutil.copytree(source / "fixture.pretty", directory / "fixture.pretty")
        board = pcbnew.PCB_IO_KICAD_SEXPR().LoadBoard(str(source / "candidate.kicad_pcb"), None)
        footprints = {fp.GetReference(): fp for fp in board.GetFootprints()}
        terminal_points = {
            (pad.GetPosition().x, pad.GetPosition().y)
            for ref in ("J1", "J2", "J3") for pad in footprints[ref].Pads()
        }
        # Remove the old terminal bridges, routes and J2 via in their entirety.
        for track in list(board.GetTracks()):
            if any((p.x, p.y) in terminal_points for p in (track.GetStart(), track.GetEnd())):
                board.Delete(track)
        for ref, (x, y) in variant["terminals"].items():
            footprints[ref].SetPosition(point(x, y))
        # Keep the lowest GND label inside the reserved-b outline.
        footprints["J2"].Value().SetPosition(point(6, variant["terminals"]["J2"][1] + 2.5))

        def route(net, layer, points):
            for start, end in zip(points, points[1:]):
                if start == end:
                    continue
                segment = pcbnew.PCB_TRACK(board)
                segment.SetStart(point(*start))
                segment.SetEnd(point(*end))
                segment.SetLayer(layer)
                segment.SetWidth(pcbnew.FromMM(0.6))
                segment.SetNet(board.FindNet(net))
                board.Add(segment)

        pads = {}
        for ref in ("J1", "J2", "J3"):
            pads[ref] = sorted((pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y)) for p in footprints[ref].Pads())
        for ref, net in (("J1", "+15V"), ("J2", "gnd"), ("J3", "+3V3")):
            route(net, pcbnew.F_Cu, pads[ref])
        route("+15V", pcbnew.F_Cu, [pads["J1"][1], (8, pads["J1"][1][1]), (8, 18), (10, 18)])
        via = pcbnew.PCB_VIA(board)
        via.SetPosition(point(*pads["J2"][0]))
        via.SetWidth(pcbnew.FromMM(0.8))
        via.SetDrill(pcbnew.FromMM(0.4))
        via.SetViaType(pcbnew.VIATYPE_THROUGH)
        via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        via.SetNet(board.FindNet("gnd"))
        board.Add(via)
        route("gnd", pcbnew.B_Cu, [pads["J2"][0], (6, pads["J2"][0][1]), (6, 28), (10, 28)])
        route("+3V3", pcbnew.F_Cu, [(41.225, 18), (46.225, 18), pads["J3"][0]])
        pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(directory / "witness.kicad_pcb"), board)
        for track in list(board.GetTracks()):
            board.Delete(track)
        for ref, (x, y, degrees) in variant["staging"].items():
            footprints[ref].SetOrientationDegrees(degrees)
            footprints[ref].SetPosition(point(x, y))
        pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(directory / "candidate.kicad_pcb"), board)
        shutil.copyfile(directory / "candidate.kicad_pcb", directory / "start.kicad_pcb")
        metadata = json.loads((LAB / "fixtures/buck" / vid / "source.json").read_text())
        metadata.update(kicad_version="10.0.6", fixture_revision="buck-v2-reference-v5", bom=bom,
                        reference_board_sha256=sha(source / "candidate.kicad_pcb"),
                        component_contract_sha256=sha(LAB / "engineering/circuit-contract.json"))
        (directory / "source.json").write_text(json.dumps(metadata, indent=2) + "\n")
    contract_path = destination / "buck-v2-contract.json"
    build_buck.write_contract(destination, contract_path, pcbnew)
    contract = json.loads(contract_path.read_text())
    contract.update(version=2, fixture_revision="buck-v2-reference-v5")
    contract["source"]["reference_board_sha256"] = sha(source / "candidate.kicad_pcb")
    contract["source"]["component_contract_sha256"] = sha(LAB / "engineering/circuit-contract.json")
    contract_path.write_text(json.dumps(contract, indent=2) + "\n")


if __name__ == "__main__":
    build()
