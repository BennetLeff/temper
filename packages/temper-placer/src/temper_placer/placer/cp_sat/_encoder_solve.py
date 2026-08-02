"""CP-SAT placement solver entry point.

Builds the model, encodes constraints, solves, and returns a result.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from temper_placer.pcl.constraints import BaseConstraint
from temper_placer.placer.cp_sat import _encoder_core
from temper_placer.placer.cp_sat._encoder_core import (
    EncoderContext,
    encode_constraints,
    validate_constraint_refs,
)
from temper_placer.placer.cp_sat.model import CpSatModel

if TYPE_CHECKING:
    from temper_placer.placer.cp_sat.fixed_copper import PadRectLocal

logger = logging.getLogger(__name__)

# Industry-standard solder mask expansion (mm): the mask-expansion term
# of the courtyard clearance τ (C1).  Kept here — not in the Rust crate —
# because it is board/setup data with a TODO to parse it from the board;
# only the arithmetic moves to Rust (``courtyard_clearance_mm``).
MASK_EXPANSION_MM = 0.1


# ---------------------------------------------------------------------------
# Solver result
# ---------------------------------------------------------------------------


@dataclass
class CpSatPlacementResult:
    """Result of a CP-SAT placement solve.

    Carries placed component positions, rotation indices, solve status
    and timing metadata.  This is the interface that the place→route loop
    reads — every field that loop.py accesses must be defined here.
    """

    positions: dict[str, tuple[float, float]] = field(default_factory=dict)
    rotations: dict[str, int] = field(default_factory=dict)
    # Retained for feedback-loop compatibility.  New solver results derive
    # this from ``positions`` when absent; legacy callers may provide it
    # explicitly.
    placed_refs: list[str] = field(default_factory=list)
    # Compatibility metadata used by callers that distinguish a proven UNSAT
    # result from a partial/unknown placement.
    unplaced_refs: list[str] = field(default_factory=list)
    status: str = "unknown"  # "optimal" | "feasible" | "infeasible" | "model_invalid"
    solve_time_ms: float = 0.0
    objective_value: float = 0.0
    unsat_core: list[dict] = field(default_factory=list)  # [{name, because}] when infeasible
    # Populated only when solve_placement(isolation_barrier=...) was passed;
    # see isolation_barrier.py::IsolationBarrierReport.
    isolation_barrier_report: object | None = None

    def to_placements_dict(self) -> dict[str, tuple[float, float]]:
        """Return {component_ref: (x_mm, y_mm)} mapping (loop.py interface)."""
        return dict(self.positions)

    def to_rotations_dict(self) -> dict[str, float]:
        """Return {component_ref: rotation_degrees}, converting each solved
        rotation index (0-3) to degrees via ``index * 90.0`` -- the same
        convention already used ad hoc at the one existing call site
        (``cli/__init__.py``'s ``optimize`` command). Only refs with a
        nonzero rotation index are included; a ref absent from this dict
        should be treated as "no rotation change" by a consumer such as
        ``_apply_placements_to_pcb``'s ``rotations=`` parameter, not as an
        explicit 0 degrees -- absence and explicit-zero are handled
        identically by that consumer, but keeping the dict sparse here
        avoids implying every omitted ref was solved at 0 degrees.
        """
        return {ref: idx * 90.0 for ref, idx in self.rotations.items() if idx}


# ---------------------------------------------------------------------------
# Solver entry point
# ---------------------------------------------------------------------------


def solve_placement(
    netlist,
    board,
    extra_constraints: list | None = None,
    timeout_ms: int = 1_000,
    seed: int = 0,
    zones: dict[str, tuple[float, float, float, float]] | None = None,
    loop_components: dict[str, list[str]] | None = None,
    zone_components: dict[str, list[str]] | None = None,
    hint_positions: dict[str, tuple[float, float, int]] | None = None,
    minimize_displacement_to: dict[str, tuple[float, float]] | None = None,
    reference_aliases: Mapping[str, str] | None = None,
    loop_aliases: Mapping[str, str] | None = None,
    fixed_rotations: dict[str, int] | None = None,
    max_displacement_mm: float | None = None,
    isolation_barrier: dict | None = None,
    fixed_positions: dict[str, tuple[float, float, int]] | None = None,
    fixed_copper: dict | None = None,
) -> CpSatPlacementResult:
    """Build a CP-SAT model, encode constraints, solve, and return the result.

    This is the single entry point consumed by PlaceRouteLoop and ``temper
    optimize``.  It wires the full pipeline: model creation → PCL encoding
    → solve → position extraction.

    Args:
        hint_positions: Optional warm-start hints.  Dict mapping component
            ref to ``(x_mm, y_mm, rotation_0_3)``.  Hints are seeded via
            ``CpModel.AddHint()`` before solving so CP-SAT searches locally
            from the supplied positions rather than exploring the full space.
        minimize_displacement_to: Optional reference coordinates for an
            opt-in Manhattan-distance objective: ``{ref: (x_mm, y_mm)}``.
            The objective is a *preference*, not a constraint -- hard
            constraints stay authoritative and the solver returns the
            feasible placement closest (in Manhattan distance) to the
            reference.  This is the "minimum-displacement" half of the
            route-aware repair loop (issue #504): a repair solve over a
            routed board starts from the current positions, so components
            only move as far as the clearance constraints force them, and
            the existing routed copper is not disturbed wholesale the way a
            free reshuffle disturbs it.
        reference_aliases: Optional explicit config-to-netlist component
            reference mapping applied before validation. Unmapped names
            remain subject to the fail-closed unresolved-reference policy.
        loop_aliases: Optional explicit mapping for legacy loop names to the
            loop namespace supplied by ``loop_components`` or netlist loop
            extraction.
        fixed_rotations: Optional hard pinning of component rotations to
            their current 0-3 quadrant index: ``{ref: rotation_0_3}``.
            Routed-board repair must not rotate footprints (a rotation moves
            every pad, disconnecting the routed copper attached to it), so
            repair callers pin every ref to its current board rotation.
        max_displacement_mm: Optional hard per-component Manhattan
            displacement bound applied to every ref in
            ``minimize_displacement_to``: each such component may move at
            most ``max_displacement_mm`` in total (|dx| + |dy|). This is
            the bounded-repair formulation -- it *guarantees* the solved
            placement stays inside a displacement envelope around the
            current board (feasibility permitting), rather than trusting
            the objective search to find a low-displacement solution. Only
            meaningful together with ``minimize_displacement_to``.
        fixed_positions: Optional HARD position pins.  Dict mapping component
            ref to ``(x_mm, y_mm, rotation_0_3)``.  Unlike ``hint_positions``,
            these are binding equality constraints -- the solver cannot move a
            pinned ref (it will report ``infeasible`` if a pin conflicts with
            the encoded constraints).  This is the minimal-disruption
            primitive: freeze every component NOT involved in a violation at
            its current board position, and re-solve only the violating
            neighborhood (issue #504).  Rotation is pinned only when the ref
            has a rotation variable (polarized refs are pinned by
            construction to rot=0).
        isolation_barrier: Optional kwargs forwarded to
            ``isolation_barrier.add_isolation_barrier_to_model`` (minus
            ``model``/``netlist``/``board_w_mm``/``board_h_mm``, which this
            function supplies) -- e.g. ``{"manifest_path": Path(...),
            "corridor_width_mm": 8.5, "orientation": "vertical"}``. When
            given, registers the mains<->SELV physical isolation-barrier
            HARD constraint (see ``isolation_barrier.py``) before encoding.
            The resulting report is attached to the returned
            ``CpSatPlacementResult.isolation_barrier_report``.
        fixed_copper: Optional pad-vs-fixed-copper NoOverlap constraint set
            (issue #523). A dict with keys ``parse_result`` (a
            ``ParseResult`` carrying ``.traces``/``.vias``/``.board``),
            ``free_refs`` (set of component refs being placed -- their pads
            must not land on different-net fixed copper), ``margin_mm``
            (default 0.05) and ``include_other_pads`` (default True: pinned
            components' pads are obstacles too). When given, the fixed-copper
            constraints are encoded for every free ref and the R24 post-solve
            audit is run on the resolved placement -- a feasible solve with
            audit violations raises (an encoding bug; see ``fixed_copper.py``).
            Absent (default): existing behaviour is unchanged.
    """
    from ortools.sat.python import cp_model as cp

    t_start = time.monotonic()

    # Determine board dimensions.
    board_w = float(getattr(board, "width", 100.0))
    board_h = float(getattr(board, "height", 100.0))

    model_wrapper = CpSatModel(units_per_mm=100)
    board_w_units = model_wrapper.mm_to_units(board_w)
    board_h_units = model_wrapper.mm_to_units(board_h)

    # Register every board component in the model.
    comp_refs: list[str] = []
    for comp in netlist.components:
        ref = comp.ref
        comp_refs.append(ref)
        bounds = getattr(comp, "bounds", (10.0, 10.0))
        model_wrapper.add_component(
            ref,
            x_start_val=0,
            y_start_val=0,
            width=model_wrapper.mm_to_units(float(bounds[0])),
            height=model_wrapper.mm_to_units(float(bounds[1])),
        )
        # Add rotation unless it's a known polarized part.
        polarized = ref in _POLARIZED_REFS
        model_wrapper.add_rotation(ref, is_polarized=polarized)

    # Routed-board repair: pin every requested component's rotation to its
    # current board value (hard constraint). A rotation would move every pad
    # and disconnect the routed copper attached to it, so repair callers
    # pin all refs; the min-displacement objective then only has translation
    # freedom to work with.
    if fixed_rotations:
        for ref, rot in fixed_rotations.items():
            model_wrapper.add_fixed_rotation(ref, rot)

    # Load netclass rules early — needed for auto-generated cross-class
    # separation AND for computing courtyard clearance τ (U1).
    loaded_netclass_rules = None
    default_clearance_mm = 0.2
    try:
        from pathlib import Path

        from temper_placer.io.netclass_loader import load_netclass_rules

        _config_yaml = (
            Path(__file__).parent.parent.parent.parent.parent / "configs" / "netclass_rules.yaml"
        )
        if _config_yaml.exists():
            loaded_netclass_rules = load_netclass_rules(_config_yaml)
            default_clearance_mm = loaded_netclass_rules.design_rules.default_clearance
    except Exception:
        logger.debug("Could not load netclass_rules.yaml", exc_info=True)

    # Compute courtyard clearance τ (C1) and board-edge margin m (C2).
    # τ = default_clearance_mm + 2 * mask_expansion_mm (strict >, not max).
    # mask_expansion_mm = 0.1 is the industry-standard solder mask expansion.
    # Using + instead of max() guarantees strict separation so mask apertures
    # never touch at 0, preventing solder mask bridging.
    # TODO: parse mask_expansion_mm from board (setup) via kiutils.
    tau_mm = courtyard_clearance_mm(default_clearance_mm)

    # m derives from copper_edge_clearance_mm.
    # copper_edge_clearance_mm = 0.5 is a conservative default.
    # TODO: parse copper_edge_clearance_mm from board (setup) via kiutils.
    COPPER_EDGE_CLEARANCE_MM = 0.5
    margin_units = model_wrapper.mm_to_units(COPPER_EDGE_CLEARANCE_MM)

    # Constrain all components to lie within board bounds with edge margin (C2).
    model_wrapper.set_bounds(
        margin_units, margin_units, board_w_units - margin_units, board_h_units - margin_units
    )

    # Wire up NoOverlap2D (redundant global for propagation — per-pair
    # SEPARATED-τ is added during constraint encoding in U2).
    model_wrapper.add_no_overlap_2d(comp_refs)

    # Mains<->SELV physical isolation barrier (opt-in). Must run AFTER every
    # real component is registered (above) — add_isolation_barrier_to_model
    # calls model_wrapper.get_component(ref) for every HV/SELV/isolator ref
    # and adds its constraints directly to the model; nothing further needs
    # encoding for it.
    isolation_barrier_report = None
    if isolation_barrier is not None:
        from temper_placer.placer.cp_sat.isolation_barrier import add_isolation_barrier_to_model

        isolation_barrier_report = add_isolation_barrier_to_model(
            model_wrapper,
            netlist,
            board_w_mm=board_w,
            board_h_mm=board_h,
            **isolation_barrier,
        )

    # Warm-start: seed solver with hint positions so CP-SAT searches
    # locally from a known-feasible point rather than exploring the full
    # space.  Hints are validated against constraints by the solver;
    # AddHint is a soft suggestion, not a binding assignment.
    if hint_positions:
        for ref, (x_mm, y_mm, rot) in hint_positions.items():
            if ref in model_wrapper.component_map:
                cv = model_wrapper.get_component(ref)
                hint_x = model_wrapper.mm_to_units(x_mm)
                hint_y = model_wrapper.mm_to_units(y_mm)
                model_wrapper.model_ref.AddHint(cv.x_center, hint_x)
                model_wrapper.model_ref.AddHint(cv.y_center, hint_y)
                if cv.rot_ref is not None:
                    model_wrapper.model_ref.AddHint(cv.rot_ref, rot)

    # Minimum-displacement repair objective (issue #504): the solver returns
    # the feasible placement closest (Manhattan) to these reference
    # positions.  A preference, never a hard bound -- the objective is
    # applied below via model_wrapper.apply_objective() BEFORE solving; this
    # is what makes the parameter actually steer the solve (a previous,
    # never-landed attempt registered objective terms without ever calling
    # Minimize on this path, making the parameter a silent no-op).
    if max_displacement_mm is not None and not minimize_displacement_to:
        # Same no-op class as the #498 bug: a bound with no reference would
        # silently constrain nothing. Fail loudly instead.
        raise ValueError(
            "max_displacement_mm requires minimize_displacement_to (the bound "
            "applies to every ref in the reference dict)"
        )
    if minimize_displacement_to:
        bound_units = None
        if max_displacement_mm is not None:
            bound_units = model_wrapper.mm_to_units(max_displacement_mm)
        for ref, (x_mm, y_mm) in minimize_displacement_to.items():
            model_wrapper.add_displacement_objective(
                ref,
                model_wrapper.mm_to_units(x_mm),
                model_wrapper.mm_to_units(y_mm),
                max_units=bound_units,
            )

    # Hard position pins (minimal-disruption API): unlike AddHint above,
    # these are binding equality constraints -- the solver cannot move a
    # pinned ref.  This is the "freeze these refs, re-solve the rest"
    # primitive issue #504's minimum-displacement loop needs.  An
    # unresolved ref is a silent no-op if skipped here, so fail loudly
    # (same fail-closed discipline as validate_constraint_refs below).
    if fixed_positions:
        for ref, (x_mm, y_mm, rot) in fixed_positions.items():
            if ref not in model_wrapper.component_map:
                raise ValueError(
                    f"fixed_positions references unknown component {ref!r}; "
                    "a silent skip would freeze nothing and produce a "
                    "misleadingly 'minimal' displacement"
                )
            cv = model_wrapper.get_component(ref)
            pin_x = model_wrapper.mm_to_units(x_mm)
            pin_y = model_wrapper.mm_to_units(y_mm)
            model_wrapper.model_ref.Add(cv.x_center == pin_x)  # type: ignore[operator]
            model_wrapper.model_ref.Add(cv.y_center == pin_y)  # type: ignore[operator]
            if cv.rot_ref is not None:
                model_wrapper.model_ref.Add(cv.rot_ref == rot)  # type: ignore[operator]

    # Build EncoderContext from board and netlist data.
    # Coerce every zone rectangle to a validated Rect (x_min,y_min,x_max,y_max)
    # so an inverted/degenerate zone — the (x,y,w,h) convention mismatch —
    # fails loudly here instead of silently encoding an empty, infeasible
    # enclosing region.
    from temper_placer.core.board import Rect

    resolved_zones: dict[str, Rect] = {
        name: Rect.coerce(bounds) for name, bounds in (zones or {}).items()
    }
    resolved_zone_components: dict[str, list[str]] = dict(zone_components or {})
    for z in board.zones:
        if z.name not in resolved_zones:
            resolved_zones[z.name] = Rect.coerce(z.bounds)
        zone_refs = list(z.components)
        for comp in netlist.components:
            if getattr(comp, "zone", None) == z.name and comp.ref not in zone_refs:
                zone_refs.append(comp.ref)
        if zone_refs:
            resolved_zone_components[z.name] = zone_refs

    resolved_loop_components = loop_components or _resolve_loop_components(netlist)
    loop_reconciliation = _encoder_core.reconcile_loop_components(
        resolved_loop_components,
        reference_aliases,
        loop_aliases,
    )
    if loop_reconciliation.aliases_applied:
        logger.info("Applied loop aliases: %s", loop_reconciliation.aliases_applied)

    ctx = EncoderContext(
        board_w,
        board_h,
        zones={k: (v.x_min, v.y_min, v.x_max, v.y_max) for k, v in resolved_zones.items()},
        loop_components=loop_reconciliation.loop_components,
        zone_components=resolved_zone_components,
        board_x_min_units=0,
        board_y_min_units=0,
        board_x_max_units=board_w_units,
        board_y_max_units=board_h_units,
        courtyard_clearance_mm=tau_mm,
        board_edge_margin_units=margin_units,
    )

    constraint_objects: list[BaseConstraint] = list(extra_constraints or [])
    pcl_coll = getattr(board, "constraints", None)
    if pcl_coll is not None:
        constraint_objects.extend(pcl_coll)

    reconciliation = _encoder_core.reconcile_constraint_refs(
        constraint_objects,
        reference_aliases,
        loop_aliases=loop_aliases,
    )
    constraint_objects = list(reconciliation.constraints)
    if reconciliation.aliases_applied:
        logger.info("Applied constraint aliases: %s", reconciliation.aliases_applied)

    # Fail loud on config↔netlist drift: a constraint operand that resolves
    # to nothing is a silent no-op, so validate before encoding. This is the
    # fail-closed guard for the "looks applied but isn't" failure mode.
    validate_constraint_refs(
        constraint_objects,
        component_refs=set(model_wrapper.component_map.keys()),
        zone_names=set(resolved_zones.keys()),
        loop_names=set(ctx.loop_components.keys()),
        # Read through the module rather than a `from ... import` binding.
        # A module-level `from _encoder_core import _UNRESOLVED_REF_POLICY`
        # snapshots the value at import time, so tests that downgrade the
        # policy would set an attribute nothing ever reads -- green, and
        # vacuous. One canonical location, read at call time.
        on_unresolved=_encoder_core._UNRESOLVED_REF_POLICY,
    )

    encode_constraints(
        constraint_objects,
        model_wrapper,
        ctx,
        netlist=netlist,
        netclass_rules_data=loaded_netclass_rules,
    )

    # Pad-vs-fixed-copper NoOverlap (issue #523): encode one BoolOr per
    # (free pad, fixed item) pair after every other constraint so the
    # rotation variables and sizes are fully wired. See fixed_copper.py.
    _fixed_copper_pads: dict[str, list[PadRectLocal]] | None = None
    _fixed_copper_items: list | None = None
    if fixed_copper is not None:
        from temper_placer.placer.cp_sat.fixed_copper import (
            build_fixed_copper_items,
            build_free_component_pads,
            encode_fixed_copper_constraints,
        )

        free_refs = set(fixed_copper.get("free_refs", ()))
        margin_mm = float(fixed_copper.get("margin_mm", 0.05))
        include_other_pads = bool(fixed_copper.get("include_other_pads", True))
        parse_result = fixed_copper["parse_result"]
        _fixed_copper_pads = build_free_component_pads(netlist, free_refs)
        _fixed_copper_items = build_fixed_copper_items(
            parse_result,
            netlist,
            free_refs,
            margin_mm=margin_mm,
            include_other_pads=include_other_pads,
        )
        encode_fixed_copper_constraints(
            model_wrapper,
            _fixed_copper_pads,
            _fixed_copper_items,
            free_refs=free_refs,
        )
        logger.info(
            "fixed-copper constraints encoded for %d free ref(s) (%d pads, %d items)",
            len(free_refs),
            sum(len(p) for p in _fixed_copper_pads.values()),
            len(_fixed_copper_items),
        )

    # Phase 1 (feasibility): no objective — find any valid placement.
    # Phase 2 (wirelength polish) runs separately with a longer timeout
    # and bounded pair count.  The full O(n²) objective with 33 components
    # creates ~2100 extra variables and makes the solver hit the timeout.
    # See loop.py:_solve_phase2 for the polish path.

    solver = cp.CpSolver()
    solver.parameters.max_time_in_seconds = timeout_ms / 1000.0
    solver.parameters.random_seed = seed
    solver.parameters.num_search_workers = 4
    solver.parameters.log_search_progress = False

    # Apply the accumulated objective (if any) BEFORE solving.  This is the
    # single point where the minimum-displacement objective becomes real:
    # without it the terms registered by add_displacement_objective() would
    # be collected and never used.
    model_wrapper.apply_objective()

    status_code = solver.Solve(model_wrapper.model_ref)
    elapsed_ms = (time.monotonic() - t_start) * 1000.0

    status_map = {
        cp.OPTIMAL: "optimal",
        cp.FEASIBLE: "feasible",
        cp.INFEASIBLE: "infeasible",
        cp.MODEL_INVALID: "model_invalid",
        cp.UNKNOWN: "unknown",
    }
    status_str = status_map.get(status_code, "unknown")

    positions: dict[str, tuple[float, float]] = {}
    rotations: dict[str, int] = {}
    objective = 0.0

    if status_str in ("optimal", "feasible"):
        objective = solver.ObjectiveValue()
        for ref in comp_refs:
            cv = model_wrapper.get_component(ref)
            x_mm = solver.Value(cv.x_center) / model_wrapper.units_per_mm
            y_mm = solver.Value(cv.y_center) / model_wrapper.units_per_mm
            positions[ref] = (round(x_mm, 3), round(y_mm, 3))
            if cv.rot_ref is not None:
                rotations[ref] = solver.Value(cv.rot_ref)

    unsat_core: list[dict] = []
    if status_str in ("infeasible", "model_invalid"):
        try:
            proto_indices = solver.SufficientAssumptionsForInfeasibility()
            for idx in proto_indices:
                label = model_wrapper._assumption_labels.get(idx, f"constraint_{idx}")
                unsat_core.append({"name": label, "because": "", "literal_index": idx})
        except Exception:
            pass

    # R24 item-3 post-solve audit (issue #523): recompute the EXACT
    # pad-to-copper clearance from the resolved coordinates, independent of
    # the solver's feasibility claim. By fixed_copper.py's soundness proof a
    # feasible solve must clear every applicable item by at least the margin;
    # any violation means the encoding is unsound for this solve and is a
    # hard failure, not a reportable "warning".
    if (
        status_str in ("optimal", "feasible")
        and _fixed_copper_items is not None
        and _fixed_copper_pads is not None
    ):
        from temper_placer.placer.cp_sat.fixed_copper import audit_fixed_copper

        audit_violations = audit_fixed_copper(
            _fixed_copper_pads,
            _fixed_copper_items,
            positions,
            rotations,
        )
        if audit_violations:
            first = audit_violations[0]
            raise RuntimeError(
                f"fixed-copper post-solve audit FAILED for a {status_str} solve: "
                f"{len(audit_violations)} violation(s); first: "
                f"{first.ref} pad {first.pad_number} vs {first.item_kind} "
                f"({first.item_net}): actual clearance {first.actual_mm:.4f}mm "
                f"< required {first.required_mm}mm. The fixed-copper encoding "
                "is unsound for this solve (see fixed_copper.py soundness proof)."
            )
        logger.info("fixed-copper post-solve audit: %d violation(s)", len(audit_violations))

    return CpSatPlacementResult(
        positions=positions,
        rotations=rotations,
        placed_refs=list(positions),
        unplaced_refs=[ref for ref in comp_refs if ref not in positions],
        status=status_str,
        solve_time_ms=elapsed_ms,
        objective_value=objective,
        unsat_core=unsat_core,
        isolation_barrier_report=isolation_barrier_report,
    )


def _resolve_loop_components(netlist) -> dict[str, list[str]]:
    """Return {loop_name: [comp_ref, ...]} for all detectable commutation loops."""
    from temper_placer.core.loop_extractor import auto_extract_loops

    try:
        loops = auto_extract_loops(netlist)
        return {loop.name: loop.components for loop in loops}
    except Exception:
        return {}


def courtyard_clearance_mm(default_clearance_mm: float) -> float:
    """Courtyard clearance τ (C1): the separated-constraint margin the
    encoder applies to every component pair.

    ``default_clearance_mm + 2 * mask_expansion_mm`` — a strict ``+``,
    not ``max()``, so solder-mask apertures never touch at 0 (the
    ``+`` vs ``max`` distinction is the point; see the C1 comment in
    :func:`solve_placement`).

    Computed in the ``temper-constraints`` Rust crate
    (``encoder.rs::courtyard_clearance_mm``) with the exact f64
    operation order (``2 * expansion`` first, then the addition);
    pinned bit-exactly by
    ``tests/placer/cp_sat/test_encoder_rust_differential.py``.
    """
    import temper_constraints as _tc

    return _tc.courtyard_clearance_mm_py(default_clearance_mm, MASK_EXPANSION_MM)


# List of component refs known to be polarized on the temper board.
# This is the v1 fallback; automatic footprint detection is a follow-up.
_POLARIZED_REFS: set[str] = {
    "D_1",
    "D_2",
    "D_3",
    "D_4",
    "D_5",
    "D_6",  # diodes
    "K_1",
    "K_2",
    "K_5",
    "K_6",  # electrolytic capacitors
}
