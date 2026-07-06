---
date: 2026-07-05
topic: acceptance-gate-real-drc-and-unsat-ux
---

# Acceptance Gate: Real KiCad DRC + UNSAT as a Product Feature

## Summary

Make the placement pipeline's acceptance gate a **two-tier fence** — fast inner gate (CP-SAT audit + physics oracle) for iteration, truth gate (`validation/drc_runner.py` against real 6mm KiCad DRC rules) for acceptance — and promote the existing `unsat.extract_unsat_core` pipeline to a **first-class product output** that surfaces the minimal conflicting-constraint set with `because` text. Decisive result: *the temper board passes real KiCad DRC at 6mm with zero violations, and an artificially-over-constrained PCL produces a UNSAT report whose minimal core names the conflicting constraints with their physics rationale — both surfaced as the placer's native output, not as log lines.*

---

## Problem Frame

The constraint-completion and place→route workstreams land the *capability* to satisfy all 8 PCL constraint types and route the placement. The acceptance-gate workstream lands the *evidence* that the placement is ready to ship. Two failures it has to prevent:

1. **Inner-gate misclassifies a real violation as satisfied.** The CP-SAT audit verifies the *encoder's* invariants (Chebyshev clearance at 8.5mm, etc.) but the physical DRC rule is Euclidean 6mm. The audit's pass and the real-DRC pass can disagree — and the audit was explicitly built to catch *encoder* bugs, not *model-vs-reality* drift. If only the audit passes for acceptance, a placement can ship with a 6mm Euclidean DRC violation that Chebyshev passes at 8.5mm × sin(45°) ≈ 6.0mm — within audit's tolerance but a real DRC fail.
2. **UNSAT remains a developer-side debug log, not a domain-expert output.** The existing `UnsatReport` (per `unsat.py:34`, `extract_unsat_core` at line 164) outputs to structured data classes; surfacing to a panel, formatted report, or JSON file is the workstream's UX contribution. The CP-SAT paradigm's unique value — telling the domain expert *which constraints conflict*, instead of returning "no feasible placement found" — is unrealized if the report stays in `pprint`.

What also lands here, per the umbrella's F5 fusion: this workstream ships the oracle-worktree hierarchy decision. The physics oracle becomes the fast inner gate; `human-reference-corpus-oracle` lands demoted to the regression floor (49-board no-crash / geometric-no-regress — its right role from way back). The placement-init worktree close is *not* here (that's F1 of the umbrella / the JAX-retirement per-workstream doc).

---

## Actors

- A1. **CP-SAT audit** (`placer/cp_sat/audit.py`): the inner-gate side; fast; per-solve; encoder-invariant verification.
- A2. **Physics oracle** (`metrics/external_oracle.py`): the inner-gate's oracle-component side; non-DRC physics scores (thermal, clearance_3mm/6mm, dual-rail).
- A3. **KiCad DRC** (`validation/drc_runner.py`): the truth gate; `run_drc(pcb_path) -> DrcResult`; consumes a placed+routed PCB and returns real-rule violations.
- A4. **`human-reference-corpus-oracle`**: regression-floor only; 49-board corpus liveness, not acceptance. Demoted by this workstream.
- A5. **`unsat.extract_unsat_core` + `refine_mus`**: the UNSAT-extraction pipeline; surfacing is this workstream's UX contribution.

---

## Key Flows

- F1. **Per-solve inner gate (the fast path)**
  - **Trigger:** Every CP-SAT solve during iteration (place→route loop, manual placement runs, regression tests).
  - **Actors:** A1, A2
  - **Steps:** Audit verifies the encoded invariants (8/8 constraint types post-completion); `score_placement()` (or `run_physics_oracle()` during the strangler tail) returns the dual-rail clearance and thermal scores. Decision: continue iterating (gate pass), surface failure (gate fail with metric breakdown), or escalate to truth gate (gate pass at threshold where real-DRC likelihood is high — e.g. completion=100% AND all audit checks green AND clearance_6mm ≥ 0.85).
  - **Outcome:** A cheap gate that the loop runs every round-trip; truth gate runs only on phase-2 stable placements or acceptance runs.
  - **Covered by:** R1

