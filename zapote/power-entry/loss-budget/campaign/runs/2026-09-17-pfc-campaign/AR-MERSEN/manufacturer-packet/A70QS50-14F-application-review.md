# Manufacturer application review — Mersen A70QS50-14F

**Prepared:** 2026-09-18  
**Subject:** confirmation of the capacitor-discharge application conditions
for A70QS50-14F against a described 400 Vdc bus discharge.

**Status of this document.** It is a *request for confirmation*, and a record
of the conditional screening already done. Nothing here is a qualified
operating point, a demonstrated coordination, or a hardware result. The
quantities we are least sure of are listed as such, and the questions we need
answered are specific.

---

## 1. Application

A single-phase boost power-factor-correction front end for an induction
cooker: mains rectifier, boost inductor and switch, 400 Vdc bus with an
electrolytic bank, feeding a quasi-resonant inverter. The fuse under
consideration is the **A70QS50-14F** (50 A, 14 x 51 mm French cylindrical),
evaluated as a bus-side candidate.

**Bus bank energy:** 2240.47 uF at 400 Vdc =
**179.24 J** stored, modelled as a single lumped capacitor.

## 2. The condition we are screening against

We read the A70QS page (catalogue p.20 / HS 20) as stating:

> ... these fuses have an **890 VDC rating for capacitor discharge
> applications up to 2.5 ms time constant**.

We read "time constant" as **L/R**, on the basis that the catalogue's DC
tables state `*Time Constant: L/R <= 1ms`, and the same A70QS page uses
`L/R <= 10 ms` and `10 ms time constant` interchangeably for its general DC
rating. **We are not certain the capacitor-discharge sentence uses the same
definition** — the explicit `L/R` statements concern the general DC ratings
and other product lines. Question 1 asks you to confirm it.

## 3. Fault scenario being analysed

**This inquiry evaluates U10 and U9 both failed short.** The loop also
exists with U10 shorted and a healthy U9 conducting; that separate case
does not establish shutdown without detection, latency and survival evidence.

- **U10 (the boost diode, C3D20065D) fails short.** This is what connects the
  400 Vdc bus to the switch node `a1`. Without it, a healthy U10 is
  reverse-biased and **blocks the discharge entirely** — a bare boost-switch
  short does *not* discharge the bank. That was established earlier in this
  work and is the reason U10 is named as a failed device rather than a
  conducting one.
- **U9 (the boost switch, STW65N65DM2AG) fails short.** This completes the
  loop from `a1` to the bus return. It is specified as *failed* short, not
  merely gated on. A healthy U9 might interrupt after detection, but no
  detection/latency or turn-off-survival credit is taken in this inquiry.
- **F2, a proposed series high-speed DC fuse in the bus path**, sits in this
  loop. With U9 failed short it is the **only** element that can interrupt,
  which is why its capacitor-discharge capability is the question.

The proposed stored-energy loop is `bank+ -> F2 -> U10 (short) -> a1 ->
U9 (short) -> PFC_BUS_MINUS -> bank-`. U12 (shunt) and F1 are outside
this loop. The bank and U9 source share PFC_BUS_MINUS; U12 bridges that
net to the rectifier-side minus net. F2 is proposed, not present in CAD.

The loop's resistance and inductance are **not known**. They are swept rather
than asserted:

| Quantity | Envelope swept |
| --- | --- |
| Loop resistance R | 5 mOhm to 5 ohm |
| Loop inductance L | 20 nH to 20 uH |

These are sensitivity cases, not proven application limits. Peak current
depends on both R and L; the largest L/R occurs at high L and low R.
Section 4 gives what we can currently estimate for this board, together with
what those estimates are not.

## 4. R and L for this board: estimates, with their assumptions

These are **estimates under stated assumptions**, not proven bounds. We are
giving them so the inquiry carries real numbers; we are not asking you to
treat any of them as established. Components with no published figure are
left null rather than filled with a plausible default.

| Term | Estimate | Basis and what it is *not* |
| --- | ---: | --- |
| Copper R, 20 C | 10.29 mOhm | geometry-derived from the least-resistance *extracted path* per capacitor |
| Copper R, 100 C | 20.49 mOhm | same method, elevated temperature |
| Fuse R | 4.64 mOhm | derived from 11.6 W at 50 A; a *hot* figure, so onset R is lower |
| Bank ESR, per bank | 118.42 mOhm | from tan-delta max at **120 Hz** and nominal capacitance |
| U9 failed-short residual | **null** | not published |
| U10 failed-short residual | **null** | not published |

Three caveats that matter more than the numbers:

