---
title: "Pattern: the post-solve audit must re-run the truth function, not a cheaper proxy (validator-aligned audit)"
date: 2026-08-02
category: design-patterns
module: temper-placer
problem_type: design_pattern
component: placer
severity: high
applies_when:
  - "A solver/optimizer encodes a constraint with one geometry (boxes, centers) while the acceptance gate measures a stricter one (exact pad copper), and a cheaper 'audit' exists between them"
  - "A post-solve audit recomputes a distance with a different formula than the function the CI gate actually runs"
  - "The audit's own docstring contains 'cheaper, weaker check' or 'upper bound' language"
  - "A solve terminates 'audit-clean' but the acceptance gate fails — the failure mode is silent by construction, because both the solver and its audit agree"
symptoms:
  - "Run-B candidate: the scoped K3/tank3 solve passed its post-solve audit (audit_domain_clearance, center-to-center Euclidean) with 0 violations while the REQ-SAFE-01 gate (verify_iec60335_compliance, exact copper-to-copper on pad geometry) found 12 violations: C27 landed 0.32mm from U24 while its centers were 15.360mm apart"
  - "REQ-SAFE-01 went 3 → 12 on a candidate the solve reported clean"
  - "The audit and the validator disagree about a placement that one of them must gate"
root_cause: proxy_divergence
resolution_type: pattern_introduced
tags:
  - post-solve-audit
  - validator-alignment
  - R24
  - safety-clearance
---

# The post-solve audit must re-run the truth function, not a cheaper proxy

## The failure

The placer's post-solve audit (`audit_domain_clearance`) recomputed **center-to-center
Euclidean distance** (`math.dist`) against the required margin. Its own docstring
admitted this was "a cheaper, weaker check than what `clearance.py`'s validator
actually measures (copper-to-copper on exact pad geometry)". On the run-B candidate,
this audit reported **0 violations** while `verify_iec60335_compliance` — the exact
copper-to-copper function the CI gate runs — reported **12** (C27/U24: centers
15.360mm apart, copper 0.320mm; reproduced bit-exact in
`docs/evidence/2026-08-01-runb-audit-lie-reproduction.md`).

The failure is silent by construction: the solver encodes box separation, the audit
checks center separation, and both agree the placement is fine — the *gate* disagrees,
and nobody sees the gate result until after the solve is consumed.

## The soundness hierarchy that makes this predictable

For two components, the separations order strictly:

```
center distance  ≥  box edge distance  ≥  exact copper-to-copper distance
```

A check at any level *passing* says nothing about the levels below it. A center
check passing is an **upper bound** on copper separation: it can be arbitrarily
optimistic (15.360mm of center distance with 0.320mm of copper). Any "cheaper,
weaker check" in an audit is a place where the lie can re-enter.

## The pattern (what gap 2 shipped)

1. **The post-solve audit re-runs the truth function itself** — the same
   `verify_iec60335_compliance(placement, voltage_domains)` the CI gate runs — on a
   placement whose positions/rotations come from the solve
   (`validator_audit.audit_domain_clearance_validator`,
   `packages/temper-placer/src/temper_placer/placer/cp_sat/validator_audit.py`).
   The cheaper center audit stays only as a fast encoding-bug catcher; it is never
   the acceptance check.
2. **Classify every validator violation by coverage**, because not all violations
   are the solver's fault:
   - **HARD** — inter-component pair covered by a generated `SeparatedConstraint`:
     the box separation the solver SAT did not imply the validator's copper
     separation → the encoding is unsound for this solve → raise (same contract as
     `fixed_copper.audit_fixed_copper`).
   - **intra_footprint** — `ref_a == ref_b` straddler: placement-independent
     (translating/rotating a part rigidly cannot separate its own pads) → report,
     never raise. K3's G5LE-1 gap is exactly this.
   - **coverage_gaps** — pair the generator never constrained (the
     `component_refs` filter or the straddler exemption) → report, never raise.
   - Classification is on the **unordered pair key** (`frozenset`) — the generator
     emits reversed-duplicate rows (451 measured on the production board), and the
     classification must absorb them.
3. **Integrity guards against vacuous-clean**: the validator models a component
   without `pads` as a zero-extent point — *optimistic* in exactly the dangerous
   direction. Surface `stats.components_without_pads` / `pairs_origin_modelled`
   with a `geometry_trusted` flag and a loud error log; raise `ValueError` when the
   placement does not describe the solve (zero components, disjoint refs).
4. **Frame contract**: fixed refs keep their true board positions; free refs get
   solver positions; a ref the solve *touched* (position + rotation index) gets the
   solver's rotation overlaid unconditionally (that is what gets written to the
   board); refs the solve did not rotate keep their exact base rotation.

## When to apply

Any solver/validator split where the solve-side geometry (box, center, grid) is
coarser than the acceptance-side geometry (exact pads, true polygon distances):
the audit must call the acceptance function, not re-derive it. "Cheaper, weaker
check" in a docstring is a demand notice, not a design note.

## Evidence

- `docs/evidence/2026-08-01-runb-audit-lie-reproduction.md` — the lie, bit-exact
  (7/12 records to ≤0.001mm, C27/U24 center 15.360 vs copper 0.320).
- `docs/evidence/2026-08-01-validator-aligned-solve-audit.md` — the pattern as
  built (R24 falsifier: centers ≥ margin apart, copper < margin, old audit passes,
  new audit fires).
- `docs/evidence/2026-08-01-domain-constraint-coverage-gap.md` — the generator's
  pair set is bit-identical to the validator's (11,571 pairs, symmetric difference
  0), so the only divergence was the audit's formula.
