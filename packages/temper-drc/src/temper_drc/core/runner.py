"""Check runner — now delegates to the Rust DRC engine (temper_drc_rs).

This module exists for backward compatibility.  The ``CheckRunner`` preserves
the same public interface but calls ``temper_drc_rs.run_drc()`` under the hood.
It converts the Python ``Placement`` / ``ConstraintSet`` objects into the
K1-schema dict format that the Rust engine expects, then maps returned
violation dicts back to Python ``CheckResult`` / ``Issue`` objects.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from temper_drc.core.check import Check
from temper_drc.core.result import CheckResult, Issue, Location, RunResult
from temper_drc.core.severity import Severity

if TYPE_CHECKING:
    from temper_drc.input.constraints import ConstraintSet
    from temper_drc.input.placement import Placement

# ---------------------------------------------------------------------------
# Severity string → Severity enum
# ---------------------------------------------------------------------------
_SEVERITY_MAP: dict[str, Severity] = {
    "INFO": Severity.INFO,
    "WARNING": Severity.WARNING,
    "ERROR": Severity.ERROR,
    "CRITICAL": Severity.CRITICAL,
}


# ---------------------------------------------------------------------------
# Dict conversion helpers  (K1 schema)
# ---------------------------------------------------------------------------


def _placement_to_board_dict(placement: Placement) -> dict[str, Any]:
    """Convert a ``Placement`` to the K1-schema board dict."""
    components: list[dict[str, Any]] = []
    for ref, comp in placement.components.items():
        side = "bottom" if comp.layer and "B" in (comp.layer or "") else "top"
        components.append(
            {
                "ref": comp.ref,
                "x": comp.x,
                "y": comp.y,
                "rot": comp.rotation,
                "side": side,
                "width": comp.width,
                "height": comp.height,
                "net_class": comp.net_class,
                "voltage_domain": comp.voltage_domain,
                "package_type": "smd",
                "power_dissipation_w": None,
                "is_magnetic": False,
                "is_electrolytic": False,
                "vent_direction": None,
                "footprint_polygon": None,
            }
        )

    zones_list: list[dict[str, Any]] = []
    for name, bounds in placement.zones.items():
        zones_list.append({"name": name, "bounds": list(bounds)})

    board_dict: dict[str, Any] = {
        "board": {
            "width_mm": placement.board_width,
            "height_mm": placement.board_height,
            "margin_mm": 3.0,
        },
        "components": components,
        "nets": dict(placement.nets),
        "net_classes": dict(placement.net_classes),
        "zones": zones_list,
    }

    # Include via/trace placement if present (optional — set by fence adapters)
    if placement.via_placement is not None:
        via_list: list[dict[str, Any]] = []
        for via in placement.via_placement.vias:
            via_list.append(
                {
                    "position": list(via.position),
                    "from_layer": via.from_layer,
                    "to_layer": via.to_layer,
                    "diameter": via.diameter,
                    "drill": via.drill,
                    "net_name": via.net_name,
                }
            )
        board_dict["vias"] = via_list

    if placement.trace_placement is not None:
        seg_list: list[dict[str, Any]] = []
        for seg in placement.trace_placement.segments:
            seg_list.append(
                {
                    "net_name": seg.net_name,
                    "layer": seg.layer,
                    "width": seg.width,
                    "start": list(seg.start),
                    "end": list(seg.end),
                }
            )
        board_dict["traces"] = seg_list

    return board_dict


def _constraints_to_dict(constraints: ConstraintSet) -> dict[str, Any]:
    """Convert a ``ConstraintSet`` to the dict format expected by ``temper_drc_rs``."""
    return {
        "clearances": [
            {
                "from_class": r.from_class,
                "to_class": r.to_class,
                "clearance_mm": r.min_mm,
                "description": r.description,
            }
            for r in constraints.clearances
        ],
        "zones": [
            {
                "name": z.name,
                "bounds": list(z.bounds),
                "net_classes": z.net_classes,
                "components": z.components,
            }
            for z in constraints.zones
        ],
        "critical_loops": [
            {
                "name": l.name,
                "nets": l.nets,
                "max_area_mm2": l.max_area_mm2,
                "weight": l.weight,
                "description": l.description,
            }
            for l in constraints.critical_loops
        ],
        "thermal_constraints": [
            {
                "components": t.components,
                "prefer_edge": t.prefer_edge,
                "min_spacing_mm": t.min_spacing_mm,
                "max_distance_from_edge_mm": t.max_distance_from_edge_mm,
                "description": t.description,
            }
            for t in constraints.thermal_constraints
        ],
        "component_groups": [
            {
                "name": g.name,
                "components": g.components,
                "max_spread_mm": g.max_spread_mm,
                "zone": g.zone,
                "description": g.description,
            }
            for g in constraints.component_groups
        ],
        "net_classes": dict(constraints.net_classes),
        "voltage_domains": dict(constraints.voltage_domains),
        "hv_clearance_mm": constraints.hv_clearance_mm,
        "board": {
            "width_mm": constraints.board_width,
            "height_mm": constraints.board_height,
        },
    }


def _violations_to_run_result(
    violation_dicts: list[dict[str, Any]],
    elapsed_ms: float = 0.0,
) -> RunResult:
    """Convert a list of Rust DRC violation dicts to a ``RunResult``.

    Groups violations by ``check_name`` and wraps each group into a
    ``CheckResult`` so existing Python consumers (loss functions, CI
    reports, formatters) can consume Rust DRC output transparently.
    """
    # Group by check_name
    grouped: dict[str, list[dict[str, Any]]] = {}
    for v in violation_dicts:
        name = v.get("check_name", "unknown")
        grouped.setdefault(name, []).append(v)

    check_results: list[CheckResult] = []
    for check_name, violations in sorted(grouped.items()):
        issues: list[Issue] = []
        has_failure = False
        for v in violations:
            severity_str = v.get("severity", "ERROR").upper()
            severity = _SEVERITY_MAP.get(severity_str, Severity.ERROR)
            if severity in (Severity.ERROR, Severity.CRITICAL):
                has_failure = True

            # Build Location (optional)
            loc_dict = v.get("location")
            location = None
            if loc_dict is not None and isinstance(loc_dict, dict):
                location = Location(
                    x=loc_dict.get("x"),
                    y=loc_dict.get("y"),
                    layer=loc_dict.get("layer"),
                )

            issue = Issue(
                severity=severity,
                code=v.get("code", "DRC_RS_000"),
                message=v.get("message", ""),
                category=v.get("category", "drc"),
                check_name=check_name,
                affected_items=v.get("affected_items", []),
                location=location,
                details=v.get("details", {}),
            )
            issues.append(issue)

        check_results.append(
            CheckResult(
                check_name=check_name,
                passed=not has_failure,
                issues=issues,
            )
        )

    return RunResult(check_results=check_results, total_elapsed_ms=elapsed_ms)


# ---------------------------------------------------------------------------
# CheckRunner
# ---------------------------------------------------------------------------


@dataclass
class CheckRunner:
    """
    Orchestrates running multiple checks — delegates to the Rust DRC engine.

    The runner preserves the same public interface as before but ignores
    the Python ``Check`` subclasses (they are kept as import-compatibility
    stubs).  Actual check execution is done by ``temper_drc_rs.run_drc()``.

    Example::

        runner = CheckRunner()
        result = runner.run(placement, constraints)

        if not result.passed:
            for issue in result.all_issues:
                print(f"[{issue.code}] {issue.message}")
    """

    checks: list[Check] = field(default_factory=list)

    # NOTE: on_check_start / on_check_complete are no longer per-check.
    # They are kept as attributes for API compatibility but are no longer
    # invoked by ``run()`` — the Rust engine handles all execution.

    def add_check(self, check: Check) -> CheckRunner:
        """Add a single check (for import-compatibility; ignored by run)."""
        self.checks.append(check)
        return self

    def add_checks(self, checks: list[Check]) -> CheckRunner:
        """Add multiple checks (for import-compatibility; ignored by run)."""
        self.checks.extend(checks)
        return self

    def clear(self) -> CheckRunner:
        """Remove all checks from the runner."""
        self.checks.clear()
        return self

    def get_checks_by_category(self, category: str) -> list[Check]:
        """Get all checks in a specific category."""
        return [c for c in self.checks if c.category == category]

    def run(
        self,
        placement: Placement,
        constraints: ConstraintSet,
        categories: list[str] | None = None,
        check_names: list[str] | None = None,
        modified_regions: list[tuple[float, float, float, float]] | None = None,
    ) -> RunResult:
        """
        Run DRC checks via the Rust engine.

        Converts ``Placement`` / ``ConstraintSet`` to dicts, calls
        ``temper_drc_rs.run_drc()``, and maps the returned violation dicts
        to Python ``CheckResult`` objects.

        Args:
            placement: Component placement data.
            constraints: PCL constraint set.
            categories: Optional list of categories to run (e.g., ``["drc", "safety"]``).
            check_names: Optional list of specific check names (passed to Rust engine).
            modified_regions: Not supported by Rust engine; ignored.

        Returns:
            RunResult with all check results and aggregate metrics.
        """
        # Lazy import — the Rust bridge may not be installed at import time.
        try:
            import temper_drc_rs  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ImportError(
                "The temper-drc Rust engine is required. "
                "Install it with: pip install temper-drc-rs"
            ) from exc

        board_dict = _placement_to_board_dict(placement)
        constraints_dict = _constraints_to_dict(constraints)

        start_time = time.time()

        # Build kwargs — only pass parameters the Rust bridge understands.
        kwargs: dict[str, Any] = {}
        if categories is not None:
            kwargs["categories"] = categories
        if check_names is not None:
            kwargs["check_names"] = check_names

        violation_dicts: list[dict[str, Any]] = temper_drc_rs.run_drc(
            board_dict,
            constraints_dict,
            **kwargs,
        )

        elapsed_ms = (time.time() - start_time) * 1000
        return _violations_to_run_result(violation_dicts, elapsed_ms=elapsed_ms)

    def run_single(
        self,
        check_name: str,
        placement: Placement,
        constraints: ConstraintSet,
    ) -> CheckResult | None:
        """
        Run a single check by name via the Rust engine.

        Args:
            check_name: Name of the check to run.
            placement: Component placement data.
            constraints: PCL constraint set.

        Returns:
            CheckResult if the check ran, or ``None`` if not found.
        """
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
        return [c.name for c in self.checks]

    @property
    def categories(self) -> set[str]:
        """Set of all categories represented in this runner."""
        return {c.category for c in self.checks}

    def summary(self) -> str:
        """Get a summary of registered checks."""
        lines = [f"CheckRunner with {len(self.checks)} checks:"]

        by_category: dict[str, list[str]] = {}
        for check in self.checks:
            if check.category not in by_category:
                by_category[check.category] = []
            by_category[check.category].append(check.name)

        for category, names in sorted(by_category.items()):
            lines.append(f"  {category.upper()}: {', '.join(names)}")

        return "\n".join(lines)
