"""Router V6 Stage 3 net-batching: prototype for `#871`.

`docs/evidence/2026-08-07-sat-model-reduction-options.md` (S2) rated
net-batching the best-evidenced non-bundling reduction for the 22.5M-primary
-variable monolith that OOMs at 5.43GB under an 8GB `ulimit -v` cap before
ever reaching Rust's ``encode_to_cnf``. Rather than building one
``ConstraintModel`` covering every net, this module partitions the net list
into batches of size ``B`` and solves each batch's SAT model separately,
with each later batch's channel capacity reduced by what earlier batches
already consumed.

**What this does and does not preserve, stated plainly up front (see the
module's own docstrings below for the mechanism):**

- **Capacity** (the one constraint class `constraint_model.py` actually
  encodes as a cross-net SAT constraint) is preserved across batch
  boundaries by explicit bookkeeping: :func:`_consume_capacity` subtracts
  each successfully-routed net's ``trace_width + clearance`` from the
  remaining capacity of every channel edge it used, and
  :func:`_shrink_channel_widths` feeds that reduced capacity into the next
  batch's ``ModelBuilder``. This is the one piece of "preserve the global
  constraint across batches" that is this module's own responsibility, and
  it is the state that now has to survive the subprocess boundary (see
  below) once per batch, every batch: the ``consumed`` dict lives in the
  *parent* process, is used to compute ``shrunk_widths`` in the parent, and
  ``shrunk_widths`` is then pickled as a ``multiprocessing`` ``Process``
  arg into each batch's fresh (``spawn``-context) child process (see
  :func:`_run_subset_subprocess`).
- **Creepage, HV/SELV separation, and geometric clearance** are, by
  inspection of ``constraint_model.py`` (no ``CreepageConstraint`` or
  ``ClearanceConstraint`` class exists there — only ``CapacityConstraint``,
  ``DiffPairConstraint``, ``LayerConstraint``, and an unused
  ``ChannelSeparationConstraint``), never encoded in the Stage 3 SAT model
  in the first place, batched or not. They are enforced downstream, in
  Stage 4's occupancy-grid A* (``occupancy_grid.py``'s
  ``mark_path_blocked``/``mark_via_blocked`` dilate every routed path and
  via by its net's required clearance before the *next* net's A* search
  runs — a single whole-board pass over every net regardless of how Stage 3
  produced its topology) and verified post-hoc by whole-board KiCad DRC on
  the fully assembled output. Net-batching only changes how Stage 3 assigns
  *topology* (which channel edges a net's path may use); it does not batch
  Stage 4, which still runs once, after all Stage 3 batches complete, over
  the complete net list with a single occupancy grid. This is why batching
  Stage 3 does not weaken whole-board clearance/creepage/HV-SELV
  enforcement — that enforcement was never inside Stage 3 to begin with.

**Subprocess-per-batch (follow-up to the first prototype run, `#871`).**
The first prototype ran every batch in-process and died on batch 5 of a
production-board run to a Rust allocator ``abort()`` (SIGABRT, exit 134) --
uncatchable from Python -- after peak RSS had crept up batch-over-batch
(5.21 -> 5.78 GB) even though each batch's model was discarded after use
(see ``docs/evidence/2026-08-07-net-batching-prototype.md`` S4). Since an
``abort()`` kills the whole process, that run lost all 5 already-completed
batches' in-memory results with it. This module now runs each batch's
build+solve in a **fresh ``multiprocessing`` child process** (spawn, not
fork -- see :func:`_run_subset_subprocess`) instead of in the caller's own
process:

- **What crosses the boundary, and why that set was chosen.** The child
  needs everything ``_solve_subset`` needs to build and solve one batch's
  model. The *static-across-the-whole-run* pieces -- the board's source
  path (each child re-parses it once, cheap: ~40ms measured on the
  production board) plus the skeleton graphs and a precomputed per-net
  trace-width/clearance snapshot -- are written to a temp pickle file
  **once**, before the batch loop, and re-read by every child from that
  path (:func:`_write_shared_context`; see its docstring for why this is
  a source path and a rules *snapshot*, not the live ``ParsedPCB``/
  ``DesignRules`` objects -- they turned out to be Rust pyo3 pyclasses
  with no pickle support, discovered by this failing loudly rather than
  assumed). The *per-batch* pieces that actually vary -- the net-name
  subset, this batch's already-shrunk ``channel_widths``, and the batch's
  diff pairs -- are passed directly as ``Process`` args (small). The
  child sends back only a **small, plain-dict summary** -- topology
  (edges/channels actually used, needed for Stage 4 and for
  :func:`_consume_capacity`), variable/constraint counts, wall time, and
  its own peak RSS -- never the ``ConstraintModel`` itself (millions of
  ``Variable``/``Constraint`` dataclass instances; pickling that back
  would cost as much memory and time as the OOM this change exists to
  avoid) and never the raw Rust solver result's full ``assignments`` dict
  (one entry per CNF variable, same problem).
- **Crash vs. UNSAT, made distinguishable by construction, not by
  guesswork.** A clean outcome -- ``"sat"``, ``"unsat"``, ``"unknown"``, or
  a *caught* ``"memory_error"`` -- means the child ran its ``finally``-free
  happy path far enough to call ``conn.send(...)`` before exiting, so the
  parent both receives a result *and* observes exit code 0. A process-level
  abort (SIGABRT from Rust's allocator, SIGKILL from an OOM-killer, a
  ``ulimit -v`` allocation failure that doesn't raise a catchable
  exception, or simply timing out) means the child dies **without ever
  calling ``send``**: the parent's ``Connection.poll()`` returns with
  nothing to ``recv()`` and/or ``Process.exitcode`` comes back nonzero /
  negative (a negative exitcode is ``-signum`` on POSIX). That
  no-result-received condition is recorded as ``status="crashed"`` --
  a **distinct** status value from ``"unsat"`` -- specifically so a batch
  that never got a fair chance to prove infeasibility is never reported or
  treated as though it had.
- **Recovery is still attempted for a crash, deliberately more eagerly
  than the original design.** The original in-process prototype's
  singleton-retry recovery only fired on a genuine SAT-level UNSAT/unknown
  result; an in-process ``MemoryError`` (or a crash, which didn't exist as
  a recoverable case at all before this change) went straight to
  "no topology, all nets in the batch fall through to Stage 4's fallback."
  That is exactly the "silently drop nets" failure mode the task calls
  out: a crashed batch of 10 is not proof that all 10 nets are infeasible,
  only that *something* about solving them *together* didn't fit or
  finish. So a crashed (or memory-errored) batch now gets the *same*
  singleton-retry treatment a batch-level UNSAT already got -- each net
  retried alone, in its own fresh subprocess, against the same
  already-shrunk capacity -- on the reasoning that a singleton model is
  far smaller than a 10-net batch model and much less likely to hit the
  same ceiling. The per-batch ``NetBatchResult.status`` field still
  records the *original* batch-level outcome (``"crashed"``, distinct from
  ``"unsat"``) for reporting, even though the recovery *mechanism* applied
  next is now shared.
"""

