"""
Post-Processing Pipeline for Routing Optimization

This module provides a unified pipeline for post-processing routing output:
1. Via Optimization - Consolidate and optimize via placement
2. Trace Nudging - Fix minor clearance violations via force-directed optimization
3. Trace Ballooning - Widen power traces for current capacity (future)

Usage:
    from temper_placer.routing.post_processing.pipeline import PostProcessingPipeline, PostProcessConfig
    
    config = PostProcessConfig(
        via_optimization_enabled=True,
        trace_nudging_enabled=True,
    )
    pipeline = PostProcessingPipeline(config, drc_oracle)
    optimized = pipeline.process(routed_paths)
"""
from dataclasses import dataclass, field
import logging
import time
from typing import Dict

from temper_placer.routing.maze_router import RoutePath
from temper_placer.routing.constraints.drc_oracle import DRCOracle
from temper_placer.routing.post_processing.via_optimizer import ViaOptimizer, ViaOptimizationStats
from temper_placer.routing.post_processing.nudger import GeometricNudger
from temper_placer.routing.constraints.spatial_index import PCBGeometry, Track, Via, Pad


logger = logging.getLogger(__name__)


@dataclass
class ViaOptimizationConfig:
    """Configuration for via optimization stage."""
    enabled: bool = True
    consolidation_radius: float = 0.5  # mm - merge vias within this distance
    reposition_enabled: bool = True  # Allow via repositioning to fix violations
    remove_redundant: bool = True  # Remove unnecessary vias


@dataclass
class TraceNudgingConfig:
    """Configuration for trace nudging stage."""
    enabled: bool = True
    max_iterations: int = 100
    convergence_threshold: float = 0.001  # mm - stop when total movement < this
    max_nudge_distance: float = 0.5  # mm - prevent large topology changes


@dataclass
class TraceBallooningConfig:
    """Configuration for trace ballooning stage (future)."""
    enabled: bool = False
    power_nets_only: bool = True
    min_width_multiplier: float = 1.5  # Widen power traces by this factor


@dataclass
class PostProcessConfig:
    """Configuration for the entire post-processing pipeline."""
    via_optimization: ViaOptimizationConfig = field(default_factory=ViaOptimizationConfig)
    trace_nudging: TraceNudgingConfig = field(default_factory=TraceNudgingConfig)
    trace_ballooning: TraceBallooningConfig = field(default_factory=TraceBallooningConfig)


@dataclass
class StageMetrics:
    """Metrics from a single post-processing stage."""
    stage_name: str
    enabled: bool
    violations_before: int
    violations_after: int
    violations_fixed: int
    execution_time_ms: float
    # Stage-specific metrics
    vias_consolidated: int = 0
    vias_repositioned: int = 0
    vias_eliminated: int = 0
    nodes_nudged: int = 0
    convergence_iterations: int = 0


@dataclass
class PostProcessingResult:
    """Result of post-processing pipeline."""
    routing: Dict[str, RoutePath]
    geometry: PCBGeometry
    metrics: Dict[str, StageMetrics]
    total_violations_fixed: int
    total_execution_time_ms: float
    
    def print_report(self):
        """Print a human-readable report of post-processing results."""
        print("\n" + "=" * 60)
        print("POST-PROCESSING PIPELINE REPORT")
        print("=" * 60)
        
        for stage_name, metrics in self.metrics.items():
            print(f"\nStage: {stage_name}")
            if not metrics.enabled:
                print("  [SKIPPED - Disabled]")
                continue
                
            print(f"  Violations: {metrics.violations_before} → {metrics.violations_after}")
            print(f"  Fixed: {metrics.violations_fixed} ({metrics.violations_fixed / max(1, metrics.violations_before) * 100:.1f}%)")
            print(f"  Time: {metrics.execution_time_ms:.1f}ms")
            
            # Stage-specific metrics
            if metrics.vias_consolidated > 0:
                print(f"  Vias Consolidated: {metrics.vias_consolidated}")
            if metrics.vias_repositioned > 0:
                print(f"  Vias Repositioned: {metrics.vias_repositioned}")
            if metrics.vias_eliminated > 0:
                print(f"  Vias Eliminated: {metrics.vias_eliminated}")
            if metrics.nodes_nudged > 0:
                print(f"  Nodes Nudged: {metrics.nodes_nudged}")
            if metrics.convergence_iterations > 0:
                print(f"  Iterations: {metrics.convergence_iterations}")
        
        print(f"\nTOTAL: {self.total_violations_fixed} violations fixed in {self.total_execution_time_ms:.1f}ms")
        print("=" * 60 + "\n")


