"""Differential test: Rust CP-SAT loop orchestration vs the pinned Python oracle.

Orchestration-port unit U-I (Rust Orchestration Engine plan 2026-08-09-001):
the residual non-ortools orchestration of ``placer/cp_sat/_loop_core.py`` --
the loop SEQUENCING, gate checks, and convergence/stability/feedback
DECISIONS -- moved to ``temper-orchestration``'s ``cpsat_loop.rs``. The
pre-migration ``_LoopCoreMixin`` is pinned VERBATIM as
``_loop_core_py_oracle.py``; every assertion here drives IDENTICAL inputs
through both the delegated ``PlaceRouteLoop`` (Rust loop) and an
``OracleLoop`` that mixes in the verbatim Python mixin, and asserts the
canonicalized ``LoopResult``, the solver call sequence (timeout/seed/
constraint-count -- the solve-budget and delta-re-solve sequencing) and the
route call sequence are byte-identical.

Boundary (what is NOT compared -- the Python call-backs both sides share by
construction): the CP-SAT solve itself (``encoder.solve_placement`` is
mocked identically for both), ``_route_placement`` (mocked identically), the
``FeedbackClassifier`` (real, shared -- its own U-I slice), the gate
implementations (mocked), and the field compute (off here). Wall-clock is
made deterministic by patching ``time.monotonic`` on BOTH the delegated
module and the oracle module with an identical fixed-increment sequence, so
``solve_time_ms`` / ``route_time_ms`` are byte-identical too (the migrated
surface is the sequencing; the timing call-back is the mockable wall clock,
preserved on both sides).

Each scenario is a FACTORY returning fresh solver/route callables, so the
two loop runs (delegated then oracle) share no mutable mock state.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from unittest import mock

import numpy as np

import tests.placer.cp_sat._loop_core_py_oracle as _oracle
from temper_placer.placer.cp_sat.encoder import CpSatPlacementResult
from temper_placer.placer.cp_sat.gates import GateResult, GateStatus
from temper_placer.placer.cp_sat.loop import PlaceRouteLoop

ORACLE_TIME = "tests.placer.cp_sat._loop_core_py_oracle.time.monotonic"
DELEG_TIME = "temper_placer.placer.cp_sat._loop_core.time.monotonic"

_GATE_CLASSES = ("DrcGate", "RoutingGate", "StackupGate", "PhysicsGate", "QualityGate")


class OracleLoop(_oracle._LoopCoreMixin, PlaceRouteLoop):
    """``PlaceRouteLoop`` driven by the VERBATIM pre-migration loop core."""


# ---------------------------------------------------------------------------
# Fixtures / mocks
# ---------------------------------------------------------------------------


@dataclass
class MockComp:
    ref: str
    footprint: str = "Resistor_SMD:R_0805_2012Metric"
    pins: list = field(default_factory=list)


@dataclass
class MockNet:
    name: str


@dataclass
class MockNetlist:
    components: list
    nets: list = field(default_factory=lambda: [MockNet("GND"), MockNet("VCC")])


@dataclass
class MockZone:
    name: str
    bounds: tuple


@dataclass
class MockBoard:
    zones: list
    width: float = 100.0
    height: float = 100.0


@dataclass
class MockRoutingResult:
    completion_rate: float = 0.5
    unrouted_nets: list = field(default_factory=list)
    drc_violations: list = field(default_factory=list)
    congestion_regions: list = field(default_factory=list)
    drc_errors: int = 0


def _netlist():
    return MockNetlist(components=[MockComp("Q1"), MockComp("Q2"), MockComp("C_BUS1")])


def _board():
    return MockBoard(zones=[MockZone("power_zone", (0, 0, 50, 50))])


def _placement(round_num: int = 0):
    x_offset = round_num * 0.5
    return CpSatPlacementResult(
        positions=np.array(
            [[10.0 + x_offset, 20.0], [30.0, 40.0], [50.0, 60.0]], dtype=np.float32
        ),
        rotations=np.array([0, 0, 0], dtype=np.int32),
        placed_refs=["Q1", "Q2", "C_BUS1"],
        status="optimal",
        solve_time_ms=50.0,
    )


def _unsat():
    return CpSatPlacementResult(
        positions=np.zeros((3, 2), dtype=np.float32),
        rotations=np.zeros(3, dtype=np.int32),
        placed_refs=[],
        unplaced_refs=["Q1", "Q2", "C_BUS1"],
        status="infeasible",
    )


def _mono():
    """A fixed-increment ``time.monotonic`` stand-in (deterministic timing)."""
    state = [0.0]

    def tick():
        state[0] += 0.05
        return state[0]

    return tick


def _solver_optimal(*args, **kwargs):
    """Stateless optimal solve stub (the mocked solve boundary)."""
    return _placement()


def _solver_unsat(*args, **kwargs):
    """Stateless infeasible solve stub."""
    return _unsat()


def _solver_oscillation(*args, **kwargs):
    """Stateless identical-position solve stub (drives the oscillation exit)."""
    return _placement(0)


def _route_clean(placement, *args, **kwargs):
    """Stateless clean-route stub."""
    return MockRoutingResult(completion_rate=1.0, drc_errors=0)


def _route_zero(placement, *args, **kwargs):
    """Stateless zero-completion route stub."""
    return MockRoutingResult(completion_rate=0.0, drc_errors=0)


def _clearance_violation():
    return type("V", (), {"comp_a": "Q1", "comp_b": "Q2", "required_mm": 6.0})()


# ---------------------------------------------------------------------------
# Canonicalization (the migrated decision surface, minus the shared call-backs)
# ---------------------------------------------------------------------------


def _canon_core(core):
    if core is None:
        return None
    if isinstance(core, dict):
        return tuple(sorted((k, _canon_core(v)) for k, v in core.items()))
    if isinstance(core, (list, tuple)):
        return tuple(_canon_core(v) for v in core)
    return core


def _canon(result):
    """Canonicalize a LoopResult into plain comparable tuples.

    Floats compared bit-exactly via ``float.hex()`` (deterministic: identical
    inputs + identical mocked wall clock). Delta ordering is preserved (the
    priority-sorted backtracking order IS the migrated surface).
    """
    return (
        result.success,
        result.reason,
        tuple(
            (
                r.round_number,
                float(r.completion_rate).hex(),
                r.drc_errors,
                float(r.solve_time_ms).hex(),
                float(r.route_time_ms).hex(),
                r.status,
                tuple(d.reason for d in r.deltas_applied),
            )
            for r in result.rounds
        ),
        _canon_core(result.unsat_core),
        tuple(sorted(result.unmeasured_gates.items())),
        getattr(result.placement, "status", None),
        float(getattr(result.routing, "completion_rate", float("nan"))).hex(),
    )


# ---------------------------------------------------------------------------
# The driver
# ---------------------------------------------------------------------------


def _drive(
    loop_cls,
    time_target,
    solver_factory,
    route_factory,
    all_gates,
    gates_clean,
    patches_factory=None,
):
    loop = loop_cls()
    solver_fn = solver_factory()
    route_fn = route_factory()
    solve_trace = []
    route_trace = []

    def rec_solver(**kwargs):
        solve_trace.append(
            (kwargs.get("timeout_ms"), kwargs.get("seed"), len(kwargs.get("extra_constraints") or []))
        )
        return solver_fn(**kwargs)

    def rec_route(placement, netlist, board, seed, **kwargs):
        route_trace.append(tuple(sorted(kwargs.keys())))
        return route_fn(placement, netlist, board, seed, **kwargs)

    patches = [
        mock.patch(
            "temper_placer.placer.cp_sat.encoder.solve_placement", side_effect=rec_solver
        ),
        mock.patch.object(loop, "_route_placement", side_effect=rec_route),
        mock.patch(time_target, side_effect=_mono()),
    ]
    if gates_clean:
        for gate in _GATE_CLASSES:
            patches.append(
                mock.patch(
                    f"temper_placer.placer.cp_sat.gates.{gate}.check",
                    return_value=GateResult(GateStatus.CLEAN),
                )
            )
    if patches_factory is not None:
        patches.extend(patches_factory())
    with contextlib.ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        result = loop.run(_netlist(), _board(), seed=42, all_gates=all_gates)
    return _canon(result), solve_trace, route_trace


def _assert_identical(
    scenario_name,
    solver_factory,
    route_factory,
    all_gates=False,
    gates_clean=True,
    patches_factory=None,
):
    """Run one scenario through both loops and assert byte-identical results
    and call sequences."""
    deleg = _drive(
        PlaceRouteLoop, DELEG_TIME, solver_factory, route_factory, all_gates, gates_clean, patches_factory
    )
    oracle = _drive(
        OracleLoop, ORACLE_TIME, solver_factory, route_factory, all_gates, gates_clean, patches_factory
    )

    d_canon, d_solve, d_route = deleg
    o_canon, o_solve, o_route = oracle
    assert d_canon == o_canon, (
        f"[{scenario_name}] LoopResult diverged:\n  delegated={d_canon}\n  oracle={o_canon}"
    )
    assert d_solve == o_solve, (
        f"[{scenario_name}] solver call sequence diverged: {d_solve} vs {o_solve}"
    )
    assert d_route == o_route, (
        f"[{scenario_name}] route call sequence diverged: {d_route} vs {o_route}"
    )


# ---------------------------------------------------------------------------
# Legacy (classifier) loop scenarios
# ---------------------------------------------------------------------------


def test_clean_placement_converges():
    _assert_identical(
        "clean",
        lambda: _solver_optimal,
        lambda: _route_clean,
    )


def test_single_clearance_violation_injects_delta():
    def make_route():
        calls = [0]

        def route(placement, netlist, board, seed, **kwargs):
            calls[0] += 1
            if calls[0] == 1:
                return MockRoutingResult(
                    completion_rate=1.0, drc_errors=1, drc_violations=[_clearance_violation()]
                )
            return MockRoutingResult(completion_rate=1.0, drc_errors=0)

        return route

    _assert_identical("clearance", lambda: _solver_optimal, make_route)


def test_closed_loop_backtracking():
    """Clearance delta UNSAT -> try congestion delta (priority order)."""
    from temper_placer.placer.cp_sat.loop import UnsatError

    def make_route():
        calls = [0]

        def route(placement, netlist, board, seed, **kwargs):
            calls[0] += 1
            if calls[0] == 1:
                return MockRoutingResult(
                    completion_rate=1.0,
                    drc_errors=1,
                    drc_violations=[_clearance_violation()],
                    congestion_regions=[
                        type(
                            "CR",
                            (),
                            {"comp_a": "Q1", "comp_b": "C_BUS1", "current_distance_mm": 2.0},
                        )()
                    ],
                )
            return MockRoutingResult(completion_rate=1.0, drc_errors=0)

        return route

    def make_delta():
        n = [0]

        def delta_side_effect(netlist, board, base_constraints, new_deltas, seed, warm=None):
            n[0] += 1
            if n[0] == 1:  # clearance (priority 5) UNSAT
                raise UnsatError(deltas=[], message="clearance unsat")
            return _placement()  # congestion (priority 10) works

        return delta_side_effect

    # patch _solve_with_delta on BOTH instances: the try/except backtracking
    # (skip UnsatError -> next delta) is what is exercised identically.
    deleg = _drive_with_delta_patch(PlaceRouteLoop, DELEG_TIME, make_route, make_delta)
    oracle = _drive_with_delta_patch(OracleLoop, ORACLE_TIME, make_route, make_delta)
    assert deleg == oracle


def _drive_with_delta_patch(loop_cls, time_target, route_factory, delta_factory):
    loop = loop_cls()
    route_fn = route_factory()
    solve_trace = []
    route_trace = []

    def rec_solver(**kwargs):
        solve_trace.append(
            (kwargs.get("timeout_ms"), kwargs.get("seed"), len(kwargs.get("extra_constraints") or []))
        )
        return _placement()

    def rec_route(placement, netlist, board, seed, **kwargs):
        route_trace.append(tuple(sorted(kwargs.keys())))
        return route_fn(placement, netlist, board, seed, **kwargs)

    patches = [
        mock.patch(
            "temper_placer.placer.cp_sat.encoder.solve_placement", side_effect=rec_solver
        ),
        mock.patch.object(loop, "_route_placement", side_effect=rec_route),
        mock.patch.object(loop, "_solve_with_delta", side_effect=delta_factory()),
        mock.patch(time_target, side_effect=_mono()),
    ]
    with contextlib.ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        result = loop.run(_netlist(), _board(), seed=42, all_gates=False)
    return _canon(result), solve_trace, route_trace


def test_all_feedback_unsat_exits():
    from temper_placer.placer.cp_sat.loop import UnsatError

    def make_route():
        def route(placement, netlist, board, seed, **kwargs):
            return MockRoutingResult(
                completion_rate=1.0, drc_errors=1, drc_violations=[_clearance_violation()]
            )

        return route

    def make_delta():
        def unsat_delta(netlist, board, base_constraints, new_deltas, seed, warm=None):
            raise UnsatError(deltas=[], message="unsat")

        return unsat_delta

    deleg = _drive_with_delta_patch(PlaceRouteLoop, DELEG_TIME, make_route, make_delta)
    oracle = _drive_with_delta_patch(OracleLoop, ORACLE_TIME, make_route, make_delta)
    assert deleg == oracle
    assert deleg[0][1] == "all_feedback_unsat"  # reason


def test_round_limit_exceeded():
    def make_solver():
        n = [0]

        def solver(**kwargs):
            n[0] += 1
            return _placement(n[0])  # drift to avoid oscillation

        return solver

    def make_route():
        def route(placement, netlist, board, seed, **kwargs):
            return MockRoutingResult(
                completion_rate=0.85,
                drc_errors=2,
                drc_violations=[_clearance_violation()],
            )

        return route

    _assert_identical("round_limit", make_solver, make_route)


def test_infeasible_first_solve_exits():
    _assert_identical(
        "infeasible",
        lambda: _solver_unsat,
        lambda: _route_zero,
    )


def test_no_classifiable_feedback_exits():
    def make_route():
        def route(placement, netlist, board, seed, **kwargs):
            # completion 0.5 with NO violations -> classifier produces no deltas.
            return MockRoutingResult(completion_rate=0.5, drc_errors=0)

        return route

    _assert_identical("no_feedback", lambda: _solver_optimal, make_route)


def test_oscillation_detected_exits():
    def make_route():
        def route(placement, netlist, board, seed, **kwargs):
            return MockRoutingResult(
                completion_rate=0.85,
                drc_errors=2,
                drc_violations=[_clearance_violation()],
            )

        return route

    # identical positions every round -> oscillation after OSCILLATION_WINDOW.
    _assert_identical("oscillation", lambda: _solver_oscillation, make_route)


# ---------------------------------------------------------------------------
# Gate-driven loop scenarios
# ---------------------------------------------------------------------------


def test_gates_all_clean_converges():
    _assert_identical(
        "gates_clean",
        lambda: _solver_optimal,
        lambda: _route_clean,
        all_gates=True,
    )


def test_gates_violation_injects_delta():
    """A DrcGate VIOLATION on round 1 exercises the ROUTING-stage delta
    collection + backtracking; the gates then go clean."""
    from temper_placer.placer.cp_sat.gates import Violation, ViolationType

    def make_drc():
        calls = [0]

        def drc_check(state):
            calls[0] += 1
            if calls[0] == 1:
                return GateResult(
                    GateStatus.VIOLATIONS,
                    violations=(
                        Violation(
                            type=ViolationType.CLEARANCE,
                            components=("Q1", "Q2"),
                            nets=(),
                            severity=1.0,
                            threshold=6.0,
                            description="clearance violation",
                            context={},
                        ),
                    ),
                )
            return GateResult(GateStatus.CLEAN)

        return drc_check

    def patches_factory():
        return [
            mock.patch(
                "temper_placer.placer.cp_sat.gates.DrcGate.check", side_effect=make_drc()
            )
        ] + [
            mock.patch(
                f"temper_placer.placer.cp_sat.gates.{gate}.check",
                return_value=GateResult(GateStatus.CLEAN),
            )
            for gate in ("RoutingGate", "StackupGate", "PhysicsGate", "QualityGate")
        ]

    # The shared DeltaMapper path (real) turns the clearance violation into a
    # SeparatedConstraint delta; both loops re-solve identically.
    deleg = _drive(
        PlaceRouteLoop,
        DELEG_TIME,
        lambda: _solver_optimal,
        lambda: _route_clean,
        all_gates=True,
        gates_clean=False,
        patches_factory=patches_factory,
    )
    oracle = _drive(
        OracleLoop,
        ORACLE_TIME,
        lambda: _solver_optimal,
        lambda: _route_clean,
        all_gates=True,
        gates_clean=False,
        patches_factory=patches_factory,
    )
    assert deleg == oracle
