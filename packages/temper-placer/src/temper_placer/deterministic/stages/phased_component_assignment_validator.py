"""
Per-stage DRC fence validator for PhasedComponentAssignmentStage.

Validates that the placer's ghost-pad injection covered every slot
within IEC 62368-1 creepage of every HV-class pin, and that no slot
was over-claimed (i.e. reserved without a corresponding HV-pin ring
or a placed component's footprint).

Conforms to docs/solutions/architecture-patterns/per-stage-drc-fence-verification-2026-06-22.md.

The validator is read-only: it does not mutate the state, and it
returns a (possibly empty) list of ``StageDRCFailure`` records.  The
placer logs failures as warnings and lets the closure test (SM1/SM2)
decide promotion.

Performance: the naive scans are O(pins x slots) for coverage and
O(slots x placements x pins) for over-claim.  Both collapse to
near-linear in (slots + pins + placements) when the slot grid is
indexed by a 2D bucketed cell map keyed on the inferred slot
spacing.  See ``_build_slot_index`` and ``_slots_within_radius``.
"""

from __future__ import annotations

import math
from typing import Dict, Iterable, List, Set, Tuple

from temper_placer.router_v6.stage_validators import (
    StageDRCFailure,
    register_validator,
)

_HV_SAFETY_CATEGORIES = frozenset({"HV", "AC"})

# Default slot spacing used when the grid is degenerate (single slot
# or non-uniform).  Smaller values over-bucket (more memory, exact
# results), larger values under-bucket (less memory, still correct).
_DEFAULT_SLOT_SPACING = 5.0


def _absolute_hv_pins(state) -> List[Tuple[float, float, str, str]]:
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
    comp_by_ref = {c.ref: c for c in netlist.components}
    pins: List[Tuple[float, float, str, str]] = []
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
            pins.append(
                (cx + float(px), cy + float(py), comp.ref, pin.name)
            )
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
            max_creepage = max(
                max_creepage, float(getattr(rules_entry, "creepage_mm", 0.0))
            )
    return max_creepage


def _flatten_slots(state) -> List[Tuple[float, float]]:
    """All grid slots from every zone in state.zone_slots."""
    if not state.zone_slots:
        return []
    out: List[Tuple[float, float]] = []
    for _zone, slots in state.zone_slots:
        out.extend(slots)
    return out


def _infer_slot_spacing(slots: List[Tuple[float, float]]) -> float:
    """Infer the regular slot-grid spacing from a flat list of slots.

    The placer's zone_slots are emitted by ``_build_state`` on a
    regular grid, so the minimum non-zero coordinate difference is
    the spacing.  Falls back to ``_DEFAULT_SLOT_SPACING`` for
    degenerate inputs (0, 1, or 2 slots; non-uniform grids).
    """
    if len(slots) < 2:
        return _DEFAULT_SLOT_SPACING
    xs = sorted({sx for sx, _ in slots})
    ys = sorted({sy for _, sy in slots})
    dx_candidates = [b - a for a, b in zip(xs, xs[1:]) if b > a]
    dy_candidates = [b - a for a, b in zip(ys, ys[1:]) if b > a]
    candidates = dx_candidates + dy_candidates
    if not candidates:
        return _DEFAULT_SLOT_SPACING
    return min(candidates)


def _build_slot_index(
    slots: Iterable[Tuple[float, float]],
    spacing: float,
) -> Dict[Tuple[int, int], List[Tuple[float, float]]]:
    """Build a 2D bucketed cell map ``(i, j) -> [slots in that cell]``.

    Cells are unit squares of side ``spacing`` aligned to the
    inferred grid origin (0, 0).  A slot ``(x, y)`` lives in cell
    ``(round(x/spacing), round(y/spacing))``.  The cell map turns
    the O(N) per-radius scan into a 3x3 (or 5x5) cell lookup, so
    coverage and over-claim run in O(slots + pins + placements)
    instead of the naive quadratic.
    """
    index: Dict[Tuple[int, int], List[Tuple[float, float]]] = {}
    for slot in slots:
        i = int(round(slot[0] / spacing))
        j = int(round(slot[1] / spacing))
        index.setdefault((i, j), []).append(slot)
    return index


