"""Property-based tests (G4) for the U4 pipeline-state port (Rust
Orchestration Engine plan 2026-08-09-001, U4) — the
``temper_placer.pipeline.state`` classes as Rust pyclasses in
``temper-orchestration``.

Module-to-property map (G4 — every reachable behavior pinned):
- PipelineConfig -> P1 (dataclass defaults), P2 (kwargs round-trip),
  P3 (repr self-describes), P4 (eq symmetry + reflexivity),
  P5 (mutation observable).
- PipelineState   -> P6 (dataclass defaults), P7 (default-factory
  independence).
- PipelinePhase   -> P8 (members unique, self-equal, non-equal to others).

Non-vacuity: every property routes its observable through the ``_IMPL``
indirection below and has a ``test_pN_fails_for_<mutant>`` companion
re-running it via ``hypothesis.inner_test`` against a degenerate Python
stand-in and asserting AssertionError.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import temper_orchestration as _to
from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.pipeline import state as _state

_CONFIG_FIELDS = [
    "input_pcb",
    "constraints_yaml",
    "loops_yaml",
    "output_pcb",
    "output_report",
    "output_trace",
    "skip_topological",
    "skip_routing",
    "skip_local_refinement",
    "dry_run",
    "epochs",
    "seed",
    "max_movement_mm",
    "max_iterations",
    "routability_threshold",
    "convergence_threshold",
    "fab_preset",
]

_STATE_FIELDS = [
    "config",
    "current_phase",
    "iteration",
    "success",
    "failure_reason",
    "failed_phase",
    "elapsed_time_s",
    "phase_timings",
    "board",
    "netlist",
    "loops",
    "constraints",
    "deterministic_result",
    "placement_state",
    "routing_result",
    "physics_report",
    "preflight_report",
    "decision_trace",
    "_refinement_complete",
    "_best_routed_nets",
    "_best_routability",
    "_stall_count",
]

_PHASE_MEMBERS = {
    "INPUT": "input",
    "SEMANTIC": "semantic",
    "TOPOLOGICAL": "topological",
    "PREFLIGHT": "preflight",
    "GEOMETRIC": "geometric",
    "ROUTING": "routing",
    "REFINEMENT": "refinement",
    "OUTPUT": "output",
    "ZONE_GEOMETRY": "zone_geometry",
    "ZONE_ASSIGNMENT": "zone_assignment",
    "SLOT_GENERATION": "slot_generation",
    "COMPONENT_ASSIGNMENT": "component_assignment",
    "APPLY_PLACEMENTS": "apply_placements",
    "COURTYARD_CHECK": "courtyard_check",
    "APPLY_PLACEMENTS_REAPPLY": "apply_placements_reapply",
    "PLACEMENT_VALIDATION": "placement_validation",
}

# The observable surface of the pyclasses, routed through an indirection so
# mutation guards can swap in degenerate stand-ins (hypothesis.inner_test)
# and restore.
_IMPL = {
    "make_config": lambda **kw: _state.PipelineConfig(**kw),
    "make_state": lambda cfg: _state.PipelineState(cfg),
    "field": lambda obj, name: getattr(obj, name),
    "config_fields": lambda cfg: tuple(getattr(cfg, f) for f in _CONFIG_FIELDS),
    "state_fields": lambda st: tuple(getattr(st, f) for f in _STATE_FIELDS),
    "repr": lambda obj: repr(obj),
    "eq": lambda a, b: a == b,
}

_FINITE = {"allow_nan": False, "allow_infinity": False}


def _path_or_none():
    return st.one_of(st.none(), st.just(Path("p.kicad_pcb")), st.text(min_size=1, max_size=20))


@pytest.fixture
def _restore_impl():
    saved = dict(_IMPL)
    yield
    _IMPL.clear()
    _IMPL.update(saved)


def _config_kwargs():
    return st.fixed_dictionaries({
        "input_pcb": st.one_of(st.just(Path("x.kicad_pcb")), st.text(min_size=1, max_size=20)),
        "constraints_yaml": _path_or_none(),
        "loops_yaml": _path_or_none(),
        "output_pcb": _path_or_none(),
        "output_report": _path_or_none(),
        "output_trace": _path_or_none(),
        "skip_topological": st.booleans(),
        "skip_routing": st.booleans(),
        "skip_local_refinement": st.booleans(),
        "dry_run": st.booleans(),
        "epochs": st.integers(min_value=0, max_value=20000),
        "seed": st.integers(min_value=-1000, max_value=1000),
        "max_movement_mm": st.floats(min_value=0.0, max_value=50.0, **_FINITE),
        "max_iterations": st.integers(min_value=0, max_value=100),
        "routability_threshold": st.floats(min_value=0.0, max_value=1.0, **_FINITE),
        "convergence_threshold": st.floats(min_value=0.0, max_value=1.0, **_FINITE),
        "fab_preset": st.text(max_size=20),
    })


# ---------------------------------------------------------------------------
# G4 — P1: PipelineConfig dataclass defaults
# ---------------------------------------------------------------------------


@given(pcb=st.text(min_size=1, max_size=20))
@settings(max_examples=100, deadline=30000)
def test_p1_config_defaults(pcb):
    """P1. `PipelineConfig(input_pcb)` yields the documented dataclass
    defaults for every field, in field order.

    A config that defaulted any field differently violates this.
    """
    cfg = _IMPL["make_config"](input_pcb=Path(pcb))
    assert _IMPL["config_fields"](cfg) == (
        Path(pcb), None, None, None, None, None,
        False, False, False, False,
        8000, 42, 2.0, 5, 0.85, 0.01,
        "jlcpcb_standard",
    )


def test_p1_fails_for_wrong_defaults_mutant(_restore_impl):
    class _WrongDefaults:
        def __init__(self):
            self.input_pcb = Path("x")
            self.constraints_yaml = None
            self.loops_yaml = None
            self.output_pcb = None
            self.output_report = None
            self.output_trace = None
            self.skip_topological = False
            self.skip_routing = False
            self.skip_local_refinement = False
            self.dry_run = False
            self.epochs = 0  # wrong
            self.seed = 42
            self.max_movement_mm = 2.0
            self.max_iterations = 5
            self.routability_threshold = 0.85
            self.convergence_threshold = 0.01
            self.fab_preset = "jlcpcb_standard"

    _IMPL["make_config"] = lambda **kw: _WrongDefaults()  # noqa: ARG005
    with pytest.raises(AssertionError):
        test_p1_config_defaults.hypothesis.inner_test("b.kicad_pcb")


def test_p1_fails_for_missing_fields_mutant(_restore_impl):
    _IMPL["make_config"] = lambda **kw: object()  # noqa: ARG005
    with pytest.raises((AssertionError, AttributeError)):
        test_p1_config_defaults.hypothesis.inner_test("b.kicad_pcb")


# ---------------------------------------------------------------------------
# G4 — P2: PipelineConfig kwargs round-trip
# ---------------------------------------------------------------------------


@given(kw=_config_kwargs())
@settings(max_examples=100, deadline=30000)
def test_p2_config_kwargs_roundtrip(kw):
    """P2. Every constructor kwarg is observable via getattr (the dataclass
    stores what it is given — no coercion, no dropped fields)."""
    cfg = _IMPL["make_config"](**kw)
    for field, value in kw.items():
        assert _IMPL["field"](cfg, field) == value, f"field {field} diverged"


def test_p2_fails_for_dropped_value_mutant(_restore_impl):
    _IMPL["field"] = lambda obj, name: None  # noqa: ARG005
    with pytest.raises(AssertionError):
        test_p2_config_kwargs_roundtrip.hypothesis.inner_test(
            {
                "input_pcb": Path("x.kicad_pcb"),
                "epochs": 9000,
                "fab_preset": "custom",
            }
        )


def test_p2_fails_for_coerced_value_mutant(_restore_impl):
    _IMPL["field"] = lambda obj, name: str(getattr(obj, name))  # noqa: ARG005
    with pytest.raises(AssertionError):
        test_p2_config_kwargs_roundtrip.hypothesis.inner_test(
            {"input_pcb": Path("x.kicad_pcb"), "epochs": 9000}
        )


# ---------------------------------------------------------------------------
# G4 — P3: PipelineConfig repr self-describes
# ---------------------------------------------------------------------------


@given(kw=_config_kwargs())
@settings(max_examples=100, deadline=30000)
def test_p3_config_repr_self_describes(kw):
    """P3. repr(cfg) names the class and every field (a repr that omits a
    field is not the dataclass repr)."""
    cfg = _IMPL["make_config"](**kw)
    text = _IMPL["repr"](cfg)
    assert text.startswith("PipelineConfig(")
    assert text.endswith(")")
    for field in _CONFIG_FIELDS:
        assert f"{field}=" in text


def test_p3_fails_for_empty_repr_mutant(_restore_impl):
    _IMPL["repr"] = lambda obj: ""
    with pytest.raises(AssertionError):
        test_p3_config_repr_self_describes.hypothesis.inner_test(
            {"input_pcb": Path("x.kicad_pcb")}
        )


def test_p3_fails_for_partial_repr_mutant(_restore_impl):
    _IMPL["repr"] = lambda obj: "PipelineConfig(epochs=1)"  # noqa: ARG005
    with pytest.raises(AssertionError):
        test_p3_config_repr_self_describes.hypothesis.inner_test(
            {"input_pcb": Path("x.kicad_pcb")}
        )


# ---------------------------------------------------------------------------
# G4 — P4: PipelineConfig equality is symmetric and reflexive
# ---------------------------------------------------------------------------


@given(a=_config_kwargs(), b=_config_kwargs())
@settings(max_examples=100, deadline=30000)
def test_p4_config_eq_symmetric_and_reflexive(a, b):
    """P4. Dataclass equality is symmetric (a==b iff b==a) and reflexive
    (a==a). A `==` that returns a non-bool or is asymmetric violates it."""
    ca = _IMPL["make_config"](**a)
    cb = _IMPL["make_config"](**b)
    ab = _IMPL["eq"](ca, cb)
    ba = _IMPL["eq"](cb, ca)
    assert ab == ba
    assert ab in (True, False)
    assert _IMPL["eq"](ca, ca) is True


def test_p4_fails_for_never_equal_mutant(_restore_impl):
    _IMPL["eq"] = lambda a, b: False  # noqa: ARG005
    with pytest.raises(AssertionError):
        test_p4_config_eq_symmetric_and_reflexive.hypothesis.inner_test(
            {"input_pcb": Path("x.kicad_pcb")}, {"input_pcb": Path("x.kicad_pcb")}
        )


def test_p4_fails_for_asymmetric_mutant(_restore_impl):
    def asymmetric(a, b):
        if a is b:
            return True
        return getattr(a, "epochs", None) >= getattr(b, "epochs", None)

    _IMPL["eq"] = asymmetric
    with pytest.raises(AssertionError):
        test_p4_config_eq_symmetric_and_reflexive.hypothesis.inner_test(
            {"input_pcb": Path("x.kicad_pcb"), "epochs": 5},
            {"input_pcb": Path("x.kicad_pcb"), "epochs": 9},
        )


# ---------------------------------------------------------------------------
# G4 — P5: field mutation is observable
# ---------------------------------------------------------------------------

_BOOL_FIELDS = ["skip_topological", "skip_routing", "skip_local_refinement", "dry_run"]
_FLOAT_FIELDS = ["max_movement_mm", "routability_threshold", "convergence_threshold"]
_INT_FIELDS = ["epochs", "seed", "max_iterations"]
_ANY_FIELDS = [
    "input_pcb", "constraints_yaml", "loops_yaml", "output_pcb", "output_report",
    "output_trace", "fab_preset",
]

_mutation_pairs = st.one_of(
    st.tuples(st.sampled_from(_BOOL_FIELDS), st.booleans()),
    st.tuples(st.sampled_from(_FLOAT_FIELDS), st.floats(min_value=0.0, max_value=10.0, **_FINITE)),
    st.tuples(st.sampled_from(_INT_FIELDS), st.integers(0, 1_000_000)),
    st.tuples(
        st.sampled_from(_ANY_FIELDS),
        st.one_of(st.none(), st.text(min_size=1, max_size=10)),
    ),
)


@given(kw=_config_kwargs(), pair=_mutation_pairs)
@settings(max_examples=100, deadline=30000)
def test_p5_mutation_observable(kw, pair):
    """P5. Setting a field is observable via getattr (mutable dataclass
    semantics — no frozen/read-only surface)."""
    field, value = pair
    cfg = _IMPL["make_config"](**kw)
    setattr(cfg, field, value)
    assert _IMPL["field"](cfg, field) == value


def test_p5_fails_for_readonly_mutant(_restore_impl):
    _IMPL["field"] = lambda obj, name: None  # noqa: ARG005
    with pytest.raises(AssertionError):
        test_p5_mutation_observable.hypothesis.inner_test(
            {"input_pcb": Path("x.kicad_pcb")}, ("epochs", 12345)
        )


# ---------------------------------------------------------------------------
# G4 — P6: PipelineState dataclass defaults
# ---------------------------------------------------------------------------


@given(pcb=st.text(min_size=1, max_size=20))
@settings(max_examples=100, deadline=30000)
def test_p6_state_defaults(pcb):
    """P6. `PipelineState(config)` yields the documented dataclass
    defaults: current_phase INPUT, zero iteration, no failure, empty
    timings/loops, None data slots."""
    st = _IMPL["make_state"](_IMPL["make_config"](input_pcb=Path(pcb)))
    fields = _IMPL["state_fields"](st)
    assert fields[0] is not None  # config
    assert fields[1].value == "input"
    assert fields[2] == 0
    assert fields[3] is False
    assert fields[4] is None
    assert fields[5] is None
    assert fields[6] == 0.0
    assert fields[7] == {}
    assert fields[8] is None
    assert fields[9] is None
    assert fields[10] == []
    assert fields[11] is None
    assert fields[18] is False
    assert fields[19] is None
    assert fields[20] is None
    assert fields[21] == 0


def test_p6_fails_for_wrong_phase_default_mutant(_restore_impl):
    _IMPL["make_state"] = lambda cfg: object()  # noqa: ARG005
    with pytest.raises((AssertionError, AttributeError)):
        test_p6_state_defaults.hypothesis.inner_test("b.kicad_pcb")


def test_p6_fails_for_wrong_stall_default_mutant(_restore_impl):
    class _WrongStall:
        def __init__(self, config):
            self.config = config
            self.current_phase = _to.PipelinePhase.INPUT
            self.iteration = 0
            self.success = False
            self.failure_reason = None
            self.failed_phase = None
            self.elapsed_time_s = 0.0
            self.phase_timings = {}
            self.board = None
            self.netlist = None
            self.loops = []
            self.constraints = None
            self.deterministic_result = None
            self.placement_state = None
            self.routing_result = None
            self.physics_report = None
            self.preflight_report = None
            self.decision_trace = None
            self._refinement_complete = False
            self._best_routed_nets = None
            self._best_routability = None
            self._stall_count = 99  # wrong

    _IMPL["make_state"] = lambda cfg: _WrongStall(cfg)
    with pytest.raises(AssertionError):
        test_p6_state_defaults.hypothesis.inner_test("b.kicad_pcb")


# ---------------------------------------------------------------------------
# G4 — P7: default factories are per-instance
# ---------------------------------------------------------------------------


@given(x=st.text(min_size=1, max_size=10))
@settings(max_examples=100, deadline=30000)
def test_p7_default_factories_independent(x):
    """P7. Each PipelineState gets a FRESH loops list and phase_timings dict
    (the dataclass `field(default_factory=...)` — mutating one instance
    never leaks into another)."""
    s1 = _IMPL["make_state"](_IMPL["make_config"](input_pcb=Path("x.kicad_pcb")))
    s2 = _IMPL["make_state"](_IMPL["make_config"](input_pcb=Path("x.kicad_pcb")))
    s1.loops.append(x)
    s1.phase_timings[x] = 1.0
    assert s2.loops == []
    assert s2.phase_timings == {}


def test_p7_fails_for_shared_container_mutant(_restore_impl):
    class _SharingState:
        loops = []
        phase_timings = {}

        def __init__(self, config):
            self.config = config

    _IMPL["make_state"] = lambda cfg: _SharingState(cfg)
    with pytest.raises(AssertionError):
        test_p7_default_factories_independent.hypothesis.inner_test("leak")


# ---------------------------------------------------------------------------
# G4 — P8: PipelinePhase members are unique and self-equal
# ---------------------------------------------------------------------------


@given(name=st.sampled_from(sorted(_PHASE_MEMBERS)))
@settings(max_examples=100, deadline=30000)
def test_p8_phase_members_unique_and_self_equal(name):
    """P8. Each member carries its documented value, equals only itself
    among the members, and is not equal to its value string."""
    member = getattr(_to.PipelinePhase, name)
    assert member.value == _PHASE_MEMBERS[name]
    assert member.name == name
    assert _IMPL["eq"](member, member) is True
    assert _IMPL["eq"](member, member.value) is False
    for other_name, other_value in _PHASE_MEMBERS.items():
        other = getattr(_to.PipelinePhase, other_name)
        assert _IMPL["eq"](member, other) == (name == other_name)
        assert other.value == other_value


def test_p8_fails_for_always_equal_mutant(_restore_impl):
    _IMPL["eq"] = lambda a, b: True  # noqa: ARG005
    with pytest.raises(AssertionError):
        test_p8_phase_members_unique_and_self_equal.hypothesis.inner_test("INPUT")


def test_p8_fails_for_value_string_mutant(_restore_impl):
    def eq_to_value_string(a, b):
        return a is b or a.value == b

    _IMPL["eq"] = eq_to_value_string
    with pytest.raises(AssertionError):
        test_p8_phase_members_unique_and_self_equal.hypothesis.inner_test("INPUT")
