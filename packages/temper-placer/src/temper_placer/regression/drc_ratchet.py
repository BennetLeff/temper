"""DRC ratchet CI gate.

Loads drc_ceiling.json, runs DRC on target boards, and enforces
a monotonically-non-increasing ceiling on DRC violation counts.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class DrcCeilingEntry:
    """A single board entry in the DRC ceiling file."""

    board_id: str
    path: str
    error_ceiling: int
    warning_ceiling: int
    violations_by_type: dict[str, int] = field(default_factory=dict)


@dataclass
class DrcRatchetResult:
    """Result of a DRC ratchet check."""

    passed: bool
    board_id: str
    message: str
    exit_code: int = 0
    violation_deltas: dict[str, int] = field(default_factory=dict)


class DrcRatchet:
    """Enforces DRC ceiling via committed JSON file."""

    def __init__(self, ceiling_path: Path):
        self.ceiling_path = Path(ceiling_path)
        self.entries: dict[str, DrcCeilingEntry] = {}

    def load(self) -> None:
        if not self.ceiling_path.exists():
            return

        with open(self.ceiling_path) as f:
            data = json.load(f)

        for entry in data.get("boards", []):
            board_id = entry["board_id"]
            self.entries[board_id] = DrcCeilingEntry(
                board_id=board_id,
                path=entry["path"],
                error_ceiling=entry.get("error_ceiling", 0),
                warning_ceiling=entry.get("warning_ceiling", 0),
                violations_by_type=entry.get("violations_by_type", {}),
            )

    def check(self, repo_root: Path) -> list[DrcRatchetResult]:
        results: list[DrcRatchetResult] = []

        for board_id, entry in self.entries.items():
            pcb_path = repo_root / entry.path
            result = self._check_board(board_id, pcb_path, entry)
            results.append(result)

        return results

    def _check_board(
        self, board_id: str, pcb_path: Path, entry: DrcCeilingEntry
    ) -> DrcRatchetResult:
        if not pcb_path.exists():
            return DrcRatchetResult(
                passed=False,
                board_id=board_id,
                message=f"PCB file not found: {pcb_path}",
                exit_code=1,
            )

        try:
            from temper_placer.validation.drc_runner import run_drc

            drc_result = run_drc(pcb_path)
        except Exception as e:
            return DrcRatchetResult(
                passed=False,
                board_id=board_id,
                message=f"DRC failed: {e}",
                exit_code=1,
            )

        current_errors = drc_result.error_count
        current_warnings = drc_result.warning_count

        if current_errors > entry.error_ceiling:
            delta = current_errors - entry.error_ceiling
            return DrcRatchetResult(
                passed=False,
                board_id=board_id,
                message=f"{board_id}: DRC {current_errors} exceeds ceiling {entry.error_ceiling} (+{delta} errors)",
                exit_code=1,
            )

        if current_warnings > entry.warning_ceiling:
            delta = current_warnings - entry.warning_ceiling
            return DrcRatchetResult(
                passed=False,
                board_id=board_id,
                message=f"{board_id}: DRC {current_warnings} exceeds ceiling {entry.warning_ceiling} (+{delta} warnings)",
                exit_code=1,
            )

        return DrcRatchetResult(
            passed=True,
            board_id=board_id,
            message=f"{board_id}: DRC {current_errors}/{entry.error_ceiling} errors, {current_warnings}/{entry.warning_ceiling} warnings within ceiling",
        )

    def detect_ceiling_raise(
        self, old_ceiling: dict, new_ceiling: dict, commit_message: str = ""
    ) -> DrcRatchetResult | None:
        """Detect if ceiling was raised without approval."""
        old_boards = {b["board_id"]: b for b in old_ceiling.get("boards", [])}
        new_boards = {b["board_id"]: b for b in new_ceiling.get("boards", [])}

        for board_id, new_entry in new_boards.items():
            old_entry = old_boards.get(board_id)
            if old_entry is None:
                continue

            old_errors = old_entry.get("error_ceiling", 0)
            new_errors = new_entry.get("error_ceiling", 0)
            old_warnings = old_entry.get("warning_ceiling", 0)
            new_warnings = new_entry.get("warning_ceiling", 0)

            if new_errors > old_errors or new_warnings > old_warnings:
                has_approval = "Ceiling-Approval:" in commit_message
                if not has_approval:
                    return DrcRatchetResult(
                        passed=False,
                        board_id=board_id,
                        message=f"Ceiling increase {old_errors} -> {new_errors} requires explicit approval.",
                        exit_code=2,
                    )

        return None
