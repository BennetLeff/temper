"""R1a: behavioural differential of the AutomatedZeroDRC feedback LOOP
against the pinned pre-migration oracle.

Rust Orchestration Engine plan 2026-08-09-001, orchestration-port unit U-F:
the iterate-until-clean LOOP of ``AutomatedZeroDRC.run()`` (solve -> run DRC
-> map violations -> adjust zones -> re-solve until clean or the iteration
cap) moves to ``temper-orchestration``'s ``run_automated_zero_drc``
pyfunction, which drives the per-iteration call-backs through the Rust
``PipelineRunner<BoardState>`` (the U-E pattern). The pre-migration
``orchestrator.py`` is pinned VERBATIM as the oracle
(``tests/deterministic/_orchestrator_py_oracle.py``, content-hash-pinned
below).

What this suite pins is the LOOP: both arms run the SAME call-backs (the
pipeline fake, the DRC-runner fake, the report parser, the violation mapper,
the zone adjuster and the config update -- the leaf compute is pinned
individually by the Wave-4 Phase-5 differentials), so the only divergence
surface is the iteration sequencing: the call ORDER, the break conditions
(truthiness of the parsed violations / of the adjustments dict), the
iteration cap, the EXP-5 state reset (board/netlist/locked_routes/config
preserved, derived state cleared) and the exception propagation. The tests
compare:

- the recorded call sequence per iteration (pipeline.run -> drc_runner ->
  parse -> [get_zone_config, map x n] -> [get_zone_config,
  compute_adjustments] -> update_config -> reset), including the per-call
  zone_config refresh values -- byte-identical between arms;
- the log-message sequence (both arms emit through the SAME logger name) --
  byte-identical;
- the iteration counts on every termination path (clean break, no-adjustment
  break, iteration-cap exhaustion);
- the config mutations on the raw-dict path (the shared ``_update_config``
  call-back; the effects must be identical because the loop drives them in
  the same order);
- the EXP-5 state-reset semantics: board/netlist/locked_routes/config
  preserved, derived fields (routes/vias) reset to defaults;
- exception propagation: a raising call-back halts both loops with the same
  exception.

Anti-vacuity: ``test_oracle_and_port_are_different_implementations`` asserts
the shim delegates to the Rust pyfunction (``__module__`` + bytecode), not
back onto the oracle. The oracle body digest below is pinned: a differential
whose oracle can be edited to agree with the port proves nothing.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import temper_orchestration as _to
import tests.deterministic._orchestrator_py_oracle as _orc

from temper_placer.core.board import Board, Trace, Via
from temper_placer.deterministic import feedback as _feedback_pkg
from temper_placer.deterministic.feedback import (
    AdjustmentResult,
    DRCViolation,
    ZoneAdjustment,
)
from temper_placer.deterministic.feedback import (
    AutomatedZeroDRC as _ShimAutomatedZeroDRC,
)
from temper_placer.deterministic.state import BoardState

# ---------------------------------------------------------------------------
# Oracle body pinning (G1)
# ---------------------------------------------------------------------------

_PINNED = {
    "_orchestrator_py_oracle.py": "544ca475ad442837752ff471f4c193935db450ce7b317cc3b1974e62f90a5f4f",
}
_BODY_MARKER = "# --- BEGIN PINNED BODY ---\n"


def test_oracle_body_matches_pinned_digests() -> None:
    for name, expected in _PINNED.items():
        text = (Path(__file__).with_name(name)).read_text(encoding="utf-8")
        assert _BODY_MARKER in text, f"{name} oracle header marker missing"
        body = text.split(_BODY_MARKER, 1)[1]
        digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
        assert digest == expected, (
            f"{name} oracle body changed; it must stay verbatim "
            f"(expected {expected}, got {digest})"
        )


def test_oracle_and_port_are_different_implementations() -> None:
    """Anti-vacuity: the shim must delegate to the Rust pyfunction."""
    # The pyfunction lives in the Rust crate (its module path starts with
    # the extension module name).
    assert _to.run_automated_zero_drc.__module__.startswith("temper_orchestration")
    # The shim run() calls the Rust pyfunction by name.
    assert (
        "run_automated_zero_drc"
        in _ShimAutomatedZeroDRC.run.__code__.co_names
    )
    # The oracle's run() does NOT reference the Rust pyfunction.
    assert (
        "run_automated_zero_drc"
        not in _orc.AutomatedZeroDRC.run.__code__.co_names
    )
    # The shim run loop is a different implementation from the oracle's
    # (different bytecode), and delegates through the temper_orchestration
    # module (the run method's `_to` global is the Rust crate).
    assert (
        _ShimAutomatedZeroDRC.run.__code__.co_code
        != _orc.AutomatedZeroDRC.run.__code__.co_code
    )
    assert _ShimAutomatedZeroDRC.run.__globals__["_to"] is _to
    # The oracle keeps the pure-Python loop (range-based).
    assert "range" in _orc.AutomatedZeroDRC.run.__code__.co_names


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


def _initial_config() -> dict:
    """Raw-dict config: HV zone on the left, MCU zone on the right."""
    return {
        "board": {"width_mm": 100.0, "height_mm": 100.0},
        "zones": [
            {"name": "HV", "bounds_ratio": [0.0, 0.0, 0.5, 1.0]},
            {"name": "MCU", "bounds_ratio": [0.5, 0.0, 1.0, 1.0]},
        ],
    }


def _mock_netlist():
    # A module-level singleton: the differential compares `repr`-recorded
    # state payloads across arms, and a fresh MagicMock per call would leak
    # its per-object id into the repr and break the comparison.
    global _NETLIST
    if _NETLIST is not None:
        return _NETLIST
    netlist = MagicMock()
    comp = MagicMock()
    comp.ref = "Q1"
    netlist.components = [comp]
    _NETLIST = netlist
    return _NETLIST


_NETLIST = None


def _violation():
    return DRCViolation(type="clearance", items=["of Q1"], pos=(10, 10))


def _populated_state() -> BoardState:
    """A BoardState carrying the fields the EXP-5 reset preserves."""
    return BoardState(
        board=Board(width=100.0, height=80.0, zones=[]),
        netlist=_mock_netlist(),
        locked_routes=frozenset({"NET1", "NET2"}),
        config={"block": "hv_lv"},
        routes=frozenset({_trace("NET1", (0.0, 0.0), (10.0, 10.0))}),
        vias=frozenset({_via("VIA1", (5.0, 5.0))}),
    )


def _trace(net, start, end) -> Trace:
    """Canonical route element: a ``Trace`` Rust pyclass (object form). Tuple
    routes ("NET1", ...) are NOT accepted by the shared Rust ``RouteSet``
    Marshal, which reads ``.start``/``.end`` (see issue #1143)."""
    return Trace(start=start, end=end, width=0.25, layer="F.Cu", net=net)


def _via(net, position) -> Via:
    """Canonical via element: a ``Via`` Rust pyclass (object form)."""
    return Via(
        position=position, drill=0.3, width=0.6, layers=("F.Cu", "B.Cu"), net=net
    )


def _run_arms(orc_kwargs, shim_kwargs):
    """Construct + run both arms with per-arm kwargs; return (orc, shim)."""
    orc = _orc.AutomatedZeroDRC(**orc_kwargs)
    shim = _ShimAutomatedZeroDRC(**shim_kwargs)
    return orc, shim


class _RecPipeline:
    """Fake pipeline: records each run() call (input state repr) and returns
    scripted states in order."""

    def __init__(self, states, log):
        self.states = list(states)
        self.log = log
        self.stages = []  # for _inject_zone_config (no zone_geometry stage)

    def run(self, state):
        self.log.append(("pipeline.run", repr(state)))
        return self.states.pop(0) if self.states else None


class _RecRunner:
    def __init__(self, log):
        self.log = log

    def __call__(self):
        self.log.append("drc_runner")
        return "report.json"


class _RecMapper:
    """Recording stand-in for ViolationComponentMapper (the leaf compute is
    pinned by the Wave-4 Phase-5 differential; here we pin the LOOP's call
    pattern and the per-iteration zone_config refresh)."""

    def __init__(self, netlist, zone_config, log, mapped_out=None):
        self.netlist = netlist
        self.zone_config = zone_config
        self.log = log
        self.mapped_out = mapped_out if mapped_out is not None else {"z": "HV"}

    def map_violation(self, violation):
        self.log.append(("map_violation", repr(violation), repr(self.zone_config)))
        return self.mapped_out


class _RecAdjuster:
    """Recording stand-in for ZoneAdjuster with a per-call script of
    adjustments dicts (empty dict -> the no-adjustment break)."""

    def __init__(self, zone_config, log, script, violation_threshold=5,
                 expansion_per_violation=0.5):
        self.zone_config = zone_config
        self.log = log
        self.script = list(script)
        self.violation_threshold = violation_threshold
        self.expansion_per_violation = expansion_per_violation

    def compute_adjustments(self, violations):
        self.log.append(("compute_adjustments", repr(self.zone_config), len(violations)))
        adj = self.script.pop(0) if self.script else {}
        return AdjustmentResult(adjustments=adj)


def _recording_update(log):
    def rec(adjustment):
        log.append(("update_config", repr(adjustment)))
    return rec


def _recording_get_zone_config(log, value):
    def rec():
        log.append("get_zone_config")
        return value
    return rec


_ZONE_CFG = {
    "HV": {
        "bounds": ((0.0, 0.0), (50.0, 100.0)),
        "max_size": (100.0, 100.0),
        "can_expand": ["right", "left", "up", "down"],
    },
}


# ---------------------------------------------------------------------------
# Scenario A -- call sequence with recording fakes (both arms, same script)
# ---------------------------------------------------------------------------


def _run_sequence_scenario():
    """Script: iteration 1 -> 2 violations + non-empty adjustments;
    iteration 2 -> 0 violations (clean break). max_iterations=5.
    Returns (oracle_log, shim_log) -- the per-arm recording call logs."""
    max_iterations = 5
    violations_script = [
        [_violation(), DRCViolation(type="creepage", items=["of Q1"], pos=(20, 20))],
        [],
    ]
    adjust_script = [
        {"HV": ZoneAdjustment(zone_name="HV", delta_width=5.0, delta_height=0.0)},
    ]

    def arm(module):
        log = []
        pipeline = _RecPipeline([_populated_state(), _populated_state()], log)
        drc_runner = _RecRunner(log)
        parse = MagicMock(side_effect=list(violations_script))
        get_zone_config = _recording_get_zone_config(log, _ZONE_CFG)
        update_config = _recording_update(log)
        with patch.object(module, "ViolationComponentMapper") as mapper_cls, \
             patch.object(module, "ZoneAdjuster") as adjuster_cls, \
             patch.object(module, "parse_kicad_drc", parse):
            mapper_cls.side_effect = lambda nl, zc: _RecMapper(nl, zc, log)
            adjuster_cls.side_effect = lambda zc, **kw: _RecAdjuster(zc, log, adjust_script, **kw)
            orc = module.AutomatedZeroDRC(
                pipeline=pipeline,
                netlist=_mock_netlist(),
                initial_config=_initial_config(),
                drc_runner=drc_runner,
                max_iterations=max_iterations,
            )
            # Install the recording config call-backs: the loop under test
            # must call THESE (the real _get_zone_config/_update_config are
            # pinned by the real-leaves scenarios).
            orc._get_zone_config = get_zone_config
            orc._update_config = update_config
            orc.run()
        return log

    return arm(_orc), arm(_feedback_pkg.orchestrator)


def test_sequence_matches_between_arms() -> None:
    log_orc, log_shim = _run_sequence_scenario()
    assert log_orc == log_shim, (
        f"call sequences diverged:\n  oracle={log_orc}\n  shim  ={log_shim}"
    )


def test_sequence_matches_expected_order() -> None:
    log_orc, _ = _run_sequence_scenario()
    # Two iterations: 1 violating (2 violations) -> adjust -> reset, then a
    # clean break. Compare structurally: drop the payloads, keep the kinds.
    kinds = [t[0] if isinstance(t, tuple) else t for t in log_orc]
    assert kinds == [
        "pipeline.run", "drc_runner",
        "get_zone_config", "map_violation", "map_violation",
        "get_zone_config", "compute_adjustments", "update_config",
        "pipeline.run", "drc_runner",
    ], f"call kinds diverged: {kinds}"


_EXPECTED_LOG_MESSAGES = [
    "--- Feedback Iteration 1/5 ---",
    "Running DRC...",
    "Found 2 raw DRC violations",
    "EXP-5: Preserving 2 locked routes for next iteration",
    "--- Feedback Iteration 2/5 ---",
    "Running DRC...",
    "Zero DRC violations achieved!",
]


def _arm_log_messages(module, caplog) -> list[str]:
    """Run one arm under caplog (its logger redirected to the shim's logger
    name so both arms emit into one stream) and return its messages."""
    with caplog.at_level(logging.INFO,
                         logger="temper_placer.deterministic.feedback.orchestrator"), \
         patch.object(module, "logger",
                      logging.getLogger("temper_placer.deterministic.feedback.orchestrator")):
        _run_arm_single(module)
    return [r.getMessage() for r in caplog.records]


def _run_arm_single(module) -> None:
    """Run the sequence scenario for ONE arm (no caplog interaction)."""
    log = []
    pipeline = _RecPipeline([_populated_state(), _populated_state()], log)
    drc_runner = _RecRunner(log)
    parse = MagicMock(side_effect=[
        [_violation(), DRCViolation(type="creepage", items=["of Q1"], pos=(20, 20))],
        [],
    ])
    adjust_script = [
        {"HV": ZoneAdjustment(zone_name="HV", delta_width=5.0, delta_height=0.0)},
    ]
    with patch.object(module, "ViolationComponentMapper") as mapper_cls, \
         patch.object(module, "ZoneAdjuster") as adjuster_cls, \
         patch.object(module, "parse_kicad_drc", parse):
        mapper_cls.side_effect = lambda nl, zc: _RecMapper(nl, zc, log)
        adjuster_cls.side_effect = lambda zc, **kw: _RecAdjuster(zc, log, adjust_script, **kw)
        orc = module.AutomatedZeroDRC(
            pipeline=pipeline,
            netlist=_mock_netlist(),
            initial_config=_initial_config(),
            drc_runner=drc_runner,
            max_iterations=5,
        )
        # Recording config call-backs (see _run_sequence_scenario).
        get_zone_config = _recording_get_zone_config(log, _ZONE_CFG)
        update_config = _recording_update(log)
        orc._get_zone_config = get_zone_config
        orc._update_config = update_config
        orc.run()


def test_log_messages_match_between_arms(caplog) -> None:
    """Both arms emit the identical log-message sequence through the SAME
    logger (the oracle module's `logger` binding is redirected to the shim's
    logger name so caplog sees one stream)."""
    msg_orc = _arm_log_messages(_orc, caplog)
    caplog.clear()
    msg_shim = _arm_log_messages(_feedback_pkg.orchestrator, caplog)
    assert msg_orc == _EXPECTED_LOG_MESSAGES, f"oracle log diverged: {msg_orc}"
    assert msg_shim == _EXPECTED_LOG_MESSAGES, f"shim log diverged: {msg_shim}"


# ---------------------------------------------------------------------------
# Scenario B -- real leaves end-to-end (violations -> adjust -> clean)
# ---------------------------------------------------------------------------


def _real_config_mutation():
    """Real ViolationComponentMapper + ZoneAdjuster; the parse script is
    [violations, clean]. Mirrors test_orchestrator.py's adjust-and-retry
    scenario with the real leaf helpers."""
    out = {}

    def arm(module):
        log = []
        pipeline = _RecPipeline([_populated_state(), _populated_state()], log)
        drc_runner = _RecRunner(log)
        with patch.object(module, "parse_kicad_drc",
                          side_effect=[[_violation()], []]):
            orc = module.AutomatedZeroDRC(
                pipeline=pipeline,
                netlist=_mock_netlist(),
                initial_config=_initial_config(),
                drc_runner=drc_runner,
                max_iterations=5,
            )
            # Force adjustment threshold to 1 for testing (existing
            # test_orchestrator.py convention).
            orc.adjuster.violation_threshold = 1
            orc.adjuster.expansion_per_violation = 5.0  # 5mm expansion
            final = orc.run()
        out["log"] = log
        out["config"] = orc.config
        out["final"] = final
        return orc

    arm(_orc)
    orc_result = (out["log"], out["config"], out["final"])
    arm(_feedback_pkg.orchestrator)
    shim_result = (out["log"], out["config"], out["final"])
    return orc_result, shim_result


def test_real_leaves_end_to_end_parity() -> None:
    (log_o, cfg_o, final_o), (log_s, cfg_s, final_s) = _real_config_mutation()
    assert log_o == log_s
    # Both arms ran exactly 2 pipeline runs + 2 DRC runs.
    kinds_o = [t[0] if isinstance(t, tuple) else t for t in log_o]
    assert kinds_o.count("pipeline.run") == 2
    assert kinds_o.count("drc_runner") == 2
    # 5mm expansion on 100mm board is a 0.05 ratio.
    assert cfg_o["zones"][0]["bounds_ratio"][2] == pytest.approx(0.55)
    assert cfg_o["zones"][1]["bounds_ratio"][0] == pytest.approx(0.55)
    assert cfg_o["zones"][1]["bounds_ratio"][2] == pytest.approx(1.05)
    assert cfg_s["zones"][0]["bounds_ratio"][2] == pytest.approx(0.55)
    assert cfg_s["zones"][1]["bounds_ratio"][0] == pytest.approx(0.55)
    assert cfg_s["zones"][1]["bounds_ratio"][2] == pytest.approx(1.05)
    # Identical final states field-by-field.
    _assert_state_fields_equal(final_o, final_s)


def _assert_state_fields_equal(a: BoardState, b: BoardState) -> None:
    assert type(a) is type(b)
    fields = [f.name for f in a.__dataclass_fields__.values()]
    for name in fields:
        assert repr(getattr(a, name)) == repr(getattr(b, name)), (
            f"field {name!r} diverged:\n  oracle={getattr(a, name)!r}\n  shim ={getattr(b, name)!r}"
        )


# ---------------------------------------------------------------------------
# Scenario C -- iteration-cap exhaustion + the EXP-5 state reset
# ---------------------------------------------------------------------------


def _cap_and_reset(max_iterations: int = 2):
    """Violations + adjustments always non-empty -> the loop exhausts the
    cap; every iteration performs the EXP-5 reset. The final state must have
    board/netlist/locked_routes/config preserved and derived fields reset."""
    out = {}

    def arm(module):
        log = []
        pipeline = _RecPipeline(
            [_populated_state(), _populated_state(), _populated_state()], log
        )
        drc_runner = _RecRunner(log)
        with patch.object(module, "parse_kicad_drc", return_value=[_violation()]):
            orc = module.AutomatedZeroDRC(
                pipeline=pipeline,
                netlist=_mock_netlist(),
                initial_config=_initial_config(),
                drc_runner=drc_runner,
                max_iterations=max_iterations,
            )
            orc.adjuster.violation_threshold = 1
            orc.adjuster.expansion_per_violation = 0.5
            final = orc.run()
        out["log"] = log
        out["final"] = final
        return orc

    arm(_orc)
    o = (out["log"], out["final"])
    arm(_feedback_pkg.orchestrator)
    s = (out["log"], out["final"])
    return o, s


def test_cap_exhaustion_and_reset_parity() -> None:
    (log_o, final_o), (log_s, final_s) = _cap_and_reset(max_iterations=2)
    assert log_o == log_s
    kinds = [t[0] if isinstance(t, tuple) else t for t in log_o]
    assert kinds.count("pipeline.run") == 2  # exactly the cap
    assert kinds.count("drc_runner") == 2
    # EXP-5 reset: preserved fields carry the pipeline output's values...
    for final in (final_o, final_s):
        assert final.locked_routes == frozenset({"NET1", "NET2"})
        assert final.config == {"block": "hv_lv"}
        assert final.board.width == 100.0
        # ...and derived state was cleared (reset to defaults).
        assert final.routes == frozenset()
        assert final.vias == frozenset()
    _assert_state_fields_equal(final_o, final_s)


def test_cap_zero_runs_nothing() -> None:
    """A zero iteration cap runs nothing. NOTE: the constructor's
    `max_iterations or config_default` treats 0 as falsy (the oracle's
    Python `or`), so the cap is forced post-construction -- the oracle's
    `for i in range(0)` then runs no iterations."""
    out = {}

    def arm(module):
        log = []
        pipeline = _RecPipeline([_populated_state(), _populated_state()], log)
        drc_runner = _RecRunner(log)
        with patch.object(module, "parse_kicad_drc", return_value=[_violation()]):
            orc = module.AutomatedZeroDRC(
                pipeline=pipeline,
                netlist=_mock_netlist(),
                initial_config=_initial_config(),
                drc_runner=drc_runner,
                max_iterations=5,
            )
            orc.max_iterations = 0  # forced: `0 or default` would revive 5
            final = orc.run()
        out["log"] = log
        out["final"] = final

    arm(_orc)
    o = (out["log"], out["final"])
    arm(_feedback_pkg.orchestrator)
    s = (out["log"], out["final"])
    assert o == s == ([], None)


def test_negative_cap_runs_nothing() -> None:
    """A NEGATIVE iteration cap behaves exactly like zero (resolves #1102):
    the oracle's `for i in range(-1)` iterates zero times and returns the
    initial state (None) untouched. The Rust pyfunction previously diverged
    (u64 extraction raised OverflowError for a negative Python int); it now
    clamps negatives to 0 at the FFI boundary. NOTE: a negative budget is
    truthy in Python, so `-1` passes the constructor's `max_iterations or
    default` directly (no post-construction forcing needed)."""
    out = {}

    def arm(module):
        log = []
        pipeline = _RecPipeline([_populated_state(), _populated_state()], log)
        drc_runner = _RecRunner(log)
        with patch.object(module, "parse_kicad_drc", return_value=[_violation()]):
            orc = module.AutomatedZeroDRC(
                pipeline=pipeline,
                netlist=_mock_netlist(),
                initial_config=_initial_config(),
                drc_runner=drc_runner,
                max_iterations=-1,
            )
            final = orc.run()
        out["log"] = log
        out["final"] = final

    arm(_orc)
    o = (out["log"], out["final"])
    arm(_feedback_pkg.orchestrator)
    s = (out["log"], out["final"])
    assert _log_empty_and_none(o) and _log_empty_and_none(s), (o, s)


def _log_empty_and_none(res) -> bool:
    return res == ([], None)


def test_zero_cap_non_board_state_returned_untouched() -> None:
    """At zero iterations with a NON-BoardState initial_state, the oracle
    returns the object untouched (the loop body never runs). The Rust port
    now short-circuits the zero path before the BoardState snapshot, so it
    returns the object untouched too instead of AttributeError-ing (#1102
    secondary)."""
    out = {}

    def arm(module):
        log = []
        pipeline = _RecPipeline([_populated_state()], log)
        drc_runner = _RecRunner(log)
        with patch.object(module, "parse_kicad_drc", return_value=[_violation()]):
            orc = module.AutomatedZeroDRC(
                pipeline=pipeline,
                netlist=_mock_netlist(),
                initial_config=_initial_config(),
                drc_runner=drc_runner,
                max_iterations=5,
            )
            orc.max_iterations = 0  # forced
            marker = {"not": "a BoardState"}
            final = orc.run(initial_state=marker)
        out["log"] = log
        out["final"] = final

    arm(_orc)
    o_final = out["final"]
    arm(_feedback_pkg.orchestrator)
    s_final = out["final"]
    assert o_final == s_final == {"not": "a BoardState"}
    assert type(o_final) is dict and type(s_final) is dict



# ---------------------------------------------------------------------------
# Scenario D -- the no-adjustment break
# ---------------------------------------------------------------------------


def test_no_adjustments_break_parity() -> None:
    """Violations found but zero adjustments -> the loop breaks after the
    FIRST iteration (pipeline.run once; update_config never called)."""

    def arm(module):
        log = []
        pipeline = _RecPipeline([_populated_state()], log)
        drc_runner = _RecRunner(log)
        with patch.object(module, "parse_kicad_drc", return_value=[_violation()]):
            orc = module.AutomatedZeroDRC(
                pipeline=pipeline,
                netlist=_mock_netlist(),
                initial_config=_initial_config(),
                drc_runner=drc_runner,
                max_iterations=5,
            )
            # Patch the adjuster to always produce empty adjustments.
            orc.adjuster.compute_adjustments = lambda _violations: AdjustmentResult(adjustments={})
            orc._update_config = _recording_update(log)  # must NOT be called
            final = orc.run()
        return log, final

    log_o, final_o = arm(_orc)
    log_s, final_s = arm(_feedback_pkg.orchestrator)
    assert log_o == log_s
    kinds_o = [t[0] if isinstance(t, tuple) else t for t in log_o]
    assert kinds_o.count("pipeline.run") == 1
    assert kinds_o.count("drc_runner") == 1
    # No config update on the no-adjustment path.
    assert not any(k == "update_config" or k[0] == "update_config" for k in log_o)
    _assert_state_fields_equal(final_o, final_s)
    # The final state is the pipeline's output of iteration 1 (no reset on
    # the adjustment break path): derived fields are NOT cleared.
    assert final_o.routes != frozenset()


# ---------------------------------------------------------------------------
# Scenario E -- exception propagation
# ---------------------------------------------------------------------------


class _BoomPipeline:
    """Raises RuntimeError on the second run() call."""

    def __init__(self):
        self.calls = 0
        self.stages = []

    def run(self, state):
        self.calls += 1
        if self.calls >= 2:
            raise RuntimeError("drc boom")
        return _populated_state()


def test_exception_propagates_from_both_arms() -> None:
    def arm(module):
        pipeline = _BoomPipeline()
        drc_runner = _RecRunner([])
        with patch.object(module, "parse_kicad_drc", return_value=[_violation()]):
            orc = module.AutomatedZeroDRC(
                pipeline=pipeline,
                netlist=_mock_netlist(),
                initial_config=_initial_config(),
                drc_runner=drc_runner,
                max_iterations=5,
            )
            # Threshold 1: every iteration yields an adjustment, so the
            # second iteration runs and the pipeline's boom fires.
            orc.adjuster.violation_threshold = 1
            with pytest.raises(RuntimeError, match="drc boom"):
                orc.run()
        return pipeline.calls

    assert arm(_orc) == 2
    assert arm(_feedback_pkg.orchestrator) == 2
