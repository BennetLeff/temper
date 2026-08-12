"""Property-based tests (G4) for the orchestration-port unit U-G run-loop
(Rust Orchestration Engine plan 2026-08-09-001): the
``RouterV6Pipeline.run()`` stage-sequencing driver, now implemented in Rust
(``temper-orchestration``'s ``RouterPipeline`` pyclass driving the stages
through ``PipelineRunner<BoardState>``).

The unit under test is the DRIVER: the fixed stage sequence, the
conditionals (legalization, skip_stage3, manufacturing DRC + fail modes),
the state threading, the determinism and the exception propagation. The
leaf call-backs are deterministic fakes (the per-stage compute is pinned by
the E6 / U-G differentials).

Module-to-property map (G4 -- every reachable driver behaviour pinned):
- P1 -- CALL ORDER: the shared stage call-backs always fire in the fixed
  canonical order, regardless of the optional-flag permutation.
- P2 -- SKIP BYPASS: skip_stage3=True never invokes ``_run_stage3``;
  False invokes it exactly once.
- P3 -- DFM CONDITIONAL: manufacturing off never invokes the DFM check and
  yields ``manufacturing_report=None``; on invokes it exactly once, and the
  dfm_fail_on raise decision (critical/all/none vs the reported violation
  counts) matches the oracle.
- P4 -- LEGALIZATION CONDITIONAL: the Legalizer is constructed iff
  ``enable_legalization``; its ``legalize()`` is invoked exactly once when
  constructed.
- P5 -- DETERMINISM: two runs with identical config + fakes yield
  byte-identical results (repr) and call sequences.
- P6 -- EXCEPTION PROPAGATION: a raising stage halts the run, the original
  exception type propagates, the stages before it ran and the stages after
  it did not.

Non-vacuity: every property routes its observable through an ``impl``
parameter (default: the Rust pyclass driver via the shim ``run()``) and has
a ``test_pN_fails_for_<mutant>`` companion re-running the body against a
degenerate Python stand-in driver and asserting AssertionError.
"""

from __future__ import annotations

import contextlib
from types import SimpleNamespace
from unittest import mock

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.router_v6._pipeline_core import RouterV6Pipeline

# ---------------------------------------------------------------------------
# Deterministic fake leaf call-backs
# ---------------------------------------------------------------------------


class _FakeNet:
    def __init__(self, name: str):
        self.name = name
        self.pins = [0, 1]


class _FakePcb:
    def __init__(self, nets=()):
        self.nets = [n for n in nets]
        self.components = ["U1"]
        self.design_rules = SimpleNamespace(
            net_class_assignments={}, net_classes={}, default_clearance_mm=0.3
        )
        self.board = None

    def validate_placement(self):
        return []


class _FakeStage2:
    pass


class _FakeStage3:
    topology_graph = object()


class _FakeStage4:
    def __init__(self):
        self.routing_results = SimpleNamespace(success_count=3, failure_count=1)


class _FakeReport:
    def __init__(self, critical=0, total=0):
        self.critical_violations = critical
        self.total_violations = total


class _FakeLedger:
    def __init__(self, log):
        self._log = log

    def checkin(self, _s):
        self._log.append(("ledger.checkin",))

    def checkout(self, stage_name, _s):
        self._log.append(("ledger.checkout", stage_name))


def _make_legalizer_cls(log):
    """A fake Legalizer CLASS for one log: constructed via ``Legalizer(pcb)``
    (the call-site shape), recording construction + legalize into ``log``."""

    class _FL:
        def __init__(self, pcb):
            self.auditor = SimpleNamespace(check_collisions=lambda: [])
            log.append(("legalizer_ctor",))

        def legalize(self):
            log.append(("legalize",))
            return True

    return _FL


# ---------------------------------------------------------------------------
# The driver under test + degenerate mutants (vacuity guards)
# ---------------------------------------------------------------------------


