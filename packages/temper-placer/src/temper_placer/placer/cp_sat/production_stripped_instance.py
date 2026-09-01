"""Prepare the exact stripped creepage instance from a real KiCad board.

This is intentionally a marshalling boundary.  KiCad parsing, net
classification, and the generated creepage matrix remain the existing
production authorities; Rust owns the component-pair reduction.  The module
does not infer safety classes from reference names or duplicate the matrix in
Python.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import temper_orchestration as _to

from temper_placer.core.design_rules import DesignRules
from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.placer.cp_sat.bounded_feasibility_probe import (
    BoundedProbeResult,
    ProbeLimits,
    ProbeMode,
    run_bounded_probe,
)
from temper_placer.placer.cp_sat.netclass_constraints import (
    _generated_creepage_rows,
    _pin_class_infos,
)
from temper_placer.placer.cp_sat.stripped_creepage_solver import (
    ComponentSpec,
    PairRequirement,
    Placement,
)


@dataclass(frozen=True, slots=True)
class ProductionStrippedDiagnostics:
    """Counts and provenance facts that must accompany a production probe."""

    board_width_mm: float
    board_height_mm: float
    component_count: int
    pin_classified_component_count: int
    requirement_count: int
    requirements_by_gap_mm: tuple[tuple[float, int], ...]
    fixed_orientation_quadrants: tuple[tuple[int, int], ...]
    initial_position_count: int


@dataclass(frozen=True, slots=True)
class ProductionStrippedInstance:
    """Complete plain-data input for the stripped solver and warm start."""

    components: tuple[ComponentSpec, ...]
    requirements: tuple[PairRequirement, ...]
    board_width_mm: float
    board_height_mm: float
    initial_placements: dict[str, Placement]
    diagnostics: ProductionStrippedDiagnostics

    @property
    def component_count(self) -> int:
        return len(self.components)

    @property
    def requirement_count(self) -> int:
        return len(self.requirements)


@dataclass(frozen=True, slots=True)
class ProductionStrippedProbeReport:
    """Bounded fixed/rotatable probe plus the instance census."""

    instance: ProductionStrippedInstance
    probe: BoundedProbeResult

    @property
    def accepted(self) -> bool:
        return self.probe.accepted

    def accepted_run(self):
        return self.probe.accepted_run()


def _load_design_rules() -> DesignRules:
    """Load the package's authoritative class-pair rules document."""
    from temper_placer.io.netclass_loader import load_netclass_rules

    rules_path = Path(__file__).resolve().parents[4] / "configs" / "netclass_rules.yaml"
    if not rules_path.is_file():
        raise FileNotFoundError(f"netclass rules not found: {rules_path}")
    return load_netclass_rules(rules_path).design_rules


def _component_geometry(component: Any) -> tuple[ComponentSpec, Placement, int]:
    ref = getattr(component, "ref", None)
    if not isinstance(ref, str) or not ref.strip():
        raise ValueError(f"component has invalid reference {ref!r}")
    try:
        width, height = (float(value) for value in component.bounds)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"component {ref!r} has unusable bounds") from exc
    if not all(math.isfinite(value) and value > 0.0 for value in (width, height)):
        raise ValueError(f"component {ref!r} has non-positive or non-finite bounds")

    raw_quadrant = getattr(component, "initial_rotation_quadrant", None)
    if isinstance(raw_quadrant, bool) or not isinstance(raw_quadrant, int):
        raise ValueError(f"component {ref!r} has invalid initial rotation {raw_quadrant!r}")
    quadrant = int(raw_quadrant)
    if quadrant not in range(4):
        raise ValueError(f"component {ref!r} has invalid initial rotation {quadrant}")
    if quadrant % 2:
        width, height = height, width

    position = getattr(component, "initial_position", None)
    if position is None:
        raise ValueError(f"component {ref!r} has no initial position for warm start")
    try:
        center_x, center_y = (float(value) for value in position)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"component {ref!r} has unusable initial position") from exc
    if not all(math.isfinite(value) for value in (center_x, center_y)):
        raise ValueError(f"component {ref!r} has non-finite initial position")
    return (
        (ref, width, height),
        (center_x - width / 2.0, center_y - height / 2.0, quadrant),
        quadrant,
    )


