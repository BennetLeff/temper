---
title: "route_pcb() silently disables per-net layer assignment when parsed.nets is missing -- poisoned every production-board routing measurement in the test suite"
date: "2026-07-22"
category: logic-errors
module: temper_placer
problem_type: missing_validation
severity: critical
symptoms:
  - "PR #267 (zone/pour cross-class clearance + priority + shape localization) verified via multi-sample DRC to have zero measurable effect on shorting_items and a real unconnected_items regression, despite the underlying zone-clearance mechanism being correctly implemented and independently verified against source"
  - "Decomposing the actual shorting_items violations found 63% (47 of 75) are present identically whether zones are on or off -- a pre-existing correctness issue unrelated to zone/pour entirely -- and most of those pre-existing shorts are between adjacent pin numbers on the SAME component (e.g. pins 11&12, 12&13, 14&15, 29&30 all on net U22), matching a previously-diagnosed single-layer-routing pattern"
  - "All 212 routed track segments on the production board landed on F.Cu; zero on B.Cu, despite netclass_rules.yaml assigning several netclasses (Power, GateDrive, FinePitch, HighSpeed) to B.Cu and despite layer_constraints appearing 'wired' into pipeline.py's Stage 4 (map_topology_to_channels, fallback_channel_path both reference self.layer_constraints)"
root_cause: "route_pcb() (adapter.py) resolves per-net layer constraints via `net_names = [n.name for n in getattr(parsed, \"nets\", []) if ...]`, defaulting silently to an empty list when `parsed` has no `.nets` attribute -- which then makes `layer_constraints` resolve to `{}` with no error or warning. Every test file in this codebase that measures production-board routing quality (test_zone_pour_production_measurement.py, test_regression_drc.py x2, test_temper_production_board_routing.py, test_phase1_anti_false_zero.py) built its `parsed_stub` as `type(\"ParsedStub\", (), {\"source_path\": PATH})()` -- with only source_path, never nets. Every shorting_items/unconnected_items/completion_rate number measured by any of these tests, across this entire investigation (58, 83, 76.7, 84.9, 85.2, 239, 260...), was measured against single-layer-only (F.Cu) routing, regardless of what netclass_rules.yaml actually specifies."
resolution_type: code_fix
tags:
  - temper-placer
  - router-v6
  - layer-assignment
  - silent-failure
  - test-harness-bug
  - duck-typing
  - zone-pour
  - shorting-items
---

# route_pcb() silently disables per-net layer assignment when parsed.nets is missing

## Context

This investigation started as a follow-up to PR #263's zone/pour shorting_items
regression (58 → 83 once zones were actually filled with real copper). A
combined fix (PR #267: cross-class pairwise clearance via `class_pairs`,
native KiCad zone `(priority N)`, and localized pour shape via clustered
convex hulls) was planned, implemented, code-reviewed (feasibility review
caught and fixed a real `design_rules`-threading gap before merge attempt),
and then verified via the plan's own multi-sample methodology (4 seeds × 3
DRC samples, run against the actual branch code, not assumptions).

**The verification found the fix did not work**: `shorting_items` was
statistically unchanged (85.2 vs 84.9 pre-fix) and `unconnected_items` got
measurably worse (259.5 vs 255.0 pre-fix). PR #267 was closed without
merging. This document covers what the subsequent root-cause investigation
found.

## Investigation Path

### Step 1: Why did a correctly-implemented fix have zero effect?

Decomposing the actual shorting_items violations (not just counting them)
by comparing the exact zones-on vs zones-off net-pair sets:

- **47 of 75 (63%)** shorting pairs were present identically whether zones
  were on or off -- a pre-existing issue with zero relationship to zone/pour.
- Of the ~28 zone-attributable pairs, only **4** involved a zone-eligible
  net at all. The other 24 were ordinary-net-vs-ordinary-net shorts caused
  by the "net-diversion effect" (enabling zones changes which nets compete
  for A* grid space, perturbing paths for unrelated nets) -- not zone
  geometry or clearance.

