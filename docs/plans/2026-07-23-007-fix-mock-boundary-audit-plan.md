---
title: "fix: Close mock-boundary blind spots in router_v6 test suite"
type: fix
status: planned
date: 2026-07-23
origin: docs/brainstorms/2026-07-23-mock-boundary-audit-requirements.md
adversarial_review: true
review_findings:
  - "R3 is gated on an unresolved architectural decision (injection vs. native extraction) — building R3 before that decision lands tests the wrong thing for either outcome"
  - "R5 (comment convention) is unenforceable without automation — same review process that missed a pass-stub test will miss a missing comment"
  - "The pass-stub harm mechanism is name-squatting, not false coverage confidence"
  - "test_router_integration.py:216 has a different risk profile than the design_rules mock — no 'decoy trap' dual-object pattern, but still has zero diagnostic value"
---

## Summary

The `design_rules` wiring bug (`2026-07-23-005`) survived undetected because the only test near the break, `test_route_pcb_e2e_threads_design_rules`, mocked `RouterV6Pipeline` out entirely and asserted only on the writer's zone-pour output — never on what was passed into `pipeline.run()`. A sweep of the test suite found four `RouterV6Pipeline` mock sites plus a `pass`-bodied stub test and zero coverage on `parse_kicad_pcb_v6`'s native `design_rules` extraction. This plan closes each gap, prioritizing the mock sites that directly replicate the bug-concealing pattern.

---

## Requirements

### R1 — Add `.run()` call-args assertion to `test_route_pcb_e2e_threads_design_rules`
**Priority: P1**

`test_adapter.py:455` (`test_route_pcb_e2e_threads_design_rules`) mocks `RouterV6Pipeline` entirely and asserts only `result.routed_pcb_content` (zone-pour clearance output). Never inspects `mock_pipe.run.call_args`. Its name promises "threads design_rules" but only verifies one downstream consumer (the writer), not the pipeline invocation itself.

**Action:** Add `mock_pipe.run.call_args` assertions for `net_class_assignments` and `net_classes` kwargs, matching the pattern already established in `test_route_pcb_forwards_real_netclass_rules_to_pipeline_engine` (same file, line ~530, added same day as the fix). Alternatively, split into two tests: one for zone-pour output, one for pipeline-wiring, so each has a single responsibility.

### R2 — Fix `test_route_pcb_with_placements` to assert on call arguments, not mock return value
**Priority: P1**

`test_router_integration.py:216` mocks `RouterV6Pipeline`, sets `mock_pipe.run.return_value = mock_result`, and asserts `result.completion_rate == 0.85`. This is the return-value-only anti-pattern — it proves `route_pcb()` passes through whatever the pipeline returns, proving nothing about what it sends to the pipeline.

> **Risk profile distinction (post-review):** Unlike the `design_rules` bug, there is no "decoy trap" here — placements are a simple `dict[str, tuple[float, float]]` with no secondary reconstruction inside the pipeline. The test's weakness is diagnostic zero-value, not a hidden structural vulnerability. Still worth fixing: it currently provides no coverage of the `placements` code path it exists to verify.

**Action:** Assert on `RouterV6Pipeline(...)` constructor kwargs (specifically `placements` forwarding) and/or `mock_pipe.run.call_args`. Also pass `design_rules` so the test covers the full argument set.

### R3 — Test `parse_kicad_pcb_v6`'s native `design_rules` extraction (resolved)
**Priority: P2 — resolved (architectural decision reached)**

**Decision (2026-07-23):** Injection is the long-term mechanism (resolved by `2026-07-23-008` wiring). Native `.kicad_pcb` file extraction is vestigial — documented in `_parse_nets.py` as such. No native extraction test needed; `_extract_design_rules()` should not be extended with new fields (e.g., `safety_category`).

The YAML SSOT (`configs/netclass_rules.yaml`) is authoritative; `_to_stage0_netclass_rules()` is the one-way adapter into the A* engine format.

### R4 — Replace or delete the `pass`-bodied `test_parse_kicad_pcb_v6_basic` stub
**Priority: P2**

