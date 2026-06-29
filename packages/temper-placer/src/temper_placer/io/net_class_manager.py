"""
Net class manager for determining trace widths and clearances.

Assigns appropriate trace widths based on net function (power, signal, etc.).
Includes impedance-driven trace width computation from stackup dielectric properties.
Part of Phase 2: Design Rule Compliance (temper-1rt5).
"""

from __future__ import annotations

import math

from temper_placer.core.netlist import Netlist
from temper_placer.router_v6.net_classification import (
    is_ground_net as _is_ground_net,
)
from temper_placer.router_v6.net_classification import (
    is_hv_net as _is_hv_net,
)
from temper_placer.router_v6.net_classification import (
    is_power_net as _is_power_net,
)

POWER_KEYWORDS = ["GND", "VCC", "VDD", "VSS", "VBUS", "+3V3", "+5V", "+12V", "+15V", "VBAT", "AC_L", "AC_N", "DC_BUS", "PGND", "CGND"]
HIGH_SPEED_KEYWORDS = ["USB", "SPI", "I2C", "SDA", "SCL", "MISO", "MOSI", "CLK", "RX", "TX"]

# ---------------------------------------------------------------------------
# Fallback lookup table: common FR4 4/6-layer stackups
# ---------------------------------------------------------------------------
# Maps (target_impedance_ohms, layer_count) -> typical microstrip width (mm)
# for 1oz (35um) copper on standard FR4 (epsilon_r ~ 4.5).
# Used only when no explicit StackupInfo is available.
#
# Sources: JLCPCB / generic FR4 stackup tables.
_FALLBACK_TRACE_WIDTH_TABLE: dict[tuple[float, int], float] = {
    # 4-layer FR4 (1.6mm total, ~0.2mm prepreg to reference plane)
    (50.0, 4): 0.35,
    (50.0, 6): 0.18,
    (90.0, 4): 0.12,
    (90.0, 6): 0.08,
    (100.0, 4): 0.10,
    (100.0, 6): 0.07,
}

# ---------------------------------------------------------------------------
# Microstrip impedance computation
# ---------------------------------------------------------------------------


def _microstrip_z0_wheeler(w_over_h: float, epsilon_r: float, t_over_h: float = 0.0) -> float:
    """Compute microstrip characteristic impedance using Wheeler's formula.

    Args:
        w_over_h: Ratio of trace width to dielectric height (W/h)
        epsilon_r: Relative permittivity of the dielectric
        t_over_h: Ratio of trace thickness to dielectric height (t/h)

    Returns:
        Characteristic impedance Z0 in ohms
    """
    # Effective width correction for conductor thickness (t > 0)
    if t_over_h > 0 and w_over_h > 0:
        # Wheeler's thickness correction
        if w_over_h < 1.0 / (2.0 * math.pi):
            w_eff = w_over_h + (
                t_over_h / math.pi * (1.0 + math.log(4.0 * math.pi * w_over_h / t_over_h))
                if t_over_h < w_over_h
                else w_over_h + t_over_h / math.pi * (1.0 + math.log(2.0 / t_over_h))
            )
        else:
            w_eff = w_over_h + (
                t_over_h / math.pi * (1.0 + math.log(2.0 / t_over_h))
            )
    else:
        w_eff = w_over_h

    w = w_eff

    if w <= 1.0:
        # Narrow strip: W/h <= 1
        eps_eff = (
            (epsilon_r + 1.0) / 2.0
            + (epsilon_r - 1.0) / 2.0
            * (1.0 / math.sqrt(1.0 + 12.0 / w) + 0.04 * (1.0 - w) ** 2)
        )
        z0 = (60.0 / math.sqrt(eps_eff)) * math.log(8.0 / w + w / 4.0)
    else:
        # Wide strip: W/h >= 1
        eps_eff = (
            (epsilon_r + 1.0) / 2.0
            + (epsilon_r - 1.0) / 2.0 * 1.0 / math.sqrt(1.0 + 12.0 / w)
        )
        z0 = (120.0 * math.pi / math.sqrt(eps_eff)) / (
            w + 1.393 + 0.667 * math.log(w + 1.444)
        )

    return z0


