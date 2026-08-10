"""
DRCOracle: Batch DRC evaluator using temper-drc composable checks (or Rust engine).

Provides a DRCOracle class that wraps temper_drc.CheckRunner for batch
placement evaluation. Not to be confused with routing.constraints.drc_oracle.DRCOracle
which serves real-time track/via clearance queries.

This oracle:
- Converts temper-placer Netlist/Board data into temper_drc.input.Placement + ConstraintSet
- Runs the full temper-drc check suite (DRC, Safety, EMC, ERC)
- Returns RunResult with aggregate penalty
- Optionally uses the Rust DRC engine (temper_drc_rs) for improved performance

Graceful degradation: If temper-drc is not installed, the factory function raises
ImportError with a clear message. If temper_drc_rs is not installed, the Rust
backend is unavailable but the Python backend still works.
"""

from __future__ import annotations

from typing import TypeAlias

import numpy as np

Array: TypeAlias = np.ndarray  # numpy alias replacing JAX Array post-JAX retirement

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from temper_placer.validation.drc_result import RunResult
    from temper_placer.validation.drc_types import ConstraintSet as DrcConstraintSet
    from temper_placer.validation.drc_types import Placement as DrcPlacement

try:
    import temper_drc_rs

    _HAS_RUST_DRC = True
except ImportError:
    _HAS_RUST_DRC = False

_RS = None


def _rs() -> Any:
    """Lazily import the Rust kernel module."""
    global _RS
    if _RS is None:
        import temper_drc_rs  # type: ignore[import-untyped]

        _RS = temper_drc_rs
    return _RS


def _constraint_value_to_plain(value: Any) -> Any:
    """Convert a ``constraints_config`` field into the plain
    dict/list/str/int/float/bool/None shape ``temper_drc_rs.run_drc()``
    understands.

    Delegates to the Rust kernel ``temper_drc_rs.constraint_value_to_plain_py``
    (Wave 4 marshalling-boundary migration).  Falls back to the verbatim
    pure-Python implementation when the Rust extension is not available — the
    module's graceful-degradation contract for extension-absent callers
    (e.g. ``test_isolation_barrier_wiring.py`` in its
    ``pytest.importorskip``-absent path).
    """
    if _HAS_RUST_DRC:
        return _rs().constraint_value_to_plain_py(value)
    # Pure-Python fallback (verbatim pre-migration body).
    from pydantic import BaseModel  # noqa: PLC0415

    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, (list, tuple)):
        return [_constraint_value_to_plain(v) for v in value]
    return value


def _infer_package_type(footprint: str | None) -> str:
    """Infer SMD package type from footprint name.

    Heuristic used by both the placer-path and parsed-PCB-path
    board-dict builders.

    Wave 4 Phase 4: with the Rust extension present, delegates to the Rust
    kernel ``temper_drc_rs.infer_package_type`` (verbatim first-match
    keyword-order port, case-insensitive substring matching, None/empty →
    "smd"; pinned by the differential suite
    ``test_drc_oracle_rust_differential.py``). Without the extension
    (``_HAS_RUST_DRC=False``), falls back to the verbatim pre-migration
    pure-Python body — the module's graceful-degradation contract, which
    the parsed-PCB dict-builder path (``ci_closure_test.py``) depends on
    extension-absent (adversarial-review pass 2 restored this after the
    migration had introduced a hard runtime dependency on ``_rs()``).
    """
    if _HAS_RUST_DRC:
        return _rs().infer_package_type(footprint)
    fp_lower = footprint.lower() if footprint else ""
    if any(p in fp_lower for p in ("tht", "through", "pin", "dip")):
        return "tht"
    if "to-247" in fp_lower or "to247" in fp_lower:
        return "to247"
    if "to-220" in fp_lower or "to220" in fp_lower:
        return "to220"
    if "bga" in fp_lower:
        return "bga"
    if "qfn" in fp_lower:
        return "qfn"
    if "qfp" in fp_lower or "tqfp" in fp_lower:
        return "qfp"
    if "dpak" in fp_lower or "d2pak" in fp_lower:
        return "dpak"
    return "smd"


