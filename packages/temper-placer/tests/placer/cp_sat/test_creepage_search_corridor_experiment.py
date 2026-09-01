"""Truthfulness tests for the bounded two-axis search-corridor experiment."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from temper_placer.core.board import Board
from temper_placer.core.fab_body import FabBody
from temper_placer.core.netlist import Component, Netlist, Pin
from temper_placer.placer.cp_sat.body_collision import EMPTY_ALLOWLIST
from temper_placer.placer.cp_sat.creepage_search_corridor_experiment import (
    AxisExperimentResult,
    CandidateGateResult,
    CreepageSearchCorridorExperimentRecord,
    ExperimentIdentity,
    PreparedCorridorExperiment,
    SharedPreflightError,
    build_experiment_identity,
    canonical_experiment_json,
    execute_axis_probe,
    read_experiment_record,
    run_prepared_corridor_experiment,
    run_with_shared_preflight,
    write_experiment_record,
)
from temper_placer.placer.cp_sat.domain_clearance import generate_domain_clearance_constraints
from temper_placer.requirements.validators.clearance import VoltageDomain


def _identity() -> ExperimentIdentity:
    return ExperimentIdentity(
        input_sha256=(("pcb", "a" * 64), ("constraints", "b" * 64), ("manifest", "c" * 64)),
        requirement_sha256="d" * 64,
        requirement_count=9176,
        requirements_by_gap_mm=((3.0, 10), (12.6, 9166)),
        partition=(
            ("hv_only", ("H",)),
            ("isolators", ()),
            ("selv_only", ("S",)),
            ("unclassified", ()),
        ),
        gap_mm=12.6,
        polarity="hv-low-selv-high",
        seed=7,
        num_search_workers=4,
        solve_limit_s=120.0,
        watchdog_grace_s=5.0,
        warm_start_limit_s=30.0,
        tool_code_sha256=(("experiment", "e" * 64),),
    )


def _gate(name: str, status: str = "passed") -> CandidateGateResult:
    return CandidateGateResult(name=name, status=status, checked_count=1, violation_count=0)


def _axis(
    axis: str, *, solver: str, execution: str = "returned", acceptance: str = "not-run"
) -> AxisExperimentResult:
    gates_by_verdict = {
        "accepted": (_gate("rust-creepage"), _gate("req-safe-01"), _gate("f-fab")),
        "rejected": (
            _gate("rust-creepage", "failed"),
            _gate("req-safe-01"),
            _gate("f-fab"),
        ),
        "gate-error": (
            _gate("rust-creepage", "error"),
            _gate("req-safe-01"),
            _gate("f-fab"),
        ),
    }
    gates = gates_by_verdict.get(acceptance, ())
    return AxisExperimentResult(
        axis=axis,
        solver_status=solver,
        execution_outcome=execution,
        acceptance_verdict=acceptance,
        elapsed_s=1.0,
        candidate_complete=acceptance in {"accepted", "rejected", "gate-error"},
        gates=gates,
    )


def _prepared() -> PreparedCorridorExperiment:
    return PreparedCorridorExperiment(
        identity=_identity(),
        netlist=SimpleNamespace(components=[]),
        board=SimpleNamespace(width=100.0, height=80.0),
        solve_kwargs={},
        expected_refs=("H", "S"),
        hint_positions=(("H", (1.0, 1.0, 0)), ("S", (20.0, 1.0, 0))),
        manifest_path=Path("manifest.yaml"),
        hv_only_refs=("H",),
        selv_only_refs=("S",),
        verifier=lambda _candidate: SimpleNamespace(violations=()),
        domain_constraints=(),
        validator_placement={"components": [{"ref": "H"}, {"ref": "S"}]},
        voltage_domains={},
        fab_bodies={"H": object()},
        body_allowlist=object(),
    )


def test_axis_outcomes_remain_independent_and_second_gets_no_first_result() -> None:
    prepared = _prepared()
    seen: list[tuple[str, int, tuple]] = []

    def runner(shared, axis, _limit, _grace):
        seen.append((axis, id(shared), shared.hint_positions))
        if axis == "x":
            return _axis("x", solver="feasible", acceptance="accepted")
        return _axis("y", solver="unknown")

    record = run_prepared_corridor_experiment(prepared, axis_runner=runner)

    assert record.success is True
    assert [(item.axis, item.solver_status, item.acceptance_verdict) for item in record.axes] == [
        ("x", "feasible", "accepted"),
        ("y", "unknown", "not-run"),
    ]
    assert seen == [
        ("x", id(prepared), prepared.hint_positions),
        ("y", id(prepared), prepared.hint_positions),
    ]


def test_infeasible_or_axis_error_does_not_stop_other_axis() -> None:
    calls: list[str] = []

    def runner(_shared, axis, _limit, _grace):
        calls.append(axis)
        if axis == "x":
            return _axis("x", solver="infeasible")
        raise RuntimeError("worker disappeared")

    record = run_prepared_corridor_experiment(_prepared(), axis_runner=runner)
    assert calls == ["x", "y"]
    assert record.axes[0].solver_status == "infeasible"
    assert record.axes[1].execution_outcome == "error"
    assert record.axes[1].solver_status == "not-run"


def test_unknown_and_watchdog_timeout_remain_distinct_negative_results() -> None:
    def runner(_shared, axis, _limit, _grace):
        if axis == "x":
            return _axis("x", solver="unknown")
        return _axis("y", solver="not-run", execution="timeout")

    record = run_prepared_corridor_experiment(_prepared(), axis_runner=runner)
    assert record.success is False
    assert (record.axes[0].solver_status, record.axes[0].execution_outcome) == (
        "unknown",
        "returned",
    )
    assert (record.axes[1].solver_status, record.axes[1].execution_outcome) == (
        "not-run",
        "timeout",
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"candidate_complete": False},
        {"solver_status": "unknown"},
        {"execution_outcome": "timeout"},
        {"gates": (_gate("rust-creepage"), _gate("req-safe-01"))},
        {
            "gates": (
                _gate("rust-creepage", "failed"),
                _gate("req-safe-01"),
                _gate("f-fab"),
            )
        },
    ],
)
def test_axis_result_rejects_impossible_accepted_states(changes: dict[str, object]) -> None:
    valid = _axis("x", solver="feasible", acceptance="accepted")
    with pytest.raises(ValueError):
        dataclasses.replace(valid, **changes)


def test_axis_result_rejects_gate_records_without_a_complete_candidate() -> None:
    with pytest.raises(ValueError):
        AxisExperimentResult(
            axis="x",
            solver_status="unknown",
            execution_outcome="returned",
            acceptance_verdict="not-run",
            elapsed_s=1.0,
            gates=(_gate("rust-creepage"),),
        )


@pytest.mark.parametrize(
    ("category", "solver", "acceptance"),
    [("gate", "not-run", "gate-error"), ("input", "model-invalid", "not-run")],
)
def test_shared_preflight_failure_stops_both_axes(
    category: str, solver: str, acceptance: str
) -> None:
    called = False

    def prepare():
        raise SharedPreflightError(category, "shared input is unavailable", _identity())

    def runner(*_args):
        nonlocal called
        called = True
        raise AssertionError("must not run")

    record = run_with_shared_preflight(prepare, axis_runner=runner)
    assert called is False
    assert [
        (axis.solver_status, axis.execution_outcome, axis.acceptance_verdict)
        for axis in record.axes
    ] == [
        (solver, "not-started", acceptance),
        (solver, "not-started", acceptance),
    ]


def test_feasible_candidate_runs_all_gates_without_short_circuit() -> None:
    prepared = dataclasses.replace(_prepared(), expected_refs=("H", "S"))
    calls: list[str] = []
    result = SimpleNamespace(
        status="feasible",
        positions={"H": (1.0, 1.0), "S": (20.0, 1.0)},
        rotations={"H": 0, "S": 0},
        solve_time_ms=12.0,
        solver_telemetry=None,
        creepage_search_corridor_report=None,
    )

    def verifier(_candidate):
        calls.append("rust")
        return SimpleNamespace(violations=("too close",))

    def validator(*_args):
        calls.append("validator")
        return SimpleNamespace(
            geometry_trusted=True,
            hard_failures=[],
            coverage_gaps=[],
            intra_footprint=[object()],
            covered_pair_count=1,
            validator_violation_count=1,
            stats={},
        )

    def body(*_args):
        calls.append("body")
        return SimpleNamespace(
            clean=False,
            violations=[object()],
            allowlisted=[],
            checked_pairs=1,
            refs_without_geometry=["S"],
        )

    axis = execute_axis_probe(
        prepared,
        "x",
        solver=lambda *_args, **_kwargs: result,
        validator_audit=validator,
        body_audit=body,
        verifier=verifier,
    )
    assert calls == ["rust", "validator", "body"]
    assert axis.solver_status == "feasible"
    assert axis.execution_outcome == "returned"
    assert axis.acceptance_verdict == "rejected"
    assert [gate.status for gate in axis.gates] == ["failed", "passed", "failed"]


def test_incomplete_candidate_is_model_invalid_and_skips_gates() -> None:
    result = SimpleNamespace(
        status="feasible",
        positions={"H": (1.0, 1.0)},
        rotations={"H": 0},
        solve_time_ms=12.0,
        solver_telemetry=None,
        creepage_search_corridor_report=None,
    )
    axis = execute_axis_probe(_prepared(), "x", solver=lambda *_a, **_kw: result)
    assert axis.solver_status == "model-invalid"
    assert axis.execution_outcome == "returned"
    assert axis.acceptance_verdict == "not-run"
    assert axis.gates == ()


def test_gate_exception_preserves_feasible_status_and_other_gates_run() -> None:
    calls: list[str] = []
    candidate = SimpleNamespace(
        status="feasible",
        positions={"H": (1.0, 1.0), "S": (20.0, 1.0)},
        rotations={"H": 0, "S": 0},
        solver_telemetry=None,
        creepage_search_corridor_report=None,
    )

    def rust(_candidate):
        calls.append("rust")
        raise RuntimeError("extension unavailable")

    def validator(*_args):
        calls.append("validator")
        return SimpleNamespace(
            geometry_trusted=True,
            hard_failures=[],
            coverage_gaps=[],
            intra_footprint=[],
            covered_pair_count=1,
            validator_violation_count=0,
            stats={},
        )

    def body(*_args):
        calls.append("body")
        return SimpleNamespace(
            clean=True,
            violations=[],
            allowlisted=[],
            checked_pairs=1,
            refs_without_geometry=[],
        )

    axis = execute_axis_probe(
        _prepared(),
        "x",
        solver=lambda *_args, **_kwargs: candidate,
        verifier=rust,
        validator_audit=validator,
        body_audit=body,
    )
    assert calls == ["rust", "validator", "body"]
    assert axis.solver_status == "feasible"
    assert axis.acceptance_verdict == "gate-error"
    assert [gate.status for gate in axis.gates] == ["error", "passed", "passed"]


def test_real_synthetic_solver_seam_builds_a_fresh_corridor_model(tmp_path: Path) -> None:
    manifest = tmp_path / "domain_manifest.yaml"
    manifest.write_text(
        "domains:\n  HV:\n    nets: [AC_L]\n  SELV:\n    nets: [GND]\n",
        encoding="utf-8",
    )
    components = [
        Component(
            ref="H",
            footprint="Synthetic",
            bounds=(4.0, 4.0),
            pins=[Pin("1", "1", (0.0, 0.0), net="AC_L")],
            initial_position=(5.0, 5.0),
            initial_rotation_quadrant=0,
        ),
        Component(
            ref="S",
            footprint="Synthetic",
            bounds=(4.0, 4.0),
            pins=[Pin("1", "1", (0.0, 0.0), net="GND")],
            initial_position=(30.0, 5.0),
            initial_rotation_quadrant=0,
        ),
    ]
    prepared = dataclasses.replace(
        _prepared(),
        netlist=Netlist(components=components),
        board=Board(width=60.0, height=30.0),
        manifest_path=manifest,
        validator_placement={"components": [{"ref": "H"}, {"ref": "S"}]},
    )

    axis = execute_axis_probe(
        prepared,
        "x",
        verifier=lambda _candidate: SimpleNamespace(violations=()),
        validator_audit=lambda *_args: SimpleNamespace(
            geometry_trusted=True,
            hard_failures=[],
            coverage_gaps=[],
            intra_footprint=[],
            covered_pair_count=1,
            validator_violation_count=0,
            stats={},
        ),
        body_audit=lambda *_args: SimpleNamespace(
            clean=True,
            violations=[],
            allowlisted=[],
            checked_pairs=1,
            refs_without_geometry=[],
        ),
    )
    assert axis.solver_status in {"optimal", "feasible"}
    assert axis.acceptance_verdict == "accepted"
    assert axis.candidate_complete is True
    assert {ref: (x, y) for ref, x, y in axis.candidate_positions}.keys() == {"H", "S"}
    assert dict(axis.corridor)["axis"] == "x"


def test_both_synthetic_axes_run_in_fresh_processes_and_round_trip(tmp_path: Path) -> None:
    manifest = tmp_path / "domain_manifest.yaml"
    manifest.write_text(
        "domains:\n  HV:\n    nets: [AC_L]\n  SELV:\n    nets: [GND]\n",
        encoding="utf-8",
    )
    components = [
        Component(
            ref="H",
            footprint="Synthetic",
            bounds=(4.0, 4.0),
            pins=[Pin("1", "1", (0.0, 0.0), net="AC_L")],
            initial_position=(5.0, 5.0),
            initial_rotation_quadrant=0,
        ),
        Component(
            ref="S",
            footprint="Synthetic",
            bounds=(4.0, 4.0),
            pins=[Pin("1", "1", (0.0, 0.0), net="GND")],
            initial_position=(30.0, 20.0),
            initial_rotation_quadrant=0,
        ),
    ]
    placement = {
        "components": [
            {
                "ref": "H",
                "position": (5.0, 5.0),
                "rotation_deg": 0.0,
                "nets": ["AC_L"],
                "pads": [
                    {
                        "number": "1",
                        "net": "AC_L",
                        "offset": (0.0, 0.0),
                        "width": 1.0,
                        "height": 1.0,
                        "shape": "rect",
                        "layer": "F.Cu",
                    }
                ],
            },
            {
                "ref": "S",
                "position": (30.0, 20.0),
                "rotation_deg": 0.0,
                "nets": ["GND"],
                "pads": [
                    {
                        "number": "1",
                        "net": "GND",
                        "offset": (0.0, 0.0),
                        "width": 1.0,
                        "height": 1.0,
                        "shape": "rect",
                        "layer": "F.Cu",
                    }
                ],
            },
        ],
        "nets": {},
        "board": {"surface_cutouts": []},
    }
    domains = {"AC_L": VoltageDomain.MAINS, "GND": VoltageDomain.LV_CONTROL}
    prepared = dataclasses.replace(
        _prepared(),
        netlist=Netlist(components=components),
        board=Board(width=60.0, height=50.0),
        manifest_path=manifest,
        domain_constraints=tuple(
            generate_domain_clearance_constraints(placement, domains, {"H", "S"})
        ),
        validator_placement=placement,
        voltage_domains=domains,
        fab_bodies={
            ref: FabBody(
                component_ref=ref,
                points=[(-1.0, -1.0), (1.0, -1.0), (1.0, 1.0), (-1.0, 1.0)],
            )
            for ref in ("H", "S")
        },
        body_allowlist=EMPTY_ALLOWLIST,
    )

    record = run_prepared_corridor_experiment(prepared)
    assert [axis.axis for axis in record.axes] == ["x", "y"]
    assert all(axis.execution_outcome == "returned" for axis in record.axes)
    assert all(axis.acceptance_verdict == "accepted" for axis in record.axes)
    output = tmp_path / "record.json"
    write_experiment_record(record, output)
    assert canonical_experiment_json(read_experiment_record(output)) == canonical_experiment_json(
        record
    )


def test_identity_changes_for_every_meaningful_input(tmp_path: Path) -> None:
    pcb = tmp_path / "board.kicad_pcb"
    constraints = tmp_path / "constraints.yaml"
    manifest = tmp_path / "manifest.yaml"
    allowlist = tmp_path / "allowlist.yaml"
    for path, text in (
        (pcb, "pcb"),
        (constraints, "constraints"),
        (manifest, "manifest"),
        (allowlist, "allowlist"),
    ):
        path.write_text(text, encoding="utf-8")
    kwargs = {
        "pcb_path": pcb,
        "constraints_path": constraints,
        "manifest_path": manifest,
        "allowlist_path": allowlist,
        "requirements": (("H", "S", 12.6),),
        "partition": {"hv_only": ("H",), "selv_only": ("S",), "isolators": (), "unclassified": ()},
        "gap_mm": 12.6,
        "polarity": "hv-low-selv-high",
        "seed": 0,
        "num_search_workers": 4,
        "solve_limit_s": 120.0,
        "watchdog_grace_s": 5.0,
        "warm_start_limit_s": 30.0,
    }
    baseline = build_experiment_identity(**kwargs)
    assert {name for name, _digest in baseline.tool_code_sha256} == {
        "corridor",
        "experiment",
        "production_inputs",
        "solver",
        "solver_telemetry",
    }
    variants = [
        {"requirements": (("H", "S", 8.0),)},
        {
            "partition": {
                "hv_only": ("H2",),
                "selv_only": ("S",),
                "isolators": (),
                "unclassified": (),
            }
        },
        {"gap_mm": 8.0},
        {"polarity": "selv-low-hv-high"},
        {"seed": 1},
        {"num_search_workers": 3},
        {"solve_limit_s": 60.0},
    ]
    for changed in variants:
        assert build_experiment_identity(**(kwargs | changed)) != baseline
    pcb.write_text("changed pcb", encoding="utf-8")
    assert build_experiment_identity(**kwargs) != baseline


def test_canonical_serialization_is_stable_and_atomic(tmp_path: Path) -> None:
    record = CreepageSearchCorridorExperimentRecord(
        identity=_identity(),
        axes=(_axis("x", solver="unknown"), _axis("y", solver="unknown")),
    )
    expected = canonical_experiment_json(record)
    assert expected == canonical_experiment_json(record)
    assert json.loads(expected)["schema"] == "temper.creepage-search-corridor-experiment"

    destination = tmp_path / "nested" / "result.json"
    write_experiment_record(record, destination)
    assert destination.read_text(encoding="utf-8") == expected + "\n"
    assert canonical_experiment_json(read_experiment_record(destination)) == expected
    assert not list(destination.parent.glob("*.tmp"))
