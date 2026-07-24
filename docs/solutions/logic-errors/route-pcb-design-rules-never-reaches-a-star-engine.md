---
title: "route_pcb() accepted real per-net design rules but never forwarded them to the A* engine -- every net was clearance-enforced at the flat board default, including HighVoltage-class 400V nets"
date: "2026-07-24"
category: logic-errors
module: temper_placer
problem_type: logic_error
severity: critical
symptoms:
  - "Enabling enable_all_pad_tree=True appeared to regress DRC badly (shorting_items 74->199, clearance 6->499), suggesting the multi-pad tree planner was broken -- it was actually successfully routing previously-unrouted high-fanout power/HV nets for the first time, exposing a pre-existing, board-wide clearance bug unrelated to the tree planner"
  - "A first fix attempt (resolving design_rules.get_rules_for_net() inside the tree executor's call site) was code-correct by inspection and produced zero measurable change when actually measured"
  - "A runtime probe during a live route_pcb() run showed design_rules.net_class_assignments had 0 entries for every net, including HighVoltage-class nets that should resolve 6.0mm clearance per IEC 60335-1"
  - "A later PR built a correctly-converted net_classes dict but silently reused the original dead _net_class_assignments input parameter (always None from every real caller) at the pipeline.run() call sites instead of the newly-built local variable, reintroducing the same bug in a new form"
root_cause: logic_error
resolution_type: code_fix
tags:
  - temper-placer
  - router-v6
  - design-rules
  - clearance
  - safety-critical
  - silent-failure
  - wiring-bug
---

# route_pcb() accepted real per-net design rules but never forwarded them to the A* engine

## Problem

`route_pcb()` accepted a rich, YAML-SSOT-loaded `design_rules` object (real per-netclass clearance/trace-width values, including `HighVoltage=6.0mm` per IEC 60335-1 Table 16) from its caller, but only used it for two things: computing `layer_constraints` and feeding the writer's zone-pour emission. It never forwarded `net_class_assignments`/`net_classes` into `RouterV6Pipeline.run()`, so `pcb.design_rules` -- the object the actual A* pathfinding engine reads -- was always the empty, freshly-parsed default. Every net this router has ever traced, tree-executed or plain A*, across the router's entire history, was clearance-enforced at a flat 0.2mm regardless of netclass, including the 400V HV bus.

## Symptoms

- Enabling `enable_all_pad_tree=True` looked like a DRC regression (`shorting_items` 74->199, `clearance` 6->499) -- the tree planner appeared broken.
- A first fix attempt, threading `design_rules.get_rules_for_net(net_name)` into the tree executor's call site, was the right code but changed nothing when measured.
- A runtime probe showed `design_rules.net_class_assignments` had 0 entries for every net, always -- including HighVoltage-class nets.
- A later PR (property-test hardening) built a correctly-converted `net_classes` dict but wired the *old* dead `_net_class_assignments` input parameter into `pipeline.run()` instead of the properly-built local variable, silently reintroducing the bug.

## What Didn't Work

- **Fixing the resolution call without checking what it resolves against.** `design_rules.get_rules_for_net(net_name)` inside `_astar_reconstruct.py`'s tree executor call was the correct fix in isolation -- but `design_rules` itself (`pcb.design_rules`, rebuilt by `RouterV6Pipeline.run()` re-parsing the board file from scratch) was never populated with real data. The fix never reached anything. Code review alone could not catch this; only a live runtime probe of the actual object at the actual call site could.
- **Trusting a passing test suite as proof.** The one existing test near the eventual fix, `test_route_pcb_e2e_threads_design_rules`, fully mocked out `RouterV6Pipeline` and asserted only on the writer's zone-pour output. It could not have caught a bug in what was passed to `pipeline.run()`, by construction -- it never inspected the mock's call arguments for that half of the contract.

## Solution

`route_pcb()` (`_adapter_convert.py`) now builds both the net-name mapping and the real per-class rules from the caller's `design_rules`, and forwards both explicitly:

