"""Canonical, resumable cache for production constraint-family probes.

Family probes are fresh-model feasibility experiments.  A cache entry records
the solver's result, but does not reinterpret an ``unknown`` result as either
feasible or infeasible.  The identity deliberately includes the board hash,
the exact family set, stable digests of the caller's JSON-safe projections,
and the solve limits that affect the result.

This module owns persistence only.  It does not assemble CP-SAT constraints or
invoke the solver; the campaign remains the sole owner of that behaviour.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from collections.abc import Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path

from temper_placer.placer.cp_sat.constraint_restoration_campaign import (
    RestorationLimits,
    RestorationStageStatus,
)
from temper_placer.placer.cp_sat.displacement_deletion_frontier import (
    available_board_hash,
    canonical_json,
)

FRONTIER_SCHEMA = "temper.constraint-family-feasibility-frontier"
FRONTIER_VERSION = 1


def _digest(value: object) -> str:
    """Return the SHA-256 digest of a strict canonical JSON projection."""

    # canonical_json performs the important JSON-safe validation and rejects
    # object reprs, bytes, non-finite floats, and non-string mapping keys.
    encoded = canonical_json(value).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _normalise_family_set(value: object) -> tuple[str, ...]:
    if isinstance(value, Mapping):
        values = tuple(value.keys())
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        values = tuple(value)
    else:
        raise TypeError("family_set must be a sequence of names or a mapping")
    if any(not isinstance(name, str) or not name.strip() for name in values):
        raise ValueError("family_set must contain non-empty string names")
    names = tuple(sorted(name.strip() for name in values))
    if len(set(names)) != len(names):
        raise ValueError("family_set must not contain duplicate names")
    return names


def _normalise_limits(value: object) -> dict[str, object]:
    if isinstance(value, RestorationLimits):
        normalized = {
            "total_timeout_s": float(value.total_timeout_s),
            "stage_timeout_s": float(value.stage_timeout_s),
            "memory_limit_mb": value.memory_limit_mb,
        }
        # RestorationLimits predates this cache and intentionally keeps its
        # constructor lightweight; enforce the serialization contract here.
        if any(not math.isfinite(normalized[key]) or normalized[key] <= 0.0 for key in ("total_timeout_s", "stage_timeout_s")):
            raise ValueError("limits timeouts must be finite and positive")
        if normalized["memory_limit_mb"] is not None and (
            isinstance(normalized["memory_limit_mb"], bool)
            or not isinstance(normalized["memory_limit_mb"], int)
            or normalized["memory_limit_mb"] <= 0
        ):
            raise ValueError("limits.memory_limit_mb must be a positive integer or null")
        return normalized
    if value is None:
        return {}
    if isinstance(value, (str, bytes)) or not isinstance(value, Mapping):
        raise TypeError("limits must be RestorationLimits or a JSON-safe mapping")
    # The digest call is also the strict validation.  Keep the normalized
    # projection so key spelling is deterministic when a record is written.
    normalized = json.loads(canonical_json(value))
    assert isinstance(normalized, dict)
    for key in ("total_timeout_s", "stage_timeout_s"):
        if key in normalized:
            number = normalized[key]
            if not isinstance(number, (int, float)) or isinstance(number, bool) or not math.isfinite(float(number)):
                raise ValueError(f"limits.{key} must be a finite number")
            if float(number) <= 0.0:
                raise ValueError(f"limits.{key} must be positive")
    if "memory_limit_mb" in normalized and normalized["memory_limit_mb"] is not None:
        memory = normalized["memory_limit_mb"]
        if isinstance(memory, bool) or not isinstance(memory, int) or memory <= 0:
            raise ValueError("limits.memory_limit_mb must be a positive integer or null")
    return normalized


@dataclass(frozen=True, slots=True)
class ConstraintFamilyProbeKey:
    """Canonical identity of one exact family-set feasibility probe."""

    family_set: tuple[str, ...]
    production_options: Mapping[str, object] = field(default_factory=dict)
    family_options: Mapping[str, object] = field(default_factory=dict)
    limits: Mapping[str, object] = field(default_factory=dict)
    board_hash: str | None = None

    def __post_init__(self) -> None:
        families = _normalise_family_set(self.family_set)
        if isinstance(self.production_options, (str, bytes)) or not isinstance(self.production_options, Mapping):
            raise TypeError("production_options must be a mapping")
        if isinstance(self.family_options, (str, bytes)) or not isinstance(self.family_options, Mapping):
            raise TypeError("family_options must be a mapping")
        production = json.loads(canonical_json(self.production_options))
        family = json.loads(canonical_json(self.family_options))
        limits = _normalise_limits(self.limits)
        board_hash = self.board_hash
        if board_hash is not None and (not isinstance(board_hash, str) or not board_hash.strip()):
            raise ValueError("board_hash must be a non-empty string or None")
        object.__setattr__(self, "family_set", families)
        object.__setattr__(self, "production_options", production)
        object.__setattr__(self, "family_options", family)
        object.__setattr__(self, "limits", limits)
        object.__setattr__(self, "board_hash", board_hash.strip().lower() if board_hash else None)

    @property
    def production_options_digest(self) -> str:
        return _digest(self.production_options)

    @property
    def family_digest(self) -> str:
        return _digest(self.family_options)

    @property
    def limits_digest(self) -> str:
        return _digest(self.limits)

    def to_dict(self) -> dict[str, object]:
        return {
            "board_hash": self.board_hash,
            "family_set": list(self.family_set),
            "family_options": self.family_options,
            "family_digest": self.family_digest,
            "production_options": self.production_options,
            "production_options_digest": self.production_options_digest,
            "limits": self.limits,
            "limits_digest": self.limits_digest,
        }

    @property
    def canonical(self) -> str:
        return canonical_json(self.to_dict())

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.canonical.encode("utf-8")).hexdigest()

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> ConstraintFamilyProbeKey:
        try:
            key = cls(
                tuple(payload["family_set"]),  # type: ignore[arg-type]
                payload["production_options"],  # type: ignore[arg-type]
                payload["family_options"],  # type: ignore[arg-type]
                payload.get("limits", {}),  # type: ignore[arg-type]
                payload.get("board_hash"),  # type: ignore[arg-type]
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"invalid constraint-family probe key: {exc}") from exc
        expected = payload.get("limits_digest")
        if expected is not None and expected != key.limits_digest:
            raise ValueError("constraint-family probe key has an invalid limits digest")
        # Validate the declared digests against the JSON-safe projections;
        # this rejects hand-edited or truncated cache identities.
        if key.production_options_digest != payload.get("production_options_digest"):
            raise ValueError("invalid production option digest")
        if key.family_digest != payload.get("family_digest"):
            raise ValueError("invalid family digest")
        return key


@dataclass(frozen=True, slots=True)
class ConstraintFamilyProbeRecord:
    """Plain-data result of one family feasibility probe."""

    key: ConstraintFamilyProbeKey
    status: RestorationStageStatus
    elapsed_s: float
    solver_status: str | None = None
    positions: Mapping[str, tuple[float, float]] = field(default_factory=dict)
    rotations: Mapping[str, int] = field(default_factory=dict)
    verification_passed: bool | None = None
    violation_count: int | None = None
    diagnostics: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.status, RestorationStageStatus):
            raise TypeError("status must be a RestorationStageStatus")
        elapsed = float(self.elapsed_s)
        if not math.isfinite(elapsed) or elapsed < 0.0:
            raise ValueError("elapsed_s must be finite and non-negative")
        if self.solver_status is not None and not isinstance(self.solver_status, str):
            raise TypeError("solver_status must be a string or None")
        if not isinstance(self.positions, Mapping) or not isinstance(self.rotations, Mapping):
            raise TypeError("positions and rotations must be mappings")
        for ref, point in self.positions.items():
            if not isinstance(ref, str) or isinstance(point, (str, bytes)) or not isinstance(point, Sequence) or len(point) != 2:
                raise ValueError("positions must map refs to two-coordinate sequences")
            if any(not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(float(value)) for value in point):
                raise ValueError("positions must contain finite numeric coordinates")
        for ref, rotation in self.rotations.items():
            if not isinstance(ref, str) or isinstance(rotation, bool) or not isinstance(rotation, int):
                raise ValueError("rotations must map refs to integer angles")
        if self.verification_passed is not None and not isinstance(self.verification_passed, bool):
            raise TypeError("verification_passed must be bool or None")
        if self.violation_count is not None and (isinstance(self.violation_count, bool) or not isinstance(self.violation_count, int) or self.violation_count < 0):
            raise ValueError("violation_count must be a non-negative integer or None")
        if any(not isinstance(item, str) for item in self.diagnostics):
            raise TypeError("diagnostics must contain strings")
        object.__setattr__(self, "elapsed_s", elapsed)
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key.to_dict(),
            "status": self.status.value,
            "elapsed_s": self.elapsed_s,
            "solver_status": self.solver_status,
            "positions": {ref: list(point) for ref, point in sorted(self.positions.items())},
            "rotations": dict(sorted(self.rotations.items())),
            "verification_passed": self.verification_passed,
            "violation_count": self.violation_count,
            "diagnostics": list(self.diagnostics),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> ConstraintFamilyProbeRecord:
        try:
            status = RestorationStageStatus(payload["status"])
            raw_positions = payload.get("positions", {})
            raw_rotations = payload.get("rotations", {})
            diagnostics = payload.get("diagnostics", ())
            if not isinstance(raw_positions, Mapping) or not isinstance(raw_rotations, Mapping):
                raise TypeError("positions and rotations must be mappings")
            if isinstance(diagnostics, (str, bytes)) or not isinstance(diagnostics, Sequence):
                raise TypeError("diagnostics must be a sequence")
            return cls(
                ConstraintFamilyProbeKey.from_dict(payload["key"]),  # type: ignore[arg-type]
                status,
                float(payload["elapsed_s"]),
                payload.get("solver_status"),  # type: ignore[arg-type]
                {ref: tuple(point) for ref, point in raw_positions.items()},  # type: ignore[arg-type]
                raw_rotations,
                payload.get("verification_passed"),  # type: ignore[arg-type]
                payload.get("violation_count"),  # type: ignore[arg-type]
                tuple(diagnostics),  # type: ignore[arg-type]
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"invalid constraint-family probe record: {exc}") from exc


def accepted_placement_covers(record: ConstraintFamilyProbeRecord, expected_refs: Sequence[str]) -> bool:
    """Return whether an accepted cached result covers exactly all refs."""

    expected = set(expected_refs)
    return record.status is RestorationStageStatus.ACCEPTED and (
        set(record.positions) == expected and set(record.rotations) == expected
    )


@dataclass(frozen=True, slots=True)
class ConstraintFamilySearchFrontier:
    """Immutable collection of cached family-probe records."""

    records: tuple[ConstraintFamilyProbeRecord, ...] = ()

    def __post_init__(self) -> None:
        by_key: dict[str, ConstraintFamilyProbeRecord] = {}
        for record in self.records:
            if not isinstance(record, ConstraintFamilyProbeRecord):
                raise TypeError("frontier records must be ConstraintFamilyProbeRecord values")
            by_key[record.key.canonical] = record
        object.__setattr__(self, "records", tuple(by_key[key] for key in sorted(by_key)))

    def lookup(self, key: ConstraintFamilyProbeKey, expected_refs: Sequence[str] | None = None) -> ConstraintFamilyProbeRecord | None:
        wanted = key.canonical
        record = next((item for item in self.records if item.key.canonical == wanted), None)
        if (
            record is not None
            and expected_refs is not None
            and record.status is RestorationStageStatus.ACCEPTED
            and not accepted_placement_covers(record, expected_refs)
        ):
            return None
        return record

    def add(
        self,
        record_or_key: ConstraintFamilyProbeRecord | ConstraintFamilyProbeKey,
        result: object | None = None,
    ) -> ConstraintFamilySearchFrontier:
        """Return a frontier with one record, accepting campaign adapters.

        The native form is ``add(record)``.  The family campaign also uses a
        deliberately small duck-typed protocol, ``add(key, result)``; this
        adapter copies only its plain result fields and never stores the live
        solver result object.
        """

        if result is None:
            if not isinstance(record_or_key, ConstraintFamilyProbeRecord):
                raise TypeError("add(record) requires a ConstraintFamilyProbeRecord")
            record = record_or_key
        else:
            if not isinstance(record_or_key, ConstraintFamilyProbeKey):
                raise TypeError("add(key, result) requires a ConstraintFamilyProbeKey")
            status = getattr(result, "status", None)
            if not isinstance(status, RestorationStageStatus):
                status = RestorationStageStatus(str(status))
            record = ConstraintFamilyProbeRecord(
                record_or_key,
                status,
                float(getattr(result, "elapsed_s", 0.0)),
                getattr(result, "solver_status", None),
                getattr(result, "positions", {}),
                getattr(result, "rotations", {}),
                getattr(result, "verification_passed", None),
                getattr(result, "violation_count", None),
                tuple(getattr(result, "diagnostics", ())),
            )
        return ConstraintFamilySearchFrontier((*self.records, record))

    def to_dict(self) -> dict[str, object]:
        return {"schema": FRONTIER_SCHEMA, "version": FRONTIER_VERSION, "records": [record.to_dict() for record in self.records]}

    def to_json(self) -> str:
        return canonical_json(self.to_dict())

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> ConstraintFamilySearchFrontier:
        if payload.get("schema") != FRONTIER_SCHEMA or payload.get("version") != FRONTIER_VERSION:
            raise ValueError("unsupported constraint-family frontier schema or version")
        records = payload.get("records")
        if isinstance(records, (str, bytes)) or not isinstance(records, Sequence):
            raise ValueError("constraint-family frontier records must be a sequence")
        return cls(tuple(ConstraintFamilyProbeRecord.from_dict(record) for record in records))  # type: ignore[arg-type]

    @classmethod
    def from_json(cls, text: str) -> ConstraintFamilySearchFrontier:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid constraint-family frontier JSON: {exc}") from exc
        if not isinstance(payload, Mapping):
            raise ValueError("constraint-family frontier JSON root must be an object")
        return cls.from_dict(payload)

    @classmethod
    def read(cls, path: str | Path) -> ConstraintFamilySearchFrontier:
        return cls.from_json(Path(path).read_text(encoding="utf-8"))

    def write(self, path: str | Path) -> None:
        """Atomically persist canonical JSON in the destination directory."""

        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary_name = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(self.to_json() + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_name, destination)
        except BaseException:
            with suppress(OSError):
                os.unlink(temporary_name)
            raise


def constraint_family_probe_key(
    family_set: Sequence[str] | Mapping[str, object],
    *,
    production_options: Mapping[str, object],
    family_options: Mapping[str, object] | None = None,
    limits: RestorationLimits | Mapping[str, object] | None = None,
    board: object | None = None,
    board_hash: str | None = None,
) -> ConstraintFamilyProbeKey:
    """Build a family-probe key, preferring an explicit board hash."""

    selected = _normalise_family_set(family_set)
    options = family_options if family_options is not None else (family_set if isinstance(family_set, Mapping) else {})
    return ConstraintFamilyProbeKey(
        selected,
        production_options,
        options,
        _normalise_limits(limits),
        board_hash if board_hash is not None else available_board_hash(board),
    )


# Names used by the campaign/document vocabulary.  They are aliases, not
# second implementations, so status and serialization semantics stay shared.
FamilyProbeKey = ConstraintFamilyProbeKey
FamilyProbeRecord = ConstraintFamilyProbeRecord
FamilySearchFrontier = ConstraintFamilySearchFrontier
ConstraintFamilyFrontier = ConstraintFamilySearchFrontier

__all__ = [
    "FRONTIER_SCHEMA",
    "FRONTIER_VERSION",
    "ConstraintFamilyProbeKey",
    "ConstraintFamilyProbeRecord",
    "ConstraintFamilySearchFrontier",
    "ConstraintFamilyFrontier",
    "FamilyProbeKey",
    "FamilyProbeRecord",
    "FamilySearchFrontier",
    "RestorationStageStatus",
    "accepted_placement_covers",
    "available_board_hash",
    "constraint_family_probe_key",
]
