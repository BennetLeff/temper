# RTD model correctness

Started 2026-09-11 at the user's direction. Assume the intended circuit is
acceptable for this pass. Check whether the executable models represent that
circuit and the selected devices faithfully enough to support their claims.
No source-circuit, BOM, placement or routing changes are part of this pass.

A model result must answer four separate questions:

1. **Circuit correspondence:** do modeled nodes, branches, values and fault
   disconnections match the adopted source and native circuit?
2. **Device applicability:** do parameter bounds come from the correct datasheet
   columns and apply at the modeled supply, temperature, load and input conditions?
   A deliberately omitted device behavior remains an explicit limitation.
3. **Numerical correctness:** do independent solvers or analytic results agree,
   and does reducing the transient timestep converge? Solver agreement alone
   cannot validate shared topology or parameter mistakes.
4. **Claim validity:** does a claimed worst-case bound cover the whole declared
   population, rather than one parameter combination or a copied summary value?
   Check that deliberate model errors invalidate the result.


## Current result — passive-network qualification

The full adopted two-state external network now has a continuous-range
analytical fault-response certificate. Rust independently reconstructs its
conductance/capacitance matrices, initial-energy bounds, final-overdrive margins
and timing; it does not accept a producer's PASS label as evidence. The
slowest bound is **0.971460 ms**, including conditional 55 ns comparator and
10 ns logic allocations, within the unchanged **2 ms** detector allocation.

| Fault | Conditional bound (ms) |
|---|---:|
| FORCE+ open | 0.002308 |
| FORCE− open | 0.001619 |
| SENSE+ open | 0.971460 |
| SENSE− open | 0.135356 |
| RTD short, 0–10 ohm | 0.000927 |

Coverage includes healthy initial RTD 100–194.1 ohm, independent 1–50 ohm
leads, resistor tolerance/TCR, corrected reference voltage, signed leakage and
offset, 0.94–1.10 nF differential capacitance, and independently 0–200 pF
per input to ground. The latter is a conservative model allowance, not a
measured parasitic-capacitance guarantee. Single permanent faults start from
healthy equilibrium with fixed sources/parameters.

The current [bound unit report](qualified-input/report.json) separates
`ERC.RTD.MODEL_QUALIFICATION` from
`ERC.RTD.MODEL_DEVICE_APPLICABILITY`. Mathematical network qualification
passes; device applicability and the prior brownout timing result remain
**INDETERMINATE**. This does not renew every inherited static, supply, startup
or accuracy assertion in the historical model. No physical measurements ran.

Verification: 62 Rust tests pass, formatting passes, and all 34 compiled-validator
scenarios produce the required verdicts. Clippy reports one pre-existing warning
in unchanged DRC code. [Replay instructions](REPLAY.md) and the
[closeout receipt](closeout-receipt.json) retain commands and identities.

Artifacts: [derivation](root-review/analytic-derivation.md),
[model and representative SPICE checks](qualification/qualification.md),
[device applicability review](applicability-review.json),
[compiled-validator mutation replay](root-review/mutation-replay.json), and
[new input](qualified-input/input.json). The frozen acceptance bundle was not
rewritten. Its missing qualification now produces INDETERMINATE under the new
validator.

The independent Python/SPICE comparisons cover all four actual open assertions
and an exact zero-ohm transient. Separately, 2,500 seeded fault evaluations
found no violation of the analytical inequalities. These are implementation
checks, not the reason continuous parameter coverage is claimed.

## Retained lessons for the next unit

- Include threshold-divider current when bounding a supposedly unchanged sense
  node. The rejected SENSE− displacement of 0.25 mV was below a reproduced
  0.651 mV change; the accepted conservative bound is about 5.8 mV.
- Check SPICE switch polarity and pre-fault state. A reconnecting wire can
  produce an apparently plausible timing receipt for the wrong experiment.
- Use maximum datasheet columns and their actual test conditions. Hashing an
  incorrect envelope only makes the incorrect assumption reproducible.
