"""R1a: behavioural differential of the deterministic pipeline LOOP + FACTORY
against the pinned pre-migration oracle.

Rust Orchestration Engine plan 2026-08-09-001, orchestration-port unit U-E:
the sequencing of ``DeterministicPipeline.run()`` (the per-stage
``state = stage.run(state)`` loop, including the per-stage fence invocation)
and the ``create_drc_aware_pipeline()`` stage factory (the D1->D7 ordered
construction, the zone-aware / phased stage selection and the sidecar
injection) move to ``temper-orchestration``'s ``DeterministicPipeline``
pyclass, which drives the stages through the Rust ``PipelineRunner<BoardState>``.
The pre-migration ``deterministic/__init__.py`` is pinned VERBATIM as the
oracle (``tests/deterministic/_deterministic_pipeline_py_oracle.py``,
content-hash-pinned below).

What this suite pins is the LOOP and the ORDER: both arms run the SAME stage
objects (the per-stage compute is pinned individually by the D1..D7
differentials), so the only divergence surface is (a) the stage list
construction (factory) and (b) the state threading through the loop. The
tests compare:

- the factory's stage ORDER (names) for every stage-selection axis
  (zone_aware on/off, phased config present/absent) — byte-identical;
- per-stage state THREADING through the run loop: a prefix run through the
  oracle's pure-Python loop vs. the Rust ``PipelineRunner`` loop must leave
  every ``BoardState`` field byte-identical, with untouched fields keeping
  OBJECT IDENTITY (the loop must not copy what no stage replaced);
- the full real D1->D7 pipeline end-to-end on a minimal board (both arms run
  the same real stages; the final state must be identical field-by-field);
- the fence path: with a recording fence, both loops must issue the identical
  ``fence.check`` call sequence (stage_name / invariants / placement /
  constraints / modified_regions / previous_violations; wall-clock timing is
  nondeterministic by design and compared only for presence);
- error propagation: a stage raising mid-loop halts both loops with the same
  exception.

Anti-vacuity: ``test_oracle_and_port_are_different_implementations`` asserts
the shim delegates to the Rust pyclass (``__module__`` + bytecode), not back
onto the oracle. The oracle body digests below are pinned: a differential
whose oracle can be edited to agree with the port proves nothing.
"""

from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path

import pytest
import temper_orchestration as _to
from tests._legacy_oracle_modules import install as _install_legacy_oracle_modules

_install_legacy_oracle_modules()

import tests.deterministic._deterministic_pipeline_py_oracle as _orc

from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.deterministic import (
    DeterministicPipeline,
)
from temper_placer.deterministic import (
    create_drc_aware_pipeline as _shim_create_drc_aware_pipeline,
)
from temper_placer.deterministic.state import BoardState
from temper_placer.io.kicad_metadata import KiCadMetadata

# ---------------------------------------------------------------------------
# Oracle body pinning (G1)
# ---------------------------------------------------------------------------

