"""Shared pytest fixtures for temper-drc tests."""

from pathlib import Path

import pytest

from temper_drc.input.constraints import (
    ClearanceRule,
    ConstraintSet,
    LoopConstraint,
    ZoneDefinition,
)
from temper_drc.input.placement import ComponentPlacement, Placement


@pytest.fixture
def fixtures_dir() -> Path:
    """Path to test fixtures directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def simple_placement() -> Placement:
    """Minimal valid placement for basic testing."""
    return Placement(
        components={
            "U1": ComponentPlacement(
                ref="U1",
                footprint="SOT-223",
                x=25.0,
                y=25.0,
                rotation=0.0,
                layer="F.Cu",
                width=6.5,
                height=7.0,
                net_class="Signal",
            ),
            "U2": ComponentPlacement(
                ref="U2",
                footprint="SOT-223",
                x=50.0,
                y=25.0,
                rotation=0.0,
                layer="F.Cu",
                width=6.5,
                height=7.0,
                net_class="Signal",
            ),
        },
        nets={
            "VCC": ["U1", "U2"],
            "GND": ["U1", "U2"],
        },
        zones={
            "ZONE_A": (0.0, 0.0, 50.0, 50.0),
            "ZONE_B": (50.0, 0.0, 100.0, 50.0),
        },
        board_width=100.0,
        board_height=100.0,
    )


@pytest.fixture
def half_bridge_placement() -> Placement:
    """Realistic half-bridge topology for integration testing."""
    return Placement(
        components={
            "Q1": ComponentPlacement(
                ref="Q1",
                footprint="TO-247",
                x=20.0,
                y=30.0,
                rotation=0.0,
                layer="F.Cu",
                width=15.0,
                height=20.0,
                net_class="HighVoltage",
                voltage_domain="HV",
            ),
            "Q2": ComponentPlacement(
                ref="Q2",
                footprint="TO-247",
                x=20.0,
                y=60.0,
                rotation=0.0,
                layer="F.Cu",
                width=15.0,
                height=20.0,
                net_class="HighVoltage",
                voltage_domain="HV",
            ),
            "U_GATE": ComponentPlacement(
                ref="U_GATE",
                footprint="SOIC-16",
                x=45.0,
                y=45.0,
                rotation=0.0,
                layer="F.Cu",
                width=10.0,
                height=6.0,
                net_class="Signal",
                voltage_domain="LV",
            ),
            "U_MCU": ComponentPlacement(
                ref="U_MCU",
                footprint="QFN-48",
                x=75.0,
                y=75.0,
                rotation=0.0,
                layer="F.Cu",
                width=7.0,
                height=7.0,
                net_class="Signal",
                voltage_domain="LV",
            ),
            "C_BUS": ComponentPlacement(
                ref="C_BUS",
                footprint="CAP_ELEC_18x35",
                x=10.0,
                y=45.0,
                rotation=0.0,
                layer="F.Cu",
                width=18.0,
                height=18.0,
                net_class="HighVoltage",
                voltage_domain="HV",
            ),
        },
        nets={
            "DC_BUS+": ["Q1", "C_BUS"],
            "DC_BUS-": ["Q2", "C_BUS"],
            "SW_NODE": ["Q1", "Q2"],
            "GATE_H": ["U_GATE", "Q1"],
            "GATE_L": ["U_GATE", "Q2"],
            "VCC_3V3": ["U_MCU"],
        },
        zones={
            "HV_ZONE": (0.0, 0.0, 50.0, 80.0),
            "LV_ZONE": (50.0, 0.0, 100.0, 80.0),
            "MCU_ZONE": (50.0, 50.0, 100.0, 100.0),
        },
        board_width=100.0,
        board_height=100.0,
        net_classes={
            "DC_BUS+": "HighVoltage",
            "DC_BUS-": "HighVoltage",
            "SW_NODE": "HighVoltage",
            "GATE_H": "Signal",
            "GATE_L": "Signal",
            "VCC_3V3": "Power",
        },
        voltage_domains={
            "DC_BUS+": "HV",
            "DC_BUS-": "HV",
            "SW_NODE": "HV",
            "GATE_H": "LV",
            "GATE_L": "LV",
            "VCC_3V3": "LV",
        },
    )


@pytest.fixture
def empty_constraints() -> ConstraintSet:
    """Empty constraints for testing check behavior."""
    return ConstraintSet()


@pytest.fixture
def simple_constraints() -> ConstraintSet:
    """Minimal constraints for basic testing."""
    return ConstraintSet(
        clearances=[
            ClearanceRule(from_class="*", to_class="*", min_mm=0.5),
        ],
        zones=[
            ZoneDefinition(name="ZONE_A", bounds=(0.0, 0.0, 50.0, 50.0)),
            ZoneDefinition(name="ZONE_B", bounds=(50.0, 0.0, 100.0, 50.0)),
        ],
        board_width=100.0,
        board_height=100.0,
    )


@pytest.fixture
def temper_constraints() -> ConstraintSet:
    """Realistic constraints for Temper half-bridge topology."""
    return ConstraintSet(
        clearances=[
            ClearanceRule(
                from_class="HighVoltage",
                to_class="Signal",
                min_mm=10.0,
                description="IEC 60335 creepage requirement",
            ),
            ClearanceRule(
                from_class="HighVoltage",
                to_class="Power",
                min_mm=5.0,
                description="HV to LV power clearance",
            ),
            ClearanceRule(
                from_class="*",
                to_class="*",
                min_mm=0.3,
                description="Default clearance",
            ),
        ],
        zones=[
            ZoneDefinition(
                name="HV_ZONE",
                bounds=(0.0, 0.0, 50.0, 80.0),
                net_classes=["HighVoltage", "Power"],
                components=["Q1", "Q2", "C_BUS", "D1", "D2"],
            ),
            ZoneDefinition(
                name="LV_ZONE",
                bounds=(50.0, 0.0, 100.0, 80.0),
                net_classes=["Signal", "Power"],
            ),
            ZoneDefinition(
                name="MCU_ZONE",
                bounds=(50.0, 50.0, 100.0, 100.0),
                net_classes=["Signal"],
                components=["U_MCU"],
            ),
        ],
        critical_loops=[
            LoopConstraint(
                name="gate_drive_high",
                nets=["GATE_H", "SW_NODE", "VCC_15V"],
                max_area_mm2=100.0,
                weight=2.0,
                description="High-side gate drive loop",
            ),
            LoopConstraint(
                name="power_commutation",
                nets=["DC_BUS+", "SW_NODE", "DC_BUS-"],
                max_area_mm2=500.0,
                weight=1.5,
                description="Main power commutation loop",
            ),
        ],
        net_classes={
            "DC_BUS+": "HighVoltage",
            "DC_BUS-": "HighVoltage",
            "SW_NODE": "HighVoltage",
            "GATE_H": "Signal",
            "GATE_L": "Signal",
            "VCC_3V3": "Power",
        },
        hv_clearance_mm=10.0,
        board_width=100.0,
        board_height=100.0,
    )