def _microstrip_impedance_error(
    w_over_h: float, target_z0: float, epsilon_r: float, t_over_h: float
) -> float:
    """Return the error between computed Z0 and target Z0."""
    return _microstrip_z0_wheeler(w_over_h, epsilon_r, t_over_h) - target_z0


def compute_microstrip_width(
    target_impedance_ohms: float,
    epsilon_r: float,
    height_mm: float,
    trace_thickness_mm: float = 0.035,
) -> float:
    """Compute microstrip trace width for a target characteristic impedance.

    Uses Wheeler's formula with binary search refinement, accurate to
    within ~0.5% for W/h ratios between 0.1 and 10.

    Args:
        target_impedance_ohms: Desired characteristic impedance (Omega), e.g. 50.0
        epsilon_r: Dielectric constant of the substrate (epsilon_r)
        height_mm: Height of the dielectric between trace and reference plane (mm)
        trace_thickness_mm: Copper trace thickness (mm), default 0.035mm = 1oz

    Returns:
        Computed trace width in mm

    Raises:
        ValueError: If parameters are non-positive or the target impedance
                    is unreachable with the given stackup.

    Example:
        >>> # 50 Omega on FR4 with 0.2mm prepreg, 1oz Cu
        >>> w = compute_microstrip_width(50.0, 4.5, 0.2)
        >>> 0.30 < w < 0.40
        True
    """
    if target_impedance_ohms <= 0:
        raise ValueError(
            f"target_impedance_ohms must be positive, got {target_impedance_ohms}"
        )
    if epsilon_r <= 1.0:
        raise ValueError(f"epsilon_r must be > 1.0, got {epsilon_r}")
    if height_mm <= 0:
        raise ValueError(f"height_mm must be positive, got {height_mm}")
    if trace_thickness_mm <= 0:
        raise ValueError(
            f"trace_thickness_mm must be positive, got {trace_thickness_mm}"
        )

    t_over_h = trace_thickness_mm / height_mm

    # --- Initial guess via inverted IPC-2141 formula ---
    # Z0 approx (87/sqrt(epsilon_r+1.41)) * ln(5.98*h / (0.8*W + t))
    # -> W = (5.98*h / exp(Z0*sqrt(epsilon_r+1.41)/87) - t) / 0.8
    factor = 87.0 / math.sqrt(epsilon_r + 1.41)
    exponent = target_impedance_ohms / factor
    # Guard against overflow: if exponent is too large, W will be tiny
    if exponent > 50:
        w_mm = 0.001  # extremely narrow
    else:
        w_mm = (5.98 * height_mm / math.exp(exponent) - trace_thickness_mm) / 0.8
        if w_mm <= 0:
            w_mm = 0.001

    w_over_h = w_mm / height_mm

    # --- Binary search refinement using Wheeler's formula ---
    lo = max(w_over_h * 0.3, 0.01)
    hi = w_over_h * 3.0 + 2.0  # generous upper bound
    # Ensure the target is bracketed
    z_lo = _microstrip_z0_wheeler(lo, epsilon_r, t_over_h)
    z_hi = _microstrip_z0_wheeler(hi, epsilon_r, t_over_h)

    # Expand bounds if needed
    for _ in range(20):
        if z_lo >= target_impedance_ohms >= z_hi:
            break
        if target_impedance_ohms > z_lo:
            lo *= 0.5
            z_lo = _microstrip_z0_wheeler(lo, epsilon_r, t_over_h)
        if target_impedance_ohms < z_hi:
            hi *= 2.0
            z_hi = _microstrip_z0_wheeler(hi, epsilon_r, t_over_h)
    else:
        raise ValueError(
            f"Cannot achieve {target_impedance_ohms} Ohm with "
            f"epsilon_r={epsilon_r}, h={height_mm}mm: Z0 range [{z_lo:.1f}, {z_hi:.1f}] Ohm"
        )

    # Binary search
    for _ in range(40):
        mid = (lo + hi) / 2.0
        z_mid = _microstrip_z0_wheeler(mid, epsilon_r, t_over_h)
        if z_mid > target_impedance_ohms:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-6:
            break

    w_over_h_final = (lo + hi) / 2.0
    return w_over_h_final * height_mm


# ---------------------------------------------------------------------------
# Fallback trace width lookup by stackup
# ---------------------------------------------------------------------------