from __future__ import annotations

import multiprocessing as mp
import os
import pickle
import re
import resource
import signal
import sys
import tempfile
import threading
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace
from multiprocessing.connection import Connection
from pathlib import Path
from typing import Any

import networkx as nx

from temper_placer.core.netlist import Net
from temper_placer.router_v6._pipeline_types import Stage2Output, Stage3Output
from temper_placer.router_v6.channel_widths import ChannelWidths
from temper_placer.router_v6.constraint_model import (
    ConstraintModel,
    ModelBuilder,
    canonical_channel_edges,
)
from temper_placer.router_v6.diff_pair_inference import DiffPair, infer_differential_pairs
from temper_placer.router_v6.stage0_data import ParsedPCB
from temper_placer.router_v6.topology_extraction import NetTopology, TopologyGraph

#: Default wall-clock budget, per subprocess launch (one full batch attempt,
#: or one singleton retry attempt), before the parent gives up waiting and
#: treats it as a crash. Generous relative to the largest single-batch wall
#: time MEASURED in the first prototype run (192.95s, batch 3's UNSAT +
#: 10-way singleton retry) to leave headroom for subprocess spawn (a fresh
#: interpreter re-importing the Rust extension) and for the unpickle of the
#: shared-context file.
DEFAULT_SUBPROCESS_TIMEOUT_S = 900.0

