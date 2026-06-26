"""Shared base for DFM check report dataclasses.

Provides the ``violation_count`` and ``pass_rate`` properties that are
duplicated across ClearanceReport, CreepageReport, and
AnnularRingReport (and any future check modules).

Usage::

    from dataclasses import dataclass

    from temper_placer.router_v6._check_report_base import BaseCheckReport

    @dataclass
    class MyReport(BaseCheckReport):
        violations: list[MyViolation]
        total_checks: int = 0  # denominator for pass_rate
"""

from __future__ import annotations


class BaseCheckReport:
    """Mixin providing ``violation_count`` and ``pass_rate`` properties.

    Subclasses must define:
    * ``violations: list[...]``  – the list whose length is the violation count
    * a denominator field whose name is given by ``_denominator_field``
      (default ``"total_checks"``)
    """

    violations: list  # type: ignore[annotation-unchecked]  -- set by subclasses
    _denominator_field: str = "total_checks"

    @property
    def violation_count(self) -> int:
        return len(self.violations)

    @property
    def pass_rate(self) -> float:
        denominator: int = getattr(self, self._denominator_field, 0)
        if denominator == 0:
            return 100.0
        return (denominator - self.violation_count) / denominator * 100.0
