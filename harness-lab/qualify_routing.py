"""Qualify routing against native KiCad positive and adversarial controls."""

from __future__ import annotations

import argparse
import copy
import json
import subprocess
from pathlib import Path

import harness
import routing_host as routing
from run_trials import audit

WITNESS = {
    "+15V": [[6, 11.475], [7.5, 11.475], [8.8625, 10.95]],
    "gnd": [[6, 8.525], [7.5, 8.525], [8.8625, 9.05]],
}


def mutate(board: Path, expression: str) -> None:
    subprocess.run(
        [
            harness.KICAD_PYTHON,
            "-c",
            "import pcbnew,sys; b=pcbnew.PCB_IO_KICAD_SEXPR().LoadBoard(sys.argv[1],None); f={x.GetReference():x for x in b.GetFootprints()}; "
            + expression
            + "; pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(sys.argv[1],b)",
            str(board),
        ],
        check=True,
        capture_output=True,
    )


def put(directory: Path, net: str, points: list) -> None:
    harness.native(
        "route",
        directory / "candidate.kicad_pcb",
        net,
        json.dumps(points),
        adapter=routing.ADAPTER,
    )


def qualify(output: Path) -> None:
    if not __debug__:
        raise RuntimeError("Qualification requires assertions")
    output.mkdir(parents=True, exist_ok=False)
    contract = json.loads(routing.CONTRACT.read_text())
    results = []

    def case(name, expected, change=None, required_id=None, witness=True):
        directory = output / name
        routing.prepare(directory, [6, 10, 90])
        if witness:
            for net, points in WITNESS.items():
                put(directory, net, points)
        if change:
            change(directory)
        result = routing.evaluate(directory, contract, directory / "evaluation")
        assert result["status"] == expected, (name, result)
        if required_id:
            assert any(f["id"].startswith(required_id) for f in result["findings"]), (
                name,
                result,
            )
        results.append({"case": name, "expected": expected, "actual": result["status"]})
        print(name, result["status"], flush=True)
        return directory, result

    for i in range(3):
        valid, observed = case(f"multi-segment-witness-{i + 1}", "pass")
    case("blank-same-net-labels", "fail", required_id="unrouted:", witness=False)
    case("missing-ground", "fail", lambda d: put(d, "gnd", []), "unrouted:")
    # Gap lies between pads, beyond both pad copper extents; net labels unchanged.
    case(
        "broken-native-cluster",
        "fail",
        lambda d: mutate(
            d / "candidate.kicad_pcb",
            "t=next(t for t in b.GetTracks() if t.GetNetname()=='gnd' and pcbnew.ToMM(t.GetStart().x)>7); t.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(8.1),pcbnew.FromMM(8.9)))",
        ),
        "unrouted:",
    )
    case(
        "wrong-net",
        "fail",
        lambda d: mutate(
            d / "candidate.kicad_pcb",
            "next(t for t in b.GetTracks() if t.GetNetname()=='gnd').SetNet(b.FindNet('sw'))",
        ),
        "unsupported_track:",
    )
    case(
        "wrong-admitted-net-not-auto-repaired",
        "fail",
        lambda d: put(d, "gnd", WITNESS["+15V"]),
        "extraneous_copper:",
    )
    case(
        "short-across-pads",
        "fail",
        lambda d: put(d, "+15V", [[6, 11.475], [6, 8.525], [8.8625, 10.95]]),
        "kicad:shorting_items:",
    )
    case(
        "clearance",
        "fail",
        lambda d: put(
            d, "+15V", [[6, 11.475], [7.7, 10.5], [8.8625, 10.5], [8.8625, 10.95]]
        ),
        "kicad:clearance:",
    )
    case(
        "wrong-layer",
        "fail",
        lambda d: mutate(
            d / "candidate.kicad_pcb", "next(iter(b.GetTracks())).SetLayer(pcbnew.B_Cu)"
        ),
        "unsupported_track:",
    )
    case(
        "wrong-width",
        "fail",
        lambda d: mutate(
            d / "candidate.kicad_pcb",
            "next(iter(b.GetTracks())).SetWidth(pcbnew.FromMM(0.3))",
        ),
        "unsupported_track:",
    )
    case(
        "via",
        "fail",
        lambda d: mutate(
            d / "candidate.kicad_pcb",
            "v=pcbnew.PCB_VIA(b); v.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(6),pcbnew.FromMM(11.475))); v.SetWidth(pcbnew.FromMM(.6)); v.SetDrill(pcbnew.FromMM(.3)); v.SetNet(b.FindNet('+15V')); b.Add(v)",
        ),
        "unsupported_track:",
    )
    case(
        "outside-copper",
        "fail",
        lambda d: put(d, "+15V", [[6, 11.475], [0, 13], [8.8625, 10.95]]),
        "copper_outside_outline:",
    )
    case(
        "unwanted-enable-pad",
        "fail",
        lambda d: put(
            d,
            "+15V",
            [[6, 11.475], [8.8625, 10.95], [9.9, 10.95], [9.9, 10], [11.1375, 10]],
        ),
        "unintended_connection:",
    )
    case(
        "moved-fixed-capacitor",
        "fail",
        lambda d: harness.native("place", d / "candidate.kicad_pcb", 5, 10, 90),
        "protected_state_changed",
    )
    case(
        "changed-pad-net",
        "fail",
        lambda d: mutate(
            d / "candidate.kicad_pcb",
            "next(p for p in f['U3'].Pads() if p.GetNumber()=='5').SetNet(b.FindNet('gnd'))",
        ),
        "protected_state_changed",
    )
    case(
        "changed-rules",
        "fail",
        lambda d: (d / "candidate.kicad_dru").write_text("(version 1)\n"),
        "protected_context_changed",
    )

    packet = {
        "measurement": observed["measurement"],
        "contract": contract,
        "drc": json.loads((valid / "evaluation/drc.json").read_text()),
    }
    for name, change in [
        ("missing-connectivity", lambda m: m.pop("routing")),
        ("partial-connectivity", lambda m: m["routing"]["connectivity"].pop()),
        (
            "asymmetric-connectivity",
            lambda m: m["routing"]["connectivity"][0]["pads"].pop(),
        ),
    ]:
        broken = copy.deepcopy(packet)
        change(broken["measurement"])
        process = subprocess.run(
            [str(harness.JUDGE)],
            input=json.dumps(broken),
            text=True,
            capture_output=True,
            check=False,
        )
        assert (
            process.returncode == 2
            and json.loads(process.stdout)["status"] == "indeterminate"
        ), name
        (output / f"{name}.json").write_text(
            json.dumps(
                {"input": broken, "result": json.loads(process.stdout)}, indent=2
            )
        )
        results.append({"case": name, "actual": "indeterminate"})

    directory = output / "operation-recovery"
    routing.prepare(directory, [6, 10, 90])
    session = routing.Session(directory, contract)
    assert session.call("inspect", {})["status"] == "fail"
    for net, points in WITNESS.items():
        result = session.call("route", {"net": net, "points_mm": points})
    assert result["status"] == "pass", result
    assert session.call("remove_route", {"net": "gnd"})["status"] == "fail"
    assert (
        session.call("route", {"net": "gnd", "points_mm": WITNESS["gnd"]})["status"]
        == "pass"
    )
    assert session.call("check", {})["status"] == "pass"
    assert session.edits == 4
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
                "tool": request["operation"],
                "arguments": request["arguments"],
                "result": {
                    "content": [
                        {"type": "text", "text": json.dumps(response["result"])}
                    ]
                },
            },
        }
        for request, response in zip(actions[1::2], actions[2::2])
    ]
    events.append({"type": "turn.completed"})
    checked = audit(
        directory, events, 30, 0, contract, edit_operations=("route", "remove_route")
    )
    assert checked["status"] == "pass" and checked["placement_edits"] == 4
    results.append({"case": "native-remove-replace-transcript-audit", "actual": "pass"})

    # Reject requests without touching the candidate; preflight forbids all edits.
    directory = output / "operation-boundaries"
    routing.prepare(directory, [6, 10, 90])
    session = routing.Session(directory, contract)
    before = harness.file_hash(session.board)
    for name, args in [
        ("place", {}),
        ("route", {"net": "sw", "points_mm": [[1, 1], [2, 2]]}),
        ("route", {"net": "gnd", "points_mm": [[True, 1], [2, 2]]}),
        ("route", {"net": "gnd", "points_mm": [[1, 1]]}),
    ]:
        assert session.call(name, args)["status"] == "indeterminate"
        assert harness.file_hash(session.board) == before
    session.edits = 10
    assert session.call("remove_route", {"net": "gnd"})["status"] == "indeterminate"
    session.deadline = 0
    assert session.call("check", {})["status"] == "indeterminate"
    session.log.close()
    directory = output / "inspection-boundary"
    routing.prepare(directory, [6, 10, 90])
    session = routing.InspectionSession(directory, contract)
    assert (
        session.call("route", {"net": "gnd", "points_mm": WITNESS["gnd"]})["status"]
        == "indeterminate"
    )
    assert session.edits == 0
    session.log.close()
    results.append(
        {"case": "routing-budgets-invalid-inputs-preflight", "actual": "pass"}
    )

    receipt = {
        "status": "qualified",
        "scope": "two_capacitor_routes",
        "contract_sha256": harness.file_hash(routing.CONTRACT),
        "cases": results,
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
    print(f"Qualified {len(results)} routing controls", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    qualify(parser.parse_args().output.resolve())
