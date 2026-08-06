"""
Per-stage DRC fence validator for PhasedComponentAssignmentStage.

Validates that the placer's ghost-pad injection covered every slot
within IEC 62368-1 creepage of every HV-class pin, and that no slot
was over-claimed (i.e. reserved without a corresponding HV-pin ring
or a placed component's footprint).

The three pure slot-grid kernels — ``_infer_slot_spacing``, ``_build_slot_index``,
``_slots_within_radius`` — are implemented in Rust in the ``temper-design-bundle``
crate (Wave 4 **Phase 5, batch 2** — deterministic leaf stages) and delegate to
``temper_design_bundle_python.deterministic_leaves``. ``_flatten_slots`` stays
Python (a 7-line list flattening over ``state.zone_slots`` — no bit-exact
compute worth crossing the boundary for). The
``validate_phased_component_assignment_hv`` function stays Python: it binds
router_v6's ``StageDRCFailure`` and the phasing mixins'
``_get_footprint_radius`` / ``_effective_ghost_pad_radius`` (unmigrated
surfaces), and its failure ordering is orchestration over the migrated
slot-grid kernels.

Bit-exactness: slot-spacing inference (minimum non-zero coordinate
difference), the bucketed cell index (`int(round(x/spacing))` — CPython
round-half-to-even), and the radius scan (`ceil`, `math.hypot`, exact
(di, dj) raster order) are reproduced identically. Verified by
``tests/deterministic/stages/test_phased_component_assignment_validator_rust_differential.py``
(oracle: ``tests/deterministic/stages/_phased_component_assignment_validator_py_oracle.py``)
and the PBT suite; the structural proof lives in
``packages/temper-design-bundle/VERIFICATION.md``.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from typing import TYPE_CHECKING

import temper_design_bundle_python as _tdb

if TYPE_CHECKING:
    from temper_placer.router_v6.stage_validators import StageDRCFailure

_HV_SAFETY_CATEGORIES = frozenset({"HV", "AC"})

# Default slot spacing used when the grid is degenerate (single slot
# or non-uniform).  Smaller values over-bucket (more memory, exact
# results), larger values under-bucket (less memory, still correct).
_DEFAULT_SLOT_SPACING = 5.0

_RS = _tdb.deterministic_leaves


def _flatten_slots(state) -> list[tuple[float, float]]:
    """All grid slots from every zone in state.zone_slots."""
    if not state.zone_slots:
        return []
    out: list[tuple[float, float]] = []
    for _zone, slots in state.zone_slots:
        out.extend(slots)
    return out


def _infer_slot_spacing(slots: list[tuple[float, float]]) -> float:
    """Infer the regular slot-grid spacing from a flat list of slots.

    The placer's zone_slots are emitted by ``_build_state`` on a
    regular grid, so the minimum non-zero coordinate difference is
    the spacing.  Falls back to ``_DEFAULT_SLOT_SPACING`` for
    degenerate inputs (0, 1, or 2 slots; non-uniform grids).
    """
    return _RS.infer_slot_spacing_py(slots)


def _build_slot_index(
    slots: Iterable[tuple[float, float]],
    spacing: float,
) -> dict[tuple[int, int], list[tuple[float, float]]]:
    """Build a 2D bucketed cell map ``(i, j) -> [slots in that cell]``.

    Cells are unit squares of side ``spacing`` aligned to the
    inferred grid origin (0, 0).  A slot ``(x, y)`` lives in cell
    ``(round(x/spacing), round(y/spacing))``.
    """
    return _RS.build_slot_index_py(slots, spacing)


def _slots_within_radius(
    center: tuple[float, float],
    radius: float,
    index: dict[tuple[int, int], list[tuple[float, float]]],
    spacing: float,
) -> list[tuple[float, float]]:
    """Yield all slots within ``radius`` of ``center`` using the cell index.

    Walks the (2k+1) x (2k+1) cell window where
    ``k = ceil(radius / spacing)``.  Each candidate slot is
    distance-checked exactly once (de-duplicated via a per-call
    seen-set) so the result is O(k^2 + matched) where matched is
    the number of slots actually within the radius.
    """
    return _RS.slots_within_radius_py(center, radius, index, spacing)


def _absolute_hv_pins(state) -> list[tuple[float, float, str, str]]:
    """Return ABSOLUTE (x, y, comp_ref, pin_name) for every HV pin of every placed component.

    Pin positions on the netlist are component-relative.  The placer
    injects ghost pads at the absolute positions
    ``placed + pin_relative``, so the validator must check coverage
    at the same absolute coordinates.
    """
    rules = getattr(state, "design_rules", None)
    if rules is None or not getattr(rules, "net_classes", None):
        return []
    netlist = state.netlist
    if netlist is None:
        return []
    net_classes = rules.net_classes
    net_class_assignments = getattr(rules, "net_class_assignments", {}) or {}
    placements = dict(getattr(state, "placements", frozenset()))
    {c.ref: c for c in netlist.components}
    pins: list[tuple[float, float, str, str]] = []
    for comp in netlist.components:
        if comp.ref not in placements:
            continue
        cx, cy = placements[comp.ref]
        for pin in comp.pins:
            if pin.net is None:
                continue
            class_name = net_class_assignments.get(pin.net)
            if class_name is None or class_name not in net_classes:
                continue
            safety = getattr(net_classes[class_name], "safety_category", None)
            if safety not in _HV_SAFETY_CATEGORIES:
                continue
            px, py = pin.position
            pins.append((cx + float(px), cy + float(py), comp.ref, pin.name))
    return pins


def _creepage_mm(state) -> float:
    """Max creepage_mm across HV/AC net classes (the FR4 SSOT)."""
    rules = getattr(state, "design_rules", None)
    if rules is None:
        return 0.0
    max_creepage = 0.0
    for rules_entry in getattr(rules, "net_classes", {}).values():
        safety = getattr(rules_entry, "safety_category", None)
        if safety in _HV_SAFETY_CATEGORIES:
            max_creepage = max(max_creepage, float(getattr(rules_entry, "creepage_mm", 0.0)))
    return max_creepage


def validate_phased_component_assignment_hv(state) -> list[StageDRCFailure]:
    """Verify the placer reserved every HV pin's creepage ring AND no slot is over-claimed.

    Two checks run in this order:

      1. Coverage: for every placed component's HV pin at absolute
         position ``(placed + pin_relative)``, every grid slot within
         ``creepage_mm`` must be reserved (either by the placer's
         per-component footprint ring or by the HV creepage ring).
      2. Non-over-claim: every reserved slot must have a "legitimate"
         origin (a placed component's footprint ring OR an HV pin's
         creepage ring).  Catches placer logic errors that reserve
         too many slots.

    A degenerate ``creepage_mm == 0`` is treated as a no-op (no
    rings, no failures).  A ``creepage_mm`` larger than the slot-grid
    diagonal saturates coverage and the validator returns an empty
    failure list.

    The bucketed cell-map kernels are the migrated Rust functions; the
    coverage / over-claim loops and the ``StageDRCFailure`` construction
    stay Python (router_v6-bound).
    """
    from temper_placer.router_v6.stage_validators import StageDRCFailure

    failures: list[StageDRCFailure] = []
    netlist = getattr(state, "netlist", None)
    if netlist is None:
        return failures

    creepage = _creepage_mm(state)
    if creepage <= 0.0:
        return failures

    all_slots = _flatten_slots(state)
    if not all_slots:
        return failures

    pins = _absolute_hv_pins(state)
    if not pins:
        return failures

    # Build the bucketed slot index once; reuse for both checks.
    spacing = _infer_slot_spacing(all_slots)
    slot_index = _build_slot_index(all_slots, spacing)

    # Saturation short-circuit: creepage > slot-grid diagonal means
    # every slot is "within creepage" of every HV pin.  Coverage is
    # a tautology; the non-over-claim check still applies but
    # trivially returns no failures since every slot is covered.
    xs = [s[0] for s in all_slots]
    ys = [s[1] for s in all_slots]
    diagonal = math.hypot(max(xs) - min(xs), max(ys) - min(ys))
    if creepage >= diagonal:
        return failures

    # Pre-compute placement/component metadata once.
    placements = dict(getattr(state, "placements", frozenset()))
    comp_by_ref = {c.ref: c for c in netlist.components}
    from temper_placer.deterministic.stages.phased_component_assignment import (
        PhasedComponentAssignmentStage,
    )

    stage = PhasedComponentAssignmentStage.__new__(PhasedComponentAssignmentStage)
    stage.slot_spacing = spacing
    if getattr(state, "design_rules", None) is not None:
        stage.design_rules = state.design_rules
        stage.use_isolation_slots = False

    # Use the actual used_slots recorded by the placer if available;
    # this is the only way the validator can detect a placer bug that
    # left an HV ring incomplete (the recompute-from-placements path
    # would mask such a bug by re-deriving the expected ring).
    used_slots_attr = getattr(state, "used_slots", None)
    if used_slots_attr is not None and len(used_slots_attr) > 0:
        used_slots: set[tuple[float, float]] = set(used_slots_attr)
    else:
        # Fallback for older state objects that pre-date U3.
        used_slots = set()
        for ref, pos in placements.items():
            comp = comp_by_ref.get(ref)
            if comp is None:
                continue
            cx, cy = pos
            radius = stage._get_footprint_radius(comp)
            used_slots.update(_slots_within_radius((cx, cy), radius, slot_index, spacing))
            for pin in comp.pins:
                if pin.net is None:
                    continue
                class_name = (getattr(state.design_rules, "net_class_assignments", {}) or {}).get(
                    pin.net
                )
                if class_name is None or class_name not in (
                    getattr(state.design_rules, "net_classes", {}) or {}
                ):
                    continue
                safety = getattr(
                    (getattr(state.design_rules, "net_classes", {}) or {}).get(class_name),
                    "safety_category",
                    None,
                )
                if safety not in _HV_SAFETY_CATEGORIES:
                    continue
                ring_radius = stage._effective_ghost_pad_radius(
                    comp.ref,
                    pin.name,
                    creepage,
                    (cx, cy),
                    (cx, cy),
                )
                if ring_radius <= 0.0:
                    continue
                px, py = pin.position
                ax = cx + float(px)
                ay = cy + float(py)
                used_slots.update(_slots_within_radius((ax, ay), ring_radius, slot_index, spacing))

    # Pre-compute the legitimate-origin set (slots that fall within
    # some footprint ring OR some HV creepage ring).  Used by both
    # the coverage check and the over-claim check.
    legitimate_origin: set[tuple[float, float]] = set()
    for ref, pos in placements.items():
        comp = comp_by_ref.get(ref)
        if comp is None:
            continue
        cx, cy = pos
        radius = stage._get_footprint_radius(comp)
        legitimate_origin.update(_slots_within_radius((cx, cy), radius, slot_index, spacing))
        for pin in comp.pins:
            if pin.net is None:
                continue
            class_name = (getattr(state.design_rules, "net_class_assignments", {}) or {}).get(
                pin.net
            )
            if class_name is None or class_name not in (
                getattr(state.design_rules, "net_classes", {}) or {}
            ):
                continue
            safety = getattr(
                (getattr(state.design_rules, "net_classes", {}) or {}).get(class_name),
                "safety_category",
                None,
            )
            if safety not in _HV_SAFETY_CATEGORIES:
                continue
            ring_radius = stage._effective_ghost_pad_radius(
                comp.ref,
                pin.name,
                creepage,
                (cx, cy),
                (cx, cy),
            )
            if ring_radius <= 0.0:
                continue
            px, py = pin.position
            ax = cx + float(px)
            ay = cy + float(py)
            legitimate_origin.update(
                _slots_within_radius((ax, ay), ring_radius, slot_index, spacing)
            )

    # 1. Coverage: for every (pin, slot) where the slot is within
    # creepage of the pin, the slot must be in used_slots.  Built
    # by indexing each pin in the bucketed grid and walking its
    # 3x3 cell window.
    for px, py, comp_ref, pin_name in pins:
        for slot in _slots_within_radius((px, py), creepage, slot_index, spacing):
            if slot not in used_slots:
                failures.append(
                    StageDRCFailure(
                        field=f"hv_creepage_unblocked.{comp_ref}.{pin_name}",
                        value=slot,
                        reason=(
                            f"Slot {slot} is within {creepage}mm of HV pin "
                            f"{comp_ref}.{pin_name} at ({px},{py}) but is "
                            f"not in used_slots"
                        ),
                        stage="PhasedComponentAssignment",
                    )
                )

    # 2. Non-over-claim: every used slot must have a legitimate
    # origin.  O(1) membership lookup against the pre-computed set.
    for slot in used_slots:
        if slot not in legitimate_origin:
            failures.append(
                StageDRCFailure(
                    field="used_slot_overclaim",
                    value=slot,
                    reason=(
                        f"Slot {slot} is in used_slots but is not within "
                        f"any HV pin's creepage ring nor within any placed "
                        f"component's footprint radius"
                    ),
                    stage="PhasedComponentAssignment",
                )
            )

    return failures