1. **The copper figure is not a lower bound — it is a path estimate, and it
   tends to over-state.** It comes from tracing a single least-resistance
   path per capacitor, and other conductors (including the return-side B.Cu
   zone) were excluded from the sum. **Parallel paths can only reduce the
   effective resistance**, so the extracted-path figure sits above the true
   network value and cannot bound it from below.
2. **The ESR figure is a 120 Hz estimate, not a broadband bound.** It uses
   nominal capacitance, whereas the parts carry a +/-20% tolerance that alone
   moves the derived ESR by roughly a quarter, and it extends a 120 Hz
   loss-angle specification to the discharge waveform without evidence that
   the specification holds there.
3. **The listed resistances belong to different device states and must not be
   added into one subtotal.** In particular, U9's healthy on-resistance
   applies when U9 is *not* shorted; in the fault being analysed U9 is short
   and that term does not apply. There is also no published short residual to
   put in its place.

**Inductance: an estimate of roughly 76 nH to
2.8 uH**, the span coming from the
**return-path assumption** (return current directly beneath the forward trace
versus horizontally offset by the measured 34.5 mm worst case). Bank, fuse
and semiconductor-package internal inductances are not published and we have
**not** bounded them; they add an unknown amount above these figures.

**Where this leaves the location: INDETERMINATE — and deliberately so.**
Neither the copper resistance nor the inductance is bounded on the evidence
we have, and the two failed-short residuals that dominate the resistance are
unpublished. We therefore cannot say whether the real discharge lands inside
the screened region `{400*L <= R <= 0.64013 ohm}` or outside it, and we are
not asserting either. This is the gap the questions in Section 7 are aimed
at.

## 5. Representative discharge cases

Computed from the series R-L-C model (lumped C, constant R), and reproduced
in `representative-cases.json`. `tau` is `L/R`, the quantity we believe your
2.5 ms condition refers to; `zeta` is the damping factor, given because it
governs how oscillatory the real waveform is.

| Case | R | L | tau = L/R | zeta | Peak | Action |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Envelope peak corner | 5 mOhm | 20 nH | 4 us | 0.837 | 55.23 kA | 35848 A2s |
| Most underdamped cell (= the 4.00 ms exclusion) | 5 mOhm | 20 uH | 4 ms | 0.0265 | 4.06 kA | 35848 A2s |
| Second exclusion: tau = 2.52 ms | 5 mOhm | 12.6 uH | 2.52 ms | 0.0333 | 5.06 kA | 35848 A2s |
| Mid-damped, low R | 50 mOhm | 20 uH | 400 us | 0.265 | 2.96 kA | 3585 A2s |
| Near-critical (zeta ~ 1) | 0.2 ohm | 20 uH | 100 us | 1.06 | 1.50 kA | 896 A2s |
| Screen edge: R = 0.64013 ohm | 0.64 ohm | 20 uH | 31.2 us | 3.39 | 0.59 kA | 280 A2s |
| Most damped envelope corner | 5 ohm | 20 uH | 4 us | 26.5 | 0.08 kA | 36 A2s |

**Action basis.** The Action column is `E/R` exactly, by energy balance:
all the stored energy is dissipated in the loop resistance, so
`integral(i^2 dt) = 179.24/R`. It is not a numerical approximation,
and it is the quantity we compare against the **maximum** pre-arcing figure
of 280 A2s. A separate quadrature reproduces it to better than 1e-6 relative.

**Waveform character.** Two regimes occur in the swept range and we need
guidance on the applicable one:

- **Underdamped** (`zeta << 1`, e.g. 5 mOhm / 20 uH, `zeta = 0.0265`): the
  current rings, and `L/R` understates how long energy stays in the loop.
  The oscillation-envelope decay is `2L/R` (8.0 ms at that corner), not `L/R`
  (4.0 ms).
- **Overdamped** (`zeta > 1`, e.g. 0.64 ohm / 20 uH): a unipolar pulse.

## 6. What we have screened, and what it does not mean

Intersecting the envelope with the conditions we could read:

- **Pre-arcing action screen** (adiabatic, L-independent): `E/R` versus the
  catalogue's **maximum** pre-arcing I2t of 280 A2s. Met for
  `R <= 0.640 ohm`. This is an **available-action screen, not a melting
  result** — it does not establish melting across arbitrary pulse durations,
  temperatures and fuse tolerances.
- **Time-constant condition** `L/R <= 2.5 ms`: 2 of those cells fail, at
  (5 mOhm, 12.62 uH) and (5 mOhm, 20 uH).
- **Peak current**: up to 55.2 kA, screened only against the **general**
  100 kA DC interrupting rating — a different condition from capacitor
  discharge.

