"""Pydantic v2 models for DAG manifest loading and validation.

Loads a YAML manifest, builds the stage DAG, performs cycle detection
via Tarjan's SCC, validates requires/provides dependencies, and checks
feedback contract target_stage references.
"""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, model_validator

from temper_placer.pipeline.dag_types import (
    DAGCycleError,
    DAGDuplicateStageError,
    DAGExprSyntaxError,
    DAGMissingDependencyError,
)
from temper_placer.pipeline.dag_expr import parse_skip_expr

BUILTIN_CONFIG_KEYS = frozenset({
    "input_pcb",
    "constraints_yaml",
    "loops_yaml",
    "output_pcb",
    "output_report",
    "output_trace",
    "skip_topological",
    "skip_routing",
    "skip_local_refinement",
    "dry_run",
    "epochs",
    "seed",
    "max_movement_mm",
    "max_iterations",
    "routability_threshold",
    "convergence_threshold",
    "fab_preset",
    "deadline",
})


class PipelineMeta(BaseModel):
    name: str
    version: str


class TriggerCondition(BaseModel):
    metric: str
    condition: Literal["lt", "gt", "lte", "gte", "eq", "neq"]
    threshold: float


class FeedbackContract(BaseModel):
    name: str
    trigger: TriggerCondition
    target_stage: str
    parameter_adjustments: dict[str, Any] = Field(default_factory=dict)
    max_retriggers: int = 3


class RetryConfig(BaseModel):
    max_attempts: int = 0
    backoff_s: float = 1.0


class DataKeySpec(BaseModel):
    type: str = ""
    description: str = ""


class StageDefinition(BaseModel):
    name: str
    handler: str
    requires: list[str] = Field(default_factory=list)
    provides: list[str] = Field(default_factory=list)
    skip_if: str | None = None
    timeout_s: float | None = None
    on_timeout: Literal["skip", "fail"] = "fail"
    retry: RetryConfig | None = None
    feedback_contracts: list[FeedbackContract] = Field(default_factory=list)


class StageDAGManifest(BaseModel):
    pipeline: PipelineMeta
    stages: list[StageDefinition]
    data_keys: dict[str, DataKeySpec] | None = None

    @model_validator(mode="after")
    def _validate_dag(self) -> StageDAGManifest:
        stage_names = [s.name for s in self.stages]

        seen: set[str] = set()
        for name in stage_names:
            if name in seen:
                raise DAGDuplicateStageError(name)
            seen.add(name)

        for stage in self.stages:
            if stage.skip_if is not None:
                try:
                    parse_skip_expr(stage.skip_if)
                except DAGExprSyntaxError as e:
                    raise DAGExprSyntaxError(
                        f"Invalid skip_if in stage '{stage.name}': {e}"
                    ) from e

        provides_map: dict[str, set[str]] = {}
        for stage in self.stages:
            for key in stage.provides:
                provides_map.setdefault(key, set()).add(stage.name)

        for stage in self.stages:
            for key in stage.requires:
                if key in provides_map:
                    continue
                if key in BUILTIN_CONFIG_KEYS:
                    continue
                raise DAGMissingDependencyError(key=key, requiring_stage=stage.name)

        _detect_cycles(self.stages, provides_map)

        for stage in self.stages:
            for fc in stage.feedback_contracts:
                if fc.target_stage not in seen:
                    raise ValueError(
                        f"Feedback contract '{fc.name}' in stage '{stage.name}' "
                        f"references unknown target_stage '{fc.target_stage}'"
                    )

        _warn_unreachable(self.stages, provides_map)

        return self


def _detect_cycles(stages: list[StageDefinition], provides_map: dict[str, set[str]]) -> None:
    stage_names = {s.name for s in stages}
    stage_idx = {name: i for i, name in enumerate(sorted(stage_names))}
    n = len(stage_names)

    stage_decl_order = [s.name for s in stages]

    def _first_provider(key: str) -> str | None:
        providers = provides_map.get(key, set())
        if not providers:
            return None
        return min(providers, key=lambda p: stage_decl_order.index(p))

    adj: list[list[int]] = [[] for _ in range(n)]
    for stage in stages:
        src = stage_idx[stage.name]
        for key in stage.provides:
            main_provider = _first_provider(key)
            if main_provider is not None and main_provider != stage.name:
                continue
            for consumer in stages:
                if consumer.name == stage.name:
                    continue
                if key in consumer.requires:
                    dst = stage_idx[consumer.name]
                    adj[src].append(dst)

    UNVISITED, VISITING, VISITED = 0, 1, 2
    state: list[int] = [UNVISITED] * n
    path: list[int] = []
    idx_to_name = {v: k for k, v in stage_idx.items()}

    def _dfs(v: int) -> None:
        state[v] = VISITING
        path.append(v)
        for w in sorted(adj[v]):
            if state[w] == VISITING:
                cycle_start = path.index(w)
                cycle = [idx_to_name[x] for x in path[cycle_start:]]
                cycle.append(idx_to_name[w])
                raise DAGCycleError(cycle=cycle)
            elif state[w] == UNVISITED:
                _dfs(w)
        path.pop()
        state[v] = VISITED

    for v in range(n):
        if state[v] == UNVISITED:
            _dfs(v)


def _warn_unreachable(stages: list[StageDefinition], provides_map: dict[str, set[str]]) -> None:
    stage_map = {s.name: s for s in stages}
    roots = set()
    for s in stages:
        unmet = [r for r in s.requires if r not in BUILTIN_CONFIG_KEYS and r not in provides_map]
        if not unmet:
            roots.add(s.name)

    reachable: set[str] = set(roots)
    queue = list(roots)
    while queue:
        current = queue.pop(0)
        for key in stage_map[current].provides:
            for consumer in stages:
                if consumer.name in reachable:
                    continue
                if key in consumer.requires:
                    reachable.add(consumer.name)
                    queue.append(consumer.name)

    unreachable = {s.name for s in stages} - reachable
    for name in sorted(unreachable):
        warnings.warn(f"Stage '{name}' is unreachable from any root stage")


def load_manifest(path: Path) -> StageDAGManifest:
    with open(path) as f:
        data = yaml.safe_load(f)
    return StageDAGManifest(**data)
