"""
Net class manager for determining trace widths and clearances.

Assigns appropriate trace widths based on net function (power, signal, etc.).
Part of Phase 2: Design Rule Compliance (temper-1rt5).
"""

from temper_placer.core.netlist import Netlist
from temper_placer.routing.net_classification import (
    is_ground_net as _is_ground_net,
    is_hv_net as _is_hv_net,
    is_power_net as _is_power_net,
)


POWER_KEYWORDS = ["GND", "VCC", "VDD", "VSS", "VBUS", "+3V3", "+5V", "+12V", "+15V", "VBAT", "AC_L", "AC_N", "DC_BUS", "PGND", "CGND"]
HIGH_SPEED_KEYWORDS = ["USB", "SPI", "I2C", "SDA", "SCL", "MISO", "MOSI", "CLK", "RX", "TX"]


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
) -> float:
    """Determine appropriate trace width for a net.

    Selection rules:
    - AC Power nets (AC_L, AC_N): 2.0mm
    - DC Bus nets (DC_BUS+, DC_BUS-): 1.5mm
    - Low voltage power nets (+5V, +3V3): 0.5mm
    - High-speed nets: 0.2mm (controlled impedance)
    - Signal nets: 0.25mm (default)
    - Fine-pitch nets: 0.15mm (detected from component pitch)

    Args:
        net_name: Name of the net
        netlist: Optional netlist for context-aware selection
        default: Default width if no rules match

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

    # High-speed nets get narrow traces for impedance control
    if is_high_speed_net(net_name):
        return 0.2

    # Fine-pitch detection (if netlist provided)
    if netlist:
        # Check if any component on this net has fine pitch
        for net in netlist.nets:
            if net.name == net_name:
                # Check component pitch through pin spacing
                for comp_ref, pin_num in net.pins:
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
    netclasses = {
        "Default": {
            "description": "Default net class",
            "clearance": 0.2,  # mm
            "trace_width": 0.25,  # mm
            "via_diameter": 0.8,  # mm
            "via_drill": 0.4,  # mm
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
