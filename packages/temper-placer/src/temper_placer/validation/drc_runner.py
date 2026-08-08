"""
KiCad DRC runner — programmatic interface to kicad-cli DRC and Rust CheckRunner.

This module re-exports the kicad-cli DRC API from ``_drc_api`` (for backward
compatibility) and provides the ``CheckRunner`` that delegates to the Rust
DRC engine (``temper_drc_rs``).
"""

from __future__ import annotations

# =========================================================================
#  CheckRunner — delegates to the Rust DRC engine (temper_drc_rs)
#
#  Formerly in temper_drc.core.runner.  Preserves the same public
#  interface but calls ``temper_drc_rs.run_drc()`` under the hood.
#  Converts Python ``Placement`` / ``ConstraintSet`` objects into the
#  K1-schema dict format that the Rust engine expects, then maps
#  returned violation dicts back to Python ``CheckResult`` / ``Issue``
#  objects.
# =========================================================================
import time as _time
from dataclasses import dataclass as _dataclass
from dataclasses import field
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


def _placement_to_board_dict(placement: _Placement) -> dict[str, _Any]:
    """Convert a ``Placement`` to the K1-schema board dict."""
    components: list[dict[str, _Any]] = []
    for _ref, comp in placement.components.items():
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

    # NOTE (Python<->Rust boundary schema fix, 2026-08-08): `board_dict`
    # deliberately does NOT carry a "zones" key built from
    # ``placement.zones``. ``Placement.zones`` is a *placement-boundary*
    # map (``name -> (x0, y0, x1, y1)`` rectangles, e.g. the
    # ``temper_constraints.yaml`` ``power_zone``/``driver_zone`` regions) --
    # a completely different concept from the K1-schema ``board_dict["zones"]``
    # key, which ``temper_drc_rs.board_py_bridge::extract_copper_zone``
    # (`packages/temper-drc-rs/src/board_py_bridge.rs`) parses as
    # ``CopperZone`` records: ``{net, layer, polygon}`` -- actual copper
    # zone/pour geometry.
    #
    # Previously this function *did* populate "zones" from
    # ``placement.zones`` as ``{"name": ..., "bounds": [...]}`` -- a key
    # collision with the CopperZone shape. `extract_copper_zone` requires
    # "net" (`board_py_bridge.rs::extract_str`), so any call through this
    # path with a non-empty ``placement.zones`` (a legitimate, common state)
    # raised ``ValueError: missing required key: net`` deep in the Rust
    # deserializer, and ``CheckRunner.run()`` never returned a result at
    # all -- not just for zone-aware checks, for every check. Reproduced
    # live via ``temper_drc_rs.run_drc()`` before this fix.
    #
    # ``Placement`` carries no copper-pour geometry at all today, so there
    # is nothing correct to put under "zones" here yet -- omitting the key
    # (the K1 schema treats it as optional) is the fix, not a substitute
    # shape.
    board_dict: dict[str, _Any] = {
        "board": {
            "width_mm": placement.board_width,
            "height_mm": placement.board_height,
            "margin_mm": 3.0,
        },
        "components": components,
        "nets": dict(placement.nets),
        "net_classes": dict(placement.net_classes),
    }

    if placement.via_placement is not None:
        # `extract_via` (`board_py_bridge.rs:378`) requires "net" (a
        # required key, no default) plus "x"/"y" (each independently
        # defaulted to 0.0 when absent -- so this bug's discard was
        # *silent* for position, not just a hard "net" crash: an omitted
        # or misspelled x/y key would not raise, it would quietly place
        # every via at the origin) and reads pad diameter under "pad", not
        # "diameter". The previous shape here sent "position"/"diameter"/
        # "net_name" -- none of which `extract_via` reads -- so every
        # placement with vias raised "missing required key: net" before
        # any DRC rule ran. Fixed by sending the key names Rust actually
        # reads; `via.diameter` maps to Rust's "pad" (outer pad/land
        # diameter, not drill).
        via_list: list[dict[str, _Any]] = []
        for via in placement.via_placement.vias:
            via_list.append(
                {
                    "net": via.net_name,
                    "x": via.position[0],
                    "y": via.position[1],
                    "drill": via.drill,
                    "pad": via.diameter,
                    "from_layer": via.from_layer,
                    "to_layer": via.to_layer,
                }
            )
        board_dict["vias"] = via_list

    if placement.trace_placement is not None:
        # Same class of bug as "zones" above, on the same K1-schema
        # boundary: `board_py_bridge.rs::extract_trace_segment` requires
        # key "net" (not "net_name") and a "segments" list of
        # ``[x1, y1, x2, y2]`` coordinate groups (not top-level
        # "start"/"end" keys) -- see `board_py_bridge.rs:345-372`. The
        # previous shape here raised the identical
        # ``missing required key: net`` error whenever
        # ``placement.trace_placement`` was set, independent of the
        # "zones"/"vias" bugs above. One ``board_dict["traces"]`` entry
        # per raw segment (a "segments" list of length 1 each) keeps this
        # a minimal, cardinality-preserving fix rather than a regrouping.
        seg_list: list[dict[str, _Any]] = []
        for seg in placement.trace_placement.segments:
            seg_list.append(
                {
                    "net": seg.net_name,
                    "layer": seg.layer,
                    "width": seg.width,
                    "segments": [[seg.start[0], seg.start[1], seg.end[0], seg.end[1]]],
                }
            )
        board_dict["traces"] = seg_list

    return board_dict


