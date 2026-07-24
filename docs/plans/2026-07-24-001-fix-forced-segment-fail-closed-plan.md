---
title: "fix: Uniform Fail-Closed Forced-Segment Disposition"
type: fix
status: active
date: 2026-07-24
origin: docs/brainstorms/2026-07-24-router-forced-segment-fail-closed-requirements.md
---

# fix: Uniform Fail-Closed Forced-Segment Disposition

## Summary

This plan generalizes the already-shipped HV/AC-only fail-closed gate in the plain A* router (`_allow_forced_segments()`) into an unconditional close for every net class — a smaller change than expected, since the surrounding forced-segment interception plumbing turns out to already be net-class-agnostic. It also fixes a newly-discovered, pre-existing test-coverage gap for that gate, adds property-test coverage sweeping all net classes, retires the now-dead forced-segment success path, and verifies the result with a real production-board DRC re-measurement rather than trusting green unit tests.

---

## Problem Frame

See origin: `docs/brainstorms/2026-07-24-router-forced-segment-fail-closed-requirements.md` for the full problem history. In short: the plain A* pathfinder's forced-segment fallback still fabricates zero-clearance copper for every net outside the HV/AC-only gate shipped earlier this session, which is why `shorting_items` didn't improve (199 → 200) after the netclass-clearance wiring fix landed. This plan closes that gap.

---

## Requirements

- R1. When the plain A* pathfinder's forced-segment fallback would trigger for any net, the net must be reported as unrouted/incomplete rather than having a zero-clearance line drawn, regardless of net class.
- R2. The fail-closed policy applies uniformly across every net class — no exemption remains for any class.
- R3. The unrouted/incomplete disposition must be clearly distinguishable from a genuine successful route in the router's result and reporting.
- R4. The router's completion count reflects only genuinely, safely routed nets after this ships; the resulting number, even if lower than today's, becomes the new honest baseline with no compatibility shim.
- R5. Downstream tracks (finish-the-board DRC/ERC gate, hybrid-pour-stitch promotion decision) are not blocked; they measure against the new baseline with no special handling.

**Origin acceptance examples:** AE1 (covers R1, R2, R3), AE2 (covers R4, R5)

---

## Scope Boundaries

- Re-routing or re-closing the nets that flip to unrouted as a result of this change — separate follow-up work.
- CI integration of the DRC/ERC anti-false-zero guard (`docs/plans/2026-07-23-001-feat-finish-the-board-drc-erc-guard-plan.md`).
- The `enable_all_pad_tree`/`enable_zone_pours` default-on promotion decision (`docs/plans/2026-07-22-001-feat-hybrid-pour-trace-stitch-plan.md`).
- Broader pathfinding/ripup-reroute algorithm improvements to reduce how often the forced-segment fallback is needed in the first place.
- The tree-executor's own routing path (`execute_terminal_tree`) — it already hardcodes fail-closed behavior independently of the gate this plan changes.
- Full IEC 60335-1 compliance sign-off.
- Wiring the plain A* path into the richer `NetDisposition` enum (`ROUTED`/`INCOMPLETE`/`PLANE_CONNECTED`/`EXEMPT`/`FAILED`) used by the tree executor — the existing `failed_nets`/`unrouted_nets` machinery already satisfies R3; full unification is a larger architectural change (see Key Technical Decisions).
- The zone-pour cross-class clearance issue (`docs/solutions/architecture-patterns/zone-pour-bounding-box-shorting-regression-2026-07-21.md`, `docs/solutions/logic-errors/missing-cross-class-zone-clearance-regression-2026-07-21.md`) — a separate, adjacent mechanism that may account for some residual `shorting_items` this plan does not touch.

### Deferred to Follow-Up Work

- Removing the now-permanently-empty `PathfindingResult.total_forced_segments` and `RoutingResult.forced_segment_nets` fields: a larger API-surface change, tracked as a future dead-code sweep rather than done here.

---

## Context & Research

### Relevant Code and Patterns

