"""RouterV6Pipeline adapter — 5 individually callable ``PipelineStage`` instances.

Decomposes the 4-stage ``RouterV6Pipeline`` into standalone stages so each
can be used independently or composed via the strategy-registry composite
``"router_v6_full"``.  The original ``RouterV6Pipeline`` class is **not**
modified.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from temper_placer.router_v6.stage0_data import ParsedPCB  # noqa: F401
    from temper_placer.protocol import PipelineStage, StageInput, StageOutput  # noqa: F401


# ---- Stage 0: Load PCB ------------------------------------------------------


class RouterV6Stage0_LoadPCB:
    """Stage 0: Parse a KiCad PCB file into a ``ParsedPCB``."""

    name = "router_v6/load_pcb"
    requires: list[str] = []
    provides: list[str] = ["parsed_pcb"]
    contract = None

    def run(self, input):
        from temper_placer.io.kicad_parser import parse_kicad_pcb_v6
        from temper_placer.protocol import StageOutput

        path = input.data
        if not isinstance(path, (str, Path)):
            raise TypeError(
                f"RouterV6Stage0 expects Path, got {type(path).__name__}"
            )
        parsed = parse_kicad_pcb_v6(Path(path))
        return StageOutput(data=parsed, meta=input.meta)


# ---- Stage 1: Escape Vias ---------------------------------------------------


class RouterV6Stage1_EscapeVias:
    """Stage 1: Detect dense packages and generate escape vias."""

    name = "router_v6/escape_vias"
    requires: list[str] = ["parsed_pcb"]
    provides: list[str] = ["escape_vias"]
    contract = None

    def run(self, input):
        from temper_placer.router_v6.dense_package_detection import (
            identify_dense_packages,
        )
        from temper_placer.router_v6.escape_via_generator import (
            generate_escape_vias,
        )
        from temper_placer.protocol import StageOutput

        pcb = input.data
        dense_packages = identify_dense_packages(pcb.components)
        escape_vias: list = []
        for dense_pkg in dense_packages:
            vias = generate_escape_vias(
                dense_pkg, pcb.design_rules, strategy="dog-bone"
            )
            if not vias:
                vias = generate_escape_vias(
                    dense_pkg, pcb.design_rules, strategy="via-in-pad"
                )
            escape_vias.extend(vias)
        return StageOutput(data=escape_vias, meta=input.meta)


# ---- Stage 2: Channel Analysis ----------------------------------------------


class RouterV6Stage2_ChannelAnalysis:
    """Stage 2: Channel extraction and analysis."""

    name = "router_v6/channel_analysis"
    requires: list[str] = ["parsed_pcb", "escape_vias"]
    provides: list[str] = ["stage2_output"]
    contract = None

    def run(self, input):
        from temper_placer.router_v6.pipeline import RouterV6Pipeline
        from temper_placer.protocol import StageOutput

        data = input.data
        pcb = data.pcb if hasattr(data, "pcb") else data
        escape_vias = data.escape_vias if hasattr(data, "escape_vias") else []
        pipeline = RouterV6Pipeline(
            verbose=False,
            enable_theta_star=True,
            enable_lazy_theta_star=True,
            enable_smoothing=True,
        )
        stage2 = pipeline._run_stage2(pcb, escape_vias)
        return StageOutput(data=stage2, meta=input.meta)


# ---- Stage 3: Topological Routing -------------------------------------------


class RouterV6Stage3_TopologicalRouting:
    """Stage 3: Topological routing (SAT-based)."""

    name = "router_v6/topological_routing"
    requires: list[str] = ["parsed_pcb", "stage2_output"]
    provides: list[str] = ["stage3_output"]
    contract = None

    def run(self, input):
        from temper_placer.router_v6.pipeline import RouterV6Pipeline
        from temper_placer.protocol import StageOutput

        data = input.data
        pcb = data.pcb if hasattr(data, "pcb") else data
        stage2 = data.stage2_output if hasattr(data, "stage2_output") else data
        pipeline = RouterV6Pipeline(
            verbose=False,
            enable_theta_star=True,
            enable_lazy_theta_star=True,
            enable_smoothing=True,
        )
        stage3 = pipeline._run_stage3(pcb, stage2)
        return StageOutput(data=stage3, meta=input.meta)


# ---- Stage 4: Geometric Realization -----------------------------------------


class RouterV6Stage4_GeometricRealization:
    """Stage 4: Geometric realization (A* pathfinding)."""

    name = "router_v6/geometric_realization"
    requires: list[str] = [
        "parsed_pcb", "stage2_output", "stage3_output", "escape_vias",
    ]
    provides: list[str] = ["stage4_output", "routing_results"]
    contract = None

    def run(self, input):
        from temper_placer.router_v6.pipeline import RouterV6Pipeline
        from temper_placer.protocol import StageOutput

        data = input.data
        pcb = data.pcb if hasattr(data, "pcb") else data
        stage2 = data.stage2_output if hasattr(data, "stage2_output") else None
        stage3 = data.stage3_output if hasattr(data, "stage3_output") else None
        escape_vias = data.escape_vias if hasattr(data, "escape_vias") else []
        pipeline = RouterV6Pipeline(
            verbose=False,
            enable_theta_star=True,
            enable_lazy_theta_star=True,
            enable_smoothing=True,
        )
        stage4 = pipeline._run_stage4(pcb, stage2, stage3, escape_vias)
        return StageOutput(data=stage4, meta=input.meta)


# ---- Registration at import time --------------------------------------------


def _register_router_v6_stages() -> None:
    from temper_placer.strategy_registry import register, register_composite

    register("routing", "router_v6_stage0", lambda: RouterV6Stage0_LoadPCB())
    register("routing", "router_v6_stage1", lambda: RouterV6Stage1_EscapeVias())
    register("routing", "router_v6_stage2", lambda: RouterV6Stage2_ChannelAnalysis())
    register("routing", "router_v6_stage3", lambda: RouterV6Stage3_TopologicalRouting())
    register("routing", "router_v6_stage4", lambda: RouterV6Stage4_GeometricRealization())
    register_composite("router_v6_full", [
        ("routing", "router_v6_stage0"),
        ("routing", "router_v6_stage1"),
        ("routing", "router_v6_stage2"),
        ("routing", "router_v6_stage3"),
        ("routing", "router_v6_stage4"),
    ])


_register_router_v6_stages()
