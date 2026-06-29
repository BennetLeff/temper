"""
Bus cohort routing constraints.

This module defines constraints for routing multi-signal buses (e.g., SPI, I2C, Parallel)
as a single cohort to maintain parallel paths and minimize crossings.

Classes:
    BusCohortConstraint: Constraint for routing a bus cohort.
    BusRegistry: Registry for managing bus cohorts with automatic inference.
"""

from dataclasses import dataclass


@dataclass
class BusCohortConstraint:
    """Constraint for routing a bus cohort.

    Defines requirements for routing a group of nets in parallel with
    consistent spacing.

    Attributes:
        name: Name of the bus (e.g., 'SPI_BUS')
        nets: List of net names in the cohort (ordered).
        pitch_mm: Center-to-center spacing between traces in mm.
        max_skew_mm: Maximum length mismatch within the cohort in mm.
        allow_swapping: Whether signal order can be swapped to optimize routing.
    """

    name: str
    nets: list[str]
    pitch_mm: float = 0.5
    max_skew_mm: float = 2.0
    allow_swapping: bool = False

    def __post_init__(self):
        """Validate bus cohort parameters."""
        if not self.nets:
            raise ValueError("Bus cohort must contain at least one net.")
        if self.pitch_mm <= 0:
            raise ValueError(f"pitch_mm must be positive, got {self.pitch_mm}")
        if self.max_skew_mm < 0:
            raise ValueError(f"max_skew_mm must be non-negative, got {self.max_skew_mm}")

    @property
    def signal_count(self) -> int:
        """Total number of signals in the bus."""
        return len(self.nets)


class BusRegistry:
    """Registry for managing bus cohorts with automatic inference.

    Provides registration, lookup, and automatic bus detection from netlists
    based on naming patterns.

    Attributes:
        buses: Dictionary mapping bus name to BusCohortConstraint.
        _net_to_bus: Reverse lookup from net name to bus name.
    """

    def __init__(self):
        self.buses: dict[str, BusCohortConstraint] = {}
        self._net_to_bus: dict[str, str] = {}

    def register_bus(self, bus: BusCohortConstraint) -> None:
        """Register a bus cohort.

        Args:
            bus: BusCohortConstraint to register.
        """
        self.buses[bus.name] = bus
        for net in bus.nets:
            self._net_to_bus[net] = bus.name

    def get_bus_for_net(self, net: str) -> BusCohortConstraint | None:
        """Return the bus this net belongs to, if any.

        Args:
            net: Net name to look up.

        Returns:
            BusCohortConstraint if net is part of a bus, None otherwise.
        """
        bus_name = self._net_to_bus.get(net)
        if bus_name is not None:
            return self.buses.get(bus_name)
        return None

    def infer_buses_from_nets(self, net_names: list[str]) -> list[BusCohortConstraint]:
        """Auto-detect buses from net naming patterns.

        Detects common bus patterns:
        - SPI_* → SPI bus (SPI_CLK, SPI_MOSI, SPI_MISO, SPI_CS)
        - I2C_* → I2C bus (I2C_SDA, I2C_SCL)
        - JTAG_* → JTAG bus (JTAG_TCK, JTAG_TMS, JTAG_TDI, JTAG_TDO)
        - USB_D+, USB_D- → USB differential pair
        - *_P, *_N suffix → Differential pair

        Args:
            net_names: List of net names to analyze.

        Returns:
            List of inferred BusCohortConstraints.
        """
        from collections import defaultdict

        inferred: list[BusCohortConstraint] = []

        # Group nets by prefix patterns
        spi_nets = []
        i2c_nets = []
        jtag_nets = []

        # Differential pairs grouped by base name
        diff_pairs: dict[str, list[str]] = defaultdict(list)

        for net in net_names:
            upper_net = net.upper()

            if (
                upper_net.startswith("SPI_")
                or upper_net == "SPI_CLK"
                or upper_net == "SPI_MOSI"
                or upper_net == "SPI_MISO"
                or upper_net == "SPI_CS"
            ):
                spi_nets.append(net)
            elif upper_net.startswith("I2C_") or upper_net == "I2C_SDA" or upper_net == "I2C_SCL":
                i2c_nets.append(net)
            elif upper_net.startswith("JTAG_") or upper_net in [
                "JTAG_TCK",
                "JTAG_TMS",
                "JTAG_TDI",
                "JTAG_TDO",
            ]:
                jtag_nets.append(net)

            # Differential pair detection: *_P, *_N or *_DP, *_DN
            if upper_net.endswith("_DP") or upper_net.endswith("_DN"):
                base = net[:-3]
                diff_pairs[base].append(net)
            elif upper_net.endswith("_P") and not upper_net.endswith("_DP") or upper_net.endswith("_N") and not upper_net.endswith("_DN"):
                base = net[:-2]
                diff_pairs[base].append(net)

        # Create bus cohorts from detected patterns
        if len(spi_nets) >= 2:
            spi_bus = BusCohortConstraint(
                name="SPI_BUS",
                nets=spi_nets,
                pitch_mm=0.4,
                max_skew_mm=2.0,
            )
            inferred.append(spi_bus)

        if len(i2c_nets) >= 2:
            i2c_bus = BusCohortConstraint(
                name="I2C_BUS",
                nets=i2c_nets,
                pitch_mm=0.5,
                max_skew_mm=5.0,
            )
            inferred.append(i2c_bus)

        if len(jtag_nets) >= 2:
            jtag_bus = BusCohortConstraint(
                name="JTAG_BUS",
                nets=jtag_nets,
                pitch_mm=0.4,
                max_skew_mm=1.0,
            )
            inferred.append(jtag_bus)

        # Register differential pairs
        for base, pair_nets in diff_pairs.items():
            if len(pair_nets) >= 2:
                diff_bus = BusCohortConstraint(
                    name=f"DIFF_{base}",
                    nets=pair_nets,
                    pitch_mm=0.3,
                    max_skew_mm=0.5,
                )
                inferred.append(diff_bus)

        return inferred
