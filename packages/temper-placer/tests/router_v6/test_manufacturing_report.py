"""
Tests for Router V6 Stage 5.8: Generate Manufacturing Report

Part of temper-klru
"""


from temper_placer.router_v6.acid_trap_detection import AcidTrap, AcidTrapReport
from temper_placer.router_v6.annular_ring_check import AnnularRingReport, AnnularRingViolation
from temper_placer.router_v6.clearance_check import ClearanceReport
from temper_placer.router_v6.copper_balance import CopperBalanceReport, LayerCopperBalance
from temper_placer.router_v6.creepage_check import CreepageReport
from temper_placer.router_v6.manufacturing_report import (
    ManufacturingReport,
    format_manufacturing_report,
    generate_manufacturing_report,
)
from temper_placer.router_v6.teardrop_generation import Teardrop, TeardropReport
from temper_placer.router_v6.thermal_relief import ThermalRelief, ThermalReliefReport


def test_generate_empty_report():
    """Test generating report with no violations."""
    acid = AcidTrapReport(acid_traps=[])
    annular = AnnularRingReport(violations=[], total_vias_checked=0)
    teardrops = TeardropReport(teardrops=[
        Teardrop("NET1", (0, 0), "via", 0.3, 0.6, "F.Cu")
    ])
    thermal = ThermalReliefReport(thermal_reliefs=[
        ThermalRelief("GND", (0, 0), 4, 0.254, 0.254, pad_size=(0.0, 0.0), spoke_segments=[])
    ])
    copper = CopperBalanceReport(layer_balances=[], total_area_mm2=0.0)
    creepage = CreepageReport(violations=[], total_checks=0)
    clearance = ClearanceReport(violations=[], total_checks=0)

    report = generate_manufacturing_report(
        acid, annular, teardrops, thermal, copper, creepage, clearance
    )

    assert report.total_violations == 0
    assert report.is_manufacturability_ok


def test_generate_report_with_violations():
    """Test generating report with violations."""
    acid = AcidTrapReport(acid_traps=[
        AcidTrap("NET1", (0, 0), 30.0, "high")
    ])
    annular = AnnularRingReport(violations=[
        AnnularRingViolation("NET1", (5, 5), 0.4, 0.35, 0.025, 0.1)
    ], total_vias_checked=1)
    teardrops = TeardropReport(teardrops=[
        Teardrop("NET1", (0, 0), "via", 0.3, 0.6, "F.Cu")
    ])
    thermal = ThermalReliefReport(thermal_reliefs=[
        ThermalRelief("GND", (0, 0), 4, 0.254, 0.254, pad_size=(0.0, 0.0), spoke_segments=[])
    ])
    copper = CopperBalanceReport(layer_balances=[], total_area_mm2=0.0)
    creepage = CreepageReport(violations=[], total_checks=0)
    clearance = ClearanceReport(violations=[], total_checks=0)

    report = generate_manufacturing_report(
        acid, annular, teardrops, thermal, copper, creepage, clearance
    )

    # 1 acid trap + 1 annular ring = 2 total violations (teardrops/thermal present)
    assert report.total_violations == 2
    assert not report.is_manufacturability_ok


def test_manufacturing_report_dataclass():
    """Test ManufacturingReport dataclass."""
    acid = AcidTrapReport(acid_traps=[])
    annular = AnnularRingReport(violations=[], total_vias_checked=5)
    teardrops = TeardropReport(teardrops=[
        Teardrop("NET1", (5, 5), "via", 0.3, 0.6, "F.Cu")
    ])
    thermal = ThermalReliefReport(thermal_reliefs=[
        ThermalRelief("GND", (10, 10), 4, 0.254, 0.254)
    ])
    copper = CopperBalanceReport(layer_balances=[], total_area_mm2=0.0)
    creepage = CreepageReport(violations=[], total_checks=0)
    clearance = ClearanceReport(violations=[], total_checks=0)

    report = ManufacturingReport(
        acid_traps=acid,
        annular_rings=annular,
        teardrops=teardrops,
        thermal_reliefs=thermal,
        copper_balance=copper,
        creepage=creepage,
        clearance=clearance,
    )

    assert report.total_violations == 0
    assert report.teardrops.teardrop_count == 1
    assert report.thermal_reliefs.relief_count == 1


