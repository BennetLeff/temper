"""Rust Orchestration Engine plan 2026-08-09-001, the FINAL portable router_v6
orchestration module: behavioural A/B of the stage_ledger cardinality compute
(temper-orchestration ``stage_ledger`` module) against the pinned
pre-migration oracle.

The pre-migration ``router_v6/stage_ledger.py`` is pinned VERBATIM as
``tests/router_v6/_stage_ledger_py_oracle.py`` (content-hash registered in
``scripts/oracle_hashes.json`` AND in this file's body digests). Both arms are
driven with IDENTICAL inputs; every assertion is bit-exact:

- ``temper_orchestration.snapshot_cardinality``   vs oracle ``_snapshot``
  (field-by-field AND ``repr()`` — the Rust ``CardinalitySnapshot.__repr__``
  reproduces the ``_CardinalitySnapshot`` dataclass repr string exactly);
- ``temper_orchestration.diff_cardinality``       vs oracle ``_diff``
  (exact list/tuple equality — the ``(field, before, after)`` order pins the
  fixed field iteration);
- shim ``StageLedger`` (which delegates to the two pyfunctions) vs oracle
  ``StageLedger`` — ``LedgerReport`` fields, ``__str__``, and the
  ``StageLedgerImbalanceError`` raise are compared end-to-end.

Anti-vacuity: ``test_shim_and_oracle_are_different_implementations`` asserts
the shim binds to ``temper_orchestration`` pyfunctions and no longer contains
the ``_snapshot``/``_diff`` compute, and ``test_shim_delegates_snapshot`` /
``test_shim_delegates_diff`` prove the shim's ``checkin``/``checkout`` really
call across the pyo3 boundary (recording stubs).

What stays Python (documented boundary): the ``StageLedger`` state machine,
``LedgerReport`` + ``__str__``, the checkout message rendering (presentation
of the diff list), and ``StageLedgerImbalanceError``. The differential still
pins them bit-exactly because the shim keeps the SAME orchestration the
oracle had — the only divergence under test is the migrated compute feeding
it. See the module header in ``temper-orchestration/src/stage_ledger.rs`` and
VERIFICATION.md for the split argument.
"""

from __future__ import annotations

import hashlib
import textwrap
from pathlib import Path
from types import SimpleNamespace

import pytest
import temper_orchestration as _to
from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.router_v6 import stage_ledger as shim_mod
from temper_placer.router_v6.stage_ledger import (
    LedgerReport,
    StageLedger,
    StageLedgerImbalanceError,
)
from tests.router_v6 import _stage_ledger_py_oracle as _oracle

# ---------------------------------------------------------------------------
# The oracle must stay verbatim
# ---------------------------------------------------------------------------

_ORACLE_PATH = Path(__file__).with_name("_stage_ledger_py_oracle.py")

# Body digests of the two ported kernels, extracted from the oracle file
# (AST ranges, dedented) — pinned here so a body edit in the oracle fails this
# test rather than silently re-pinning the differential.
_BODY_DIGESTS = {
    "_snapshot": "aedafb8a96a0669070b808615bc0a5cd1dd5204aa2c641daf3dfd509046ab30b",
    "_diff": "bf8968becc01762280f58a40b5223cbd248ea6c9573bfb9564fb681bf6a6d330",
}


def _oracle_body_digests(path: Path) -> dict[str, str]:
    import ast

    src = path.read_text(encoding="utf-8")
    lines = src.splitlines(keepends=True)
    out: dict[str, str] = {}
    for node in ast.parse(src).body:
        if isinstance(node, ast.FunctionDef):
            body = "".join(lines[node.lineno - 1 : node.end_lineno])
            out[node.name] = hashlib.sha256(textwrap.dedent(body).encode()).hexdigest()
    return out


