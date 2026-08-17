"""
Router V6 Pipeline: Routing dispatch (Stages 3-5).

Extracted from ``_pipeline_stages.py`` — contains SAT topological
routing, geometric realization, and post-processing.

Phase E batch E6 (Rust Orchestration Engine plan 2026-08-09-001): the
portable orchestration — ``_select_sat_nets`` /
``_build_clause_origin`` / ``select_routing_grids`` — moved to
``temper-orchestration``'s ``pipeline_route.rs`` as the ``run_select_sat_nets`` /
``run_build_clause_origin`` / ``run_select_routing_grids`` pyfunctions; this
module keeps its public API as a thin FFI delegation (the shim marshals the
pcb/nets and model into the plain shapes the pyfunctions consume). The rest —
``_run_stage3`` / ``_run_stage4`` / ``_run_stage5`` /
``_augment_with_pcl_constraints`` — stays Python: it is the ortools /
CP-SAT-boundary glue (the net-batching branch is batch E5's owner, the
``temper_rust_router`` solve invocation is that package's surface, the
``ModelBuilder`` / ``BundleAnalyzer`` / ``TopologicalSolution`` /
``TopologyGraph`` / ``Stage4Orchestrator`` wiring is dataclass-construction
glue whose kernels are already Rust), argued in VERIFICATION.md. The oracle is
pinned verbatim as ``tests/router_v6/_pipeline_route_py_oracle.py``
(content-hash registered in ``scripts/oracle_hashes.json``).
"""

from __future__ import annotations

import logging
import os
from collections import defaultdict
from typing import Any, cast

import temper_orchestration as _to

from temper_placer.deterministic.state import BoardState
from temper_placer.router_v6._pipeline_types import (
    Stage2Output,
    Stage3Output,
    Stage4Output,
)
from temper_placer.router_v6.astar_pathfinding import PathfindingResult
from temper_placer.router_v6.channel_mapping import (
    ChannelMapping,
    expand_channel_path_terminals,
    fallback_channel_path,
    map_topology_to_channels,
)
from temper_placer.router_v6.constraint_model import (
    CapacityConstraint,
    ConstraintModel,
    DiffPairConstraint,
    LayerConstraint,
    ModelBuilder,
)
from temper_placer.router_v6.diff_pair_inference import infer_differential_pairs
from temper_placer.router_v6.escape_via_generator import EscapeVia
from temper_placer.router_v6.occupancy_grid import OccupancyGrid
from temper_placer.router_v6.routing_results import compile_routing_results
from temper_placer.router_v6.stage0_data import ParsedPCB
from temper_placer.router_v6.stage4_orchestrator import Stage4Orchestrator
from temper_placer.router_v6.topology_extraction import (
    NetTopology,
    PathGraph,
    TopologyGraph,
)
from temper_placer.router_v6.topology_solver import SolverStatus, TopologicalSolution
from temper_placer.router_v6.trace_width_assignment import assign_trace_widths
from temper_placer.router_v6.via_placement import drop_redundant_vias, place_vias


def _select_sat_nets(self, pcb: ParsedPCB) -> list[str] | None:
    """Select top N nets by ascending pin count for selective SAT routing.

    Phase E E6: the selection orchestration moved to
    ``temper_orchestration.pipeline_route::run_select_sat_nets`` (the dict
    first-insertion-order / last-writer-wins semantics and the stable sort
    replicate the oracle exactly); the shim marshals
    ``[(net.name, len(net.pins))]``.
    """
    nets = [(net.name, len(net.pins)) for net in pcb.nets]
    return _to.run_select_sat_nets(nets, self.max_sat_nets)


#: Stage 3 auto-batch threshold (2026-08-16, the Stage 3 memory fix's
#: option 1). The monolithic Stage 3 SAT model is exactly
#: ``|nets| x |edges|`` raw variables (verified exact in
#: ``docs/evidence/2026-08-15-stage3-memory-blowup-investigation.md``),
#: and the Sinz sequential-counter CNF encoding multiplies that by
#: ~17.7x CNF vars / ~34x clauses. On the production board (110 nets x
#: ~204K edges = ~22.5M raw vars) the monolith's CNF demand is
#: ~182-200 GB against a 62 GB machine and is OOM-killed at ~58 GB
#: inside ``encode_to_cnf`` before CaDiCaL even loads.
#:
#: 2.5M raw vars caps an attempted monolith's CNF demand at roughly
#: ~20-25 GB (survivable alone, never safe on a busy shared machine).
#: The initial 10M suggestion was rejected deliberately: 10M raw vars
#: extrapolates to ~80-88 GB demand -- an OOM on this machine by
#: construction, i.e. exactly the bug this threshold exists to prevent.
#: Test boards (<= ~2M raw vars) never trip it, so their monolith
#: behavior is unchanged.
_AUTO_BATCH_VAR_THRESHOLD = 2_500_000


def _estimate_stage3_model_vars(
    pcb: ParsedPCB,
    stage2: Stage2Output,
    net_filter: list[str] | None,
) -> int:
    """Estimate the monolithic Stage 3 model's raw variable count.

    ``ModelBuilder.create_per_net_channel_vars`` allocates one
    NetChannelVar per (net, edge) pair, so the raw model is exactly
    ``|nets| x |edges|`` variables (verified exact at two scales in the
    2026-08-15 memory-blowup investigation). ``|nets|`` is the number of
    nets in the model -- ``net_filter`` (selective SAT / ``max_sat_nets``)
    when set, else every net on the board. ``|edges|`` is the total
    skeleton edge count across layers (escape vias are obstacles and
    enlarge the skeleton, so they are included by construction here).
    Returns 0 when Stage 2 produced no skeletons.
    """
    if not stage2.skeletons:
        return 0
    n_nets = len(net_filter) if net_filter else len(pcb.nets)
    total_edges = sum(sk.edge_count for sk in stage2.skeletons.values())
    return n_nets * total_edges


