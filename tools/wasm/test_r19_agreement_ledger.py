from __future__ import annotations

import copy
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

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
    validate_source_run,
)
from r19_compare import inject_one_disagreement, run_comparison

SLOT = datetime(2026, 9, 1, 4, 40, tzinfo=UTC)


def _run_metadata(candidate: dict) -> dict:
    return {
        "id": int(candidate["run_id"]),
        "run_attempt": candidate["run_attempt"],
        "event": candidate["event_name"],
        "head_sha": candidate["source_commit"],
        "head_branch": "main",
        "path": ".github/workflows/wasm-tier-nightly.yml",
        "status": "completed",
        "conclusion": "success",
        "created_at": candidate["expected_schedule_slot"],
        "head_repository": {"full_name": "owner/temper"},
        "repository": {"full_name": "owner/temper"},
    }


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
    candidate: str = "temper-io-types",
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
        "candidate": candidate,
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


def _apply_matrix(candidate: dict, matrix: dict) -> dict:
    comparison = matrix["comparison"]
    candidate["native"] = matrix["native"]
    candidate["worker_counts"] = matrix["wasm32"]
    candidate["r19"] = {
        "agree_pass": comparison["agree_pass"],
        "agree_fail": comparison["agree_fail"],
        "expected_fail": comparison["expected_fail"],
        "unexpected_pass": comparison["unexpected_pass"],
        "disagreement": comparison["disagree"],
        "native_only": comparison["native_only"],
        "wasm_only": comparison["wasm32_only"],
        "agreement_rate": comparison["agreement_rate"],
    }
    return candidate


def test_candidate_injection_flips_one_verdict_and_only_resets_candidate_streak() -> None:
    native = [
        {"name": "suite::zeta", "status": "pass"},
        {"name": "suite::alpha", "status": "pass"},
        {"name": "suite::middle", "status": "pass"},
        {"name": "suite::omega", "status": "pass"},
    ]
    worker = [{"name": result["name"], "status": "pass"} for result in reversed(native)]

    injected, injected_name = inject_one_disagreement(worker)
    changed = [
        after["name"] for before, after in zip(worker, injected, strict=True) if before != after
    ]
    matrix = run_comparison(native, injected, {}, "a" * 40)

    assert injected_name == "suite::alpha"
    assert changed == ["suite::alpha"]
    assert next(result for result in worker if result["name"] == injected_name)["status"] == "pass"
    assert matrix["comparison"]["disagree"] == 1
    assert matrix["comparison"]["disagreements"] == [
        {
            "name": "suite::alpha",
            "native_status": "pass",
            "wasm32_status": "fail",
        }
    ]

    # Model a different tier rotating on either side of the explicit candidate
    # injection. Its independent streak must survive the candidate's reset.
    injected_row = _apply_matrix(_candidate(2, event_name="workflow_dispatch"), matrix)
    rows = append_candidates(
        [],
        [
            _candidate(0),
            _candidate(1, candidate="temper-drc-rs"),
            injected_row,
            _candidate(3, candidate="temper-drc-rs"),
            _candidate(4),
        ],
    )
    by_sequence = {row["sequence"]: row for row in rows}
    assert by_sequence[3]["candidate"] == "temper-io-types"
    assert by_sequence[3]["reset_reason"] == "disagreement"
    assert by_sequence[3]["derived_streak"] == 0
    assert by_sequence[4]["candidate"] == "temper-drc-rs"
    assert by_sequence[4]["derived_streak"] == 2
    assert by_sequence[5]["candidate"] == "temper-io-types"
    assert by_sequence[5]["derived_streak"] == 1


def test_precomparison_failure_is_infrastructure_reset_not_disagreement() -> None:
    with pytest.raises(ValueError, match="no pass-status result"):
        inject_one_disagreement([{"name": "suite::failed", "status": "fail"}])

    failed = _candidate(1, infrastructure_outcome="timeout")
    rows = append_candidates([], [_candidate(0), failed])

    assert rows[-1]["r19"]["disagreement"] == 0
    assert rows[-1]["reset_reason"] == "timeout"
    assert rows[-1]["derived_streak"] == 0