def build_placement_from_netlist(
    positions: Array,
    context: Any,
) -> DrcPlacement:
    """Convert temper-placer Netlist + positions into a temper_drc.input.Placement.

    Maps each Component to ComponentPlacement:
    - ref, footprint, width, height, net_class from netlist components
    - x, y from positions array
    - rotation from initial_rotation if available (converted from quantized 0-3 to degrees)
    - layer from initial_side (0=F.Cu, 1=B.Cu)
    - voltage_domain set to None (not present on temper-placer Component)
    """
    from temper_placer.validation.drc_types import ComponentPlacement, Placement

    netlist = context.netlist
    components: dict[str, ComponentPlacement] = {}

    for i, c in enumerate(netlist.components):
        x = float(positions[i, 0])
        y = float(positions[i, 1])

        width = c.width
        height = c.height

        rotation = 0.0
        if c.initial_rotation is not None:
            rotation = float(c.initial_rotation * 90)

        layer = "F.Cu"
        if c.initial_side is not None and c.initial_side == 1:
            layer = "B.Cu"

        comp = ComponentPlacement(
            ref=c.ref,
            footprint=c.footprint,
            x=x,
            y=y,
            rotation=rotation,
            layer=layer,
            width=width,
            height=height,
            net_class=c.net_class,
            voltage_domain=None,
        )
        components[c.ref] = comp

    return Placement(
        components=components,
        board_width=context.board.width,
        board_height=context.board.height,
    )


def build_constraint_set(context: Any) -> DrcConstraintSet:
    """Convert temper-placer clearance_rules into a temper_drc.input.ConstraintSet.

    Maps temper_placer.losses.types.ClearanceRule (net_class_a, net_class_b,
    min_clearance) to temper_drc.input.constraints.ClearanceRule (from_class,
    to_class, min_mm).
    """
    from temper_placer.validation.drc_types import ClearanceRule, ConstraintSet

    clearances: list[ClearanceRule] = []
    for rule in context.clearance_rules:
        clearances.append(
            ClearanceRule(
                from_class=rule.net_class_a,
                to_class=rule.net_class_b,
                min_mm=rule.min_clearance,
                description=getattr(rule, "because", ""),
            )
        )

    return ConstraintSet(
        clearances=clearances,
        board_width=context.board.width,
        board_height=context.board.height,
    )


