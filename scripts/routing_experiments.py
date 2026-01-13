#!/usr/bin/env python3.11
"""
Routing Experiment Framework

Validates routing improvements on isolated subproblems before running full benchmarks.
Each experiment is a minimal test case extracted from real failing scenarios.

Usage:
    python scripts/routing_experiments.py                    # Run all experiments
    python scripts/routing_experiments.py --experiment spi   # Run specific experiment
    python scripts/routing_experiments.py --list             # List available experiments
"""

import argparse
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Callable
import json

sys.path.insert(0, str(Path(__file__).parent.parent / "packages" / "temper-placer" / "src"))

from temper_placer.deterministic.stages.clearance_grid import ClearanceGrid
from temper_placer.deterministic.stages.astar import DeterministicAStar
from temper_placer.deterministic.stages.multilayer_astar import MultiLayerAStar


@dataclass
class RoutingTarget:
    """A single routing target (pin-to-pin connection)."""

    name: str
    start: Tuple[float, float]
    end: Tuple[float, float]
    start_layer: int = 0
    end_layer: int = -1  # -1 = any layer OK
    net_class: str = "Signal"


@dataclass
class Obstacle:
    """An obstacle (pad, via, existing trace)."""

    center: Tuple[float, float]
    radius: float
    clearance: float = 0.2
    layers: List[int] = field(default_factory=lambda: [0, 1, 2, 3])
    net_name: str = ""  # Empty = blocks all nets


@dataclass
class ExperimentResult:
    """Result of running one routing target."""

    target_name: str
    success: bool
    method: str  # "single_layer", "multi_layer", "failed"
    iterations: int
    iteration_limit: int
    timeout: bool
    elapsed_ms: float
    via_count: int = 0
    path_length_mm: float = 0.0


