"""DAG execution engine for declarative pipeline orchestration.

Loads a YAML manifest, topologically sorts stages, executes them with
feedback contracts, timeouts, retries, and lifecycle event emission.
"""

from __future__ import annotations

import importlib
import time
from pathlib import Path
from typing import Any

from temper_placer.pipeline.dag_observability import (
    PipelineExecutionLog,
    ProgressObserver,
    StageEvent,
    write_execution_log_json,
)
from temper_placer.pipeline.dag_schema import (
    StageDAGManifest,
    StageDefinition,
    load_manifest,
)
from temper_placer.pipeline.dag_types import (
    DAGError,
    FeedbackExhaustedError,
    StageHandler,
    StageResult,
    StageTimeoutError,
)


class StageDAGEngine:
    """Executes a pipeline described by a DAG manifest."""

    def __init__(self, manifest_path: Path | str):
        if isinstance(manifest_path, str):
            manifest_path = Path(manifest_path)

        self.manifest_path = manifest_path
        self.manifest: StageDAGManifest = load_manifest(manifest_path)
        self.stage_map: dict[str, StageDefinition] = {}
        self.provides_map: dict[str, set[str]] = {}
        self.requires_map: dict[str, set[str]] = {}
        self.stage_order: list[str] = []
        self.observers: list[ProgressObserver] = []
        self.execution_log = PipelineExecutionLog()

        self._build_maps()
        self._topological_sort()
        self._build_execution_log_topology()

    def add_observer(self, observer: ProgressObserver) -> None:
        self.observers.append(observer)

    def _build_maps(self) -> None:
        for stage in self.manifest.stages:
            self.stage_map[stage.name] = stage
            self.requires_map[stage.name] = set(stage.requires)
            for key in stage.provides:
                self.provides_map.setdefault(key, set()).add(stage.name)

    def _topological_sort(self) -> None:
        in_degree: dict[str, int] = {s.name: 0 for s in self.manifest.stages}
        manifest_order = {s.name: i for i, s in enumerate(self.manifest.stages)}

        consumers_map: dict[str, set[str]] = {}
        for stage in self.manifest.stages:
            for key in stage.requires:
                consumers_map.setdefault(key, set()).add(stage.name)

        stage_decl_order = [s.name for s in self.manifest.stages]

        def _first_provider(key: str) -> str | None:
            providers = self.provides_map.get(key, set())
            if not providers:
                return None
            return min(providers, key=lambda p: stage_decl_order.index(p))

        for stage in self.manifest.stages:
            for key in stage.requires:
                if key in self.provides_map:
                    provider = _first_provider(key)
                    if provider is not None and provider != stage.name:
                        in_degree[stage.name] = in_degree.get(stage.name, 0) + 1

        queue = sorted(
            [name for name, deg in in_degree.items() if deg == 0],
            key=lambda n: manifest_order.get(n, 999),
        )
        result = []

        while queue:
            node = queue.pop(0)
            result.append(node)

            newly_ready = []
            for key in self.stage_map[node].provides:
                for consumer_name in consumers_map.get(key, set()):
                    if consumer_name == node:
                        continue
                    in_degree[consumer_name] -= 1
                    if in_degree[consumer_name] == 0:
                        newly_ready.append(consumer_name)

            queue.extend(
                sorted(newly_ready, key=lambda n: manifest_order.get(n, 999))
            )

        if len(result) != len(self.manifest.stages):
            raise ValueError(
                "DAG topological sort incomplete — cycle should have been caught by validation"
            )

        self.stage_order = result

    def _build_execution_log_topology(self) -> None:
        self.execution_log.dag_topology = [
            {"name": s.name, "requires": s.requires, "provides": s.provides}
            for s in self.manifest.stages
        ]
        self.execution_log.stage_order = list(self.stage_order)

    def run(self, state: Any) -> Any:
        pipeline_start = time.time()

        context: dict[str, Any] = self._init_context(state.config)

        stage_index = 0
        while stage_index < len(self.stage_order):
            stage_name = self.stage_order[stage_index]
            stage_def = self.stage_map[stage_name]

            if stage_def.skip_if:
                if self._evaluate_skip(stage_def.skip_if, state.config, state, context):
                    self._emit_skip(stage_name, f"skip_if: {stage_def.skip_if}")
                    stage_index += 1
                    continue

            if context.get("skip_topological") and stage_name == "topological":
                self._emit_skip(stage_name, "skip_topological is set")
                stage_index += 1
                continue

            if context.get("skip_routing") and stage_name in ("routing", "refinement"):
                self._emit_skip(stage_name, "skip_routing is set")
                stage_index += 1
                continue

            if context.get("dry_run") and stage_name in ("geometric", "routing", "refinement", "output"):
                self._emit_skip(stage_name, "dry_run is set")
                stage_index += 1
                continue

            self._emit_stage_start(stage_name, state.iteration, context)

            retry_attempts = 0
            max_attempts = stage_def.retry.max_attempts if stage_def.retry else 0

            stage_start = time.time()
            try:
                for attempt in range(max_attempts + 1):
                    try:
                        result = self._execute_stage(stage_def, state, context)
                        break
                    except Exception as e:
                        retry_attempts = attempt + 1
                        if attempt < max_attempts:
                            time.sleep(stage_def.retry.backoff_s)
                            continue
                        raise
            except StageTimeoutError:
                if stage_def.on_timeout == "skip":
                    self._emit_skip(stage_name, f"timed out after {stage_def.timeout_s}s")
                else:
                    state.success = False
                    state.failure_reason = f"Stage '{stage_name}' timed out"
                    state.elapsed_time_s = time.time() - pipeline_start
                    self._emit_stage_error(stage_name, StageTimeoutError(stage_name, stage_def.timeout_s or 0))
                    self._emit_pipeline_complete(False, state.elapsed_time_s, {})
                    return state
                stage_index += 1
                continue
            except Exception as e:
                if isinstance(e, DAGError):
                    raise
                from temper_placer.pipeline.state import PipelineError
                if isinstance(e, PipelineError):
                    state.success = False
                    state.failure_reason = str(e)
                    state.failed_phase = e.phase
                    state.elapsed_time_s = time.time() - pipeline_start
                    self._emit_stage_error(stage_name, e)
                    self._emit_pipeline_complete(False, state.elapsed_time_s, {})
                    return state
                state.success = False
                state.failure_reason = str(e)
                state.elapsed_time_s = time.time() - pipeline_start
                self._emit_stage_error(stage_name, e)
                self._emit_pipeline_complete(False, state.elapsed_time_s, {})
                return state

            stage_duration = time.time() - stage_start

            for key, value in result.outputs.items():
                context[key] = value

            self._record_phase_timing(state, stage_name, stage_duration)
            self.execution_log.stage_timings[stage_name] = stage_duration
            if retry_attempts > 0:
                self.execution_log.retry_counts[stage_name] = retry_attempts

            self._emit_stage_complete(stage_name, stage_duration, result.outputs)

            retriggered = self._evaluate_feedback_contracts(stage_def, state, context, stage_name)
            if retriggered:
                target_index = self.stage_order.index(stage_def.feedback_contracts[0].target_stage)
                for ci in range(target_index, len(self.stage_order)):
                    cs_name = self.stage_order[ci]
                    cs_def = self.stage_map[cs_name]
                    for key in cs_def.provides:
                        context.pop(key, None)
                stage_index = target_index
                continue

            stage_index += 1

        state.success = True
        total_duration = time.time() - pipeline_start
        state.elapsed_time_s = total_duration

        self.execution_log.success = True
        self.execution_log.total_duration_s = total_duration

        self._emit_pipeline_complete(True, total_duration, dict(state.phase_timings))

        output_dir = Path(".")
        if context.get("output_pcb"):
            output_dir = context["output_pcb"].parent
        try:
            write_execution_log_json(self.execution_log, output_dir)
        except OSError:
            pass

        return state

    @staticmethod
    def _record_phase_timing(state: Any, stage_name: str, duration: float) -> None:
        """Record phase timing, converting stage name to PipelinePhase if possible."""
        try:
            from temper_placer.pipeline.orchestrator import PipelinePhase
            phase = PipelinePhase(stage_name)
            state.phase_timings[phase] = duration
        except (ValueError, ImportError):
            state.phase_timings[stage_name] = duration

    def _init_context(self, config: Any) -> dict[str, Any]:
        context: dict[str, Any] = {}
        field_names = [
            "input_pcb", "constraints_yaml", "loops_yaml",
            "output_pcb", "output_report", "output_trace",
            "skip_topological", "skip_routing", "dry_run",
            "epochs", "seed", "max_movement_mm",
            "max_iterations", "routability_threshold",
            "convergence_threshold", "fab_preset",
        ]
        for name in field_names:
            if hasattr(config, name):
                context[name] = getattr(config, name)

        for stage in self.manifest.stages:
            for key in stage.provides:
                if key not in context:
                    context[key] = None

        return context

    def _evaluate_skip(self, expr_src: str, config: Any, state: Any, context: dict[str, Any]) -> bool:
        from temper_placer.pipeline.dag_expr import evaluate_skip_expr, parse_skip_expr

        try:
            parsed = parse_skip_expr(expr_src)
            return evaluate_skip_expr(parsed, config, state, context)
        except Exception:
            return False

    def _execute_stage(self, stage_def: StageDefinition, state: Any, context: dict[str, Any]) -> StageResult:
        handler = self._load_handler(stage_def.handler)

        deadline = None
        if stage_def.timeout_s is not None:
            deadline = time.time() + stage_def.timeout_s
            context["deadline"] = deadline

        try:
            result = handler(state, context)
        except Exception:
            raise

        if deadline is not None and time.time() > deadline:
            raise StageTimeoutError(stage_def.name, stage_def.timeout_s)

        return result

    def _load_handler(self, handler_path: str) -> StageHandler:
        parts = handler_path.rsplit(".", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid handler path: {handler_path}")
        module_name, class_name = parts
        module = importlib.import_module(module_name)
        cls = getattr(module, class_name)
        instance = cls()
        return instance

    def _evaluate_feedback_contracts(
        self, stage_def: StageDefinition, state: Any, context: dict[str, Any],
        current_stage_name: str,
    ) -> bool:
        counts = context.setdefault("_feedback_retrigger_counts", {})

        for fc in stage_def.feedback_contracts:
            count = counts.get(fc.name, 0)

            if count >= fc.max_retriggers:
                if count == fc.max_retriggers:
                    context.setdefault("feedback_errors", []).append(
                        FeedbackExhaustedError(fc.name, stage_def.name, count)
                    )
                continue

            metric_val = context.get(fc.trigger.metric)
            if metric_val is None:
                continue

            triggered = False
            op = fc.trigger.condition
            threshold = fc.trigger.threshold
            if op == "lt" and metric_val < threshold:
                triggered = True
            elif op == "gt" and metric_val > threshold:
                triggered = True
            elif op == "lte" and metric_val <= threshold:
                triggered = True
            elif op == "gte" and metric_val >= threshold:
                triggered = True
            elif op == "eq" and metric_val == threshold:
                triggered = True
            elif op == "neq" and metric_val != threshold:
                triggered = True

            if not triggered:
                continue

            count += 1
            context["_feedback_retrigger_counts"][fc.name] = count

            self._emit_feedback_triggered(fc.name, current_stage_name, fc.target_stage, count)

            for key, value in fc.parameter_adjustments.items():
                context[key] = value

            activation = {
                "contract_name": fc.name,
                "from_stage": current_stage_name,
                "to_stage": fc.target_stage,
                "attempt": count,
                "adjusted_params": fc.parameter_adjustments,
            }
            self.execution_log.feedback_activations.append(activation)

            return True

        return False

    def _emit_stage_start(self, name: str, iteration: int, context: dict[str, Any]) -> None:
        event = StageEvent(name=name, kind="start", iteration=iteration)
        self.execution_log.events.append(event)
        for obs in self.observers:
            try:
                obs.on_stage_start(name, iteration, context)
            except Exception:
                pass

    def _emit_stage_complete(self, name: str, duration_s: float, outputs: dict[str, Any]) -> None:
        event = StageEvent(name=name, kind="complete", duration_s=duration_s, outputs=outputs)
        self.execution_log.events.append(event)
        for obs in self.observers:
            try:
                obs.on_stage_complete(name, duration_s, outputs)
            except Exception:
                pass

    def _emit_stage_skip(self, name: str, reason: str) -> None:
        event = StageEvent(name=name, kind="skip", reason=reason)
        self.execution_log.events.append(event)
        for obs in self.observers:
            try:
                obs.on_stage_skip(name, reason)
            except Exception:
                pass

    _emit_skip = _emit_stage_skip

    def _emit_stage_error(self, name: str, error: Exception) -> None:
        event = StageEvent(name=name, kind="error", error=str(error))
        self.execution_log.events.append(event)
        for obs in self.observers:
            try:
                obs.on_stage_error(name, error)
            except Exception:
                pass

    def _emit_feedback_triggered(self, contract_name: str, from_stage: str, to_stage: str,
                                  attempt: int) -> None:
        event = StageEvent(
            name=from_stage, kind="feedback_triggered",
            feedback_contract=contract_name, feedback_attempt=attempt,
        )
        self.execution_log.events.append(event)
        for obs in self.observers:
            try:
                obs.on_feedback_triggered(contract_name, from_stage, to_stage, attempt)
            except Exception:
                pass

    def _emit_pipeline_complete(self, success: bool, total_duration_s: float,
                                 stage_timings: dict[str, float]) -> None:
        for obs in self.observers:
            try:
                obs.on_pipeline_complete(success, total_duration_s, stage_timings)
            except Exception:
                pass
