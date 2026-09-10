"""Trusted host for the complete nine-component buck operation contract.

Rust owns the public schema and all request policy.  This module owns only
the trusted fixture directory, atomic file replacement, and native KiCad
calls.  A native action is committed only after independent refill, reload,
measurement, and Rust/DRC checks; ordinary DRC ``fail`` feedback remains
committable while apparatus failures do not.
"""

from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

import harness
import qualify_buck

ROOT = Path(__file__).resolve().parent
_POLICY_PROFILE = "buck-operation"


def _rust_schema() -> dict[str, Any]:
    result = subprocess.run(
        [str(harness.JUDGE)],
        input=json.dumps({"profile": _POLICY_PROFILE, "operation": "schema", "arguments": {}}),
        text=True,
        capture_output=True,
        timeout=5,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Rust operation schema unavailable")
    schema = json.loads(result.stdout)
    if not isinstance(schema, dict) or not isinstance(schema.get("tools"), list):
        raise RuntimeError("Rust operation schema is malformed")
    return schema


# Discovering this at import keeps tool descriptions and nested schemas tied
# to the Rust policy.  Build the standalone judge before importing the host.
_SCHEMA = _rust_schema()
TOOLS = _SCHEMA["tools"]
MAX_ACTIONS = int(_SCHEMA["max_actions"])
MAX_SECONDS = float(_SCHEMA["max_seconds"])
MAX_OBJECTS = int(_SCHEMA["max_objects"])
MAX_EXECUTE_BYTES = int(_SCHEMA["max_execute_bytes"])


def prepare(directory: Path, variant: str) -> None:
    qualify_buck.prepare(directory, variant)


def _safe_json(value: Any) -> Any:
    """Make malformed requests recordable without allowing NaN JSON."""
    if isinstance(value, float) and not math.isfinite(value):
        return {"invalid_number_repr": repr(value)}
    if isinstance(value, float):
        return value
    if isinstance(value, dict):
        return {str(key): _safe_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe_json(item) for item in value]
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    return {"invalid_value_repr": repr(value)}


class Session:
    tools = TOOLS

    def __init__(
        self,
        directory: Path,
        variant: str | dict[str, Any],
        maybe_variant: str | None = None,
        *,
        deadline: float | None = None,
    ) -> None:
        self.directory = directory.resolve()
        # Preserve the historical Session(directory, contract, variant)
        # spelling while the operation contract remains self-contained.
        if isinstance(variant, dict):
            if maybe_variant is None:
                raise ValueError("variant is required")
            variant = maybe_variant
        self.variant = variant
        contract = json.loads(qualify_buck.CONTRACT.read_text())
        self.contract = qualify_buck.variant_contract(contract, variant)
        self.context_sha256 = qualify_buck.variant_spec(contract, variant)["context_sha256"]
        self.board = self.directory / "candidate.kicad_pcb"
        self._require_fixture_context()
        self.started = time.monotonic()
        now = time.monotonic()
        self.deadline = (
            min(deadline, now + MAX_SECONDS) if deadline is not None else now + MAX_SECONDS
        )
        self.actions = 0
        self.sequence = 0
        self.terminal_error: str | None = None
        self.revision = harness.file_hash(self.board)
        self.log = (self.directory / "operations.jsonl").open("x")
        self._record(
            {
                "kind": "session",
                "variant": variant,
                "revision": self.revision,
                "deadline": self.deadline,
                "tools": TOOLS,
            }
        )

    def _require_fixture_context(self) -> None:
        required = (
            "source.json",
            "candidate.kicad_pro",
            "candidate.kicad_dru",
            "fp-lib-table",
        )
        missing = [name for name in required if not (self.directory / name).is_file()]
        if not self.board.is_file() or missing:
            raise ValueError(
                f"incomplete buck fixture context: missing {missing or ['candidate.kicad_pcb']}"
            )
        if harness.context_hash(self.directory) != self.context_sha256:
            raise ValueError("protected fixture context changed")

    def _record(self, event: dict[str, Any]) -> None:
        self.log.write(json.dumps(_safe_json(event), allow_nan=False) + "\n")
        self.log.flush()
        os.fsync(self.log.fileno())

    def _budget(self) -> None:
        if time.monotonic() >= self.deadline:
            raise TimeoutError("absolute buck attempt deadline expired")
        if self.actions >= MAX_ACTIONS:
            raise ValueError(f"{MAX_ACTIONS}-action mutation budget exhausted")

    def _deadline(self) -> None:
        if time.monotonic() >= self.deadline:
            raise TimeoutError("absolute buck attempt deadline expired")

    def _rust_policy(self, operation: str, args: Any) -> dict[str, Any]:
        payload = {
            "profile": _POLICY_PROFILE,
            "operation": operation,
            "arguments": args,
            "context": {"outline_mm": self.contract["outline_mm"]},
        }
        try:
            result = subprocess.run(
                [str(harness.JUDGE)],
                input=json.dumps(payload, allow_nan=False),
                text=True,
                capture_output=True,
                timeout=self._remaining_timeout(5.0),
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise RuntimeError(f"Rust policy apparatus failed: {error}") from error
        try:
            response = json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise RuntimeError("Rust policy returned malformed JSON") from error
        if result.returncode != 0 or response.get("status") != "pass":
            raise ValueError(response.get("error", "Rust policy rejected request"))
        return response

    def _snapshot(self, sequence: int) -> None:
        shutil.copyfile(self.board, self.directory / f"state-{sequence:06d}.kicad_pcb")

    def _remaining_timeout(self, maximum: float) -> float:
        remaining = self.deadline - time.monotonic()
        active_cell_deadline = getattr(self, "_active_cell_deadline", None)
        if active_cell_deadline is not None:
            remaining = min(remaining, active_cell_deadline - time.monotonic())
        if remaining <= 0:
            raise TimeoutError("absolute buck attempt deadline expired")
        return min(maximum, remaining)

    def _native(self, command: str, path: Path, *args: object) -> dict[str, Any] | None:
        argv = [
            harness.KICAD_PYTHON,
            str(qualify_buck.ADAPTER),
            command,
            str(path),
            *map(str, args),
        ]
        try:
            result = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=self._remaining_timeout(15.0),
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise RuntimeError(f"native {command} apparatus failed: {error}") from error
        if result.returncode != 0:
            raise RuntimeError(
                f"native {command} exited {result.returncode}: {result.stderr.strip()}"
            )
        if not result.stdout.strip():
            return None
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise RuntimeError(f"native {command} returned malformed JSON") from error

    def _copy_context(self, destination: Path, board: bytes) -> None:
        destination.mkdir(parents=True, exist_ok=False)
        for name in (
            "source.json",
            "candidate.kicad_pro",
            "candidate.kicad_dru",
            "fp-lib-table",
        ):
            shutil.copyfile(self.directory / name, destination / name)
        fixture_lib = self.directory / "fixture.pretty"
        if fixture_lib.is_dir():
            shutil.copytree(fixture_lib, destination / "fixture.pretty")
        (destination / "candidate.kicad_pcb").write_bytes(board)
        if harness.context_hash(destination) != self.context_sha256:
            raise RuntimeError("staged fixture context hash mismatch")

    def _native_drc(self, stage: Path, *, refill: bool) -> dict[str, Any]:
        evidence = stage / "native-check"
        evidence.mkdir()
        config = evidence / "kicad-config"
        config.mkdir()
        (config / "kicad_common.json").write_text('{"environment":{"vars":{}}}\n')
        (config / "kicad_advanced").write_text("MaximumThreads=1\n")
        report = evidence / "drc.json"
        board = stage / "candidate.kicad_pcb"
        command = [
            "kicad-cli",
            "pcb",
            "drc",
            "--format",
            "json",
            "--all-track-errors",
            "--severity-all",
            *(["--refill-zones", "--save-board"] if refill else []),
            "--output",
            str(report),
            str(board),
        ]
        try:
            completed = subprocess.run(
                command,
                env={**os.environ, "KICAD_CONFIG_HOME": str(config)},
                capture_output=True,
                text=True,
                timeout=self._remaining_timeout(30.0),
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise RuntimeError(f"KiCad DRC apparatus failed: {error}") from error
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
        if completed.returncode != 0 or not report.is_file():
            raise RuntimeError(f"KiCad DRC exited {completed.returncode}")
        try:
            return json.loads(report.read_text())
        except json.JSONDecodeError as error:
            raise RuntimeError("KiCad DRC returned malformed JSON") from error

    def _rust_check(self, stage: Path, drc: dict[str, Any]) -> dict[str, Any]:
        measurement = self._native("measure", stage / "candidate.kicad_pcb")
        if (
            not isinstance(measurement, dict)
            or measurement.get("protected_sha256") != self.contract["protected_sha256"]
        ):
            raise RuntimeError("native reload changed protected state")
        payload = {"measurement": measurement, "contract": self.contract, "drc": drc}
        try:
            completed = subprocess.run(
                [str(harness.JUDGE)],
                input=json.dumps(payload, allow_nan=False),
                capture_output=True,
                text=True,
                timeout=self._remaining_timeout(5.0),
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise RuntimeError(f"Rust check apparatus failed: {error}") from error
        try:
            result = json.loads(completed.stdout)
        except json.JSONDecodeError as error:
            raise RuntimeError("Rust check returned malformed JSON") from error
        if result.get("status") == "indeterminate" or completed.returncode not in (
            0,
            2,
        ):
            raise RuntimeError(result.get("error", "Rust check indeterminate"))
        (stage / "native-check" / "result.json").write_text(json.dumps(result, indent=2) + "\n")
        return {
            "status": result.get("status"),
            "measurement": measurement,
            "drc": drc,
            "rust": result,
        }

    def _check_stage(self, stage: Path, *, refill: bool = True) -> dict[str, Any]:
        return self._rust_check(stage, self._native_drc(stage, refill=refill))

    def _native_action(self, operation: str, args: dict[str, Any]) -> dict[str, Any]:
        stage = self.directory / f"attempt-{self.sequence:06d}"
        self._copy_context(stage, self.board.read_bytes())
        board = stage / "candidate.kicad_pcb"
        if operation == "place":
            self._native(
                "place",
                board,
                args["reference"],
                args["x_mm"],
                args["y_mm"],
                args["angle_deg"],
            )
        elif operation == "replace_copper":
            self._native(
                "replace_copper",
                board,
                args["net"],
                json.dumps(args["segments"]),
                json.dumps(args["vias"]),
                json.dumps(args["zones"]),
            )
        else:
            raise ValueError(f"{operation} is not a mutating operation")
        native_result = self._check_stage(stage)
        if native_result["status"] not in ("pass", "fail"):
            raise RuntimeError("native check did not produce a terminal result")
        self._deadline()
        os.replace(board, self.board)
        self.actions += 1
        self.revision = harness.file_hash(self.board)
        native_result.update(
            {
                "operation": operation,
                "mutation_committed": True,
                "mutation_index": self.actions,
                "native_verdict": native_result["status"],
                "board_sha256": self.revision,
                "revision": self.revision,
                "remaining_actions": MAX_ACTIONS - self.actions,
            }
        )
        return native_result

    def _independent_measure(self) -> dict[str, Any]:
        measurement = self._native("measure", self.board)
        if (
            not isinstance(measurement, dict)
            or measurement.get("protected_sha256") != self.contract["protected_sha256"]
        ):
            raise RuntimeError("native reload changed protected state")
        return measurement

    def call(self, operation: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
        args = {} if args is None else args
        self.sequence += 1
        sequence = self.sequence
        before = self.revision
        before_actions = self.actions
        self._record(
            {
                "kind": "request",
                "sequence": sequence,
                "operation": operation,
                "arguments": args,
                "before_sha256": before,
                "elapsed_s": time.monotonic() - self.started,
            }
        )
        try:
            if self.terminal_error is not None:
                raise RuntimeError(
                    f"session is terminal after indeterminate native failure: {self.terminal_error}"
                )
            if harness.context_hash(self.directory) != self.context_sha256:
                raise ValueError("protected fixture context changed")
            if harness.file_hash(self.board) != self.revision:
                raise ValueError("stale request: board revision changed outside this session")
            self._rust_policy(operation, args)
            self._deadline()
            if operation in ("place", "replace_copper"):
                self._budget()
                result = self._native_action(operation, args)
            elif operation == "inspect":
                result = {
                    "status": "pass",
                    "operation": operation,
                    "mutation_committed": False,
                    "native_verdict": None,
                    "measurement": self._independent_measure(),
                }
            elif operation == "check":
                stage = self.directory / f"check-{sequence:06d}"
                self._copy_context(stage, self.board.read_bytes())
                result = self._check_stage(stage, refill=False)
                if result["measurement"]["board_sha256"] != self.revision:
                    raise RuntimeError("read-only check changed the measured board")
                result.update(
                    {
                        "operation": operation,
                        "mutation_committed": False,
                        "native_verdict": result["status"],
                    }
                )
            else:  # execute is rejected by Rust policy before reaching here.
                raise ValueError(f"unsupported operation {operation}")
            self._deadline()
            result.update(
                {
                    "revision": self.revision,
                    "remaining_actions": MAX_ACTIONS - self.actions,
                }
            )
        except (
            TimeoutError,
            OSError,
            RuntimeError,
            subprocess.SubprocessError,
        ) as error:
            if isinstance(error, (RuntimeError, OSError, subprocess.SubprocessError, TimeoutError)):
                self.terminal_error = str(error)
            result = {
                "status": "indeterminate",
                "error": f"{type(error).__name__}: {error}",
                "mutation_committed": self.actions > before_actions,
                "native_verdict": "indeterminate",
                "board_sha256": self.revision,
                "revision": self.revision,
                "remaining_actions": MAX_ACTIONS - self.actions,
            }
            self._record(
                {
                    "kind": "indeterminate",
                    "sequence": sequence,
                    "operation": operation,
                    "arguments": args,
                    "before_sha256": before,
                    "after_sha256": self.revision,
                    "actions": self.actions,
                    "error": str(error),
                }
            )
        except Exception as error:
            result = {
                "status": "invalid",
                "error": f"{type(error).__name__}: {error}",
                "mutation_committed": False,
                "native_verdict": "invalid",
                "board_sha256": self.revision,
                "revision": self.revision,
                "remaining_actions": MAX_ACTIONS - self.actions,
            }
            self._record(
                {
                    "kind": "rejection",
                    "sequence": sequence,
                    "operation": operation,
                    "arguments": args,
                    "before_sha256": before,
                    "after_sha256": self.revision,
                    "actions": self.actions,
                    "error": str(error),
                }
            )
        finally:
            # Every attempt has an immutable board snapshot, including malformed
            # requests and failed independent checks.
            self._snapshot(sequence)
            result["sequence"] = sequence
            result["after_sha256"] = self.revision
            result["elapsed_s"] = time.monotonic() - self.started
            self._record(
                {
                    "kind": "response",
                    "sequence": sequence,
                    "operation": operation,
                    "arguments": args,
                    "before_sha256": before,
                    "after_sha256": self.revision,
                    "actions": self.actions,
                    "deadline": self.deadline,
                    "status": result.get("status", "indeterminate"),
                    "result": result,
                }
            )
        return result

    def close(self) -> None:
        self.log.close()
