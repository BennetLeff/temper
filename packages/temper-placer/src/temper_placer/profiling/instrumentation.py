"""Unified pipeline profiler with context-manager instrumentation.

Replaces ad-hoc profiling scripts with a single PipelineProfiler that
auto-instruments pipeline stages and writes structured ProfileReport output.

Usage:
    profiler = PipelineProfiler()
    with profiler.stage("routing"):
        router.route_all(nets)
    print(profiler.report.to_json())
"""

from __future__ import annotations

import json
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from temper_placer.regression.metrics_recorder import PipelineMetricsRecord


@dataclass
class StageTiming:
    wall_time_ms: float = 0.0
    cpu_time_ms: float = 0.0
    iterations: int = 0
    sub_steps: dict[str, StageTiming] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "wall_time_ms": round(self.wall_time_ms, 3),
            "cpu_time_ms": round(self.cpu_time_ms, 3),
            "iterations": self.iterations,
        }
        if self.sub_steps:
            result["sub_steps"] = {
                name: ss.to_dict() for name, ss in self.sub_steps.items()
            }
        return result


@dataclass
class ProfileReport:
    stage_timings: dict[str, StageTiming] = field(default_factory=dict)
    per_path_latency_ms: dict[str, float] = field(default_factory=dict)
    numba_time_ms: float = 0.0
    python_time_ms: float = 0.0
    astar_total_ms: float = 0.0
    dist_map_ms: float = 0.0
    total_wall_time_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        result["stages"] = {name: s.to_dict() for name, s in self.stage_timings.items()}
        if self.per_path_latency_ms:
            result["per_path_latency_ms"] = self.per_path_latency_ms
        result["maze_router"] = {
            "numba_time_ms": round(self.numba_time_ms, 3),
            "python_time_ms": round(self.python_time_ms, 3),
            "astar_total_ms": round(self.astar_total_ms, 3),
            "dist_map_ms": round(self.dist_map_ms, 3),
        }
        result["total_wall_time_ms"] = round(self.total_wall_time_ms, 3)
        return result

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    def merge_maze_router_stats(self, stats: Any) -> None:
        self.numba_time_ms = getattr(stats, "numba_time_ms", 0.0)
        self.python_time_ms = getattr(stats, "python_time_ms", 0.0)
        self.astar_total_ms = getattr(stats, "astar_total_ms", 0.0)
        self.dist_map_ms = getattr(stats, "dist_map_ms", 0.0)

    def to_pipeline_metrics_record(
        self, board: str, stage: str, module: str = "profiler"
    ) -> PipelineMetricsRecord:
        from temper_placer.regression.metrics_recorder import PipelineMetricsRecord

        metrics: dict[str, float] = {}
        for name, timing in self.stage_timings.items():
            metrics[f"{name}_wall_ms"] = round(timing.wall_time_ms, 3)
            metrics[f"{name}_cpu_ms"] = round(timing.cpu_time_ms, 3)
            for sub_name, sub in timing.sub_steps.items():
                metrics[f"{name}_{sub_name}_ms"] = round(sub.wall_time_ms, 3)
        metrics["maze_router_numba_ms"] = round(self.numba_time_ms, 3)
        metrics["maze_router_python_ms"] = round(self.python_time_ms, 3)
        metrics["maze_router_astar_total_ms"] = round(self.astar_total_ms, 3)
        metrics["maze_router_dist_map_ms"] = round(self.dist_map_ms, 3)
        metrics["total_wall_ms"] = round(self.total_wall_time_ms, 3)
        for net, lat in self.per_path_latency_ms.items():
            metrics[f"per_path_latency_{net}_ms"] = round(lat, 3)

        return PipelineMetricsRecord(
            board=board,
            stage=stage,
            module=module,
            metrics=metrics,
        )


class PipelineProfiler:
    def __init__(self) -> None:
        self._report = ProfileReport()
        self._active_timings: dict[str, StageTiming] = {}
        self._t0: float | None = None

    @property
    def report(self) -> ProfileReport:
        return self._report

    def start(self) -> None:
        self._t0 = time.perf_counter()

    def stop(self) -> None:
        if self._t0 is not None:
            self._report.total_wall_time_ms = (time.perf_counter() - self._t0) * 1000.0

    @contextmanager
    def stage(self, name: str):
        t0_wall = time.perf_counter()
        t0_cpu = time.process_time()
        iteration_count = 0

        timing = StageTiming()
        self._active_timings[name] = timing

        def _tick():
            nonlocal iteration_count
            iteration_count += 1

        try:
            yield _tick
        finally:
            del self._active_timings[name]
            timing.wall_time_ms = (time.perf_counter() - t0_wall) * 1000.0
            timing.cpu_time_ms = (time.process_time() - t0_cpu) * 1000.0
            timing.iterations = iteration_count
            self._report.stage_timings[name] = timing

    @contextmanager
    def sub_step(self, parent_stage: str, name: str):
        t0 = time.perf_counter()
        try:
            yield
        finally:
            wall_ms = (time.perf_counter() - t0) * 1000.0
            if parent_stage in self._active_timings:
                parent = self._active_timings[parent_stage]
                sub = StageTiming(wall_time_ms=wall_ms)
                parent.sub_steps[name] = sub

    def record_per_path_latency(self, net_name: str, latency_ms: float) -> None:
        self._report.per_path_latency_ms[net_name] = latency_ms

    def merge_router_stats(self, stats: Any) -> None:
        self._report.merge_maze_router_stats(stats)
