"""Serializable search frontiers for displacement deletion experiments.

Deletion probes are independent, but a real campaign can take many solver
hours.  This module gives those probes a small, deterministic cache key and a
plain JSON cache.  The key deliberately contains the things that change the
meaning of a probe: the released component references, both radii, the
caller-supplied production options, and an available board content hash.

Cached ``unknown`` results are allowed to save work when resuming, but they
remain ``unknown``.  In particular, this module never turns a cache hit into
evidence for a release or for an infeasibility claim.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from temper_placer.placer.cp_sat.constraint_restoration_campaign import RestorationStageStatus

FRONTIER_SCHEMA = "temper.displacement-deletion-frontier"
FRONTIER_VERSION = 1


def _json_value(value: object, *, path: str = "option") -> object:
    """Convert a key value to a strict JSON value.

    Cache keys must not depend on Python object identity or an incidental
    ``repr``.  Callers that pass opaque production objects should provide a
    separate, stable JSON-safe ``production_options`` mapping.
    """

    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{path} contains a non-finite float")
        return value
    if isinstance(value, Mapping):
        result: dict[str, object] = {}
        for key in sorted(value, key=lambda item: str(item)):
            if not isinstance(key, str):
                raise TypeError(f"{path} has a non-string mapping key")
            result[key] = _json_value(value[key], path=f"{path}.{key}")
        return result
    if isinstance(value, (str, bytes)):
        raise TypeError(f"{path} contains bytes, which are not a JSON option")
    if isinstance(value, Sequence):
        return [_json_value(item, path=f"{path}[{index}]") for index, item in enumerate(value)]
    raise TypeError(
        f"{path} contains unsupported {type(value).__module__}.{type(value).__qualname__}; "
        "pass a stable JSON-safe production_options mapping"
    )


def canonical_json(value: object) -> str:
    """Return the canonical JSON spelling used for cache identity."""

    return json.dumps(
        _json_value(value),
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def available_board_hash(board: object) -> str | None:
    """Read a board hash already exposed by ``board`` without filesystem I/O.

    Board adapters in different investigation harnesses expose different
    names.  We accept those names when they contain a non-empty string; an
    explicit hash can always be supplied to :func:`deletion_probe_key`.
    Reading a path or hashing an implicit file here would make cache identity
    surprising, so this helper intentionally does not inspect the filesystem.
    """

    for name in ("board_sha256", "sha256", "content_hash"):
        value = getattr(board, name, None)
        if isinstance(value, str) and value.strip():
            return value.strip().lower()
    return None


@dataclass(frozen=True, slots=True)
class DeletionProbeKey:
    """Canonical identity of one unconditional deletion probe."""

    released_refs: tuple[str, ...]
    base_radius_mm: float
    release_radius_mm: float
    production_options: Mapping[str, object] = field(default_factory=dict)
    board_hash: str | None = None

    def __post_init__(self) -> None:
        refs = tuple(sorted(self.released_refs))
        if any(not isinstance(ref, str) or not ref.strip() for ref in refs):
            raise ValueError("released_refs must contain non-empty strings")
        if len(set(refs)) != len(refs):
            raise ValueError("released_refs must not contain duplicates")
        base = float(self.base_radius_mm)
        release = float(self.release_radius_mm)
        if not math.isfinite(base) or base < 0.0:
            raise ValueError("base_radius_mm must be finite and non-negative")
        if not math.isfinite(release) or release <= base:
            raise ValueError("release_radius_mm must be finite and greater than base_radius_mm")
        if isinstance(self.production_options, (str, bytes)) or not isinstance(self.production_options, Mapping):
            raise TypeError("production_options must be a mapping")
        options = _json_value(self.production_options, path="production_options")
        board_hash = self.board_hash
        if board_hash is not None and (not isinstance(board_hash, str) or not board_hash.strip()):
            raise ValueError("board_hash must be a non-empty string or None")
        object.__setattr__(self, "released_refs", refs)
        object.__setattr__(self, "base_radius_mm", base)
        object.__setattr__(self, "release_radius_mm", release)
        object.__setattr__(self, "production_options", options)
        object.__setattr__(self, "board_hash", board_hash.strip().lower() if board_hash else None)

    def to_dict(self) -> dict[str, object]:
        return {
            "released_refs": list(self.released_refs),
            "base_radius_mm": self.base_radius_mm,
            "release_radius_mm": self.release_radius_mm,
            "production_options": self.production_options,
            "board_hash": self.board_hash,
        }

    @property
    def canonical(self) -> str:
        return canonical_json(self.to_dict())

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.canonical.encode("utf-8")).hexdigest()

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> DeletionProbeKey:
        try:
            return cls(
                tuple(payload["released_refs"]),  # type: ignore[arg-type]
                float(payload["base_radius_mm"]),
                float(payload["release_radius_mm"]),
                payload["production_options"],  # type: ignore[arg-type]
                payload.get("board_hash"),  # type: ignore[arg-type]
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"invalid deletion probe key: {exc}") from exc


@dataclass(frozen=True, slots=True)
class DeletionProbeRecord:
    """Plain-data result of a deletion probe, suitable for JSON storage."""

    key: DeletionProbeKey
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
        for ref, position in self.positions.items():
            if not isinstance(ref, str) or not isinstance(position, Sequence) or len(position) != 2:
                raise ValueError("positions must map refs to two-coordinate sequences")
            if any(not isinstance(value, (int, float)) or not math.isfinite(float(value)) for value in position):
                raise ValueError("positions must contain finite numeric coordinates")
        for ref, rotation in self.rotations.items():
            if not isinstance(ref, str) or isinstance(rotation, bool) or not isinstance(rotation, int):
                raise ValueError("rotations must map refs to integer angles")
        if self.verification_passed is not None and not isinstance(self.verification_passed, bool):
            raise TypeError("verification_passed must be bool or None")
        if self.violation_count is not None and (
            isinstance(self.violation_count, bool)
            or not isinstance(self.violation_count, int)
            or self.violation_count < 0
        ):
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
            "positions": {ref: list(position) for ref, position in sorted(self.positions.items())},
            "rotations": dict(sorted(self.rotations.items())),
            "verification_passed": self.verification_passed,
            "violation_count": self.violation_count,
            "diagnostics": list(self.diagnostics),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> DeletionProbeRecord:
        try:
            status = RestorationStageStatus(payload["status"])
            raw_diagnostics = payload.get("diagnostics", ())
            if isinstance(raw_diagnostics, (str, bytes)) or not isinstance(raw_diagnostics, Sequence):
                raise TypeError("diagnostics must be a sequence")
            diagnostics = tuple(raw_diagnostics)
            raw_positions = payload.get("positions", {})
            raw_rotations = payload.get("rotations", {})
            if not isinstance(raw_positions, Mapping) or not isinstance(raw_rotations, Mapping):
                raise TypeError("positions and rotations must be mappings")
            return cls(
                DeletionProbeKey.from_dict(payload["key"]),  # type: ignore[arg-type]
                status,
                float(payload["elapsed_s"]),
                payload.get("solver_status"),  # type: ignore[arg-type]
                {ref: tuple(position) for ref, position in raw_positions.items()},  # type: ignore[arg-type]
                raw_rotations,
                payload.get("verification_passed"),  # type: ignore[arg-type]
                payload.get("violation_count"),  # type: ignore[arg-type]
                diagnostics,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"invalid deletion probe record: {exc}") from exc


@dataclass(frozen=True, slots=True)
class DeletionSearchFrontier:
    """Immutable collection of cached deletion-probe records."""

    records: tuple[DeletionProbeRecord, ...] = ()

    def __post_init__(self) -> None:
        by_key: dict[str, DeletionProbeRecord] = {}
        for record in self.records:
            if not isinstance(record, DeletionProbeRecord):
                raise TypeError("frontier records must be DeletionProbeRecord values")
            by_key[record.key.canonical] = record
        object.__setattr__(self, "records", tuple(by_key[key] for key in sorted(by_key)))

    def lookup(self, key: DeletionProbeKey) -> DeletionProbeRecord | None:
        wanted = key.canonical
        return next((record for record in self.records if record.key.canonical == wanted), None)

    def add(self, record: DeletionProbeRecord) -> DeletionSearchFrontier:
        return DeletionSearchFrontier((*self.records, record))

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": FRONTIER_SCHEMA,
            "version": FRONTIER_VERSION,
            "records": [record.to_dict() for record in self.records],
        }

    def to_json(self) -> str:
        return canonical_json(self.to_dict())

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> DeletionSearchFrontier:
        if payload.get("schema") != FRONTIER_SCHEMA or payload.get("version") != FRONTIER_VERSION:
            raise ValueError("unsupported deletion frontier schema or version")
        raw_records = payload.get("records")
        if isinstance(raw_records, (str, bytes)) or not isinstance(raw_records, Sequence):
            raise ValueError("deletion frontier records must be a sequence")
        return cls(tuple(DeletionProbeRecord.from_dict(record) for record in raw_records))  # type: ignore[arg-type]

    @classmethod
    def from_json(cls, text: str) -> DeletionSearchFrontier:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid deletion frontier JSON: {exc}") from exc
        if not isinstance(payload, Mapping):
            raise ValueError("deletion frontier JSON root must be an object")
        return cls.from_dict(payload)

    @classmethod
    def read(cls, path: str | Path) -> DeletionSearchFrontier:
        return cls.from_json(Path(path).read_text(encoding="utf-8"))

    def write(self, path: str | Path) -> None:
        """Atomically persist the canonical frontier JSON."""

        destination = Path(path)
        temporary = destination.with_name(f".{destination.name}.tmp")
        temporary.write_text(self.to_json() + "\n", encoding="utf-8")
        os.replace(temporary, destination)


def deletion_probe_key(
    released_refs: Sequence[str],
    *,
    base_radius_mm: float,
    release_radius_mm: float,
    production_options: Mapping[str, object],
    board: object | None = None,
    board_hash: str | None = None,
) -> DeletionProbeKey:
    """Build a deletion key, using an explicit hash before board metadata."""

    return DeletionProbeKey(
        tuple(released_refs),
        base_radius_mm,
        release_radius_mm,
        production_options,
        board_hash if board_hash is not None else available_board_hash(board),
    )


# Investigation-facing names.  Keep aliases rather than duplicate record
# implementations so serialization and lookup semantics have one owner.
DeletionSearchKey = DeletionProbeKey
DeletionSearchFrontierRecord = DeletionProbeRecord


__all__ = [
    "FRONTIER_SCHEMA",
    "FRONTIER_VERSION",
    "DeletionProbeKey",
    "DeletionProbeRecord",
    "DeletionSearchKey",
    "DeletionSearchFrontier",
    "DeletionSearchFrontierRecord",
    "available_board_hash",
    "canonical_json",
    "deletion_probe_key",
]