@dataclass
class DRCOracle:
    """Batch DRC evaluator using temper-drc composable checks (or Rust engine).

    Not to be confused with routing.constraints.drc_oracle.DRCOracle,
    which serves real-time track/via clearance queries.

    Pre-builds static lookup maps at construction from the netlist.
    The ConstraintSet is built once and cached (net classes and
    clearance rules are static for a design).

    Attributes:
        runner: Configured CheckRunner with all desired checks.
        constraints: Pre-built ConstraintSet (static for the design).
        net_class_map: component_ref → net_class.
        footprint_map: component_ref → footprint_name.
        layer_map: component_ref → layer.
    """

    runner: object  # temper_drc.core.runner.CheckRunner
    constraints: object  # temper_drc.input.constraints.ConstraintSet
    net_class_map: dict[str, str]
    footprint_map: dict[str, str]
    layer_map: dict[str, str]

    def evaluate(
        self,
        positions: Array,
        context: Any,
        categories: list[str] | None = None,
        use_rust: bool = True,
    ) -> RunResult:
        """Convert positions to Placement, run checks, return RunResult.

        Optionally uses the Rust DRC engine (temper_drc_rs) for improved
        performance. Falls back to the Python CheckRunner if the Rust
        engine is unavailable or use_rust is False.

        Args:
            positions: (N, 2) array of component positions in mm.
            context: Object with netlist and board (duck-typed).
            categories: Optional list of check categories to run
                (e.g. ["drc", "safety"]). None means all categories.
            use_rust: If True and temper_drc_rs is installed, use the
                Rust DRC engine instead of the Python CheckRunner.
                Defaults to True for strangler-fig migration (K3).

        Returns:
            RunResult with per-check results and aggregate metrics.
        """
        if use_rust and _HAS_RUST_DRC:
            board_dict = self._build_board_dict(positions, context)
            constraints_dict = self._build_constraints_dict(context)
            # @req(U9, R1): Call temper_drc_rs.run_drc() instead of Python CheckRunner
            violation_dicts = temper_drc_rs.run_drc(
                board_dict,
                constraints_dict,
                categories=categories,
            )
            return self._violations_to_run_result(violation_dicts)
        # Fallback: existing Python path
        placement = build_placement_from_netlist(positions, context)
        return self.runner.run(placement, self.constraints, categories=categories)  # type: ignore[attr-defined]

    def evaluate_placement(
        self,
        placement: DrcPlacement,
        categories: list[str] | None = None,
    ) -> RunResult:
        """Evaluate a pre-built Placement (useful for testing).

        Args:
            placement: Pre-built temper_drc.input.Placement.
            categories: Optional list of check categories.

        Returns:
            RunResult with per-check results and aggregate metrics.
        """
        return self.runner.run(placement, self.constraints, categories=categories)  # type: ignore[attr-defined]

    # ------------------------------------------------------------------
    # Board dict builders (K1 schema)
    # ------------------------------------------------------------------

    def _build_board_dict(
        self,
        positions: Array,
        context: Any,
        parsed_pcb: Any = None,
    ) -> dict[str, Any]:
        """Build a K1-schema board dict from positions + context.

        Delegates to the Rust kernel ``temper_drc_rs.build_board_dict_py``
        or ``temper_drc_rs.build_board_dict_from_parsed_pcb_py`` (Wave 4
        marshalling-boundary migration).

        When ``parsed_pcb`` is provided, delegates to the parsed-PCB path
        (ignoring positions/context).  This allows callers like
        ``ci_closure_test.py`` to reuse the same dict builder for either
        placer output or a static KiCad-parsed board.

        Returns:
            dict matching the K1 schema (see plan §K1).
        """
        rs = _rs()
        if parsed_pcb is not None:
            return dict(rs.build_board_dict_from_parsed_pcb_py(parsed_pcb))
        return dict(
            rs.build_board_dict_py(
                positions=positions,
                netlist=context.netlist,
                board_width=float(context.board.width),
                board_height=float(context.board.height),
                board_margin=float(context.board_margin),
                clearance_rules=context.clearance_rules,
            )
        )

    @staticmethod
    def _build_board_dict_from_parsed_pcb(
        parsed_pcb: Any,
    ) -> dict[str, Any]:
        """Build a K1-schema board dict from a ParsedPCB object.

        Delegates to the Rust kernel
        ``temper_drc_rs.build_board_dict_from_parsed_pcb_py`` (Wave 4
        marshalling-boundary migration).

        Args:
            parsed_pcb: A ``ParsedPCB`` instance (from
                ``temper_placer.router_v6.stage0_data``).

        Returns:
            dict matching the K1 schema.
        """
        return dict(_rs().build_board_dict_from_parsed_pcb_py(parsed_pcb))

    def _build_constraints_dict(
        self,
        context: Any,
    ) -> dict[str, Any]:
        """Build a constraints dict for the Rust DRC engine.

        Delegates to the Rust kernel
        ``temper_drc_rs.build_constraints_dict_py`` (Wave 4 marshalling-
        boundary migration).

        Returns:
            dict matching the ConstraintSet serde schema.
        """
        config = getattr(context, "constraints_config", None)
        return dict(
            _rs().build_constraints_dict_py(
                clearance_rules=context.clearance_rules,
                constraints_config=config,
                board_width=float(context.board.width),
                board_height=float(context.board.height),
            )
        )

    @staticmethod
    def _violations_to_run_result(
        violation_dicts: list[dict[str, Any]],
    ) -> RunResult:
        """Convert a list of Rust DRC violation dicts to a RunResult.

        Groups violations by ``check_name`` and wraps each group into a
        ``CheckResult``.  This allows existing Python consumers (loss
        functions, CI reports) to consume Rust DRC output transparently.

        Wave 4 Phase 4: the grouping + severity-normalization compute runs
        in the shared Rust kernel ``temper_drc_rs.group_violations`` (also
        consumed by ``drc_runner._violations_to_run_result``); this wrapper
        only marshals the normalized records into the contract objects.

        Args:
            violation_dicts: List of violation dicts from
                ``temper_drc_rs.run_drc()``, each with keys:
                severity, code, message, category, check_name,
                affected_items, location, details.

        Returns:
            RunResult consumable by temper_drc consumers.
        """
        # Lazy import to avoid hard dependency on temper_drc
        from temper_placer.validation.drc_result import (
            CheckResult,
            Issue,
            Location,
            RunResult,
            Severity,
        )

        _SEVERITY_MAP = {
            "INFO": Severity.INFO,
            "WARNING": Severity.WARNING,
            "ERROR": Severity.ERROR,
            "CRITICAL": Severity.CRITICAL,
        }

        # --- Group by check_name (Rust kernel) ---
        check_results: list[CheckResult] = []
        for check_name, records in _rs().group_violations(violation_dicts):
            issues: list[Issue] = []
            has_failure = False
            for v in records:
                severity = _SEVERITY_MAP[v["severity"]]
                if severity in (Severity.ERROR, Severity.CRITICAL):
                    has_failure = True

                # Build Location
                loc_dict = v["location"]
                location = None
                if loc_dict is not None:
                    location = Location(
                        x=loc_dict.get("x"),
                        y=loc_dict.get("y"),
                        layer=loc_dict.get("layer"),
                    )

                issues.append(
                    Issue(
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
                CheckResult(
                    check_name=check_name,
                    passed=not has_failure,
                    issues=issues,
                )
            )

        return RunResult(check_results=check_results)


def create_standard_drc_oracle(context: Any) -> DRCOracle:
    """Create a DRCOracle pre-loaded with all 12 standard temper-drc checks.

    The oracle is configured with:
    - All DRC checks: component_overlap, courtyard, clearance, zone_containment
    - All Safety checks: creepage, hv_lv_separation, isolation
    - All EMC checks: noise_coupling, loop_area, ground_plane
    - All ERC checks: floating_pins, net_connectivity, power_domain

    Args:
        context: Object with netlist and clearance_rules (duck-typed).

    Returns:
        Configured DRCOracle instance.

    Raises:
        ImportError: If temper-drc is not installed.
    """
    try:
        from temper_placer.validation.drc_result import (
            ClearanceCheck,
            ComponentOverlapCheck,
            CourtyardCheck,
            CreepageCheck,
            FloatingPinsCheck,
            GroundPlaneCheck,
            HVLVSeparationCheck,
            IsolationCheck,
            LoopAreaCheck,
            NetConnectivityCheck,
            NoiseCouplingCheck,
            PowerDomainCheck,
            ZoneContainmentCheck,
        )
        from temper_placer.validation.drc_runner import CheckRunner
    except ImportError as e:
        raise ImportError(
            "temper-drc is not installed. Install it with: pip install temper-placer"
        ) from e

    runner = CheckRunner()
    runner.add_checks(
        [
            ComponentOverlapCheck(),
            CourtyardCheck(),
            ClearanceCheck(),
            ZoneContainmentCheck(),
            CreepageCheck(),
            HVLVSeparationCheck(),
            IsolationCheck(),
            NoiseCouplingCheck(),
            LoopAreaCheck(),
            GroundPlaneCheck(),
            FloatingPinsCheck(),
            NetConnectivityCheck(),
            PowerDomainCheck(),
        ]
    )

    constraints = build_constraint_set(context)

    netlist = context.netlist
    net_class_map: dict[str, str] = {}
    footprint_map: dict[str, str] = {}
    layer_map: dict[str, str] = {}

    for c in netlist.components:
        net_class_map[c.ref] = c.net_class
        footprint_map[c.ref] = c.footprint
        layer = "F.Cu"
        if c.initial_side is not None and c.initial_side == 1:
            layer = "B.Cu"
        layer_map[c.ref] = layer

    return DRCOracle(
        runner=runner,
        constraints=constraints,
        net_class_map=net_class_map,
        footprint_map=footprint_map,
        layer_map=layer_map,
    )
