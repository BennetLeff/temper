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

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from jax import Array

if TYPE_CHECKING:
    from temper_placer.validation.drc_result import RunResult
    from temper_placer.validation.drc_types import ConstraintSet as DrcConstraintSet
    from temper_placer.validation.drc_types import Placement as DrcPlacement

    from temper_placer.losses.base import LossContext

try:
    import temper_drc_rs

    _HAS_RUST_DRC = True
except ImportError:
    _HAS_RUST_DRC = False


def _infer_package_type(footprint: str | None) -> str:
    """Infer SMD package type from footprint name.

    Heuristic used by both the placer-path and parsed-PCB-path
    board-dict builders.
    """
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
    context: LossContext,
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


def build_constraint_set(context: LossContext) -> DrcConstraintSet:
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
        context: LossContext,
        categories: list[str] | None = None,
        use_rust: bool = True,
    ) -> RunResult:
        """Convert positions to Placement, run checks, return RunResult.

        Optionally uses the Rust DRC engine (temper_drc_rs) for improved
        performance. Falls back to the Python CheckRunner if the Rust
        engine is unavailable or use_rust is False.

        Args:
            positions: (N, 2) array of component positions in mm.
            context: LossContext with netlist and board.
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
        context: LossContext,
        parsed_pcb: Any = None,
    ) -> dict[str, Any]:
        """Build a K1-schema board dict from positions + LossContext.

        Produces the dict format consumed by temper_drc_rs.run_drc():
        - components: list of dicts with ref, x, y, rot, side, width, height, net_class, ...
        - nets: net_name → list of component refs
        - net_classes: net_name → class_name
        - net_class_rules: class_name → rule dict
        - board: {width_mm, height_mm, margin_mm}

        When ``parsed_pcb`` is provided, delegates to the parsed-PCB path
        (ignoring positions/context).  This allows callers like
        ``ci_closure_test.py`` to reuse the same dict builder for either
        placer output or a static KiCad-parsed board.

        Returns:
            dict matching the K1 schema (see plan §K1).
        """
        if parsed_pcb is not None:
            return self._build_board_dict_from_parsed_pcb(parsed_pcb)

        netlist = context.netlist

        # --- Board dimensions ---
        board_dict: dict[str, Any] = {
            "width_mm": float(context.board.width),
            "height_mm": float(context.board.height),
            "margin_mm": float(context.board_margin),
        }

        # --- Components ---
        components: list[dict[str, Any]] = []
        for i, c in enumerate(netlist.components):
            x = float(positions[i, 0])
            y = float(positions[i, 1])
            rotation = float(c.initial_rotation * 90) if c.initial_rotation is not None else 0.0
            side = "bottom" if c.initial_side is not None and c.initial_side == 1 else "top"
            package_type = _infer_package_type(c.footprint)
            is_mechanical = c.ref.startswith("MH") or package_type == "MECHANICAL"
            comp: dict[str, Any] = {
                "ref": c.ref,
                "x": x,
                "y": y,
                "rot": rotation,
                "side": side,
                "width": float(c.width),
                "height": float(c.height),
                "net_class": c.net_class,
                "package_type": package_type,
                "power_dissipation_w": None,
                "is_magnetic": False,
                "is_electrolytic": False,
                "is_mechanical": is_mechanical,
                "vent_direction": None,
                "footprint_polygon": None,
            }
            components.append(comp)

        # --- Nets ---
        nets: dict[str, list[str]] = {}
        net_classes: dict[str, str] = {}
        for net in netlist.nets:
            comp_refs = list({ref for ref, _ in net.pins})
            nets[net.name] = comp_refs
            net_classes[net.name] = net.net_class

        # --- Net class rules ---
        net_class_rules: dict[str, dict[str, Any]] = {}
        for rule in context.clearance_rules:
            for nc in (rule.net_class_a, rule.net_class_b):
                if nc not in net_class_rules:
                    net_class_rules[nc] = {
                        "trace_width_mm": 0.2,
                        "clearance_mm": rule.min_clearance,
                        "creepage_mm": None,
                        "voltage_v": None,
                        "max_current_rating": None,
                        "safety_category": None,
                        "required_layer": None,
                        "routing_strategy": None,
                    }

        return {
            "board": board_dict,
            "components": components,
            "nets": nets,
            "net_classes": net_classes,
            "net_class_rules": net_class_rules,
        }

    @staticmethod
    def _build_board_dict_from_parsed_pcb(
        parsed_pcb: Any,
    ) -> dict[str, Any]:
        """Build a K1-schema board dict from a ParsedPCB object.

        This is the static path used by ``ci_closure_test.py`` and other
        callers that have a ``ParsedPCB`` (from ``parse_kicad_pcb_v6()``)
        rather than a placer positions array.

        Args:
            parsed_pcb: A ``ParsedPCB`` instance (from
                ``temper_placer.router_v6.stage0_data``).

        Returns:
            dict matching the K1 schema.
        """
        components: list[dict[str, Any]] = []
        for c in parsed_pcb.components:
            x, y = c.initial_position or (0.0, 0.0)
            rotation = float(c.initial_rotation * 90) if c.initial_rotation is not None else 0.0
            side = "bottom" if c.initial_side is not None and c.initial_side == 1 else "top"
            package_type = _infer_package_type(c.footprint)
            is_mechanical = c.ref.startswith("MH") or package_type == "MECHANICAL"
            components.append({
                "ref": c.ref,
                "x": x,
                "y": y,
                "rot": rotation,
                "side": side,
                "width": float(c.width),
                "height": float(c.height),
                "net_class": c.net_class,
                "package_type": package_type,
                "power_dissipation_w": None,
                "is_magnetic": False,
                "is_electrolytic": False,
                "is_mechanical": is_mechanical,
                "vent_direction": None,
                "footprint_polygon": None,
            })

        nets: dict[str, list[str]] = {}
        net_classes: dict[str, str] = {}
        for net in parsed_pcb.nets:
            comp_refs = list({ref for ref, _ in net.pins})
            nets[net.name] = comp_refs
            net_classes[net.name] = net.net_class

        # Populate net_class_rules from parsed DesignRules
        net_class_rules: dict[str, dict[str, Any]] = {}
        for class_name, rules in parsed_pcb.design_rules.net_classes.items():
            net_class_rules[class_name] = {
                "trace_width_mm": rules.trace_width_mm,
                "clearance_mm": rules.clearance_mm,
                "creepage_mm": None,
                "voltage_v": None,
                "max_current_rating": None,
                "safety_category": None,
                "required_layer": None,
                "routing_strategy": None,
            }

        return {
            "board": {
                "width_mm": float(parsed_pcb.board.width),
                "height_mm": float(parsed_pcb.board.height),
                "margin_mm": 3.0,
            },
            "components": components,
            "nets": nets,
            "net_classes": net_classes,
            "net_class_rules": net_class_rules,
        }

    def _build_constraints_dict(
        self,
        context: LossContext,
    ) -> dict[str, Any]:
        """Build a constraints dict for the Rust DRC engine.

        Produces the dict format consumed by temper_drc_rs.build_constraint_set().
        Every field that Rust's ``ConstraintSet`` (de)serializes via serde is
        included with its default value, ensuring the JSON bridge never encounters
        a missing key.

        Fields that Rust expects as sequences (all default to ``[]``):
        - ``clearances``: list of ``{"from_class": str, "to_class": str,
          "clearance_mm": float, "description": str}``
        - ``matched_length_groups``: list of ``{"name": str,
          "tolerance_mm": float, "nets": [str]}``
        - ``noise_domains``: list of ``{"emitters": [str], "victims": [str],
          "max_parallel_run_mm": float}``
        - ``isolation_barriers``: list of ``{"name": str, "x_mm": float,
          "y_span": [float, float], "layers": str}``
        - ``thermal_properties``: list of ``{"component": str,
          "power_dissipation_w": float|None, "max_ambient_c": float|None}``
        - ``snubber_requirements``: list of dicts

        Optional singleton fields:
        - ``bleed_resistor``: ``None`` or ``{"bus_voltage_v": float,
          "target_voltage_v": float, "timeout_s": float}``
        - ``skin_effect_derating``: ``None`` or ``{"frequency_hz": float,
          "derating_factor": float}``

        See also ``ConstraintSet`` in ``packages/temper-drc-rs/src/constraints.rs``.

        Returns:
            dict matching the ConstraintSet serde schema.
        """
        constraints_dict: dict[str, Any] = {
            "clearances": [],
            "zones": [],
            "critical_loops": [],
            "noise_domains": [],
            "isolation_barriers": [],
            "thermal_properties": [],
            "matched_length_groups": [],
            "snubber_requirements": [],
            "bleed_resistor": None,
            "skin_effect_derating": None,
            "hv_clearance_mm": 10.0,
            "board_width": float(context.board.width),
            "board_height": float(context.board.height),
        }

        # --- Clearance rules ---
        for rule in context.clearance_rules:
            constraints_dict["clearances"].append({
                "from_class": rule.net_class_a,
                "to_class": rule.net_class_b,
                "clearance_mm": rule.min_clearance,
                "description": getattr(rule, "because", ""),
            })

        # --- Merge constraints_config if present ---
        # This carries the YAML-derived PlacementConstraints which may
        # override the defaults above (noise_domains, isolation_barriers,
        # thermal_properties, matched_length_groups, etc.)
        config = getattr(context, "constraints_config", None)
        if config is not None:
            for key in (
                "zones",
                "critical_loops",
                "noise_domains",
                "isolation_barriers",
                "thermal_properties",
                "matched_length_groups",
                "snubber_requirements",
                "bleed_resistor",
                "skin_effect_derating",
            ):
                val = getattr(config, key, None)
                if val is not None:
                    constraints_dict[key] = val

        return constraints_dict

    @staticmethod
    def _violations_to_run_result(
        violation_dicts: list[dict[str, Any]],
    ) -> RunResult:
        """Convert a list of Rust DRC violation dicts to a RunResult.

        Groups violations by ``check_name`` and wraps each group into a
        ``CheckResult``.  This allows existing Python consumers (loss
        functions, CI reports) to consume Rust DRC output transparently.

        Args:
            violation_dicts: List of violation dicts from
                ``temper_drc_rs.run_drc()``, each with keys:
                severity, code, message, category, check_name,
                affected_items, location, details.

        Returns:
            RunResult consumable by temper_drc consumers.
        """
        # Lazy import to avoid hard dependency on temper_drc
        from temper_placer.validation.drc_result import CheckResult, Issue, RunResult
        from temper_placer.validation.drc_result import Severity

        _SEVERITY_MAP = {
            "INFO": Severity.INFO,
            "WARNING": Severity.WARNING,
            "ERROR": Severity.ERROR,
            "CRITICAL": Severity.CRITICAL,
        }

        # --- Group by check_name ---
        grouped: dict[str, list[dict[str, Any]]] = {}
        for v in violation_dicts:
            name = v.get("check_name", "unknown")
            grouped.setdefault(name, []).append(v)

        # --- Build CheckResult per group ---
        check_results: list[CheckResult] = []
        for check_name, violations in sorted(grouped.items()):
            issues: list[Issue] = []
            has_failure = False
            for v in violations:
                severity_str = v.get("severity", "ERROR").upper()
                severity = _SEVERITY_MAP.get(severity_str, Severity.ERROR)
                if severity in (Severity.ERROR, Severity.CRITICAL):
                    has_failure = True

                # Build Location
                loc_dict = v.get("location")
                location = None
                if loc_dict is not None and isinstance(loc_dict, dict):
                    from temper_placer.validation.drc_result import Location as DrcLocation

                    location = DrcLocation(
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

        return RunResult(check_results=check_results)


def create_standard_drc_oracle(context: LossContext) -> DRCOracle:
    """Create a DRCOracle pre-loaded with all 12 standard temper-drc checks.

    The oracle is configured with:
    - All DRC checks: component_overlap, courtyard, clearance, zone_containment
    - All Safety checks: creepage, hv_lv_separation, isolation
    - All EMC checks: noise_coupling, loop_area, ground_plane
    - All ERC checks: floating_pins, net_connectivity, power_domain

    Args:
        context: LossContext with netlist and clearance rules.

    Returns:
        Configured DRCOracle instance.

    Raises:
        ImportError: If temper-drc is not installed.
    """
    try:
        from temper_placer.validation.drc_runner import CheckRunner
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
