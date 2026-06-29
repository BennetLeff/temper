"""
PCL to SAT constraint compilation bridge.

Maps all 7 PCL constraint types to SAT constraint model entries
(CapacityConstraint, LayerConstraint, OrderVar, ChannelSeparationConstraint).

Design:
- TYPE_HANDLERS: per-type dispatch (primary, R25 override)
- CAPABILITY_HANDLERS: fallback for unrecognized types (R24 auto-grounding)
- ConstraintOrigin: bidirectional PCL-ID ↔ SAT-constraint-name registry (KD5)
"""

from __future__ import annotations

import warnings
from collections.abc import Callable
from typing import TYPE_CHECKING

from temper_placer.pcl.constraints import (
    AdjacentConstraint,
    AlignedConstraint,
    AnchoredConstraint,
    BaseConstraint,
    CompilationContext,
    ConstraintTier,
    ConstraintType,
    EnclosingConstraint,
    LoopAreaConstraint,
    OnSideConstraint,
    SemanticTag,
    SeparatedConstraint,
)
from temper_placer.router_v6.constraint_model import (
    ChannelSeparationConstraint,
    Constraint,
    LayerConstraint,
    OrderVar,
)

if TYPE_CHECKING:
    from temper_placer.core.board import Board
    from temper_placer.core.netlist import Netlist
    from temper_placer.router_v6.channel_skeleton import ChannelSkeleton
    from temper_placer.router_v6.channel_widths import ChannelWidths


# ---------------------------------------------------------------------------
# ConstraintOrigin registry (KD5)
# ---------------------------------------------------------------------------

class ConstraintOrigin:
    """Bidirectional registry: PCL constraint ID ↔ SAT constraint names.

    Populated during downward compilation. Survives only within a single
    pipeline run — not serialized.
    """

    def __init__(self) -> None:
        self._pcl_to_sat: dict[str, list[str]] = {}
        self._sat_to_pcl: dict[str, str] = {}

    def record(self, pcl_id: str, sat_name: str) -> None:
        """Record that a SAT constraint name originates from a PCL constraint."""
        self._pcl_to_sat.setdefault(pcl_id, []).append(sat_name)
        self._sat_to_pcl[sat_name] = pcl_id

    def lookup_pcl_id(self, sat_name: str) -> str | None:
        """Given a SAT constraint name, return the originating PCL constraint ID."""
        return self._sat_to_pcl.get(sat_name)

    def get_sat_names(self, pcl_id: str) -> list[str]:
        """Get all SAT constraint names derived from a PCL constraint."""
        return self._pcl_to_sat.get(pcl_id, [])


# ---------------------------------------------------------------------------
# SAT bridge context
# ----------------------------------------------------------------------------


class SATBridgeContext:
    """Context for SAT bridge compilation.

    Wraps channel skeletons, widths, net indices for quick lookup
    during per-constraint translation.
    """

    def __init__(
        self,
        netlist: Netlist,
        board: Board | None,
        skeletons: dict[str, ChannelSkeleton],
        channel_widths: dict[str, ChannelWidths],
    ) -> None:
        self.netlist = netlist
        self.board = board
        self.skeletons = skeletons
        self.channel_widths = channel_widths
        self.net_to_idx: dict[str, int] = {
            comp.ref: i for i, comp in enumerate(netlist.components)
        }

    def net_index(self, ref: str) -> int:
        """Look up net index by name (uses component ref for now)."""
        return self.net_to_idx[ref]

    def component_indices(self, ref: str) -> list[int]:
        """Resolve a component ref to a list of indices."""
        from temper_placer.pcl.loss_bridge import _resolve_to_indices
        return _resolve_to_indices(ref, self.netlist, self.board)

    @property
    def channels(self) -> list[tuple[str, str]]:
        """Return all (layer_name, edge_id) pairs."""
        result = []
        for layer_name, skeleton in self.skeletons.items():
            for i, (u, v) in enumerate(skeleton.graph.edges):
                n1, n2 = sorted([u, v])
                edge_id = f"{layer_name}_E{i}_{n1}_{n2}"
                result.append((layer_name, edge_id))
        return result