#: How often the parent's watcher thread re-reads ``/proc/<pid>/status`` for
#: a child's current ``VmHWM`` (peak resident set size so far). Independent
#: of the child's own self-reported ``resource.getrusage`` figure -- see
#: :func:`_watch_peak_rss_kb` -- specifically so a peak-RSS figure is still
#: MEASURED even for a batch that crashes before it can self-report anything.
_RSS_POLL_INTERVAL_S = 0.15

#: Blocks whose atopile ``Sheetpath`` prefix identifies them as high
#: boundary-net-count "hub" blocks on ``pcb/temper.kicad_pcb``.
#:
#: MEASURED this task (script: scratchpad ``block_analysis.py``, direct
#: regex extraction of each footprint's ``(property "Sheetpath" ...)`` from
#: ``pcb/temper.kicad_pcb``, cross-tabulated against which nets connect
#: components in more than one top-level block): ``mcu`` has 20
#: boundary-crossing nets and ``safety`` has 13 — both far above the next
#: block (9, ``rtd_pan``). This corroborates (does not byte-for-byte
#: reproduce — different counting methodology, not re-derived here) the
#: task brief's cited "18 and 11 boundary nets" for the same two blocks.
#: Every other block (``discharge`` 6, ``power_in`` 8, ``hb`` 8,
#: ``power_mgmt`` 3, ``ct_sense`` 5, ``aux_supply`` 4, ``tank`` 2,
#: ``thermal`` 2) is a clear second tier.
HUB_BLOCKS: frozenset[str] = frozenset({"mcu", "safety"})

#: Default batch size. The reduction survey's own arithmetic
#: (docs/evidence/2026-08-07-sat-model-reduction-options.md S2): peak raw
#: vars per batch ~= B * 204,490 channel edges; B=10 estimates ~2.04M
#: vars, corroborated by an existing MEASURED data point (a 2.6M-variable
#: model already survived construction under the same 8GB ulimit -v cap).
DEFAULT_BATCH_SIZE = 10

_FOOTPRINT_START_RE = re.compile(r'\n\s*\(footprint\s+"')
_SHEETPATH_RE = re.compile(r'\(property\s+"Sheetpath"\s+"([^"]*)"')
_REFERENCE_RE = re.compile(r'\(property\s+"Reference"\s+"([^"]*)"')


def _extract_ref_to_block(pcb_source_path: Path | str) -> dict[str, str]:
    """Map component ref -> top-level atopile block name.

    Re-reads the raw ``.kicad_pcb`` text for each footprint's
    ``Sheetpath`` property (e.g. ``"mcu.mcu"`` -> block ``"mcu"``).  This
    information does not survive into the parsed ``ParsedPCB``/``Net``
    dataclasses (checked this task: no ``sheetpath``/``hierarchy`` field
    exists on either), so it is re-derived directly from the board file,
    the same raw-text-regex technique ``_apply_placements_to_pcb`` already
    uses elsewhere in this codebase for other footprint-level properties.
    """
    text = Path(pcb_source_path).read_text(encoding="utf-8")
    starts = [m.start() for m in _FOOTPRINT_START_RE.finditer(text)]
    starts.append(len(text))
    ref_to_block: dict[str, str] = {}
    for i in range(len(starts) - 1):
        block_text = text[starts[i] : starts[i + 1]]
        sp_match = _SHEETPATH_RE.search(block_text)
        ref_match = _REFERENCE_RE.search(block_text)
        if not sp_match or not ref_match:
            continue
        sheetpath = sp_match.group(1)
        top_block = sheetpath.split(".")[0] if "." in sheetpath else sheetpath
        ref_to_block[ref_match.group(1)] = top_block
    return ref_to_block


