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

The ``Check`` ABC and ``CompositeCheck`` remain Python, as do the 15
former "check stub" classes below — but as of the 2026-08-08 Python-side
DRC vacuity fix, 14 of those 15 (every one whose Rust rule name is
registered in ``temper_drc_rs::rules::create_default_registry()``) call
``_run_check_via_rust()`` from their own ``run()``: a real, per-check-name
delegation to ``temper_drc_rs.run_drc()``, not a hardcoded result. The one
exception is ``PowerDomainCheck``: the Rust engine deliberately does NOT
register ``erc_power_domain`` (the native ``BoardState``/``Component``
schema has no ``voltage_domain`` field to check against), so its ``run()``
reports not-run (``passed=False`` plus an INFO ``ERC_PWR_000`` issue)
instead of fabricating a pass — see its class docstring.

Note that the production entry point, ``CheckRunner.run()``
(``drc_runner.py``), still bypasses every one of these classes' own
``run()`` methods and calls ``temper_drc_rs.run_drc()`` directly as one
full/category-filtered sweep; these classes' ``run()`` bodies matter for
direct callers (tests, ``CompositeCheck``, anything that instantiates and
calls a single check) and for import compatibility.

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
#  2026-08-08 vacuity fix: 14 of these 15 classes now call
#  ``_run_check_via_rust()`` below, which is a REAL per-check-name
#  delegation to ``temper_drc_rs.run_drc()`` — not a hardcoded result.  The
#  one exception, ``PowerDomainCheck``, cannot delegate (its Rust rule is
#  deliberately unregistered; see its docstring) and reports not-run
#  instead of a fabricated pass.
# =========================================================================


def _run_check_via_rust(
    check_name: str,
    placement: Placement,
    constraints: ConstraintSet,
) -> CheckResult:
    """Delegate a single named check to the Rust engine (temper_drc_rs).

    Converts *placement*/*constraints* to the K1-schema dicts (reusing
    ``drc_runner``'s marshalling helpers — a deferred import, since
    ``drc_runner`` imports this module at load time and importing it back
    here at module scope would be circular; deferring to call time is safe
    because both modules are already fully loaded by the time any check's
    ``run()`` executes) and calls ``temper_drc_rs.run_drc(...,
    check_names=[check_name])``. That runs the full registered-rule sweep
    and filters the violations down to this one check's name (see
    ``temper_drc_rs``'s ``run_drc`` check-name-filtered branch in
    ``packages/temper-drc-rs/src/lib.rs``). A check with real violations
    reports them (``passed=False`` with the ``Issue``\\ s attached); a check
    with none reports a genuinely-earned ``passed=True``.

    Callers MUST only pass a *check_name* that is actually registered in
    ``temper_drc_rs::rules::create_default_registry()``. A name that is not
    registered silently filters to zero violations here — indistinguishable
    from "ran clean" — which is exactly the vacuity defect this module used
    to have. ``PowerDomainCheck`` (``erc_power_domain`` is deliberately
    unregistered) does NOT go through this helper for that reason.

    KNOWN GAP shared with ``CheckRunner.run()`` (``drc_runner.py``):
    incremental ``modified_regions`` re-checking is not wired through this
    per-check path either — the caller-supplied region bounds are accepted
    (by every ``run()`` below) and ignored, same as the runner's own
    documented gap.
    """
    import temper_drc_rs as _tdrc_mod

    from temper_placer.validation.drc_runner import (
        _constraints_to_dict,
        _placement_to_board_dict,
        _violations_to_run_result,
    )

    board_dict = _placement_to_board_dict(placement)
    constraints_dict = _constraints_to_dict(constraints)
    violation_dicts = _tdrc_mod.run_drc(
        board_dict,
        constraints_dict,
        check_names=[check_name],
    )
    run_result = _violations_to_run_result(violation_dicts)
    for cr in run_result.check_results:
        if cr.check_name == check_name:
            return cr
    return CheckResult(check_name=check_name, passed=True)


class ClearanceCheck(Check):
    """Clearance check — delegates to the Rust engine (temper_drc_rs),
    filtered to this check's name (``drc_clearance``)."""

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
        _modified_regions: list[tuple[float, float, float, float]] | None = None,
    ) -> CheckResult:
        return _run_check_via_rust(self.name, placement, constraints)


class ComponentOverlapCheck(Check):
    """Component overlap check — delegates to the Rust engine
    (temper_drc_rs), filtered to this check's name
    (``drc_component_overlap``)."""

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
        _modified_regions: list[tuple[float, float, float, float]] | None = None,
    ) -> CheckResult:
        return _run_check_via_rust(self.name, placement, constraints)


