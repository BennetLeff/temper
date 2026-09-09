"""Build the fixed native keepout fixture once; run with KiCad's bundled Python."""

from __future__ import annotations

import json
import shutil

import pcbnew

import harness
import native
import routing_native


def build() -> None:
    if pcbnew.GetBuildVersion() != "10.0.4":
        raise RuntimeError("Fixture requires KiCad 10.0.4")
    root = harness.ROOT
    destination = root / "fixtures/e00r-obstacle"
    shutil.copytree(root / "fixtures/e00r", destination)
    path = destination / "candidate.kicad_pcb"
    board = routing_native.load(path)
    area = pcbnew.ZONE(board)
    area.SetLayer(pcbnew.F_Cu)
    area.SetIsRuleArea(True)
    area.SetDoNotAllowTracks(True)
    area.SetDoNotAllowVias(False)
    area.SetDoNotAllowPads(False)
    area.SetDoNotAllowZoneFills(False)
    area.SetDoNotAllowFootprints(False)
    area.Outline().NewOutline()
    for x, y in [(7.55, 10.5), (7.95, 10.5), (7.95, 12.0), (7.55, 12.0)]:
        area.Outline().Append(native.position(x, y))
    board.Add(area)
    routing_native.save(board, path)
    measurement = routing_native.measure(path)
    contract = json.loads((root / "fixtures/routing-contract.json").read_text())
    contract.update(
        experiment="00R-O",
        initial_board_sha256=harness.file_hash(path),
        protected_sha256=measurement["protected_sha256"],
        context_sha256=harness.context_hash(destination),
    )
    (root / "fixtures/obstacle-contract.json").write_text(
        json.dumps(contract, indent=2) + "\n"
    )
    print(json.dumps(measurement["routing"]["keepouts"], indent=2))


if __name__ == "__main__":
    build()
