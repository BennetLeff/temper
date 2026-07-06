---
date: 2026-07-01
topic: dag-native-observability-middleware
---

# DAG-Native Structured Observability & Profiling Middleware

## Summary

Inject structured logging, JAX profiling, and per-stage canary metrics into the DAG pipeline as middleware — zero per-stage instrumentation code for timing and profiling. Each stage must include `loss_result` in its output dict (a one-key add). Every `StageResult` carries `StageMetrics` non-optionally (after a deprecation window). Plumb to CI regression gates.

---

## Problem Frame

Every stage uses bare `print()` calls (`input_stage.py:18`, `geometric_stage.py:29`, etc.). There is no per-stage timing record, no profiling infrastructure, no metrics baseline. The PCL silent-skip bug was undetectable because no metric surfaced `constraints_active: 0`.

Existing infrastructure is incomplete:
- `ProgressObserver` (7 lifecycle events) exists but isn't wired to structured log output
- `MetricsObserver` bridges `on_stage_complete` → `PipelineMetricsRecord` JSONL, but only captures `wall_time_ms` + canary — no loss deltas, no memory, no JAX device utilization
- 96 records in `pipeline_metrics.jsonl` all have `wall_time_ms: 0` — the recording path was broken
- Canary check exists but only warns; never blocks
- No JAX `profiler.trace()` integration, so XLA fusion splits and kernel launch events are invisible
- `StageResult` (`dag_types.py:15`) has `outputs: dict` and `duration_s: float` — no metrics field, so the observer runs side-band and can't enforce completeness

The goal is middleware that makes observability non-optional: every stage emits structured logs, profiler traces, and validated `StageMetrics` without writing timing or profiling code in the stage body. Stage bodies must replace bare `print()` calls with a structured logger (one-line substitution per file) and include `loss_result` in their output dict (one key per optimization stage).

---

## Actors

- **A1. Pipeline operator**: Runs `temper optimize`, reads live structured logs and sees per-stage wall-clock and loss
- **A2. CI system**: Runs pipeline in CI (`temper optimize --profile`), consumes JSONL metrics artifact, blocks PR on regression
- **A3. Pipeline developer**: Adds or modifies stages — gets timing, profiling, and metrics emission for free, constrained by a non-optional contract; must call `self.log()` instead of `print()` and include `loss_result` in outputs for optimization stages

---

## Key Flows

- **F1. Interactive pipeline run with live telemetry**
  - **Trigger:** `temper optimize --log-level=info`
  - **Actors:** A1
  - **Steps:**
    1. DAG engine starts, initializes structured logger with `[INFO dag-engine 001] pipeline start: manifest=default` on stderr
    2. Each stage `__call__` is wrapped in a middleware context at `_execute_stage` (`dag_engine.py:296`) that injects `[INFO <stage_name> 002] start` before the handler and `[INFO <stage_name> 003] completed: 1.23s, loss=0.0456, constraints_active=12` after
    3. Every bare `print()` call in existing stage bodies is replaced with `self.log.info(...)` or module-level logger calls — a one-line-per-file change (e.g., `print(f"Running refinement...")` → `self.log.info(f"Running refinement...")`). This is required because middleware wrapping at `_execute_stage` intercepts the handler boundary, not internal `print()` calls inside the handler body.
    4. Pipeline completion emits `[INFO dag-engine 004] pipeline complete: success, 4 stages, 5.67s`
  - **Outcome:** Terminal shows structured `[SEVERITY TOOL-ID-MSGID]` lines; `pipeline_metrics.jsonl` has one record per stage with `wall_time_ms > 0`; `pipeline_execution.jsonl` (new file, distinct from the existing `pipeline_execution.json` snapshot) receives streaming structured log records
  - **Covered by:** R1, R2, R3, R4