def prepare_production_stripped_instance(
    pcb_path: Path | str,
    *,
    design_rules: DesignRules | None = None,
    normalize: bool = True,
) -> ProductionStrippedInstance:
    """Parse *pcb_path* and derive its exact stripped creepage instance.

    Component dimensions are the parsed footprint bounds after applying the
    board's committed quarter-turn orientation.  Requirements are generated
    by the Rust pin-class cross-product kernel from the generated KiCad table;
    every non-zero component pair is retained.  Any malformed or incomplete
    board data raises instead of producing a partial model.
    """

    rules = _load_design_rules() if design_rules is None else design_rules
    parsed = parse_kicad_pcb(Path(pcb_path), normalize=normalize, design_rules=rules)
    board = getattr(parsed, "board", None)
    netlist = getattr(parsed, "netlist", None)
    if board is None or netlist is None:
        raise ValueError("KiCad parser returned no board or netlist")
    try:
        board_width = float(board.width)
        board_height = float(board.height)
    except (TypeError, ValueError) as exc:
        raise ValueError("parsed board dimensions are unusable") from exc
    if not all(math.isfinite(value) and value > 0.0 for value in (board_width, board_height)):
        raise ValueError("parsed board dimensions must be finite and positive")

    components: list[ComponentSpec] = []
    initial: dict[str, Placement] = {}
    orientation_counts: Counter[int] = Counter()
    pin_infos: list[tuple[str, list[tuple[str, str | None, float]]]] = []
    for component in netlist.components:
        spec, placement, quadrant = _component_geometry(component)
        ref = spec[0]
        if ref in initial:
            raise ValueError(f"duplicate component reference {ref!r}")
        components.append(spec)
        initial[ref] = placement
        orientation_counts[quadrant] += 1
        infos = _pin_class_infos(getattr(component, "pins", []), rules, {})
        if infos:
            pin_infos.append((ref, infos))

    if not components:
        raise ValueError("parsed board has no components")
    class_clearance = {
        cls: float(rules.get_rules_for_net("", net_class=cls).clearance)
        for cls in rules.net_classes
    }
    class_pair_overrides: list[tuple[str, str, float | None, str]] = []
    for key, value in (getattr(rules, "class_pairs", {}) or {}).items():
        if not (isinstance(key, tuple) and len(key) == 2 and isinstance(value, dict)):
            continue
        class_a, class_b = key
        if isinstance(class_a, str) and isinstance(class_b, str):
            class_pair_overrides.append(
                (class_a, class_b, value.get("clearance"), str(value.get("because", "")))
            )
    requirements = tuple(
        _to.netclass_creepage_requirements_py(
            pin_infos,
            class_clearance,
            class_pair_overrides,
            _generated_creepage_rows(),
        )
    )
    gap_counts = Counter(float(required) for _left, _right, required in requirements)
    diagnostics = ProductionStrippedDiagnostics(
        board_width_mm=board_width,
        board_height_mm=board_height,
        component_count=len(components),
        pin_classified_component_count=len(pin_infos),
        requirement_count=len(requirements),
        requirements_by_gap_mm=tuple(sorted(gap_counts.items())),
        fixed_orientation_quadrants=tuple(sorted(orientation_counts.items())),
        initial_position_count=len(initial),
    )
    return ProductionStrippedInstance(
        components=tuple(components),
        requirements=requirements,
        board_width_mm=board_width,
        board_height_mm=board_height,
        initial_placements=initial,
        diagnostics=diagnostics,
    )


def run_production_stripped_probe(
    instance: ProductionStrippedInstance,
    *,
    limits: ProbeLimits = ProbeLimits(),
    modes: tuple[ProbeMode, ...] = (ProbeMode.FIXED, ProbeMode.ROTATABLE),
    units_per_mm: int = 100,
    num_search_workers: int = 4,
) -> ProductionStrippedProbeReport:
    """Run the real-board instance under external bounds and Rust checking.

    ``solve_stripped_creepage`` already performs one fail-closed Rust check;
    the callback below repeats that check at the process boundary so this
    function remains safe if the solver implementation changes later.
    """
    from temper_placer.placer.cp_sat.stripped_creepage_solver import solve_stripped_creepage

    class _Verification:
        def __init__(self, violations: tuple[str, ...]):
            self.violations = violations

    def solve(mode: ProbeMode, timeout_s: float):
        return solve_stripped_creepage(
            instance.components,
            instance.requirements,
            instance.board_width_mm,
            instance.board_height_mm,
            allow_rotations=mode is ProbeMode.ROTATABLE,
            timeout_s=timeout_s,
            units_per_mm=units_per_mm,
            num_search_workers=num_search_workers,
        )

    def verify(mode: ProbeMode, candidate: Any) -> _Verification:
        placements = [
            (ref, x, y, int(candidate.rotations.get(ref, 0)))
            for ref, (x, y) in candidate.positions.items()
        ]
        try:
            _to.verify_stripped_creepage_py(
                list(instance.components),
                list(instance.requirements),
                instance.board_width_mm,
                instance.board_height_mm,
                placements,
                mode is ProbeMode.ROTATABLE,
            )
        except Exception as exc:
            return _Verification((f"{type(exc).__name__}: {exc}",))
        return _Verification(())

    probe = run_bounded_probe(solve, verify, limits=limits, modes=modes)
    return ProductionStrippedProbeReport(instance, probe)


__all__ = [
    "ProductionStrippedDiagnostics",
    "ProductionStrippedInstance",
    "ProductionStrippedProbeReport",
    "prepare_production_stripped_instance",
    "run_production_stripped_probe",
]
