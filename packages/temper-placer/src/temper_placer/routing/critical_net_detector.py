"""
Automatic critical net detection for pre-routing (temper-cjxg.1).

This module identifies and categorizes critical nets from a netlist based on:
- Naming patterns (e.g., VCC, GND, CLK)
- Connectivity analysis (power pins, clock pins)
- Component attributes

Critical nets are then routed before general signal routing to ensure
optimal paths for power distribution and high-speed signals.

Example usage:
    >>> from temper_placer.routing.critical_net_detector import CriticalNetDetector, CriticalNetCategory
    >>> from temper_placer.core.netlist import Netlist
    >>>
    >>> detector = CriticalNetDetector()
    >>> critical_nets = detector.detect_critical_nets(netlist)
    >>> print(f"Found {len(critical_nets)} critical nets")
"""

from dataclasses import dataclass
from enum import IntEnum
from typing import Optional

from temper_placer.core.netlist import Net, Netlist


class CriticalNetCategory(IntEnum):
    """Category of critical net for routing priority.

    Values determine routing order within critical nets:
    - POWER: Power distribution (VCC, VDD, etc.) - route first
    - GROUND: Ground networks - route second
    - CLOCK: Clock signals - route third
    - HIGH_SPEED: High-speed buses (SPI, I2C, etc.)
    - HIGH_CURRENT: High-current paths (heaters, motors)
    """

    POWER = 0
    GROUND = 1
    CLOCK = 2
    HIGH_SPEED = 3
    HIGH_CURRENT = 4


@dataclass
class CriticalNet:
    """A detected critical net with category and metadata.

    Attributes:
        name: Net name.
        category: CriticalNetCategory classification.
        pin_count: Number of pins connected to this net.
        sources: List of power source component references (for power nets).
        loads: List of load component references (for power nets).
    """

    name: str
    category: CriticalNetCategory
    pin_count: int
    sources: list[str]
    loads: list[str]


@dataclass
class CriticalNetDetectionResult:
    """Result of critical net detection.

    Attributes:
        critical_nets: Dictionary mapping net names to CriticalNet.
        power_nets: List of power net names.
        ground_nets: List of ground net names.
        clock_nets: List of clock net names.
        high_speed_nets: List of high-speed bus net names.
        high_current_nets: List of high-current net names.
    """

    critical_nets: dict[str, CriticalNet]
    power_nets: list[str]
    ground_nets: list[str]
    clock_nets: list[str]
    high_speed_nets: list[str]
    high_current_nets: list[str]

    def get_nets_by_category(self, category: CriticalNetCategory) -> list[str]:
        """Get list of net names for a specific category."""
        return [net.name for net in self.critical_nets.values() if net.category == category]


