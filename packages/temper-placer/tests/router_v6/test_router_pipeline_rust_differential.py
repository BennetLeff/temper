"""R1a: behavioural differential of the RouterV6Pipeline.run() stage-
sequencing driver against the pinned pre-migration oracle.

Rust Orchestration Engine plan 2026-08-09-001, orchestration-port unit U-G:
the run-loop of ``router_v6/_pipeline_core.py`` (the fixed stage sequence —
Stage 0 load, Stage 0.5 legalization, Stage 1 escape vias, Stage 2 channel
analysis, Stage 3 topological routing, Stage 4 geometric realization, Stage 5
manufacturing DRC, result assembly — with the per-stage fences, the ledger
checkin/checkout calls, the verbose print orchestration, the wall-clock
runtime and the exception propagation) moves to ``temper-orchestration``'s
``RouterPipeline`` pyclass, which drives the stages through the Rust
``PipelineRunner<BoardState>``. The pre-migration ``run()`` body is pinned
VERBATIM as ``tests/router_v6/_pipeline_core_py_oracle.py``
(content-hash-pinned below).

What this suite pins is the LOOP: both arms run the SAME leaf call-backs —
deterministic fakes for the parse, the Legalizer, the escape-via generation,
``_run_stage2/3/4/5``, ``_run_fence``, ``_run_manufacturing_drc``, the
ledger and the ERC gate, plus the real modules for the Stage-0 setup
marshalling (the netclass injection + net priority sort, pinned by a direct
injection/order test) and a real minimal-board end-to-end run — so the only
divergence surface is the driver itself. The tests compare:

- the call SEQUENCE the driver issues (order + per-stage arguments);
- the state THREADING (pcb / escape_vias / stage2 / stage3 / stage4 object
  identity through the loop);
- the CONDITIONALS (legalization on/off, skip_stage3, manufacturing DRC
  on/off + the dfm_fail_on raise decision, fence presence, ERC on/off);
- the EXCEPTION propagation (ValueError on validation failure,
  ManufacturingDRCViolationError on a DFM fail, a stage exception re-raised
  with type and message);
- the verbose stdout (byte-for-byte, modulo the wall-clock runtime line);
- a real end-to-end run on the minimal board fixture (skip_stage3=True,
  max_nets=1) compared field-for-field.

Anti-vacuity: ``test_oracle_and_port_are_different_implementations`` asserts
the shim ``run()`` delegates to the Rust pyclass (``co_names`` + module
binding), not back onto the oracle. The oracle body digest is pinned: a
differential whose oracle can be edited to agree with the port proves
nothing.

The router's own nondeterminism (wall-clock, seeds, the route_board.py
subprocess) is preserved by design: the driver only sequences; the fakes are
deterministic, and the real-run arm exercises the deterministic leaf path
(SAT off, conflict-bounded).
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
import temper_orchestration as _to

from temper_placer.router_v6._pipeline_core import RouterV6Pipeline
from tests.router_v6 import _pipeline_core_py_oracle as _orc

# ---------------------------------------------------------------------------
# Oracle body pinning (G1)
# ---------------------------------------------------------------------------

# The digest changes ONLY when the oracle body is deliberately re-pinned, and
# every re-pin belongs in a commit that says why. Log:
#   8d3221be... -> 3a719cb2...  2026-08-12, clearance-floor re-land: deleted
#     ``dr.default_clearance_mm = 0.15`` from the Stage-0 injection block in
#     lockstep with the shim. The oracle pins the MIGRATION contract (shim
#     output == pre-migration output), not the VALUE, so a deliberate value
#     correction has to be made on both sides or the differential starts
#     asserting the defect. Same treatment the io oracle got for
#     ``default_trace_width`` 0.25 -> 0.20. See
#     scripts/check_router_clearance_floor.py and
#     docs/evidence/2026-08-12-clearance-congestion-band.md.
_PINNED = {
    "_pipeline_core_py_oracle.py": "3a719cb2aae66699c4e7aac5d41fb6fcecfefc1e1d82d08735392c5304e7340d",
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
    """Anti-vacuity: the shim run() must delegate to the Rust pyclass."""
    # The pyclass that implements the driver lives in the Rust crate.
    assert _to.RouterPipeline.__module__ == "temper_orchestration"
    # The shim run() references the Rust pyclass by name.
    assert "RouterPipeline" in RouterV6Pipeline.run.__code__.co_names, (
        "shim run() must delegate to the Rust RouterPipeline pyclass"
    )
    assert RouterV6Pipeline.run.__globals__["_to"] is _to
    # The oracle's run_verbatim does NOT reference the Rust pyclass.
    assert "RouterPipeline" not in _orc.run_verbatim.__code__.co_names
    # The oracle keeps the pure-Python loop (time.time wall-clock etc.).
    assert "time" in _orc.run_verbatim.__code__.co_names


# ---------------------------------------------------------------------------
# Corpus: deterministic fake leaf call-backs (shared by both arms)
# ---------------------------------------------------------------------------


class _FakeNet:
    def __init__(self, name: str, pins: int = 2):
        self.name = name
        self.pins = list(range(pins))


class _FakeDesignRules:
    def __init__(self):
        self.net_class_assignments: dict = {}
        self.net_classes: dict = {}
        self.default_clearance_mm = 0.3


class _FakePcb:
    def __init__(self, nets, components=(), board=None, validation_errors=()):
        self.nets = list(nets)
        self.components = list(components)
        self.design_rules = _FakeDesignRules()
        self.board = board
        self._validation_errors = list(validation_errors)

    def validate_placement(self):
        return list(self._validation_errors)


class _FakeStage2:
    def __init__(self, tag="s2"):
        self.tag = tag
        self.occupancy_grids = {}
        self.skeletons = {}


class _FakeStage3:
    def __init__(self, tag="s3"):
        self.tag = tag
        self.topology_graph = object()  # truthy
        self.constraint_model = None
        self.solution = None


class _FakeRoutingResults:
    def __init__(self, success=3, failed=1):
        self.success_count = success
        self.failure_count = failed
        self.results = {}


class _FakeStage4:
    def __init__(self, tag="s4"):
        self.tag = tag
        self.routing_results = _FakeRoutingResults()


class _FakeManufacturingReport:
    def __init__(self, critical=0, total=0):
        self.critical_violations = critical
        self.total_violations = total


class _FakeLedger:
    def __init__(self, log):
        self._log = log

    def checkin(self, state_or_pcb):
        self._log.append(("ledger.checkin",))

    def checkout(self, stage_name, state_or_pcb):
        self._log.append(("ledger.checkout", stage_name))


class _FakeGateStatus:
    UNMEASURED = object()
    VIOLATIONS = object()


class _FakeGateBoardState:
    """Fake ``gates.BoardState``: constructed via
    ``BoardState(routed_pcb_path=...)`` (the call-site shape); construction
    is recorded into the class-level ``log`` the tests set per arm."""

    log = None

    def __init__(self, routed_pcb_path=None):
        self.routed_pcb_path = routed_pcb_path
        if type(self).log is not None:
            type(self).log.append(("erc_bs", routed_pcb_path))


class _FakeErcGate:
    """Fake ErcGate class: constructed via ``ErcGate()`` (the call-site
    shape), recording into the arm log; ``result`` is returned by ``check``
    (a class attribute the tests set, so both arms see the same object)."""

    result = None

    def __init__(self, log):
        self._log = log
        log.append(("erc_gate_ctor",))

    def check(self, state):
        self._log.append(("erc_check", getattr(state, "routed_pcb_path", None)))
        return type(self).result


# The shared legalize() result holder (both arms' fake Legalizer classes read
# it; the failure-path test flips it).
_LEGALIZER_HOLDER = {"result": True}


def _make_legalizer_cls(log):
    """A fake Legalizer CLASS for one arm: constructed via ``Legalizer(pcb)``
    (the call-site shape), recording construction + legalize into ``log``."""

    class _FL:
        def __init__(self, pcb):
            self.auditor = SimpleNamespace(check_collisions=lambda: [])
            log.append(("legalizer_ctor",))

        def legalize(self):
            log.append(("legalize",))
            return _LEGALIZER_HOLDER["result"]

    return _FL


# ---------------------------------------------------------------------------
# Corpus helpers
# ---------------------------------------------------------------------------

DEFAULT_NETS = [
    _FakeNet("SPI_MOSI", 2),
    _FakeNet("GND", 4),
    _FakeNet("USB_D_P", 2),
]


def _fake_parse(log, nets, validation_errors=()):
    def _parse(pcb_path, *, use_declared_layer_roles=False):
        log.append(("parse", pcb_path, use_declared_layer_roles))
        return _FakePcb(
            [_FakeNet(n.name, len(n.pins)) for n in nets],
            validation_errors=validation_errors,
        )

    return _parse


def _fake_dense(log, refs=("U1", "U2")):
    def _identify(pcb_components):
        log.append(("dense", len(pcb_components)))
        return [
            SimpleNamespace(
                component=SimpleNamespace(ref=r),
                _ref=r,
                requires_escape=True,
            )
            for r in refs
        ]

    return _identify


def _fake_escape(log, with_vias=("U1",)):
    def _generate(pkg, design_rules, strategy="dog-bone"):
        log.append(("escape", pkg._ref, strategy))
        if pkg._ref in with_vias:
            return [object()]
        return []

    return _generate


class _ArmState:
    """Per-arm capture of the objects the leaf call-backs received/returned,
    so the state THREADING can be asserted intra-arm (object identity)."""

    def __init__(self, log):
        self.log = log
        self.stage2_in = None
        self.stage2_out = None
        self.stage3_in = None
        self.stage3_out = None
        self.stage4_in = None
        self.stage4_out = None
        self.resource_in = None
        self.fence_calls = []
        self.manufacturing_in = None
        self.manufacturing_out = None


def _make_pipeline(
    arm: _ArmState,
    *,
    verbose=False,
    skip_stage3=False,
    enable_legalization=True,
    enable_manufacturing_drc=False,
    dfm_fail_on="critical",
    report=None,
    fence=None,
    enable_erc_check=False,
    stage2_out=None,
    stage3_out=None,
    stage4_out=None,
    stage3_raises=None,
    batch_results=None,
):
    pipe = RouterV6Pipeline(
        verbose=verbose,
        skip_stage3=skip_stage3,
        enable_legalization=enable_legalization,
        enable_manufacturing_drc=enable_manufacturing_drc,
        dfm_fail_on=dfm_fail_on,
        fence=fence,
        enable_erc_check=enable_erc_check,
    )

    def _stage2(pcb, escape_vias):
        arm.log.append(("stage2",))
        arm.stage2_in = (pcb, escape_vias)
        out = stage2_out if stage2_out is not None else _FakeStage2()
        arm.stage2_out = out
        return out

    def _resource_bound(pcb, stage2):
        arm.log.append(("resource_bound",))
        arm.resource_in = (pcb, stage2)

    def _stage3(pcb, stage2):
        arm.log.append(("stage3",))
        arm.stage3_in = (pcb, stage2)
        if stage3_raises is not None:
            raise stage3_raises
        out = stage3_out if stage3_out is not None else _FakeStage3()
        arm.stage3_out = out
        return out

    def _stage4(pcb, stage2, stage3, escape_vias):
        arm.log.append(("stage4",))
        arm.stage4_in = (pcb, stage2, stage3, escape_vias)
        out = stage4_out if stage4_out is not None else _FakeStage4()
        arm.stage4_out = out
        return out

    def _manufacturing(pcb, routing_results):
        arm.log.append(("manufacturing",))
        arm.manufacturing_in = (pcb, routing_results)
        out = report if report is not None else _FakeManufacturingReport()
        arm.manufacturing_out = out
        return out

    def _fence(*, stage_name, invariants, pcb, escape_vias=None, routing_results=None):
        arm.log.append(("fence", stage_name, len(invariants)))
        arm.fence_calls.append((stage_name, pcb, escape_vias, routing_results))

    pipe._run_stage2 = _stage2
    pipe._compute_resource_bound = _resource_bound
    pipe._run_stage3 = _stage3
    pipe._run_stage4 = _stage4
    pipe._run_stage5 = lambda _pcb, _stage2, _pf: _FakeStage4()  # unreachable: stage4 faked
    pipe._run_manufacturing_drc = _manufacturing
    pipe._run_fence = _fence
    pipe.ledger = _FakeLedger(arm.log)
    if batch_results is not None:
        pipe.last_batch_results = list(batch_results)
    return pipe


def _patch_modules(monkeypatch, arm, *, nets=DEFAULT_NETS, validation_errors=()):
    """Patch the module-level leaf call-backs the DRIVER imports at runtime
    (and the oracle's call-time inline imports resolve to). The ``_pipeline_core``
    module-top bindings are patched too: the pre-port (verbatim) ``run()``
    resolves ``Legalizer`` / ``identify_dense_packages`` /
    ``generate_escape_vias`` through them; once the shim delegates to the
    Rust driver (which imports the source modules at runtime) those bindings
    are inert."""
    import temper_placer.io.kicad_parser as _kicad_parser
    import temper_placer.placer.cp_sat.gates as _gates_mod
    import temper_placer.router_v6._pipeline_core as _core_mod
    import temper_placer.router_v6.dense_package_detection as _dense_mod
    import temper_placer.router_v6.escape_via_generator as _escape_mod
    import temper_placer.router_v6.placement_legalization as _legalizer_mod

    monkeypatch.setattr(
        _kicad_parser, "parse_kicad_pcb_v6",
        _fake_parse(arm.log, nets, validation_errors),
    )
    monkeypatch.setattr(_dense_mod, "identify_dense_packages", _fake_dense(arm.log))
    monkeypatch.setattr(_escape_mod, "generate_escape_vias", _fake_escape(arm.log))
    monkeypatch.setattr(_legalizer_mod, "Legalizer", _make_legalizer_cls(arm.log))
    # RED-mode compatibility: the verbatim run() resolves these through the
    # _pipeline_core module bindings. In GREEN (the shim delegates; the
    # driver imports the source modules) the module no longer binds them,
    # so `raising=False` creates the attrs for the patch and the inert
    # entries are harmless.
    monkeypatch.setattr(_core_mod, "identify_dense_packages", _fake_dense(arm.log), raising=False)
    monkeypatch.setattr(_core_mod, "generate_escape_vias", _fake_escape(arm.log), raising=False)
    monkeypatch.setattr(_core_mod, "Legalizer", _make_legalizer_cls(arm.log), raising=False)
    monkeypatch.setattr(_gates_mod, "GateStatus", _FakeGateStatus)
    monkeypatch.setattr(_gates_mod, "BoardState", _FakeGateBoardState)
    monkeypatch.setattr(_gates_mod, "ErcGate", _FakeErcGate)


def _patch_oracle_arm(monkeypatch, arm):
    """Patch the oracle module's OWN module-top bindings (the oracle body
    references the bare names; the shim driver references the source modules
    -- patched by ``_patch_modules``)."""
    import temper_placer.placer.cp_sat.gates as _gates_mod

    monkeypatch.setattr(_orc, "identify_dense_packages", _fake_dense(arm.log))
    monkeypatch.setattr(_orc, "generate_escape_vias", _fake_escape(arm.log))
    monkeypatch.setattr(_orc, "Legalizer", _make_legalizer_cls(arm.log))
    monkeypatch.setattr(_gates_mod, "GateStatus", _FakeGateStatus)
    monkeypatch.setattr(_gates_mod, "BoardState", _FakeGateBoardState)
    monkeypatch.setattr(_gates_mod, "ErcGate", _FakeErcGate)


def _run_oracle(monkeypatch, pipe, pcb_path, arm, validation_errors=(), **run_kwargs):
    """Oracle arm: the VERBATIM pre-migration run() body on a real shim
    instance whose leaf call-backs are the shared fakes."""
    _patch_modules(monkeypatch, arm, validation_errors=validation_errors)
    _patch_oracle_arm(monkeypatch, arm)
    return _orc.run_verbatim(pipe, pcb_path, **run_kwargs)


def _run_shim(monkeypatch, pipe, pcb_path, arm, validation_errors=(), **run_kwargs):
    """Shim arm: the delegation run() -> the Rust RouterPipeline driver."""
    _patch_modules(monkeypatch, arm, validation_errors=validation_errors)
    return pipe.run(pcb_path, **run_kwargs)


def _run_both(monkeypatch, pcb_path, validation_errors=(), **kwargs):
    """Run both arms with identical config + fakes; return (result_o, result_s,
    arm_o, arm_s). ``kwargs`` are the pipeline config kwargs."""
    arm_o = _ArmState([])
    arm_s = _ArmState([])
    pipe_o = _make_pipeline(arm_o, **kwargs)
    pipe_s = _make_pipeline(arm_s, **kwargs)
    result_o = _run_oracle(
        monkeypatch, pipe_o, pcb_path, arm_o, validation_errors=validation_errors
    )
    result_s = _run_shim(
        monkeypatch, pipe_s, pcb_path, arm_s, validation_errors=validation_errors
    )
    return result_o, result_s, arm_o, arm_s


_PCB_PATH = Path("/nonexistent/placeholder-not-read.kicad_pcb")

# The canonical default-config call sequence (fence off, DFM off, ERC off).
# validate_placement is a method on the fake PCB, not a logged call-back; the
# logged sequence is the call-backs only.
_CANONICAL_SEQUENCE = [
    "parse",
    "legalizer_ctor",
    "legalize",
    "ledger.checkin",
    "dense",
    "escape",  # U1 dog-bone -> vias
    "escape",  # U2 dog-bone -> empty
    "escape",  # U2 via-in-pad -> vias
    "ledger.checkout",
    "stage2",
    "resource_bound",
    "stage3",
    "stage4",
    "ledger.checkout",
]


def test_requires_escape_false_skips_rust_generation_but_not_oracle(monkeypatch) -> None:
    """Rust must not consume escape-via space for a non-escaping dense package.

    The pinned oracle intentionally retains its historical behavior so this
    test makes the migration's deliberate semantic divergence explicit.
    """
    package = SimpleNamespace(
        component=SimpleNamespace(ref="U8"),
        _ref="U8",
        pin_count=20,
        pitch_mm=0.635,
        package_type="QFN",
        requires_escape=False,
    )

    def _one_non_escaping_package(_pcb_components):
        return [package]

    def _one_escape_via(log):
        def _generate(pkg, design_rules, strategy="dog-bone"):  # noqa: ARG001
            log.append(("escape", pkg._ref, strategy))
            return [object()]

        return _generate

    arm_o = _ArmState([])
    arm_s = _ArmState([])
    pipe_o = _make_pipeline(arm_o)
    pipe_s = _make_pipeline(arm_s)

    _patch_modules(monkeypatch, arm_o)
    _patch_oracle_arm(monkeypatch, arm_o)
    import temper_placer.router_v6._pipeline_core as _core_mod
    import temper_placer.router_v6.dense_package_detection as _dense_mod
    import temper_placer.router_v6.escape_via_generator as _escape_mod

    monkeypatch.setattr(_dense_mod, "identify_dense_packages", _one_non_escaping_package)
    monkeypatch.setattr(_escape_mod, "generate_escape_vias", _one_escape_via(arm_o.log))
    monkeypatch.setattr(_core_mod, "identify_dense_packages", _one_non_escaping_package, raising=False)
    monkeypatch.setattr(_core_mod, "generate_escape_vias", _one_escape_via(arm_o.log), raising=False)
    monkeypatch.setattr(_orc, "identify_dense_packages", _one_non_escaping_package)
    monkeypatch.setattr(_orc, "generate_escape_vias", _one_escape_via(arm_o.log))

    result_o = _orc.run_verbatim(pipe_o, _PCB_PATH)

    _patch_modules(monkeypatch, arm_s)
    monkeypatch.setattr(_dense_mod, "identify_dense_packages", _one_non_escaping_package)
    monkeypatch.setattr(_escape_mod, "generate_escape_vias", _one_escape_via(arm_s.log))
    monkeypatch.setattr(_core_mod, "identify_dense_packages", _one_non_escaping_package, raising=False)
    monkeypatch.setattr(_core_mod, "generate_escape_vias", _one_escape_via(arm_s.log), raising=False)

    result_s = pipe_s.run(_PCB_PATH)

    assert len(result_o.escape_vias) == 1
    assert [entry for entry in arm_o.log if entry[0] == "escape"] == [
        ("escape", "U8", "dog-bone"),
    ]
    assert result_s.escape_vias == []
    assert [entry for entry in arm_s.log if entry[0] == "escape"] == []

# ---------------------------------------------------------------------------
# Call sequence + state threading (G2)
# ---------------------------------------------------------------------------


def test_call_sequence_matches_oracle(monkeypatch) -> None:
    """The driver issues the identical call sequence (order + stage args) as
    the verbatim oracle loop, on the default config."""
    result_o, result_s, arm_o, arm_s = _run_both(monkeypatch, _PCB_PATH)

    assert arm_s.log == arm_o.log, (
        f"call sequence diverged:\n  oracle={arm_o.log}\n  shim  ={arm_s.log}"
    )
    assert [e[0] for e in arm_s.log] == _CANONICAL_SEQUENCE
    # The parse call carried the plane-condemnation flag (R8) on both arms.
    assert arm_o.log[0] == ("parse", _PCB_PATH, True)
    assert arm_s.log[0] == ("parse", _PCB_PATH, True)
    # Result equality (content level; object identity asserted separately).
    assert result_s.stage4.routing_results.success_count == result_o.stage4.routing_results.success_count
    assert result_s.escape_vias and result_o.escape_vias


def test_state_threading_preserves_object_identity(monkeypatch) -> None:
    """The pcb / escape_vias / stage2 / stage3 / stage4 objects thread
    through the driver with object identity (no copies) -- asserted
    intra-arm on BOTH arms."""
    _, _, arm_o, arm_s = _run_both(monkeypatch, _PCB_PATH, fence=object())

    for arm, label in ((arm_o, "oracle"), (arm_s, "shim")):
        pcb, stage2_in, stage3_in, escape_vias = arm.stage4_in
        # The pcb threaded from parse through every stage.
        assert arm.stage2_in[0] is pcb, f"{label}: pcb identity broken at stage2"
        assert arm.resource_in[0] is pcb, f"{label}: pcb identity broken at resource"
        assert arm.stage3_in[0] is pcb, f"{label}: pcb identity broken at stage3"
        # escape_vias threaded from the S1 loop into stage2/stage4.
        assert arm.stage2_in[1] is escape_vias, f"{label}: escape_vias identity broken"
        # stage4 received the stage3 object the stage3 call-back returned.
        assert stage3_in is arm.stage3_out, f"{label}: stage3 threading broken"
        # resource bound saw the stage2 the stage2 call-back returned.
        assert arm.resource_in[1] is arm.stage2_out, f"{label}: stage2 threading broken"
        # the fences saw the same pcb and escape_vias.
        assert arm.fence_calls, f"{label}: fence not invoked with fence set"
        for stage_name, p, ev, _rr in arm.fence_calls:
            assert p is pcb, f"{label}: fence {stage_name} pcb identity broken"
            if ev is not None:
                assert ev is escape_vias, f"{label}: fence {stage_name} vias identity broken"


def test_batch_results_threaded_into_result(monkeypatch) -> None:
    """``batch_results=list(self.last_batch_results)`` on both arms."""
    batch = [{"net": "N1"}]
    result_o, result_s, _, _ = _run_both(monkeypatch, _PCB_PATH, batch_results=batch)
    assert result_o.batch_results == batch
    assert result_s.batch_results == batch


# ---------------------------------------------------------------------------
# Conditionals
# ---------------------------------------------------------------------------


def test_skip_stage3_bypasses_sat(monkeypatch) -> None:
    """skip_stage3=True: ``_run_stage3`` is never called on either arm and
    the result's stage3 is the empty Stage3Output (topology_graph=None)."""
    result_o, result_s, arm_o, arm_s = _run_both(monkeypatch, _PCB_PATH, skip_stage3=True)
    assert [e[0] for e in arm_o.log].count("stage3") == 0
    assert [e[0] for e in arm_s.log].count("stage3") == 0
    for result in (result_o, result_s):
        assert result.stage3.topology_graph is None
        assert result.stage3.constraint_model is None
        assert result.stage3.solution is None
    # The rest of the sequence is unchanged (stage4 still runs).
    assert ("stage4",) in arm_s.log
    assert arm_s.log == arm_o.log


