"""TDD tests for profiling instrumentation of CP-SAT loop, KiCad I/O, and physics modules."""
from __future__ import annotations
import time
from contextlib import nullcontext
from temper_placer.profiling.instrumentation import PipelineProfiler

class TestGracefulDegradation:
    def test_profiler_none_sub_step_safe(self):
        profiler = None
        with (profiler.sub_step("cp_sat", "round_1") if profiler else nullcontext()):
            pass

    def test_profiler_none_stage_safe(self):
        profiler = None
        with (profiler.stage("cp_sat") if profiler else nullcontext()):
            pass

class TestStageNames:
    def test_single_stage(self):
        p = PipelineProfiler()
        with p.stage("cp_sat"):
            pass
        assert "cp_sat" in p.report.stage_timings

    def test_stage_with_sub_steps(self):
        p = PipelineProfiler()
        with p.stage("cp_sat"):
            with p.sub_step("cp_sat", "round_1"):
                pass
        timing = p.report.stage_timings["cp_sat"]
        assert "round_1" in timing.sub_steps

class TestWallTime:
    def test_sub_step_wall_time_positive(self):
        p = PipelineProfiler()
        with p.stage("test"):
            with p.sub_step("test", "child"):
                time.sleep(0.005)
        timing = p.report.stage_timings["test"]
        assert timing.sub_steps["child"].wall_time_ms > 0

class TestParentDuration:
    def test_parent_gte_sum_of_children(self):
        p = PipelineProfiler()
        with p.stage("parent"):
            with p.sub_step("parent", "c1"):
                time.sleep(0.005)
            with p.sub_step("parent", "c2"):
                time.sleep(0.005)
        timing = p.report.stage_timings["parent"]
        child_sum = sum(s.wall_time_ms for s in timing.sub_steps.values())
        assert timing.wall_time_ms >= child_sum
