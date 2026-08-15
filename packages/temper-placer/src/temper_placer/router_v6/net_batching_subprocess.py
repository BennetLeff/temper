"""Subprocess-per-batch boundary for :mod:`temper_placer.router_v6.net_batching`.

Split out of ``net_batching.py`` on 2026-08-14 to bring that module back
under its LOC-cap allowlist baseline (``.loc-allowlist.txt``) after
``#1073`` (``d5eb7adde``) legitimately grew it past the recorded baseline
while fixing a real production defect (the constraint audit not running on
the net-batching path) -- see that commit and
``docs/solutions/logic-errors/unsound-atmostk-capacity-encoding.md``. This
split changes no behavior: every name below is verbatim from
``net_batching.py``'s "Subprocess-per-batch boundary" section, moved as-is.

See ``net_batching.py``'s own module docstring ("Subprocess-per-batch" and
the Phase E5 boundary sections) for the design rationale -- what crosses the
process boundary and why, how a crash is distinguished from UNSAT, and why
this mechanism (not just the SAT dispatch) is the part of the module the E5
Rust-orchestration migration explicitly kept in Python. This file is that
mechanism; ``net_batching.py`` still re-exports every name here (so
``net_batching.X`` and ``from temper_placer.router_v6.net_batching import
X`` keep working) and remains the single import surface documented there.
"""

from __future__ import annotations

import multiprocessing as mp
import os
import pickle
import resource
import signal
import tempfile
import threading
import time
from dataclasses import dataclass
from multiprocessing.connection import Connection
from pathlib import Path
from typing import Any

from temper_placer.router_v6.channel_widths import ChannelWidths
from temper_placer.router_v6.diff_pair_inference import DiffPair
from temper_placer.router_v6.stage0_data import ParsedPCB

#: How often the parent's watcher thread re-reads ``/proc/<pid>/status`` for
#: a child's current ``VmHWM`` (peak resident set size so far). Independent
#: of the child's own self-reported ``resource.getrusage`` figure -- see
#: :func:`_watch_peak_rss_kb` -- specifically so a peak-RSS figure is still
#: MEASURED even for a batch that crashes before it can self-report anything.
_RSS_POLL_INTERVAL_S = 0.15


@dataclass
class _SkeletonGraphProjection:
    """Picklable projection of a Rust ``SkeletonGraph`` (``.graph`` on a
    ``ChannelSkeleton``), exposing only ``.edges``/``.nodes`` -- see
    :func:`_project_skeletons` for why this narrower substitute is
    sufficient and how that was verified rather than assumed.
    """

    edges: list[tuple[tuple[float, float], tuple[float, float]]]
    nodes: list[tuple[float, float]]


@dataclass
class _ChannelSkeletonProjection:
    """Picklable stand-in for ``ChannelSkeleton``, carrying only ``.graph``
    (see :class:`_SkeletonGraphProjection`) -- the one attribute
    ``_solve_subset``'s codepath ever reads off a skeleton. ``layer_name``/
    ``total_length`` are dropped: nothing reachable from ``_solve_subset``
    reads either (``layer_name`` is already the ``skeletons`` dict key
    everywhere it matters).
    """

    graph: _SkeletonGraphProjection


