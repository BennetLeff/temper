"""Property-based tests (G4) for the orchestration-port unit U-F feedback
loop (Rust Orchestration Engine plan 2026-08-09-001): the
``AutomatedZeroDRC.run()`` iterate-until-clean LOOP, now implemented in Rust
(``temper-orchestration``'s ``run_automated_zero_drc`` pyfunction driving the
per-iteration call-backs through ``PipelineRunner<BoardState>``, the U-E
pattern).

The unit under test is the LOOP: the per-iteration call sequence (pipeline.run
-> drc_runner -> parse -> [get_zone_config, map x n] -> [get_zone_config,
compute_adjustments] -> update_config -> EXP-5 state reset), the break
conditions (clean-parse truthiness, empty-adjustments truthiness), the
iteration cap, the loop's determinism, and the reset's preserve/clear field
split. The call-backs are deterministic fakes driven by a randomized scenario
(the leaf compute is pinned by the Wave-4 Phase-5 differentials; the oracle
parity by ``test_orchestrator_rust_differential.py``).

Module-to-property map (G4 -- every reachable loop behavior pinned):
- P1  -- call ORDER: the per-iteration sequence matches the reference model
  (a pure-Python transcription of the oracle loop) for every scenario.
- P2  -- DETERMINISM: the same scenario yields a byte-identical call log and
  final state across runs.
- P3  -- ITERATION CAP: with violations + adjustments always present, the
  loop runs pipeline exactly ``max_iterations`` times.
- P4  -- BREAK-ON-CLEAN: a zero-violation parse halts the loop after the
  pipeline run that produced it (no map/adjust/update calls; the returned
  state is the pipeline's output, NOT the reset).
- P5  -- BREAK-ON-NO-ADJUSTMENTS: violations found but an empty adjustments
  dict halts the loop after the pipeline run (update_config never called).
- P6  -- EXP-5 STATE RESET: after an adjusting iteration, the threaded state
  keeps board/netlist/locked_routes/config and clears derived state
  (routes/vias back to defaults).

Non-vacuity: every property routes its observable through an ``impl``
parameter (default: the Rust pyclass loop) and has a
``test_pN_fails_for_<mutant>`` companion re-running the body against a
degenerate Python stand-in and asserting AssertionError.
"""

from __future__ import annotations

import pytest
import temper_orchestration as _to
from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.core.board import Board, Trace, Via
from temper_placer.deterministic.feedback import (
    AdjustmentResult,
    DRCViolation,
    ZoneAdjustment,
)
from temper_placer.deterministic.state import BoardState

# ---------------------------------------------------------------------------
# The loop under test + degenerate mutants (vacuity guards)
# ---------------------------------------------------------------------------


def _rust_run(scenario) -> tuple[list[str], BoardState | None]:
    """The U-F loop under test: the Rust pyfunction with scenario-driven
    deterministic fakes. Returns (recorded call log, final state)."""
    fakes = _build_fakes(scenario)
    out = _to.run_automated_zero_drc(
        pipeline=fakes["pipeline"],
        drc_runner=fakes["drc_runner"],
        parse_kicad_drc=fakes["parse"],
        mapper=fakes["mapper"],
        adjuster=fakes["adjuster"],
        get_zone_config=fakes["get_zone_config"],
        update_config=fakes["update_config"],
        max_iterations=scenario["max_iterations"],
        initial_state=scenario["initial_state"],
    )
    return fakes["log"], out


def _reference_log(scenario) -> list[str]:
    """Pure-Python transcription of the oracle loop -- the expected call log
    for a scenario. (P1's reference model.) Only the call-back invocations
    the fakes record appear; the termination is observed through the counts
    (P3/P4/P5), not an invented marker."""
    log = []
    n = scenario["max_iterations"]
    for i in range(n):
        log.append("pipeline.run")
        log.append("drc_runner")
        log.append("parse")
        if scenario["violations_per_iter"][i] == 0:
            break
        log.append("get_zone_config")
        for _ in range(scenario["violations_per_iter"][i]):
            log.append("map_violation")
        log.append("get_zone_config")
        log.append("compute_adjustments")
        if not scenario["adjustments_nonempty"][i]:
            break
        log.append("update_config")
    return log