- Keep device applicability separate from passive-network mathematics. The
  MAX31865 force paths and TLV3201 conditions are not proved by independent
  solvers that share those idealizations. The Rust gate preserves that gap
  even when a producer claims device PASS.
- Bind the qualification to the exact source topology and artifact bytes, and
  deliberately corrupt evidence through the normal validation entry point.

These reinforce the existing repo lessons on
[solver versus model independence](../../../docs/solutions/best-practices/solver-independence-is-not-model-independence-2026-07-09.md)
and [model invariants versus physical correspondence](../../../docs/solutions/best-practices/invariants-verify-model-not-reality-2026-07-09.md).

## Earlier audit (retained history)

### Confirmed finding: reference regulation envelope

The static model uses REF2025 line/load regulation values of 3 ppm/V and
8 ppm/mA. TI's electrical table identifies those as typical; its maxima are
35 ppm/V and 20 ppm/mA. Initial accuracy is specified at VIN=5 V, so the
3.135–3.465 V unit supply must be evaluated relative to that test condition,
not only as ±0.165 V around 3.3 V.

Holding all other original terms and the original divider load constant,
this changes the 1.25 V output's calculated error envelope from ±1.226581 mV
to ±1.309000 mV. This confirms an underestimated envelope. It does not itself
show an incorrectly functioning circuit; representative healthy/open classifications remain unchanged in the revised
model. A complete revised sweep has not been used to renew acceptance.

Source and calculation: [datasheet-audit.json](datasheet-audit.json), retained
[official TI REF20 datasheet](sources/ref20-sbos600f.pdf), page 6 section 6.5.
The revision is recorded explicitly because a stable manufacturer URL can
return a newer document.

### Timing qualification finding

The retained scalar RC calculation is not a demonstrated upper bound. Its
choice of starting comparator margin can reduce the computed crossing time:
for a fixed negative final margin, a larger positive starting margin increases
that time. A consistent healthy/FORCE+ endpoint pair from the old static model
at 194.1 ohm gives about 2.106 ms with the same scalar time constant, exceeding
the claimed 1.324 ms maximum and the 2 ms allocation.

This is a counterexample to the scalar calculation's claimed maximum, not a
measurement or a full-network transient showing a 2 ms violation. The separate
two-node simulation and the validity of its corner coverage must establish the
actual timing bound. Existing passing samples cannot restore that guarantee.
See [topology-review.md](topology-review.md) for the executable evidence and
limitations of the retained isolated ngspice checks.

### Completed first-pass evidence

- Root: independent datasheet-parameter audit, source retention and qualification
  status. Verified TLV3201's 4 mV offset, 5 nA bias and 55 ns propagation entries
  with their conditions; this is not a complete device-model qualification.
- Luna: retained a revised reference-envelope candidate, an independent ngspice
  comparison, a timing counterexample, and a selected timestep-convergence check.
  Root replayed all four scripts successfully. The old reference envelope fails
  the corrected requirement; the revised candidate passes this focused check.
- Numerical samples: the static network agrees with ngspice within 4.84e-8 V
  at one operating point. One selected transient crossing converges from
  0.370000 to 0.369250 ms as the timestep shrinks from 1 to 0.25 us.
  These checks do not establish full parameter coverage.

### First-pass acceptance boundary (superseded for passive timing only)

This pass has not established comprehensive model correctness. Historical native
ERC/DRC and board-connectivity evidence remain intact. The prior model-derived
acceptance claims are under review; the old passing Rust tests do not resolve
newly found model defects. Revised models must be qualified and rebound before
being used to renew those claims. Physical measurements remain NOT RUN.

At the end of the first pass, model-qualification verdict logic was to be enforced by Rust
against explicit model evidence. Existing Python circuit models can remain;
rebuilding the board editor, placer or router is outside this work.

That pass identified the next bounded milestone: qualify the full-network transient model,
including device applicability and parameter coverage, then bind that evidence
to Rust acceptance checks. Do not raise the 2 ms budget just to absorb the
scalar counterexample. Physical measurements remain a separate obligation.
