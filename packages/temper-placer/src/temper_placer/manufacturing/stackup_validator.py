"""Professional PCB stackup validation checks.

Validates the 4-layer Temper board against industry-standard
stackup quality criteria: effective copper symmetry, return-path
adjacency for differential nets, controlled-impedance specification,
and copper density balance.

All checks return advisory warnings -- they do not block the pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from temper_placer.core.board import LayerStackup

if TYPE_CHECKING:
    from temper_placer.router_v6.routing_results import RoutingResults

# IPC-2221 / IPC-6012 guidance: 25-75% copper fill per layer to avoid
# warping during reflow.  Power-electronics boards may push to 20-80%
# on outer layers carrying high current.
COPPER_BALANCE_MIN_PCT: float = 25.0
COPPER_BALANCE_MAX_PCT: float = 75.0

# USB 2.0 Full-Speed (12 Mbps) differential impedance target.
# ESP32-S3 uses USB OTG 1.1 -- standard 90Ω differential.
USB_DIFFERENTIAL_IMPEDANCE_OHMS: float = 90.0

# Effective copper-weight imbalance threshold above which a warping
# risk warning fires.  Expressed as (max_eff - min_eff) / total_eff.
COPPER_SYMMETRY_IMBALANCE_THRESHOLD: float = 0.25


@dataclass
class StackupValidationResult:
    """Result of a single stackup validation check."""

    check_name: str
    passed: bool
    message: str
    layer: str | None = None
    details: dict | None = None


@dataclass
class StackupValidationReport:
    """Aggregate report from all stackup validation checks."""

    results: list[StackupValidationResult] = field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        return all(r.passed for r in self.results)

    @property
    def warnings(self) -> list[StackupValidationResult]:
        return [r for r in self.results if not r.passed]

    def summary(self) -> str:
        lines = ["Stackup Validation:"]
        for r in self.results:
            icon = "[PASS]" if r.passed else "[WARN]"
            lines.append(f"  {icon} {r.check_name}: {r.message}")
        return "\n".join(lines)


def validate_stackup(
    stackup: LayerStackup,
    differential_nets: frozenset[str] = frozenset(),
    impedance_spec_ohms: float | None = None,
    copper_fill_percentages: dict[str, float] | None = None,
    routing_results: RoutingResults | None = None,
    board_dims: tuple[float, float] | None = None,
    has_stitching_vias: bool = False,
) -> StackupValidationReport:
    """Run all stackup validation checks against a LayerStackup.

    Args:
        stackup: LayerStackup to validate.
        differential_nets: Set of net names classified as differential pairs.
        impedance_spec_ohms: Target differential impedance in ohms, or None if
            not configured.  USB 2.0 FS targets 90 Omega (ESP32-S3 USB OTG 1.1).
        copper_fill_percentages: Per-layer estimated fill percentages
            (layer name -> %).  When absent and routing_results is None,
            the check uses the default Temper stackup estimates.
        routing_results: Optional RoutingResults for computing fill from
            actual routed copper via analyze_copper_balance().
        board_dims: Board (width_mm, height_mm) for computing fill percentages
            when routing_results is provided.
        has_stitching_vias: If True, GND stitching vias are present near the
            differential pair, mitigating the L4-to-PWR adjacency concern.

    Returns:
        StackupValidationReport with per-check results.
    """
    fill_pct = _resolve_fill_percentages(
        stackup, copper_fill_percentages, routing_results, board_dims,
    )
    results: list[StackupValidationResult] = []
    results.append(_check_copper_symmetry(stackup, fill_pct))
    results.append(_check_return_path_adjacency(stackup, differential_nets, has_stitching_vias))
    results.append(_check_impedance_spec(differential_nets, impedance_spec_ohms))
    results.append(_check_copper_balance(stackup, fill_pct))
    return StackupValidationReport(results=results)


def _resolve_fill_percentages(
    stackup: LayerStackup,
    explicit: dict[str, float] | None,
    routing_results: RoutingResults | None,
    board_dims: tuple[float, float] | None,
) -> dict[str, float]:
    """Resolve copper fill percentages from explicit data, routing results,
    or default Temper estimates."""
    if explicit:
        return explicit
    if routing_results is not None and board_dims is not None:
        from temper_placer.router_v6.copper_balance import analyze_copper_balance

        report = analyze_copper_balance(
            routing_results, board_dims[0], board_dims[1],
            min_copper_percentage=COPPER_BALANCE_MIN_PCT,
            max_copper_percentage=COPPER_BALANCE_MAX_PCT,
        )
        return {
            lb.layer_name: lb.copper_percentage
            for lb in report.layer_balances
        }
    # Default Temper 4-layer estimates (pre-routing, from footprint density).
    # F.Cu: 2oz, HV + gate-drive traces  ~35% fill
    # In1.Cu: 1oz, solid GND plane       ~95% fill
    # In2.Cu: 1oz, solid PWR plane       ~95% fill
    # B.Cu: 1oz, control signals          ~30% fill
    if len(stackup.layers) == 4 and stackup.layers[0].name == "F.Cu":
        return {"F.Cu": 35.0, "In1.Cu": 95.0, "In2.Cu": 95.0, "B.Cu": 30.0}
    return {}


# ---------------------------------------------------------------------------
# R8 -- Copper symmetry (effective weight)
# ---------------------------------------------------------------------------


def _check_copper_symmetry(
    stackup: LayerStackup,
    fill_pct: dict[str, float],
) -> StackupValidationResult:
    """R8: Verify effective copper weight is balanced across the stackup.

    Effective weight = nominal copper weight (oz) * estimated fill percentage.
    Imbalance formula: (max_eff - min_eff) / total_eff.
    Threshold: COPPER_SYMMETRY_IMBALANCE_THRESHOLD (0.25).
    """
    if not fill_pct:
        return StackupValidationResult(
            "Copper Symmetry", True,
            "No fill data available -- symmetry check skipped",
        )
    effective_weights: dict[str, float] = {}
    for ly in stackup.layers:
        pct = fill_pct.get(ly.name, 0.0) / 100.0
        effective_weights[ly.name] = ly.copper_weight * pct
    total = sum(effective_weights.values())
    if total == 0:
        return StackupValidationResult(
            "Copper Symmetry", True,
            "Zero effective copper -- symmetry check skipped",
        )
    max_eff = max(effective_weights.values())
    min_eff = min(effective_weights.values())
    imbalance = (max_eff - min_eff) / total
    if imbalance > COPPER_SYMMETRY_IMBALANCE_THRESHOLD:
        heaviest = max(effective_weights, key=effective_weights.get)  # type: ignore[arg-type]
        lightest = min(effective_weights, key=effective_weights.get)  # type: ignore[arg-type]
        return StackupValidationResult(
            "Copper Symmetry", False,
            f"Effective copper imbalance detected: {heaviest} at {max_eff:.2f} vs "
            f"{lightest} at {min_eff:.2f} (imbalance={imbalance:.1%}). "
            f"This may cause board warping during reflow.",
            layer=f"{heaviest} vs {lightest}",
            details={"max_eff": max_eff, "min_eff": min_eff, "imbalance": imbalance},
        )
    return StackupValidationResult(
        "Copper Symmetry", True,
        f"Effective copper balanced (imbalance={imbalance:.1%})",
    )


# ---------------------------------------------------------------------------
# R9 -- Return-path adjacency
# ---------------------------------------------------------------------------


def _check_return_path_adjacency(
    stackup: LayerStackup,
    differential_nets: frozenset[str],
    has_stitching_vias: bool = False,
) -> StackupValidationResult:
    """R9: For differential nets, verify adjacent reference plane quality.

    L1 references L2 (GND) -- passes.
    L4 references L3 (PWR) -- warns, unless stitching GND vias are present.

    GND stitching vias placed near the differential pair on L4 provide
    a low-impedance return path to the GND plane (L2), mitigating the
    PWR-plane adjacency concern.  When has_stitching_vias is True the
    warning is suppressed.

    Non-differential nets are not checked.
    """
    if not differential_nets:
        return StackupValidationResult(
            "Return-Path Adjacency", True,
            "No differential nets configured -- adjacency check skipped",
        )
    layers = stackup.layers
    if len(layers) >= 4 and layers[2].layer_type == "plane":
        if has_stitching_vias:
            return StackupValidationResult(
                "Return-Path Adjacency", True,
                "L4 references L3 (PWR plane), but stitching GND vias are present "
                "-- return-path concern mitigated.",
            )
        return StackupValidationResult(
            "Return-Path Adjacency", False,
            "L4 (control signals) references L3 (PWR plane). "
            "Verify return-path quality for differential nets. "
            "Consider adding stitching GND vias near the differential pair.",
            layer="L4 (B.Cu)",
        )
    return StackupValidationResult(
        "Return-Path Adjacency", True,
        "Signal layers have adequate reference plane adjacency",
    )


# ---------------------------------------------------------------------------
# R10 -- Controlled-impedance specification
# ---------------------------------------------------------------------------


def _check_impedance_spec(
    differential_nets: frozenset[str],
    impedance_spec_ohms: float | None,
) -> StackupValidationResult:
    """R10: Verify controlled-impedance specification exists AND is valid.

    ESP32-S3 uses USB OTG 1.1 (Full Speed, 12 Mbps).  Standard target is
    90 Omega differential for USB 2.0.  Values outside 70-120 Omega are
    flagged as suspicious.
    """
    if not differential_nets:
        return StackupValidationResult(
            "Controlled Impedance", True,
            "No differential nets configured -- impedance check skipped",
        )
    if impedance_spec_ohms is None:
        return StackupValidationResult(
            "Controlled Impedance", False,
            "No target impedance specified for differential nets "
            f"({len(differential_nets)} nets: {sorted(differential_nets)}). "
            f"Expected: {USB_DIFFERENTIAL_IMPEDANCE_OHMS:.0f} Omega differential "
            f"for USB 2.0 (ESP32-S3 USB OTG 1.1).",
        )
    if impedance_spec_ohms <= 0:
        return StackupValidationResult(
            "Controlled Impedance", False,
            f"Invalid impedance value: {impedance_spec_ohms} Omega. Expected positive value.",
        )
    if not (70.0 <= impedance_spec_ohms <= 120.0):
        return StackupValidationResult(
            "Controlled Impedance", False,
            f"Impedance {impedance_spec_ohms} Omega outside typical USB range (70-120 Omega). "
            "Verify this is intentional.",
        )
    return StackupValidationResult(
        "Controlled Impedance", True,
        f"Impedance specification: {impedance_spec_ohms} Omega for differential nets",
    )


# ---------------------------------------------------------------------------
# R11 -- Copper density balance
# ---------------------------------------------------------------------------


def _check_copper_balance(
    _stackup: LayerStackup,
    fill_pct: dict[str, float],
) -> StackupValidationResult:
    """R11: Verify copper density is balanced across all layers.

    IPC-2221 / IPC-6012 recommend 25-75% copper fill per layer to avoid
    board warping during reflow.  Power-electronics designs may tolerate
    wider ranges on outer layers carrying high current.
    """
    if not fill_pct:
        return StackupValidationResult(
            "Copper Balance", True,
            "No fill data available -- balance check skipped",
        )
    percents = list(fill_pct.values())
    max_fill = max(percents)
    min_fill = min(percents)
    if min_fill < COPPER_BALANCE_MIN_PCT or max_fill > COPPER_BALANCE_MAX_PCT:
        return StackupValidationResult(
            "Copper Balance", False,
            f"Copper density imbalance: max={max_fill:.0f}%, min={min_fill:.0f}% "
            f"(target: {COPPER_BALANCE_MIN_PCT:.0f}-{COPPER_BALANCE_MAX_PCT:.0f}%). "
            f"This may cause board warping during reflow.",
            details={"max_fill": max_fill, "min_fill": min_fill},
        )
    return StackupValidationResult(
        "Copper Balance", True,
        f"Copper density balanced (range: {min_fill:.0f}%-{max_fill:.0f}%)",
    )