def _lookup_fallback_width(
    target_impedance_ohms: float,
    layer_count: int = 4,
) -> float | None:
    """Look up a pre-computed trace width from the fallback table.

    Args:
        target_impedance_ohms: Target characteristic impedance (Omega)
        layer_count: Number of PCB layers (4 or 6)

    Returns:
        Trace width in mm, or None if no entry matches.
    """
    # Exact match
    key = (target_impedance_ohms, layer_count)
    if key in _FALLBACK_TRACE_WIDTH_TABLE:
        return _FALLBACK_TRACE_WIDTH_TABLE[key]

    # Closest impedance match for the given layer count
    candidates = [
        (abs(z - target_impedance_ohms), w)
        for (z, lc), w in _FALLBACK_TRACE_WIDTH_TABLE.items()
        if lc == layer_count
    ]
    if not candidates:
        # Try any layer count
        candidates = [
            (abs(z - target_impedance_ohms), w)
            for (z, _lc), w in _FALLBACK_TRACE_WIDTH_TABLE.items()
        ]
    if candidates:
        candidates.sort()
        return candidates[0][1]

    return None


def is_power_net(net_name: str) -> bool:
    """Check if net is a power/ground net.

    Args:
        net_name: Net name to check

    Returns:
        True if net appears to be power or ground

    Example:
        >>> is_power_net("GND")
        True
        >>> is_power_net("SIG_DATA")
        False
    """
    return (
        _is_ground_net(net_name)
        or _is_power_net(net_name)
        or _is_hv_net(net_name)
    )


def is_high_speed_net(net_name: str) -> bool:
    """Check if net is likely high-speed signal.

    Args:
        net_name: Net name to check

    Returns:
        True if net appears to be high-speed

    Example:
        >>> is_high_speed_net("USB_DP")
        True
        >>> is_high_speed_net("LED1")
        False
    """
    net_upper = net_name.upper()
    return any(keyword in net_upper for keyword in HIGH_SPEED_KEYWORDS)


def get_trace_width(
    net_name: str,
    netlist: Netlist | None = None,
    default: float = 0.25,
    target_impedance: float | None = None,
    stackup_epsilon_r: float | None = None,
    stackup_height_mm: float | None = None,
    stackup_layer_count: int = 4,
) -> float:
    """Determine appropriate trace width for a net.

    Selection rules (in priority order):
    - AC Power nets (AC_L, AC_N): 2.0mm
    - DC Bus nets (DC_BUS+, DC_BUS-): 1.5mm
    - Low voltage power nets (+5V, +3V3): 0.5mm
    - Impedance-controlled nets: computed from stackup when
      target_impedance is set AND dielectric data is available,
      otherwise looked up from a fallback table.
    - High-speed nets: 0.2mm (controlled impedance)
    - Signal nets: 0.25mm (default)
    - Fine-pitch nets: 0.15mm (detected from component pitch)

    Args:
        net_name: Name of the net
        netlist: Optional netlist for context-aware selection
        default: Default width if no rules match
        target_impedance: Optional target impedance in ohms from net class rules
        stackup_epsilon_r: Dielectric constant from stackup (epsilon_r)
        stackup_height_mm: Dielectric height from signal layer to reference plane (mm)
        stackup_layer_count: Total PCB layer count (4 or 6), for fallback lookup

    Returns:
        Trace width in mm
    """
    net_upper = net_name.upper()

    # AC Power
    if "AC_L" in net_upper or "AC_N" in net_upper:
        return 2.0

    # DC Bus
    if "DC_BUS" in net_upper:
        return 1.5

    # Power nets get wider traces
    if is_power_net(net_name):
        return 0.5

    # --- Impedance-driven trace width ---
    # When target_impedance is set and we have stackup data, compute
    # the exact microstrip width. Falls back to a lookup table when
    # stackup data is unavailable.
    if target_impedance is not None and target_impedance > 0:
        if (
            stackup_epsilon_r is not None
            and stackup_height_mm is not None
            and stackup_epsilon_r > 1.0
            and stackup_height_mm > 0
        ):
            try:
                return compute_microstrip_width(
                    target_impedance_ohms=target_impedance,
                    epsilon_r=stackup_epsilon_r,
                    height_mm=stackup_height_mm,
                )
            except ValueError:
                # Fall through to fallback table
                pass

        # Fallback: use lookup table for common FR4 stackups
        fallback = _lookup_fallback_width(target_impedance, stackup_layer_count)
        if fallback is not None:
            return fallback

        # Last resort: return narrow trace for impedance control
        return 0.2

    # High-speed nets get narrow traces for impedance control
    if is_high_speed_net(net_name):
        return 0.2

    # Fine-pitch detection (if netlist provided)
    if netlist:
        # Check if any component on this net has fine pitch
        for net in netlist.nets:
            if net.name == net_name:
                # Check component pitch through pin spacing
                for comp_ref, _pin_num in net.pins:
                    comp = next((c for c in netlist.components if c.ref == comp_ref), None)
                    if comp and _is_fine_pitch_component(comp):
                        return 0.15

    return default


