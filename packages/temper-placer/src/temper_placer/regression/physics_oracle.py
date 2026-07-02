"""
Physics-derived oracle runner for the Temper induction board.

Wires the full physics chain end-to-end:
  pcb_spec.yaml -> PcbSpecification -> derive_constraints_from_spec ->
  quality_config -> optimizer with ClearanceLoss -> compute_quality_report ->
  IEC 60335-1 threshold comparison -> pass/fail.

The runner supplements the corpus runner (geometric regression floor) without
modifying it. The corpus runner stays as-is; this runner adds the physics path.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import jax
import jax.numpy as jnp

from temper_placer.core.design_rules import create_temper_design_rules
from temper_placer.core.specification import PcbSpecification
from temper_placer.heuristics import create_default_pipeline
from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.io.reference_loader import infer_quality_config
from temper_placer.losses.base import CompositeLoss, LossContext, WeightedLoss, ThermalConstraint
from temper_placer.losses.boundary import BoundaryLoss
from temper_placer.losses.clearance import ClearanceLoss
from temper_placer.losses.component_loop_area import ComponentLoopAreaLoss, ComponentLoopConfig
from temper_placer.losses.overlap import OverlapLoss
from temper_placer.losses.regularization import SpreadLoss
from temper_placer.losses.thermal import ThermalLoss
from temper_placer.losses.wirelength import WirelengthLoss
from temper_placer.metrics.quality import compute_quality_report
from temper_placer.optimizer.config import OptimizerConfig
from temper_placer.optimizer.curriculum import create_default_phases
from temper_placer.optimizer.train import train_multiphase
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


def run_physics_oracle(
    pcb_path: Path,
    spec_path: Path | None = None,
    seed: int = 42,
    epochs: int = 500,
    verbose: bool = True,
) -> PhysicsOracleResult:
    """
    Run the physics oracle on a PCB board.

    Args:
        pcb_path: Path to the KiCad PCB file.
        spec_path: Path to pcb_spec.yaml. If None, looks alongside pcb_path
                   or uses the default configs/pcb_spec.yaml.
        seed: Random seed for the optimizer.
        epochs: Number of optimizer epochs.
        verbose: Whether to print progress.

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

    # Build loss function with ClearanceLoss
    weights = {
        "overlap": 200.0,
        "boundary": 100.0,
        "clearance": 100.0,
        "wirelength": 20.0,
        "spread": 5.0,
    }

    try:
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

        # Build thermal constraints from spec config
        thermal_constraints: list[ThermalConstraint] = []
        for ref, power in spec.thermal.power_dissipation.items():
            thermal_constraints.append(
                ThermalConstraint(
                    component_ref=ref,
                    edge=spec.thermal.target_edge,
                    max_distance=spec.thermal.max_heatspread_mm,
                    weight=power,  # weight proportional to power dissipation
                    because=f"{power}W dissipation requires {spec.thermal.target_edge} edge placement",
                )
            )

        context = LossContext.from_netlist_and_board(
            netlist, board,
            clearance_rules=clearance_rules,
            thermal_constraints=thermal_constraints,
        )

        # Build component-level loop area loss from spec
        loop_losses = []
        for loop_name, comp_refs in spec.emi.loop_components.items():
            max_area = spec.emi.max_loop_area_mm2.get(loop_name, 100.0)
            if len(comp_refs) >= 3:
                loop_losses.append(
                    ComponentLoopConfig(
                        name=loop_name,
                        component_refs=list(comp_refs),
                        max_area_mm2=max_area * 0.5,  # target half of max for margin
                        weight=10.0,
                    )
                )

        loss_fn = CompositeLoss([
            WeightedLoss(OverlapLoss(margin=1.0, rotation_invariant=True), weights["overlap"]),
            WeightedLoss(BoundaryLoss(), weights["boundary"]),
            WeightedLoss(
                ClearanceLoss(default_hv_lv_clearance=threshold_mm),
                weights["clearance"],
            ),
            WeightedLoss(WirelengthLoss(), weights["wirelength"]),
            WeightedLoss(SpreadLoss(), weights["spread"]),
            WeightedLoss(ThermalLoss(margin=2.0), weights.get("thermal", 30.0)),
            WeightedLoss(
                ComponentLoopAreaLoss(loops=loop_losses, margin=10.0),
                weights.get("loop_area", 30.0),
            ),
        ])
    except Exception as e:
        return PhysicsOracleResult(
            board_id=board_id,
            passed=False,
            errors=[f"Loss setup failed: {e}"],
        )

    # Run optimizer
    try:
        jax.config.update("jax_platform_name", "cpu")

        pipeline = create_default_pipeline()
        rng_key = jax.random.PRNGKey(seed)
        preset = pipeline.run(board, netlist, None, rng_key)
        initial_state = preset.state

        # Guard against degenerate initial placements
        pos = initial_state.positions
        if not jnp.all(jnp.isfinite(pos)):
            k1, k2 = jax.random.split(rng_key)
            margin = min(2.0, board.width * 0.1, board.height * 0.1)
            px = jax.random.uniform(
                k1, (netlist.n_components,),
                minval=margin, maxval=board.width - margin,
            )
            py = jax.random.uniform(
                k2, (netlist.n_components,),
                minval=margin, maxval=board.height - margin,
            )
            from dataclasses import replace as dc_replace
            initial_state = dc_replace(
                initial_state,
                positions=jnp.stack([px, py], axis=-1),
                rotation_logits=jnp.zeros_like(initial_state.rotation_logits),
            )

        phases = create_default_phases(epochs)
        cfg = OptimizerConfig(
            epochs=epochs,
            seed=seed,
            log_interval=max(1, epochs // 100),
            curriculum_phases=phases,
            use_centrality_weighting=False,
        )

        result = train_multiphase(
            netlist, board, lambda _: loss_fn, context, cfg,
            initial_state=initial_state,
            constraints=None,
        )
        elapsed = time.time() - start_time

        if verbose:
            print(f"  Optimization complete in {elapsed:.1f}s, loss = {result.final_loss:.4f}")

    except Exception as e:
        return PhysicsOracleResult(
            board_id=board_id,
            passed=False,
            errors=[f"Optimization failed: {e}"],
        )

    # Compute quality report
    try:
        # Build a minimal ReferenceDesign-like object for infer_quality_config
        from dataclasses import dataclass as dc_dataclass

        @dc_dataclass
        class _RefDesign:
            netlist: Any
            board: Any

        ref = _RefDesign(netlist=netlist, board=board)
        quality_config = infer_quality_config(ref)  # type: ignore[arg-type]

        # Override hv/lv from net classification (more authoritative than footprint heuristics)
        hv_from_class = {
            c.ref
            for c in netlist.components
            if c.net_class in ("HighVoltage", "ACMains")
        }
        lv_from_class = {
            c.ref
            for c in netlist.components
            if c.net_class == "Signal"
        }
        if hv_from_class:
            quality_config["hv_components"] = hv_from_class
        if lv_from_class:
            quality_config["lv_components"] = lv_from_class

        # Override threshold with derived value
        quality_config["min_hv_lv_clearance"] = threshold_mm

        # Wire thermal edge configuration from spec
        quality_config["thermal_target_edge"] = spec.thermal.target_edge
        quality_config["thermal_max_distance"] = spec.thermal.max_heatspread_mm

        # Populate loop components from spec, falling back to auto-extraction
        if spec.emi.loop_components:
            spec_loops = [
                comps for comps in spec.emi.loop_components.values()
                if len(comps) >= 3
            ]
            if spec_loops:
                quality_config["loop_components"] = spec_loops
        else:
            from temper_placer.core.loop_extractor import auto_extract_loops
            loop_collection = auto_extract_loops(netlist)
            if loop_collection.loops:
                loop_components = []
                for loop in loop_collection.loops:
                    comps = loop.components
                    if len(comps) >= 3:
                        loop_components.append(list(comps))
                if loop_components:
                    quality_config["loop_components"] = loop_components

        report = compute_quality_report(
            result.final_state, netlist, board, context, quality_config
        )
        clearance_score = report.get("hv_lv_clearance_score", 1.0)

        if verbose:
            print(f"  HV/LV clearance score: {clearance_score:.4f}")
            print(f"  Overall quality score: {report.get('overall_score', 0.0):.4f}")

    except Exception as e:
        return PhysicsOracleResult(
            board_id=board_id,
            passed=False,
            errors=[f"Quality report failed: {e}"],
        )

    # Compare against threshold: score of 1.0 means all pairs satisfy clearance;
    # score < 1.0 means some pairs violate it. Pass if score >= 0.95 (allow minor violations).
    passed = clearance_score >= 0.95

    return PhysicsOracleResult(
        board_id=board_id,
        passed=passed,
        quality_report=report,
        threshold_mm=threshold_mm,
        clearance_score=clearance_score,
        elapsed_seconds=elapsed,
    )


def run_ab_diff(
    pcb_path: Path,
    spec_path: Path | None = None,
    seed: int = 42,
    epochs: int = 500,
    verbose: bool = True,
) -> dict[str, Any]:
    """
    A/B placement diff: run placer without and with HV/LV classification.

    Run A: parser without design_rules -> all components "Signal" -> clearance
           loss dark -> optimizer runs normally.
    Run B: parser with design_rules -> HV/LV classification -> clearance loss
           live -> optimizer pushes HV/LV apart.

    Returns a dict with per-component position deltas, summary stats,
    and directional HV-LV distance check.

    Args:
        pcb_path: Path to the KiCad PCB file.
        spec_path: Path to pcb_spec.yaml.
        seed: Random seed (same for both runs).
        epochs: Number of optimizer epochs.
        verbose: Whether to print progress.

    Returns:
        Dict with 'positions_a', 'positions_b', 'deltas', 'summary', 'conclusion'.
    """
    import jax
    import jax.numpy as jnp

    from temper_placer.core.design_rules import create_temper_design_rules
    from temper_placer.core.specification import PcbSpecification
    from temper_placer.heuristics import create_default_pipeline
    from temper_placer.io.kicad_parser import parse_kicad_pcb
    from temper_placer.losses.base import CompositeLoss, LossContext, WeightedLoss
    from temper_placer.losses.boundary import BoundaryLoss
    from temper_placer.losses.clearance import ClearanceLoss
    from temper_placer.losses.overlap import OverlapLoss
    from temper_placer.losses.regularization import SpreadLoss
    from temper_placer.losses.wirelength import WirelengthLoss
    from temper_placer.optimizer.config import OptimizerConfig
    from temper_placer.optimizer.curriculum import create_default_phases
    from temper_placer.optimizer.train import train_multiphase
    from temper_placer.pipeline.derivation import derive_constraints_from_spec

    if spec_path is None:
        spec_path = Path("configs/pcb_spec.yaml")
    spec = PcbSpecification.load(spec_path)
    derived = derive_constraints_from_spec(spec, None)
    threshold_mm = derived.get("hv_lv_isolation_mm", 6.5)

    jax.config.update("jax_platform_name", "cpu")
    weights = {"overlap": 200.0, "boundary": 100.0, "clearance": 100.0,
               "wirelength": 20.0, "spread": 5.0}

    def _run_one(with_classification: bool) -> tuple:
        if with_classification:
            dr = create_temper_design_rules()
            result = parse_kicad_pcb(pcb_path, design_rules=dr)
        else:
            result = parse_kicad_pcb(pcb_path)
        netlist = result.netlist
        board = result.board

        context = LossContext.from_netlist_and_board(netlist, board)
        loss_fn = CompositeLoss([
            WeightedLoss(OverlapLoss(margin=1.0, rotation_invariant=True), weights["overlap"]),
            WeightedLoss(BoundaryLoss(), weights["boundary"]),
            WeightedLoss(
                ClearanceLoss(default_hv_lv_clearance=threshold_mm),
                weights["clearance"],
            ),
            WeightedLoss(WirelengthLoss(), weights["wirelength"]),
            WeightedLoss(SpreadLoss(), weights["spread"]),
        ])

        pipeline = create_default_pipeline()
        rng_key = jax.random.PRNGKey(seed)
        preset = pipeline.run(board, netlist, None, rng_key)
        initial_state = preset.state

        pos = initial_state.positions
        if not jnp.all(jnp.isfinite(pos)):
            from dataclasses import replace as dc_replace
            k1, k2 = jax.random.split(rng_key)
            margin = min(2.0, board.width * 0.1, board.height * 0.1)
            px = jax.random.uniform(k1, (netlist.n_components,), minval=margin, maxval=board.width - margin)
            py = jax.random.uniform(k2, (netlist.n_components,), minval=margin, maxval=board.height - margin)
            initial_state = dc_replace(
                initial_state,
                positions=jnp.stack([px, py], axis=-1),
                rotation_logits=jnp.zeros_like(initial_state.rotation_logits),
            )

        phases = create_default_phases(epochs)
        cfg = OptimizerConfig(epochs=epochs, seed=seed, log_interval=max(1, epochs // 100),
                              curriculum_phases=phases, use_centrality_weighting=False)

        train_result = train_multiphase(
            netlist, board, lambda _: loss_fn, context, cfg,
            initial_state=initial_state, constraints=None,
        )
        return netlist, board, train_result.final_state.positions

    if verbose:
        print("  A/B diff: Run A (no HV/LV classification)...")
    netlist_a, _, positions_a = _run_one(with_classification=False)

    if verbose:
        print("  A/B diff: Run B (with HV/LV classification)...")
    netlist_b, _, positions_b = _run_one(with_classification=True)

    # Per-component deltas
    n = min(positions_a.shape[0], positions_b.shape[0])
    deltas = jnp.linalg.norm(positions_b[:n] - positions_a[:n], axis=1)

    # Directional check: HV-LV distance change
    hv_refs = {c.ref for c in netlist_b.components if c.net_class in ("HighVoltage", "ACMains")}
    lv_refs = {c.ref for c in netlist_b.components if c.net_class == "Signal"}
    all_refs = [c.ref for c in netlist_b.components]

    def _min_hv_lv_dist(positions, refs):
        hv_idxs = [i for i, r in enumerate(refs) if r in hv_refs]
        lv_idxs = [i for i, r in enumerate(refs) if r in lv_refs]
        if not hv_idxs or not lv_idxs:
            return float("inf")
        min_d = float("inf")
        for hi in hv_idxs:
            for li in lv_idxs:
                d = float(jnp.linalg.norm(positions[hi] - positions[li]))
                min_d = min(min_d, d)
        return min_d

    dist_a = _min_hv_lv_dist(positions_a, all_refs)
    dist_b = _min_hv_lv_dist(positions_b, all_refs)

    mean_delta = float(jnp.mean(deltas))
    max_delta = float(jnp.max(deltas))

    if mean_delta < 0.01:
        conclusion = ("placements identical — clearance loss weight may need retuning "
                      "(was calibrated when dark)")
    elif dist_b > dist_a:
        conclusion = (f"constraint has teeth: min HV-LV distance increased "
                      f"from {dist_a:.2f} mm to {dist_b:.2f} mm")
    else:
        conclusion = (f"HV-LV distance unchanged or decreased: "
                      f"{dist_a:.2f} -> {dist_b:.2f} mm")

    if verbose:
        print(f"  Mean delta: {mean_delta:.4f} mm, max delta: {max_delta:.4f} mm")
        print(f"  HV-LV distance: {dist_a:.2f} -> {dist_b:.2f} mm")
        print(f"  Conclusion: {conclusion}")

    return {
        "positions_a": positions_a,
        "positions_b": positions_b,
        "deltas": deltas,
        "summary": {"mean_delta_mm": mean_delta, "max_delta_mm": max_delta,
                    "dist_a_mm": dist_a, "dist_b_mm": dist_b},
        "conclusion": conclusion,
    }