def test_workflow_routes_diagnostic_injection_to_explicit_candidate() -> None:
    workflow = Path(".github/workflows/wasm-tier-nightly.yml").read_text()
    injection_step = workflow.split(
        "- name: Anti-vacuity — flip one completed immutable Worker verdict", 1
    )[1].split("- name: R19 comparison — selected tiers", 1)[0]

    assert "/tmp/worker_sweep_io-types.json" in injection_step
    assert '"candidate": "temper-io-types"' in injection_step
    assert '"stage": "post-immutable-sweep"' in injection_step
    assert "ROTATED_SUFFIX" not in injection_step


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


def test_active_run_without_result_becomes_missing_after_grace() -> None:
    missing = synthesize_missing_candidates(
        candidate="temper-io-types",
        expected_slots=[SLOT],
        run_census=[{
            "event": "schedule",
            "status": "in_progress",
            "run_id": "112233",
            "run_attempt": 1,
            "expected_schedule_slot": "2026-09-01T04:40:00Z",
        }],
        existing_rows=[],
        now=SLOT + timedelta(hours=3),
        grace=timedelta(minutes=90),
    )
    assert len(missing) == 1
    assert missing[0]["infrastructure_outcome"] == "missing_result"
    assert missing[0]["run_id"].startswith("0:missing:")

    # A real run can start after GitHub's scheduling delay. Keep the missed
    # deadline as a reset, then retain the late result instead of rejecting it
    # as out-of-order evidence.
    late = _candidate()
    rows = append_candidates([], [missing[0], late])
    assert [row["reset_reason"] for row in rows] == ["missing_result", None]
    assert rows[-1]["derived_streak"] == 1


def test_completed_run_without_candidate_becomes_missing_result() -> None:
    missing_slot = SLOT + timedelta(days=1)
    missing = synthesize_missing_candidates(
        candidate="temper-io-types",
        expected_slots=[missing_slot],
        run_census=[{
            "event": "schedule",
            "status": "completed",
            "conclusion": "failure",
            "run_id": "998877",
            "run_attempt": 1,
            "expected_schedule_slot": "2026-09-02T04:40:00Z",
        }],
        existing_rows=[],
        now=missing_slot + timedelta(hours=3),
        grace=timedelta(minutes=90),
    )
    assert len(missing) == 1
    assert missing[0]["run_id"] == "998877"
    assert missing[0]["run_attempt"] == 1
    previous = append_candidates([], [_candidate(0)])
    rows = append_candidates(previous, missing)
    assert rows[-1]["reset_reason"] == "missing_result"
    assert rows[-1]["derived_streak"] == 0


def test_candidate_is_bound_to_authoritative_workflow_run_metadata() -> None:
    candidate = _candidate()
    metadata = _run_metadata(candidate)
    validate_source_run(
        candidate,
        metadata,
        workflow_path=".github/workflows/wasm-tier-nightly.yml",
        branch="main",
    )

    mutations = [
        ("path", ".github/workflows/forged.yml"),
        ("head_branch", "feature/forged-evidence"),
        ("head_sha", "f" * 40),
        ("run_attempt", 2),
        ("created_at", "2026-09-02T04:40:00Z"),
    ]
    for field, value in mutations:
        changed = copy.deepcopy(metadata)
        changed[field] = value
        with pytest.raises(LedgerError):
            validate_source_run(
                candidate,
                changed,
                workflow_path=".github/workflows/wasm-tier-nightly.yml",
                branch="main",
            )


def test_candidate_source_must_be_the_base_repository() -> None:
    candidate = _candidate()
    metadata = _run_metadata(candidate)
    metadata["head_repository"]["full_name"] = "fork/temper"
    with pytest.raises(LedgerError, match="base repository"):
        validate_source_run(
            candidate,
            metadata,
            workflow_path=".github/workflows/wasm-tier-nightly.yml",
            branch="main",
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


def test_evidence_workflow_pushes_only_when_this_run_appended_a_row() -> None:
    workflow = (
        Path(__file__).resolve().parents[2] / ".github/workflows/wasm-tier-ledger.yml"
    ).read_text()
    assert "git rev-parse HEAD > /tmp/r19-ledger-start-head.txt" in workflow
    assert '$(cat /tmp/r19-ledger-start-head.txt)' in workflow
    assert "git diff --quiet origin/main...HEAD" not in workflow