- **F2. Profiled run with JAX trace**
  - **Trigger:** `temper optimize --profile`
  - **Actors:** A1
  - **Steps:**
    1. DAG engine wraps each stage with `jax.profiler.start_trace()` before and `jax.profiler.stop_trace()` + `block_until_ready()` after
    2. JAX records XLA compile events, kernel launches, and device utilization for each stage
    3. `StageMetrics` includes `jax_device_time_ms`, `peak_memory_mb`, and `loss_delta` in addition to `wall_time_ms`
    4. Perfetto/XProf trace files land in `output_dir/traces/` alongside `pipeline_metrics.jsonl`
  - **Outcome:** Profiler trace exists; all `StageMetrics` fields are populated with real values
  - **Covered by:** R4, R5

- **F3. CI regression detection**
  - **Trigger:** PR push triggers CI pipeline (`temper optimize --profile --canary-gate`)
  - **Actors:** A2
  - **Steps:**
    1. Pipeline runs on the golden placement dataset (checked-in snapshot)
    2. Geometric stage emits `loss_result` and `loss_delta` into `StageMetrics` (via its output dict `loss_result` key, captured by the middleware)
    3. Canary check compares `loss_result` against `golden_loss` from the committed baseline
    4. If `loss_result < 0.8 × golden_loss` or `loss_result > 1.2 × golden_loss`, the check fails
    5. During silent-room period: `[WARN canary <stage_name> 005] loss 1.30× golden exceeds threshold 1.20×` is logged but pipeline succeeds
    6. After silent-room calibration: CI gate blocks the PR with a non-zero exit code
  - **Outcome:** PR blocked if metrics regress beyond threshold; trend data available per-commit
  - **Covered by:** R5, R6, R7, R8, R11

---

## Requirements

### Structured logging
- **R1.** Every DAG stage emits structured log events in `[SEVERITY TOOL-ID-MSGID] text` format on stderr, where TOOL-ID is the stage name and MSGID is a monotonically increasing integer — without any per-stage instrumentation code (middleware-injected)
- **R2.** Each log event includes, at minimum: severity, stage name, wall-clock elapsed in seconds, an `extras` dict with `{"loss": float | None, "constraints_active": int, "errors": [str]}`
- **R3.** Structured logs are simultaneously human-readable on stderr AND machine-parseable — each line is valid JSONL appended to `pipeline_execution.jsonl` (a new streaming file, distinct from the existing `pipeline_execution.json` snapshot at `dag_observability.py:144`, which remains a single-object JSON snapshot written at pipeline completion); a second consumer (the `MetricsObserver`) uses in-process callbacks, not log parsing
- **R3.1.** The existing `pipeline_execution.json` (single JSON snapshot) is unchanged by this feature; the new `pipeline_execution.jsonl` is a JSON Lines file written incrementally as each log event occurs, with one JSON object per line

### Profiling instrumentation
- **R4.** Each DAG stage `__call__` is wrapped with `jax.profiler.trace()` annotations (via `_trace_stage` middleware that calls `start_trace()`/`stop_trace()` around the handler) and a `block_until_ready()` fence before the wall-clock stop time to ensure XLA operations have completed
- **R5.** `StageMetrics` is a new `@dataclass` with fields: `wall_time_ms: int`, `jax_device_time_ms: float`, `peak_memory_mb: float`, `loss_result: float | None`, `loss_delta: float | None`, `constraints_active: int`, `errors_suppressed: int` — emitted to JSONL via `MetricsObserver` on every `on_stage_complete`
- **R5.1.** Optimization stages (e.g., `geometric`, `refinement`) MUST include `loss_result: float` in their output dict (`StageResult.outputs["loss_result"]`). Non-optimization stages omit the key. The middleware reads `loss_result` and `loss_delta` from the stage's output dict — this is the one place stages provide instrumentation data. See migration path in AE4.1.

