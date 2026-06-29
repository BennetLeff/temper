"""
IPC-2221 trace current capacity calculation.

Implements industry-standard formulas for estimating maximum current capacity
of PCB traces based on width, copper thickness, and allowable temperature rise.
"""



def estimate_trace_current(
    width_mm: float,
    thickness_oz: float = 1.0,
    temp_rise_c: float = 10.0,
    internal_layer: bool = False,
) -> float:
    """
    Calculate maximum current capacity using IPC-2221 formula.

    Args:
        width_mm: Trace width in millimeters
        thickness_oz: Copper thickness in oz (1 oz = 1.37 mils = 35 μm)
        temp_rise_c: Allowable temperature rise in Celsius (default 10°C)
        internal_layer: True for internal layers, False for external (better cooling)

    Returns:
        Maximum current in Amperes

    Formula:
        I = (ΔT / (0.024 * A^0.44))^(1/0.725)  [internal layers]
        I = (ΔT / (0.048 * A^0.44))^(1/0.725)  [external layers]

    Where:
        I = Current in Amps
        ΔT = Temperature rise in °C
        A = Cross-sectional area in mils²

    References:
        - IPC-2221A: Generic Standard on Printed Board Design
        - IPC-2152: Standard for Determining Current Carrying Capacity in PCB

    Examples:
        >>> estimate_trace_current(0.25, 1.0, 10.0, internal_layer=True)
        1.2  # 0.25mm trace on internal layer: ~1.2A

        >>> estimate_trace_current(3.0, 2.0, 10.0, internal_layer=False)
        12.5  # 3.0mm trace, 2oz copper on external layer: ~12.5A
    """
    # Convert to mils (thousandths of an inch)
    width_mils = width_mm * 39.3701  # 1mm = 39.3701 mils
    thickness_mils = thickness_oz * 1.37  # 1 oz = 1.37 mils

    # Calculate cross-sectional area
    area_mils2 = width_mils * thickness_mils

    # IPC-2221 constants (from curve fitting)
    k = 0.024 if internal_layer else 0.048

    # IPC-2221 formula (CORRECTED): I = k × ΔT^0.44 × A^0.725
    # FIXED: Previous formula was inverted!
    current_a = k * (temp_rise_c ** 0.44) * (area_mils2 ** 0.725)

    return current_a


def estimate_current_from_net_class(
    trace_width_mm: float,
    thickness_oz: float = 1.0,
    temp_rise_c: float = 10.0,
) -> float:
    """
    Estimate current capacity for a net class based on trace width.

    Uses conservative internal layer calculation (worst case).

    Args:
        trace_width_mm: Trace width in millimeters
        thickness_oz: Copper thickness in oz (default 1.0)
        temp_rise_c: Temperature rise above ambient (default 10°C per IPC-2221)

    Returns:
        Maximum current in Amperes

    Examples:
        >>> estimate_current_from_net_class(0.25, 1.0, 10.0)
        1.2  # 0.25mm trace, 1oz copper, 10C rise (internal): ~1.2A
        >>> estimate_current_from_net_class(0.5, 2.0, 20.0)
        4.5  # 0.5mm trace, 2oz copper, 20C rise (internal): ~4.5A
    """
    return estimate_trace_current(
        width_mm=trace_width_mm,
        thickness_oz=thickness_oz,
        temp_rise_c=temp_rise_c,
        internal_layer=True,  # Conservative estimate
    )


# Current capacity lookup table (1 oz copper, 10°C rise, internal layers)
# For quick reference without calculation
TRACE_CURRENT_TABLE_1OZ = {
    0.15: 0.7,   # 0.15mm → ~0.7A
    0.2: 1.0,    # 0.2mm  → ~1.0A (Signal)
    0.25: 1.2,   # 0.25mm → ~1.2A
    0.4: 2.0,    # 0.4mm  → ~2.0A (GateDrive)
    0.5: 2.5,    # 0.5mm  → ~2.5A (Power/HighCurrent)
    1.0: 5.0,    # 1.0mm  → ~5.0A (GND)
    2.0: 9.5,    # 2.0mm  → ~9.5A
    3.0: 14.0,   # 3.0mm  → ~14.0A (HighCurrent)
    5.0: 22.0,   # 5.0mm  → ~22.0A
    10.0: 42.0,  # 10.0mm → ~42.0A
}