def _constraints_to_dict(constraints: _ConstraintSet) -> dict[str, _Any]:
    """Convert a ``ConstraintSet`` to the dict format expected by ``temper_drc_rs``.

    NOTE (Python<->Rust boundary schema fix, 2026-08-08): this dict is
    deserialized by ``temper_drc_rs::constraints::build_constraint_set``
    (`packages/temper-drc-rs/src/constraints.rs`) into its serde
    ``ConstraintSet`` -- a *different* Rust type from the
    ``temper_drc_rs.ConstraintSet`` pyclass this function reads its input
    from (`drc_contracts.rs`, installed with dataclass-compat fields in
    ``drc_types.py``). The two share a name but not a field set, and this
    function is the marshalling point between them. It used to forward
    several pyclass fields the serde struct has no matching field for --
    each was a real, populated value that ``serde_json::from_value``
    silently dropped (no ``deny_unknown_fields``, the exact defect class
    this remediation closes):

    - ``zones[].bounds`` / ``zones[].components``: the pyclass
      ``ZoneDefinition`` has 4 fields (name, bounds, net_classes,
      components); the serde ``ZoneDefinition`` actually consumed here
      has only 2 (name, net_classes) -- confirmed no rule in
      ``packages/temper-drc-rs/src/rules/`` reads zone bounds/components
      from constraints at all (zone geometry reaches DRC rules via the K1
      ``board_dict["zones"]`` ``CopperZone`` list instead, a wholly
      separate mechanism -- see ``_placement_to_board_dict``'s "zones"
      NOTE above). Dropped rather than invented on the Rust side.
    - ``critical_loops[].description``: the serde ``LoopConstraint`` has
      no ``description`` field; no violation message renders it. Dropped.
    - ``component_groups``: the serde ``ConstraintSet`` has no matching
      field at all (confirmed: zero references anywhere in
      ``temper-drc-rs/src/``) -- component-group proximity constraints
      are consumed by the CP-SAT placer's preflight path
      (``_preflight_py_oracle.py``-style checks), never by the native DRC
      engine. Always silently discarded before; not sent at all now.
    - ``net_classes`` / ``voltage_domains`` (top-level): same -- no
      matching serde field, no native-engine consumer.
      ``voltage_domains`` mirrors the same documented native-schema gap
      as per-component ``voltage_domain`` (see
      ``rules/erc/power_domain.rs`` -- ``PowerDomainCheck`` is
      deliberately deregistered for exactly this reason).
    - ``board`` (nested ``{width_mm, height_mm}``): the serde
      ``ConstraintSet`` wants flat ``board_width``/``board_height`` keys.
      Dead either way today (no rule reads
      ``constraints.board_width``/``board_height``), but sent in the
      correct shape now instead of under a key the target struct doesn't
      have.

    None of the dropped keys were read by any native Rust DRC rule
    (verified by grep across ``constraints.rs`` and ``rules/``), so this
    is a shape correction, not a behavior change -- and it is what makes
    it safe to add ``#[serde(deny_unknown_fields)]`` to the serde
    ``ConstraintSet`` without breaking the production ``CheckRunner.run()``
    path.
    """
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
                "net_classes": z.net_classes,
            }
            for z in constraints.zones
        ],
        "critical_loops": [
            {
                "name": l.name,
                "nets": l.nets,
                "max_area_mm2": l.max_area_mm2,
                "weight": l.weight,
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
        "hv_clearance_mm": constraints.hv_clearance_mm,
        "board_width": constraints.board_width,
        "board_height": constraints.board_height,
    }


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


@_dataclass
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

    checks: list[_Check] = field(default_factory=list)

    def add_check(self, check: _Check) -> CheckRunner:
        """Add a single check (for import-compatibility; ignored by run)."""
        self.checks.append(check)
        return self

    def add_checks(self, checks: list[_Check]) -> CheckRunner:
        """Add multiple checks (for import-compatibility; ignored by run)."""
        self.checks.extend(checks)
        return self

    def clear(self) -> CheckRunner:
        """Remove all checks from the runner."""
        self.checks.clear()
        return self

    def get_checks_by_category(self, category: str) -> list[_Check]:
        """Get all checks in a specific category."""
        return [c for c in self.checks if c.category == category]

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

        Converts ``Placement`` / ``ConstraintSet`` to dicts, calls
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
        try:
            import temper_drc_rs  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ImportError(
                "The temper-drc Rust engine is required. Install it with: pip install temper-drc-rs"
            ) from exc

        board_dict = _placement_to_board_dict(placement)
        constraints_dict = _constraints_to_dict(constraints)

        start_time = _time.time()

        kwargs: dict[str, _Any] = {}
        if categories is not None:
            kwargs["categories"] = categories
        if check_names is not None:
            kwargs["check_names"] = check_names

        violation_dicts: list[dict[str, _Any]] = temper_drc_rs.run_drc(
            board_dict,
            constraints_dict,
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
