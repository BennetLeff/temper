---
title: "A runnable behavioral model is evidence only inside its declared boundary"
date: "2026-09-09"
category: best-practices
module: simulation
problem_type: best_practice
component: hardware_design
severity: high
applies_when:
  - "a datasheet-derived or otherwise approximate SPICE model is being used before an exact vendor model or hardware data exists"
  - "a simulation produces plausible nominal regulation and someone is tempted to call the model qualified"
  - "a published application circuit is used as a cross-check after it has helped debug or tune the model"
  - "a transient, efficiency, stability, or fault result is being promoted from model evidence to a product requirement"
tags:
  - behavioral-model
  - evidence-boundary
  - model-qualification
  - ngspice
  - development-cross-check
  - retained-receipt
  - assumption-ledger
---

# A runnable behavioral model is evidence only inside its declared boundary

## Context

The LMR51430 buck work needed a runnable circuit model, but this audit had not
obtained an independently qualified model for the exact regulator. The first drafts
looked like switching circuits while leaving the power path, latch behavior,
low-side commutation, reset, and soft start incomplete. A later revision ran
the TI application example at 4.759 V, apparently close enough to invite
interpretation as a controller result. The cause was a 10 Meg integrator
leakage that reduced the model's DC gain. Replacing that numerical grounding
with 1 Tohm restored the intended feedback behavior.

The corrected model is useful, but the work demonstrated why “it runs” and
“it predicts the device” are different claims. The retained audit explicitly
labels the model exploratory, binds each receipt to model, source, deck,
simulator, log, and waveform hashes, and separates model-development checks
from device or hardware qualification ([model-simulation.md](../../../harness-lab/audits/buck-20260909/model-simulation.md)).

This learning captures verified validation work, not completion of the broader
paper-inspired harness. The [capability status matrix](../../../harness-lab/BUCK-ENGINEERING.md#paper-inspired-harness-coverage--2026-09-09)
records partial recovery, incomplete automated diagnosis, and the missing
automatic promotion of evidence into versioned skills, memories, or subagent
specifications. Manually writing this document does not implement that
persistent learned-memory mechanism.

## Guidance

Treat a behavioral model as a bounded evidence instrument. Before using its
results, write down four things:

1. **What is sourced and what is assumed.** Datasheet anchors such as the
   0.600 V reference, 500 kHz oscillator, switch resistances, thresholds, and
   soft-start timing can be checked against the source. Internal compensation,
   parasitics, bootstrap drive, and omitted protections remain assumptions or
   omissions; keep them visible in the model report rather than hiding them in
   a convenient parameter.
2. **What the circuit physically exercises.** The model should regulate through
   the actual feedback divider and draw input power through its modeled power
   path. Independent divider arithmetic, finite input power, inductor
   volt-second balance, switching edges, and restart behavior are useful
   checks that the constructed circuit is connected and behaving coherently.
3. **What evidence the receipt actually identifies.** Retain the exact model
   snapshot, source and executed deck, simulator version, logs, raw waveform
   identity, and native measurements. A digest for a missing raw waveform is
   an identity record, not the waveform itself.
4. **Where the claim stops.** A nominal output match or timestep convergence
   supports model development. It does not establish transient accuracy,
   efficiency, stability, thermal behavior, fault behavior, or hardware
   performance unless those claims have independent evidence.

Keep the execution harness fail-closed around this boundary. It should reject
missing or stale artifacts, incomplete or nonfinite measurements, timeouts, and
unqualified model manifests, while retaining the useful output for diagnosis.
The runner can prove that a declared measurement was collected; it cannot turn
that measurement into a qualification claim.

## Why This Matters

Approximate control-loop models can produce persuasive waveforms while being
wrong in a way that a nominal voltage table will not reveal. In this work, the
10 Meg leakage created a real-looking but incorrect 4.759 V TI-example result;
the 1 Tohm correction fixed the numerical disturbance, but it did not reveal
the regulator's unpublished compensation. The corrected report therefore
retains a plausible 3.314861 V nominal result and a 4.978407 V TI cross-check,
while refusing to call either a hardware or transient qualification.

This boundary also prevents a “holdout” from becoming circular evidence. The
TI example exposed a development defect and was rerun after the fix, so it is
properly labeled a development cross-check rather than a blind holdout or
independent qualification receipt. A check that has influenced model changes
can still be valuable, but its evidentiary status has changed and should be
recorded.

## When to Apply

- When no exact, independently qualified device model is available and a
  datasheet-derived model is being built.
- Before using nominal regulation, ripple, startup, or load-step output as a
  design decision or product requirement.
- When a test case is called a holdout, golden case, or independent check after
  it has been inspected or used to change the model.
- When simulation artifacts are copied, regenerated, or stored outside version
  control and their identity could be confused with their availability.

## Examples

The evidence ladder for this buck model is:

```text
source-backed anchors + explicit assumptions
        -> physical-path and feedback sanity checks
        -> retained native measurements and artifact hashes
        -> timestep / restart checks
        -> bounded model-development conclusion
        -> hardware or independently qualified model evidence (still required)
```

The corrected audit reports the independent divider calculation (3.314932 V)
against nominal simulation (3.314861 V), finite input/output power, balanced
inductor volt-seconds, 20 ns versus 10 ns convergence, and EN hysteresis and
restart. It separately records that the 2.871829 V load-step dip is a model
result requiring real-device comparison, not a board failure or accepted
transient specification.

The rejected history is part of the evidence. `measured-v2` remains available
with its receipt and model snapshot, while `measured-v3` retains the corrected
1 Tohm model. This makes the correction auditable and prevents a later reader
from treating the rejected model's 4.759 V result as evidence for the current
model or real device.

## Related

- [LMR51430XDDCR measured audit](../../../harness-lab/audits/buck-20260909/model-simulation.md)
- [Rejected development artifacts](../../../harness-lab/audits/buck-20260909/rejected-v1/README.md)
- [A citation loop — validating a model against the uncited table it came from](citation-loop-validates-a-model-against-itself-2026-07-27.md) — independent source tracing
- [Solver-independence is not model-independence](solver-independence-is-not-model-independence-2026-07-09.md) — why a different solver does not establish a different physical model
- [Calibration point and design point must be the same point](calibration-point-must-equal-design-point-2026-07-28.md) — a related category error in simulation claims
