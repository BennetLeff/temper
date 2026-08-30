"""Boundary tests for the Rust-owned collision campaign.

These tests intentionally retain aliases to every consumed object.  A
successful transition is not enough evidence here: the old alias must be
poisoned before any later campaign mutation can occur.
"""

from __future__ import annotations

import json

import pytest
import temper_orchestration as rust


def _prepared(max_rounds: int = 4):
    return rust.prepare_collision_campaign(
        "board-sha",
        "rules-sha",
        "solver-build",
        "axis-x",
        ["U1", "R1"],
        max_rounds,
        120_000,
    )


def _candidate(solving):
    return solving.complete_candidate({"U1": (100, 200, 0), "R1": (300, 400, 1)})


def _witnesses():
    return [("R1", "U1", 0.25, "candidate-1")]


def test_every_consuming_transition_invalidates_retained_aliases():
    prepared = _prepared()
    prepared_alias = prepared
    solving = prepared.start_solving()
    with pytest.raises(RuntimeError, match="handle has been consumed"):
        prepared_alias.start_solving()

    solving_alias = solving
    candidate = _candidate(solving)
    with pytest.raises(RuntimeError, match="handle has been consumed"):
        _candidate(solving_alias)

    candidate_alias = candidate
    decision = candidate.audit("passed", "rejected:body collision", "trusted", _witnesses())
    with pytest.raises(RuntimeError, match="handle has been consumed"):
        candidate_alias.audit("passed", "passed", "trusted", [])

    decision_alias = decision
    refining = decision.take_refining()
    with pytest.raises(RuntimeError, match="handle has been consumed"):
        decision_alias.take_refining()

    refining_alias = refining
    next_solving = refining.next_round()
    with pytest.raises(RuntimeError, match="handle has been consumed"):
        refining_alias.next_round()
    assert isinstance(next_solving, rust.CollisionCampaignSolving)


def test_terminal_decision_is_closed_and_old_alias_is_consumed():
    candidate = _candidate(_prepared().start_solving())
    candidate_alias = candidate
    decision = candidate.audit("passed", "passed", "trusted", [])
    with pytest.raises(RuntimeError, match="handle has been consumed"):
        candidate_alias.audit("passed", "passed", "trusted", [])

    decision_alias = decision
    terminal = decision.take_terminal()
    with pytest.raises(RuntimeError, match="handle has been consumed"):
        decision_alias.take_terminal()
    assert terminal.kind == "accepted"
    assert terminal.rounds == 1
    with pytest.raises(ValueError, match="TerminalState"):
        terminal.resume()


def test_terminal_checkpoint_retains_the_final_collision_cut():
    candidate = _candidate(_prepared(max_rounds=1).start_solving())
    decision = candidate.audit("passed", "passed", "trusted", _witnesses())

    checkpoint = decision.terminal_checkpoint()
    payload = json.loads(checkpoint.to_bytes().removeprefix(b"TCAMP001"))
    assert len(payload["state"]["cuts"]) == 1
    assert payload["state"]["cuts"][0]["key"]["pair"] == {
        "first": "R1",
        "second": "U1",
    }
    assert payload["terminal"] is not None


@pytest.mark.parametrize(
    ("method", "kind", "reason"),
    (
        ("solver_unresolved", "solver_unresolved", "solver timeout"),
        ("proven_infeasible", "proven_infeasible", "no feasible assignment"),
        ("budget_exhausted", "budget_exhausted", "campaign budget"),
    ),
)
def test_solving_terminal_transitions_are_typed_and_serialized(method, kind, reason):
    solving = _prepared().start_solving()
    solving_alias = solving
    decision = getattr(solving, method)(reason)
    terminal_checkpoint = decision.terminal_checkpoint()
    terminal = decision.take_terminal()

    assert terminal.kind == kind
    assert terminal.reason == reason
    assert terminal_checkpoint.terminal_kind == kind
    assert terminal_checkpoint.terminal_reason == reason
    restored = rust.CollisionCampaignCheckpoint.from_bytes(terminal_checkpoint.to_bytes())
    assert restored.terminal_kind == kind
    assert restored.terminal_reason == reason
    restored.validate_for("board-sha", "rules-sha", "solver-build", "axis-x")
    with pytest.raises(RuntimeError, match="handle has been consumed"):
        getattr(solving_alias, method)(reason)


def test_solving_terminal_transitions_reject_empty_reasons():
    for method in ("solver_unresolved", "proven_infeasible", "budget_exhausted"):
        with pytest.raises(ValueError, match="terminal reason"):
            getattr(_prepared().start_solving(), method)("")


def test_untrusted_provenance_cannot_be_promoted_to_accepted():
    candidate = _candidate(_prepared().start_solving())
    decision = candidate.audit("passed", "passed", "passed", [])
    terminal = decision.take_terminal()
    assert terminal.kind == "verifier_rejected"
    assert terminal.reason == "provenance gate is not trusted"


def test_malformed_inputs_fail_at_boundary_before_a_campaign_handle_exists():
    with pytest.raises(ValueError):
        _prepared(max_rounds=0)
    with pytest.raises(ValueError):
        rust.prepare_collision_campaign(
            "board-sha", "rules-sha", "solver-build", "axis-x", [], 4, 120_000
        )
    with pytest.raises(TypeError):
        rust.CollisionCampaignPrepared()

    solving = _prepared().start_solving()
    with pytest.raises(ValueError, match="rotation quadrant"):
        solving.complete_candidate({"U1": (100, 200, 4), "R1": (300, 400, 1)})

    solving = _prepared().start_solving()
    with pytest.raises(TypeError, match="poses must be a dict"):
        solving.complete_candidate([("U1", 100, 200, 0)])


def test_checkpoint_is_rust_serialized_and_round_trips_without_python_state():
    prepared = _prepared()
    checkpoint = prepared.checkpoint()
    payload = checkpoint.to_bytes()
    assert payload.startswith(b"TCAMP001")

    restored = rust.CollisionCampaignCheckpoint.from_bytes(payload)
    resumed = restored.restore_for("board-sha", "rules-sha", "solver-build", "axis-x")
    assert isinstance(resumed, rust.CollisionCampaignPrepared)
    assert isinstance(resumed.start_solving(), rust.CollisionCampaignSolving)

    with pytest.raises(ValueError, match="ForeignIdentity"):
        restored.restore_for("other-board", "rules-sha", "solver-build", "axis-x")
    with pytest.raises(ValueError, match="checkpoint"):
        rust.CollisionCampaignCheckpoint.from_bytes(b"not-a-checkpoint")


def test_checkpoint_version_has_one_envelope_schema() -> None:
    payload = _prepared().checkpoint().to_bytes()
    envelope = json.loads(payload.removeprefix(b"TCAMP001"))
    branch_era_state_only = b"TCAMP001" + json.dumps(envelope["state"]).encode()
    with pytest.raises(ValueError, match="(?i)checkpoint"):
        rust.CollisionCampaignCheckpoint.from_bytes(branch_era_state_only)
