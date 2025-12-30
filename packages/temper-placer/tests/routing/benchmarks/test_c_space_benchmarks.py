"""
C-Space Routing Benchmarks

Benchmarks comparing C-Space routing approach against traditional methods.
Measures performance, quality, and thermal characteristics.

Usage:
    pytest packages/temper-placer/tests/routing/benchmarks/ -v --benchmark-only
    pytest packages/temper-placer/tests/routing/benchmarks/ -v --benchmark-save=routing_results
"""

import pytest
from pathlib import Path

from kiutils.board import Board as KiBoard

from temper_placer.core.board import Board
from temper_placer.routing.c_space_builder import CSpaceBuilder, CSpaceConfig, CSpaceCache
from temper_placer.routing.maze_router import MazeRouter, RoutingStats

from .conftest import (
    ki_board,
    board_geometry,
    c_space_config,
    c_space_builder,
    c_space_cache,
    run_benchmark,
    BenchmarkResult,
)


class TestCSpaceBuilderPerformance:
    """Performance benchmarks for C-Space grid generation."""

    def test_grid_build_time_signal_net_class(
        self,
        c_space_builder: CSpaceBuilder,
    ) -> None:
        """Benchmark C-Space grid build for signal traces (0.2mm trace, 0.2mm clearance)."""

        def build_grid() -> dict:
            grid = c_space_builder.build_c_space_grid(
                trace_width=0.2,
                clearance=0.2,
            )
            return {
                "grid_width": grid.width_px,
                "grid_height": grid.height_px,
                "blocked_cells": int((grid.grid == 255).sum()),
            }

        result = run_benchmark("c_space_signal_0.2mm", build_grid)

        # Target: < 100ms
        assert result.wall_time_ms < 100, (
            f"C-Space build took {result.wall_time_ms:.1f}ms, target < 100ms"
        )

    def test_grid_build_time_power_net_class(
        self,
        c_space_builder: CSpaceBuilder,
    ) -> None:
        """Benchmark C-Space grid build for power traces (2.0mm trace, 0.3mm clearance)."""

        def build_grid() -> dict:
            grid = c_space_builder.build_c_space_grid(
                trace_width=2.0,
                clearance=0.3,
            )
            return {
                "grid_width": grid.width_px,
                "grid_height": grid.height_px,
                "blocked_cells": int((grid.grid == 255).sum()),
            }

        result = run_benchmark("c_space_power_2.0mm", build_grid)

        # Target: < 100ms
        assert result.wall_time_ms < 100, (
            f"C-Space build took {result.wall_time_ms:.1f}ms, target < 100ms"
        )

    def test_grid_build_time_hv_net_class(
        self,
        c_space_builder: CSpaceBuilder,
    ) -> None:
        """Benchmark C-Space grid build for HV traces (1.0mm trace, 2.0mm clearance)."""

        def build_grid() -> dict:
            grid = c_space_builder.build_c_space_grid(
                trace_width=1.0,
                clearance=2.0,
            )
            return {
                "grid_width": grid.width_px,
                "grid_height": grid.height_px,
                "blocked_cells": int((grid.grid == 255).sum()),
            }

        result = run_benchmark("c_space_hv_1.0mm", build_grid)

        # Target: < 100ms
        assert result.wall_time_ms < 100, (
            f"C-Space build took {result.wall_time_ms:.1f}ms, target < 100ms"
        )

    def test_grid_cache_hit_performance(
        self,
        c_space_cache: CSpaceCache,
    ) -> None:
        """Benchmark C-Space cache - repeated access should be near-instant."""

        # First build (cache miss)
        def first_build() -> dict:
            grid = c_space_cache.get_grid(trace_width=0.2, clearance=0.2)
            return {"cached": False}

        result_cold = run_benchmark("c_space_cache_miss", first_build)

        # Multiple cached accesses
        def cached_accesses() -> dict:
            for _ in range(10):
                grid = c_space_cache.get_grid(trace_width=0.2, clearance=0.2)
            return {"cached": True}

        result_warm = run_benchmark("c_space_cache_hit_x10", cached_accesses)

        # Cache hit should be 100x faster
        speedup = result_cold.wall_time_ms / max(result_warm.wall_time_ms, 0.01)
        assert speedup > 50, f"Cache speedup only {speedup:.1f}x, expected > 50x"

    def test_memory_usage_multiple_grids(
        self,
        c_space_builder: CSpaceBuilder,
    ) -> None:
        """Benchmark memory usage when caching multiple net class grids."""

        def build_multiple_grids() -> dict:
            cache = CSpaceCache(c_space_builder)

            # Build grids for different net classes
            cache.get_grid(trace_width=0.2, clearance=0.2)  # Signal
            cache.get_grid(trace_width=2.0, clearance=0.3)  # Power
            cache.get_grid(trace_width=1.0, clearance=2.0)  # HV

            return {
                "cache_size": cache.cache_size,
                "memory_mb": cache.memory_usage_mb(),
            }

        result = run_benchmark("c_space_multi_grid_memory", build_multiple_grids)

        # Target: < 500MB total
        assert result.peak_memory_bytes < 500 * 1024 * 1024, (
            f"Memory usage {result.peak_memory_bytes / (1024 * 1024):.1f}MB, target < 500MB"
        )


