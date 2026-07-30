---
title: DRC Burn-Down to Zero - Implementation Plan
type: feat
status: planned
date: 2026-07-30
topic: drc-burndown-to-zero
base_commit: d510f4ede1ce0f3db343776f024c0f8a36085675
source_requirements: docs/plans/2026-07-30-001-fix-drc-burndown-to-zero-plan.md
execution: code
---

# DRC Burn-Down to Zero - Implementation Plan

## Outcome

Implement the approved DRC burn-down contract so the committed board remains
the measured gate, the placer/router is the only source of credited progress,
and every run reports both external-DRC soundness and absolute prover
coverage. The implementation will not freeze a new DRC ceiling until the
`#474` netclass-pattern correction and `#486` rule correction are present and
the PD3/12.6 mm decision remains the active safety determination.

The current main commit is `d510f4ede`. This plan was written in the isolated
detached worktree `/private/tmp/temper-drc-burndown-plan`; the shared checkout
is intentionally left untouched.

## Non-negotiable ordering

1. **Prerequisite convergence.** Confirm the exact `#474` and `#486` inputs,
   verify all mains/high-voltage assignments in `pcb/temper.kicad_pro` agree
   with `TEMPER_NET_ASSIGNMENTS`, and verify the active creepage constant is
   PD3/12.6 mm. If either safety input is unresolved, stop before measuring.
2. **Measurement contract.** Re-measure the corrected board with the existing
   `run_drc()` path, `--all-track-errors`, and the repository's 120-sample
   protocol. Attribute every per-type change to a named board/rule/component
   cause. Do not update `drc_ceiling.json` in this implementation until the
   measurement is complete and any rise has an externally supplied
   `Ceiling-Approval:` decision.
3. **Prover output contract.** Add structured decline reasons and make the
   full route result carry them without changing the meaning of existing
   `failed_nets` consumers.
4. **Stackup/pour atomic change.** Land declared stackup roles and post-route
   pour regeneration together. A real-board completion and DRC before/after
   check is required; unit tests alone are insufficient because the prior
   role-only change caused a 12x completion regression.
5. **External soundness.** Grade the exact board emitted by the run with
   KiCad DRC and fail when a DRC violation is attributable to copper emitted in
   that run. Keep inherited/placement-only debt on the existing ceiling path.
6. **Coverage and campaign controls.** Ratchet absolute nets proven safe,
   then add campaign state that holds inactive DRC categories at their current
   values, tightens successful ceilings automatically, and rejects aggregate
   or per-category increases.
7. **Unattended determinism.** Finish with one entry point, byte-stable output
   checks, and the full end-to-end report. Only after this is green may a new
   burn-down baseline be committed.

## Work breakdown

### P0 - Establish the corrected measurement input

**Purpose:** Make the baseline reproducible before any new gate treats its
numbers as authoritative.

**Work:**

- Inspect the landing commits for `#474` and `#486` and record their SHAs in
  the evidence for this run; do not infer their contents from PR titles.
- Run `scripts/check_measurement_provenance.py` before measurement and confirm
  the board hash, branch, dirty state, KiCad version, DRC invocation, and
  sample count are recorded.
- Run the existing 120-sample `temper_placer.validation._drc_api.run_drc`
  campaign against `pcb/temper.kicad_pcb`; use `Counter` per DRC category and
  retain the complete observed range, not only one sample.
- Compare the observed categories with the prior `_march` entry. Explain
  increases from newly applied netclasses/rules separately from genuine board
  changes. If a rise cannot be attributed, stop and report it.
- Treat `power_pcb_dataset/drc_ceiling.json` as read-only during this step.

**Verification:** A checked-in evidence record or plan attachment names the
input commit, board hash, tool/flags/sample count, observed ranges, and
per-type attribution. No ceiling file changes are made without the required
approval decision.

### P1 - Structured decline reasons (provable-safety U1)

**Purpose:** Turn every non-routed net into an explicit, machine-readable
backlog item without weakening fail-closed behavior.

**Files:**

- `packages/temper-placer/src/temper_placer/router_v6/connectivity.py`
- `packages/temper-placer/src/temper_placer/router_v6/_astar_reconstruct.py`
- `packages/temper-placer/src/temper_placer/router_v6/_pipeline_route.py`
- `packages/temper-placer/src/temper_placer/router_v6/routing_results.py`
- `packages/temper-placer/tests/router_v6/test_decline_reason_contract.py`
- `packages/temper-placer/tests/router_v6/test_adapter.py`

