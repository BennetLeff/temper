# Coordinator receipt — AR-DESIGN attempt-001

Date: 2026-09-18
Attempt: `zapote/power-entry/loss-budget/campaign/runs/2026-09-17-pfc-campaign/AR-DESIGN/attempt-001/`
Verdict: **ACCEPTED_CONDITIONAL.** Consistent evidence, bounded claims, eligible
for a conditional comparison — not hardware acceptance.

## 1. Admission

- Dispatch: **ADMITTED** (deadline computed at issue time, gate passes).
- Handback: **NOT COUNTED AS A VALIDATED RUN** — no checker was issued, per
  `ADMISSION.md`. Retained as source-and-arithmetic evidence, not a validated
  harness result. This is expected for the current campaign state, not a defect
  of the attempt.

## 2. Both corrections verified fixed

**Gate bias (was: "VGS = 10 V is conservative").** The attempt establishes the
actual gate voltage rather than assuming it: `Vregd` is the VCC rail, not VGS,
and the high-side gate sits behind a floating bootstrap (VCCHL/VCCHR referenced
to the switching node, internal bootstrap diode 0.8/1.0/1.3 V, 100-220 nF cap).
Solving the charge/discharge self-consistently:

| Rail | Actual VGS |
| --- | --- |
| High side | **~8.5 V** (8.49 at 220 nF; 7.31 at 100 nF; 6.31 worst case) |
| Low side | **~10.4 V** (9.91-10.91) |

So the 10 V data applies to the low side and **not** the high side. The
high-side correction is small (f_VGS = 1.02, bound 1.00-1.07) because the C7 die
is near fully enhanced above ~7-8 V, but it grows materially at 100 nF — hence
the requirement to specify ~220 nF. **Fixed, and the assumption is now a
computed value with a stated bound.**

**Junction temperature (was: an assumed value used to bound a margin).** Tj is
now an output. Coupling the device losses to the proposed assembly
(Ta = 40 °C, Rsa = 0.50 K/W, Rjc = 0.28 K/W max, Rcs = 0.50 K/W assumed) and
iterating gives **Tj ≈ 45.5 °C typ**, 46.3 °C on the 98 % curve, and ≤50.7 °C at
the pessimistic Rcs = Rsa = 1.0. Rds(on) at that temperature is **17.56 mΩ (HS)
/ 17.21 mΩ (LS) typ**. The arithmetic is self-consistent (≈3.91 W per device
across ≈1.28 K/W). **Fixed.** No 25 °C maximum was used as a hot value and no
typical hot value was presented as a bound.

## 3. Voltage contract — correctly left open

Line peak is **186.68 V** at 132 Vrms. The required device rating is a function
of an **undeclared** product clamp:

| Assumption | Permitted rating |
| --- | --- |
| line only, ×2 margin | 400 V |
| NXP 700 V node limit binding | 800 V |
| **added clamp ≤500 V** | **600 V** (the reference candidate) |
| retained-bridge equivalent | 1000 V |

The reference candidate's 600 V class is therefore **valid only with an added
≤500 V clamp**. A lower-voltage alternative is not supported by any retained
variant, and the attempt correctly **did not screen one for performance** rather
than assuming a rating. That is the discipline the previous attempt lacked.

## 4. Result

`P_saved = P_bridge − 225·(R_HS + R_LS) − P_add` across the committed bridge
bracket:

| P_bridge | P_saved (typ) | P_saved (98 %) |
| ---: | ---: | ---: |
| 23.0 W | 15.2 W | 13.98 W |
| 28.30 W | 20.5 W | 19.28 W |
| 35.0 W | 27.2 W | 25.98 W |

Additional losses: gate plus controller 2.5 mW; dead-time bound 2.7 µW; an
over-bound reverse-recovery figure of 43 mW whose operating value is unknown;
inrush and EMI **null**. The conduction saving (~7.8 W of the total) dominates
because the bridge switches at line frequency.

## 5. Retained uncertainties

Operating reverse-recovery loss at the zero crossing; start-up inrush body-diode
loss; EMI and filter re-qualification; a guaranteed hot Rds(on) maximum;
installed Rcs; and the slow C7 body diode (Qrr 18 µC typ) as a selection risk,
not a loss input.

## 6. The gating input

**The product's real input transient/surge contract** — the test level and
whether a front-end clamp is fitted. It is the one input that decides whether
*any* 600 V-class device may be used, so it gates the entire result. The loss
matter is otherwise favourable and robust: even the pessimistic 98 % curve at
the worst bracket point leaves **~26 W**.

## 7. Next

Resolve the transient/surge contract. If a ≤500 V clamp is acceptable, the
reference candidate stands and the comparison is decided. If not, the rating
requirement rises and the device must be re-selected against it — which is a
sourcing task, not a measurement.