# --- mutants (each implements a BUGGY variant of the loop over the same
# --- scenario-driven fakes; the property bodies must trip on them) ---


def _mutant_reversed(scenario) -> tuple[list[str], BoardState | None]:
    """P1 mutant: drc_runner is invoked BEFORE pipeline.run each iteration."""
    fakes = _build_fakes(scenario)
    for _ in range(scenario["max_iterations"]):
        fakes["drc_runner"]()
        fakes["pipeline"].run(scenario["initial_state"])
        violations = fakes["parse"]("report.json")
        if not violations:
            fakes["log"].append("break-clean")
            break
        fakes["get_zone_config"]()
        for v in violations:
            fakes["mapper"].map_violation(v)
        fakes["get_zone_config"]()
        adj = fakes["adjuster"].compute_adjustments([])
        if not adj.adjustments:
            fakes["log"].append("break-no-adjustments")
            break
        fakes["update_config"](adj)
        fakes["log"].append("reset")
    return fakes["log"], None


def _mutant_nondeterministic(scenario) -> tuple[list[str], BoardState | None]:
    """P2 mutant: every second invocation skips the adjuster refresh."""
    _MUTATION_STATE["runs"] += 1
    fakes = _build_fakes(scenario)
    skip = _MUTATION_STATE["runs"] % 2 == 0
    n = scenario["max_iterations"]
    for _i in range(n):
        fakes["pipeline"].run(scenario["initial_state"])
        fakes["drc_runner"]()
        violations = fakes["parse"]("report.json")
        if not violations:
            fakes["log"].append("break-clean")
            break
        fakes["get_zone_config"]()
        for v in violations:
            fakes["mapper"].map_violation(v)
        if not skip:
            fakes["get_zone_config"]()
        adj = fakes["adjuster"].compute_adjustments([])
        if not adj.adjustments:
            fakes["log"].append("break-no-adjustments")
            break
        fakes["update_config"](adj)
        fakes["log"].append("reset")
    return fakes["log"], None


def _mutant_cap_plus_one(scenario) -> tuple[list[str], BoardState | None]:
    """P3 mutant: runs one extra iteration past the cap."""
    fakes = _build_fakes(scenario)
    for _ in range(scenario["max_iterations"] + 1):
        fakes["pipeline"].run(scenario["initial_state"])
        fakes["drc_runner"]()
        violations = fakes["parse"]("report.json")
        if not violations:
            fakes["log"].append("break-clean")
            break
        fakes["get_zone_config"]()
        for v in violations:
            fakes["mapper"].map_violation(v)
        fakes["get_zone_config"]()
        adj = fakes["adjuster"].compute_adjustments([])
        if not adj.adjustments:
            fakes["log"].append("break-no-adjustments")
            break
        fakes["update_config"](adj)
        fakes["log"].append("reset")
    return fakes["log"], None


def _mutant_continue_after_clean(scenario) -> tuple[list[str], BoardState | None]:
    """P4 mutant: keeps iterating after a clean parse."""
    fakes = _build_fakes(scenario)
    ran = 0
    for _ in range(scenario["max_iterations"]):
        fakes["pipeline"].run(scenario["initial_state"])
        fakes["drc_runner"]()
        violations = fakes["parse"]("report.json")
        if not violations and ran > 0:
            fakes["log"].append("break-clean")
            break
        ran += 1
        if not violations:
            continue  # BUG: no break -- loop continues
        fakes["get_zone_config"]()
        for v in violations:
            fakes["mapper"].map_violation(v)
        fakes["get_zone_config"]()
        adj = fakes["adjuster"].compute_adjustments([])
        if not adj.adjustments:
            fakes["log"].append("break-no-adjustments")
            break
        fakes["update_config"](adj)
        fakes["log"].append("reset")
    return fakes["log"], None