class CriticalNetDetector:
    """Detector for automatic identification of critical nets.

    This class analyzes a netlist to identify nets that should be routed
    before general signal routing. Detection uses:
    1. Naming pattern matching (e.g., "VCC", "GND", "CLK")
    2. Connectivity analysis (power pin connections)
    3. Component footprint analysis

    Attributes:
        power_patterns: Regex patterns for power net names.
        ground_patterns: Regex patterns for ground net names.
        clock_patterns: Regex patterns for clock signal names.
        high_speed_patterns: Regex patterns for high-speed bus names.
        high_current_patterns: Regex patterns for high-current net names.
    """

    POWER_PATTERNS = [
        r"^VCC$",
        r"^VDD$",
        r"^V\+$",
        r"^VBAT",
        r"^\+[0-9]+\.?[0-9]*V$",
        r"^PWR_",
        r"^POWER_",
        r"^BUS_.*_POS$",
        r"^DC_BUS_P$",
        r"^PVCC$",
        r"^VIN$",
        r"^VSYS$",
    ]

    GROUND_PATTERNS = [
        r"^GND$",
        r"^VSS$",
        r"^0V$",
        r"^AGND$",
        r"^DGND$",
        r"^PGND$",
        r"^EARTH$",
        r"^BUS_.*_NEG$",
        r"^DC_BUS_N$",
    ]

    CLOCK_PATTERNS = [
        r"^CLK",
        r"^CLOCK",
        r"^OSC",
        r"^XTAL",
        r"^.*_CLK$",
        r"^.*_CLOCK$",
    ]

    HIGH_SPEED_PATTERNS = [
        r"^SPI_",
        r"^I2C_",
        r"^USB_",
        r"^JTAG_",
        r"^UART_",
        r"^CAN_",
        r"^RS485_",
        r"^ETH_",
        r"^SD_",
        r"^DQ_",  # DDR data
        r"^DQS_",  # DDR strobe
    ]

    HIGH_CURRENT_PATTERNS = [
        r"^MOTOR_",
        r"^HEATER_",
        r"^SW_NODE",
        r"^GATE_",
        r"^DRIVE_",
        r"^LOAD_",
        r"^BUS_.*_PWR$",
        r"^.*_HIGH_CURRENT$",
    ]

    POWER_PIN_PATTERNS = [
        "VCC",
        "VDD",
        "VIN",
        "VOUT",
        "PVCC",
        "VBAT",
        "PWR",
        "POWER",
        "V+",
        "VCC_IN",
        "VCC_OUT",
    ]

    GROUND_PIN_PATTERNS = [
        "GND",
        "VSS",
        "AGND",
        "DGND",
        "PGND",
        "0V",
    ]

    CLOCK_PIN_PATTERNS = [
        "CLK",
        "CLOCK",
        "XTAL1",
        "XTAL2",
        "OSC_IN",
        "OSC_OUT",
    ]

    def __init__(
        self,
        power_patterns: Optional[list[str]] = None,
        ground_patterns: Optional[list[str]] = None,
        clock_patterns: Optional[list[str]] = None,
        high_speed_patterns: Optional[list[str]] = None,
        high_current_patterns: Optional[list[str]] = None,
    ):
        """Initialize the detector with optional custom patterns.

        Args:
            power_patterns: Custom regex patterns for power nets.
            ground_patterns: Custom regex patterns for ground nets.
            clock_patterns: Custom regex patterns for clock nets.
            high_speed_patterns: Custom regex patterns for high-speed buses.
            high_current_patterns: Custom regex patterns for high-current nets.
        """
        import re

        self._power_patterns = [re.compile(p) for p in (power_patterns or self.POWER_PATTERNS)]
        self._ground_patterns = [re.compile(p) for p in (ground_patterns or self.GROUND_PATTERNS)]
        self._clock_patterns = [re.compile(p) for p in (clock_patterns or self.CLOCK_PATTERNS)]
        self._high_speed_patterns = [
            re.compile(p) for p in (high_speed_patterns or self.HIGH_SPEED_PATTERNS)
        ]
        self._high_current_patterns = [
            re.compile(p) for p in (high_current_patterns or self.HIGH_CURRENT_PATTERNS)
        ]

    def _matches_any_pattern(self, name: str, patterns: list) -> bool:
        """Check if a name matches any of the given patterns."""
        for pattern in patterns:
            if pattern.match(name):
                return True
        return False

    def _matches_any_pin_pattern(self, pin_name: str, pin_patterns: list[str]) -> bool:
        """Check if a pin name matches any of the given patterns (substring match)."""
        pin_upper = pin_name.upper()
        for pattern in pin_patterns:
            if pattern.upper() in pin_upper:
                return True
        return False

    def _categorize_net_by_name(self, net_name: str) -> Optional[CriticalNetCategory]:
        """Determine critical net category based on name patterns."""
        if self._matches_any_pattern(net_name, self._power_patterns):
            return CriticalNetCategory.POWER
        if self._matches_any_pattern(net_name, self._ground_patterns):
            return CriticalNetCategory.GROUND
        if self._matches_any_pattern(net_name, self._clock_patterns):
            return CriticalNetCategory.CLOCK
        if self._matches_any_pattern(net_name, self._high_speed_patterns):
            return CriticalNetCategory.HIGH_SPEED
        if self._matches_any_pattern(net_name, self._high_current_patterns):
            return CriticalNetCategory.HIGH_CURRENT
        return None

    def _categorize_net_by_connectivity(
        self, net: Net, netlist: Netlist
    ) -> Optional[CriticalNetCategory]:
        """Determine critical net category based on connectivity patterns."""
        has_power_pin = False
        has_ground_pin = False
        has_clock_pin = False

        for component_ref, pin_name in net.pins:
            if self._matches_any_pin_pattern(pin_name, self.POWER_PIN_PATTERNS):
                has_power_pin = True
            if self._matches_any_pin_pattern(pin_name, self.GROUND_PIN_PATTERNS):
                has_ground_pin = True
            if self._matches_any_pin_pattern(pin_name, self.CLOCK_PIN_PATTERNS):
                has_clock_pin = True

        if has_power_pin and not has_ground_pin:
            return CriticalNetCategory.POWER
        if has_ground_pin and not has_power_pin:
            return CriticalNetCategory.GROUND
        if has_clock_pin:
            return CriticalNetCategory.CLOCK

        return None

    def _identify_power_sources_and_loads(
        self, net: Net, netlist: Netlist
    ) -> tuple[list[str], list[str]]:
        """Identify power sources (regulators) and loads for a power net."""
        sources = []
        loads = []

        power_source_footprints = [
            "LDO",
            "DC-DC",
            "BUCK",
            "BOOST",
            "REGULATOR",
            "AMS1117",
            "LM7805",
            "TPS",
            "RTQ",
            "LMR",
        ]

        for component in netlist.components:
            for pin in component.pins:
                if pin.net == net.name:
                    footprint_upper = component.footprint.upper()
                    if any(ps in footprint_upper for ps in power_source_footprints):
                        if self._matches_any_pin_pattern(pin.name, ["OUT", "VOUT", "SW"]):
                            if component.ref not in sources:
                                sources.append(component.ref)
                    else:
                        if component.ref not in loads:
                            loads.append(component.ref)

        return sources, loads

    def detect_critical_nets(self, netlist: Netlist) -> CriticalNetDetectionResult:
        """Identify all critical nets in the netlist.

        This method analyzes all nets in the netlist and identifies which
        ones are critical based on naming patterns and connectivity.

        Args:
            netlist: Netlist containing all components and nets.

        Returns:
            CriticalNetDetectionResult with categorized critical nets.

        Example:
            >>> result = detector.detect_critical_nets(netlist)
            >>> result.power_nets
            ['VCC', '+3.3V', '+5V']
            >>> result.clock_nets
            ['SPI_CLK', 'SPI_MOSI', 'SPI_MISO']
        """
        critical_nets: dict[str, CriticalNet] = {}
        power_nets: list[str] = []
        ground_nets: list[str] = []
        clock_nets: list[str] = []
        high_speed_nets: list[str] = []
        high_current_nets: list[str] = []

        for net in netlist.nets:
            if len(net.pins) < 2:
                continue

            category = self._categorize_net_by_name(net.name)
            if category is None:
                category = self._categorize_net_by_connectivity(net, netlist)

            if category is not None:
                sources: list[str] = []
                loads: list[str] = []

                if category == CriticalNetCategory.POWER:
                    sources, loads = self._identify_power_sources_and_loads(net, netlist)

                critical_net = CriticalNet(
                    name=net.name,
                    category=category,
                    pin_count=len(net.pins),
                    sources=sources,
                    loads=loads,
                )
                critical_nets[net.name] = critical_net

                if category == CriticalNetCategory.POWER:
                    power_nets.append(net.name)
                elif category == CriticalNetCategory.GROUND:
                    ground_nets.append(net.name)
                elif category == CriticalNetCategory.CLOCK:
                    clock_nets.append(net.name)
                elif category == CriticalNetCategory.HIGH_SPEED:
                    high_speed_nets.append(net.name)
                elif category == CriticalNetCategory.HIGH_CURRENT:
                    high_current_nets.append(net.name)

        return CriticalNetDetectionResult(
            critical_nets=critical_nets,
            power_nets=power_nets,
            ground_nets=ground_nets,
            clock_nets=clock_nets,
            high_speed_nets=high_speed_nets,
            high_current_nets=high_current_nets,
        )

    def is_critical(self, net_name: str, result: CriticalNetDetectionResult) -> bool:
        """Check if a specific net is critical.

        Args:
            net_name: Name of the net to check.
            result: Detection result from detect_critical_nets.

        Returns:
            True if the net is critical.
        """
        return net_name in result.critical_nets

    def get_category(
        self, net_name: str, result: CriticalNetDetectionResult
    ) -> Optional[CriticalNetCategory]:
        """Get the category of a specific net.

        Args:
            net_name: Name of the net to check.
            result: Detection result from detect_critical_nets.

        Returns:
            CriticalNetCategory if critical, None otherwise.
        """
        if net_name in result.critical_nets:
            return result.critical_nets[net_name].category
        return None
