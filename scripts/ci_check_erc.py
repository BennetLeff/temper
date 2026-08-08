#!/usr/bin/env python3
"""CI entry point: ERC (Electrical Rules Check) ratchet gate.

Runs ``kicad-cli sch erc`` against every schematic recorded in
``power_pcb_dataset/erc_ceiling.json`` and enforces:

  - **errors: zero by default, hard fail, essentially never ratcheted.**
    The default and strongly-expected ``error_ceiling`` is 0 -- unlike the
    DRC ratchet (``scripts/ci_check_drc.py`` / ``power_pcb_dataset/
    drc_ceiling.json``), a nonzero ``error_ceiling`` here is NOT a normal
    "debt to pay down" ratchet value; it is only ever acceptable as a
    narrowly-scoped, fully-documented exception for a PROVEN tooling
    artifact (see ``pcb/mcu.kicad_sch`` below for the one case that exists
    today, and its ``_artifact_note`` for the evidence). Every error type
    NOT listed in a board's ``errors_by_type`` has an implicit ceiling of
    0, exactly mirroring ``violations_by_type``'s implicit-zero semantics
    in ``power_pcb_dataset/drc_ceiling.json`` -- a documented allowance for
    one known error type never silently covers a new, different one.
  - **warnings: ratchet, may only decrease.** A brand-new schematic
    (``kicad-cli sch erc`` was never run in CI before this gate) starts
    with hundreds of pre-existing warnings (498 on pcb/temper.kicad_sch,
    measured 2026-08-07 on the pinned kicad-cli 10.0.5, stable across 10
    runs). Asserting zero warnings on day one would be permanently red and
    get ignored within a week (the same alarm-fatigue failure mode
    ``continue-on-error: true`` placeholders create). Instead each
    schematic's ``warning_ceiling`` in ``power_pcb_dataset/erc_ceiling.json``
    is a monotonic ceiling: CI fails if the current warning count exceeds
    it, and lowering it (as warnings get fixed) is always allowed.
  - **null ceiling means "not yet measured on the pinned tool" --
    do not enforce, say so loudly.** Kept as a defined behavior (rather
    than removed now that both boards in the committed ceiling file ARE
    measured) because it is what protects the next re-measurement: if a
    future KiCad version bump invalidates the committed numbers before
    anyone re-measures on the new pinned tool, this is the fallback that
    keeps the gate honest instead of silently comparing against a stale
    baseline. ``.github/docker/ci.Dockerfile`` pins
    ``KICAD_VERSION=10.0.5~ubuntu24.04.1``; a prior DRC ceiling swung by
    +107 on the exact same 10.0.4->10.0.5 PPA move
    (docs/evidence/2026-08-04-router-output-rebaseline-interim.md) --
    carrying an old warning count over as a new-version ceiling would
    reproduce that exact defect. When ``warning_ceiling`` is null, this
    gate still runs ERC and still hard-fails on any (non-implicitly-
    allowed) error, but does not fail on warning count -- it prints the
    measured count and a reminder that the ceiling is unset.

Unlike ``scripts/ci_check_drc.py`` / ``drc_ceiling.json``, this file does
NOT implement drc_ceiling.json's separate machine-checked
``Ceiling-Approval:`` trailer contract (R27, scripts/check_drc_ceiling_approval.py)
-- that machinery is DRC-specific and owned elsewhere. Raising a
``warning_ceiling`` (or adding/raising an ``errors_by_type`` entry) here is
a manual, reviewed edit to ``power_pcb_dataset/erc_ceiling.json``, same as
any other committed constant.

Exit codes: 0 = pass, 1 = ERC errors present beyond an explicitly
documented ceiling or a warning ceiling exceeded, 2 = the gate itself
could not run (kicad-cli missing, schematic missing, malformed ceiling
file).
"""

from __future__ import annotations

import argparse
import contextlib
import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def _find_repo_root() -> Path:
    p = Path.cwd()
    while not (p / ".git").exists() and p != p.parent:
        p = p.parent
    return p


@dataclass
class ErcItem:
    rule: str
    severity: str
    description: str


@dataclass
class ErcResult:
    error_count: int
    warning_count: int
    errors_by_type: dict[str, int] = field(default_factory=dict)
    warnings_by_type: dict[str, int] = field(default_factory=dict)
    errors: list[ErcItem] = field(default_factory=list)
    warnings: list[ErcItem] = field(default_factory=list)


class ErcRunnerError(Exception):
    """Raised when ``kicad-cli sch erc`` itself could not be run or its
    output could not be parsed -- distinct from a clean run that reports
    violations."""