### CI integration
- **R6.** A canary check runs on every `on_stage_complete`: if the stage has `loss_result` and a golden baseline exists for that stage, assert `0.8 × golden_loss ≤ loss_result ≤ 1.2 × golden_loss`; deviation triggers `[WARN canary <stage>]` during silent-room period, then `[ERROR canary <stage>]` + exit code after calibration
- **R7.** A CI gate (`--canary-gate`) causes the DAG engine to exit non-zero when any canary check fails post-silent-room; PRs are blocked
- **R8.** Pipeline runs in CI write a `ci_metrics_artifact.json` containing per-stage `StageMetrics` records keyed by `commit_sha` for trend analysis (per-commit latency, loss, constraint-satisfaction history)

### Contract enforcement
- **R9.** `StageMetrics` is added as an optional field on `StageResult` (`dag_types.py:15`) with default `None`: `metrics: StageMetrics | None = None`. After a deprecation window, the field becomes required. `StageHandler.__call__` return type remains `StageResult` (the protocol is unchanged; validation happens in the middleware, not in the type signature).
- **R9.1.** Migration path for R9:
  1. **Phase 1 (now):** Add `metrics: StageMetrics | None = None` to `StageResult`. Existing stages continue to work unchanged. Middleware constructs `StageMetrics` from `outputs` dict and `duration_s` at `_execute_stage` — no stage call site changes. If `StageResult.metrics` is `None`, the middleware sets it before emitting `on_stage_complete`.
  2. **Phase 2 (deprecation, 30 days):** Stages that return `StageResult` with `metrics=None` emit a `[WARN]` log. All existing stages are updated to populate `metrics` explicitly.
  3. **Phase 3 (hard enforcement, after deprecation window):** `StageResult.metrics` becomes `metrics: StageMetrics` (required, no default). Middleware raises `StageError` if `metrics` is missing. See AE4.
- **R10.** The DAG engine validates that every `StageResult.outputs` key matches the stage's manifest-declared `provides` set before the next stage executes; missing keys or extra keys raise `DAGContractError`
- **R11.** `--canary-gate` requires `--profile` to be active. If `--canary-gate` is passed without `--profile`, the engine exits with a non-zero error code and a message instructing the user to add `--profile`. Canary checks depend on profiling instrumentation (`loss_result`, `loss_delta`, `jax_device_time_ms`).

### New error types
- **R12.** The following new error types are introduced under `dag_types.py`:
  - `StageError(DAGError)`: Raised by the middleware when stage result validation fails (e.g., `StageResult.metrics is None` after the hard-enforcement window, or missing required output keys). See AE4.
  - `DAGContractError(DAGError)`: Raised by the DAG engine when `StageResult.outputs` keys don't match the manifest-declared `provides` set. See AE5 and R10.

---

## Acceptance Examples

- **AE1. Covers R1, R2, R3.** Given `temper optimize --log-level=info` on `temper.kicad_pcb`, after `input_stage` completes the terminal shows `[INFO input_stage 002] completed: 1.23s, constraints_active=12, errors=0` on stderr, and `pipeline_execution.jsonl` (new streaming file) contains `{"severity": "INFO", "tool_id": "input_stage", "msg_id": 2, "event": "completed", "wall_clock_s": 1.23, "extras": {"loss": null, "constraints_active": 12, "errors": []}}`. No `print()` calls appear in stage source — stage uses `self.log.info(...)` instead. The existing `pipeline_execution.json` snapshot file is unchanged.

- **AE2. Covers R4, R5, R5.1.** Given `temper optimize --profile`, after the geometric stage runs a JAX optimization loop: a Perfetto trace file exists at `output_dir/traces/geometric.trace.json.gz`, `pipeline_metrics.jsonl` contains `{"stage_name": "geometric", "metrics": {"wall_time_ms": 4521, "jax_device_time_ms": 4410.3, "peak_memory_mb": 2048.7, "loss_result": 0.0456, "loss_delta": 0.0123, "constraints_active": 12, "errors_suppressed": 0}}`, and `wall_time_ms > 0`. The geometric stage includes `"loss_result": 0.0456` in its `StageResult.outputs` dict, from which the middleware extracts the value.