def _patched(log):
    """Patch the module-level leaf call-backs (parse, dense, escape,
    Legalizer) with deterministic fakes recording into ``log``."""
    stack = contextlib.ExitStack()

    def _parse(pcb_path, *, use_declared_layer_roles=False):
        log.append(("parse", pcb_path, use_declared_layer_roles))
        return _FakePcb([_FakeNet("GND"), _FakeNet("SPI_MOSI")])

    stack.enter_context(
        mock.patch("temper_placer.io.kicad_parser.parse_kicad_pcb_v6", _parse)
    )

    def _dense(pcb_components):
        log.append(("dense", len(pcb_components)))
        return [SimpleNamespace(component=SimpleNamespace(ref="U1"), _ref="U1")]

    stack.enter_context(
        mock.patch(
            "temper_placer.router_v6.dense_package_detection.identify_dense_packages",
            _dense,
        )
    )

    def _escape(pkg, design_rules, strategy="dog-bone"):
        log.append(("escape", strategy))
        return [object()]

    stack.enter_context(
        mock.patch(
            "temper_placer.router_v6.escape_via_generator.generate_escape_vias",
            _escape,
        )
    )
    stack.enter_context(
        mock.patch(
            "temper_placer.router_v6.placement_legalization.Legalizer",
            _make_legalizer_cls(log),
        )
    )
    # RED-mode compatibility: the verbatim run() resolves the Legalizer and
    # the dense/escape call-backs through the _pipeline_core module-top
    # bindings; once the shim delegates to the Rust driver (which imports
    # the source modules at runtime) these are inert.
    stack.enter_context(
        mock.patch(
            "temper_placer.router_v6._pipeline_core.identify_dense_packages",
            _dense,
        )
    )
    stack.enter_context(
        mock.patch(
            "temper_placer.router_v6._pipeline_core.generate_escape_vias",
            _escape,
        )
    )
    stack.enter_context(
        mock.patch(
            "temper_placer.router_v6._pipeline_core.Legalizer",
            _make_legalizer_cls(log),
        )
    )
    return stack


def _make_pipeline(config, log, raising=None):
    ctor_kwargs = {k: v for k, v in config.items() if k != "_report"}
    pipe = RouterV6Pipeline(**ctor_kwargs)

    def _stage2(pcb, escape_vias):
        log.append(("stage2",))
        if raising == "stage2":
            raise RuntimeError("boom-stage2")
        return _FakeStage2()

    def _resource(pcb, stage2):
        log.append(("resource_bound",))

    def _stage3(pcb, stage2):
        log.append(("stage3",))
        if raising == "stage3":
            raise RuntimeError("boom-stage3")
        return _FakeStage3()

    def _stage4(pcb, stage2, stage3, escape_vias):
        log.append(("stage4",))
        if raising == "stage4":
            raise RuntimeError("boom-stage4")
        return _FakeStage4()

    def _manufacturing(pcb, routing_results):
        log.append(("manufacturing",))
        report = config.get("_report")
        return report if report is not None else _FakeReport()

    pipe._run_stage2 = _stage2
    pipe._compute_resource_bound = _resource
    pipe._run_stage3 = _stage3
    pipe._run_stage4 = _stage4
    pipe._run_stage5 = lambda pcb, stage2, pf: _FakeStage4()
    pipe._run_manufacturing_drc = _manufacturing
    pipe._run_fence = lambda **kw: log.append(("fence", kw["stage_name"]))
    pipe.ledger = _FakeLedger(log)
    return pipe


def _shim_run(config: dict, log: list, raising: str | None = None):
    """The U-G driver under test: the shim run() -> Rust RouterPipeline."""
    with _patched(log):
        pipe = _make_pipeline(config, log, raising)
        return pipe.run("/fake/pcb.kicad_pcb")


# ---------------------------------------------------------------------------
# Mutant drivers (pure-Python stand-ins that trip the properties)
# ---------------------------------------------------------------------------


