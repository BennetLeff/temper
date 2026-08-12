"""HV/LV pre-placement guard strip. @req(2026-06-23-001, FR1, FR2, FR3, FR6, FR7, FR8, FR9)"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import temper_drc_rs as _drc
import temper_orchestration as _to
from pydantic import BaseModel, ConfigDict
from shapely.geometry import Polygon

from ..state import BoardState
from .base import Stage

logger = logging.getLogger(__name__)


class PartitionError(Exception):
    def __init__(
        self,
        bucket: object,
        largest_ref: object,
        region_area_mm2: float,
        required_area_mm2: float,
    ) -> None:
        self.bucket, self.largest_ref = bucket, largest_ref
        self.region_area_mm2, self.required_area_mm2 = region_area_mm2, required_area_mm2
        super().__init__(
            f"PartitionError: {bucket} cannot fit {largest_ref} ({region_area_mm2:.2f}mm^2 < {required_area_mm2:.2f}mm^2)"
        )


class HvLvGuardConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    enabled: bool = True
    width_mm: float | None = None
    fallback_to_unconstrained: bool = True


def load_guard_config(config: Mapping[str, Any] | None) -> HvLvGuardConfig:
    if not config:
        return HvLvGuardConfig()
    block = getattr(config, "get", lambda _: None)("hv_lv_guard_strip")
    if block is not None and not isinstance(block, Mapping):
        logger.warning("hv_lv_guard_strip block is not a mapping; using defaults")
        return HvLvGuardConfig()
    if not block:
        return HvLvGuardConfig()
    return HvLvGuardConfig(**dict(block))


def _outline(board: Any) -> Polygon:
    p = getattr(board, "outline_polygon", None)
    return (
        Polygon(p)
        if p
        else Polygon([(0, 0), (board.width, 0), (board.width, board.height), (0, board.height)])
    )


def _nets(netlist: object, ref: str) -> list[object]:
    g = getattr(netlist, "get_component_nets", None)
    return (
        list(g(ref)) if callable(g) else list(getattr(netlist, "_component_nets", {}).get(ref, []))
    )


def _area(c: object) -> float:
    b = getattr(c, "bounds", None) or (0, 0)
    return _drc.component_bounds_area_py((float(b[0]), float(b[1])))


def _rules_by_net(state: Any) -> dict[Any, Any]:
    dr = getattr(getattr(state, "drc_oracle", None), "design_rules", None)
    if dr is None:
        return {}
    classes, assigns = (
        getattr(dr, "net_classes", {}) or {},
        getattr(dr, "net_class_assignments", {}) or {},
    )
    gr = getattr(dr, "get_rules_for_net", None)
    out = {}
    for net in getattr(state.netlist, "nets", []):
        name, nc = getattr(net, "name", None), getattr(net, "net_class", None)
        if not name:
            continue
        if nc and nc in classes:
            out[name] = classes[nc]
        elif name in assigns and assigns[name] in classes:
            out[name] = classes[assigns[name]]
        elif callable(gr):
            out[name] = gr(name, nc)
    return out


class HvLvPartitionStage(Stage):
    @property
    def name(self) -> str:
        return "hv_lv_partition"

    def run(self, state: BoardState) -> BoardState:
        """Partition components into HV-edge / LV-interior domains.

        Phase D batch D7 of the Rust Orchestration Engine plan (2026-08-09-001):
        the **run orchestration** (the config load + guards, the
        ``_rules_by_net`` / ``_nets`` / ``_area`` reading, the design-bundle
        ``hv_lv_classify`` / ``hv_lv_area_check`` kernel calls, the decision
        dispatch, the ``PartitionError`` raise decisions and the
        ``component_domain_map`` / ``routing_corridors`` / ``domain_regions``
        write) is implemented in Rust (``temper-orchestration``'s
        ``HvLvPartitionStage`` / ``run_hv_lv_partition``), crossing the FFI
        once per stage call. The `PartitionError` class, the pydantic guard
        config, the shapely outline + ``compute_guard_strip`` GEOS surface
        and the ``_rules_by_net`` / ``_nets`` / ``_area`` duck-typed readers
        stay Python (the Rust stage calls the helpers back; ``_rules_by_net``
        is inlined and pinned by the differential). ``_area``'s bounds product
        delegates to ``temper_drc_rs.component_bounds_area_py`` (Wave 4
        orchestration-port). The pre-migration
        implementation is pinned VERBATIM in
        ``tests/deterministic/_hv_lv_partition_run_py_oracle.py``.
        """
        return _to.run_hv_lv_partition(state)


__all__ = ["PartitionError", "HvLvGuardConfig", "load_guard_config", "HvLvPartitionStage"]
