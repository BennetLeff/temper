import temper_geometry as _tg
import temper_orchestration as _to

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

    The layer-set membership test stays here (it resolves against the
    board's layer constants); the factor application is computed in
    temper-geometry (``grid_raster.rs``) with the identical f64 literal
    and single rounded multiply.

    Args:
        layer: KiCad layer name (e.g., "F.Cu", "In1.Cu").
        base_creepage_mm: Base creepage distance in mm (typically 6.0).

    Returns:
        Effective creepage distance in mm for the given layer.
    """
    return _tg.effective_creepage_py(layer in OUTER_COPPER_LAYERS, base_creepage_mm)


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
#
# The orchestration is implemented in Rust (``temper-orchestration``'s
# ``run_hv_pad_set``, Phase D batch D3): the zone-resolution loop (explicit
# ``component_refdes`` first, then the spatial fallback via the
# temper-geometry ``closest_component_for_zone_py`` kernel) and the pad-set
# assembly move Rust-side; the ``ConfigError`` exception class stays here.
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
    return _to.run_hv_pad_set(pads, hv_exclusion_zones, component_positions)
