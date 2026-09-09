"""Freeze three misplaced, unrouted starts using native KiCad transforms."""

from __future__ import annotations

import json
import shutil

import pcbnew

import combined_native
import harness


def build() -> None:
    if pcbnew.GetBuildVersion() != "10.0.4":
        raise RuntimeError("Fixture requires KiCad 10.0.4")
    root = harness.ROOT
    dest = root / "fixtures/e00pr"
    dest.mkdir(exist_ok=False)
    contract = json.loads((root / "fixtures/obstacle-contract.json").read_text())
    contract.pop("initial_board_sha256")
    contract.pop("max_routing_edits")
    contract.update(
        experiment="00PR",
        max_total_edits=10,
        starts=[[22, 15, 0], [22, 5, 180], [16, 16, 270]],
        initial_boards_sha256=[],
    )
    protected = set()
    for index, pose in enumerate(contract["starts"], 1):
        directory = dest / str(index)
        shutil.copytree(root / "fixtures/e00r-obstacle", directory)
        path = directory / "candidate.kicad_pcb"
        combined_native.place(path, *pose)
        measured = combined_native.measure(path)
        protected.add(measured["protected_sha256"])
        assert harness.context_hash(directory) == contract["context_sha256"]
        assert not measured["routing"]["tracks"]
        contract["initial_boards_sha256"].append(harness.file_hash(path))
    assert len(protected) == 1
    contract["protected_sha256"] = protected.pop()
    (root / "fixtures/combined-contract.json").write_text(
        json.dumps(contract, indent=2) + "\n"
    )


if __name__ == "__main__":
    build()
