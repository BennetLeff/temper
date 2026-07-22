"""PCL-to-CP-SAT constraint encoder.

Maps all 8 PCL constraint types to CP-SAT model constraints via
Protocol-based handlers with decorator auto-registration and
``assert_never`` exhaustiveness checking. Handlers live in
``cp_sat/handlers/`` and register themselves into ``HANDLER_REGISTRY``
via the ``@register_handler`` decorator.

Each handler returns a list of assumption literals for UNSAT-core extraction.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from temper_placer.pcl.constraints import (
    AnchoredConstraint,
    BaseConstraint,
    ConstraintTier,
    CompilationTarget,
    ConstraintType,
    EnclosingConstraint,
    KeepoutConstraint,
    SeparatedConstraint,
)

from .model import ComponentVars, CpSatModel

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

UNSUPPORTED_TYPES: set[ConstraintType] = set()

# Policy for constraints that reference unknown component/zone/loop names.
# Defaults to "raise" (fail-closed): silent constraint drop is the exact
# "looks applied but isn't" bug this guard exists to catch. Override via
# TEMPER_UNRESOLVED_REF_POLICY=warn|ignore for exploratory runs.
import os as _os

_UNRESOLVED_REF_POLICY: str = _os.environ.get(
    "TEMPER_UNRESOLVED_REF_POLICY", "raise"
).lower()


# ---------------------------------------------------------------------------
# Encoder context
# ---------------------------------------------------------------------------

class EncoderContext:
    """Context passed to each handler during encoding.

    Carries board dimensions, region definitions, loop data, and
    courtyard/edge-margin parameters needed by specific handlers.
    """

    def __init__(
        self,
        board_w_mm: float,
        board_h_mm: float,
        zones: dict[str, tuple[float, float, float, float]] | None = None,
        loop_components: dict[str, list[str]] | None = None,
        zone_components: dict[str, list[str]] | None = None,
        board_x_min_units: int = 0,
        board_y_min_units: int = 0,
        board_x_max_units: int = 0,
        board_y_max_units: int = 0,
        courtyard_clearance_mm: float = 0.0,
        board_edge_margin_units: int = 0,
    ) -> None:
        self.board_w_mm = board_w_mm
        self.board_h_mm = board_h_mm
        self.zones = zones or {}
        self.loop_components = loop_components or {}
        self.zone_components = zone_components or {}
        self.board_x_min_units = board_x_min_units
        self.board_y_min_units = board_y_min_units
        self.board_x_max_units = board_x_max_units
        self.board_y_max_units = board_y_max_units
        self.courtyard_clearance_mm = courtyard_clearance_mm
        self.board_edge_margin_units = board_edge_margin_units


# ---------------------------------------------------------------------------
# Handler imports (trigger @register_handler side-effects)
# ---------------------------------------------------------------------------

from .handlers import HANDLER_REGISTRY  # noqa: E402
from .handlers import AssumptionLiteral  # noqa: E402
from .handlers import (  # noqa: E402, F401 — trigger @register_handler side-effects
    adjacent,
    aligned,
    anchored,
    enclosing,
    keepout,
    loop_area,
    onside,
    separated,
)

from typing import assert_never as _assert_never


def _check_handler_coverage() -> None:
    """Verify every ConstraintType has a registered handler."""
    for ct in ConstraintType:
        if ct not in HANDLER_REGISTRY:
            if ct.supported_targets and CompilationTarget.CP_SAT not in ct.supported_targets:
                continue
            _assert_never(ct)  # type: ignore[arg-type]


_check_handler_coverage()


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def encode_constraints(
    constraints: list[BaseConstraint],
    model: CpSatModel,
    ctx: EncoderContext | None = None,
    *,
    netlist=None,
    netclass_rules_data=None,
) -> list[AssumptionLiteral]:
    """Encode all constraints into the CP-SAT model.

    When *netclass_rules_data* is provided together with *netlist*,
    auto-generates cross-class separation constraints and appends them
    to the constraint list before encoding.

    Returns a flat list of assumption literal indices for downstream
    UNSAT-core inspection.
    """
    components = model.component_map
    if ctx is None:
        ctx = EncoderContext(
            board_w_mm=100.0,
            board_h_mm=100.0,
            board_x_max_units=10_000,
            board_y_max_units=10_000,
        )

    if netlist is not None and netclass_rules_data is not None:
        from temper_placer.placer.cp_sat.netclass_constraints import (
            generate_netclass_separated_constraints,
        )

        auto_constraints = generate_netclass_separated_constraints(
            netlist,
            netlist.components,
            netclass_rules_data.design_rules,
            existing_constraints=constraints,
        )
        constraints = list(constraints) + auto_constraints

    if ctx.courtyard_clearance_mm > 0:
        courtyard_constraints = _generate_courtyard_separated_constraints(
            model, ctx.courtyard_clearance_mm, constraints,
        )
        constraints = list(constraints) + courtyard_constraints

    all_assumptions: list[AssumptionLiteral] = []
    for c in constraints:
        handler = HANDLER_REGISTRY.get(c.constraint_type)
        if handler is None:
            UNSUPPORTED_TYPES.add(c.constraint_type)
            logger.warning(
                "No CP-SAT handler for constraint type %s (%s)",
                c.constraint_type,
                c.id,
            )
            continue
        assumptions = handler(c, components, model, ctx)
        all_assumptions.extend(assumptions)

    return all_assumptions


def _generate_courtyard_separated_constraints(
    model,
    tau_mm: float,
    existing_constraints: list[BaseConstraint],
) -> list[SeparatedConstraint]:
    """Generate per-pair SEPARATED constraints with ``min_distance_mm=tau_mm``.

    Skips pairs that already carry a SEPARATED constraint with clearance >= τ
    (e.g. cross-class netclass constraints at 6mm dominate the τ constraint).
    """
    constraints: list[SeparatedConstraint] = []
    comp_refs = list(model.component_map.keys())
    if len(comp_refs) < 2:
        return constraints

    existing_pairs: dict[tuple[str, str], float] = {}
    for c in existing_constraints:
        if isinstance(c, SeparatedConstraint) and c.min_distance_mm >= tau_mm:
            a_ref = c.a if c.a in model.component_map else None
            b_ref = c.b if c.b in model.component_map else None
            if a_ref is not None and b_ref is not None and a_ref != b_ref:
                key = tuple(sorted([a_ref, b_ref]))
                existing_pairs[key] = max(existing_pairs.get(key, 0.0), c.min_distance_mm)

    for i in range(len(comp_refs)):
        for j in range(i + 1, len(comp_refs)):
            ra, rb = comp_refs[i], comp_refs[j]
            key = tuple(sorted([ra, rb]))
            if key in existing_pairs:
                continue
            constraints.append(
                SeparatedConstraint(
                    a=ra,
                    b=rb,
                    min_distance_mm=tau_mm,
                    tier=ConstraintTier.HARD,
                    because=f"Courtyard clearance {tau_mm}mm to prevent shorting and solder mask bridging",
                    id=f"courtyard_{ra}_{rb}",
                )
            )

    logger.info("Auto-generated %d courtyard SEPARATED constraints (τ=%.2fmm)", len(constraints), tau_mm)
    return constraints


def _resolve_refs(
    name: str,
    components: dict[str, ComponentVars],
    ctx: EncoderContext,
) -> list[str]:
    """Resolve a ref or zone name to list of component refs."""
    if name in components:
        return [name]
    if name in ctx.zones and name in ctx.zone_components:
        return [r for r in ctx.zone_components[name] if r in components]
    return []


class UnresolvedConstraintRefsError(ValueError):
    """Raised when constraints reference component refs absent from the netlist.

    A constraint whose operand does not resolve to any component is a
    silent no-op — it is encoded against nothing and simply drops. That
    is a fail-closed violation: config↔netlist drift (a renamed or
    missing component) silently degrades the placement with no signal.
    Making it raise turns "looks applied but isn't" into an error at the
    resolution boundary, which is the one place it can be caught cheaply.
    """


def validate_constraint_refs(
    constraints: list,
    component_refs: set[str],
    zone_names: set[str],
    loop_names: set[str],
    *,
    on_unresolved: str = "raise",
) -> dict[str, list[str]]:
    """Check that every component ref in *constraints* actually resolves.

    A component operand resolves if it is a known component ref or a zone
    name (zones expand to their members, mirroring ``_resolve_refs``).
    Zone-only operands (``outer``, ``zone_name``) must be zones;
    ``loop_name`` operands must be known loops. Anything else is drift.

    Args:
        constraints: PCL constraint objects (duck-typed by attribute).
        component_refs: Known component refs from the netlist.
        zone_names: Known zone names.
        loop_names: Known loop-definition names.
        on_unresolved: ``"raise"`` (default) raises
            :class:`UnresolvedConstraintRefsError`; ``"warn"`` logs a
            warning; ``"ignore"`` only returns the report.

    Returns:
        Mapping of ``constraint_id -> [unresolved refs]`` (empty if clean).
    """
    comp_or_zone = component_refs | zone_names
    unresolved: dict[str, list[str]] = {}

    for c in constraints:
        cid = getattr(c, "id", "") or type(c).__name__
        missing: list[str] = []

        # Component operands: must be a component or a zone (zones expand).
        for attr in ("a", "b", "component"):
            val = getattr(c, attr, None)
            if isinstance(val, str) and val not in comp_or_zone:
                missing.append(val)
        for attr in ("inner", "components"):
            val = getattr(c, attr, None)
            if isinstance(val, (list, tuple)):
                missing.extend(r for r in val if isinstance(r, str) and r not in comp_or_zone)

        # Zone-only operands: must be a known zone.
        for attr in ("outer", "zone_name"):
            val = getattr(c, attr, None)
            if isinstance(val, str) and val not in zone_names:
                missing.append(val)

        # Loop operands: must be a known loop definition.
        loop_name = getattr(c, "loop_name", None)
        if isinstance(loop_name, str) and loop_name not in loop_names:
            missing.append(loop_name)

        if missing:
            # De-dup while preserving order.
            seen: set[str] = set()
            unresolved[cid] = [m for m in missing if not (m in seen or seen.add(m))]

    if unresolved and on_unresolved != "ignore":
        lines = [
            f"  {cid}: {', '.join(refs)}" for cid, refs in sorted(unresolved.items())
        ]
        msg = (
            "Constraint(s) reference names absent from the netlist/zones/loops "
            "— these would silently drop (fail-closed violation):\n"
            + "\n".join(lines)
            + "\nFix the config↔netlist drift (rename or add the components), "
            "or pass on_unresolved='warn' to downgrade."
        )
        if on_unresolved == "raise":
            raise UnresolvedConstraintRefsError(msg)
        logger.warning(msg)

    return unresolved



# ---------------------------------------------------------------------------
# Extra constraints (feedback-driven)
# ---------------------------------------------------------------------------

def _encode_extra_constraints(
    model,
    extra_constraints: list,
    comp_refs: list[str],
    x_vars,
    y_vars,
    rot_vars,
    grid_step: float,
    max_x: int,
    max_y: int,
    board: object | None = None,
) -> None:
    """Encode additional PCL constraints into the CP-SAT model."""
    from temper_placer.pcl.constraints import (
        AnchoredConstraint,
        EnclosingConstraint,
        KeepoutConstraint,
        SeparatedConstraint,
    )

    ref_to_idx = {ref: i for i, ref in enumerate(comp_refs)}

    for constraint in extra_constraints:
        if isinstance(constraint, SeparatedConstraint):
            if constraint.a in comp_refs and constraint.b in comp_refs:
                a_idx = ref_to_idx[constraint.a]
                b_idx = ref_to_idx[constraint.b]
                min_sep = int(constraint.min_distance_mm / grid_step)
                dx = model.NewIntVar(-max_x, max_x, f"extra_dx_{constraint.id}")
                dy = model.NewIntVar(-max_y, max_y, f"extra_dy_{constraint.id}")
                model.Add(dx == x_vars[a_idx] - x_vars[b_idx])
                model.Add(dy == y_vars[a_idx] - y_vars[b_idx])
                abs_dx = model.NewIntVar(0, max_x, f"extra_abs_dx_{constraint.id}")
                abs_dy = model.NewIntVar(0, max_y, f"extra_abs_dy_{constraint.id}")
                model.AddAbsEquality(abs_dx, dx)
                model.AddAbsEquality(abs_dy, dy)
                sep_x = model.NewBoolVar(f"extra_sep_x_{constraint.id}")
                sep_y = model.NewBoolVar(f"extra_sep_y_{constraint.id}")
                model.Add(abs_dx >= min_sep).OnlyEnforceIf(sep_x)
                model.Add(abs_dy >= min_sep).OnlyEnforceIf(sep_y)
                model.Add(sep_x + sep_y >= 1)

        elif isinstance(constraint, AnchoredConstraint):
            if constraint.component in comp_refs:
                idx = ref_to_idx[constraint.component]
                if constraint.position:
                    px = int(constraint.position[0] / grid_step)
                    py = int(constraint.position[1] / grid_step)
                    model.Add(x_vars[idx] == px)
                    model.Add(y_vars[idx] == py)
                elif constraint.region:
                    rx_min, ry_min, rx_max, ry_max = constraint.region
                    model.Add(x_vars[idx] >= int(rx_min / grid_step))
                    model.Add(x_vars[idx] <= int(rx_max / grid_step))
                    model.Add(y_vars[idx] >= int(ry_min / grid_step))
                    model.Add(y_vars[idx] <= int(ry_max / grid_step))

        elif isinstance(constraint, EnclosingConstraint):
            pass  # Already handled via zone logic above

        elif isinstance(constraint, KeepoutConstraint):
            _encode_keepout_constraint(
                model, constraint, comp_refs, x_vars, y_vars,
                grid_step, max_x, max_y, board,
            )


def _encode_keepout_constraint(
    model,
    constraint,
    comp_refs: list[str],
    x_vars,
    y_vars,
    grid_step: float,
    max_x: int,
    max_y: int,
    board: object | None = None,
) -> None:
    """Encode a KeepoutConstraint as component exclusion from a zone.

    Resolves the keepout zone bounds from one of:
    1. A matching board zone (by name) with ``zone_type="keepout"``.
    2. A ``congestion_*`` synthetic keepout: parses bbox from the zone name
       format ``congestion_xmin_ymin_xmax_ymax``.
    3. Falls back to a warning if neither resolution works.
    """
    zone_name: str = constraint.zone_name
    bounds: tuple[float, float, float, float] | None = None
    margin_mm: float = getattr(constraint, 'margin_mm', 0.0)

    # 1. Look up from board zones
    if board is not None and hasattr(board, 'zones'):
        for z in board.zones:
            if getattr(z, 'name', '') == zone_name:
                if getattr(z, 'zone_type', 'placement') in ('keepout', 'no_place'):
                    bounds = (
                        float(z.bounds[0]) - margin_mm,
                        float(z.bounds[1]) - margin_mm,
                        float(z.bounds[2]) + margin_mm,
                        float(z.bounds[3]) + margin_mm,
                    )
                break

    # 2. Parse synthetic congestion keepout name
    if bounds is None and zone_name.startswith('congestion_'):
        parts = zone_name.split('_')
        if len(parts) == 5:
            try:
                x0, y0, x1, y1 = float(parts[1]), float(parts[2]), float(parts[3]), float(parts[4])
                bounds = (
                    x0 - margin_mm,
                    y0 - margin_mm,
                    x1 + margin_mm,
                    y1 + margin_mm,
                )
            except ValueError:
                pass

    if bounds is None:
        logger.warning(
            f"KeepoutConstraint '{zone_name}' could not be resolved to board "
            f"bounds — ignored during CP-SAT encoding"
        )
        return

    kx_min = max(0, int(bounds[0] / grid_step))
    ky_min = max(0, int(bounds[1] / grid_step))
    kx_max = min(max_x, int(bounds[2] / grid_step))
    ky_max = min(max_y, int(bounds[3] / grid_step))

    if kx_max <= kx_min or ky_max <= ky_min:
        return

    # Exclude all components from the keepout zone via a negated
    # bounding-box constraint: for each component i, add
    #   NOT (kx_min <= xi <= kx_max AND ky_min <= yi <= ky_max)
    # which expands to:
    #   (xi < kx_min) OR (xi > kx_max) OR (yi < ky_min) OR (yi > ky_max)
    for i in range(len(comp_refs)):
        below_x = model.NewBoolVar(f"keepout_{zone_name}_below_x_{i}")
        above_x = model.NewBoolVar(f"keepout_{zone_name}_above_x_{i}")
        below_y = model.NewBoolVar(f"keepout_{zone_name}_below_y_{i}")
        above_y = model.NewBoolVar(f"keepout_{zone_name}_above_y_{i}")
        model.Add(x_vars[i] < kx_min).OnlyEnforceIf(below_x)
        model.Add(x_vars[i] >= kx_min).OnlyEnforceIf(below_x.Not())
        model.Add(x_vars[i] > kx_max).OnlyEnforceIf(above_x)
        model.Add(x_vars[i] <= kx_max).OnlyEnforceIf(above_x.Not())
        model.Add(y_vars[i] < ky_min).OnlyEnforceIf(below_y)
        model.Add(y_vars[i] >= ky_min).OnlyEnforceIf(below_y.Not())
        model.Add(y_vars[i] > ky_max).OnlyEnforceIf(above_y)
        model.Add(y_vars[i] <= ky_max).OnlyEnforceIf(above_y.Not())
        model.Add(below_x + above_x + below_y + above_y >= 1)


# ---------------------------------------------------------------------------
# Solver entry point
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

    def to_placements_dict(self) -> dict[str, tuple[float, float]]:
        """Return {component_ref: (x_mm, y_mm)} mapping (loop.py interface)."""
        return dict(self.positions)


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
        _config_yaml = Path(__file__).parent.parent.parent.parent.parent / "configs" / "netclass_rules.yaml"
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
    model_wrapper.set_bounds(margin_units, margin_units, board_w_units - margin_units, board_h_units - margin_units)

    # Wire up NoOverlap2D (redundant global for propagation — per-pair
    # SEPARATED-τ is added during constraint encoding in U2).
    model_wrapper.add_no_overlap_2d(comp_refs)

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
        on_unresolved=_UNRESOLVED_REF_POLICY,
    )

    labels = encode_constraints(
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
    "D_1", "D_2", "D_3", "D_4", "D_5", "D_6",  # diodes
    "K_1", "K_2", "K_5", "K_6",               # electrolytic capacitors
}
