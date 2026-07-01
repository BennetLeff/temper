"""Input stage: loads KiCad PCB, constraints, and loop definitions."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from temper_placer.pipeline.dag_types import DataContext, StageResult


class InputStage:
    def __call__(self, state: Any, context: DataContext) -> StageResult:
        start = time.time()
        from temper_placer.io.kicad_parser import parse_kicad_pcb

        input_pcb_path: Path = context["input_pcb"]
        print(f"Loading PCB from {input_pcb_path}")
        if not input_pcb_path.exists():
            from temper_placer.pipeline.state import PipelineError, PipelinePhase
            raise PipelineError(f"Input PCB not found: {input_pcb_path}", phase=PipelinePhase.INPUT)

        try:
            result = parse_kicad_pcb(input_pcb_path)
        except Exception as e:
            from temper_placer.pipeline.state import PipelineError, PipelinePhase
            raise PipelineError(f"Failed to parse PCB: {e}", phase=PipelinePhase.INPUT) from e

        board = result.board
        netlist = result.netlist
        loops: list = []

        state.board = board
        state.netlist = netlist

        from temper_placer.io.config_loader import (
            apply_fixed_components_to_netlist,
            apply_zones_to_netlist,
            create_board_from_constraints,
            load_constraints,
        )

        constraints_yaml: Path | None = context.get("constraints_yaml")
        if constraints_yaml:
            print(f"Loading constraints from {constraints_yaml}")
            try:
                constraints = load_constraints(constraints_yaml)
                constrained_board = create_board_from_constraints(constraints)
                board = constrained_board
                state.board = constrained_board
                apply_fixed_components_to_netlist(netlist, constraints)
                apply_zones_to_netlist(netlist, constraints)
            except Exception as e:
                from temper_placer.pipeline.state import PipelineError, PipelinePhase
                raise PipelineError(f"Failed to load constraints: {e}", phase=PipelinePhase.INPUT) from e
        else:
            class MockConstraints:
                constraints: list = []
            mock_constraints = MockConstraints()
            constraints = mock_constraints  # type: ignore[assignment]

        state.constraints = constraints
        state.loops = loops

        # Enrich PCL constraints from design data
        if hasattr(state.constraints, "pcl_constraints"):
            try:
                from temper_placer.losses.decoupling import auto_detect_decoupling_set

                detections = auto_detect_decoupling_set(netlist)
                for constraint in detections.to_constraints():
                    state.constraints.pcl_constraints.append(constraint)
                if detections.detections:
                    print(
                        f"  Auto-detected {len(detections.detections)} decoupling "
                        f"constraints ({detections.bypass_count} bypass, "
                        f"{detections.bulk_count} bulk)"
                    )
            except Exception as e:
                print(f"  Note: decoupling auto-detection skipped ({e})")

        from temper_placer.core.specification import PcbSpecification
        from temper_placer.pipeline.derivation import derive_constraints_from_spec

        spec_path = Path("packages/temper-placer/configs/pcb_spec.yaml")
        if spec_path.exists():
            print(f"Loading specification from {spec_path}")
            spec = PcbSpecification.load(spec_path)
            derived = derive_constraints_from_spec(spec, netlist)
            print(f"  Derived {len(derived)} physical constraints from spec.")

        elapsed = time.time() - start
        return StageResult(
            outputs={
                "board": board,
                "netlist": netlist,
                "constraints": constraints,
                "loops": loops,
            },
            duration_s=elapsed,
        )