- F2. **Acceptance truth gate (KiCad DRC)**
  - **Trigger:** An accepted placement (post-loop, manual placement sign-off, or release-tag preparation).
  - **Actors:** A3
  - **Steps:** Routed PCB consumed by `run_drc(pcb_path)`; the `DrcResult` parsed into structured `DrcError`/`DrcWarning` lists. The placement is accepted iff `len(drc_result.errors) == 0`. Warnings are surfaced but do not block. Real DRC rules: 6mm HV/LV creepage netclass rule, manufacturer-rule 0.2mm track/0.2mm clearance, via/silkscreen/board-edge rules from the relevant design-rules profile.
  - **Outcome:** A pass/fail on real KiCad rules; on fail, structured violation report covering what would actually prevent board fabrication.
  - **Covered by:** R2

- F3. **UNSAT as a product feature**
  - **Trigger:** CP-SAT returns INFEASIBLE — either on initial placement or on a place→route loop's feedback-injection round.
  - **Actors:** A5
  - **Steps:** `extract_unsat_core(solver, model, assumption_vars, constraint_map)` produces the `UnsatReport` (sufficient core + MUS-refined minimal core); the workstream's surfacing layer formats it:
    - **Stderr / Rich panel**: per-conflicting-constraint line ("Constraint 'Q1 must be ≥6mm from U_MCU' (because: 'Reinforced isolation per IEC 60335-1') conflicts with 'All HV components must fit inside HV_ZONE' (because: 'HV segregation for touch safety') — the HV zone is too small to hold all HV parts at required clearance."), grouped by minimal-core membership.
    - **Structured JSON file** (optional, behind a `--unsat-report` flag): machine-readable for downstream tooling or future IDE integration.
  - **Outcome:** A domain expert reading the report *understands the conflict* without re-deriving the geometry from the placement — the L_loop derivation's `because` field surfaces; the IEC 60335-1 rationale surfaces; the operator isn't reduced to "the placer failed."
  - **Covered by:** R3, R4

- F4. **Oracle-worktree hygiene (F5-of-umbrella)**
  - **Trigger:** F1+F2 lands.
  - **Actors:** A2, A4
  - **Steps:** Land `physics-derived-oracle` as A2 (the inner-gate physics-oracle side); demote `human-reference-corpus-oracle` to regression-floor status with a documented scope statement ("liveness + no-geometric-regression across 49 boards; not acceptance"). Both worktrees close after their lands or explicit rejects.
  - **Outcome:** Oracle hierarchy reflects the post-paradigm-swap shape: one acceptance oracle, one regression oracle, no parallel-branch mental model residue.
  - **Covered by:** R5

---

## Requirements

