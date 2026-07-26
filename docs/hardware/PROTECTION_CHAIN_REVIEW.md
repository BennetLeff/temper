# Protection Chain Design Review

**Date:** 2026-07-25
**Scope:** the seven protection gates in `docs/STRATEGY.md` plus IGBT
desaturation.
**Status:** analysis and recommendations. **No design files were changed.**

Every number below is derived from the committed values in
`elec/src/modules.ato` and reproduced by hand; simulated figures come from
`simulation/harness/`. All models are uncalibrated (`calibrated: false`) — no
bench data exists.

---

## Summary

> **Updated 2026-07-25 (later same day).** OCP-01 and THM-01 are now **fixed**;
> OCP-01 required a transformer change, not the one-resistor fix this document
> originally proposed. See "OCP-01 — resolution" below. The remaining gates are
> unchanged.

| Gate | Requirement | As committed | Disposition |
|---|---|---|---|
| OCP-01 | 45–55 A | 37.6 A → **50.1 A** | **FIXED** — needed a new CT, not just a resistor |
| THM-01 | 85 °C | 99.5 °C → **84.9 °C** | **FIXED** — resistor + ref divider |
| OVP-01 | 390–410 V | 195 V sensed | **Blocked on a design decision** |
| OCP-02 | 55–65 A | absent | **Needs design** |
| THM-02 | coil 120 °C | absent | **Needs design** |
| DESAT | (not a numbered gate) | absent, but costed | **Needs decision: design or de-scope** |
| UVL-01 | <12.0 V | UCC21550B internal | Document only |
| UVL-02 | <2.9 V | ambiguous circuit | Identify intended circuit |

Two are one-part fixes. Two need circuits. One needs a decision before it can
be analysed.

---

## OCP-01 — primary overcurrent

### As built

```
VCC 3V3 ──[3.2k]──┬──[10k]── GND      V_ref = 3.3 × 10/13.2 = 2.500 V
                  └── TLV3201 INN
CT 1:100 ── burden 6.65 Ω ── TLV3201 INP
```

Trip = V_ref × N / R_burden = 2.5 × 100 / 6.65 = **37.6 A** (simulated 37.611 A).

Raising the trip by raising V_ref is impossible: 50 A needs
50 × 6.65 / 100 = **3.325 V from a 3.3 V rail.**

### Recommendation — change the burden resistor only

**R_burden: 6.65 Ω → 4.99 Ω** (E96 standard).

| | |
|---|---|
| Trip | 2.5 × 100 / 4.99 = **50.10 A** — centred in the 45–55 A window |
| Worst case (±1 % divider, ±1 % burden) | **49.4 – 50.9 A** — comfortably inside spec |
| Continuous dissipation at 15 A primary | **0.112 W**, improved from 0.150 W |

Lowering the burden *reduces* continuous dissipation, so the existing 0.25 W
1206 part is no worse off. Fault-condition dissipation is 1.25 W for the
microseconds before the comparator trips — confirm the chosen part's pulse
rating, but this is not a continuous-rating problem.

This is a single line change in `elec/src/modules.ato` plus the matching BOM
entry (`BOM.md:102–103`, which currently disagrees with source anyway).

### OCP-01 — resolution

**The one-resistor fix above was wrong, and was reverted before being kept.**

A 4.99 Ω burden puts the trip at 50.1 A, but `components.ato` records that the
`CST2010-100L` **senses only to 47 A**. Above its rated current the core
saturates and the secondary under-reads, so the comparator could trip late or
not at all — a worse failure than tripping early. Checking the divider and
burden arithmetic without checking the sensor's range was the gap.

The conflict was structural, not a value error:

| R_burden | Trip | Worst case ±1% | |
|---|---|---|---|
| 5.36 Ω | 46.64 A | 46.0 – 47.3 A | exceeds CT |
| 5.49 Ω | 45.54 A | 44.9 – 46.2 A | below spec |

OCP-01 wants 45–55 A; the CT sensed to 47 A; tolerances closed the 45–47 A
overlap. **No E96 value satisfied both.**

**Resolved by changing the transformer** to the Coilcraft **CST3015-100ED**
(Document 1608-1):