def _net_touches_hub(net: Net, ref_to_block: dict[str, str], hub_blocks: frozenset[str]) -> bool:
    for comp_ref, _pin_name in getattr(net, "pins", None) or ():
        if ref_to_block.get(comp_ref) in hub_blocks:
            return True
    return False


def order_nets_for_batching(
    nets: Sequence[Net],
    pcb_source_path: Path | str | None,
    *,
    hub_blocks: frozenset[str] = HUB_BLOCKS,
) -> list[int]:
    """Return net indices in batching order: low-fan-out-first, hubs last.

    Primary key: whether the net touches a hub block (``mcu`` or
    ``safety`` — see :data:`HUB_BLOCKS`). Non-hub nets sort first, hub
    nets sort last, matching the task brief's "low-fan-out-first with hubs
    last" guidance (mcu/safety are the two blocks with dramatically higher
    boundary-net counts than any other block on this board, so routing
    them last defers the SAT model's hardest, most cross-cutting
    congestion to the end, after channel capacity for everything else is
    already committed and easy to reason about).

    Secondary key: ascending pin count ("low fan-out first") — the same
    convention ``_select_sat_nets`` already uses elsewhere in this
    codebase for selective SAT routing (top-N nets by ascending pin
    count). Fewer pins means a smaller, easier-to-satisfy per-net
    footprint, so routing those first fills in the "easy" capacity
    consumption before anything contentious.

    Tertiary key: net name, for full determinism.

    A post-pass moves each differential pair's second net to immediately
    follow its partner in the resulting order, so same-batch placement is
    likely (though not strictly guaranteed at a batch boundary) --
    ``ModelBuilder._create_diff_pair_constraints`` silently drops a pair
    that spans two batches (looks up both members in the *same* model's
    ``net_to_idx``; a batch-local model simply never sees the missing
    member), so keeping pairs adjacent is what makes the per-batch model
    actually enforce the pair's coupled-routing constraint instead of
    silently not applying it.
    """
    ref_to_block = _extract_ref_to_block(pcb_source_path) if pcb_source_path else {}

    def sort_key(i: int) -> tuple[bool, int, str]:
        net = nets[i]
        touches_hub = _net_touches_hub(net, ref_to_block, hub_blocks)
        pin_count = len(getattr(net, "pins", None) or ())
        return (touches_hub, pin_count, net.name)

    order = sorted(range(len(nets)), key=sort_key)

    name_to_idx = {net.name: i for i, net in enumerate(nets)}
    diff_pairs = infer_differential_pairs([n.name for n in nets])
    for pair in diff_pairs:
        p_i = name_to_idx.get(pair.p_net)
        n_i = name_to_idx.get(pair.n_net)
        if p_i is None or n_i is None or p_i == n_i:
            continue
        try:
            order.remove(n_i)
        except ValueError:
            continue
        insert_at = order.index(p_i) + 1
        order.insert(insert_at, n_i)

    return order


def _chunks(seq: Sequence[int], size: int) -> Iterable[list[int]]:
    for i in range(0, len(seq), max(1, size)):
        yield list(seq[i : i + size])


def _build_edge_lookup(
    skeletons: dict[str, Any],
) -> dict[str, tuple[str, tuple[float, float], tuple[float, float]]]:
    """One-time ``edge_id -> (layer_name, u, v)`` map, built from the
    skeleton geometry (independent of which nets are being batched).
    """
    lookup: dict[str, tuple[str, tuple[float, float], tuple[float, float]]] = {}
    for layer_name, skeleton in skeletons.items():
        for edge_id, u, v in canonical_channel_edges(skeleton.graph, layer_name):
            lookup[edge_id] = (layer_name, u, v)
    return lookup