- **AE3. Covers R6, R7, R11.** Given a PR that changes the loss function such that golden placement loss increases by 30%, when CI runs `temper optimize --profile --canary-gate`, the geometric stage canary emits `[WARN canary geometric 005] loss 0.0583 is 1.30× golden (0.0449), exceeds threshold 1.20×`. In silent-room mode, pipeline succeeds but CI log captures the warning. After silent-room, the engine exits with code 3 and CI blocks the PR. If `--canary-gate` is passed without `--profile`, the engine exits immediately with an error.

- **AE4. Covers R9 (Phase 3 hard enforcement).** Given a stage implementation that returns `StageResult(outputs={}, duration_s=1.0)` (no `metrics`) after the deprecation window has closed and `StageMetrics` is a required field, when the DAG engine's middleware wrapper inspects the result, it raises `StageError("StageResult.metrics is missing for stage 'geometric'")` before emitting `on_stage_complete`.

- **AE4.1. Covers R9.1 (Phase 1 migration).** Given an existing stage that returns `StageResult(outputs={"placement_state": ps, "loss_result": 0.0456}, duration_s=1.0)` with `metrics=None` (the current behavior), during Phase 1 the middleware constructs `StageMetrics` from `outputs` and `duration_s` and sets it on the result before `on_stage_complete`. No stage call sites are broken. The stage must add `"loss_result"` to its outputs dict (one key); timing and profiling fields are populated by the middleware.

- **AE5. Covers R10.** Given a stage manifest declares `provides: ["board", "netlist"]` but the stage returns `outputs: {"board": b}` (missing `netlist`), the DAG engine raises `DAGContractError("Stage 'input' missing declared outputs: {'netlist'}")` before `on_stage_complete`.

- **AE6. Covers R11.** Given `temper optimize --canary-gate` without `--profile`, the engine exits with non-zero status and prints `[ERROR dag-engine 001] --canary-gate requires --profile` to stderr.

---

## Success Criteria

- PCL silent-skip or similar constraint-omission bugs emit a `constraints_active: 0` metric visible in the first pipeline run — not weeks of silent degradation
- Pipeline developers add observability to new stages by implementing `StageHandler`, replacing `print()` with `self.log.*()` (one-line substitutions per file), including `loss_result` in outputs (one key for optimization stages), and returning `StageResult` — no timing calls, no profiler annotations in the stage body
- CI blocks metric regressions deterministically — a PR that changes loss beyond the golden tolerance band cannot be merged without canary gate override or baseline update

---

## Scope Boundaries

- **Not** a replacement for external APM/Observability platforms (Datadog, Honeycomb) — pipeline metrics stay local JSONL + CI artifacts
- **Not** a live dashboard — terminal output + CI artifacts only; the Andon Board (`andon_observer.py`) is a separate feature that consumes the same `ProgressObserver` events
- **Not** SPC/chart-based alerting — threshold-based gating only; statistical process control is deferred
- Profiling budgets (`jax_device_time_ms`, `peak_memory_mb`) are advisory initially; they become enforced gates after silent-room calibration
- Perfetto trace files are scoped to the profile path (`--profile` flag); non-profiled runs skip `jax.profiler.trace()` wrapping to avoid overhead

---

## Key Decisions