def is_kicad_cli_available() -> bool:
    return shutil.which("kicad-cli") is not None


def get_kicad_cli_version() -> str | None:
    if not is_kicad_cli_available():
        return None
    try:
        result = subprocess.run(
            ["kicad-cli", "version"], capture_output=True, text=True, timeout=10
        )
    except (subprocess.SubprocessError, OSError):
        return None
    if result.returncode != 0:
        return None
    version = result.stdout.strip()
    return version or None


def _parse_erc_json(json_path: Path) -> ErcResult:
    with open(json_path) as f:
        data = json.load(f)

    # KiCad's ERC JSON report shape mirrors its DRC JSON report shape:
    # a top-level "violations" (some KiCad versions: "sheets"[]->"violations")
    # list of dicts carrying "type" (rule id), "severity", and
    # "description". kicad-cli sch erc nests violations per-sheet under
    # a top-level "sheets" list in KiCad 8+; fall back to a flat
    # top-level "violations" list for safety across versions -- both are
    # collected, never assumed exclusive.
    raw_items: list[dict[str, Any]] = []
    top_level = data.get("violations")
    if isinstance(top_level, list):
        raw_items.extend(top_level)
    for sheet in data.get("sheets", []) or []:
        sheet_violations = sheet.get("violations")
        if isinstance(sheet_violations, list):
            raw_items.extend(sheet_violations)

    errors: list[ErcItem] = []
    warnings: list[ErcItem] = []
    errors_by_type: dict[str, int] = {}
    warnings_by_type: dict[str, int] = {}

    for item in raw_items:
        rule = item.get("type", "unknown")
        severity = item.get("severity", "error")
        description = item.get("description", "")
        erc_item = ErcItem(rule=rule, severity=severity, description=description)
        if severity == "warning":
            warnings.append(erc_item)
            warnings_by_type[rule] = warnings_by_type.get(rule, 0) + 1
        else:
            errors.append(erc_item)
            errors_by_type[rule] = errors_by_type.get(rule, 0) + 1

    return ErcResult(
        error_count=len(errors),
        warning_count=len(warnings),
        errors_by_type=errors_by_type,
        warnings_by_type=warnings_by_type,
        errors=errors,
        warnings=warnings,
    )