def test_oracle_bodies_match_pinned_digests() -> None:
    """The oracle is evidence only while it is unmodified.

    A differential whose oracle can be edited to agree with the port proves
    nothing, so the copied bodies are content-addressed. If this fails,
    either the oracle was edited (revert it) or a pre-migration module's
    source really changed upstream (re-pin deliberately, in its own commit).
    """
    digests = _oracle_body_digests(_ORACLE_PATH)
    for name, want in _BODY_DIGESTS.items():
        assert digests.get(name) == want, (
            f"the pinned oracle body {name} changed; it must stay verbatim "
            "(see scripts/oracle_hashes.json for the registered hash)"
        )


def test_shim_and_oracle_are_different_implementations() -> None:
    """Anti-vacuity: the shim must bind to temper_orchestration pyfunctions,
    not resolve back onto the oracle or keep the compute inline."""
    assert _to.snapshot_cardinality.__module__ == "temper_orchestration.temper_orchestration"
    assert _to.diff_cardinality.__module__ == "temper_orchestration.temper_orchestration"
    assert _to.CardinalitySnapshot.__module__ == "temper_orchestration"
    # The oracle's compute must not have been collapsed onto the shims.
    assert _oracle._snapshot.__module__ != "temper_orchestration.temper_orchestration"
    assert _oracle._diff.__module__ != "temper_orchestration.temper_orchestration"
    # The shim no longer contains the migrated compute inline.
    assert not hasattr(shim_mod, "_snapshot")
    assert not hasattr(shim_mod, "_diff")


def test_shim_delegates_snapshot_to_rust(monkeypatch) -> None:
    """Anti-vacuity: StageLedger.checkin/checkout call snapshot_cardinality."""
    calls: list[object] = []
    real = _to.snapshot_cardinality

    def recording(obj):
        calls.append(obj)
        return real(obj)

    monkeypatch.setattr(_to, "snapshot_cardinality", recording)
    ledger = StageLedger()
    ledger.checkin(_FakeState())
    assert len(calls) == 1
    ledger.checkout("s", _FakeState())
    assert len(calls) == 2


def test_shim_delegates_diff_to_rust(monkeypatch) -> None:
    """Anti-vacuity: StageLedger.checkout calls diff_cardinality on the
    snapshot pair it stored from the Rust snapshots."""
    diff_calls: list[tuple[object, object]] = []
    real_diff = _to.diff_cardinality
    real_snap = _to.snapshot_cardinality

    def recording_diff(pre, post):
        diff_calls.append((pre, post))
        return real_diff(pre, post)

    monkeypatch.setattr(_to, "diff_cardinality", recording_diff)
    monkeypatch.setattr(
        _to,
        "snapshot_cardinality",
        lambda obj: real_snap(obj),
    )
    ledger = StageLedger()
    ledger.checkin(_FakeState())
    ledger.checkout("s", _FakeState())
    assert len(diff_calls) == 1
    pre, post = diff_calls[0]
    assert isinstance(pre, _to.CardinalitySnapshot)
    assert isinstance(post, _to.CardinalitySnapshot)


# ---------------------------------------------------------------------------
# Duck-typed object shapes covering every _snapshot branch
# ---------------------------------------------------------------------------


class _FakePCB:
    nets = [1, 2]
    components = [1, 2, 3]


class _FakeState:
    """BoardState branch: _parsed_pcb + channel_skeletons + _escape_vias."""

    _parsed_pcb = _FakePCB()
    channel_skeletons = {}
    _escape_vias = ()


def _pcb_obj(nets=0, components=0, routing_spaces=None, routing_results=None):
    return SimpleNamespace(
        nets=[object() for _ in range(nets)],
        components=[object() for _ in range(components)],
        routing_spaces=routing_spaces or {},
        routing_results=routing_results,
    )


def _path_obj(segments=None, coordinates=None):
    attrs = {}
    if segments is not None:
        attrs["segments"] = [object() for _ in range(segments)]
    elif coordinates is not None:
        attrs["coordinates"] = [object() for _ in range(coordinates)]
    return SimpleNamespace(**attrs)


def _results_obj(compiled=None):
    return SimpleNamespace(compiled_routes=compiled or {})


