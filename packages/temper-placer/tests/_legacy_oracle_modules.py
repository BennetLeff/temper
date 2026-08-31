"""Install test-only module sentinels for immutable pre-migration oracles.

Some pinned oracle bodies retain imports of historical production module
paths.  Those paths are intentionally deleted once their live callers have
been migrated; changing the oracle body would invalidate its differential
proof.  The tests therefore install the smallest possible in-memory modules
before importing an oracle.  No compatibility module is shipped in the
production package.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from types import ModuleType

import temper_orchestration as _to


@dataclass
class GridCell:
    """Historical router grid value retained only for pinned-oracle tests."""

    x: int
    y: int
    layer: int = 0


class DAGError(Exception):
    """Test-only historical exception namespace for pinned parser oracles."""


class DAGExprError(DAGError):
    pass


class DAGExprSyntaxError(DAGError):
    pass


# Keep diagnostics from old tests stable while making the compatibility
# module genuinely in-memory.  These classes have no production owner after
# the DAG parser migration, but immutable parser oracles still import them.
for _cls in (DAGError, DAGExprError, DAGExprSyntaxError):
    _cls.__module__ = "temper_placer.pipeline.dag_types"


def _module(name: str, **symbols: object) -> None:
    module = ModuleType(name)
    module.__all__ = list(symbols)
    for symbol, value in symbols.items():
        setattr(module, symbol, value)
    sys.modules.setdefault(name, module)


def isolation_slot_aabb(slot: object, component_xy: tuple[float, float]) -> tuple[tuple[float, float], tuple[float, float]]:
    """Historical test-only AABB helper for the immutable D5 oracle.

    The production re-export was deleted; keeping this tiny copy in the test
    sentinel lets the pinned oracle retain its original import path without
    restoring a compatibility module in the package.
    """
    sx, sy = slot.start_offset
    ex, ey = slot.end_offset
    width_mm = slot.width_mm
    cx, cy = component_xy
    x_lo, x_hi = min(sx, ex), max(sx, ex)
    y_lo, y_hi = min(sy, ey), max(sy, ey)
    half_width = width_mm / 2.0
    if abs(ex - sx) >= abs(ey - sy):
        y_lo -= half_width
        y_hi += half_width
    else:
        x_lo -= half_width
        x_hi += half_width
    return ((cx + x_lo, cy + y_lo), (cx + x_hi, cy + y_hi))


def install() -> None:
    """Provide historical imports needed only while loading pinned oracles."""

    from temper_geometry import get_rotated_bounds

    from temper_placer.deterministic.stages import (
        ConfigAttachStage,
        SlotGenerationStage,
    )

    _module(
        "temper_placer.deterministic.stages.config_attach",
        ConfigAttachStage=ConfigAttachStage,
    )
    _module(
        "temper_placer.deterministic.stages.slot_generation",
        SlotGenerationStage=SlotGenerationStage,
    )
    _module("temper_placer.geometry.transform", get_rotated_bounds=get_rotated_bounds)
    _module(
        "temper_placer.io.isolation_slot_geometry",
        isolation_slot_aabb=isolation_slot_aabb,
    )
    # ``path_simplify``'s immutable oracle imports this historical path.  It
    # is intentionally installed in memory so deleting the production facade
    # cannot turn a test fixture into a shipped compatibility API.
    _module("temper_placer.router_v6.grid_types", GridCell=GridCell)
    _module(
        "temper_placer.explainability.trace",
        Entry=_to.Entry,
        Trace=_to.Trace,
    )
    _module(
        "temper_placer.pipeline.dag_types",
        DataContext=dict,
        DAGError=DAGError,
        DAGExprError=DAGExprError,
        DAGExprSyntaxError=DAGExprSyntaxError,
        _rs=_to,
    )