def _mutant_stage2_before_parse(config, log, raising=None):  # noqa: ARG001
    """P1 mutant: fires stage2 before parse (order violation)."""
    with _patched(log):
        pipe = _make_pipeline(config, log)
        pipe._run_stage2(None, [])
        return pipe.run("/fake/pcb.kicad_pcb")


def _mutant_ignore_skip(config, log, raising=None):  # noqa: ARG001
    """P2 mutant: runs _run_stage3 even when skip_stage3=True."""
    with _patched(log):
        pipe = _make_pipeline(config, log)
        pipe.skip_stage3 = False
        return pipe.run("/fake/pcb.kicad_pcb")


def _mutant_dfm_always_raises(config, log, raising=None):  # noqa: ARG001
    """P3 mutant: the DFM report always carries a critical violation, so the
    fail decision raises even when the configured report is clean."""
    with _patched(log):
        pipe = _make_pipeline(config, log)

        def _m(pcb, rr):
            log.append(("manufacturing",))
            return _FakeReport(critical=1, total=1)

        pipe._run_manufacturing_drc = _m
        return pipe.run("/fake/pcb.kicad_pcb")


def _mutant_always_legalize(config, log, raising=None):  # noqa: ARG001
    """P4 mutant: constructs the Legalizer even when legalization is off."""
    with _patched(log):
        pipe = _make_pipeline(config, log)
        pipe.enable_legalization = True
        return pipe.run("/fake/pcb.kicad_pcb")


def _mutant_skip_last_stage(config, log, raising=None):  # noqa: ARG001
    """P5 mutant: the second invocation swallows the final
    ``ledger.checkout("routing_complete", ...)`` (nondeterministic)."""
    _mutant_skip_last_stage.calls = getattr(_mutant_skip_last_stage, "calls", 0) + 1
    with _patched(log):
        pipe = _make_pipeline(config, log)
        if _mutant_skip_last_stage.calls % 2 == 0:
            class _SilentLedger(_FakeLedger):
                def checkout(self, stage_name, _s):
                    if stage_name == "routing_complete":
                        return None
                    self._log.append(("ledger.checkout", stage_name))

            pipe.ledger = _SilentLedger(log)
        return pipe.run("/fake/pcb.kicad_pcb")


def _mutant_swallow_exceptions(config, log, raising=None):  # noqa: ARG001
    """P6 mutant: swallows a raising stage and returns a fake result."""
    with _patched(log):
        pipe = _make_pipeline(config, log, raising=None)
        try:
            return pipe.run("/fake/pcb.kicad_pcb")
        except RuntimeError:
            return SimpleNamespace(stage4=_FakeStage4())


def _assert_mutant_detected(body, mutant, config, log) -> None:
    """Run ``body`` against the degenerate mutant; the body's assertions MUST
    trip. If they do not, the property is vacuous -- a hard failure."""
    with pytest.raises(AssertionError):
        body(mutant, config, log)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_FLAGS = st.fixed_dictionaries(
    {
        "skip_stage3": st.booleans(),
        "enable_legalization": st.booleans(),
        "enable_manufacturing_drc": st.booleans(),
    }
)


@st.composite
def _configs(draw):
    """Shared config strategy: never triggers the DFM fail-mode raise (the
    raise is P3's observable; the other properties would see a truncated
    run)."""
    cfg = dict(draw(_FLAGS))
    cfg["dfm_fail_on"] = "none"
    if cfg["enable_manufacturing_drc"]:
        cfg["_report"] = _FakeReport(0, 0)
    return cfg


@st.composite
def _dfm_configs(draw):
    """P3's config strategy: exercises the fail-mode raise decision."""
    cfg = dict(draw(_FLAGS))
    cfg["enable_manufacturing_drc"] = True
    cfg["dfm_fail_on"] = draw(st.sampled_from(["none", "critical", "all"]))
    cfg["_report"] = _FakeReport(
        critical=draw(st.integers(min_value=0, max_value=2)),
        total=draw(st.integers(min_value=0, max_value=2)),
    )
    return cfg


def _log_names(log):
    return [e[0] for e in log]


