---
title: "Pipeline Observability: Observer Pattern with Dual-Source Cross-Validation and Silent-Room Activation"
date: "2026-06-29"
category: architecture-patterns
module: CI
problem_type: architecture_pattern
component: development_workflow
severity: medium
applies_when:
  - "Building CI observability on an existing pipeline that has two code paths (e.g., DAG engine and legacy orchestrator)"
  - "Injecting metric recording into pipeline stages via an observer protocol"
  - "Recording metrics that require integrity verification — you need to prove the recording path is not dead or corrupted"
  - "Deploying CI gates that need a data-collection period before enforcement activates"
symptoms:
  - "Observer exceptions silently swallowed by engine's `contextlib.suppress(Exception)` wrapper"
  - "Cross-validation comparing identical values from the same source, making the check tautological"
  - "Canary integrity check logged a warning but still wrote the corrupted record"
tags:
  - observability
  - observer-pattern
  - cross-validation
  - silent-room
  - pr-scorecard
  - spc
  - slo
  - jsonl
---

# Pipeline Observability: Observer Pattern with Dual-Source Cross-Validation and Silent-Room Activation

## Context

The temper-placer pipeline had CI runs producing observable data (timing, DRC results, `PipelineExecutionLog`) that never reached the metrics recording path. The `ProgressObserver` protocol fired 6 lifecycle events per run but no implementation listened for metrics. Operators manually inspected output with no per-stage timing, no trend awareness, no regression detection.

The solution wired a `MetricsObserver` into both orchestration paths — the DAG engine's observer chain and the CI's `ClosureTest` shim — with three integrity guardrails executed before every write: schema validation, dual-source cross-validation, and canary injection. An SPC/SLO gating system would auto-enforce after a 14-day, 20-run silent-room data-collection period.

During review, three critical architectural pitfalls were found that would have silently corrupted or bypassed every guardrail had they shipped.

## Guidance

### Architecture: Three Guardrails Before Every Write

Every pipeline stage completion fires `on_stage_complete` in the observer. Before a single byte is written to the JSONL metrics store, three checks run in fixed order:

```
on_stage_complete(stage_name, duration_s, outputs)
  │
  ├── 1. Schema validation (rejects zero-valued required fields, unknown fields, range violations)
  │       ↓ SchemaValidationError? → abort, no write
  │
  ├── 2. Cross-validation (compares observer's independent timing vs. engine's timing)
  │       ↓ CrossValidationError? → abort, no write
  │
  ├── 3. Canary check (verifies sentinel value survived the recording path round-trip)
  │       ↓ CanaryCheckError? → abort, no write
  │
  └── 4. Write to pipeline_metrics.jsonl
```

The ordering matters. Schema runs first because zero-valued metrics violate the schema (e.g., `wall_time_ms: 0` with `zero_is_valid: false`) and should short-circuit before expensive cross-validation or canary checks. Canary runs last because it proves the full record construction path is intact — if a record incorrectly constructed by a buggy adapter has the right canary value, the schema and cross-validation should have caught it first.

### Dual-Source Cross-Validation

The cross-validation guardrail uses two independent timing sources, not two references to the same value:

```python
def _cross_validate_against(self, *, start_t, stage_name, caller_duration_s):
    if start_t is not None:
        # PATH A: Observer's own clock (time.monotonic())
        observer_duration_s = time.monotonic() - start_t
        if abs(caller_duration_s - observer_duration_s) > TOLERANCE_S:
            raise CrossValidationError(...)
        return
    # PATH B: Fallback — engine's execution_log (independent recording)
    expected = self.execution_log.stage_timings.get(stage_name)
    if expected is None:
        return  # no reference, skip validation
    if abs(caller_duration_s - expected) > TOLERANCE_S:
        raise CrossValidationError(...)
```

**Path A** is the primary path: `on_stage_start` records `time.monotonic()`, `on_stage_complete` computes the elapsed observer time and compares it against `caller_duration_s` (the value passed by the engine, which uses its own `time.time()` clock). These are genuinely independent measurements from two different time functions.

