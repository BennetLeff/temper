"""Ablation study framework for placer/optimizer analysis."""

from temper_placer.ablation.analysis import (
    AblationAnalyzer,
    ComponentImportance,
    SynergyPair,
)
from temper_placer.ablation.config import (
    AblationStudyConfig,
    ComponentToggle,
    ExperimentConfig,
    HyperparameterOverrides,
    LossToggle,
)
from temper_placer.ablation.metrics import (
    AggregatedMetrics,
    MetricAggregator,
)
from temper_placer.ablation.runner import (
    ExperimentCheckpoint,
    ExperimentRun,
    ExperimentRunner,
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
