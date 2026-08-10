"""
KiCad DRC runner — programmatic interface to kicad-cli DRC and Rust CheckRunner.

This module re-exports the kicad-cli DRC API from ``_drc_api`` (for backward
compatibility) and provides the ``CheckRunner`` whose data surface delegates
to the Rust DRC engine (``temper_drc_rs``).

.. _drc-runner-u5-typed-marshal:

Phase-A U5 (rust-orchestration-engine plan) — typed marshalling
----------------------------------------------------------------

The two marshalers and the ``CheckRunner`` data surface are now Rust-side
(``packages/temper-drc-rs/src/drc_marshal.rs``):

- ``_placement_to_board_dict`` → ``temper_drc_rs.DrcBoardSnapshot.from_state``
- ``_constraints_to_dict``     → ``temper_drc_rs.TypedConstraintSet.from_state``
- ``CheckRunner`` dataclass    → ``temper_drc_rs.CheckRunner`` (checks list +
  data methods), wrapped here so the public API (``.checks``, ``.add_check``,
  ``.add_checks``, ``.clear``, ``.get_checks_by_category``, ``.check_names``,
  ``.categories``, ``.summary``) is unchanged.

**What stayed Python (with evidence):** ``CheckRunner.run()`` — it needs the
Python ``RunResult``/``CheckResult``/``Issue`` contract classes
(``drc_result.py``) and the kicad-cli subprocess path (``_drc_api.run_drc``),
so the execution is kept here while the marshalling moved to Rust. The old
dict-taking kernels (``temper_drc_rs.build_board_dict_py`` /
``build_constraints_dict_py`` / ``constraint_value_to_plain_py``) are retained
for the existing differential suite and external dict callers such as
``drc_ratchet.py``; ``run_drc`` accepts both the dict wire format and the new
typed structs.

The pre-migration marshaler bodies are pinned verbatim as ``_oracle_*`` blocks
in ``tests/validation/test_drc_marshal_rust_differential.py`` (G1).
"""

from __future__ import annotations

# =========================================================================
#  CheckRunner — delegates to the Rust DRC engine (temper_drc_rs)
#
#  Formerly in temper_drc.core.runner.  Preserves the same public
#  interface but calls ``temper_drc_rs.run_drc()`` under the hood with
#  the Phase-A U5 typed marshalling structs (DrcBoardSnapshot /
#  TypedConstraintSet), then maps returned violation dicts back to Python
#  ``CheckResult`` / ``Issue`` objects.
# =========================================================================
import time as _time
from typing import TYPE_CHECKING as _TYPE_CHECKING
from typing import Any as _Any

# Re-export the KiCad CLI DRC API from _drc_api (backward-compatible)
from temper_placer.validation._drc_api import (  # noqa: F401
    DrcError,
    DrcResult,
    DrcRunnerError,
    DrcWarning,
    is_kicad_cli_available,
    run_drc,
)
from temper_placer.validation.drc_result import (
    Check as _Check,
)
from temper_placer.validation.drc_result import (
    CheckResult as _CheckResult,
)
from temper_placer.validation.drc_result import (
    Issue as _Issue,
)
from temper_placer.validation.drc_result import (
    Location as _Location,
)
from temper_placer.validation.drc_result import (
    RunResult as _RunResult,
)
from temper_placer.validation.drc_result import (
    Severity as _Severity,
)

if _TYPE_CHECKING:
    from temper_placer.validation.drc_types import ConstraintSet as _ConstraintSet
    from temper_placer.validation.drc_types import Placement as _Placement

# Severity string → Severity enum
_SEVERITY_MAP: dict[str, _Severity] = {
    "INFO": _Severity.INFO,
    "WARNING": _Severity.WARNING,
    "ERROR": _Severity.ERROR,
    "CRITICAL": _Severity.CRITICAL,
}