def _board_state(nets=0, components=0, channels=0, vias=0):
    pcb = SimpleNamespace(
        nets=[object() for _ in range(nets)],
        components=[object() for _ in range(components)],
    )
    skeletons = {}
    if channels:
        skeletons["s0"] = SimpleNamespace(
            channels=[object() for _ in range(channels)]
        )
    return SimpleNamespace(
        _parsed_pcb=pcb,
        channel_skeletons=skeletons,
        _escape_vias=tuple(object() for _ in range(vias)),
    )


# Every _snapshot branch, as (object, (net, comp, channel, via, segment)):
_SNAPSHOT_CASES = [
    # BoardState branch
    (_FakeState(), (2, 3, 0, 0, 0)),
    (_board_state(nets=5, components=2, channels=4, vias=3), (5, 2, 4, 3, 0)),
    (_board_state(nets=0, components=0, channels=0, vias=0), (0, 0, 0, 0, 0)),
    # BoardState with a falsy _escape_vias (the `or ()` fallback)
    (_board_state(nets=1, vias=0), (1, 0, 0, 0, 0)),
    # BoardState with channels split across skeleton values
    (
        SimpleNamespace(
            _parsed_pcb=_FakePCB(),
            channel_skeletons={
                "a": SimpleNamespace(channels=[object()] * 2),
                "b": SimpleNamespace(channels=[object()] * 3),
            },
            _escape_vias=None,
        ),
        (2, 3, 5, 0, 0),
    ),
    # BoardState whose _parsed_pcb is None
    (
        SimpleNamespace(
            _parsed_pcb=None,
            channel_skeletons={},
            _escape_vias=(),
        ),
        (0, 0, 0, 0, 0),
    ),
    # ParsedPCB branch
    (_pcb_obj(nets=2, components=3), (2, 3, 0, 0, 0)),
    (
        _pcb_obj(
            nets=1,
            components=2,
            routing_spaces={"rs": SimpleNamespace(channels=[object()] * 4)},
        ),
        (1, 2, 4, 0, 0),
    ),
    # routing_spaces present but not a dict -> skipped
    (_pcb_obj(nets=1, routing_spaces=[1, 2, 3]), (1, 0, 0, 0, 0)),
    # routing_spaces value without a `channels` attribute -> not counted
    (
        _pcb_obj(nets=1, routing_spaces={"rs": SimpleNamespace(other=1)}),
        (1, 0, 0, 0, 0),
    ),
    # segment counting over path.segments
    (
        _pcb_obj(
            nets=2,
            routing_results=_results_obj(
                {
                    "n1": SimpleNamespace(path=_path_obj(segments=3)),
                    "n2": SimpleNamespace(path=_path_obj(segments=5)),
                }
            ),
        ),
        (2, 0, 0, 0, 8),
    ),
    # segment counting over path.coordinates (len - 1)
    (
        _pcb_obj(
            nets=1,
            routing_results=_results_obj(
                {"n1": SimpleNamespace(path=_path_obj(coordinates=4))}
            ),
        ),
        (1, 0, 0, 0, 3),
    ),
    # empty coordinates -> max(0, 0 - 1) == 0
    (
        _pcb_obj(
            nets=1,
            routing_results=_results_obj(
                {"n1": SimpleNamespace(path=_path_obj(coordinates=0))}
            ),
        ),
        (1, 0, 0, 0, 0),
    ),
    # route with no path -> skipped
    (
        _pcb_obj(
            nets=1,
            routing_results=_results_obj({"n1": SimpleNamespace(path=None)}),
        ),
        (1, 0, 0, 0, 0),
    ),
    # routing_results with no compiled_routes attribute -> skipped
    (_pcb_obj(nets=1, routing_results=SimpleNamespace(compiled=1)), (1, 0, 0, 0, 0)),
    # bare object with none of the shapes -> all zeros
    (object(), (0, 0, 0, 0, 0)),
]


# ---------------------------------------------------------------------------
# snapshot_cardinality vs _snapshot
# ---------------------------------------------------------------------------


def _snapshot_fields(snap) -> tuple:
    return (
        snap.net_count,
        snap.component_count,
        snap.channel_count,
        snap.via_count,
        snap.segment_count,
    )


