"""Freeze three scripted bad copper starts; run with KiCad's bundled Python."""

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
    destination = root / "fixtures/e00r-repair"
    destination.mkdir(exist_ok=False)
    contract = json.loads((root / "fixtures/obstacle-contract.json").read_text())
    contract.pop("initial_board_sha256")
    contract.update(experiment="00R-R", starts=["a", "b", "c"], repair_cases={})
    detour = [[6, 11.475], [6, 12.5], [8.8625, 12.5], [8.8625, 10.95]]
    ground = [[6, 8.525], [7.5, 8.525], [8.8625, 9.05]]
    cases = [
        ("a", [[6, 11.475], [8.8625, 10.95]], "kicad:items_not_allowed:"),
        (
            "b",
            [
                [6, 11.475],
                [6, 12.5],
                [9.9, 12.5],
                [9.9, 10.5],
                [8.8625, 10.5],
                [8.8625, 10.95],
            ],
            "kicad:clearance:",
        ),
        ("c", detour, "unrouted:"),
    ]
    for name, points, prefix in cases:
        directory = destination / name
        shutil.copytree(root / "fixtures/e00r-obstacle", directory)
        path = directory / "candidate.kicad_pcb"
        routing_native.route(path, "+15V", points)
        routing_native.route(path, "gnd", ground)
        if name == "c":
            board = routing_native.load(path)
            track = next(
                t
                for t in board.GetTracks()
                if t.GetNetname() == "gnd" and pcbnew.ToMM(t.GetStart().x) > 7
            )
            track.SetStart(native.position(8.1, 8.9))
            routing_native.save(board, path)
        measured = routing_native.measure(path)
        assert measured["protected_sha256"] == contract["protected_sha256"]
        assert harness.context_hash(directory) == contract["context_sha256"]
        contract["repair_cases"][name] = {
            "initial_board_sha256": harness.file_hash(path),
            "required_finding_prefix": prefix,
        }
    (root / "fixtures/repair-contract.json").write_text(
        json.dumps(contract, indent=2) + "\n"
    )


if __name__ == "__main__":
    build()
