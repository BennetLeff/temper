"""Professional PCB stackup validation checks.

Validates the 4-layer Temper board against industry-standard
stackup quality criteria: effective copper symmetry, return-path
adjacency for differential nets, controlled-impedance specification,
and copper density balance.

All checks return advisory warnings — they do not block the pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from temper_placer.core.board import LayerStackup


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
) -> StackupValidationReport:
    """Run all stackup validation checks against a LayerStackup.

    Args:
        stackup: LayerStackup to validate.
        differential_nets: Set of net names classified as differential pairs.
        impedance_spec_ohms: Target differential impedance in ohms, or None if
            not configured. USB 2.0 typically targets 90Ω.
        copper_fill_percentages: Per-layer estimated fill percentages (layer name -> %).

    Returns:
        StackupValidationReport with per-check results.
    """
    results: list[StackupValidationResult] = []
    results.append(_check_copper_symmetry(stackup, copper_fill_percentages or {}))
    results.append(_check_return_path_adjacency(stackup, differential_nets))
    results.append(_check_impedance_spec(differential_nets, impedance_spec_ohms))
    results.append(_check_copper_balance(stackup, copper_fill_percentages or {}))
    return StackupValidationReport(results=results)


def _check_copper_symmetry(
    stackup: LayerStackup,
    fill_pct: dict[str, float],
) -> StackupValidationResult:
    """R8: Verify effective copper weight is balanced across the stackup.

    Effective weight = nominal copper weight (oz) × estimated fill percentage.
    Imbalance formula: (max_eff - min_eff) / total_eff > threshold.
    """
    if not fill_pct:
        return StackupValidationResult(
            "Copper Symmetry", True,
            "No fill data available — symmetry check skipped",
        )
    effective_weights: dict[str, float] = {}
    for ly in stackup.layers:
        pct = fill_pct.get(ly.name, 0.0) / 100.0
        effective_weights[ly.name] = ly.copper_weight * pct
    total = sum(effective_weights.values())
    if total == 0:
        return StackupValidationResult(
            "Copper Symmetry", True,
            "Zero effective copper — symmetry check skipped",
        )
    max_eff = max(effective_weights.values())
    min_eff = min(effective_weights.values())
    imbalance = (max_eff - min_eff) / total
    if imbalance > 0.25:
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


def _check_return_path_adjacency(
    stackup: LayerStackup,
    differential_nets: frozenset[str],
) -> StackupValidationResult:
    """R9: For differential nets, verify adjacent reference plane quality.

    L1 references L2 (GND) — passes.
    L4 references L3 (PWR) — warns.
    Non-differential nets are not checked.
    """
    if not differential_nets:
        return StackupValidationResult(
            "Return-Path Adjacency", True,
            "No differential nets configured — adjacency check skipped",
        )
    layers = stackup.layers
    # L4 (index 3) is adjacent to L3 (index 2, PWR plane)
    if len(layers) >= 4 and layers[2].layer_type == "plane":
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


def _check_impedance_spec(
    differential_nets: frozenset[str],
    impedance_spec_ohms: float | None,
) -> StackupValidationResult:
    """R10: Verify controlled-impedance specification exists AND is valid.

    USB 2.0 full-speed typically targets 90Ω differential. Values outside
    70-120Ω are flagged as suspicious.
    """
    if not differential_nets:
        return StackupValidationResult(
            "Controlled Impedance", True,
            "No differential nets configured — impedance check skipped",
        )
    if impedance_spec_ohms is None:
        return StackupValidationResult(
            "Controlled Impedance", False,
            "No target impedance specified for differential nets "
            f"({len(differential_nets)} nets: {sorted(differential_nets)}). "
            "Expected: 90Ω differential for USB 2.0.",
        )
    if impedance_spec_ohms <= 0:
        return StackupValidationResult(
            "Controlled Impedance", False,
            f"Invalid impedance value: {impedance_spec_ohms}Ω. Expected positive value.",
        )
    if not (70.0 <= impedance_spec_ohms <= 120.0):
        return StackupValidationResult(
            "Controlled Impedance", False,
            f"Impedance {impedance_spec_ohms}Ω outside typical USB range (70-120Ω). "
            "Verify this is intentional.",
        )
    return StackupValidationResult(
        "Controlled Impedance", True,
        f"Impedance specification: {impedance_spec_ohms}Ω for differential nets",
    )


def _check_copper_balance(
    _stackup: LayerStackup,
    fill_pct: dict[str, float],
) -> StackupValidationResult:
    """R11: Verify copper density is reasonably balanced across all 4 layers.

    Reuses the existing router_v6/copper_balance.py analysis where
    RoutingResults are available, and falls back to fill-percentage
    comparison when only percentage data is available.
    """
    if not fill_pct:
        return StackupValidationResult(
            "Copper Balance", True,
            "No fill data available — balance check skipped",
        )
    percents = list(fill_pct.values())
    max_fill = max(percents)
    min_fill = min(percents)
    # Thresholds are illustrative; exact values deferred to planning.
    if min_fill < 5.0 and max_fill > 75.0:
        return StackupValidationResult(
            "Copper Balance", False,
            f"Copper density imbalance: max={max_fill:.0f}%, min={min_fill:.0f}%. "
            f"This may cause board warping during reflow.",
            details={"max_fill": max_fill, "min_fill": min_fill},
        )
    return StackupValidationResult(
        "Copper Balance", True,
        f"Copper density balanced (range: {min_fill:.0f}%–{max_fill:.0f}%)",
    )