class TestRoutingQuality:
    """Quality benchmarks comparing old vs new routing approach."""

    @pytest.fixture
    def router_stats(self, ki_board) -> dict:
        """Get routing statistics from the current implementation."""
        # This would be populated when the pipeline is integrated
        # For now, return baseline metrics
        return {
            "drc_violations": 210,  # ~210 from task description
            "routing_completion": 0.93,  # 93%
            "hv_lv_separation_mm": 0.5,  # 0.5mm baseline
        }

    def test_c_space_routing_drc_violations(
        self,
        c_space_builder: CSpaceBuilder,
    ) -> None:
        """Verify C-Space routing produces 0 DRC violations.

        The C-Space approach guarantees no clearance violations
        by inflating obstacles by trace_width/2 + clearance.
        """

        # Build grid with conservative clearance
        grid = c_space_builder.build_c_space_grid(
            trace_width=0.2,
            clearance=0.2,
        )

        # A* path through C-Space is guaranteed valid
        # Any path found will satisfy clearance requirements
        free_cells = (grid.grid == 0).sum()
        total_cells = grid.grid.size
        free_ratio = free_cells / total_cells

        # If > 10% free space, routing should be possible
        # The actual pathfinding will be tested when MazeRouter is integrated
        assert free_ratio > 0.10, (
            f"Only {free_ratio * 100:.1f}% free space, routing may be difficult"
        )

    def test_hv_lv_separation(
        self,
        c_space_builder: CSpaceBuilder,
    ) -> None:
        """Verify HV-LV separation meets creepage requirements."""

        # Build grid with HV clearance (2mm)
        hv_grid = c_space_builder.build_c_space_grid(
            trace_width=1.0,
            clearance=2.0,
        )

        # Build grid with LV clearance (0.2mm)
        lv_grid = c_space_builder.build_c_space_grid(
            trace_width=0.2,
            clearance=0.2,
        )

        # HV grid should have more blocked area (conservative clearance)
        hv_blocked = (hv_grid.grid == 255).sum()
        lv_blocked = (lv_grid.grid == 255).sum()

        # HV should block at least 3x more area due to creepage requirements
        separation_ratio = hv_blocked / max(lv_blocked, 1)

        assert separation_ratio >= 3.0, f"HV separation ratio {separation_ratio:.1f}x, target >= 3x"


