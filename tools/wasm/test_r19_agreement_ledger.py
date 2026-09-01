from __future__ import annotations

import copy
import json
from datetime import UTC, datetime, timedelta

import pytest
from r19_agreement_ledger import (
    GENESIS_SHA256,
    LedgerError,
    append_candidates,
    canonical_line,
    comparison_contract_digest,
    rebuild_ledger,
    row_sha256,
    synthesize_missing_candidates,
    validate_append_only,
    validate_ledger,
)

SLOT = datetime(2026, 9, 1, 4, 40, tzinfo=UTC)


def _components(*, abi: str = "temper-worker-abi-v1") -> dict[str, str]:
    return {
        "test_names_sha256": "1" * 64,
        "expected_failure_manifest_sha256": "2" * 64,
        "native_args_sha256": "3" * 64,
        "abi": abi,
        "topology_sha256": "4" * 64,
        "comparator_version": "r19_compare.py@" + "5" * 64,
    }


def _candidate(
    n: int = 0,
    *,
    event_name: str = "schedule",
    run_attempt: int = 1,
    runtime_arm: str = "immutable-worker",
    infrastructure_outcome: str = "success",
    source_commit: str | None = None,
    wasm_sha256: str | None = None,
    components: dict[str, str] | None = None,
    r19: dict[str, int | float] | None = None,
) -> dict:
    slot = SLOT + timedelta(days=n)
    parts = components or _components()
    row = {
        "schema_version": 1,
        "candidate": "temper-io-types",
        "runtime_arm": runtime_arm,
        "expected_schedule_slot": slot.isoformat().replace("+00:00", "Z"),
        "observed_at": (slot + timedelta(minutes=17)).isoformat().replace("+00:00", "Z"),
        "source_commit": source_commit or f"{n + 10:040x}",
        "run_id": str(9000 + n),
        "run_attempt": run_attempt,
        "event_name": event_name,
        "comparison_contract": {
            "digest": comparison_contract_digest(parts),
            "components": parts,
        },
        "wasm_sha256": wasm_sha256 or f"{n + 100:064x}",
        "worker": {
            "service": "temper-wasm-io-types",
            "version_id": f"version-{n}",
            "immutable_url": f"https://version-{n}-temper-wasm-io-types.example.workers.dev",
        },
        "native": {"total": 4, "passed": 4, "failed": 0},
        "worker_counts": {
            "total": 4,
            "passed": 4,
            "failed": 0,
            "expected_fail": 0,
            "unexpected": 0,
        },
        "r19": r19
        or {
            "agree_pass": 4,
            "agree_fail": 0,
            "expected_fail": 0,
            "unexpected_pass": 0,
            "disagreement": 0,
            "native_only": 0,
            "wasm_only": 0,
            "agreement_rate": 1.0,
        },
        "infrastructure_outcome": infrastructure_outcome,
    }
    if infrastructure_outcome != "success":
        row["worker"] = {"service": None, "version_id": None, "immutable_url": None}
        row["wasm_sha256"] = None
    return row


def test_happy_path_derives_streak_and_chain() -> None:
    rows = append_candidates([], [_candidate(0), _candidate(1)])

    assert [row["derived_streak"] for row in rows] == [1, 2]
    assert all(row["qualifying"] for row in rows)
    assert rows[0]["sequence"] == 1
    assert rows[0]["prior_row_sha256"] == GENESIS_SHA256
    assert rows[1]["prior_row_sha256"] == row_sha256(rows[0])
    validate_ledger(rows)


def test_duplicate_is_idempotent_but_conflicting_duplicate_is_rejected() -> None:
    candidate = _candidate()
    rows = append_candidates([], [candidate, copy.deepcopy(candidate)])
    assert len(rows) == 1

    conflict = copy.deepcopy(candidate)
    conflict["observed_at"] = "2026-09-01T05:00:00Z"
    with pytest.raises(LedgerError, match="conflicting duplicate"):
        append_candidates(rows, [conflict])


def test_out_of_order_candidate_is_rejected() -> None:
    rows = append_candidates([], [_candidate(1)])
    with pytest.raises(LedgerError, match="out of order"):
        append_candidates(rows, [_candidate(0)])