**Path B** is the fallback when `start_t` is unavailable (e.g., the shim didn't call `on_stage_start`). It reads the engine's post-hoc `PipelineExecutionLog.stage_timings`, which is recorded independently.

The tolerance is 10ms, not 0, to account for clock precision differences between `time.monotonic()` and `time.time()`.

### Pitfall 1: Don't Suppress Observer Exceptions in Emission Loops

The DAG engine originally wrapped every observer callback in `contextlib.suppress(Exception)`:

```python
# WRONG: Silently swallows CrossValidationError, SchemaValidationError, CanaryCheckError
for obs in self.observers:
    with contextlib.suppress(Exception):
        obs.on_stage_complete(name, duration_s, outputs)
```

This made all three guardrails **dead code through the DAG path**. Schema violations, cross-validation mismatches, and canary corruption were caught and silently dropped. The observer's contract was: if a check fails, raise an exception to prevent the write. The engine's contract was: if an observer raises, suppress it and continue.

**The fix**: log warnings instead of silently suppressing. The engine's emission code now logs the observer name, stage name, and exception before continuing:

```python
for obs in self.observers:
    try:
        obs.on_stage_complete(name, duration_s, outputs)
    except Exception as exc:
        _LOGGER.warning(
            "Observer %s failed on_stage_complete for stage '%s': %s",
            type(obs).__name__, name, exc,
        )
```

The write-side guardrails now function as intended: the exception propagates out of the observer, the engine logs it, and the stage does NOT write a corrupted record.

### Pitfall 2: Cross-Validation Must Compare Independent Sources

Cross-validation was tautological in both paths before the fix:

- **DAG engine path**: The engine computed `stage_duration` once and passed the same value to both the observer callback AND the `execution_log`. Both arms of the cross-validation check compared the same number. The `start_t` branch was dead because `on_stage_start` was called, but with `time.monotonic() - start_t` producing essentially the same value as `caller_duration_s` (the engine's `time.time()` delta). This was borderline — the two clock functions differ, but by less than the 10ms tolerance in practice.

- **ClosureTest path**: The real problem was that `start_t` was never set (the shim called `on_stage_complete` without `on_stage_start`), AND the `execution_log` had no entry. The function simply `return`ed on line 142, making the entire check a no-op. Every record passed cross-validation regardless of timing correctness.

**The fix**: The observer now computes its own timing independently (`time.monotonic() - self._stage_start_times[stage_name]`), and the engine passes its own independently-computed duration. They come from two separate clock readings and two separate code paths. The fallback to `execution_log.stage_timings` is separately verified by the engine's own recording at `dag_engine.py:210`.

### Pitfall 3: Canary Checks Must Block, Not Just Log

The original implementation logged a warning on canary mismatch but still called `self._write(record)`. A broken metrics construction path (wrong `PipelineMetricsRecord` fields, truncated dict, adapter bug) would silently produce corrupted JSONL. The warning would scroll past in CI logs unnoticed.

**The fix**: Raise `CanaryCheckError`, which aborts the write. The canary value is set at observer init, written into every record's `metrics` dict, and verified before the `_write` call:

```python
def _check_canary(self, record):
    canary = record.metrics.get(_CANARY_KEY)
    if canary != self._canary_value:
        raise CanaryCheckError(
            f"Expected canary value {self._canary_value}, got {canary}"
        )
```

A corrupted canary means the recording path is broken (e.g., a serializer dropped fields, a dict was shallow-copied instead of deep-copied). The only correct response is to refuse the write and signal CI failure.

### Silent Room: Deferred Enforcement with a Deadline

SPC and SLO CI gates must not block merges on day one — they need historical data for meaningful baselines. The silent-room pattern provides a data-collection period with a dual-activation condition:

- **14 calendar days** since the first pipeline run with observability enabled, AND
- **20 completed pipeline runs**

Both conditions must be satisfied before enforcement activates. This prevents activation on a project with infrequent CI (one run per week would need 20 weeks). The state is tracked in `observability_state.json` committed to the repo:

```json
{
  "first_run_date": "2026-06-29",
  "total_runs": 20,
  "activation_status": "enforcing"
}
```

During the silent room, SPC and SLO violations are computed and reported (visible in CI logs and health-digest) but exit code is always 0. After activation, `block`-severity violations fail CI.

### PR Scorecard: Delta Table Against Merge-Base

The PR scorecard workflow runs the pipeline on both the merge-base and the PR branch, then posts a markdown delta table as a PR comment:

```
| Stage       | Baseline (ms) | Current (ms) | Delta   | Drift |
|-------------|---------------|--------------|---------|-------|
| placement   | 4523          | 4780         | +5.7%   | -     |
| routing     | 12034         | 12210        | +1.5%   | +2 drc|
| geometric   | 890           | 905          | +1.7%   | -     |
| topological | 2340          | 2335         | -0.2%   | -     |
```

Critical detail: corrupted JSONL lines are counted and warned, not silently dropped. The original code used `try/except: pass` on `json.loads`, which would hide entire runs of data loss. Fixed to tally parse errors and emit a `LOGGER.warning` with the count and file path.

## Why This Matters

**Observer emission loops are a single point of failure for all guardrails.** When the engine suppresses observer exceptions, every integrity check (schema, cross-validation, canary) becomes dead code through that path. The observer pattern must have a contract about exception propagation: if the observer raises, the engine must log the error and treat the stage as having failed its observability obligations, not silently ignore it.

**Cross-validation must compare independent instrumentation sources.** Comparing two references to the same value is not validation — it's self-consistency. The two sources must come from independent code paths and independent measurement mechanisms. A single `time.monotonic()` reading passed to both arms is tautological, not validating.

**Integrity checks must halt the write path, not just warn.** A logged warning that a canary is corrupted while the corrupted record is still written to the persistent store means the canary serves no protective function. If you're going to check integrity, you must reject the data on failure.

**Silent room is a structural pattern, not a flag.** Simply delaying enforcement by N days invites the same problem as a warn-only CI gate — the deadline arrives and nobody is ready. The dual condition (days AND runs) ensures there is actual data volume, and the committed state file makes the activation date a diffable, reviewable event.

## When to Apply

- When building observability into a pipeline that writes persistent metrics (e.g., JSONL, SQLite, any append-only log)
- When the pipeline has multiple orchestration paths that must both produce the same metrics (requires adapter/bridge code)
- When CI gates depend on historical data and cannot enforce on day one (silent room)
- When metrics integrity matters — corrupted or zero-valued data in production would silently mislead regression detection

Do NOT apply when:
- The pipeline has a single, well-tested orchestration path with no legacy shim (cross-validation is lower value)
- Metrics are purely informational with no downstream CI gates depending on correctness (schema/canary guards are overhead)
- You can enforce CI gates immediately because historical baselines already exist

## Examples

### Minimal MetricsObserver with Three Guardrails

```python
class MetricsObserver:
    def __init__(self, output_dir, execution_log, *, board, canary_value=42.0):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.execution_log = execution_log
        self.board = board
        self._canary_value = canary_value
        self._stage_start_times: dict[str, float] = {}
        self._output_path = self.output_dir / "pipeline_metrics.jsonl"
        self._schema_validator = SchemaValidator()

    def on_stage_start(self, stage_name, iteration, context):
        self._stage_start_times[stage_name] = time.monotonic()

    def on_stage_complete(self, stage_name, duration_s, outputs):
        record = build_record(stage_name, duration_s, outputs)
        self._validate_schema(record)                            # 1
        self._cross_validate(stage_name, duration_s)             # 2
        self._check_canary(record)                               # 3
        self._write(record)                                      # 4

    def _cross_validate(self, stage_name, caller_duration_s):
        start_t = self._stage_start_times.pop(stage_name, None)
        if start_t is not None:
            observer_duration = time.monotonic() - start_t
            if abs(caller_duration_s - observer_duration) > 0.01:
                raise CrossValidationError(...)
            return
        # Fallback to execution_log's independent recording
        expected = self.execution_log.stage_timings.get(stage_name)
        if expected is not None:
            if abs(caller_duration_s - expected) > 0.01:
                raise CrossValidationError(...)

    def _check_canary(self, record):
        if record.metrics.get("__pipeline_liveness__") != self._canary_value:
            raise CanaryCheckError(...)  # raises, aborts write
```

### Correct Engine Emission: Log, Don't Suppress

```python
# WRONG — all guardrails dead code
def _emit_stage_complete(self, name, duration_s, outputs):
    for obs in self.observers:
        with contextlib.suppress(Exception):
            obs.on_stage_complete(name, duration_s, outputs)

# CORRECT — log and continue; observer's own internal logic handles the abort
def _emit_stage_complete(self, name, duration_s, outputs):
    for obs in self.observers:
        try:
            obs.on_stage_complete(name, duration_s, outputs)
        except Exception as exc:
            _LOGGER.warning("Observer %s failed for stage '%s': %s",
                            type(obs).__name__, name, exc)
```

### Silent Room State File

```json
{
  "first_run_date": "2026-06-29",
  "total_runs": 5,
  "activation_status": "collecting"
}
```

The CI trend-check reads this file. While `activation_status` is `"collecting"`, SPC/SLO violations are computed and reported but never fail CI. The file is committed by `metrics-record.yml` after each run increments `total_runs`. When 14 days have elapsed AND `total_runs >= 20`, the workflow sets `activation_status` to `"enforcing"`.

### PR Scorecard: Corrupted Lines Must Be Counted

```python
def load_metrics(filepath):
    records = []
    parse_errors = 0
    with open(filepath) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                parse_errors += 1
    if parse_errors:
        _LOGGER.warning("Skipped %d unparseable lines in %s (corrupted JSONL)",
                        parse_errors, filepath)
    return records
```

This ensures partial data corruption is visible in CI logs rather than silently producing an incomplete scorecard that appears normal.

## Related

- `docs/plans/2026-06-28-011-feat-pipeline-observability-plan.md` — full observability plan with 8 implementation units
- `docs/solutions/architecture-patterns/ci-profiling-platform-canonical-metrics-contract-2026-06-28.md` — the `PipelineMetricsRecord` contract that this observer writes into
- `docs/solutions/architecture-patterns/ci-gate-quality-enforcement.md` — the baseline-allowlist meta-pattern used by SPC/SLO gates
- `packages/temper-placer/src/temper_placer/pipeline/metrics_observer.py` — MetricsObserver implementation
- `packages/temper-placer/src/temper_placer/pipeline/dag_engine.py:368-409` — emission methods with `contextlib.suppress(Exception)` replaced
- `scripts/pr_scorecard.py` — PR delta table computation
