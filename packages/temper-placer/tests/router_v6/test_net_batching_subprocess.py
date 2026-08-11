"""Tests for the subprocess-per-batch boundary added to ``net_batching.py``.

Follow-up to the `#871` net-batching prototype
(``docs/evidence/2026-08-07-net-batching-prototype.md``), which ran every
batch in-process and died on a Rust allocator ``abort()`` mid-run, losing
every already-completed batch's results with it (uncatchable from Python).
The fix is subprocess-per-batch; these tests cover the two things that fix
has to get right and that a change here could silently break:

1. **Crash vs. clean, unambiguously.** A child that dies without sending a
   result must be reported as ``crashed=True`` -- never conflated with a
   clean ``"unsat"``/``"unknown"`` result -- and a child that *does* send a
   result must never be reported as crashed regardless of its own exit
   path afterwards. Tested directly against
   :func:`temper_placer.router_v6.net_batching._run_target_in_subprocess`
   with trivial stand-in targets, independent of the SAT solver.
2. **Capacity state survives the process boundary.** ``channel_widths``
   crosses into every child by being pickled as a ``multiprocessing``
   ``Process`` arg (spawn context). A batching scheme that silently lost
   or corrupted that state on the round trip would over-subscribe a
   channel edge and produce a short -- tested here with a literal
   ``pickle.dumps``/``pickle.loads`` round trip (the same mechanism
   ``multiprocessing`` spawn uses to hand ``Process`` args to the child),
   not merely asserted by inspection.
"""

from __future__ import annotations

import pickle
import signal
import time
from pathlib import Path

import pytest

from temper_placer.router_v6.channel_skeleton import ChannelSkeleton, SkeletonGraph
from temper_placer.router_v6.channel_widths import ChannelWidths
from temper_placer.router_v6.net_batching import (
    _consume_capacity,
    _DesignRulesStub,
    _project_skeletons,
    _run_target_in_subprocess,
    _shrink_channel_widths,
    _write_shared_context,
)
from temper_placer.router_v6.stage0_data import NetClassRules
from temper_placer.router_v6.topology_extraction import NetTopology

# ---------------------------------------------------------------------------
# Trivial subprocess targets for crash-detection tests. Module-level (not
# closures/lambdas) because `multiprocessing`'s "spawn" context pickles the
# target by qualified reference to hand it to the fresh interpreter -- the
# same constraint `_batch_worker_entry` itself is under in production.
# ---------------------------------------------------------------------------


def _ok_worker(conn, payload):
    conn.send({"echo": payload})
    conn.close()


def _abort_worker(conn, _payload):
    # Simulates the uncatchable Rust allocator abort() from the first
    # prototype run: SIGABRT terminates the process before anything is
    # (or even could be) sent back to the parent.
    import os

    os.kill(os.getpid(), signal.SIGABRT)


def _hang_worker(conn, sleep_s):
    # Never sends; simulates a child that is alive but stuck (or slower
    # than the caller's budget) -- must be detected as "crashed" (no
    # result) via the poll timeout, not hang the caller forever.
    time.sleep(sleep_s)


def _memory_error_worker(conn, _payload):
    # Simulates a *catchable* Python-level OOM, as opposed to the Rust
    # abort() case: the child catches it and still sends a clean result,
    # exactly like _batch_worker_entry's own `except MemoryError` branch.
    try:
        raise MemoryError("simulated")
    except MemoryError:
        conn.send({"status": "memory_error"})
    conn.close()