def _project_skeletons(skeletons: dict[str, Any]) -> dict[str, _ChannelSkeletonProjection]:
    """Build a plain, picklable projection of *skeletons* carrying only
    what a batch worker actually reads.

    **Why a projection instead of pickling the real ``ChannelSkeleton``/
    ``SkeletonGraph`` objects.** ``SkeletonGraph`` (``temper_design_bundle
    _python.channel_skeleton_contracts.SkeletonGraph``, the Rust pyclass
    that replaced ``networkx.Graph`` here) already implements ``__reduce__``/
    ``__getstate__``/``__setstate__`` -- but pickling an instance still
    raises ``PicklingError: Can't pickle ... SkeletonGraph: import of
    module 'temper_design_bundle_python.channel_skeleton_contracts' failed``
    (confirmed by reproduction, not assumed). The cause is one level up
    from the class itself: pickle resolves a ``__reduce__``-returned class
    by ``__import__(obj.__module__)`` then ``getattr(..., obj.__qualname__)``,
    and ``channel_skeleton_contracts`` is a **submodule registered via
    pyo3's ``parent_module.add_submodule(&sub)``** -- which makes it
    reachable as ``temper_design_bundle_python.channel_skeleton_contracts``
    (an attribute lookup) without ever inserting it into ``sys.modules``,
    so a plain ``import temper_design_bundle_python.channel_skeleton_
    contracts`` fails even though ``tdb.channel_skeleton_contracts`` works
    fine. This is a crate-wide packaging gap (every pyo3 submodule this
    crate registers has the same shape -- ``board_contracts``,
    ``geometry_contracts``, ``topological_graph_contracts``, and others all
    reproduce it too), out of scope to fix generally here.

    **Why the narrower substitute is sufficient.** Tracing every
    ``skeleton.graph.`` / ``sk.graph.`` read reachable from
    ``_solve_subset`` -- ``ModelBuilder`` in
    ``packages/temper-design-bundle/src/model_builder.rs``
    (``skeleton_edges`` reads ``graph.edges``; ``create_via_vars`` reads
    ``graph.nodes``) and the Python-side ``TEMPER_MODEL_TRACE``/R10
    non-emptiness check in ``constraint_model.py`` (``sk.graph.nodes``) --
    shows exactly those two attributes are read, both already plain lists
    of ``(x, y)``/``(u, v)`` float tuples once materialised (no ``weight``,
    no ``is_connected``/``connected_components`` call on this path). So
    each child gets a small duck-typed stand-in exposing only those two
    lists, the same pattern :class:`_DesignRulesStub` already uses for
    ``design_rules``, rather than either (a) pickling the real Rust object
    (blocked by the packaging gap above) or (b) having every child
    re-derive the skeleton from scratch (the medial-axis extraction +
    ``_ensure_skeleton_connectivity`` bridging pass this projection skips
    costs ~10s/layer on the production board per
    ``_ensure_skeleton_connectivity``'s own docstring -- paying that again
    on every one of up to ~11 + N-retry subprocess launches would be far
    more expensive than the ~40ms ``pcb`` re-parse this function already
    accepts for a different reason).
    """
    return {
        layer_name: _ChannelSkeletonProjection(
            graph=_SkeletonGraphProjection(
                edges=[(u, v) for (u, v) in skeleton.graph.edges],
                nodes=list(skeleton.graph.nodes),
            )
        )
        for layer_name, skeleton in skeletons.items()
    }


