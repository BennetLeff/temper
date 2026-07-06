"""
Physics-derived oracle runner for the Temper induction board.

Wires the full physics chain end-to-end:
  pcb_spec.yaml -> PcbSpecification -> derive_constraints_from_spec ->
  score CP-SAT placement -> IEC 60335-1 threshold comparison -> pass/fail.

The oracle accepts a CP-SAT placement result and scores it against physics
metrics (thermal, clearance, dual-rail) without running gradient optimization.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from temper_placer.core.design_rules import create_temper_design_rules
from temper_placer.core.loss_types import LossContext
from temper_placer.core.specification import PcbSpecification
from temper_placer.core.state import PlacementState
from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.io.reference_loader import infer_quality_config
from temper_placer.metrics.quality import (
    compactness_score,
    dual_rail_clearance_report,
    hv_lv_clearance_score,
    loop_area_score,
    thermal_score,
    zone_compliance_score,
)
from temper_placer.placer.deterministic import PlacementResult
from temper_placer.pipeline.derivation import derive_constraints_from_spec


@dataclass
class PhysicsOracleResult:
    """Result from a physics-oracle run."""

    board_id: str
    passed: bool
    skipped: bool = False
    skip_reason: str = ""
    errors: list[str] = None  # type: ignore[assignment]

    quality_report: dict[str, float] = None  # type: ignore[assignment]
    threshold_mm: float = 0.0
    clearance_score: float = 0.0
    elapsed_seconds: float = 0.0

    def __post_init__(self):
        if self.errors is None:
            self.errors = []
        if self.quality_report is None:
            self.quality_report = {}


# Module-level constants for experiment thresholds
_CLEARANCE_PASS_THRESHOLD = 0.95  # legacy pass/fail for single-run oracle


@dataclass
class _BoardSnapshot:
    """Minimal adapter to bridge Netlist + Board into infer_quality_config."""
    netlist: Any
    board: Any


def _build_placement_state(positions: np.ndarray, n_components: int) -> PlacementState:
    """Build a PlacementState from a (N, 2) positions array."""
    return PlacementState(
        positions=np.asarray(positions, dtype=np.float32),
        rotation_logits=np.zeros((n_components, 4), dtype=np.float32),
    )


def _make_minimal_context(netlist, board) -> LossContext:
    """Create a minimal LossContext for metric functions that need one.

    Post-JAX retirement, LossContext is a stub; metric functions that take
    context only access shape checks (e.g. net_pin_indices.shape[0]) before
    early-returning.  We populate just enough to keep those guards happy.
    """
    ctx = LossContext(netlist=netlist, board=board)
    ctx.net_pin_indices = np.array([], dtype=np.int32).reshape(0, 2)
    return ctx


def score_placement(
    placement: PlacementResult,
    board,
    netlist,
) -> dict[str, Any]:
    """
    Compute physics metrics from a CP-SAT placement without running optimization.

    Args:
        placement: PlacementResult from deterministic placer (positions in mm).
        board: Board geometry.
        netlist: Design netlist.

    Returns:
        Dict with physics metrics: hv_lv_clearance_score, clearance_score_3mm,
        clearance_score_6mm, violations_3mm, violations_6mm, thermal_score,
        zone_compliance_score, loop_area_score, compactness_score, overall_score.
    """
    positions = np.asarray(placement.positions, dtype=np.float32)
    n_components = positions.shape[0]
    state = _build_placement_state(positions, n_components)
    context = _make_minimal_context(netlist, board)

    hv_components = {
        c.ref for c in netlist.components
        if c.net_class in ("HighVoltage", "ACMains")
    }
    lv_components = {
        c.ref for c in netlist.components
        if c.net_class == "Signal"
    }

    dual_rail = dual_rail_clearance_report(state, netlist, hv_components, lv_components)
    clearance = hv_lv_clearance_score(state, netlist, hv_components, lv_components, min_clearance=8.0)
    thermal = thermal_score(state, netlist, board, set())
    zone = zone_compliance_score(state, netlist, board, {})
    loop = loop_area_score(state, netlist, context, [])
    compact = compactness_score(state, netlist, board)

    normalized_scores = [thermal, zone, clearance, loop, compact]
    overall = sum(normalized_scores) / len(normalized_scores) if normalized_scores else 0.0

    return {
        "hv_lv_clearance_score": clearance,
        "clearance_score_3mm": dual_rail["clearance_score_3mm"],
        "clearance_score_6mm": dual_rail["clearance_score_6mm"],
        "violations_3mm": dual_rail["violations_3mm"],
        "violations_6mm": dual_rail["violations_6mm"],
        "thermal_score": thermal,
        "zone_compliance_score": zone,
        "loop_area_score": loop,
        "compactness_score": compact,
        "overall_score": overall,
    }


def run_physics_oracle(
    pcb_path: Path,
    placement: PlacementResult | None = None,
    spec_path: Path | None = None,
    verbose: bool = True,
    weights_override: dict[str, float] | None = None,
) -> PhysicsOracleResult:
    """
    Score a CP-SAT placement against the physics oracle.

    Args:
        pcb_path: Path to the KiCad PCB file.
        placement: CP-SAT placement result from deterministic placer.
                   If None, uses the intrinsic KiCad reference positions.
        spec_path: Path to pcb_spec.yaml. If None, looks alongside pcb_path
                   or uses the default configs/pcb_spec.yaml.
        verbose: Whether to print progress.
        weights_override: (unused, kept for signature compatibility)

    Returns:
        PhysicsOracleResult with quality report and threshold comparison.
    """
    board_id = pcb_path.stem
    start_time = time.time()

    # Resolve spec path
    if spec_path is None:
        default_spec = Path("configs/pcb_spec.yaml")
        if default_spec.exists():
            spec_path = default_spec
        else:
            pcb_dir = pcb_path.parent
            candidate = pcb_dir / "pcb_spec.yaml"
            if candidate.exists():
                spec_path = candidate

    if spec_path is None or not Path(spec_path).exists():
        return PhysicsOracleResult(
            board_id=board_id,
            passed=False,
            skipped=True,
            skip_reason=f"PCB spec not found: {spec_path}",
        )

    # Load spec
    try:
        spec = PcbSpecification.load(spec_path)
    except Exception as e:
        return PhysicsOracleResult(
            board_id=board_id,
            passed=False,
            skipped=True,
            skip_reason=f"Failed to load spec: {e}",
        )

    # Parse PCB with design rules for net classification
    design_rules = create_temper_design_rules()
    try:
        parse_result = parse_kicad_pcb(pcb_path, design_rules=design_rules)
        netlist = parse_result.netlist
    except Exception as e:
        return PhysicsOracleResult(
            board_id=board_id,
            passed=False,
            errors=[f"Failed to parse PCB: {e}"],
        )

    if netlist.n_components == 0:
        return PhysicsOracleResult(
            board_id=board_id,
            passed=False,
            skipped=True,
            skip_reason="Board has zero components",
        )

    # Get board from parse result
    board = parse_result.board
    if board is None:
        return PhysicsOracleResult(
            board_id=board_id,
            passed=False,
            skipped=True,
            skip_reason="No board geometry extracted from PCB",
        )

    # Derive constraints from spec
    try:
        derived = derive_constraints_from_spec(spec, netlist)
    except Exception as e:
        return PhysicsOracleResult(
            board_id=board_id,
            passed=False,
            errors=[f"Constraint derivation failed: {e}"],
        )

    threshold_mm = derived.get("hv_lv_isolation_mm", 6.5)
    if verbose:
        print(f"  Physics oracle for '{board_id}': threshold = {threshold_mm} mm")

    # Build PlacementState from the placement result
    if placement is not None:
        positions = np.asarray(placement.positions, dtype=np.float32)
    else:
        # Fall back to KiCad reference positions from the netlist
        positions = np.array(
            [c.initial_position for c in netlist.components],
            dtype=np.float32,
        )

    n_components = positions.shape[0]
    state = _build_placement_state(positions, n_components)
    context = _make_minimal_context(netlist, board)

    # Solve HV/LV component sets from net classification
    hv_components = {
        c.ref for c in netlist.components
        if c.net_class in ("HighVoltage", "ACMains")
    }
    lv_components = {
        c.ref for c in netlist.components
        if c.net_class == "Signal"
    }

    # Compute quality report from individual metric functions
    try:
        ref = _BoardSnapshot(netlist=netlist, board=board)
        quality_config = infer_quality_config(ref)  # type: ignore[arg-type]

        if hv_components:
            quality_config["hv_components"] = hv_components
        if lv_components:
            quality_config["lv_components"] = lv_components

        quality_config["min_hv_lv_clearance"] = threshold_mm
        quality_config["thermal_target_edge"] = spec.thermal.target_edge
        quality_config["thermal_max_distance"] = spec.thermal.max_heatspread_mm

        loop_comps = []
        if spec.emi.loop_components:
            loop_comps = [
                list(comps) for comps in spec.emi.loop_components.values()
                if len(comps) >= 3
            ]

        dual_rail = dual_rail_clearance_report(state, netlist, hv_components, lv_components)
        clearance = hv_lv_clearance_score(
            state, netlist, hv_components, lv_components, min_clearance=threshold_mm,
        )
        thermal = thermal_score(
            state, netlist, board,
            quality_config.get("thermal_components", set()),
            target_edge=spec.thermal.target_edge,
            max_distance=spec.thermal.max_heatspread_mm,
        )
        zone = zone_compliance_score(
            state, netlist, board,
            quality_config.get("zone_assignments", {}),
        )
        loop = loop_area_score(state, netlist, context, loop_comps)
        compact = compactness_score(state, netlist, board)

        normalized_scores = [thermal, zone, clearance, loop, compact]
        overall = sum(normalized_scores) / len(normalized_scores) if normalized_scores else 0.0

        report = {
            "thermal_score": thermal,
            "zone_compliance_score": zone,
            "hv_lv_clearance_score": clearance,
            "clearance_score_3mm": dual_rail["clearance_score_3mm"],
            "clearance_score_6mm": dual_rail["clearance_score_6mm"],
            "violations_3mm": dual_rail["violations_3mm"],
            "violations_6mm": dual_rail["violations_6mm"],
            "loop_area_score": loop,
            "compactness_score": compact,
            "overall_score": overall,
        }
        elapsed = time.time() - start_time

        if verbose:
            print(f"  HV/LV clearance score: {clearance:.4f}")
            print(f"  Overall quality score: {overall:.4f}")

    except Exception as e:
        return PhysicsOracleResult(
            board_id=board_id,
            passed=False,
            errors=[f"Quality report failed: {e}"],
        )

    passed = clearance >= _CLEARANCE_PASS_THRESHOLD

    return PhysicsOracleResult(
        board_id=board_id,
        passed=passed,
        quality_report=report,
        threshold_mm=threshold_mm,
        clearance_score=clearance,
        elapsed_seconds=elapsed,
    )


def score_human_baseline(
    pcb_path: Path,
    spec_path: Path | None = None,
    verbose: bool = True,
) -> dict[str, float | int]:
    """
    Score the human reference placement under the dual-rail clearance metric.

    Loads the KiCad PCB at its original component positions (no optimizer run)
    and computes worst-pair severity and violation count against both the
    3.0mm IEC regulatory floor and the 6.0mm DRC design-rule rail.

    Args:
        pcb_path: Path to the KiCad PCB file (human reference placement).
        spec_path: Path to pcb_spec.yaml. If None, looks alongside pcb_path.
        verbose: Whether to print the four numbers.

    Returns:
        Dict with clearance_score_3mm, clearance_score_6mm,
        violations_3mm, violations_6mm.
    """
    # Resolve spec
    if spec_path is None:
        default_spec = Path("configs/pcb_spec.yaml")
        spec_path = default_spec if default_spec.exists() else pcb_path.parent / "pcb_spec.yaml"

    spec = PcbSpecification.load(spec_path)
    design_rules = create_temper_design_rules()
    parse_result = parse_kicad_pcb(pcb_path, design_rules=design_rules)
    netlist = parse_result.netlist
    board = parse_result.board
    if board is None:
        raise ValueError("No board geometry extracted from PCB")

    derived = derive_constraints_from_spec(spec, netlist)
    threshold_mm = derived.get("hv_lv_isolation_mm", 6.5)

    # Build state from intrinsic KiCad positions (no optimizer pipeline)
    positions = np.array(
        [c.initial_position for c in netlist.components],
        dtype=np.float32,
    )
    state = _build_placement_state(positions, len(netlist.components))

    # Build quality config mirroring the oracle's setup
    ref = _BoardSnapshot(netlist=netlist, board=board)
    quality_config = infer_quality_config(ref)  # type: ignore[arg-type]

    hv_from_class = {
        c.ref for c in netlist.components
        if c.net_class in ("HighVoltage", "ACMains")
    }
    lv_from_class = {
        c.ref for c in netlist.components
        if c.net_class == "Signal"
    }
    if hv_from_class:
        quality_config["hv_components"] = hv_from_class
    if lv_from_class:
        quality_config["lv_components"] = lv_from_class

    # Score with dual-rail metric
    result = dual_rail_clearance_report(
        state, netlist,
        quality_config.get("hv_components", set()),
        quality_config.get("lv_components", set()),
    )

    if verbose:
        print(f"Human baseline ({pcb_path.stem}):")
        print(f"  clearance_score_3mm  = {result['clearance_score_3mm']:.4f}")
        print(f"  clearance_score_6mm  = {result['clearance_score_6mm']:.4f}")
        print(f"  violations_3mm       = {result['violations_3mm']}")
        print(f"  violations_6mm       = {result['violations_6mm']}")
        print(f"  (threshold from spec  = {threshold_mm} mm)")

    return result


# Re-export multi-seed experiment API from its own module.
# NOTE: multi_seed_experiment.py also needs JAX retirement; re-export is
# conditional until that module is updated.
try:
    from temper_placer.regression.multi_seed_experiment import (  # noqa: E402, F401
        MultiSeedExperimentResult,
        MultiSeedRunResult,
        _compute_experiment_stats,
        run_multi_seed_experiment,
    )
except Exception:
    # Multi-seed experiment module still has JAX dependencies;
    # these symbols will be available once that module is updated.
    pass