def _shrink_channel_widths(
    channel_widths: dict[str, ChannelWidths],
    consumed: dict[str, float],
    edge_lookup: dict[str, tuple[str, tuple[float, float], tuple[float, float]]],
) -> dict[str, ChannelWidths]:
    """Return a copy of *channel_widths* with each consumed edge's
    capacity reduced by the width already committed to it by earlier
    batches (floored at 0 -- a fully consumed edge simply admits no more
    nets, rather than producing a negative/contradictory AtMostK bound).

    This is the batching-specific mechanism that makes the shared,
    physical "how much copper can this channel carry" resource — the one
    thing ``constraint_model.py`` actually encodes as a cross-net SAT
    constraint — hold across batch boundaries and not just within one
    batch's model.
    """
    if not consumed:
        return channel_widths

    deltas_by_layer: dict[str, dict[tuple[float, float], tuple[float, float]] | Any] = {}
    for edge_id, amount in consumed.items():
        if amount <= 0:
            continue
        loc = edge_lookup.get(edge_id)
        if loc is None:
            continue
        layer_name, u, v = loc
        deltas_by_layer.setdefault(layer_name, {})[(u, v)] = (
            deltas_by_layer.setdefault(layer_name, {}).get((u, v), 0.0) + amount
        )

    new_widths = dict(channel_widths)
    for layer_name, deltas in deltas_by_layer.items():
        widths = channel_widths.get(layer_name)
        if widths is None:
            continue
        new_edge_widths = dict(widths.edge_widths)
        for (u, v), amount in deltas.items():
            key = None
            if (u, v) in new_edge_widths:
                key = (u, v)
            elif (v, u) in new_edge_widths:
                key = (v, u)
            if key is None:
                continue
            new_edge_widths[key] = max(0.0, new_edge_widths[key] - amount)
        new_widths[layer_name] = replace(widths, edge_widths=new_edge_widths)
    return new_widths


def _topology_from_rust_result(rust_result: dict[str, Any]) -> dict[str, NetTopology]:
    out: dict[str, NetTopology] = {}
    for net_name, topo_data in rust_result.get("topology_graph", {}).items():
        path_edges = list(topo_data.get("path_graph", []))
        if path_edges:
            pg = nx.DiGraph()
            pg.add_edges_from(path_edges)
        else:
            pg = None
        out[net_name] = NetTopology(
            net_name=net_name,
            path_graph=pg,
            uses_channels=list(topo_data.get("uses_channels", [])),
            total_length_estimate=float(topo_data.get("total_length_estimate", 0)),
        )
    return out


def _consume_capacity(
    consumed: dict[str, float],
    topo_by_net: dict[str, NetTopology],
    nets_subset: Sequence[Net],
    design_rules: Any,
) -> None:
    if design_rules is None:
        return
    name_to_net = {n.name: n for n in nets_subset}
    for net_name, ntopo in topo_by_net.items():
        net = name_to_net.get(net_name)
        if net is None:
            continue
        rule = design_rules.get_rules_for_net(net.name)
        net_width = rule.trace_width_mm + rule.clearance_mm
        for edge_id in ntopo.uses_channels:
            consumed[edge_id] = consumed.get(edge_id, 0.0) + net_width


@dataclass
class NetBatchResult:
    """Per-batch measurement record (MEASURED fields, printed under
    ``TEMPER_BATCH_TRACE=1`` and returned to the caller for reporting).
    """

    batch_index: int
    net_names: list[str]
    status: str  # "sat" | "unsat" | "unknown" | "memory_error" | "crashed"
    primary_vars: int
    net_channel_vars: int
    via_vars: int
    constraints: int
    wall_s: float
    peak_rss_kb: int
    solved_at_batch_level: bool
    failed_nets: list[str] = field(default_factory=list)
    retried_singleton_nets: list[str] = field(default_factory=list)
    #: Nets whose *singleton* retry attempt (batch-level attempt AND retry)
    #: also died to a subprocess crash rather than being proven UNSAT --
    #: a strict subset of ``failed_nets``, kept separate so a reader can
    #: tell "we tried and it's infeasible" apart from "we never got a clean
    #: answer, even at singleton granularity."
    crashed_nets: list[str] = field(default_factory=list)
    #: True if the *batch-level* (not singleton-retry) subprocess attempt
    #: died without sending a result -- the crash-vs-UNSAT distinction the
    #: task asks be preserved. See the module docstring's "Crash vs. UNSAT"
    #: section.
    batch_crashed: bool = False
    crash_reason: str | None = None