def _augment_with_pcl_constraints(
    self,
    constraint_model: ConstraintModel,
    net_names: list[str],
    pcb: ParsedPCB,
    stage2: Stage2Output,
) -> ConstraintModel:
    """Augment the constraint model with lowered PCL constraints.

    Loads PCL constraint data from the PCB (if available), builds
    net-class metadata from design rules, resolves component-to-net
    indices, and invokes the Rust compiler to lower PCL constraints
    into InternalConstraint instances.

    The augmented model preserves all existing constraints; PCL
    constraints are additive.
    """
    try:
        from temper_constraint_compiler import (
            compile_pcl_constraints,  # type: ignore[import-untyped]
        )
    except ImportError:
        if self.verbose:
            print("    [PCL] temper_constraint_compiler not available; skipping")
        return constraint_model

    design_rules = getattr(pcb, "design_rules", None)
    net_classes = getattr(design_rules, "net_classes", {}) if design_rules else {}

    pcl_constraints_dicts: list[dict[str, Any]] = []
    zone_map: dict[str, dict[str, float]] = {}

    component_map: dict[str, int] = {}
    for i, net in enumerate(pcb.nets):
        if net.name in net_names:
            component_map[net.name] = i

    net_class_dicts: list[dict[str, Any]] = []
    seen_classes: set[str] = set()
    for cls_name, rules in net_classes.items():
        if cls_name in seen_classes:
            continue
        seen_classes.add(cls_name)
        entry = {
            "name": cls_name,
            "safety_category": getattr(rules, "safety_category", None),
            "clearance": getattr(rules, "clearance", 0.0),
            "creepage_mm": getattr(rules, "creepage_mm", 0.0),
            "required_layer": getattr(rules, "required_layer", None),
            "dru_priority": getattr(rules, "dru_priority", 0),
        }
        net_class_dicts.append(entry)

    skeletons_list: list[dict[str, Any]] = []
    for skeleton in stage2.skeletons or []:
        for edge in getattr(skeleton, "edges", []):
            skeletons_list.append(
                {
                    "net_a": str(edge[0]),
                    "net_b": str(edge[1]),
                    "channel_id": getattr(edge, "channel_id", str(edge[2]))
                    if len(edge) > 2
                    else "?",
                    "channel": getattr(edge, "channel_id", str(edge[2])) if len(edge) > 2 else "?",
                }
            )

    channel_widths_dict: dict[str, float] = {}
    for ch_id, cw in (stage2.channel_widths or {}).items():
        channel_widths_dict[str(ch_id)] = float(cw.avg_width) if cw.avg_width else 2.0

    if self.verbose:
        print(f"    [PCL] Compiling {len(pcl_constraints_dicts)} PCL constraints...")

    result = compile_pcl_constraints(
        pcl_constraints_dicts,
        net_class_dicts,
        component_map,
        zone_map,
        skeletons_list,
        channel_widths_dict,
        [],
        [],
        net_names,
    )

    num_lowered = result.get("num_lowered", 0)
    conflicts = result.get("conflicts", [])
    warnings_list = result.get("warnings", [])

    if self.verbose:
        print(f"    [PCL] Lowered {num_lowered} constraints")
        for w in warnings_list:
            print(f"    [PCL] Warning: {w}")
        for c in conflicts:
            print(f"    [PCL] Conflict: {c}")

    for lowered in result.get("constraints", []):
        ctype = lowered.get("type", "unknown")
        if ctype == "capacity":
            constraint_model.add_constraint(
                CapacityConstraint(
                    name=lowered.get("channel_id", "pcl_cap"),
                    channel_id=lowered.get("channel_id", ""),
                    capacity=lowered.get("capacity", 0.0),
                    slack_factor=lowered.get("slack_factor", 0.8),
                    terms=lowered.get("terms", []),
                )
            )
        elif ctype == "diff_pair":
            constraint_model.add_constraint(
                DiffPairConstraint(
                    name=lowered.get("channel_id", "pcl_diffpair"),
                    channel_id=lowered.get("channel_id", ""),
                    p_net_idx=0,
                    n_net_idx=0,
                    p_var=lowered.get("p_var_name", ""),
                    n_var=lowered.get("n_var_name", ""),
                )
            )
        elif ctype == "layer_restriction":
            constraint_model.add_constraint(
                LayerConstraint(
                    name=lowered.get("var_name", "pcl_layer"),
                    net_idx=0,
                    channel_id="",
                    allowed=lowered.get("allowed", True),
                )
            )

    return constraint_model


def _build_clause_origin(model: ConstraintModel) -> list[str]:
    """Build a clause-origin registry mapping CNF clause indices to constraint names.

    Each constraint in the model may produce multiple CNF clauses
    (e.g., AtMostK produces O(n*k) clauses). This function estimates
    the owner constraint for each clause position so that UNSAT core
    clause indices can be mapped back to constraint names.

    Returns:
        List where ``clause_origin[i]`` is the constraint name for clause i.

    Phase E E6: the registry computation moved to
    ``temper_orchestration.pipeline_route::run_build_clause_origin``; the
    ``ConstraintModel`` is passed through and the duck-typed attribute walk
    (``hasattr`` / truthiness / ``len``) mirrors the oracle exactly.
    """
    return _to.run_build_clause_origin(model)


