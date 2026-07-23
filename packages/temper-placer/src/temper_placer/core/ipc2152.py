"""
IPC-2152 inverse ampacity: minimum trace width from expected current.

Delegates core computation to the temper_ipc Rust extension.
"""
from temper_ipc import (  # noqa: F401 — re-export
    ipc2152_min_width_mm,
    ipc2152_current_capacity,
    get_net_current,
    NET_CURRENTS,
    DEFAULT_SIGNAL_CURRENT,
)


def ipc2152_external_width(current_amps, copper_weight_oz, temp_rise_c=10.0):
    """Trace width in mm for external layers (F.Cu / B.Cu).
    
    Convenience wrapper around ipc2152_min_width_mm with internal_layer=False.
    """
    return ipc2152_min_width_mm(current_amps, copper_weight_oz, temp_rise_c, False)


def ipc2152_internal_width(current_amps, copper_weight_oz, temp_rise_c=10.0):
    """Trace width in mm for internal layers (In1.Cu / In2.Cu).

    Uses the internal-layer curve (k=0.024), producing roughly double the
    area requirement of the external curve for the same current (approx
    0.5x derating in current capacity).
    """
    return ipc2152_min_width_mm(current_amps, copper_weight_oz, temp_rise_c, True)


def ipc2152_min_width(net_name, current_amps, layer=None, stackup=None):
    """IPC-2152 minimum trace width for a net on its assigned layer.

    Resolves copper weight and internal/external layer type from the
    stackup if provided; falls back to defaults (1oz outer, 0.5oz inner)
    otherwise.

    Supports both board.LayerStackup (board.py) and core/stackup.Stackup
    (stackup.py) via duck-typing of copper_weight/copper_weight_oz and
    layer_type/type attributes.
    """
    if current_amps <= 0:
        return 0.0

    copper_oz = 1.0
    internal = False

    if stackup is not None and hasattr(stackup, "layers"):
        for idx, candidate in enumerate(stackup.layers):
            match = False
            if isinstance(layer, str) and candidate.name == layer:
                match = True
            elif isinstance(layer, int):
                kicad_idx = getattr(candidate, "kicad_index", None)
                if kicad_idx is not None and kicad_idx == layer or idx == layer:
                    match = True
            if match:
                copper_oz = getattr(
                    candidate, "copper_weight",
                    getattr(candidate, "copper_weight_oz", 1.0),
                )
                layer_type = getattr(
                    candidate, "layer_type",
                    getattr(candidate, "type", "signal"),
                )
                internal = layer_type == "plane" or (
                    hasattr(candidate, "is_routable") and not candidate.is_routable
                )
                break
    elif isinstance(layer, str):
        internal = layer.startswith("In")
    elif isinstance(layer, int):
        internal = layer in (1, 2)

    return ipc2152_min_width_mm(current_amps, copper_oz, 10.0, internal)