def test_critical_violations():
    """Test critical violation counting."""
    acid = AcidTrapReport(acid_traps=[
        AcidTrap("NET1", (0, 0), 30.0, "high"),  # Critical
        AcidTrap("NET2", (5, 5), 70.0, "low"),   # Not critical
    ])
    annular = AnnularRingReport(violations=[
        AnnularRingViolation("NET1", (5, 5), 0.4, 0.35, 0.025, 0.1)
    ], total_vias_checked=1)
    teardrops = TeardropReport(teardrops=[
        Teardrop("NET1", (0, 0), "via", 0.3, 0.6, "F.Cu")
    ])
    thermal = ThermalReliefReport(thermal_reliefs=[
        ThermalRelief("GND", (0, 0), 4, 0.254, 0.254, pad_size=(0.0, 0.0), spoke_segments=[])
    ])
    copper = CopperBalanceReport(layer_balances=[], total_area_mm2=0.0)
    creepage = CreepageReport(violations=[], total_checks=0)
    clearance = ClearanceReport(violations=[], total_checks=0)

    report = generate_manufacturing_report(
        acid, annular, teardrops, thermal, copper, creepage, clearance
    )

    # 1 critical acid trap + 1 annular ring violation
    assert report.critical_violations == 2


def test_format_report():
    """Test report formatting."""
    acid = AcidTrapReport(acid_traps=[])
    annular = AnnularRingReport(violations=[], total_vias_checked=10)
    teardrops = TeardropReport(teardrops=[
        Teardrop("NET1", (0, 0), "via", 0.3, 0.6, "F.Cu")
    ])
    thermal = ThermalReliefReport(thermal_reliefs=[
        ThermalRelief("GND", (0, 0), 4, 0.254, 0.254, pad_size=(0.0, 0.0), spoke_segments=[])
    ])
    copper = CopperBalanceReport(layer_balances=[], total_area_mm2=0.0)
    creepage = CreepageReport(violations=[], total_checks=5)
    clearance = ClearanceReport(violations=[], total_checks=20)

    report = generate_manufacturing_report(
        acid, annular, teardrops, thermal, copper, creepage, clearance
    )

    formatted = format_manufacturing_report(report)

    assert "MANUFACTURING DRC REPORT" in formatted
    assert "✓ PASS" in formatted
    assert "Total Violations: 0" in formatted


def test_copper_balance_violations():
    """Test copper balance violations in report."""
    acid = AcidTrapReport(acid_traps=[])
    annular = AnnularRingReport(violations=[], total_vias_checked=0)
    teardrops = TeardropReport(teardrops=[
        Teardrop("NET1", (0, 0), "via", 0.3, 0.6, "F.Cu")
    ])
    thermal = ThermalReliefReport(thermal_reliefs=[
        ThermalRelief("GND", (0, 0), 4, 0.254, 0.254, pad_size=(0.0, 0.0), spoke_segments=[])
    ])

    # Unbalanced layers
    copper = CopperBalanceReport(layer_balances=[
        LayerCopperBalance("F.Cu", 1000, 10, False),
        LayerCopperBalance("B.Cu", 8000, 80, False),
    ], total_area_mm2=0.0)

    creepage = CreepageReport(violations=[], total_checks=0)
    clearance = ClearanceReport(violations=[], total_checks=0)

    report = generate_manufacturing_report(
        acid, annular, teardrops, thermal, copper, creepage, clearance
    )

    # 2 unbalanced layers count as violations (teardrops/thermal present, so no partial failures)
    assert report.total_violations == 2
    assert report.critical_violations == 2
    assert not report.is_manufacturability_ok