**Implementation:** Extend the existing disposition/report structures with a
typed decline payload containing the net, failure stage, rule/domain when
known, and an explicit attribution-gap/prover-error variant when not known.
Thread it through topology UNSAT, pathfinding, forced-segment, and exception
paths. Preserve compatibility for callers that only read `failed_nets`, while
making a missing reason a test failure rather than silently treating it as a
normal route failure.

**Tests:** Cover a clearance refusal, topology UNSAT, internal prover error,
and a full-board assertion that 100% of declined nets have a non-empty reason.
Use board data for identifiers; do not add temper-specific rule literals to
generic router code.

### P2 - Declared stackup roles plus post-route pours (provable-safety U2/U3)

**Purpose:** Remove the zone-content/role coupling and make zones derived
output, in one reviewed change.

**Files:**

- `packages/temper-placer/src/temper_placer/io/_parse_board.py`
- `packages/temper-placer/src/temper_placer/router_v6/routing_space.py`
- `packages/temper-placer/src/temper_placer/router_v6/zone_emission.py`
- `packages/temper-placer/src/temper_placer/io/_write_zones.py`
- `packages/temper-placer/src/temper_placer/io/zone_filler.py`
- `scripts/kicad_fill_zones.py`
- a board-facts/stackup declaration source selected from the existing SSOT
  structure during implementation
- `packages/temper-placer/tests/router_v6/test_stackup_parsing.py`
- `packages/temper-placer/tests/core/test_stackup.py`
- `packages/temper-placer/tests/manufacturing/test_stackup_validator.py`
- `packages/temper-placer/tests/router_v6/test_zone_emission.py`
- `packages/temper-placer/tests/placer/cp_sat/test_zone_pour_production_measurement.py`

**Implementation:** Read signal/plane roles from declared board data, fail
closed if that data is absent or malformed, and keep existing zone contents
from masquerading as role evidence or permanent routing obstacles. Run zone
generation only after routing/declines finish; replace input zones atomically,
fill them, and pass the filled output to DRC. Reuse existing cross-class
clearance, priority, clustering, and trace-stitch logic.

**Falsifiers:** A zero-zone and fully-zoned board must produce the same role
set; a signal layer with legacy zones must retain routing capacity; a declined
net must not receive a compensating pour; the output zone set must differ when
the input zone set is deliberately changed but routed geometry is unchanged.

**Real-board gate:** Run completion and KiCad DRC before and after the combined
change. The gate must explain any completion shortfall using P1 decline
records; an unexplained drop is a hard failure. Add a CI-enforced check rather
than relying on a reviewer remembering that U2 and U3 are coupled.

### P3 - KiCad DRC prover-soundness gate (provable-safety U4)

**Purpose:** Separate violations already inherited by the input board from
violations caused by copper emitted by this run.

**Files:**

- `packages/temper-placer/src/temper_placer/validation/_drc_api.py`
- a new emitted-copper identity/geometry attribution module
- `scripts/check_prover_soundness_gate.py`
- `scripts/manifest.yaml`
- `packages/temper-placer/tests/validation/test_drc.py`
- `packages/temper-placer/tests/router_v6/test_manufacturing_drc_integration.py`

**Implementation:** Run DRC on the exact output file after pour filling. Carry
stable item/net geometry identities from emission into the report, and use
geometric matching only where KiCad's report lacks sufficient identity. Any
violation matched to this run's track, via, or filled zone fails unconditionally
and is reported with the item and DRC rule. Inherited/placement-only defects
remain visible to, but are not absorbed by, the existing ceiling gate.

**Falsifier first:** Add a fault-injection fixture that emits a known
clearance violation and prove the new gate fails on it before trusting the
green path. Also cover zero emitted copper: the invariant passes, but the
report must say `0 nets proven`, never imply successful coverage.

### P4 - Absolute coverage ratchet (provable-safety U5)

**Purpose:** Count only nets whose emitted copper passes P3, and prevent a
better ratio from hiding a lower absolute count.

**Files:**

- a new committed coverage baseline JSON with provenance and per-domain/
  net-class breakdown
- `scripts/check_coverage_ratchet.py`
- `scripts/check_measurement_provenance.py` or its shared provenance helper
- `packages/temper-placer/tests/regression/test_coverage_ratchet.py`