class TestCrashVsCleanDetection:
    def test_clean_result_is_not_crashed(self):
        outcome = _run_target_in_subprocess(_ok_worker, ("hello",), timeout_s=30)
        assert outcome.crashed is False
        assert outcome.got_result is True
        assert outcome.result == {"echo": "hello"}
        assert outcome.exitcode == 0

    def test_sigabrt_is_reported_as_crashed_not_unsat(self):
        outcome = _run_target_in_subprocess(_abort_worker, (None,), timeout_s=30)
        assert outcome.crashed is True
        assert outcome.got_result is False
        assert outcome.result is None
        # Negative exitcode == -SIGABRT on POSIX -- the parent can tell a
        # signal death apart from a normal nonzero exit.
        assert outcome.exitcode is not None
        assert outcome.exitcode < 0
        assert "SIGABRT" in (outcome.crash_reason or "")

    def test_hang_past_timeout_is_reported_as_crashed(self):
        outcome = _run_target_in_subprocess(_hang_worker, (5,), timeout_s=0.5)
        assert outcome.crashed is True
        assert outcome.got_result is False
        assert "timed out" in (outcome.crash_reason or "")

    def test_memory_error_caught_in_child_is_not_crashed(self):
        """A catchable Python MemoryError inside the child is a clean
        result (status distinguishable as "memory_error" by the caller),
        not a subprocess crash -- only an uncatchable process-level death
        (SIGABRT/SIGKILL/timeout) is "crashed". See
        `_batch_worker_entry`'s own `except MemoryError` branch, which this
        mirrors at a unit-test remove from the full SAT stack.
        """
        outcome = _run_target_in_subprocess(_memory_error_worker, (None,), timeout_s=30)
        assert outcome.crashed is False
        assert outcome.result == {"status": "memory_error"}

    def test_peak_rss_is_measured_even_for_a_result_that_crashed(self):
        outcome = _run_target_in_subprocess(_abort_worker, (None,), timeout_s=30)
        # The /proc-based watcher thread should have observed *some*
        # nonzero RSS for the child before it died -- this is the
        # mechanism that makes batch 5's peak RSS (UNMEASURED in the first
        # prototype run's evidence doc) measurable now even on a crash.
        assert outcome.external_peak_rss_kb > 0


# ---------------------------------------------------------------------------
# Capacity round-trip: prove `channel_widths` (and the plain-dataclass
# `NetClassRules` used by `_DesignRulesStub`) survive a literal pickle
# round trip byte-for-byte in the fields that matter, not merely "looks
# picklable by inspection".
# ---------------------------------------------------------------------------


def _make_channel_widths(edge_widths: dict[tuple, float]) -> ChannelWidths:
    return ChannelWidths(
        layer_name="F.Cu",
        node_widths={},
        edge_widths=dict(edge_widths),
        min_width=min(edge_widths.values()),
        max_width=max(edge_widths.values()),
        avg_width=sum(edge_widths.values()) / len(edge_widths),
    )


