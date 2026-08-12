"""Property-based tests (G4) for the orchestration-port unit U-E run loop
(Rust Orchestration Engine plan 2026-08-09-001): the
``DeterministicPipeline.run()`` sequencing loop, now implemented in Rust
(``temper-orchestration``'s ``DeterministicPipeline`` pyclass driving the
stages through ``PipelineRunner<BoardState>``).

The unit under test is the LOOP: the per-stage ``state = stage.run(state)``
threading, the call ORDER, the empty-list identity, the untouched-field
identity, the exception propagation and the loop's determinism. The stage
objects are deterministic fakes (the per-stage compute is pinned by the
D1..D7 differentials; the factory ORDER by
``test_deterministic_pipeline_rust_differential.py``).

Module-to-property map (G4 -- every reachable loop behavior pinned):
- P1  -- call ORDER: stages run in declaration order.
- P2  -- DETERMINISM: the same stage list + state yield a byte-identical
  final state across runs.
- P3  -- EMPTY-LIST IDENTITY: no stages -> run(state) IS state (object
  identity, not a copy).
- P4  -- UNTOUCHED-FIELD IDENTITY: fields no stage replaced keep OBJECT
  IDENTITY through the loop.
- P5  -- PREFIX COMPOSITION: run(all) == run(suffix, run(prefix, state))
  for every split point (the loop is a pure left fold).
- P6  -- EXCEPTION PROPAGATION: a raising stage halts the loop, the
  exception propagates unchanged, stages before it ran and stages after it
  did not.

Non-vacuity: every property routes its observable through an ``impl``
parameter (default: the Rust pyclass loop) and has a
``test_pN_fails_for_<mutant>`` companion re-running the body against a
degenerate Python stand-in and asserting AssertionError.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
import temper_orchestration as _to
from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.deterministic.state import BoardState

# ---------------------------------------------------------------------------
# The loop under test + degenerate mutants (vacuity guards)
# ---------------------------------------------------------------------------


def _rust_run(stages, state) -> BoardState:
    """The U-E loop under test: the Rust pyclass run()."""
    return _to.DeterministicPipeline().run(stages, None, state)


def _loop_reversed(stages, state) -> BoardState:
    out = state
    for s in reversed(stages):
        out = s.run(out)
    return out


_MUTATION_STATE = {"calls": 0}


def _loop_nondeterministic(stages, state) -> BoardState:
    """Mutant for P2: every second invocation skips the last stage."""
    _MUTATION_STATE["calls"] += 1
    target = stages if _MUTATION_STATE["calls"] % 2 == 1 else stages[:-1]
    out = state
    for s in target:
        out = s.run(out)
    return out


def _loop_fresh_state(stages, state) -> BoardState:  # noqa: ARG001
    """Mutant for P3: always returns a freshly constructed state."""
    return BoardState()


def _loop_unconditional_replace(stages, state) -> BoardState:
    """Mutant for P4: rebuilds a field's container unconditionally, so
    untouched fields lose OBJECT IDENTITY (a plain `replace(out)` would keep
    the refs -- the point of the property is the loop must NOT copy)."""
    out = state
    for s in stages:
        out = s.run(out)
    if out.config is None:
        return replace(out, net_order=tuple(out.net_order))
    return replace(out, config=dict(out.config))


def _loop_skip_first(stages, state) -> BoardState:
    """Mutant for P5: drops the first stage of the list."""
    out = state
    for s in stages[1:]:
        out = s.run(out)
    return out


def _loop_swallow_exceptions(stages, state) -> BoardState:
    """Mutant for P6: swallows a raising stage and returns the state."""
    out = state
    for s in stages:
        try:
            out = s.run(out)
        except Exception:
            return out
    return out


def _assert_mutant_detected(body, mutant, *args) -> None:
    """Run ``body`` against the degenerate mutant; the body's assertions MUST
    trip. If they do not, the property is vacuous -- a hard failure."""
    with pytest.raises(AssertionError):
        body(mutant, *args)


# ---------------------------------------------------------------------------
# Deterministic fake stages
# ---------------------------------------------------------------------------


class _FakeStage:
    """A named deterministic transform on the frozen BoardState, recording
    its invocation into a shared order log."""

    def __init__(self, name, kind, value, log):
        self._name = name
        self._kind = kind
        self._value = value
        self._log = log
        self.invariants = []
        self.last_modified_regions = None

    @property
    def name(self) -> str:
        return self._name

    def run(self, state: BoardState) -> BoardState:
        self._log.append(self._name)
        if self._kind == "config":
            return replace(state, config={"tag": self._value})
        if self._kind == "net_order":
            return replace(state, net_order=(self._value,))
        if self._kind == "placements":
            return replace(state, placements=frozenset({(self._value, (1.0, 2.0))}))
        if self._kind == "raise":
            raise RuntimeError(f"boom-{self._value}")
        return state  # identity


def _make_stages(specs, log) -> list[_FakeStage]:
    return [_FakeStage(f"s{i}", kind, value, log) for i, (kind, value) in enumerate(specs)]


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_NON_RAISING = ["config", "net_order", "placements", "identity"]


@st.composite
def _stage_specs(draw):
    n = draw(st.integers(min_value=0, max_value=8))
    return [
        (draw(st.sampled_from(_NON_RAISING)), draw(st.text(min_size=1)))
        for _ in range(n)
    ]


@st.composite
def _raising_specs(draw):
    n = draw(st.integers(min_value=1, max_value=6))
    pos = draw(st.integers(min_value=0, max_value=n - 1))
    specs = [
        (draw(st.sampled_from(_NON_RAISING)), draw(st.text(min_size=1)))
        for _ in range(n)
    ]
    specs[pos] = ("raise", "boom")
    return specs


@st.composite
def _states(draw):
    return BoardState(
        config=draw(
            st.one_of(st.none(), st.dictionaries(st.text(min_size=1), st.text()))
        ),
        # net_order is always a tuple on a real BoardState (default_factory);
        # from_python extracts it as Vec<String>, so None is not representable.
        net_order=draw(st.tuples(st.text(min_size=1))),
        placements=draw(
            st.one_of(
                st.none(),
                st.frozensets(
                    st.tuples(
                        st.text(min_size=1),
                        st.tuples(st.floats(allow_nan=False), st.floats(allow_nan=False)),
                    ),
                    max_size=3,
                ),
            )
        ),
    )


# ---------------------------------------------------------------------------
# P1 -- call order
# ---------------------------------------------------------------------------


def _body_p1(impl, specs, state) -> None:
    log = []
    stages = _make_stages(specs, log)
    impl(stages, state)
    assert log == [s.name for s in stages], f"call order diverged: {log}"


@given(_stage_specs(), _states())
@settings(max_examples=100, deadline=None)
def test_p1_stages_run_in_declaration_order(specs, state):
    _body_p1(_rust_run, specs, state)


def test_p1_fails_for_reversed_mutant() -> None:
    _assert_mutant_detected(
        _body_p1,
        _loop_reversed,
        [("config", "a"), ("net_order", "b"), ("identity", "c")],
        BoardState(),
    )


# ---------------------------------------------------------------------------
# P2 -- determinism
# ---------------------------------------------------------------------------


def _body_p2(impl, specs, state) -> None:
    log = []
    stages = _make_stages(specs, log)
    out1 = impl(stages, state)
    out2 = impl(stages, state)
    assert repr(out1) == repr(out2), "two runs of the same stages diverged"


@given(_stage_specs(), _states())
@settings(max_examples=100, deadline=None)
def test_p2_run_is_deterministic(specs, state):
    _body_p2(_rust_run, specs, state)


def test_p2_fails_for_nondeterministic_mutant() -> None:
    _MUTATION_STATE["calls"] = 0
    _assert_mutant_detected(
        _body_p2,
        _loop_nondeterministic,
        [("config", "a"), ("net_order", "b"), ("config", "last")],
        BoardState(),
    )


# ---------------------------------------------------------------------------
# P3 -- empty-list identity
# ---------------------------------------------------------------------------


def _body_p3(impl, state) -> None:
    out = impl([], state)
    assert out is state, "an empty stage list must return the exact state object"


@given(_states())
@settings(max_examples=100, deadline=None)
def test_p3_empty_stage_list_is_identity(state):
    _body_p3(_rust_run, state)


def test_p3_fails_for_fresh_state_mutant() -> None:
    _assert_mutant_detected(_body_p3, _loop_fresh_state, BoardState(config={"x": 1}))


# ---------------------------------------------------------------------------
# P4 -- untouched-field identity
# ---------------------------------------------------------------------------


def _body_p4(impl, specs, state) -> None:
    log = []
    stages = _make_stages(specs, log)
    touched = {kind for kind, _v in specs}
    out = impl(stages, state)
    # Fields no stage replaced must keep OBJECT IDENTITY through the loop.
    if "config" not in touched:
        assert out.config is state.config, "untouched config lost object identity"
    if "net_order" not in touched:
        assert out.net_order is state.net_order, "untouched net_order lost object identity"
    if "placements" not in touched:
        assert out.placements is state.placements, "untouched placements lost object identity"


@given(_stage_specs(), _states())
@settings(max_examples=100, deadline=None)
def test_p4_untouched_fields_keep_identity(specs, state):
    _body_p4(_rust_run, specs, state)


def test_p4_fails_for_unconditional_replace_mutant() -> None:
    _assert_mutant_detected(
        _body_p4,
        _loop_unconditional_replace,
        [("placements", "U1")],
        BoardState(config={"k": "v"}, net_order=("N",)),
    )


# ---------------------------------------------------------------------------
# P5 -- prefix composition (the loop is a pure left fold)
# ---------------------------------------------------------------------------


def _body_p5(impl, specs, state) -> None:
    for k in range(len(specs) + 1):
        prefix_log = []
        suffix_log = []
        prefix = _make_stages(specs[:k], prefix_log)
        suffix = _make_stages(specs[k:], suffix_log)
        all_log = []
        all_stages = _make_stages(specs, all_log)

        direct = impl(all_stages, state)
        composed = impl(suffix, impl(prefix, state))
        assert repr(direct) == repr(composed), (
            f"run(all) diverged from run(suffix, run(prefix, state)) at split {k}"
        )


@given(_stage_specs(), _states())
@settings(max_examples=50, deadline=None)
def test_p5_prefix_composition(specs, state):
    _body_p5(_rust_run, specs, state)


def test_p5_fails_for_skip_first_mutant() -> None:
    _assert_mutant_detected(
        _body_p5,
        _loop_skip_first,
        [("config", "a"), ("net_order", "b")],
        BoardState(),
    )


# ---------------------------------------------------------------------------
# P6 -- exception propagation
# ---------------------------------------------------------------------------


def _body_p6(impl, specs, state) -> None:
    log = []
    stages = _make_stages(specs, log)
    pos = next(i for i, (kind, _v) in enumerate(specs) if kind == "raise")
    raised = False
    try:
        impl(stages, state)
    except RuntimeError as exc:
        raised = True
        assert "boom" in str(exc)
    assert raised, "the loop must propagate the stage exception"
    # Stages up to AND INCLUDING the raising stage ran; the rest did not.
    assert log == [s.name for s in stages[: pos + 1]], (
        f"prefix before the raise diverged: {log}"
    )


@given(_raising_specs(), _states())
@settings(max_examples=50, deadline=None)
def test_p6_stage_exception_propagates_and_halts(specs, state):
    _body_p6(_rust_run, specs, state)


def test_p6_fails_for_swallow_mutant() -> None:
    _assert_mutant_detected(
        _body_p6,
        _loop_swallow_exceptions,
        [("config", "a"), ("raise", "boom"), ("config", "b")],
        BoardState(),
    )
