"""Deterministic text codec for generated creepage cutting-plane replays.

This module is a policy-free text boundary: callers provide cuts and optional
identity metadata; it never discovers requirements or writes files.
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable
from numbers import Real
from typing import Any, TypeAlias

ReplayCut: TypeAlias = tuple[str, str, float]
SCHEMA_NAME = "temper.creepage_cut_replay"
SCHEMA_VERSION = 1
_TOP_LEVEL_KEYS = frozenset({"schema", "version", "cuts", "board_identity", "input_identity"})
_CUT_KEYS = frozenset({"ref_a", "ref_b", "required_mm"})


def _identity(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{label} must be a finite non-negative number")
    result = float(value)
    if not math.isfinite(result) or result < 0.0:
        raise ValueError(f"{label} must be a finite non-negative number")
    return 0.0 if result == 0.0 else result


def _ref(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{label} must be a non-empty, trimmed string")
    return value


def _canonical(cuts: Iterable[object]) -> tuple[ReplayCut, ...]:
    reduced: dict[tuple[str, str], float] = {}
    for index, raw in enumerate(cuts):
        if not isinstance(raw, (tuple, list)) or len(raw) != 3:
            raise ValueError(f"cut {index} must be a three-item sequence")
        a = _ref(raw[0], f"cut {index} ref_a")
        b = _ref(raw[1], f"cut {index} ref_b")
        if a == b:
            raise ValueError(f"cut {index} cannot reference the same component twice")
        pair = (a, b) if a < b else (b, a)
        reduced[pair] = max(_number(raw[2], f"cut {index} required_mm"), reduced.get(pair, 0.0))
    return tuple((a, b, reduced[(a, b)]) for a, b in sorted(reduced))


def encode_creepage_cut_replay(cuts: Iterable[object], *, board_identity: str | None = None, input_identity: str | None = None) -> str:
    """Encode canonical cuts as deterministic, versioned JSON text."""
    if isinstance(cuts, (str, bytes, bytearray)):
        raise ValueError("cuts must be an iterable of three-item cuts")
    try:
        canonical = _canonical(cuts)
    except TypeError as exc:
        raise ValueError("cuts must be an iterable of three-item cuts") from exc
    payload: dict[str, Any] = {
        "schema": SCHEMA_NAME,
        "version": SCHEMA_VERSION,
        "cuts": [{"ref_a": a, "ref_b": b, "required_mm": mm} for a, b, mm in canonical],
    }
    if board_identity is not None:
        payload["board_identity"] = _identity(board_identity, "board_identity")
    if input_identity is not None:
        payload["input_identity"] = _identity(input_identity, "input_identity")
    return json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=True)


def _reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def _reject_constant(value: str) -> object:
    raise ValueError(f"non-finite JSON number is not allowed: {value}")


def decode_creepage_cut_replay(text: str, *, expected_board_identity: str | None = None, expected_input_identity: str | None = None) -> tuple[ReplayCut, ...]:
    """Strictly decode replay text and return canonical cuts."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("replay text must be a non-empty string")
    try:
        payload = json.loads(text, object_pairs_hook=_reject_duplicates, parse_constant=_reject_constant)
    except (TypeError, json.JSONDecodeError, ValueError) as exc:
        if isinstance(exc, ValueError) and not isinstance(exc, json.JSONDecodeError):
            raise
        raise ValueError("invalid creepage cut replay JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("replay root must be a JSON object")
    unknown = set(payload) - _TOP_LEVEL_KEYS
    if unknown:
        raise ValueError(f"replay has unknown field(s): {sorted(unknown)!r}")
    if payload.get("schema") != SCHEMA_NAME:
        raise ValueError("replay schema is unsupported")
    version = payload.get("version")
    if isinstance(version, bool) or version != SCHEMA_VERSION:
        raise ValueError("replay schema version is unsupported")
    raw_cuts = payload.get("cuts")
    if not isinstance(raw_cuts, list):
        raise ValueError("replay cuts must be a JSON array")
    cuts: list[object] = []
    for index, raw in enumerate(raw_cuts):
        if not isinstance(raw, dict) or set(raw) != _CUT_KEYS:
            raise ValueError(f"cut {index} must contain exactly {_CUT_KEYS!r}")
        cuts.append((raw["ref_a"], raw["ref_b"], raw["required_mm"]))
    board = payload.get("board_identity")
    source = payload.get("input_identity")
    if "board_identity" in payload:
        board = _identity(board, "board_identity")
    if "input_identity" in payload:
        source = _identity(source, "input_identity")
    if expected_board_identity is not None and board != _identity(expected_board_identity, "expected_board_identity"):
        raise ValueError("replay board identity does not match expected identity")
    if expected_input_identity is not None and source != _identity(expected_input_identity, "expected_input_identity"):
        raise ValueError("replay input identity does not match expected identity")
    return _canonical(cuts)


__all__ = ["ReplayCut", "SCHEMA_NAME", "SCHEMA_VERSION", "decode_creepage_cut_replay", "encode_creepage_cut_replay"]
