"""
Scale testing and profiling for temper-placer.

This module provides tools for testing optimizer performance at scale.
"""

from temper_placer.scale.memory_profiler import (
    MemoryProfile,
    ThresholdResult,
    check_memory_thresholds,
    profile_optimizer_memory,
)

__all__ = [
    "MemoryProfile",
    "profile_optimizer_memory",
    "check_memory_thresholds",
    "ThresholdResult",
]