- `packages/temper-placer/src/temper_placer/router_v6/_astar_reconstruct.py:184-215` — `_allow_forced_segments()`, the single function this plan changes. Reads `safety_category` via `design_rules.get_rules_for_net(net_name)`; returns `False` (disallow) when `tree_route_active`, on exception, or when `safety_category in ("HV", "AC")`; otherwise returns `True` (allow).
- Only one dynamic call site evaluates this gate: `attempt_route()` at `_astar_reconstruct.py:392`. A second call at line 434 is a post-hoc re-check of the same gate. All other references (`_astar_reconstruct.py:780`, `_astar_reconstruct.py:888`, `_astar_reconstruct.py:1112`, and their internal passthroughs at 1155/1172) are function parameters that thread the boolean through unchanged — none need logic changes.
- `_astar_reconstruct.py:829-843` (`_astar_route`) and `:1054-1068` (`_astar_route_multilayer`) already correctly early-return a failed-segment result (no raise) when `allow_forced_segments=False` and no legal path exists. `_astar_reconstruct.py:409-448` (`attempt_route`) already intercepts any resulting forced segment and converts it into a recorded failure. This plumbing is net-class-agnostic today — no change needed here.
- `packages/temper-placer/src/temper_placer/router_v6/terminal_tree_execution.py:123` hardcodes `allow_forced_segments=False` for tree-executed nets, independent of the gate this plan generalizes — confirms this is established, out-of-scope precedent, not something to touch.
- `packages/temper-placer/src/temper_placer/router_v6/net_classification.py:22-27` — `GROUND_NET_PATTERNS`/`POWER_NET_PATTERNS`/`HV_NET_PATTERNS`, consulted by `_should_route()` (`_astar_reconstruct.py:168-181`) to exclude certain nets from A* entirely (handled by zone pours instead). The brainstorm's illustrative nets (`vcc`, `+3V3`, `PWR_RTN`) substring-match `POWER_NET_PATTERNS`, meaning they may already be excluded from A* and thus unaffected by this fix — see U5.
- `packages/temper-placer/src/temper_placer/router_v6/connectivity.py:28-33` — the `NetDisposition` `StrEnum` (`ROUTED, INCOMPLETE, PLANE_CONNECTED, EXEMPT, FAILED`), the canonical disposition type, currently wired only for the tree-executor path.
- `packages/temper-placer/src/temper_placer/router_v6/routing_results.py:45-98, 101-233` — `RoutingResults.compile_routing_results()`; the plain A* path's failures already flow through `failed_nets` (direct passthrough at line 226) into the top-level `RoutingResult.unrouted_nets` via `_build_routing_result()` (`_adapter_convert.py:813-905`, reading `routing_results.failed_nets` at line 827).
- `packages/temper-placer/tests/router_v6/test_adapter.py:1146-1283` — `TestHVACForcedSegmentFailClosed`, the existing test for the HV/AC-only gate. Its net names (`"SW_NODE"`, `"AC_L"`) are themselves excluded from A* by `_should_route()`'s HV pattern matching before `_allow_forced_segments` is ever invoked — these tests currently pass vacuously and do not exercise the gate's decision logic. Fixed in U2.
- The same test class also contains `test_signal_net_still_allows_forced_segments`, which builds a Signal-class net (`"SPI_MOSI"`, which passes `_should_route()` and genuinely reaches the gate) on a fully blocked grid and asserts it still gets a forced segment (`forced_segment_count > 0`, present in `routed_paths`). This test is not vacuous and directly contradicts R2 once U1 lands — it must be updated in U2, or it will fail immediately after U1's change lands, before U2 runs.
- `packages/temper-placer/tests/router_v6/test_astar_route_multilayer_via_fallback.py:203-248` (`test_3d_fallback_legality_uses_each_netclass_via_envelope`) — the pattern to follow for constructing real `DesignRules`/`NetClassRules` and sweeping `net_class=st.sampled_from(_CONFIGURED_NET_CLASSES + (None,))`.
- `packages/temper-placer/tests/router_v6/astar_property_strategies.py` — shared Hypothesis strategies (`grids()`, `start_goal_pairs()`, `obstacle_perturbations()`) to build on for U3.

### Institutional Learnings

