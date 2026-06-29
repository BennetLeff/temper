"""HV/LV pre-placement guard strip. @req(2026-06-23-001, FR1, FR2, FR3, FR6, FR7, FR8, FR9)"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from pydantic import BaseModel, ConfigDict
from shapely.geometry import Polygon

from ..geometry.guard_strip import compute_guard_strip
from ..state import BoardState
from .base import Stage

logger = logging.getLogger(__name__)
_HV, _LV = frozenset({"HV", "AC"}), frozenset({"LV", "iso"})


class PartitionError(Exception):
    def __init__(self, bucket, largest_ref, region_area_mm2, required_area_mm2):
        self.bucket, self.largest_ref = bucket, largest_ref
        self.region_area_mm2, self.required_area_mm2 = region_area_mm2, required_area_mm2
        super().__init__(f"PartitionError: {bucket} cannot fit {largest_ref} ({region_area_mm2:.2f}mm^2 < {required_area_mm2:.2f}mm^2)")


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


def _outline(board):
    p = getattr(board, "outline_polygon", None)
    return Polygon(p) if p else Polygon([(0, 0), (board.width, 0), (board.width, board.height), (0, board.height)])


def _nets(netlist, ref):
    g = getattr(netlist, "get_component_nets", None)
    return list(g(ref)) if callable(g) else list(getattr(netlist, "_component_nets", {}).get(ref, []))


def _area(c):
    b = getattr(c, "bounds", None) or (0, 0)
    return float(b[0]) * float(b[1])


def _rules_by_net(state):
    dr = getattr(getattr(state, "drc_oracle", None), "design_rules", None)
    if dr is None:
        return {}
    classes, assigns = getattr(dr, "net_classes", {}) or {}, getattr(dr, "net_class_assignments", {}) or {}
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
    def name(self):
        return "hv_lv_partition"

    def run(self, state: BoardState) -> BoardState:
        cfg = load_guard_config(state.config)
        if not cfg.enabled or state.board is None or state.netlist is None:
            return state
        rules = _rules_by_net(state)
        hv, lv, creepage = [], [], 0.0
        for c in state.netlist.components:
            ns = _nets(state.netlist, c.ref)
            cats = {rules[n].safety_category for n in ns if n in rules}
            hh, hl = bool(cats & _HV), bool(cats & _LV)
            if hh and hl:
                lv.append(c.ref)
                logger.warning("dual-domain %s -> LV bucket", c.ref)
            elif hh:
                hv.append(c.ref)
            else:
                lv.append(c.ref)
            if hh:
                for n in ns:
                    if n in rules and rules[n].safety_category in _HV:
                        creepage = max(creepage, getattr(rules[n], "creepage_mm", 0.0) or 0.0)
        if not hv or not lv:
            logger.info("empty HV/LV bucket (hv=%d lv=%d); skipping", len(hv), len(lv))
            return state
        if cfg.width_mm == 0:
            return state
        width = cfg.width_mm if cfg.width_mm is not None else creepage
        if cfg.width_mm is not None and cfg.width_mm < creepage:
            logger.warning("hv_lv_guard_strip.width_mm=%s below creepage %s, using creepage", cfg.width_mm, creepage)
            width = creepage
        if width <= 0:
            return state
        outline = _outline(state.board)
        if outline.exterior is None or not outline.exterior.is_closed:
            raise PartitionError("geometry", "outline", 0.0, 0.0)
        try:
            hv_poly, lv_poly, corridor = compute_guard_strip(outline, width)
        except ValueError as exc:
            raise PartitionError("geometry", "outline", 0.0, 0.0) from exc
        comp = {c.ref: c for c in state.netlist.components}
        for bucket, refs, region in (("HV", hv, hv_poly), ("LV", lv, lv_poly)):
            if not refs or region.is_empty:
                continue
            largest = max(refs, key=lambda r: _area(comp[r]))
            if region.area < _area(comp[largest]):
                if cfg.fallback_to_unconstrained:
                    logger.warning("insufficient %s bucket area: %s requires %.2fmm^2, region has %.2fmm^2", bucket, largest, _area(comp[largest]), region.area)
                    return state
                raise PartitionError(bucket, largest, float(region.area), _area(comp[largest]))
        domain = [(r, "HV_edge") for r in hv] + [(r, "LV_interior") for r in lv]
        return replace(state, component_domain_map=frozenset(domain), routing_corridors=(corridor,), domain_regions=(hv_poly, lv_poly))


__all__ = ["PartitionError", "HvLvGuardConfig", "load_guard_config", "HvLvPartitionStage"]