**Implementation:** Consume P3's proven-net output, not raw router completion.
Print `N nets proven safe / M total nets` plus the breakdown on every run.
Reject stale board provenance and any decrease in absolute proven-net count;
allow a forward update only when the measured count increases. The coverage
key space comes from declared board data, not a hardcoded temper list.

**Falsifier:** Narrow the attempted set so the proven/attempted ratio rises
while the absolute proven count falls; the gate must fail before CI wiring.

### P5 - Campaign floor and automatic DRC ceiling tightening

**Purpose:** Give the zero-error goal an active work queue instead of only a
non-increasing ratchet.

**Files:**

- `packages/temper-placer/src/temper_placer/regression/drc_ratchet.py`
- `scripts/ci_check_drc.py` (the single campaign gate entry point)
- a committed campaign-state artifact under `power_pcb_dataset/`
- `packages/temper-placer/tests/regression/test_drc_ratchet.py`
- new campaign gate tests for active/inactive category behavior

**Implementation:** Extend `DrcRatchet` and its existing
`scripts/ci_check_drc.py` entry point to represent the active category and
declared safety order;
start with creepage, then clearance, then the remaining categories grouped by
hazard/fabrication semantics rather than raw count. During an active campaign,
the measured category must decrease to close the campaign, while inactive
categories may not increase. Any measured reduction tightens its ceiling
automatically. Any aggregate or per-type increase fails unless a human-owned
`Ceiling-Approval:` trailer is present and the increase is already attributed
to documented noise or deliberate input change. Keep warnings outside this
error campaign.

**Falsifiers:** A run that improves creepage but raises solder-mask bridges
fails; a run below the current ceiling tightens without approval; a run that
does not reduce the active category cannot close it; an unexplained raise is
reported without silently editing the ceiling.

### P6 - Single invocation and deterministic output (provable-safety U6)

**Purpose:** Make the whole flow executable and make coverage changes
trustworthy.

**Files:**

- the existing router_v6 entry point selected by tracing callers
- new full-run orchestration/report module if no suitable entry point exists
- touched net iteration and serialization paths
- a deterministic integration test under `packages/temper-placer/tests/`
- relevant CI workflow wiring, linted with `actionlint` if changed

**Implementation:** Orchestrate stackup read → route/decline → derived pour
generation → fill → DRC soundness → coverage → campaign report from one
non-interactive command. Sort all net, geometry, report, and serialization
inputs at boundaries. Run identical inputs twice and compare emitted copper,
zones, decline records, DRC attribution, and coverage output byte-for-byte.
Distinguish pipeline nondeterminism from KiCad measurement jitter; do not
average away a failure.

## Verification sequence

After each unit, run the smallest relevant tests and `ruff`/`ty` for touched
Python packages. Before declaring the feature complete, run:

1. all P1-P6 targeted tests, including every falsifier;
2. the full `packages/temper-placer` regression/core suite as appropriate;
3. the real-board two-run determinism test;
4. the 120-sample DRC measurement with provenance;
5. `uv run python scripts/import_linter_gate.py`;
6. `uv run python scripts/check_manifest_gate.py` if scripts changed;
7. `make extensions-check` if Rust sources or extension-facing code changed;
8. `SHELLCHECK_OPTS='--severity=error' actionlint ...` if workflows changed.

Do not regenerate firmware artifacts unless a firmware manifest is changed.
Do not run the board re-measurement in parallel with a board-changing edit;
the measured hash must be the final reviewed board input.

## Commit boundaries

Use separate, reviewable commits for P1, the coupled P2 change, P3, P4/P5,
and P6. Keep measurement/evidence and any `drc_ceiling.json` update in the
same board-change commit that caused the measurement to move. Never create a
`Ceiling-Approval:` trailer on the agent's own authority; pause and report if
one is required. Do not use `git stash`.

## Definition of done

- Every declined net has a structured reason.
- Stackup roles are declared, not inferred from zones; regenerated zones are
  filled, replaced atomically, and graded as emitted copper.
- A fault-injected emitted violation fails the prover-soundness gate.
- Coverage reports absolute proven/total counts and cannot regress through
  denominator narrowing.
- The active campaign requires category progress, while inactive categories
  and per-type ceilings cannot increase silently.
- Two identical full runs produce identical output.
- The corrected-board DRC baseline is measured once, with complete provenance
  and per-type attribution, after all moving prerequisites land.
- Required tests and import/manifest/workflow gates pass.
