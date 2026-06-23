"""Tests for the unified pipeline profiler, Stage 2 instrumentation, and ProfileStats integration."""

import json
import time

import pytest

from temper_placer.profiling.instrumentation import (
    PipelineProfiler,
    ProfileReport,
    StageTiming,
)


class TestPipelineProfiler:
    def test_context_manager_records_wall_time(self):
        profiler = PipelineProfiler()
        with profiler.stage("test_stage"):
            time.sleep(0.01)
        assert "test_stage" in profiler.report.stage_timings
        timing = profiler.report.stage_timings["test_stage"]
        assert timing.wall_time_ms > 0

    def test_stage_tick_counts_iterations(self):
        profiler = PipelineProfiler()
        with profiler.stage("iter_stage") as tick:
            for _ in range(5):
                tick()
        assert profiler.report.stage_timings["iter_stage"].iterations == 5

    def test_sub_step_nesting(self):
        profiler = PipelineProfiler()
        with profiler.stage("parent") as _tick:
            time.sleep(0.005)
            with profiler.sub_step("parent", "child"):
                time.sleep(0.01)
            time.sleep(0.005)

        timing = profiler.report.stage_timings["parent"]
        assert "child" in timing.sub_steps
        assert timing.sub_steps["child"].wall_time_ms > 0
        assert timing.wall_time_ms > timing.sub_steps["child"].wall_time_ms

    def test_start_stop_total_time(self):
        profiler = PipelineProfiler()
        profiler.start()
        time.sleep(0.01)
        profiler.stop()
        assert profiler.report.total_wall_time_ms > 0

    def test_record_per_path_latency(self):
        profiler = PipelineProfiler()
        profiler.record_per_path_latency("NET1", 1.234)
        profiler.record_per_path_latency("NET2", 5.678)
        assert profiler.report.per_path_latency_ms["NET1"] == 1.234
        assert profiler.report.per_path_latency_ms["NET2"] == 5.678

    def test_merge_router_stats(self):
        from dataclasses import dataclass

        @dataclass
        class FakeStats:
            numba_time_ms: float = 10.0
            python_time_ms: float = 20.0
            astar_total_ms: float = 30.0
            dist_map_ms: float = 5.0

        profiler = PipelineProfiler()
        profiler.merge_router_stats(FakeStats())
        assert profiler.report.numba_time_ms == 10.0
        assert profiler.report.python_time_ms == 20.0
        assert profiler.report.astar_total_ms == 30.0
        assert profiler.report.dist_map_ms == 5.0

    def test_to_json_valid_output(self):
        profiler = PipelineProfiler()
        with profiler.stage("a"):
            pass
        json_str = profiler.report.to_json()
        data = json.loads(json_str)
        assert "stages" in data
        assert "a" in data["stages"]
        assert "maze_router" in data
        assert "total_wall_time_ms" in data
        assert data["maze_router"]["numba_time_ms"] == 0.0

    def test_empty_report_has_defaults(self):
        report = ProfileReport()
        d = report.to_dict()
        assert d["stages"] == {}
        assert d["maze_router"]["numba_time_ms"] == 0.0

    def test_multiple_stages_preserved_in_order(self):
        profiler = PipelineProfiler()
        for name in ("parse", "stage1", "stage2"):
            with profiler.stage(name):
                pass
        assert list(profiler.report.stage_timings.keys()) == ["parse", "stage1", "stage2"]


class TestStageTiming:
    def test_to_dict_no_sub_steps(self):
        t = StageTiming(wall_time_ms=1.5, cpu_time_ms=1.0, iterations=3)
        d = t.to_dict()
        assert d["wall_time_ms"] == 1.5
        assert d["cpu_time_ms"] == 1.0
        assert d["iterations"] == 3
        assert "sub_steps" not in d

    def test_to_dict_with_sub_steps(self):
        t = StageTiming(wall_time_ms=10.0, cpu_time_ms=8.0, iterations=1)
        t.sub_steps["child"] = StageTiming(wall_time_ms=3.0, cpu_time_ms=2.5)
        d = t.to_dict()
        assert "sub_steps" in d
        assert d["sub_steps"]["child"]["wall_time_ms"] == 3.0


class TestProfileStatsIntegration:
    """U3: integration tests for ProfileStats wiring and per-path latency."""

    def test_per_path_latency_no_duplicates(self):
        profiler = PipelineProfiler()
        profiler.record_per_path_latency("NET_A", 1.5)
        profiler.record_per_path_latency("NET_A", 2.0)
        profiler.record_per_path_latency("NET_B", 3.0)
        assert profiler.report.per_path_latency_ms["NET_A"] == 2.0
        assert profiler.report.per_path_latency_ms["NET_B"] == 3.0

    def test_merge_router_stats_preserves_all_fields(self):
        from dataclasses import dataclass

        @dataclass
        class RealisticStats:
            numba_time_ms: float = 15.5
            python_time_ms: float = 5.2
            astar_total_ms: float = 45.0
            dist_map_ms: float = 2.3

        profiler = PipelineProfiler()
        profiler.merge_router_stats(RealisticStats())
        d = profiler.report.to_dict()
        maze = d["maze_router"]
        assert maze["numba_time_ms"] == 15.5
        assert maze["python_time_ms"] == 5.2
        assert maze["astar_total_ms"] == 45.0
        assert maze["dist_map_ms"] == 2.3