def _write_shared_context(pcb: ParsedPCB, skeletons: dict[str, Any]) -> str:
    """Pickle the *static-across-the-run* inputs once, to a temp file, and
    return its path. Every batch's (and every singleton retry's) child
    process re-reads this same file rather than having the parent re-pickle
    these through a ``Process`` args pipe on every one of up to
    ~11 + N-retry subprocess launches.

    **Why this is a source path + a per-net rules snapshot, not the
    ``ParsedPCB`` object itself.** ``ParsedPCB.nets``/``.components`` --
    and, one level deeper than first expected, ``ParsedPCB.design_rules``
    itself -- are ``temper_design_bundle_python`` pyo3 pyclasses (the
    Rust-migrated netlist/design-rules model; see ``core/netlist.py`` and
    ``core/design_rules.py``'s module docstrings) and do not implement
    ``__reduce__``/``__getstate__``. Pickling either directly raises
    ``TypeError: cannot pickle '...Component'/'...DesignRules' object``
    (both hit while building this feature; neither is hypothetical --
    ``stage0_data.DesignRules`` is a same-shaped plain dataclass that
    exists in this codebase, but it is *not* the type a real parsed board
    actually carries at runtime, which is the trap). Re-implementing
    pickle support for those pyclasses is out of scope here and would
    reach into a different crate for a router-only concern.

    So the boundary is drawn narrower than "pass pcb + design_rules": each
    child reconstructs its own equivalent ``ParsedPCB`` by **re-parsing
    the same source file** with the identical call
    (``parse_kicad_pcb_v6(path, use_declared_layer_roles=True)``) Stage 0
    itself uses (see ``_pipeline_core.py``'s ``run()``) -- deterministic
    for a byte-identical file, so the reconstructed ``Net``/``Component``
    objects carry the same names, pins, and positions as the parent's, and
    ``_create_layer_constraints`` (the one place ``ModelBuilder`` reads
    ``pcb.components`` -- see ``constraint_model.py``) gets what it needs
    from that reconstruction directly. For ``design_rules``, tracing every
    use inside the ``_solve_subset`` codepath (``constraint_model.py``)
    shows exactly one method call site, ``design_rules.get_rules_for_net
    (net.name).{trace_width_mm,clearance_mm}`` (``_create_capacity_
    constraints``) plus a bare truthiness check -- nothing else about the
    Rust ``DesignRules`` object is ever read on this path. So rather than
    reconstruct the whole ``DesignRules`` object (which would additionally
    require re-deriving the netclass-assignment injections
    ``RouterV6Pipeline.run()`` applied before ``net_batching`` ever saw
    ``pcb``, from inputs this function does not have), the parent
    pre-computes ``get_rules_for_net(name)`` for every net **once**, up
    front, while it still holds the live functional object -- each
    result is already a ``stage0_data.NetClassRules``, a plain dataclass,
    fully picklable -- and the child wraps that lookup dict in a tiny
    local duck-typed stand-in (:class:`_DesignRulesStub`) exposing the one
    method actually called. Net selection is done **by name**, not index
    (:func:`_batch_worker_entry`), so none of this depends on the child's
    re-parse producing ``nets`` in the same list order the parent's
    already-sorted ``pcb.nets`` is in.

    **``skeletons`` crosses as a projection, not the live objects, for the
    same "trace what's actually read, ship only that" reasoning applied
    above to ``pcb``/``design_rules``.** See :func:`_project_skeletons`
    for why: the live ``ChannelSkeleton``/``SkeletonGraph`` objects turned
    out to be unpicklable too, but for a different, narrower reason than
    ``pcb``/``design_rules`` (a pyo3 submodule-packaging gap, not a
    missing ``__reduce__`` -- ``SkeletonGraph`` has one), discovered by
    this failing loudly (a real ``PicklingError`` reproduced via
    ``scripts/route_board.py --net-batching``) rather than assumed safe
    just because the pre-Rust-migration ``networkx.Graph`` it replaced
    pickled fine.
    """
    fd, path = tempfile.mkstemp(prefix="temper_batch_ctx_", suffix=".pkl")
    source_path = getattr(pcb, "source_path", None)
    if source_path is None:
        raise ValueError("pcb.source_path is required for subprocess-per-batch reconstruction")
    net_rules = {net.name: pcb.design_rules.get_rules_for_net(net.name) for net in pcb.nets}
    with os.fdopen(fd, "wb") as f:
        pickle.dump(
            {
                "pcb_path": str(source_path),
                "net_rules": net_rules,
                "default_trace_width_mm": float(pcb.design_rules.default_trace_width_mm),
                "default_clearance_mm": float(pcb.design_rules.default_clearance_mm),
                "skeletons": _project_skeletons(skeletons),
            },
            f,
            protocol=pickle.HIGHEST_PROTOCOL,
        )
    return path