def _assert_reports_same(got: LedgerReport, want: LedgerReport, msg: str = "") -> None:
    """Compare the shim's LedgerReport against the oracle's — the two classes
    are distinct (dataclass ``__eq__`` is type-strict), so compare fields."""
    assert got.is_balanced == want.is_balanced, msg
    assert got.stage_name == want.stage_name, msg
    assert got.message == want.message, msg
    assert str(got) == str(want), msg


def test_snapshot_matches_oracle_field_and_repr() -> None:
    for obj, want_counts in _SNAPSHOT_CASES:
        want = _oracle._snapshot(obj)
        got = _to.snapshot_cardinality(obj)
        assert _snapshot_fields(got) == want_counts, f"{obj!r}: expected {want_counts}"
        assert _snapshot_fields(got) == _snapshot_fields(want), f"{obj!r}: field mismatch"
        # Bit-identical repr: the Rust __repr__ reproduces the dataclass string.
        assert repr(got) == repr(want), f"{obj!r}: repr mismatch"


def test_snapshot_errors_propagate_like_hasattr() -> None:
    """hasattr swallows only AttributeError; a __len__ TypeError propagates."""

    class _Weird:
        _parsed_pcb = SimpleNamespace(nets=object())  # nets has no __len__

    with pytest.raises(TypeError):
        _to.snapshot_cardinality(_Weird())
    with pytest.raises(TypeError):
        _oracle._snapshot(_Weird())

    # Same propagation through the routing_spaces channel-counting branch.
    obj = _pcb_obj(nets=1, routing_spaces={"rs": SimpleNamespace(channels=object())})
    with pytest.raises(TypeError):
        _to.snapshot_cardinality(obj)
    with pytest.raises(TypeError):
        _oracle._snapshot(obj)


# ---------------------------------------------------------------------------
# diff_cardinality vs _diff
# ---------------------------------------------------------------------------


def _oracle_snap(n=0, c=0, ch=0, v=0, s=0):
    return _oracle._CardinalitySnapshot(n, c, ch, v, s)


def _rust_snap(n=0, c=0, ch=0, v=0, s=0):
    return _to.CardinalitySnapshot(
        net_count=n, component_count=c, channel_count=ch, via_count=v, segment_count=s
    )


_SNAPSHOT_PAIRS = [
    ((0, 0, 0, 0, 0), (0, 0, 0, 0, 0)),          # balanced
    ((0, 0, 0, 0, 0), (1, 1, 1, 1, 1)),          # all changed
    ((2, 3, 4, 5, 6), (2, 9, 4, 5, 1)),          # mixed
    ((1, 1, 1, 1, 1), (0, 0, 0, 0, 0)),          # every before > after
    ((7, 0, 3, 0, 2), (7, 0, 3, 0, 2)),          # identical non-zero
]


def test_diff_matches_oracle() -> None:
    for pre_counts, post_counts in _SNAPSHOT_PAIRS:
        want = _oracle._diff(_oracle_snap(*pre_counts), _oracle_snap(*post_counts))
        got = _to.diff_cardinality(_rust_snap(*pre_counts), _rust_snap(*post_counts))
        assert got == want
        assert isinstance(got, list)
        for entry in got:
            assert len(entry) == 3
            assert isinstance(entry[0], str)
            assert isinstance(entry[1], int)
            assert isinstance(entry[2], int)


# ---------------------------------------------------------------------------
# End-to-end: shim StageLedger vs oracle StageLedger
# ---------------------------------------------------------------------------

_STATE_PAIRS = [
    (_FakeState(), _FakeState()),
    (_FakeState(), SimpleNamespace(_parsed_pcb=_FakePCB(), channel_skeletons={}, _escape_vias=(1, 2))),
    (_board_state(nets=3, components=1), _board_state(nets=5, components=1, channels=2, vias=1)),
    (_pcb_obj(nets=2, components=1), _pcb_obj(nets=2, components=3)),
    (
        _pcb_obj(nets=1, routing_results=_results_obj({"n1": SimpleNamespace(path=_path_obj(segments=4))})),
        _pcb_obj(nets=1, routing_results=_results_obj({"n1": SimpleNamespace(path=_path_obj(segments=2))})),
    ),
    (object(), object()),
]