@pytest.mark.parametrize(
    ("event_name", "attempt", "reason"),
    [("workflow_dispatch", 1, "manual_dispatch"), ("schedule", 2, "rerun")],
)
def test_manual_and_rerun_rows_are_diagnostic(event_name: str, attempt: int, reason: str) -> None:
    first = append_candidates([], [_candidate(0)])
    diagnostic = _candidate(1, event_name=event_name, run_attempt=attempt)
    rows = append_candidates(first, [diagnostic])

    assert rows[-1]["qualifying"] is False
    assert rows[-1]["reset_reason"] == reason
    assert rows[-1]["derived_streak"] == 1


def test_manual_disagreement_resets_an_existing_streak() -> None:
    bad = _candidate(1, event_name="workflow_dispatch")
    bad["r19"].update({"agree_pass": 3, "disagreement": 1, "agreement_rate": 0.75})
    rows = append_candidates(append_candidates([], [_candidate(0)]), [bad])

    assert rows[-1]["qualifying"] is False
    assert rows[-1]["reset_reason"] == "disagreement"
    assert rows[-1]["derived_streak"] == 0


def test_validator_rejects_manual_row_edited_to_claim_eligibility() -> None:
    rows = append_candidates([], [_candidate(event_name="workflow_dispatch")])
    rows[0]["qualifying"] = True
    with pytest.raises(LedgerError, match="derived fields"):
        validate_ledger(rows)


@pytest.mark.parametrize(
    ("patch", "reason"),
    [
        ({"disagreement": 1, "agreement_rate": 0.75}, "disagreement"),
        ({"unexpected_pass": 1, "agreement_rate": 0.75}, "unexpected_pass"),
        ({"native_only": 1}, "native_only"),
        ({"wasm_only": 1}, "wasm_only"),
    ],
)
def test_r19_reset_outcomes_reset_streak(patch: dict, reason: str) -> None:
    bad = _candidate(1)
    bad["r19"].update(patch)
    if reason in {"disagreement", "unexpected_pass"}:
        bad["r19"]["agree_pass"] = 3
        if reason == "unexpected_pass":
            bad["worker_counts"]["passed"] = 3
            bad["worker_counts"]["unexpected"] = 1
    elif reason == "native_only":
        bad["r19"]["agree_pass"] = 3
        bad["worker_counts"]["total"] = 3
        bad["worker_counts"]["passed"] = 3
    elif reason == "wasm_only":
        bad["r19"]["agree_pass"] = 3
        bad["native"]["total"] = 3
        bad["native"]["passed"] = 3
    rows = append_candidates([], [_candidate(0), bad])
    assert rows[-1]["qualifying"] is False
    assert rows[-1]["reset_reason"] == reason
    assert rows[-1]["derived_streak"] == 0


@pytest.mark.parametrize(
    "outcome",
    ["identity_mismatch", "timeout", "cancellation"],
)
def test_every_infrastructure_outcome_resets(outcome: str) -> None:
    rows = append_candidates([], [_candidate(0), _candidate(1, infrastructure_outcome=outcome)])
    assert rows[-1]["qualifying"] is False
    assert rows[-1]["reset_reason"] == outcome
    assert rows[-1]["derived_streak"] == 0


def test_missing_slot_is_synthesized_once_after_grace() -> None:
    slot = SLOT + timedelta(days=2)
    before = synthesize_missing_candidates(
        candidate="temper-io-types",
        expected_slots=[slot],
        run_census=[],
        existing_rows=[],
        now=slot + timedelta(minutes=89),
        grace=timedelta(minutes=90),
    )
    assert before == []

    missing = synthesize_missing_candidates(
        candidate="temper-io-types",
        expected_slots=[slot],
        run_census=[],
        existing_rows=[],
        now=slot + timedelta(minutes=90),
        grace=timedelta(minutes=90),
    )
    assert len(missing) == 1
    rows = append_candidates([], missing)
    assert rows[0]["reset_reason"] == "missing_result"
    assert rows[0]["observed_at"] == "2026-09-03T06:10:00Z"
    assert (
        synthesize_missing_candidates(
            candidate="temper-io-types",
            expected_slots=[slot],
            run_census=[],
            existing_rows=rows,
            now=slot + timedelta(days=1),
            grace=timedelta(minutes=90),
        )
        == []
    )


