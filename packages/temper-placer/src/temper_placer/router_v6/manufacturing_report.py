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

    def __post_init__(self) -> None:
        """Validate that no sub-report is None."""
        field_names = [
            "acid_traps",
            "annular_rings",
            "teardrops",
            "thermal_reliefs",
            "copper_balance",
            "creepage",
            "clearance",
        ]
        for name in field_names:
            if getattr(self, name) is None:
                raise TypeError(
                    f"ManufacturingReport field '{name}' cannot be None; "
                    f"a valid {name.replace('_', ' ').title()} sub-report is required."
                )

    @property
    def errored_checks(self) -> tuple[str, ...]:
        """Names of DFM checks that crashed, or hit the anti-vacuous-truth
        guard (total_checks == 0 on a board with routed copper).

        This must be visible in the *returned report*, not only in a log
        line -- see
        docs/evidence/2026-07-25-manufacturing-drc-crash-swallow.md.
        """
        candidates = (
            ("acid_trap", self.acid_traps),
            ("annular_ring", self.annular_rings),
            ("teardrop", self.teardrops),
            ("thermal_relief", self.thermal_reliefs),
            ("copper_balance", self.copper_balance),
            ("creepage", self.creepage),
            ("clearance", self.clearance),
        )
        return tuple(name for name, sub_report in candidates if getattr(sub_report, "errored", False))

    @property
    def total_violations(self) -> int:
        """Total number of violations across all checks, including partial failures.

        ``creepage``, ``clearance``, and ``annular_ring`` fail closed
        (METHODOLOGY.md Sec 5; matches the ``_allow_forced_segments``
        precedent): an errored check counts as at least one violation
        even when its (necessarily incomplete) violation list is empty,
        rather than being read as "0 violations found".
        """
        teardrop_failure = 1 if self.teardrops.teardrop_count == 0 else 0
        thermal_failure = 1 if self.thermal_reliefs.relief_count == 0 else 0
        annular_count = (
            max(self.annular_rings.violation_count, 1)
            if self.annular_rings.errored
            else self.annular_rings.violation_count
        )
        creepage_count = (
            max(self.creepage.violation_count, 1)
            if self.creepage.errored
            else self.creepage.violation_count
        )
        clearance_count = (
            max(self.clearance.violation_count, 1)
            if self.clearance.errored
            else self.clearance.violation_count
        )
        return (
            self.acid_traps.trap_count
            + annular_count
            + creepage_count
            + clearance_count
            + self.copper_balance.unbalanced_layer_count
            + teardrop_failure
            + thermal_failure
        )

    @property
    def is_manufacturability_ok(self) -> bool:
        """Check if design meets all manufacturing requirements."""
        return self.total_violations == 0

    @property
    def critical_violations(self) -> int:
        """Number of critical violations (blocking manufacture).

        Fails closed on an errored creepage/clearance/annular_ring check
        -- see ``total_violations``.
        """
        annular_count = (
            max(self.annular_rings.violation_count, 1)
            if self.annular_rings.errored
            else self.annular_rings.violation_count
        )
        creepage_count = (
            max(self.creepage.violation_count, 1)
            if self.creepage.errored
            else self.creepage.violation_count
        )
        clearance_count = (
            max(self.clearance.violation_count, 1)
            if self.clearance.errored
            else self.clearance.violation_count
        )
        return (
            self.acid_traps.critical_count
            + annular_count
            + creepage_count
            + clearance_count
            + self.copper_balance.unbalanced_layer_count
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
        >>> from temper_placer.router_v6.teardrop_generation import Teardrop, TeardropReport
        >>> from temper_placer.router_v6.thermal_relief import ThermalRelief, ThermalReliefReport
        >>> from temper_placer.router_v6.copper_balance import CopperBalanceReport
        >>> from temper_placer.router_v6.creepage_check import CreepageReport
        >>> from temper_placer.router_v6.clearance_check import ClearanceReport
        >>> acid = AcidTrapReport(acid_traps=[])
        >>> annular = AnnularRingReport(violations=[], total_vias_checked=0)
        >>> teardrops = TeardropReport(teardrops=[Teardrop("NET1", (0, 0), "via", 0.3, 0.6, "F.Cu")])
        >>> thermal = ThermalReliefReport(thermal_reliefs=[ThermalRelief("GND", (0, 0), 4, 0.254, 0.254)])
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
    if report.errored_checks:
        lines.append(
            "⚠ CHECK ERRORS (crashed or vacuous -- results below are "
            f"unreliable/fail-closed): {', '.join(report.errored_checks)}"
        )
    lines.append("")

    # Acid Traps
    lines.append(f"Acid Traps: {report.acid_traps.trap_count} found")
    lines.append(f"  - Critical (< 45°): {report.acid_traps.critical_count}")
    lines.append("")

    # Annular Rings
    annular_tag = (
        " [ERRORED -- fail-closed, see CHECK ERRORS above]"
        if report.annular_rings.errored
        else ""
    )
    lines.append(f"Annular Rings: {report.annular_rings.violation_count} violations{annular_tag}")
    lines.append(f"  - Total vias checked: {report.annular_rings.total_vias_checked}")
    if report.annular_rings.total_vias_checked == 0:
        lines.append("  - Pass rate: N/A")
    else:
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
    creepage_tag = " [ERRORED -- fail-closed, see CHECK ERRORS above]" if report.creepage.errored else ""
    lines.append(f"Creepage: {report.creepage.violation_count} violations{creepage_tag}")
    lines.append(f"  - Total checks: {report.creepage.total_checks}")
    if report.creepage.total_checks == 0:
        lines.append("  - Pass rate: N/A")
    else:
        lines.append(f"  - Pass rate: {report.creepage.pass_rate:.1f}%")
    lines.append("")

    # Clearance
    clearance_tag = " [ERRORED -- fail-closed, see CHECK ERRORS above]" if report.clearance.errored else ""
    lines.append(f"Clearance: {report.clearance.violation_count} violations{clearance_tag}")
    lines.append(f"  - Total checks: {report.clearance.total_checks}")
    if report.clearance.total_checks == 0:
        lines.append("  - Pass rate: N/A")
    else:
        lines.append(f"  - Pass rate: {report.clearance.pass_rate:.1f}%")
    lines.append("")

    lines.append("=" * 60)

    return "\n".join(lines)