def test_checkout_report_matches_oracle() -> None:
    for before, after in _STATE_PAIRS:
        got = StageLedger(fail_on_imbalance=False).verify("stageX", before, after)
        want = _oracle.StageLedger(fail_on_imbalance=False).verify("stageX", before, after)
        _assert_reports_same(got, want, f"{before!r} -> {after!r}")
        assert str(got) == str(want)


def test_fail_on_imbalance_raises_identically() -> None:
    state_a = _FakeState()
    state_b = _FakeState()
    state_b._escape_vias = (1, 2)
    with pytest.raises(StageLedgerImbalanceError) as got_exc:
        StageLedger(fail_on_imbalance=True).verify("stage1", state_a, state_b)
    with pytest.raises(_oracle.StageLedgerImbalanceError) as want_exc:
        _oracle.StageLedger(fail_on_imbalance=True).verify("stage1", state_a, state_b)
    assert str(got_exc.value) == str(want_exc.value)
    assert "via_count" in str(got_exc.value)


def test_fail_on_imbalance_false_does_not_raise() -> None:
    state_a = _FakeState()
    state_b = _FakeState()
    state_b._escape_vias = (1, 2)
    got = StageLedger(fail_on_imbalance=False).verify("stage1", state_a, state_b)
    want = _oracle.StageLedger(fail_on_imbalance=False).verify("stage1", state_a, state_b)
    _assert_reports_same(got, want)
    assert got.is_balanced is False


def test_missing_pre_snapshot_matches_oracle() -> None:
    got = StageLedger(fail_on_imbalance=False).checkout("orphan", _FakeState())
    want = _oracle.StageLedger(fail_on_imbalance=False).checkout("orphan", _FakeState())
    _assert_reports_same(got, want)
    assert got.is_balanced is False
    assert "missing pre-snapshot" in got.message.lower()


def test_checkin_checkout_flow_matches_oracle() -> None:
    got = StageLedger(fail_on_imbalance=False)
    want = _oracle.StageLedger(fail_on_imbalance=False)
    got.checkin(_FakeState())
    want.checkin(_FakeState())
    got_report = got.checkout("mystage", _FakeState())
    want_report = want.checkout("mystage", _FakeState())
    _assert_reports_same(got_report, want_report)
    assert got_report.is_balanced is True


# ---------------------------------------------------------------------------
# PBT (Hypothesis): differential + invariants over random count vectors
# ---------------------------------------------------------------------------

# A five-field count vector in the oracle's field order
# (net, component, channel, via, segment).
_counts = st.tuples(*([st.integers(min_value=0, max_value=40)] * 5))

_FIELD_NAMES = ["net_count", "component_count", "channel_count", "via_count", "segment_count"]


def _rust_snap_from(t: tuple) -> _to.CardinalitySnapshot:
    return _to.CardinalitySnapshot(
        net_count=t[0], component_count=t[1], channel_count=t[2], via_count=t[3], segment_count=t[4]
    )


def _oracle_snap_from(t: tuple):
    return _oracle._CardinalitySnapshot(t[0], t[1], t[2], t[3], t[4])


@settings(deadline=None)
@given(pre=_counts, post=_counts)
def test_pbt_diff_matches_oracle(pre, post):
    """Differential: the Rust diff is list-identical to the oracle's over
    arbitrary random count vectors."""
    want = _oracle._diff(_oracle_snap_from(pre), _oracle_snap_from(post))
    got = _to.diff_cardinality(_rust_snap_from(pre), _rust_snap_from(post))
    assert got == want


@settings(deadline=None)
@given(counts=_counts)
def test_pbt_diff_self_is_balanced(counts):
    """A snapshot never differs from itself."""
    snap = _rust_snap_from(counts)
    assert _to.diff_cardinality(snap, snap) == []


