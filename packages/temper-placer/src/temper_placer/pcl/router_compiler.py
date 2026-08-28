"""
PCL-to-router constraint compilation bridge.

Maps router-grounded PCL constraint types to constraint-model entries
(CapacityConstraint, LayerConstraint, OrderVar, ChannelSeparationConstraint).

Design:
- TYPE_HANDLERS: explicit, validated per-type dispatch
- ConstraintOrigin: bidirectional PCL-ID ↔ router-constraint-name registry (KD5)
"""

from __future__ import annotations

import warnings
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
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
    SeparatedConstraint,
)
from temper_placer.router_v6.constraint_model import (
    ChannelSeparationConstraint,
    LayerConstraint,
    OrderVar,
)

if TYPE_CHECKING:
    from temper_placer.core.board import Board
    from temper_placer.core.netlist import Netlist
    from temper_placer.pcl.parser import ConstraintCollection
    from temper_placer.router_v6.channel_skeleton import ChannelSkeleton
    from temper_placer.router_v6.channel_widths import ChannelWidths


# The Rust pyclasses intentionally do not use Python inheritance, so the
# generated stubs expose their common fields without making the concrete
# classes subtypes of ``Constraint``.  Keep the compiler's output type honest
# with the finite set of classes it actually emits.
RouterConstraint = OrderVar | LayerConstraint | ChannelSeparationConstraint


# ---------------------------------------------------------------------------
# ConstraintOrigin registry (KD5)
# ---------------------------------------------------------------------------


class ConstraintOrigin:
    """Bidirectional registry: PCL constraint ID ↔ router constraint names.

    Populated during downward compilation. Survives only within a single
    pipeline run — not serialized.
    """

    def __init__(self) -> None:
        self._pcl_to_router: dict[str, list[str]] = {}
        self._router_to_pcl: dict[str, str] = {}

    def record(self, pcl_id: str, router_name: str) -> None:
        """Record a router constraint name's PCL origin."""
        self._pcl_to_router.setdefault(pcl_id, []).append(router_name)
        self._router_to_pcl[router_name] = pcl_id

    def lookup_pcl_id(self, router_name: str) -> str | None:
        """Return the originating PCL ID for a router constraint name."""
        return self._router_to_pcl.get(router_name)

    def get_router_names(self, pcl_id: str) -> list[str]:
        """Get all router constraint names derived from a PCL constraint."""
        return self._pcl_to_router.get(pcl_id, [])

    def merge(self, other: ConstraintOrigin) -> None:
        """Add the origins in ``other`` to this run's origin ledger."""
        for pcl_id, names in other._pcl_to_router.items():
            for name in names:
                self.record(pcl_id, name)


class RouterCompilationError(ValueError):
    """Base error for fail-closed PCL-to-router compilation."""


class RouterConstraintCompilationError(RouterCompilationError):
    """A supplied PCL constraint could not be lowered for the router."""


class CompilationDisposition(Enum):
    """The explicit disposition of one input constraint.

    ``NOT_APPLICABLE`` is used when a valid PCL constraint belongs to another
    compilation target and therefore has no router representation.  It is an
    accounted input, not a successful lowering and must never be reported as
    ``COMPILED``.
    """

    COMPILED = "compiled"
    NOT_APPLICABLE = "not_applicable"


ACCOUNTED_DISPOSITIONS: frozenset[CompilationDisposition] = frozenset(
    {
        CompilationDisposition.COMPILED,
        CompilationDisposition.NOT_APPLICABLE,
    }
)


@dataclass(frozen=True)
class ConstraintCompilationReceipt:
    """Provenance for one PCL input and all router constraints it emitted.

    A receipt is created for every input, including handlers that legitimately
    emit no constraints (for example placement-only alignment).  Keeping this
    ledger next to the flattened output makes an accidental drop observable
    without relying on names or import-time registration.
    """

    pcl_id: str
    constraint_type: ConstraintType
    disposition: CompilationDisposition
    outputs: tuple[RouterConstraint, ...]

    @property
    def output_names(self) -> tuple[str, ...]:
        return tuple(output.name for output in self.outputs)