# ---------------------------------------------------------------------------
# P1 -- call order invariance under flag permutation
# ---------------------------------------------------------------------------


def _body_p1(impl, config, log) -> None:
    impl(config, log)
    names = _log_names(log)
    # The always-present shared call-backs fire in the fixed canonical
    # relative order, with the optional stages inserted at their canonical
    # positions.
    base = [
        n for n in names
        if n in ("parse", "dense", "escape", "stage2", "resource_bound",
                 "stage3", "stage4")
    ]
    expected_base = ["parse", "dense", "escape", "stage2", "resource_bound"]
    if not config["skip_stage3"]:
        expected_base.append("stage3")
    expected_base.append("stage4")
    assert base == expected_base, f"base order diverged: {base}"
    if config["enable_legalization"]:
        assert "legalizer_ctor" in names
        assert names.index("legalizer_ctor") < names.index("stage2")
    if config["enable_manufacturing_drc"]:
        assert "manufacturing" in names
        assert names.index("manufacturing") > names.index("stage4")
    # the result-assembly ledger checkout is always last
    assert names[-1] == "ledger.checkout"


@given(_configs())
@settings(max_examples=100, deadline=None)
def test_p1_stage_order_invariant(config):
    _body_p1(_shim_run, config, [])


def test_p1_fails_for_reordered_mutant() -> None:
    _assert_mutant_detected(
        _body_p1,
        _mutant_stage2_before_parse,
        {"skip_stage3": False, "enable_legalization": False,
         "enable_manufacturing_drc": False, "dfm_fail_on": "critical"},
        [],
    )


# ---------------------------------------------------------------------------
# P2 -- skip_stage3 bypass
# ---------------------------------------------------------------------------


def _body_p2(impl, config, log) -> None:
    impl(config, log)
    stage3_calls = _log_names(log).count("stage3")
    if config["skip_stage3"]:
        assert stage3_calls == 0, "skip_stage3=True must bypass _run_stage3"
    else:
        assert stage3_calls == 1, "skip_stage3=False must run _run_stage3 once"


@given(_configs())
@settings(max_examples=100, deadline=None)
def test_p2_skip_bypass(config):
    _body_p2(_shim_run, config, [])


def test_p2_fails_for_ignore_skip_mutant() -> None:
    _assert_mutant_detected(
        _body_p2,
        _mutant_ignore_skip,
        {"skip_stage3": True, "enable_legalization": False,
         "enable_manufacturing_drc": False, "dfm_fail_on": "critical"},
        [],
    )


# ---------------------------------------------------------------------------
# P3 -- manufacturing DRC conditional + fail decision
# ---------------------------------------------------------------------------


def _body_p3(impl, config, log) -> None:
    report = config.get("_report", _FakeReport(0, 0))
    raised = False
    result = None
    try:
        result = impl(config, log)
    except Exception as exc:  # noqa: BLE001 -- the raise IS the observable
        raised = True
        assert type(exc).__name__ == "ManufacturingDRCViolationError", (
            f"fail-mode raise must be ManufacturingDRCViolationError, got {type(exc).__name__}"
        )
    names = _log_names(log)
    if not config["enable_manufacturing_drc"]:
        assert "manufacturing" not in names
        assert not raised
        assert result.manufacturing_report is None
        return
    assert names.count("manufacturing") == 1
    # The fail decision: raises iff the configured threshold is exceeded.
    should_fail = config["dfm_fail_on"] != "none" and (
        (config["dfm_fail_on"] == "critical" and report.critical_violations > 0)
        or (config["dfm_fail_on"] == "all" and report.total_violations > 0)
    )
    assert raised == should_fail, (
        f"fail decision diverged: dfm={config['dfm_fail_on']} "
        f"report=({report.critical_violations},{report.total_violations}) "
        f"raised={raised}"
    )
    if not raised:
        assert result.manufacturing_report is report


@given(_dfm_configs())
@settings(max_examples=100, deadline=None)
def test_p3_dfm_conditional(config):
    _body_p3(_shim_run, config, [])


