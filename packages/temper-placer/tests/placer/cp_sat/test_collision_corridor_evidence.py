"""Fail-closed tests for the U6 collision-corridor evidence contract."""

from __future__ import annotations

from copy import deepcopy

import pytest

from temper_placer.placer.cp_sat.collision_corridor_evidence import (
    EVIDENCE_SCHEMA,
    EVIDENCE_VERSION,
    EvidenceValidationError,
    canonical_collision_corridor_evidence,
    validate_collision_corridor_evidence,
)


def _run(run_id: str, kind: str, axis: str | None, budget: float) -> dict[str, object]:
    campaign = kind == "collision_aware_campaign"
    terminal = "solver_unresolved" if not campaign else "budget_exhausted"
    gates = (
        []
        if not campaign
        else [
            {"name": "rust-creepage", "status": "failed"},
            {"name": "req-safe-01", "status": "passed"},
            {"name": "f-fab", "status": "failed"},
        ]
    )
    result: dict[str, object] = {
        "id": run_id,
        "kind": kind,
        "axis": axis,
        "budget_s": budget,
        "terminal": {"kind": terminal, "reason": "fixture"},
        "rounds": [
            {
                "round_index": 0,
                "model_identity": f"model-{run_id}",
                "frontier_size": 0,
                "cuts_applied": 0,
                "elapsed_s": budget,
                "solver_status": "unknown",
                "candidate_complete": False,
                "telemetry": {},
                "witnesses": [],
                "cuts": [],
            }
        ],
        "cumulative": {
            "round_count": 1,
            "wall_time_s": budget,
            "first_incumbent_s": 0,
            "conflicts": 0,
            "branches": 0,
            "unique_cuts": 0,
        },
        "final": {"candidate": {"complete": False}, "gates": gates},
    }
    if campaign:
        result["cumulative"] = {
            "round_count": 1,
            "wall_time_s": budget,
            "first_incumbent_s": 0,
            "conflicts": 0,
            "branches": 0,
            "unique_cuts": 0,
        }
    return result


def _evidence() -> dict[str, object]:
    return {
        "schema": EVIDENCE_SCHEMA,
        "version": EVIDENCE_VERSION,
        "provenance": {
            "source": "measured-live",
            "board_hash_before": "a" * 64,
            "board_hash_after": "a" * 64,
            "board_sha256": "a" * 64,
            "board_byte_identical": True,
        },
        "regime": {
            "corridor": {"axis": "both", "gap_mm": 12.6},
            "campaign_limits": {
                "max_rounds": 4,
                "round_budget_s": 120.0,
                "total_budget_s": 480.0,
            },
        },
        "runs": [
            _run("historical_control_120s", "unrestricted_control", None, 120.0),
            _run("matched_control_480s", "unrestricted_control", None, 480.0),
            _run("campaign_x", "collision_aware_campaign", "x", 480.0),
            _run("campaign_y", "collision_aware_campaign", "y", 480.0),
        ],
    }


def test_valid_comparison_is_canonical_and_round_trippable() -> None:
    payload = _evidence()
    encoded = canonical_collision_corridor_evidence(payload)
    assert '"schema":"temper.collision-aware-creepage-corridor"' in encoded
    validate_collision_corridor_evidence(payload)


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        (("schema",), "wrong", "schema"),
        (("runs",), [], "four runs"),
        (("provenance", "board_hash_after"), "b" * 64, "board changed"),
        (("regime", "campaign_limits", "total_budget_s"), 240.0, "480"),
        (("runs", 2, "terminal", "kind"), "made_up", "unknown terminal"),
        (("runs", 2, "axis"), "z", "axes"),
    ],
)
def test_malformed_or_inconsistent_evidence_is_rejected(
    path: tuple[object, ...], value: object, message: str
) -> None:
    payload = _evidence()
    cursor: object = payload
    for part in path[:-1]:
        cursor = cursor[part]  # type: ignore[index]
    cursor[path[-1]] = value  # type: ignore[index]
    with pytest.raises(EvidenceValidationError, match=message):
        validate_collision_corridor_evidence(payload)


def test_accepted_verdict_requires_complete_candidate_and_three_passed_gates() -> None:
    payload = _evidence()
    accepted = payload["runs"][2]  # type: ignore[index]
    accepted["terminal"] = {"kind": "accepted"}  # type: ignore[index]
    with pytest.raises(EvidenceValidationError, match="complete candidate"):
        validate_collision_corridor_evidence(payload)


def test_accepted_verdict_rejects_anonymous_gates_and_empty_candidate() -> None:
    payload = _evidence()
    accepted = payload["runs"][2]  # type: ignore[index]
    accepted["terminal"] = {"kind": "accepted"}  # type: ignore[index]
    accepted["final"] = {  # type: ignore[index]
        "candidate": {
            "complete": True,
            "digest": "0" * 64,
            "positions": [],
            "rotations": [],
        },
        "gates": [{"status": "passed"}, {"status": "passed"}, {"status": "passed"}],
    }
    with pytest.raises(EvidenceValidationError, match="all three gates"):
        validate_collision_corridor_evidence(payload)


def test_campaign_cumulative_round_count_and_unique_cuts_are_consistent() -> None:
    payload = _evidence()
    campaign = payload["runs"][2]  # type: ignore[index]
    campaign["rounds"].append(deepcopy(campaign["rounds"][0]))  # type: ignore[index]
    with pytest.raises(EvidenceValidationError, match="round count"):
        validate_collision_corridor_evidence(payload)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("wall_time_s", 479.0, "wall time"),
        ("first_incumbent_s", 1.0, "first-incumbent"),
        ("conflicts", 1, "conflicts"),
        ("branches", 1, "branches"),
        ("unique_cuts", 1, "unique cut"),
    ],
)
def test_cumulative_measurements_must_equal_their_round_records(
    field: str, value: object, message: str
) -> None:
    payload = _evidence()
    payload["runs"][2]["cumulative"][field] = value  # type: ignore[index]
    with pytest.raises(EvidenceValidationError, match=message):
        validate_collision_corridor_evidence(payload)
