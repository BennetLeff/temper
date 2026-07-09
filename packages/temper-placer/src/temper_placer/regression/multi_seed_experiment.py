"""
Multi-seed experiment runner for the physics oracle.

Runs n_seeds x {C-CAP on, C-CAP off} = 2*n_seeds optimizer passes
against the corrected dual-rail clearance metric, checks convergence
per run, and fires a pre-registered decision rule (DISSOLVED / HOLDS /
INCONCLUSIVE).

Extracted from physics_oracle.py to keep the module focused.
"""

from __future__ import annotations

import math
import statistics
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from temper_placer.core.design_rules import create_temper_design_rules
from temper_placer.core.specification import PcbSpecification
from temper_placer.heuristics import create_default_pipeline
from temper_placer.io.config_loader import PlacementConstraints
from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.io.reference_loader import infer_quality_config
from temper_placer.losses.base import (
    CompositeLoss,
    LoopConstraint,
    LossContext,
    ThermalConstraint,
    WeightedLoss,
)
from temper_placer.losses.boundary import BoundaryLoss
from temper_placer.losses.clearance import ClearanceLoss
from temper_placer.losses.component_loop_area import ComponentLoopAreaLoss, ComponentLoopConfig
from temper_placer.losses.loop_area import LoopAreaLoss
from temper_placer.losses.overlap import OverlapLoss
from temper_placer.losses.regularization import SpreadLoss
from temper_placer.losses.thermal import ThermalLoss
from temper_placer.losses.wirelength import WirelengthLoss
from temper_placer.metrics.quality import dual_rail_clearance_report, thermal_score
from temper_placer.optimizer.config import OptimizerConfig
from temper_placer.optimizer.curriculum import create_default_phases
from temper_placer.optimizer.train import train_multiphase
from temper_placer.pipeline.derivation import derive_constraints_from_spec

# ---- Module-level constants for experiment thresholds ----

_CONVERGENCE_FRACTION = 0.2       # last N% of epochs for reference slope computation
_PLATEAU_THRESHOLD = 1e-4         # reference slope threshold (not used for convergence gate)
_DISSOLVED_CLR6_MIN = 0.85        # min mean clearance_6mm for DISSOLVED
_DISSOLVED_CLR6_STD_MAX = 0.05    # max std of clearance_6mm for DISSOLVED
_DISSOLVED_THERM_MIN = 0.45       # min mean thermal_score for DISSOLVED

# ---- Dataclasses ----


@dataclass
class _BoardSnapshot:
    """Minimal adapter to bridge Netlist + Board into infer_quality_config."""
    netlist: Any
    board: Any


@dataclass
class MultiSeedRunResult:
    """Per-run result from a multi-seed experiment run."""

    seed: int
    ccap_on: bool
    converged: bool
    ccap_convergence_status: str  # "converged" | "oscillation" | "failed" | "disabled"
    ccap_cycles: int
    ccap_post_projection_clearance: float | None
    clearance_score_3mm: float
    clearance_score_6mm: float
    violations_3mm: int
    violations_6mm: int
    thermal_score: float
    final_loss: float
    plateau_check_passed: bool
    plateau_slope: float
    elapsed_seconds: float
    error: str | None = None


@dataclass
class MultiSeedExperimentResult:
    """Aggregated result from a multi-seed experiment."""

    board_id: str
    n_seeds: int
    per_run: list[MultiSeedRunResult]
    human_baseline: dict[str, float | int]
    ccap_on_mean_clearance_6mm: float
    ccap_on_std_clearance_6mm: float
    ccap_on_mean_thermal: float
    ccap_on_std_thermal: float
    ccap_off_mean_clearance_6mm: float
    ccap_off_std_clearance_6mm: float
    ccap_off_mean_thermal: float
    ccap_off_std_thermal: float
    verdict: str  # "DISSOLVED" | "HOLDS" | "INCONCLUSIVE"
    verdict_details: str


# ---- Stats and verdict computation ----