@dataclass
class _DesignRulesStub:
    """Picklable duck-typed stand-in for the Rust ``DesignRules`` pyclass,
    exposing only the one method ``_solve_subset``'s codepath calls
    (``get_rules_for_net``) -- see :func:`_write_shared_context`'s
    docstring for why the real object can't cross the subprocess boundary
    and why this narrower substitute is sufficient and verified sufficient
    (not merely assumed) by tracing every ``design_rules.``/``self.pcb.``
    read in ``constraint_model.py``.
    """

    net_rules: dict[str, Any]
    default_trace_width_mm: float
    default_clearance_mm: float

    def get_rules_for_net(self, net_name: str) -> Any:
        rule = self.net_rules.get(net_name)
        if rule is not None:
            return rule
        from temper_placer.router_v6.stage0_data import NetClassRules

        return NetClassRules(
            name="Default",
            clearance_mm=self.default_clearance_mm,
            trace_width_mm=self.default_trace_width_mm,
            via_diameter_mm=0.6,
            via_drill_mm=0.3,
        )


def _batch_worker_entry(
    conn: Connection,
    ctx_path: str,
    net_names_subset: list[str],
    channel_widths: dict[str, ChannelWidths],
    diff_pairs_subset: list[DiffPair],
    enable_geographic_pruning: bool,
    sat_conflict_limit: int | None,
    sat_time_limit_ms: int | None,
) -> None:
    """Child-process entry point: build + solve exactly one batch (or one
    singleton retry) and send a small, plain-dict summary back over *conn*.

    Runs in a **fresh** ``multiprocessing`` (spawn) process -- a brand-new
    interpreter with its own heap, not a fork of the parent's -- so a Rust
    allocator ``abort()`` here terminates only this process, and any
    unreleased Rust/CPython allocator state from a *previous* batch (the
    RSS-creep hypothesis from the first prototype run) cannot carry over,
    because there is no previous-batch state in this process to begin with.

    Deliberately catches ``MemoryError`` here (same as the original
    in-process design) so an ordinary Python-level OOM is still reported as
    a clean, distinguishable ``"memory_error"`` result -- only a hard
    process abort (uncatchable from Python by construction) is left to be
    inferred by the *parent* from the absence of any message on *conn*.
    """
    t0 = time.perf_counter()
    try:
        from temper_placer.io.kicad_parser import parse_kicad_pcb_v6
        from temper_placer.router_v6.net_batching import _solve_subset

        with open(ctx_path, "rb") as f:
            shared = pickle.load(f)
        # Reconstruct an equivalent ParsedPCB by re-parsing the same source
        # file -- see _write_shared_context's docstring for why this
        # crosses the boundary as a path instead of a pickled object.
        pcb: ParsedPCB = parse_kicad_pcb_v6(
            Path(shared["pcb_path"]), use_declared_layer_roles=True
        )
        design_rules_stub = _DesignRulesStub(
            net_rules=shared["net_rules"],
            default_trace_width_mm=shared["default_trace_width_mm"],
            default_clearance_mm=shared["default_clearance_mm"],
        )
        skeletons: dict[str, Any] = shared["skeletons"]
        name_to_net = {n.name: n for n in pcb.nets}
        nets_subset = [name_to_net[name] for name in net_names_subset]

        cm, rust_result = _solve_subset(
            skeletons=skeletons,
            nets_subset=nets_subset,
            channel_widths=channel_widths,
            design_rules=design_rules_stub,
            diff_pairs_subset=diff_pairs_subset,
            pcb=pcb,
            enable_geographic_pruning=enable_geographic_pruning,
            sat_conflict_limit=sat_conflict_limit,
            sat_time_limit_ms=sat_time_limit_ms,
        )
        status = rust_result.get("status", "unknown")
        n_net_channel = sum(1 for v in cm.variables if type(v).__name__ == "NetChannelVar")
        n_via = sum(1 for v in cm.variables if type(v).__name__ == "ViaVar")
        result = {
            "status": status,
            "topology_graph": rust_result.get("topology_graph", {}),
            # Per plan 2026-08-12-003's R3 (see _solve_subset above):
            # `_solve_subset` already computed this (audit_result) right
            # after the solve, while it still held
            # cm.variables/cm.constraints -- carried across the subprocess
            # pipe as plain data so the parent (`run_net_batched_stage3`)
            # can raise on it, mirroring where `_consume_capacity` is
            # called for the same "sat" result.
            "audit_violations": rust_result.get("audit_violations", []),
            "primary_vars": cm.variable_count,
            "net_channel_vars": n_net_channel,
            "via_vars": n_via,
            "constraints": cm.constraint_count,
            "wall_s": time.perf_counter() - t0,
            "peak_rss_kb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        }
    except MemoryError:
        result = {
            "status": "memory_error",
            "topology_graph": {},
            "audit_violations": [],
            "primary_vars": 0,
            "net_channel_vars": 0,
            "via_vars": 0,
            "constraints": 0,
            "wall_s": time.perf_counter() - t0,
            "peak_rss_kb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        }
    conn.send(result)
    conn.close()


def _watch_peak_rss_kb(pid: int, stop_evt: threading.Event, out: dict[str, int]) -> None:
    """Poll ``/proc/<pid>/status`` for ``VmHWM`` (the kernel's own running
    peak-RSS high-water mark) until *stop_evt* fires or the process is gone.

    Runs even for a child that crashes: the kernel updates ``VmHWM`` live as
    the process allocates, so this measures peak RSS independently of
    whether the child survives long enough to self-report via
    ``resource.getrusage`` (it may not -- SIGABRT does not run Python
    cleanup code). This is why batch 5's "peak RSS" was UNMEASURED in the
    first prototype run's evidence doc and is no longer unmeasurable here.
    """
    path = f"/proc/{pid}/status"
    peak = 0
    while not stop_evt.is_set():
        try:
            with open(path) as f:
                for line in f:
                    if line.startswith("VmHWM:"):
                        peak = max(peak, int(line.split()[1]))
                        break
        except (FileNotFoundError, ProcessLookupError, PermissionError, OSError):
            break
        stop_evt.wait(_RSS_POLL_INTERVAL_S)
    out["peak_rss_kb"] = peak


@dataclass
class _SubprocessOutcome:
    got_result: bool
    result: dict[str, Any] | None
    crashed: bool
    crash_reason: str | None
    exitcode: int | None
    external_peak_rss_kb: int
    wall_s_wall: float


def _describe_exitcode(exitcode: int | None) -> str:
    if exitcode is None:
        return "still running (timed out, terminated by parent)"
    if exitcode == 0:
        return "exit 0"
    if exitcode < 0:
        signum = -exitcode
        try:
            name = signal.Signals(signum).name
        except ValueError:
            name = f"signal {signum}"
        return f"killed by {name} (exit code {exitcode})"
    return f"exit code {exitcode}"


def _run_target_in_subprocess(
    target: Any,
    extra_args: tuple[Any, ...],
    *,
    timeout_s: float,
) -> _SubprocessOutcome:
    """Run ``target(conn, *extra_args)`` in a fresh child process and return
    a structured outcome that makes crash-vs-clean unambiguous to the
    caller. Generic over *target* deliberately -- :func:`_run_subset_subprocess`
    is the only production caller (always ``_batch_worker_entry``), but
    keeping the crash-detection mechanism itself independent of what the
    child actually computes is what makes it exercisable by a unit test
    with a trivial, deliberately-crashing stand-in target instead of
    needing a full SAT solve to prove the polling/exitcode logic correct
    (see ``test_net_batching_subprocess.py``).

    ``spawn`` (not the POSIX default ``fork``) is used deliberately: a fork
    child starts as a copy-on-write clone of the parent's *current* heap,
    which would not conclusively rule out inherited allocator/arena state
    as a contributor to the original RSS-creep finding. ``spawn`` starts a
    genuinely fresh interpreter with nothing inherited but open file
    descriptors and the pickled ``Process`` args, which is the strongest
    version of "fresh process" available and the one the evidence doc's
    fix recommendation described.
    """
    t_wall0 = time.perf_counter()
    ctx = mp.get_context("spawn")
    parent_conn, child_conn = ctx.Pipe(duplex=False)
    proc = ctx.Process(target=target, args=(child_conn, *extra_args))
    proc.start()
    child_conn.close()  # parent doesn't write; drop its copy of the send end

    stop_evt = threading.Event()
    watch_out: dict[str, int] = {}
    watcher = threading.Thread(
        target=_watch_peak_rss_kb, args=(proc.pid, stop_evt, watch_out), daemon=True
    )
    watcher.start()

    got_result = False
    poll_completed = False
    result: dict[str, Any] | None = None
    try:
        poll_completed = parent_conn.poll(timeout_s)
        if poll_completed:
            try:
                result = parent_conn.recv()
                got_result = True
            except (EOFError, OSError):
                got_result = False
    finally:
        if got_result:
            # The child already did the one thing that matters; give it a
            # normal grace period to exit cleanly on its own.
            proc.join(timeout=30)
        else:
            # No result -- either the child already crashed/exited without
            # sending (a short join just reaps it), or it blew through
            # *our* timeout budget and is still running. Either way we are
            # not waiting any further for it: granting a long grace period
            # here would let a merely-slow-but-alive child finish normally
            # just after we'd already decided not to use its result, which
            # both wastes wall time and (as caught by this module's own
            # test suite) makes the reported exit code misleadingly clean.
            proc.join(timeout=2)
        if proc.is_alive():
            proc.terminate()
            proc.join(timeout=10)
        if proc.is_alive():
            proc.kill()
            proc.join(timeout=10)
        stop_evt.set()
        watcher.join(timeout=2)
        parent_conn.close()

    exitcode = proc.exitcode
    # A received result is trusted regardless of the exit code that
    # followed it (the child already did the one thing that matters --
    # ``conn.send`` -- before anything else could go wrong on its way out).
    # Only the absence of a result is "crashed": that is the one condition
    # that is, by construction, indistinguishable from "never got a fair
    # chance to answer sat/unsat/unknown" -- see the module docstring.
    crashed = not got_result
    crash_reason = None
    if crashed:
        if not poll_completed:
            crash_reason = (
                f"timed out after {timeout_s:.0f}s waiting for a result "
                f"({_describe_exitcode(exitcode)})"
            )
        else:
            crash_reason = f"no result received before child exit ({_describe_exitcode(exitcode)})"

    return _SubprocessOutcome(
        got_result=got_result,
        result=result,
        crashed=crashed,
        crash_reason=crash_reason,
        exitcode=exitcode,
        external_peak_rss_kb=watch_out.get("peak_rss_kb", 0),
        wall_s_wall=time.perf_counter() - t_wall0,
    )


def _run_subset_subprocess(
    *,
    ctx_path: str,
    net_names: list[str],
    channel_widths: dict[str, ChannelWidths],
    diff_pairs_subset: list[DiffPair],
    enable_geographic_pruning: bool,
    sat_conflict_limit: int | None,
    sat_time_limit_ms: int | None,
    timeout_s: float,
) -> _SubprocessOutcome:
    """Run one batch's (or one singleton retry's) build+solve in a fresh
    child process via :func:`_run_target_in_subprocess`, target
    ``_batch_worker_entry``.
    """
    return _run_target_in_subprocess(
        _batch_worker_entry,
        (
            ctx_path,
            net_names,
            channel_widths,
            diff_pairs_subset,
            enable_geographic_pruning,
            sat_conflict_limit,
            sat_time_limit_ms,
        ),
        timeout_s=timeout_s,
    )
