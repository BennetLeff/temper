#!/usr/bin/env python3
"""Append-only, deterministic evidence ledger for Phase 6 R19 agreement.

Nightly jobs upload *candidate* JSON documents.  They are deliberately treated
as untrusted: this module validates their closed schema, derives eligibility,
streaks and the hash chain, and only then emits canonical JSONL.  A caller may
never supply any derived field in a candidate document.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

SCHEMA_VERSION = 1
GENESIS_SHA256 = "0" * 64
QUALIFICATION_BAR = 10
RESET_WINDOW_SLOTS = 14
RESET_BUDGET = 3

CONTRACT_COMPONENT_KEYS = {
    "test_names_sha256",
    "expected_failure_manifest_sha256",
    "native_args_sha256",
    "abi",
    "topology_sha256",
    "comparator_version",
}
RUNTIME_ARMS = {"immutable-worker", "local-node", "deployed-worker", "missing"}
EVENT_NAMES = {"schedule", "workflow_dispatch", "watchdog"}
INFRASTRUCTURE_OUTCOMES = {
    "success",
    "identity_mismatch",
    "timeout",
    "cancellation",
    "missing_result",
    "artifact_invalid",
    "workflow_failure",
}
INFRASTRUCTURE_RESETS = INFRASTRUCTURE_OUTCOMES - {"success"}

RAW_FIELDS = {
    "schema_version",
    "candidate",
    "runtime_arm",
    "expected_schedule_slot",
    "observed_at",
    "source_commit",
    "run_id",
    "run_attempt",
    "event_name",
    "comparison_contract",
    "wasm_sha256",
    "worker",
    "native",
    "worker_counts",
    "r19",
    "infrastructure_outcome",
}
DERIVED_FIELDS = {
    "sequence",
    "prior_row_sha256",
    "qualifying",
    "reset_reason",
    "derived_streak",
    "qualification_bar_met",
    "investigation_halt",
}
CANONICAL_FIELDS = RAW_FIELDS | DERIVED_FIELDS

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")


class LedgerError(ValueError):
    """The candidate or ledger violates the evidence contract."""


def canonical_line(value: Any) -> str:
    """Return the one permitted JSON representation (without its JSONL LF)."""
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise LedgerError(f"value is not canonical JSON: {exc}") from exc


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def row_sha256(row: dict[str, Any]) -> str:
    """Digest one canonical row, including the JSONL line terminator."""
    return _sha256_bytes((canonical_line(row) + "\n").encode())


def comparison_contract_digest(components: dict[str, str]) -> str:
    """Digest the closed set of inputs that defines R19 comparability."""
    if not isinstance(components, dict) or set(components) != CONTRACT_COMPONENT_KEYS:
        got = sorted(components) if isinstance(components, dict) else type(components).__name__
        raise LedgerError(
            f"comparison-contract component keys must be exactly "
            f"{sorted(CONTRACT_COMPONENT_KEYS)}; got {got}"
        )
    for key in (
        "test_names_sha256",
        "expected_failure_manifest_sha256",
        "native_args_sha256",
        "topology_sha256",
    ):
        _require_sha256(components[key], f"comparison_contract.components.{key}")
    for key in ("abi", "comparator_version"):
        if not isinstance(components[key], str) or not components[key].strip():
            raise LedgerError(f"comparison_contract.components.{key} must be non-empty")
    return _sha256_bytes(canonical_line(components).encode())


def _require_sha256(value: Any, field: str) -> None:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise LedgerError(f"{field} must be a lowercase 64-character SHA-256")


def _parse_timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise LedgerError(f"{field} must be an RFC3339 UTC timestamp ending in Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise LedgerError(f"{field} is not a valid RFC3339 timestamp") from exc
    if parsed.tzinfo != UTC:
        raise LedgerError(f"{field} must be UTC")
    return parsed


def _format_timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise LedgerError("timestamp must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _canonicalize_timestamp(value: str, field: str) -> str:
    """Accept an input UTC offset, but always persist the canonical Z form."""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise LedgerError(f"{field} is not a valid RFC3339 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise LedgerError(f"{field} must be UTC")
    return _format_timestamp(parsed)


def _require_nonnegative_int(value: Any, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise LedgerError(f"{field} must be a non-negative integer")


def _validate_counts(row: dict[str, Any]) -> None:
    expected_native = {"total", "passed", "failed"}
    expected_worker = {"total", "passed", "failed", "expected_fail", "unexpected"}
    expected_r19 = {
        "agree_pass",
        "agree_fail",
        "expected_fail",
        "unexpected_pass",
        "disagreement",
        "native_only",
        "wasm_only",
        "agreement_rate",
    }
    for field, expected in (
        ("native", expected_native),
        ("worker_counts", expected_worker),
        ("r19", expected_r19),
    ):
        value = row[field]
        if not isinstance(value, dict) or set(value) != expected:
            raise LedgerError(f"{field} keys must be exactly {sorted(expected)}")
        for key, count in value.items():
            if field == "r19" and key == "agreement_rate":
                if (
                    isinstance(count, bool)
                    or not isinstance(count, (int, float))
                    or not math.isfinite(count)
                    or not 0.0 <= count <= 1.0
                ):
                    raise LedgerError("r19.agreement_rate must be finite and in [0, 1]")
            else:
                _require_nonnegative_int(count, f"{field}.{key}")

    native = row["native"]
    worker = row["worker_counts"]
    r19 = row["r19"]
    if native["passed"] + native["failed"] != native["total"]:
        raise LedgerError("native passed + failed must equal native total")
    if (
        worker["passed"] + worker["failed"] + worker["expected_fail"] + worker["unexpected"]
        != worker["total"]
    ):
        raise LedgerError("Worker verdict counts must sum to worker total")
    in_both = sum(
        r19[key]
        for key in (
            "agree_pass",
            "agree_fail",
            "expected_fail",
            "unexpected_pass",
            "disagreement",
        )
    )
    if in_both + r19["native_only"] != native["total"]:
        raise LedgerError("R19 in-both + native-only must equal native total")
    if in_both + r19["wasm_only"] != worker["total"]:
        raise LedgerError("R19 in-both + wasm-only must equal Worker total")
    if r19["expected_fail"] != worker["expected_fail"]:
        raise LedgerError("R19 expected-fail must equal Worker expected-fail")
    if r19["unexpected_pass"] != worker["unexpected"]:
        raise LedgerError("R19 unexpected-pass must equal Worker unexpected")


def _validate_immutable_worker(worker: dict[str, Any]) -> None:
    if not all(isinstance(worker[key], str) and worker[key] for key in worker):
        raise LedgerError("successful immutable-worker rows require complete Worker identity")
    parsed = urlparse(worker["immutable_url"])
    hostname = parsed.hostname or ""
    version_token = re.sub(r"[^a-z0-9]", "", worker["version_id"].lower())
    hostname_token = re.sub(r"[^a-z0-9]", "", hostname.lower().split(".", 1)[0])
    if (
        parsed.scheme != "https"
        or parsed.path not in ("", "/")
        or not hostname.endswith(".workers.dev")
        or len(version_token) < 8
        or version_token[:8] not in hostname_token
    ):
        raise LedgerError("immutable_url must be a version-bound https workers.dev URL")


def _validate_candidate(row: dict[str, Any]) -> None:
    if not isinstance(row, dict):
        raise LedgerError("candidate row must be a JSON object")
    forbidden = set(row) & DERIVED_FIELDS
    if forbidden:
        raise LedgerError(f"candidate supplied derived fields: {sorted(forbidden)}")
    if set(row) != RAW_FIELDS:
        raise LedgerError(
            f"candidate fields must be exactly {sorted(RAW_FIELDS)}; got {sorted(row)}"
        )
    if row["schema_version"] != SCHEMA_VERSION:
        raise LedgerError(f"schema_version must be {SCHEMA_VERSION}")
    if not isinstance(row["candidate"], str) or not row["candidate"].strip():
        raise LedgerError("candidate must be non-empty")
    if row["runtime_arm"] not in RUNTIME_ARMS:
        raise LedgerError(f"unknown runtime_arm: {row['runtime_arm']!r}")
    if row["event_name"] not in EVENT_NAMES:
        raise LedgerError(f"unknown event_name: {row['event_name']!r}")
    _parse_timestamp(row["expected_schedule_slot"], "expected_schedule_slot")
    observed = _parse_timestamp(row["observed_at"], "observed_at")
    slot = _parse_timestamp(row["expected_schedule_slot"], "expected_schedule_slot")
    if observed < slot:
        raise LedgerError("observed_at cannot precede expected_schedule_slot")
    if not isinstance(row["run_id"], str) or not row["run_id"]:
        raise LedgerError("run_id must be a non-empty string")
    _require_nonnegative_int(row["run_attempt"], "run_attempt")
    if row["event_name"] != "watchdog" and row["run_attempt"] < 1:
        raise LedgerError("workflow run_attempt must be at least one")
    if row["infrastructure_outcome"] not in INFRASTRUCTURE_OUTCOMES:
        raise LedgerError(f"unknown infrastructure_outcome: {row['infrastructure_outcome']!r}")

    contract = row["comparison_contract"]
    is_missing = row["infrastructure_outcome"] == "missing_result"
    if is_missing:
        if contract != {"digest": None, "components": None}:
            raise LedgerError("missing-result rows must not invent a comparison contract")
    else:
        if not isinstance(contract, dict) or set(contract) != {"digest", "components"}:
            raise LedgerError("comparison_contract must contain digest and components")
        digest = comparison_contract_digest(contract["components"])
        if contract["digest"] != digest:
            raise LedgerError("comparison-contract digest does not match its components")

    if is_missing:
        if row["source_commit"] is not None or row["wasm_sha256"] is not None:
            raise LedgerError("missing-result rows cannot claim source or Wasm identity")
    else:
        if (
            not isinstance(row["source_commit"], str)
            or _COMMIT_RE.fullmatch(row["source_commit"]) is None
        ):
            raise LedgerError(
                "source_commit must be a full lowercase 40- or 64-character hex digest"
            )
        if row["wasm_sha256"] is not None:
            _require_sha256(row["wasm_sha256"], "wasm_sha256")

    worker = row["worker"]
    if not isinstance(worker, dict) or set(worker) != {"service", "version_id", "immutable_url"}:
        raise LedgerError("worker must contain service, version_id, and immutable_url")
    if row["runtime_arm"] == "immutable-worker" and row["infrastructure_outcome"] == "success":
        _require_sha256(row["wasm_sha256"], "wasm_sha256")
        _validate_immutable_worker(worker)
    else:
        for value in worker.values():
            if value is not None and (not isinstance(value, str) or not value):
                raise LedgerError("Worker identity values must be non-empty strings or null")
    _validate_counts(row)


def validate_source_run(
    candidate: dict[str, Any],
    metadata: dict[str, Any],
    *,
    workflow_path: str,
    branch: str,
) -> None:
    """Bind an untrusted candidate to GitHub's authoritative workflow-run record."""
    _validate_candidate(candidate)
    if not isinstance(metadata, dict):
        raise LedgerError("workflow-run metadata must be a JSON object")
    expected = {
        "run_id": str(metadata.get("id", "")),
        "run_attempt": metadata.get("run_attempt"),
        "event_name": metadata.get("event"),
        "source_commit": metadata.get("head_sha"),
    }
    for field, value in expected.items():
        if candidate[field] != value:
            raise LedgerError(
                f"candidate {field} does not match authoritative workflow-run metadata"
            )
    if metadata.get("path") != workflow_path:
        raise LedgerError("source run did not execute the trusted nightly workflow path")
    if metadata.get("head_branch") != branch:
        raise LedgerError("source run did not execute on the trusted nightly branch")
    if metadata.get("status") != "completed":
        raise LedgerError("source workflow run is not completed")
    if metadata.get("conclusion") not in {
        "success", "failure", "timed_out", "cancelled", "action_required", "neutral"
    }:
        raise LedgerError("source workflow run has no terminal conclusion")
    head_repository = metadata.get("head_repository")
    repository = metadata.get("repository")
    if (
        not isinstance(head_repository, dict)
        or not isinstance(repository, dict)
        or head_repository.get("full_name") != repository.get("full_name")
    ):
        raise LedgerError("source workflow run did not execute from the base repository")
    if candidate["event_name"] == "schedule":
        created = _parse_timestamp(metadata.get("created_at"), "workflow_run.created_at")
        expected_slot = created.astimezone(UTC).strftime("%Y-%m-%dT04:40:00Z")
        if candidate["expected_schedule_slot"] != expected_slot:
            raise LedgerError(
                "candidate expected_schedule_slot does not match the scheduled source run"
            )


