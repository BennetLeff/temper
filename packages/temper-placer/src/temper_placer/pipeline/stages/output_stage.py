"""Output stage: writes placed PCB, metrics, and reports."""

from __future__ import annotations

import json
import time
from typing import Any

import jax.numpy as jnp

from temper_placer.pipeline.dag_types import DataContext, StageResult


class OutputStage:
    def __call__(self, state: Any, context: DataContext) -> StageResult:
        start = time.time()
        from temper_placer.core.state import PlacementState
        from temper_placer.io.kicad_writer import (
            add_bounding_boxes_to_pcb,
            add_silkscreen_labels,
            export_placements,
        )

        _compute_physics_metrics(state)

        output_pcb_path = context.get("output_pcb")
        if not output_pcb_path:
            print("No output path specified.")
            elapsed = time.time() - start
            return StageResult(
                outputs={"output_files": [], "physics_report": state.physics_report},
                duration_s=elapsed,
            )

        print(f"Exporting placed PCB to {output_pcb_path}...")
        input_pcb_path = context["input_pcb"]
        board = context["board"]
        netlist = context["netlist"]
        ps = state.placement_state
        if ps is None:
            deterministic_result = context.get("deterministic_result")
            ps = PlacementState.from_positions(jnp.array(deterministic_result.positions))  # type: ignore[union-attr]

        try:
            write_result = export_placements(input_pcb_path, output_pcb_path, ps,
                                             [c.ref for c in netlist.components], board.origin)
            print(f"  Updated: {write_result.components_updated} components")
            add_bounding_boxes_to_pcb(output_pcb_path)
            add_silkscreen_labels(output_pcb_path)
            metrics_path = output_pcb_path.with_suffix(".metrics.json")
            with open(metrics_path, "w") as f:
                json.dump(state.physics_report.to_dict(), f, indent=2)
            print(f"  Metrics saved to {metrics_path.name}")
            output_files = [output_pcb_path, metrics_path]
        except Exception as e:
            print(f"Error during export: {e}")
            output_files = []

        elapsed = time.time() - start
        return StageResult(
            outputs={
                "output_files": output_files,
                "physics_report": state.physics_report,
            },
            duration_s=elapsed,
        )


def _compute_physics_metrics(state: Any) -> None:
    from temper_placer.core.state import PlacementState
    from temper_placer.metrics.physics import (
        PhysicsReport,
        measure_emi,
        measure_geometric,
        measure_routability,
        measure_thermal,
    )

    if state.placement_state is None and state.deterministic_result is None:
        return
    ps = state.placement_state
    if ps is None:
        ps = PlacementState.from_positions(jnp.array(state.deterministic_result.positions))
    geo = measure_geometric(ps, state.netlist, state.board)
    loop_refs = [["Q1", "Q2", "C_BUS1"], ["U_MCU", "C_MCU_1"]]
    emi = measure_emi(ps, state.netlist, loop_refs=loop_refs)
    power = {"Q1": 15.0, "Q2": 15.0, "U_BUCK": 2.0}
    thermal = measure_thermal(ps, state.netlist, state.board, power_dissipation=power)
    routability = measure_routability(ps, state.netlist, state.board)
    state.physics_report = PhysicsReport(geometric=geo, emi=emi, thermal=thermal, routability=routability)
