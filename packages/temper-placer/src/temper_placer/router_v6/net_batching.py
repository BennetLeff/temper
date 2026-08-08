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
  constraint across batches" that is this module's own responsibility.
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
"""

from __future__ import annotations

import os
import re
import resource
import sys
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace
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
    status: str  # "sat" | "unsat" | "unknown" | "memory_error"
    primary_vars: int
    net_channel_vars: int
    via_vars: int
    constraints: int
    wall_s: float
    peak_rss_kb: int
    solved_at_batch_level: bool
    failed_nets: list[str] = field(default_factory=list)
    retried_singleton_nets: list[str] = field(default_factory=list)


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

    if trace:
        print(
            f"[batch-trace] start: {len(nets)} nets, batch_size={batch_size}, "
            f"{len(list(_chunks(order, batch_size)))} batches, "
            f"hub_blocks={sorted(hub_blocks)}",
            file=sys.stderr,
            flush=True,
        )

    for batch_index, idx_batch in enumerate(_chunks(order, batch_size)):
        batch_nets = [nets[i] for i in idx_batch]
        batch_names = {n.name for n in batch_nets}
        batch_diff_pairs = [
            p for p in all_diff_pairs if p.p_net in batch_names and p.n_net in batch_names
        ]
        shrunk_widths = _shrink_channel_widths(channel_widths, consumed, edge_lookup)

        t0 = time.perf_counter()
        batch_failed: list[str] = []
        retried: list[str] = []
        solved_at_batch_level = False
        status = "unknown"
        cm: ConstraintModel | None = None
        try:
            cm, rust_result = _solve_subset(
                skeletons=skeletons,
                nets_subset=batch_nets,
                channel_widths=shrunk_widths,
                design_rules=pcb.design_rules,
                diff_pairs_subset=batch_diff_pairs,
                pcb=pcb,
                enable_geographic_pruning=enable_geographic_pruning,
                sat_conflict_limit=sat_conflict_limit,
                sat_time_limit_ms=sat_time_limit_ms,
            )
            status = rust_result.get("status", "unknown")
            if status == "sat":
                solved_at_batch_level = True
                topo = _topology_from_rust_result(rust_result)
                merged_topology.update(topo)
                _consume_capacity(consumed, topo, batch_nets, pcb.design_rules)
                for n in batch_nets:
                    if n.name not in topo:
                        batch_failed.append(n.name)
            else:
                # Batch UNSAT/unknown: retry once at singleton granularity.
                # `consumed` (and therefore the per-net shrunk capacity) is
                # recomputed before EACH singleton solve, not just once for
                # the whole retry loop -- otherwise an earlier singleton
                # success within this same retry pass would not be visible
                # to a later singleton in the same failed batch, and two
                # nets could each be granted the same now-scarce capacity.
                # See the function docstring for why singleton retry
                # against currently-remaining capacity, not a full rip-up
                # of earlier batches.
                for n in batch_nets:
                    retried.append(n.name)
                    retry_widths = _shrink_channel_widths(channel_widths, consumed, edge_lookup)
                    try:
                        cm1, rr1 = _solve_subset(
                            skeletons=skeletons,
                            nets_subset=[n],
                            channel_widths=retry_widths,
                            design_rules=pcb.design_rules,
                            diff_pairs_subset=[],
                            pcb=pcb,
                            enable_geographic_pruning=enable_geographic_pruning,
                            sat_conflict_limit=sat_conflict_limit,
                            sat_time_limit_ms=sat_time_limit_ms,
                        )
                    except MemoryError:
                        batch_failed.append(n.name)
                        continue
                    if rr1.get("status") == "sat" and n.name in rr1.get("topology_graph", {}):
                        topo1 = _topology_from_rust_result(rr1)
                        merged_topology.update(topo1)
                        _consume_capacity(consumed, topo1, [n], pcb.design_rules)
                    else:
                        batch_failed.append(n.name)
        except MemoryError:
            status = "memory_error"
            batch_failed = [n.name for n in batch_nets]

        wall_batch = time.perf_counter() - t0
        peak_rss_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        all_failed_nets.extend(batch_failed)

        n_net_channel = 0
        n_via = 0
        n_vars = 0
        n_cons = 0
        if cm is not None:
            n_net_channel = sum(1 for v in cm.variables if type(v).__name__ == "NetChannelVar")
            n_via = sum(1 for v in cm.variables if type(v).__name__ == "ViaVar")
            n_vars = cm.variable_count
            n_cons = cm.constraint_count

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
        )
        batch_results.append(result)

        if trace or verbose:
            print(
                f"[batch-trace] batch={batch_index} nets={len(batch_nets)} "
                f"status={status} batch_sat={solved_at_batch_level} "
                f"vars={n_vars} (net_channel={n_net_channel}, via={n_via}) "
                f"constraints={n_cons} wall_s={wall_batch:.2f} "
                f"peak_rss_kb={peak_rss_kb} retried={len(retried)} "
                f"failed={len(batch_failed)}",
                file=sys.stderr,
                flush=True,
            )

    total_wall = time.perf_counter() - t_total0
    if trace or verbose:
        n_batches = len(batch_results)
        n_sat_batches = sum(1 for r in batch_results if r.solved_at_batch_level)
        print(
            f"[batch-trace] done: {n_batches} batches, {n_sat_batches} solved "
            f"at batch level, {len(all_failed_nets)}/{len(nets)} nets fell "
            f"back to Stage 4's existing no-topology path, total_wall_s="
            f"{total_wall:.2f}",
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