class TestCapacityRoundTrip:
    def test_channel_widths_pickle_round_trip_is_exact(self):
        u, v = (0.0, 0.0), (1.0, 0.0)
        widths = _make_channel_widths({(u, v): 2.5})
        restored: ChannelWidths = pickle.loads(pickle.dumps(widths))
        assert restored.edge_widths == widths.edge_widths
        assert restored.layer_name == widths.layer_name
        assert restored.avg_width == pytest.approx(widths.avg_width)

    def test_shrink_then_pickle_round_trip_preserves_consumed_capacity(self):
        """Simulates exactly what crosses the subprocess boundary each
        batch: the parent computes `shrunk_widths` from `consumed`
        (capacity already committed by earlier batches), and that dict is
        what gets pickled into the next child's `Process` args. If the
        round trip silently lost or rounded the consumption, a later
        batch would see more capacity than actually remains and could
        over-subscribe the edge (the short-circuit risk the task calls
        out).
        """
        u, v = (0.0, 0.0), (1.0, 0.0)
        edge_id = "F.Cu:(0.0,0.0)-(1.0,0.0)"
        channel_widths = {"F.Cu": _make_channel_widths({(u, v): 2.5})}
        edge_lookup = {edge_id: ("F.Cu", u, v)}

        # A net "consumes" 0.5mm + 0.2mm clearance off this edge -- mirrors
        # _consume_capacity's own arithmetic (trace_width_mm + clearance_mm).
        consumed = {edge_id: 0.7}
        shrunk = _shrink_channel_widths(channel_widths, consumed, edge_lookup)

        # This is the literal boundary-crossing step: pickle.dumps/loads,
        # the same serialization multiprocessing's spawn context applies
        # to every Process() arg.
        shrunk_after_roundtrip: dict[str, ChannelWidths] = pickle.loads(pickle.dumps(shrunk))

        assert shrunk_after_roundtrip["F.Cu"].edge_widths[(u, v)] == pytest.approx(2.5 - 0.7)
        # The original (parent-side, pre-shrink) object must be untouched --
        # _shrink_channel_widths returns a copy, not an in-place mutation.
        assert channel_widths["F.Cu"].edge_widths[(u, v)] == pytest.approx(2.5)

    def test_consumption_floors_at_zero_across_round_trip(self):
        """Two nets consuming more than the edge's total capacity must
        floor at 0, not go negative -- a negative capacity crossing the
        boundary would silently invert the AtMostK bound in the next
        batch's model.
        """
        u, v = (0.0, 0.0), (1.0, 0.0)
        edge_id = "F.Cu:(0.0,0.0)-(1.0,0.0)"
        channel_widths = {"F.Cu": _make_channel_widths({(u, v): 1.0})}
        edge_lookup = {edge_id: ("F.Cu", u, v)}
        consumed = {edge_id: 5.0}  # more than the edge can hold

        shrunk = _shrink_channel_widths(channel_widths, consumed, edge_lookup)
        restored = pickle.loads(pickle.dumps(shrunk))
        assert restored["F.Cu"].edge_widths[(u, v)] == 0.0

    def test_consume_capacity_matches_design_rules_stub(self):
        """`_consume_capacity` (parent-side bookkeeping) and
        `_DesignRulesStub.get_rules_for_net` (the child-side substitute
        for the real Rust `DesignRules`, see `_write_shared_context`'s
        docstring) must agree on trace_width_mm + clearance_mm for the
        same net -- otherwise the two sides of the boundary would consume
        capacity inconsistently with what the child's own model assumed.
        """
        rule = NetClassRules(
            name="Signal",
            clearance_mm=0.2,
            trace_width_mm=0.3,
            via_diameter_mm=0.6,
            via_drill_mm=0.3,
        )
        stub = _DesignRulesStub(
            net_rules={"NET1": rule},
            default_trace_width_mm=0.25,
            default_clearance_mm=0.2,
        )
        # Round-trip the stub itself -- it is exactly what
        # `_batch_worker_entry` constructs from the pickled shared-context
        # file's `net_rules` dict, so it must survive the same trip.
        stub_restored: _DesignRulesStub = pickle.loads(pickle.dumps(stub))
        looked_up = stub_restored.get_rules_for_net("NET1")
        assert looked_up.trace_width_mm == pytest.approx(0.3)
        assert looked_up.clearance_mm == pytest.approx(0.2)

        topo = {
            "NET1": NetTopology(
                net_name="NET1",
                path_graph=None,
                uses_channels=["F.Cu:(0.0,0.0)-(1.0,0.0)"],
                total_length_estimate=1.0,
            )
        }

        class _FakeNet:
            name = "NET1"

        class _FakeDesignRules:
            def get_rules_for_net(self, name):
                return rule

        consumed: dict[str, float] = {}
        _consume_capacity(consumed, topo, [_FakeNet()], _FakeDesignRules())
        expected = looked_up.trace_width_mm + looked_up.clearance_mm
        assert consumed["F.Cu:(0.0,0.0)-(1.0,0.0)"] == pytest.approx(expected)

    def test_design_rules_stub_falls_back_to_defaults_for_unknown_net(self):
        stub = _DesignRulesStub(
            net_rules={},
            default_trace_width_mm=0.25,
            default_clearance_mm=0.2,
        )
        rule = stub.get_rules_for_net("UNKNOWN_NET")
        assert rule.trace_width_mm == pytest.approx(0.25)
        assert rule.clearance_mm == pytest.approx(0.2)


# ---------------------------------------------------------------------------
# Skeleton pickle round trip. Regression coverage for the bug this task
# fixes: `_write_shared_context` unconditionally pickled Stage 2's
# `skeletons` dict, whose values became unpicklable Rust `SkeletonGraph`
# pyo3 objects when `channel_skeleton.py` was migrated to Rust -- crashing
# every `--net-batching` run before Stage 3 ever solved a batch. Nothing in
# the prior suite pickled a *real* `SkeletonGraph`; `TestCapacityRoundTrip`
# above round-trips `ChannelWidths`/`_DesignRulesStub`/`NetClassRules` (all
# plain dataclasses) but never touched the skeleton graphs. This class
# closes that gap: it pickles the actual `_write_shared_context` output
# file (the same file every batch/singleton-retry child process reads),
# containing a real `SkeletonGraph`-backed `ChannelSkeleton`, and asserts
# it loads back with the edge/node data intact -- the same round trip
# `multiprocessing`'s spawn context and this function's own temp-file
# handoff both perform in production.
# ---------------------------------------------------------------------------


