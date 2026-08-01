---
title: Fix PR #513 red checks and attempt the board-clearance solve
type: fix
status: active
date: 2026-07-31
topic: pr513-red-checks-and-board-debt
artifact_contract: ce-unified-plan/v1
artifact_readiness: planned
product_contract_source: ce-brainstorm
execution: code
---

# Fix PR #513 red checks and attempt the board-clearance solve

## Landing Status

Authored on branch `codex/repair-generated-plan-index` (PR #513), tip
`f350f4daa`, base `origin/main` `4a387393e` merged in. This plan records the
re-derivation of PR #513's failing checks (fresh `gh pr checks 513` on
2026-07-31) and the board-debt solve attempt assigned to this session.

## Goal Capsule

- **Objective 1:** Every failing check on PR #513 is GREEN or has a
  documented, evidenced, issue-tracked reason.
- **Objective 2:** Genuinely attempt the #504 fix ("add a minimum-displacement
  or route-aware placement/re-routing loop") with the existing placer
  machinery and report whether a solve/reroute path can produce a board
  meeting REQ-SAFE-01 without breaking the netlist/board gates.
- **Product authority:** This artifact owns the triage of the red checks and
  the evidence for the board-solve attempt. It does not own the placer
  capabilities themselves.

## Red-check triage (re-derived 2026-07-31, run 30645106963)

Three failing jobs:

### 1. Requirements Tests (safety / EMC / review / DFM) — REQ-SAFE-01

Root cause: repo-wide board clearance debt. `test_temper_board_clearance_compliance`
reports **123 REQ-SAFE-01 violations across 86 pairs** (11 intra-footprint
records, unfixable by any placement) plus **6 unclassified components within
12.6mm of a declared-HV part**. Requirement level enforced at branch HEAD is
12.6mm reinforced creepage (PD3; the PD2/8.0mm exception is not earned until
the enclosure prerequisite is verified — `clearance.py` module comment, #506).

Options considered:

- **Full CP-SAT re-solve** — proven to clear placement-fixable pairs
  (`docs/evidence/2026-07-30-copper-aware-domain-resolve.md`: 76 → 11 at
  8.0mm, all 5 remaining pairs are intra-footprint isolators; #460 re-solve
  98 → 28), but the resulting full-board reshuffle (median displacement
  ~100mm) reproducibly increases `shorting_items` (+30-44) and
  `unconnected_items` (+30) when written to the fully-routed board
  (`write_placements_to_pcb` moves footprints without re-routing). **Not a
  clean landing as-is.**
- **Minimal-disruption variant (pin non-violating components, free only the
  violating neighborhood)** — identified as "the natural next step" in the
  2026-07-30 evidence doc, never attempted (encoder has no exposed
  fix-refs/free-refs API). **This session attempts it.**
- **Document-only** — the check stays red with an issue-tracked reason
  (#504, #517, #518).

**Decision:** attempt the minimal-disruption solve. Success criteria: every
placement-fixable pair cleared AND DRC (shorting/unconnected) not regressing
beyond measurement noise. Even on success, the Requirements Tests job CANNOT
go fully green at 12.6mm because the 11 intra-footprint isolator records
(`C6, K1, K2, K3, T1, U3, U7` family) are structurally unfixable by placement
(part/footprint changes are the remedy — handoff doc Phase 2). The
intra-footprint floor is therefore an **issue-tracked, documented reason** the
check stays red, exactly as #504/#517 already state.

### 2. Board & Netlist Gates — three sub-failures

| Step | Failure | Root cause | Action |
|---|---|---|---|
| Board-copper / netlist consistency gate | exit 5 "netlist is STALE" | CI netlist-cache mtime artifact: cache restores `elec/build` with original mtimes; freshly-checked-out `elec/src/*.ato` look newer. Content is hash-verified identical (cache key covers all inputs). **Passes locally** after `make netlist` (0 violations, 2482 copper items checked). | Workflow: touch the restored netlist on cache hit (content proven identical by cache key). |
| Footprint-drift gate | exit 5 same "netlist is STALE" | Same artifact. **Passes locally** (169/169 matched). | Same fix. |
| Physical mains<->SELV isolation-barrier gate | missing `MAINS_SELV_ISOLATION_BARRIER` keepout | #518 — the keepout cannot be drawn onto the interleaved board (cuts pads; far-side crossings). Needs domain-first floorplan + boundary-part BOM (handoff doc). | Issue-tracked (#518). Stays red with documented reason. Do NOT fake a zone. |

(Note: "Regenerate schematics and check drift" prints CHECK FAIL 7/7 in its
log but is `continue-on-error: true` with a TODO ticket — soft gate, not a
job failure. Optionally regenerate schematics if time permits, but it is not
a red check.)

### 3. Provenance & Anti-Vacuity Gates — Evidence provenance gate

7 `docs/evidence/` files cite commits that are unreachable from `origin/main`
(pre-squash/rebased branch commits; `git cat-file` resolves them locally only
because other refs still hold the objects — CI fetch cannot resolve them).
Gate convention (module docstring): cite a commit that persists — the merge
commit into main. Verified: all 7 files are **byte-identical** at reachable
main commits (`57f0c7550`, `0a8e7194f`, `bb7592755`).

**Action:** update the 7 `commit=` provenance fields to the reachable merge
commits, keeping `dirty=false`. This is the gate's own documented remedy and
is not an allowlist entry (no monotonic-shrink impact).

## Execution order

1. Fix 7 evidence-file provenance fields → re-run
   `scripts/check_evidence_provenance.py` (GREEN).
2. Fix Board-gates workflow netlist-cache mtime artifact (`touch` on cache
   hit) → re-run both gates locally; actionlint the workflow.
3. Attempt the minimal-disruption CP-SAT solve (scratch driver, pinned
   non-violating refs, full 11,856-constraint classified-domain set +
   keep-away group) at 8.0mm and 12.6mm margins; measure REQ-SAFE-01 and DRC
   (shorting/unconnected) before/after. Report findings as an evidence doc —
   commit a new board ONLY if DRC is flat and violations drop materially
   (then follow the AGENTS.md DRC-ceiling protocol exactly).
4. Push; `gh pr checks 513`; report per-check status + commit SHAs
   (board commit + `drc_ceiling.json` commit are the sibling cherry-pick
   targets if a board lands).

## Success / stop criteria

- Provenance gate GREEN.
- Copper-net + footprint-drift gates GREEN (via workflow fix).
- Isolation-barrier gate: red, reason = #518 (documented).
- Requirements Tests: attempt the solve; the intra-footprint floor is a
  documented, issue-tracked reason the job cannot be green at 12.6mm without
  part changes. Do NOT fake convergence; do NOT weaken or skip any safety
  gate.

## Rollback

- Workflow fix: revert the touch step (self-contained, one job).
- Provenance edits: revert 7 frontmatter lines (no content change).
- Board: the solve is scratch-first; nothing is written to
  `pcb/temper.kicad_pcb` unless DRC is flat. Board + `drc_ceiling.json`
  land as a single commit pair per AGENTS.md.