_PINNED = {
    "_deterministic_pipeline_py_oracle.py": "e9eeea3bda864fd37e67dcb91d26949a6339558b446a850c84c980c4d6e1f12a",
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
    """Anti-vacuity: the shim must delegate to the Rust pyclass."""
    # The pyclass that implements the loop + factory lives in the Rust crate.
    assert _to.DeterministicPipeline.__module__ == "temper_orchestration"
    # The shim factory's bytecode calls the Rust factory staticmethod by name.
    assert (
        "create_drc_aware_pipeline_stages"
        in _shim_create_drc_aware_pipeline.__code__.co_names
    )
    # The oracle's factory does NOT reference the Rust factory.
    assert (
        "create_drc_aware_pipeline_stages"
        not in _orc.create_drc_aware_pipeline.__code__.co_names
    )
    # The shim run loop is a different implementation from the oracle's
    # (different bytecode), and delegates through the temper_orchestration
    # module's pyclass (the run method's `_to` global is the Rust crate).
    assert DeterministicPipeline.run.__code__.co_code != _orc.DeterministicPipeline.run.__code__.co_code
    assert DeterministicPipeline.run.__globals__["_to"] is _to
    # The oracle keeps the pure-Python loop (time.time fence timing etc.).
    assert "time" in _orc.DeterministicPipeline.run.__code__.co_names


# ---------------------------------------------------------------------------
# Corpus helpers
# ---------------------------------------------------------------------------

_ORDER_DEFAULT = [
    "config_attach",
    "net_class_setup",
    "zone_geometry",
    "zone_assignment",
    "hv_lv_partition",
    "zone_aware_slot_generation",
    "component_assignment",
    "apply_placements",
    "courtyard_check",
    "apply_placements",
    "placement_validation",
    "drc_oracle_setup",
    "clearance_grid",
    "net_ordering",
    "layer_assignment",
    "power_plane",
    "fine_pitch_escape",
    "track_deduplication",
    "short_circuit_detection",
    "via_deduplication",
    "via_validation",
    "drc_validation",
    "connectivity_validation",
]


def _metadata() -> KiCadMetadata:
    return KiCadMetadata(
        courtyards={},
        pad_sizes={},
        board_width=100.0,
        board_height=80.0,
    )


def _stage_names(pipeline) -> list[str]:
    return [s.name for s in pipeline.stages]


def _minimal_state() -> BoardState:
    board = Board(width=100.0, height=80.0, zones=[])
    pin = Pin(
        "1", "1", (2.0, 0.0), net="GND", width=1.0, height=1.0,
        shape="circle", layer="F.Cu",
    )
    comp = Component(
        ref="U1", footprint="FP", bounds=(5.0, 5.0), pins=[pin],
        initial_position=(10.0, 10.0),
    )
    netlist = Netlist(
        components=[comp],
        nets=[Net(name="GND", pins=[("U1", "1")])],
    )
    return BoardState(board=board, netlist=netlist)


def _assert_state_fields_equal(a: BoardState, b: BoardState) -> None:
    """Field-by-field equality (dataclass `==` plus explicit field set so a
    field added to BoardState later is not silently skipped).

    The comparison is by ``repr``, not ``==``: some fields (the DRCOracle in
    particular) hold numpy-array members whose ``==`` raises
    ``ValueError: truth value of an array is ambiguous``, while ``repr`` is
    deterministic and total (the U4 differential's convention).
    """
    assert type(a) is type(b)
    fields = [f.name for f in a.__dataclass_fields__.values()]
    for name in fields:
        va, vb = getattr(a, name), getattr(b, name)
        assert repr(va) == repr(vb), (
            f"field {name!r} diverged:\n  oracle={va!r}\n  shim ={vb!r}"
        )


# ---------------------------------------------------------------------------
# Factory: stage ORDER (G2 — the ORDER is the migrated surface)
# ---------------------------------------------------------------------------

def test_stage_order_matches_oracle_default() -> None:
    orc = _orc.create_drc_aware_pipeline(metadata=_metadata())
    shim = _shim_create_drc_aware_pipeline(metadata=_metadata())
    assert _stage_names(shim) == _stage_names(orc)
    assert _stage_names(shim) == _ORDER_DEFAULT


def test_stage_order_matches_oracle_no_zone_aware() -> None:
    orc = _orc.create_drc_aware_pipeline(metadata=_metadata(), zone_aware=False)
    shim = _shim_create_drc_aware_pipeline(metadata=_metadata(), zone_aware=False)
    assert _stage_names(shim) == _stage_names(orc)
    assert "zone_aware_slot_generation" not in _stage_names(shim)
    assert "slot_generation" in _stage_names(shim)
    # everything except the slot stage is identical to the default order
    assert _stage_names(shim) == [s.replace("zone_aware_slot_generation", "slot_generation") for s in _ORDER_DEFAULT]


def test_stage_order_matches_oracle_with_phased_config() -> None:
    from temper_placer._constraint_types.config import PlacementConstraints

    config = PlacementConstraints(placement_priority={"GND": 0})
    orc = _orc.create_drc_aware_pipeline(
        metadata=_metadata(), config=config, zone_aware=False
    )
    shim = _shim_create_drc_aware_pipeline(
        metadata=_metadata(), config=config, zone_aware=False
    )
    assert _stage_names(shim) == _stage_names(orc)
    assert "phased_component_assignment" in _stage_names(shim)
    assert "component_assignment" not in _stage_names(shim)


def test_factory_type_error_without_metadata() -> None:
    with pytest.raises(TypeError, match="metadata"):
        _shim_create_drc_aware_pipeline()
    with pytest.raises(TypeError, match="metadata"):
        _orc.create_drc_aware_pipeline()


def test_factory_sidecar_injection_matches_oracle(tmp_path) -> None:
    """A grid-carrying channel_map is injected into the phased component
    stage on both arms (R4c); the injection decision is part of the factory."""
    import json

    payload = {
        "temper_schema_hash": "temper.channels.v1",
        "cell_size_um": 1000.0,
        "grid": [[0.0, 0.0, 0.0], [0.0, 0.5, 0.0], [0.0, 0.0, 0.0]],
        "bottlenecks": [],
    }
    sidecar = tmp_path / "placement.channels.json"
    sidecar.write_text(json.dumps(payload))
    cmap = _to_channel_map(sidecar)
    assert cmap.has_grid()

    from temper_placer._constraint_types.config import PlacementConstraints

    config = PlacementConstraints(placement_priority={"GND": 0})

    orc = _orc.create_drc_aware_pipeline(
        metadata=_metadata(), config=config, output_dir=tmp_path,
    )
    shim = _shim_create_drc_aware_pipeline(
        metadata=_metadata(), config=config, output_dir=tmp_path,
    )
    assert _stage_names(shim) == _stage_names(orc)
    assert orc.channel_map is not None and shim.channel_map is not None
    # both arms injected the map onto the phased stage
    from temper_placer.deterministic.stages.phased_component_assignment import (
        PhasedComponentAssignmentStage,
    )

    for pipe, label in ((orc, "oracle"), (shim, "shim")):
        phased = [s for s in pipe.stages if isinstance(s, PhasedComponentAssignmentStage)]
        assert len(phased) == 1, f"{label}: expected one phased stage"
        assert phased[0].channel_map is not None, f"{label}: sidecar not injected"
        assert phased[0].channel_map.has_grid()


def _to_channel_map(sidecar_path: Path):
    from temper_placer.deterministic import ChannelMap

    return ChannelMap.load_from_sidecar(sidecar_path)


# ---------------------------------------------------------------------------
# Run loop: state threading (G2 — the SEQUENCING is the migrated surface)
# ---------------------------------------------------------------------------

class _FakeStage:
    """Deterministic fake stage: a named transform on the frozen BoardState.

    Mirrors the real stages' surface (`name`, `run`, `invariants`,
    `last_modified_regions`) with fully deterministic bodies so the LOOP can
    be pinned without any per-stage compute noise.
    """

    def __init__(self, name, mutate=None, invariants=(), modified_regions=None):
        self._name = name
        self._mutate = mutate
        self.invariants = list(invariants)
        self.last_modified_regions = modified_regions
        self.calls = 0

    @property
    def name(self) -> str:
        return self._name

    def run(self, state: BoardState) -> BoardState:
        self.calls += 1
        if self._mutate is None:
            return state
        return self._mutate(state)


def _set(field: str, value):
    def mutate(state: BoardState) -> BoardState:
        return replace(state, **{field: value})
    return mutate


def _fake_pipeline(stages, fence=None) -> DeterministicPipeline:
    return DeterministicPipeline(stages=stages, fence=fence)


def test_run_threads_state_in_stage_order() -> None:
    """The loop calls stages in declaration order and threads the state."""

    def _stages():
        return [
            _FakeStage("a", _set("config", {"tag": "a"})),
            _FakeStage("b", _set("net_order", ("N1", "N2"))),
            _FakeStage("c"),  # identity
        ]

    initial = BoardState()

    stages_orc = _stages()
    out_orc = _orc.DeterministicPipeline(stages=stages_orc).run(initial)
    stages_shim = _stages()
    out_shim = _fake_pipeline(stages_shim).run(initial)

    _assert_state_fields_equal(out_orc, out_shim)
    assert out_orc.config == {"tag": "a"}
    assert out_orc.net_order == ("N1", "N2")
    # every stage ran exactly once on each arm
    assert [s.calls for s in stages_orc] == [1, 1, 1]
    assert [s.calls for s in stages_shim] == [1, 1, 1]


def test_run_preserves_untouched_field_identity() -> None:
    """Fields no stage replaced keep OBJECT IDENTITY through the Rust loop
    (the threading must not copy what no stage replaced)."""
    stage = _FakeStage("touch_net_order", _set("net_order", ("X",)))
    initial = BoardState(config={"k": "v"}, placements=frozenset({("U1", (1.0, 2.0))}))

    out_shim = _fake_pipeline([stage]).run(initial)
    assert out_shim.config is initial.config
    assert out_shim.placements is initial.placements
    assert out_shim.net_order == ("X",)

    out_orc = _orc.DeterministicPipeline(stages=[stage]).run(initial)
    assert out_orc.config is initial.config
    assert out_orc.net_order == ("X",)


def test_per_stage_prefix_threading_matches_oracle() -> None:
    """After EVERY prefix of the stage list, the accumulated state is
    byte-identical between the two loops (per-stage state threading)."""
    stages = [
        _FakeStage("s1", _set("config", {"n": 1})),
        _FakeStage("s2", _set("net_order", ("A", "B"))),
        _FakeStage("s3", _set("placements", frozenset({("U1", (5.0, 5.0))}))),
        # O-C3/U1 typed `used_slots` as an owned `HashSet<SlotId>`, so the
        # opaque `"slot0"` sentinel this stage used to thread is no longer a
        # legal value for the field. A real `(x, y)` slot keeps the test's
        # actual subject -- per-stage state threading -- unchanged.
        _FakeStage("s4", _set("used_slots", frozenset({(0.0, 0.0)}))),
        _FakeStage("s5", _set("drc_violations", ())),
    ]
    initial = BoardState()
    for k in range(len(stages) + 1):
        prefix = stages[:k]
        out_orc = _orc.DeterministicPipeline(stages=prefix).run(initial)
        out_shim = _fake_pipeline(prefix).run(initial)
        _assert_state_fields_equal(out_orc, out_shim)


def test_run_default_initial_state() -> None:
    """`run()` with no initial state constructs a fresh BoardState on both
    arms (the `initial_state or BoardState()` fallback)."""
    stage = _FakeStage("s", _set("config", {"fresh": True}))
    out_orc = _orc.DeterministicPipeline(stages=[stage]).run()
    out_shim = _fake_pipeline([stage]).run()
    _assert_state_fields_equal(out_orc, out_shim)
    assert out_orc.config == {"fresh": True}
    assert out_shim.config == {"fresh": True}


def test_empty_stage_list_returns_state_unchanged() -> None:
    initial = BoardState(config={"x": 1})
    out_orc = _orc.DeterministicPipeline(stages=[]).run(initial)
    out_shim = _fake_pipeline([]).run(initial)
    _assert_state_fields_equal(out_orc, out_shim)
    assert out_shim is initial  # no stages -> the exact same object


def test_run_propagates_stage_exception_identically() -> None:
    """A raising stage halts both loops and propagates the SAME exception."""

    class _Boom(Exception):
        pass

    def _raise(state):
        raise _Boom("stage blew up")

    stages = [_FakeStage("ok", _set("config", {"a": 1})), _FakeStage("boom", _raise)]

    with pytest.raises(_Boom, match="stage blew up"):
        _orc.DeterministicPipeline(stages=stages).run(BoardState())
    with pytest.raises(_Boom, match="stage blew up"):
        _fake_pipeline(stages).run(BoardState())


def test_run_propagates_after_successful_stages() -> None:
    """Stages before the raising stage still ran (their effects are not
    rolled back) on both arms."""
    seen: list[str] = []

    def _mark(tag):
        def mutate(state):
            seen.append(tag)
            return state
        return mutate

    def _mark_and_set(tag):
        def mutate(state):
            seen.append(tag)
            return replace(state, net_order=("N",))
        return mutate

    class _Boom(Exception):
        pass

    def _raise(state):
        seen.append("boom")
        raise _Boom("x")

    stages = [
        _FakeStage("a", _mark("a")),
        _FakeStage("b", _mark_and_set("b")),
        _FakeStage("c", _raise),
    ]
    with pytest.raises(_Boom):
        _orc.DeterministicPipeline(stages=stages).run(BoardState())
    assert seen == ["a", "b", "boom"]
    seen.clear()
    with pytest.raises(_Boom):
        _fake_pipeline(stages).run(BoardState())
    assert seen == ["a", "b", "boom"]


# ---------------------------------------------------------------------------
# Run loop: the fence path (the oracle's `if self.fence and stage.invariants`)
# ---------------------------------------------------------------------------

class _RecordingFence:
    """Records every `check` call (minus wall-clock timing)."""

    def __init__(self):
        self.calls: list[dict] = []

    def check(self, **kwargs):
        record = dict(kwargs)
        record.pop("stage_wall_time_ms", None)
        self.calls.append(record)
        return _FenceResult()

    @property
    def timed(self) -> list[float]:
        return []  # placeholder; timing compared separately below


class _FenceResult:
    def __init__(self):
        self.violations = []


class _Issue:
    def __init__(self, code, message, affected_items):
        self.code = code
        self.message = message
        self.affected_items = affected_items


def test_fence_path_issues_identical_check_sequence() -> None:
    """With a fence and invariant-bearing stages, both loops invoke
    fence.check with the identical (stage_name, invariants, placement,
    constraints, modified_regions, previous_violations) sequence. Wall-clock
    timing is nondeterministic by design (preserved, not pinned)."""
    inv = [object()]  # truthy non-empty invariants
    regions = [(0.0, 0.0, 1.0, 1.0)]
    stages = [
        _FakeStage("inv1", _set("config", {"f": 1}), invariants=inv, modified_regions=regions),
        _FakeStage("inv2", _set("net_order", ("F",)), invariants=inv, modified_regions=None),
        _FakeStage("plain", _set("placements", frozenset())),  # no invariants
    ]
    initial = BoardState()

    fence_orc = _RecordingFence()
    _orc.DeterministicPipeline(stages=stages, fence=fence_orc).run(initial)
    fence_shim = _RecordingFence()
    _fake_pipeline(stages, fence=fence_shim).run(initial)

    def _normalize(record):
        return {
            "stage_name": record["stage_name"],
            "invariants_len": len(record["invariants"]),
            "placement_components": len(record["placement"].components),
            "constraints_clearances": len(record["constraints"].clearances),
            "modified_regions": record["modified_regions"],
            "previous_violations": record["previous_violations"],
        }

    assert len(fence_shim.calls) == len(fence_orc.calls) == 2
    assert [_normalize(c) for c in fence_shim.calls] == [
        _normalize(c) for c in fence_orc.calls
    ]
    # previous_violations threads from the first check into the second
    assert fence_shim.calls[1]["previous_violations"] == fence_orc.calls[1]["previous_violations"]


def test_fence_previous_violations_threading() -> None:
    """The second fence check receives the fingerprint of the first check's
    violations (the frozenset threading), identically on both arms."""
    from temper_placer.validation.drc_fence import _issue_fingerprint

    class _FenceWithViolations:
        def __init__(self):
            self.calls = []
            self.issue = _Issue("c1", "msg", ["U1"])

        def check(self, **kwargs):
            record = dict(kwargs)
            record.pop("stage_wall_time_ms", None)
            self.calls.append(record)
            return type("R", (), {"violations": [type("V", (), {"issue": self.issue})()]})()

    stages = [
        _FakeStage("a", _set("config", {}), invariants=[object()]),
        _FakeStage("b", _set("net_order", ()), invariants=[object()]),
    ]
    initial = BoardState()

    f_orc = _FenceWithViolations()
    _orc.DeterministicPipeline(stages=stages, fence=f_orc).run(initial)
    f_shim = _FenceWithViolations()
    _fake_pipeline(stages, fence=f_shim).run(initial)

    expected_first = frozenset([_issue_fingerprint(f_orc.issue)])
    assert f_orc.calls[0]["previous_violations"] is None
    assert f_shim.calls[0]["previous_violations"] is None
    assert f_orc.calls[1]["previous_violations"] == expected_first
    assert f_shim.calls[1]["previous_violations"] == expected_first


# ---------------------------------------------------------------------------
# End-to-end: the real D1->D7 stages through both loops (G2)
# ---------------------------------------------------------------------------

def test_real_pipeline_end_to_end_matches_oracle() -> None:
    """The full real factory stage list run through the Rust loop produces a
    final state byte-identical to the oracle's Python loop on a minimal
    board (the stages themselves are the shared shims; this pins the loop's
    state threading through all 23 stages)."""
    initial = _minimal_state()
    stages_orc = _orc.create_drc_aware_pipeline(metadata=_metadata()).stages
    stages_shim = _shim_create_drc_aware_pipeline(metadata=_metadata()).stages
    assert [s.name for s in stages_shim] == [s.name for s in stages_orc]

    out_orc = _orc.DeterministicPipeline(stages=stages_orc).run(initial)
    out_shim = _shim_create_drc_aware_pipeline(metadata=_metadata()).run(initial)

    _assert_state_fields_equal(out_orc, out_shim)
    assert len(out_shim.placements) > 0
    assert out_shim.grid is not None
