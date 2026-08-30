"""Focused fake-model integration tests for the collision corridor campaign."""

from __future__ import annotations

import time
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
import temper_orchestration as rust

from temper_placer.placer.cp_sat.collision_corridor_campaign import (
    CollisionCorridorLimits,
    _identity_parts,
    run_collision_corridor_campaign,
)
from temper_placer.placer.cp_sat.collision_corridor_checkpoint import (
    write_collision_campaign_checkpoint,
)
from temper_placer.placer.cp_sat.collision_corridor_evidence import _campaign_record
from temper_placer.placer.cp_sat.creepage_search_corridor_experiment import (
    ExperimentIdentity,
    PreparedCorridorExperiment,
)


def _prepared(*, refs: tuple[str, ...] = ("A", "B"), complete: bool = True):
    identity = ExperimentIdentity(
        input_sha256=(("pcb", "a" * 64), ("constraints", "b" * 64)),
        requirement_sha256="c" * 64,
        requirement_count=2,
        requirements_by_gap_mm=((1.0, 2),),
        partition=(
            ("hv_only", ("A",)),
            ("selv_only", ("B",)),
            ("isolators", ()),
            ("unclassified", ()),
        ),
        gap_mm=1.0,
        polarity="hv-low-selv-high",
        seed=0,
        num_search_workers=4,
        solve_limit_s=1.0,
        watchdog_grace_s=1.0,
        warm_start_limit_s=1.0,
        tool_code_sha256=(("solver", "d" * 64),),
    )
    bodies = {ref: object() for ref in refs}
    if not complete:
        bodies.pop(refs[-1])
    return PreparedCorridorExperiment(
        identity,
        SimpleNamespace(components=[]),
        SimpleNamespace(),
        {},
        refs,
        tuple((ref, (float(index + 1), 1.0, 0)) for index, ref in enumerate(refs)),
        Path("manifest.yaml"),
        ("A",),
        ("B",),
        lambda _candidate: SimpleNamespace(violations=()),
        (),
        {"components": []},
        {},
        bodies,
        object(),
        SimpleNamespace(complete=complete, missing=(() if complete else (refs[-1],)), invalid={}),
    )


def _validator(*_args):
    return SimpleNamespace(
        geometry_trusted=True,
        hard_failures=[],
        coverage_gaps=[],
        intra_footprint=[],
        covered_pair_count=1,
        validator_violation_count=0,
        stats={},
    )


def _solver_factory(seen: list[tuple[object, ...]], *, fail_after: int | None = None):
    calls = 0

    def solve(_netlist, _board, **kwargs):
        nonlocal calls
        calls += 1
        seen.append(tuple(kwargs["collision_campaign_cuts"]))
        if fail_after is not None and calls > fail_after:
            raise RuntimeError("fake child stopped")
        return SimpleNamespace(
            status="feasible",
            positions={"A": (1.0 + calls, 1.0), "B": (3.0, 1.0)},
            rotations={"A": 0, "B": 0},
            solver_telemetry=None,
        )

    return solve


def _clean_body(*_args):
    return SimpleNamespace(
        clean=True, violations=[], allowlisted=[], checked_pairs=1, refs_without_geometry=[]
    )


def _collision_body(*_args):
    return SimpleNamespace(
        clean=False,
        violations=[SimpleNamespace(ref_a="B", ref_b="A", overlap_mm2=0.5)],
        allowlisted=[],
        checked_pairs=1,
        refs_without_geometry=[],
    )


def test_accepted_campaign_builds_a_fresh_model_path_and_keeps_axes_independent():
    prepared = _prepared()
    x_calls: list[tuple[object, ...]] = []
    y_calls: list[tuple[object, ...]] = []
    x = run_collision_corridor_campaign(
        prepared,
        "x",
        limits=CollisionCorridorLimits(max_rounds=2, round_budget_s=1),
        solver=_solver_factory(x_calls),
        validator_audit=_validator,
        body_audit=_clean_body,
    )
    y = run_collision_corridor_campaign(
        prepared,
        "y",
        limits=CollisionCorridorLimits(max_rounds=2, round_budget_s=1),
        solver=_solver_factory(y_calls),
        validator_audit=_validator,
        body_audit=_clean_body,
    )
    assert x.accepted and y.accepted
    assert x.rounds[0].model_identity != y.rounds[0].model_identity
    assert x_calls == [()]
    assert y_calls == [()]


