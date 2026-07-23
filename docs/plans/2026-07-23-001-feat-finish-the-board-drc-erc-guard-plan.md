---
title: "feat: Finish the Board — ERC-to-Zero + Portable DRC Gate + CI Anti-False-Zero Guard"
type: feat
status: active
date: 2026-07-23
origin: docs/plans/2026-07-10-001-feat-finish-the-board-plan.md
supersedes: [2026-07-10-001]
---

# feat: Finish the Board — ERC-to-Zero + Portable DRC Gate + CI Anti-False-Zero Guard

## Summary

The predecessor plan (`2026-07-10-001`, now closed as superseded) set out to produce one complete temper induction-cooker board: 100% routed and literal-zero DRC/ERC. The routing-completion half of that milestone shipped through a different path than the plan anticipated. Its R1 diagnosis (3 unrouted signal nets fixable by a net-ordering heuristic) was produced on the original un-optimized placement and identified the wrong mechanism — the handoff at `docs/handoffs/2026-07-11-finish-the-board-agent-brief.md` proved ordering is a weak RRR lever (it only shuffles which nets fail, doesn't reduce the count). The actual routing-completion drivers were the CP-SAT placement path fix (commit `a281f865`, which restored `_build_temp_pcb` as a class method and let the router run on the CP-SAT placement) and the hybrid pour + trace-stitch work (plan `2026-07-22-001`, which closed the high-fanout plane-style net gap for `PWR_RTN`, `+3V3`, and similar nets). Routing is at 100% (24/24) per the handoff.

What remains unshipped from the predecessor: a portable (non-macOS-hardcoded) `kicad-cli` DRC footprint-library-table configuration (today's `gates.py:182` hardcodes `/Applications/KiCad/KiCad.app/...`); an actual `kicad-cli pcb erc` code path (today, zero code paths invoke ERC); and a CI-integrated, non-skippable anti-false-zero guard covering both DRC and ERC (the existing `test_finish_board_gate.py` is skip-gated on a manually-produced board artifact). The honest DRC frontier was 381 per the handoff — routing completion did not make that number zero, nor did it add ERC coverage. The remaining work is measurement infrastructure (DRC portability + ERC) and gate discipline (anti-false-zero in CI), not router changes.

---

## Requirements

Traces to the predecessor (`docs/plans/2026-07-10-001-feat-finish-the-board-plan.md`).

- R1 — **Portable `kicad-cli` DRC footprint-library-table configuration**: replace the macOS-hardcoded `KICAD7_FOOTPRINT_DIR=/Applications/KiCad/KiCad.app/...` at `packages/temper-placer/src/temper_placer/placer/cp_sat/gates.py:182` with an env-var + search-path approach that works on Linux CI (the same runner that runs the regression-gate DRC per `2026-07-13-001`). Add a fail-closed check: if the library directory is missing, the gate reports `UNMEASURED`, not a silent zero-violation pass.
- R2 — **ERC-to-zero**: an actual `kicad-cli pcb erc` invocation path on the routed board. Run-first-then-fix (per the predecessor's original R6 framing): start with a diagnostic ERC run, capture the violation list, triage, fix, re-run to literal zero.
- R3 — **CI-integrated anti-false-zero guard**: lift `packages/temper-placer/tests/router_v6/test_finish_board_gate.py` from its current skip-gated/manual-board-artifact state to a proper CI gate. Drop the macOS-specific `~/Library/Preferences/kicad/10.0/fp-lib-table` check (superseded by R1's portable search). Add ERC coverage alongside the existing DRC coverage. The gate must run on every PR that touches `packages/temper-placer/router_v6/` or `pcb/` (match the path filter pattern of `python-tests.yml`).
- R4 — **Defended-against constraint relaxation**: any anti-false-zero assertion that the constraint set is unchanged continues to be enforced. Builds on the institutional discipline documented in `docs/solutions/logic-errors/weak-nooverlap2d-encoding-allows-zero-gap-2026-07-08.md` and `docs/solutions/best-practices/per-net-isolation-routing-diagnosis-2026-07-10.md`.

---

## Scope Boundaries

**In scope:**
- ERC infrastructure (code path + diagnostic run + fix cycle to zero).
- Portable DRC gate configuration (env-var + search-path, non-macOS-hardcoded).
- Lifting the existing anti-false-zero guard from skip-gated to CI-integrated, with ERC coverage added.

**Out of scope:**
- Router changes — routing is at 100%; the hybrid pour+stitch successor plans (`2026-07-18-002`, `2026-07-19-001`, `2026-07-22-001`) delivered that. This plan operates downstream of routing.
- Placement changes — CP-SAT placement is already the production path per commit `a281f865`.
- The `verify_net_connectivity` geometric verifier — it covers net-completion claims (per `2026-07-22-001` U4/U5) and is orthogonal to the DRC/ERC gate correctness this plan addresses. It stays behind its own `enable_connectivity_verifier` flag.
- DRC violation reduction — the honest frontier of 381 violations is a separate emitter-cleanup follow-up. This plan ensures the measurement gate is correctly configured and not a false-zero; it does not reduce the violation count.

**Deferred:**
- Full IEC 60335-1 compliance certification — this plan produces the measurement infrastructure; certification is a lab activity.

---

## Implementation Units

### U1. Portable `kicad-cli` DRC footprint-library-table (R1)

**Goal:** Replace `gates.py:182`'s macOS-hardcoded `KICAD7_FOOTPRINT_DIR` with a search-path approach that finds the KiCad footprint libraries on both macOS and Linux CI. Fail-closed if no path is found.

**Requirements:** R1

**Dependencies:** None

**Files:**
- `packages/temper-placer/src/temper_placer/placer/cp_sat/gates.py` — replace hardcoded path with env-var lookup (`KICAD7_FOOTPRINT_DIR` if set; else search common Linux paths: `/usr/share/kicad/footprints`, `/usr/share/kicad/7.0/footprints`, `/usr/local/share/kicad/footprints`; then macOS path as last-resort fallback). Add a fail-closed: if no path is found, the DRC gate reports `UNMEASURED`.
- `packages/temper-placer/tests/placer/cp_sat/test_drc_gate_config.py` (new or extend) — unit tests covering: env-var takes precedence; Linux path found; macOS path found; nothing found → `UNMEASURED` (not silent 0).

**Approach:** Mirror the search-path pattern from `tools/setup_kicad_env.sh` (per `2026-07-13-001`'s Linux truth-gate runner). Fail-closed matches the project's existing discipline (per `docs/solutions/architecture-patterns/two-tier-acceptance-gate-unsat-surfacing-2026-07-05.md`).

**Test scenarios:**
- Happy: `KICAD7_FOOTPRINT_DIR` env-var set → that path is used.
- Happy: no env-var, Linux runner with `/usr/share/kicad/footprints` present → Linux path found.
- Happy: no env-var, macOS runner with `/Applications/KiCad/...` present → macOS path found.
- Error: no env-var and no search path resolves → `UNMEASURED`, not a silent zero-violation pass (regression test for the project's 121→0 false-zero lesson at `docs/solutions/logic-errors/weak-nooverlap2d-encoding-allows-zero-gap-2026-07-08.md`).

**Verification:** DRC gate works on a Linux CI runner without manual env-var setup; failure mode is `UNMEASURED`, not silent zero.

---

### U2. ERC-to-zero (R2)

**Goal:** An actual `kicad-cli pcb erc` code path on the routed temper board. Run-first-then-fix; start with a diagnostic ERC run, capture violations, triage, fix, re-run to literal zero.

**Requirements:** R2

**Dependencies:** None (the diagnostic run can start immediately; the fix cycle depends on what the diagnostic reveals)

**Files:**
- New module: `packages/temper-placer/src/temper_placer/placer/cp_sat/erc_gate.py` (or extend `gates.py` with an `ErcGate` class mirroring `DrcGate`'s shape). The `ErcGate` invokes `kicad-cli pcb erc <board>` and parses the violation count.
- Wire into the existing `pipeline.py` post-routing flow at the same point `DrcGate` currently runs (examine `gates.py` and `pipeline.py` to match the pattern exactly).
- Test: `packages/temper-placer/tests/placer/cp_sat/test_erc_gate.py` — covers: CLI invocation; parse-zero-violations happy path; parse-N-violations; CLI unavailable → `UNMEASURED`.

**Approach:** Mirror `DrcGate`'s structure exactly. Treat `kicad-cli pcb erc` output the same way DRC treats `kicad-cli pcb drc` output (two-tier `CLEAN`/`VIOLATIONS`/`UNMEASURED` per `two-tier-acceptance-gate-unsat-surfacing-2026-07-05.md`).

Initial ERC run is diagnostic — capture violations, triage, fix (unconnected pins, missing power flags — per the predecessor's R6 scope), re-run to zero. Document the failure list and fix steps inline in this unit's implementation or in a sibling solutions doc.

**Test scenarios:**
- Happy: 0 violations = `CLEAN`.
- Happy: N violations (N > 0) = `VIOLATIONS`, count matches the real KI-parse output.
- Error: `kicad-cli` crashes or is absent → `UNMEASURED`, fail-closed.
- Integration: ERC on the routed temper board, after fixes, returns 0 violations.

**Verification:** `kicad-cli pcb erc <routed-board>` returns 0 violations after fixes.

---

### U3. CI-integrated anti-false-zero guard (R3, R4)

**Goal:** Lift `test_finish_board_gate.py` from skip-gated/manual to a proper CI gate. Add ERC coverage. Drop macOS-specific fp-lib-table check (superseded by U1). Make non-skippable.

**Requirements:** R3, R4

**Dependencies:** U1, U2 (needs the portable DRC gate config and ERC gate to be the things it asserts against)

**Files:**
- `packages/temper-placer/tests/router_v6/test_finish_board_gate.py` — remove the `@pytest.mark.skipif(not Path("/tmp/temper_routed.kicad_pcb").exists(), ...)` gating. Replace with a CI-environmental skip that is true on Linux runners (i.e., the guard runs when `kicad-cli` is available). Drop the macOS `~/Library/Preferences/kicad/10.0/fp-lib-table` path check (replaced by U1's portable env-var/search-path). Add an ERC assertion alongside the existing DRC assertion. Replace the doc-grep traceability check with a concrete assertion (e.g., the unrouted-net baseline count from the R1 diagnosis matches the routing-log summary).
- `.github/workflows/python-tests.yml` — confirm the path filter includes `packages/temper-placer/tests/router_v6/test_finish_board_gate.py` (mirror the path-filter pattern that already covers the `regression` job). If not present, add it.

**Approach:** The guard's existing structure (`constraint-set-unchanged`, `DRC gate configured`, `DRC-clean`, `R1 traceability`, `no-regression`) is sound — it needs to be ungated, ported to Linux, and extended with ERC. The `verify_net_connectivity` geometric verifier (`2026-07-22-001` U4/U5) is orthogonal — let it stay behind its own flag; this unit's guard is about DRC/ERC correctness, not net-completion.

**Test scenarios:**
- CI-integrated happy path: Linux runner produces a routed board via `route_pcb()`, guard runs DRC + ERC + constraint-set diff, asserts all pass.
- Mutation: deliberately relax a constraint → guard fails (constraint diff ≠ baseline).
- Mutation: deliberately misconfigure the DRC gate (remove library path) → guard fails `UNMEASURED`, not silent 0.
- Mutation: deliberately misconfigure the ERC gate (broken CLI invocation) → guard fails `UNMEASURED`, not silent 0.

**Verification:** PRs touching `router_v6/` or `pcb/` run the guard automatically; failures block merge.

---

## Key Technical Decisions

- **No router changes.** Routing is at 100%; the anti-false-zero guard's job is to surface false-zero at the gate, not to fix routing.
- **Fail-closed `UNMEASURED` over silent zero.** Carries forward the institutional discipline documented in the cited solutions docs. U1's portable path lookup explicitly fails as `UNMEASURED` when no KiCad env is configured (matching the macOS-26 / KiCad 10.0.4 local crash handling pattern from `2026-07-13-001`).
- **Mirror `DrcGate`'s shape for `ErcGate`.** Same two-tier `CLEAN`/`VIOLATIONS`/`UNMEASURED` output, same fail-closed discipline, same parsing discipline. Minimizes new surface area.
- **CI integration is real, not a skip-gated test.** The predecessor's U5 was structurally complete but never executed in CI; this unit flips it from "exists" to "runs."

---

## Dependencies / Assumptions

- KiCad 7+ footprint libraries are available on the Linux CI runner (per `2026-07-13-001`'s runner setup; U1's fail-closed surfaces this as `UNMEASURED` if not).
- `kicad-cli pcb erc` exists and supports a parseable output format (JSON or text). Verify on the Linux runner before building the parser; if JSON is not available, fall back to text parsing with a documented assumption.
- The routed board artifact is reproducible on the Linux runner from a `route_pcb()` call (per `2026-07-18-002`'s regression suite — already running).
- Anti-false-zero discipline remains the project's hard-won convention; this plan operationalizes it, doesn't redefine it.

---

## Success Criteria

- `kicad-cli pcb drc` and `kicad-cli pcb erc` both run successfully on the Linux CI runner against the routed temper board.
- DRC: 0 violations (per the honest 381 frontier noted in the handoff; the remaining 381 is a separate emitter-cleanup follow-up — this plan's DRC scope is the measurement gate, not the violation reduction).
- ERC: 0 violations (after the run-first-then-fix cycle U2 specifies).
- The anti-false-zero guard runs on every PR touching `router_v6/` or `pcb/`, asserting: constraint-set unchanged, DRC properly configured + 0, ERC properly configured + 0, no regression vs the post-routing baseline.
- A relaxation or mis-configuration induces a hard CI failure (`UNMEASURED` or `VIOLATIONS`), not a silent zero.

---

## Sources & References

- Predecessor plan: `docs/plans/2026-07-10-001-feat-finish-the-board-plan.md` (closed as superseded by this plan).
- Routing-completion successor plans: `2026-07-18-002-feat-board-routing-completion-plan.md`, `2026-07-19-001-feat-all-pad-routing-connectivity-plan.md`, `2026-07-22-001-feat-hybrid-pour-trace-stitch-plan.md` (delivered routing completion; credited in the predecessor's Superseded section).
- Handoff (the ground-truth investigation trail): `docs/handoffs/2026-07-11-finish-the-board-agent-brief.md`
- Institutional learnings: `docs/solutions/logic-errors/weak-nooverlap2d-encoding-allows-zero-gap-2026-07-08.md`, `docs/solutions/architecture-patterns/two-tier-acceptance-gate-unsat-surfacing-2026-07-05.md`, `docs/solutions/best-practices/per-net-isolation-routing-diagnosis-2026-07-10.md`.
- UCC21550 + audit follow-through: `2026-07-15-003` through `2026-07-15-009` (shipped in PRs #214 + #215).
