# D-3: does the IPW65R018CFD7 model's body-diode recovery match the datasheet?

**Read [README.md](README.md) first (ground rules, board facts).**

## Why it matters

Round 17's D2 grid fails **every** hard-turn-on case (S4: partner body
diode carrying 20 A when the other device turns on). In the model the
diode's reverse-recovery current reaches about +89 A and then snaps (die
VDS 24 → 400 V in ~4 ns, ~15 A/ns), overshooting to ~541 V on a 170 V bus
and ringing at ~41 MHz; the ringing lifts the off device's gate to 3.2–5.0 V
(false turn-on). Both the snap and the peak come from Infineon's
**IPW65R018CFD7_L1** subcircuit at 27 °C. Before believing S4, check that
the model's diode recovery matches the datasheet.

## Task

1. From the **Infineon IPW65R018CFD7 datasheet**
   (https://www.infineon.com/assets/row/public/documents/24/49/infineon-ipw65r018cfd7-datasheet-en.pdf;
   cite revision and table/figure), record the body-diode reverse-recovery
   data: Qrr, trr, Irrm, the test conditions (IF, di/dt, VR, Tj), and any
   recovery-charge vs di/dt or temperature curves.
2. Build a **standard reverse-recovery test** in ngspice with the L1 model
   (`validation-plan/sim-kit/models/vendor/IFX_CFD7_650V.lib`, ngspice in
   PSpice mode: `.spiceinit` with `set ngbehavior=psa`; solver options from
   `validation-plan/sim-kit/common/options.inc`): a double-pulse or clamped
   inductive test that reproduces the datasheet's IF, di/dt, VR and
   temperature as closely as the model allows. Measure Qrr, trr, Irrm and
   the softness factor.
3. Compare with the datasheet. If the model has temperature dependence,
   repeat at the datasheet's Tj. Report whether the model's recovery is
   softer, similar or snappier than the datasheet implies, and by how much.
4. Re-run D2 case S4 (VBUS 170, IL −20, DIR 0, DT 348, ESL 10 nH) with
   `round17/d2/run_d2.py` on `round17/d2/legA-h0-lin12.matrix.txt`, and if
   the model offers a temperature parameter, at the datasheet Tj too. Do not
   edit `round17/d2/`; copy what you change into your output folder.

## Deliverable

`round17/delegation/out-D3/README.md`: one-line answer (model recovery vs
datasheet; implication for the S4 result), the datasheet table, the test
deck(s), measured Qrr/trr/Irrm with waveforms (CSV + PNG), and the S4
rerun.

## Acceptance

The test conditions match the datasheet's (or the differences are stated);
the measured values come from committed decks and outputs; no generic
diode model is substituted without saying so.
