"""Run the frozen three-start experiment through fresh, restricted Codex sessions."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import harness

INSTRUCTIONS = """You operate a small PCB placement experiment through the provided PCB tools.
Use inspect to learn the actual geometry and requirements, place to change the permitted
footprint, and check to verify the saved candidate. Choose coordinates yourself from tool
evidence. Do not claim success without a successful final check. Stop on an indeterminate
measurement and report it. You have five minutes and at most ten placement edits.
Only the PCB task tools are admitted. No filesystem, shell, web, other agents, or external
applications are part of this task. Provide a short factual final result.
"""
PROMPT = "Place C9 so the two-footprint fixture meets all of its placement requirements. Begin by inspecting the board."
PREFLIGHT_PROMPT = "Runtime preflight only: call PCB inspect once, do not place anything, then list the tool names available to you."


def configuration(private: Path, workspace: Path, deadline: float) -> list[str]:
    instructions = private / "instructions.txt"
    instructions.write_text(INSTRUCTIONS)
    disabled_skills = []
    for root in (Path.home() / ".agents/skills", Path.home() / ".codex/skills"):
        for skill in sorted(root.rglob("SKILL.md")):
            disabled_skills.append(
                "{path=" + json.dumps(str(skill.parent)) + ",enabled=false}"
            )
    values = [
        'approval_policy="never"',
        'web_search="disabled"',
        "project_doc_max_bytes=0",
        "tools.view_image=false",
        "features.shell_tool=false",
        "features.unified_exec=false",
        "features.apps=false",
        "features.plugins=false",
        "features.remote_plugin=false",
        "features.image_generation=false",
        "features.in_app_browser=false",
        "features.multi_agent=false",
        "features.memories=false",
        "features.tool_suggest=false",
        "features.shell_snapshot=false",
        "skills.config=[" + ",".join(disabled_skills) + "]",
        "model_instructions_file=" + json.dumps(str(instructions)),
        "mcp_servers.pcb="
        + "{command="
        + json.dumps(sys.executable)
        + ",args="
        + json.dumps(
            [
                str(harness.ROOT / "harness.py"),
                str(workspace),
                "--deadline",
                str(deadline),
            ]
        )
        + ',enabled_tools=["inspect","place","check"],startup_timeout_sec=20,tool_timeout_sec=60}',
    ]
    return [item for value in values for item in ("-c", value)]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def audit(
    directory: Path,
    model_events: list[dict],
    elapsed: float,
    returncode: int,
    contract: dict,
) -> dict:
    events = [
        json.loads(line)
        for line in (directory / "actions.jsonl").read_text().splitlines()
    ]
    require(
        events[0]["initial_sha256"]
        == harness.file_hash(directory / "initial.kicad_pcb"),
        'Trial evidence invariant failed: events[0]["initial_sha256"] == harness.file_hash(         directory / "initial.kicad_pcb"     )',
    )
    require(
        events[0]["contract"] == contract,
        'Trial evidence invariant failed: events[0]["contract"] == contract',
    )
    requests, responses = events[1::2], events[2::2]
    require(
        len(requests) == len(responses) and requests,
        "Trial evidence invariant failed: len(requests) == len(responses) and requests",
    )
    previous_hash = events[0]["initial_sha256"]
    for sequence, (request, response) in enumerate(zip(requests, responses), 1):
        require(
            request["kind"] == "request" and response["kind"] == "response",
            'Trial evidence invariant failed: request["kind"] == "request" and response["kind"] == "response"',
        )
        require(
            request["sequence"] == response["sequence"] == sequence,
            'Trial evidence invariant failed: request["sequence"] == response["sequence"] == sequence',
        )
        require(
            request["before_sha256"] == previous_hash,
            'Trial evidence invariant failed: request["before_sha256"] == previous_hash',
        )
        previous_hash = response["result"]["after_sha256"]
        require(
            previous_hash
            == harness.file_hash(directory / f"state-{sequence:03}.kicad_pcb"),
            'Trial evidence invariant failed: previous_hash == harness.file_hash(             directory / f"state-{sequence:03}.kicad_pcb"         )',
        )
    require(
        previous_hash == harness.file_hash(directory / "candidate.kicad_pcb"),
        'Trial evidence invariant failed: previous_hash == harness.file_hash(directory / "candidate.kicad_pcb")',
    )
    require(
        harness.context_hash(directory) == contract["context_sha256"],
        'Trial evidence invariant failed: harness.context_hash(directory) == contract["context_sha256"]',
    )
    completed = [e["item"] for e in model_events if e.get("type") == "item.completed"]
    tool_calls = [item for item in completed if item.get("type") == "mcp_tool_call"]
    require(len(tool_calls) == len(requests), "model transcript and tool log disagree")
    for item, request, response in zip(tool_calls, requests, responses):
        require(
            item["server"] == "pcb" and item["tool"] == request["operation"],
            'Trial evidence invariant failed: item["server"] == "pcb" and item["tool"] == request["operation"]',
        )
        require(
            item["arguments"] == request["arguments"],
            'Trial evidence invariant failed: item["arguments"] == request["arguments"]',
        )
        content = item["result"]["content"]
        shown = json.loads(next(c["text"] for c in content if c["type"] == "text"))
        require(shown == response["result"], "model was shown a different response")
    allowed_items = {"agent_message", "reasoning", "mcp_tool_call"}
    unexpected = [
        item.get("type") for item in completed if item.get("type") not in allowed_items
    ]
    last = responses[-1]["result"]
    edits = sum(r["operation"] == "place" for r in requests)
    terminal = any(e.get("type") == "turn.completed" for e in model_events)
    passed = (
        returncode == 0
        and terminal
        and not unexpected
        and elapsed <= 300
        and edits <= 10
        and requests[-1]["operation"] == "check"
        and last["status"] == "pass"
        and all(r["result"]["status"] != "indeterminate" for r in responses)
    )
    return {
        "status": "pass" if passed else "fail",
        "elapsed_s": elapsed,
        "placement_edits": edits,
        "returncode": returncode,
        "unexpected_tools": unexpected,
        "log_matches_model_transcript": True,
        "final_board_sha256": previous_hash,
        "final_check": last,
        "usage": [
            e.get("usage") for e in model_events if e.get("type") == "turn.completed"
        ],
        "cost_usd": None,
        "cost_note": "Codex subscription run; no monetary cost receipt exposed",
    }


def run(output: Path, qualification: Path, preflight: bool) -> None:
    contract = json.loads((harness.ROOT / "fixtures/contract.json").read_text())
    receipt = json.loads(qualification.read_text())
    require(
        receipt["status"] == "qualified",
        'Trial evidence invariant failed: receipt["status"] == "qualified"',
    )
    require(
        receipt["contract_sha256"]
        == harness.file_hash(harness.ROOT / "fixtures/contract.json"),
        'Trial evidence invariant failed: receipt["contract_sha256"] == harness.file_hash(         harness.ROOT / "fixtures/contract.json"     )',
    )
    for name, digest in receipt["source_sha256"].items():
        require(
            harness.file_hash(harness.ROOT / name) == digest,
            f"Requalify changed source: {name}",
        )
    require(
        harness.file_hash(harness.JUDGE) == receipt["evaluator_sha256"],
        "Requalify changed evaluator binary",
    )
    output.mkdir(parents=True, exist_ok=False)
    manifest = {
        "contract": contract,
        "qualification_sha256": harness.file_hash(qualification),
        "codex_version": subprocess.check_output(
            ["codex", "--version"], text=True
        ).strip(),
        "requested_model": "Codex CLI default (user config excluded)",
        "served_model": None,
        "instructions": INSTRUCTIONS,
        "prompt": PREFLIGHT_PROMPT if preflight else PROMPT,
        "preflight": preflight,
        "source_sha256": {
            name: harness.file_hash(harness.ROOT / name)
            for name in (
                "harness.py",
                "native.py",
                "run_trials.py",
                "src/main.rs",
                "Cargo.lock",
            )
        },
        "evaluator_sha256": harness.file_hash(harness.JUDGE),
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    results = []
    for index, start in enumerate(
        contract["starts"][:1] if preflight else contract["starts"], 1
    ):
        directory = output / f"trial-{index}"
        harness.prepare(directory, start)
        # A fresh empty directory outside the repository prevents repository
        # discovery. The model has no candidate file paths; MCP owns the board.
        with tempfile.TemporaryDirectory(prefix="temper-e00-agent-") as tmp:
            private = Path(tmp)
            empty = private / "workspace"
            empty.mkdir()
            deadline = time.time() + 300
            command = [
                "codex",
                "exec",
                "--ignore-user-config",
                "--strict-config",
                "--ephemeral",
                "--skip-git-repo-check",
                "--sandbox",
                "read-only",
                "--json",
                "--cd",
                str(empty),
                *configuration(private, directory, deadline),
                manifest["prompt"],
            ]
            (directory / "invocation.json").write_text(
                json.dumps(command, indent=2) + "\n"
            )
            started = time.monotonic()
            with (
                (directory / "model.jsonl").open("w") as out,
                (directory / "model.stderr").open("w") as err,
            ):
                process = subprocess.Popen(
                    command, stdout=out, stderr=err, start_new_session=True
                )
                try:
                    returncode = process.wait(timeout=300)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait()
                    returncode = 124
            elapsed = time.monotonic() - started
        model_events = [
            json.loads(line)
            for line in (directory / "model.jsonl").read_text().splitlines()
            if line.strip()
        ]
        if preflight:
            result = {
                "returncode": returncode,
                "elapsed_s": elapsed,
                "preflight_only": True,
            }
        else:
            try:
                result = audit(directory, model_events, elapsed, returncode, contract)
                verification = harness.evaluate(
                    directory, contract, directory / "host-final-check"
                )
                if verification["status"] != "pass":
                    result["status"] = "fail"
                result["independent_host_check"] = verification
            except Exception as error:
                result = {
                    "status": "indeterminate",
                    "error": f"{type(error).__name__}: {error}",
                    "returncode": returncode,
                    "elapsed_s": elapsed,
                }
        shutil.copyfile(
            directory / "candidate.kicad_pcb", directory / "final.kicad_pcb"
        )
        (directory / "result.json").write_text(json.dumps(result, indent=2) + "\n")
        results.append(result)
        print(
            json.dumps(
                {
                    "trial": index,
                    "status": result.get("status", "preflight"),
                    "elapsed_s": elapsed,
                    "placement_edits": result.get("placement_edits"),
                }
            ),
            flush=True,
        )
    (output / "results.json").write_text(
        json.dumps(
            {
                "status": "preflight"
                if preflight
                else (
                    "pass" if all(r["status"] == "pass" for r in results) else "fail"
                ),
                "trials": results,
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--qualification", type=Path, required=True)
    parser.add_argument("--preflight", action="store_true")
    args = parser.parse_args()
    run(args.output.resolve(), args.qualification.resolve(), args.preflight)