def test_legalization_conditional(monkeypatch) -> None:
    """enable_legalization=False: no Legalizer is constructed; True: exactly
    one construction and one legalize call on both arms."""
    _, _, arm_o_off, arm_s_off = _run_both(
        monkeypatch, _PCB_PATH, enable_legalization=False
    )
    for arm in (arm_o_off, arm_s_off):
        assert "legalizer_ctor" not in [e[0] for e in arm.log]

    _, _, arm_o_on, arm_s_on = _run_both(
        monkeypatch, _PCB_PATH, enable_legalization=True
    )
    for arm in (arm_o_on, arm_s_on):
        names = [e[0] for e in arm.log]
        assert names.count("legalizer_ctor") == 1
        assert names.count("legalize") == 1


def test_legalize_failure_path_rechecks_auditor(monkeypatch) -> None:
    """legalize() returning False re-invokes the auditor (the advisory
    pin-hull path) identically on both arms; the run still completes."""
    _LEGALIZER_HOLDER["result"] = False
    try:
        _, _, arm_o, arm_s = _run_both(
            monkeypatch, _PCB_PATH, enable_legalization=True
        )
        for arm in (arm_o, arm_s):
            names = [e[0] for e in arm.log]
            assert names.count("legalizer_ctor") == 1
            assert names.count("legalize") == 1
        assert arm_s.log == arm_o.log
    finally:
        _LEGALIZER_HOLDER["result"] = True


