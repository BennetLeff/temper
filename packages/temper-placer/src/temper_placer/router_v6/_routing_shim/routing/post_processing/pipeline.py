"""
Post-Processing Pipeline for Routing Optimization

This module provides a unified pipeline for post-processing routing output:
1. Via Optimization - Consolidate and optimize via placement
2. Trace Nudging - Fix minor clearance violations via force-directed optimization
3. Trace Ballooning - Widen power traces for current capacity

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
from temper_placer.routing.post_processing.trace_ballooner import TraceBallooner
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
    step_size: float = 0.5 # mm - movement multiplier per iteration


@dataclass
class TraceBallooningConfig:
    """Configuration for trace ballooning stage."""
    enabled: bool = False
    power_nets_only: bool = True
    max_width: float = 6.0  # mm - max trace width for manufacturability
    safety_margin: float = 0.2  # mm - clearance margin to maintain
    default_current_a: float = 10.0  # A - default current for IPC-2221 width calc
    copper_thickness_oz: float = 1.0  # oz
    temp_rise_c: float = 10.0  # °C


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
    segments_ballooned: int = 0


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
            if metrics.segments_ballooned > 0:
                print(f"  Segments Ballooned: {metrics.segments_ballooned}")
        
        print(f"\nTOTAL: {self.total_violations_fixed} violations fixed in {self.total_execution_time_ms:.1f}ms")
        print("=" * 60 + "\n")


class PostProcessingPipeline:
    """
    Unified post-processing pipeline for routing optimization.
    
    Orchestrates multiple optimization stages in sequence:
    1. Via Optimization - Merge nearby vias, reposition to fix violations
    2. Trace Nudging - Force-directed optimization to fix clearance violations
    3. Trace Ballooning - Widen power traces for current capacity
    
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
            oracle=drc_oracle
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
        
        # Stage 3: Trace Ballooning
        if self.config.trace_ballooning.enabled:
            stage_metrics, geometry = self._run_trace_ballooning(geometry)
            metrics['Trace Ballooning'] = stage_metrics
            total_violations_fixed += stage_metrics.violations_fixed
        
        total_time_ms = (time.perf_counter() - pipeline_start) * 1000.0
        
        return PostProcessingResult(
            routing=routing,  # Routing paths unchanged (geometry is updated)
            geometry=geometry,
            metrics=metrics,
            total_violations_fixed=total_violations_fixed,
            total_execution_time_ms=total_time_ms,
        )

    
    def _run_via_optimization(self, geometry: PCBGeometry) -> tuple[StageMetrics, PCBGeometry]:
        """Run via optimization stage."""
        stage_start = time.perf_counter()
        
        # Count violations before
        violations_before = len(self.oracle.validate_all())
        
        # Run via optimizer
        optimized_geometry = self.via_optimizer.optimize_vias(geometry)
        stats = self.via_optimizer.stats
        
        # Count violations after
        violations_after = len(self.oracle.validate_all())
        
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
    
    def _run_trace_nudging(self, geometry: PCBGeometry) -> tuple[StageMetrics, PCBGeometry]:
        """Run trace nudging stage."""
        stage_start = time.perf_counter()
        
        # Count violations before
        violations_before = len(self.oracle.validate_all())
        
        # Run trace nudger
        self.trace_nudger.build_topology()
        self.trace_nudger.optimize(
            iterations=self.config.trace_nudging.max_iterations,
            step_size=self.config.trace_nudging.step_size
        )
        optimized_geometry = self.oracle.geometry
        
        # Count violations after
        violations_after = len(self.oracle.validate_all())
        
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

    def _run_trace_ballooning(self, geometry: PCBGeometry) -> tuple[StageMetrics, PCBGeometry]:
        """Run trace ballooning stage.

        For each power-net track segment:
        1. Compute IPC-2221 required width for target current
        2. Attempt incremental ballooning via TraceBallooner
        3. Validate each expansion against DRCOracle
        4. Revert expansions that cause DRC violations
        """
        stage_start = time.perf_counter()

        # Count violations before
        violations_before = len(self.oracle.validate_all())

        # Compute IPC-2221 minimum width for power nets
        ipc2221_target_width = _ipc2221_width_for_current(
            current_a=self.config.trace_ballooning.default_current_a,
            thickness_oz=self.config.trace_ballooning.copper_thickness_oz,
            temp_rise_c=self.config.trace_ballooning.temp_rise_c,
        )
        logger.info(
            "IPC-2221 target width for %.1fA: %.2f mm",
            self.config.trace_ballooning.default_current_a,
            ipc2221_target_width,
        )

        # Create ballooner with config
        ballooner = TraceBallooner(
            geometry=geometry,
            max_width=self.config.trace_ballooning.max_width,
            safety_margin=self.config.trace_ballooning.safety_margin,
        )

        # Build a mapping from track id -> original width for revert-on-failure
        original_widths: dict[str, float] = {}
        for track in geometry.tracks:
            original_widths[track.id] = track.width

        # Expand power net tracks: target at least IPC-2221 width,
        # up to max_width or available clearance
        max_expansion = max(0.0, ipc2221_target_width)
        result = ballooner.balloon_traces(
            list(geometry.tracks),
            max_expansion=max_expansion,
        )

        segments_expanded = result.segments_expanded
        segments_reverted = 0

        # Validate each expanded track against DRC oracle
        validated_tracks: list[Track] = []
        for track in result.tracks:
            orig_width = original_widths.get(track.id, track.width)
            if track.width > orig_width + 0.001:
                # This track was expanded — validate
                valid, reason = self.oracle.can_place_track_segment(
                    start=(track.start.x, track.start.y),
                    end=(track.end.x, track.end.y),
                    layer=track.layer,
                    net=track.net,
                    width=track.width,
                )
                if not valid:
                    logger.debug("Balloon reverted for %s: %s", track.id, reason)
                    # Revert to original width
                    track = Track(
                        start=track.start,
                        end=track.end,
                        width=orig_width,
                        layer=track.layer,
                        net=track.net,
                        id=track.id,
                    )
                    segments_reverted += 1
            validated_tracks.append(track)

        # Build new geometry with validated tracks
        optimized_geometry = PCBGeometry()
        for track in validated_tracks:
            optimized_geometry.add_track(track)
        for via in geometry.vias:
            optimized_geometry.add_via(via)
        for pad in geometry.pads:
            optimized_geometry.add_pad(pad)
        optimized_geometry.rebuild_index()

        # Update the oracle's geometry reference for violation counting
        self.oracle.geometry = optimized_geometry

        # Count violations after
        violations_after = len(self.oracle.validate_all())

        execution_time_ms = (time.perf_counter() - stage_start) * 1000.0

        logger.info(
            "Trace ballooning: %d segments expanded, %d reverted by DRC, "
            "%d violations before -> %d after",
            segments_expanded,
            segments_reverted,
            violations_before,
            violations_after,
        )

        return StageMetrics(
            stage_name="Trace Ballooning",
            enabled=True,
            violations_before=violations_before,
            violations_after=violations_after,
            violations_fixed=violations_before - violations_after,
            execution_time_ms=execution_time_ms,
            segments_ballooned=segments_expanded - segments_reverted,
        ), optimized_geometry


def _ipc2221_width_for_current(
    current_a: float,
    thickness_oz: float = 1.0,
    temp_rise_c: float = 10.0,
    internal_layer: bool = True,
) -> float:
    """Compute minimum trace width (mm) for a target current using IPC-2221.

    Inverse of the IPC-2221 formula:
        I = k * ΔT^0.44 * (width_mils * thickness_mils)^0.725

    Args:
        current_a: Target current in Amperes
        thickness_oz: Copper thickness in oz (1 oz = 1.37 mils)
        temp_rise_c: Allowable temperature rise in °C
        internal_layer: True for internal layers (conservative)

    Returns:
        Minimum trace width in mm
    """
    if current_a <= 0:
        return 0.0

    k = 0.024 if internal_layer else 0.048
    thickness_mils = thickness_oz * 1.37

    # Invert: A = (I / (k * ΔT^0.44))^(1/0.725)
    area_mils2 = (current_a / (k * (temp_rise_c ** 0.44))) ** (1.0 / 0.725)
    width_mils = area_mils2 / thickness_mils
    width_mm = width_mils / 39.3701

    return max(0.0, width_mm)