- `docs/solutions/logic-errors/route-pcb-design-rules-never-reaches-a-star-engine.md` — the direct predecessor bug and fix; establishes the "verify at the real consumption point with a runtime probe, not code review alone" discipline this plan's U1/U5 follow, and that a config-wiring fix that looks correct by inspection can still be a complete no-op.
- `docs/solutions/architecture-patterns/two-tier-acceptance-gate-unsat-surfacing-2026-07-05.md` — fail-closed/UNMEASURED discipline: absence of verification must never silently read as success; this plan's gate already follows this (`except Exception: return False`), and the generalization preserves it.
- `docs/solutions/logic-errors/parsed-stub-missing-nets-silently-disables-layer-constraints-2026-07-22.md` — production-board measurement fixtures missing `.nets` have silently produced misleading before/after readings in this exact router before; U5 must confirm its fixture carries real net data.
- `docs/solutions/best-practices/lie-proof-the-green-before-believing-it-2026-07-11.md` — measure a plausible root-cause claim before believing it; directly informs U5's real DRC re-measurement requirement.
- `docs/solutions/best-practices/hypothesis-invariant-test-suite-pattern-2026-06-28.md` — the established PBT convention (shared strategies, one theorem class per file, `@pytest.mark.property` + `@given` + `@settings(max_examples=100, deadline=30000)`) that U3 follows.
- `docs/solutions/architecture-patterns/router-v6-all-pad-connectivity-foundation-2026-07-19.md` — establishes the `NetDisposition`-based "truthful completion" precedent this plan's disposition philosophy matches, without requiring full enum unification.
- `docs/brainstorms/2026-07-23-property-test-hardening-requirements.md` — origin of the current HV/AC-only gate; explicitly considered and rejected raise-on-failure and visibility-only (non-fail-closed) alternatives in favor of the same fail-closed mechanism this plan now generalizes.

### External References

