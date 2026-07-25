---
title: "feat: Board Routing Completion — Resume Stalled Work, Then Escalate to Multi-Layer"
type: feat
status: completed
date: 2026-07-18
origin: docs/brainstorms/2026-07-18-board-routing-completion-requirements.md
swept: 2026-07-25
swept_basis: "already declared"
---

# feat: Board Routing Completion — Resume Stalled Work, Then Escalate to Multi-Layer

## Summary

The temper production board (`pcb/temper.kicad_pcb`) has never been routed through `router_v6`/`PlaceRouteLoop`. This plan has two phases. **Phase 1** verifies and completes the 2026-07-10 stalled plan's scope against the *production* board specifically: verification (not re-implementation — investigation below shows the adapter repair, net-ordering heuristic, and FinePitch netclass calibration were already committed 2026-07-11/07-12, unknown to the origin brainstorm) plus a first-ever `PlaceRouteLoop` run against `pcb/temper.kicad_pcb` using the fixed gate-dispatch path, ERC-to-zero, and a production-board routing-quality CI gate. **Phase 2** scopes the multi-layer escalation — and a second major finding changes that phase's shape too: an active plan already exists for exactly this work (`docs/plans/2026-07-08-004-feat-4-layer-functional-stackup-plan.md`, workstream W2), is partially implemented, and the corpus-board routing-DRC gate still measures 261 (local) / 443 (CI) violations *despite* that partial implementation already being live in `route_pcb()`'s default path. Phase 2 is therefore an audit-and-close pass against the existing W2 plan, not a new design, plus individual diagnosis of the two violation categories (`shorting_items`, `diff_pair_gap_out_of_range`) a layer alone won't fix.

---

## Requirements

Traces to the origin (`docs/brainstorms/2026-07-18-board-routing-completion-requirements.md`).