def _run_stage3_direct(
    self,
    pcb: ParsedPCB,
    stage2: Stage2Output,
    target_names: list[str] | None = None,
) -> Stage3Output:
    """Stage 3 topological routing via the direct capacity-aware solver.

    Replaces the (vacuously satisfied, memory-infeasible) monolithic SAT
    model with ``temper_rust_router.solve_topology_direct_py``: each net's
    pads are snapped to the nearest skeleton node and a capacity-aware
    shortest path is computed between consecutive pads; edges whose
    remaining width cannot carry the net are blocked, so later nets
    re-route around congested channels. Every net receives a **real**
    topology (the connectivity the SAT model never forced), capacity is
    enforced by construction, and the CNF that cost 182-200 GB at full
    scale is never built.

    The output shape is identical to the SAT path's ``topology_graph``, so
    Stage 4's ``map_topology_to_channels`` consumes it unchanged. Nets that
    cannot be routed within capacity (or whose pads lie outside the
    skeleton's reachable component) are reported in ``degraded_nets`` and
    fall through to Stage 4's existing ``fallback_channel_path`` A* path —
    the same honest degraded handling the net-batching path uses.

    ``target_names`` (the ``max_sat_nets`` selective cap): when set, only
    the named nets receive topology; every other net falls through to
    Stage 4's unguided A* fallback, preserving the documented selective-SAT
    semantic.
    """
    from temper_placer.router_v6._pipeline_grid import _net_pad_positions
    from temper_placer.router_v6.constraint_model import _stage3_mem_trace
    from temper_placer.router_v6.net_batching import HUB_BLOCKS, order_nets_for_batching
    from temper_rust_router import solve_topology_direct_py

    if self.verbose:
        print("  3.1-3.6: Direct capacity-aware topology solve (no SAT model)...")

    skeletons = stage2.skeletons or {}
    channel_widths = stage2.channel_widths or {}
    design_rules = getattr(pcb, "design_rules", None)
    nets = list(pcb.nets)
    source_path = getattr(pcb, "source_path", None)

    # Batching order (low fan-out first, hubs last, diff pairs adjacent):
    # easy nets commit their channel capacity first, so contentious nets
    # re-route around what is already committed — the same priority the
    # net-batching path applies, and fully deterministic.
    order = order_nets_for_batching(nets, source_path, hub_blocks=HUB_BLOCKS)
    comp_by_ref = {c.ref: c for c in pcb.components}

    net_names: list[str] = []
    pads_by_net: list[list[tuple[float, float]]] = []
    widths_by_net: list[float] = []
    for i in order:
        net = nets[i]
        if target_names is not None and net.name not in target_names:
            continue
        pads = _net_pad_positions(net, comp_by_ref)
        width = 0.0
        if design_rules is not None:
            rule = design_rules.get_rules_for_net(net.name)
            width = rule.trace_width_mm + rule.clearance_mm
        net_names.append(net.name)
        pads_by_net.append(pads)
        widths_by_net.append(width)

    # Skeleton edges with per-layer channel widths (capacity). Mirrors the
    # Rust model builder's lookup: `edge_widths.get((u, v))` with a
    # reversed-key fallback, missing/zero width => no capacity constraint.
    edges: list[tuple[str, tuple[float, float], tuple[float, float], float]] = []
    for layer_name, skeleton in skeletons.items():
        cw = channel_widths.get(layer_name)
        edge_widths = cw.edge_widths if cw is not None else {}
        for u, v in skeleton.graph.edges:
            cap = edge_widths.get((u, v))
            if cap is None:
                cap = edge_widths.get((v, u), 0.0)
            edges.append((layer_name, u, v, float(cap)))

    _stage3_mem_trace(
        f"_run_stage3_direct solve_topology_direct_py ENTER "
        f"(nets={len(net_names)} edges={len(edges)})"
    )
    rust_result = solve_topology_direct_py(
        net_names,
        pads_by_net,
        widths_by_net,
        edges,
    )
    _stage3_mem_trace("_run_stage3_direct solve_topology_direct_py EXIT")

    # Post-condition violations are the direct analog of `audit_result`:
    # raise, don't warn (same contract as the SAT path's audit).
    violations = list(rust_result.get("post_condition_violations", []))
    if violations:
        msg = (
            f"Direct topology solver produced {len(violations)} post-condition "
            f"violation(s): {violations}"
        )
        raise RuntimeError(msg)

    if self.verbose:
        stats = rust_result.get("solver_stats", {})
        print(
            f"    Direct topology: {stats.get('nets_routed', 0)} nets routed, "
            f"{stats.get('nets_unrouted', 0)} unrouted, "
            f"{stats.get('total_channel_refs', 0)} channel references over "
            f"{stats.get('total_edges', 0)} edges, "
            f"{rust_result.get('solver_time_ms', 0.0):.1f} ms"
        )

    topology_graph = TopologyGraph(net_topologies={})
    for net_name, topo_data in rust_result.get("topology_graph", {}).items():
        path_edges = list(topo_data.get("path_graph", []))
        if path_edges:
            pg = PathGraph(path_edges)
        else:
            pg = None
        ntopo = NetTopology(
            net_name=net_name,
            path_graph=pg,
            uses_channels=list(topo_data.get("uses_channels", [])),
            total_length_estimate=float(topo_data.get("total_length_estimate", 0)),
        )
        topology_graph.net_topologies[net_name] = ntopo

    degraded_nets = list(rust_result.get("unrouted_nets", []))
    if self.verbose:
        print(f"    Direct topology: {len(topology_graph.net_topologies)} nets assigned, {len(degraded_nets)} degraded")

    return Stage3Output(
        constraint_model=None,
        solution=None,
        topology_graph=topology_graph,
        aesthetic_preferences=[],
        degraded_nets=degraded_nets,
        cegar_iterations=0,
        budget_used=0,
    )