None — strong local precedent (the existing HV/AC gate, the tree-executor's `NetDisposition` philosophy, the established Hypothesis/PBT convention) fully covers this change; external research was skipped.

---

## Key Technical Decisions

- **Single-function generalization, no plumbing changes**: only `_allow_forced_segments()`'s decision logic changes. The interception/reporting plumbing (`attempt_route`, `_astar_route`, `_astar_route_multilayer`) is already net-class-agnostic and needs no modification. Rationale: confirmed by research — this is the smallest correct diff, and matches the original gate's own "least code, reuses established pattern" reasoning.
- **Reuse `failed_nets`/`unrouted_nets`, don't wire into `NetDisposition`**: R3's "distinguishable disposition" requirement is already satisfied by the existing `RoutingFailureReport`/`RoutingResult.unrouted_nets` pipe. Full `NetDisposition` unification across both routing paths is a larger architectural change, explicitly deferred per AGENTS.md's Bug-Triage Rule (R22) against inlining a redesign into a bugfix.
- **Fix the vacuous HV/AC test coverage inline, not separately**: discovered as a direct byproduct of this plan's own research, in the same file/code path this plan must correctly test anyway. Leaving a known-vacuous test beside a newly-correct one would be misleading.
- **Remove the directly-caused dead branch, defer field removal**: the `"congestion_forced"` success branch becomes provably unreachable and is removed (U4). `total_forced_segments`/`forced_segment_nets` become permanently empty but are left in place — removing them touches more API surface for no behavioral gain and is tracked as separate follow-up work.
- **Verify with real DRC, not just green tests**: per the "lie-proof the green" and "parsed-stub missing nets" learnings, both of which document this exact router producing misleading "no change" readings from under-measured or improperly-fixtured tests.

---

## Open Questions

### Resolved During Planning

- Which call sites need to change to generalize the gate: only the one dynamic call site (`attempt_route` at `_astar_reconstruct.py:392`) evaluates `_allow_forced_segments()`; all other references are unaffected parameter passthroughs.
- Whether the plain A* failure needs a new result type/field to satisfy R3: no — `failed_nets`/`unrouted_nets`/`RoutingFailureReport` already provide this, confirmed via `_build_routing_result()`'s existing passthrough.

### Deferred to Implementation

- Exactly which nets on the current production board flip from routed to unrouted, and whether the brainstorm's illustrative nets (`vcc`, `+3V3`, `PWR_RTN`) are actually affected or are excluded from A* entirely by `_should_route()`'s power-net pattern matching — resolved by U5's live re-measurement, not assumed here.
- Whether `_allow_forced_segments()` should be simplified to an unconditional constant, have its now-unused parameters removed, or be deleted entirely in favor of passing the disallow value directly at its one call site — a style choice with no behavioral difference; U1's implementer decides, leaning toward keeping a named function for readability given the safety-critical nature of this gate.

---

## Implementation Units

### U1. Generalize the forced-segment fail-closed gate

**Goal:** Make `_allow_forced_segments()` fail closed unconditionally for every net, removing the `safety_category`-based HV/AC-only branch.

**Requirements:** R1, R2 (Covers AE1)

**Dependencies:** None

**Files:**
- Modify: `packages/temper-placer/src/temper_placer/router_v6/_astar_reconstruct.py` (`_allow_forced_segments`, ~lines 184-215)
- Test: `packages/temper-placer/tests/router_v6/test_adapter.py` (or a new dedicated test module, implementer's call)

**Approach:**
- Collapse the function so it disallows forced segments unconditionally — for every net class, every `tree_route_active` value, and every `design_rules` state (including the currently-dead `None` branch, which should also fail closed rather than default-allow) — removing the class-based branching entirely.
- Keep a short comment on the function explaining the fail-closed rationale and referencing this plan, given the safety history here (two prior sessions' bugs in this exact area).

**Execution note:** Write the failing test first — a net that should now fail closed but currently doesn't under the HV/AC-only gate — before changing `_allow_forced_segments()`. Matches this codebase's established TDD discipline for gate/wiring changes.

**Patterns to follow:**
- The existing fail-closed `except Exception: return False` branch already in the function — the generalization extends the same posture to the rest of the logic rather than introducing a new one.

**Test scenarios:**
- Happy path (Covers AE1): given a net that passes `_should_route()` and is not tree-executed, when the plain A* pathfinder cannot find a legal, clearance-respecting path, the net is reported as failed (`failed_nets`/`RoutingFailureReport`) and no route with `forced_segment_count > 0` reaches `routed_paths`.
- Edge case: a congested net with a genuinely available legal path still routes normally — the gate must not block routable nets.
- Edge case: a previously HV/AC-exempted net still fails closed the same way via the general path, confirming the generalization didn't accidentally special-case break the safety-critical case.
- Error path: `design_rules is None` or `get_rules_for_net()` raises — the gate still disallows, matching the two-tier UNMEASURED discipline.
- Integration: end-to-end through `route_pcb()` confirms the disposition change is visible all the way to `RoutingResult.unrouted_nets`, not just at the gate function's own boundary — per the design-rules-wiring lesson that a correct-looking unit change can still be a no-op downstream.

**Verification:** A runtime check confirms `_allow_forced_segments()` disallows for a representative sweep of net classes and edge inputs (not only HV/AC), and that a disallowed net never appears in `routed_paths` with `forced_segment_count > 0`.

---

### U2. Fix vacuous and now-contradicted HV/AC forced-segment test coverage

**Goal:** Repair `TestHVACForcedSegmentFailClosed` so its net names actually reach `attempt_route`/`_allow_forced_segments` instead of being excluded pre-A* by `_should_route()`'s HV pattern matching, and update the class's `test_signal_net_still_allows_forced_segments` test, which currently asserts the opposite of R2 (that a Signal-class net should still get a forced segment) and will fail as soon as U1 lands.

**Requirements:** R2, R3 (retains dedicated coverage for the safety-critical case; corrects a test that would otherwise contradict R2)

**Dependencies:** U1

**Files:**
- Modify: `packages/temper-placer/tests/router_v6/test_adapter.py` (`TestHVACForcedSegmentFailClosed`, including `test_signal_net_still_allows_forced_segments`)

**Approach:**
- Choose net names/fixtures that pass `_should_route()` (don't substring-match `GROUND_NET_PATTERNS`/`POWER_NET_PATTERNS`/`HV_NET_PATTERNS`) while still carrying an HV/AC-equivalent safety classification via `design_rules`, so the test genuinely drives execution into the gate rather than being filtered out earlier.
- Reframe the test's intent from "HV/AC nets specifically get gated" (no longer a distinct code path after U1) to "the fail-closed gate reliably rejects a safety-critical case via a real, non-vacuous code path."
- Flip `test_signal_net_still_allows_forced_segments`'s assertions to match R2's uniform behavior (the net now lands in `failed_nets`, not `routed_paths` with `forced_segment_count > 0`), and rename it to state that no net class is exempt post-generalization (e.g. `test_signal_net_also_fails_closed`).

**Patterns to follow:**
- `packages/temper-placer/tests/router_v6/test_astar_route_multilayer_via_fallback.py:203-248` for constructing real `DesignRules`/`NetClassRules` from config.

**Test scenarios:**
- Happy path (Covers AE1): a net name that passes `_should_route()` and carries a safety-relevant classification reaches `attempt_route`, hits an unroutable grid, and is reported as failed — proving the test is no longer vacuous.
- Happy path (Covers AE1): the renamed signal-net test confirms a Signal-class net on a fully blocked grid now lands in `failed_nets`, not `routed_paths`, matching every other net class.

**Verification:** Reverting U1 locally causes both tests to fail (a mutation-style sanity check confirming the tests actually discriminate gate behavior, not run permanently in CI).

---

### U3. Property test: no forced segment survives for any net class

**Goal:** A Hypothesis property test sweeping representative net classes proving that whenever the plain A* pathfinder cannot find a legal path, the net is reported failed with zero clearance-violating geometry, never a forced segment.

**Requirements:** R1, R2 (Covers AE1)

**Dependencies:** U1

**Files:**
- Create or extend: `packages/temper-placer/tests/router_v6/` — add to an existing `test_astar_*_pbt.py`-shaped file (e.g. alongside `test_astar_dijkstra_oracle_pbt.py` / `test_astar_inductive_ladder.py`) rather than introducing a new file convention
- Modify if needed: `packages/temper-placer/tests/router_v6/astar_property_strategies.py` (a strategy generating no-legal-path grids paired with varied net classes, if none suitable exists)

**Approach:**
- Build on existing composable strategies (`grids()`, `start_goal_pairs()`); sweep net class similarly to `test_3d_fallback_legality_uses_each_netclass_via_envelope`'s `st.sampled_from(_CONFIGURED_NET_CLASSES + (None,))`.

**Execution note:** This test should fail (red) against the pre-U1 gate and pass (green) after — confirm both, not just the green state.

**Patterns to follow:**
- `docs/solutions/best-practices/hypothesis-invariant-test-suite-pattern-2026-06-28.md` — one theorem class per file, `@pytest.mark.property` + `@given(...)` + `@settings(max_examples=100, deadline=30000)`.

**Test scenarios:**
- Happy path (Covers AE1): for a swept range of net classes and no-legal-path grid configurations, the resulting route is never returned with `forced_segment_count > 0` inside `routed_paths` — it always lands in `failed_nets`/`failure_reports` instead.
- Edge case: a net with no netclass assignment at all (falls through to "Default") still fails closed, not silently allowed through a missing-classification loophole.

**Verification:** The property test demonstrably discriminates old vs. new behavior (fails against pre-U1 code, passes against post-U1 code).

---

### U4. Remove the now-unreachable forced-segment success path

**Goal:** Delete the `"congestion_forced"` success branch, now provably unreachable once U1 lands; flag `total_forced_segments`/`forced_segment_nets` as vestigial without removing them.

**Requirements:** Direct consequence of R1/R2 — cleanup, not a new requirement.

**Dependencies:** U1

**Files:**
- Modify: `packages/temper-placer/src/temper_placer/router_v6/_astar_reconstruct.py` (the `"congestion_forced"` branch, ~line 484-486)
- Modify: a short comment near `PathfindingResult.total_forced_segments` and wherever `RoutingResult.forced_segment_nets` is populated in `_adapter_convert.py`, noting the fields are now always empty pending future removal

**Approach:**
- Grep across `src/`, `tests/`, `scripts/`, and `benchmarks/` (not just `src/`/`tests/`) for `"congestion_forced"` before deleting — this repo has been bitten before by a narrower grep scope missing a real caller.
- Do not remove `total_forced_segments`/`forced_segment_nets` themselves — larger API-surface change, deferred (see Scope Boundaries).

**Test scenarios:**
- Test expectation: none -- pure dead-code removal with no remaining behavioral path; the U1-U3 test suite already proves the branch is unreachable.

**Verification:** Repo-wide grep (including `scripts/` and `benchmarks/`) confirms no remaining reference to `"congestion_forced"`; full test suite still passes.

---

### U5. Verify with a real production-board re-measurement

**Goal:** Re-run the router on the current production board with a properly `.nets`-carrying fixture and real `kicad-cli` DRC, establishing the new honest completion count and `shorting_items` baseline, and confirming whether the brainstorm's illustrative nets are actually affected by this change.

**Requirements:** R4, R5 (Covers AE2)

**Dependencies:** U1, U2, U3, U4

**Files:**
- No production source changes. Run existing measurement tooling (e.g. `test_zone_pour_production_measurement.py` / `test_regression_drc.py` / `test_temper_production_board_routing.py`) — confirm which fixture correctly carries `.nets` before trusting its output.

**Approach:**
- Record the pre- and post-change completion count and `shorting_items` as a dated addendum, following this session's established pattern of recording measurement evidence.
- Explicitly note which nets flipped disposition, and whether `vcc`/`+3V3`/`PWR_RTN` were affected or excluded from A* entirely (per the `_should_route()` power-net pattern finding). If those nets are confirmed excluded and their shorting persists, attribute the residual to the separate zone-pour cross-class clearance issue rather than treating it as this fix underperforming.

**Test scenarios:**
- Test expectation: none -- a measurement/verification activity; its evidence is the recorded before/after data itself, not new product behavior.

**Verification:** A dated measurement record exists showing the new completion count and `shorting_items` number, with an explicit accounting of which nets changed disposition and why — this becomes the baseline R4/R5 refer to.

---

## System-Wide Impact

- **Interaction graph:** Only the plain A* pathfinding path (`attempt_route` and its helpers) is affected; the tree-executor path (`execute_terminal_tree`) already fails closed independently and is untouched.
- **Error propagation:** Failed nets already propagate via `failed_nets`/`RoutingFailureReport` → `RoutingResults`/`RoutingResult.unrouted_nets`; no new propagation path is introduced.
- **State lifecycle risks:** None beyond U4's dead-code removal — this change only prevents a route from being recorded as successful.
- **API surface parity:** `RoutingResult.forced_segment_nets`/`total_forced_segments` become permanently empty/zero (flagged in U4) but remain structurally present; no consumer contract change.
- **Integration coverage:** U1's end-to-end `route_pcb()` scenario is the cross-layer proof; U5's real DRC re-measurement is the physical-correspondence proof neither unit nor property tests alone can provide.
- **Unchanged invariants:** The tree-executor's `NetDisposition`/connectivity-verifier path, zone-pour emission, and every other net class's clearance/trace-width resolution logic are unaffected.

---

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| The completion count regresses noticeably, reading as a new problem to anyone unaware of this plan | U5 records and documents the new baseline explicitly; origin R4/R5 already establish downstream tracks adopt it with no special handling |
| The illustrative nets (`vcc`/`+3V3`/`PWR_RTN`) turn out not to be affected, understating this fix's value relative to expectations | U5 explicitly measures and reports which nets are actually affected, naming the separate zone-pour mechanism if that's the real residual cause |
| Deleting the `congestion_forced` branch (U4) misses a reference elsewhere in scripts/benchmarks — the same class of miss caused a live crash earlier this session in `scripts/internal_route.py` | U4's Approach requires a repo-wide grep across `src/`, `tests/`, `scripts/`, and `benchmarks/` before deletion |

---

## Sources & References

- **Origin document:** [docs/brainstorms/2026-07-24-router-forced-segment-fail-closed-requirements.md](../brainstorms/2026-07-24-router-forced-segment-fail-closed-requirements.md)
- Related plan (direct origin of R8): [docs/plans/2026-07-23-005-fix-router-design-rules-wiring-plan.md](2026-07-23-005-fix-router-design-rules-wiring-plan.md)
- Related plan (shipped the HV/AC-only predecessor gate): [docs/plans/2026-07-23-008-feat-property-test-hardening-plan.md](2026-07-23-008-feat-property-test-hardening-plan.md)
- Downstream consumers of the new baseline: [docs/plans/2026-07-23-001-feat-finish-the-board-drc-erc-guard-plan.md](2026-07-23-001-feat-finish-the-board-drc-erc-guard-plan.md), [docs/plans/2026-07-22-001-feat-hybrid-pour-trace-stitch-plan.md](2026-07-22-001-feat-hybrid-pour-trace-stitch-plan.md)
- Institutional learnings: `docs/solutions/logic-errors/route-pcb-design-rules-never-reaches-a-star-engine.md`, `docs/solutions/architecture-patterns/two-tier-acceptance-gate-unsat-surfacing-2026-07-05.md`, `docs/solutions/logic-errors/parsed-stub-missing-nets-silently-disables-layer-constraints-2026-07-22.md`, `docs/solutions/best-practices/lie-proof-the-green-before-believing-it-2026-07-11.md`, `docs/solutions/best-practices/hypothesis-invariant-test-suite-pattern-2026-06-28.md`, `docs/solutions/architecture-patterns/router-v6-all-pad-connectivity-foundation-2026-07-19.md`
- Adjacent, not fixed by this plan: `docs/solutions/architecture-patterns/zone-pour-bounding-box-shorting-regression-2026-07-21.md`, `docs/solutions/logic-errors/missing-cross-class-zone-clearance-regression-2026-07-21.md`
- Code: `packages/temper-placer/src/temper_placer/router_v6/_astar_reconstruct.py`, `net_classification.py`, `terminal_tree_execution.py`, `connectivity.py`, `routing_results.py`, `_adapter_types.py`, `_adapter_convert.py`
