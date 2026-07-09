"""
IPC-2152 inverse ampacity: minimum trace width from expected current.

Computes the minimum trace width required to carry a given current under
IPC-2152 with internal-layer derating. IPC-2152 is less conservative than
IPC-2221 (used in ipc2221.py) and is the recommended standard for current
carrying capacity in PCB design.

The external-layer formula is derived from curve-fitting the IPC-2152
universal chart:

    area_mils2 = (current_amps / (k * temp_rise_c**b))**(1/c)
    width_mm = area_to_width(area_mils2, copper_weight_oz)

where k=0.048, b=0.44, c=0.725 for external layers and k=0.024 for internal
layers (roughly 0.5x the external current capacity).

References:
    - IPC-2152: Standard for Determining Current Carrying Capacity in PCB
    - IPC-2152 with Amendment 1, 2023
"""


# IPC-2152 curve-fit constants (conservative fit to universal chart).
_IPC2152_K_EXTERNAL = 0.048
_IPC2152_K_INTERNAL = 0.024
_IPC2152_B = 0.44
_IPC2152_C = 0.725

# Copper thickness: 1 oz = 1.37 mils.
_OZ_TO_MILS = 1.37
# Length: 1 mm = 39.3701 mils.
_MM_TO_MILS = 39.3701


def _area_to_width_mm(area_mils2: float, copper_weight_oz: float) -> float:
    """Convert cross-sectional area (mils^2) to trace width (mm)."""
    thickness_mils = copper_weight_oz * _OZ_TO_MILS
    if thickness_mils <= 0:
        return 0.0
    width_mils = area_mils2 / thickness_mils
    return width_mils / _MM_TO_MILS


def _width_to_area_mils2(width_mm: float, copper_weight_oz: float) -> float:
    """Convert trace width (mm) to cross-sectional area (mils^2)."""
    width_mils = width_mm * _MM_TO_MILS
    thickness_mils = copper_weight_oz * _OZ_TO_MILS
    return width_mils * thickness_mils


# ---------------------------------------------------------------------------
# Inverse ampacity: current -> minimum width
# ---------------------------------------------------------------------------


def ipc2152_min_width_mm(
    current_amps: float,
    copper_weight_oz: float,
    temp_rise_c: float = 10.0,
    internal_layer: bool = False,
) -> float:
    """Minimum trace width in mm for a given current under IPC-2152.

    Args:
        current_amps: Expected current in Amperes.
        copper_weight_oz: Copper weight in oz (1.0 = 1oz = 35um).
        temp_rise_c: Allowable temperature rise in degC (default 10).
        internal_layer: True for internal (inner) layers.

    Returns:
        Minimum trace width in millimeters.

    >>> round(ipc2152_min_width_mm(0.5, 1.0, 10.0, internal_layer=False), 4)
    0.1160
    >>> round(ipc2152_min_width_mm(0.5, 1.0, 10.0, internal_layer=True), 4)
    0.3019
    >>> round(ipc2152_min_width_mm(2.0, 1.0, 10.0, internal_layer=False), 3)
    0.784
    """
    if current_amps <= 0:
        return 0.0

    k = _IPC2152_K_INTERNAL if internal_layer else _IPC2152_K_EXTERNAL

    area_mils2 = (current_amps / (k * temp_rise_c**_IPC2152_B)) ** (1.0 / _IPC2152_C)

    return _area_to_width_mm(area_mils2, copper_weight_oz)


def ipc2152_external_width(
    current_amps: float,
    copper_weight_oz: float,
    temp_rise_c: float = 10.0,
) -> float:
    """Trace width in mm for external layers (F.Cu / B.Cu).

    Convenience wrapper around ipc2152_min_width_mm with internal_layer=False.
    """
    return ipc2152_min_width_mm(current_amps, copper_weight_oz, temp_rise_c, internal_layer=False)


def ipc2152_internal_width(
    current_amps: float,
    copper_weight_oz: float,
    temp_rise_c: float = 10.0,
) -> float:
    """Trace width in mm for internal layers (In1.Cu / In2.Cu).

    Uses the internal-layer curve (k=0.024), producing roughly double the
    area requirement of the external curve for the same current (approx
    0.5x derating in current capacity).
    """
    return ipc2152_min_width_mm(current_amps, copper_weight_oz, temp_rise_c, internal_layer=True)


# ---------------------------------------------------------------------------
# Forward ampacity: width -> current capacity (for gate / round-trip checks)
# ---------------------------------------------------------------------------