def _is_fine_pitch_component(comp) -> bool:
    """Check if component has fine pitch (< 0.5mm).

    Args:
        comp: Component object

    Returns:
        True if component has fine pitch pads
    """
    # Check footprint name for common fine-pitch packages
    fp_upper = comp.footprint.upper()
    fine_pitch_packages = ["QFN", "QFP", "BGA", "CSP", "USB-C", "TQFP"]

    return any(pkg in fp_upper for pkg in fine_pitch_packages)


def create_trace_width_map(
    netlist: Netlist,
    default: float = 0.25,
) -> dict[str, float]:
    """Create a complete trace width mapping for all nets in netlist.

    Args:
        netlist: Netlist containing all nets
        default: Default trace width for unmapped nets

    Returns:
        Dictionary of net_name → trace_width (mm)

    Example:
        >>> netlist = Netlist(...)
        >>> widths = create_trace_width_map(netlist)
        >>> widths["GND"]
        0.5
        >>> widths["DATA_BUS"]
        0.25
    """
    width_map = {}

    for net in netlist.nets:
        width_map[net.name] = get_trace_width(net.name, netlist, default)

    return width_map


def create_netclass_config(netlist: Netlist) -> dict[str, dict]:
    """Generate KiCad net class definitions.

    Creates net class configurations suitable for KiCad PCB setup.

    Args:
        netlist: Netlist to analyze

    Returns:
        Dictionary of netclass_name → config dict

    Example:
        >>> config = create_netclass_config(netlist)
        >>> config["Power"]["clearance"]
        0.2
        >>> config["FinePitch"]["trace_width"]
        0.15
    """
    netclasses: dict[str, dict] = {
        "Default": {
            "description": "Default net class",
            "clearance": 0.2,
            "trace_width": 0.2,
            "via_diameter": 0.6,
            "via_drill": 0.3,
            "nets": [],
        },
        "Power": {
            "description": "Power and ground nets",
            "clearance": 0.2,
            "trace_width": 0.5,  # Wider for current handling
            "via_diameter": 0.8,
            "via_drill": 0.4,
            "nets": [],
        },
        "FinePitch": {
            "description": "Fine-pitch component nets",
            "clearance": 0.1,  # Tighter spacing allowed
            "trace_width": 0.15,  # Narrow traces
            "via_diameter": 0.6,  # Smaller vias
            "via_drill": 0.3,
            "nets": [],
        },
        "HighSpeed": {
            "description": "High-speed signals",
            "clearance": 0.2,
            "trace_width": 0.2,  # Controlled impedance
            "via_diameter": 0.6,
            "via_drill": 0.3,
            "nets": [],
        },
    }

    # Assign nets to classes
    for net in netlist.nets:
        if is_power_net(net.name):
            netclasses["Power"]["nets"].append(net.name)
        elif is_high_speed_net(net.name):
            netclasses["HighSpeed"]["nets"].append(net.name)
        elif any(_is_fine_pitch_component(c) for c in netlist.components
                 if any(conn[0] == c.ref for conn in net.connections)):
            netclasses["FinePitch"]["nets"].append(net.name)
        else:
            netclasses["Default"]["nets"].append(net.name)

    return netclasses


def get_clearance_for_net(net_name: str, default: float = 0.2) -> float:
    """Get clearance requirement for a net.

    Args:
        net_name: Net name
        default: Default clearance in mm

    Returns:
        Clearance in mm
    """
    # Power nets can use standard clearance
    if is_power_net(net_name):
        return 0.2

    # High-speed nets need good separation
    if is_high_speed_net(net_name):
        return 0.2

    return default