@settings(deadline=None)
@given(pre=_counts, post=_counts)
def test_pbt_diff_reports_exactly_the_changed_fields(pre, post):
    """The diff names every changed field with the true before/after values,
    and names nothing else."""
    got = _to.diff_cardinality(_rust_snap_from(pre), _rust_snap_from(post))
    changed = [i for i in range(5) if pre[i] != post[i]]
    assert got == [(_FIELD_NAMES[i], pre[i], post[i]) for i in changed]


@settings(deadline=None)
@given(counts=_counts)
def test_pbt_identical_board_state_is_balanced(counts):
    """verify(before, after) with two objects that snapshot identically is
    balanced — every count included."""
    before = _board_state(nets=counts[0], components=counts[1], channels=counts[2], vias=counts[3])
    after = _board_state(nets=counts[0], components=counts[1], channels=counts[2], vias=counts[3])
    got = StageLedger(fail_on_imbalance=False).verify("s", before, after)
    assert got.is_balanced is True


@settings(deadline=None)
@given(pre=_counts, post=_counts)
def test_pbt_report_matches_oracle_board_state(pre, post):
    """Differential through the full StageLedger: shim and oracle produce the
    same report for arbitrary BoardState-shape inputs (net/component/channel/
    via counts; segment stays 0 in this branch — covered separately below)."""
    before = _board_state(nets=pre[0], components=pre[1], channels=pre[2], vias=pre[3])
    after = _board_state(nets=post[0], components=post[1], channels=post[2], vias=post[3])
    got = StageLedger(fail_on_imbalance=False).verify("s", before, after)
    want = _oracle.StageLedger(fail_on_imbalance=False).verify("s", before, after)
    _assert_reports_same(got, want)
    assert got.message == want.message


@settings(deadline=None)
@given(pre=_counts, post=_counts)
def test_pbt_report_matches_oracle_segments(pre, post):
    """Differential through the full StageLedger over the ParsedPCB shape with
    segment-counting routing results (via stays 0 in this branch)."""
    before = _pcb_obj(
        nets=pre[0],
        components=pre[1],
        routing_spaces={"rs": SimpleNamespace(channels=[object()] * pre[2])}
        if pre[2]
        else {},
        routing_results=_results_obj({"n1": SimpleNamespace(path=_path_obj(segments=pre[4]))})
        if pre[4]
        else None,
    )
    after = _pcb_obj(
        nets=post[0],
        components=post[1],
        routing_spaces={"rs": SimpleNamespace(channels=[object()] * post[2])}
        if post[2]
        else {},
        routing_results=_results_obj({"n1": SimpleNamespace(path=_path_obj(segments=post[4]))})
        if post[4]
        else None,
    )
    got = StageLedger(fail_on_imbalance=False).verify("s", before, after)
    want = _oracle.StageLedger(fail_on_imbalance=False).verify("s", before, after)
    _assert_reports_same(got, want)
    assert got.message == want.message


@settings(deadline=None)
@given(pre=_counts, post=_counts)
def test_pbt_message_renders_every_diff_line_in_order(pre, post):
    """Metamorphic-style exhaustiveness: the imbalance message contains
    exactly the changed fields as `field: before -> after` lines, in the fixed
    field order (this pins the shim's presentation over the Rust diff)."""
    before = _board_state(nets=pre[0], components=pre[1], channels=pre[2], vias=pre[3])
    after = _board_state(nets=post[0], components=post[1], channels=post[2], vias=post[3])
    report = StageLedger(fail_on_imbalance=False).verify("s", before, after)
    changed = [i for i in range(4) if pre[i] != post[i]]
    if not changed:
        assert report.is_balanced is True
        assert report.message == "All tracked objects balanced across stage."
        return
    assert report.is_balanced is False
    for i in changed:
        line = f"  {_FIELD_NAMES[i]}: {pre[i]} -> {post[i]}"
        assert line in report.message
    # No line names an unchanged field.
    for i in range(4):
        if i not in changed:
            assert f"  {_FIELD_NAMES[i]}:" not in report.message


