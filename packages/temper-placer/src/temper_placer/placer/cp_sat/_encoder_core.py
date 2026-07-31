"""CP-SAT constraint encoder core — context, dispatch, and validation.

Handlers are registered by the handlers/ package at import time.
encode_constraints() dispatches through HANDLER_REGISTRY.
"""

from __future__ import annotations

import logging
import os as _os
from collections.abc import Mapping
from copy import copy
from dataclasses import dataclass
from typing import TYPE_CHECKING

from temper_placer.pcl.constraints import (
    BaseConstraint,
    ConstraintTier,
    ConstraintType,
    SeparatedConstraint,
)
from temper_placer.placer.cp_sat.handlers import HANDLER_REGISTRY
from temper_placer.placer.cp_sat.model import ComponentVars, CpSatModel

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

UNSUPPORTED_TYPES: set[ConstraintType] = set()

_UNRESOLVED_REF_POLICY: str = _os.environ.get("TEMPER_UNRESOLVED_REF_POLICY", "raise").lower()


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


@dataclass(frozen=True)
class ReferenceReconciliation:
    """Result of applying an explicit config-to-netlist reference map."""

    constraints: tuple[BaseConstraint, ...]
    aliases_applied: tuple[tuple[str, str], ...] = ()


_REFERENCE_FIELDS = (
    "a",
    "b",
    "component",
    "components",
    "inner",
    "outer",
    "zone_name",
    "loop_name",
)


def reconcile_constraint_refs(
    constraints: list[BaseConstraint],
    aliases: Mapping[str, str] | None = None,
) -> ReferenceReconciliation:
    """Apply an explicit, canonical config-to-netlist reference map.

    This is deliberately separate from :func:`validate_constraint_refs`:
    reconciliation may rename a reference only when a caller supplies the
    source-backed alias. Any name that remains unresolved is still handled by
    the existing fail-closed validator. Alias chains are canonicalized and
    cycles are rejected before a placement model can be built.
    """
    if not aliases:
        return ReferenceReconciliation(tuple(constraints))

    alias_map = dict(aliases)
    if any(not source or not target for source, target in alias_map.items()):
        raise ValueError("reference aliases must have non-empty source and target names")

    resolved: dict[str, str] = {}

    def canonical(name: str, trail: tuple[str, ...] = ()) -> str:
        if name not in alias_map:
            return name
        if name in trail:
            cycle = " -> ".join((*trail, name))
            raise ValueError(f"reference alias cycle: {cycle}")
        if name not in resolved:
            resolved[name] = canonical(alias_map[name], (*trail, name))
        return resolved[name]

    for source in alias_map:
        canonical(source)

    applied: set[tuple[str, str]] = set()
    reconciled: list[BaseConstraint] = []

    for constraint in constraints:
        updates: dict[str, object] = {}
        for field_name in _REFERENCE_FIELDS:
            if not hasattr(constraint, field_name):
                continue
            value = getattr(constraint, field_name, None)
            if isinstance(value, str):
                canonical_value = canonical(value)
                if canonical_value != value:
                    updates[field_name] = canonical_value
                    applied.add((value, canonical_value))
            elif isinstance(value, (list, tuple)):
                updated_values = []
                changed = False
                for item in value:
                    if isinstance(item, str):
                        canonical_item = canonical(item)
                        updated_values.append(canonical_item)
                        changed = changed or canonical_item != item
                        if canonical_item != item:
                            applied.add((item, canonical_item))
                    else:
                        updated_values.append(item)
                if changed:
                    updates[field_name] = (
                        tuple(updated_values) if isinstance(value, tuple) else updated_values
                    )

        if updates:
            reconciled_constraint = copy(constraint)
            for field_name, value in updates.items():
                setattr(reconciled_constraint, field_name, value)
            reconciled.append(reconciled_constraint)
        else:
            reconciled.append(constraint)

    return ReferenceReconciliation(
        tuple(reconciled),
        tuple(sorted(applied)),
    )


# ---------------------------------------------------------------------------
# SEEN: Assumption literal type alias
# ---------------------------------------------------------------------------

AssumptionLiteral = int  # index of assumption BoolVar


# ---------------------------------------------------------------------------
# Ref resolution
# ---------------------------------------------------------------------------


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
            model,
            ctx.courtyard_clearance_mm,
            constraints,
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

    logger.info(
        "Auto-generated %d courtyard SEPARATED constraints (τ=%.2fmm)", len(constraints), tau_mm
    )
    return constraints


# ---------------------------------------------------------------------------
# Constraint ref validation
# ---------------------------------------------------------------------------


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
        lines = [f"  {cid}: {', '.join(refs)}" for cid, refs in sorted(unresolved.items())]
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
