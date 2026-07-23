"""Validation of committed DRC evidence for via-aware routing changes.

This is deliberately small and fail-closed: a missing, malformed, or
unmeasured record is never evidence that routing is clean. Connectivity is
compared against the declared pre-U1 baseline, because the production board
already carries known multi-pad-net disconnects outside the via-transition
workstream.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class MeasurementRecordError(ValueError):
    """Raised when a routing measurement cannot prove what it claims."""


_BOARD_NAMES = frozenset(("corpus", "production"))
_MEASURED_GATE_STATUSES = frozenset(("CLEAN", "VIOLATIONS"))


def _load_record(record_or_path: object) -> object:
    if isinstance(record_or_path, Path):
        try:
            return json.loads(record_or_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise MeasurementRecordError(f"Cannot read routing measurement record: {exc}") from exc
    return record_or_path


def _require_mapping(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise MeasurementRecordError(f"{name} must be an object")
    return value


def validate_via_routing_measurement(record_or_path: object) -> dict[str, Any]:
    """Validate the U8 measurement schema and fail on unmeasured gate output.

    A ``VIOLATIONS`` status is valid evidence: it reports a real measurement
    without disguising an unresolved physical problem as clean.  In contrast,
    ``UNMEASURED`` is rejected because it offers no routing truth at all.
    """
    record = _require_mapping(_load_record(record_or_path), "measurement record")
    if record.get("schema_version") != 1:
        raise MeasurementRecordError("schema_version must be 1")

    boards = _require_mapping(record.get("boards"), "boards")
    if set(boards) != _BOARD_NAMES:
        raise MeasurementRecordError(
            f"boards must be exactly {sorted(_BOARD_NAMES)}, got {sorted(boards)}"
        )

    for board_name in sorted(_BOARD_NAMES):
        board = _require_mapping(boards[board_name], f"boards.{board_name}")
        completion = board.get("completion_rate")
        if not isinstance(completion, (int, float)) or completion != 1.0:
            raise MeasurementRecordError(f"boards.{board_name}.completion_rate must be exactly 1.0")
        baseline_unconnected = board.get("baseline_unconnected_items")
        if (
            not isinstance(baseline_unconnected, int)
            or isinstance(baseline_unconnected, bool)
            or baseline_unconnected < 0
        ):
            raise MeasurementRecordError(
                f"boards.{board_name}.baseline_unconnected_items must be a non-negative integer"
            )
        unconnected = board.get("unconnected_items")
        if not isinstance(unconnected, int) or isinstance(unconnected, bool) or unconnected < 0:
            raise MeasurementRecordError(
                f"boards.{board_name}.unconnected_items must be a non-negative integer"
            )
        if unconnected > baseline_unconnected:
            raise MeasurementRecordError(
                f"boards.{board_name}.unconnected_items ({unconnected}) exceeds "
                f"the pre-U1 baseline ({baseline_unconnected})"
            )
        if board.get("contains_vias") is not True:
            raise MeasurementRecordError(f"boards.{board_name}.contains_vias must be true")
        counts = _require_mapping(board.get("drc_counts"), f"boards.{board_name}.drc_counts")
        if any(
            not isinstance(count, int) or isinstance(count, bool) or count < 0
            for count in counts.values()
        ):
            raise MeasurementRecordError(
                f"boards.{board_name}.drc_counts must contain non-negative integers"
            )
        gates = _require_mapping(board.get("gates"), f"boards.{board_name}.gates")
        if set(gates) != {"clearance", "iec_creepage"}:
            raise MeasurementRecordError(
                f"boards.{board_name}.gates must contain clearance and iec_creepage"
            )
        for gate_name, status in gates.items():
            if status not in _MEASURED_GATE_STATUSES:
                raise MeasurementRecordError(
                    f"boards.{board_name}.gates.{gate_name} is {status!r}; "
                    "UNMEASURED or unknown statuses are not evidence"
                )
    return record
