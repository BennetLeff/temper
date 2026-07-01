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

        # Wire PCL constraint auto-enrichment
        pcl_constraints_yaml: Path | None = context.get("pcl_constraints_yaml")
        if pcl_constraints_yaml:
            print(f"Loading PCL constraints from {pcl_constraints_yaml}")
            try:
                from temper_placer.pcl.parser import parse_pcl_file

                pcl_collection = parse_pcl_file(pcl_constraints_yaml)
                pcl_collection.auto_enrich(netlist, board)
                if not hasattr(state, "pcl_constraints"):
                    state.pcl_constraints = pcl_collection
                else:
                    state.pcl_constraints.constraints.extend(
                        pcl_collection.constraints
                    )
                print(
                    f"  Loaded {len(pcl_collection)} PCL constraints "
                    f"(with auto-enrichment)"
                )
            except Exception as e:
                print(f"Warning: Failed to load PCL constraints: {e}")

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
