"""VERBATIM pre-migration oracle for ``deterministic/stages/hv_lv_partition.py``.

Wave 4 follow-up (HV/LV guard-strip partitioning). Pinned from
``packages/temper-placer/src/temper_placer/deterministic/stages/hv_lv_partition.py``
at the dispatch base (origin/main f1ffc013). Do NOT edit: this file is the
Python arm of the differential. If it drifts, the differential proves nothing.

The pure compute of ``HvLvPartitionStage.run`` -- the safety-category
classification + creepage ``max`` loop, the width resolution, and the
bucket-area decision -- is pinned as two module-level functions (the ``run``
orchestration -- the state/netlist guards, the ``_rules_by_net`` / ``_nets``
reading, the shapely outline + ``compute_guard_strip`` GEOS surface, the
``PartitionError`` construction, and the ``dataclasses.replace`` wrap -- stays
Python in the shim and is not part of the oracle).

Marshalled-input contract (identical for both arms of the differential):

- ``components_nets``: ``list[(ref, [net, ...])]`` in netlist component order.
- ``rules``: ``{net_name: (safety_category, creepage_mm)}``. The shim marshals
  ``safety_category or ""`` and ``float(creepage_mm or 0.0)`` from the
  ``NetClassRules`` objects, so ``None`` categories/creepages are normalised
  to ``""`` / ``0.0`` before the kernel sees them.
- ``areas``: ``{ref: float}`` -- the shim's ``_area`` (``float(bounds[0]) *
  float(bounds[1])``).
- region areas/empties are the GEOS ``region.area`` / ``region.is_empty``
  marshalled from Python; the region geometry itself (outline polygon, guard
  strip buffer/difference) is the non-portable GEOS surface.
"""

_HV = frozenset({"HV", "AC"})
_LV = frozenset({"LV", "iso"})


def hv_lv_classify(components_nets, rules, width_mm):
    """Pin ``run``'s classification loop + width resolution.

    Returns ``(decision, hv, lv, creepage, width, dual)``:
    - decision: ``"skip_empty"`` / ``"skip_zero"`` / ``"ok"``.
    - ``dual``: the dual-domain refs in component order (the oracle emits a
      ``dual-domain ... -> LV bucket`` warning per one).
    """
    hv, lv, creepage = [], [], 0.0
    dual = []
    for ref, ns in components_nets:
        cats = {rules[n][0] for n in ns if n in rules}
        hh, hl = bool(cats & _HV), bool(cats & _LV)
        if hh and hl:
            lv.append(ref)
            dual.append(ref)
        elif hh:
            hv.append(ref)
        else:
            lv.append(ref)
        if hh:
            for n in ns:
                if n in rules and rules[n][0] in _HV:
                    creepage = max(creepage, rules[n][1])
    if not hv or not lv:
        return ("skip_empty", hv, lv, creepage, 0.0, dual)
    if width_mm == 0:
        return ("skip_zero", hv, lv, creepage, 0.0, dual)
    width = width_mm if width_mm is not None else creepage
    if width_mm is not None and width_mm < creepage:
        width = creepage
    if width <= 0:
        return ("skip_zero", hv, lv, creepage, 0.0, dual)
    return ("ok", hv, lv, creepage, width, dual)


def hv_lv_area_check(
    hv,
    lv,
    areas,
    hv_region_area,
    hv_region_empty,
    lv_region_area,
    lv_region_empty,
    fallback_to_unconstrained,
):
    """Pin ``run``'s per-bucket area decision.

    Returns ``(outcome, bucket, largest, region_area, required_area)`` with
    outcome ``"ok"`` / ``"fallback"`` / ``"raise"``. Bucket order (HV then LV)
    is load-bearing: the FIRST failing bucket decides.
    """
    for bucket, refs, region_area, region_empty in (
        ("HV", hv, hv_region_area, hv_region_empty),
        ("LV", lv, lv_region_area, lv_region_empty),
    ):
        if not refs or region_empty:
            continue
        largest = max(refs, key=lambda r: areas[r])
        if region_area < areas[largest]:
            if fallback_to_unconstrained:
                return ("fallback", bucket, largest, float(region_area), areas[largest])
            return ("raise", bucket, largest, float(region_area), areas[largest])
    return ("ok", None, None, None, None)
