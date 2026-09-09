"""Three-tool stdio MCP host; trusted files are never model-selected paths."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
KICAD_PYTHON = os.environ.get(
    "TEMPER_KICAD_PYTHON",
    "/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3.9",
)


def default_judge() -> Path:
    common = subprocess.check_output(
        [
            "git",
            "-C",
            str(ROOT),
            "rev-parse",
            "--path-format=absolute",
            "--git-common-dir",
        ],
        text=True,
    ).strip()
    return Path(common).parent / "target-shared/debug/temper-harness-e00"


JUDGE = (
    Path(os.environ["TEMPER_E00_JUDGE"])
    if "TEMPER_E00_JUDGE" in os.environ
    else default_judge()
)
EMPTY_SCHEMA = {"type": "object", "properties": {}, "additionalProperties": False}
TOOLS = [
    {
        "name": "inspect",
        "description": "Read exact saved footprint/pad coordinates in mm, constraints, and current findings. Board x increases right; y increases down.",
        "inputSchema": EMPTY_SCHEMA,
    },
    {
        "name": "place",
        "description": "Move C9's footprint origin to x_mm/y_mm and set its KiCad orientation. Only C9 moves. Returns reloaded state and introduced/resolved findings. Maximum ten edits.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "x_mm": {"type": "number"},
                "y_mm": {"type": "number"},
                "angle_deg": {"type": "integer", "enum": [0, 90, 180, 270]},
            },
            "required": ["x_mm", "y_mm", "angle_deg"],
            "additionalProperties": False,
        },
    },
    {
        "name": "check",
        "description": "Independently reload the saved candidate and run KiCad DRC plus the protected placement evaluator. Only a placement-only pass completes the task.",
        "inputSchema": EMPTY_SCHEMA,
    },
]


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def context_hash(path: Path) -> str:
    files = [
        path / "candidate.kicad_pro",
        path / "candidate.kicad_dru",
        path / "fp-lib-table",
    ]
    files.extend(sorted((path / "fixture.pretty").glob("*.kicad_mod")))
    return hashlib.sha256(
        json.dumps(
            [(p.relative_to(path).as_posix(), file_hash(p)) for p in files]
        ).encode()
    ).hexdigest()


def native(command: str, path: Path, *args: object) -> dict | None:
    result = subprocess.run(
        [KICAD_PYTHON, str(ROOT / "native.py"), command, str(path), *map(str, args)],
        capture_output=True,
        text=True,
        timeout=15,
        check=True,
    )
    return json.loads(result.stdout) if result.stdout.strip() else None


def evaluate(directory: Path, contract: dict, evidence: Path) -> dict:
    if context_hash(directory) != contract["context_sha256"]:
        return {"status": "fail", "findings": [{"id": "protected_context_changed"}]}
    evidence.mkdir(parents=True, exist_ok=False)
    board = directory / "candidate.kicad_pcb"
    measurement = native("measure", board)
    (evidence / "measurement.json").write_text(json.dumps(measurement, indent=2) + "\n")
    # Every evaluation gets a fresh output and explicit local library/config
    # context. A crash, timeout, or missing report can never reuse old evidence.
    config = evidence / "kicad-config"
    config.mkdir()
    (config / "kicad_common.json").write_text('{"environment":{"vars":{}}}\n')
    (config / "kicad_advanced").write_text("MaximumThreads=1\n")
    report_path = evidence / "drc.json"
    command = [
        "kicad-cli",
        "pcb",
        "drc",
        "--format",
        "json",
        "--all-track-errors",
        "--severity-all",
        "--output",
        str(report_path),
        str(board),
    ]
    completed = subprocess.run(
        command,
        env={**os.environ, "KICAD_CONFIG_HOME": str(config)},
        capture_output=True,
        text=True,
        timeout=30,
    )
    (evidence / "drc-command.json").write_text(
        json.dumps(
            {
                "argv": command,
                "returncode": completed.returncode,
                "stdout": completed.stdout,
                "stderr": completed.stderr,
            },
            indent=2,
        )
        + "\n"
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"KiCad DRC exited {completed.returncode}; see retained evidence"
        )
    drc = json.loads(report_path.read_text())
    if file_hash(board) != measurement["board_sha256"]:
        raise RuntimeError("Board changed during evaluation")
    completed = subprocess.run(
        [str(JUDGE)],
        input=json.dumps(
            {"measurement": measurement, "contract": contract, "drc": drc}
        ),
        capture_output=True,
        text=True,
        timeout=5,
    )
    result = json.loads(completed.stdout)
    if completed.returncode not in (0, 2):
        raise RuntimeError(f"Evaluator exited {completed.returncode}")
    (evidence / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    return {**result, "measurement": measurement}


def prepare(directory: Path, start: list) -> None:
    shutil.copytree(ROOT / "fixtures/e00", directory)
    native("place", directory / "candidate.kicad_pcb", *start)
    shutil.copyfile(directory / "candidate.kicad_pcb", directory / "initial.kicad_pcb")


class Session:
    def __init__(self, directory: Path, contract: dict, deadline: float | None = None):
        self.directory = directory.resolve()
        self.contract = contract
        self.started = time.monotonic()
        self.deadline = deadline if deadline is not None else time.time() + 300
        self.edits = 0
        self.sequence = 0
        self.previous_findings: set[str] = set()
        self.board = self.directory / "candidate.kicad_pcb"
        self.last_hash = file_hash(self.board)
        # Exclusive creation forbids silent continuation/reset of trial budgets.
        self.log = (self.directory / "actions.jsonl").open("x")
        self.append(
            {
                "kind": "session",
                "contract": contract,
                "tools": TOOLS,
                "initial_sha256": self.last_hash,
                "deadline_unix": self.deadline,
            }
        )

    def append(self, event: dict) -> None:
        self.log.write(json.dumps(event, allow_nan=False) + "\n")
        self.log.flush()
        os.fsync(self.log.fileno())

    def call(self, name: str, arguments: dict) -> dict:
        self.sequence += 1
        before = file_hash(self.board)
        self.append(
            {
                "kind": "request",
                "sequence": self.sequence,
                "operation": name,
                "arguments": arguments,
                "before_sha256": before,
                "elapsed_s": time.monotonic() - self.started,
            }
        )
        try:
            if time.time() >= self.deadline:
                raise ValueError("Five-minute trial budget expired")
            if before != self.last_hash:
                raise ValueError("Candidate changed outside the operation interface")
            if context_hash(self.directory) != self.contract["context_sha256"]:
                raise ValueError("Protected context changed")
            if name == "place":
                if set(arguments) != {"x_mm", "y_mm", "angle_deg"}:
                    raise ValueError("place requires exactly x_mm, y_mm, angle_deg")
                x, y, angle = (arguments[k] for k in ("x_mm", "y_mm", "angle_deg"))
                if any(
                    type(v) not in (int, float) or not math.isfinite(v) for v in (x, y)
                ):
                    raise ValueError("Coordinates must be finite numbers")
                if type(angle) is not int or angle not in (0, 90, 180, 270):
                    raise ValueError("Orientation must be 0, 90, 180, or 270")
                if not (1 <= x <= 29 and 1 <= y <= 19):
                    raise ValueError("Footprint origin must be inside the task outline")
                if self.edits >= 10:
                    raise ValueError("Ten-placement budget exhausted")
                self.edits += 1
                staging = self.directory / "next.kicad_pcb"
                shutil.copyfile(self.board, staging)
                native("place", staging, x, y, angle)
                os.replace(staging, self.board)
                self.last_hash = file_hash(self.board)
            elif name not in ("inspect", "check") or arguments:
                raise ValueError("Unknown operation or unexpected arguments")
            result = evaluate(
                self.directory,
                self.contract,
                self.directory / "evidence" / f"{self.sequence:03}",
            )
            current = {f["id"] for f in result.get("findings", [])}
            result["introduced"] = sorted(current - self.previous_findings)
            result["resolved"] = sorted(self.previous_findings - current)
            self.previous_findings = current
            result["requirements"] = {
                "editable": "C9 position and orientation only",
                "outline_mm": self.contract["outline_mm"],
                "minimum_copper_clearance_mm": 0.2,
                "maximum_mapped_pad_distance_mm": self.contract["max_pad_distance_mm"],
                "mapped_pairs": ["C9.1 (+15V) -> U3.3", "C9.2 (gnd) -> U3.1"],
                "no_courtyard_overlap": True,
                "remaining_placement_edits": 10 - self.edits,
            }
            if time.time() >= self.deadline:
                result["status"] = "fail"
                result["budget_expired"] = True
        except Exception as error:
            result = {
                "status": "indeterminate",
                "error": f"{type(error).__name__}: {error}",
            }
        result["sequence"] = self.sequence
        result["after_sha256"] = file_hash(self.board)
        result["elapsed_s"] = time.monotonic() - self.started
        shutil.copyfile(
            self.board, self.directory / f"state-{self.sequence:03}.kicad_pcb"
        )
        self.append({"kind": "response", "sequence": self.sequence, "result": result})
        return result


def serve(session: Session) -> None:
    for line in sys.stdin:
        request = json.loads(line)
        if "id" not in request:
            continue
        method = request["method"]
        if method == "initialize":
            result = {
                "protocolVersion": "2025-11-25",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "temper-e00", "version": "0.1.0"},
            }
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call":
            params = request["params"]
            response = session.call(params["name"], params.get("arguments", {}))
            result = {
                "content": [{"type": "text", "text": json.dumps(response)}],
                "isError": response["status"] == "indeterminate",
            }
        elif method == "ping":
            result = {}
        else:
            print(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": request["id"],
                        "error": {"code": -32601, "message": "Method not found"},
                    }
                ),
                flush=True,
            )
            continue
        print(
            json.dumps({"jsonrpc": "2.0", "id": request["id"], "result": result}),
            flush=True,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("--deadline", type=float)
    args = parser.parse_args()
    contract = json.loads((ROOT / "fixtures/contract.json").read_text())
    serve(Session(args.directory, contract, args.deadline))