def _compute_experiment_stats(
    per_run: list[MultiSeedRunResult],
    human_baseline: dict[str, float | int],
) -> dict[str, Any]:
    """Compute means, stds, and pre-registered verdict from per-run results.

    Extracted for independent testability of the decision rule (R10).
    """
    ccap_on_converged = [r for r in per_run if r.ccap_on and r.plateau_check_passed and not r.error]
    ccap_off_converged = [r for r in per_run if not r.ccap_on and r.plateau_check_passed and not r.error]

    if ccap_on_converged:
        clr6_on = [r.clearance_score_6mm for r in ccap_on_converged]
        ccap_on_mean_clr6 = statistics.mean(clr6_on)
        ccap_on_std_clr6 = statistics.stdev(clr6_on) if len(clr6_on) > 1 else 0.0
        therm_on = [r.thermal_score for r in ccap_on_converged]
        ccap_on_mean_therm = statistics.mean(therm_on)
        ccap_on_std_therm = statistics.stdev(therm_on) if len(therm_on) > 1 else 0.0
    else:
        ccap_on_mean_clr6 = 0.0
        ccap_on_std_clr6 = 0.0
        ccap_on_mean_therm = 0.0
        ccap_on_std_therm = 0.0

    if ccap_off_converged:
        clr6_off = [r.clearance_score_6mm for r in ccap_off_converged]
        ccap_off_mean_clr6 = statistics.mean(clr6_off)
        ccap_off_std_clr6 = statistics.stdev(clr6_off) if len(clr6_off) > 1 else 0.0
        therm_off = [r.thermal_score for r in ccap_off_converged]
        ccap_off_mean_therm = statistics.mean(therm_off)
        ccap_off_std_therm = statistics.stdev(therm_off) if len(therm_off) > 1 else 0.0
    else:
        ccap_off_mean_clr6 = 0.0
        ccap_off_std_clr6 = 0.0
        ccap_off_mean_therm = 0.0
        ccap_off_std_therm = 0.0

    human_clr6_floor = float(human_baseline["clearance_score_6mm"])
    ccap_on_best_clr6 = max((r.clearance_score_6mm for r in ccap_on_converged), default=0.0)
    ccap_on_best_therm = max((r.thermal_score for r in ccap_on_converged), default=0.0)

    # Guard: no converged C-CAP-on runs means no data to evaluate
    if not ccap_on_converged:
        verdict = "INCONCLUSIVE"
        verdict_details = "No C-CAP-on runs converged — insufficient data for verdict"
    else:
        dissolved = (
            ccap_on_mean_clr6 >= _DISSOLVED_CLR6_MIN
            and ccap_on_std_clr6 < _DISSOLVED_CLR6_STD_MAX
            and ccap_on_mean_therm >= _DISSOLVED_THERM_MIN
        )
        holds = (
            ccap_on_best_clr6 < human_clr6_floor
            and ccap_on_best_therm < _DISSOLVED_THERM_MIN
        )

        if dissolved:
            verdict = "DISSOLVED"
            verdict_details = (
                f"C-CAP-on mean clearance_6mm={ccap_on_mean_clr6:.3f} "
                f"(std={ccap_on_std_clr6:.3f}) >= {_DISSOLVED_CLR6_MIN}, "
                f"mean thermal={ccap_on_mean_therm:.3f} >= {_DISSOLVED_THERM_MIN}"
            )
        elif holds:
            verdict = "HOLDS"
            verdict_details = (
                f"C-CAP-on best clearance_6mm={ccap_on_best_clr6:.3f} "
                f"< human floor={human_clr6_floor:.3f}, "
                f"best thermal={ccap_on_best_therm:.3f} < {_DISSOLVED_THERM_MIN}"
            )
        else:
            verdict = "INCONCLUSIVE"
            verdict_details = (
                f"Neither DISSOLVED nor HOLDS thresholds met: "
                f"mean_clr6={ccap_on_mean_clr6:.3f}(std={ccap_on_std_clr6:.3f}), "
                f"mean_therm={ccap_on_mean_therm:.3f}, "
                f"best_clr6={ccap_on_best_clr6:.3f}, "
                f"best_therm={ccap_on_best_therm:.3f}, "
                f"human_clr6_floor={human_clr6_floor:.3f}"
            )

    return {
        "ccap_on_mean_clr6": ccap_on_mean_clr6,
        "ccap_on_std_clr6": ccap_on_std_clr6,
        "ccap_on_mean_therm": ccap_on_mean_therm,
        "ccap_on_std_therm": ccap_on_std_therm,
        "ccap_off_mean_clr6": ccap_off_mean_clr6,
        "ccap_off_std_clr6": ccap_off_std_clr6,
        "ccap_off_mean_therm": ccap_off_mean_therm,
        "ccap_off_std_therm": ccap_off_std_therm,
        "verdict": verdict,
        "verdict_details": verdict_details,
        "n_ccap_on": len(ccap_on_converged),
        "n_ccap_off": len(ccap_off_converged),
        "human_clr6_floor": human_clr6_floor,
        "ccap_on_best_clr6": ccap_on_best_clr6,
        "ccap_on_best_therm": ccap_on_best_therm,
    }