| | CST2010-100L | CST3015-100ED |
|---|---|---|
| Sensed current | 47 A | **88 A** |
| Turns ratio | 1:100 | **1:100 — unchanged** |
| Isolation | 1500 Vrms | **5000 Vrms, reinforced** |
| Creepage/clearance | — | **≥8 mm** |
| Frequency | to 1 MHz+ | 0.78 kHz – >1 MHz |
| Volt-time product | — | 638 V·µs |

Holding the ratio at 1:100 means the burden analysis carries over unchanged.
With 4.99 Ω the trip is **50.121 A simulated**, worst case 49.4–50.9 A, leaving
**1.73× headroom** to the 88 A rating.

Checked rather than assumed: volt-time at trip is 2.5 V × 14.3 µs = 35.7 V·µs
against the 638 V·µs limit (**18× margin**); the 35 kHz tank sits inside the
0.78 kHz–1 MHz range; secondary compliance is 3.27 V. Datasheet note 5 records
that the sensed-current figure is a 40 °C-rise reference point, not an absolute
maximum.

The isolation improvement is worth as much as the current rating: 5000 Vrms
reinforced with ≥8 mm creepage materially strengthens the IEC 60335-1 position
over 1500 Vrms.

**⚠ Not fabricable yet.** `temper:CST3015` has not been drawn —
`pcb/libs/temper.pretty/` holds only `CST2010` and the retired `CST-1005`. The
CST3015 is physically larger (16.6–16.9 g) and will require board re-layout
around T1.

### Still open — OCP-01 timing

The **<1 µs** propagation budget is not yet measured end to end. The `TLV3201`
behavioural model declares no timing model, so simulation cannot supply it.
The BOM records the `TLV3201AIDBVR` at **40 ns** propagation delay, which
leaves generous room, but the budget applies to the *whole chain* — comparator
→ `SN74HC4075` OR → latch — not the comparator alone. Sum the datasheet delays,
then confirm on the bench.

---

## THM-01 — heatsink over-temperature

### As built

```
VCC 3V3 ──[100k fixed]──┬── TLV3201 INP
                        └──[NTC 100k, B=4190]── GND
```

NTC resistance (`NTCALUG01A104GA`, R25 = 100 kΩ, B = 4190 K):

| Temp | R_NTC | V_sense with 100 k fixed |
|---|---|---|
| 25 °C | 100.0 kΩ | 1.650 V |
| **85 °C** (target) | **9.50 kΩ** | **0.286 V** |
| 99.5 °C (actual trip) | 6.02 kΩ | 0.188 V |

The threshold is wrong by ~14.5 °C, contradicting the module's own docstring
("85C threshold").

### The deeper problem

At the trip point the sense node sits at **0.19–0.29 V** — under 9 % of rail.
Comparator offset, leakage and noise all matter at that level, and the
volts-per-degree slope is poor. **The divider is badly proportioned**, not just
mis-valued. A fixed resistor equal to the NTC resistance *at the trip
temperature* maximises sensitivity.

### Recommendation — re-proportion the divider

**`r_ntc_fixed`: 100 kΩ → 10 kΩ**, and set the reference to **≈1.61 V**
(e.g. 10 kΩ / 9.53 kΩ from 3V3 → 1.610 V).

| Temp | V_sense with 10 k fixed |
|---|---|
| 25 °C | 3.000 V |
| **85 °C** | **1.607 V** ← trip, near mid-rail |
| 120 °C | 0.828 V |

Trip lands at **84.9 °C**. Sensitivity improves roughly 5×, and the node now
swings across most of the rail over the useful range.

Confirm the comparator polarity while making this change: rising temperature
*lowers* V_sense, so the fault must assert on `V_sense < V_ref`.

---

## OVP-01 — DC bus overvoltage — **decision required**

### As built

Divider: 3 × 430 kΩ (1.29 MΩ) over 10 kΩ → ratio **130:1**. Reference ≈1.50 V.
Trip at the sensed node = 1.50 × 130 = **195 V** (simulated 195.18 V).

### The ambiguity, which is in the source itself

`modules.ato`, inside `OVPComparator`:

> *"Note: v_bus reference might be different (HV ground), but here it's
> measuring relative to signal ground via divider? Actually OVP measures HV
> bus."*