def test_run_census_prevents_false_missing_slot() -> None:
    assert (
        synthesize_missing_candidates(
            candidate="temper-io-types",
            expected_slots=[SLOT],
            run_census=[{"event": "schedule", "expected_schedule_slot": "2026-09-01T04:40:00Z"}],
            existing_rows=[],
            now=SLOT + timedelta(hours=3),
            grace=timedelta(minutes=90),
        )
        == []
    )


def test_contract_change_starts_new_streak_at_one() -> None:
    changed = _candidate(2, components=_components(abi="temper-worker-abi-v2"))
    rows = append_candidates([], [_candidate(0), _candidate(1), changed])
    assert [row["derived_streak"] for row in rows] == [1, 2, 1]
    assert rows[-1]["qualifying"] is True
    assert rows[-1]["reset_reason"] == "comparison_contract_changed"


@pytest.mark.parametrize("field", ["source_commit", "wasm_sha256"])
def test_repeated_source_bytes_are_diagnostic(field: str) -> None:
    first = _candidate(0)
    repeated = _candidate(1)
    repeated[field] = first[field]
    rows = append_candidates([], [first, repeated])
    assert rows[-1]["qualifying"] is False
    assert rows[-1]["reset_reason"] == "repeated_source_bytes"
    assert rows[-1]["derived_streak"] == 1


def test_ten_distinct_rows_qualify() -> None:
    rows = append_candidates([], [_candidate(i) for i in range(10)])
    assert rows[-1]["derived_streak"] == 10
    assert rows[-1]["qualification_bar_met"] is True


def test_three_infrastructure_resets_in_rolling_fourteen_halts() -> None:
    candidates = [_candidate(i) for i in range(14)]
    for i, outcome in [(1, "timeout"), (6, "cancellation"), (13, "identity_mismatch")]:
        candidates[i] = _candidate(i, infrastructure_outcome=outcome)
    rows = append_candidates([], candidates)
    assert rows[-1]["investigation_halt"] is True
    assert rows[-1]["reset_reason"] == "identity_mismatch"

    next_good = append_candidates(rows, [_candidate(14)])[-1]
    assert next_good["qualifying"] is False
    assert next_good["reset_reason"] == "infrastructure_reset_budget"
    assert next_good["qualification_bar_met"] is False


def test_chain_deletion_reorder_and_manual_streak_edit_fail() -> None:
    rows = append_candidates([], [_candidate(0), _candidate(1), _candidate(2)])
    for corrupt in (rows[1:], [rows[1], rows[0], rows[2]]):
        with pytest.raises(LedgerError):
            validate_ledger(corrupt)

    edited = copy.deepcopy(rows)
    edited[1]["derived_streak"] = 99
    with pytest.raises(LedgerError, match="derived fields"):
        validate_ledger(edited)


def test_append_only_check_rejects_tail_deletion_or_rewrite() -> None:
    previous = append_candidates([], [_candidate(0), _candidate(1), _candidate(2)])
    extended = append_candidates(previous, [_candidate(3)])
    validate_append_only(previous, extended)

    with pytest.raises(LedgerError, match="append-only"):
        validate_append_only(previous, previous[:-1])

    rewritten = copy.deepcopy(previous)
    rewritten[-1]["observed_at"] = "2026-09-03T05:00:00Z"
    with pytest.raises(LedgerError, match="append-only"):
        validate_append_only(previous, rewritten)


def test_canonical_rebuild_is_byte_for_byte_deterministic() -> None:
    rows = append_candidates([], [_candidate(0), _candidate(1)])
    rebuilt = rebuild_ledger(rows)
    assert [canonical_line(row) for row in rebuilt] == [canonical_line(row) for row in rows]
    assert json.loads(canonical_line(rows[0])) == rows[0]


def test_contract_digest_rejects_missing_or_extra_components() -> None:
    with pytest.raises(LedgerError, match="component keys"):
        comparison_contract_digest({"abi": "v1"})
    extra = _components()
    extra["unreviewed_component"] = "surprise"
    with pytest.raises(LedgerError, match="component keys"):
        comparison_contract_digest(extra)