def test_manufacturing_drc_conditional(monkeypatch) -> None:
    """DFM off: no manufacturing call, report None. On: exactly one call and
    the report is threaded into the result."""
    result_o, result_s, arm_o, arm_s = _run_both(
        monkeypatch, _PCB_PATH, enable_manufacturing_drc=False
    )
    for arm in (arm_o, arm_s):
        assert "manufacturing" not in [e[0] for e in arm.log]
    assert result_o.manufacturing_report is None
    assert result_s.manufacturing_report is None

    report = _FakeManufacturingReport(critical=0, total=2)
    result_o, result_s, arm_o, arm_s = _run_both(
        monkeypatch, _PCB_PATH,
        enable_manufacturing_drc=True, dfm_fail_on="none", report=report,
    )
    for arm in (arm_o, arm_s):
        assert [e[0] for e in arm.log].count("manufacturing") == 1
    assert result_o.manufacturing_report is report
    assert result_s.manufacturing_report is report


def test_manufacturing_fail_mode_raise_parity(monkeypatch) -> None:
    """The dfm_fail_on raise decision matches the oracle exactly: "critical"
    raises iff critical_violations > 0; "all" raises iff total > 0; "none"
    never raises. Error parity: the raised exception's type and message are
    compared; the success path's result content is pinned elsewhere (the
    default-object repr embeds memory addresses, so the outcome projection
    is ("ok",) vs ("raised", type, message))."""

    def _outcome(fn):
        try:
            fn()
            return ("ok",)
        except Exception as exc:  # noqa: BLE001 -- failure parity IS the test
            return ("raised", type(exc).__name__, str(exc))

    cases = [
        {"dfm_fail_on": "critical", "report": _FakeManufacturingReport(0, 0)},
        {"dfm_fail_on": "critical", "report": _FakeManufacturingReport(1, 1)},
        {"dfm_fail_on": "critical", "report": _FakeManufacturingReport(0, 5)},
        {"dfm_fail_on": "all", "report": _FakeManufacturingReport(0, 0)},
        {"dfm_fail_on": "all", "report": _FakeManufacturingReport(1, 0)},
        {"dfm_fail_on": "all", "report": _FakeManufacturingReport(0, 3)},
        {"dfm_fail_on": "none", "report": _FakeManufacturingReport(9, 9)},
    ]
    for kwargs in cases:
        arm_o = _ArmState([])
        arm_s = _ArmState([])
        pipe_o = _make_pipeline(arm_o, enable_manufacturing_drc=True, **kwargs)
        pipe_s = _make_pipeline(arm_s, enable_manufacturing_drc=True, **kwargs)
        out_o = _outcome(
            lambda _po=pipe_o, _ao=arm_o: _run_oracle(monkeypatch, _po, _PCB_PATH, _ao)
        )
        out_s = _outcome(
            lambda _ps=pipe_s, _as=arm_s: _run_shim(monkeypatch, _ps, _PCB_PATH, _as)
        )
        assert out_s == out_o, f"fail-mode divergence for {kwargs}: {out_s} != {out_o}"
        if out_s[0] == "raised":
            assert out_s[1] == "ManufacturingDRCViolationError"
            assert "Fail mode" in out_s[2]