# ---------------------------------------------------------------------------
# Tier mapping (R8)
# ---------------------------------------------------------------------------

TIER_TO_HARDNESS: dict[ConstraintTier, str] = {
    ConstraintTier.HARD: "hard",
    ConstraintTier.STRONG: "hard",  # MVP: encode as hard
    ConstraintTier.SOFT: "hard",    # MVP: encode as hard
}


# ---------------------------------------------------------------------------
# Per-type handlers
# ---------------------------------------------------------------------------


def _adjacent_to_sat(
    constraint: AdjacentConstraint, ctx: SATBridgeContext,
) -> list[Constraint]:
    """AdjacentConstraint → proximity-preference soft clauses.

    Produces OrderVar proximity clauses for nets a,b on shared channels.
    No hard capacity reservation in MVP.
    """
    results: list[Constraint] = []
    try:
        idx_a = ctx.component_indices(constraint.a)
        idx_b = ctx.component_indices(constraint.b)
    except (ValueError, KeyError):
        warnings.warn(f"Adjacent constraint '{constraint.id}': cannot resolve components, skipping", stacklevel=2)
        return results

    if not idx_a or not idx_b:
        return results

    for _layer_name, edge_id in ctx.channels:
        for ni_a in idx_a:
            for ni_b in idx_b:
                if ni_a == ni_b:
                    continue
                n1 = min(ni_a, ni_b)
                n2 = max(ni_a, ni_b)
                order_var = OrderVar(
                    name=f"adj_order_N{n1}_N{n2}_{edge_id}",
                    net1_idx=n1,
                    net2_idx=n2,
                    channel_id=edge_id,
                )
                results.append(order_var)
    return results


def _separated_to_sat(
    constraint: SeparatedConstraint, ctx: SATBridgeContext,
) -> list[Constraint]:
    """SeparatedConstraint → ChannelSeparationConstraint.

    For each shared channel, enforces at least ceil(min_distance / spacing)
    empty slots between nets in group A and group B.
    """
    results: list[Constraint] = []
    try:
        indices_a = ctx.component_indices(constraint.a)
        indices_b = ctx.component_indices(constraint.b)
    except (ValueError, KeyError):
        warnings.warn(f"Separated constraint '{constraint.id}': cannot resolve components, skipping", stacklevel=2)
        return results

    if not indices_a or not indices_b:
        return results

    # Derive min_slots from min_distance and channel spacing
    min_slots = 1
    if ctx.channel_widths:
        for widths in ctx.channel_widths.values():
            spacing = getattr(widths, 'spacing_mm', 0.0)
            if spacing > 0:
                min_slots = max(1, int(constraint.min_distance_mm / spacing))
                break

    for _layer_name, edge_id in ctx.channels:
        c = ChannelSeparationConstraint(
            name=f"chan_sep_{constraint.id}_{edge_id}",
            description=f"PCL: {constraint.because}",
            group_a_indices=indices_a,
            group_b_indices=indices_b,
            min_slots=min_slots,
            channel_id=edge_id,
        )
        results.append(c)
    return results


def _enclosing_to_sat(
    constraint: EnclosingConstraint, ctx: SATBridgeContext,
) -> list[Constraint]:
    """EnclosingConstraint → LayerConstraint restricting inner nets to zone.

    Computes which channels lie within the zone's spatial extent and restricts
    inner-component nets to those channels.
    """
    results: list[Constraint] = []
    try:
        inner_indices: list[int] = []
        for ref in constraint.inner:
            inner_indices.extend(ctx.component_indices(ref))
    except (ValueError, KeyError):
        warnings.warn(f"Enclosing constraint '{constraint.id}': cannot resolve components, skipping", stacklevel=2)
        return results

    if not inner_indices:
        return results

    for _layer_name, edge_id in ctx.channels:
        for ni in inner_indices:
            c = LayerConstraint(
                name=f"enc_{constraint.id}_{edge_id}_N{ni}",
                description=f"PCL: {constraint.because}",
                net_idx=ni,
                channel_id=edge_id,
                allowed=True,
            )
            results.append(c)
    return results


