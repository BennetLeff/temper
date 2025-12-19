# Temper Metrics Registry

This document defines all metrics tracked by the GPBM measurement system.

## How to Use

1. **Define new metrics** by adding entries to the appropriate section below
2. **Reference metrics** in bd issue descriptions using `measurement_targets` YAML block
3. **Measurements** are collected automatically on `bd close` (via `bd-done`)
4. **Historical data** is stored in `measurements.jsonl`

### Adding Measurement Targets to Issues

Include a YAML block in your issue description:

```yaml
measurement_targets:
  - metric: fw_test_coverage
    target: ">=80"
  - metric: placer_drc_violations
    target: "==0"
```

## Firmware Metrics

| Metric ID | Description | Target | Source | Command |
|-----------|-------------|--------|--------|---------|
| `fw_test_coverage` | Unit test line coverage | >=80% | pytest/gcov | `cd firmware/test/build && ctest --output-on-failure` |
| `fw_state_machine_tests` | State machine test count | >=37 | Unity | `ctest -N \| grep -c 'test_state'` |
| `fw_integration_tests` | Integration test count | >=30 | Unity | `ctest -N \| grep -c 'test_integration'` |
| `fw_build_size_kb` | Firmware binary size | <=512 | ESP-IDF | `ls -la build/*.bin \| awk '{print $5/1024}'` |
| `fw_stack_usage_pct` | Peak stack usage | <=80% | FreeRTOS | Runtime analysis |
| `fw_heap_fragmentation` | Heap fragmentation ratio | <=20% | FreeRTOS | Runtime analysis |

## Placer Metrics

| Metric ID | Description | Target | Source | Command |
|-----------|-------------|--------|--------|---------|
| `placer_drc_violations` | KiCad DRC violation count | ==0 | KiCad | `temper-placer validate {pcb} --json` |
| `placer_wirelength_mm` | Total estimated wirelength | project-specific | Optimizer | `temper-placer metrics {pcb}` |
| `placer_overlap_loss` | Final overlap loss value | <1.0 | Optimizer | Optimizer output JSON |
| `placer_boundary_loss` | Final boundary loss value | <10.0 | Optimizer | Optimizer output JSON |
| `placer_convergence_epochs` | Epochs to convergence | <=8000 | Optimizer | Optimizer output JSON |
| `placer_heuristic_improvement` | Wirelength reduction from heuristics | >=20% | Benchmark | Benchmark tests |

## Simulation Metrics

| Metric ID | Description | Target | Source | Command |
|-----------|-------------|--------|--------|---------|
| `sim_zvs_margin_ns` | ZVS timing margin | >=100ns | ngspice | Extract from waveform |
| `sim_thermal_rise_c` | Max junction temp rise | <=40C | ngspice | Thermal simulation |
| `sim_efficiency_pct` | Power conversion efficiency | >=92% | ngspice | Power simulation |
| `sim_overshoot_pct` | Voltage overshoot percentage | <=10% | ngspice | Transient simulation |
| `sim_dead_time_ns` | Dead time measurement | 200-500ns | ngspice | Gate driver simulation |

## Requirements Metrics

| Metric ID | Description | Target | Source | Command |
|-----------|-------------|--------|--------|---------|
| `req_p0_verified_pct` | P0 requirements verified % | ==100% | Requirements parser | `python3 tools/gpbm/requirements_parser.py --status` |
| `req_total_verified_pct` | All requirements verified % | >=90% | Requirements parser | `python3 tools/gpbm/requirements_parser.py --status` |
| `req_linked_issues_pct` | Requirements linked to issues % | >=80% | Requirements parser | Cross-reference with bd |

## Code Quality Metrics

| Metric ID | Description | Target | Source | Command |
|-----------|-------------|--------|--------|---------|
| `py_type_coverage` | Python type annotation coverage | >=90% | mypy | `mypy src --txt-report /dev/stdout` |
| `py_lint_errors` | Ruff lint error count | ==0 | ruff | `ruff check src --statistics` |
| `c_lint_warnings` | cppcheck warning count | ==0 | cppcheck | `cppcheck --enable=all firmware/` |