def _raw(row: dict[str, Any]) -> dict[str, Any]:
    return {key: copy_value(row[key]) for key in RAW_FIELDS}


def copy_value(value: Any) -> Any:
    """JSON-shaped deep copy without accepting non-JSON Python objects."""
    return json.loads(canonical_line(value))


def _idempotency_key(row: dict[str, Any]) -> tuple[str, str, str, int]:
    return (
        row["candidate"],
        row["expected_schedule_slot"],
        row["run_id"],
        row["run_attempt"],
    )


def _ordering_key(row: dict[str, Any]) -> tuple[str, str, str, int]:
    return (
        row["expected_schedule_slot"],
        row["candidate"],
        row["run_id"],
        row["run_attempt"],
    )


def _r19_reset_reason(row: dict[str, Any]) -> str | None:
    r19 = row["r19"]
    for field, reason in (
        ("disagreement", "disagreement"),
        ("unexpected_pass", "unexpected_pass"),
        ("native_only", "native_only"),
        ("wasm_only", "wasm_only"),
    ):
        if r19[field] != 0:
            return reason
    if r19["agreement_rate"] != 1.0:
        return "agreement_rate_below_one"
    return None


def _build_ledger(candidates: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: dict[tuple[str, str, str, int], str] = {}
    last_order: tuple[str, str, str, int] | None = None
    state: dict[str, dict[str, Any]] = {}

    for supplied in candidates:
        candidate = copy_value(supplied)
        _validate_candidate(candidate)
        key = _idempotency_key(candidate)
        fingerprint = canonical_line(candidate)
        if key in seen:
            if seen[key] != fingerprint:
                raise LedgerError(f"conflicting duplicate idempotency key: {key}")
            continue
        order = _ordering_key(candidate)
        if last_order is not None and order <= last_order:
            raise LedgerError(f"candidate is out of order: {order} follows {last_order}")
        last_order = order
        seen[key] = fingerprint

        candidate_state = state.setdefault(
            candidate["candidate"],
            {
                "streak": 0,
                "contract": None,
                "sources": set(),
                "wasm": set(),
                "infra_slots": [],
                "halted": False,
            },
        )
        is_expected_slot = (
            candidate["event_name"] == "schedule" and candidate["run_attempt"] == 1
        ) or candidate["event_name"] == "watchdog"
        is_infra_reset = candidate["infrastructure_outcome"] in INFRASTRUCTURE_RESETS
        slot = candidate["expected_schedule_slot"]
        if is_expected_slot and not any(
            recorded_slot == slot for recorded_slot, _ in candidate_state["infra_slots"]
        ):
            candidate_state["infra_slots"].append((slot, is_infra_reset))
            candidate_state["infra_slots"] = candidate_state["infra_slots"][-RESET_WINDOW_SLOTS:]
        if sum(reset for _, reset in candidate_state["infra_slots"]) >= RESET_BUDGET:
            candidate_state["halted"] = True
        halted = candidate_state["halted"]

        qualifying = False
        reason: str | None = None
        if candidate["infrastructure_outcome"] != "success":
            reason = candidate["infrastructure_outcome"]
            candidate_state["streak"] = 0
            candidate_state["sources"].clear()
            candidate_state["wasm"].clear()
        elif (r19_reason := _r19_reset_reason(candidate)) is not None:
            # A manual anti-vacuity injection is still evidence that the
            # comparison can fail.  Classify resets before diagnostic-only
            # execution modes so they cannot preserve an earned streak.
            reason = r19_reason
            candidate_state["streak"] = 0
            candidate_state["sources"].clear()
            candidate_state["wasm"].clear()
        elif candidate["event_name"] == "workflow_dispatch":
            reason = "manual_dispatch"
        elif candidate["run_attempt"] != 1:
            reason = "rerun"
        elif candidate["runtime_arm"] != "immutable-worker":
            reason = "non_immutable_runtime"
        elif halted:
            reason = "infrastructure_reset_budget"
            candidate_state["streak"] = 0
            candidate_state["sources"].clear()
            candidate_state["wasm"].clear()
        else:
            contract_digest = candidate["comparison_contract"]["digest"]
            if candidate_state["contract"] not in (None, contract_digest):
                reason = "comparison_contract_changed"
                candidate_state["streak"] = 0
                candidate_state["sources"].clear()
                candidate_state["wasm"].clear()
            candidate_state["contract"] = contract_digest
            if (
                candidate["source_commit"] in candidate_state["sources"]
                or candidate["wasm_sha256"] in candidate_state["wasm"]
            ):
                reason = "repeated_source_bytes"
            else:
                qualifying = True
                candidate_state["streak"] += 1
                candidate_state["sources"].add(candidate["source_commit"])
                candidate_state["wasm"].add(candidate["wasm_sha256"])

        row = {
            **candidate,
            "sequence": len(rows) + 1,
            "prior_row_sha256": GENESIS_SHA256 if not rows else row_sha256(rows[-1]),
            "qualifying": qualifying,
            "reset_reason": reason,
            "derived_streak": candidate_state["streak"],
            "qualification_bar_met": (
                candidate_state["streak"] >= QUALIFICATION_BAR and not halted
            ),
            "investigation_halt": halted,
        }
        rows.append(row)
    return rows


def rebuild_ledger(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rebuild all derived state from raw fields only."""
    candidates: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != CANONICAL_FIELDS:
            raise LedgerError(f"canonical row fields must be exactly {sorted(CANONICAL_FIELDS)}")
        candidates.append(_raw(row))
    return _build_ledger(candidates)


def validate_ledger(rows: list[dict[str, Any]]) -> None:
    """Fail unless every stored byte-level value is the deterministic rebuild."""
    rebuilt = rebuild_ledger(rows)
    for index, (stored, derived) in enumerate(zip(rows, rebuilt, strict=True), start=1):
        if canonical_line(stored) != canonical_line(derived):
            mismatches = sorted(
                key for key in CANONICAL_FIELDS if stored.get(key) != derived.get(key)
            )
            if set(mismatches) & DERIVED_FIELDS:
                raise LedgerError(
                    f"row {index} has stored derived fields that do not match rebuild: {mismatches}"
                )
            raise LedgerError(f"row {index} differs from canonical rebuild: {mismatches}")


def validate_append_only(
    previous_rows: list[dict[str, Any]], current_rows: list[dict[str, Any]]
) -> None:
    """Require ``current_rows`` to preserve every canonical prior row as a prefix."""
    validate_ledger(previous_rows)
    validate_ledger(current_rows)
    if len(current_rows) < len(previous_rows):
        raise LedgerError("ledger is not append-only: prior tail was deleted")
    for index, previous in enumerate(previous_rows):
        if canonical_line(previous) != canonical_line(current_rows[index]):
            raise LedgerError(f"ledger is not append-only: row {index + 1} was rewritten")


def append_candidates(
    existing_rows: list[dict[str, Any]], candidates: Iterable[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Validate existing history, append candidates idempotently, and rebuild."""
    validate_ledger(existing_rows)
    combined = [_raw(row) for row in existing_rows]
    existing_by_key = {_idempotency_key(row): canonical_line(_raw(row)) for row in existing_rows}
    for candidate in candidates:
        normalized = copy_value(candidate)
        _validate_candidate(normalized)
        key = _idempotency_key(normalized)
        if key in existing_by_key:
            if existing_by_key[key] != canonical_line(normalized):
                raise LedgerError(f"conflicting duplicate idempotency key: {key}")
            continue
        combined.append(normalized)
        existing_by_key[key] = canonical_line(normalized)
    return _build_ledger(combined)


def synthesize_missing_candidates(
    *,
    candidate: str,
    expected_slots: Iterable[datetime],
    run_census: Iterable[dict[str, Any]],
    existing_rows: list[dict[str, Any]],
    now: datetime,
    grace: timedelta,
) -> list[dict[str, Any]]:
    """Represent absent scheduled workflow starts after a bounded grace period."""
    validate_ledger(existing_rows)
    if now.tzinfo is None:
        raise LedgerError("watchdog now must be timezone-aware")
    represented = {
        row["expected_schedule_slot"] for row in existing_rows if row["candidate"] == candidate
    }
    census = list(run_census)
    completed_by_slot: dict[str, dict[str, Any]] = {}
    for entry in census:
        if entry.get("event") != "schedule" or entry.get("status") != "completed":
            continue
        slot_text = entry.get("expected_schedule_slot")
        if not isinstance(slot_text, str):
            continue
        current = completed_by_slot.get(slot_text)
        entry_key = (entry.get("run_attempt", 0), str(entry.get("run_id", "")))
        current_key = (
            (current or {}).get("run_attempt", 0),
            str((current or {}).get("run_id", "")),
        )
        if current is None or entry_key > current_key:
            completed_by_slot[slot_text] = entry
    missing: list[dict[str, Any]] = []
    for slot in sorted(expected_slots):
        slot_text = _format_timestamp(slot)
        deadline = slot.astimezone(UTC) + grace
        if slot_text in represented or now.astimezone(UTC) < deadline:
            continue
        completed = completed_by_slot.get(slot_text)
        completed_run_id = (completed or {}).get("run_id")
        completed_attempt = (completed or {}).get("run_attempt")
        run_id = (
            str(completed_run_id)
            if isinstance(completed_run_id, (str, int)) and str(completed_run_id)
            else f"0:missing:{slot_text}"
        )
        run_attempt = (
            completed_attempt
            if isinstance(completed_attempt, int) and not isinstance(completed_attempt, bool)
            and completed_attempt >= 0
            else 0
        )
        missing.append(
            {
                "schema_version": SCHEMA_VERSION,
                "candidate": candidate,
                "runtime_arm": "missing",
                "expected_schedule_slot": slot_text,
                "observed_at": _format_timestamp(deadline),
                "source_commit": None,
                "run_id": run_id,
                "run_attempt": run_attempt,
                "event_name": "watchdog",
                "comparison_contract": {"digest": None, "components": None},
                "wasm_sha256": None,
                "worker": {"service": None, "version_id": None, "immutable_url": None},
                "native": {"total": 0, "passed": 0, "failed": 0},
                "worker_counts": {
                    "total": 0,
                    "passed": 0,
                    "failed": 0,
                    "expected_fail": 0,
                    "unexpected": 0,
                },
                "r19": {
                    "agree_pass": 0,
                    "agree_fail": 0,
                    "expected_fail": 0,
                    "unexpected_pass": 0,
                    "disagreement": 0,
                    "native_only": 0,
                    "wasm_only": 0,
                    "agreement_rate": 0.0,
                },
                "infrastructure_outcome": "missing_result",
            }
        )
    return missing


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            raise LedgerError(f"blank JSONL line at {path}:{line_number}")
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise LedgerError(f"invalid JSON at {path}:{line_number}: {exc}") from exc
        if canonical_line(value) != line:
            raise LedgerError(f"non-canonical JSON at {path}:{line_number}")
        rows.append(value)
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = "".join(canonical_line(row) + "\n" for row in rows)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(data)
    temporary.replace(path)


def _load_candidate_documents(path: Path) -> list[dict[str, Any]]:
    value = json.loads(path.read_text())
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    raise LedgerError(f"candidate artifact {path} must contain an object or list")


def _candidate_from_r19(args: argparse.Namespace) -> dict[str, Any]:
    matrix = json.loads(args.matrix.read_text())
    wasm = json.loads(args.wasm_json.read_text())
    test_names = sorted({result["name"] for result in wasm.get("results", [])})
    if not test_names:
        raise LedgerError("Wasm result contains no executable test names")
    topology = json.loads(args.topology.read_text())
    tier = next(
        (item for item in topology.get("tiers", []) if item.get("crate") == args.candidate), None
    )
    if tier is None:
        raise LedgerError(f"candidate {args.candidate!r} is absent from topology")
    native_args = json.loads(args.native_args_json)
    if not isinstance(native_args, list) or not all(
        isinstance(value, str) for value in native_args
    ):
        raise LedgerError("--native-args-json must be a JSON string array")
    components = {
        "test_names_sha256": _sha256_bytes(canonical_line(test_names).encode()),
        "expected_failure_manifest_sha256": _sha256_bytes(args.expected_failures.read_bytes()),
        "native_args_sha256": _sha256_bytes(canonical_line(native_args).encode()),
        "abi": args.abi,
        "topology_sha256": _sha256_bytes(canonical_line(tier).encode()),
        "comparator_version": f"r19_compare.py@{_sha256_bytes(args.comparator.read_bytes())}",
    }
    comparison = matrix["comparison"]
    worker_counts = matrix["wasm32"]
    worker = {
        "service": args.worker_service,
        "version_id": args.worker_version_id,
        "immutable_url": args.immutable_url,
    }
    if args.runtime_arm != "immutable-worker":
        worker = {"service": None, "version_id": None, "immutable_url": None}
    return {
        "schema_version": SCHEMA_VERSION,
        "candidate": args.candidate,
        "runtime_arm": args.runtime_arm,
        "expected_schedule_slot": _canonicalize_timestamp(args.expected_slot, "expected_slot"),
        "observed_at": _canonicalize_timestamp(
            args.observed_at or matrix["timestamp"], "observed_at"
        ),
        "source_commit": args.source_commit,
        "run_id": args.run_id,
        "run_attempt": args.run_attempt,
        "event_name": args.event_name,
        "comparison_contract": {
            "digest": comparison_contract_digest(components),
            "components": components,
        },
        "wasm_sha256": _sha256_bytes(args.wasm_file.read_bytes()),
        "worker": worker,
        "native": matrix["native"],
        "worker_counts": worker_counts,
        "r19": {
            "agree_pass": comparison["agree_pass"],
            "agree_fail": comparison["agree_fail"],
            "expected_fail": comparison["expected_fail"],
            "unexpected_pass": comparison["unexpected_pass"],
            "disagreement": comparison["disagree"],
            "native_only": comparison["native_only"],
            "wasm_only": comparison["wasm32_only"],
            "agreement_rate": comparison["agreement_rate"],
        },
        "infrastructure_outcome": args.infrastructure_outcome,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate", help="validate and rebuild a canonical ledger")
    validate.add_argument("--ledger", type=Path, required=True)

    append_only = sub.add_parser(
        "validate-append-only", help="prove a candidate ledger preserves a trusted prefix"
    )
    append_only.add_argument("--previous", type=Path, required=True)
    append_only.add_argument("--ledger", type=Path, required=True)

    append = sub.add_parser("append", help="append one or more untrusted candidate artifacts")
    append.add_argument("--ledger", type=Path, required=True)
    append.add_argument("--candidate", type=Path, action="append", required=True)

    source_run = sub.add_parser(
        "validate-source-run", help="bind one candidate to authoritative Actions metadata"
    )
    source_run.add_argument("--candidate", type=Path, required=True)
    source_run.add_argument("--run-metadata", type=Path, required=True)
    source_run.add_argument("--workflow-path", required=True)
    source_run.add_argument("--branch", required=True)

    watchdog = sub.add_parser("watchdog", help="append missing-result rows after grace")
    watchdog.add_argument("--ledger", type=Path, required=True)
    watchdog.add_argument("--candidate-name", required=True)
    watchdog.add_argument("--expected-slot", action="append", required=True)
    watchdog.add_argument("--run-census", type=Path, required=True)
    watchdog.add_argument("--now", required=True)
    watchdog.add_argument("--grace-minutes", type=int, default=90)

    produce = sub.add_parser("candidate-from-r19", help="make a diagnostic or immutable candidate")
    produce.add_argument("--matrix", type=Path, required=True)
    produce.add_argument("--wasm-json", type=Path, required=True)
    produce.add_argument("--wasm-file", type=Path, required=True)
    produce.add_argument("--expected-failures", type=Path, required=True)
    produce.add_argument("--topology", type=Path, required=True)
    produce.add_argument("--comparator", type=Path, required=True)
    produce.add_argument("--candidate", required=True)
    produce.add_argument("--runtime-arm", choices=sorted(RUNTIME_ARMS), required=True)
    produce.add_argument("--expected-slot", required=True)
    produce.add_argument("--observed-at")
    produce.add_argument("--source-commit", required=True)
    produce.add_argument("--run-id", required=True)
    produce.add_argument("--run-attempt", type=int, required=True)
    produce.add_argument("--event-name", choices=sorted(EVENT_NAMES), required=True)
    produce.add_argument("--native-args-json", required=True)
    produce.add_argument("--abi", required=True)
    produce.add_argument("--worker-service")
    produce.add_argument("--worker-version-id")
    produce.add_argument("--immutable-url")
    produce.add_argument(
        "--infrastructure-outcome", choices=sorted(INFRASTRUCTURE_OUTCOMES), default="success"
    )
    produce.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "validate":
            rows = load_jsonl(args.ledger)
            validate_ledger(rows)
            print(f"validated {len(rows)} canonical R19 ledger row(s)")
        elif args.command == "validate-append-only":
            previous = load_jsonl(args.previous)
            current = load_jsonl(args.ledger)
            validate_append_only(previous, current)
            print(
                f"validated append-only prefix of {len(previous)} row(s); "
                f"ledger has {len(current)}"
            )
        elif args.command == "append":
            before = load_jsonl(args.ledger)
            candidates = [row for path in args.candidate for row in _load_candidate_documents(path)]
            after = append_candidates(before, candidates)
            write_jsonl(args.ledger, after)
            print(f"accepted {len(after) - len(before)} new row(s); ledger has {len(after)}")
        elif args.command == "validate-source-run":
            candidates = _load_candidate_documents(args.candidate)
            if len(candidates) != 1:
                raise LedgerError("source-run validation requires exactly one candidate row")
            validate_source_run(
                candidates[0],
                json.loads(args.run_metadata.read_text()),
                workflow_path=args.workflow_path,
                branch=args.branch,
            )
            print("candidate matches authoritative workflow-run metadata")
        elif args.command == "watchdog":
            before = load_jsonl(args.ledger)
            census_value = json.loads(args.run_census.read_text())
            census = (
                census_value.get("workflow_runs", census_value)
                if isinstance(census_value, dict)
                else census_value
            )
            missing = synthesize_missing_candidates(
                candidate=args.candidate_name,
                expected_slots=[
                    _parse_timestamp(value, "expected_slot") for value in args.expected_slot
                ],
                run_census=census,
                existing_rows=before,
                now=_parse_timestamp(args.now, "now"),
                grace=timedelta(minutes=args.grace_minutes),
            )
            after = append_candidates(before, missing)
            write_jsonl(args.ledger, after)
            print(f"accepted {len(after) - len(before)} missing-result row(s)")
        else:
            candidate = _candidate_from_r19(args)
            _validate_candidate(candidate)
            args.output.write_text(canonical_line(candidate) + "\n")
            print(f"wrote {args.output}")
    except (LedgerError, KeyError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
