---
title: Invariants verify the model, not reality — separate internal consistency from physical correspondence
date: "2026-07-09"
category: best-practices
module: temper_placer
problem_type: best_practice
component: testing_framework
severity: high
applies_when:
  - "building a PBT / invariant / BMC / oracle battery to validate a simulation or numerical model"
  - "writing a success criterion that claims a verification effort 'closes' a correctness gap"
  - "a green test suite is about to be treated as sign-off for a physical or safety-critical outcome"
tags:
  - verification
  - invariants
  - map-vs-territory
  - simulation
  - property-based-testing
  - validation-scope
---

# Invariants verify the model, not reality — separate internal consistency from physical correspondence

## Context
A verification effort layered a four-layer battery (fuzz → domain invariant → independent-method oracle → composition) plus a BMC/k-induction ladder over a thermal-simulation feature, and a draft success criterion read: "the map-vs-territory failure mode is closed for this feature." It is not — every invariant (energy conservation, monotonicity, maximum principle, SPD, symmetry, termination, verdict totality) checks an *internal* property of the model. None checks whether the model matches a real board.

## Guidance
State the scope of what a formal battery can and cannot establish, and don't overclaim:

- **What invariants/PBT/BMC/oracles close:** *internal model consistency* — no solver bug, no assembly sign error, no indexing/BC mistake, no non-termination, no false-zero metric. If the harmonic-mean interface model is wrong for high-contrast materials, every invariant still passes on the physically-wrong field, because all of them check the model against itself.
- **What only measurement closes:** *physical correspondence* — wrong effective conductivity, omitted convection, 3-D/via effects. The only instrument that catches these is hardware validation (thermocouple/IR vs prediction on instrumented boards).

Write the success criterion as: "a *solver/assembly/integration/termination* bug is caught before it ships (model-level map-vs-territory closed); physical correspondence is a separate gap requiring hardware validation." Make the deferred hardware step explicit in scope boundaries.

## Why This Matters
The most dangerous outcome is a fully-green formal suite treated as sign-off to energise a mains board. A self-consistent but physically-wrong simulation passes every invariant and an insufficiently-independent oracle (see the companion note on solver- vs model-independence), then fails at power-on. Naming the boundary keeps the team honest about what "verified" means and preserves the power-on measurement trigger as non-negotiable.

## When to Apply
- Any verification effort over a simulation, estimator, or physical model.
- Any doc/PR claiming a test battery "closes" a correctness or safety gap — check whether it means model-consistency or physical-correspondence.

## Examples
```
Weak (overclaims):
  "A wrong field/verdict is caught before it ships — map-vs-territory is closed."

Strong (scoped):
  "A wrong field/verdict caused by a solver/assembly/integration/termination bug is
   caught before it ships (model-level closed). Physical correspondence — whether the
   model matches reality — requires hardware validation and is out of scope here."
```

## Related
- `docs/solutions/best-practices/solver-independence-is-not-model-independence-2026-07-09.md`
- `docs/physics-verification-methodology.md`
- `docs/solutions/best-practices/hypothesis-invariant-test-suite-pattern-2026-06-28.md`