class CourtyardCheck(Check):
    """Courtyard check — delegates to the Rust engine (temper_drc_rs),
    filtered to this check's name (``drc_courtyard``).

    ``margin_mm`` is NOT forwarded to the Rust side: delegation runs the
    Rust registry's own registered ``CourtyardCheck`` instance (constructed
    with a fixed 0.05mm margin in
    ``temper_drc_rs::rules::create_default_registry()``), not a fresh one
    parameterized by this constructor arg. Kept for import/API compat and
    because it happens to match the Rust default; it does not currently
    change delegated behavior if overridden.
    """

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
        _modified_regions: list[tuple[float, float, float, float]] | None = None,
    ) -> CheckResult:
        return _run_check_via_rust(self.name, placement, constraints)


class ZoneContainmentCheck(Check):
    """Zone containment check — delegates to the Rust engine
    (temper_drc_rs), filtered to this check's name
    (``drc_zone_containment``)."""

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
        _modified_regions: list[tuple[float, float, float, float]] | None = None,
    ) -> CheckResult:
        return _run_check_via_rust(self.name, placement, constraints)


class TraceClearanceCheck(Check):
    """Trace clearance check — delegates to the Rust engine
    (temper_drc_rs), filtered to this check's name
    (``drc_trace_clearance``).

    Registered in ``temper_drc_rs::rules::create_default_registry()`` but
    not currently instantiated by ``drc_cli.py`` / ``drc_oracle.py``'s
    check lists — orphaned from Python wiring, not from the Rust engine.
    """

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
        _modified_regions: list[tuple[float, float, float, float]] | None = None,
    ) -> CheckResult:
        return _run_check_via_rust(self.name, placement, constraints)


class ViaSpacingCheck(Check):
    """Via spacing check — delegates to the Rust engine (temper_drc_rs),
    filtered to this check's name (``drc_via_spacing``).

    Registered in ``temper_drc_rs::rules::create_default_registry()`` but
    not currently instantiated by ``drc_cli.py`` / ``drc_oracle.py``'s
    check lists — orphaned from Python wiring, not from the Rust engine.
    """

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
        _modified_regions: list[tuple[float, float, float, float]] | None = None,
    ) -> CheckResult:
        return _run_check_via_rust(self.name, placement, constraints)


class NetConnectivityCheck(Check):
    """Net connectivity check — delegates to the Rust engine
    (temper_drc_rs), filtered to this check's name
    (``erc_net_connectivity``).

    2026-08-08 vacuity fix: prior to this, ``run()`` unconditionally
    returned ``passed=True`` while claiming to delegate. The Rust rule
    itself had the same defect (computed a real per-net connection tally
    and discarded it) and has now been implemented for real — it emits
    ``ERC_NET_001`` for any net with fewer than 2 connected components
    (see ``packages/temper-drc-rs/src/rules/erc/net_connectivity.rs``).
    This class now genuinely delegates to that.
    """

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
        _modified_regions: list[tuple[float, float, float, float]] | None = None,
    ) -> CheckResult:
        return _run_check_via_rust(self.name, placement, constraints)


class PowerDomainCheck(Check):
    """Power domain check — UNIMPLEMENTED; ``run()`` never delegates and
    never reports a pass.

    2026-08-08 vacuity fix: this class used to carry a docstring claiming
    Rust delegation while ``run()`` unconditionally hardcoded
    ``passed=True``. The truth is there is nothing to delegate to:
    ``erc_power_domain`` is deliberately NOT registered in
    ``temper_drc_rs::rules::create_default_registry()`` (see
    ``packages/temper-drc-rs/src/rules/erc/power_domain.rs``) because the
    native ``BoardState``/``Component`` schema carries no
    ``voltage_domain`` field at all — a real implementation needs a schema
    addition that is a human decision, not something to invent silently.

    ``run()`` now returns a not-run ``CheckResult``: ``passed=False`` (never
    ``True`` — a pass here would be indistinguishable from "ran and found
    zero violations", the exact defect being fixed) plus a single
    INFO-severity ``ERC_PWR_000`` issue (``details={"not_run": True}``)
    that marks it as not-run rather than "found a violation" (an
    ERROR/CRITICAL issue) — so a consumer inspecting severities, not just
    ``passed``, can also tell the three states apart: ran-clean,
    ran-and-failed, and did-not-run.
    """

    @property
    def name(self) -> str:
        return "erc_power_domain"

    @property
    def category(self) -> str:
        return "erc"

    @property
    def description(self) -> str:
        return (
            "UNIMPLEMENTED: identify nets connecting components from different "
            "voltage domains. The native Rust board schema has no voltage_domain "
            "field to check against, so this check does not run."
        )

    def run(
        self,
        _placement: Placement,
        _constraints: ConstraintSet,
        _modified_regions: list[tuple[float, float, float, float]] | None = None,
    ) -> CheckResult:
        return CheckResult(
            check_name=self.name,
            passed=False,
            issues=[
                Issue(
                    severity=Severity.INFO,
                    code="ERC_PWR_000",
                    message=(
                        "erc_power_domain did not run: the native Rust "
                        "BoardState/Component schema has no voltage_domain field, "
                        "so there is nothing to delegate to (deregistered in "
                        "packages/temper-drc-rs/src/rules/erc/power_domain.rs). "
                        "passed=False marks this as NOT-RUN -- it must not be read "
                        "as either a clean pass or a found violation."
                    ),
                    category=self.category,
                    check_name=self.name,
                    details={"not_run": True},
                )
            ],
        )


