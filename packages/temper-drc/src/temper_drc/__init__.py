"""
temper-drc: Composable Design Rule Checker for PCB Designs.

This package provides standalone DRC (Design Rule Check) and ERC (Electrical
Rule Check) validation for PCB designs using the PCL (Placement Constraint
Language) YAML format.

Features:
- Composable check architecture - combine checks as needed
- Four check categories: ERC, DRC, Safety, EMC
- Rich metrics and reporting
- No external dependencies (standalone, no KiCad required)

Example usage:
    from temper_drc import CheckRunner, create_standard_checks
    from temper_drc.input import Placement, ConstraintSet

    placement = Placement.from_yaml("placement.yaml")
    constraints = ConstraintSet.from_yaml("constraints.yaml")

    runner = CheckRunner()
    runner.add_checks(create_standard_checks())

    result = runner.run(placement, constraints)

    if not result.passed:
        for issue in result.all_issues:
            print(f"[{issue.code}] {issue.message}")
"""

__version__ = "0.1.0"

from temper_drc.core.check import Check, CompositeCheck
from temper_drc.core.fence import (
    DRCFence,
    FenceBudgetError,
    FenceResult,
    FenceViolation,
    FenceViolationError,
    InvariantSpec,
    _issue_fingerprint,
)
from temper_drc.core.metrics import CheckMetrics, MetricsSummary
from temper_drc.core.result import CheckResult, Issue, Location, RunResult
from temper_drc.core.runner import CheckRunner
from temper_drc.core.severity import Severity

__all__ = [
    # Version
    "__version__",
    # Core classes
    "Check",
    "CompositeCheck",
    "CheckRunner",
    "CheckResult",
    "RunResult",
    "Issue",
    "Location",
    "Severity",
    "CheckMetrics",
    "MetricsSummary",
    # Fence classes
    "DRCFence",
    "FenceBudgetError",
    "FenceResult",
    "FenceViolation",
    "FenceViolationError",
    "InvariantSpec",
    "_issue_fingerprint",
]
