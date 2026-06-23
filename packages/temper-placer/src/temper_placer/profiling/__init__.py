"""Pipeline profiling and validation toolkit.

Provides:
- PipelineProfiler: context manager for auto-instrumenting pipeline stages
- ProfileReport: structured profiling output dataclass
- Validation layers: Hypothesis PBT and golden fixture tests
- Autoprof: GPBM experiment loop for bottleneck identification
"""

from temper_placer.profiling.instrumentation import PipelineProfiler, ProfileReport

__all__ = ["PipelineProfiler", "ProfileReport"]
