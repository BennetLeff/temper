from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from temper_placer.io.boundary_registry import BoundaryRegistry
from temper_placer.io.dsn_exporter import DSNExporter
from temper_placer.io.dsn_normalizer import DSNNormalizer

if TYPE_CHECKING:
    from temper_placer.pipeline.orchestrator import PipelineState


class DSNBoundaryExporter:
    """Export DSN at pipeline stage boundaries."""

    @staticmethod
    def export_at_boundary(
        boundary_name: str,
        input_pcb: Path,
        config: Path | None = None,
    ) -> str:
        """Run the monolith pipeline to the named boundary and return DSN text."""
        from temper_placer.pipeline.orchestrator import (
            PipelineConfig,
            PipelineOrchestrator,
            PipelinePhase,
            PipelineState,
        )

        boundary_def = BoundaryRegistry.get_boundary(boundary_name)
        phase_enum = PipelinePhase(boundary_def.phase_name)

        pipeline_config = PipelineConfig(
            input_pcb=input_pcb,
            constraints_yaml=config,
            skip_topological=False,
            skip_routing=False,
            skip_local_refinement=False,
            dry_run=False,
        )

        dsn_results: dict[str, str] = {}

        def make_callback(target_phase: PipelinePhase):
            def callback(phase: PipelinePhase, state: PipelineState) -> None:
                if phase != target_phase:
                    return
                if state.board is None and state.netlist is None:
                    return
                exporter = DSNExporter(
                    board=state.board,
                    netlist=state.netlist,
                    positions=getattr(state.placement_state, 'positions', None) if state.placement_state else None,
                    deterministic=True,
                )
                dsn_expr = exporter.export_pcb(input_pcb.stem)
                dsn_text = str(dsn_expr)
                dsn_text = DSNNormalizer.normalize(dsn_text)
                dsn_results[target_phase.value] = dsn_text
            return callback

        orchestrator = PipelineOrchestrator(pipeline_config)
        orchestrator.on_phase_complete = make_callback(phase_enum)
        orchestrator.run()

        return dsn_results.get(phase_enum.value, "")

    @staticmethod
    def export_all_boundaries(
        input_pcb: Path,
        config: Path | None = None,
    ) -> dict[str, str]:
        """Run the pipeline once, snapshot DSN at each registered boundary."""
        from temper_placer.pipeline.orchestrator import (
            PipelineConfig,
            PipelineOrchestrator,
            PipelinePhase,
            PipelineState,
        )

        pipeline_config = PipelineConfig(
            input_pcb=input_pcb,
            constraints_yaml=config,
            skip_topological=False,
            skip_routing=False,
            skip_local_refinement=False,
            dry_run=False,
        )

        dsn_results: dict[str, str] = {}

        # Collect all phase -> boundary mappings
        phase_to_boundary: dict[PipelinePhase, str] = {}
        for name in BoundaryRegistry.list_boundaries():
            bd = BoundaryRegistry.get_boundary(name)
            phase_to_boundary[PipelinePhase(bd.phase_name)] = name

        def callback(phase: PipelinePhase, state: PipelineState) -> None:
            if state.board is None or state.netlist is None:
                return
            if phase not in phase_to_boundary:
                return
            exporter = DSNExporter(
                board=state.board,
                netlist=state.netlist,
                positions=getattr(state.placement_state, 'positions', None) if state.placement_state else None,
                deterministic=True,
            )
            dsn_expr = exporter.export_pcb(input_pcb.stem)
            dsn_text = str(dsn_expr)
            dsn_text = DSNNormalizer.normalize(dsn_text)
            boundary_name = phase_to_boundary[phase]
            dsn_results[boundary_name] = dsn_text

        orchestrator = PipelineOrchestrator(pipeline_config)
        orchestrator.on_phase_complete = callback
        orchestrator.run()

        return dsn_results