```python
net_class_assignments: dict[str, str] = {}
if design_rules is not None:
    net_class_assignments = dict(getattr(design_rules, "net_class_assignments", {}) or {})

_stage0_net_classes: dict[str, Any] = {}
if design_rules is not None:
    core_net_classes = getattr(design_rules, "net_classes", None)
    if core_net_classes:
        for class_name, core_rules in core_net_classes.items():
            _stage0_net_classes[class_name] = _to_stage0_netclass_rules(core_rules)

result = pipeline.run(
    Path(temp_path),
    net_class_assignments=net_class_assignments,
    net_classes=_stage0_net_classes if _stage0_net_classes else None,
)
```

`RouterV6Pipeline.run()` (`_pipeline_core.py`) gained a `net_classes` parameter that merges into `pcb.design_rules.net_classes`, alongside the pre-existing (previously unused-in-practice) `net_class_assignments` merge into `pcb.design_rules.net_class_assignments`. Both dicts have to be populated for `get_rules_for_net()` to resolve anything beyond the flat "Default" fallback.

A new `_to_stage0_netclass_rules()` adapter converts the YAML-SSOT shape (`core.netclass_rules_gen.NetClassRules`, `.clearance`/`.trace_width`) into the A* engine's shape (`stage0_data.NetClassRules`, `.clearance_mm`/`.trace_width_mm`), preserving `safety_category` (needed by the HV/AC forced-segment fail-closed gate) and raising on an unrecognized input shape rather than silently returning flat defaults.

Verified with a runtime probe, not just review: `design_rules.net_class_assignments` went from 0 entries (always) to 38, with `+340V_BUS`/`SW_NODE` correctly resolving `HighVoltage, clearance_mm=6.0`.

## Why This Works

`stage0_data.DesignRules.get_rules_for_net(net_name)` looks up `class_name = self.net_class_assignments.get(net_name)`, then `self.net_classes[class_name]`. Both dicts must be populated for resolution to succeed -- a class name with no matching rules entry, or rules with no name mapping pointing to it, both fall through to the "Default" flat-clearance fallback silently. `get_rules_for_net()` itself was never wrong. The bug was that `pcb.design_rules` -- the object the A* engine actually reads -- is rebuilt by `RouterV6Pipeline.run()` re-parsing the board file internally, and `route_pcb()` never threaded the caller's real `design_rules` into that re-parse at all.

## Prevention

- Any config object threaded through more than one pipeline layer needs at least one test that exercises the real call chain end-to-end, or spies on the exact call arguments crossing the boundary -- not only a test that mocks the downstream consumer and checks its return value survives the round trip. See `test_route_pcb_forwards_real_netclass_rules_to_pipeline_engine` (`test_adapter.py`) for the pattern that would have caught this: it asserts on what `route_pcb()` calls `pipeline.run()` with, using a Hypothesis-generated sweep of clearance values rather than one hardcoded example.
- Fixes to config-wiring bugs must be verified with a live runtime probe of the value actually reaching its consumer, not code review alone -- the first fix attempt here was correct code and still a complete no-op.
- A local variable that shadows or resembles a dead parameter's name (`_net_class_assignments` the unused input vs `net_class_assignments` the correctly-built local) is a real regression risk during refactors. Prefer removing the dead parameter entirely -- done here -- over leaving both names in scope where a later edit can silently pick the wrong one.
- `_to_stage0_netclass_rules()` now warns loudly when a source netclass field has no equivalent in the target schema (e.g. `creepage_mm`, `voltage_v`) instead of silently dropping it.

## Related Issues

- `docs/plans/2026-07-23-005-fix-router-design-rules-wiring-plan.md` -- the plan this fix was implemented under.
- `docs/solutions/logic-errors/parsed-stub-missing-nets-silently-disables-layer-constraints-2026-07-22.md` -- an earlier, closely related bug: `route_pcb()`'s `layer_constraints` resolution silently no-ops when `parsed.nets` is missing, found by the same "measured it, got zero effect" methodology.
- `docs/brainstorms/2026-07-20-router-tree-executor-resilience-and-zone-policy-requirements.md` R11 -- prior art for the "decoy trap" of similarly-named but unrelated `design_rules` objects.
- `docs/brainstorms/2026-07-23-property-test-hardening-requirements.md` -- the property-test scoping that found the `_net_class_assignments` regression (R3) after the first fix attempt.