def test_p3_fails_for_always_raise_mutant() -> None:
    _assert_mutant_detected(
        _body_p3,
        _mutant_dfm_always_raises,
        {"skip_stage3": False, "enable_legalization": False,
         "enable_manufacturing_drc": True, "dfm_fail_on": "critical",
         "_report": _FakeReport(0, 0)},
        [],
    )


# ---------------------------------------------------------------------------
# P4 -- legalization conditional
# ---------------------------------------------------------------------------


def _body_p4(impl, config, log) -> None:
    impl(config, log)
    names = _log_names(log)
    if config["enable_legalization"]:
        assert names.count("legalizer_ctor") == 1
        assert names.count("legalize") == 1
    else:
        assert "legalizer_ctor" not in names
        assert "legalize" not in names


@given(_configs())
@settings(max_examples=100, deadline=None)
def test_p4_legalization_conditional(config):
    _body_p4(_shim_run, config, [])


def test_p4_fails_for_always_legalize_mutant() -> None:
    _assert_mutant_detected(
        _body_p4,
        _mutant_always_legalize,
        {"skip_stage3": False, "enable_legalization": False,
         "enable_manufacturing_drc": False, "dfm_fail_on": "critical"},
        [],
    )


# ---------------------------------------------------------------------------
# P5 -- determinism
# ---------------------------------------------------------------------------


def _body_p5(impl, config, log) -> None:
    log.clear()
    r1 = impl(dict(config), log)
    first_log = list(log)
    log.clear()
    r2 = impl(dict(config), log)
    # default-object reprs embed memory addresses; compare the observable
    # content + the call sequence instead (stage3's class varies with
    # skip_stage3 -- the empty Stage3Output vs the fake -- but is identical
    # across two runs of the same config).
    assert type(r1.stage4).__name__ == type(r2.stage4).__name__ == "_FakeStage4"
    assert (
        r1.stage4.routing_results.success_count
        == r2.stage4.routing_results.success_count
        == 3
    )
    assert type(r1.stage3).__name__ == type(r2.stage3).__name__
    assert first_log == log, "two identical runs diverged in call sequence"


@given(_configs())
@settings(max_examples=50, deadline=None)
def test_p5_determinism(config):
    _body_p5(_shim_run, config, [])


def test_p5_fails_for_nondeterministic_mutant() -> None:
    _mutant_skip_last_stage.calls = 0
    _assert_mutant_detected(
        _body_p5,
        _mutant_skip_last_stage,
        {"skip_stage3": False, "enable_legalization": False,
         "enable_manufacturing_drc": False, "dfm_fail_on": "critical"},
        [],
    )


# ---------------------------------------------------------------------------
# P6 -- exception propagation
# ---------------------------------------------------------------------------


def _body_p6(impl, config, log) -> None:
    for raising in ("stage2", "stage3", "stage4"):
        if raising == "stage3" and config["skip_stage3"]:
            continue  # _run_stage3 is bypassed; nothing can raise there
        log.clear()
        raised = False
        try:
            impl(dict(config), log, raising)
        except RuntimeError as exc:
            raised = True
            assert f"boom-{raising}" in str(exc)
        assert raised, f"the driver must propagate the {raising} exception"
        names = _log_names(log)
        assert raising in names, f"{raising} stage marker missing"
        # stages after the raising stage never ran
        idx = names.index(raising)
        trailing = names[idx + 1 :]
        assert "ledger.checkout" not in trailing
        if raising == "stage2":
            assert "stage3" not in trailing and "stage4" not in trailing


@given(_configs())
@settings(max_examples=50, deadline=None)
def test_p6_exception_propagation(config):
    _body_p6(_shim_run, config, [])


def test_p6_fails_for_swallow_mutant() -> None:
    _assert_mutant_detected(
        _body_p6,
        _mutant_swallow_exceptions,
        {"skip_stage3": False, "enable_legalization": False,
         "enable_manufacturing_drc": False, "dfm_fail_on": "critical"},
        [],
    )