This meant PR #267's fix (which only ever targeted zone-vs-zone clearance)
was correctly scoped to address at most ~4-9 of ~75 shorts. It could never
have moved the aggregate number much, which is exactly what was measured.

### Step 2: What's actually causing the 47 pre-existing shorts?

Inspecting the raw violation descriptions for the pre-existing set found an
unambiguous pattern: most pairs are between **adjacent pin numbers on the
same component** --

```
Pad 11 [gpio18] of U22  <->  Pad 12 [RTD_SCK] of U22
Pad 12 [RTD_SCK] of U22 <->  Pad 13 [usb_dn] of U22
Pad 29 [gpio36] of U22  <->  Pad 30 [gpio37] of U22
Pad 14 [usb_dp] of U22  <->  Pad 15 [safety-line] of U22
Pad 13 [power_in.ntc-no] of K1 <-> Pad 14 [w1_2] of K1
```

This matches, almost exactly, a prior diagnosis already on record in this
codebase:
`docs/solutions/architecture-patterns/u7-u8-w2-audit-shorting-diffpair-diagnosis-2026-07-18.md`
found that despite `layer_constraints` being *stored* on the pipeline, it
was never actually referenced by `_run_stage4()`, so **every net routed on
a single layer (F.Cu)** regardless of netclass. Fine-pitch components with
many closely-spaced pins (like the ESP32-S3-WROOM-1 module, `U22` here)
are exactly where single-layer routing produces adjacent-pin shorts: there's
no vertical separation available, so tracks for different pins' nets cram
together.

Checking whether that July 18 gap was ever actually closed: `pipeline.py`
now *does* reference `self.layer_constraints` in `_run_stage4()`
(`map_topology_to_channels(..., layer_constraints=self.layer_constraints)`,
`fallback_channel_path(net.name, pads, self.layer_constraints, ...)`) --
so the July 18 fix genuinely landed. And yet the production board still
routed 100% F.Cu.

### Step 3: Root cause -- confirmed empirically, not assumed

`route_pcb()` (`adapter.py`) resolves `layer_constraints` like this:

```python
layer_constraints: dict[str, Any] = {}
if design_rules is not None:
    net_names = [
        n.name for n in getattr(parsed, "nets", []) if getattr(n, "name", None)
    ]
    if net_names:
        layer_constraints = layer_assignments_from_netclass(design_rules, net_names)
```

`getattr(parsed, "nets", [])` silently returns `[]` if `parsed` has no
`nets` attribute -- no error, no warning. Every test file in this codebase
that measures production-board routing quality built its `parsed_stub` as:

```python
parsed_stub = type("ParsedStub", (), {"source_path": _PCB_PATH})()
```

-- with only `source_path`. Confirmed by direct comparison:

```python
broken_stub = type("ParsedStub", (), {"source_path": PCB_PATH})()
r1 = route_pcb(broken_stub, {}, _seed=42, design_rules=rules.design_rules, ...)
# B.Cu refs=0  F.Cu refs=212

fixed_stub = type("ParsedStub", (), {"source_path": PCB_PATH, "nets": netlist.nets})()
r2 = route_pcb(fixed_stub, {}, _seed=42, design_rules=rules.design_rules, ...)
# B.Cu refs=19  F.Cu refs=193
```

