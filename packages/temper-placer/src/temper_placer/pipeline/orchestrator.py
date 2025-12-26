"""
Pipeline orchestrator for temper-placer.

This module coordinates the execution of all pipeline phases.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from temper_placer.pipeline.state import (
    PipelineConfig,
    PipelineError,
    PipelinePhase,
    PipelineState,
)


class PipelineOrchestrator:
    """Orchestrates the full placement pipeline."""

    def __init__(self, config: PipelineConfig):
        """Initialize the orchestrator with configuration."""
        self.config = config
        self.state = PipelineState(config=config)

        # Phase handlers
        self.phases: dict[PipelinePhase, Callable[[PipelineState], PipelineState]] = {
            PipelinePhase.INPUT: self._run_input,
            PipelinePhase.SEMANTIC: self._run_semantic,
            PipelinePhase.TOPOLOGICAL: self._run_topological,
            PipelinePhase.PREFLIGHT: self._run_preflight,
            PipelinePhase.GEOMETRIC: self._run_geometric,
            PipelinePhase.ROUTING: self._run_routing,
            PipelinePhase.REFINEMENT: self._run_refinement,
            PipelinePhase.OUTPUT: self._run_output,
        }

        # Callbacks
        self.on_phase_start: Callable[[PipelinePhase, PipelineState], None] | None = None
        self.on_phase_complete: Callable[[PipelinePhase, PipelineState], None] | None = None

    def get_phase_order(self) -> list[PipelinePhase]:
        """Get the ordered list of phases to execute."""
        all_phases = [
            PipelinePhase.INPUT,
            PipelinePhase.SEMANTIC,
            PipelinePhase.TOPOLOGICAL,
            PipelinePhase.PREFLIGHT,
            PipelinePhase.GEOMETRIC,
            PipelinePhase.ROUTING,
            PipelinePhase.REFINEMENT,
            PipelinePhase.OUTPUT,
        ]

        phases = []
        for phase in all_phases:
            if phase == PipelinePhase.TOPOLOGICAL and self.config.skip_topological:
                continue
            if phase in (PipelinePhase.ROUTING, PipelinePhase.REFINEMENT) and self.config.skip_routing:
                continue
            if phase == PipelinePhase.GEOMETRIC and self.config.skip_local_refinement:
                continue
            if self.config.dry_run and phase in (
                PipelinePhase.GEOMETRIC,
                PipelinePhase.ROUTING,
                PipelinePhase.REFINEMENT,
                PipelinePhase.OUTPUT,
            ):
                continue
            phases.append(phase)
        return phases

    def run(self) -> PipelineState:
        """Execute the full pipeline."""
        start_time = time.time()
        phase_order = self.get_phase_order()

        idx = 0
        while idx < len(phase_order):
            phase = phase_order[idx]
            self.state.current_phase = phase

            if self.on_phase_start:
                self.on_phase_start(phase, self.state)

            phase_start = time.time()
            try:
                handler = self.phases[phase]
                self.state = handler(self.state)
            except PipelineError as e:
                self.state.success = False
                self.state.failure_reason = str(e)
                self.state.failed_phase = e.phase if e.phase else phase
                self.state.elapsed_time_s = time.time() - start_time
                return self.state
            except Exception as e:
                import traceback
                print(f"Error in phase {phase}: {e}")
                traceback.print_exc()
                self.state.success = False
                self.state.failure_reason = str(e)
                self.state.failed_phase = phase
                self.state.elapsed_time_s = time.time() - start_time
                return self.state

            self.state.phase_timings[phase] = time.time() - phase_start
            self._save_snapshot(phase)

            if self.on_phase_complete:
                self.on_phase_complete(phase, self.state)

            # Handle refinement loop
            if (
                phase == PipelinePhase.REFINEMENT
                and not self.state._refinement_complete
                and self.state.iteration < self.state.config.max_iterations
            ):
                try:
                    idx = phase_order.index(PipelinePhase.GEOMETRIC)
                    continue
                except ValueError:
                    pass
            idx += 1

        self.state.success = True
        self.state.elapsed_time_s = time.time() - start_time
        return self.state

    def _save_snapshot(self, phase: PipelinePhase) -> None:
        """Save state snapshot (JSON + SVG)."""
        from temper_placer.io.snapshot import save_json_snapshot, save_svg_snapshot
        
        snapshot_dir = Path("snapshots")
        if self.config.output_pcb:
            snapshot_dir = self.config.output_pcb.parent / "snapshots"
            
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        
        phase_idx = self.get_phase_order().index(phase)
        prefix = f"{phase_idx:02d}_{phase.value}"
        if phase == PipelinePhase.REFINEMENT:
            prefix += f"_iter{self.state.iteration}"
            
        json_path = snapshot_dir / f"{prefix}.json"
        svg_path = snapshot_dir / f"{prefix}.svg"
        
        try:
            save_json_snapshot(self.state, json_path)
            save_svg_snapshot(self.state, svg_path)
        except Exception as e:
            print(f"Warning: Failed to save snapshot for {phase}: {e}")

    # ==========================================================================
    # Phase Handler Wrappers
    # ==========================================================================

    def _run_input(self, state: PipelineState) -> PipelineState:
        """Load input files."""
        from temper_placer.io.kicad_parser import parse_kicad_pcb
        from temper_placer.io.config_loader import (
            apply_fixed_components_to_netlist,
            apply_zones_to_netlist,
            create_board_from_constraints,
            load_constraints,
        )
        from temper_placer.core.specification import PcbSpecification
        from temper_placer.pipeline.derivation import derive_constraints_from_spec
        
        print(f"Loading PCB from {state.config.input_pcb}")
        result = parse_kicad_pcb(state.config.input_pcb)
        state.board = result.board
        state.netlist = result.netlist

        if state.config.constraints_yaml:
            print(f"Loading constraints from {state.config.constraints_yaml}")
            state.constraints = load_constraints(state.config.constraints_yaml)
            state.board = create_board_from_constraints(state.constraints)
            apply_fixed_components_to_netlist(state.netlist, state.constraints)
            apply_zones_to_netlist(state.netlist, state.constraints)
        
        spec_path = Path("packages/temper-placer/configs/pcb_spec.yaml")
        if spec_path.exists():
            print(f"Loading specification from {spec_path}")
            spec = PcbSpecification.load(spec_path)
            derive_constraints_from_spec(spec, state.netlist)

        return state

    def _run_semantic(self, state: PipelineState) -> PipelineState:
        """Extract semantic information (Stub)."""
        return state

    def _run_topological(self, state: PipelineState) -> PipelineState:
        """Run topological placement phase."""
        from temper_placer.pipeline.topological import run_topological_phase
        return run_topological_phase(state)

    def _run_preflight(self, state: PipelineState) -> PipelineState:
        """Run preflight feasibility checks."""
        from temper_placer.pipeline.preflight import PreflightChecker
        from dataclasses import dataclass

        print("Running preflight feasibility checks...")
        @dataclass
        class MockFabPreset:
            min_clearance: float = 0.2
            
        checker = PreflightChecker()
        report = checker.run(state.board, state.netlist, state.constraints, MockFabPreset())
        state.preflight_report = report
        print(report.summary())
        
        if not report.passed:
            raise PipelineError(f"Preflight checks failed", phase=PipelinePhase.PREFLIGHT)
        return state

    def _run_geometric(self, state: PipelineState) -> PipelineState:
        """Run geometric optimization."""
        from temper_placer.pipeline.geometric import run_geometric_phase
        return run_geometric_phase(state)

    def _run_routing(self, state: PipelineState) -> PipelineState:
        """Run routing verification."""
        from temper_placer.routing.congestion import analyze_congestion
        import jax.numpy as jnp
        
        print("Running routing verification...")
        positions = state.placement_state.positions if state.placement_state else jnp.array(state.deterministic_result.positions)
        result = analyze_congestion(state.netlist, state.board, positions=positions)
        print(f"Max congestion: {result.max_utilization:.2f}, Total overflow: {result.total_overflow:.2f}")
        state.routing_result = result
        return state

    def _run_refinement(self, state: PipelineState) -> PipelineState:
        """Run placement-routing refinement loop."""
        from temper_placer.placer.adjustment import adjust_for_congestion
        from temper_placer.optimizer.legalization import legalize_zone_aware
        from temper_placer.pipeline.feedback import analyze_root_cause, ValidationFailure
        from temper_placer.core.state import PlacementState
        import jax.numpy as jnp
        import numpy as np

        if state.routing_result is None or state.routing_result.is_feasible(threshold=state.config.routability_threshold):
            state._refinement_complete = True
            return state

        print(f"Refinement iteration {state.iteration + 1}: Routing congestion too high.")
        failure = ValidationFailure(
            spec_name="routability", 
            actual_value=state.routing_result.max_utilization,
            limit_value=state.config.routability_threshold,
            margin=state.config.routability_threshold - state.routing_result.max_utilization
        )
        analyze_root_cause(failure, state.placement_state or state.deterministic_result, state.netlist, state.board)

        current_pos = np.array(state.placement_state.positions if state.placement_state else state.deterministic_result.positions)
        new_pos = adjust_for_congestion(current_pos, state.netlist, state.board, state.routing_result)
        new_pos, _ = legalize_zone_aware(new_pos, state.netlist, state.board)
        
        state.placement_state = PlacementState.from_positions(jnp.array(new_pos))
        state.iteration += 1
        return state

    def _run_output(self, state: PipelineState) -> PipelineState:
        """Generate output files."""
        from temper_placer.io.kicad_writer import export_placements, add_bounding_boxes_to_pcb, add_silkscreen_labels
        from temper_placer.core.state import PlacementState
        import jax.numpy as jnp
        import json
        
        self._compute_physics_metrics()
        
        if not state.config.output_pcb:
            return state
            
        print(f"Exporting placed PCB to {state.config.output_pcb}...")
        ps = state.placement_state or PlacementState.from_positions(jnp.array(state.deterministic_result.positions))
        
        try:
            export_placements(state.config.input_pcb, state.config.output_pcb, ps, [c.ref for c in state.netlist.components], state.board.origin)
            add_bounding_boxes_to_pcb(state.config.output_pcb)
            add_silkscreen_labels(state.config.output_pcb)
            
            metrics_path = state.config.output_pcb.with_suffix(".metrics.json")
            with open(metrics_path, "w") as f:
                json.dump(state.physics_report.to_dict(), f, indent=2)
        except Exception as e:
            print(f"Error during export: {e}")
            
        return state

    def _compute_physics_metrics(self) -> None:
        """Compute physical metrics."""
        from temper_placer.metrics.physics import measure_emi, measure_geometric, measure_routability, measure_thermal, PhysicsReport
        from temper_placer.core.state import PlacementState
        import jax.numpy as jnp
        
        state = self.state
        if state.placement_state is None and state.deterministic_result is None:
            return
            
        ps = state.placement_state or PlacementState.from_positions(jnp.array(state.deterministic_result.positions))
        geo = measure_geometric(ps, state.netlist, state.board)
        emi = measure_emi(ps, state.netlist, loop_refs=[["Q1", "Q2", "C_BUS1"]])
        thermal = measure_thermal(ps, state.netlist, state.board, power_dissipation={"Q1": 15.0, "Q2": 15.0})
        routability = measure_routability(ps, state.netlist, state.board)
        state.physics_report = PhysicsReport(geometric=geo, emi=emi, thermal=thermal, routability=routability)
