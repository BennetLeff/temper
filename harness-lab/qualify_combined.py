"""Qualify joint placement/routing and native copper behavior before model trials."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import combined_host as task
import harness
from qualify_routing import mutate
from run_trials import audit

DETOUR = [[6, 11.475], [6, 12.5], [8.8625, 12.5], [8.8625, 10.95]]
GROUND = [[6, 8.525], [8.8625, 9.05]]
POSE = {"x_mm": 6, "y_mm": 10, "angle_deg": 90}


def qualify(output: Path) -> None:
    if not __debug__:
        raise RuntimeError("Qualification requires assertions")
    output.mkdir(parents=True, exist_ok=False)
    contract = json.loads(task.CONTRACT.read_text())
    cases = []
    for index, start in enumerate(contract["starts"], 1):
        directory = output / f"start-{index}"
        task.prepare(directory, start)
        session = task.Session(directory, contract)
        first = session.call("inspect", {})
        assert first["status"] == "fail"
        assert first["measurement"]["protected_sha256"] == contract["protected_sha256"]
        placed = session.call("place", POSE)
        assert placed["status"] == "fail" and any(
            f["id"].startswith("unrouted:") for f in placed["findings"]
        )
        assert (
            session.call("route", {"net": "+15V", "points_mm": DETOUR})["status"]
            == "fail"
        )
        assert (
            session.call("route", {"net": "gnd", "points_mm": GROUND})["status"]
            == "pass"
        )
        assert session.call("check", {})["status"] == "pass"
        assert session.edits == 3
        session.log.close()
        actions = [
            json.loads(line)
            for line in (directory / "actions.jsonl").read_text().splitlines()
        ]
        events = [
            {
                "type": "item.completed",
                "item": {
                    "type": "mcp_tool_call",
                    "server": "pcb",
                    "tool": a["operation"],
                    "arguments": a["arguments"],
                    "result": {
                        "content": [{"type": "text", "text": json.dumps(b["result"])}]
                    },
                },
            }
            for a, b in zip(actions[1::2], actions[2::2])
        ]
        events.append({"type": "turn.completed"})
        checked = audit(
            directory,
            events,
            30,
            0,
            contract,
            edit_operations=("place", "route", "remove_route"),
        )
        assert checked["status"] == "pass" and checked["placement_edits"] == 3
        task.audit_combined(directory, start, contract)
        assert (
            task.evaluate(directory, contract, directory / "host-final-check")["status"]
            == "pass"
        )
        cases.append(
            {
                "case": f"start-{index}-place-and-route",
                "actual": "pass",
                "scripted_edits": 3,
            }
        )
        print(cases[-1], flush=True)
    valid = output / "start-1/candidate.kicad_pcb"

    def ready(name):
        directory = output / name
        task.prepare(directory, contract["starts"][0])
        shutil.copyfile(valid, directory / "candidate.kicad_pcb")
        return directory

    for name, expression, prefix in [
        (
            "moved-U3",
            "f['U3'].SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(11),pcbnew.FromMM(10)))",
            "protected_state_changed",
        ),
        (
            "changed-pad-net",
            "next(iter(f['C9'].Pads())).SetNet(b.FindNet('sw'))",
            "protected_state_changed",
        ),
        (
            "changed-pad-shape",
            "next(iter(f['C9'].Pads())).SetSize(pcbnew.VECTOR2I(pcbnew.FromMM(1),pcbnew.FromMM(1)))",
            "protected_state_changed",
        ),
        (
            "removed-keepout",
            "b.Delete(next(iter(b.Zones())))",
            "protected_state_changed",
        ),
        (
            "wrong-width",
            "next(iter(b.GetTracks())).SetWidth(pcbnew.FromMM(.3))",
            "unsupported_track:",
        ),
    ]:
        directory = ready(name)
        mutate(directory / "candidate.kicad_pcb", expression)
        result = task.evaluate(directory, contract, directory / "evaluation")
        assert result["status"] == "fail" and any(
            f["id"].startswith(prefix) for f in result["findings"]
        ), result
        cases.append({"case": name, "expected": "fail", "actual": result["status"]})
    directory = ready("changed-rules")
    (directory / "candidate.kicad_dru").write_text("(version 1)\n")
    result = task.evaluate(directory, contract, directory / "evaluation")
    assert result["status"] == "fail" and any(
        f["id"] == "protected_context_changed" for f in result["findings"]
    )
    cases.append({"case": "changed-rules", "expected": "fail", "actual": "fail"})

    directory = ready("move-after-routing")
    session = task.Session(directory, contract)
    before = session.call("inspect", {})
    assert before["status"] == "pass"
    moved = session.call("place", {"x_mm": 16, "y_mm": 16, "angle_deg": 270})
    assert moved["status"] == "fail" and any(
        f["id"].startswith("unrouted:") for f in moved["findings"]
    )
    assert (
        moved["measurement"]["routing"]["tracks"]
        == before["measurement"]["routing"]["tracks"]
    )
    assert moved["measurement"]["protected_sha256"] == contract["protected_sha256"]
    assert session.call("place", POSE)["status"] == "pass"
    session.log.close()
    cases.append(
        {
            "case": "move-leaves-copper-and-breaks-connectivity-restore-passes",
            "actual": "pass",
        }
    )

    directory = ready("raw-net-survives-place")
    mutate(
        directory / "candidate.kicad_pcb",
        "next(iter(b.GetTracks())).SetNet(b.FindNet('sw'))",
    )
    session = task.Session(directory, contract)
    before = session.call("inspect", {})
    moved = session.call("place", {"x_mm": 16, "y_mm": 16, "angle_deg": 270})
    assert (
        moved["measurement"]["routing"]["tracks"]
        == before["measurement"]["routing"]["tracks"]
    )
    assert any(t["net"] == "sw" for t in moved["measurement"]["routing"]["tracks"])
    assert moved["status"] == "fail"
    session.log.close()
    cases.append(
        {"case": "placement-does-not-auto-fix-raw-track-nets", "actual": "pass"}
    )

    directory = ready("shared-edit-budget")
    session = task.Session(directory, contract)
    for i in range(10):
        result = (
            session.call("place", POSE)
            if i % 2 == 0
            else session.call("route", {"net": "gnd", "points_mm": GROUND})
        )
        assert result["status"] == "pass"
    assert session.edits == 10
    before = harness.file_hash(session.board)
    for name, args in [
        ("place", POSE),
        ("route", {"net": "gnd", "points_mm": GROUND}),
        ("remove_route", {"net": "gnd"}),
    ]:
        assert session.call(name, args)["status"] == "indeterminate"
        assert harness.file_hash(session.board) == before
    session.log.close()
    cases.append({"case": "one-budget-for-mixed-edits", "actual": "pass"})

    directory = ready("inspection-and-input-boundaries")
    session = task.InspectionSession(directory, contract)
    before = harness.file_hash(session.board)
    for name, args in [
        ("place", POSE),
        ("route", {"net": "gnd", "points_mm": GROUND}),
        ("remove_route", {"net": "gnd"}),
    ]:
        assert session.call(name, args)["status"] == "indeterminate"
        assert harness.file_hash(session.board) == before
    assert session.edits == 0
    session.log.close()
    directory = ready("invalid-placement")
    session = task.Session(directory, contract)
    before = harness.file_hash(session.board)
    for args in [
        {**POSE, "angle_deg": 45},
        {**POSE, "x_mm": True},
        {**POSE, "reference": "U3"},
    ]:
        assert session.call("place", args)["status"] == "indeterminate"
        assert harness.file_hash(session.board) == before
    session.log.close()
    cases.append(
        {"case": "preflight-and-invalid-placement-do-not-edit", "actual": "pass"}
    )
    receipt = {
        "status": "qualified",
        "scope": "joint_placement_and_routing",
        "cases": cases,
        "contract_sha256": harness.file_hash(task.CONTRACT),
        "source_sha256": {
            str(p.relative_to(harness.ROOT)): harness.file_hash(p)
            for p in sorted(
                [
                    *harness.ROOT.glob("*.py"),
                    *harness.ROOT.glob("src/*.rs"),
                    harness.ROOT / "Cargo.lock",
                ]
            )
        },
        "evaluator_sha256": harness.file_hash(harness.JUDGE),
    }
    (output / "qualification.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(f"Qualified {len(cases)} combined controls", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    qualify(parser.parse_args().output.resolve())