def test_fence_sequence_matches_oracle(monkeypatch) -> None:
    """With a fence set, both loops invoke the fence call-back with the
    identical (stage_name, invariants-count, pcb, escape_vias,
    routing_results) sequence; the fence gates (fence-1 only when
    escape_vias is non-empty, fence-4 only when routing_results is truthy)
    match."""
    _, _, arm_o, arm_s = _run_both(monkeypatch, _PCB_PATH, fence=object())
    # fence_calls carry the per-arm pcb object (identity differs across
    # arms); project to (stage_name, escape_vias-present, routing_results-present)
    # for the cross-arm comparison -- object identity is pinned intra-arm by
    # test_state_threading_preserves_object_identity.
    def _proj(calls):
        return [(name, ev is not None, rr is not None) for name, _p, ev, rr in calls]

    assert _proj(arm_s.fence_calls) == _proj(arm_o.fence_calls)
    assert len(arm_s.fence_calls) == 3  # 0.5 + 1 + 4 (escape_vias non-empty)
    assert [c[0] for c in arm_s.fence_calls] == [
        "router_v6.legalization",
        "router_v6.escape_vias",
        "router_v6.geometric",
    ]
    # fence-1 carries escape_vias; fence-4 carries routing_results.
    assert arm_s.fence_calls[1][2] is not None and arm_s.fence_calls[1][3] is None
    assert arm_s.fence_calls[2][3] is not None and arm_s.fence_calls[2][2] is None


