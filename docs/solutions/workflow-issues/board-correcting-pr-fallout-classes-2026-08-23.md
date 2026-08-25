---
title: "Landing a board-correcting PR: the fallout is classed, not generic — five artifact classes need five different resolutions"
date: "2026-08-23"
category: workflow-issues
module: board-gates
problem_type: workflow_issue
component: development_workflow
severity: critical
applies_when:
  - "a PR corrects footprints, placements, or netlist-derived content on pcb/*.kicad_pcb after a period of source/board drift"
  - "multiple gates, tests, and provenance records fail at once and look like one undifferentiated 'fallout' pile"
  - "someone proposes greening every red check by re-pinning baselines wholesale"
  - "a reviewer asks whether a failing safety test is a stale pin or a live alarm"
  - "CI checks are evaluated per-branch while the fix stack spans several branches forked at different points"
tags:
  - compound-engineering
  - board-drift
  - stale-pins
  - same-pr-discipline
  - drc-ceiling
  - provenance
  - safety-alarms
  - ci-canonical-artifacts
  - false-green
---

# Landing a board-correcting PR: the fallout is classed, not generic

## Context

When `pcb/temper.kicad_pcb` carries superseded footprints for weeks, landing
the correction (PR #1424: C6 film cap + K1 Schrack relay replacing a disc cap
and phantom Faston tabs) triggers a cascade: the DRC ceiling, two provenance
records, three geometry-pinned safety tests, a schematic drift gate, a
board-sync stamp, an evidence-provenance gate, and a whole-board safety audit
all fail in one run. Measured on main @ `11b9573e` (2026-08-23): errors had
ratcheted **down** 402 → 398 across the landing sequence, yet five jobs still
carried red.

The trap is treating that cascade as one problem. It is five classes with
five different resolutions — and two of them must **not** be "fixed" at all.

## The classes (measured on temper, 2026-08-22/23)

### Class 1 — Re-measurable ceilings: same-PR re-measurement, attribution required

DRC ceiling categories move when copper moves. Resolution is mechanical but
attribution-bearing: 120-sample characterization via `_drc_api.run_drc`,
baseline re-measured first to validate the environment, per-type deltas each
named to a component pair or commit. Decreases ratchet down freely; any rise
needs a `Ceiling-Approval:` trailer plus a new `_march` entry.

