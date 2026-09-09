"""Qualify seeded repair starts against native evidence and the real tool ledger."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import harness
import routing_host as routing
from run_trials import audit

FIXTURE = "e00r-repair"
DETOUR = [[6, 11.475], [6, 12.5], [8.8625, 12.5], [8.8625, 10.95]]
GROUND = [[6, 8.525], [7.5, 8.525], [8.8625, 9.05]]


def qualify(output: Path) -> None:
    if not __debug__:
        raise RuntimeError("Qualification requires assertions")
    output.mkdir(parents=True, exist_ok=False)
    contract_path = routing.CONTRACTS[FIXTURE]
    contract = json.loads(contract_path.read_text())
    cases = []
    for start in contract["starts"]:
        directory = output / start
        routing.prepare(directory, start, fixture=FIXTURE)
        session = routing.Session(directory, contract)
        first = session.call("inspect", {})
        assert first["status"] == "fail", first
        assert first["measurement"]["protected_sha256"] == contract["protected_sha256"]
        assert not any(f["id"].startswith("protected_") for f in first["findings"])
        prefix = contract["repair_cases"][start]["required_finding_prefix"]
        defects = {f["id"] for f in first["findings"] if f["id"].startswith(prefix)}
        assert defects, first
        net, points = ("gnd", GROUND) if start == "c" else ("+15V", DETOUR)
        repaired = session.call("route", {"net": net, "points_mm": points})
        assert repaired["status"] == "pass", repaired
        assert defects <= set(repaired["resolved"])
        assert session.call("check", {})["status"] == "pass"
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
            directory,
            events,
            30,
            0,
            contract,
            edit_operations=("route", "remove_route"),
        )
        assert checked["status"] == "pass" and checked["placement_edits"] == 1
        repair = routing.audit_repair(directory, start, contract)
        final = routing.evaluate(directory, contract, directory / "host-final-check")
        assert final["status"] == "pass", final
        cases.append(
            {
                "start": start,
                "initial_status": first["status"],
                "initial_findings": [f["id"] for f in first["findings"]],
                "repair_audit": repair,
                "final_status": final["status"],
                "scripted_edits": 1,
            }
        )
        print(
            start,
            "initial defect observed; scripted repair and full action audit pass",
            flush=True,
        )
    receipt = {
        "status": "qualified",
        "scope": "three_seeded_copper_repairs",
        "cases": cases,
        "contract_sha256": harness.file_hash(contract_path),
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    qualify(parser.parse_args().output.resolve())
