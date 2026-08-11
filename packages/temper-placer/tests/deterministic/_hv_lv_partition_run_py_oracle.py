"""
D7 run-orchestration oracle for `deterministic/stages/hv_lv_partition.py`.

Verbatim pre-D7 snapshot of the module at the D7 dispatch base (origin/main
`3a7dd1d9`), with ONLY the documented relative-import rewrites below. The body
below `# --- BEGIN PINNED BODY ---` is byte-identical to the module except for
the three relative imports (`from ..geometry.guard_strip` / `from ..state` /
`from .base`) rewritten to their absolute forms so the oracle imports from the
test tree; the D7 Rust port (`temper-orchestration::HvLvPartitionStage`) is
the differential subject, pinned by `test_deterministic_d7_rust_differential.py`.
The classification / area-decision kernels (`hv_lv_classify` / `hv_lv_area_check`)
stay single-source in `temper_design_bundle_python.hv_lv_partition`; the
pydantic config model, the shapely outline + guard-strip GEOS surface and the
duck-typed `_rules_by_net` / `_nets` / `_area` readers stay Python and are
called back by the port.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import replace
from typing import Any

import temper_design_bundle_python as _tdb
from pydantic import BaseModel, ConfigDict
from shapely.geometry import Polygon

from temper_placer.deterministic.geometry.guard_strip import compute_guard_strip
from temper_placer.deterministic.state import BoardState
from temper_placer.deterministic.stages.base import Stage

# --- BEGIN PINNED BODY ---

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
    return float(b[0]) * float(b[1])


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

        The pure decision (safety-category classification + creepage max,
        width resolution, per-bucket area check) delegates to
        ``temper_design_bundle_python.hv_lv_partition``; the ``run``
        orchestration stays Python: the state/netlist guards, the
        ``_rules_by_net`` / ``_nets`` reading, the ``_area`` marshalling, the
        shapely outline + ``compute_guard_strip`` GEOS surface, the
        ``PartitionError`` construction, and the ``dataclasses.replace``
        wrap. The pre-migration implementation is pinned VERBATIM as the
        differential oracle (``tests/deterministic/_hv_lv_partition_py_oracle.py``).
        """
        cfg = load_guard_config(state.config)
        if not cfg.enabled or state.board is None or state.netlist is None:
            return state
        rules = _rules_by_net(state)
        rules_marshalled = {
            name: (getattr(r, "safety_category", None) or "", float(getattr(r, "creepage_mm", 0.0) or 0.0))
            for name, r in rules.items()
        }
        components_nets = [(c.ref, _nets(state.netlist, c.ref)) for c in state.netlist.components]
        decision, hv, lv, creepage, width, dual = _tdb.hv_lv_partition.hv_lv_classify(
            components_nets, rules_marshalled, cfg.width_mm
        )
        for ref in dual:
            logger.warning("dual-domain %s -> LV bucket", ref)
        if decision == "skip_empty":
            logger.info("empty HV/LV bucket (hv=%d lv=%d); skipping", len(hv), len(lv))
            return state
        if decision == "skip_zero":
            return state
        if cfg.width_mm is not None and cfg.width_mm < creepage:
            logger.warning(
                "hv_lv_guard_strip.width_mm=%s below creepage %s, using creepage",
                cfg.width_mm,
                creepage,
            )
        outline = _outline(state.board)
        if outline.exterior is None or not outline.exterior.is_closed:
            raise PartitionError("geometry", "outline", 0.0, 0.0)
        try:
            hv_poly, lv_poly, corridor = compute_guard_strip(outline, width)
        except ValueError as exc:
            raise PartitionError("geometry", "outline", 0.0, 0.0) from exc
        comp = {c.ref: c for c in state.netlist.components}
        areas = {ref: _area(comp[ref]) for ref in hv + lv}
        outcome, bucket, largest, region_area, required_area = _tdb.hv_lv_partition.hv_lv_area_check(
            hv,
            lv,
            areas,
            float(hv_poly.area),
            bool(hv_poly.is_empty),
            float(lv_poly.area),
            bool(lv_poly.is_empty),
            cfg.fallback_to_unconstrained,
        )
        if outcome == "fallback":
            logger.warning(
                "insufficient %s bucket area: %s requires %.2fmm^2, region has %.2fmm^2",
                bucket,
                largest,
                required_area,
                region_area,
            )
            return state
        if outcome == "raise":
            raise PartitionError(bucket, largest, region_area, required_area)
        domain = [(r, "HV_edge") for r in hv] + [(r, "LV_interior") for r in lv]
        return replace(
            state,
            component_domain_map=frozenset(domain),
            routing_corridors=(corridor,),
            domain_regions=(hv_poly, lv_poly),
        )


__all__ = ["PartitionError", "HvLvGuardConfig", "load_guard_config", "HvLvPartitionStage"]
