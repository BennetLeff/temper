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
from temper_placer.router_v6.via_placement import place_vias


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


def _run_stage3(self, pcb: ParsedPCB, stage2: Stage2Output) -> Stage3Output:
    """Run Stage 3: Topological Routing."""
    from temper_placer.router_v6.constraint_model import (
        _stage3_mem_trace,
    )

    _stage3_mem_trace("_run_stage3 ENTER")

    # `#871` net-batching prototype: solve Stage 3's SAT model in batches
    # of `self.net_batch_size` nets instead of one monolithic model.
    # Checked first/takes priority over enable_bundling/max_sat_nets --
    # see RouterV6Pipeline.__init__'s enable_net_batching docstring.
    if getattr(self, "enable_net_batching", False):
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
    target_names = (
        self._select_sat_nets(pcb) if self.max_sat_nets and not self.enable_bundling else None
    )

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
        rust_result = solve_topology_rust(
            py_vars,
            py_cons,
            net_names,
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

    if pathfinding_result is None and self.enable_nlayer_astar_spike:
        # SPIKE PROTOTYPE opt-in (default False; see
        # RouterV6Pipeline.__init__'s enable_nlayer_astar_spike docstring
        # and docs/evidence/2026-08-08-nlayer-via-astar-spike.md). Routes
        # through _astar_nlayer.py's N-layer, via-aware generalization
        # instead of the production 2-layer-capped path below.
        from temper_placer.router_v6._astar_nlayer import (
            run_astar_pathfinding_nlayer,
            select_routing_grids_nlayer,
        )

        nlayer_grids = select_routing_grids_nlayer(stage2.occupancy_grids)
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
        )
    elif pathfinding_result is None:
        fcu_grid, bcu_grid = select_routing_grids(stage2.occupancy_grids)

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

    if self.verbose:
        print("  4.4: Assigning trace widths...")
    # `design_rules` is what makes this stage read the netclass `trace_width`
    # SSOT instead of the three hardcoded keyword buckets -- the identical
    # threading `place_vias` above already has.  See
    # docs/evidence/2026-08-13-router-netclass-trace-widths.md.
    width_assignment = assign_trace_widths(
        pathfinding_result,
        default_width=pcb.design_rules.default_trace_width_mm,
        design_rules=pcb.design_rules,
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