Measured example (#1360/#1363/#1462): classifying seven HV nets was expected
to cost ~+11 errors; it actually *cleared* same-domain false positives and
ratcheted down −4, and collapsed creepage's run-to-run scatter to a constant.
Predictions about direction can be wrong; the measurement is the decision.

Trap within the class: the cap-saturation guard (`ci_check_drc.py` exit 4)
cannot be greened by any ceiling value while kicad-cli truncates reports at
199/499. If a category saturates, either commit its true uncapped total
(`uncapped_totals`, measured by the bucket-partition protocol) so the kernel
compares true-count vs ceiling, or the gate stays red honestly. See
`power_pcb_dataset/drc_ceiling.json` `uncapped_totals` and #1442/#1455.

### Class 2 — Provenance records: verify identity invariants, re-pin same-PR

Any registered record whose inputs include the board
(`drc_ceiling.json`, `temper_constraints.references.yaml`) goes STALE the
moment the board bytes change. Re-pin in the same PR — but only after
re-verifying the record's own semantic claim against the new board:

```text
references.yaml: Sheetpath->Reference map diffed identical across all 168
footprints before re-pinning (width/footprint swaps change geometry, never
identity).
```

A re-pin without the verification is the "false-fresh record" the gate's
docstring was written to prevent.

### Class 3 — Stale geometry test pins: re-point WITH provenance of the change

Tests that pin board figures (via size, outline dimensions, pad gaps,
documented violation counts) describe one session's tree. They go stale the
moment anything moves copper. Resolution: re-point to the measured current
value **with a dated comment naming the cause**, e.g.

```python
# Via::new enforces the 0.254mm annular-ring floor at construction
# (docs/evidence/2026-08-17-blind-via-annular-floor-fix.md): a 0.6/0.3 via
# would give a 0.15mm ring, so the emitter raises the diameter to 0.9.
assert "(size 0.9000)" in content
```

Never silently update the number. The comment IS the audit trail that
separates a legitimate re-pin from suppressing a regression.

### Class 4 — Safety-alarm tests: do NOT re-base; they are the alarm

Whole-board compliance audits (REQ-SAFE-01-style: currently 66 violations)
and footprint-isolation tests fail because **the board genuinely violates**.
Re-basing them to accept the current state is the exact ratchet-down this
repo forbids — the handoff's own §3.3 principle applies: *total count is the
wrong objective when composition differs in severity*, and creepage findings
outrank silk/courtyard wins. These stay red until real placement work
shrinks them; their failure inventory IS the work order.

Sub-case: some pins reference pads that no longer exist
(`KeyError: '13'` after a relay footprint swap). Those still stay red until
the replacement part's real geometry is measured and the test re-pointed as
part of the same session that owns the physical fix.

### Class 5 — Environment-canonical stamps: adopt CI write+diff, don't chase bytes

If a committed stamp folds in bytes that embed the build environment
(atopile netlists embed absolute build paths in sheetpaths; toolchain output
varies), no developer-committed stamp is byte-reproducible by CI — ever.
Chasing it fails three ways in a row (version pin insufficient, path
normalisation locally-correct-but-CI-different). Resolution is structural:
convert the gate to the repo's standard **regen-and-diff** pattern
(`gen_config`, `gen_schematics`, wasm registry all use it) — CI writes the
artifact against its canonical inputs, then `git diff --exit-code` fails
visibly if the committed copy differs. Commit whatever digest CI prints;
local runs use the local check script knowing CI wins.

## The meta-traps around the cascade itself

1. **Per-branch CI verdicts lie across a stacked fix series.** Each branch
   was green only at its own fork point; the combined tree was never tested.
   A merge queue or one combined-tree CI run before the last merge prevents
   discovering interaction failures post-merge.

2. **Audit/aggregator scripts can report false GREENs.** A step-level audit
   that dedupes results across multiple workflow runs mixed a stale success
   into the verdict and reported Clippy green when the primary job log said
   failed. Verify contested verdicts from the primary job log
   (`gh api actions/jobs/<id>` → steps), never from a secondary aggregation.

3. **Uncommitted stamp writes die on checkout.** A normalized re-stamp
   written in a detached-HEAD investigation round was lost when the tree
   moved. In this repo, commit before you verify (HANDOFF §1.6).

## Resolution checklist

```text
For each failing check after a board-correcting PR:

[ ] Does the check pin a MEASURABLE board figure?
    -> yes: re-measure; if changed, re-point with dated cause comment (Class 3)
    -> yes, and it asserts compliance: STOP - Class 4, fold into the fix session
[ ] Is it a ceiling/provenance record keyed to board content?
    -> re-verify the record's semantic claim, re-pin same-PR (Class 2);
       rises need Ceiling-Approval + _march attribution (Class 1)
[ ] Does it hash bytes that embed the build environment?
    -> convert to CI-canonical regen+diff (Class 5); do not chase local bytes
[ ] Was the check green only at its branch's fork point?
    -> rebase the stack, re-run, re-read verdicts from primary job logs
[ ] Would going green here mean accepting more creepage/reinforced-barrier
    exposure than the enforced model requires?
    -> STOP regardless of everything above
```

## What this method closes, and what it leaves open

Closed: the cascade becomes a finite, classified work list; each item has a
canonical resolution and an evidence trail; the two do-not-fix classes are
protected by explicit rule rather than judgement call mid-marathon.

Left open deliberately: the underlying board debt (dense-pocket creepage
clusters, K1 contact routing, body collisions) that Class 4 alarms point at.
The gates staying red there is the system working — see #1445 for the live
inventory and the K1 place-and-reroute brief.

## Related records

- `docs/HANDOFF-2026-08-21.md` — session origin; §1 operating rules, §3.3/§6
- `docs/evidence/2026-08-21-footprint-drift-drc-remeasure.md` — the
  120-sample re-measurement and silk_overlap decomposition this doc's Class 1
  procedure produced
- PRs #1424 (the correcting PR), #1449 (four-gate triage), #1455 (uncapped
  totals), #1457+1460+1465+1467 (stamp saga arc), #1462 (classification
  landing), #1458 (anti-vacuity triage)
- issue #1445 — live inventory; issue #1442 — saturation guard contract;
  issue #1446 — wasm geometry tier
