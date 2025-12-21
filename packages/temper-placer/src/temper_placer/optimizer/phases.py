"""
Pipeline phases for placement optimization.

This module defines the explicit stages of the optimization pipeline:
1. Topological Phase: Analyze connectivity and generate initial placement.
2. Geometric Phase: Gradient-based optimization of component positions.
3. Routing Phase: Verify routing feasibility of the placement.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable, List, Optional

import jax
import jax.numpy as jnp
from jax import Array

from temper_placer.core.state import PlacementState
from temper_placer.pipeline.topology_phase import (
    run_topological_phase,
    generate_initial_placement,
)

if TYPE_CHECKING:
    from temper_placer.core.board import Board
    from temper_placer.core.netlist import Netlist
    from temper_placer.pcl.parser import ConstraintCollection
    from temper_placer.optimizer.config import OptimizerConfig
    from temper_placer.losses.base import CompositeLoss, LossContext


class PhaseStatus(Enum):
    """Execution status of a pipeline phase."""
    PENDING = 'pending'
    RUNNING = 'running'
    SUCCESS = 'success'
    FAILED = 'failed'
    SKIPPED = 'skipped'


@dataclass
class PhaseResult:
    """Result of a pipeline phase execution."""
    status: PhaseStatus
    duration_seconds: float
    state: Optional[PlacementState] = None
    error: Optional[str] = None
    diagnostics: list[str] = field(default_factory=list)


@dataclass
class PipelineResult:
    """Final result of the optimization pipeline."""
    success: bool
    phases: list[PhaseResult]
    final_state: Optional[PlacementState] = None
    error: Optional[str] = None


class TopologicalPhase:
    """Phase 1: Topological analysis and initial placement."""

    def __init__(self, skip: bool = False):
        self.skip = skip

    def run(
        self,
        netlist: Netlist,
        board: Board,
        constraints: ConstraintCollection,
        initial_state: Optional[PlacementState] = None,
    ) -> PhaseResult:
        start_time = time.time()
        
        if self.skip:
            return PhaseResult(
                status=PhaseStatus.SKIPPED,
                duration_seconds=0.0,
                state=initial_state
            )

        try:
            # 1. Run topological analysis
            solution = run_topological_phase(netlist, board, constraints)
            
            if not solution.feasible:
                return PhaseResult(
                    status=PhaseStatus.FAILED,
                    duration_seconds=time.time() - start_time,
                    error=f"Topological infeasibility detected"
                )

            # 2. Generate initial placement
            state = generate_initial_placement(solution, board, netlist)
            
            return PhaseResult(
                status=PhaseStatus.SUCCESS,
                duration_seconds=time.time() - start_time,
                state=state,
                diagnostics=[
                    f"Identified {len(solution.clusters)} clusters",
                ]
            )
        except Exception as e:
            return PhaseResult(
                status=PhaseStatus.FAILED,
                duration_seconds=time.time() - start_time,
                error=str(e)
            )


class GeometricPhase:
    """Phase 2: Gradient-based geometric optimization."""

    def __init__(self, config: OptimizerConfig):
        self.config = config

    def run(
        self,
        netlist: Netlist,
        board: Board,
        loss_factory: Callable[[dict[str, float]], CompositeLoss],
        context: LossContext,
        initial_state: PlacementState,
    ) -> PhaseResult:
        from temper_placer.optimizer.train import train_multiphase
        start_time = time.time()

        try:
            result = train_multiphase(
                netlist=netlist,
                board=board,
                loss_factory=loss_factory,
                context=context,
                config=self.config,
                initial_state=initial_state
            )
            
            return PhaseResult(
                status=PhaseStatus.SUCCESS,
                duration_seconds=time.time() - start_time,
                state=result.best_state,
                diagnostics=[
                    f"Final loss: {result.final_loss:.4f}",
                    f"Converged: {result.converged}"
                ]
            )
        except Exception as e:
            import traceback
            traceback.print_exc()
            return PhaseResult(
                status=PhaseStatus.FAILED,
                duration_seconds=time.time() - start_time,
                error=str(e)
            )


class OptimizationPipeline:
    """Orchestrates the full placement optimization pipeline."""

    def __init__(
        self,
        netlist: Netlist,
        board: Board,
        constraints: ConstraintCollection,
        opt_config: OptimizerConfig,
        loss_factory: Callable[[dict[str, float]], CompositeLoss],
        context: LossContext,
    ):
        self.netlist = netlist
        self.board = board
        self.constraints = constraints
        self.opt_config = opt_config
        self.loss_factory = loss_factory
        self.context = context
        
        self.topological_phase = TopologicalPhase()
        self.geometric_phase = GeometricPhase(opt_config)

    def run(self) -> PipelineResult:
        phases = []
        
        # 1. Topological Phase
        topo_res = self.topological_phase.run(
            self.netlist, self.board, self.constraints
        )
        phases.append(topo_res)
        
        if topo_res.status == PhaseStatus.FAILED:
            return PipelineResult(success=False, phases=phases, error=topo_res.error)
            
        # 2. Geometric Phase
        geo_res = self.geometric_phase.run(
            self.netlist, 
            self.board, 
            self.loss_factory, 
            self.context, 
            topo_res.state
        )
        phases.append(geo_res)
        
        if geo_res.status == PhaseStatus.FAILED:
            return PipelineResult(success=False, phases=phases, error=geo_res.error)
            
        return PipelineResult(
            success=True,
            phases=phases,
            final_state=geo_res.state
        )