`test_stage0_loader.py:9-12` — a test function with a `pass` body and no import of `parse_kicad_pcb_v6`. The harm is **name-squatting** (post-review correction): the name `test_parse_kicad_pcb_v6_basic` occupies the slot a real "does basic parsing work" test should have. A future contributor sees it "exists," assumes coverage, and either doesn't write a real test or writes one under a different name that coexists confusingly with the stub.

**Action:** Delete the stub. If basic-parsing coverage is independently wanted, write it as a real test with actual assertions — but don't leave an occupied name with no body.

### R5 — Establish an automated check for mock call-args assertions (not a convention)
**Priority: P3**

**Post-review correction:** The original proposal (a comment convention) is unenforceable without automation. The same review process that missed the `pass`-bodied stub and the `test_router_integration.py:216` return-value-only pattern will miss a missing comment.

**Action:** A cheap grep-based CI check (matching this repo's existing `scripts/manifest.yaml`/`check_manifest_gate` pattern): flag any test file containing `patch(...RouterV6Pipeline...)` that has no `call_args` reference and no explicit opt-out comment tag (e.g., `# sibling-coverage:` referencing the test that covers the real path). This is a mechanical backstop, not a semantic check — it can be fooled, but it catches the obvious cases that human review already misses. Without this, downgrade R5 from "requirement" to "documented aspiration."

---

## Scope Boundaries

**In scope:** R1–R5 as scoped above — the four specific test-coverage gaps and the automated enforcement mechanism.

**Out of scope:** Auditing mock usage outside `router_v6`/`placer/cp_sat` router-adjacent tests (different subsystems, different risk profiles). **Out of scope:** actually implementing the tests — this is a planning doc.

**Deferred:** A broader "does mocking hide real integration failures" sweep across the rest of the `temper-placer` test suite. Worth doing eventually but a much larger effort than this session's scope.

---

## Key Technical Decisions

- **R1 follows the existing pattern.** `test_route_pcb_forwards_real_netclass_rules_to_pipeline_engine` already establishes the correct call-args-spying approach in the same file. R1 extends it to the zone-pour-focused test.
- **R3 is sequenced after the architectural decision**, not before. Avoid investing in tests whose value is conditional on an unresolved design choice.
- **R4 prefers deletion** over indefinite deferral. An occupied name with no body is worse than no test.
- **R5 is automation-backed or it's not a requirement.** Human-enforced conventions decay; this codebase already has evidence (the `pass` stub, the return-value-only mock).

---

## Dependencies / Assumptions

- R3 is gated on `2026-07-23-005`'s deferred architectural decision (injection vs. native extraction as the long-term netclass mechanism).
- R5 assumes a grep-based CI check is acceptable at this project's current automation maturity level (the `check_manifest_gate` precedent exists).

---

## Success Criteria

- [ ] R1: `test_route_pcb_e2e_threads_design_rules` asserts on `mock_pipe.run.call_args` for `net_class_assignments`/`net_classes`, or is split into two single-responsibility tests.
- [ ] R2: `test_route_pcb_with_placements` asserts on pipeline constructor/run call arguments for `placements` forwarding, not just mock return value pass-through.
- [x] R3: Either a real test for native extraction exists (if that's the long-term mechanism), or the extraction code is documented as vestigial (if injection wins). **(Resolved — injection is the mechanism; native extraction documented as vestigial.)**
- [ ] R4: `test_parse_kicad_pcb_v6_basic` deleted. Empty slot freed for a real test if needed.
- [ ] R5: CI check (grep-based or equivalent) flags `patch(...RouterV6Pipeline...)` without `call_args` or opt-out tag. Or R5 is documented as aspiration and explicitly deferred.

---

## Sources & References

- `docs/brainstorms/2026-07-23-mock-boundary-audit-requirements.md` — source requirements doc
- `docs/plans/2026-07-23-005-fix-router-design-rules-wiring-plan.md` — the upstream fix; its deferred architectural decision gates R3
- `packages/temper-placer/tests/router_v6/test_adapter.py` — all three mock sites (lines 210, 455, ~530)
- `packages/temper-placer/tests/placer/cp_sat/test_router_integration.py:216` — R2 target
- `packages/temper-placer/tests/router_v6/test_stage0_loader.py:9-12` — R4 target (pass stub)
- `_pipeline_core.py:214-240` — the merge point where native extraction and injection compete
- `io/_parse_nets.py` — `_extract_design_rules()`, the untested extraction path
