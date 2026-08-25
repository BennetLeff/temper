---
title: Merge gating vs standing safety debt — stop one board finding blocking every PR
type: fix
date: 2026-08-24
topic: merge-gating-safety-debt
artifact_contract: ce-unified-plan/v1
artifact_readiness: requirements-only
execution: code
product_contract_source: measurement
status: draft
swept: null
swept_basis: null
---

# Merge Gating vs Standing Safety Debt — Plan

## Goal Capsule

**Objective:** Make `Required Python Tests` block a PR for what that PR broke,
not for what the board has not finished. Today two of its twelve required
contexts are red for standing board findings that no code change can clear, so
**every** open PR is blocked by findings unrelated to it.

**This plan does not accept, hide, or re-baseline any safety finding.** It
changes which findings block *merges*. The findings stay measured, stay
reported, and stay blocking for anything new.

## Product Contract

### Summary

Two required contexts carry a standing red. Both reds are single steps inside
large jobs. This plan moves those steps behind a ratchet whose baseline is an
evidence-linked, owner-signed list of accepted-as-known findings — green on
exactly that list, red on anything else — so known debt stops blocking and new
regressions still block.

### Problem Frame

**1. The repo already holds this doctrine, and applied it only in one
direction.** `.github/required-checks.json`, on why `regression` was not added
to `required_contexts`:

> Adding a currently-red workflow to required_contexts wedges every PR
> immediately -- exactly the failure mode #1032's own title warns against
> ('fix-then-require').

That is exactly the present state of `Core Tests` and `Cross-Source Consistency
Gates` — except they were added while green and went red later. The doctrine was
applied at admission and never re-applied.

**2. The blocking reds are two steps, both standing design findings.**

| context | failing step | finding | can a PR fix it? |
|---|---|---|---|
| `Core Tests` | `Run tank<->bus creepage gate (safety shortfall)` | enforced clearance **2.0 mm** and `HighVoltageTank.creepage_mm` **6.3 mm** against a governing **10.0 mm** PD3 functional figure | **No** — declared design figures |
| `Cross-Source Consistency Gates` | `ERC endpoint_off_grid consequence gate` | `ac_l` (mains Line at F1.1) rendered as a KiCad `no_connect` by `gen_schematics.py` | **No** — generator policy + an assembly decision |

`Core Tests` has 20 substantive steps; the creepage gate is one. `Cross-Source`
has 54; the ERC gate is the last. Everything else in both passes.

**3. `Board, Provenance & Requirements Gates` is red and is NOT required.** It
carries the K1↔R56 5.036 mm and RT1↔K1 7.000 mm placement violations. So the
repo already tolerates a red board-state context outside the merge gate — the
precedent for this plan's shape exists, undocumented, one job over.

**4. The cost, measured 2026-08-24.** 57 open PRs. Bucketed by whether their
reds are their own: **10 have none**, 2 have only the shared standing reds, 42
have at least one of their own (many being a `Fast Gates` red that `#1473` fixed
on main today — i.e. they are stale, not broken). Zero `Python Tests` runs on
`main` succeeded in the 63 completed runs before today.

**5. Why this is not "re-baseline the gate to green".** The repo's established
mechanism for a verified-real finding that will not be fixed today is an
evidence-linked allowlist entry, not a moved threshold —
`power_pcb_dataset/drc_ceiling.json`'s `_march` log,
`bom-reconciliation-allowlist.yaml`, and #1438 (*"y_cap_pe E-series violation —
verified real, allowlisted with evidence"*). This plan applies that mechanism to
merge gating. The measured figures do not move.

### Key Decisions

- **D1. Ratchet, do not de-require.** Chosen over moving the two steps into a
  non-required job: an advisory check that is red by default is a check nobody
  reads — this repo's own `wasm-tier-nightly.yml` header opens with "produces
  numbers nobody reads" as its cautionary case. A ratchet keeps the context
  required and therefore load-bearing, and inverts the default: red means
  *something new*.
- **D2. The baseline is evidence-linked and owner-signed, not agent-writable.**
  Chosen over a plain allowlist file: each entry names the finding, its measured
  figure, the evidence document establishing it is real, and the owner decision
  accepting it as non-blocking. Mirrors `drc_ceiling.json`'s provenance block
  and the DRC-ceiling same-PR discipline in `AGENTS.md`.
- **D3. Baseline entries carry an expiry.** Chosen over open-ended acceptance:
  standing debt with no clock becomes permanent. An expired entry fails the
  ratchet, which forces a re-decision rather than silent drift.
- **D4. The findings keep their own visible report.** Chosen over folding them
  into the ratchet's pass/fail alone: the step summary enumerates every
  baselined finding on every run, so the debt is visible in CI output even while
  green.

### Requirements

- **R1.** `Core Tests` and `Cross-Source Consistency Gates` are green on `main`
  with no measured figure changed and no assertion deleted.
- **R2.** A finding not in the baseline fails its context, blocking the merge.
- **R3.** A baselined finding whose *measured value worsens* fails — the ratchet
  pins the figure, not just the finding's identity.
