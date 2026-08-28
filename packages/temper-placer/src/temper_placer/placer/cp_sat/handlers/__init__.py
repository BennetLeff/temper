"""The complete, explicit CP-SAT constraint-handler table.

Handler modules stay split by constraint type, but dispatch ownership lives
here.  Keeping the table as an ordinary value (rather than populating a
mutable global from decorators) means that importing one handler cannot
silently change the set of handlers available to the encoder.

``ConstraintType`` is a closed enum in the PCL contract.  The completeness
check below is intentionally run while this package is imported: adding a
new constraint type without adding a handler (or adding it to the explicit
unsupported set) is an immediate error, not a constraint that gets skipped
at solve time.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from types import MappingProxyType

from temper_placer.pcl.constraints import ConstraintType
from temper_placer.placer.cp_sat.handlers._protocol import (
    AssumptionLiteral,
    ConstraintHandler,
)
from temper_placer.placer.cp_sat.handlers.adjacent import encode_adjacent
from temper_placer.placer.cp_sat.handlers.aligned import encode_aligned
from temper_placer.placer.cp_sat.handlers.anchored import encode_anchored
from temper_placer.placer.cp_sat.handlers.enclosing import encode_enclosing
from temper_placer.placer.cp_sat.handlers.keepout import encode_keepout
from temper_placer.placer.cp_sat.handlers.loop_area import encode_loop_area
from temper_placer.placer.cp_sat.handlers.onside import encode_onside
from temper_placer.placer.cp_sat.handlers.separated import encode_separated

# This set is deliberately named and explicit.  A new enum member must be
# handled in the table above or consciously listed here with a follow-up
# implementation plan; it may not become an accidental runtime drop.
EXPLICITLY_UNSUPPORTED_TYPES: frozenset[ConstraintType] = frozenset()

_Handler = Callable[..., list[AssumptionLiteral]]
_HANDLER_ENTRIES: tuple[tuple[ConstraintType, _Handler], ...] = (
    (ConstraintType.ADJACENT, encode_adjacent),
    (ConstraintType.ALIGNED, encode_aligned),
    (ConstraintType.ANCHORED, encode_anchored),
    (ConstraintType.ENCLOSING, encode_enclosing),
    (ConstraintType.KEEPOUT, encode_keepout),
    (ConstraintType.LOOP_AREA, encode_loop_area),
    (ConstraintType.ON_SIDE, encode_onside),
    (ConstraintType.SEPARATED, encode_separated),
)


def _build_handler_catalog(
    entries: Iterable[tuple[ConstraintType, _Handler]],
    *,
    explicitly_unsupported: frozenset[ConstraintType] = EXPLICITLY_UNSUPPORTED_TYPES,
) -> Mapping[ConstraintType, _Handler]:
    """Build and validate the one CP-SAT handler catalog.

    The entries are represented as a sequence instead of a dict literal so a
    duplicate key cannot be silently overwritten by Python.  The checks are
    kept in this small function both for import-time enforcement and for a
    focused test that proves the failure modes future edits must preserve.
    """
    registry: dict[ConstraintType, _Handler] = {}
    duplicates: set[ConstraintType] = set()
    for constraint_type, handler in entries:
        if not isinstance(constraint_type, ConstraintType):
            raise RuntimeError(
                "CP-SAT handler key is not a ConstraintType: "
                f"{constraint_type!r}"
            )
        if not callable(handler):
            raise RuntimeError(
                f"CP-SAT handler for {constraint_type.name} is not callable"
            )
        if constraint_type in registry:
            duplicates.add(constraint_type)
        registry[constraint_type] = handler

    if duplicates:
        names = ", ".join(sorted(item.name for item in duplicates))
        raise RuntimeError(f"duplicate CP-SAT handlers for ConstraintType: {names}")

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
        raise RuntimeError("invalid CP-SAT handler table (" + "; ".join(details) + ")")

    return MappingProxyType(registry)


# MappingProxyType makes the dispatch surface immutable after import.  Tests
# and mutation tools that need alternate behavior must pass an explicit
# catalog to ``encode_constraints`` rather than altering process-global state.
CP_SAT_HANDLER_CATALOG: Mapping[ConstraintType, _Handler] = _build_handler_catalog(
    _HANDLER_ENTRIES
)

__all__ = [
    "AssumptionLiteral",
    "ConstraintHandler",
    "EXPLICITLY_UNSUPPORTED_TYPES",
    "CP_SAT_HANDLER_CATALOG",
    "_build_handler_catalog",
]