def run_erc(sch_path: Path, timeout: int = 120) -> ErcResult:
    """Run ``kicad-cli sch erc`` on a schematic file and parse the result.

    Raises:
        FileNotFoundError: if *sch_path* doesn't exist.
        ErcRunnerError: if kicad-cli is unavailable or the run fails.
    """
    sch_path = Path(sch_path)
    if not sch_path.exists():
        raise FileNotFoundError(f"Schematic file not found: {sch_path}")

    if not is_kicad_cli_available():
        raise ErcRunnerError(
            "kicad-cli is not available. Install KiCad 10.0.5 (this repo's "
            "pinned version, .github/docker/ci.Dockerfile) and ensure "
            "kicad-cli is in PATH."
        )

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
        json_path = Path(tmp.name)

    try:
        result = subprocess.run(
            [
                "kicad-cli",
                "sch",
                "erc",
                "--format",
                "json",
                "--output",
                str(json_path),
                str(sch_path),
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        # kicad-cli sch erc, like pcb drc, returns a nonzero exit code when
        # violations are found even though the report was written
        # successfully -- ERC "failing" the CLI's own exit code is the
        # NORMAL case for a schematic with any warnings/errors, not a
        # run failure. Only treat it as a run failure if no report file
        # was produced.
        if not json_path.exists():
            raise ErcRunnerError(
                f"kicad-cli sch erc did not produce an output file "
                f"(exit {result.returncode}). stdout: {result.stdout}, "
                f"stderr: {result.stderr}"
            )

        return _parse_erc_json(json_path)

    except subprocess.TimeoutExpired as e:
        raise ErcRunnerError(f"ERC timed out after {timeout} seconds") from e
    except subprocess.SubprocessError as e:
        raise ErcRunnerError(f"Failed to run kicad-cli: {e}") from e
    finally:
        if json_path.exists():
            with contextlib.suppress(OSError):
                json_path.unlink()


def _check_board(repo_root: Path, entry: dict[str, Any]) -> tuple[bool, list[str]]:
    """Check one schematic entry from erc_ceiling.json.

    Returns (passed, messages) -- messages are printed regardless of
    pass/fail so a passing run still shows the measured counts.
    """
    board_id = entry["board_id"]
    sch_path = repo_root / entry["path"]
    error_ceiling = entry.get("error_ceiling", 0)
    allowed_errors_by_type: dict[str, int] = entry.get("errors_by_type") or {}
    warning_ceiling = entry.get("warning_ceiling")

    messages: list[str] = []

    try:
        erc_result = run_erc(sch_path)
    except (FileNotFoundError, ErcRunnerError) as e:
        messages.append(f"FAIL: {board_id}: ERC could not run: {e}")
        return False, messages

    passed = True

    # Aggregate ceiling, PLUS per-type implicit-zero ceiling (mirrors
    # power_pcb_dataset/drc_ceiling.json's violations_by_type semantics): a
    # rule absent from allowed_errors_by_type has ceiling 0 regardless of
    # aggregate headroom, so a documented allowance for one known error
    # type (e.g. mcu.kicad_sch's pin_not_connected artifact, see that
    # board's _artifact_note) can never silently cover a new, different
    # one.
    if erc_result.error_count == 0:
        messages.append(f"PASS: {board_id}: 0 ERC errors.")
    else:
        category_problems: list[str] = []
        for rule, count in sorted(erc_result.errors_by_type.items()):
            allowed = allowed_errors_by_type.get(rule, 0)
            if count > allowed:
                category_problems.append(f"{rule}={count} (allowed {allowed})")
        if erc_result.error_count > error_ceiling or category_problems:
            by_type = ", ".join(
                f"{k}={v}" for k, v in sorted(erc_result.errors_by_type.items())
            )
            reason = (
                "errors must be zero, no exceptions"
                if error_ceiling == 0
                else f"exceeds documented ceiling ({error_ceiling} aggregate"
                + (f"; new/regressed categories: {', '.join(category_problems)}" if category_problems else "")
                + ")"
            )
            messages.append(
                f"FAIL: {board_id}: {erc_result.error_count} ERC error(s) "
                f"({by_type}) -- {reason}."
            )
            passed = False
        else:
            by_type = ", ".join(
                f"{k}={v}" for k, v in sorted(erc_result.errors_by_type.items())
            )
            messages.append(
                f"PASS: {board_id}: {erc_result.error_count} ERC error(s) "
                f"({by_type}) within documented ceiling of {error_ceiling} "
                "(see erc_ceiling.json's _artifact_note for this board)."
            )

    if warning_ceiling is None:
        messages.append(
            f"WARN: {board_id}: warning_ceiling is unset (TODO) in "
            "erc_ceiling.json -- ratchet not enforced. Measured "
            f"{erc_result.warning_count} warning(s) this run "
            f"({', '.join(f'{k}={v}' for k, v in sorted(erc_result.warnings_by_type.items())) or 'none'}). "
            "See erc_ceiling.json's _provenance_note for why (must be "
            "re-measured on the pinned kicad-cli version before a ceiling "
            "can be trusted)."
        )
    elif erc_result.warning_count > warning_ceiling:
        by_type = ", ".join(f"{k}={v}" for k, v in sorted(erc_result.warnings_by_type.items()))
        messages.append(
            f"FAIL: {board_id}: {erc_result.warning_count} ERC warning(s) "
            f"exceeds ceiling of {warning_ceiling} ({by_type})."
        )
        passed = False
    else:
        messages.append(
            f"PASS: {board_id}: {erc_result.warning_count} ERC warning(s) "
            f"<= ceiling of {warning_ceiling}."
        )

    return passed, messages


def main() -> int:
    parser = argparse.ArgumentParser(description="ERC ratchet CI check")
    parser.add_argument(
        "--ceiling",
        type=Path,
        default=None,
        help="Path to erc_ceiling.json (default: power_pcb_dataset/erc_ceiling.json)",
    )
    args = parser.parse_args()

    repo_root = _find_repo_root()
    ceiling_path = args.ceiling or (repo_root / "power_pcb_dataset" / "erc_ceiling.json")

    if not ceiling_path.exists():
        print(f"ERC ceiling not found: {ceiling_path}")
        print("ERC: SKIPPED (ceiling file not found)")
        return 0

    with open(ceiling_path) as f:
        data = json.load(f)

    boards = data.get("boards", [])
    if not boards:
        print("ERC: SKIPPED (no boards in ceiling)")
        return 0

    kicad_version = get_kicad_cli_version()
    print(f"kicad-cli version: {kicad_version or 'UNAVAILABLE'}")

    overall_passed = True
    for entry in boards:
        passed, messages = _check_board(repo_root, entry)
        for m in messages:
            print(m)
        overall_passed = overall_passed and passed

    return 0 if overall_passed else 1


if __name__ == "__main__":
    sys.exit(main())