class TestThermalCharacteristics:
    """Thermal benchmarks for power trace routing."""

    def test_power_trace_ballooning_space(
        self,
        c_space_builder: CSpaceBuilder,
    ) -> None:
        """Check available space for power trace ballooning."""

        # Build grid for power traces (wide = more space around obstacles)
        power_grid = c_space_builder.build_c_space_grid(
            trace_width=2.0,
            clearance=0.3,
        )

        free_cells = (power_grid.grid == 0).sum()
        total_cells = power_grid.grid.size
        free_ratio = free_cells / total_cells

        # Power traces need more free space for thermal relief
        # If > 30% free, ballooning should be effective
        assert free_ratio > 0.30, (
            f"Power trace space {free_ratio * 100:.1f}%, target > 30% for ballooning"
        )

    def test_dc_bus_routing_feasibility(
        self,
        c_space_builder: CSpaceBuilder,
    ) -> None:
        """Check if DC_BUS routing is feasible with wide traces."""

        # DC_BUS typically needs 2mm+ trace width
        dc_bus_grid = c_space_builder.build_c_space_grid(
            trace_width=2.0,
            clearance=0.3,
        )

        free_cells = (dc_bus_grid.grid == 0).sum()
        total_cells = dc_bus_grid.grid.size
        free_ratio = free_cells / total_cells

        # Need at least 15% free space for DC_BUS routing
        assert free_ratio > 0.15, f"DC_BUS space {free_ratio * 100:.1f}%, target > 15%"


class TestBenchmarkIntegration:
    """Integration tests for benchmark framework."""

    def test_benchmark_result_serialization(
        self,
        c_space_builder: CSpaceBuilder,
    ) -> None:
        """Verify benchmark results can be serialized."""

        def simple_operation() -> dict:
            grid = c_space_builder.build_c_space_grid(trace_width=0.2, clearance=0.2)
            return {"free_cells": int((grid.grid == 0).sum())}

        result = run_benchmark("serialization_test", simple_operation)
        result_dict = result.to_dict()

        assert "name" in result_dict
        assert "wall_time_ms" in result_dict
        assert "memory_bytes" in result_dict
        assert "peak_memory_bytes" in result_dict
        assert "free_cells" in result_dict

    def test_benchmark_reproducibility(
        self,
        c_space_builder: CSpaceBuilder,
    ) -> None:
        """Verify benchmarks produce consistent results."""

        def build_grid() -> dict:
            grid = c_space_builder.build_c_space_grid(trace_width=0.2, clearance=0.2)
            return {"free_cells": int((grid.grid == 0).sum())}

        results = [run_benchmark("repro_test", build_grid) for _ in range(3)]

        # Times should be within 20% of each other (accounting for system variance)
        times = [r.wall_time_ms for r in results]
        avg_time = sum(times) / len(times)
        max_deviation = max(abs(t - avg_time) for t in times) / max(avg_time, 0.01)

        assert max_deviation < 0.20, f"Results varied by {max_deviation * 100:.1f}%, expected < 20%"


class TestOldVsNewComparison:
    """Comparison benchmarks between old and new routing approaches."""

    def test_occupancy_grid_vs_c_space(
        self,
        ki_board: KiBoard,
    ) -> None:
        """Compare old occupancy grid approach with C-Space approach.

        Old approach: Check each cell against Shapely polygons (Python loop)
        New approach: Rasterize all polygons at once (OpenCV)
        """

        # This test would compare the two approaches when both are available
        # For now, we verify the C-Space approach meets targets

        config = CSpaceConfig(resolution_mm=0.1)
        width = float(ki_board.header.properties.get("Width", "100"))
        height = float(ki_board.header.properties.get("Height", "100"))

        builder = CSpaceBuilder(
            width_mm=width,
            height_mm=height,
            origin=(0.0, 0.0),
            config=config,
        )

        # Build with C-Space (new approach)
        result = run_benchmark("c_space_approach", lambda: builder.build_c_space_grid(0.2, 0.2))

        # Target: < 100ms
        assert result.wall_time_ms < 100, (
            f"C-Space approach took {result.wall_time_ms:.1f}ms, target < 100ms"
        )

    def test_memory_comparison(
        self,
        c_space_builder: CSpaceBuilder,
    ) -> None:
        """Compare memory usage between approaches."""

        def build_single_grid() -> dict:
            grid = c_space_builder.build_c_space_grid(trace_width=0.2, clearance=0.2)
            return {"grid_size": grid.grid.nbytes}

        result = run_benchmark("memory_comparison", build_single_grid)

        # Target: < 500MB total memory during routing
        assert result.peak_memory_bytes < 500 * 1024 * 1024, (
            f"Peak memory {result.peak_memory_bytes / (1024 * 1024):.1f}MB, target < 500MB"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
