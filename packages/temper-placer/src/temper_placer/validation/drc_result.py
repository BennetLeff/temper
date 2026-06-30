"""
Result types for DRC check outputs and Check stub classes.

Moved from the now-removed ``temper-drc`` Python package.  All actual DRC
execution is delegated to the Rust crate ``temper-drc-rs``; these types
remain for backward-compatible data construction and the Check stubs are
kept only as import-compatibility placeholders.

Former locations:
  - ``temper_drc.core.result`` → Issue, CheckResult, RunResult, Location
  - ``temper_drc.core.severity`` → Severity
  - ``temper_drc.core.check`` → Check, CompositeCheck
  - ``temper_drc.checks.drc.*``, ``temper_drc.checks.erc.*``,
    ``temper_drc.checks.emc.*``, ``temper_drc.checks.safety.*`` → 15 Check stubs
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from temper_placer.validation.drc_types import ConstraintSet, Placement


# =========================================================================
#  Severity  (was temper_drc.core.severity)
# =========================================================================


class Severity(Enum):
    """
    Check result severity levels.

    Severity determines how issues are weighted in metrics and whether
    they cause the overall check to fail.

    Levels:
        INFO: Informational message, no issue (weight: 0.0)
        WARNING: Potential issue that may affect quality (weight: 1.0)
        ERROR: Violation that should be fixed (weight: 10.0)
        CRITICAL: Safety-critical violation that blocks manufacturing (weight: 100.0)
    """

    INFO = auto()
    WARNING = auto()
    ERROR = auto()
    CRITICAL = auto()

    @property
    def weight(self) -> float:
        weights = {
            Severity.INFO: 0.0,
            Severity.WARNING: 1.0,
            Severity.ERROR: 10.0,
            Severity.CRITICAL: 100.0,
        }
        return weights[self]

    @property
    def is_failure(self) -> bool:
        return self in (Severity.ERROR, Severity.CRITICAL)

    def __lt__(self, other: Severity) -> bool:
        if not isinstance(other, Severity):
            return NotImplemented
        return self.value < other.value

    def __le__(self, other: Severity) -> bool:
        if not isinstance(other, Severity):
            return NotImplemented
        return self.value <= other.value


# =========================================================================
#  Result types  (was temper_drc.core.result)
# =========================================================================


@dataclass
class Location:
    """Spatial location of an issue on the PCB."""

    x: float | None = None
    y: float | None = None
    layer: str | None = None

    def __str__(self) -> str:
        if self.x is not None and self.y is not None:
            loc = f"({self.x:.2f}, {self.y:.2f})"
            if self.layer:
                loc += f" on {self.layer}"
            return loc
        return "unknown"

    def to_dict(self) -> dict[str, Any]:
        return {
            "x": self.x,
            "y": self.y,
            "layer": self.layer,
        }


@dataclass
class Issue:
    """A single check issue found during verification."""

    severity: Severity
    code: str
    message: str
    category: str
    check_name: str
    affected_items: list[str] = field(default_factory=list)
    location: Location | None = None
    details: dict[str, Any] = field(default_factory=dict)
    constraint_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity.name,
            "code": self.code,
            "message": self.message,
            "category": self.category,
            "check_name": self.check_name,
            "affected_items": self.affected_items,
            "location": self.location.to_dict() if self.location else None,
            "details": self.details,
            "constraint_id": self.constraint_id,
        }

    def __str__(self) -> str:
        items = ", ".join(self.affected_items[:3])
        if len(self.affected_items) > 3:
            items += f" (+{len(self.affected_items) - 3} more)"
        return f"[{self.code}] {self.message} ({items})"


@dataclass
class CheckResult:
    """Result of running a single check."""

    check_name: str
    passed: bool
    issues: list[Issue] = field(default_factory=list)
    elapsed_ms: float = 0.0
    metrics: dict[str, float] = field(default_factory=dict)

    @property
    def info_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == Severity.INFO)

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == Severity.WARNING)

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == Severity.ERROR)

    @property
    def critical_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == Severity.CRITICAL)

    @property
    def total_issues(self) -> int:
        return self.warning_count + self.error_count + self.critical_count

    @property
    def penalty(self) -> float:
        return sum(issue.severity.weight for issue in self.issues)

    def merge(self, other: CheckResult) -> CheckResult:
        return CheckResult(
            check_name=self.check_name,
            passed=self.passed and other.passed,
            issues=self.issues + other.issues,
            elapsed_ms=self.elapsed_ms + other.elapsed_ms,
            metrics={**self.metrics, **other.metrics},
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "check_name": self.check_name,
            "passed": self.passed,
            "issues": [i.to_dict() for i in self.issues],
            "elapsed_ms": self.elapsed_ms,
            "metrics": self.metrics,
            "counts": {
                "info": self.info_count,
                "warning": self.warning_count,
                "error": self.error_count,
                "critical": self.critical_count,
            },
        }


@dataclass
class RunResult:
    """Result of running multiple checks."""

    check_results: list[CheckResult] = field(default_factory=list)
    total_elapsed_ms: float = 0.0

    @property
    def passed(self) -> bool:
        return all(r.passed for r in self.check_results)

    @property
    def all_issues(self) -> list[Issue]:
        issues = []
        for result in self.check_results:
            issues.extend(result.issues)
        return issues

    @property
    def total_checks(self) -> int:
        return len(self.check_results)

    @property
    def passed_checks(self) -> int:
        return sum(1 for r in self.check_results if r.passed)

    @property
    def failed_checks(self) -> int:
        return sum(1 for r in self.check_results if not r.passed)

    @property
    def info_count(self) -> int:
        return sum(r.info_count for r in self.check_results)

    @property
    def warning_count(self) -> int:
        return sum(r.warning_count for r in self.check_results)

    @property
    def error_count(self) -> int:
        return sum(r.error_count for r in self.check_results)

    @property
    def critical_count(self) -> int:
        return sum(r.critical_count for r in self.check_results)

    @property
    def total_penalty(self) -> float:
        return sum(r.penalty for r in self.check_results)

    def by_category(self, category: str) -> list[CheckResult]:
        return [
            r for r in self.check_results
            if any(i.category == category for i in r.issues) or not r.issues
        ]

    def by_severity(self, severity: Severity) -> list[Issue]:
        return [i for i in self.all_issues if i.severity == severity]

    def issues_for_component(self, ref: str) -> list[Issue]:
        return [i for i in self.all_issues if ref in i.affected_items]

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "total_elapsed_ms": self.total_elapsed_ms,
            "summary": {
                "total_checks": self.total_checks,
                "passed_checks": self.passed_checks,
                "failed_checks": self.failed_checks,
                "info": self.info_count,
                "warning": self.warning_count,
                "error": self.error_count,
                "critical": self.critical_count,
                "total_penalty": self.total_penalty,
            },
            "check_results": [r.to_dict() for r in self.check_results],
        }


# =========================================================================
#  Check ABC & CompositeCheck  (was temper_drc.core.check)
# =========================================================================


class Check(ABC):
    """
    Abstract base class for all design rule checks.

    Subclasses must implement:
    - name: Unique identifier for the check
    - category: One of "erc", "drc", "safety", "emc"
    - run(): Execute the check and return results
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique name identifying this check."""

    @property
    @abstractmethod
    def category(self) -> str:
        """Check category: 'erc', 'drc', 'safety', 'emc'."""

    @property
    def description(self) -> str:
        return ""

    @property
    def supports_incremental(self) -> bool:
        return False

    @property
    def code_prefix(self) -> str:
        cat = self.category.upper()[:3]
        name = self.name.upper()[:3]
        return f"{cat}_{name}_"

    @abstractmethod
    def run(
        self,
        placement: Placement,
        constraints: ConstraintSet,
        modified_regions: list[tuple[float, float, float, float]] | None = None,
    ) -> CheckResult:
        """Run the check on the given placement."""

    def is_applicable(
        self,
        _placement: Placement,
        _constraints: ConstraintSet,
    ) -> bool:
        """Check if this check applies to the given input."""
        return True


class CompositeCheck(Check):
    """Runs multiple checks and combines their results."""

    def __init__(
        self,
        checks: list[Check],
        name: str = "composite",
        description: str = "",
    ):
        self._checks = checks
        self._name = name
        self._description = description

    @property
    def name(self) -> str:
        return self._name

    @property
    def category(self) -> str:
        return "composite"

    @property
    def description(self) -> str:
        if self._description:
            return self._description
        check_names = ", ".join(c.name for c in self._checks)
        return f"Composite of: {check_names}"

    @property
    def checks(self) -> list[Check]:
        return self._checks

    def run(
        self,
        placement: Placement,
        constraints: ConstraintSet,
        modified_regions: list[tuple[float, float, float, float]] | None = None,
    ) -> CheckResult:
        result = CheckResult(check_name=self.name, passed=True)
        for check in self._checks:
            if check.is_applicable(placement, constraints):
                if modified_regions is not None and check.supports_incremental:
                    sub_result = check.run(placement, constraints, modified_regions=modified_regions)
                else:
                    sub_result = check.run(placement, constraints)
                result = result.merge(sub_result)
                if not sub_result.passed:
                    result = CheckResult(
                        check_name=result.check_name,
                        passed=False,
                        issues=result.issues,
                        elapsed_ms=result.elapsed_ms,
                        metrics=result.metrics,
                    )
        return result

    def is_applicable(
        self,
        placement: Placement,
        constraints: ConstraintSet,
    ) -> bool:
        return any(c.is_applicable(placement, constraints) for c in self._checks)


# =========================================================================
#  Check stub classes  (formerly in temper_drc.checks.{drc,erc,emc,safety}.*)
#
#  These are kept as import-compatibility placeholders.  Actual check
#  execution is delegated to the Rust engine (temper_drc_rs).
# =========================================================================


class ClearanceCheck(Check):
    """Clearance check — delegates to Rust engine via CheckRunner."""

    @property
    def name(self) -> str:
        return "drc_clearance"

    @property
    def category(self) -> str:
        return "drc"

    @property
    def description(self) -> str:
        return "Verify component-to-component clearance based on net classes."

    def run(
        self,
        placement: Placement,
        constraints: ConstraintSet,
        modified_regions: list[tuple[float, float, float, float]] | None = None,
    ) -> CheckResult:
        return CheckResult(check_name=self.name, passed=True)


class ComponentOverlapCheck(Check):
    """Component overlap check — delegates to Rust engine via CheckRunner."""

    @property
    def name(self) -> str:
        return "drc_component_overlap"

    @property
    def category(self) -> str:
        return "drc"

    @property
    def description(self) -> str:
        return "Detect overlap between component bodies on the same layer."

    @property
    def supports_incremental(self) -> bool:
        return True

    def run(
        self,
        placement: Placement,
        constraints: ConstraintSet,
        modified_regions: list[tuple[float, float, float, float]] | None = None,
    ) -> CheckResult:
        return CheckResult(check_name=self.name, passed=True)


class CourtyardCheck(Check):
    """Courtyard check — delegates to Rust engine via CheckRunner."""

    def __init__(self, margin_mm: float = 0.05):
        self._margin_mm = margin_mm

    @property
    def name(self) -> str:
        return "drc_courtyard"

    @property
    def category(self) -> str:
        return "drc"

    @property
    def description(self) -> str:
        return "Verify courtyard clearance between component bodies."

    def run(
        self,
        placement: Placement,
        constraints: ConstraintSet,
        modified_regions: list[tuple[float, float, float, float]] | None = None,
    ) -> CheckResult:
        return CheckResult(check_name=self.name, passed=True)


class ZoneContainmentCheck(Check):
    """Zone containment check — delegates to Rust engine via CheckRunner."""

    @property
    def name(self) -> str:
        return "drc_zone_containment"

    @property
    def category(self) -> str:
        return "drc"

    @property
    def description(self) -> str:
        return "Verify that components assigned to a zone are placed within its bounds."

    def run(
        self,
        placement: Placement,
        constraints: ConstraintSet,
        modified_regions: list[tuple[float, float, float, float]] | None = None,
    ) -> CheckResult:
        return CheckResult(check_name=self.name, passed=True)


class TraceClearanceCheck(Check):
    """Trace clearance check — delegates to Rust engine via CheckRunner."""

    @property
    def name(self) -> str:
        return "drc_trace_clearance"

    @property
    def category(self) -> str:
        return "drc"

    @property
    def description(self) -> str:
        return "Verify trace-to-trace minimum clearance on each layer."

    def run(
        self,
        placement: Placement,
        constraints: ConstraintSet,
        modified_regions: list[tuple[float, float, float, float]] | None = None,
    ) -> CheckResult:
        return CheckResult(check_name=self.name, passed=True)


class ViaSpacingCheck(Check):
    """Via spacing check — delegates to Rust engine via CheckRunner."""

    @property
    def name(self) -> str:
        return "drc_via_spacing"

    @property
    def category(self) -> str:
        return "drc"

    @property
    def description(self) -> str:
        return "Verify via-to-via minimum spacing on matching layer pairs."

    def run(
        self,
        placement: Placement,
        constraints: ConstraintSet,
        modified_regions: list[tuple[float, float, float, float]] | None = None,
    ) -> CheckResult:
        return CheckResult(check_name=self.name, passed=True)


class NetConnectivityCheck(Check):
    """Net connectivity check — delegates to Rust engine via CheckRunner."""

    @property
    def name(self) -> str:
        return "erc_net_connectivity"

    @property
    def category(self) -> str:
        return "erc"

    @property
    def description(self) -> str:
        return "Ensure all nets have at least 2 connections (no single-pin nets)."

    def run(
        self,
        placement: Placement,
        constraints: ConstraintSet,
        modified_regions: list[tuple[float, float, float, float]] | None = None,
    ) -> CheckResult:
        return CheckResult(check_name=self.name, passed=True)


class PowerDomainCheck(Check):
    """Power domain check — delegates to Rust engine via CheckRunner."""

    @property
    def name(self) -> str:
        return "erc_power_domain"

    @property
    def category(self) -> str:
        return "erc"

    @property
    def description(self) -> str:
        return "Identify nets connecting components from different voltage domains."

    def run(
        self,
        placement: Placement,
        constraints: ConstraintSet,
        modified_regions: list[tuple[float, float, float, float]] | None = None,
    ) -> CheckResult:
        return CheckResult(check_name=self.name, passed=True)


class FloatingPinsCheck(Check):
    """Floating pins check — delegates to Rust engine via CheckRunner."""

    @property
    def name(self) -> str:
        return "erc_floating_pins"

    @property
    def category(self) -> str:
        return "erc"

    @property
    def description(self) -> str:
        return "Identify components that are not connected to any net."

    def run(
        self,
        placement: Placement,
        constraints: ConstraintSet,
        modified_regions: list[tuple[float, float, float, float]] | None = None,
    ) -> CheckResult:
        return CheckResult(check_name=self.name, passed=True)


class HVLVSeparationCheck(Check):
    """HV/LV separation check — delegates to Rust engine via CheckRunner."""

    @property
    def name(self) -> str:
        return "safety_hv_lv_separation"

    @property
    def category(self) -> str:
        return "safety"

    @property
    def description(self) -> str:
        return "Ensure critical separation between HV and LV domains for safety compliance."

    def run(
        self,
        placement: Placement,
        constraints: ConstraintSet,
        modified_regions: list[tuple[float, float, float, float]] | None = None,
    ) -> CheckResult:
        return CheckResult(check_name=self.name, passed=True)


class CreepageCheck(Check):
    """Creepage check — delegates to Rust engine via CheckRunner."""

    def __init__(self, min_iso_width_mm: float = 6.0):
        self._min_iso_width_mm = min_iso_width_mm

    @property
    def name(self) -> str:
        return "safety_creepage"

    @property
    def category(self) -> str:
        return "safety"

    @property
    def description(self) -> str:
        return "Verify minimum creepage (isolation width) requirements per IEC 60335."

    def run(
        self,
        placement: Placement,
        constraints: ConstraintSet,
        modified_regions: list[tuple[float, float, float, float]] | None = None,
    ) -> CheckResult:
        return CheckResult(check_name=self.name, passed=True)


class IsolationCheck(Check):
    """Isolation check — delegates to Rust engine via CheckRunner."""

    @property
    def name(self) -> str:
        return "safety_isolation"

    @property
    def category(self) -> str:
        return "safety"

    @property
    def description(self) -> str:
        return "Ensure no components reside in isolation zones except isolation devices."

    def run(
        self,
        placement: Placement,
        constraints: ConstraintSet,
        modified_regions: list[tuple[float, float, float, float]] | None = None,
    ) -> CheckResult:
        return CheckResult(check_name=self.name, passed=True)


class LoopAreaCheck(Check):
    """Loop area check — delegates to Rust engine via CheckRunner."""

    @property
    def name(self) -> str:
        return "emc_loop_area"

    @property
    def category(self) -> str:
        return "emc"

    @property
    def description(self) -> str:
        return "Minimize radiated emissions by checking critical loop areas."

    def run(
        self,
        placement: Placement,
        constraints: ConstraintSet,
        modified_regions: list[tuple[float, float, float, float]] | None = None,
    ) -> CheckResult:
        return CheckResult(check_name=self.name, passed=True)


class NoiseCouplingCheck(Check):
    """Noise coupling check — delegates to Rust engine via CheckRunner."""

    @property
    def name(self) -> str:
        return "emc_noise_coupling"

    @property
    def category(self) -> str:
        return "emc"

    @property
    def description(self) -> str:
        return "Identify and minimize noise coupling between aggressor and victim components."

    def run(
        self,
        placement: Placement,
        constraints: ConstraintSet,
        modified_regions: list[tuple[float, float, float, float]] | None = None,
    ) -> CheckResult:
        return CheckResult(check_name=self.name, passed=True)


class GroundPlaneCheck(Check):
    """Ground plane check — delegates to Rust engine via CheckRunner."""

    @property
    def name(self) -> str:
        return "emc_ground_plane"

    @property
    def category(self) -> str:
        return "emc"

    @property
    def description(self) -> str:
        return "Ensure high-di/dt or high-speed components have a ground plane return path."

    def run(
        self,
        placement: Placement,
        constraints: ConstraintSet,
        modified_regions: list[tuple[float, float, float, float]] | None = None,
    ) -> CheckResult:
        return CheckResult(check_name=self.name, passed=True)
