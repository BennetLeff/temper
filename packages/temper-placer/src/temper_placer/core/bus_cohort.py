"""
Bus cohort routing constraints.

This module defines constraints for routing multi-signal buses (e.g., SPI, I2C, Parallel)
as a single cohort to maintain parallel paths and minimize crossings.

Classes:
    BusCohortConstraint: Constraint for routing a bus cohort.
    BusRegistry: Registry for managing bus cohorts with automatic inference.

``BusCohortConstraint`` migrated to a Rust pyclass (Wave 4, Wave C,
``temper-design-bundle``, ``bus_cohort_contracts.rs``) — this module is now a
pure-delegation shim re-exporting it (plan
``docs/plans/2026-08-08-002-feat-buscohort-pyclass-migration-plan.md``, D5).
``BusRegistry`` stays Python: it is registry state (``dict[str, ...]`` + a
reverse map) with string-prefix classification — genuinely Python glue with no
numeric kernel worth crossing the boundary.
"""

from typing import TYPE_CHECKING, Any, TypeAlias

import temper_design_bundle_python as _tdb

if TYPE_CHECKING:
    # ``temper_design_bundle_python`` is a compiled pyo3 extension with no
    # stub, so ``_tdb.bus_cohort_contracts.BusCohortConstraint`` binds a
    # *variable* of type Any and every annotation using it is "not valid as
    # a type". Aliasing to Any under TYPE_CHECKING keeps the runtime binding
    # below untouched -- same idiom as core/manufacturing.py's FabPreset and
    # core/placement_drc.py's PinInfo.
    BusCohortConstraint: TypeAlias = Any
else:
    BusCohortConstraint = _tdb.bus_cohort_contracts.BusCohortConstraint


class BusRegistry:
    """Registry for managing bus cohorts with automatic inference.

    Provides registration, lookup, and automatic bus detection from netlists
    based on naming patterns.

    Attributes:
        buses: Dictionary mapping bus name to BusCohortConstraint.
        _net_to_bus: Reverse lookup from net name to bus name.
    """

    def __init__(self) -> None:
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
            elif (
                upper_net.endswith("_P")
                and not upper_net.endswith("_DP")
                or upper_net.endswith("_N")
                and not upper_net.endswith("_DN")
            ):
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