def _run_stage3(self, pcb: ParsedPCB, stage2: Stage2Output) -> Stage3Output:
    """Run Stage 3: Topological Routing."""
    from temper_placer.router_v6.constraint_model import (
        _stage3_mem_trace,
    )

    _stage3_mem_trace("_run_stage3 ENTER")

    net_names = [net.name for net in pcb.nets]
    diff_pairs = infer_differential_pairs(net_names)

    # `_select_sat_nets` computes the top-N nets for selective SAT routing.
    # It used to be print-only: the model below encoded EVERY net and the
    # Stage 3 CNF blew up at |nets| x |edges| (the 2026-08-15 Stage 3
    # memory-blowup investigation -- 182-200 GB monolith demand). The
    # filtered list is now threaded into ModelBuilder as `net_filter` so
    # only the selected nets get variables / capacity terms, and into
    # solve_topology_rust so the reported topology covers exactly the
    # selected nets. Non-selected nets fall through to Stage 4's existing
    # `fallback_channel_path` A* path (the same path nets the solver
    # leaves unassigned take today).
    target_names = (
        self._select_sat_nets(pcb) if self.max_sat_nets and not self.enable_bundling else None
    )

    # `#871` net-batching prototype: solve Stage 3's SAT model in batches
    # of `self.net_batch_size` nets instead of one monolithic model.
    # Checked first/takes priority over enable_bundling/max_sat_nets --
    # see RouterV6Pipeline.__init__'s enable_net_batching docstring.
    use_net_batching = bool(getattr(self, "enable_net_batching", False))

    # 2026-08-16 vacuity fix (docs/evidence/2026-08-16-sat-capacity-vacuity-fix.md,
    # and this task's measurement summary in
    # docs/evidence/2026-08-16-sat-vacuity-noop-vs-direct-solver.md):
    # the SAT model is structurally vacuous (nothing forces a `NetChannelVar`
    # true — every solve returns "0 conflicts, 0 decisions" and an empty
    # topology) AND its monolith cannot fit in memory (110 nets × 204,144
    # edges → ~399M Sinz aux vars / ~768M clauses ≈ 182-200 GB on this
    # board).
    #
    # Two candidate fixes were implemented and measured: (1) a direct
    # capacity-aware solver (solve_topology_direct_py, merged as #1260)
    # and (2) a structural no-op (this branch). On the production board
    # and the 33-net fixture, both produce **byte-identical routed
    # output** (same md5, same 88/139 pad-connected, same segments/vias/
    # zones, same ~243 s wall) — the direct solver's emitted topology
    # guidance changes nothing about Stage 4's occupancy-grid A* routes on
    # this board (it emits zero topology on the fixture). The measured
    # batched baseline (89-92/139 pad-connected) was itself produced by
    # the vacuous SAT = empty topology = the same fallback-A* behavior a
    # no-op Stage 3 yields.
    #
    # The default (non-batched, non-bundling) Stage 3 path is therefore a
    # structural no-op: the empty Stage3Output below makes Stage 4 route
    # every net through its existing `fallback_channel_path` A* — exactly
    # the behavior the vacuous SAT produced, without building any CNF at
    # all. This reproduces the measured batched baseline byte-for-byte
    # with Stage 3 adding ~0 memory, in the same wall time as the merged
    # direct solver. The SAT paths remain reachable: net-batching
    # (above), `enable_bundling` (below), or the
    # `TEMPER_STAGE3_FORCE_SAT=1` env escape hatch.
    if (
        not use_net_batching
        and not self.enable_bundling
        and not os.environ.get("TEMPER_STAGE3_FORCE_SAT")
    ):
        if self.verbose:
            print("Stage 3: Topological routing... SKIPPED (SAT structurally vacuous; Stage 4 A* routes directly)")
        return Stage3Output(
            constraint_model=None,
            solution=None,
            topology_graph=None,
            aesthetic_preferences=[],
            degraded_nets=[],
            cegar_iterations=0,
            budget_used=0,
        )

    # 2026-08-16 auto-batch safety net (Stage 3 memory fix, option 1):
    # when batching was NOT explicitly requested and the caller is not
    # already reducing the model via bundling or geographic pruning, the
    # default is the monolithic path -- which on this board (110 nets x
    # ~204K edges = ~22.5M raw vars) demands ~182-200 GB and is
    # OOM-killed at ~58 GB before CaDiCaL even loads. Estimate the raw
    # variable count and route through the batched path (the documented
    # production recipe) instead of attempting an OOM. Callers that
    # genuinely want the monolith on a large board can shrink the model
    # below the threshold with max_sat_nets (the estimate honors the
    # selective-SAT subset).
    #
    # Only the SAT monolith paths can still OOM (the direct solver above
    # never builds a model), so this net is reachable only via
    # `enable_bundling` or `TEMPER_STAGE3_FORCE_SAT=1` -- which is
    # exactly where the safety net is still needed.
    if (
        not use_net_batching
        and not self.enable_bundling
        and not self.enable_geographic_pruning
    ):
        est_vars = _estimate_stage3_model_vars(pcb, stage2, target_names)
        if est_vars > _AUTO_BATCH_VAR_THRESHOLD:
            logging.getLogger(__name__).warning(
                "Stage 3 monolithic model would be ~%d raw variables "
                "(|nets| x |edges|), above the auto-batch threshold (%d). "
                "Routing through net-batching (batch_size=%d) instead of "
                "the OOMing monolith. Pass enable_net_batching=True "
                "explicitly, or max_sat_nets to shrink the model below the "
                "threshold, to control this. See "
                "docs/evidence/2026-08-15-stage3-memory-blowup-"
                "investigation.md.",
                est_vars,
                _AUTO_BATCH_VAR_THRESHOLD,
                self.net_batch_size,
            )
            use_net_batching = True

    if use_net_batching:
        from temper_placer.router_v6.net_batching import run_net_batched_stage3

        stage3_output, batch_results = run_net_batched_stage3(
            pcb,
            stage2,
            batch_size=self.net_batch_size,
            enable_geographic_pruning=self.enable_geographic_pruning,
            sat_conflict_limit=self.sat_conflict_limit,
            sat_time_limit_ms=self.sat_time_limit_ms,
            verbose=self.verbose,
        )
        self.last_batch_results = batch_results
        return stage3_output

    net_names = [net.name for net in pcb.nets]
    diff_pairs = infer_differential_pairs(net_names)

    if self.verbose:
        print("  3.1-3.6: Building constraint model...")

    if self.enable_bundling:
        assert stage2.skeletons is not None, "Stage 2 skeletons required for bundling"
        from temper_placer.router_v6.bundle_analyzer import BundleAnalyzer

        bundle_analyzer = BundleAnalyzer(
            nets=pcb.nets,
            skeletons=stage2.skeletons,
            design_rules=pcb.design_rules,
            diff_pairs=diff_pairs,
            pcb=pcb,
        )
        bundle_manifest = bundle_analyzer.analyze()

        if self.verbose:
            print(
                f"    Bundle analysis: {bundle_manifest.bundle_count} bundle classes "
                f"for {len(pcb.nets)} nets"
            )

        model_builder = ModelBuilder(
            skeletons=stage2.skeletons,
            nets=pcb.nets,
            channel_widths=stage2.channel_widths,
            design_rules=pcb.design_rules,
            diff_pairs=diff_pairs,
            pcb=pcb,
            enable_bundling=True,
            bundle_manifest=bundle_manifest,
            enable_geographic_pruning=self.enable_geographic_pruning,
            net_filter=target_names,
        )
        constraint_model = model_builder.build()
    else:
        model_builder = ModelBuilder(
            skeletons=stage2.skeletons,
            nets=pcb.nets,
            channel_widths=stage2.channel_widths,
            design_rules=pcb.design_rules,
            diff_pairs=diff_pairs,
            pcb=pcb,
            enable_geographic_pruning=self.enable_geographic_pruning,
            net_filter=target_names,
        )
        constraint_model = model_builder.build()
        bundle_manifest = None

    _stage3_mem_trace("_run_stage3 ModelBuilder.build() done")

    if os.environ.get("TEMPER_PCL_CONSTRAINTS"):
        constraint_model = self._augment_with_pcl_constraints(
            constraint_model, net_names, pcb, stage2
        )

    if self.verbose and target_names:
        print(f"    Selective SAT: top {len(target_names)} nets = {sorted(target_names)}")

    if self.verbose:
        print("  3.8: Solving topology (Rust)...")

    py_vars = list(constraint_model.variables)
    py_cons = list(constraint_model.constraints)

    if self.enable_bundling and bundle_manifest is not None:
        from temper_rust_router import solve_topology_rust_bundled

        manifest_dict = {
            "bundles": [
                {
                    "bundle_id": b.bundle_id,
                    "net_indices": b.net_indices,
                    "constraint_types": list(b.constraint_types),
                    "is_diff_pair": b.is_diff_pair,
                }
                for b in bundle_manifest.bundles.values()
            ],
            "bundle_id_for_net": dict(bundle_manifest.bundle_id_for_net),
            "unbundled_net_indices": bundle_manifest.unbundled_net_indices,
        }
        rust_result = solve_topology_rust_bundled(py_vars, py_cons, manifest_dict, net_names)
        cegar_iterations = int(rust_result.get("cegar_iterations", 0))
        budget_used = int(rust_result.get("budget_used", 0))
        degraded_nets = list(rust_result.get("degraded_nets", []))
        aesthetic_preferences: list = []
    else:
        from temper_rust_router import solve_topology_rust

        _stage3_mem_trace(
            f"_run_stage3 solve_topology_rust ENTER "
            f"(py_vars={len(py_vars)} py_cons={len(py_cons)})"
        )
        # `target_names` (the selective-SAT subset) when active, else the
        # full net list -- the topology output then covers exactly the nets
        # the model encodes; unselected nets fall through to Stage 4's
        # fallback A* path (map_topology_to_channels drops nets with no
        # channel sequence before Stage 4's fallback_channel_path fires).
        rust_result = solve_topology_rust(
            py_vars,
            py_cons,
            target_names if target_names is not None else net_names,
            conflict_limit=self.sat_conflict_limit,
            time_limit_ms=self.sat_time_limit_ms,
        )
        _stage3_mem_trace("_run_stage3 solve_topology_rust EXIT")
        cegar_iterations = 0
        budget_used = 0
        degraded_nets = []
        aesthetic_preferences = []

    tensions = rust_result.get("tensions", [])
    for t in tensions:
        sev = t.get("severity", "unknown")
        expl = t.get("explanation", "")
        ch = t.get("channel_id", "")
        if sev == "hard_conflict":
            if self.verbose:
                print(f"    PRE-SOLVE HARD CONFLICT on channel {ch}: {expl}")
        elif sev == "capacity_warning" and self.verbose:
            print(f"    PRE-SOLVE CAPACITY WARNING on channel {ch}: {expl}")

    if self.verbose:
        print(
            f"    SAT model: {rust_result.get('num_vars', 0)} vars, "
            f"{rust_result.get('num_clauses', 0)} clauses"
        )

    if rust_result["status"] == "sat":
        status = SolverStatus.SATISFIABLE
    elif rust_result["status"] == "unsat":
        status = SolverStatus.UNSATISFIABLE
    else:
        status = SolverStatus.UNKNOWN

    solution = TopologicalSolution(
        status=status,
        assignment=dict(rust_result["assignments"]),
        solver_time_ms=float(rust_result.get("solver_time_ms", 0)),
        solver_stats=rust_result.get("solver_stats"),
        var_to_net=rust_result.get("var_to_net"),
    )

    clause_origin = _build_clause_origin(constraint_model)
    _stage3_mem_trace(
        f"_run_stage3 _build_clause_origin done "
        f"(origins={len(clause_origin)})"
    )
    if rust_result["status"] == "unsat":
        core_indices = rust_result.get("unsat_core", [])
        unsat_core_names = []
        for idx in core_indices:
            if 0 <= idx < len(clause_origin):
                unsat_core_names.append(clause_origin[idx])
        solution.unsat_core = unsat_core_names

    topology_graph = TopologyGraph(net_topologies={})
    for net_name, topo_data in rust_result.get("topology_graph", {}).items():
        path_edges = list(topo_data.get("path_graph", []))
        if path_edges:
            pg = PathGraph(path_edges)
        else:
            pg = None

        ntopo = NetTopology(
            net_name=net_name,
            path_graph=pg,
            uses_channels=list(topo_data.get("uses_channels", [])),
            total_length_estimate=float(topo_data.get("total_length_estimate", 0)),
        )
        topology_graph.net_topologies[net_name] = ntopo

    if rust_result["status"] == "unsat":
        conflict = rust_result.get("conflicts")
        if conflict:
            import logging as _log_unsat

            _logger_unsat = _log_unsat.getLogger(__name__)
            _logger_unsat.info("UNSAT CONFLICT: %s", conflict.get("explanation", ""))
            _logger_unsat.info("  Constraints: %s", conflict.get("conflicting_constraints", []))
            _logger_unsat.info("  Channels: %s", conflict.get("channels_involved", []))
            _logger_unsat.info("  Core clauses: %d", conflict.get("core_clause_count", 0))
            if self.verbose:
                print(
                    f"    UNSAT CONFLICT: {conflict.get('explanation', '')}\n"
                    f"      Constraints: {conflict.get('conflicting_constraints', [])}\n"
                    f"      Channels: {conflict.get('channels_involved', [])}\n"
                    f"      Core clauses: {conflict.get('core_clause_count', 0)}"
                )
        elif self.verbose:
            print("    UNSAT: No conflict report available (core extraction failed)")

    if rust_result["status"] == "sat":
        from temper_rust_router import audit_result

        audit_violations = list(
            audit_result(
                py_vars,
                py_cons,
                dict(rust_result.get("assignments", {})),
                net_names,
            )
        )
        if audit_violations:
            msg = f"Rust solver produced {len(audit_violations)} constraint violation(s): {audit_violations}"
            if self.verbose:
                print(f"    WARNING: {msg}")
            raise RuntimeError(msg)
        elif self.verbose:
            print("    Constraint audit: clean (0 violations)")
    elif rust_result["status"] == "unknown":
        if self.verbose:
            print("    Solver status: UNKNOWN (timeout/internal error)")

    if self.verbose:
        if solution.is_satisfiable:
            print(f"    Solution found (SAT) in {solution.solver_time_ms:.1f}ms")
        elif rust_result["status"] == "unsat":
            print(f"    No solution found (UNSAT) in {solution.solver_time_ms:.1f}ms")
        elif rust_result["status"] == "unknown":
            print(f"    Solver result: UNKNOWN in {solution.solver_time_ms:.1f}ms")

    return Stage3Output(
        constraint_model=constraint_model,
        solution=solution,
        topology_graph=topology_graph,
        aesthetic_preferences=aesthetic_preferences,
        degraded_nets=degraded_nets,
        cegar_iterations=cegar_iterations,
        budget_used=budget_used,
    )


