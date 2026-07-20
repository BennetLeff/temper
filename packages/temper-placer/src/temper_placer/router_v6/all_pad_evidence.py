"""Fail-closed validation for APC1 all-pad KiCad baseline evidence."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


class AllPadEvidenceError(ValueError):
    """Raised when an APC1 baseline does not prove a real KiCad measurement."""


_BOARD_NAMES = frozenset(("corpus", "production"))
_HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")


def _load_record(record_or_path: object) -> object:
    if isinstance(record_or_path, Path):
        try:
            return json.loads(record_or_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise AllPadEvidenceError(f"Cannot read APC1 evidence: {exc}") from exc
    return record_or_path


def _mapping(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise AllPadEvidenceError(f"{name} must be an object")
    return value


def _sha(value: object, name: str) -> None:
    if not isinstance(value, str) or not _HEX_SHA256.fullmatch(value):
        raise AllPadEvidenceError(f"{name} must be a lowercase SHA-256")


def _nonnegative_integer(value: object, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise AllPadEvidenceError(f"{name} must be a non-negative integer")
    return value


def _validate_board(board_name: str, board_value: object) -> None:
    board = _mapping(board_value, f"boards.{board_name}")
    status = board.get("measurement_status")
    if status == "UNMEASURED":
        raise AllPadEvidenceError(f"boards.{board_name} is UNMEASURED")
    if status not in {"CLEAN", "VIOLATIONS"}:
        raise AllPadEvidenceError(
            f"boards.{board_name}.measurement_status must be CLEAN or VIOLATIONS"
        )

    source = _mapping(board.get("source_board"), f"boards.{board_name}.source_board")
    if not isinstance(source.get("path"), str) or not source["path"]:
        raise AllPadEvidenceError(f"boards.{board_name}.source_board.path is required")
    _sha(source.get("sha256"), f"boards.{board_name}.source_board.sha256")
    _sha(board.get("routed_output_sha256"), f"boards.{board_name}.routed_output_sha256")
    _sha(board.get("drc_report_sha256"), f"boards.{board_name}.drc_report_sha256")

    command = board.get("command")
    if not isinstance(command, list) or not command or not all(
        isinstance(argument, str) and argument for argument in command
    ):
        raise AllPadEvidenceError(f"boards.{board_name}.command must be a non-empty string list")
    if not isinstance(board.get("kicad_cli_version"), str) or not board["kicad_cli_version"]:
        raise AllPadEvidenceError(f"boards.{board_name}.kicad_cli_version is required")
    invocation = _mapping(board.get("router_invocation"), f"boards.{board_name}.router_invocation")
    if not invocation:
        raise AllPadEvidenceError(f"boards.{board_name}.router_invocation is required")

    counts = _mapping(board.get("drc_counts"), f"boards.{board_name}.drc_counts")
    if "unconnected_items" not in counts:
        raise AllPadEvidenceError(f"boards.{board_name}.drc_counts must include unconnected_items")
    for error_class, count in counts.items():
        if not isinstance(error_class, str) or not error_class:
            raise AllPadEvidenceError(f"boards.{board_name}.drc_counts keys must be non-empty strings")
        _nonnegative_integer(count, f"boards.{board_name}.drc_counts.{error_class}")
    unconnected = _nonnegative_integer(
        board.get("unconnected_items"), f"boards.{board_name}.unconnected_items"
    )
    if counts["unconnected_items"] != unconnected:
        raise AllPadEvidenceError(f"boards.{board_name} unconnected_items must match drc_counts")

    attribution = _mapping(
        board.get("unconnected_by_net"), f"boards.{board_name}.unconnected_by_net"
    )
    if attribution.get("status") != "UNAVAILABLE" or not isinstance(
        attribution.get("reason"), str
    ) or not attribution["reason"]:
        raise AllPadEvidenceError(
            f"boards.{board_name}.unconnected_by_net must explicitly be UNAVAILABLE with a reason"
        )

    expected = 0 if board_name == "corpus" else 149
    if board_name == "corpus" and unconnected != expected:
        raise AllPadEvidenceError("boards.corpus.unconnected_items must be exactly 0")
    if board_name == "production" and unconnected > expected:
        raise AllPadEvidenceError("boards.production.unconnected_items must not exceed 149")


def validate_all_pad_baseline(record_or_path: object) -> dict[str, Any]:
    """Validate APC1 U0 evidence; missing or unmeasured data never passes."""
    record = _mapping(_load_record(record_or_path), "APC1 evidence")
    if record.get("schema_version") != 1:
        raise AllPadEvidenceError("schema_version must be 1")
    if record.get("evidence_kind") != "APC1_U0_ALL_PAD_ROUTING_BASELINE":
        raise AllPadEvidenceError("evidence_kind must identify the APC1 U0 baseline")
    if not isinstance(record.get("generated_at_utc"), str) or not record["generated_at_utc"].endswith("Z"):
        raise AllPadEvidenceError("generated_at_utc must be a UTC timestamp")
    source_commit = record.get("source_commit")
    if not isinstance(source_commit, str) or not _GIT_SHA.fullmatch(source_commit):
        raise AllPadEvidenceError("source_commit must be a lowercase full Git SHA")

    boards = _mapping(record.get("boards"), "boards")
    if set(boards) != _BOARD_NAMES:
        raise AllPadEvidenceError(f"boards must be exactly {sorted(_BOARD_NAMES)}")
    for board_name in sorted(_BOARD_NAMES):
        _validate_board(board_name, boards[board_name])
    return record