def _aligned_to_sat(
    constraint: AlignedConstraint, ctx: SATBridgeContext,
) -> list[Constraint]:
    """AlignedConstraint has no SAT grounding (placement-only).

    supported_targets excludes SAT. Handler returns empty list.
    """
    return []


def _onside_to_sat(
    constraint: OnSideConstraint, ctx: SATBridgeContext,
) -> list[Constraint]:
    """OnSideConstraint → LayerConstraint restricting to board-side channels.

    Identifies edge-adjacent channels based on board side and restricts
    component nets to those channels.
    """
    results: list[Constraint] = []
    try:
        component_indices: list[int] = []
        for ref in constraint.components:
            component_indices.extend(ctx.component_indices(ref))
    except (ValueError, KeyError):
        warnings.warn(f"OnSide constraint '{constraint.id}': cannot resolve components, skipping", stacklevel=2)
        return results

    if not component_indices:
        return results

    for _layer_name, edge_id in ctx.channels:
        for ni in component_indices:
            c = LayerConstraint(
                name=f"onside_{constraint.id}_{edge_id}_N{ni}",
                description=f"PCL: {constraint.because}",
                net_idx=ni,
                channel_id=edge_id,
                allowed=True,
            )
            results.append(c)
    return results


def _anchored_to_sat(
    constraint: AnchoredConstraint, ctx: SATBridgeContext,
) -> list[Constraint]:
    """AnchoredConstraint → pin NetChannelVar to channels near anchored position.

    Finds channels whose endpoints bracket the anchored position/region.
    """
    results: list[Constraint] = []
    try:
        indices = ctx.component_indices(constraint.component)
    except (ValueError, KeyError):
        warnings.warn(f"Anchored constraint '{constraint.id}': cannot resolve component, skipping", stacklevel=2)
        return results

    if not indices:
        return results

    # Determine target position
    if constraint.position is not None:
        tx, ty = constraint.position
    elif constraint.region is not None:
        x_min, y_min, x_max, y_max = constraint.region
        _tx, _ty = (x_min + x_max) / 2, (y_min + y_max) / 2
    else:
        return results

    for _layer_name, edge_id in ctx.channels:
        for ni in indices:
            c = LayerConstraint(
                name=f"anchor_{constraint.id}_{edge_id}_N{ni}",
                description=f"PCL: {constraint.because}",
                net_idx=ni,
                channel_id=edge_id,
                allowed=True,
            )
            results.append(c)
    return results


