"""route_pcb entry point and conversion/writing functions for the router_v6 adapter."""

from __future__ import annotations

import contextlib
import logging
import math
import os
import re
import tempfile
import uuid
from pathlib import Path
from typing import Any

from temper_placer.geometry.kicad_transform import rotate_local_to_world
from temper_placer.router_v6._adapter_types import (
    CongestionRegion,
    DrcViolation,
    ParsedPcbLike,
    RoutingResult,
)
from temper_placer.router_v6._strip_copper import strip_existing_zones

# Re-exported from _zone_pour_stitch.py (LOC cap paydown, temper-N7-cap5):
# _stitch_isolated_pads/_emit_zone_pours/_zone_layers_for_net/
# _zone_params_for_net are in __all__ below; _chamfer_path_points is used
# directly in _write_routes_to_content() and imported directly by
# tests/router_v6/test_adapter.py from this module path, so both re-exports
# are load-bearing, not vestigial.
from temper_placer.router_v6._zone_pour_stitch import (  # noqa: F401
    _chamfer_path_points,
    _emit_zone_pours,
    _stitch_isolated_pads,
    _zone_layers_for_net,
    _zone_params_for_net,
)

logger = logging.getLogger(__name__)

__all__ = [
    "_apply_placements_to_pcb",
    "_build_routing_result",
    "_emit_zone_pours",
    "_stitch_isolated_pads",
    "_to_stage0_netclass_rules",
    "_write_routes_to_content",
    "_zone_layers_for_net",
    "_zone_params_for_net",
    "route_pcb",
]

# Fixed namespace for deriving synthetic KiCad ``tstamp`` UUIDs
# deterministically (see ``_next_tstamp`` below).
_TSTAMP_NAMESPACE = uuid.UUID("f8b1a2b0-6c4e-4a3a-9b7a-1a2b3c4d5e6f")


def _next_tstamp(counter: list[int]) -> str:
    """Return the next deterministic KiCad ``tstamp`` UUID.

    A single ``route_pcb()`` call writes many synthetic ``(segment ...)``/
    ``(via ...)`` elements. The previous implementation drew each
    ``tstamp`` from ``uuid.uuid4()``, which reads ``os.urandom`` -- so
    identical code and identical input produced a byte-different
    ``.kicad_pcb`` on every single run. Measurement showed this was the
    *only* source of that non-determinism: net topology, routed geometry,
    and layer/via assignment were already stable across 8 independent
    runs with default (randomized) ``PYTHONHASHSEED`` -- diffing two
    such runs after normalizing ``tstamp`` fields to a placeholder
    produced a zero-line diff (see
    docs/evidence/2026-07-27-router-determinism.md).

    ``tstamp`` is a KiCad object identifier only; it carries no
    electrical, geometric, or DRC meaning, so replacing the random draw
    with a value derived from a stable emission-order sequence number is
    safe and does not change what gets routed.

    This *does* depend on segment/via emission happening in a fixed
    order within one ``route_pcb()`` call -- an explicit, documented
    dependency rather than an incidental one. That order is already
    deterministic today (net iteration in ``_write_routes_to_content``
    walks a plain ``dict`` in insertion order, not a ``set``/``HashMap``
    in hash order), so a monotonic counter over that order is sufficient;
    it is not itself a tie-break.
    """
    n = counter[0]
    counter[0] = n + 1
    return str(uuid.uuid5(_TSTAMP_NAMESPACE, f"temper-router-v6-tstamp-{n}"))


def _to_stage0_netclass_rules(rules: Any) -> Any:
    """Convert a core NetClassRules (or duck-type-compatible shape) into a
    stage0 NetClassRules dataclass.

    This adapter is the single conversion boundary between the YAML SSOT
    representation (``core.netclass_rules_gen.NetClassRules``) and the A*
    engine's internal representation (``stage0_data.NetClassRules``).

    Explicit attribute checking replaces the previous ``getattr(rules, attr,
    default)`` duck-type approach: unrecognized shapes raise ``TypeError``
    rather than silently returning defaults.
    """
    from temper_placer.router_v6.stage0_data import NetClassRules as Stage0NetClassRules

    # --- Resolve each mapped field with explicit shape checking ---

    def _resolve(name: str, *aliases: str) -> Any:
        """Return the first attribute of *aliases* that exists on *rules*."""
        del name  # kept for call-site symmetry; only *aliases* are consulted
        for alias in aliases:
            if hasattr(rules, alias):
                return getattr(rules, alias)
        raise TypeError(
            f"Cannot convert {type(rules).__name__!r} to stage0 NetClassRules: "
            f"no attribute matching any of {list(aliases)} found"
        )

    name = _resolve("name", "name")
    clearance_mm = _resolve("clearance", "clearance", "clearance_mm")
    trace_width_mm = _resolve("trace_width", "trace_width", "trace_width_mm")
    via_diameter_mm = _resolve("via_diameter", "via_diameter", "via_diameter_mm")
    via_drill_mm = _resolve("via_drill", "via_drill", "via_drill_mm")

    # max_current_rating → current_rating_amps (R1 fix)
    current_rating_amps: float | None = None
    if hasattr(rules, "max_current_rating"):
        current_rating_amps = rules.max_current_rating

    # safety_category survives conversion (needed by R6 HV/AC forced-segment gate)
    safety_category: str | None = None
    if hasattr(rules, "safety_category"):
        val = rules.safety_category
        if val is not None:
            safety_category = str(val)

    # creepage_mm survives conversion: previously this field was dropped
    # (only appeared in _UNREPRESENTED_WARN below), so every consumer that
    # reads it off the stage0 object via getattr(..., 0.0) -- e.g.
    # bottleneck_geometry.py's _required_creepage_mm and
    # _pipeline_route.py's PCL netclass metadata -- silently enforced ZERO
    # creepage regardless of the netclass's declared requirement.
    creepage_mm: float = 0.0
    if hasattr(rules, "creepage_mm"):
        val = rules.creepage_mm
        if val is not None:
            creepage_mm = float(val)

    # --- R1b: Warn on unrepresented fields that are explicitly set ---
    _UNREPRESENTED_WARN = (
        ("voltage_v", "Voltage rating", 0.0),
        ("routing_strategy", "Routing strategy", None),
        ("via_cost_multiplier", "Via cost multiplier", 1.0),
        ("layer_costs", "Layer cost overrides", None),
        ("via_template", "Via template", None),
        ("target_impedance", "Target impedance", None),
        ("required_layer", "Required KiCad layer", None),
        ("layer", "KiCad layer", None),
        ("dru_priority", "DRU priority", 0),
    )
    for attr_name, human_label, default_val in _UNREPRESENTED_WARN:
        val = getattr(rules, attr_name, None)
        if val is not None and val != default_val:
            logger.warning(
                "_to_stage0_netclass_rules: dropping %s=%s for netclass %r "
                "— no stage0 equivalent field exists",
                human_label,
                val,
                name,
            )

    return Stage0NetClassRules(
        name=name,
        clearance_mm=clearance_mm,
        trace_width_mm=trace_width_mm,
        via_diameter_mm=via_diameter_mm,
        via_drill_mm=via_drill_mm,
        current_rating_amps=current_rating_amps,
        safety_category=safety_category,
        creepage_mm=creepage_mm,
    )