- R1. The inner gate (audit + physics oracle) runs on *every* CP-SAT solve; the truth gate (KiCad DRC) runs on accepted placements only. The two are not interchangeable: audit-pass-without-DRC-pass is *not* acceptance; DRC-pass-without-audit-pass is *not* acceptance. The two-tier distinction is explicit in code and docs.
- R2. KiCad DRC acceptance: `validation/drc_runner.run_drc(pcb_path)` returns a `DrcResult` with `len(errors) == 0` on the temper board at the real 6mm design rules. The placement is routed (post-place→route-loop R4) before DRC. Errors (not warnings) are the blocking bar.
- R3. UNSAT report surface: a Rich-formatted panel to stderr AND an optional JSON file (under `--unsat-report <path>`). Content: minimal core (`extract_unsat_core`'s MUS refinement) + each constraint's `because` field populated in the PCL spec; the existing `unsat.py`'s `UnsatReport` is the data source; the workstream adds the *surfacing* layer, not the extraction logic.
- R4. UNSAT report's `because` accuracy: the surfaced text comes from the PCL spec's `because` field — not from a hypothesis about why the constraint exists. If a constraint's `because` field is missing or vague, the report surfaces *that* as a finding (constraint unannotated, rationale unknowable from the spec — a PCL data-quality gap, not the placement engine's responsibility). The L_loop-derivation-recommended update to `commutation.yaml`'s `because` field (per the constraint-completion doc) dereferences here: the UNSAT report's loop-area conflict surfaces "IGBT overvoltage destruction," not "EMI."
- R5. **Oracle-worktree decisions** (per the umbrella's R6, enumerated here not in a separate per-workstream doc):
  - `physics-derived-oracle` → LAND as A2 (the inner-gate physics-oracle side).
  - `human-reference-corpus-oracle` → LAND demoted to regression-floor status; documented scope statement in its README and in `docs/solutions/`; not invoked by the acceptance path.
  - `viz-server` → out of scope (not an oracle worktree).
  - The five `placement-init-*` worktrees → closed per the JAX-retirement per-workstream doc, NOT here.
- R6. **Decisive result** (per the umbrella's Discipline): two-part — *(a) the temper board passes real KiCad DRC at 6mm with zero violations; AND (b) an artificially-over-constrained PCL (e.g. `max_area_mm2=10` below the L_loop derivation's threshold) produces a UNSAT report whose minimal core names the loop-area constraint AND its `because` field cites the overvoltage rationale — both surfaced as the placer's native output (panel + JSON), not via a `.pprint()` in a test.*

---

## Acceptance Examples

- AE1. **Covers R1, R2, R6(a).** Given the temper board post-constraint-completion and post-place→route-loop, when the accepted placement is routed and run through `drc_runner.run_drc()`, the `DrcResult.errors` list is empty.
- AE2. **Covers R1, R6(b).** Given an artificially-over-constrained PCL (`loop_area.max_area_mm2=10`) and the modified temper_induction.yaml's `because` field updated to cite the L_loop derivation's "IGBT overvoltage destruction" failure mode, when CP-SAT returns INFEASIBLE, the UNSAT panel surfaces:
  ```
  Infeasibility detected. Minimum conflicting constraints:
    - loop_area 'commutation' (because: IGBT overvoltage destruction above 635mm² at 1A/ns di/dt and 80%-derated V_CE=960V — exceeds derated rating)
      conflicts with one or more enclosure/geometry constraints. Area budget 500mm² exceeds overconstrained 10mm².
  ```
  AND the JSON file produced by `--unsat-report out.json` contains the same minimal core as machine-readable entries.
- AE3. **Covers R3, R4.** Given a constraint whose `because` field is blank, when the UNSAT report surfaces it, the report includes the line `'because' field is unannotated; rationale not available from PCL spec — constraint X lacks a physics grounding` — surfacing the PCL data-quality gap, not a fabricated rationale.
- AE4. **Covers R5.** Given the oracle-worktree hierarchy post-merge: `physics-derived-oracle`'s README states "acceptance inner-gate oracle"; `human-reference-corpus-oracle`'s README states "regression-floor corpus liveness — 49 boards, no-crash / geometric-no-regress; not acceptance." Acceptance path imports from `physics-derived-oracle` or its successor location; never from the corpus oracle.
- AE5. **Covers R1.** Given a CP-SAT placement whose audit passes but real KiCad DRC fails with one clearance violation at 5.8mm (within Chebyshev's 8.5mm-audited tolerance but below the 6mm Euclidean rule), the workstream's gate-classification reports `audit_passed=true, drc_passed=false` — and *blocks* on `drc_passed=false`, with the violation surfaced as the cause. The audit-vs-DRC disagreement is the *signal* the truth gate exists to produce.

---

## Success Criteria

- *Temper board passes real KiCad DRC at 6mm with zero violations* AND *an over-constrained PCL produces a surfaced UNSAT report naming the conflicting constraint and its physics rationale* (decisive result, R6).
- The audit-vs-DRC disagreement (AE5) is *expected and surfaced as signal*, not hidden by treating audit-pass as acceptance.
- `physics-derived-oracle` lands as acceptance inner-gate; `human-reference-corpus-oracle` lands demoted; `viz-server` out of scope; the five placement-init-* branches closed by the JAX-retirement per-workstream doc, not here (R5 enumeration).
- UNSAT report's `because` text comes from the spec — never fabricated. Missing `because` text is itself surfaced as a PCL data-quality finding.
- The L_loop derivation's recommended `commutation.yaml` `because` update is consumed by the report — the EMI framing goes away in favor of the overvoltage-destruction rationale.

---

## Scope Boundaries

- **Routing completion bar** — out of scope; owned by the Place→Route Loop workstream (`docs/brainstorms/2026-07-05-place-route-loop-feedback-as-constraint-requirements.md`). This workstream consumes the routed PCB; whether the routing is "good enough" is a separate decision.
- **Continuous-angle rotation, soft-routed loop-area minimization** — out of scope per the constraint-completion doc's scope boundaries.
- **Corpus-oracle producing a confidence-coded acceptance verdict** — out of scope; corpus-oracle is *demoted* here, not re-tooled.
- **UNSAT report's UI beyond panel+JSON** — out of scope. A future IDE/PR-comment-bot integration is plausible but its design belongs in a future workstream.
- **PCL `because`-field audit / enforcement** — out of scope, *except* in the AE3 surfacing sense (missing `because` is surfaced as a PCL data-quality gap in the UNSAT report itself). The workstream flags the gap; fixing all PCL spec entries is the constraint-completion doc's responsibility.
- **Truth-gate performance** — out of scope; `kicad-cli` is sourced kicad-cli, runs as fast as it runs. The workstream does not optimize KiCad DRC throughput.
- **Five placement-init worktree closes** — out of scope (JAX-retirement per-workstream doc, F3 there).
- **`viz-server` disposition** — out of scope entirely.

---

## Key Decisions

- **Two-tier gate (audit + physics-oracle as inner; KiCad DRC as truth)** — the audit verifies *encoder invariants*; the physics oracle produces *non-DRC physics scores* (thermal, dual-rail clearance); DRC verifies *physical-rule satisfaction*. The audit-vs-DRC disagreement (AE5) is the *truth-gate's whole point* — when they disagree, DRC wins; the disagreement indicates a Chebyshev-vs-Euclidean safety-factor mismatch, an encoder bug, or a spec-vs-physical-reality gap, all of which are real findings worth surfacing.
- **Errors block, warnings don't** — `DrcResult.errors` are design-rule failures that *prevent fabrication*; `DrcResult.warnings` are non-blocking manufacturability suggestions. The workstream binds the bar on the former, surfaces the latter for human review, and does *not* conflate them into a single pass/fail.
- **UNSAT surfacing as panel+JSON, not as the `pprint` of the `UnsatReport`** — `unsat.py:34`'s `UnsatReport` dataclass carries sufficient_core + minimal_core + is_minimal; the workstream's contribution is the *surfacing layer* that translates that into the panel/JSON formats. The extraction logic is already built (#121's U7).
- **`because` from PCL spec, not from extraction** — the report does not invent rationales. Surfacing "constraint unannotated" as a finding (AE3) is the workstream's candor surface for PCL data quality. The L_loop derivation's `commutation.yaml` `because` update (per the constraint-completion doc's outstanding question) dereferences here — the UNSAT report can only cite the overvoltage rationale if the PCL spec's `because` field carries it. Surfacing the gap is this workstream's contribution; *fixing* the gap is the constraint-completion doc's outstanding question.
- **`human-reference-corpus-oracle` demoted, not deleted** — it was correct at its purpose (corpus liveness regression, 49-board no-crash / geometric-no-regress); it was wrong at its *aspirational* purpose (acceptance gate). Demotion + documented scope statement lands it fit-for-purpose without losing the regression-floor capability.
- **`viz-server` out of scope** — it is adjacent (visualization), not in the oracle hierarchy. Whatever disposition is decided for it belongs in its own future workstream, not here.

---

## Dependencies / Assumptions

- **Hard prerequisite: PR #121 merged.** All "existing infrastructure" claims in this doc — `unsat.extract_unsat_core` at `placer/cp_sat/unsat.py:164`, `UnsatReport` dataclass at line 34, `_build_proto_index_map` at line 64, `validation/drc_runner.run_drc()` at `validation/drc_runner.py:162`, `score_placement()` — resolve against the post-#121 state. Round-2 doc-review #7 reported `unsat.py` and `extract_unsat_core` as not existing; the worktree has them (`packages/temper-placer/src/temper_placer/placer/cp_sat/unsat.py` exists). The doc-reviewer's largest "does not exist" claim — the headline Theme 1 — was a main-not-worktree check; verifying the worktree confirms the cited infra.
- **Constraint-completion workstream (F2 of the umbrella; per doc `2026-07-05-constraint-completion-cp-sat-encoder-requirements.md`, including U0b passing)** has landed — its R1 workstream's update to `commutation.yaml`'s `because` field (the L_loop derivation's recommended revision) is *consumed* here. Without that, the UNSAT report's loop-area conflict surfaces "EMI" instead of "overvoltage destruction" — accurate to the spec, but the spec is wrong. Sequencing: constraint-completion's `because` update lands first; this workstream consumes it.
- **Place→route loop workstream (F3; per doc `2026-07-05-place-route-loop-feedback-as-constraint-requirements.md`) has landed** — truth-gate-R2 accepts a *routed* PCB; placement-only DRC is structurally inadequate (most real-DRC rules check routed features — track clearance, via annular rings, etc.). The place→route loop produces the routed PCB; the acceptance gate consumes it. *Hard prerequisite for R2.*
- **`validation/drc_runner.run_drc()` exists and parses `kicad-cli` JSON** — verified at `validation/drc_runner.py:162` + `_parse_drc_json:104`. The workstream's R2 uses this programmatic interface.
- **OR-Tools `SufficientAssumptionsForInfeasibility` proto-index translation** — verified at `unsat.py:64`'s `_build_proto_index_map`; existing #121 U7 implementation handles this. No new infra.
- **`kicad-cli` is available in the workstream's execution environment** — round-2 residual concern #2: this is load-bearing for the decisive results of Docs 2, 3, AND 4. Workstream-shape assumption (CI vs local: implementer's discretion; the workstream binds the bar, not the availability), but the doc explicitly surfaces the kicad-cli-dependency risk: if CI doesn't have kicad-cli, the truth gate runs on local/runner-side environments only and CI truth-gate is a soft-fail (surfaced as a non-blocking warning) — the workstream does not silently downgrade the truth gate to oracle-proxy.
- **The five placement-init-worktree closures are completed separately by the JAX-retirement workstream** — this doc enumerates them in R5 *as decisions* (closed without merge) but does not perform the closures; they belong to F1 of the umbrella / the JAX-retirement per-workstream doc.
- **Physics-derived-oracle's fate when landing at A2** — round-2 deferred question #4 surfaces: physics-derived-oracle's code as it exists today was derived against JAX (`run_physics_oracle()` invokes `train_multiphase`); when it lands at A2 (the inner-gate physics-oracle side per Doc 4 R5), it must be adapted to consume CP-SAT placements via `score_placement()` from `metrics/external_oracle.py` — not its current JAX-train-coupled form. The "LAND" decision in R5 includes this adaptation; the workstream specifies the adapter, not just the move.

---

## Outstanding Questions

### Resolve Before Planning

_None — the doc binds the two-tier gate's bar, the UNSAT surfacing's content, and the oracle-worktree decisions per the umbrella's R5/R6 enumeration._

### Deferred to Planning

- [Affects R2][Technical] Routed-PCB handoff: whether the truth gate runs `drc_runner.run_drc()` on a placed+routed `.kicad_pcb` file on disk vs. on an in-memory representation; `drc_runner` interface suggests file-based, so the workstream writes the routed PCB and DRCs it.
- [Affects R3][Technical] Exact Rich-panel-layout: per-constraint entries vs. grouped-core-block format. The minimal-core grouping is the substantive design decision (how to present "these N constraints form the irreducible conflict"); the visual rendering is implementer's discretion.
- [Affects R3][Technical] JSON schema for `--unsat-report`: probably mirrors `UnsatReport`'s dataclass shape 1:1; whether to include sufficient core AND minimal core OR only minimal is implementer's discretion (minimal is the answerable result; sufficient is the fallback when MUS doesn't converge).
- [Affects R5][User decision] `human-reference-corpus-oracle`'s final location: lands as a separate module within `regression/`, stays in its own directory, or folds into `physics-derived-oracle`'s hierarchy. The demotion scope statement is binding; the location is not.
- [Affects R5][Technical] Whether to gate a CI integration test on `kicad-cli` availability — ⛔ if the CI doesn't have kicad-cli, the workstream must fall back to oracle-proxy DRC for the CI truth gate and reserve real-DRC for local/run-acceptance — *a proxy-vs-truth distinction this workstream must surface in its docs, not silently default on*. Per "verify before claiming" — the brainstorm flags `kicad-cli` availability as a deferred-to-planning question.