def _trace_enabled() -> bool:
    return bool(os.environ.get("TEMPER_BATCH_TRACE"))


def _solve_subset(
    *,
    skeletons: dict[str, Any],
    nets_subset: Sequence[Net],
    channel_widths: dict[str, ChannelWidths],
    design_rules: Any,
    diff_pairs_subset: list[DiffPair],
    pcb: ParsedPCB,
    enable_geographic_pruning: bool,
    sat_conflict_limit: int | None,
    sat_time_limit_ms: int | None,
) -> tuple[ConstraintModel, dict[str, Any]]:
    from temper_rust_router import solve_topology_rust

    model_builder = ModelBuilder(
        skeletons=skeletons,
        nets=list(nets_subset),
        channel_widths=channel_widths,
        design_rules=design_rules,
        diff_pairs=diff_pairs_subset,
        pcb=pcb,
        enable_geographic_pruning=enable_geographic_pruning,
    )
    cm = model_builder.build()
    py_vars = list(cm.variables)
    py_cons = list(cm.constraints)
    net_names_subset = [n.name for n in nets_subset]
    rust_result = solve_topology_rust(
        py_vars,
        py_cons,
        net_names_subset,
        conflict_limit=sat_conflict_limit,
        time_limit_ms=sat_time_limit_ms,
    )
    return cm, rust_result


# --------------------------------------------------------------------------
# Subprocess-per-batch boundary.
#
# See the module docstring's "Subprocess-per-batch" section for the design
# rationale (what crosses the boundary and why, how crash is distinguished
# from UNSAT). This section is the mechanism.
# --------------------------------------------------------------------------


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
                "skeletons": skeletons,
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


