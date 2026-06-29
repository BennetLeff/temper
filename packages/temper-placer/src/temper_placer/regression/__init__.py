"""Regression testing infrastructure for temper-placer.

Provides golden-board regression suite, corpus regression runner,
DRC ratchet CI gate, Benders<->Router closure test, and pipeline metrics recording.
"""

from temper_placer.regression.closure_test import ClosureResult, ClosureTest
from temper_placer.regression.corpus_runner import (
    BaselineFile,
    BaselineSpec,
    CorpusBoardResult,
    CorpusEntry,
    CorpusManifest,
    CorpusRegressionRunner,
    check_metric,
)
from temper_placer.regression.drc_ratchet import DrcRatchet
from temper_placer.regression.manifest import GoldenBoard, GoldenManifest
from temper_placer.regression.metrics_recorder import (
    CURRENT_SCHEMA_VERSION,
    PipelineMetricsRecord,
    find_metrics_file,
    load_metrics,
    record_closure_result,
    record_metrics,
)
from temper_placer.regression.reporter import BoardResult, RegressionReporter
from temper_placer.regression.runner import RegressionRunner

__all__ = [
    "RegressionRunner",
    "GoldenManifest",
    "GoldenBoard",
    "RegressionReporter",
    "BoardResult",
    "DrcRatchet",
    "ClosureTest",
    "ClosureResult",
    "PipelineMetricsRecord",
    "CURRENT_SCHEMA_VERSION",
    "record_closure_result",
    "record_metrics",
    "load_metrics",
    "find_metrics_file",
    "CorpusRegressionRunner",
    "CorpusEntry",
    "CorpusManifest",
    "BaselineFile",
    "BaselineSpec",
    "CorpusBoardResult",
    "check_metric",
]