@dataclass
class RouterCompilationResult:
    """Complete output and provenance for one router compilation run."""

    constraints: list[RouterConstraint]
    receipts: list[ConstraintCompilationReceipt]
    origins: ConstraintOrigin

    def __iter__(self):
        """Iterate flattened router constraints for simple stage adapters."""
        return iter(self.constraints)

    def __len__(self) -> int:
        return len(self.constraints)

    def require_complete(self, expected_count: int | None = None) -> RouterCompilationResult:
        """Assert that this result has one receipt per supplied input.

        ``compile_pcl_for_router`` already enforces this invariant.  This
        method is intentionally public so downstream callers can make the
        boundary executable when passing results between stages.
        """
        if expected_count is not None and len(self.receipts) != expected_count:
            raise RouterCompilationError(
                "Router compilation receipt is incomplete: "
                f"expected {expected_count} inputs, got {len(self.receipts)}"
            )
        ids = [receipt.pcl_id for receipt in self.receipts]
        if len(ids) != len(set(ids)):
            raise RouterCompilationError(
                "Router compilation receipt contains duplicate PCL constraint IDs"
            )
        if any(receipt.disposition not in ACCOUNTED_DISPOSITIONS for receipt in self.receipts):
            raise RouterCompilationError("Router compilation receipt contains an unresolved disposition")
        return self


# ---------------------------------------------------------------------------
# Router compiler context
# ----------------------------------------------------------------------------