- **R4.** A baselined finding that has been **fixed** fails the ratchet (stale
  entry), by the same argument `run_wasm_tests.mjs` exits non-zero on an
  unexpected pass and `test_ci_test_file_registration.py` fails on a
  tracked-but-now-covered file.
- **R5.** Every baseline entry names an evidence document and an expiry date.
- **R6.** The ratchet is falsifiable by a test that injects a synthetic finding
  and asserts the gate reds — not by inspection. This repo has shipped
  anti-vacuity gates that ran zero tests (#1423, #494385928).

## Units

### U1 — Measure the exact finding set (R1)

**Deliverable.** The complete, current output of both gates on `main`, as
structured data: finding identity, measured figure, and which of the two
contexts reports it.

**Why first.** The baseline cannot be written from the three assertions I
happen to have reproduced. #1486 already re-derived four stale pins in the same
file; the live set is what governs.

**Evidence of closure.** Both gates run on a clean checkout at a named commit,
output captured, and the count reconciled against this plan's §2 table.

### U2 — The baseline format and its gate (R2, R3, R4, R5)

**Deliverable.** `safety-debt-baseline.yaml` at repo root (sibling of the
existing `*-allowlist.yaml` files) plus the checker that consumes it.

Per entry: `id`, `gate`, `finding`, `measured`, `requirement`, `evidence`
(path), `accepted_by`, `accepted_on`, `expires_on`, `why_not_fixed_now`.

The checker: red on unknown findings (R2), on a worsened figure (R3), on a
disappeared finding (R4), and on an expired entry (D3).

**Evidence of closure.** Unit tests for all four red paths.

### U3 — Wire it into the two gates (R1)

**Deliverable.** The two failing steps consult the baseline. Nothing else in
either job changes.

**Evidence of closure.** Both contexts green on `main`; the step summary lists
every baselined finding with its figure and expiry (D4).

### U4 — Prove it bites (R6)

**Deliverable.** A test that injects a synthetic creepage finding and asserts
the gate reds, and a second that worsens a baselined figure and asserts the same.

**Evidence of closure.** Both tests fail if the corresponding check is removed
from the checker.

### U5 — The owner decision, recorded

**Deliverable.** The initial baseline, signed. **This unit is not executable by
an agent.** Each entry is an owner statement that a named, measured safety
finding does not block unrelated merges while it is being fixed.

**Evidence of closure.** Every entry has `accepted_by` and `expires_on`
populated by the owner, and an evidence document that establishes the finding is
real.

## Scope Boundaries

- **Not in scope: fixing any finding.** Moving R56 or K1, changing
  `HighVoltageTank.creepage_mm`, adopting PD2 over PD3, or deciding `ac_l`'s
  wire-landing policy. Each is a design decision with its own discipline.
- **Not in scope: changing any measured figure or deleting any assertion.**
- **Not in scope: `Board, Provenance & Requirements Gates`.** Already
  non-required (§3); bringing it *into* the required set once the ratchet exists
  is a follow-up worth having, not this plan's work.
- **Not in scope: the 42 stale-red PRs.** A rebase sweep is separate and
  cheaper; it should happen after `main` is green so the sweep measures
  something.

## Dependencies / Assumptions

- Both gates emit findings identifiable stably across runs. If a finding's
  identity is positional or set-ordered, U2's `id` needs deriving first — a
  ratchet keyed on an unstable id fails open or fails constantly.
- `main` going green depends on nothing else being red in those two jobs. U1
  measures this; if a third standing red exists, it joins the baseline or the
  plan grows.
- The owner is willing to sign U5. **If not, this plan should be closed and the
  findings fixed instead** — which is a legitimate outcome and a faster route to
  a green trunk if the design changes are small.

## Outstanding Questions

- **Q1.** What expiry is right? The DRC-ceiling convention has no clock; this
  plan proposes one and the interval is a judgement (30 / 90 days).
- **Q2.** Should the ERC/`ac_l` finding be baselined at all, or fixed? It is a
  generator-policy change plus a one-line list, and may be cheaper to fix than
  to accept. `docs/evidence/2026-08-24-ac-l-mains-no-connect.md` §4 has the fix;
  it needs a `kicad-cli` that can run schematic operations to verify.
- **Q3.** Does a baselined-but-expired entry block merges, or only fail the
  nightly? D3 says block; that is arguable.

## Sources / Research

- `.github/required-checks.json` — the aggregator, `required_contexts`, and the
  `fix-then-require` doctrine this plan extends.
- `docs/evidence/2026-08-24-trunk-red-triage.md` — the four red jobs and which
  are real.
- `docs/evidence/2026-08-24-k1-isolation-barrier-triage.md`,
  `docs/evidence/2026-08-24-ac-l-mains-no-connect.md`,
  `docs/evidence/2026-08-24-tank-creepage-pour-containment.md` — the findings.
- `power_pcb_dataset/drc_ceiling.json`, `bom-reconciliation-allowlist.yaml`,
  #1438 — the established evidence-linked-allowlist pattern D2 mirrors.
- #1486 — re-derived four stale pins and kept three honest reds; the three it
  kept are §2's `Core Tests` finding.
