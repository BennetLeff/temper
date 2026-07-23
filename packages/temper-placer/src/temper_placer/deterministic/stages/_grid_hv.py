from temper_placer.core.board import (
    LAYER_IDX_TO_NAME,
    PLANE_LAYER_INDICES,
    STANDARD_LAYER_ORDER,
    LayerIndex,
)

# @req(2026-06-23-005, R2): Layer-aware creepage factor for inner layers.
# Outer copper layers (F.Cu, B.Cu) carry the full creepage distance; inner
# layers (In1.Cu, In2.Cu, ...) carry the reduced factor (0.30) because the
# plane acts as a shield, consistent with router_v6.clearance_engine.
INTERNAL_LAYER_CREEPAGE_FACTOR: float = 0.30
OUTER_COPPER_LAYERS = frozenset(
    str(idx) for idx in STANDARD_LAYER_ORDER if idx not in PLANE_LAYER_INDICES
)

_STANDARD_LAYER_NAMES: tuple[str, ...] = tuple(str(idx) for idx in STANDARD_LAYER_ORDER)


class ConfigError(ValueError):
    """Raised when HV exclusion zone config cannot be resolved against the netlist.

    The pre-route creepage expansion requires each HV zone to map to a known
    component. This error names the offending refdes/zone to make failures
    actionable during config validation.
    """


def effective_creepage(layer: str, base_creepage_mm: float) -> float:
    """Return the per-layer effective creepage distance in mm.

    @req(2026-06-23-005, R2): Outer layers use the full base creepage; inner
    layers use `base_creepage_mm * INTERNAL_LAYER_CREEPAGE_FACTOR`.

    Args:
        layer: KiCad layer name (e.g., "F.Cu", "In1.Cu").
        base_creepage_mm: Base creepage distance in mm (typically 6.0).

    Returns:
        Effective creepage distance in mm for the given layer.
    """
    if layer in OUTER_COPPER_LAYERS:
        return base_creepage_mm
    return base_creepage_mm * INTERNAL_LAYER_CREEPAGE_FACTOR


def _layer_index_to_name(layer_idx: int, _layer_count: int) -> str:
    """Map a 0-based layer index to its KiCad layer name.

    Used to translate grid layer indices into the names `effective_creepage`
    accepts. Matches the convention in `ClearanceGrid.export_visualization`.
    """
    try:
        return str(LAYER_IDX_TO_NAME[LayerIndex(layer_idx)])
    except (KeyError, ValueError):
        return f"Layer_{layer_idx}"


# @req(2026-06-23-005, R1): HV-pad identification. The set is the union of all
# pads whose parent component is mapped to an HV exclusion zone.
def hv_pad_set(pads, hv_exclusion_zones, component_positions):
    """Identify the set of (component_ref, pin_name) pads that belong to HV components.

    For each HV exclusion zone, resolve the parent component refdes:
      1. If the zone has `component_refdes` set explicitly, use it (R1).
      2. Otherwise, fall back to the component closest to the zone center.

    All pads of the resolved HV components are returned. The set is rebuilt on
    every stage run; no module-level state is mutated.

    Args:
        pads: Iterable of pad dicts each having keys ``"ref"`` and ``"name"``.
        hv_exclusion_zones: Iterable of `HVExclusionZone` (or duck-typed
            objects exposing ``component_refdes``, ``center``, ``size``,
            ``name``).
        component_positions: Dict mapping ``component_ref -> (x, y)`` position
            in mm. Used for the spatial fallback.

    Returns:
        Set of ``(ref, pin_name)`` tuples for HV pads.

    Raises:
        ConfigError: If an explicit ``component_refdes`` does not appear in
            ``component_positions``, or if the spatial fallback finds no
            component within the zone bounds.
    """
    hv_refs: set[str] = set()
    for zone in hv_exclusion_zones:
        ref = getattr(zone, "component_refdes", None)
        if ref is not None:
            if ref not in component_positions:
                raise ConfigError(
                    f"HV exclusion zone '{getattr(zone, 'name', '?')}' declares "
                    f"component_refdes '{ref}' which is not present in the "
                    f"placed netlist."
                )
            hv_refs.add(ref)
            continue

        zx, zy = zone.center
        zw, zh = zone.size
        half_w, half_h = zw / 2.0, zh / 2.0
        candidates = [
            (ref, pos)
            for ref, pos in component_positions.items()
            if (zx - half_w) <= pos[0] <= (zx + half_w) and (zy - half_h) <= pos[1] <= (zy + half_h)
        ]
        if not candidates:
            raise ConfigError(
                f"HV exclusion zone '{getattr(zone, 'name', '?')}' centered at "
                f"({zx}, {zy}) with size {zone.size} contains no placed component."
            )
        closest_ref, _ = min(
            candidates,
            key=lambda item: (item[1][0] - zx) ** 2 + (item[1][1] - zy) ** 2,
        )
        hv_refs.add(closest_ref)

    return {(pad["ref"], pad["name"]) for pad in pads if pad["ref"] in hv_refs}