def _mutant_update_anyway(scenario) -> tuple[list[str], BoardState | None]:
    """P5 mutant: calls update_config even when adjustments are empty."""
    fakes = _build_fakes(scenario)
    for _ in range(scenario["max_iterations"]):
        fakes["pipeline"].run(scenario["initial_state"])
        fakes["drc_runner"]()
        violations = fakes["parse"]("report.json")
        if not violations:
            fakes["log"].append("break-clean")
            break
        fakes["get_zone_config"]()
        for v in violations:
            fakes["mapper"].map_violation(v)
        fakes["get_zone_config"]()
        adj = fakes["adjuster"].compute_adjustments([])
        if not adj.adjustments:
            fakes["update_config"](adj)  # BUG: update despite empty
            fakes["log"].append("break-no-adjustments")
            break
        fakes["update_config"](adj)
        fakes["log"].append("reset")
    return fakes["log"], None


def _mutant_no_reset(scenario) -> tuple[list[str], BoardState | None]:
    """P6 mutant: returns the pipeline output without the EXP-5 reset."""
    fakes = _build_fakes(scenario)
    state = scenario["initial_state"]
    for _i in range(scenario["max_iterations"]):
        state = fakes["pipeline"].run(state)
        fakes["drc_runner"]()
        violations = fakes["parse"]("report.json")
        if not violations:
            fakes["log"].append("break-clean")
            break
        fakes["get_zone_config"]()
        for v in violations:
            fakes["mapper"].map_violation(v)
        fakes["get_zone_config"]()
        adj = fakes["adjuster"].compute_adjustments([])
        if not adj.adjustments:
            fakes["log"].append("break-no-adjustments")
            break
        fakes["update_config"](adj)
        # BUG: no BoardState reset -- derived state survives
        fakes["log"].append("reset")
    return fakes["log"], state


_MUTATION_STATE = {"runs": 0}


def _assert_mutant_detected(body, mutant, scenario) -> None:
    """Run ``body`` against the degenerate mutant; the body's assertions MUST
    trip. If they do not, the property is vacuous -- a hard failure."""
    with pytest.raises(AssertionError):
        body(mutant, scenario)


# ---------------------------------------------------------------------------
# Deterministic fakes (scenario-driven)
# ---------------------------------------------------------------------------


def _out_state() -> BoardState:
    """The pipeline-output state the fakes return: carries non-default
    derived state (routes/vias) so the P6 reset split is observable."""
    return BoardState(
        board=Board(width=100.0, height=80.0, zones=[]),
        locked_routes=frozenset({"NET1"}),
        config={"block": "hv_lv"},
        routes=frozenset({
            Trace(start=(0.0, 0.0), end=(10.0, 10.0), width=0.25, layer="F.Cu", net="NET1")
        }),
        vias=frozenset({
            Via(
                position=(5.0, 5.0),
                drill=0.3,
                width=0.6,
                layers=("F.Cu", "B.Cu"),
                net="VIA1",
            )
        }),
    )


_ZONE_CFG = {
    "HV": {
        "bounds": ((0.0, 0.0), (50.0, 100.0)),
        "max_size": (100.0, 100.0),
        "can_expand": ["right", "left", "up", "down"],
    },
}


def _build_fakes(scenario):
    """Build the deterministic fakes from a scenario. Every fake appends its
    call to the shared log; the adjuster's per-call decision comes from
    ``scenario["adjustments_nonempty"]`` in call order."""
    log: list[str] = []
    adj_script = list(scenario["adjustments_nonempty"])

    class _Pipeline:
        def __init__(self):
            self.stages = []
            self.calls = 0

        def run(self, state):
            self.calls += 1
            log.append("pipeline.run")
            return scenario["out_state"]  # the SHARED pipeline-output object

    class _Runner:
        def __call__(self):
            log.append("drc_runner")
            return "report.json"

    def _parse(report_path):
        log.append("parse")
        idx = min(_parse.calls, len(scenario["violations_per_iter"]) - 1)
        n = scenario["violations_per_iter"][idx]
        _parse.calls += 1
        return [_VIOLATION] * n

    _parse.calls = 0

    class _Mapper:
        def __init__(self):
            self.zone_config = None

        def map_violation(self, violation):
            log.append("map_violation")

    class _Adjuster:
        def __init__(self):
            self.zone_config = None

        def compute_adjustments(self, violations):
            log.append("compute_adjustments")
            nonempty = adj_script.pop(0) if adj_script else False
            if nonempty:
                return AdjustmentResult(
                    adjustments={"HV": ZoneAdjustment(zone_name="HV", delta_width=5.0)}
                )
            return AdjustmentResult(adjustments={})

    def _get_zone_config():
        log.append("get_zone_config")
        return _ZONE_CFG

    def _update_config(adjustment):
        log.append("update_config")

    return {
        "pipeline": _Pipeline(),
        "drc_runner": _Runner(),
        "parse": _parse,
        "mapper": _Mapper(),
        "adjuster": _Adjuster(),
        "get_zone_config": _get_zone_config,
        "update_config": _update_config,
        "log": log,
    }


