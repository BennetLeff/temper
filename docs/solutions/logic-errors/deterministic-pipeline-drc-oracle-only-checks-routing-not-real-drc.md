---
title: "Deterministic pipeline's 'DRC violations: 0' self-report is nearly vacuous — the internal oracle only checks routing-geometry clearance, not real KiCad DRC"
date: "2026-07-17"
category: logic-errors
module: temper_placer
problem_type: logic_error
component: service_object
severity: critical
symptoms:
  - "power_pcb_dataset/baselines/temper_production_baseline.yaml's deterministic_pipeline.drc_violations reads 0, and the pipeline's own drc_validation stage logs 'DRC validation passed: 0 violations'"
  - "Independent kicad-cli DRC on the exact same exported board reports 803 real violations (225 errors, 578 warnings) -- not close to zero"
  - "Even the unplaced INPUT board (before any placement/routing) has 629 pre-existing kicad-cli violations (170 errors, 459 warnings)"
root_cause: logic_error
resolution_type: documentation
tags:
  - temper-placer
  - drc
  - deterministic-pipeline
  - self-grading
  - kicad-cli
  - metric-definition-mismatch
---

# Deterministic pipeline's "DRC violations: 0" checks routing clearance, not real DRC

## Problem

The deterministic pipeline's `DRCValidationStage` calls
`state.drc_oracle.validate_all()` and stores the result as
`state.drc_violations`, which flows into
`power_pcb_dataset/baselines/temper_production_baseline.yaml`'s
`deterministic_pipeline.drc_violations: 0`. Read at face value, "0 DRC
violations" says the production board's placement is clean. It is not:
running the codebase's own real DRC path
(`temper_placer.validation._drc_api.run_drc`, the same `kicad-cli`-backed
function `DrcRatchet`'s `"kicad-cli"` backend uses) against the exact same
exported board finds **803 real violations** (225 errors, 578 warnings).

## Root Cause

`state.drc_oracle` (populated in `deterministic/stages/setup.py:207`) is a
`router_v6.constraints_drc_oracle.DRCOracle` — a router-internal geometry
checker, not a KiCad-rule engine. Its `validate_all()` (`constraints_drc_
oracle.py:611`) checks exactly two things: track-to-track clearance and
via-to-via clearance, using its own internal `self.geometry` model of
tracks and vias.

The deterministic pipeline's routing stages currently produce almost no
routing geometry — `power_pcb_dataset/baselines/temper_production_baseline.yaml`'s
own `escape_vias: 124, routed_nets: 0` already documents this honestly.
With zero routed nets and only escape vias, `validate_all()`'s track-
clearance loop has essentially nothing to iterate over, so it trivially
returns an (almost) empty violation list. **The check isn't wrong — its
scope was always narrower than "DRC" implies, and that gap only becomes
visible once you ask what geometry it's actually checking against.**

None of the 803 real kicad-cli violations are things this oracle was ever
built to catch: courtyard overlaps between placed components, silkscreen-
to-pad clearance, unrouted-net flags, hole-to-hole spacing, edge-of-board
clearance, and (per the symptom list) net shorts — categories entirely
outside a track/via-clearance-only checker's scope.

## What Didn't Work

- Assuming `drc_available: false` at the baseline's top level was the only
  honesty caveat needed. It correctly flags that full DRC wasn't run for
  the *baseline extraction* metrics, but `deterministic_pipeline
  .drc_violations: 0` sits right next to it with no equivalent caveat, and
  reads as a real number because the pipeline's own log line says
  "DRC validation passed."
- Trusting the stage name (`DRCValidationStage`, `drc_oracle`,
  `drc_violations`) as a description of scope. The naming implies general
  DRC; the implementation is routing-geometry-only. This is the same
  failure shape as `net_count` meaning two different things in two
  different code paths (see the sibling doc), just with a name that reads
  as far more comprehensive than the metric it actually reports.

## Resolution

Not a code fix — the oracle's narrow scope is legitimate for its actual
job (giving the *router* a fast internal clearance check as it lays
tracks). The fix is honest labeling:

```yaml
# Before:
deterministic_pipeline:
  drc_violations: 0

# After:
deterministic_pipeline:
  drc_violations: 0  # router-geometry oracle only (track/via clearance) --
                      # NOT equivalent to real DRC. Board is barely routed
                      # (routed_nets: 0, escape vias only), so this check
                      # has almost nothing to evaluate. Real kicad-cli DRC
                      # on this exact export: 225 errors, 578 warnings
                      # (verified 2026-07-17). See docs/solutions/
                      # logic-errors/deterministic-pipeline-drc-oracle-
                      # only-checks-routing-not-real-drc.md.
  kicad_cli_drc_errors: 225    # ground truth, verified 2026-07-17
  kicad_cli_drc_warnings: 578  # ground truth, verified 2026-07-17
```

## Why This Matters

This is the most consequential self-grading gap found in this arc. Every
other instance (net_count, the CP-SAT CLI stub, `ClosureTest`'s dead
strategy) misreported a *tooling* status. This one misreports whether the
board itself is electrically and mechanically sound — the kind of claim
someone could reasonably act on ("placement is DRC-clean, proceed to
routing/fab") without realizing the check behind it never looked at
courtyard overlaps, shorts, or silkscreen at all.

## Prevention

- **A stage/field named after a broad concept (DRC, validation, check)
  should either cover that concept's real scope or say explicitly which
  narrow slice it covers.** `TrackViaClearanceOracle` would have been an
  honest name for what this class does; `DRCOracle` is not.
- **When a real, independent version of a check already exists in the
  codebase** (here, `validation._drc_api.run_drc`, backed by kicad-cli and
  already used by `DrcRatchet`), a narrower internal approximation used
  elsewhere should be explicitly labeled as an approximation in both code
  comments and any metrics it feeds, not left to imply equivalence.
- **A "0 violations" result on a mostly-empty board (0 routed nets) is a
  red flag by construction**, not reassurance — a check with almost
  nothing to examine will almost always report clean. Any metrics
  pipeline should treat "0 violations AND <meaningful amount of the
  thing being checked>" as a case worth flagging, not celebrating.

## Related Issues

- [`docs/solutions/logic-errors/net-count-metric-definition-mismatch-regression-baseline.md`](net-count-metric-definition-mismatch-regression-baseline.md)
  — same failure shape (a metric name implies more than the code behind it
  measures), much lower stakes (a count, not a safety-relevant pass/fail).
- `docs/solutions/architecture-patterns/cp-sat-feasibility-first-paradigm-2026-07-03.md`
  — the CP-SAT scale-wall investigation that led to independently
  verifying this DRC claim in the first place (the warm-start work
  prompted an end-to-end correctness sweep, per the user's explicit
  request to "root out sources of incorrectness... end to end").
- `power_pcb_dataset/baselines/temper_production_baseline.yaml` — updated
  with the real kicad-cli figures alongside the honestly-scoped oracle
  count.
