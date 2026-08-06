"""
Result types for DRC check outputs and Check stub classes.

Wave 4 **Phase 2** contract migration: the result contract types
(``Severity``, ``Location``, ``Issue``, ``CheckResult``, ``RunResult``) are
now pyo3 pyclasses in the ``temper-drc-rs`` crate (the ``temper_drc_rs``
extension). This module is a pure-delegation re-export of those pyclasses
(the pattern established by ``core/board.py`` and ``core/netlist.py`` and
applied to the ``drc_types`` contracts in this same slice), with the
dataclass protocol (``__dataclass_fields__`` / ``dataclasses.fields`` /
``dataclasses.replace``) restored on each class by
``core/_contract_dataclass_compat``.

The pre-migration implementation is pinned VERBATIM as the oracle
``tests/validation/_drc_result_py_oracle.py`` (commit ``17553437d``);
construction/field/repr/str/eq/mutation parity and the consumer access
patterns are asserted by ``tests/validation/test_drc_contracts_rust_differential.py``.
See ``packages/temper-drc-rs/VERIFICATION.md``.

The ``Check`` ABC, ``CompositeCheck`` and the 15 check stub classes remain
Python: they are import-compatibility execution placeholders (actual check
execution delegates to the Rust engine), not data contracts — only their
``CheckResult`` construction calls cross to the pyclass.

Former locations:
  - ``temper_drc.core.result`` → Issue, CheckResult, RunResult, Location
  - ``temper_drc.core.severity`` → Severity
  - ``temper_drc.core.check`` → Check, CompositeCheck
  - ``temper_drc.checks.drc.*``, ``temper_drc.checks.erc.*``,
    ``temper_drc.checks.emc.*``, ``temper_drc.checks.safety.*`` → 15 Check stubs
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import (  # noqa: F401  (annotation resolution for get_type_hints)
    TYPE_CHECKING,
    Any,
    TypeAlias,
)

import temper_drc_rs as _tdrc

from temper_placer.core._contract_dataclass_compat import (
    field as _field,
)
from temper_placer.core._contract_dataclass_compat import (
    install_dataclass_fields as _install_dataclass_fields,
)

if TYPE_CHECKING:
    from temper_placer.validation.drc_types import ConstraintSet, Placement

# =========================================================================
#  Result contracts  (was temper_drc.core.result / temper_drc.core.severity)
#
#  These are pyo3 pyclasses in temper-drc-rs. The dataclass protocol is
#  restored field-for-field against the pinned oracle below.
#
#  The `TypeAlias` marker is the mypy idiom for "a module-level name bound
#  to an (untyped) extension class that must also be usable in annotations"
#  — the Check/stub classes annotate `-> CheckResult` below.
# =========================================================================

Severity: TypeAlias = _tdrc.Severity
Location: TypeAlias = _tdrc.Location
Issue: TypeAlias = _tdrc.Issue
CheckResult: TypeAlias = _tdrc.CheckResult
RunResult: TypeAlias = _tdrc.RunResult

_install_dataclass_fields(
    Location,
    (
        _field("x", "float | None", None),
        _field("y", "float | None", None),
        _field("layer", "str | None", None),
    ),
    module=__name__,
)
_install_dataclass_fields(
    Issue,
    (
        _field("severity", "Severity"),
        _field("code", "str"),
        _field("message", "str"),
        _field("category", "str"),
        _field("check_name", "str"),
        _field("affected_items", "list[str]", default_factory=list),
        _field("location", "Location | None", None),
        _field("details", "dict[str, Any]", default_factory=dict),
        _field("constraint_id", "str | None", None),
    ),
    module=__name__,
)
_install_dataclass_fields(
    CheckResult,
    (
        _field("check_name", "str"),
        _field("passed", "bool"),
        _field("issues", "list[Issue]", default_factory=list),
        _field("elapsed_ms", "float", 0.0),
        _field("metrics", "dict[str, float]", default_factory=dict),
    ),
    module=__name__,
)
_install_dataclass_fields(
    RunResult,
    (
        _field("check_results", "list[CheckResult]", default_factory=list),
        _field("total_elapsed_ms", "float", 0.0),
    ),
    module=__name__,
)


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
        self.checks = checks
        self.name = name
        self._description = description

    @property
    def category(self) -> str:
        return "composite"

    @property
    def description(self) -> str:
        if self._description:
            return self._description
        check_names = ", ".join(c.name for c in self.checks)
        return f"Composite of: {check_names}"

    def run(
        self,
        placement: Placement,
        constraints: ConstraintSet,
        modified_regions: list[tuple[float, float, float, float]] | None = None,
    ) -> CheckResult:
        result = CheckResult(check_name=self.name, passed=True)
        for check in self.checks:
            if check.is_applicable(placement, constraints):
                if modified_regions is not None and check.supports_incremental:
                    sub_result = check.run(
                        placement, constraints, modified_regions=modified_regions
                    )
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
        return any(c.is_applicable(placement, constraints) for c in self.checks)


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
        _placement: Placement,
        _constraints: ConstraintSet,
        _modified_regions: list[tuple[float, float, float, float]] | None = None,
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
        _placement: Placement,
        _constraints: ConstraintSet,
        _modified_regions: list[tuple[float, float, float, float]] | None = None,
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
        _placement: Placement,
        _constraints: ConstraintSet,
        _modified_regions: list[tuple[float, float, float, float]] | None = None,
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
        _placement: Placement,
        _constraints: ConstraintSet,
        _modified_regions: list[tuple[float, float, float, float]] | None = None,
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
        _placement: Placement,
        _constraints: ConstraintSet,
        _modified_regions: list[tuple[float, float, float, float]] | None = None,
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
        _placement: Placement,
        _constraints: ConstraintSet,
        _modified_regions: list[tuple[float, float, float, float]] | None = None,
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
        _placement: Placement,
        _constraints: ConstraintSet,
        _modified_regions: list[tuple[float, float, float, float]] | None = None,
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
        _placement: Placement,
        _constraints: ConstraintSet,
        _modified_regions: list[tuple[float, float, float, float]] | None = None,
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
        _placement: Placement,
        _constraints: ConstraintSet,
        _modified_regions: list[tuple[float, float, float, float]] | None = None,
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
        _placement: Placement,
        _constraints: ConstraintSet,
        _modified_regions: list[tuple[float, float, float, float]] | None = None,
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
        _placement: Placement,
        _constraints: ConstraintSet,
        _modified_regions: list[tuple[float, float, float, float]] | None = None,
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
        _placement: Placement,
        _constraints: ConstraintSet,
        _modified_regions: list[tuple[float, float, float, float]] | None = None,
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
        _placement: Placement,
        _constraints: ConstraintSet,
        _modified_regions: list[tuple[float, float, float, float]] | None = None,
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
        _placement: Placement,
        _constraints: ConstraintSet,
        _modified_regions: list[tuple[float, float, float, float]] | None = None,
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
        _placement: Placement,
        _constraints: ConstraintSet,
        _modified_regions: list[tuple[float, float, float, float]] | None = None,
    ) -> CheckResult:
        return CheckResult(check_name=self.name, passed=True)
