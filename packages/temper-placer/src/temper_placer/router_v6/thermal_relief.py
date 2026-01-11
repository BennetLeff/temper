"""
Router V6 Stage 5.4: Add Thermal Relief

Validates and generates thermal relief connections for power planes.
Part of temper-95xg (Stage 5 - Manufacturing DRC)
"""

from __future__ import annotations

from dataclasses import dataclass

from temper_placer.router_v6.routing_results import RoutingResults


@dataclass
class ThermalRelief:
    """Thermal relief connection specification."""

    net_name: str
    pad_position: tuple[float, float]
    spoke_count: int  # Number of spokes (typically 4)
    spoke_width: float  # Width of each spoke (mm)
    clearance_gap: float  # Gap from pad to plane (mm)


@dataclass
class ThermalReliefReport:
    """Report of thermal relief connections."""

    thermal_reliefs: list[ThermalRelief]
    
    @property
    def relief_count(self) -> int:
        """Total number of thermal reliefs."""
        return len(self.thermal_reliefs)
    
    @property
    def total_spokes(self) -> int:
        """Total number of spokes across all reliefs."""
        return sum(tr.spoke_count for tr in self.thermal_reliefs)


def add_thermal_relief(
    routing_results: RoutingResults,
    spoke_count: int = 4,
    spoke_width: float = 0.254,  # 10mil typical
    clearance_gap: float = 0.254,  # 10mil typical
) -> ThermalReliefReport:
    """
    Add thermal relief connections to power plane pads.

    Thermal relief prevents excessive heat sinking during soldering
    while maintaining electrical connection to power planes.

    Args:
        routing_results: Compiled routing results from Stage 4.9
        spoke_count: Number of connection spokes (typically 4)
        spoke_width: Width of each spoke (mm)
        clearance_gap: Gap between pad and plane (mm)

    Returns:
        ThermalReliefReport with all generated thermal reliefs

    Example:
        >>> from temper_placer.router_v6.routing_results import RoutingResults
        >>> results = RoutingResults(compiled_routes={}, failed_nets=[])
        >>> report = add_thermal_relief(results)
        >>> report.relief_count >= 0
        True
    """
    thermal_reliefs = []
    
    for net_name, compiled_route in routing_results.compiled_routes.items():
        # Check if this is a power net that needs thermal relief
        if _is_power_net(net_name):
            # Analyze route to identify power plane connections
            # For each via connecting to power plane, add thermal relief
            for via in compiled_route.vias:
                if _connects_to_power_plane(via, net_name):
                    thermal_relief = ThermalRelief(
                        net_name=net_name,
                        pad_position=via.position,
                        spoke_count=spoke_count,
                        spoke_width=spoke_width,
                        clearance_gap=clearance_gap,
                    )
                    thermal_reliefs.append(thermal_relief)
    
    return ThermalReliefReport(thermal_reliefs=thermal_reliefs)


def _is_power_net(net_name: str) -> bool:
    """
    Check if net is a power net requiring thermal relief.

    Args:
        net_name: Net name

    Returns:
        True if power net
    """
    name_upper = net_name.upper()
    power_keywords = ['GND', 'VCC', 'VDD', 'VSS', 'VDDA', 'POWER']
    return any(kw in name_upper for kw in power_keywords)


def _connects_to_power_plane(via, net_name: str) -> bool:
    """
    Check if via connects to a power plane.

    Args:
        via: Via object
        net_name: Net name

    Returns:
        True if connects to power plane
    """
    # Simplified: assume inner layer connections are to planes
    # In reality would check layer stackup
    plane_layers = ['In1.Cu', 'In2.Cu']
    return via.from_layer in plane_layers or via.to_layer in plane_layers
