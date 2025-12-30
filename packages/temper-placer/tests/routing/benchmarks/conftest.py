"""
Pytest configuration and shared fixtures for routing benchmarks.

Provides fixtures for:
- Loading KiCad boards for benchmarking
- Board geometry extraction
- Netlist parsing
- C-Space grid configuration
"""

import time
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

import numpy as np
import pytest
from kiutils.board import Board as KiBoard

from temper_placer.core.board import Board
from temper_placer.core.netlist import Netlist
from temper_placer.routing.c_space_builder import CSpaceBuilder, CSpaceConfig, CSpaceCache


@pytest.fixture(scope="session")
def ki_board() -> Generator[KiBoard, None, None]:
    """Load the Temper board from KiCad file for benchmarking."""
    board_path = Path("temper_drc_verified.kicad_pcb")
    if not board_path.exists():
        board_path = Path("pre_routed_v6.kicad_pcb")
    if not board_path.exists():
        pytest.skip("Temper board file not found for benchmarking")

    board = KiBoard.from_file(str(board_path))
    return board


@pytest.fixture(scope="session")
def board_geometry(ki_board) -> tuple[float, float, tuple[float, float]]:
    """Extract board dimensions and origin for C-Space builder."""
    # KiCad boards use mm units
    width = ki_board.header.properties.get("Width", "100")
    height = ki_board.header.properties.get("Height", "100")

    try:
        width_mm = float(width)
        height_mm = float(height)
    except ValueError:
        width_mm = 100.0
        height_mm = 100.0

    # Find board edges for origin
    min_x = min(fp.position.X for fp in ki_board.footprints)
    min_y = min(fp.position.Y for fp in ki_board.footprints)
    origin = (float(min_x), float(min_y))

    return width_mm, height_mm, origin


@pytest.fixture(scope="session")
def c_space_config() -> CSpaceConfig:
    """Provide C-Space configuration for benchmarks."""
    return CSpaceConfig(
        resolution_mm=0.1,
        default_trace_width=0.2,
        default_clearance=0.2,
        power_trace_width=2.0,
        power_clearance=0.3,
        hv_trace_width=1.0,
        hv_clearance=2.0,
    )


@pytest.fixture
def c_space_builder(board_geometry, c_space_config) -> CSpaceBuilder:
    """Create a C-Space builder with board geometry."""
    width_mm, height_mm, origin = board_geometry
    return CSpaceBuilder(
        width_mm=width_mm,
        height_mm=height_mm,
        origin=origin,
        config=c_space_config,
    )


@pytest.fixture
def c_space_cache(c_space_builder) -> CSpaceCache:
    """Create a C-Space cache for benchmarks."""
    return CSpaceCache(c_space_builder)


@contextmanager
def track_time() -> Generator[dict, None, None]:
    """Context manager to track execution time and memory."""
    import tracemalloc

    stats = {
        "wall_time_ms": 0.0,
        "memory_bytes": 0,
        "peak_memory_bytes": 0,
    }

    tracemalloc.start()
    start = time.perf_counter()

    try:
        yield stats
    finally:
        end = time.perf_counter()
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        stats["wall_time_ms"] = (end - start) * 1000
        stats["memory_bytes"] = current
        stats["peak_memory_bytes"] = peak


class BenchmarkResult:
    """Container for benchmark results."""

    def __init__(
        self,
        name: str,
        wall_time_ms: float,
        memory_bytes: int,
        peak_memory_bytes: int,
        **extra_metrics,
    ):
        self.name = name
        self.wall_time_ms = wall_time_ms
        self.memory_bytes = memory_bytes
        self.peak_memory_bytes = peak_memory_bytes
        self.extra_metrics = extra_metrics

    def to_dict(self) -> dict:
        result = {
            "name": self.name,
            "wall_time_ms": round(self.wall_time_ms, 3),
            "memory_bytes": self.memory_bytes,
            "peak_memory_bytes": self.peak_memory_bytes,
        }
        result.update(self.extra_metrics)
        return result


def run_benchmark(
    name: str,
    func,
    *args,
    **kwargs,
) -> BenchmarkResult:
    """Run a function and capture benchmark metrics."""
    with track_time() as stats:
        result = func(*args, **kwargs)

    # Extract any metrics from the result
    extra = {}
    if isinstance(result, dict):
        extra = {k: v for k, v in result.items() if isinstance(v, (int, float, str, bool))}
    elif hasattr(result, "__dict__"):
        extra = vars(result)

    return BenchmarkResult(
        name=name,
        wall_time_ms=stats["wall_time_ms"],
        memory_bytes=stats["memory_bytes"],
        peak_memory_bytes=stats["peak_memory_bytes"],
        **extra,
    )