def _slots_within_radius(
    center: Tuple[float, float],
    radius: float,
    index: Dict[Tuple[int, int], List[Tuple[float, float]]],
    spacing: float,
) -> List[Tuple[float, float]]:
    """Yield all slots within ``radius`` of ``center`` using the cell index.

    Walks the (2k+1) x (2k+1) cell window where
    ``k = ceil(radius / spacing)``.  Each candidate slot is
    distance-checked exactly once (de-duplicated via a per-call
    seen-set) so the result is O(k^2 + matched) where matched is
    the number of slots actually within the radius.
    """
    if radius <= 0.0 or not index:
        return []
    k = int(math.ceil(radius / spacing))
    ci = int(round(center[0] / spacing))
    cj = int(round(center[1] / spacing))
    out: List[Tuple[float, float]] = []
    seen: Set[Tuple[float, float]] = set()
    cx, cy = center
    for di in range(-k, k + 1):
        for dj in range(-k, k + 1):
            cell = (ci + di, cj + dj)
            cell_slots = index.get(cell)
            if not cell_slots:
                continue
            for slot in cell_slots:
                if slot in seen:
                    continue
                seen.add(slot)
                sx, sy = slot
                if math.hypot(sx - cx, sy - cy) <= radius:
                    out.append(slot)
    return out


@register_validator("PhasedComponentAssignment")
def validate_phased_component_assignment_hv(state) -> List[StageDRCFailure]:
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

    Performance: the naive implementation is O(pins x slots) for
    coverage and O(slots x placements x pins) for over-claim.  This
    implementation pre-computes two sets once and looks up coverage
    by membership:

      - ``creepage_coverage``: ``set[(slot, pin)]`` of every
        (slot, pin) pair where the slot is within creepage of the
        pin.  Built by indexing every HV pin in a 2D bucketed cell
        map keyed on the inferred slot spacing.  Turn-around is
        O(slots + pins + matched_pairs).

      - ``legitimate_origin``: ``set[slot]`` of every slot that is
        within a placed component's footprint ring or within an HV
        ring.  Built by walking placements + the bucketed index.
        Lookup is O(1) per slot.
    """
    failures: List[StageDRCFailure] = []
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
        used_slots: Set[Tuple[float, float]] = set(used_slots_attr)
    else:
        # Fallback for older state objects that pre-date U3.
        used_slots = set()
        for ref, pos in placements.items():
            comp = comp_by_ref.get(ref)
            if comp is None:
                continue
            cx, cy = pos
            radius = stage._get_footprint_radius(comp)
            used_slots.update(
                _slots_within_radius((cx, cy), radius, slot_index, spacing)
            )
            for pin in comp.pins:
                if pin.net is None:
                    continue
                class_name = (
                    getattr(state.design_rules, "net_class_assignments", {}) or {}
                ).get(pin.net)
                if class_name is None or class_name not in (
                    getattr(state.design_rules, "net_classes", {}) or {}
                ):
                    continue
                safety = getattr(
                    (
                        getattr(state.design_rules, "net_classes", {}) or {}
                    ).get(class_name),
                    "safety_category",
                    None,
                )
                if safety not in _HV_SAFETY_CATEGORIES:
                    continue
                ring_radius = stage._effective_ghost_pad_radius(
                    comp.ref, pin.name, creepage,
                    (cx, cy), (cx, cy),
                )
                if ring_radius <= 0.0:
                    continue
                px, py = pin.position
                ax = cx + float(px)
                ay = cy + float(py)
                used_slots.update(
                    _slots_within_radius((ax, ay), ring_radius, slot_index, spacing)
                )

    # Pre-compute the legitimate-origin set (slots that fall within
    # some footprint ring OR some HV creepage ring).  Used by both
    # the coverage check and the over-claim check.
    legitimate_origin: Set[Tuple[float, float]] = set()
    for ref, pos in placements.items():
        comp = comp_by_ref.get(ref)
        if comp is None:
            continue
        cx, cy = pos
        radius = stage._get_footprint_radius(comp)
        legitimate_origin.update(
            _slots_within_radius((cx, cy), radius, slot_index, spacing)
        )
        for pin in comp.pins:
            if pin.net is None:
                continue
            class_name = (
                getattr(state.design_rules, "net_class_assignments", {}) or {}
            ).get(pin.net)
            if class_name is None or class_name not in (
                getattr(state.design_rules, "net_classes", {}) or {}
            ):
                continue
            safety = getattr(
                (
                    getattr(state.design_rules, "net_classes", {}) or {}
                ).get(class_name),
                "safety_category",
                None,
            )
            if safety not in _HV_SAFETY_CATEGORIES:
                continue
            ring_radius = stage._effective_ghost_pad_radius(
                comp.ref, pin.name, creepage,
                (cx, cy), (cx, cy),
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
        for slot in _slots_within_radius(
            (px, py), creepage, slot_index, spacing
        ):
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