The author was unsure what this divider is referenced to, and the uncertainty
was committed. Compounding it, `main.ato` declares `signal dc_bus_plus # +340V`
while every downstream use treats it as a **170 V half-bus** rail.

**Two readings, with opposite verdicts:**

- **Symmetric half-bus** — the divider senses one 170 V half. Trip at 195 V is
  ~15 % over nominal, and the total-bus equivalent is 390 V, matching the
  module comment and roughly satisfying OVP-01.
- **Full bus** — the divider senses the whole 340 V rail. Trip at 195 V is
  **below normal operating voltage**; the cooker would shut down on power-up.

These are not close. **Answering "what node does `v_bus` physically connect
to?" must precede any component change.** It is traceable in `main.ato` and the
schematic, and it is the one question in this review that measurement cannot
settle.

If the answer is full-bus, the top divider must grow to roughly 2.6 MΩ
(e.g. 6 × 430 kΩ) for a ~390 V trip.

---

## OCP-02, THM-02 — no circuit exists

Verified by inspection: exactly one `OCPComparator` instance and exactly one
`ThermalComparator` instance exist in `elec/src/modules.ato`, the latter wired
to the heatsink NTC.

- **OCP-02** (secondary OCP, 55–65 A, <5 µs) — `BOM.md:109–111` costs a shunt,
  differential amplifier and `LM393DR` comparator chain for it. None is wired.
- **THM-02** (coil NTC, 120 °C) — no coil-temperature sensing exists at all.

Both are non-negotiable gates in `STRATEGY.md`. They need designing, not
debugging. THM-02 is the cheaper of the two: a second `ThermalComparator`
instance with a coil-mounted NTC, using the re-proportioned divider above
(at 120 °C, R_NTC = 3.35 kΩ; a 3.3 kΩ fixed resistor would centre it).

---

## IGBT desaturation — costed, never designed

`BOM.md:145–163` costs 19 line items — `STTH1R06` 1200 V DESAT diodes, 1 MΩ
current-limit resistors, blanking capacitors — and
`grep -ni desat elec/src/*.ato` returns nothing. `docs/hardware/IGBT_DESATURATION_PROTECTION.md`
describes a circuit that does not exist.

DESAT detects an IGBT leaving saturation — the signature of a short-circuit —
and shuts the stage down within microseconds. It is standard practice on
hard-switched mains inverters, and the `UCC21550` gate driver family supports
it directly.

**This needs an explicit decision: design it, or de-scope it and remove the BOM
lines.** Leaving 19 costed parts for an undesigned safety circuit is the worst
of both.

---

## UVL-01, UVL-02

- **UVL-01** (gate-drive UVLO, <12.0 V): handled inside the `UCC21550B` — fixed
  silicon thresholds (VCC 7.6/8.1 V, VCCI 10.5/11.5 V per
  `docs/hardware/SAFETY_INTERLOCK_DESIGN.md`). No external circuit, no SPICE
  model. **Verify the datasheet thresholds satisfy the gate, then document it
  as vendor-guaranteed** rather than leaving it UNMEASURED.
- **UVL-02** (logic UVLO, <2.9 V): the measured candidate (TPS3700 monitoring
  RTD_AVDD, trips 2.825 V) belongs to the RTD subsystem. The more plausible
  intended circuit is the `TPS3823-33` watchdog supervisor (2.93 V typ), also
  fixed silicon. **Decide which circuit the gate refers to** and record it.

---

## Recommended order

1. **Answer the OVP-01 reference question.** It blocks analysis and may be the
   most serious defect here if the divider senses the full bus.
2. **Apply the two one-part fixes** — OCP-01 burden 6.65 → 4.99 Ω; THM-01 fixed
   resistor 100 k → 10 k with a ~1.61 V reference. Re-run
   `simulation/harness/` to confirm, then update the BOM entries.
3. **Decide DESAT** — design or de-scope.
4. **Design OCP-02 and THM-02.** THM-02 is a near-copy of the corrected
   THM-01.
5. **Document UVL-01/02** as vendor-guaranteed, with datasheet references.

Steps 1, 3 and 4 are engineering judgment. Step 2 is determinate and verified
above. Nothing here should be applied without a power-electronics review —
these figures were derived from committed values and uncalibrated models, and
have never been checked against hardware.