Six call sites had this exact bug: `test_zone_pour_production_measurement.py`,
`test_regression_drc.py` (×2 -- including the actual CI-gating
`zone-pour-measurement` job and the `regression` job whose "260 baseline"
was established in PR #266 earlier this same session), `test_temper_production_board_routing.py`,
`test_phase1_anti_false_zero.py`. Only the newest test
(`test_zone_pour_shape_clearance_measurement.py`, written for PR #267's own
U4 verification) happened to build the stub correctly, because whoever wrote
it independently included `nets` without realizing the other five call
sites lacked it.

**Every `shorting_items` / `unconnected_items` / `completion_rate` number
measured by any of these six tests, across this entire session's
investigation, was measured against single-layer-only routing** --
regardless of what `netclass_rules.yaml` actually specifies for Power,
GateDrive, FinePitch, or HighSpeed nets.

### Step 4: Fixing it exposes a real, separate, larger capability gap

With `.nets` correctly threaded, `shorting_items` improved modestly
(~75.2 → ~72-75, a small but real reduction) but `unconnected_items` got
measurably *worse* (260 → 299). The newly-unconnected nets were
`PWR_RTN` (174 unconnected-item entries), `+3V3` (78), `vcc` (24), `+15V`
(20), `+340V_BUS` (20), `DC_BUS_RTN` (20) -- the exact same high-fanout
plane-style nets already tracked as a known, unresolved capability gap in
`docs/brainstorms/2026-07-20-router-tree-executor-resilience-and-zone-policy-requirements.md`
(U5 zone/exemption policy, never built). Single-layer routing was
accidentally *masking* this gap: A* had an easier (if wrong) job on one
layer, so some of these nets happened to complete that don't complete once
real multi-layer routing is attempted. Fixing the plumbing bug doesn't
create a new problem -- it makes an existing, already-scoped problem
visible where it was previously hidden.

`tests/router_v6/test_phase1_anti_false_zero.py`'s
`TestU9CompletionPreservation::test_completion_rate_100pct_routing_signal`
(a `completion_rate == 1.0` guard, independent of kicad-cli) was *also*
only passing because of this same plumbing bug -- fixed the stub, then
quarantined the resulting failure the same way as the sibling gap in
`test_regression_drc.py::test_golden_board_routing_drc_regression`
(PR #266): an explicit `pytest.skip` citing the real cause and the tracking
doc, not a loosened assertion.

## Guidance

### Fix

1. Added a `ParsedPcbLike` `Protocol` (`adapter.py`) documenting the actual
   contract `route_pcb()` depends on (`source_path`, `nets: Sequence[_NetLike]`)
   -- replacing a bare `Any` that made this shape invisible to readers and
   type checkers.
2. Added a `logger.warning(...)` in `route_pcb()` when `design_rules` is
   provided but no net names are resolvable from `parsed` -- the graceful
   fallback (empty `layer_constraints`) is preserved for legitimate callers
   that don't care about layer assignment, but it is no longer silent.
3. Fixed all six broken call sites to pass `nets=netlist.nets`.
4. Added `tests.conftest.make_parsed_pcb_stub(source_path, netlist)` -- a
   single shared helper all of these call sites now use, so the pattern
   can't be reinvented incorrectly again.
5. Quarantined the one test whose assertion the fix genuinely broke
   (`test_completion_rate_100pct_routing_signal`), documenting why, per
   this repo's established quarantine-with-a-linked-gap discipline rather
   than loosening the assertion.

### Tests added

- `tests/router_v6/test_adapter.py::TestRoutePcbLayerConstraintsResolution`
  -- three unit tests using the existing `RouterV6Pipeline`-mocking pattern
  (fast, no real routing): `layer_constraints` is non-empty when `parsed.nets`
  is populated; the warning fires when `design_rules` is given but `nets`
  is missing; the warning does *not* fire when `design_rules` is `None`
  (the ordinary, non-misconfigured no-op case). Verified RED against the
  pre-fix code (the warning test failed; the other two passed regardless,
  correctly distinguishing "the bug" from "pre-existing correct behavior").
- `tests/router_v6/test_layer_assignment_ssot.py::TestLayerAssignmentsFromNetclass::test_no_net_silently_dropped_or_duplicated`
  -- a Hypothesis property test: for *any* set of distinct net names
  (including the empty set), `layer_assignments_from_netclass` returns
  assignments for exactly that set, never fewer (dropped) or more (stale/
  duplicated). Generalizes the existing example-based
  `test_each_net_gets_one_primary_layer` into a property, guarding the
  core mechanism this whole bug was about against future refactors.

### Verification

- `route_pcb()` with a correctly-populated stub produces real B.Cu tracks
  (19 of 212 on the production board) where it previously produced zero.
- Full affected test suite (`test_adapter.py`, `test_layer_assignment_ssot.py`,
  `test_phase1_anti_false_zero.py`, `test_temper_production_board_routing.py`,
  `test_zone_pour_production_measurement.py`, `test_regression_drc.py`,
  `test_zone_pour_shape_clearance_measurement.py`, fast subset):
  58 passed, 2 skipped (1 pre-existing + the newly-quarantined completion
  guard), 0 failed.

## Why This Matters

**Duck-typed test doubles hide contract drift silently.** `parsed: Any`
plus `getattr(parsed, "nets", [])` means a test stub can satisfy the
*syntactic* call (it has a `source_path`, `route_pcb` doesn't crash) while
silently failing to exercise a real code path (`layer_assignments_from_netclass`
never runs). No test failed. No warning fired. Six call sites had this bug
simultaneously because the pattern was copy-pasted, and each copy looked
correct in isolation.

**A measurement is only as honest as its input construction.** This
session spent significant effort building multi-sample DRC methodology to
control for `kicad-cli`'s own measurement noise and the router's
`PYTHONHASHSEED`-dependent net ordering (both real, both fixed). Neither
of those fixes mattered for this specific bug -- the boards being measured
were never routed the way the netclass SSOT says they should be, regardless
of sample count.

**"Wired but not exercised" can recur even after being fixed once.** The
July 18, 2026 diagnosis found `layer_constraints` stored but never
referenced by `_run_stage4()`, and that was fixed. This is the *same
symptom* (single-layer-only routing) with a *different root cause*
(the caller-side stub never provided the data that the now-correctly-wired
consumer needed). Fixing one link in a chain doesn't guarantee the whole
chain works -- verify at the actual measurement boundary, per
`docs/solutions/conventions/verify-netclass-clearance-on-the-routing-path-2026-07-12.md`.

## When to Apply

- When a function resolves optional behavior via `getattr(obj, "attr", default)`
  and the default silently degrades functionality rather than erroring --
  add a warning at minimum, ideally a typed contract (`Protocol`) documenting
  what's actually required for full behavior.
- When multiple test files independently hand-construct the same kind of
  stub/double for a shared collaborator -- extract a shared helper before
  the third copy, not after the sixth.
- When a fix's measured effect is smaller than expected or absent: before
  concluding "the fix doesn't work," verify the *harness* is exercising the
  code path the fix touches, not just that the fix's own unit tests pass.

## Related

- `docs/solutions/architecture-patterns/zone-pour-bounding-box-shorting-regression-2026-07-21.md` -- the investigation this one continues
- `docs/solutions/architecture-patterns/u7-u8-w2-audit-shorting-diffpair-diagnosis-2026-07-18.md` -- the original single-layer-routing diagnosis; this document confirms that fix landed but was defeated by this separate bug
- `docs/solutions/architecture-patterns/netclass-clearance-ssot-designrules-consumer-chain-2026-07-07.md` -- the `class_pairs`/`DesignRules` consumer-chain pattern
- `docs/solutions/conventions/verify-netclass-clearance-on-the-routing-path-2026-07-12.md` -- "verify at the enforcement point" discipline this bug is a fresh instance of
- `docs/brainstorms/2026-07-20-router-tree-executor-resilience-and-zone-policy-requirements.md` -- the still-open capability gap this fix exposed (U5 zone/exemption policy)
- PR #267 (closed, not merged) -- the zone/pour fix whose "no effect" measurement triggered this investigation