def select_routing_grids(
    occupancy_grids: dict[str, OccupancyGrid] | None,
) -> tuple[OccupancyGrid, OccupancyGrid | None]:
    """Pick the (primary, alternate) occupancy grids handed to A*.

    Outer layers are preferred because most boards route on them, but they are
    only *preferences*: a board whose F.Cu/B.Cu carry copper pours has those
    layers classified as planes (``_parse_board.py``), so they get no routing
    space and therefore no occupancy grid at all, and routing happens on the
    inner layers instead.

    The alternate must be a different *layer* from the primary.  Selecting it
    by excluding the literal name ``"F.Cu"`` — rather than the primary grid's
    actual layer — returned the primary grid a second time on exactly those
    plane-outer boards, so the router was handed one layer twice and the
    second real inner layer was dropped before pathfinding ever saw it.

    Phase E E6: the selection orchestration moved to
    ``temper_orchestration.pipeline_route::run_select_routing_grids`` (the
    ``or`` truthiness fallback and the alternate-excludes-primary-LAYER rule
    replicate the oracle exactly); the original grid objects are returned
    unchanged.
    """
    return _to.run_select_routing_grids(occupancy_grids)


def _run_stage4(
    self,
    pcb: ParsedPCB,
    stage2: Stage2Output,
    stage3: Stage3Output,
    escape_vias: list[EscapeVia] | None = None,
) -> Stage4Output:
    """Run Stage 4: Geometric Realization with multi-layer support."""
    from temper_placer.router_v6._pipeline_grid import _last_skeleton, _net_pad_positions
    from temper_placer.router_v6.astar_pathfinding import run_astar_pathfinding

    escape_vias_map: dict[str, list[tuple[float, float, float]]] = defaultdict(list)
    for v in escape_vias or ():
        escape_vias_map[v.net_name].append((v.position[0], v.position[1], v.diameter))

    if self.verbose:
        print("  4.1: Setting up channel mapping...")

    assert stage2.skeletons is not None, "Stage 2 skeletons required for Stage 4"
    fcu_skeleton = stage2.skeletons.get("F.Cu") or next(iter(stage2.skeletons.values()), None)
    stage2.skeletons.get("B.Cu") or _last_skeleton(stage2.skeletons)

    if fcu_skeleton is not None:
        channel_mapping = map_topology_to_channels(
            stage3.topology_graph,
            fcu_skeleton,
            layer_constraints=self.layer_constraints,
        )
    else:
        channel_mapping = ChannelMapping(channel_paths={})

    comp_by_ref = {c.ref: c for c in pcb.components}
    for net in pcb.nets:
        pads = _net_pad_positions(net, comp_by_ref)
        if len(pads) < 2:
            continue
        existing_path = channel_mapping.channel_paths.get(net.name)
        if existing_path is None:
            channel_mapping.channel_paths[net.name] = fallback_channel_path(
                net.name,
                pads,
                self.layer_constraints,
                enable_all_pad_tree=self.enable_all_pad_tree,
            )
        else:
            channel_mapping.channel_paths[net.name] = expand_channel_path_terminals(
                existing_path,
                pads,
                enable_all_pad_tree=self.enable_all_pad_tree,
            )

    if self.enable_all_pad_tree:
        from temper_placer.router_v6.terminal_extraction import extract_net_terminals
        from temper_placer.router_v6.terminal_tree import TreeTerminal, plan_terminal_tree

        for net in pcb.nets:
            channel_path = channel_mapping.channel_paths.get(net.name)
            if channel_path is None:
                continue
            terminals = extract_net_terminals(pcb, net.name, net.pins)
            if len(terminals) < 3:
                continue
            channel_path.terminals = terminals
            channel_path.terminal_tree = plan_terminal_tree(
                cast("tuple[TreeTerminal, ...]", terminals)
            )

    if self.verbose:
        print("  4.2: Running A* pathfinding (orchestrated)...")

    thermal_field = None
    if self.thermal_flat is not None and self.thermal_weight > 0.0:
        from temper_placer.fields.interface import CostFieldInput

        thermal_field = CostFieldInput(
            cost_flat=self.thermal_flat,
            weight=self.thermal_weight,
        )

    orchestrated = Stage4Orchestrator(verbose=self.verbose)
    state = BoardState(
        _parsed_pcb=pcb,
        channel_mapping=channel_mapping,
        escape_vias_map=escape_vias_map,
        enable_theta_star=self.enable_theta_star,
        enable_lazy_theta_star=self.enable_lazy_theta_star,
        congestion_weight=self.congestion_weight,
        thermal_field=thermal_field,
        enable_coarse_to_fine=self.enable_coarse_to_fine,
        enable_all_pad_tree=self.enable_all_pad_tree,
        coarse_factor=self.coarse_factor,
        corridor_buffer_cells=self.corridor_buffer_cells,
    )
    pathfinding_result = orchestrated.assemble_pathfinding_result(state)

    # Restrict the grids A* is ever handed to the board's *routable signal*
    # layers -- the declared-``signal``-role set intersected with the
    # router's real engine capability (``core.board_layer_roles.
    # routable_signal_layers_from_path``), not every grid Stage 2 happened
    # to build. This matters because Stage 2's occupancy-grid construction
    # (``routing_space.py``) classifies a layer routable from
    # ``pcb.stackup.layers[*].layer_type in {"signal", "mixed"}``, and on
    # today's production board (net-batching's ``use_declared_layer_roles=
    # True`` parse) that MIXED bucket also catches ``In1.Cu``/``In2.Cu`` --
    # declared ``power`` planes for GND/PWR distribution, not general
    # signal-routing targets -- purely because nothing is poured on them
    # yet (see docs/evidence/2026-08-13-router-nlayer-routing.md Sec 3).
    # Feeding those two straight to A* would let the router place ordinary
    # signal traces on a plane layer; filtering to the declared-signal set
    # here is what keeps that from happening while still letting every
    # declared signal layer (F.Cu, In3.Cu, In4.Cu, B.Cu) through.
    all_grids = stage2.occupancy_grids or {}
    routable_layers = _routable_signal_layers_for_pcb(pcb)
    available_grids = {name: g for name, g in all_grids.items() if name in routable_layers}
    if not available_grids:
        # No declared-signal layer got a Stage 2 grid at all (e.g. a
        # synthetic/test board whose stackup doesn't match the SSOT
        # accessor's expectations) -- fail open to whatever Stage 2 built
        # rather than silently routing zero nets, matching this function's
        # pre-existing behavior for boards outside the production shape.
        available_grids = all_grids

    use_nlayer = self.enable_nlayer_astar_spike or len(available_grids) > 2

    if pathfinding_result is None and use_nlayer:
        # Routes through _astar_nlayer.py's N-layer, via-aware
        # generalization (see docs/evidence/2026-08-08-nlayer-via-astar-spike.md
        # for its original spike writeup) instead of the legacy
        # 2-grid-capped path below. Triggered automatically whenever more
        # than 2 routable signal layers are available -- not just behind
        # the opt-in ``enable_nlayer_astar_spike`` flag, which callers may
        # still set explicitly to force this path on a 2-layer board.
        from temper_placer.router_v6._astar_nlayer import (
            run_astar_pathfinding_nlayer,
            select_routing_grids_nlayer,
        )

        nlayer_grids = select_routing_grids_nlayer(available_grids)
        if self.single_layer:
            first_layer = next(iter(nlayer_grids))
            nlayer_grids = {first_layer: nlayer_grids[first_layer]}

        pathfinding_result = run_astar_pathfinding_nlayer(
            channel_mapping,
            nlayer_grids,
            pcb.design_rules,
            pcb=pcb,
            escape_vias_map=escape_vias_map,
            use_theta_star=self.enable_theta_star,
            use_lazy_theta_star=self.enable_lazy_theta_star,
            max_nets=self.max_nets,
            target_nets=self.target_nets,
            max_iter=self.max_iter,
            enable_coarse_to_fine=self.enable_coarse_to_fine,
            coarse_factor=self.coarse_factor,
            corridor_buffer_cells=self.corridor_buffer_cells,
            # 2026-08-16 width-aware C-space: per-net-width grid families
            # rebuilt from the Stage-2 routing spaces (each family erodes
            # its static layer by width/2 + clearance instead of the flat
            # 0.1mm default) -- see _astar_nlayer.py's family helpers.
            routing_spaces=stage2.routing_spaces,
        )
    elif pathfinding_result is None:
        fcu_grid, bcu_grid = select_routing_grids(available_grids)

        pathfinding_result = run_astar_pathfinding(
            channel_mapping,
            fcu_grid,
            pcb.design_rules,
            alternate_grid=None if self.single_layer else bcu_grid,
            pcb=pcb,
            escape_vias_map=escape_vias_map,
            use_theta_star=self.enable_theta_star,
            use_lazy_theta_star=self.enable_lazy_theta_star,
            max_nets=self.max_nets,
            target_nets=self.target_nets,
            max_iter=self.max_iter,
            enable_coarse_to_fine=self.enable_coarse_to_fine,
            coarse_factor=self.coarse_factor,
            corridor_buffer_cells=self.corridor_buffer_cells,
            enforce_all_pad_tree=self.enable_all_pad_tree,
        )

    return self._run_stage5(pcb, stage2, pathfinding_result)