def _placement_to_board_dict(placement: _Placement) -> _Any:
    """Convert a ``Placement`` to the typed ``DrcBoardSnapshot``.

    Phase-A U5: the marshalling body moved to Rust
    (``temper_drc_rs.DrcBoardSnapshot.from_state``). The function is kept as
    a compat shim for ``drc_result._run_check_via_rust()``; its return value
    is accepted directly by the polymorphic ``temper_drc_rs.run_drc``.
    """
    import temper_drc_rs as _tdrc_mod  # type: ignore[import-untyped]

    return _tdrc_mod.DrcBoardSnapshot.from_state(placement)


def _constraints_to_dict(constraints: _ConstraintSet) -> _Any:
    """Convert a ``ConstraintSet`` to the typed ``TypedConstraintSet``.

    Phase-A U5: the marshalling body moved to Rust
    (``temper_drc_rs.TypedConstraintSet.from_state``), including the
    documented field drops (zone bounds/components, loop description,
    component_groups, net_classes, voltage_domains — all fields the engine
    serde ``ConstraintSet`` has no matching field for; see the pre-migration
    body pinned in ``test_drc_marshal_rust_differential.py``).
    """
    import temper_drc_rs as _tdrc_mod  # type: ignore[import-untyped]

    return _tdrc_mod.TypedConstraintSet.from_state(constraints)


def _violations_to_run_result(
    violation_dicts: list[dict[str, _Any]],
    elapsed_ms: float = 0.0,
) -> _RunResult:
    """Convert a list of Rust DRC violation dicts to a ``RunResult``.

    Wave 4 Phase 4: the grouping + normalization compute (group by
    ``check_name`` preserving first-seen order, sort groups by name,
    severity normalization with the ERROR fallback) runs in the shared Rust
    kernel ``temper_drc_rs.group_violations`` (also consumed by
    ``drc_oracle._violations_to_run_result``). The per-group failure flag is
    recomputed here from the normalized severity (the kernel emits no
    ``has_failure`` — dead-output removal, adversarial-review pass 2). This
    wrapper only marshals the normalized records back into the
    ``CheckResult``/``Issue`` contract objects.
    """
    import temper_drc_rs  # type: ignore[import-untyped]

    check_results: list[_CheckResult] = []
    for check_name, records in temper_drc_rs.group_violations(violation_dicts):
        issues: list[_Issue] = []
        has_failure = False
        for v in records:
            severity = _SEVERITY_MAP[v["severity"]]
            if severity in (_Severity.ERROR, _Severity.CRITICAL):
                has_failure = True

            loc_dict = v["location"]
            location = None
            if loc_dict is not None:
                location = _Location(
                    x=loc_dict.get("x"),
                    y=loc_dict.get("y"),
                    layer=loc_dict.get("layer"),
                )

            issues.append(
                _Issue(
                    severity=severity,
                    code=v["code"],
                    message=v["message"],
                    category=v["category"],
                    check_name=check_name,
                    affected_items=v["affected_items"],
                    location=location,
                    details=v["details"],
                )
            )

        check_results.append(
            _CheckResult(
                check_name=check_name,
                passed=not has_failure,
                issues=issues,
            )
        )

    return _RunResult(check_results=check_results, total_elapsed_ms=elapsed_ms)


def _new_rust_runner() -> _Any:
    """Construct the Rust ``CheckRunner`` data surface (lazy import)."""
    import temper_drc_rs as _tdrc_mod  # type: ignore[import-untyped]

    return _tdrc_mod.CheckRunner()