_VIOLATION = DRCViolation(type="clearance", items=["of Q1"], pos=(10, 10))


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------


@st.composite
def _scenarios(draw):
    max_iterations = draw(st.integers(min_value=0, max_value=5))
    violations = draw(
        st.lists(st.integers(min_value=0, max_value=3), min_size=max_iterations,
                 max_size=max_iterations)
    )
    adjustments = draw(
        st.lists(st.booleans(), min_size=max_iterations, max_size=max_iterations)
    )
    return {
        "max_iterations": max_iterations,
        "violations_per_iter": violations,
        "adjustments_nonempty": adjustments,
        "initial_state": draw(st.one_of(st.none(), st.just(_out_state()))),
        "out_state": _out_state(),
    }


# ---------------------------------------------------------------------------
# P1 -- call order matches the reference model
# ---------------------------------------------------------------------------


def _body_p1(impl, scenario) -> None:
    log, _final = impl(scenario)
    assert log == _reference_log(scenario), (
        f"call log diverged from the reference model:\n"
        f"  loop={log}\n  ref ={_reference_log(scenario)}"
    )


@given(_scenarios())
@settings(max_examples=100, deadline=None)
def test_p1_call_order_matches_reference_model(scenario):
    _body_p1(_rust_run, scenario)


def test_p1_fails_for_reversed_mutant() -> None:
    _assert_mutant_detected(
        _body_p1, _mutant_reversed,
        {"max_iterations": 3,
         "violations_per_iter": [1, 0, 0],
         "adjustments_nonempty": [True, True, True],
         "initial_state": None, "out_state": _out_state()},
    )


# ---------------------------------------------------------------------------
# P2 -- determinism
# ---------------------------------------------------------------------------


def _body_p2(impl, scenario) -> None:
    log1, final1 = impl(scenario)
    log2, final2 = impl(scenario)
    assert log1 == log2, "two runs of the same scenario diverged in the call log"
    assert repr(final1) == repr(final2), "two runs of the same scenario diverged"


@given(_scenarios())
@settings(max_examples=100, deadline=None)
def test_p2_loop_is_deterministic(scenario):
    _body_p2(_rust_run, scenario)


def test_p2_fails_for_nondeterministic_mutant() -> None:
    _MUTATION_STATE["runs"] = 0
    _assert_mutant_detected(
        _body_p2, _mutant_nondeterministic,
        {"max_iterations": 2,
         "violations_per_iter": [1, 1],
         "adjustments_nonempty": [True, True],
         "initial_state": None, "out_state": _out_state()},
    )


# ---------------------------------------------------------------------------
# P3 -- iteration cap
# ---------------------------------------------------------------------------


def _body_p3(impl, scenario) -> None:
    log, _final = impl(scenario)
    n = log.count("pipeline.run")
    assert n == scenario["max_iterations"], (
        f"pipeline ran {n} times, expected {scenario['max_iterations']}"
    )


@given(_scenarios())
@settings(max_examples=100, deadline=None)
def test_p3_pipeline_runs_exactly_cap_times(scenario):
    # Only scenarios where the loop cannot break early exercise the cap:
    # violations + adjustments present every iteration.
    if all(v > 0 for v in scenario["violations_per_iter"]) and all(
        scenario["adjustments_nonempty"]
    ):
        _body_p3(_rust_run, scenario)