def _routable_signal_layers_for_pcb(pcb: ParsedPCB) -> frozenset[str]:
    """The board's routable signal layers per the stackup SSOT.

    Reads through ``core.board_layer_roles.routable_signal_layers_from_path``
    -- the board's own declared ``(layers ...)`` role tokens intersected
    with :data:`core.board_layer_roles.ENGINE_SUPPORTED_SIGNAL_LAYERS` --
    rather than any hardcoded layer-name literal, so a stackup edit
    propagates here automatically. Falls back to the engine-capability set
    alone when ``pcb`` has no real ``source_path`` on disk (synthetic/test
    fixtures) or the file can't be parsed for its declared roles.
    """
    from temper_placer.core.board_layer_roles import (
        ENGINE_SUPPORTED_SIGNAL_LAYERS,
        routable_signal_layers_from_path,
    )

    source_path = getattr(pcb, "source_path", None)
    if source_path:
        try:
            layers = routable_signal_layers_from_path(source_path)
            if layers:
                return frozenset(layers)
        except (OSError, ValueError):
            pass
    return ENGINE_SUPPORTED_SIGNAL_LAYERS


def _run_stage5(
    self,
    pcb: ParsedPCB,
    stage2: Stage2Output,  # noqa: ARG001
    pathfinding_result: PathfindingResult,
) -> Stage4Output:
    """Run Stage 5: Post-processing (smoothing, via placement, width, results)."""
    if self.verbose:
        print("Stage 5: Post-processing...")

    if self.verbose:
        print("  4.3: Placing vias...")
    via_placement = place_vias(
        pathfinding_result,
        pcb.design_rules.default_via_diameter_mm,
        pcb.design_rules.default_via_drill_mm,
        design_rules=pcb.design_rules,
    )
    # FIXED 2026-08-17 (docs/evidence/2026-08-17-blind-via-annular-floor-
    # fix.md): a DIFFERENT root cause than the annular-ring floor, sharing
    # only a coincidental origin (the newer via-emitting code paths this
    # module and the N-layer pathfinder cover) -- a via placed at the
    # exact same point as another via on the same net, or on top of an
    # existing PTH/THT pad of its own net, whose plating already provides
    # every layer transition the via would. Connectivity-neutral to drop
    # (see drop_redundant_vias' own docstring).
    via_placement.vias = drop_redundant_vias(via_placement.vias, pcb)

    if self.verbose:
        print("  4.4: Assigning trace widths...")
    # Both width SSOTs, merged from the two PRs that threaded them: the
    # netclass `trace_width` table (`design_rules`, PR #1199-era netclass
    # threading, docs/evidence/2026-08-13-router-netclass-trace-widths.md)
    # is the declared-width floor, and `stackup` (PR #1195 layer-aware
    # ampacity, docs/evidence/2026-08-13-router-nlayer-routing.md SS4)
    # makes width a function of (current, copper weight,
    # internal-vs-external) per net via IPC-2221B -- which can only WIDEN
    # the netclass floor, never narrow it.  `pcb.stackup` is read live
    # from this board's own declared `(setup (stackup ...))` block
    # (io/_parse_board.py's `_extract_stackup`), so a stackup edit
    # propagates automatically.
    width_assignment = assign_trace_widths(
        pathfinding_result,
        default_width=pcb.design_rules.default_trace_width_mm,
        design_rules=pcb.design_rules,
        stackup=pcb.stackup,
    )

    if self.verbose:
        print("  4.9: Compiling routing results...")
    plane_net_names: list[str] = []
    routing_results = compile_routing_results(
        pathfinding_result,
        width_assignment,
        via_placement,
        plane_net_names=plane_net_names,
        connectivity=None,
    )

    return Stage4Output(
        pathfinding_result=pathfinding_result,
        via_placement=via_placement,
        width_assignment=width_assignment,
        routing_results=routing_results,
    )
