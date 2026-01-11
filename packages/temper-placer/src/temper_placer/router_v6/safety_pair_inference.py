"""
Router V6 Stage 0.4: Safety Pair Inference

Identifies safety-critical net pairs for creepage verification.
Part of temper-vha9
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SafetyPair:
    """A safety-critical pair of nets requiring creepage/clearance verification."""

    net_a: str  # High-voltage net (e.g., "AC_L", "MAINS_L")
    net_b: str  # Low-voltage net (e.g., "3V3", "GND")
    required_creepage_mm: float  # Surface distance (IEC 62368-1)
    required_clearance_mm: float  # Air distance

    def __post_init__(self):
        """Validate safety pair."""
        if self.net_a == self.net_b:
            raise ValueError(f"Safety pair nets must be different: {self.net_a}")
        if self.required_creepage_mm < self.required_clearance_mm:
            raise ValueError(
                f"Creepage ({self.required_creepage_mm}mm) must be >= clearance ({self.required_clearance_mm}mm)"
            )


def infer_safety_pairs(net_names: list[str], net_class_assignments: dict[str, str] | None = None) -> list[SafetyPair]:
    """
    Identify safety-critical net pairs for creepage verification.

    Applies IEC 62368-1 rules for Temper induction cooker:
    - 240VAC mains, pollution degree 2
    - Mains to SELV (Safety Extra Low Voltage): creepage=5mm, clearance=3mm
    - Mains to earth: creepage=3mm, clearance=2mm

    Args:
        net_names: List of all net names in the design.
        net_class_assignments: Optional mapping of net_name -> net_class for better HV detection

    Returns:
        List of SafetyPair instances requiring verification.

    Example:
        >>> nets = ["AC_L", "AC_N", "3V3", "GND", "PGND"]
        >>> pairs = infer_safety_pairs(nets)
        >>> len(pairs) >= 2  # At least AC_L->3V3 and AC_L->GND
        True
    """
    # Identify high-voltage nets
    hv_nets = set()
    for net in net_names:
        upper = net.upper()
        # Pattern matching for HV nets
        if any(pattern in upper for pattern in ["AC_", "MAINS_", "LINE_", "HV_"]):
            hv_nets.add(net)
        elif upper.startswith("AC") and len(upper) <= 4:  # AC, ACL, ACN, AC_L, etc
            hv_nets.add(net)
        # Check net class if provided
        elif net_class_assignments and net_class_assignments.get(net, "").upper() in ["HV", "HIGHVOLTAGE", "MAINS"]:
            hv_nets.add(net)

    # Identify low-voltage nets (logic/SELV)
    lv_nets = set()
    for net in net_names:
        if net in hv_nets:
            continue  # Skip HV nets
        upper = net.upper()
        # Logic voltage patterns
        if any(pattern in upper for pattern in ["3V3", "5V", "VCC", "VDD", "12V", "15V", "24V"]):
            lv_nets.add(net)
        # Signal nets (non-power)
        elif not any(pattern in upper for pattern in ["GND", "PGND", "EARTH"]):
            # Generic signals are LV
            lv_nets.add(net)

    # Identify ground nets (separate category - special creepage rules)
    gnd_nets = set()
    earth_nets = set()
    for net in net_names:
        if net in hv_nets:
            continue
        upper = net.upper()
        if "PGND" in upper or "POWER_GND" in upper:
            gnd_nets.add(net)  # Power ground (connected to IGBT source, isolated from logic)
        elif "EARTH" in upper or "PE" in upper or upper == "GND" and "POWER" in net:
            earth_nets.add(net)  # Protective earth
        elif "GND" in upper:
            lv_nets.add(net)  # Logic ground (SELV)

    # Generate safety pairs with IEC 62368-1 requirements
    pairs = []

    # HV to LV (SELV): strictest requirements
    for hv_net in hv_nets:
        for lv_net in lv_nets:
            pairs.append(
                SafetyPair(
                    net_a=hv_net,
                    net_b=lv_net,
                    required_creepage_mm=5.0,  # Mains to SELV
                    required_clearance_mm=3.0,
                )
            )

    # HV to earth/PGND: relaxed (both referenced to mains)
    for hv_net in hv_nets:
        for gnd_net in gnd_nets | earth_nets:
            pairs.append(
                SafetyPair(
                    net_a=hv_net,
                    net_b=gnd_net,
                    required_creepage_mm=3.0,  # Mains to earth
                    required_clearance_mm=2.0,
                )
            )

    # Power GND (PGND) to logic (SELV): medium requirements
    for pgnd_net in gnd_nets:
        for lv_net in lv_nets:
            pairs.append(
                SafetyPair(
                    net_a=pgnd_net,
                    net_b=lv_net,
                    required_creepage_mm=4.0,  # PGND often at mains potential via IGBT
                    required_clearance_mm=2.5,
                )
            )

    return pairs