def test_p3_fails_for_cap_plus_one_mutant() -> None:
    _assert_mutant_detected(
        _body_p3, _mutant_cap_plus_one,
        {"max_iterations": 2,
         "violations_per_iter": [1, 1],
         "adjustments_nonempty": [True, True],
         "initial_state": None, "out_state": _out_state()},
    )


# ---------------------------------------------------------------------------
# P4 -- break on a clean parse
# ---------------------------------------------------------------------------


def _body_p4(impl, scenario) -> None:
    log, final = impl(scenario)
    # A clean first parse halts the loop after ONE pipeline run.
    assert log.count("pipeline.run") == 1
    assert log.count("drc_runner") == 1
    assert "map_violation" not in log
    assert "compute_adjustments" not in log
    assert "update_config" not in log
    # The returned state is the pipeline's output (no reset on this path).
    assert repr(final) == repr(_out_state())


@given(_scenarios())
@settings(max_examples=100, deadline=None)
def test_p4_clean_parse_breaks_immediately(scenario):
    if scenario["max_iterations"] > 0 and scenario["violations_per_iter"][0] == 0:
        _body_p4(_rust_run, scenario)


def test_p4_fails_for_continue_after_clean_mutant() -> None:
    _assert_mutant_detected(
        _body_p4, _mutant_continue_after_clean,
        {"max_iterations": 3,
         "violations_per_iter": [0, 1, 0],
         "adjustments_nonempty": [True, True, True],
         "initial_state": None, "out_state": _out_state()},
    )


# ---------------------------------------------------------------------------
# P5 -- break on an empty adjustments dict
# ---------------------------------------------------------------------------


def _body_p5(impl, scenario) -> None:
    log, _final = impl(scenario)
    # Violations found but zero adjustments: one pipeline run, no config
    # update, no reset.
    assert log.count("pipeline.run") == 1
    assert log.count("drc_runner") == 1
    assert "update_config" not in log


@given(_scenarios())
@settings(max_examples=100, deadline=None)
def test_p5_empty_adjustments_break_immediately(scenario):
    if (
        scenario["max_iterations"] > 0
        and scenario["violations_per_iter"][0] > 0
        and not scenario["adjustments_nonempty"][0]
    ):
        _body_p5(_rust_run, scenario)


def test_p5_fails_for_update_anyway_mutant() -> None:
    _assert_mutant_detected(
        _body_p5, _mutant_update_anyway,
        {"max_iterations": 2,
         "violations_per_iter": [1, 1],
         "adjustments_nonempty": [False, True],
         "initial_state": None, "out_state": _out_state()},
    )


# ---------------------------------------------------------------------------
# P6 -- the EXP-5 state reset (preserve/clear split)
# ---------------------------------------------------------------------------


def _body_p6(impl, scenario) -> None:
    _log, final = impl(scenario)
    out = scenario["out_state"]
    # Preserved: board / netlist / locked_routes / config carry the pipeline
    # output's values (board keeps OBJECT IDENTITY -- the reset preserves the
    # exact object, not a copy).
    assert final.board is out.board
    assert final.locked_routes == frozenset({"NET1"})
    assert final.config == {"block": "hv_lv"}
    # Cleared: derived routing state reset to defaults.
    assert final.routes == frozenset()
    assert final.vias == frozenset()


@given(_scenarios())
@settings(max_examples=100, deadline=None)
def test_p6_reset_preserves_locks_and_clears_derived_state(scenario):
    if (
        scenario["max_iterations"] > 0
        and all(v > 0 for v in scenario["violations_per_iter"])
        and all(scenario["adjustments_nonempty"])
    ):
        _body_p6(_rust_run, scenario)


def test_p6_fails_for_no_reset_mutant() -> None:
    _assert_mutant_detected(
        _body_p6, _mutant_no_reset,
        {"max_iterations": 1,
         "violations_per_iter": [1],
         "adjustments_nonempty": [True],
         "initial_state": None, "out_state": _out_state()},
    )