def test_fence_gated_on_escape_vias_and_routing_results(monkeypatch) -> None:
    """A package set with NO escape vias skips the fence-1 call on both
    arms (``if self.fence and escape_vias:``); the fence-4 gate mirrors it."""
    arm_o = _ArmState([])
    arm_s = _ArmState([])
    pipe_o = _make_pipeline(arm_o, fence=object())
    pipe_s = _make_pipeline(arm_s, fence=object())

    def no_vias(pkg, design_rules, strategy="dog-bone"):  # noqa: ARG001
        return []

    def one_pkg(pcb_components):  # noqa: ARG001
        return [
            SimpleNamespace(
                component=SimpleNamespace(ref="U1"),
                _ref="U1",
                requires_escape=True,
            )
        ]
    _patch_modules(monkeypatch, arm_o)
    _patch_modules(monkeypatch, arm_s)
    _patch_oracle_arm(monkeypatch, arm_o)
    import temper_placer.router_v6._pipeline_core as _core_mod
    import temper_placer.router_v6.dense_package_detection as _dense_mod
    import temper_placer.router_v6.escape_via_generator as _escape_mod

    monkeypatch.setattr(_dense_mod, "identify_dense_packages", one_pkg)
    monkeypatch.setattr(_escape_mod, "generate_escape_vias", no_vias)
    monkeypatch.setattr(_core_mod, "identify_dense_packages", one_pkg, raising=False)
    monkeypatch.setattr(_core_mod, "generate_escape_vias", no_vias, raising=False)
    monkeypatch.setattr(_orc, "identify_dense_packages", one_pkg)
    monkeypatch.setattr(_orc, "generate_escape_vias", no_vias)

    result_o = _orc.run_verbatim(pipe_o, _PCB_PATH)
    result_s = pipe_s.run(_PCB_PATH)

    assert result_o.escape_vias == []
    assert result_s.escape_vias == []
    # fence-1 is gated on escape_vias (skipped); fence-4 is gated on
    # routing_results (truthy -> runs). Object identity is pinned intra-arm.
    def _proj(calls):
        return [(name, ev is not None, rr is not None) for name, _p, ev, rr in calls]

    assert [c[0] for c in arm_o.fence_calls] == [
        "router_v6.legalization", "router_v6.geometric",
    ]
    assert _proj(arm_s.fence_calls) == _proj(arm_o.fence_calls)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


