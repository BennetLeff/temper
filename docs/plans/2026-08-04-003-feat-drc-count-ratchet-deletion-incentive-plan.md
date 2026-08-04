---
title: The DRC Count Ratchet Rewards Deleting Components - Decision Plan
type: feat
date: 2026-08-04
topic: drc-count-ratchet-deletion-incentive
artifact_contract: ce-unified-plan/v1
artifact_readiness: requirements-only
product_contract_source: ce-brainstorm
execution: code
origin: docs/evidence/2026-08-04-board-defect-corpus-uncovered-classes.md (PR #689)
---

# The DRC Count Ratchet Rewards Deleting Components - Decision Plan

## Goal Capsule

- **Objective:** Decide how the project should respond to a structural property of `power_pcb_dataset/drc_ceiling.json`: because it caps *counts* of DRC errors, removing a component from the board scores as an improvement. PR #689 observed this in passing while closing the `off-board` corpus class. This document re-derives the observation, measures how far it reaches, enumerates what actually guards against it, weighs the options, and recommends one. It changes no gate, no threshold and no ceiling.
- **Headline finding:** The premise holds exactly, and it is larger and better-guarded than #689's note implies. Re-measured at N=11, moving C26 off the board is **−9 errors**, and *deleting C26 outright produces the identical per-category delta* — at the ratchet's resolution the two mutations are the same event. The exposure is not 9: the single most profitable deletion on this board is **−46 errors** (C4), the five most profitable together are **−147** (11.6% of the 1263-error board), and **625 of 1263 clean errors (49.5%) name at least one footprint**. But the class is already detected, three times over, by landed and currently-green gates (`check_footprint_drift.py`, `check_netlist_board_reconciliation.py`, `check_measurement_provenance.py`) — all of which live in `Board, Provenance & Requirements Gates`, which is **not a required context** and is red on `main`. Two corrections to the framing that motivated this work: #689's own containment gate is **blind to deletion** (it iterates the footprints that are present, so a deleted one is simply not checked), and errors-per-component normalisation **does not remove the incentive** (deleting C4 improves errors/component from 7.47 to 7.24).
- **Scope:** Analysis, options and a recommendation. `pcb/temper.kicad_pcb` and `power_pcb_dataset/drc_ceiling.json` were read-only throughout; every measurement was taken on run-time copies under a scratch directory. No `Ceiling-Approval:` trailer is authored by this work. Nothing here is implemented.
- **Product authority:** temper board maintainer.
- **Open blockers:** The recommended sequence cannot start until the two currently-failing steps in `Board, Provenance & Requirements Gates` are fixed; a red job cannot be promoted to required.

---

## Product Contract

### Summary

Counting errors is a measure of board health that a deletion improves. That is not a defect in `drc_ceiling.json`; it is a property of the measure. The question this document answers is not "is the ratchet wrong" — it is "given that the measure has this property, where is the compensating invariant, and is it in a place that can stop anything." The answer is that the compensating invariants already exist and already pass, and the entire gap is CI policy: they sit in a job no PR is blocked by. The recommendation is therefore to keep the count ratchet and close the policy gap, not to redesign the measurement.

### Problem Frame

`power_pcb_dataset/drc_ceiling.json` caps each DRC violation category and requires a `Ceiling-Approval:` commit trailer to raise any of them (`_goal`, and `DrcRatchet.detect_ceiling_raise`). The rule is one-sided by construction: a *fall* needs no approval, no attribution and no evidence. Removing a component removes its copper from the layout, so every collision that copper participated in disappears, so counts fall. The ratchet reads that as progress.

Three things make this more than a curiosity in this repository:

1. **The board is measured, not derived.** Every recent change to `pcb/temper.kicad_pcb` is a scoped CP-SAT placement solve written by hand after candidate selection (`docs/plans/2026-08-04-001-feat-board-regeneration-proposal.md` §1). A solve that drops a component from its output is a plausible failure mode of exactly the automation the project is planning.
2. **The approval hook never fires on this class.** `check_drc_ceiling_approval.py` only reacts to increases. A PR that deletes a component, re-measures, and commits a *lower* ceiling requires no trailer at all — so the one place a human is forced to look is bypassed by construction, not by evading a check.
3. **Nothing required notices.** `.github/required-checks.json` lists ten required contexts. None of them compares the board's footprint inventory against the compiled netlist. The gates that do are in a job the manifest deliberately leaves unrequired.

### Key Decisions

- **D1. The count ratchet stays; the compensating invariant is what moves.** (Chosen over changing the unit of measurement: §5 Option C shows per-component normalisation does not remove the incentive, and it would rebase every recorded baseline, every `_march` entry and every evidence doc that cites an absolute count.) Governs R1, R2.
- **D2. The invariant that covers this class is an *inventory* invariant, not a positional one.** (Chosen over generalising #689's containment gate: §3 shows that gate iterates the footprints present on the board and therefore cannot see a footprint that is gone. Two landed gates already implement the inventory check; a third positional gate would not.) Governs R2, R3.
- **D3. Promotion, not construction, is the work.** (Chosen over building a new gate: `check_footprint_drift.py`, `check_netlist_board_reconciliation.py` and `check_measurement_provenance.py` each detect this class today, are unit-tested for it, and are green on `main`. A fourth checker with the same logic is the vacuous-gate class `scripts/check_vacuous_gates.py` exists to catch.) Governs R3, R4.
- **D4. Promotion must be capacity-honest.** (Chosen over making `Board, Provenance & Requirements Gates` required as it stands: that job has a 40-minute budget and builds three Rust crates plus the netlist before any gate runs, and `.github/required-checks.json`'s own `_required_contexts_note` records eight contexts being *removed* on 2026-08-03 because CI is capacity-bound at ~24 concurrent jobs against ~40 requested per push.) Governs R4, R5.

### Requirements

- **R1. The DRC ceiling remains a count ratchet.** Absolute per-category counts stay the unit; no normalisation, no rebasing of recorded baselines.
  - Success signal: `violations_by_type` keeps its current semantics and every historical `_march` entry stays directly comparable.
- **R2. A fall in any per-category count is covered by an inventory invariant that is a required context.** The board's footprint inventory, keyed by instance path against the compiled netlist, must be checked by a gate that can block a merge.
  - Success signal: a PR that deletes one footprint from `pcb/temper.kicad_pcb` turns a *required* check red, with a finding naming that component.
- **R3. The inventory invariant is one of the gates that already implements it.** No new checker is written for a class three landed gates already cover.
  - Success signal: the required check runs `check_footprint_drift.py` and `check_netlist_board_reconciliation.py` unchanged.
- **R4. Promotion costs at most one additional required runner slot, and that slot does not build the Rust crates.** The inventory gates need the compiled netlist and Python; they do not need `temper-rust-router`, `temper-drc-rs` or `temper-constraints`.
  - Success signal: the new required context's median wall time is measured, and is a small fraction of `Board, Provenance & Requirements Gates`'s current budget.
- **R5. `Board, Provenance & Requirements Gates` is green before anything is promoted out of it.** Its two failing steps (`Evidence provenance gate (docs/evidence/)`, `Physical mains<->SELV isolation-barrier gate`) are fixed first.
  - Success signal: the job passes on `main` at the commit promotion lands on.
- **R6. A ceiling *decrease* carries an attributed cause, on the same contract a raise will carry under R27.** The `_march` log already does this by convention; the contract makes it checked.
  - Success signal: a PR that lowers a per-category ceiling without naming a cause fails the approval gate, symmetrically with `docs/plans/2026-08-02-023-feat-drc-ceiling-monotone-contract-plan.md`'s treatment of raises.

### Acceptance Examples

- **AE1. Covers R2, R3.** A PR deletes one footprint and commits a re-measured, lower ceiling. Every count falls, `ci_check_drc.py` passes, `detect_ceiling_raise` sees only decreases so no trailer is required, and `check_measurement_provenance.py` is satisfied by the fresh input hash. The PR is still blocked, by a required context naming the missing component. *Today every clause of this example except the last one is true, and the last one is false.*
- **AE2. Covers R1, R6.** A genuine fix lowers `hole_clearance` by 3. The PR is not blocked; it names the cause in the ceiling's `_march` entry, and the required inventory check confirms the component inventory is unchanged. The distinction between this and AE1 is made by the inventory, not by the size or sign of the delta.
- **AE3. Covers R4, R5.** Promotion adds one required context. Its measured wall time is reported in the same PR that registers it, and the aggregate number of required contexts does not grow by more than one.
- **AE4. Covers R2.** A placement solve silently drops a component from its output and the resulting board is committed. The count ratchet reports an improvement. The inventory check reports the component missing. The improvement does not land.

### Scope Boundaries

- Implementing any of this. The decision is the maintainer's and this document stops at a recommendation.
- Changing `power_pcb_dataset/drc_ceiling.json`, `pcb/temper.kicad_pcb`, any gate, any threshold, or any CI workflow.
- The `Ceiling-Approval:` trailer's *content* contract for raises. That is R27 (`docs/plans/2026-08-02-023-...md`) and is unbuilt; R6 above extends it to falls but does not replace it.
- Warnings. `warnings_by_type` has the same structural property and is not analysed here.

### Dependencies / Assumptions

- Measurements below were taken with `kicad-cli 10.0.4` on darwin. CI runs 10.0.5 and the two disagree on geometric counts, so **no absolute number here may be compared against a CI-recorded figure**. Every claim is a clean-vs-mutated comparison within one environment — the same comparison the ratchet makes.
- The compiled netlist used to count components (168) was the one present in the working checkout, dated before `origin/main`'s tip. It is used only for the `min_overlap` arithmetic in §3, where a ±few-component error does not change the conclusion.
- `check_footprint_drift.py` and `check_netlist_board_reconciliation.py` detect a deleted footprint. This is asserted from their documented finding classes (`MISSING-FROM-BOARD`, `MISSING`) and from their landed unit tests (`test_component_missing_from_board`, `test_gate_exits_three_on_missing_component`), which pass in CI. It was **not** re-executed here: both gates refuse to run against a netlist they consider stale (exit 5, fail-closed), and rebuilding the netlist would have mutated a checkout other sessions were building in.

### Outstanding Questions

- **Q1.** Should the promoted required context be a new small job, or should the three inventory gates move into an existing required job (`Cross-Source Consistency Gates` already triggers on `pcb/**` and already builds the netlist)? The second is cheaper in slots and is probably the right answer, but it widens that job's failure surface.
- **Q2.** R6 (attributed falls) is a review hook, not a mechanical check — "cause: removed unused C4" is as free-text as `Ceiling-Approval:` is today. Is it worth the friction it adds to the thing the project wants to encourage, given that R2 already blocks the class mechanically?
- **Q3.** `check_board_containment.py` already parses the whole board and reports `footprints_checked`. Asserting that number against the netlist's component count would make #689's gate cover the class it was built for, at the cost of coupling a geometry gate to the netlist. Worth it, or does it duplicate R3?

---

## 1. Verifying the premise — re-derived, not inherited

**Environment.** `origin/main` at `f2b09d846`; board `pcb/temper.kicad_pcb` sha256 `51e39844…` (the exact board #689 measured and the exact board `drc_ceiling.json` records); `kicad-cli 10.0.4`; `temper.kicad_dru` regenerated from `scripts/generate_kicad_dru.py`. The committed board was copied out of `origin/main` once and every mutation applied to a copy.

**A configuration correction, found while reproducing.** #689 measured 842 clean errors. That figure is reproducible exactly — but it is not the ratchet's measurement. Placing only the regenerated `.kicad_dru` beside the board omits `pcb/temper.kicad_pro`, and with it the project's netclass constraints and rule-severity map. Four categories the ceiling records then never appear at all (`track_width` 199, `creepage` 188, `annular_width` 4, `hole_to_hole` 3), and `pth_inside_courtyard` is reported as an error rather than the warning the project file declares. Adding `temper.kicad_pro` beside each board copy reproduces the ceiling's own record, including its documented nondeterminism bands:

| category | ceiling | this measurement, N=11 |
|---|---:|---|
| `clearance` | 379 | 378 (378–378) — ceiling notes observed `[377, 378]` |
| `creepage` | 188 | 186 (186–187) — ceiling notes observed `[185, 186, 187]` |
| `shorting_items` | 201 | 199 (199–199) — ceiling notes observed `[199, 200]` |
| `hole_clearance` | 105 | 105 (105–105) |
| `solder_mask_bridge` | 154 | 154 (154–154) |
| `track_width` | 199 | 199 (199–199) |
| **total** | 1267 | **1262 (1262–1263)** |

Both configurations are reported below. The premise holds identically in both, so the correction does not affect #689's conclusion — but every number in this document is taken in the ratchet's configuration, not the 842-error one.

**The result.** N=11 per board, medians with (min–max):

| category | clean | C26 moved off-board | C26 **deleted** |
|---|---|---|---|
| `hole_clearance` | 105 (105–105) | 102 (102–102) | 102 (102–102) |
| `shorting_items` | 199 (199–199) | 197 (197–197) | 197 (197–197) |
| `solder_mask_bridge` | 154 (154–154) | 151 (151–151) | 151 (151–151) |
| `clearance` | 378 (378–378) | 377 (377–377) | 377 (377–377) |
| **total** | **1262 (1262–1263)** | **1253 (1252–1254)** | **1253 (1252–1254)** |
| **delta** | — | **−9** | **−9** |

**Verdict: the premise holds, exactly.** Moving a component off the board improves DRC by 9 errors. Every contributing category has zero run-to-run variance across 11 runs; the ±1 band on the total is `creepage` noise unrelated to the mutation. #689 attributed the 9 as `hole_clearance` −3, `shorting_items` −3, `solder_mask_bridge` −3; the attribution measured here is −3/−2/−3 plus `clearance` −1, which is the same 9 split one error differently because `shorting_items` sat at 200 rather than 199 in #689's sample. The total is the robust figure and it reproduces to the error.

**And the premise is understated in one respect that matters.** Deleting C26 outright and moving C26 off the board produce **byte-identical DRC signatures** — the same total, the same categories, the same magnitudes, in both measurement configurations. #689 framed the finding as "no count-delta can detect the `off-board` class." The stronger and more consequential statement is that **at the ratchet's resolution, off-board and deleted are the same event**. That is why the containment gate #689 built does not close this: it distinguishes them by geometry, which the ratchet cannot see, and it can only do so while the component is still on the board to be looked at.

## 2. How much of the ceiling deletion can reach

**A model, then its validation.** For each footprint, count the clean-board DRC errors whose item descriptions name it. An error naming two refs is credited to both, because deleting either removes it. Measured against real deletions (N=11), the model is close to exact:

| deleted | modelled credit | measured total delta |
|---|---:|---:|
| C4 | 46 | **−46** |
| U27 | 29 | −29 |
| R30 | 25 | −25 |
| U7 | 26 | −22 |

**The single most profitable deletion on this board is C4 at −46 errors** — five times the C26 figure that prompted this work, and 3.6% of the whole 1263-error board. Deleting the five highest-credit components together (`C4`, `U27`, `U7`, `R30`, `U9`) measures **−147**, 11.6% of the board: `shorting_items` −40, `solder_mask_bridge` −41, `hole_clearance` −23, `creepage` −21, `clearance` −17, `courtyards_overlap` −3, `hole_to_hole` −2.

**Which categories are reachable.** For each category, how many of its clean errors name at least one footprint (N=3, clean board):

| category | clean errors | name ≥1 footprint | share | name ≥2 |
|---|---:|---:|---:|---:|
| `solder_mask_bridge` | 154 | 154 | **100%** | 0 |
| `courtyards_overlap` | 11 | 11 | **100%** | 11 |
| `creepage` | 187 | 157 | 84% | 17 |
| `shorting_items` | 199 | 154 | 77% | 0 |
| `hole_to_hole` | 3 | 2 | 67% | 0 |
| `hole_clearance` | 105 | 52 | 50% | 0 |
| `clearance` | 378 | 95 | 25% | 7 |
| `track_width` | 199 | 0 | 0% | 0 |
| `copper_edge_clearance` | 12 | 0 | 0% | 0 |
| `annular_width` | 4 | 0 | 0% | 0 |
| `drill_out_of_range` | 4 | 0 | 0% | 0 |
| `via_diameter` | 4 | 0 | 0% | 0 |
| `tracks_crossing` | 3 | 0 | 0% | 0 |
| **total** | **1263** | **625** | **49.5%** | 35 |

**Half the recorded ceiling sits in errors that name a component and vanish with it.** Two corrections to the intuition this document was commissioned with:

- `courtyards_overlap` is **not** a positional category that resists deletion — it is 100% reachable, and it is the only category where *every* error names two footprints, so it is reachable from either side. It is per-component-pair geometry, which deletion is the most effective possible way to remove.
- `unconnected_items` is not in `violations_by_type` at all, so the "genuinely connectivity-based" half of the intuition has no representation in this ceiling. The categories that genuinely resist deletion are the ones that are properties of *tracks and vias* rather than of component copper: `track_width` (199), `copper_edge_clearance` (12), `annular_width`, `drill_out_of_range`, `via_diameter`, `tracks_crossing` — 226 errors, 17.9% of the board.

The 49.5% is a **lower** bound on reach, not an upper one. Deleting components whose modelled credit is zero still measured −1 or −2, because an error can involve a footprint's copper without naming its designator in the description.

**Is deletion always rewarded?** Sampling 14 components spanning the full credit range (46 down to 0) at N=3, every one produced a negative total delta. An exhaustive single-deletion sweep over all 169 footprints (N=3) separates signal from noise: for high-credit components the reward is large and far outside any noise floor, while for zero- and low-credit components the delta is ±1–2 in either direction — inside `creepage`'s own ±2 run-to-run variance on a byte-identical board, so those cases are **not** resolvable at this sample size and no claim is made about them. The defensible statement is narrower than "always rewarded" and is sufficient for the decision: **every component whose deletion is worth anything is rewarded, by a margin far outside the measurement's noise, and no component was observed to be penalised by more than noise.**

## 3. What actually guards against this today

Enumerated honestly, including the ones that do not help:

| mechanism | catches a deleted footprint? | job | required? | green on `main`? |
|---|---|---|---|---|
| `check_footprint_drift.py` | **Yes** — `MISSING-FROM-BOARD`, keyed by sheetpath | Board, Provenance & Requirements Gates | **no** | step green, job red |
| `check_netlist_board_reconciliation.py` | **Yes** — `MISSING`, keyed by instance path | same | **no** | step green, job red |
| `check_measurement_provenance.py` | **Yes, indirectly** — any board byte change invalidates `drc_ceiling.json`'s recorded input sha256 | same | **no** | step green, job red |
| `check_copper_net_consistency.py` | Partially — designator/net drift, not an inventory count | same | **no** | step green, job red |
| `check_board_containment.py` (#689) | **No** — see below | same | **no** | step green, job red |
| `preflight_identity` (`ci_identity_check.py`) | **No, for ≤8 deletions** — see below | same | **no** | step green, job red |
| `ci_check_drc.py` (the ratchet itself) | **No** — a fall always passes | `regression` | **no** | — |
| `check_drc_ceiling_approval.py` | **No** — `detect_ceiling_raise` reacts only to increases | Board gates | **no** | step green, job red |
| golden corpus (`golden-check.yml`) | **No** — the production board has no baseline; missing baselines are `SKIP`, not `FAIL` | `golden-check` | **no** | — |

Three of these deserve their own paragraph.

**#689's containment gate is blind to deletion.** `analyze_board` in `scripts/check_board_containment.py` opens with `for footprint in board.footprints:` — a footprint that has been deleted is not in that iteration and is not checked. The gate reports `footprints_checked`, but nothing asserts that number against anything; on a board with C4 removed it would report 168 footprints checked, zero violations, exit 0. This is the most important correction in this document, because "generalise the #689 pattern" was the leading candidate going in. #689 built a *geometry* invariant over the components that are present. The class in question is the disappearance of a component. A positional invariant cannot express it; only an inventory invariant can.

**`preflight_identity` has an eight-component budget.** `packages/temper-design-bundle/src/identity.rs` computes `|board ∩ netlist| / |netlist|` and fails below `min_overlap = 0.95`. With 168 netlist components, 160 must remain, so **up to 8 footprints can be deleted before board identity objects at all**. It is a wholesale-swap detector, not an inventory check, and its own callers document it as such.

**The one hook that forces a human to look never fires on this class.** `detect_ceiling_raise` returns a failure only when a number goes *up*. A deletion makes every affected number go *down*. So the exploit path is green end to end, and not by evading anything:

> Delete C4 → every per-category count falls → `ci_check_drc.py` passes (counts are under their ceilings) → re-measure and commit the lower ceiling → `detect_ceiling_raise` sees only decreases, so **no `Ceiling-Approval:` trailer is required** → `check_measurement_provenance.py` is satisfied because the committed ceiling's input hash matches the new board → the board's DRC number is 46 lower and the ratchet has recorded it as progress.

The unchecked-free-text weakness of the `Ceiling-Approval:` trailer that `docs/plans/2026-08-04-001-...md` §3 calls "the sharpest identified risk" is, for this class, **irrelevant** — and that is worse, not better. An automated writer does not need to forge a plausible trailer to lower a ceiling. It needs no trailer.

**What is required, and what it checks.** `.github/required-checks.json` lists ten required contexts. Because `required_contexts_for_files` returns every context once any of the ~90 `trigger_paths` match, a PR touching only `pcb/temper.kicad_pcb` makes all ten required. None of them reads the board's footprint inventory:

- `Cross-Source Consistency Gates` (triggers on `pcb/**`): domain-model codegen drift, config reference doc, MPN fabrication, derived-doc drift, net-name classification, PLL range, firmware-board contract. No board/netlist inventory comparison.
- `Invariant tests (router_v6 group 3)` (triggers on `pcb/**`): router unit and property tests.
- `Core Tests`: `tests/core/`, which contains no assertion over the committed board's footprints.
- The remainder (`Rust Checks`, `Type Check`, `Cargo Smoke`, `Generated Repo State`, `Repo Hygiene`, `LOC Cap Gate`, `PR Performance Comparison`) do not read the board.

`Board, Provenance & Requirements Gates` — which holds every gate that *would* catch this — is absent from `required_contexts` and is failing on `main` (latest completed run on `f2b09d846`), for two steps unrelated to this class: `Evidence provenance gate (docs/evidence/)` and `Physical mains<->SELV isolation-barrier gate`. A PR that additionally turned `check_footprint_drift.py` red would produce no new required failure and no change in that job's already-red status.

## 4. Is this reachable in practice?

**By a human: low motive, high friction, and it would be visible.** Every recent board change is a hand-authored scoped CP-SAT solve with candidate selection recorded in the commit body, and lowering the ceiling means committing a re-measurement into a file whose `_march` log is a public, attributed record. A maintainer deleting a component to make a number fall would be writing that down. This is a real path but not a likely one.

**By automation: the mechanism exists, the actor does not yet.** The sharp case is a placer or clearance-repair solve that drops a component from its output — which the ratchet reads as a −46-error improvement and no required check contradicts. `docs/plans/2026-08-04-001-feat-board-regeneration-proposal.md` establishes that `make build` has no placement step and recommends *against* automated board regeneration until `docs/plans/2026-08-02-023-...md` lands. So the actor is planned, not built. That is the honest state: this is a live hazard for work that is on the roadmap and not a live hazard for the repository as it stands today.

**By accident: the most likely of the three.** A scripted board write, a resync, or a merge that loses a footprint would present exactly as an improvement. This is the case for which the inventory gates were built and the case for which their non-required status is the whole problem.

## 5. The options weighed

### Option A — Accept and guard

Keep the count ratchet; rely on inventory invariants to make deletion detectable, and make those invariants required and green.

- **For.** Detection already exists, is unit-tested for this exact class, and passes today. The ratchet's semantics are untouched, so every recorded baseline, every `_march` entry and every evidence doc that quotes an absolute count stays comparable. No new checker, so no new vacuous-gate surface. The work is CI policy, which is bounded and reversible.
- **Against.** It depends entirely on the scarcest resource this repository has. `.github/required-checks.json`'s own note records eight contexts being removed on 2026-08-03 because ~24 concurrent jobs is the account ceiling and one push already requests ~40. `Board, Provenance & Requirements Gates` has a 40-minute budget and builds three Rust crates plus the netlist before any gate runs; promoting it as-is is a measured capacity regression. And it cannot be promoted at all until its two unrelated red steps are fixed.
- **Cost.** Fix two red steps; then either split the three inventory gates into a light required context or move them into `Cross-Source Consistency Gates`, which already triggers on `pcb/**` and already builds the netlist.

### Option B — Pair every count with a positional invariant

The #689 pattern generalised: a count may fall only if the component inventory is unchanged.

- **For.** Strongest coupling. It states the actual contract — "improvement means the same board got better, not a smaller board" — rather than checking a proxy for it.
- **Against, measured.** The landed precedent does not cover this class. §3 shows `check_board_containment.py` iterates the footprints that are present; it is a geometry invariant and cannot see a deletion. So "generalise #689" is a misreading of what #689 built. Once the invariant is correctly identified as an *inventory* invariant, B collapses into A plus a coupling rule — and the coupling rule is the expensive part, because it forbids a legitimate change. `docs/STRATEGY.md` records the BOM as needing reduction; removing a component the design no longer needs is work the project wants. B requires an override channel for it, and an override channel carrying a free-text justification is the `Ceiling-Approval:` weakness reintroduced at a new site.
- **Cost.** A new coupling gate, plus an override path, plus the review discipline the override path needs to mean anything.

### Option C — Normalise per component

Ratchet errors-per-component rather than absolute counts.

- **Against, measured and decisive: it does not remove the incentive.** The clean board is 1262 errors over 169 footprints, 7.47 errors per component. Deleting C4 gives 1216 over 168 — **7.24, an improvement**. Deleting the top five gives 6.81. Normalisation only penalises deleting a component whose credit is *below* the mean; **26 of 169 components carry a credit above it** and remain profitable to delete. It converts "every deletion is rewarded" into "the 15% of deletions with the largest payoff are still rewarded," which is the wrong 15% to leave exposed.

  | deleted | credit | errors/component after | improved? |
  |---|---:|---:|---|
  | *(clean board, 169 footprints)* | — | *7.473* | — |
  | C4 | 46 | 7.238 | **yes** |
  | U27 | 29 | 7.345 | **yes** |
  | U9 | 25 | 7.363 | **yes** |
  | RT1 | 23 | 7.381 | **yes** |
  | R5 | 4 | 7.488 | no |
  | C13 | 0 | 7.512 | no |

- **Also against.** It rebases every recorded baseline and breaks comparability with every `_march` entry, every evidence doc citing an absolute count, and the 120-sample measurement contract that records absolute observed ranges.
- **For.** It is the only option that addresses the incentive inside the measure rather than beside it, and it needs no CI policy change.
- **Verdict.** Measurably the weakest of the three: highest migration cost, and it does not actually solve the problem.

### Option D — Attribute the fall (a complement to A, not an alternative)

Extend R27's attribution contract symmetrically: a per-category *decrease* names its cause, on the same terms a raise will.

- **For.** It removes the incentive at its root by making a deletion stop being an anonymous win. The `_march` log already does this by convention — every entry attributes its delta to a named component or commit — so the contract formalises existing practice rather than inventing it. Unlike B it forbids nothing; it only requires the change to say what it is. Cheap, and it composes with A.
- **Against.** It is a review hook, not a mechanical check: "cause: removed unused C4" is exactly as free-text as `Ceiling-Approval:` is today, which `docs/plans/2026-08-02-023-...md` exists to fix. It converts a silent incentive into a visible claim — real, but strictly weaker than an inventory check that fails closed. And it adds friction to ratcheting down, which is the behaviour the project wants to encourage.
- **Verdict.** Not sufficient alone. Worth doing alongside A, and explicitly listed as a question (Q2) rather than a requirement the maintainer is being asked to accept.

## 6. Recommendation, and its strongest counter-argument

**Recommended: Option A, sequenced, with Option D as a follow-on.**

1. **Fix the two failing steps in `Board, Provenance & Requirements Gates`** (`Evidence provenance gate`, `Physical mains<->SELV isolation-barrier gate`). Nothing can be promoted out of a red job, and until it is green the job's status carries no information about this class or any other. (R5.)
2. **Make the inventory check a required context** — `check_footprint_drift.py` and `check_netlist_board_reconciliation.py` unchanged, in a context that needs the netlist and Python but not the three Rust crate builds. Q1 asks whether that is a new small job or an addition to `Cross-Source Consistency Gates`, which already triggers on `pcb/**` and already builds the netlist; the second is cheaper in slots. (R2, R3, R4.)
3. **Consider closing the geometry/inventory gap in #689's gate** by having `check_board_containment.py` assert its `footprints_checked` count rather than merely report it. It already parses the board; this is the cheapest possible site for a second, independent inventory assertion. Recorded as Q3, not as a requirement.
4. **Extend the attribution contract to falls** when R27 lands, rather than as separate work. (R6.)

Explicitly **not** recommended: changing the unit of measurement (C), or building a new coupling gate (B). The measurement says C does not work and that B's stated precedent does not do what it is believed to do.

**The strongest counter-argument.** *This spends a scarce required-CI slot on a threat model whose agent does not exist.* Every path in §4 that is actually live today is a human one, and the human path is high-friction, self-documenting and unmotivated: a maintainer would have to delete a component, re-measure, and commit an attributed ceiling change into a public log to gain a number nobody is scoring them on. The automated path — a placer dropping a component — is the real hazard, and `docs/plans/2026-08-04-001-...md` establishes both that no such automation exists and that building it is already gated on other work. Meanwhile CI capacity is this repository's measured binding constraint; eight required contexts were *removed* one day before this document for exactly that reason, and `main` is currently red. Adding a required context to defend against an actor that has not been built, in a pipeline that cannot currently afford the contexts it already has, is a defensible thing to decline.

**Why I still recommend it.** The counter-argument is about timing, not about correctness, and two facts blunt it. First, the marginal cost is genuinely small: the gates exist, pass, and need the netlist but not the Rust builds — Q1's second answer adds *zero* new jobs. Second, the project's own acceptance criteria already condemn the status quo: `docs/plans/2026-08-04-002-...md` AE1 says a gate that reports coverage while no seeded defect has been shown to trip it is vacuous, and AE2 says violations reaching zero means nothing while a safety-critical gate has never been demonstrated to fail. A detection that can only ever fire inside a job no PR is blocked by is the same failure in a different costume — and unlike a vacuous gate, this one *works*; it just cannot stop anything. Step 1 is required regardless of the decision, and steps 2–4 can be sequenced behind the automation they defend against without losing the finding.

## Sources / Research

- `docs/evidence/2026-08-04-board-defect-corpus-uncovered-classes.md` (PR #689) — the origin of the −9 observation and of `scripts/check_board_containment.py`.
- `power_pcb_dataset/drc_ceiling.json` — `_goal` (ratchet rule), `violations_by_type`, `nondeterministic_error_types` (the observed bands §1 reproduces), `provenance.inputs[].sha256`.
- `packages/temper-placer/src/temper_placer/regression/drc_ratchet.py` — `detect_ceiling_raise` reacts only to increases; `_check_board` enforces per-type ceilings with implicit-zero semantics.
- `scripts/check_drc_ceiling_approval.py` — the trailer gate; falls need no trailer.
- `scripts/check_board_containment.py` — `analyze_board` iterates `board.footprints`; `footprints_checked` is reported, never asserted.
- `scripts/check_footprint_drift.py` — `MISSING-FROM-BOARD` finding class; `scripts/tests/test_check_footprint_drift.py::test_component_missing_from_board`.
- `scripts/check_netlist_board_reconciliation.py` — `MISSING` finding class; `scripts/tests/test_check_netlist_board_reconciliation.py::test_gate_exits_three_on_missing_component`.
- `scripts/check_measurement_provenance.py` and `scripts/_lib/measurement_provenance.py` — the ceiling's input content-hash freshness contract.
- `packages/temper-design-bundle/src/identity.rs` — `min_overlap` default 0.95 and the overlap ratio it is applied to.
- `.github/required-checks.json` — `required_contexts`, `job_triggers`, and `_required_contexts_note` (the 2026-08-03 capacity removal).
- `.github/workflows/python-tests.yml` — `Board, Provenance & Requirements Gates` job composition; `Cross-Source Consistency Gates` step list.
- `docs/plans/2026-08-04-001-feat-board-regeneration-proposal.md` §3 — the `Ceiling-Approval:` free-text risk and the absence of a placement step in `make build`.
- `docs/plans/2026-08-02-023-feat-drc-ceiling-monotone-contract-plan.md` — R27, the (unbuilt) contract for raises that R6 above would extend to falls.
- `docs/plans/2026-08-04-002-docs-temper-goal-set-plan.md` — AE1/AE2, the project's own standard for what a gate has to be able to do to count as evidence.
