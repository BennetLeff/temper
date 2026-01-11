"""
Router V6 Stage 5.8: Generate Manufacturing Report

Compiles all manufacturing DRC results into final report.
Part of temper-klru (Stage 5 - Manufacturing DRC)
"""

from __future__ import annotations

from dataclasses import dataclass

from temper_placer.router_v6.acid_trap_detection import AcidTrapReport
from temper_placer.router_v6.annular_ring_check import AnnularRingReport
from temper_placer.router_v6.clearance_check import ClearanceReport
from temper_placer.router_v6.copper_balance import CopperBalanceReport
from temper_placer.router_v6.creepage_check import CreepageReport
from temper_placer.router_v6.teardrop_generation import TeardropReport
from temper_placer.router_v6.thermal_relief import ThermalReliefReport


@dataclass
class ManufacturingReport:
    """Complete manufacturing DRC report."""

    acid_traps: AcidTrapReport
    annular_rings: AnnularRingReport
    teardrops: TeardropReport
    thermal_reliefs: ThermalReliefReport
    copper_balance: CopperBalanceReport
    creepage: CreepageReport
    clearance: ClearanceReport
    
    @property
    def total_violations(self) -> int:
        """Total number of violations across all checks."""
        return (
            self.acid_traps.trap_count +
            self.annular_rings.violation_count +
            self.creepage.violation_count +
            self.clearance.violation_count +
            self.copper_balance.unbalanced_layer_count
        )
    
    @property
    def is_manufacturability_ok(self) -> bool:
        """Check if design meets all manufacturing requirements."""
        return self.total_violations == 0
    
    @property
    def critical_violations(self) -> int:
        """Number of critical violations (blocking manufacture)."""
        return (
            self.acid_traps.critical_count +
            self.annular_rings.violation_count +
            self.creepage.violation_count +
            self.clearance.violation_count
        )


def generate_manufacturing_report(
    acid_traps: AcidTrapReport,
    annular_rings: AnnularRingReport,
    teardrops: TeardropReport,
    thermal_reliefs: ThermalReliefReport,
    copper_balance: CopperBalanceReport,
    creepage: CreepageReport,
    clearance: ClearanceReport,
) -> ManufacturingReport:
    """
    Generate complete manufacturing DRC report.

    Compiles all Stage 5 validation results into a single
    comprehensive report for manufacturing readiness.

    Args:
        acid_traps: Acid trap detection results
        annular_rings: Annular ring validation results
        teardrops: Teardrop generation results
        thermal_reliefs: Thermal relief results
        copper_balance: Copper balance analysis results
        creepage: Creepage validation results
        clearance: Clearance validation results

    Returns:
        ManufacturingReport with all DRC results

    Example:
        >>> from temper_placer.router_v6.acid_trap_detection import AcidTrapReport
        >>> from temper_placer.router_v6.annular_ring_check import AnnularRingReport
        >>> from temper_placer.router_v6.teardrop_generation import TeardropReport
        >>> from temper_placer.router_v6.thermal_relief import ThermalReliefReport
        >>> from temper_placer.router_v6.copper_balance import CopperBalanceReport
        >>> from temper_placer.router_v6.creepage_check import CreepageReport
        >>> from temper_placer.router_v6.clearance_check import ClearanceReport
        >>> acid = AcidTrapReport(acid_traps=[])
        >>> annular = AnnularRingReport(violations=[], total_vias_checked=0)
        >>> teardrops = TeardropReport(teardrops=[])
        >>> thermal = ThermalReliefReport(thermal_reliefs=[])
        >>> copper = CopperBalanceReport(layer_balances=[])
        >>> creepage = CreepageReport(violations=[], total_checks=0)
        >>> clearance = ClearanceReport(violations=[], total_checks=0)
        >>> report = generate_manufacturing_report(acid, annular, teardrops, thermal, copper, creepage, clearance)
        >>> report.is_manufacturability_ok
        True
    """
    return ManufacturingReport(
        acid_traps=acid_traps,
        annular_rings=annular_rings,
        teardrops=teardrops,
        thermal_reliefs=thermal_reliefs,
        copper_balance=copper_balance,
        creepage=creepage,
        clearance=clearance,
    )


def format_manufacturing_report(report: ManufacturingReport) -> str:
    """
    Format manufacturing report as human-readable text.

    Args:
        report: Manufacturing report

    Returns:
        Formatted report string
    """
    lines = []
    lines.append("=" * 60)
    lines.append("MANUFACTURING DRC REPORT")
    lines.append("=" * 60)
    lines.append("")
    
    # Summary
    status = "✓ PASS" if report.is_manufacturability_ok else "✗ FAIL"
    lines.append(f"Overall Status: {status}")
    lines.append(f"Total Violations: {report.total_violations}")
    lines.append(f"Critical Violations: {report.critical_violations}")
    lines.append("")
    
    # Acid Traps
    lines.append(f"Acid Traps: {report.acid_traps.trap_count} found")
    lines.append(f"  - Critical (< 45°): {report.acid_traps.critical_count}")
    lines.append("")
    
    # Annular Rings
    lines.append(f"Annular Rings: {report.annular_rings.violation_count} violations")
    lines.append(f"  - Total vias checked: {report.annular_rings.total_vias_checked}")
    lines.append(f"  - Pass rate: {report.annular_rings.pass_rate:.1f}%")
    lines.append("")
    
    # Teardrops
    lines.append(f"Teardrops: {report.teardrops.teardrop_count} generated")
    lines.append(f"  - Via teardrops: {report.teardrops.via_teardrop_count}")
    lines.append(f"  - Pad teardrops: {report.teardrops.pad_teardrop_count}")
    lines.append("")
    
    # Thermal Relief
    lines.append(f"Thermal Reliefs: {report.thermal_reliefs.relief_count} generated")
    lines.append(f"  - Total spokes: {report.thermal_reliefs.total_spokes}")
    lines.append("")
    
    # Copper Balance
    lines.append(f"Copper Balance: {report.copper_balance.balanced_layer_count} layers OK")
    lines.append(f"  - Unbalanced layers: {report.copper_balance.unbalanced_layer_count}")
    lines.append("")
    
    # Creepage
    lines.append(f"Creepage: {report.creepage.violation_count} violations")
    lines.append(f"  - Total checks: {report.creepage.total_checks}")
    lines.append(f"  - Pass rate: {report.creepage.pass_rate:.1f}%")
    lines.append("")
    
    # Clearance
    lines.append(f"Clearance: {report.clearance.violation_count} violations")
    lines.append(f"  - Total checks: {report.clearance.total_checks}")
    lines.append(f"  - Pass rate: {report.clearance.pass_rate:.1f}%")
    lines.append("")
    
    lines.append("=" * 60)
    
    return "\n".join(lines)