def test_validation_error_parity(monkeypatch) -> None:
    """A PCB whose validate_placement() reports errors raises the identical
    ValueError (type + message) on both arms."""
    from tests.validation._drc_contract_canon import canon_call

    arm_o = _ArmState([])
    arm_s = _ArmState([])
    pipe_o = _make_pipeline(arm_o)
    pipe_s = _make_pipeline(arm_s)

    out_o = canon_call(
        _run_oracle, monkeypatch, pipe_o, _PCB_PATH, arm_o,
        validation_errors=["overlap: U1/U2"],
    )
    out_s = canon_call(
        _run_shim, monkeypatch, pipe_s, _PCB_PATH, arm_s,
        validation_errors=["overlap: U1/U2"],
    )
    assert out_s == out_o
    assert out_s[0] == "raised"
    assert out_s[1] == "ValueError"
    assert "PCB validation failed" in out_s[2]


def test_stage_exception_propagation_parity(monkeypatch) -> None:
    """A raising stage halts both loops with the SAME exception (type +
    message); stages before it ran, stages after it did not."""

    class _Boom(RuntimeError):
        pass

    for stage_name in ("stage2", "stage3", "stage4"):
        arm_o = _ArmState([])
        arm_s = _ArmState([])
        if stage_name == "stage2":
            pipe_o = _make_pipeline(arm_o)
            pipe_s = _make_pipeline(arm_s)

            def _raise2(pcb, escape_vias, _log=arm_o.log):  # noqa: ARG001
                _log.append(("stage2",))
                raise _Boom("stage2 blew up")

            def _raise2_s(pcb, escape_vias, _log=arm_s.log):  # noqa: ARG001
                _log.append(("stage2",))
                raise _Boom("stage2 blew up")

            pipe_o._run_stage2 = _raise2
            pipe_s._run_stage2 = _raise2_s
        elif stage_name == "stage3":
            pipe_o = _make_pipeline(arm_o, stage3_raises=_Boom("stage3 blew up"))
            pipe_s = _make_pipeline(arm_s, stage3_raises=_Boom("stage3 blew up"))
        else:
            pipe_o = _make_pipeline(arm_o)
            pipe_s = _make_pipeline(arm_s)

            def _raise4(pcb, stage2, stage3, escape_vias, _log=arm_o.log):  # noqa: ARG001
                _log.append(("stage4",))
                raise _Boom("stage4 blew up")

            def _raise4_s(pcb, stage2, stage3, escape_vias, _log=arm_s.log):  # noqa: ARG001
                _log.append(("stage4",))
                raise _Boom("stage4 blew up")

            pipe_o._run_stage4 = _raise4
            pipe_s._run_stage4 = _raise4_s

        with pytest.raises(_Boom, match=f"{stage_name} blew up"):
            _run_oracle(monkeypatch, pipe_o, _PCB_PATH, arm_o)
        with pytest.raises(_Boom, match=f"{stage_name} blew up"):
            _run_shim(monkeypatch, pipe_s, _PCB_PATH, arm_s)
        # identical executed prefix on both arms
        assert arm_s.log == arm_o.log
        assert (stage_name,) in arm_s.log


# ---------------------------------------------------------------------------
# Verbose stdout (byte-for-byte, modulo the wall-clock runtime line)
# ---------------------------------------------------------------------------

