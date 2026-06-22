"""Regression testing infrastructure for temper-placer.

Provides golden-board regression suite, corpus regression runner,
DRC ratchet CI gate, and Benders<->Router closure test.
"""

from temper_placer.regression.runner import RegressionRunner
from temper_placer.regression.manifest import GoldenManifest, GoldenBoard
from temper_placer.regression.reporter import RegressionReporter, BoardResult
from temper_placer.regression.drc_ratchet import DrcRatchet
from temper_placer.regression.closure_test import ClosureTest
from temper_placer.regression.corpus_runner import (
    CorpusRegressionRunner,
    CorpusEntry,
    CorpusManifest,
    BaselineFile,
    BaselineSpec,
    CorpusBoardResult,
    check_metric,
)

__all__ = [
    "RegressionRunner",
    "GoldenManifest",
    "GoldenBoard",
    "RegressionReporter",
    "BoardResult",
    "DrcRatchet",
    "ClosureTest",
    "CorpusRegressionRunner",
    "CorpusEntry",
    "CorpusManifest",
    "BaselineFile",
    "BaselineSpec",
    "CorpusBoardResult",
    "check_metric",
]