@settings(deadline=None)
@given(pre=_counts, post=_counts, k=st.integers(min_value=0, max_value=10))
def test_pbt_common_shift_preserves_diff(pre, post, k):
    """Metamorphic: adding the same constant to every count of both snapshots
    preserves the changed-field set and each field's delta (the diff reports
    ABSOLUTE before/after counts, so a common shift changes the reported
    values but not which fields changed nor by how much)."""
    shifted_pre = tuple(v + k for v in pre)
    shifted_post = tuple(v + k for v in post)
    base = _to.diff_cardinality(_rust_snap_from(pre), _rust_snap_from(post))
    shifted = _to.diff_cardinality(_rust_snap_from(shifted_pre), _rust_snap_from(shifted_post))
    assert [f for f, _, _ in shifted] == [f for f, _, _ in base]
    assert [(a - b) for _, b, a in shifted] == [(a - b) for _, b, a in base]


# ---------------------------------------------------------------------------
# Metamorphic relations (deterministic samples)
# ---------------------------------------------------------------------------


def test_meta_swap_flips_before_after() -> None:
    """Swapping the two arms flips every (before, after) pair."""
    for pre, post in _SNAPSHOT_PAIRS:
        forward = _to.diff_cardinality(_rust_snap_from(pre), _rust_snap_from(post))
        backward = _to.diff_cardinality(_rust_snap_from(post), _rust_snap_from(pre))
        assert len(forward) == len(backward)
        for (f_a, b_a, a_a), (f_b, b_b, a_b) in zip(forward, backward):
            assert (f_a, b_a, a_a) == (f_b, a_b, b_b)


def test_meta_common_shift_preserves_diff() -> None:
    """A common shift preserves which fields changed and each field's delta
    (the diff reports absolute before/after counts, so the values shift)."""
    for pre, post in _SNAPSHOT_PAIRS:
        base = _to.diff_cardinality(_rust_snap_from(pre), _rust_snap_from(post))
        shifted = _to.diff_cardinality(
            _rust_snap_from(tuple(v + 3 for v in pre)),
            _rust_snap_from(tuple(v + 3 for v in post)),
        )
        assert [f for f, _, _ in shifted] == [f for f, _, _ in base]
        assert [(a - b) for _, b, a in shifted] == [(a - b) for _, b, a in base]


def test_meta_balance_is_transitive() -> None:
    """If a==b and b==c, then a==c (balance is an equivalence)."""
    a = (1, 2, 3, 4, 5)
    b = (1, 2, 3, 4, 5)
    c = (1, 2, 3, 4, 5)
    assert _to.diff_cardinality(_rust_snap_from(a), _rust_snap_from(b)) == []
    assert _to.diff_cardinality(_rust_snap_from(b), _rust_snap_from(c)) == []
    assert _to.diff_cardinality(_rust_snap_from(a), _rust_snap_from(c)) == []
    # And a change anywhere breaks the chain.
    d = (9, 2, 3, 4, 5)
    assert _to.diff_cardinality(_rust_snap_from(a), _rust_snap_from(d)) != []


def test_meta_verify_is_idempotent_across_calls() -> None:
    """Re-verifying the same pair on a fresh ledger yields the same report."""
    before = _board_state(nets=3, components=1, channels=2, vias=1)
    after = _board_state(nets=5, components=1, channels=2, vias=1)
    r1 = StageLedger().verify("s", before, after)
    r2 = StageLedger().verify("s", before, after)
    assert r1 == r2
    assert r1.is_balanced is False
    assert "net_count: 3 -> 5" in r1.message


def test_meta_snapshot_is_a_function_of_the_object_only() -> None:
    """The same object always snapshots to the same counts (no hidden state)."""
    for obj, want_counts in _SNAPSHOT_CASES:
        for _ in range(3):
            got = _to.snapshot_cardinality(obj)
            assert _snapshot_fields(got) == want_counts
            assert repr(got) == repr(_to.snapshot_cardinality(obj))