# Public alias for the verdict-decision function (consumed by helps-battery U3).
compute_experiment_stats = _compute_experiment_stats


# ---- Multi-seed experiment runner ----


def run_multi_seed_experiment(
    pcb_path: Path,
    spec_path: Path | None = None,
    epochs: int = 50000,
    n_seeds: int = 10,
    verbose: bool = True,
) -> MultiSeedExperimentResult:
    """
    Run a pre-registered multi-seed experiment: n_seeds x {C-CAP on, C-CAP off}
    against the corrected dual-rail clearance metric.

    Weights frozen at: thermal=4000, clearance=200, loop_area=1,
    overlap=200, boundary=100, wirelength=20, spread=5.

    Convergence is determined by the optimizer's built-in early_stopping
    signal (result.converged), not a post-hoc plateau check. Every run
    gets the same epoch budget (default 50k) with early_stopping enabled.

    Args:
        pcb_path: Path to the KiCad PCB file.
        spec_path: Path to pcb_spec.yaml.
        epochs: Number of optimizer epochs per run.
        n_seeds: Number of seeds (default 10).
        verbose: Whether to print per-run progress.

    Returns:
        MultiSeedExperimentResult with per-run data, means, and verdict.
    """
    board_id = pcb_path.stem

    if spec_path is None:
        default_spec = Path("configs/pcb_spec.yaml")
        spec_path = default_spec if default_spec.exists() else pcb_path.parent / "pcb_spec.yaml"

    if spec_path is None or not Path(spec_path).exists():
        raise FileNotFoundError(f"PCB spec not found: {spec_path}")

    spec = PcbSpecification.load(spec_path)
    design_rules = create_temper_design_rules()
    parse_result = parse_kicad_pcb(pcb_path, design_rules=design_rules)
    netlist = parse_result.netlist
    board = parse_result.board
    if board is None:
        raise ValueError("No board geometry extracted from PCB")

    derived = derive_constraints_from_spec(spec, netlist)
    threshold_mm = derived.get("hv_lv_isolation_mm", 6.5)

    placement_constraints = PlacementConstraints(
        board_width_mm=board.width,
        board_height_mm=board.height,
        board_margin_mm=2.0,
        hv_clearance_mm=threshold_mm,
    )

    # Experiment weights (frozen per R9)
    weights = {
        "overlap": 200.0,
        "boundary": 100.0,
        "clearance": 200.0,
        "wirelength": 20.0,
        "spread": 5.0,
        "thermal": 4000.0,
        "loop_area": 1.0,
    }

    clearance_rules = []
    if threshold_mm > 0:
        from temper_placer.losses.types import ClearanceRule
        clearance_rules.append(
            ClearanceRule(
                net_class_a="HighVoltage",
                net_class_b="Signal",
                min_clearance=threshold_mm,
            )
        )

    thermal_constraints: list[ThermalConstraint] = []
    for ref, power in spec.thermal.power_dissipation.items():
        thermal_constraints.append(
            ThermalConstraint(
                component_ref=ref,
                edge=spec.thermal.target_edge,
                max_distance=spec.thermal.max_heatspread_mm,
                weight=power,
                because=f"{power}W dissipation requires {spec.thermal.target_edge} edge placement",
            )
        )

    comm_max_area = spec.emi.max_loop_area_mm2.get("commutation_loop", 80.0)
    loop_constraints: list[LoopConstraint] = [
        LoopConstraint(
            name="commutation_loop",
            pins=(
                ("C_BUS1", "1"), ("Q1", "2"), ("Q1", "3"),
                ("Q2", "2"), ("Q2", "3"), ("C_BUS2", "2"),
                ("C_BUS2", "1"), ("C_BUS1", "2"),
            ),
            max_area=comm_max_area,
            weight=10.0,
            because="Main switching loop",
        ),
    ]

    context = LossContext.from_netlist_and_board(
        netlist, board,
        clearance_rules=clearance_rules,
        thermal_constraints=thermal_constraints,
        loop_constraints=loop_constraints,
    )

    pin_loop_losses = [
        WeightedLoss(LoopAreaLoss(area_penalty_scale=0.01, routing_factor=1.0),
                     weights.get("loop_area", 20.0)),
    ]

    comp_loop_losses = []
    for loop_name, comp_refs in spec.emi.loop_components.items():
        if loop_name == "commutation_loop":
            continue
        max_area = spec.emi.max_loop_area_mm2.get(loop_name, 100.0)
        if len(comp_refs) >= 3:
            comp_loop_losses.append(
                ComponentLoopConfig(name=loop_name, component_refs=list(comp_refs),
                                    max_area_mm2=max_area * 0.5, weight=5.0))

    loss_fn = CompositeLoss([
        WeightedLoss(OverlapLoss(margin=1.0, rotation_invariant=True), weights["overlap"]),
        WeightedLoss(BoundaryLoss(), weights["boundary"]),
        WeightedLoss(
            ClearanceLoss(default_hv_lv_clearance=6.0),
            weights["clearance"],
        ),
        WeightedLoss(WirelengthLoss(), weights["wirelength"]),
        WeightedLoss(SpreadLoss(), weights["spread"]),
        WeightedLoss(ThermalLoss(margin=2.0), weights.get("thermal", 30.0)),
    ] + pin_loop_losses + ([
        WeightedLoss(
            ComponentLoopAreaLoss(loops=comp_loop_losses, margin=10.0,
                                  min_separation_mm=2.0),
            weights.get("loop_area", 5.0),
        ),
    ] if comp_loop_losses else []))

    # Build quality config
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

    quality_config["min_hv_lv_clearance"] = threshold_mm
    quality_config["thermal_target_edge"] = spec.thermal.target_edge
    quality_config["thermal_max_distance"] = spec.thermal.max_heatspread_mm

    if spec.emi.loop_components:
        spec_loops = [comps for comps in spec.emi.loop_components.values() if len(comps) >= 3]
        if spec_loops:
            quality_config["loop_components"] = spec_loops

    human_baseline = _score_human_inline(parse_result, spec_path, verbose=False)

    # ---- Run experiment ----

    per_run: list[MultiSeedRunResult] = []
    seeds = list(range(n_seeds))
    total_runs = n_seeds * 2
    run_idx = 0

    for ccap_on in (True, False):
        for seed in seeds:
            run_idx += 1
            run_start = time.time()

            if verbose:
                label = "C-CAP ON " if ccap_on else "C-CAP OFF"
                print(f"[{run_idx}/{total_runs}] {label} seed={seed} ...")

            try:
                pipeline = create_default_pipeline()
                rng = np.random.default_rng(seed)
                preset = pipeline.run(board, netlist, None, rng)
                initial_state = preset.state

                pos = initial_state.positions
                if not np.all(np.isfinite(pos)):
                    margin_inner = min(2.0, board.width * 0.1, board.height * 0.1)
                    px = rng.uniform(margin_inner, board.width - margin_inner, size=netlist.n_components)
                    py = rng.uniform(margin_inner, board.height - margin_inner, size=netlist.n_components)
                    from dataclasses import replace as dc_replace
                    initial_state = dc_replace(
                        initial_state,
                        positions=np.stack([px, py], axis=-1),
                        rotation_logits=np.zeros_like(initial_state.rotation_logits),
                    )

                phases = create_default_phases(epochs)
                cfg = OptimizerConfig(
                    epochs=epochs,
                    seed=seed,
                    log_interval=max(1, epochs // 100),
                    curriculum_phases=phases,
                    use_centrality_weighting=False,
                )
                cfg.initialization.ccap_enabled = ccap_on

                result = train_multiphase(
                    netlist, board, lambda _: loss_fn, context, cfg,
                    initial_state=initial_state,
                    constraints=placement_constraints if ccap_on else None,
                )
                elapsed = time.time() - run_start

                # Convergence: use optimizer's built-in signal (early_stopping trigger)
                plateau_check_passed = result.converged
                plateau_slope = float("inf")
                if result.history and len(result.history) >= 5:
                    n_last = max(5, int(len(result.history) * _CONVERGENCE_FRACTION))
                    losses = [m.loss for m in result.history[-n_last:]]
                    epochs_arr = list(range(len(losses)))
                    n = len(epochs_arr)
                    sum_x = sum(epochs_arr)
                    sum_y = sum(losses)
                    sum_xy = sum(x * y for x, y in zip(epochs_arr, losses))
                    sum_xx = sum(x * x for x in epochs_arr)
                    denom = n * sum_xx - sum_x * sum_x
                    if abs(denom) > 1e-12:
                        slope = abs((n * sum_xy - sum_x * sum_y) / denom)
                        if not math.isnan(slope):
                            plateau_slope = slope

                # Score with dual-rail metric
                dc_report = dual_rail_clearance_report(
                    result.final_state, netlist,
                    quality_config.get("hv_components", set()),
                    quality_config.get("lv_components", set()),
                )

                # Thermal score
                therm = thermal_score(
                    result.final_state, netlist, board,
                    quality_config.get("thermal_components", set()),
                    target_edge=quality_config.get("thermal_target_edge", "TOP"),
                    max_distance=quality_config.get("thermal_max_distance", 10.0),
                )

                if ccap_on:
                    ccap_status = "converged"
                    ccap_cycles = cfg.initialization.ccap_max_cycles
                    ccap_clearance = None
                else:
                    ccap_status = "disabled"
                    ccap_cycles = 0
                    ccap_clearance = None

                run_result = MultiSeedRunResult(
                    seed=seed,
                    ccap_on=ccap_on,
                    converged=plateau_check_passed,
                    ccap_convergence_status=ccap_status,
                    ccap_cycles=ccap_cycles,
                    ccap_post_projection_clearance=ccap_clearance,
                    clearance_score_3mm=float(dc_report["clearance_score_3mm"]),
                    clearance_score_6mm=float(dc_report["clearance_score_6mm"]),
                    violations_3mm=int(dc_report["violations_3mm"]),
                    violations_6mm=int(dc_report["violations_6mm"]),
                    thermal_score=float(therm),
                    final_loss=float(result.final_loss),
                    plateau_check_passed=plateau_check_passed,
                    plateau_slope=float(plateau_slope),
                    elapsed_seconds=elapsed,
                )

                if verbose:
                    print(f"    loss={result.final_loss:.2f} "
                          f"clr3={dc_report['clearance_score_3mm']:.3f} "
                          f"clr6={dc_report['clearance_score_6mm']:.3f} "
                          f"v3={dc_report['violations_3mm']} "
                          f"v6={dc_report['violations_6mm']} "
                          f"therm={therm:.3f} "
                          f"converged={'YES' if plateau_check_passed else 'NO'} "
                          f"({elapsed:.1f}s)")

            except Exception as e:
                run_result = MultiSeedRunResult(
                    seed=seed,
                    ccap_on=ccap_on,
                    converged=False,
                    ccap_convergence_status="failed" if ccap_on else "disabled",
                    ccap_cycles=0,
                    ccap_post_projection_clearance=None,
                    clearance_score_3mm=0.0,
                    clearance_score_6mm=0.0,
                    violations_3mm=0,
                    violations_6mm=0,
                    thermal_score=0.0,
                    final_loss=float("inf"),
                    plateau_check_passed=False,
                    plateau_slope=float("inf"),
                    elapsed_seconds=time.time() - run_start,
                    error=str(e),
                )
                if verbose:
                    print(f"    ERROR: {e}")

            per_run.append(run_result)

    stats = _compute_experiment_stats(per_run, human_baseline)

    n_converged_rows = stats["n_ccap_on"] + stats["n_ccap_off"]
    n_flagged = len(per_run) - n_converged_rows

    if verbose:
        print()
        print("=" * 60)
        print(f"EXPERIMENT COMPLETE: {board_id}")
        print(f"  Verdict: {stats['verdict']}")
        print(f"  {stats['verdict_details']}")
        print(f"  Human floor: clearance_6mm={stats['human_clr6_floor']:.3f}")
        print(f"  C-CAP ON  (n={stats['n_ccap_on']} converged): "
              f"clr6={stats['ccap_on_mean_clr6']:.3f}±{stats['ccap_on_std_clr6']:.3f}, "
              f"therm={stats['ccap_on_mean_therm']:.3f}±{stats['ccap_on_std_therm']:.3f}")
        print(f"  C-CAP OFF (n={stats['n_ccap_off']} converged): "
              f"clr6={stats['ccap_off_mean_clr6']:.3f}±{stats['ccap_off_std_clr6']:.3f}, "
              f"therm={stats['ccap_off_mean_therm']:.3f}±{stats['ccap_off_std_therm']:.3f}")
        if n_flagged > 0:
            print(f"  Flagged (non-converged): {n_flagged} runs")
        print("=" * 60)

    return MultiSeedExperimentResult(
        board_id=board_id,
        n_seeds=n_seeds,
        per_run=per_run,
        human_baseline=human_baseline,
        ccap_on_mean_clearance_6mm=stats["ccap_on_mean_clr6"],
        ccap_on_std_clearance_6mm=stats["ccap_on_std_clr6"],
        ccap_on_mean_thermal=stats["ccap_on_mean_therm"],
        ccap_on_std_thermal=stats["ccap_on_std_therm"],
        ccap_off_mean_clearance_6mm=stats["ccap_off_mean_clr6"],
        ccap_off_std_clearance_6mm=stats["ccap_off_std_clr6"],
        ccap_off_mean_thermal=stats["ccap_off_mean_therm"],
        ccap_off_std_thermal=stats["ccap_off_std_therm"],
        verdict=stats["verdict"],
        verdict_details=stats["verdict_details"],
    )


# ---- Inline human baseline scorer ----


def _score_human_inline(
    parse_result: Any,
    spec_path: Path,
    verbose: bool = False,
) -> dict[str, float | int]:
    """Inline human baseline scoring used by the experiment runner."""
    netlist = parse_result.netlist
    board = parse_result.board

    spec = PcbSpecification.load(spec_path)
    derived = derive_constraints_from_spec(spec, netlist)

    pipeline = create_default_pipeline()
    rng = np.random.default_rng(0)
    preset = pipeline.run(board, netlist, None, rng)
    state = preset.state

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

    return dual_rail_clearance_report(
        state, netlist,
        quality_config.get("hv_components", set()),
        quality_config.get("lv_components", set()),
    )