@dataclass
class Experiment:
    """A complete routing experiment with setup and targets."""

    name: str
    description: str
    board_width: float  # mm
    board_height: float  # mm
    cell_size: float = 0.5  # mm
    layer_count: int = 4

    obstacles: List[Obstacle] = field(default_factory=list)
    targets: List[RoutingTarget] = field(default_factory=list)

    # Expected outcomes (for regression testing)
    expected_success_rate: float = 1.0  # Target success rate

    def create_grid(self) -> ClearanceGrid:
        """Create grid and populate with obstacles."""
        grid = ClearanceGrid(
            width_mm=self.board_width,
            height_mm=self.board_height,
            cell_size_mm=self.cell_size,
            layer_count=self.layer_count,
        )

        for obs in self.obstacles:
            for layer in obs.layers:
                grid.block_circle(
                    center=obs.center,
                    radius_mm=obs.radius,
                    clearance_mm=obs.clearance,
                    layer=layer,
                    net_name=obs.net_name,
                )

        return grid

    def run(self, verbose: bool = True) -> List[ExperimentResult]:
        """Run all routing targets and collect results."""
        grid = self.create_grid()
        results = []

        if verbose:
            print(f"\n{'=' * 60}")
            print(f"EXPERIMENT: {self.name}")
            print(f"{'=' * 60}")
            print(f"Description: {self.description}")
            print(f"Board: {self.board_width}x{self.board_height}mm, {self.layer_count} layers")
            print(f"Obstacles: {len(self.obstacles)}, Targets: {len(self.targets)}")
            print(
                f"\n{'Target':<20} {'Result':<10} {'Method':<12} {'Iters':<8} {'Vias':<6} {'Time'}"
            )
            print("-" * 70)

        for target in self.targets:
            result = self._route_target(grid, target)
            results.append(result)

            if verbose:
                status = "✓ PASS" if result.success else "✗ FAIL"
                print(
                    f"{target.name:<20} {status:<10} {result.method:<12} "
                    f"{result.iterations:<8} {result.via_count:<6} {result.elapsed_ms:.1f}ms"
                )

        # Summary
        successes = sum(1 for r in results if r.success)
        success_rate = successes / len(results) if results else 0

        if verbose:
            print("-" * 70)
            print(f"Success: {successes}/{len(results)} ({success_rate:.0%})")
            print(f"Expected: {self.expected_success_rate:.0%}")

            if success_rate >= self.expected_success_rate:
                print("Status: ✓ PASS")
            else:
                print("Status: ✗ FAIL (below expected)")

        return results

    def _route_target(self, grid: ClearanceGrid, target: RoutingTarget) -> ExperimentResult:
        """Route a single target using single-layer then multi-layer fallback."""

        # Try single-layer first
        pathfinder = DeterministicAStar(grid=grid, net_name=target.name, trace_width=0.25)

        t0 = time.time()
        path = pathfinder.find_path(start=target.start, end=target.end, layer=target.start_layer)
        elapsed = (time.time() - t0) * 1000

        if path:
            return ExperimentResult(
                target_name=target.name,
                success=True,
                method="single_layer",
                iterations=pathfinder.last_iterations,
                iteration_limit=pathfinder.last_iteration_limit,
                timeout=pathfinder.last_timeout,
                elapsed_ms=elapsed,
                path_length_mm=self._path_length(path),
            )

        single_iters = pathfinder.last_iterations
        single_timeout = pathfinder.last_timeout

        # Try multi-layer
        ml_pathfinder = MultiLayerAStar(
            grid=grid,
            net_name=target.name,
            trace_width=0.25,
            allowed_layers=list(range(self.layer_count)),
        )

        t0 = time.time()
        ml_path = ml_pathfinder.find_path(
            start=target.start,
            end=target.end,
            start_layer=target.start_layer,
            end_layer=target.end_layer,
        )
        elapsed += (time.time() - t0) * 1000

        if ml_path:
            return ExperimentResult(
                target_name=target.name,
                success=True,
                method="multi_layer",
                iterations=single_iters + ml_pathfinder.last_iterations,
                iteration_limit=ml_pathfinder.last_iteration_limit,
                timeout=False,
                elapsed_ms=elapsed,
                via_count=len(ml_path.via_positions),
                path_length_mm=sum(self._segment_length(s.start, s.end) for s in ml_path.segments),
            )

        # Failed
        return ExperimentResult(
            target_name=target.name,
            success=False,
            method="failed",
            iterations=single_iters + ml_pathfinder.last_iterations,
            iteration_limit=ml_pathfinder.last_iteration_limit,
            timeout=single_timeout or ml_pathfinder.last_timeout,
            elapsed_ms=elapsed,
        )

    def _path_length(self, path: List[Tuple[float, float]]) -> float:
        """Calculate path length in mm."""
        length = 0.0
        for i in range(len(path) - 1):
            length += self._segment_length(path[i], path[i + 1])
        return length

    def _segment_length(self, p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
        """Calculate segment length."""
        return ((p2[0] - p1[0]) ** 2 + (p2[1] - p1[1]) ** 2) ** 0.5


# ============================================================================
# EXPERIMENT DEFINITIONS
# ============================================================================


def create_spi_escape_experiment() -> Experiment:
    """
    SPI Escape Problem: Route signals out of a dense QFN pin field.

    This simulates the MCU SPI pins surrounded by other signals.
    The challenge is escaping the pin field without crossing other pads.
    """
    # QFN-like pin arrangement: 0.5mm pitch, 0.3mm pad
    pin_pitch = 0.5
    pad_radius = 0.15

    # Create a row of 8 pins (simulating one side of QFN)
    obstacles = []
    pin_positions = []

    for i in range(8):
        x = 10 + i * pin_pitch
        y = 10
        pin_positions.append((x, y))

        # Block all pins except the ones we want to route
        if i not in [2, 5]:  # Leave pins 2 and 5 as our routing targets
            obstacles.append(
                Obstacle(
                    center=(x, y),
                    radius=pad_radius,
                    clearance=0.15,  # Tight clearance
                    layers=[0, 3],  # Outer layers only
                )
            )

    # Target device pin (temperature sensor) - 5mm away
    target_pin = (10 + 2 * pin_pitch, 15)

    return Experiment(
        name="spi_escape",
        description="Route SPI signal out of dense QFN pin field",
        board_width=20,
        board_height=20,
        obstacles=obstacles,
        targets=[
            RoutingTarget(
                name="SPI_CS",
                start=pin_positions[2],  # MCU pin
                end=target_pin,  # Sensor pin
                net_class="SPI",
            )
        ],
        expected_success_rate=1.0,
    )


def create_channel_routing_experiment() -> Experiment:
    """
    Channel Routing: Route through a narrow gap between components.

    Tests whether the router can find paths through constrained channels.
    """
    # Two large components with a gap between them
    obstacles = []

    # Component 1: 5x5mm at (5, 10)
    for dx in range(0, 10, 2):
        for dy in range(0, 10, 2):
            obstacles.append(Obstacle(center=(5 + dx / 2, 10 + dy / 2), radius=0.4, clearance=0.2))

    # Component 2: 5x5mm at (15, 10) - leaves 5mm gap
    for dx in range(0, 10, 2):
        for dy in range(0, 10, 2):
            obstacles.append(Obstacle(center=(15 + dx / 2, 10 + dy / 2), radius=0.4, clearance=0.2))

    return Experiment(
        name="channel_routing",
        description="Route through narrow channel between two components",
        board_width=25,
        board_height=25,
        obstacles=obstacles,
        targets=[
            RoutingTarget(
                name="SIGNAL_A",
                start=(12.5, 5),  # Below the gap
                end=(12.5, 20),  # Above the gap
                net_class="Signal",
            ),
            RoutingTarget(name="SIGNAL_B", start=(11.5, 5), end=(13.5, 20), net_class="Signal"),
        ],
        expected_success_rate=1.0,
    )


def create_layer_transition_experiment() -> Experiment:
    """
    Layer Transition: Force routing to use vias to reach destination.

    Tests multi-layer routing when direct path is blocked on starting layer.
    """
    obstacles = []

    # Wall blocking layer 0 (top)
    for y in range(5, 20):
        obstacles.append(
            Obstacle(
                center=(12, y),
                radius=0.5,
                clearance=0.2,
                layers=[0],  # Only blocks top layer
            )
        )

    return Experiment(
        name="layer_transition",
        description="Force layer change via blocked top layer",
        board_width=25,
        board_height=25,
        layer_count=4,
        obstacles=obstacles,
        targets=[
            RoutingTarget(
                name="CROSS_LAYER",
                start=(5, 12),
                end=(20, 12),
                start_layer=0,
                end_layer=0,  # Must return to layer 0
            )
        ],
        expected_success_rate=1.0,
    )


def create_dense_bga_experiment() -> Experiment:
    """
    Dense BGA Escape: Route out of a BGA-like pin array.

    This is one of the hardest routing problems - escaping from
    inner pins of a dense array.
    """
    obstacles = []
    pin_positions = {}

    # 6x6 BGA with 1mm pitch
    pitch = 1.0
    pad_radius = 0.25

    for row in range(6):
        for col in range(6):
            x = 10 + col * pitch
            y = 10 + row * pitch
            pin_name = f"P{row}{col}"
            pin_positions[pin_name] = (x, y)

            # Block all except corners and center
            if (row, col) not in [(0, 0), (5, 5), (2, 2), (3, 3)]:
                obstacles.append(
                    Obstacle(center=(x, y), radius=pad_radius, clearance=0.15, layers=[0, 3])
                )

    return Experiment(
        name="dense_bga",
        description="Escape routing from inner BGA pins",
        board_width=25,
        board_height=25,
        obstacles=obstacles,
        targets=[
            # Easy: corner to edge
            RoutingTarget(
                name="CORNER_ESCAPE", start=pin_positions["P00"], end=(5, 5), net_class="Signal"
            ),
            # Hard: center pin to edge
            RoutingTarget(
                name="CENTER_ESCAPE", start=pin_positions["P22"], end=(5, 12), net_class="Signal"
            ),
        ],
        expected_success_rate=1.0,  # Both pass with multi-layer routing
    )


def create_clearance_test_experiment() -> Experiment:
    """
    Clearance Sensitivity: Test routing with different clearance rules.

    Creates a scenario where only tight clearances allow routing.
    """
    obstacles = []

    # Create a pinch point - two pads with just barely enough room
    # At 0.2mm clearance, 0.25mm trace needs 0.65mm gap
    # We'll create 0.7mm gap (should pass) and 0.5mm gap (should fail)

    # Wide gap (should pass)
    obstacles.append(Obstacle(center=(10, 10), radius=0.3, clearance=0.2))
    obstacles.append(
        Obstacle(center=(10, 10.8), radius=0.3, clearance=0.2)
    )  # 0.8mm center-to-center = 0.2mm gap

    # Narrow gap (should fail with standard clearance)
    obstacles.append(Obstacle(center=(15, 10), radius=0.3, clearance=0.2))
    obstacles.append(
        Obstacle(center=(15, 10.55), radius=0.3, clearance=0.2)
    )  # 0.55mm c-to-c = very tight

    return Experiment(
        name="clearance_test",
        description="Test routing through gaps with different clearances",
        board_width=25,
        board_height=20,
        obstacles=obstacles,
        targets=[
            RoutingTarget(name="WIDE_GAP", start=(5, 10.4), end=(12, 10.4), net_class="Signal"),
            RoutingTarget(name="NARROW_GAP", start=(12, 10.3), end=(20, 10.3), net_class="Signal"),
        ],
        expected_success_rate=1.0,  # Both pass with current clearances
    )


def create_realistic_spi_experiment() -> Experiment:
    """
    Realistic SPI Routing: Uses ALL actual pad positions from temper.kicad_pcb

    Extracted from actual board - ALL 44 pads in the routing area.
    This reproduces the real routing challenge.

    Key components in the path:
    - U_MCU at (80, 100): SPI pins at (77.6-78.8, 96.55)
    - C_MCU_1/2/3 at (72.5-73.5, 97/100/103): blocking left escape
    - U_OPAMP_CT at (40, 120): SOIC-8 in the middle
    - U_CT at (30, 110): Another SPI device sharing the bus
    - R_BURDEN at (30, 120): resistor
    - C_CT_FILT at (30, 125): filter cap
    - MAX31865 at (30, 135): destination
    """
    obstacles = []
    spi_nets = {"SPI_CLK", "SPI_MOSI", "SPI_MISO", "SPI_CS_TEMP"}

    # ALL 44 pads in routing area from actual board extraction
    all_pads = [
        # U_CT (SPI device at x=27-33, y=107-113)
        ((27.10, 107.08), "SPI_CLK", 0.15),
        ((27.10, 107.72), "SPI_MOSI", 0.15),
        ((27.10, 108.38), "SPI_MISO", 0.15),
        ((27.10, 109.03), "SPI_CS_TEMP", 0.15),
        ((27.10, 112.92), "GND", 0.15),
        ((32.90, 107.08), "+3V3", 0.15),
        # MAX31865 (destination at x=27-33, y=132-138)
        ((27.10, 132.07), "SPI_CLK", 0.15),
        ((27.10, 132.72), "SPI_MOSI", 0.15),
        ((27.10, 133.38), "SPI_MISO", 0.15),
        ((27.10, 134.03), "TEMP_SENSE", 0.15),
        ((27.10, 137.93), "GND", 0.15),
        ((32.90, 132.07), "+3V3", 0.15),
        # R_BURDEN (resistor at y=120)
        ((29.00, 120.00), "I_SENSE", 0.3),
        ((31.00, 120.00), "GND", 0.3),
        # C_CT_FILT (cap at y=125)
        ((29.18, 125.00), "I_SENSE", 0.25),
        ((30.82, 125.00), "GND", 0.25),
        # U_OPAMP_CT (SOIC-8 at x=37-43, y=118-122)
        ((37.52, 118.09), "I_SENSE", 0.25),
        ((37.52, 119.36), "I_SENSE", 0.25),
        ((37.52, 120.64), "I_SENSE", 0.25),
        ((37.52, 121.91), "GND", 0.25),
        ((42.48, 118.09), "+5V", 0.25),
        ((42.48, 119.36), "+5V", 0.25),
        ((42.48, 120.64), "I_SENSE", 0.25),
        ((42.48, 121.91), "I_SENSE", 0.25),
        # C_MCU_1/2/3 (decoupling caps blocking left escape)
        ((72.50, 97.00), "+3V3", 0.25),
        ((73.50, 97.00), "GND", 0.25),
        ((72.50, 100.00), "+3V3", 0.25),
        ((73.50, 100.00), "GND", 0.25),
        ((72.50, 103.00), "+3V3", 0.25),
        ((73.50, 103.00), "GND", 0.25),
        # U_MCU pads
        ((76.55, 97.60), "I_SENSE", 0.12),
        ((76.55, 98.00), "PWM_L", 0.12),
        ((76.55, 98.40), "PWM_H", 0.12),
        ((76.55, 102.40), "GND", 0.12),
        ((76.55, 102.80), "+3V3", 0.12),
        ((77.60, 96.55), "SPI_CLK", 0.12),  # Start point
        ((78.00, 96.55), "SPI_MOSI", 0.12),  # Start point
        ((78.40, 96.55), "SPI_MISO", 0.12),  # Start point
        ((78.80, 96.55), "SPI_CS_TEMP", 0.12),  # Start point
        ((80.00, 100.00), "GND", 1.5),  # Thermal pad - big!
        ((83.45, 100.00), "USB_D+", 0.12),
        ((83.45, 100.40), "USB_D-", 0.12),
        # C_MCU_4
        ((86.50, 100.00), "+3V3", 0.25),
        ((87.50, 100.00), "GND", 0.25),
    ]

    # Add all pads as obstacles (except SPI endpoints which we route TO)
    # Note: U_CT.1-4 and MAX31865.1-3 are on the same SPI bus, so we should
    # NOT block them for their own nets
    for pos, net, radius in all_pads:
        # Skip SPI start/end points (they're routing targets, not obstacles)
        # Start: U_MCU.20-23 at (77.6-78.8, 96.55)
        # End: MAX31865.1-3 at (27.1, 132-134)
        is_start = abs(pos[1] - 96.55) < 0.1 and 77 < pos[0] < 79
        is_end = abs(pos[0] - 27.10) < 0.1 and 132 < pos[1] < 134.5 and net in spi_nets

        if not is_start and not is_end:
            # Determine clearance based on pad type
            clearance = 0.15 if radius <= 0.15 else 0.2

            obstacles.append(
                Obstacle(
                    center=pos,
                    radius=radius,
                    clearance=clearance,
                    layers=[0, 3],  # Outer layers
                    net_name=net,
                )
            )

    # SPI routing targets: MCU pin -> MAX31865 pin
    targets = [
        RoutingTarget(
            name="SPI_CLK",
            start=(77.60, 96.55),
            end=(27.10, 132.07),
            start_layer=0,
            end_layer=-1,
            net_class="SPI",
        ),
        RoutingTarget(
            name="SPI_MOSI",
            start=(78.00, 96.55),
            end=(27.10, 132.72),
            start_layer=0,
            end_layer=-1,
            net_class="SPI",
        ),
        RoutingTarget(
            name="SPI_MISO",
            start=(78.40, 96.55),
            end=(27.10, 133.38),
            start_layer=0,
            end_layer=-1,
            net_class="SPI",
        ),
        RoutingTarget(
            name="SPI_CS",
            start=(78.80, 96.55),
            end=(27.10, 134.03),  # Note: goes to TEMP_SENSE pad position (wrong net name in board?)
            start_layer=0,
            end_layer=-1,
            net_class="SPI",
        ),
    ]

    return Experiment(
        name="realistic_spi",
        description="Real SPI routing from U_MCU to MAX31865 (ALL 44 pads)",
        board_width=100,
        board_height=150,
        cell_size=0.25,  # Fine grid for tight clearances
        layer_count=4,
        obstacles=obstacles,
        targets=targets,
        expected_success_rate=1.0,  # All should pass with blocked-layer heuristic fix
    )


def create_mcu_escape_experiment() -> Experiment:
    """
    MCU Escape Problem: Can we even get out of the MCU pin area?

    Tests just the escape routing from MCU to a nearby point,
    without the full path to MAX31865.
    """
    obstacles = []

    # U_MCU pads
    mcu_pads = [
        ((76.550, 102.800), "+3V3"),
        ((76.550, 102.400), "GND"),
        ((76.550, 98.400), "PWM_H"),
        ((76.550, 98.000), "PWM_L"),
        ((76.550, 97.600), "I_SENSE"),
        ((77.600, 96.550), "SPI_CLK"),
        ((78.000, 96.550), "SPI_MOSI"),
        ((78.400, 96.550), "SPI_MISO"),
        ((78.800, 96.550), "SPI_CS_TEMP"),
        ((83.450, 100.000), "USB_D+"),
        ((83.450, 100.400), "USB_D-"),
        ((80.000, 100.000), "GND"),
    ]

    spi_nets = {"SPI_CLK", "SPI_MOSI", "SPI_MISO", "SPI_CS_TEMP"}
    for pos, net in mcu_pads:
        if net not in spi_nets:
            obstacles.append(
                Obstacle(
                    center=pos,
                    radius=0.12,
                    clearance=0.15,
                    layers=[0, 3],
                    net_name=net,
                )
            )

    # Decoupling caps
    cap_positions = [
        ((72.500, 97.000), "+3V3"),
        ((73.500, 97.000), "GND"),
        ((72.500, 100.000), "+3V3"),
        ((73.500, 100.000), "GND"),
        ((72.500, 103.000), "+3V3"),
        ((73.500, 103.000), "GND"),
    ]
    for pos, net in cap_positions:
        obstacles.append(
            Obstacle(
                center=pos,
                radius=0.25,
                clearance=0.2,
                layers=[0, 3],
                net_name=net,
            )
        )

    # Target: escape to a point 10mm south (below the MCU)
    targets = [
        RoutingTarget(
            name="SPI_CLK_escape",
            start=(77.600, 96.550),
            end=(77.600, 90.000),  # 6.5mm south
            start_layer=0,
            net_class="SPI",
        ),
        RoutingTarget(
            name="SPI_CS_escape",
            start=(78.800, 96.550),
            end=(78.800, 90.000),
            start_layer=0,
            net_class="SPI",
        ),
    ]

    return Experiment(
        name="mcu_escape",
        description="Escape SPI from MCU to 6.5mm south (should be easy)",
        board_width=100,
        board_height=150,
        cell_size=0.25,
        layer_count=4,
        obstacles=obstacles,
        targets=targets,
        expected_success_rate=1.0,  # This should pass - it's just escape
    )


def create_constrained_channel_experiment() -> Experiment:
    """
    Constrained Channel: Route between decoupling caps and MCU.

    The real failure mode is routing through the narrow gap between
    C_MCU caps at x=72.5-73.5 and MCU pins at x=76.55.
    Gap is ~3mm but with clearances it's very tight.
    """
    obstacles = []

    # MCU left-side pins
    obstacles.append(Obstacle(center=(76.550, 97.600), radius=0.12, clearance=0.15, layers=[0, 3]))
    obstacles.append(Obstacle(center=(76.550, 98.000), radius=0.12, clearance=0.15, layers=[0, 3]))
    obstacles.append(Obstacle(center=(76.550, 98.400), radius=0.12, clearance=0.15, layers=[0, 3]))

    # Decoupling caps (narrowest gap)
    obstacles.append(Obstacle(center=(73.500, 97.000), radius=0.25, clearance=0.2, layers=[0, 3]))
    obstacles.append(Obstacle(center=(73.500, 100.000), radius=0.25, clearance=0.2, layers=[0, 3]))
    obstacles.append(Obstacle(center=(73.500, 103.000), radius=0.25, clearance=0.2, layers=[0, 3]))

    # Inner caps
    obstacles.append(Obstacle(center=(72.500, 97.000), radius=0.25, clearance=0.2, layers=[0, 3]))
    obstacles.append(Obstacle(center=(72.500, 100.000), radius=0.25, clearance=0.2, layers=[0, 3]))
    obstacles.append(Obstacle(center=(72.500, 103.000), radius=0.25, clearance=0.2, layers=[0, 3]))

    # Try to route through the gap
    targets = [
        RoutingTarget(
            name="through_gap_97",
            start=(78.000, 97.000),
            end=(70.000, 97.000),
            start_layer=0,
            net_class="Signal",
        ),
        RoutingTarget(
            name="through_gap_100",
            start=(78.000, 100.000),
            end=(70.000, 100.000),
            start_layer=0,
            net_class="Signal",
        ),
        RoutingTarget(
            name="through_gap_103",
            start=(78.000, 103.000),
            end=(70.000, 103.000),
            start_layer=0,
            net_class="Signal",
        ),
    ]

    return Experiment(
        name="constrained_channel",
        description="Route through gap between caps and MCU (real bottleneck)",
        board_width=100,
        board_height=150,
        cell_size=0.25,
        layer_count=4,
        obstacles=obstacles,
        targets=targets,
        expected_success_rate=1.0,  # All pass - gap is wide enough
    )


# Registry of all experiments
EXPERIMENTS: Dict[str, Callable[[], Experiment]] = {
    "spi_escape": create_spi_escape_experiment,
    "channel_routing": create_channel_routing_experiment,
    "layer_transition": create_layer_transition_experiment,
    "dense_bga": create_dense_bga_experiment,
    "clearance_test": create_clearance_test_experiment,
    "realistic_spi": create_realistic_spi_experiment,
    "mcu_escape": create_mcu_escape_experiment,
    "constrained_channel": create_constrained_channel_experiment,
}


def run_all_experiments(verbose: bool = True) -> Dict[str, List[ExperimentResult]]:
    """Run all experiments and return results."""
    all_results = {}

    for name, factory in EXPERIMENTS.items():
        exp = factory()
        results = exp.run(verbose=verbose)
        all_results[name] = results

    return all_results


def summarize_results(all_results: Dict[str, List[ExperimentResult]]) -> None:
    """Print summary of all experiment results."""
    print("\n" + "=" * 60)
    print("EXPERIMENT SUMMARY")
    print("=" * 60)

    total_targets = 0
    total_passed = 0
    experiments_passed = 0

    for name, results in all_results.items():
        passed = sum(1 for r in results if r.success)
        total = len(results)
        total_targets += total
        total_passed += passed

        exp = EXPERIMENTS[name]()
        expected = exp.expected_success_rate
        actual = passed / total if total else 0

        status = "✓" if actual >= expected else "✗"
        if actual >= expected:
            experiments_passed += 1

        print(f"{status} {name}: {passed}/{total} ({actual:.0%}) [expected {expected:.0%}]")

    print("-" * 60)
    print(f"Total: {total_passed}/{total_targets} targets passed")
    print(f"Experiments: {experiments_passed}/{len(all_results)} passed")


def main():
    parser = argparse.ArgumentParser(description="Run routing experiments")
    parser.add_argument("--experiment", "-e", help="Run specific experiment")
    parser.add_argument("--list", "-l", action="store_true", help="List available experiments")
    parser.add_argument("--quiet", "-q", action="store_true", help="Minimal output")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")

    args = parser.parse_args()

    if args.list:
        print("Available experiments:")
        for name, factory in EXPERIMENTS.items():
            exp = factory()
            print(f"  {name}: {exp.description}")
        return 0

    if args.experiment:
        if args.experiment not in EXPERIMENTS:
            print(f"Unknown experiment: {args.experiment}")
            print(f"Available: {', '.join(EXPERIMENTS.keys())}")
            return 1

        exp = EXPERIMENTS[args.experiment]()
        results = exp.run(verbose=not args.quiet)

        if args.json:
            print(json.dumps([r.__dict__ for r in results], indent=2))
    else:
        all_results = run_all_experiments(verbose=not args.quiet)
        summarize_results(all_results)

        if args.json:
            json_results = {
                name: [r.__dict__ for r in results] for name, results in all_results.items()
            }
            print(json.dumps(json_results, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