_RUNTIME_LINE = re.compile(r"^Router V6 complete in .*s$")


def _strip_runtime(captured: str) -> list[str]:
    return [line for line in captured.splitlines() if not _RUNTIME_LINE.match(line)]


def test_verbose_stdout_matches_oracle(monkeypatch, capsys) -> None:
    """The verbose print sequence (Stage 0 .. summary) is byte-identical
    between the two arms. The wall-clock "Router V6 complete in N.Ns" line
    is nondeterministic by design (preserved, not pinned) and is the ONLY
    line excluded from the comparison."""
    arm_o = _ArmState([])
    arm_s = _ArmState([])
    pipe_o = _make_pipeline(arm_o, verbose=True, skip_stage3=False)
    pipe_s = _make_pipeline(arm_s, verbose=True, skip_stage3=False)

    capsys.readouterr()  # flush
    _run_oracle(monkeypatch, pipe_o, _PCB_PATH, arm_o)
    out_o = capsys.readouterr().out

    _run_shim(monkeypatch, pipe_s, _PCB_PATH, arm_s)
    out_s = capsys.readouterr().out

    assert _strip_runtime(out_s) == _strip_runtime(out_o), (
        f"verbose stdout diverged:\n--- oracle ---\n{out_o}\n--- shim ---\n{out_s}"
    )


# ---------------------------------------------------------------------------
# Stage-0 setup: netclass injection + net priority sort
# ---------------------------------------------------------------------------


def test_stage0_injection_and_net_sort_match_oracle(monkeypatch) -> None:
    """The Stage-0 setup marshalling (pcb_override swap, netclass/assignment
    injection, the power-first stable net sort) leaves the pcb
    byte-identically configured on both arms.

    Since 2026-08-12 the injection no longer clobbers
    ``default_clearance_mm`` to 0.15 -- that was 0.05mm below the floor the
    DRC grades the same copper at, see
    ``scripts/check_router_clearance_floor.py`` -- so the parsed value
    (0.3 on this fake) must survive the injection unchanged on both arms."""
    nets = [
        _FakeNet("SPI_MOSI", 2),
        _FakeNet("GND", 4),
        _FakeNet("USB_D_P", 2),
        _FakeNet("GATE_H", 2),
        _FakeNet("TEMP_SENSE", 2),
    ]
    arm_o = _ArmState([])
    arm_s = _ArmState([])
    pipe_o = _make_pipeline(arm_o)
    pipe_s = _make_pipeline(arm_s)

    import temper_placer.io.kicad_parser as _kicad_parser

    _patch_oracle_arm(monkeypatch, arm_o)
    _patch_modules(monkeypatch, arm_s)

    # The 5-net corpus parse override (after _patch_modules so it wins).
    monkeypatch.setattr(
        _kicad_parser, "parse_kicad_pcb_v6",
        lambda _pcb_path, *, use_declared_layer_roles=False: _FakePcb(  # noqa: ARG005
            [_FakeNet(n.name, len(n.pins)) for n in nets]
        ),
    )

    net_classes = {"Power": object()}
    assignments = {"GND": "Power"}

    result_o = _orc.run_verbatim(
        pipe_o, _PCB_PATH,
        net_class_assignments=assignments, net_classes=net_classes,
    )
    result_s = pipe_s.run(
        _PCB_PATH,
        net_class_assignments=assignments, net_classes=net_classes,
    )

    def _state(pcb):
        return (
            [n.name for n in pcb.nets],
            dict(pcb.design_rules.net_class_assignments),
            pcb.design_rules.default_clearance_mm,
            set(pcb.design_rules.net_classes),
        )

    assert _state(result_s.pcb) == _state(result_o.pcb)
    # power-first stable sort: GND + GATE_H (priority 0) first, in stable
    # relative order; the signal nets follow in their original order.
    assert [n.name for n in result_s.pcb.nets] == [
        "GND", "GATE_H", "SPI_MOSI", "USB_D_P", "TEMP_SENSE",
    ]
    assert result_s.pcb.design_rules.default_clearance_mm == 0.3
    assert result_s.pcb.design_rules.net_class_assignments == {"GND": "Power"}


def test_stage0_pcb_override_preserves_identity(monkeypatch) -> None:
    """pcb_override replaces the parse result on both arms (object identity
    preserved); the override's own nets are still sorted."""
    arm_o = _ArmState([])
    arm_s = _ArmState([])
    pipe_o = _make_pipeline(arm_o)
    pipe_s = _make_pipeline(arm_s)
    _patch_modules(monkeypatch, arm_o)
    _patch_modules(monkeypatch, arm_s)
    _patch_oracle_arm(monkeypatch, arm_o)

    override = _FakePcb([_FakeNet("OVERRIDE_NET", 2), _FakeNet("GND", 4)])
    result_o = _orc.run_verbatim(pipe_o, _PCB_PATH, pcb_override=override)
    result_s = pipe_s.run(_PCB_PATH, pcb_override=override)

    assert result_o.pcb is override
    assert result_s.pcb is override
    assert [n.name for n in result_s.pcb.nets] == ["GND", "OVERRIDE_NET"]


def test_stage0_no_injection_when_absent(monkeypatch) -> None:
    """No net_class_assignments/net_classes: the design_rules are left
    untouched (default_clearance_mm stays) and the sort still applies."""
    result_o, result_s, _, _ = _run_both(monkeypatch, _PCB_PATH)
    for result in (result_o, result_s):
        assert result.pcb.design_rules.default_clearance_mm == 0.3
        assert result.pcb.design_rules.net_class_assignments == {}
        # the power-first stable sort ALWAYS applies (no injection needed)
        assert [n.name for n in result.pcb.nets] == ["GND", "SPI_MOSI", "USB_D_P"]


# ---------------------------------------------------------------------------
# ERC gate (opt-in)
# ---------------------------------------------------------------------------


