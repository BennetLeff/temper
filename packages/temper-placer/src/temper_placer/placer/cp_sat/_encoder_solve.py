"""CP-SAT placement solver entry point.

Builds the model, encodes constraints, solves, and returns a result.
"""

from __future__ import annotations

import logging
import time
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
    pass

logger = logging.getLogger(__name__)


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
    isolation_barrier: dict | None = None,
    fixed_positions: dict[str, tuple[float, float, int]] | None = None,
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
    MASK_EXPANSION_MM = 0.1
    tau_mm = default_clearance_mm + 2 * MASK_EXPANSION_MM

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

    ctx = EncoderContext(
        board_w,
        board_h,
        zones=resolved_zones,
        loop_components=loop_components or _resolve_loop_components(netlist),
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