def run_net_batched_stage3(
    pcb: ParsedPCB,
    stage2: Stage2Output,
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
    enable_geographic_pruning: bool = False,
    sat_conflict_limit: int | None = 20_000,
    sat_time_limit_ms: int | None = None,
    hub_blocks: frozenset[str] = HUB_BLOCKS,
    verbose: bool = False,
    subprocess_timeout_s: float = DEFAULT_SUBPROCESS_TIMEOUT_S,
) -> tuple[Stage3Output, list[NetBatchResult]]:
    """Stage 3 topological routing, batched over ``batch_size`` nets at a
    time, instead of one 22.5M-variable monolithic SAT model.

    See the module docstring for what this preserves (channel capacity,
    via explicit carry-forward bookkeeping) and what it deliberately does
    not touch (Stage 4's clearance-aware A*, which still runs once over
    every net after every batch here completes).

    **Failure handling** (task requirement: state and justify the chosen
    policy). If a batch's joint SAT model comes back UNSAT/unknown, this
    does **not** rip up and re-solve any *earlier* batch's already-fixed
    routes -- that is a materially larger engineering lift (a real
    negotiated-congestion rip-up-reroute loop with its own convergence
    concerns) that the reduction survey itself flagged as the expensive
    part of this option, and out of scope for a first prototype. Instead,
    the failed batch is retried **once**, decomposed into singleton
    (batch-of-1) models against the *same* already-shrunk capacity --
    i.e. more of a finer-grained placement attempt within what earlier
    batches already committed, not a renegotiation of it. Nets that still
    fail at singleton granularity are reported as batch-failed (recorded
    in the returned ``Stage3Output.degraded_nets`` and each
    ``NetBatchResult.failed_nets``) and are deliberately left with **no**
    topology entry -- Stage 4's existing, unmodified fallback path
    (``fallback_channel_path``, already exercised today by any net that
    Stage 3 doesn't produce topology for) picks them up via direct A* on
    the occupancy grid instead of SAT-guided channel routing. This reuses
    existing, already-tested pipeline machinery rather than inventing a
    second rip-up mechanism, at the honest cost that those specific nets
    get a degraded (non-SAT-optimal-topology) route rather than no route.

    **Subprocess isolation** (added in the follow-up to the first
    prototype run): every batch attempt, and every singleton retry, now
    runs its build+solve in a fresh child process rather than in this
    function's own process -- see the module docstring's
    "Subprocess-per-batch" section. A batch that crashes the subprocess
    (uncatchable Rust ``abort()``, OOM-killer SIGKILL, timeout) is recorded
    with ``status="crashed"`` -- distinct from ``"unsat"`` -- and, like a
    genuine UNSAT, is still given a singleton-retry chance rather than
    having all its nets silently dropped.
    """
    trace = _trace_enabled()
    t_total0 = time.perf_counter()

    skeletons = stage2.skeletons or {}
    channel_widths = stage2.channel_widths or {}
    nets = list(pcb.nets)
    net_names = [n.name for n in nets]
    all_diff_pairs = infer_differential_pairs(net_names)

    source_path = getattr(pcb, "source_path", None)
    order = order_nets_for_batching(nets, source_path, hub_blocks=hub_blocks)

    edge_lookup = _build_edge_lookup(skeletons)

    consumed: dict[str, float] = {}
    merged_topology: dict[str, NetTopology] = {}
    all_failed_nets: list[str] = []
    batch_results: list[NetBatchResult] = []

    n_batches_total = len(list(_chunks(order, batch_size)))
    if trace:
        print(
            f"[batch-trace] start: {len(nets)} nets, batch_size={batch_size}, "
            f"{n_batches_total} batches, hub_blocks={sorted(hub_blocks)}, "
            f"subprocess_timeout_s={subprocess_timeout_s}",
            file=sys.stderr,
            flush=True,
        )

    ctx_path = _write_shared_context(pcb, skeletons)
    try:
        for batch_index, idx_batch in enumerate(_chunks(order, batch_size)):
            batch_nets = [nets[i] for i in idx_batch]
            batch_names = {n.name for n in batch_nets}
            batch_diff_pairs = [
                p for p in all_diff_pairs if p.p_net in batch_names and p.n_net in batch_names
            ]
            shrunk_widths = _shrink_channel_widths(channel_widths, consumed, edge_lookup)

            t0 = time.perf_counter()
            batch_failed: list[str] = []
            crashed_nets: list[str] = []
            retried: list[str] = []

            outcome = _run_subset_subprocess(
                ctx_path=ctx_path,
                net_names=[n.name for n in batch_nets],
                channel_widths=shrunk_widths,
                diff_pairs_subset=batch_diff_pairs,
                enable_geographic_pruning=enable_geographic_pruning,
                sat_conflict_limit=sat_conflict_limit,
                sat_time_limit_ms=sat_time_limit_ms,
                timeout_s=subprocess_timeout_s,
            )

            batch_crashed = outcome.crashed
            crash_reason = outcome.crash_reason
            solved_at_batch_level = False
            n_net_channel = n_via = n_vars = n_cons = 0
            peak_rss_kb = outcome.external_peak_rss_kb

            if not outcome.crashed and outcome.result is not None:
                status = outcome.result["status"]
                n_net_channel = outcome.result["net_channel_vars"]
                n_via = outcome.result["via_vars"]
                n_vars = outcome.result["primary_vars"]
                n_cons = outcome.result["constraints"]
                peak_rss_kb = max(peak_rss_kb, outcome.result.get("peak_rss_kb", 0))
            else:
                status = "crashed"

            if status == "sat" and outcome.result is not None:
                solved_at_batch_level = True
                topo = _topology_from_rust_result(outcome.result)
                merged_topology.update(topo)
                _consume_capacity(consumed, topo, batch_nets, pcb.design_rules)
                for n in batch_nets:
                    if n.name not in topo:
                        batch_failed.append(n.name)
            else:
                # Batch UNSAT/unknown/memory_error/crashed: retry once at
                # singleton granularity, each singleton in its own fresh
                # subprocess. `consumed` (and therefore the per-net shrunk
                # capacity) is recomputed before EACH singleton solve, not
                # just once for the whole retry loop -- otherwise an
                # earlier singleton success within this same retry pass
                # would not be visible to a later singleton in the same
                # failed batch, and two nets could each be granted the
                # same now-scarce capacity. See the function docstring for
                # why singleton retry against currently-remaining
                # capacity, not a full rip-up of earlier batches -- and
                # the module docstring for why a *crashed* batch gets this
                # same recovery attempt rather than being written off.
                for n in batch_nets:
                    retried.append(n.name)
                    retry_widths = _shrink_channel_widths(channel_widths, consumed, edge_lookup)
                    single_outcome = _run_subset_subprocess(
                        ctx_path=ctx_path,
                        net_names=[n.name],
                        channel_widths=retry_widths,
                        diff_pairs_subset=[],
                        enable_geographic_pruning=enable_geographic_pruning,
                        sat_conflict_limit=sat_conflict_limit,
                        sat_time_limit_ms=sat_time_limit_ms,
                        timeout_s=subprocess_timeout_s,
                    )
                    peak_rss_kb = max(peak_rss_kb, single_outcome.external_peak_rss_kb)
                    if single_outcome.result is not None:
                        peak_rss_kb = max(peak_rss_kb, single_outcome.result.get("peak_rss_kb", 0))
                    if single_outcome.crashed:
                        crashed_nets.append(n.name)
                        batch_failed.append(n.name)
                        if trace:
                            print(
                                f"[batch-trace]   singleton retry crashed: "
                                f"net={n.name!r} reason={single_outcome.crash_reason}",
                                file=sys.stderr,
                                flush=True,
                            )
                        continue
                    rr1 = single_outcome.result
                    assert rr1 is not None
                    if rr1["status"] == "sat" and n.name in rr1.get("topology_graph", {}):
                        topo1 = _topology_from_rust_result(rr1)
                        merged_topology.update(topo1)
                        _consume_capacity(consumed, topo1, [n], pcb.design_rules)
                    else:
                        batch_failed.append(n.name)

            wall_batch = time.perf_counter() - t0
            all_failed_nets.extend(batch_failed)

            result = NetBatchResult(
                batch_index=batch_index,
                net_names=[n.name for n in batch_nets],
                status=status,
                primary_vars=n_vars,
                net_channel_vars=n_net_channel,
                via_vars=n_via,
                constraints=n_cons,
                wall_s=wall_batch,
                peak_rss_kb=peak_rss_kb,
                solved_at_batch_level=solved_at_batch_level,
                failed_nets=batch_failed,
                retried_singleton_nets=retried,
                crashed_nets=crashed_nets,
                batch_crashed=batch_crashed,
                crash_reason=crash_reason,
            )
            batch_results.append(result)

            if trace or verbose:
                print(
                    f"[batch-trace] batch={batch_index} nets={len(batch_nets)} "
                    f"status={status} batch_crashed={batch_crashed} "
                    f"crash_reason={crash_reason!r} batch_sat={solved_at_batch_level} "
                    f"vars={n_vars} (net_channel={n_net_channel}, via={n_via}) "
                    f"constraints={n_cons} wall_s={wall_batch:.2f} "
                    f"peak_rss_kb={peak_rss_kb} retried={len(retried)} "
                    f"crashed_nets={len(crashed_nets)} failed={len(batch_failed)}",
                    file=sys.stderr,
                    flush=True,
                )
    finally:
        try:
            os.unlink(ctx_path)
        except OSError:
            pass

    total_wall = time.perf_counter() - t_total0
    if trace or verbose:
        n_batches = len(batch_results)
        n_sat_batches = sum(1 for r in batch_results if r.solved_at_batch_level)
        n_crashed_batches = sum(1 for r in batch_results if r.batch_crashed)
        print(
            f"[batch-trace] done: {n_batches} batches, {n_sat_batches} solved "
            f"at batch level, {n_crashed_batches} batch-level crashes, "
            f"{len(all_failed_nets)}/{len(nets)} nets fell back to Stage 4's "
            f"existing no-topology path, total_wall_s={total_wall:.2f}",
            file=sys.stderr,
            flush=True,
        )

    stage3_output = Stage3Output(
        constraint_model=None,
        solution=None,
        topology_graph=TopologyGraph(net_topologies=merged_topology),
        aesthetic_preferences=[],
        degraded_nets=all_failed_nets,
        cegar_iterations=0,
        budget_used=0,
    )
    return stage3_output, batch_results
