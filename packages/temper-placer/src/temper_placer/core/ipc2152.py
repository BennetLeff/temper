"""
IPC-2221B inverse ampacity: minimum trace width from expected current.

Delegates core computation to the temper_drc_rs Rust extension (the
authoritative IPC-2221B kernel, k = 0.048 external / 0.024 internal).

Historical note: the "ipc2152" name is legacy — this module's formula is
IPC-2221B §6.2 (I = k·ΔT^0.44·A^0.725), and nothing in this repo is
genuinely IPC-2152.  The name predates the correction and is kept for
API stability; the k coefficients (0.048/0.024) and their IPC-2221B
source are documented in docs/hardware/TRACE_WIDTH_CALCULATIONS.md §2.
"""

from temper_drc_rs import (  # noqa: F401 — re-export
    DEFAULT_SIGNAL_CURRENT,
    NET_CURRENTS,
    TRACE_TEMP_RISE_C,
    get_net_current,
    ipc2152_current_capacity,
    ipc2152_min_width_mm,
)


def ipc2152_external_width(current_amps, copper_weight_oz, temp_rise_c=TRACE_TEMP_RISE_C):
    """Trace width in mm for external layers (F.Cu / B.Cu).

    Convenience wrapper around ipc2152_min_width_mm with internal_layer=False.

    FIXED 2026-08-14: default was an independent literal `10.0`; now reads
    the single-sourced `temper_drc_rs.TRACE_TEMP_RISE_C` (20.0, cited from
    docs/hardware/TRACE_WIDTH_CALCULATIONS.md SS1) -- see that constant's
    doc comment for the full reconciliation.
    """
    return ipc2152_min_width_mm(current_amps, copper_weight_oz, temp_rise_c, False)


def ipc2152_internal_width(current_amps, copper_weight_oz, temp_rise_c=TRACE_TEMP_RISE_C):
    """Trace width in mm for internal layers (In1.Cu / In2.Cu).

    Uses the internal-layer curve (k=0.024), producing roughly double the
    area requirement of the external curve for the same current (approx
    0.5x derating in current capacity).

    FIXED 2026-08-14: default was an independent literal `10.0`; see
    `ipc2152_external_width`'s docstring above for the reconciliation.
    """
    return ipc2152_min_width_mm(current_amps, copper_weight_oz, temp_rise_c, True)


def ipc2152_min_width(_net_name, current_amps, layer=None, stackup=None):
    """IPC-2221B minimum trace width for a net on its assigned layer.

    Resolves copper weight and internal/external layer type from the
    stackup if provided; falls back to 1.0 oz (copper_weight default)
    with internal/external decided by the layer name ("In*" = internal)
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
                    candidate,
                    "copper_weight",
                    getattr(candidate, "copper_weight_oz", 1.0),
                )
                layer_type = getattr(
                    candidate,
                    "layer_type",
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