def _make_real_skeleton(
    edges: list[tuple[tuple[float, float], tuple[float, float]]],
) -> ChannelSkeleton:
    """A `ChannelSkeleton` backed by a real Rust `SkeletonGraph` (not a
    stand-in) -- the same type Stage 2 (`channel_skeleton.py`) actually
    produces, so a test against it exercises the real pickling boundary.
    """
    g = SkeletonGraph()
    total_length = 0.0
    for u, v in edges:
        g.add_node(u, pos=u)
        g.add_node(v, pos=v)
        dx, dy = v[0] - u[0], v[1] - u[1]
        length = (dx**2 + dy**2) ** 0.5
        g.add_edge(u, v, weight=length)
        total_length += length
    return ChannelSkeleton(graph=g, layer_name="F.Cu", total_length=total_length)


class _FakeNet:
    def __init__(self, name: str) -> None:
        self.name = name


class _FakeDesignRulesForSharedContext:
    """Minimal stand-in for the real Rust `DesignRules` pyclass, exposing
    only what `_write_shared_context` itself calls: `get_rules_for_net`
    plus the two default-width attributes.
    """

    default_trace_width_mm = 0.25
    default_clearance_mm = 0.2

    def get_rules_for_net(self, net_name: str) -> NetClassRules:
        return NetClassRules(
            name="Default",
            clearance_mm=0.2,
            trace_width_mm=0.25,
            via_diameter_mm=0.6,
            via_drill_mm=0.3,
        )


class _FakePcbForSharedContext:
    def __init__(self, source_path: Path) -> None:
        self.source_path = source_path
        self.nets = [_FakeNet("NET1")]
        self.design_rules = _FakeDesignRulesForSharedContext()


class TestSkeletonPickleRoundTrip:
    def test_bare_skeletons_dict_is_not_picklable(self):
        """Pins the underlying defect this fix works around: a real
        `SkeletonGraph`-backed `ChannelSkeleton` cannot be pickled directly,
        even though `SkeletonGraph` itself implements `__reduce__`/
        `__getstate__`/`__setstate__` -- the failure is one level up (the
        pyo3 submodule it lives in, `temper_design_bundle_python.
        channel_skeleton_contracts`, is never registered in `sys.modules`,
        which is what pickle needs to resolve the class back on load). If
        this assertion ever starts failing, `SkeletonGraph` has become
        directly picklable (e.g. the submodule-registration gap was fixed
        crate-wide) and `_project_skeletons` may no longer be required --
        that would be a welcome reason to revisit this module, not a bug.
        """
        skeletons = {"F.Cu": _make_real_skeleton([((0.0, 0.0), (1.0, 0.0))])}
        with pytest.raises(pickle.PicklingError):
            pickle.dumps(skeletons)

    def test_project_skeletons_round_trips_edges_and_nodes(self):
        skeletons = {
            "F.Cu": _make_real_skeleton([((0.0, 0.0), (1.0, 0.0)), ((1.0, 0.0), (1.0, 1.0))]),
            "B.Cu": _make_real_skeleton([((2.0, 2.0), (3.0, 2.0))]),
        }
        projected = _project_skeletons(skeletons)
        restored = pickle.loads(pickle.dumps(projected))

        assert set(restored) == {"F.Cu", "B.Cu"}
        assert set(restored["F.Cu"].graph.edges) == {
            ((0.0, 0.0), (1.0, 0.0)),
            ((1.0, 0.0), (1.0, 1.0)),
        }
        assert set(restored["F.Cu"].graph.nodes) == {(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)}
        assert set(restored["B.Cu"].graph.edges) == {((2.0, 2.0), (3.0, 2.0))}

    def test_write_shared_context_round_trips_a_real_skeleton(self, tmp_path):
        """The end-to-end regression test: build a shared-context file the
        same way `run_net_batched_stage3` does (real `_write_shared_context`
        call, real `SkeletonGraph`-backed skeleton) and confirm every child
        process's `pickle.load(open(ctx_path, "rb"))` step -- the exact
        line that crashed in production -- succeeds and yields usable
        edge/node data.
        """
        pcb = _FakePcbForSharedContext(tmp_path / "board.kicad_pcb")
        skeletons = {"F.Cu": _make_real_skeleton([((0.0, 0.0), (5.0, 0.0))])}

        ctx_path = _write_shared_context(pcb, skeletons)
        try:
            with open(ctx_path, "rb") as f:
                shared = pickle.load(f)
        finally:
            import os

            os.unlink(ctx_path)

        assert shared["pcb_path"] == str(pcb.source_path)
        restored_skeleton = shared["skeletons"]["F.Cu"]
        assert list(restored_skeleton.graph.edges) == [((0.0, 0.0), (5.0, 0.0))]
        assert set(restored_skeleton.graph.nodes) == {(0.0, 0.0), (5.0, 0.0)}
