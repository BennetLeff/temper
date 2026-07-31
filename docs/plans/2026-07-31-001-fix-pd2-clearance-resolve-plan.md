---
title: "fix: Resolve REQ-SAFE-01 clearance debt at PD2/8.0mm via placement re-solve (#517)"
type: fix
status: active
date: 2026-07-31
topic: pd2-clearance-resolve
origin: https://github.com/BennetLeff/temper/issues/517
---

# Resolve REQ-SAFE-01 clearance debt at PD2/8.0mm (#517)

## Phase 0 — ce-brainstorm (scope, options, risks)

**Scope.** Issue #517: even at the selected PD2/8.0mm architecture, the routed board
`pcb/temper.kicad_pcb` reports **53 REQ-SAFE-01 violations across 25 pairs** (copper-to-copper,
measured by the validator on the branch tip, which carries PR #515's PD2 matrix). This plan's
scope is: reduce violations to the *provable minimum* by placement re-solve, commit the solved
board, and execute the AGENTS.md DRC-ceiling re-measurement protocol (120 `run_drc()` samples,
every per-type delta attributed, `Ceiling-Approval:` trailer iff any ceiling rises).

**Measured pair classification (fresh baseline, this branch, 2026-07-31):**
- 23 inter-component pairs — **fixable by placement** (subject of the solve).
- 2 intra-footprint pairs (`K2`, `K3`; discharge relays, HV contact ↔ SELV coil at 3.559mm) —
  **provably unfixable by placement**: they fail even the pollution-degree-independent 6.0mm
  clearance minimum; no translation/rotation of the part can separate its own pads. `K2`/`K3`
  need a different footprint/part (documented in #515, #518 blocker comment). They also mean
  **0 total violations is NOT reachable** by this workstream; the achievable floor is 6 records
  over the 2 intra pairs.

**Options considered.**
1. **Full-constraint-set CP-SAT re-solve at 8.0mm (selected).** Precedent:
   `docs/evidence/2026-07-30-copper-aware-domain-resolve.md` — 11,856 constraints, status
   `optimal`, all 21 placement-fixable pairs cleared (76 → 11), R24 audit 0 mismatches. This
   is the machinery the orchestrator directs us to use: the sibling #504 branch
   (`fix/clearance-resolve-reroute-loop`) is **empty** (tip == origin/main, verified
   2026-07-31), so no minimum-displacement/route-aware loop exists to consume.
2. **Minimal-displacement solve.** Requires new encoder machinery ("fix these refs, free
   those" API does not exist today, per the 2026-07-30 evidence doc Sec 4). Owned by the
   sibling #504 workstream; not built here to avoid duplicating/conflicting with it.
3. **Document-only (no board change).** Rejected: 23 of 25 pairs ARE placement-fixable; the
   mission is to determine and land the best achievable board.

**Risks / unknowns.**
- **Routing regression (known).** The free re-solve reshuffles ~all 168 components (median
  displacement ~100mm on the 2026-07-30 measurement) on a *routed* board (2338 segments /
  48 vias / 96 zones). Precedent measured +30..44 `shorting_items` and deterministic +30
  `unconnected_items`. Orchestrator policy: regression-Check failures are ignored — report,
  don't block. This plan's ceiling protocol will re-measure the candidate with the real
  `run_drc()` path (zone-fill + `--all-track-errors`), attribute every delta, and use the
  `Ceiling-Approval:` trailer for any rise. `unconnected_items` is NOT a category in
  `drc_ceiling.json` (kicad-cli `--all-track-errors` error categories are the 12 recorded
  types), so it cannot move the ceiling — but it will be reported in the PR.
- **Convergence.** 8.0mm solve is proven feasible (`optimal`) on a slightly older board
  snapshot (66ae51fc). Board file is byte-identical to origin/main
  (e2fb9237…, verified); the only change since 66ae51fc is #472 (C25/C26 move), which the
  evidence doc's solve already handled. If the current board does NOT converge within the
  180s timeout / timebox, stop and report (issue comments) per dispatch.
- **C27 (tank.c_tank3).** Staged OUTSIDE the board outline at (20, 272.75) — a documented
  human placement decision (safety-closure evidence). C27's nets (SW_NODE, tank.c_tank1-p2)
  are HV-classified, so constraints WOULD involve it if included. **Decision: exclude C27
  from the model + constraints + write** so the solve cannot move it (respects the human
  decision; C27 is in none of the 25 violating pairs, so nothing is left unfixed).
- **Ceiling movement.** The committed ceiling (875 errors / 680 warnings, provenance fresh
  against the current board hash) will move because the placement changes. Attribution is
  mechanical (placement-only delta, no netlist/footprint change, no elec change); every
  per-type delta must be tied to the re-solve before the file is committed.

## Phase 1 — ce-doc-review (findings that shaped this plan)

- `docs/evidence/2026-07-27-clearance-resolve-full-coverage.md` — prior full re-solve (17 → 0
  under the old origin-to-origin checker on an UNROUTED board; 11,725-12,409 constraints;
  keep-away constraint group for unclassified-near-HV; origin-offset write workaround).
- `docs/evidence/2026-07-28-clearance-copper-to-copper.md` — validator now measures exact
  pad copper (Minkowski formulation); origin-to-origin was optimistic by up to 8.4mm.
- `docs/evidence/2026-07-30-copper-aware-domain-resolve.md` — the 8.0mm full-set solve:
  76 → 11 (only Group B intra isolators left); audited 0 mismatches; routing regression
  quantified (+30 shorting, +30 unconnected); scoping to only the violating pairs REGRESSES
  (76 → 217) — the full classified-domain set is mandatory.
- `docs/evidence/2026-07-30-safety-closure-evidence.md` — C27 staging decision; DRC status
  (ceiling fresh at 875/680); 123-violation PD3 baseline.
- Issue #518 comment 5145503141 — barrier-constrained solve provably INFEASIBLE with
  current isolator footprints (7 of 8 can't straddle an 8mm corridor; K2/K3 −0.5mm even at
  1.0mm). **Does not block this plan**: #517's target is pad-pair clearance, not the barrier.
  It confirms K2/K3 (and the barrier itself) need footprint sourcing, tracked in #518.
- Issue #504 — sibling's required approach (min-displacement/route-aware loop); its branch
  has no commits beyond main → use the existing copper-aware solve per dispatch.

## Phase 2 — execution plan (ce-work)

Run steps (all in worktree `w-517`, branch `fix/board-clearance-resolve-pd2`, tip 10f3e20df,
verified clean; `make netlist` already run — digest 736b01f0e07e…):

1. **Baseline** (done): `test_temper_board_clearance_compliance` → 53 violations / 25 pairs,
   components matched 159. Record baseline `run_drc()` for provenance context.
2. **Solve** (scratch driver, not committed): fixture `load_real_board_placement()` (full
   manifest classification) → `generate_domain_clearance_constraints(placement,
   voltage_domains, component_refs=<all refs minus C27>)` → `solve_placement(netlist=<PCB
   parse minus C27>, board=<PCB parse>, extra_constraints=<full set>, timeout_ms=180000,
   seed=0, hint_positions=<current local positions>)`. Write candidate via
   `write_placements_to_pcb` with `board.origin` added and `components=` set (bbox-center →
   footprint-origin conversion). Candidate → scratch path, never `pcb/` until verified.
3. **Verify candidate** (the gate is the oracle): copy candidate over `pcb/temper.kicad_pcb`
   in the worktree, run the real pytest test, restore immediately. Success criterion:
   violations drop to **6 records / 2 pairs (K2, K3 intra only)** — the provable floor — with
   no new pairs, no unclassified-proximity findings, coverage unchanged (~159 matched).
   Also verify: netlist gates (`make netlist` unchanged — no elec change; netlist/PCB
   ref-designator identity: footprint refs and net assignments byte-identical, verified via
   `git diff --stat pcb/` post-write showing only position/rotation lines changed).
   R24 audit: `audit_domain_clearance` over the full constraint set → 0 mismatches.
4. **Commit the board** if and only if the candidate meets the success criterion (or is a
   strict improvement with no new violation categories).
5. **DRC ceiling protocol** (AGENTS.md, binding): read `_march` log (done — 9 prior entries);
   re-measure the committed board with 120 runs of
   `temper_placer.validation._drc_api.run_drc` (PYTHONPATH set per AGENTS.md, kicad-cli
   10.0.4, `--all-track-errors`); record observed per-category ranges; update
   `violations_by_type`/`warnings_by_type` + `provenance` (commit, branch, dirty, input
   hash, tool version); append `_march` entry attributing EVERY delta to the re-solve;
   `Ceiling-Approval:` trailer on the ceiling commit iff any per-type or aggregate ceiling
   rises (expected: `shorting_items` and likely `clearance`/`copper_edge_clearance` — all
   attributable to placement-without-reroute). If any rise cannot be attributed, STOP and
   report instead of ratcheting.
6. **Router pipeline**: attempt if feasible within timebox; regression-Check failures are
   reported, not blocking.
7. **Push + PR** referencing #517; `gh pr checks --watch` (cap ~40 min) and report.

**Timebox:** solve ≤ 3 attempts × 180s; ceiling measurement ~30-40 min (120 runs);
total session budget ~2-3 h.

**Success criteria:** (a) candidate board = 6 violations / 2 intra pairs (provable floor),
no new pairs/categories; (b) netlist semantics unchanged; (c) R24 audit 0 mismatches;
(d) ceiling re-measured, every delta attributed, trailer iff rise; (e) branch pushed, PR
open referencing #517.

**Rollback:** `git revert` of the board commit restores the previous board; the ceiling
commit is separate and revertible independently. Prior board content hash
e2fb9237… is recorded in `drc_ceiling.json` provenance.

## Phase 3 — ce-code-review

Adversarial review of: (1) the driver's origin/offset + bbox-center math (error here
silently rotates/scatters every footprint — checked against the 2026-07-27 doc's known-good
write path), (2) every `drc_ceiling.json` delta attribution, (3) nets preserved (identity
gate), (4) test genuinely failing at 6/2, not skipped/weakened. Spawn reviewers via
subagent tool; else self-review per this checklist.