def test_erc_gate_conditional_and_status_branches(monkeypatch, caplog) -> None:
    """enable_erc_check=True invokes the ErcGate with the identical
    BoardState(routed_pcb_path=...) and emits the identical warning for the
    UNMEASURED / VIOLATIONS status branches (message-level parity; the
    oracle body's ``logging.getLogger(__name__)`` resolves ``__name__`` to
    the oracle module -- the logger NAME differs by construction, the
    messages and levels are pinned)."""
    import temper_placer.io.kicad_parser as _kicad_parser
    import temper_placer.placer.cp_sat.gates as _gates_mod
    import temper_placer.router_v6._pipeline_core as _core_mod
    import temper_placer.router_v6.dense_package_detection as _dense_mod
    import temper_placer.router_v6.escape_via_generator as _escape_mod
    import temper_placer.router_v6.placement_legalization as _legalizer_mod

    monkeypatch.setattr(_gates_mod, "GateStatus", _FakeGateStatus)
    monkeypatch.setattr(_gates_mod, "BoardState", _FakeGateBoardState)
    monkeypatch.setattr(_legalizer_mod, "Legalizer", _make_legalizer_cls([]))
    monkeypatch.setattr(_dense_mod, "identify_dense_packages", _fake_dense([]))
    monkeypatch.setattr(_escape_mod, "generate_escape_vias", _fake_escape([]))
    monkeypatch.setattr(_core_mod, "Legalizer", _make_legalizer_cls([]), raising=False)
    monkeypatch.setattr(_core_mod, "identify_dense_packages", _fake_dense([]), raising=False)
    monkeypatch.setattr(_core_mod, "generate_escape_vias", _fake_escape([]), raising=False)
    monkeypatch.setattr(_orc, "Legalizer", _make_legalizer_cls([]))
    monkeypatch.setattr(_orc, "identify_dense_packages", _fake_dense([]))
    monkeypatch.setattr(_orc, "generate_escape_vias", _fake_escape([]))

    for status_name in ("UNMEASURED", "VIOLATIONS"):
        for n_violations in (0, 3):
            arm_o = _ArmState([])
            arm_s = _ArmState([])

            status = getattr(_FakeGateStatus, status_name)
            if status_name == "UNMEASURED":
                result_obj = SimpleNamespace(
                    status=status, error_message="gate not run", violations=[]
                )
            else:
                result_obj = SimpleNamespace(
                    status=status, error_message="",
                    violations=list(range(n_violations)),
                )
            _FakeErcGate.result = result_obj

            def _make_gate(log):
                class _Gate(_FakeErcGate):
                    def __init__(self):
                        super().__init__(log)

                return _Gate

            monkeypatch.setattr(
                _kicad_parser, "parse_kicad_pcb_v6", _fake_parse(arm_o.log, DEFAULT_NETS),
            )
            _FakeGateBoardState.log = arm_o.log
            pipe_o = _make_pipeline(arm_o, enable_erc_check=True)
            monkeypatch.setattr(_gates_mod, "ErcGate", _make_gate(arm_o.log))
            caplog.clear()
            _orc.run_verbatim(pipe_o, _PCB_PATH)
            msgs_o = [(r.levelname, r.getMessage()) for r in caplog.records]

            monkeypatch.setattr(
                _kicad_parser, "parse_kicad_pcb_v6", _fake_parse(arm_s.log, DEFAULT_NETS),
            )
            _FakeGateBoardState.log = arm_s.log
            pipe_s = _make_pipeline(arm_s, enable_erc_check=True)
            monkeypatch.setattr(_gates_mod, "ErcGate", _make_gate(arm_s.log))
            caplog.clear()
            pipe_s.run(_PCB_PATH)
            msgs_s = [(r.levelname, r.getMessage()) for r in caplog.records]
            _FakeGateBoardState.log = None

            assert msgs_s == msgs_o, (
                f"ERC {status_name} n={n_violations}: {msgs_s} != {msgs_o}"
            )
            if status_name == "UNMEASURED":
                assert msgs_s == [("WARNING", "ERC gate UNMEASURED: gate not run")]
            else:
                assert msgs_s == [
                    ("WARNING", f"ERC gate found {n_violations} violation(s) on routed board")
                ]
            assert ("erc_gate_ctor",) in arm_s.log
            assert ("erc_check", _PCB_PATH) in arm_s.log
            assert arm_s.log == arm_o.log


def test_erc_off_never_imports_gate(monkeypatch) -> None:
    """enable_erc_check=False: no ErcGate construction on either arm."""
    _, _, arm_o, arm_s = _run_both(monkeypatch, _PCB_PATH, enable_erc_check=False)
    for arm in (arm_o, arm_s):
        assert "erc_gate_ctor" not in [e[0] for e in arm.log]
        assert "erc_check" not in [e[0] for e in arm.log]


# ---------------------------------------------------------------------------
# Real end-to-end (G2: the same leaf compute through both loops)
# ---------------------------------------------------------------------------


def test_real_pipeline_end_to_end_matches_oracle() -> None:
    """The full real pipeline on the minimal board fixture (SAT bypassed,
    max_nets=1, verbose off) produces a result matching the oracle's
    verbatim loop -- the leaf compute is shared, so equality of the results
    pins the driver's threading and assembly."""
    pcb_path = Path(__file__).parent.parent / "fixtures" / "minimal_board.kicad_pcb"

    pipe_o = RouterV6Pipeline(
        verbose=False, enable_legalization=False, max_nets=1, skip_stage3=True,
    )
    result_o = _orc.run_verbatim(pipe_o, pcb_path)

    pipe_s = RouterV6Pipeline(
        verbose=False, enable_legalization=False, max_nets=1, skip_stage3=True,
    )
    result_s = pipe_s.run(pcb_path)

    assert result_s.success_count == result_o.success_count
    assert result_s.failure_count == result_o.failure_count
    assert result_s.completion_rate == result_o.completion_rate
    assert result_s.runtime_seconds >= 0
    # stage outputs are the SAME leaf objects produced by the shared compute
    assert repr(result_s.stage4.routing_results) == repr(result_o.stage4.routing_results)
    assert result_s.stage3.topology_graph is None  # skip path on both
    assert result_s.manufacturing_report is None
    assert len(result_s.escape_vias) == len(result_o.escape_vias)
    assert result_s.batch_results == []