def test_collision_cut_is_replayed_into_the_next_fresh_round():
    seen: list[tuple[object, ...]] = []
    result = run_collision_corridor_campaign(
        _prepared(),
        "x",
        limits=CollisionCorridorLimits(max_rounds=2, round_budget_s=1),
        solver=_solver_factory(seen),
        validator_audit=_validator,
        body_audit=_collision_body,
    )
    assert len(result.rounds) == 2
    assert seen[0] == ()
    assert len(seen[1]) == 1
    assert result.terminal_kind == "no_progress" or result.terminal_kind == "budget_exhausted"


def test_round_limit_records_the_final_collision_cut_in_telemetry():
    result = run_collision_corridor_campaign(
        _prepared(),
        "x",
        limits=CollisionCorridorLimits(max_rounds=1, round_budget_s=1),
        solver=_solver_factory([]),
        validator_audit=_validator,
        body_audit=_collision_body,
    )

    assert result.terminal_kind == "budget_exhausted"
    assert len(result.rounds) == 1
    round_record = result.rounds[0]
    assert round_record.cuts_applied == 1
    assert round_record.cuts[0]["first"] == "A"
    assert round_record.cuts[0]["second"] == "B"
    assert round_record.cuts[0]["x_first"] == 2000
    assert round_record.cuts[0]["x_second"] == 3000

    evidence = _campaign_record(result, 1.0)
    assert evidence["classification"] == "bounded_non_convergence"
    assert evidence["cumulative"]["unique_cuts"] == 1


def test_missing_fab_coverage_is_invalid_before_campaign_factory_or_solver():
    called = False

    def factory(*_args):
        nonlocal called
        called = True
        raise AssertionError("must not construct Rust campaign")

    result = run_collision_corridor_campaign(
        _prepared(complete=False),
        "x",
        campaign_factory=factory,
        solver=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not solve")),
    )
    assert result.terminal_kind == "invalid_experiment"
    assert called is False


def test_verifier_rejection_is_terminal_and_distinct_from_solver_status():
    result = run_collision_corridor_campaign(
        _prepared(),
        "x",
        limits=CollisionCorridorLimits(max_rounds=2, round_budget_s=1),
        solver=_solver_factory([]),
        verifier=lambda _candidate: SimpleNamespace(violations=("shortfall",)),
        validator_audit=_validator,
        body_audit=_clean_body,
    )
    assert result.terminal_kind == "verifier_rejected"
    assert result.rounds[0].solver_status == "feasible"


def test_refining_checkpoint_is_rust_bytes_and_resumes_with_full_frontier(tmp_path):
    path = tmp_path / "campaign.bin"
    first_seen: list[tuple[object, ...]] = []
    first = run_collision_corridor_campaign(
        _prepared(),
        "x",
        limits=CollisionCorridorLimits(max_rounds=4, round_budget_s=1),
        solver=_solver_factory(first_seen, fail_after=1),
        validator_audit=_validator,
        body_audit=_collision_body,
        checkpoint_path=str(path),
    )
    assert first.terminal_kind == "error"
    assert path.read_bytes().startswith(b"TCAMP001")
    resumed_seen: list[tuple[object, ...]] = []
    resumed = run_collision_corridor_campaign(
        _prepared(),
        "x",
        limits=CollisionCorridorLimits(max_rounds=4, round_budget_s=1),
        solver=_solver_factory(resumed_seen),
        validator_audit=_validator,
        body_audit=_clean_body,
        checkpoint_path=str(path),
    )
    assert resumed.accepted
    assert len(resumed_seen[0]) == 1


def test_rust_campaign_identity_rejects_foreign_axis_checkpoint(tmp_path):
    prepared = _prepared()
    checkpoint = rust.prepare_collision_campaign(
        "board", "rules", "solver", "x", ["A", "B"], 2, 1000
    ).checkpoint()
    path = tmp_path / "foreign.bin"
    write_collision_campaign_checkpoint(path, checkpoint)
    result = run_collision_corridor_campaign(
        prepared,
        "y",
        checkpoint_path=str(path),
        solver=_solver_factory([]),
        validator_audit=_validator,
        body_audit=_clean_body,
    )
    assert result.terminal_kind == "invalid_experiment"


