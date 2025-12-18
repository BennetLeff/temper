"""Ablation study framework for placer/optimizer analysis."""

from temper_placer.ablation.config import (
    ComponentToggle,
    LossToggle,
    HyperparameterOverrides,
    ExperimentConfig,
    AblationStudyConfig,
)
from temper_placer.ablation.runner import (
    ExperimentRun,
    ExperimentRunner,
    ExperimentCheckpoint,
)
from temper_placer.ablation.metrics import (
    AggregatedMetrics,
    MetricAggregator,
)
from temper_placer.ablation.analysis import (
    ComponentImportance,
    SynergyPair,
    AblationAnalyzer,
)

__all__ = [
    "ComponentToggle",
    "LossToggle",
    "HyperparameterOverrides",
    "ExperimentConfig",
    "AblationStudyConfig",
    "ExperimentRun",
    "ExperimentRunner",
    "ExperimentCheckpoint",
    "AggregatedMetrics",
    "MetricAggregator",
    "ComponentImportance",
    "SynergyPair",
    "AblationAnalyzer",
]