class FloatingPinsCheck(Check):
    """Floating pins check — delegates to the Rust engine (temper_drc_rs),
    filtered to this check's name (``erc_floating_pins``)."""

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
        _modified_regions: list[tuple[float, float, float, float]] | None = None,
    ) -> CheckResult:
        return _run_check_via_rust(self.name, placement, constraints)


class HVLVSeparationCheck(Check):
    """HV/LV separation check — delegates to the Rust engine
    (temper_drc_rs), filtered to this check's name
    (``safety_hv_lv_separation``)."""

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
        _modified_regions: list[tuple[float, float, float, float]] | None = None,
    ) -> CheckResult:
        return _run_check_via_rust(self.name, placement, constraints)


class CreepageCheck(Check):
    """Isolation-component package-size sanity check -- delegates to the
    Rust engine (temper_drc_rs), filtered to this check's name
    (``safety_creepage``).

    NOT a creepage (surface-path distance) measurement, despite the name
    kept here for API/registry stability. It checks one declared-isolation
    component's own package bounding box (``max(width, height)``) against
    a minimum size -- it never reads a second component's position and
    never computes a distance between conductors. See
    ``packages/temper-drc-rs/src/rules/safety/creepage.rs``'s header
    comment for the full explanation, and
    ``docs/evidence/2026-08-14-creepage-figure-integrity.md`` for how this
    was found. The real, IEC-60335-cited, currently-enforced creepage
    check for this board is ``scripts/generate_kicad_dru.py``'s generated
    ``.kicad_dru`` ``creepage`` constraint (kicad-cli DRC); the domain-
    pair/insulation-type-aware ``IEC60335_REQUIREMENTS`` matrix in
    ``packages/temper-placer/src/temper_placer/requirements/validators/
    clearance.py`` is a second, independently-sourced correct
    implementation. Consult those for a real creepage verdict, not this
    check's name.

    ``min_iso_width_mm`` is NOT forwarded to the Rust side: delegation runs
    the Rust registry's own registered ``CreepageCheck`` instance
    (constructed with a fixed 6.0mm minimum in
    ``temper_drc_rs::rules::create_default_registry()``), not a fresh one
    parameterized by this constructor arg. Kept for import/API compat and
    because it happens to match the Rust default; it does not currently
    change delegated behavior if overridden.
    """

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
        return "Isolation-component package-size sanity check (NOT a creepage/surface-path measurement -- see class docstring)."

    def run(
        self,
        placement: Placement,
        constraints: ConstraintSet,
        _modified_regions: list[tuple[float, float, float, float]] | None = None,
    ) -> CheckResult:
        return _run_check_via_rust(self.name, placement, constraints)


class IsolationCheck(Check):
    """Isolation check — delegates to the Rust engine (temper_drc_rs),
    filtered to this check's name (``safety_isolation``)."""

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
        _modified_regions: list[tuple[float, float, float, float]] | None = None,
    ) -> CheckResult:
        return _run_check_via_rust(self.name, placement, constraints)


class LoopAreaCheck(Check):
    """Loop area check — delegates to the Rust engine (temper_drc_rs),
    filtered to this check's name (``emc_loop_area``)."""

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
        _modified_regions: list[tuple[float, float, float, float]] | None = None,
    ) -> CheckResult:
        return _run_check_via_rust(self.name, placement, constraints)


class NoiseCouplingCheck(Check):
    """Noise coupling check — delegates to the Rust engine (temper_drc_rs),
    filtered to this check's name (``emc_noise_coupling``)."""

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
        _modified_regions: list[tuple[float, float, float, float]] | None = None,
    ) -> CheckResult:
        return _run_check_via_rust(self.name, placement, constraints)


class GroundPlaneCheck(Check):
    """Ground plane check — delegates to the Rust engine (temper_drc_rs),
    filtered to this check's name (``emc_ground_plane``)."""

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
        _modified_regions: list[tuple[float, float, float, float]] | None = None,
    ) -> CheckResult:
        return _run_check_via_rust(self.name, placement, constraints)