def test_terminal_checkpoint_rejects_foreign_identity_before_returning_terminal(tmp_path):
    prepared = _prepared()
    campaign = rust.prepare_collision_campaign(
        *_identity_parts(prepared, "x"), ["A", "B"], 4, 1000
    )
    candidate = campaign.start_solving().complete_candidate(
        {"A": (100, 200, 0), "B": (300, 400, 1)}
    )
    decision = candidate.audit("passed", "passed", "trusted", [])
    checkpoint = decision.terminal_checkpoint()
    path = tmp_path / "terminal.bin"
    write_collision_campaign_checkpoint(path, checkpoint)

    # Terminal checkpoints still carry the Rust identity and must be checked
    # before their stored verdict is surfaced as this campaign's result.
    result = run_collision_corridor_campaign(
        prepared,
        "y",
        checkpoint_path=str(path),
        solver=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("foreign terminal checkpoint must not run a solver")
        ),
        validator_audit=_validator,
        body_audit=_clean_body,
    )
    assert result.terminal_kind == "invalid_experiment"


@pytest.mark.parametrize("changed_identity", ("manifest", "allowlist", "campaign_code"))
def test_checkpoint_rejects_changes_to_all_campaign_input_identities(
    tmp_path, changed_identity: str
):
    prepared = _prepared()
    checkpoint = rust.prepare_collision_campaign(
        *_identity_parts(prepared, "x"), ["A", "B"], 4, 1000
    ).checkpoint()
    path = tmp_path / f"{changed_identity}.bin"
    write_collision_campaign_checkpoint(path, checkpoint)

    identity = prepared.identity
    if changed_identity == "manifest":
        identity = replace(
            identity,
            input_sha256=tuple(identity.input_sha256) + (("manifest", "e" * 64),),
        )
    elif changed_identity == "allowlist":
        identity = replace(
            identity,
            input_sha256=tuple(identity.input_sha256) + (("body_allowlist", "e" * 64),),
        )
    else:
        identity = replace(
            identity,
            tool_code_sha256=tuple(identity.tool_code_sha256)
            + (("collision_campaign", "e" * 64),),
        )
    changed = replace(prepared, identity=identity)

    result = run_collision_corridor_campaign(
        changed,
        "x",
        checkpoint_path=str(path),
        solver=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("stale checkpoint must not run a solver")
        ),
        validator_audit=_validator,
        body_audit=_clean_body,
    )
    assert result.terminal_kind == "invalid_experiment"


def test_resume_rejects_campaign_limit_mismatch(tmp_path):
    prepared = _prepared()
    checkpoint = rust.prepare_collision_campaign(
        *_identity_parts(prepared, "x"), ["A", "B"], 4, 1000
    ).checkpoint()
    path = tmp_path / "limits.bin"
    write_collision_campaign_checkpoint(path, checkpoint)
    result = run_collision_corridor_campaign(
        prepared,
        "x",
        limits=CollisionCorridorLimits(max_rounds=3, round_budget_s=1),
        checkpoint_path=str(path),
        solver=_solver_factory([]),
        validator_audit=_validator,
        body_audit=_clean_body,
    )
    assert result.terminal_kind == "invalid_experiment"
    assert "limits" in result.terminal.reason


def test_body_audit_error_is_not_masked_by_witness_cache() -> None:
    def broken_body(*_args):
        raise RuntimeError("audit instrument failed")

    result = run_collision_corridor_campaign(
        _prepared(),
        "x",
        limits=CollisionCorridorLimits(max_rounds=2, round_budget_s=1),
        solver=_solver_factory([]),
        validator_audit=_validator,
        body_audit=broken_body,
    )
    assert result.terminal_kind == "invalid_experiment"
    body_gate = next(gate for gate in result.gates if gate.name == "f-fab")
    assert body_gate.status == "error"
    assert "audit instrument failed" in body_gate.diagnostics[0]


def test_solver_result_returned_after_round_budget_cannot_be_accepted() -> None:
    def late_solver(*args, **kwargs):
        time.sleep(0.02)
        return _solver_factory([])(*args, **kwargs)

    result = run_collision_corridor_campaign(
        _prepared(),
        "x",
        limits=CollisionCorridorLimits(max_rounds=1, round_budget_s=0.001),
        solver=late_solver,
        validator_audit=_validator,
        body_audit=_clean_body,
    )
    assert result.terminal_kind == "budget_exhausted"
    assert not result.accepted