class CheckRunner:
    """
    Orchestrates running multiple checks — delegates to the Rust DRC engine.

    Phase-A U5: the data surface (the ``checks`` list and its methods) is
    the Rust ``temper_drc_rs.CheckRunner`` pyclass; this class is a thin
    shim that preserves the public API. Actual check execution is done by
    ``temper_drc_rs.run_drc()`` with the typed marshalling structs.

    Example::

        runner = CheckRunner()
        result = runner.run(placement, constraints)

        if not result.passed:
            for issue in result.all_issues:
                print(f"[{issue.code}] {issue.message}")
    """

    def __init__(self) -> None:
        self._runner = _new_rust_runner()

    @property
    def checks(self) -> _Any:
        """The live checks list (the Rust runner's own list object)."""
        return self._runner.checks

    def add_check(self, check: _Check) -> CheckRunner:
        """Add a single check (for import-compatibility; ignored by run)."""
        self._runner.add_check(check)
        return self

    def add_checks(self, checks: list[_Check]) -> CheckRunner:
        """Add multiple checks (for import-compatibility; ignored by run)."""
        self._runner.add_checks(checks)
        return self

    def clear(self) -> CheckRunner:
        """Remove all checks from the runner."""
        self._runner.clear()
        return self

    def get_checks_by_category(self, category: str) -> list[_Check]:
        """Get all checks in a specific category."""
        return list(self._runner.get_checks_by_category(category))

    def run(  # noqa: ARG002
        self,
        placement: _Placement,
        constraints: _ConstraintSet,
        categories: list[str] | None = None,
        check_names: list[str] | None = None,
        modified_regions: list[tuple[float, float, float, float]] | None = None,
    ) -> _RunResult:
        """
        Run DRC checks via the Rust engine.

        Converts ``Placement`` / ``ConstraintSet`` to the Phase-A U5 typed
        structs (``DrcBoardSnapshot`` / ``TypedConstraintSet``), calls
        ``temper_drc_rs.run_drc()``, and maps the returned violation dicts
        to Python ``CheckResult`` objects.

        ``modified_regions`` is part of this method's keyword API —
        ``drc_fence.py:222`` passes it by name. **Do not re-prefix it with an
        underscore.** A ruff ARG002 autofix did exactly that, and every
        ``DRCFence`` invocation raised ``TypeError`` as a result; see
        ``docs/evidence/2026-07-26-api-signature-drift-gate.md``.

        KNOWN GAP, deliberately not closed here: the parameter is **accepted
        and ignored** — it appears nowhere else in this module. Callers pass
        modified regions expecting incremental, region-scoped re-checking, and
        get a full re-check instead. That is conservative rather than unsafe
        (nothing goes unchecked), but the intended incremental speed-up is not
        happening. Wiring it through to ``run_drc()`` is a behaviour change and
        is scoped as a follow-up, not folded into a signature repair.
        """
        del modified_regions  # inherited unused arg (baseline debt)
        import temper_drc_rs  # type: ignore[import-untyped]

        snapshot = _placement_to_board_dict(placement)
        typed_constraints = _constraints_to_dict(constraints)

        start_time = _time.time()

        kwargs: dict[str, _Any] = {}
        if categories is not None:
            kwargs["categories"] = categories
        if check_names is not None:
            kwargs["check_names"] = check_names

        violation_dicts: list[dict[str, _Any]] = temper_drc_rs.run_drc(
            snapshot,
            typed_constraints,
            **kwargs,
        )

        elapsed_ms = (_time.time() - start_time) * 1000
        return _violations_to_run_result(violation_dicts, elapsed_ms=elapsed_ms)

    def run_single(
        self,
        check_name: str,
        placement: _Placement,
        constraints: _ConstraintSet,
    ) -> _CheckResult | None:
        """Run a single check by name via the Rust engine."""
        result = self.run(
            placement,
            constraints,
            check_names=[check_name],
        )
        for cr in result.check_results:
            if cr.check_name == check_name:
                return cr
        return None

    @property
    def check_names(self) -> list[str]:
        """List of all check names in this runner."""
        return list(self._runner.check_names)

    @property
    def categories(self) -> set[str]:
        """Set of all categories represented in this runner."""
        return set(self._runner.categories)

    def summary(self) -> str:
        """Get a summary of registered checks."""
        return self._runner.summary()
