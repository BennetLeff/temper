---
title: Silent no-op bugs in measurement code — two bugs that produced a false 0-DRC verdict
date: "2026-07-07"
category: best-practices
module: temper_placer
problem_type: best_practice
component: testing_framework
severity: medium
applies_when:
  - "Writing measurement or experiment harness code that gates decisions"
  - "Consuming data from external tools (kicad-cli, subprocess) where failures can be silent"
  - "Iterating data structures whose types are not statically verified (tuples vs objects)"
tags: ["silent-failure", "false-positive", "experiment-discipline", "measurement", "tuples-vs-objects", "subprocess"]
---

# Silent no-op bugs in measurement code — two bugs that produced a false 0-DRC verdict

## Context

The netclass-aware clearance experiment measured DRC error counts at three checkpoints. The initial result — 0 DRC errors at every checkpoint — would have been the decisive measurement closing the 121→29 DRC gap. But the 0 came from two bugs that both produced silent empty results, not from the system actually working.

The placement render revealed the truth: all 33 components collapsed into the top-left corner. The "netclass-aware SEPARATED at 6mm, DRC-clean by construction" mechanism was a silent no-op.

## Guidance

**When writing measurement code, every path that produces a number must be auditable.** Two specific patterns to guard against:

### 1. External tool failures can be silent

```python
# WRONG: returns 0 when kicad-cli produces no output (board load failure, etc.)
def run_drc(pcb_path):
    drc_out = Path(tempfile.mktemp(suffix='.json'))
    subprocess.run(['kicad-cli', 'pcb', 'drc', '-o', str(drc_out), str(pcb_path)],
                   capture_output=True, text=True, timeout=120)
    if drc_out.exists():
        return len(json.loads(drc_out.read_text()).get('violations', []))
    return 0, 0   # <-- the board didn't load, but the measurement says "0 errors"
```

```python
# RIGHT: check exit code. A non-zero exit means the tool couldn't run.
def run_drc(pcb_path):
    result = subprocess.run(...)
    if result.returncode != 0:
        return -1, -1, result.returncode  # sentinel: tool failure, not zero errors
    if not drc_out.exists() or drc_out.stat().st_size == 0:
        return -1, -1, -2  # sentinel: no output produced
    return len(errors), len(warnings), 0
```

The pattern documented in `docs/solutions/architecture-patterns/two-tier-acceptance-gate-unsat-surfacing-2026-07-05.md` — `truth_gate()` returning `error_count=0` when the PCB file didn't exist — was the exact same class of bug. This is the second occurrence.

### 2. Tuples silently fail attribute access with `getattr(default)`

```python
# WRONG: net.pins[i] is a tuple. getattr(tuple, 'component', None) returns None.
# Every component returns None → 0 constraints generated → solver "passes" trivially.
def _resolve_component_net_class(comp, netlist):
    for net in netlist.nets:
        for pin in getattr(net, 'pins', []):
            if getattr(pin, 'component', None) == comp_ref:  # tuple has no .component
                return classify(net.name)
    return None
```

```python
# RIGHT: iterate component.pins (Pin objects with .net attribute)
def _resolve_component_net_class(comp, netlist):
    for pin in getattr(comp, 'pins', []):
        net_name = getattr(pin, 'net', '')
        if net_name:
            return classify(net_name)
    return None
```

The `netlist.nets[].pins[]` vs `component.pins[]` distinction is not obvious from reading the code — both are called `pins` and both are iterables. The type difference (tuple vs Pin object) only reveals itself at runtime.

## Why This Matters

**Two silent no-ops compound into false confidence.** The DRC function reported 0 because kicad-cli couldn't load the board. The constraint generator reported 0 because the tuples had no `.component`. Together they produced "0 DRC errors at every checkpoint" — a result that passed every sanity check (it was the desired outcome) but was wrong on every layer.

**The "it measured 0" pattern is especially dangerous** because zero is the expected success value. The function that's supposed to count errors should fail noisily on its own failure — a sentinel value (-1), an exception, or a log message that can't be ignored. Returning 0 on failure is a false-negative generator.

## When to Apply

- Any function that returns a numeric measurement from an external tool
- Any iteration over data structures where the type is not statically verified (parsed formats, tuples vs objects, dicts with inconsistent keys)
- Any experiment harness whose output gates downstream investment decisions

## Related

- `docs/solutions/architecture-patterns/two-tier-acceptance-gate-unsat-surfacing-2026-07-05.md` — same `return 0 on missing file` bug in the truth gate
- `docs/experiments/netclass-layers-2026-07-07.md` — the experiment report with honest diagnosis
- `packages/temper-placer/src/temper_placer/placer/cp_sat/netclass_constraints.py` — the fixed constraint generator