- **R1 — Resume-or-reassess the stalled 2026-07-10 plan.** ✅ **Reassessed, not resumed as new work.** Investigation (see Context & Research) shows `V6RouterAdapter._build_temp_pcb` was repaired and the net-ordering heuristic added in commit `a281f865` (2026-07-11), and FinePitch netclass calibration landed in `051152e7` (2026-07-12) — both are ancestors of current `HEAD` and verified present in the current source. The 2026-07-10 plan's diagnosis was correct and the work was carried out; it was simply never applied to the *production* board (`pcb/temper.kicad_pcb`) or measured with the fixed loop gate dispatch. Phase 1 closes that gap.
- **R2 — Re-run routing with the `PlaceRouteLoop.run()` gate-dispatch fix in place.** Any production-board routing run in this plan must go through the post-2026-07-18 `loop.py` (`self._gates_explicit` dispatch, verified present at `loop.py:165-306`). No pre-fix run's gate coverage may be cited as evidence.
- **R3 — Target the production board directly, not only the corpus copy.** `test_regression_drc.py`'s `BOARD_PATH` currently points at `power_pcb_dataset/corpus/temper/temper.kicad_pcb` (confirmed, line 38) — the production board has never been measured by this gate. Decision (Phase 1 U5): **supplement**, not repoint or duplicate wholesale — add a second, explicitly production-board test function, keep the existing corpus test as a fast/stable proxy, document the relationship in both tests' docstrings.
- **R4 — Scope the multi-layer routing escalation.** Reassessed given evidence: an active plan (`2026-07-08-004`, W2) already covers this ground and is partially implemented (net-to-layer assignment from netclass SSOT, U1/U2, is live in `route_pcb()`'s default path — see Key Technical Decisions). Phase 2 audits W2's real completion state, diagnoses `shorting_items`/`diff_pair_gap_out_of_range` individually (not assumed layer-crowding symptoms), and closes the highest-leverage remaining W2 gaps rather than designing a new mechanism.
- **R5 — Anti-false-zero guard, carried forward.** Re-adopts the 2026-07-10 plan's R7 intent verbatim for this doc's scope (see that plan's U5): every "100% routed" / "0 DRC" claim in this plan is checked against (a) an unchanged-or-visibly-changed constraint set and (b) a properly-configured gate (not `UNMEASURED` misread as clean). Applied as a cross-cutting check in Phase 1 U6 and Phase 2 U10, not a one-time gate.

---

## Scope Boundaries

**In scope:** verifying/completing Phase 1's production-board routing + ERC; auditing and closing high-leverage gaps in the existing W2 (4-layer functional stackup) plan; individual diagnosis of `shorting_items`/`diff_pair_gap_out_of_range`; deciding and implementing the `test_regression_drc.py` BOARD_PATH supplement.

**Deferred:** full completion of every W2 unit (U3 IPC-2152 integration, U4 power-domain pours + thermal vias, U5 USB differential pair, U6 `StackupGate` file relocation) is not required by this plan — only the units that measurably move the routing-DRC violation count are prioritized (Phase 2 U9). Units unrelated to the current violation categories are left for W2's own backlog.

**Outside scope:** the board-size/BOM capacity decision (`docs/brainstorms/2026-07-18-board-capacity-bom-decision-requirements.md`, being planned concurrently as a sibling document). **This plan is a parallel, non-blocking sibling to that work** — per the origin brainstorm's own framing, the two threads proceed independently. If that decision results in a board resize, routing work on the current geometry may need to be redone; this plan does not pause for that outcome, and does not re-open board size/BOM as a topic. Netclass calibration and DRC footprint-library-table configuration are folded into Phase 1 (verification-first, since both already have partial implementations — see Context & Research) rather than re-litigated as new units.

---

## Context & Research

### Investigation performed for this plan (step 7 of the planning brief)

This is the evidence base for R1's reassessment and directly answers the brainstorm's open question 1 / success criterion 1: **it is now known, with commit-level evidence, that `_build_temp_pcb` and the net-ordering heuristic were implemented.**

- `git log --all --oneline -- packages/temper-placer/src/temper_placer/router_v6/adapter.py` shows commit `a281f865` ("fix(router): restore `_build_temp_pcb` as `V6RouterAdapter` class method + ordering heuristic", 2026-07-11) — `git merge-base --is-ancestor a281f865 HEAD` confirms it is an ancestor of the current worktree `HEAD` (`95c0e813`).
- `grep -n "_build_temp_pcb" adapter.py` confirms `_build_temp_pcb` is defined at 4-space indent (a real class method of `V6RouterAdapter`, not a stray module-level function) at line 317, called from `rrr_route_all_nets` at line 255.
- The net-ordering heuristic described in commit `a281f865`'s message and the 2026-07-10 plan's U1 (signal nets after power/HV nets) is present verbatim at `adapter.py:293-298` (`_SIG`/`_PWR` prefix tuples, `_net_prio` sort key, applied via `net_order = sorted(net_order, key=_net_prio)`).
- FinePitch netclass calibration (2026-07-10 plan's U3/R4) is confirmed live: `netclass_rules.yaml` has a `FinePitch` class (clearance 0.1mm, commit `051152e7`, "feat(R4): implement FinePitch netclass clearance in routing + config", 2026-07-12, ancestor of `HEAD`).
- The DRC footprint-library-table configuration (2026-07-10 plan's U4/R5) is partially done: `placer/cp_sat/gates.py:182` sets `KICAD7_FOOTPRINT_DIR`. **ERC (`kicad-cli pcb erc`) has zero wiring anywhere in `src/`** (`grep -rln "pcb erc" packages/temper-placer/src/` returns nothing) — this half of R5/R6 from the 2026-07-10 plan is genuinely unstarted and is Phase 1 U4 below.
- `power_pcb_dataset/baselines/temper_production_baseline.yaml`'s `routed_nets: 0` is confirmed still accurate **but is measuring a different pipeline** than the one just verified above: the baseline's `deterministic_pipeline` block is extracted via `create_drc_aware_pipeline` (the JAX-retired-era 22-stage CP-SAT deterministic pipeline), not `router_v6.adapter.route_pcb()`. Nothing in this repo has ever run `route_pcb()` / `PlaceRouteLoop` against `pcb/temper.kicad_pcb` — only against the corpus copy (`test_regression_drc.py`'s `BOARD_PATH`). This is the real, still-open gap R3 targets, not a re-run of already-done work.
- **Second major finding (drives Phase 2's restructuring):** the "formerly deferred W2" multi-layer escalation is not scoping-from-zero. `docs/plans/2026-07-08-004-feat-4-layer-functional-stackup-plan.md` (status `active`, workstream `W2`) already exists with 6 units (U1 stackup definition, U2 net-to-layer assignment, U3 IPC-2152 widths, U4 power pours + thermal vias, U5 USB diff-pair, U6 `StackupGate`). Checked completion:
  - **U2 (net-to-layer assignment) is live and wired into the default `route_pcb()` path** — `adapter.py:447-473` calls `layer_assignments_from_netclass(design_rules, net_names)` unconditionally whenever `design_rules is not None`, and passes the result as `layer_constraints` into `RouterV6Pipeline`. `netclass_rules.yaml` already has a `layer` field on all 9 classes (F.Cu/B.Cu/In1.Cu). Commit `06435acb` ("feat(router_v6): net-to-layer assignment from netclass SSOT (W2 U2/R2)", 2026-07-08) is this exact unit.
  - **U1 (stackup definition) is live**, though at a different path than the W2 plan specified: `core/stackup.py:58` has `jlc04161h_7628()`, not the planned `router_v6/stackup_config.py`.
  - **U3 (IPC-2152) is partially live**: `core/ipc2152.py` exists, but `configs/net_currents.yaml` (the per-net current table) does not — the width calculator has no current input to size against yet.
  - **U4 (pours + thermal), U5 (USB diff-pair) appear unstarted**: `configs/net_currents.yaml`, `router_v6/differential_pair_constraints.py`, `core/diff_impedance.py` are all missing.
  - **U6 (`StackupGate`) exists, but at a different location than planned** (`placer/cp_sat/gates.py`, not `router_v6/gates/stackup_gate.py`) and is already one of the 5 default gates `PlaceRouteLoop` builds under `all_gates=True` (confirmed in `docs/solutions/logic-errors/place-route-loop-run-ignores-constructor-gates-without-all-gates-flag.md`'s root-cause excerpt).
  - **A separate, second layer-assignment mechanism also exists and may conflict**: `router_v6/channel_mapping.py::_assign_layer()` uses a simpler heuristic (power/ground/HV → B.Cu, else F.Cu) gated by a *global* `_SINGLE_LAYER_MODE` module flag (`net_classification.py`, defaults `False`). It is unclear whether this and `layer_assignment.layer_assignments_from_netclass()` agree, conflict, or one is dead weight relative to the other — flagged as a Phase 2 U7 audit finding target, not resolved here.
  - **Conclusion for R4:** despite U1/U2 (and part of U3) of the multi-layer escalation already being live in the default routing path, the corpus-board routing-DRC gate (`test_golden_board_routing_drc_regression`) *still* measures 261 (local, kicad-cli 10.0.4) / 443 (CI, kicad-cli 8.0) violations as of 2026-07-18 — this is today's number, post all of the above. The test's own captured error message ("single-layer F.Cu routing with all 24 nets on one layer") is very likely **stale** relative to current code, since multi-layer netclass-based layer assignment has been the default since 2026-07-08. Phase 2 must not repeat that unverified attribution.

### Relevant Code and Patterns

- `packages/temper-placer/src/temper_placer/router_v6/adapter.py` — `V6RouterAdapter` (`rrr_route_all_nets`, `_build_temp_pcb`, confirmed repaired) and the module-level `route_pcb()` function (line 401, the actual entry point `PlaceRouteLoop` and `test_regression_drc.py` use — a *different* code path from `V6RouterAdapter.rrr_route_all_nets`, which has no callers outside `adapter.py` itself and is used by `auto_layout.py`/`internal_route.py` consumers per its own docstring).
- `packages/temper-placer/src/temper_placer/router_v6/layer_assignment.py` — `layer_assignments_from_netclass()`, the W2 U2 net-to-layer resolver, already wired into `route_pcb()`.
- `packages/temper-placer/src/temper_placer/router_v6/channel_mapping.py` — `_assign_layer()`, the second, simpler layer heuristic (Phase 2 audit target).
- `packages/temper-placer/src/temper_placer/router_v6/net_classification.py` — `get_single_layer_mode()`/`set_single_layer_mode()`, module-global flag defaulting `False`.
- `packages/temper-placer/src/temper_placer/router_v6/net_ordering.py` — a *more sophisticated* ordering module (`order_nets()`, config priority + loop criticality + net class + pin count + HPWL + alphabetical tiebreak) used by `route_stage.py` (U8 lexicographic ordering) and `verifier.py`, but **not** by `adapter.py`'s simple `_net_prio` heuristic — two separate ordering mechanisms exist in the router, worth noting but not in this plan's scope to unify.
- `packages/temper-placer/src/temper_placer/placer/cp_sat/loop.py` — `PlaceRouteLoop`, gate-dispatch fix at lines 165-306 (`self._gates_explicit`), confirmed present; `route_pcb()` call sites at ~1225/1241 pass `design_rules=netclass_rules.design_rules`, so `PlaceRouteLoop`-driven routing already gets W2 U2's layer constraints "for free."
- `packages/temper-placer/tests/placer/cp_sat/test_regression_drc.py` — `BOARD_PATH` (line 38, corpus board), `test_golden_board_drc_regression` (placement gate), `test_golden_board_routing_drc_regression` (routing gate, calls `route_pcb()` directly, *not* through `PlaceRouteLoop`).
- `power_pcb_dataset/baselines/temper_production_baseline.yaml` — `routed_nets: 0`, `escape_vias: 124`, `connectivity_unconnected_pads: 269` (deterministic-pipeline block; `cp_sat`/router_v6 block is entirely `null`, confirming router_v6 has never run against this board).
- `pcb/temper.kicad_pcb` — production board, 149 components / 95 nets, 100×150mm, vs. the corpus board's ~24 nets (per commit `598d3a66`'s message) — a materially larger routing problem; flagged as a risk in Phase 1 U3.
- `docs/plans/2026-07-08-004-feat-4-layer-functional-stackup-plan.md` — the existing, active W2 plan Phase 2 audits and resumes.

### Institutional Learnings

- `docs/solutions/logic-errors/place-route-loop-run-ignores-constructor-gates-without-all-gates-flag.md` — the gate-dispatch bug this plan's R2 requires be respected; also the source confirming `StackupGate` is one of the 5 default `all_gates=True` gates.
- `docs/solutions/test-failures/regression-drc-tests-missing-zone-loop-wiring.md` — source of the 261/443 corpus-board violation counts; documents that both DRC regression tests previously crashed on setup (`UnresolvedConstraintRefsError`) before ever reaching their real assertions, and that the `zones=`/`_UNRESOLVED_REF_POLICY` fix is what let the routing gate's real, still-open 261/443 number surface for the first time.
- `docs/solutions/logic-errors/weak-nooverlap2d-encoding-allows-zero-gap-2026-07-08.md`, `docs/solutions/architecture-patterns/two-tier-acceptance-gate-unsat-surfacing-2026-07-05.md`, `docs/solutions/logic-errors/baseline-extractor-four-silent-fail-metrics-2026-07-01.md` — the three learnings the 2026-07-10 plan's R7/U5 anti-false-zero guard was built on; reused verbatim as this plan's R5/U6/U10 pattern (see Key Technical Decisions).

---

## Key Technical Decisions

- **Phase 1 is verification-plus-extension, not re-implementation.** The 2026-07-10 plan's U1 (adapter repair + ordering) and U3 (FinePitch) are done; re-doing them would be wasted, unverified duplicate work. Phase 1's actual new work is: run the already-repaired pipeline against the production board for the first time (never done), close ERC (never started), and stand up a production-board routing-quality gate (R3).
- **Reuse `route_pcb()`, not `V6RouterAdapter.rrr_route_all_nets()`, for production-board routing.** `route_pcb()` is the function `PlaceRouteLoop` and the existing DRC regression test both call, and it's the one with W2 U2's `layer_constraints` wiring; `rrr_route_all_nets()` is a parallel, narrower-scoped MazeRouter-compatibility shim used by unrelated consumers (`auto_layout.py`/`internal_route.py`) and lacks the `layer_constraints` wiring entirely.
- **Phase 2 audits and resumes plan `2026-07-08-004` rather than designing a new multi-layer mechanism.** The brainstorm's own Scope Boundaries defer "full multi-layer implementation details" to a design pass — that design pass already happened (W2, 2026-07-08) and is ~2.5/6 units complete. Re-planning it here would duplicate an active document; the correct action is auditing its real state (U7) and closing the highest-leverage remaining gaps (U9), same resume-vs-reassess discipline R1 applied to the 2026-07-10 plan.
- **`shorting_items` and `diff_pair_gap_out_of_range` get individual diagnosis (U8), not folded into "more layers fixes everything."** Per brainstorm R4, a genuine net-adjacency short or a differential-pair spacing violation is not automatically resolved by adding routing area — this mirrors R3's disposition in the 2026-07-10 plan (placement-topology failures ruled off the table only after per-net diagnosis, never assumed).
- **`test_regression_drc.py` gets supplemented, not repointed.** Repointing `BOARD_PATH` at `pcb/temper.kicad_pcb` would make the existing, already-fragile-enough gate (previously crashed on `UnresolvedConstraintRefsError` for months, per the regression-drc-tests-missing-zone-loop-wiring doc) run against a ~4x larger netlist (95 vs. ~24 nets) with unknown timeout/stability implications, and would lose the fast corpus-board signal entirely. Duplicating the whole file was rejected as needless maintenance overhead (two near-identical files drifting apart). Supplementing (new test function(s) in the same file, sharing helpers, targeting `pcb/temper.kicad_pcb`) keeps one source of truth for the DRC-counting logic while adding the production-board measurement R3 requires.
- **Anti-false-zero guard (R5) is re-checked at the end of each phase, not once globally.** Phase 1 U6 and Phase 2 U10 both independently assert (a) constraint-set-unchanged-or-visibly-changed and (b) gate-properly-configured, exactly mirroring the 2026-07-10 plan's U5 pattern — a phase-scoped re-check catches false zeros introduced by either phase's own work, not just the plan's final state.

---

## Open Questions (Deferred to Implementation)

- **Are `layer_assignment.layer_assignments_from_netclass()` and `channel_mapping._assign_layer()` in agreement, redundant, or actively conflicting?** Both resolve a net's routing layer, from different inputs (netclass YAML vs. name-pattern heuristic + global single-layer flag). Phase 2 U7's audit should determine which one actually governs A* routing decisions inside `RouterV6Pipeline` before deciding whether closing W2 gaps requires touching one, both, or neither.
- **Does the production board's `pcb/temper.kicad_pcb` netlist use net-name patterns compatible with the existing FinePitch/signal-vs-power classification heuristics** (`_SIG`/`_PWR` prefixes in `adapter.py`, `is_power_net`/`is_ground_net`/`is_hv_net` in `net_classification.py`)? These were tuned against the corpus board's ~24-net naming; Phase 1 U3 should verify rather than assume the same prefixes cover the production board's 95 nets.
- **What is the real wall-clock/timeout behavior of `route_pcb()` at 95 nets / 149 components vs. the ~24-net corpus board it's only ever been measured against?** `RouterV6Pipeline` defaults to `max_iter=500_000`; Phase 1 U3 should record actual wall time and flag if it approaches CI timeout budgets.
- **Sequencing relative to the board-capacity brainstorm** (carried forward from the origin brainstorm's own open question 4, not resolved here): if that sibling decision results in a resize, does this plan's Phase 1/2 work get redone against new geometry, or does reaching 100%-routed-at-current-size first still have standalone value as a proof point? This plan does not block on or answer that question — it is explicitly out of scope (see Scope Boundaries).

---

## Implementation Units

### Phase 1 — Resume/Verify the Stalled Work

### U1. Verify adapter repair + net-ordering heuristic (no code change expected)

**Goal:** Formally close the brainstorm's open question 1 with a committed, reproducible verification artifact — not just this plan's prose — confirming `_build_temp_pcb` and the net-ordering heuristic are intact on the current branch.

**Requirements:** R1

**Dependencies:** None

**Files:**
- Test: `packages/temper-placer/tests/router_v6/test_adapter_repair_verification.py` (new — asserts `V6RouterAdapter` has a callable `_build_temp_pcb` bound method, not an `AttributeError`; asserts `_net_prio`-equivalent ordering behavior via a small synthetic net list with mixed `SPI_*`/`GATE_*` names)

**Approach:**
- Do not re-implement anything in `adapter.py` — this unit is a regression-proofing test over already-existing, already-correct code, so a future refactor can't silently re-break the exact bug commit `a281f865` fixed.
- Instantiate `V6RouterAdapter.from_board(...)` against a minimal synthetic board and call `rrr_route_all_nets` (or exercise `_build_temp_pcb` directly) to prove no `AttributeError`.
- Assert the sort order: given `["SPI_CLK", "GATE_H", "I_SENSE", "PWM_H"]`, `GATE_H`/`PWM_H` sort before `SPI_CLK`/`I_SENSE`.

**Test scenarios:**
- Happy: `_build_temp_pcb` is callable, returns valid KiCad s-expression content.
- Happy: signal-net names sort after power-net names under the `_net_prio` heuristic.
- Regression: if this test ever fails, it means the 2026-07-11 fix regressed — treat with the same urgency as a new bug, not a flaky test.

**Verification:** `uv run pytest packages/temper-placer/tests/router_v6/test_adapter_repair_verification.py -v` passes.

---

### U2. Verify FinePitch netclass + DRC footprint-library-table configuration on the production board

**Goal:** Confirm the already-implemented FinePitch netclass (051152e7) and footprint-library-table configuration (`KICAD7_FOOTPRINT_DIR` in `gates.py`) actually apply correctly to `pcb/temper.kicad_pcb`'s real net names and footprints — not just the corpus board they were originally verified against.

**Requirements:** R1

**Dependencies:** None

**Files:**
- Test: `packages/temper-placer/tests/io/test_finepitch_production_board.py` (new)

**Approach:**
- Parse `pcb/temper.kicad_pcb`, resolve each net's assigned netclass via the existing `netclass_loader`, and assert the production board's actual fine-pitch nets (U_MCU/J_USB pads, if present under the same or different naming conventions than the corpus board) land in `FinePitch`.
- If production-board net names diverge from the patterns the FinePitch assignment logic expects (open question above), this unit surfaces that gap rather than assuming it's covered.
- Confirm `KICAD7_FOOTPRINT_DIR` resolves footprints referenced by `pcb/temper.kicad_pcb` specifically (not just the corpus board's footprint set).

**Test scenarios:**
- Happy: production board's fine-pitch nets are assigned `FinePitch`.
- Edge: a production-board net that should be fine-pitch but isn't caught by existing name patterns is flagged (test fails loudly, not silently skipped).
- Integration: `kicad-cli pcb drc` on the production board finds the footprint library and reports no `lib_footprint_issues` caused by missing libraries (as opposed to genuine footprint problems).

**Verification:** `uv run pytest packages/temper-placer/tests/io/test_finepitch_production_board.py -v` passes or produces an actionable, specific gap report (not a silent pass).

---

### U3. Run `PlaceRouteLoop` (fixed gate dispatch) against `pcb/temper.kicad_pcb` for the first time

**Goal:** Produce the first-ever routed result for the actual production board through the router_v6/`PlaceRouteLoop` path, using the post-2026-07-18 gate-dispatch fix, and record `routed_nets`, `completion_rate`, DRC violation counts, and wall time as a reproducible artifact.

**Requirements:** R1, R2, R3

**Dependencies:** U1, U2

**Files:**
- No new source files — this unit runs the existing, verified-working pipeline.
- Modify: `power_pcb_dataset/baselines/temper_production_baseline.yaml` (populate the previously-`null` `cp_sat`/router_v6 metrics block with real measured values, or add a parallel `router_v6` block if the existing `cp_sat` block's schema doesn't fit — do not overwrite the `deterministic_pipeline` block, which measures a genuinely different pipeline and remains valid)
- Test: `packages/temper-placer/tests/router_v6/test_temper_production_board_routing.py` (new, integration — mirrors the 2026-07-10 plan's originally-planned `test_temper_board_integration.py` but against `pcb/temper.kicad_pcb`, not a corpus copy)

**Approach:**
- Construct `PlaceRouteLoop(...)` with `all_gates=True` (exercising the fixed dispatch path and all 5 default gates including `StackupGate`) against `pcb/temper.kicad_pcb`.
- Record wall time; if it approaches CI timeout budgets (see Open Questions), mark the test `@pytest.mark.slow` and document the actual measured time in the test docstring.
- Assert `completion_rate` and report it plainly whether or not it reaches 1.0 — if not 100%, classify remaining unrouted nets using the same legal-path-exists-vs-topology-failure method the 2026-07-10 plan's R1 established (not silently ignored, not assumed to be an ordering issue by default).
- Populate the baseline YAML with the actual measured numbers, replacing the `null` placeholders, with a comment noting the extraction command and date (matching the existing baseline file's documentation style).

**Test scenarios:**
- Happy: `PlaceRouteLoop.run(..., all_gates=True)` completes and reports a `completion_rate`; if `< 1.0`, unrouted nets are enumerated and classified.
- Regression: the six critical nets from the 2026-07-10 plan's R1 diagnosis (`GATE_H`, `GATE_L`, `PWM_H`, `SPI_CLK`, `SPI_MOSI`, `I_SENSE`) — if present under the same names on the production board — are checked for coexistence, same as the original Round 4 proof.
- Integration: the routed board file is valid KiCad s-expression format and round-trips through `kicad-cli pcb drc`.

**Verification:** A committed, dated baseline entry showing the real `routed_nets`/`completion_rate`/DRC-violation numbers for `pcb/temper.kicad_pcb`, obtained through the fixed gate-dispatch path — replacing the current `null`/`0` placeholders with ground truth (whatever that truth turns out to be).

---

### U4. ERC to zero on the production board

**Goal:** Run `kicad-cli pcb erc` against the routed production board (from U3) for the first time — this half of the 2026-07-10 plan's R5/R6 was never started (confirmed: zero ERC wiring anywhere in `src/`) — and fix or classify every violation found.

**Requirements:** R1

**Dependencies:** U3 (needs the routed board artifact)

**Files:**
- New: an ERC invocation wrapper, location TBD by implementer based on where `_run_drc`-equivalent helpers already live (candidate: `packages/temper-placer/src/temper_placer/validation/_erc_api.py`, mirroring `_drc_api.py`'s existing pattern)
- Test: `packages/temper-placer/tests/validation/test_erc_production_board.py` (new)

**Approach:**
- ERC is diagnostic-first, per the 2026-07-10 plan's own Key Technical Decision: run `kicad-cli pcb erc` on the routed production board, capture the violation list, and let it define the concrete follow-up work rather than guessing likely categories in advance.
- Fix violations within the board file or checker config where they're genuine issues (unconnected pins, missing power flags); if ERC reveals systemic netlist issues beyond config/power-flag scope, stop and file a follow-up rather than expanding this unit's scope silently.

**Test scenarios:**
- Happy: `kicad-cli pcb erc pcb/temper.kicad_pcb` (post-routing) returns 0 violations.
- Edge: a missing/misconfigured ERC environment produces an explicit "could not measure" result, not a silent 0-violation pass (same fail-closed discipline as R5).

**Verification:** Literal-zero ERC on the routed production board, measured against a properly-configured `kicad-cli pcb erc` invocation, with every fix traceable to a real diagnosed cause.

---

### U5. Supplement `test_regression_drc.py` with a production-board routing-quality measurement

**Goal:** Resolve brainstorm R3's decision (supplement, not repoint or duplicate) by adding a production-board-targeted test function alongside the existing corpus-board tests, sharing helpers, with the relationship between the two documented.

**Requirements:** R3

**Dependencies:** U3, U4

**Files:**
- Modify: `packages/temper-placer/tests/placer/cp_sat/test_regression_drc.py` (add `PRODUCTION_BOARD_PATH = REPO_ROOT / "pcb" / "temper.kicad_pcb"` and two new test functions: `test_production_board_drc_regression`, `test_production_board_routing_drc_regression`, parameterizing/reusing the existing `_run_drc`, `_count_errors_by_type`, `_load_pcl_constraints`, `_load_zones` helpers rather than duplicating them)

**Approach:**
- Add module-level docstring text explaining the corpus-vs-production relationship: the corpus board is a fast, stable proxy (~24 nets, historically the only board this gate has measured); the production board is the real ship target (95 nets, first measured in this plan's U3/U4).
- New test functions mirror the existing two (`test_golden_board_drc_regression`, `test_golden_board_routing_drc_regression`) structurally, but target `PRODUCTION_BOARD_PATH` and use thresholds seeded from U3/U4's actual measured baseline (not copied blindly from the corpus board's `<=15`/`==0` thresholds, which were calibrated against a different, smaller netlist).
- Mark both new tests `@pytest.mark.slow` (and `@pytest.mark.routing` for the routing one), matching the existing corpus tests' markers, so CI scheduling is unaffected by default.

**Test scenarios:**
- Happy: both new tests run against `pcb/temper.kicad_pcb` and assert against thresholds derived from U3/U4's real measurement, not fabricated numbers.
- Regression: if a future change to placement/routing regresses the production board specifically (independent of the corpus board), only the new tests fail — proving the supplement actually adds coverage the corpus test doesn't have.

**Verification:** `uv run pytest packages/temper-placer/tests/placer/cp_sat/test_regression_drc.py -v -k production` passes against thresholds grounded in U3/U4's real numbers; the existing corpus-board tests are unmodified and still pass.

---

### U6. Phase 1 anti-false-zero guard

**Goal:** Apply R5 to every claim made in Phase 1 (U1-U5): assert the constraint set used was unchanged-or-visibly-changed from the proven baseline, and that every gate reporting "clean"/"zero" was actually measured, not `UNMEASURED` misread as clean.

**Requirements:** R5

**Dependencies:** U1, U2, U3, U4, U5

**Files:**
- Test: `packages/temper-placer/tests/router_v6/test_phase1_anti_false_zero.py` (new, reusing the 2026-07-10 plan's U5 pattern)

**Approach:**
- Diff the constraint YAML (`configs/constraints/temper_induction_cooker.yaml`, `configs/netclass_rules.yaml`) used in U2/U3 against the versions already in the repo pre-Phase-1 — assert no relaxation, or if changed, that the change is visible/documented (not silently loosened to buy a number).
- Assert U3's DRC/ERC gate results are `CLEAN`, not `UNMEASURED` misread as `CLEAN` — check the gate's actual status enum, not just a violation count of zero (a library-path failure that causes kicad-cli to silently check nothing would report 0 violations and must not pass this guard).
- Assert every claim made in this plan's Phase 1 write-up (routed_nets, completion_rate, ERC=0) is traceable to a specific test/artifact produced by U1-U5, not asserted from memory or extrapolation.

**Test scenarios:**
- Happy: all Phase 1 anti-false-zero conditions pass.
- Error: a relaxed constraint triggers the guard.
- Error: a misconfigured DRC/ERC gate (missing footprint library, missing kicad-cli) triggers the guard as `UNMEASURED`, not a false `CLEAN`.

**Verification:** Phase 1's claims (production-board routing status, ERC status) pass the anti-false-zero guard.

---

### Phase 2 — Scope and Close the Multi-Layer Escalation

### U7. Audit the existing W2 plan's real completion state

**Goal:** Produce a precise, evidence-based completion map of `docs/plans/2026-07-08-004-feat-4-layer-functional-stackup-plan.md`'s 6 units against the current codebase (extending this plan's own preliminary audit in Context & Research), and determine which of `layer_assignment.py` vs. `channel_mapping.py`'s two layer-resolution mechanisms actually governs A* routing decisions.

**Requirements:** R4

**Dependencies:** None (can run in parallel with Phase 1)

**Files:**
- No source changes — this is an investigation unit.
- Output: an update to `docs/plans/2026-07-08-004-feat-4-layer-functional-stackup-plan.md`'s own status/units (mark U1/U2 as verified-done with commit references; mark U3 as partial with the specific missing piece; mark U4/U5/U6 with their real state) — this plan does not own that document but should leave it accurate for future readers, per this repo's convention of not letting plans silently drift from reality (mirrors the exact problem this whole plan exists to fix for the 2026-07-10 plan).

**Approach:**
- Trace `RouterV6Pipeline`'s A* kernel (`pipeline.py`) to determine whether it consults `layer_constraints` (from `layer_assignments_from_netclass`) or `channel_mapping._assign_layer()` or both, and in what order/precedence.
- For each W2 unit (U1-U6), re-verify file-by-file presence and wiring (this plan's Context & Research section is a starting point, not the final word — confirm test coverage exists and passes for whatever is present).
- Map each remaining W2 gap (U3's missing `net_currents.yaml`, U4, U5, U6's file-location mismatch) to which of the brainstorm's R4 violation categories it could plausibly affect: `clearance`/`tracks_crossing`/`solder_mask_bridge` (layer-crowding symptoms, per the brainstorm's own hypothesis) vs. `shorting_items`/`diff_pair_gap_out_of_range` (individually diagnosed in U8).

**Test scenarios:**
- N/A (investigation unit) — deliverable is the completion map, not new tests.

**Verification:** A written completion map (in the updated W2 plan doc) precise enough that U9 can pick specific, justified gaps to close rather than guessing.

---

### U8. Individually diagnose `shorting_items` and `diff_pair_gap_out_of_range`

**Goal:** Per brainstorm R4, determine the real cause of these two violation categories on the corpus board's routing-DRC run (48-88 `shorting_items`, 1-4 `diff_pair_gap_out_of_range`) — genuine netlist/placement issues needing individual fixes, not something a routing layer alone resolves.

**Requirements:** R4

**Dependencies:** None (can run in parallel with U7)

**Files:**
- Test/diagnostic script: `packages/temper-placer/tests/router_v6/test_shorting_diffpair_diagnosis.py` (new) or a scratch diagnostic script, implementer's choice, as long as findings are captured in a `docs/solutions/` entry per this repo's compounding-learnings convention.

**Approach:**
- Run the corpus-board routing DRC (`test_golden_board_routing_drc_regression`'s pipeline, or a standalone re-run) and extract the specific `shorting_items` violation details (which nets/pads are shorting, per the existing `description` field parsing pattern in `test_regression_drc.py`).
- For each shorting instance: is it two different-net traces genuinely touching (real short — layer separation would fix it), or an intra-component false-positive (same pattern `test_golden_board_drc_regression` already filters via its `PLACEMENT_IRREDUCIBLE_TYPES`/intra-component logic)?
- For `diff_pair_gap_out_of_range`: check whether the USB D+/D- pair (or whichever diff pair triggers this) has W2 U5's differential-pair constraints applied at all (per U7's finding, U5 is likely unstarted) — if the constraint infrastructure was never wired for this pair, that's the direct cause, not a layer-crowding symptom.

**Test scenarios:**
- Diagnostic: each `shorting_items` instance is classified as genuine-short vs. false-positive vs. resolves-with-layer-separation.
- Diagnostic: `diff_pair_gap_out_of_range` is attributed to a specific, named cause (missing constraint wiring, wrong geometry, or genuine routing crowding).

**Verification:** A `docs/solutions/` entry documenting the diagnosis, informing whether U9 needs to touch W2 U5 (diff-pair) specifically, or whether `shorting_items` needs a fix outside W2's scope entirely.

---

### U9. Close the highest-leverage W2 gaps identified in U7/U8

**Goal:** Close the specific W2 (2026-07-08-004) units or partial-units that U7's audit and U8's diagnosis identify as actually moving the routing-DRC violation count toward zero — scoped by evidence, not designed from scratch.

**Requirements:** R4

**Dependencies:** U7, U8

**Files:** Determined by U7's findings — likely candidates per the preliminary audit (Context & Research): completing W2 U3 (`configs/net_currents.yaml` + wiring the width calculator's current input), and/or W2 U5 (differential-pair constraints) if U8 attributes `diff_pair_gap_out_of_range` to missing constraint wiring, and/or resolving the `layer_assignment.py`/`channel_mapping.py` dual-mechanism question from U7 if that's found to be causing incorrect layer decisions.

**Approach:**
- This unit is intentionally scoped at the "what to close, and why" level, not "how" — per the brainstorm's own Scope Boundaries deferring full multi-layer implementation detail to a design pass. That design pass is W2 itself; this unit executes the specific remaining W2 units U7/U8 justify, following W2's own already-written Approach/Patterns-to-follow sections for whichever units are selected.
- Do not attempt all of W2 U3-U6 speculatively — only the units U7/U8 tie to an actual measured violation category. If U7/U8 find none of the remaining W2 gaps explain the 261/443 violations, this unit's job becomes documenting that finding and identifying what does (which may fall outside W2's scope entirely, e.g. the `_write_routes_to_content()` MST/plane-net stitching logic from commit `598d3a66`, called out in that commit's own message as a source of DRC violations).

**Test scenarios:** Inherited from whichever W2 unit(s) are closed (see that plan's own Test scenarios for U3/U4/U5/U6).

**Verification:** Whichever W2 unit(s) are closed pass their own plan's stated verification command; the corpus-board routing-DRC violation count (261/443 baseline) is re-measured and shows a documented, attributed improvement (not just a number that moved).

---

### U10. Phase 2 anti-false-zero guard + re-measurement

**Goal:** Apply R5 to Phase 2's claims: re-run both the corpus-board routing-DRC gate and the U5 production-board routing-DRC gate after U9's changes, and verify any improvement is real (measured against an unchanged-or-visibly-changed constraint set, properly-configured gate) — not a relaxed threshold or a misconfigured measurement.

**Requirements:** R4, R5

**Dependencies:** U9

**Files:**
- Test: extends `test_phase1_anti_false_zero.py` (U6) or a new `test_phase2_anti_false_zero.py`, implementer's choice.

**Approach:**
- Re-run `test_golden_board_routing_drc_regression` (corpus) and the new production-board equivalent (U5) after U9's changes; record the new violation counts by category, and the delta from the 261/443 baseline.
- Assert the delta is attributable to U9's specific changes (e.g., "shorting_items dropped from 48 to 0 because U8 found and fixed a genuine net-adjacency short" — not "violations dropped because a threshold was loosened").
- If U9 did not reach zero, the remaining violations must be diagnosed-and-classified per the same discipline as the rest of this plan (legal-path-exists vs. genuine topology failure, or its DRC-violation equivalent), not silently left unexplained.

**Test scenarios:**
- Happy: post-U9 violation counts are measured, categorized, and each delta from baseline is attributed to a specific U9 change.
- Error: a threshold relaxation (rather than a real fix) triggers the guard.

**Verification:** A final, dated measurement (corpus + production board) with every closed violation traceable to U7's audit or U8's diagnosis — the same traceability discipline the 2026-07-10 plan's R7 established for Phase 1.

---

## System-Wide Impact

- **Interaction graph:** Phase 1 (U1-U6) and Phase 2 (U7-U10) are largely independent — U7/U8 can start in parallel with Phase 1 since they investigate the corpus board, which already exists and routes. U9 depends on both U7 and U8's findings. U5 (production-board test supplement) depends on Phase 1's U3/U4 producing real baseline numbers to seed thresholds with.
- **Behavior changes:** Phase 1 changes no router/placer logic — it is verification plus a first production-board run plus ERC wiring (new, additive). Phase 2's U9 may modify `router_v6` layer-assignment or width-calculation logic, scoped to whatever U7/U8 justify — no speculative changes.
- **Error propagation:** All new gates (ERC in U4, production-board DRC in U5) follow the existing fail-closed discipline: `UNMEASURED` on a misconfigured/unavailable check, never a silent `CLEAN`.
- **Unchanged invariants:** The proven hard-constraint set (netclass `SEPARATED`, courtyard, edge margin, creepage) is unchanged by this plan. The corpus-board `test_regression_drc.py` tests are not modified in their assertions — only supplemented (U5) or benefit from Phase 2 fixes (U9/U10) that also apply to the corpus board's own measurement.
- **Sibling-plan boundary:** This plan does not touch board geometry, BOM, or component count — those are exclusively the board-capacity/BOM decision plan's domain (parallel, non-blocking, per Scope Boundaries).

---

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| Production board (95 nets, 149 components) times out or behaves qualitatively differently than the corpus board (~24 nets) it was tuned against | U3 records real wall time and flags CI-timeout risk explicitly; `RouterV6Pipeline`'s `max_iter=500_000` default is a known-adjustable knob if needed |
| Production board's net-naming conventions don't match the `_SIG`/`_PWR`/FinePitch pattern heuristics tuned on the corpus board | U2 explicitly tests for this gap rather than assuming coverage; if found, is a small, targeted follow-up (extend the pattern lists), not a redesign |
| W2's `layer_assignment.py` vs. `channel_mapping.py` duality turns out to mean the "already wired" multi-layer routing isn't actually taking effect where it matters | U7 traces the actual A* kernel code path before U9 commits to any fix, avoiding wasted work on the mechanism that isn't governing routing decisions |
| `shorting_items`/`diff_pair_gap_out_of_range` diagnosis (U8) reveals a genuine placement-topology or netlist defect outside this plan's scope | U8 is diagnostic-first by design — if the root cause is out of scope (e.g., a netlist error), it's documented and handed off, not silently absorbed into scope creep |
| ERC (U4) reveals systemic netlist issues beyond config/power-flag scope | Same diagnostic-first discipline as the 2026-07-10 plan's U4: scope adapts to what the run finds; anything beyond config/power-flag fixes gets a follow-up ticket, not silent scope expansion |
| Board-capacity/BOM sibling decision lands mid-work and results in a resize | Explicitly out of scope and non-blocking per this plan's own framing; if it happens, routing work on the current geometry may need re-running, acknowledged as a known, accepted risk rather than a blocker |

---

## Success Metrics

- **Phase 1:** `pcb/temper.kicad_pcb` has a real, measured `routed_nets`/`completion_rate` (replacing `null`/`0` placeholders) obtained through the fixed `PlaceRouteLoop` gate-dispatch path; ERC = 0 on the routed production board; a production-board routing-quality CI gate exists and runs.
- **Phase 2:** The corpus-board routing-DRC violation count trends measurably down from the 261 (local) / 443 (CI) baseline, with every closed violation category traceable to a specific U7 audit finding or U8 diagnosis — not an unexplained number change.
- **Cross-cutting (R5):** every "100% routed" / "0 DRC" / "0 ERC" claim in this plan's final state passes its phase's anti-false-zero guard (U6, U10).

---

## Sources & References

- **Origin document:** [docs/brainstorms/2026-07-18-board-routing-completion-requirements.md](../brainstorms/2026-07-18-board-routing-completion-requirements.md)
- **Stalled plan being reassessed:** [docs/plans/2026-07-10-001-feat-finish-the-board-plan.md](2026-07-10-001-feat-finish-the-board-plan.md)
- **Existing active multi-layer plan resumed in Phase 2:** [docs/plans/2026-07-08-004-feat-4-layer-functional-stackup-plan.md](2026-07-08-004-feat-4-layer-functional-stackup-plan.md)
- **Single-layer-first sequencing (origin of the "W2" deferral):** [docs/brainstorms/2026-07-08-single-layer-route-requirements.md](../brainstorms/2026-07-08-single-layer-route-requirements.md)
- **261/443 violation evidence:** [docs/solutions/test-failures/regression-drc-tests-missing-zone-loop-wiring.md](../solutions/test-failures/regression-drc-tests-missing-zone-loop-wiring.md)
- **Gate-dispatch bug fix:** [docs/solutions/logic-errors/place-route-loop-run-ignores-constructor-gates-without-all-gates-flag.md](../solutions/logic-errors/place-route-loop-run-ignores-constructor-gates-without-all-gates-flag.md)
- **Sibling, non-blocking parallel work:** [docs/brainstorms/2026-07-18-board-capacity-bom-decision-requirements.md](../brainstorms/2026-07-18-board-capacity-bom-decision-requirements.md)
- **Key commits verified as ancestors of current `HEAD`:** `a281f865` (adapter repair + ordering), `598d3a66` (100% F.Cu connectivity + route writing), `06435acb` (W2 U2 net-to-layer assignment), `051152e7` (FinePitch netclass), `a0581a49` (57% DRC violation reduction via collinear merge), `6d8e333a` (zero-width track fix).
- **Key code:** `packages/temper-placer/src/temper_placer/router_v6/adapter.py`, `layer_assignment.py`, `channel_mapping.py`, `net_classification.py`; `packages/temper-placer/src/temper_placer/placer/cp_sat/loop.py`; `packages/temper-placer/tests/placer/cp_sat/test_regression_drc.py`; `power_pcb_dataset/baselines/temper_production_baseline.yaml`; `pcb/temper.kicad_pcb`.
