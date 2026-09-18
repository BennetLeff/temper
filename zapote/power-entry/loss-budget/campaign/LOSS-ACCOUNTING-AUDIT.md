# Loss-accounting audit

Date: 2026-09-17
Scope: the campaign's headline loss numbers, recomputed from the retained
artifacts rather than from the workers' summaries.
Trigger: the first closeout reported a "~34.6 W" independent subtotal that
double-counts output capacitance. This audit corrects it and restates the
discrepancy in the right terms.

Sources audited:
- `runs/2026-09-17-pfc-campaign/R0/attempt-001/raw/report.json` (analytic, via G0)
- `runs/2026-09-17-pfc-campaign/N-DPT/attempt-001/result.json` and `REPORT.md`
- `runs/2026-09-17-pfc-campaign/N-DPT-ST/attempt-001/REPORT.md` (control)

## 1. Findings

### F1 — Eoss was double-counted (the headline number is wrong)

N-DPT's own definition, verbatim: *"overlap-only = (Eon − Eoss + Eoff)·f, since
the DPT turn-on also dissipates the stored output-capacitance energy that the
analytic model books separately."* The DPT's `Eon` therefore **already
includes** the Coss discharge. The first closeout added the analytic `Eoss`
term (1.5106 W) on top of the vendor switching result, counting that energy
twice.

Correct conditional subtotal:

```
vendor (Eon+Eoff)·f                 26.7613 W   (includes Eoss)
analytic mosfet_conduction           6.479456 W
analytic gate_charge                 0.144084 W
                                    ----------
conditional switch+gate subtotal    33.3848 W
```

The first closeout's 34.64 W was 33.3848 + 1.2603 (Eoss re-added). Corrected
figure: **~33.38 W**.

### F2 — The subtotal is a mixed quantity, not a vendor result

Only the switching term is independent. The conduction (6.4795 W) and gate
(0.1441 W) terms are still the analytic model's, computed from the analytic
waveform's `switch_rms_a` (11.9995 A). The 33.38 W figure must be labelled
**conditional**, not "vendor", and it is not a measured board loss.

### F3 — Model disagreement is not calibration

The two models disagree on the switching term by roughly a factor of 1.4
(analytic higher). That is a **discrepancy under the tested conditions only** —
one device (IPW65R045C7), one bus (400 V), one gate network (9.7/5.3 ohm,
0→12 V), two currents, and the Level-0 vendor model. It does **not** license a
universal correction factor:

- it says nothing about the STW65N65DM2AG, which has no independent result at all;
- it says nothing about conduction, gate, bridge, inductor, or auxiliary terms;
- applying "×0.72" to any other quantity would be unjustified.

### F4 — Direction of the disagreement

The analytic model predicts **more** loss than the independent vendor model
(45.50 W vs 33.38 W conditional on the switch/gate subtotal). The analytic model
is therefore **pessimistic about the design's efficiency**, not optimistic. Any
earlier phrasing to the contrary was wrong.

### F5 — The 125 °C entry is not an independent hot prediction

Vendor Level-1/Level-3 electrothermal models do not solve in ngspice-45. The
125 °C row is the Level-0 model run at `.temp 125`, i.e. resistor temperature
coefficient only. It is not the vendor's electrothermal estimate and must not be
compared as one.

### F6 — Apparent small condition mismatch

The analytic point uses `mean_turn_on_a` 11.9271 A and `mean_turn_off_a`
15.0270 A; N-DPT applied 12.07 A and 14.99 A (≤1.4% difference, reported, never
scaled). Small, but it means the comparison is not at identical currents.

### F7 — The bridge is unaffected by all of this

The bridge term (28.30 W) does not depend on the switching comparison. It
remains source-bound but derived from a single datasheet test point
(1.05 V at 12.5 A, 25 C) with an 0.85/1.30 V assumption band. It is the largest
*unchallenged* term, and it is not independently verified either.

## 2. Corrected ledger

At C1 nominal (120 V, 400 V bus, 1796.31 W requested). Evidence class per row is
the strongest class the term actually has.

| Term | Value | Evidence class | Note |
| --- | ---: | --- | --- |
| Boost switching (Eon+Eoff) | 25.50-26.76 W | independent device *model* | Eoss-inclusive at 26.76; overlap-only 25.50 |
| Boost conduction | 6.4795 W | analytic model | uses analytic switch RMS |
| Boost gate charge | 0.1441 W | analytic model | trivial |
| Analytic `Eoss` | 1.5106 W | analytic model | **already inside the 26.76 W; do not add** |
| Input bridge | 28.30 W | source-bound, 1 test point | 0.85-1.30 V band |
| Boost inductor, DC | 4.50 W | source-bound | core/AC unknown |
| Shunt + reference | 2.27 W | source-bound | |
| Relay + bleeders + divider | 1.16 W | source-bound | |
| **Conditional switch/gate subtotal** | **33.38 W** | mixed | not a measurement |
| **Analytic switch/gate subtotal** | **45.50 W** | analytic | the model's claim |

Switching-term ratio: 26.7613 / (37.3682 + 1.5106) = **0.688**;
overlap-only 25.5013 / 37.3682 = **0.683**. Both are "analytic is ~1.45x higher",
not "a 30% correction".

## 3. What this audit does NOT establish

- It does not calibrate the analytic model. It shows the two disagree.
- It does not quantify the board's real loss. No term here is measured.
- It does not extend the discrepancy to any device, condition or loss term that
  was not directly compared.
- It does not establish that the STW65N65DM2AG differs from the C7 by any
  amount.
- It does not touch the thermal question. Temperature remains unrankable.

## 4. Consequence for the campaign

The direction of the disagreement matters for the design conclusion. If the
analytic model is pessimistic by ~1.45x on switching, then the switching-term
urgency is lower than the model suggested — which **raises** the relative
importance of the largest unchallenged term, the input bridge, and weakens the
case for spending effort on the switching-adjacent axes (gate drive, frequency)
before the bridge has been screened.

That is consistent with the recommended next step: resume bridge/rectification
architecture screening, and treat the switching measurement as a parallel,
separately authorized activity rather than the critical path.