def route_pcb(
    parsed: ParsedPcbLike | Any,
    placements: dict[str, tuple[float, float]],
    design_rules: Any = None,
    thermal_flat: Any = None,
    thermal_weight: float = 0.0,
    enable_all_pad_tree: bool = False,
    enable_zone_pours: bool = True,
    enable_connectivity_verifier: bool = False,
    enable_geographic_pruning: bool = False,
    enable_manufacturing_drc: bool = False,
    sat_conflict_limit: int | None = 20_000,
    sat_time_limit_ms: int | None = None,
    rotations: dict[str, float] | None = None,
    components: list | None = None,
    enable_net_batching: bool = False,
    net_batch_size: int = 10,
) -> RoutingResult:
    """Route a PCB using the Router V6 pipeline.

    Args:
        parsed: ParsedPCB from parse_kicad_pcb_v6.
        placements: Dict mapping component ref -> (x, y) position in mm.
            If empty, routing proceeds with the board's existing positions.
        design_rules: Optional DesignRules with net_classes for netclass
            form injection into the output PCB. net_class_assignments and
            net_classes are both derived from this object and threaded
            into the pipeline automatically -- see the block below.
        rotations: Optional dict mapping component ref -> new absolute
            footprint rotation in degrees (see
            ``CpSatPlacementResult.to_rotations_dict()``). Threaded
            straight through to ``_apply_placements_to_pcb`` -- see its
            docstring for exactly what is and is not rewritten. A ref
            with no entry here keeps its existing angle unchanged,
            matching this parameter's pre-existing absence entirely.
        components: Optional list of ``Component`` objects (the netlist
            ``solve_placement`` was called with). Threaded straight through
            to ``_apply_placements_to_pcb`` so it can invert each
            footprint's pad-centroid offset (``_center_offset_x/y``) back
            to a KiCad anchor -- see its docstring. Required alongside
            ``rotations`` for any footprint whose pads are not centred on
            its raw anchor (e.g. an asymmetric TO-247); omitting it keeps
            prior behavior unchanged.
        thermal_flat: U9 optional (N,) float32 thermal cost field from
            the previous round's field.  Threaded to A* kernel.
        thermal_weight: U9 multiplier on per-cell thermal cost
            (from CostFieldInput.weight).  0.0 = field-off.
        enable_all_pad_tree: Enable experimental all-terminal tree
            expansion (default False).
        enable_zone_pours: Emit filled-copper zone geometry for power/
            ground/HV nets (per netclass SSOT).  Default True -- zones
            are enabled by default for multi-layer power/ground routing.
        enable_connectivity_verifier: Run post-write connectivity
            preflight via verify_net_connectivity (default False).
        enable_geographic_pruning: Enable geographic pruning of the
            Stage 3 SAT model (U3 of plan
            2026-08-07-001-feat-router-encoding-pruning-plan.md).
            Default False -- behavior unchanged. When True,
            NetChannelVar and ViaVar variables are created only for
            edges/nodes within max(K * pin_span, M_min) of each net's
            pins, reducing CNF variable/clause count. See
            RouterV6Pipeline.__init__'s docstring for the full
            rationale. Not yet measured against the production board
            through this entry point -- see
            docs/evidence/2026-08-07-pruned-encoding-measurement.md
            (if present) for the U5 measurement status.
        # Ported forward from a later point on `main` than this worktree's
        # branch point (see the docstring above) -- ConstraintModel.build()
        # only honors this when it is actually threaded through to
        # RouterV6Pipeline; ModelBuilder itself already defaults it False,
        # so leaving this unwired would make enable_geographic_pruning=True
        # a silent no-op at this call site specifically.
