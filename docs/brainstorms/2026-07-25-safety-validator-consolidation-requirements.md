---
date: 2026-07-25
topic: safety-validator-consolidation
---

# Safety Validator Consolidation: One Implementation, Tested

## Summary

HV isolation checking exists twice in this repo, and neither copy works. The
Python side is 27 stub functions raising `NotImplementedError` with 238 tests
pointed at them, in a directory named `tests/requirements/safety/` that has
never run in CI. The Rust side is 503 LOC of real, registered logic with **zero
tests**. This proposes deleting the stub tree, re-pointing the 238 tests at the
Rust implementation, and thereby giving the safety rules their first coverage.

---

## Problem Frame

Discovered 2026-07-25 by running `packages/temper-placer/tests/requirements/`
for the first time: **46 failed, 8 errors, 43 skipped, 166 passed**, with **84
`NotImplementedError`** raised across 27 stub sites in five validator modules —
`isolation.py`, `clearance.py`, `ground_plane.py`, `emi_filter.py`,
`schematic.py`.

The full shape:

| | Python `tests/requirements/` | Rust `temper-drc-rs` |
|---|---|---|
| Implementation | 27 stubs, `NotImplementedError` | 503 LOC, real logic |
| Registered / reachable | imported by **nothing** outside its own tests | registered at `rules/mod.rs:238`, `:247`, `:253` |
| Tests | 238 | **0 `#[test]` across all 35 rule files** |
| Runs in CI | **no workflow references the directory** | via `drc_ratchet.py`, behind a `continue-on-error` gate |

The stub tree was last modified 2026-07-23 by a batch ruff/CI formatting commit.
The project has been lint-maintaining a dead parallel implementation of its
safety checks while the live one goes untested, and nobody noticed because the
directory has no CI path.

**Why this is worth work rather than deletion alone:** the 238 tests are the
only written specification of intended safety behavior in the repository —
isolation barrier widths, UCC21550 and ADUM1250 barrier placement, ground-plane
split, creepage clearance, EMI filter topology. Pairing them with 503 LOC of
untested implementation is an unusually good position. Deleting both halves
throws away the specification along with the scaffolding.

`IsolationCheck` decides whether HV and LV are adequately separated on a
mains-connected appliance. Nothing currently verifies it does anything at all.

---

## Requirements

- **R1.** **One implementation.** The Rust rules in `temper-drc-rs` are
  canonical. `tests/requirements/validators/` is deleted, not repaired.

- **R2.** The 238 tests are **re-pointed at the Rust implementation** via the
  existing pyo3 bridge, preserving their assertions. Where a test encodes
  behavior the Rust rule does not implement, that gap is **recorded explicitly**
  as a missing check — not silently dropped, and not made to pass by weakening
  the assertion.

- **R3.** The re-pointed suite is **wired into a workflow with no
  `continue-on-error`.** A safety suite that runs nowhere is the defect being
  fixed; re-pointing it into an unwired directory reproduces it.

- **R4.** Coverage is **two-sided** (`METHODOLOGY.md` §5). Each safety rule must
  demonstrably fire on a board containing the defect it detects — proven by
  injection, not assumed — and stay quiet on the known-good corpus boards in
  `power_pcb_dataset/corpus/`.

- **R5.** The 43 currently-skipped tests are **accounted for**, per
  `docs/plans/2026-07-25-001-fix-test-skip-accounting-plan.md`: justified with a
  reason and owner, fixed, or deleted. A skipped safety check is a failed one.

- **R6.** Any test that cannot be re-pointed is **deleted with its rationale
  recorded**, rather than left failing or marked `xfail`. The end state has no
  permanently-red safety tests.

---

## Success Criteria

- `tests/requirements/validators/` no longer exists.
- The safety suite runs in CI, blocking, on every PR.
- Every Rust safety rule has at least one test that fires on an injected defect
  and one confirming it stays quiet on a known-good corpus board.
- The count of intended-but-unimplemented safety checks is written down and
  non-mysterious.

---

## Scope Boundaries

**In scope:** `tests/requirements/` (safety, emc, dfm, review, validators),
the Rust isolation/clearance/barrier rules, their CI wiring, their injection
fixtures.

**Out of scope:**
- Writing new safety *rules*. If a test describes a check the Rust side lacks,
  it is recorded as a gap, not implemented here. Implementing HV safety logic
  is engineering work needing power-electronics review, not a port.
- The other 32 rule files in `temper-drc-rs` that also have zero tests. Same
  disease, separate dose.
- `drc_ratchet.py`'s `continue-on-error` wiring — owned by
  `docs/plans/2026-07-25-002-refactor-baseline-burndown-plan.md`.
- The 4 missing-fixture errors in `dfm/`, which are ordinary test rot.

---

## Key Decisions

- **Rust is canonical, Python stubs are deleted.** The Rust side is real,
  registered, and reachable; the Python side is unreachable and unimplemented.
  The reverse choice would mean implementing HV safety logic in Python from
  scratch — real engineering, not consolidation.
- **Tests are preserved as specification.** They are the deliverable being
  rescued. Porting assertions is the work; the stub tree is disposable.
- **Gaps are recorded, not implemented.** A port that quietly grows into
  writing new safety checks is how this becomes a month.
- **Do not weaken an assertion to make a test pass.** If a re-pointed test
  fails, either the Rust rule is wrong or the check is missing — both are
  findings, and both are more valuable than green.

---

## Dependencies / Assumptions

- Assumes the pyo3 bridge exposes the isolation rules to Python in a form these
  tests can drive. Unverified, and the largest unknown.
- Assumes the 238 tests' assertions are themselves correct. They were written
  against stubs and have **never once executed against a real implementation**,
  so some may encode mistaken expectations. Expect a triage pass.
- Assumes `power_pcb_dataset/corpus/` boards are clean with respect to these
  rules — needed for R4's specificity side. If a corpus board trips a safety
  rule, that is itself a finding.

---

## Outstanding Questions

- How many of the 238 map cleanly onto an existing Rust rule? If the answer is
  "few," this is a gap-recording exercise wearing a port's clothing, and should
  be re-scoped before code is written.
- Are the Rust rules' thresholds traceable to `HIGH_VOLTAGE_CLEARANCE_SPEC.md`
  and IEC 60335-1, or were they written from memory? Untraceable safety
  thresholds are a wrong-threshold defect (`METHODOLOGY.md` §4, class 5)
  regardless of test coverage.
- Do the `emc/` and `dfm/` subtrees deserve the same treatment, or should they
  simply be deleted? They are lower stakes and may not justify the port.
- Does anything else in the repo assume `tests/requirements/validators/` exists?

### Deferred to Planning

- Port order — isolation first, as the highest-stakes rule.
- Whether injection fixtures are synthetic boards or mutations of the temper
  board.