**Result: 142 of 400 swept cells pass these screens.** They are *not*
qualified operating points. The capacitor-discharge current limit is
**unknown**, and the general DC figure was used in its place; that gap is
exactly what Question 2 addresses.

## 7. Questions

**Q1 — Time-constant definition.** Does the 2.5 ms time constant in the
capacitor-discharge sentence mean `L/R`? If the applicable definition differs
for oscillatory discharges, what is it, and how should an underdamped case
(`zeta = 0.027`) be evaluated against the rating?

**Q2 — Applicable current limit.** The 890 Vdc capacitor-discharge rating
carries no separately published peak-current limit; we could only use the
general 100 kA DC interrupting rating (`L/R = 11.6 ms`). What peak current
limit applies to capacitor discharge at 890 Vdc, and does the 100 kA general
figure remain valid for a discharge with a much shorter or oscillatory
waveform?

**Q3 — Minimum breaking current.** The A70QS line publishes no MBC column in
this catalogue (the D70QS and D100QS lines do). What is the minimum breaking
current for A70QS50-14F at the 890 Vdc capacitor-discharge condition? This
decides whether a high-impedance fault is cleared or merely held.

**Q4 — Capacitor-discharge let-through.** Is there a DC or
capacitor-discharge **total clearing I2t** (let-through) characteristic for
A70QS50-14F, valid at the 890 Vdc condition? The catalogue's only clearing
figure is 1500 A2s at 700 V**AC**, which we cannot apply to this DC case.
Without this, we cannot compare against a bank/copper withstand I2t, and
clearing stays undemonstrated.

Also, if a capacitor-discharge-specific datasheet or application note exists
for the A70QS range, that is the single most useful document you could
provide.

## 8. What we would do with each answer

| Answer | Consequence |
| --- | --- |
| Q1: `L/R` confirmed | Re-map as a plain `L/R` test; the 2 excluded cells stand and the screen becomes well-defined. |
| Q1: a different definition | Re-derive the exclusion set; an underdamped case could be outside the rating at a much higher `R`. |
| Q2: a lower cap-discharge peak limit | Re-cut the region; at 55 kA peak this could exclude the low-impedance cells entirely. |
| Q3: an MBC above our low-current faults | The fuse would not clear high-impedance faults; the protection claim would need restructuring. |
| Q4: a let-through I2t | Compare against a sourced bank/copper withstand I2t — one input to coordination, alongside applicable fault, current, duty and withstand evidence. |

## 9. What we are not claiming

- Not a qualified operating point. The loop's R and L are unknown; the
  envelope is a sweep, and only one unknown cell in it is real.
- Not a demonstrated coordination. No let-through figure and no sourced
  bank/copper withstand exist yet (Q4).
- Not a melting result. The action screen is a screen.
- Not a hardware result. No bench or powered testing has been performed.
- **Not an established bound.** The R and L figures in Section 4 are
  estimates under stated assumptions; the question we are asking you does
  not depend on their being proven limits.
- Not a CAD or BOM change. A70QS50-14F is a candidate, not a design change.

## 10. Provenance

- Catalogue quoted: Mersen *High Speed Fuses* (2024-12-16), PDF sha256
  `e0e5b788fcc883650ff771c4fa006986fec4238293856ab200b56e2cf44e9789`,
  A70QS pages PDF p.20 (HS 20) and p.21 (HS 21).
- Bank/energy constants: 2240.47 uF, 400 V, 179.2376 J.
- Envelope: 25 R x 16 L = 400 cells, R in [5 mOhm, 5 ohm], L in [20 nH,
  20 uH]; retained at
  `../attempt-001/raw/compute_result.json` and
  `../AR-COORD/attempt-001/raw/compute_result.json`.
- Representative cases in this packet: `representative-cases.json`, computed
  by `build_packet.py` with the same model; oracle checks on peak and action
  agree to a worst relative error of 8.31e-04.
- Loop R and L figures: AR-BOUNDS attempt-001, derived from
  `zapote/power-entry/shunt-repair/candidate/section.kicad_pcb`
  (sha256 `34e6fba9...`), which is the board the AR-FAULT fault netlist was
  taken from. That is deliberately *not* `pcb/temper.kicad_pcb`, which
  contains none of the loop nets.

**Correction notice.** An earlier revision of this packet presented the same
numbers as established bounds ('R >= 10.29 mOhm', a 'sourced sub-total', and a
0.4466 ohm crossing threshold). Those bound claims are **withdrawn**: the
copper figure is a single-path estimate excluding parallel conductors, the ESR
figure is a 120 Hz nominal-capacitance estimate, and the components belong to
different device states. The numbers are unchanged; their status is not.