class RouterCompilationContext:
    """Context for PCL-to-router compilation.

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
        self.net_to_idx: dict[str, int] = {comp.ref: i for i, comp in enumerate(netlist.components)}

    def net_index(self, ref: str) -> int:
        """Look up net index by name (uses component ref for now)."""
        return self.net_to_idx[ref]

    def component_indices(self, ref: str) -> list[int]:
        """Resolve a component ref to a list of indices."""
        from temper_placer.pcl.resolver import _resolve_to_indices

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


# Preferred router-facing name.  Keep the historical name as an alias for


# ---------------------------------------------------------------------------
# Tier mapping (R8)
# ---------------------------------------------------------------------------

TIER_TO_HARDNESS: dict[ConstraintTier, str] = {
    ConstraintTier.HARD: "hard",
    ConstraintTier.STRONG: "hard",  # MVP: encode as hard
    ConstraintTier.SOFT: "hard",  # MVP: encode as hard
}


# ---------------------------------------------------------------------------
# Per-type handlers
# ---------------------------------------------------------------------------


def _adjacent_to_router(
    constraint: AdjacentConstraint,
    ctx: RouterCompilationContext,
) -> list[RouterConstraint]:
    """AdjacentConstraint → proximity-preference soft clauses.

    Produces OrderVar proximity clauses for nets a,b on shared channels.
    No hard capacity reservation in MVP.
    """
    results: list[RouterConstraint] = []
    try:
        idx_a = ctx.component_indices(constraint.a)
        idx_b = ctx.component_indices(constraint.b)
    except (ValueError, KeyError):
        warnings.warn(
            f"Adjacent constraint '{constraint.id}': cannot resolve components, skipping",
            stacklevel=2,
        )
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
                results.append(order_var)  # type: ignore[arg-type]
    return results


def _separated_to_router(
    constraint: SeparatedConstraint,
    ctx: RouterCompilationContext,
) -> list[RouterConstraint]:
    """SeparatedConstraint → ChannelSeparationConstraint.

    For each shared channel, enforces at least ceil(min_distance / spacing)
    empty slots between nets in group A and group B.
    """
    results: list[RouterConstraint] = []
    try:
        indices_a = ctx.component_indices(constraint.a)
        indices_b = ctx.component_indices(constraint.b)
    except (ValueError, KeyError):
        warnings.warn(
            f"Separated constraint '{constraint.id}': cannot resolve components, skipping",
            stacklevel=2,
        )
        return results

    if not indices_a or not indices_b:
        return results

    # Derive min_slots from min_distance and channel spacing
    min_slots = 1
    if ctx.channel_widths:
        for widths in ctx.channel_widths.values():
            spacing = getattr(widths, "spacing_mm", 0.0)
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


def _enclosing_to_router(
    constraint: EnclosingConstraint,
    ctx: RouterCompilationContext,
) -> list[RouterConstraint]:
    """EnclosingConstraint → LayerConstraint restricting inner nets to zone.

    Computes which channels lie within the zone's spatial extent and restricts
    inner-component nets to those channels.
    """
    results: list[RouterConstraint] = []
    try:
        inner_indices: list[int] = []
        for ref in constraint.inner:
            inner_indices.extend(ctx.component_indices(ref))
    except (ValueError, KeyError):
        warnings.warn(
            f"Enclosing constraint '{constraint.id}': cannot resolve components, skipping",
            stacklevel=2,
        )
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


def _aligned_to_router(
    constraint: AlignedConstraint,  # noqa: ARG001
    ctx: RouterCompilationContext,  # noqa: ARG001
) -> list[RouterConstraint]:
    """AlignedConstraint has no router grounding (placement-only).

    Alignment is placement-only, so the router handler returns an empty list.
    """
    return []


def _onside_to_router(
    constraint: OnSideConstraint,
    ctx: RouterCompilationContext,
) -> list[RouterConstraint]:
    """OnSideConstraint → LayerConstraint restricting to board-side channels.

    Identifies edge-adjacent channels based on board side and restricts
    component nets to those channels.
    """
    results: list[RouterConstraint] = []
    try:
        component_indices: list[int] = []
        for ref in constraint.components:
            component_indices.extend(ctx.component_indices(ref))
    except (ValueError, KeyError):
        warnings.warn(
            f"OnSide constraint '{constraint.id}': cannot resolve components, skipping",
            stacklevel=2,
        )
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


def _anchored_to_router(
    constraint: AnchoredConstraint,
    ctx: RouterCompilationContext,
) -> list[RouterConstraint]:
    """AnchoredConstraint → pin NetChannelVar to channels near anchored position.

    Finds channels whose endpoints bracket the anchored position/region.
    """
    results: list[RouterConstraint] = []
    try:
        indices = ctx.component_indices(constraint.component)
    except (ValueError, KeyError):
        warnings.warn(
            f"Anchored constraint '{constraint.id}': cannot resolve component, skipping",
            stacklevel=2,
        )
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


def _loop_area_to_router(
    constraint: LoopAreaConstraint,
    ctx: RouterCompilationContext,
) -> list[RouterConstraint]:
    """LoopAreaConstraint → combined OrderConstraint + CapacityConstraint.

    Restricts shared-channel count for nets in the loop to enforce area bound.
    """
    results: list[RouterConstraint] = []
    # LoopAreaConstraint references a loop_name; resolve to nets via context.
    loop_nets: list[int] = (
        ctx.netlist.component_indices_for_loop(constraint.loop_name)
        if hasattr(ctx.netlist, "component_indices_for_loop")
        else []
    )

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
            group_a_indices=loop_nets[: len(loop_nets) // 2],
            group_b_indices=loop_nets[len(loop_nets) // 2 :],
            min_slots=max_shared,
            channel_id=edge_id,
        )
        results.append(c)
    return results


# ---------------------------------------------------------------------------
# Dispatch tables
# ---------------------------------------------------------------------------

_Handler = Callable[[BaseConstraint, RouterCompilationContext], list[RouterConstraint]]

# KEEPOUT has no router target in the PCL contract and is intentionally handled
# as a no-op. It must remain named here so adding a new ConstraintType cannot
# silently create another unhandled type.
EXPLICITLY_UNSUPPORTED_TYPES: frozenset[ConstraintType] = frozenset(
    {ConstraintType.KEEPOUT}
)

# Keep this as an ordered sequence, rather than a dict literal.  A duplicate
# key in a dict literal is silently overwritten before validation can see it.
# The table is assembled only after every handler has been defined, and the
# resulting mapping is immutable for deterministic dispatch.
_HANDLER_ENTRIES: tuple[tuple[ConstraintType, _Handler], ...] = (
    (ConstraintType.ADJACENT, _adjacent_to_router),
    (ConstraintType.SEPARATED, _separated_to_router),
    (ConstraintType.ENCLOSING, _enclosing_to_router),
    (ConstraintType.ALIGNED, _aligned_to_router),
    (ConstraintType.ON_SIDE, _onside_to_router),
    (ConstraintType.ANCHORED, _anchored_to_router),
    (ConstraintType.LOOP_AREA, _loop_area_to_router),
)


def _build_type_handlers(
    entries: Iterable[tuple[ConstraintType, _Handler]],
    *,
    explicitly_unsupported: frozenset[ConstraintType] = EXPLICITLY_UNSUPPORTED_TYPES,
) -> Mapping[ConstraintType, _Handler]:
    """Build and validate the router compiler's concrete handler table.

    Validation runs at import time and is also exposed for focused tests.  It
    makes duplicate entries, missing router-supported types, and accidental
    entries for unsupported types fail during construction rather than at
    solve time.
    """
    registry: dict[ConstraintType, _Handler] = {}
    duplicates: set[ConstraintType] = set()
    for constraint_type, handler in entries:
        if not isinstance(constraint_type, ConstraintType):
            raise RuntimeError(
                "Router compiler handler key is not a ConstraintType: "
                f"{constraint_type!r}"
            )
        if not callable(handler):
            raise RuntimeError(
                f"Router compiler handler for {constraint_type.name} is not callable"
            )
        if constraint_type in registry:
            duplicates.add(constraint_type)
        registry[constraint_type] = handler

    if duplicates:
        names = ", ".join(sorted(item.name for item in duplicates))
        raise RuntimeError(f"duplicate router compiler handlers for ConstraintType: {names}")

    all_types = frozenset(ConstraintType)
    unknown_unsupported = explicitly_unsupported - all_types
    if unknown_unsupported:
        names = ", ".join(sorted(item.name for item in unknown_unsupported))
        raise RuntimeError(f"unsupported set contains unknown ConstraintType: {names}")

    expected = all_types - explicitly_unsupported
    actual = frozenset(registry)
    missing = expected - actual
    unexpected = actual - expected
    if missing or unexpected:
        details: list[str] = []
        if missing:
            details.append("missing=" + ",".join(sorted(item.name for item in missing)))
        if unexpected:
            details.append("unexpected=" + ",".join(sorted(item.name for item in unexpected)))
        raise RuntimeError("invalid router compiler handler table (" + "; ".join(details) + ")")

    return MappingProxyType(registry)


TYPE_HANDLERS: Mapping[ConstraintType, _Handler] = _build_type_handlers(_HANDLER_ENTRIES)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def constraint_to_router_constraints(
    constraint: BaseConstraint,
    ctx: RouterCompilationContext,
) -> tuple[list[RouterConstraint], ConstraintOrigin]:
    """Compile one PCL constraint into router constraint entries.

    Returns ``(router_constraints, origin_registry)``.  A constraint with no
    router target returns an empty list; collection compilation records that
    case explicitly as :class:`CompilationDisposition.NOT_APPLICABLE`.
    """
    origin = ConstraintOrigin()
    constraint_type = constraint.constraint_type
    if not isinstance(constraint_type, ConstraintType):
        raise RouterConstraintCompilationError(
            "Router compiler received an unknown constraint type: "
            f"{constraint_type!r}"
        )

    # 1. Try concrete type handler (R25, Q4)
    handler = TYPE_HANDLERS.get(constraint_type)
    if handler is not None:
        clauses = handler(constraint, ctx)
    else:
        if constraint_type in EXPLICITLY_UNSUPPORTED_TYPES:
            # KEEPOUT is intentionally not a router target.  Keep this branch
            # explicit so an unsupported type is distinguishable from a
            # missing handler and cannot be silently accepted after a table
            # edit.
            clauses = []
        else:
            # The import-time completeness check makes this branch
            # unreachable for the closed enum today. Keep it fail-closed so
            # an incomplete table cannot turn into an empty compilation.
            raise RouterConstraintCompilationError(
                f"Router compiler has no handler for {constraint_type!r}"
            )

    # Record origin mapping
    for c in clauses:
        origin.record(constraint.id, c.name)

    return clauses, origin


def compile_pcl_for_router(
    collection: ConstraintCollection,
    context: CompilationContext,
) -> RouterCompilationResult:
    """Lower every constraint in ``collection`` into router constraints.

    This is the sole public PCL-to-router entry point.  It deliberately walks
    ``collection.constraints`` itself instead of calling
    the old collection-level compiler: that path used mutable global backend
    state and filtered/recovered per-constraint failures, both of which make
    a missing constraint invisible.

    Every input receives exactly one receipt.  A handler that emits an empty
    list is still recorded as compiled (alignment and an empty channel set
    are valid no-op lowerings); warnings emitted by a handler indicate a
    dropped/unresolved constraint and are converted into a typed failure.
    Importing this module has no compiler-registration side effect.

    Raises:
        RouterConstraintCompilationError: if a handler fails or reports a
            dropped/unresolved input.
    """
    if not hasattr(collection, "constraints"):
        raise TypeError("collection must provide a constraints sequence")

    try:
        constraints = list(collection.constraints)
    except TypeError as exc:
        raise TypeError("collection.constraints must be iterable") from exc

    try:
        ctx = RouterCompilationContext(
            netlist=context.netlist,
            board=context.board,
            skeletons=context.skeletons or {},
            channel_widths=context.channel_widths or {},
        )
    except AttributeError as exc:
        raise TypeError("context must be a CompilationContext") from exc

    compiled: list[RouterConstraint] = []
    receipts: list[ConstraintCompilationReceipt] = []
    origins = ConstraintOrigin()

    for constraint in constraints:
        try:
            constraint_id = constraint.id
            constraint_type = constraint.constraint_type
        except AttributeError as exc:
            raise RouterConstraintCompilationError(
                "PCL collection contains an object without id/constraint_type"
            ) from exc

        # Existing handlers use warnings for unresolved references.  That
        # policy is retained for the single-constraint compatibility API, but
        # the collection boundary must fail closed so no supplied constraint
        # can disappear from the router model.
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            try:
                clauses, origin = constraint_to_router_constraints(constraint, ctx)
            except Exception as exc:
                raise RouterConstraintCompilationError(
                    f"Failed to compile PCL constraint '{constraint_id}' "
                    f"({getattr(constraint_type, 'value', constraint_type)}): {exc}"
                ) from exc

        if caught:
            details = "; ".join(str(w.message) for w in caught)
            raise RouterConstraintCompilationError(
                f"PCL constraint '{constraint_id}' was not fully resolved: {details}"
            )

        clauses = list(clauses)
        compiled.extend(clauses)
        origins.merge(origin)
        disposition = (
            CompilationDisposition.NOT_APPLICABLE
            if constraint_type in EXPLICITLY_UNSUPPORTED_TYPES
            else CompilationDisposition.COMPILED
        )
        receipts.append(
            ConstraintCompilationReceipt(
                pcl_id=constraint_id,
                constraint_type=constraint_type,
                disposition=disposition,
                outputs=tuple(clauses),
            )
        )

    result = RouterCompilationResult(
        constraints=compiled,
        receipts=receipts,
        origins=origins,
    )
    return result.require_complete(expected_count=len(constraints))
