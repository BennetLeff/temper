"""Append-only storage for the ledger and the in-flight journal.

Two files, both append-only, both canonical JSON Lines:

``ledger.jsonl``
    Durable facts: ``root_opened``, ``session_registered``, and exactly one
    ``call_terminal`` record per attempted call (R3).

``inflight.jsonl``
    One ``call_opened`` record per call, written before the request is sent.
    This is the crash-visible half of the ledger: an ``OSError`` or a killed
    worker cannot close a row, so the absence of the matching terminal record
    is the evidence (KTD5). The two facts live in two records because an
    append-only file cannot close a row in place.

Writes go through a single ``os.write`` on a descriptor opened ``O_APPEND``, so
a concurrent appender cannot interleave a partial line.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from temper_harness.ledger.errors import UnresolvedLineageError
from temper_harness.schema_registry import build_validator

LEDGER_FILENAME = "ledger.jsonl"
INFLIGHT_FILENAME = "inflight.jsonl"


def _load_validator() -> Draft202012Validator:
    """Build the ledger-record validator from the committed schema files.

    The schema is read from disk rather than reconstructed in Python: R14
    requires committed schema files, and an inline version constant is the
    named anti-pattern this package exists to replace.
    """
    return build_validator("ledger_row.schema.json")


_VALIDATOR = _load_validator()


def validate_record(record: dict[str, Any]) -> None:
    """Raise ``jsonschema.ValidationError`` if ``record`` is not schema-valid."""
    _VALIDATOR.validate(record)


def canonical_line(record: dict[str, Any]) -> bytes:
    """Serialize one record as a canonical JSON line.

    ``sort_keys`` is load-bearing: the ledger is a determinism-bearing artifact,
    and an unsorted dict would carry the interpreter's insertion order into it.
    """
    return (json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n").encode()


class LedgerStore:
    """Append-only ledger plus in-flight journal rooted at one directory."""

    def __init__(self, directory: Path | str) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self._ledger_path = self.directory / LEDGER_FILENAME
        self._inflight_path = self.directory / INFLIGHT_FILENAME
        self._seq = self._highest_seq()

    # -- writing ---------------------------------------------------------

    def _append(self, path: Path, record: dict[str, Any]) -> dict[str, Any]:
        record = {**record, "seq": self._seq}
        validate_record(record)
        data = canonical_line(record)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        try:
            os.write(fd, data)
            os.fsync(fd)
        finally:
            os.close(fd)
        self._seq += 1
        return record

    def append_ledger(self, record: dict[str, Any]) -> dict[str, Any]:
        return self._append(self._ledger_path, record)

    def append_inflight(self, record: dict[str, Any]) -> dict[str, Any]:
        # In-flight records are not call_terminal rows, so they carry their own
        # minimal shape rather than the ledger schema.
        record = {**record, "seq": self._seq}
        data = canonical_line(record)
        fd = os.open(self._inflight_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        try:
            os.write(fd, data)
            os.fsync(fd)
        finally:
            os.close(fd)
        self._seq += 1
        return record

    # -- reading ---------------------------------------------------------

    def _read(self, path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        records: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        return records

    def ledger_records(self) -> list[dict[str, Any]]:
        return self._read(self._ledger_path)

    def inflight_records(self) -> list[dict[str, Any]]:
        return self._read(self._inflight_path)

    def call_rows(self) -> list[dict[str, Any]]:
        """The ``call_terminal`` rows: one per attempted call (R3)."""
        return [r for r in self.ledger_records() if r.get("kind") == "call_terminal"]

    def root_ids(self) -> set[str]:
        return {r["root_id"] for r in self.ledger_records() if r.get("kind") == "root_opened"}

    def parent_of(self) -> dict[str, str | None]:
        """Registered session id -> its registered parent, or ``None``."""
        return {
            r["session_id"]: r["parent_session_id"]
            for r in self.ledger_records()
            if r.get("kind") == "session_registered"
        }

    def root_of_session(self) -> dict[str, str]:
        return {
            r["session_id"]: r["root_id"]
            for r in self.ledger_records()
            if r.get("kind") == "session_registered"
        }

    def resolve_root(self, session_id: str) -> str:
        """Walk a session's parent chain to its root, or raise.

        Fails closed on a missing link rather than returning ``None``, because
        an unattributable session is a defect the aggregate must surface.
        """
        parents = self.parent_of()
        roots = self.root_of_session()
        seen: set[str] = set()
        current = session_id
        while True:
            if current in seen:
                raise UnresolvedLineageError(f"lineage cycle at session {current!r}")
            seen.add(current)
            if current not in roots:
                raise UnresolvedLineageError(
                    f"session {current!r} is not registered; its chain does not reach a root"
                )
            parent = parents.get(current)
            if parent is None:
                return roots[current]
            current = parent

    def _highest_seq(self) -> int:
        highest = -1
        for record in self._read(self._ledger_path) + self._read(self._inflight_path):
            seq = record.get("seq")
            if isinstance(seq, int) and seq > highest:
                highest = seq
        return highest + 1
