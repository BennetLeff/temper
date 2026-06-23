"""Semantic stage: extracts semantic loop information."""

from __future__ import annotations

import time
from typing import Any

from temper_placer.pipeline.dag_types import DataContext, StageResult


class SemanticStage:
    def __call__(self, state: Any, context: DataContext) -> StageResult:
        start = time.time()
        loops_enriched = context.get("loops", [])
        elapsed = time.time() - start
        return StageResult(
            outputs={"loops_enriched": loops_enriched},
            duration_s=elapsed,
        )