def ipc2152_current_capacity(
    width_mm: float,
    copper_weight_oz: float,
    temp_rise_c: float = 10.0,
    internal_layer: bool = False,
) -> float:
    """Forward IPC-2152: max current (A) for a given trace width.

    Inverse of ipc2152_min_width_mm. Useful for gate validation (U6) and
    round-trip consistency checks.

    Args:
        width_mm: Trace width in millimeters.
        copper_weight_oz: Copper weight in oz.
        temp_rise_c: Allowable temperature rise in degC.
        internal_layer: True for internal layers.

    Returns:
        Maximum current in Amperes.

    >>> round(ipc2152_current_capacity(0.1160, 1.0, 10.0, internal_layer=False), 2)
    0.5
    >>> round(ipc2152_current_capacity(0.784, 1.0, 10.0, internal_layer=False), 2)
    2.0
    """
    if width_mm <= 0:
        return 0.0

    k = _IPC2152_K_INTERNAL if internal_layer else _IPC2152_K_EXTERNAL

    area_mils2 = _width_to_area_mils2(width_mm, copper_weight_oz)

    return k * (temp_rise_c**_IPC2152_B) * (area_mils2**_IPC2152_C)


# ---------------------------------------------------------------------------
# Per-net current table (W2 R3 requirements)
# ---------------------------------------------------------------------------


NET_CURRENTS: dict[str, float] = {
    "DC_BUS+": 16.0,
    "AC_L": 10.0,
    "AC_N": 10.0,
    "SW_NODE": 16.0,
    "GATE_H": 2.0,
    "GATE_L": 2.0,
    "+3V3": 0.5,
    "+5V": 0.5,
    "+15V": 0.2,
}
"""Per-net expected currents from W2 R3 requirements.

Peak currents for switching nets, RMS for AC, average for supply rails."""

DEFAULT_SIGNAL_CURRENT = 0.1
"""Default current for unlisted signal nets (100 mA)."""


def get_net_current(net_name: str) -> float:
    """Resolve expected current for a net from the W2 current table.

    Performs case-insensitive substring matching against NET_CURRENTS.
    Falls back to DEFAULT_SIGNAL_CURRENT (100 mA) for unlisted nets.

    Args:
        net_name: Net name.

    Returns:
        Expected current in Amperes.
    """
    name_upper = net_name.upper()
    for key, current in NET_CURRENTS.items():
        if key.upper() in name_upper:
            return current
    return DEFAULT_SIGNAL_CURRENT


# ---------------------------------------------------------------------------
# Integration: IPC-2152 min-width with layer / stackup awareness
# ---------------------------------------------------------------------------


def ipc2152_min_width(
    net_name: str,
    current_amps: float,
    layer: str | int | None = None,
    stackup: object | None = None,
) -> float:
    """IPC-2152 minimum trace width for a net on its assigned layer.

    Resolves copper weight and internal/external layer type from the
    stackup if provided; falls back to defaults (1oz outer, 0.5oz inner)
    otherwise.

    Supports both board.LayerStackup (board.py) and core/stackup.Stackup
    (stackup.py) via duck-typing of copper_weight/copper_weight_oz and
    layer_type/type attributes.

    Args:
        net_name: Net name (for context; not used in computation).
        current_amps: Expected current for this net.
        layer: Layer name ("F.Cu", "B.Cu", etc.) or index (0..3).
        stackup: Optional LayerStackup or Stackup for copper weight lookup.

    Returns:
        Minimum trace width in millimeters.
    """
    if current_amps <= 0:
        return 0.0

    copper_oz = 1.0
    internal = False

    # Resolve from stackup if available.
    if stackup is not None and hasattr(stackup, "layers"):
        for idx, candidate in enumerate(stackup.layers):
            match = False
            if isinstance(layer, str) and candidate.name == layer:
                match = True
            elif isinstance(layer, int):
                # Check kicad_index (stackup.LayerConfig) or positional idx
                kicad_idx = getattr(candidate, "kicad_index", None)
                if kicad_idx is not None and kicad_idx == layer or idx == layer:
                    match = True
            if match:
                # Duck-type copper weight: board.Layer has copper_weight,
                # stackup.LayerConfig has copper_weight_oz.
                copper_oz = getattr(
                    candidate, "copper_weight",
                    getattr(candidate, "copper_weight_oz", 1.0),
                )
                # Duck-type layer type: board.Layer has layer_type,
                # stackup.LayerConfig has type.
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

    return ipc2152_min_width_mm(current_amps, copper_oz, internal_layer=internal)
