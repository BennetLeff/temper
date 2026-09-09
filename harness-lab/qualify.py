"""Exercise the real KiCad/evaluator chain before permitting scored trials."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import harness
import run_trials


def mutate(board: Path, expression: str) -> None:
    subprocess.run(
        [
            harness.KICAD_PYTHON,
            "-c",
            "import pcbnew,sys; b=pcbnew.LoadBoard(sys.argv[1]); "
            "f={x.GetReference():x for x in b.GetFootprints()}; "
            + expression
            + "; assert pcbnew.SaveBoard(sys.argv[1],b,True)",
            str(board),
        ],
        check=True,
        capture_output=True,
    )


def qualify(output: Path) -> None:
    if not __debug__:
        raise RuntimeError("Qualification requires assertions; do not use Python -O")
    output.mkdir(parents=True, exist_ok=False)
    contract = json.loads((harness.ROOT / "fixtures/contract.json").read_text())
    results = []

    def case(
        name: str, pose: list, expected: str, change=None, required_id=None
    ) -> dict:
        directory = output / name
        harness.prepare(directory, pose)
        if change:
            change(directory)
        result = harness.evaluate(directory, contract, directory / "evaluation")
        assert result["status"] == expected, (name, result)
        if required_id:
            assert any(f["id"].startswith(required_id) for f in result["findings"]), (
                name,
                result,
            )
        results.append({"case": name, "expected": expected, "actual": result["status"]})
        return result

    for i in range(3):
        case(f"witness-{i + 1}", [5, 10, 90], "pass")
    for i, start in enumerate(contract["starts"], 1):
        case(f"start-{i}", start, "fail", required_id="too_distant:")
    case("overlap", [10, 10, 0], "fail", required_id="kicad:courtyards_overlap")
    case("copper-clearance", [6.8, 10, 270], "fail", required_id="kicad:clearance")
    case("outside", [1, 1, 0], "fail", required_id="outside_outline:")
    case(
        "net-reassignment",
        [5, 10, 90],
        "fail",
        lambda d: mutate(
            d / "candidate.kicad_pcb",
            "next(p for p in f['C9'].Pads() if p.GetNumber()=='1').SetNet(next(p for p in f['C9'].Pads() if p.GetNumber()=='2').GetNet())",
        ),
        "protected_state_changed",
    )
    case(
        "moved-regulator",
        [5, 10, 90],
        "fail",
        lambda d: mutate(
            d / "candidate.kicad_pcb",
            "f['U3'].SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(11),pcbnew.FromMM(10)))",
        ),
        "protected_state_changed",
    )
    case(
        "changed-rules",
        [5, 10, 90],
        "fail",
        lambda d: (d / "candidate.kicad_dru").write_text("(version 1)\n"),
        "protected_context_changed",
    )

    # An asymmetric non-orthogonal probe pins native KiCad's orientation. This
    # adapter does not calculate rotation itself; domain policy permits 90s only.
    geometry = output / "geometry"
    harness.prepare(geometry, [5, 10, 45])
    observation = harness.native("measure", geometry / "candidate.kicad_pcb")
    cap = next(f for f in observation["footprints"] if f["reference"] == "C9")
    p1 = next(p for p in cap["pads"] if p["number"] == "1")
    assert abs(p1["position_mm"][0] - 3.957017) < 0.000002
    assert abs(p1["position_mm"][1] - 11.042983) < 0.000002
    results.append({"case": "native-45-degree-pad-position", "actual": "pass"})

    # A lying executable that exits successfully without a report must fail
    # closed at the real operation interface, even after a successful check.
    missing = output / "missing-report"
    harness.prepare(missing, [5, 10, 90])
    session = harness.Session(missing, contract)
    assert session.call("check", {})["status"] == "pass"
    fake_bin = output / "fake-bin"
    fake_bin.mkdir()
    fake_cli = fake_bin / "kicad-cli"
    fake_cli.write_text("#!/bin/sh\nexit 0\n")
    fake_cli.chmod(0o755)
    with patch.dict(
        os.environ, {"PATH": str(fake_bin) + os.pathsep + os.environ["PATH"]}
    ):
        assert session.call("check", {})["status"] == "indeterminate"
    session.log.close()
    results.append({"case": "missing-report-after-success", "actual": "indeterminate"})
    invalid = subprocess.run(
        [str(harness.JUDGE)], input="{}", text=True, capture_output=True
    )
    assert (
        invalid.returncode == 2
        and json.loads(invalid.stdout)["status"] == "indeterminate"
    )
    results.append({"case": "invalid-measurement", "actual": "indeterminate"})

    # Real edit/check/log path, rejected inputs, budget limit, and snapshot chain.
    directory = output / "operations"
    harness.prepare(directory, contract["starts"][0])
    session = harness.Session(directory, contract)
    assert session.call("inspect", {})["status"] == "fail"
    assert (
        session.call("place", {"x_mm": 5, "y_mm": 10, "angle_deg": 90})["status"]
        == "pass"
    )
    assert session.call("check", {})["status"] == "pass"
    before = harness.file_hash(session.board)
    for request in (
        {"x_mm": 5, "y_mm": 10, "angle_deg": 45},
        {"x_mm": 5, "y_mm": 10, "angle_deg": 90, "reference": "U3"},
    ):
        assert session.call("place", request)["status"] == "indeterminate"
        assert harness.file_hash(session.board) == before
    session.edits = 10
    assert (
        session.call("place", {"x_mm": 6, "y_mm": 10, "angle_deg": 90})["status"]
        == "indeterminate"
    )
    assert harness.file_hash(session.board) == before
    session.deadline = 0
    assert session.call("check", {})["status"] == "indeterminate"
    session.log.close()
    events = [
        json.loads(line)
        for line in (directory / "actions.jsonl").read_text().splitlines()
    ]
    assert len(events) == 1 + 2 * session.sequence
    for event in events:
        if event["kind"] == "response":
            assert event["result"]["after_sha256"] == harness.file_hash(
                directory / f"state-{event['sequence']:03}.kicad_pcb"
            )
    results.append({"case": "operation-bounds-and-log", "actual": "pass"})
    # This is a synthetic transcript test, not an agent trial. Reuse real
    # operation receipts to test the scorer's exact observation comparison.
    audit_dir = output / "transcript-audit"
    shutil.copytree(directory, audit_dir)
    original = events[:7]
    (audit_dir / "actions.jsonl").write_text(
        "".join(json.dumps(e) + "\n" for e in original)
    )
    model_events = []
    for request, response in zip(original[1::2], original[2::2]):
        model_events.append(
            {
                "type": "item.completed",
                "item": {
                    "type": "mcp_tool_call",
                    "server": "pcb",
                    "tool": request["operation"],
                    "arguments": request["arguments"],
                    "result": {
                        "content": [
                            {"type": "text", "text": json.dumps(response["result"])}
                        ]
                    },
                },
            }
        )
    model_events.append({"type": "turn.completed", "usage": None})
    assert (
        run_trials.audit(audit_dir, model_events, 30, 0, contract)["status"] == "pass"
    )
    assert (
        run_trials.audit(audit_dir, model_events, 301, 0, contract)["status"] == "fail"
    )
    model_events[0]["item"]["result"]["content"][0]["text"] = "{}"
    try:
        run_trials.audit(audit_dir, model_events, 30, 0, contract)
    except ValueError:
        pass
    else:
        raise AssertionError("Mismatched shown observation passed transcript audit")
    results.append({"case": "transcript-mismatch-and-run-budget", "actual": "pass"})
    transport_dir = output / "mcp-transport"
    harness.prepare(transport_dir, contract["starts"][0])
    messages = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-11-25"},
        },
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "inspect", "arguments": {}},
        },
    ]
    transport = subprocess.run(
        [sys.executable, str(harness.ROOT / "harness.py"), str(transport_dir)],
        input="".join(json.dumps(m) + "\n" for m in messages),
        text=True,
        capture_output=True,
        check=True,
        timeout=60,
    )
    (transport_dir / "transport.jsonl").write_text(transport.stdout)
    replies = [json.loads(line) for line in transport.stdout.splitlines()]
    assert [r["id"] for r in replies] == [1, 2, 3]
    assert replies[1]["result"]["tools"] == harness.TOOLS
    observed = json.loads(replies[2]["result"]["content"][0]["text"])
    assert (
        observed["status"] == "fail" and len(observed["measurement"]["footprints"]) == 2
    )
    results.append({"case": "native-mcp-initialize-list-inspect", "actual": "pass"})
    receipt = {
        "status": "qualified",
        "contract_sha256": harness.file_hash(harness.ROOT / "fixtures/contract.json"),
        "cases": results,
        "scope": "placement_only",
        "witness_pose_mm_deg": [5, 10, 90],
        "source_sha256": {
            name: harness.file_hash(harness.ROOT / name)
            for name in (
                "harness.py",
                "native.py",
                "qualify.py",
                "run_trials.py",
                "src/main.rs",
                "Cargo.lock",
            )
        },
        "evaluator_sha256": harness.file_hash(harness.JUDGE),
    }
    (output / "qualification.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    qualify(parser.parse_args().output.resolve())