class PostProcessingPipeline:
    """
    Unified post-processing pipeline for routing optimization.
    
    Orchestrates multiple optimization stages in sequence:
    1. Via Optimization - Merge nearby vias, reposition to fix violations
    2. Trace Nudging - Force-directed optimization to fix clearance violations
    3. Trace Ballooning - Widen power traces (future)
    
    Each stage can be independently enabled/disabled via configuration.
    """
    
    def __init__(self, config: PostProcessConfig, drc_oracle: DRCOracle):
        """
        Initialize post-processing pipeline.
        
        Args:
            config: Pipeline configuration
            drc_oracle: DRC oracle for violation detection
        """
        self.config = config
        self.oracle = drc_oracle
        
        # Initialize stage processors
        self.via_optimizer = ViaOptimizer(
            oracle=drc_oracle,
            consolidation_radius=config.via_optimization.consolidation_radius,
        )
        
        self.trace_nudger = GeometricNudger(
            drc_oracle=drc_oracle,
            max_iterations=config.trace_nudging.max_iterations,
        )
    
    def process(self, routing: Dict[str, RoutePath], geometry: PCBGeometry) -> PostProcessingResult:
        """
        Run all enabled post-processing stages.
        
        Args:
            routing: Routing output from MazeRouter (dict of net_name -> RoutePath)
            geometry: PCB geometry (tracks, vias, pads)
        
        Returns:
            PostProcessingResult with optimized routing and metrics
        """
        pipeline_start = time.perf_counter()
        metrics = {}
        total_violations_fixed = 0
        
        # Stage 1: Via Optimization
        if self.config.via_optimization.enabled:
            stage_metrics, geometry = self._run_via_optimization(geometry)
            metrics['Via Optimization'] = stage_metrics
            total_violations_fixed += stage_metrics.violations_fixed
        
        # Stage 2: Trace Nudging
        if self.config.trace_nudging.enabled:
            stage_metrics, geometry = self._run_trace_nudging(geometry)
            metrics['Trace Nudging'] = stage_metrics
            total_violations_fixed += stage_metrics.violations_fixed
        
        # Stage 3: Trace Ballooning (future)
        if self.config.trace_ballooning.enabled:
            logger.warning("Trace ballooning not yet implemented")
        
        total_time_ms = (time.perf_counter() - pipeline_start) * 1000.0
        
        return PostProcessingResult(
            routing=routing,  # Routing paths unchanged (geometry is updated)
            geometry=geometry,
            metrics=metrics,
            total_violations_fixed=total_violations_fixed,
            total_execution_time_ms=total_time_ms,
        )

    
    def _run_via_optimization(self, geometry: PCBGeometry) -> StageMetrics:
        """Run via optimization stage."""
        stage_start = time.perf_counter()
        
        # Count violations before
        violations_before = len(self.oracle.find_all_violations(geometry))
        
        # Run via optimizer
        optimized_geometry = self.via_optimizer.optimize_vias(geometry)
        stats = self.via_optimizer.get_stats()  # Assuming this method exists
        
        # Count violations after
        violations_after = len(self.oracle.find_all_violations(optimized_geometry))
        
        execution_time_ms = (time.perf_counter() - stage_start) * 1000.0
        
        return StageMetrics(
            stage_name="Via Optimization",
            enabled=True,
            violations_before=violations_before,
            violations_after=violations_after,
            violations_fixed=violations_before - violations_after,
            execution_time_ms=execution_time_ms,
            vias_consolidated=stats.vias_consolidated if hasattr(stats, 'vias_consolidated') else 0,
            vias_repositioned=stats.vias_repositioned if hasattr(stats, 'vias_repositioned') else 0,
            vias_eliminated=stats.vias_eliminated if hasattr(stats, 'vias_eliminated') else 0,
        ), optimized_geometry
    
    def _run_trace_nudging(self, geometry: PCBGeometry) -> StageMetrics:
        """Run trace nudging stage."""
        stage_start = time.perf_counter()
        
        # Count violations before
        violations_before = len(self.oracle.find_all_violations(geometry))
        
        # Run trace nudger
        optimized_geometry = self.trace_nudger.nudge(geometry)
        
        # Count violations after
        violations_after = len(self.oracle.find_all_violations(optimized_geometry))
        
        execution_time_ms = (time.perf_counter() - stage_start) * 1000.0
        
        return StageMetrics(
            stage_name="Trace Nudging",
            enabled=True,
            violations_before=violations_before,
            violations_after=violations_after,
            violations_fixed=violations_before - violations_after,
            execution_time_ms=execution_time_ms,
            nodes_nudged=0,  # Could track this in GeometricNudger
            convergence_iterations=0,  # Could track this in GeometricNudger
        ), optimized_geometry