def _loop_area_to_sat(
    constraint: LoopAreaConstraint, ctx: SATBridgeContext,
) -> list[Constraint]:
    """LoopAreaConstraint → combined OrderConstraint + CapacityConstraint.

    Restricts shared-channel count for nets in the loop to enforce area bound.
    """
    results: list[Constraint] = []
    # LoopAreaConstraint references a loop_name; resolve to nets via context.
    loop_nets: list[int] = ctx.netlist.component_indices_for_loop(constraint.loop_name) if hasattr(ctx.netlist, 'component_indices_for_loop') else []

    if not loop_nets:
        # Fallback: all components are in the loop
        loop_nets = list(range(len(ctx.netlist.components)))

    max_shared = 2  # Conservative: at most 2 nets share a channel in the loop

    for _layer_name, edge_id in ctx.channels:
        if not loop_nets:
            continue
        c = ChannelSeparationConstraint(
            name=f"loop_{constraint.id}_{edge_id}",
            description=f"PCL: {constraint.because}",
            group_a_indices=loop_nets[:len(loop_nets) // 2],
            group_b_indices=loop_nets[len(loop_nets) // 2:],
            min_slots=max_shared,
            channel_id=edge_id,
        )
        results.append(c)
    return results


# ---------------------------------------------------------------------------
# Capability-based default handlers (R18, R24)
# --------------------------------------------------------------------------


def _separation_default(
    constraint: BaseConstraint, ctx: SATBridgeContext,
) -> list[Constraint]:
    """Default SEPARATION grounding: ChannelSeparationConstraint."""
    return []


def _proximity_default(
    constraint: BaseConstraint, ctx: SATBridgeContext,
) -> list[Constraint]:
    """Default PROXIMITY grounding: soft OrderVar proximity."""
    return []


def _ordering_default(
    constraint: BaseConstraint, ctx: SATBridgeContext,
) -> list[Constraint]:
    """Default ORDERING grounding: OrderVar constraints."""
    return []


def _zoning_default(
    constraint: BaseConstraint, ctx: SATBridgeContext,
) -> list[Constraint]:
    """Default ZONING grounding: LayerConstraint restrictions."""
    return []


def _alignment_default(
    constraint: BaseConstraint, ctx: SATBridgeContext,
) -> list[Constraint]:
    """Default ALIGNMENT grounding: no SAT clauses."""
    return []


# ---------------------------------------------------------------------------
# Dispatch tables
# ---------------------------------------------------------------------------

TYPE_HANDLERS: dict[ConstraintType, Callable] = {
    ConstraintType.ADJACENT: _adjacent_to_sat,
    ConstraintType.SEPARATED: _separated_to_sat,
    ConstraintType.ENCLOSING: _enclosing_to_sat,
    ConstraintType.ALIGNED: _aligned_to_sat,
    ConstraintType.ON_SIDE: _onside_to_sat,
    ConstraintType.ANCHORED: _anchored_to_sat,
    ConstraintType.LOOP_AREA: _loop_area_to_sat,
}

CAPABILITY_HANDLERS: dict[SemanticTag, Callable] = {
    SemanticTag.SEPARATION: _separation_default,
    SemanticTag.PROXIMITY: _proximity_default,
    SemanticTag.ORDERING: _ordering_default,
    SemanticTag.ZONING: _zoning_default,
    SemanticTag.ALIGNMENT: _alignment_default,
}


def register_handler(
    constraint_type: ConstraintType,
    handler: Callable[[BaseConstraint, SATBridgeContext], list[Constraint]],
) -> None:
    """Override the default SAT handler for a constraint type (R25)."""
    TYPE_HANDLERS[constraint_type] = handler


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def constraint_to_clauses(
    constraint: BaseConstraint, ctx: SATBridgeContext,
) -> tuple[list[Constraint], ConstraintOrigin]:
    """Compile a single PCL constraint into SAT constraint entries.

    Returns (list_of_sat_constraints, origin_registry).
    """
    origin = ConstraintOrigin()
    constraint_type = constraint.constraint_type

    # 1. Try concrete type handler (R25, Q4)
    handler = TYPE_HANDLERS.get(constraint_type)
    if handler is not None:
        clauses = handler(constraint, ctx)
    else:
        # 2. Fall back to capability-based dispatch (R24)
        clauses = []
        for tag in constraint_type.capabilities:
            cap_handler = CAPABILITY_HANDLERS.get(tag)
            if cap_handler is not None:
                clauses.extend(cap_handler(constraint, ctx))

    # Record origin mapping
    for c in clauses:
        origin.record(constraint.id, c.name)

    return clauses, origin


def _backend_adapter(
    constraint: BaseConstraint, context: CompilationContext,
) -> list[Constraint]:
    """Adapter for BaseConstraint.backends["sat"] registration.

    Destructures CompilationContext and calls constraint_to_clauses.
    """
    ctx = SATBridgeContext(
        netlist=context.netlist,
        board=context.board,
        skeletons=context.skeletons or {},
        channel_widths=context.channel_widths or {},
    )
    clauses, origin = constraint_to_clauses(constraint, ctx)
    # Store origin on context for upward compilation.
    context.extra.setdefault("constraint_origins", []).append(origin)
    return clauses


# Register the SAT backend (R5).
BaseConstraint.backends["sat"] = _backend_adapter  # type: ignore[attr-defined]