- **D1. Middleware wrapping at `_execute_stage`, not decorators or monkey-patching:** The DAG engine already owns the `_execute_stage` call site (`dag_engine.py:296`). Wrapping the call there with a log+profile+metrics middleware is simpler than per-stage decorators and avoids touching eight stage files for timing/profiling concerns. However, `_execute_stage` wrapping CANNOT intercept `print()` calls inside stage body code — it only wraps the handler call boundary. Therefore, stages must replace bare `print()` with structured log calls (one-line substitution per file). This is a trade-off: honest about what middleware can and cannot intercept, in exchange for a minimal per-file change. The existing `ProgressObserver` lifecycle events stay intact; the middleware emits them.
- **D2. `StageMetrics` as an evolving `StageResult` field, not a parallel side-channel:** Currently `MetricsObserver.on_stage_complete` receives `duration_s` and `outputs` from the engine, and builds a `PipelineMetricsRecord` independently. This means loss, memory, and JAX device time are never captured unless the observer has intimate knowledge of the outputs dict. Making `StageMetrics` part of the `StageResult` (starting with an optional `None`-default field, progressing to required) ensures the stage _must_ report these values after the migration window.
- **D3. OpenROAD-style `[SEVERITY TOOL-ID-MSGID]` format, not structlog or loguru:** Chosen for parity with the EDA ecosystem OpenROAD uses; developers switching between tools see the same format. The JSONL side-channel preserves machine-readability without structural coupling to the human format.
- **D4. Golden placement is a checked-in snapshot, not dynamically generated:** A CI-checked-in `.npz` or `.json` blob with positions and expected loss is deterministic; dynamically generated golden placements risk drift from environment differences (JAX version, XLA compiler flags).
- **D5. Silent-room mode (canary warns, doesn't gate) before hard enforcement:** Addresses the risk that the golden baseline is miscalibrated and would block all PRs. After N runs with zero false positives, the gate activates.
- **D6. `loss_result` via output dict convention, not callback scraping:** Loss is currently reported through the `on_epoch` callback chain (`dag_engine.py:424` → `ProgressObserver.on_epoch`), not in `StageResult.outputs`. Rather than scraping the callback (which couples the middleware to the observer protocol internals), optimization stages must include `{"loss_result": float}` in their output dict. This is a one-key addition per optimization stage and is explicit, auditable, and typed — no hidden control flow.

---

## Dependencies / Assumptions

- **A1.** `ProgressObserver` protocol (`dag_observability.py:13`) is stable and all 7 lifecycle events are called at the correct points in `dag_engine.py:run()` — no new events are needed
- **A2.** `MetricsObserver` (`metrics_observer.py:34`) can be extended with `StageMetrics` fields without changing its constructor signature
- **A3.** `PipelineMetricsRecord` (`metrics_recorder.py:22`) schema v2 supports the additional fields (`jax_device_time_ms`, `peak_memory_mb`, `loss_result`, `loss_delta`, `constraints_active`, `errors_suppressed`) without a schema v3 migration
- **A4.** `jax.profiler.trace()` + `block_until_ready()` adds <5% overhead in practice (validated by existing `profiling/pipeline_metrics.py` which already uses `block_until_ready`)
- **A5.** JAX is available in CI runners with GPU profiling support
- **A6.** The CI system (GitHub Actions or similar) can consume a non-zero exit code from the canary gate and propagate it to PR block status

---

## Outstanding Questions

### Resolve Before Planning

- **[Affects R3]** What is the MSGID counter scope: per-pipeline-run (resets to 001 each invocation) or global (incrementing across runs)?
- **[Affects R6]** What is the golden placement dataset: a CI-checked-in `.npz` snapshot of positions + expected loss, or a `temper.kicad_pcb` fixture run deterministically with `seed=0`?
- **[Affects R5.1]** Which stages are expected to emit `loss_result`/`loss_delta` — only `geometric` and `refinement`, or all stages with `null` for non-optimization stages?

### Deferred to Planning

- **[Affects R4][Technical]** Maximum acceptable profiling overhead per stage boundary (`block_until_ready()` fence cost + trace start/stop cost)
- **[Affects R6][Technical]** Silent-room calibration: how many runs constitute "zero false positives" before canary hard-gate activates? Suggested default: 20 consecutive CI runs with zero canary warnings
- **[Affects R8][Technical]** CI metrics artifact retention policy: keep last N commits, or archive all with a TTL?
- **[Affects R9.1][Technical]** Deprecation timeline: 30 calendar days from merge or N released versions before Phase 3 hard enforcement?
- **[Affects R5.1][Technical]** Migration path for 8 existing stage handlers that currently return `StageResult(outputs={...}, duration_s=elapsed)` without `loss_result` in outputs — which stages need this key added? (Answer: only optimization stages; non-optimization stages have `loss_result: None` in `StageMetrics`.)

(End of file - 166 lines)