## Eco Memory Metrics

Metrics for tracking semantic memory context costs in the GPBM workflow.

| Metric ID | Description | Target | Source | Command |
|-----------|-------------|--------|--------|---------|
| `eco_gather_tokens` | GATHER output token estimate | <=1500 | gather.py | `python3 tools/gpbm/gather.py --goal "$GOAL" --domain $DOMAIN \| wc -c \| awk '{print int($1/4)}'` |
| `eco_memories_returned` | Number of memories in GATHER | 3-10 | gather.py | `python3 tools/gpbm/gather.py --goal "$GOAL" --json \| python3 -c "import sys,json; d=json.load(sys.stdin); print(sum(len(v) for v in d['eco_memories'].values()))"` |
| `eco_avg_memory_chars` | Average memory content length | <=500 | eco_client.py | Sampled from Eco API responses |
| `eco_min_score` | Minimum similarity score threshold | 0.6-0.8 | eco_client.py | Configuration value |

### Context Cost Analysis

Token cost breakdown for GATHER phase context injection:

| Component | Typical Size | Notes |
|-----------|-------------|-------|
| Eco memories (5) | 300-1500 tokens | Depends on memory sizes and count |
| Requirements (5-10) | 100-300 tokens | Table format, compact |
| Issues (10) | 200-400 tokens | List format with IDs |
| Files (12) | 50-100 tokens | Path list only |
| Boilerplate | ~200 tokens | Headers, formatting |
| **Total** | **850-2500 tokens** | Target: <=1500 |

### Optimization Levers

1. **min_score threshold** - Higher = fewer but more relevant memories
2. **limit per category** - Cap on memories returned
3. **Content truncation** - Already truncated to 300 chars in markdown
4. **Memory type filtering** - Could exclude ISSUE/BEADS mirrors, keep only REFLECTION

## Custom Metrics

Projects can define custom metrics by:

1. Adding an entry to this registry
2. Implementing a collector in `tools/gpbm/collectors/` (optional)
3. Specifying the command to run for measurement

### Collector Interface

```python
# tools/gpbm/collectors/my_metric.py
def collect(task_id: str, config: dict) -> dict:
    """
    Returns:
        {"value": <numeric>, "pass": <bool>, "details": <str>}
    """
    pass
```

## Measurement Data Format

Measurements are stored in `measurements.jsonl` with one JSON object per line:

```jsonl
{"timestamp": "2025-12-19T10:30:00Z", "metric": "fw_test_coverage", "value": 78.5, "target": ">=80", "pass": false, "task": "temper-xxx", "commit": "abc123"}
{"timestamp": "2025-12-19T10:30:05Z", "metric": "placer_drc_violations", "value": 0, "target": "==0", "pass": true, "task": "temper-yyy", "commit": "def456"}
```

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | ISO 8601 | When measurement was taken |
| `metric` | string | Metric ID from this registry |
| `value` | number | Measured value |
| `target` | string | Target expression (e.g., ">=80", "==0") |
| `pass` | boolean | Whether value meets target |
| `task` | string | bd task ID that triggered measurement |
| `commit` | string | Git commit hash |

## Dashboard Generation

Dashboards can be generated from `measurements.jsonl`:

```bash
# Generate HTML dashboard (future)
python3 tools/gpbm/dashboard.py --output metrics/dashboards/latest.html

# Export to CSV for external tools
cat metrics/measurements.jsonl | jq -r '[.timestamp, .metric, .value, .pass] | @csv'
```

## Integration with bd Issues

### Example Issue with Measurements

```markdown
# Implement PID Controller Improvements

## Description
Improve PID tuning for better temperature stability.

## Measurement Targets
measurement_targets:
  - metric: fw_test_coverage
    target: ">=85"
  - metric: fw_integration_tests
    target: ">=35"

## Acceptance Criteria
- [ ] Temperature stability within ±1°C
- [ ] All measurements pass
```

When this issue is closed via `bd-done`, the measurement system will:

1. Parse `measurement_targets` from the description
2. Run each metric's command
3. Compare against targets
4. Log results to `measurements.jsonl`
5. Report pass/fail to the user
