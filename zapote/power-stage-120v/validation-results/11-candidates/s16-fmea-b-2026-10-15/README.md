# Candidate B FMEA: one TPS3701 per window against the TL431 + LM339B monitor core

Desk study, 2026-10-15, on the read-only PS worktree (`zapote/power-stage-120v`, HEAD ee0698899 at the start,
dec0ce3a4 at the end; the two commits in between touch only OPEN-ITEMS S16 wording and the stage-44 SELV caps).
Nothing in the repo was edited. Everything here reruns offline:

```
sh scripts/run_all.sh     # manifest, sources, bands, fault simulation, truth tables, metric, timing -> results/
```

**Verdict.** Candidate B, as the S16 study drew it (V2), is not a net safety improvement over 1c-4420 (V1) under the
project's rules. It is better on most rows:
- **Front end.** Dormant masking across the three monitors falls by 39 %: 3.8 against 6.3 FIT·rails.
- **Whole-rail modes.** The front-end modes that hide a whole rail fall from 0.17 to 0 FIT, or from 4.3 to 1.0 FIT when
  package failures are spread over the pins.
- **Total.** Total exposure is 16.8 against 19.3 FIT·rails (−13 %). The common downstream chain, 13.0 FIT·rails, is the
  same in all three variants and dominates the total.

The S16 objection on C4 does not hold. A drift of the TPS3701's internal reference cannot silently mask a threshold
past its hard limit, for the same reason a TL431 drift cannot: the window's other threshold trips first.

V2 as drawn does add a new dormant path, and no test covers it:
- **How it happens.** Either of two single faults puts the 17 V span on a TPS3701 input rated 7 V absolute maximum:
  an open bottom resistor in a span divider (C5), or an INB-to-VDD pin short (N3).
- **What follows.** The data sheet and TI's safety documents do not say what the part does then, and the span-OV window
  can be lost. By the project rule, a dormant single fault in a protective path counts as a regression.

Two amendments remove that path, and with them V2 beats V1 in every exposure case (16.7 against 19.3 FIT·rails in the
base case):
- **F2:** split each span divider's bottom resistor into two in parallel. That is +6 placements and about +$0.13.
- **VDD from the local 5 V:** power both TPS3701s from v5 instead of P. That is a routing change only.

Two things stay worse even with the amendments:
- **C1 latency.** The OV path is +27 µs slower, typical, and TI gives no maximum.
- **C5 rate.** 2.8 against 2.0 FIT per rail. V1's 750 Ω neg-UV top still catches a deep collapse when its bottom
  resistor opens, and the split span-UV bottom doubles that sub-mode.

**So no single change makes V2 strictly better on every row.** The gain is about 2.6 FIT·rails (13 %) for about
+$1.49 a board over V1 and a layout change in three islands. That is worth taking only if those islands are re-laid for
another reason. **Keep 1c-4420 for S16.** If B is ever built, build it amended (V2+F2+v5), not as drawn.

---

## 1. Variants and how each claim was checked

| Variant | Monitor core per rail | Divider taps (top / bottom) | Source |
|---|---|---|---|
| **V0** (s43 as built) | TL431AIDBZR U17, rref 2.2 k, halfref 10 k / 10 k, LM339BIDR U29 | 4.42 k/10 k, 7.68 k/10 k, 120 k/10 k, 133 k/10 k | `elec/src/f6_bias.ato:112-227` |
| **V1** (1c-4420) | TL431BIDBZR, R79 4.42 k, LM339BIDR | 750/10 k, 2.94 k/10 k, 90.9 k/11 k, 104 k/11 k | `s16…/results/monitor_wc.md` |
| **V2** (candidate B) | TPS3701DDCR U29 (neg window), U47 (span window), 100 nF on U47 VDD | 15.8 k/4.42 k, 28.4 k/6.2 k, 240 k/6.2 k, 86.6 k/2.0 k | s16 README §5 |
| V2+F2+v5 (amended) | as V2; both TPS3701 VDD on v5; span bottoms split | span UV 193 k / 2 × 10 k, span OV 138 k / 2 × 6.2 k | `results/bands.md` |

**Designators.** Stage 44 took C169–C175 for the SELV transfer caps. Candidate B's three new decouplers are therefore
**C176 / C177 / C178** (LS / HS-A / HS-B), not C169–C171 as the S16 table has them. U47–U49 are still free at dec0ce3a4.

**Checks.**
- **Model.** `scripts/model.py` is a byte-identical copy of the S16 `model.py`. `bands.py` reproduces the S16 committed
  worst-case trip and release bands for V0, V1 and V2 to 1e-4 V.
- **Fault simulation.** `monitor_fault_sim.py` solves each monitor's resistor network at DC. It injects every single
  fault: TI FMD die modes, every pin open, every adjacent pin pair TI lists, every resistor open and every capacitor
  short. It then drives each rail to its hard limit H and qualified limit Q in turn.
- **Pin mapping.** Pins follow `f6_bias.ato` (LM339B pin 3 = P, 12 = N; outputs 1, 2, 13, 14 on `good`) and the
  SLCS006Z / SBVS240C pinouts.
- **Truth tables.** `truth_table.py`, the extended copy, writes the original g05 table byte-identical as a control. It
  then adds per-variant tables on the as-built heartbeat chain (`results/truth_table_b.md`).
- **Metric.** `fmea_metric.py`, the extended copy, reproduces the committed c24 scores (control). It then adds the
  front-end rows (`candidate_b.py`).

**Limits used (from the S16 model).**
- **H, hard:** span OV 21.0 V (2EDR8259X VDD operating maximum); span UV 12.4 V (VGS ≥ 10 V with a 2.4 V neg rail);
  neg UV 1.506 V (physical off-gate edge limit); neg OV 5.5 V.
- **Q, qualified:** span OV **19.0 V**, the out-D33 hot-load re-run that the 1c-4420 decision rests on; span UV 15.5 V;
  neg UV 1.754 V; neg OV 2.4 V.
- **Masking.** "Masked" means masked against H unless stated otherwise.

## 2. Row table, V0 / V1 / V2 side by side

Per rail. S / O / D follow c24 §3:
- **S:** 7 = one rail lost, 5 = one window partly lost, 3 = announced.
- **O:** set by the FIT of the mode.
- **D:** 9 = dormant, 1 = announced.

Rates for the die and passive rows use the TI FMD applied to total FIT (c24's convention). Rates for the pin rows (N1–N4)
spread the package FIT 50 % over pin opens and 50 % over adjacent shorts; this split is an assumption. Full rows are in
`results/fmea_b_metric.md`. "FIT d/a" is dormant FIT / all FIT.

| Row | Failure mode | Effect at `good` → BIAS_GOOD → DIS | V0 FIT d/a, S-O-D RPN | V1 | V2 | V2+F2+v5 |
|---|---|---|---|---|---|---|
| C1 | Rail leaves its window (the monitored event) | Comparator pulls `good` low; the heartbeat stops; DIS high | detection ≤ ~101 µs typ | ≤ ~101 µs | ≤ ~124 µs typ (OV, 10 mV overdrive) | same as V2 |
| C2 | Output cannot pull low (die Hi-Z / saturated high; output pin open) | That threshold is never reported; `good` stays high | 6.4/6.4, 5-5-9 **225** dormant | 6.4/6.4, 225 | 2.4/2.4, 5-4-9 **180** | 180 |
| C2b | Comparator out of specification (one threshold moves; in V2 this includes the internal reference) | One threshold shifted, dormant if it shifts outward (k_o) | 4.8, 180 | 4.8, 180 | 3.2, 180 | 180 |
| C3 | Output stuck low / false trip | `good` low, drive off | 0/4.0, 12 announced | 12 | 0/2.4, 12 | 12 |
| C4 | Reference: TL431 open / short / drift, rref / R79 / R80 | Open → halfref ≈ 7.7 V, UV trips. Short → halfref 0, OV trips. Drift: bounded (§3) | 0/7.5, 3-5-1 **15** announced | 15 | no separate part; see §3 and C2b | – |
| C5 | Divider resistor open or drift (8 per rail) | Top open on UV / bottom open on OV: announced. Bottom open on UV / top open on OV: that threshold lost. **V2: span bottom open puts 17.4 V on a 7 V pin** | 2.4/4.0, 180 mixed | 2.0/4.0, 180 (neg-UV bottom open still catches < 1.73 V) | 2.8/4.0, 180 (**overstress**: span-OV window may be lost) | 2.8/4.8, 180 (no overstress) |
| C6 | 1 nF tap capacitor short | UV tap: announced. OV tap: OV lost | 0.5/1.0, 135 mixed | 135 | 135 | 135 |
| C7 | Supply in the "sliver" | V0/V1: about 1.7–2.0 V, where the LM339B is below its 2 V minimum and the downstream may be live, so `good` is undetermined. V2: caught | 3-1-1 3 (covered by driver UVLO) | 3 | **closed** | closed |
| C8 / C9 | U40 Schmitt → BIAS_GOOD; U22 / U23 DIS NAND | Unchanged: 3-rail dormant single points | 216 / 216 | 216 / 216 | 216 / 216 | 216 / 216 |
| N1 | Supply pin open (LM339B VCC / GND; TPS3701 VDD / GND) | V0/V1: **all four thresholds** of the rail. V2: one window (2) | 1.0, 7-3-9 **189** | 189 | 0.67, 5-3-9 **135** | 135 |
| N2 | Output pin shorted to the adjacent supply pin (LM339B 2–3; TPS3701 5–6) | `good` tied to the supply: whole rail masked. With VDD = P, 12–21 V also reaches the ISO6721FB / oscillator input | 0.51, 7-3-9 189 | 189 | 0.33, 7-2-9 126 | 0.33, 126 (tied to 5 V: no overstress) |
| N3 | TPS3701 INB shorted to the adjacent VDD pin | VDD = P: 17 V on INB, OUTB asserts if the pin survives, unknown after damage. VDD = v5: 5 V, announced | – | – | 0.33, 5-2-9 **90** dormant | 0/0.33, 3-2-1 6 announced |
| N4 | Other input pin opens and adjacent input shorts | Mostly undetermined (TI: "output may be low or high") | 5.0/10.6, 225 mixed | 225 | 0.33/2.0, 90 mixed | 90 |
| N5 | Span-OV hysteresis (V2 only) | The release lower corner 17.06 V is below the 17.425 V rail maximum, so a unit may not recover after a genuine OV. Fail-safe, availability only | – | – | 2 | none (release ≥ 17.53 V after the re-centre) |
| N6 | TPS3701 start-up, td(start) 155 µs typ | The output state during start-up is not stated in text (SBVS240C p.6 note 2) | – | – | bench capture | bench capture |
| N7 | 100 nF p–n decoupler short (C176 new in V2) | Rail collapses, announced | 6 | 6 | 9 | 9 |

**Status per variant.** All three variants have the same classes of dormant rows: C2, C2b, C5, C6, N1, N2, N4. V2
moves C2 and N1 to lower O or lower S, and adds N3 plus the C5 overstress. The amendments turn N3 back into an
announced fault and remove the C5 overstress.

**Truth-table check** (`results/truth_table_b.md`, single rail, as-built heartbeat chain):
- **Reference faults.** TL431 open or short, and TPS3701 reference at 0 V or at 2 V, give DIS = 1 in every rail state.
- **Supply-pin faults.** LM339B VCC open leaves DIS = 0 for every rail fault. TPS3701 VDD open leaves DIS = 0 only for
  its own window's faults.
- **Dormant drifts.** A drift just inside its announcement point misses the Q excursions but catches every H excursion
  in all three variants.

## 3. Reference drift, treated the same way in both designs (the crux)

**V0 / V1.** A TL431 drift (or an R79 / R80 drift) scales the halfref, so it moves all four thresholds together.
**V2.** One internal reference sets both VIT−(INA) and VIT+(INB) ("the other input is connected to the internal
reference … trimmed to be equal to the reference voltage", SBVS240C §7.3.1 p.11). A drift therefore moves that IC's two
thresholds together.

**Method.** In both designs, a drift that raises the OV thresholds also raises the UV thresholds, and the UV trips
(announced) once its threshold passes the rail. A downward drift trips the OV first.

`bands.py` takes the worst-case vertex of every non-shared parameter: resistors at 0.1 % + 25 ppm × 60 K, LM339B VIO
and IB, TPS3701 VIT trims and IIN. It sets the rail at its worst end (span 16.575–17.425 V, neg 1.965–2.076 V) and finds
the most a threshold can move before a companion announces. The result is independent of the drift magnitude.

| Variant | Drift → masked threshold | Companion that announces | Drift at announcement | Worst dormant threshold | to H | to Q |
|---|---|---|---|---:|---:|---:|
| V0 | up → span OV | span UV / neg UV | +5.6 … +11.4 % | 19.51 V | +1.49 | −0.51 |
| V0 | down → neg UV | span OV / neg OV | −5.4 … −10.4 % | 1.645 V | +0.140 | −0.109 |
| V0 | down → span UV | | | 14.78 V | +2.38 | −0.72 |
| V1 | up → span OV | span UV / neg UV | +7.4 … +11.9 % | 19.96 V | +1.04 | −0.96 |
| V1 | down → neg UV | span OV / neg OV | −7.2 … −10.9 % | 1.684 V | +0.179 | −0.070 |
| V1 | down → span UV | | | 14.45 V | +2.05 | −1.05 |
| V2 | up → span OV (running / after restart) | span UV of the same IC | +11.1 % / +10.3 % | 19.94 / 19.79 V | +1.06 / +1.21 | −0.94 / −0.79 |
| V2 | up → neg OV | neg UV of the same IC | +14.8 % | 2.592 V | +2.91 | −0.19 |
| V2 | down → neg UV | neg OV of the same IC | −13.0 % | 1.574 V | **+0.068** | −0.18 |
| V2 | down → span UV | span OV of the same IC | −7.6 % | 14.49 V | +2.09 | −1.01 |
| V2+F2 | up → span OV | span UV | +11.4 % | 20.54 V | +0.46 | −1.54 |

**What this shows.**
- **No variant can silently mask a threshold past H through a reference drift, of any size.** The S16 C4 objection
  ("a drift in the TPS3701's reference can silently mask its window") is wrong at H. It is right at Q, but there it
  applies equally to the TL431: V1 drifting up can hold span OV at 19.96 V, against 19.94 V for V2.
- **What does differ:**
  - **V2's neg-UV drift-down margin to H is thinner:** +0.068 V against +0.179 V for V1.
  - **The F2 re-centre** of span OV to 18.2 V narrows V2's span-OV drift margin to +0.46 V. It is still positive.
- **TL431 gross faults (C4) are announced in V0 / V1.** Open is 25 % and short is 35 % of the TL431's 6 FIT (TI SNVA914
  p.1). In V2, the equivalent reference collapse is announced too: reference at 0 V gives OUTB low, reference high gives
  OUTA low (truth_table_b).
- **Per-comparator faults are the real asymmetry, and they are not bounded in any variant.** These are the
  out-of-specification modes: LM339B 30 % (SLCA004 Table 1-3), TPS3700-Q1 proxy 40 % (SLVAEM2A Table 3-1). One
  comparator's threshold moves, and nothing else does.
  - **To mask span OV at H**, the input-referred shift must be +221 mV (V0), +278 mV (V1) or **+74 mV (V2)**. That is
    +17.7 %, +16.1 % and +18.5 % of each comparator's own reference level.
  - **In millivolts V2 is 3–4× more sensitive.** As a fraction of its reference it is the same.
  - **The FMDs give no magnitude distribution,** so this enters the metric only through k_o (base 0, sensitivity 0.5,
    as in c24).

**Frequency, by source.**

| Part | Rate (FIT) | Source | Die failure modes (FMD) |
|---|---|---|---|
| TL431 | 6 (die 4, package 2), IEC TR 62380 | TI **SNVA914 p.1** (TL431-Q1/TL432-Q1; package not stated) | open 25 / short 35 / out of spec 40 % |
| LM339B | 16, SOIC-14 (die 2, package 14) | TI **SLCA004 Table 1-1 p.3**, the LM2901/LM2901B proxy (same data sheet SLCS006Z) | Hi-Z 15 / saturated high 25 / saturated low 25 / out of spec 30 / two pins 5 % (Table 1-3 p.4) |
| TPS3701 | **no TI document exists** (ti.com product page, 2026-10-15). Proxy: 4 (die 2, package 2) | TI **SLVAEM2A Table 2-1 p.3** (TPS3700-Q1 DDC) | Hi-Z 30 / stuck low 30 / out of spec 40 % (Table 3-1 p.5). TPS3702 SFFS074 has the same split. Alternative: TPS3703 SFFS944 Table 3-1 (fail to trip 15 / false trip 15 / out of spec 65 / delay 5 %) |
| TI MTBF/FIT estimator (HTOL, 60 % CL, 0 fails, Ea 0.7 eV, 55 °C) | TL431A/BIDBZR **8.0**, LM339BIDR **8.0** (1,463 units); TPS3701DDCR **0.1** (183,306 units) | ti.com estimator; recomputed from its own table in `sources.py` | TI warns these are not comparable across parts, so they are used as a sensitivity only |
| Resistor 0.5 FIT (open 80 / drift 20 %); MLCC 0.5 FIT (short 50 %) | — | **class assumption** (c24's) | swept ×5 |

## 4. C5 and N3: overstress on a TPS3701 input

**Rating** (SBVS240C §6.1 p.4):
- VINA, VINB: −0.3 to +7 V absolute maximum; recommended 0 to 6.5 V (§6.3).
- "The INA and INB inputs swings from ground to 1.7 V (7.0 V absolute maximum), regardless of the device supply voltage"
  (§7.3.1 p.11).
- The only current rating is the 40 mA output-pin rating. No input current or clamp structure is specified anywhere in
  the data sheet.

**What TI's FMA covers.** The TPS3700-Q1 pin FMA assumes all pins are in the recommended range with VDD = 5 V (SLVAEM2A
§4 p.6). Every TI FMD covers "random failure events and … not … misuse or overstress" (p.5). **No TI document states
what a TPS3701 does with 17 V on INx.**

**Pin voltage and current with a bottom resistor open** (`results/bands.md`). The rail is at its 17.425 V maximum.

| Variant | Tap, bottom open | Pin voltage (open circuit) | Rating | Current if the pin clamps at 7 V / at 0 V |
|---|---|---:|---:|---|
| V0 / V1 | any span tap | 17.4 V | 38 V (LM339B) | no issue: "either or both inputs can go to maximum VCC level without damage" (SLCS006Z p.7) |
| V2 | span UV (240 k top) | **17.4 V** | **7 V** | 43 µA / 73 µA |
| V2 | span OV (86.6 k top) | **17.4 V** | **7 V** | 120 µA / 201 µA |
| V2 | neg taps | 2.08 V | 7 V | none (inside rating) |

**Behaviour if the rating is exceeded: unknown from TI data.** The simulation therefore takes both outcomes:
- **Span-UV bottom open.** If the pin survives, span UV is lost; that is dormant, as in V1. If the IC is damaged, span OV
  may be lost too (k_u).
- **Span-OV bottom open.** If the pin survives, OUTB asserts (announced). If the IC is damaged, it may later release
  (k_u).
- **N3, INB shorted to VDD** (adjacent pins 4–5, with VDD = P = 17 V): the same as the span-OV bottom-open case.

**Cheapest fix.** A series resistor does nothing here unless the pin has a clamp, and none is specified. A zener clamp's
leakage is specified, if at all, far from 0.4 V of reverse bias, so the S16 band could not be re-proven from a data
sheet. Two fixes do work:
1. **F2: split each span bottom resistor into two equal resistors in parallel**, with both halves already on the BOM.
   When one half opens, the pin rises only to about 0.8 V. Then span OV trips at once (announced), and span UV falls to
   about 8.1 V (a partial mask, no overstress).
   - **Span UV: 193 k / 2 × 10 k** (RT0603BRD0710KL, 2.1 M stock). Worst case: trip 15.640–16.042 V, release
     15.758–16.440 V. Margins: Q catch +0.140 V, rail +0.136 V. S16's own values gave +0.182 / +0.089 V.
   - **Span OV: 138 k / 2 × 6.2 k** (RT0603BRD076K2L, 90 k stock). Trip 17.978–18.436 V, release 17.525–18.299 V.
     Against the 19.0 V qualified ceiling: catch +0.564 V, rail +0.553 V. S16 gave +0.058 / +0.074 V against 18.0 V.
   - **Side effect: the re-centre also fixes N5.** The release lower corner moves above the rail maximum. Against
     S16's old 18.0 V basis the catch side is −0.436 V, so it relies on the 19 V hot-load re-run already used for
     1c-4420.
   - **Cost.** +6 placements and about +$0.13 a board for the bottoms. The 2.0 k line goes. The new tops (193 k,
     138 k) replace the 240 k and 86.6 k lines; their price and stock were not looked up.
2. **VDD from the local 5 V (v5) instead of P**, for both TPS3701s. A routing change, no parts.
   - **N3:** 5 V on INB is inside the rating, so the fault is announced.
   - **N2:** `good` gets tied to 5 V, not to 12–21 V, which removes the downstream overstress.
   - **The sliver stays closed.** The TPS3701 is specified from 1.8 V and holds OUTA low in UVLO down to V(POR) 0.8 V.
     Below that, the downstream on the same v5 is unpowered.
   - **C176–C178** then decouple v5.

With both fixes the fault simulation finds **no single fault that overstresses an input** (`results/fault_sim.md`,
V2+F2+v5).

## 5. Other row checks

**C1, propagation delay.**
- **Data sheet values.** The data sheet gives typicals only, with no minimum or maximum (SBVS240C §6.6 p.6):
  tpd(HL) 9.9 µs and **tpd(LH) 28.1 µs**, at ±10 mV overdrive and VDD 24 V.
  - "High-to-low" means the input falls, which is a UV assert.
  - "Low-to-high" means the input rises, which is an **OV assert**. The S16 note quoted only the 9.9 µs figure; the OV
    path is the 28.1 µs one.
- **Figures 12–13 (p.8)** use a ±200 mV step over −40…125 °C at VDD 1.8 and 36 V. They read ≤ 9.6 µs for HL and
  ≤ 2.5 µs for LH (typical curves, read by eye).
- **No safety document gives timing.** The LM339B gives 1 µs typical with no maximum either (SLCS006Z §6.13 p.12).
- **The bound I can argue.** The long delay occurs only at small overdrive, and small overdrive means the rail is
  crossing the threshold slowly. The rail's excursion past the threshold during the delay is slew × delay: 28 mV at
  1 V/ms, 0.28 V at 10 V/ms. A fast fault arrives with a large overdrive and sees the 2–10 µs figure-12/13 delays.
- **Total, comparator to BIAS_GOOD** (`results/timing.md`):
  - V2: 106–124 µs typical, against 92–101 µs for V0/V1. This includes the tap RC and the 90.3 µs heartbeat SPICE bound.
  - With an assumed ×3 guard on the typical delay and a shorted pump cap: ≤ 212 µs.
- **Rail faults are ms-scale (c24).** C1 stays "function, announced" in every variant, but V2 is slower.
- **What would settle it:** a bench distribution of tpd(LH) at 10 mV overdrive on about 10 units at −10 / 25 / 85 °C.

**C7, the sliver.**
- **V2 closes it.** Confirmed from SBVS240C p.5 note 2 and §7.4.2–7.4.3 p.11: OUTA is driven low in UVLO
  (0.8 V < VDD < 1.3–1.7 V), and the part is specified from 1.8 V.
- **V0/V1 still have one, but the c24 basis is wrong.** c24 used an LM339B minimum of 3 V; SLCS006Z §6.4 p.6 says
  **2 V**.
  - **Between 2.0 and 2.7 V** the unregulated halfref (≈ 0.45 P) sits above the span-UV tap (P/13), so span UV
    catches.
  - **Between about 1.7 and 2.0 V** the LM339B is below its minimum. So is the TPS70950, below its 2.7 V input minimum
    (SBVS186H p.4), while the downstream (≥ 1.65–1.71 V, c24) may be live.
  - **Driver UVLO** still holds the gates there.

**Supply-pin fault on V2.**
- **VDD or GND open** leaves the device unpowered and both outputs Hi-Z (SLVAEM2A Table 4-3; SBVS240C §7.4.3). That
  window's two thresholds are lost (dormant, N1).
- **A VDD-to-GND short** shorts P (or v5) and is announced.
- **The LM339B equivalent loses all four thresholds.** VCC open: k = 1. GND open: k_u, because "lowest voltage pin will
  drive GND pin internally", class A (SLCA004 Table 1-6).

**Proof tests.**

| Test | V0 / V1 | V2 / V2+F2+v5 |
|---|---|---|
| OPEN-ITEMS B8 / DECISIONS 52 end-of-line veto (force MON_GOOD_HA low, then MON_GOOD_HB low) | Screens the HS veto corridor downstream of the monitors. **Detects 0 %** of front-end dormant masking | 0 % |
| Power-on | Nobody reads BIAS_GOOD (it reaches no J4 pin; readers are U22 / U23 only). Power-up reveals only announced faults, by the hob refusing to start | same |
| Per-tap forcing, end of line (hypothetical: drive each tap past its threshold through a pad) | Would reveal 88 % / 91 % of front-end dormant masking FIT (comparator, pins, tap caps), but **only defects present at manufacture**. It misses divider opens | 72 % / 73 % (V2's masking has a larger divider share) |
| LS "raise the rail" (hypothetical: ground the unused TPS7A47 3P2V pin 6, so 17.0 → 20.2 V; SBVS204G p.3, Eq. 2) | Catches every LS span-OV mask, dividers included: 27–28 % of LS dormant masking. 20.2 V lies above every variant's span-OV corner (V1 18.60 V), below the 21 V driver maximum, and VGS 18.2 V is under 20 V | 27–31 % |

- **No hook exists today.** Pin 6 is unconnected (`f6_bias.ato:64-77`), and there are no test points in the `.ato`
  sources. The HS rails would need a hook on the RECOM FB node.
- **No field diagnostic in any variant.** A random field failure that masks a window stays dormant in all three, so
  D = 9 throughout.

## 6. Quantified exposure (c24 RWL, FIT·rails)

**How the metric is built.**
- **Front end.** A front-end mode counts thresholds / 4 rail-equivalents, times 3 rails.
- **Chain.** The chain is c24's P2H heartbeat, 13.0 FIT·rails in the base case, identical in every variant.
- **Script.** `scripts/fmea_metric.py`, which also reproduces c24's committed numbers.

| Case | V0 | V1 | V2 | V2+F2+v5 | front end V1 → V2 |
|---|---:|---:|---:|---:|---|
| Base (TI FS FITs, FMD on total FIT, k_u 0.5, k_o 0) | 19.59 | 19.29 | **16.83** | **16.68** | 6.29 → 3.83 |
| k_u = 1 | 27.53 | 27.23 | 25.18 | 24.58 | |
| k_u = 0 | 11.65 | 11.35 | 8.48 | 8.78 | |
| k_o = 0.5 | 31.89 | 31.59 | 28.53 | 28.38 | |
| Allocation B (die FMD on die FIT; package FIT on pins, assumed split) | 22.83 | 22.53 | 18.93 | 18.53 | 9.53 → 5.93 |
| TI estimator FITs (8 / 8 / 0.1) | 17.08 | 16.78 | 15.07 | 14.92 | |
| TPS3703 FMD for the TPS3701 | 19.59 | 19.29 | 15.93 | 15.78 | |
| Passives ×5 | 32.69 | **31.19** | **31.73** | 30.98 | V2 as drawn loses here (C5 overstress) |
| Worst (k_u 1, k_o 0.5, passives ×5, allocation B) | 61.28 | 59.78 | 58.93 | 55.43 | |

**Per threshold, base case, 3 rails, FIT** (span OV = gate overstress; neg UV = shoot-through):

| | neg UV | neg OV | span UV | span OV | whole-rail front-end masks (base / allocation B) |
|---|---:|---:|---:|---:|---|
| V0 | 6.17 | 6.92 | 6.26 | 7.01 | 0.17 / 4.27 |
| V1 | 4.97 | 6.92 | 6.26 | 7.01 | 0.17 / 4.27 |
| V2 | 3.00 | 3.75 | 3.60 | 4.95 | 0 / 1.0 |
| V2+F2+v5 | 3.00 | 3.75 | 4.20 | 3.75 | 0 / 1.0 |

**Exceptions** (`results/fmea_b_metric.md`):
- **V2 as drawn** is worse than V1 in the passives ×5 case, on neg UV and span OV. In the worst case it is worse on
  span OV.
- **V2+F2+v5** beats V1 on total in all nine cases. It is worse only on neg UV and span UV in the passives ×5 case:
  V1's 750 Ω neg-UV quirk, and the split span-UV bottom.
- **The ratio V2 / V1 is about 0.87 on total and 0.6 on the front end** in the base case.

**What the money buys.** V2 costs **+$1.365 a board over V1** (+$1.532 against +$0.167 at 500, S16 JLC basis); the
amended form costs about +$1.49. Either buys 2.5–2.6 FIT·rails of 19.3.

## 7. Verdict, by row

**V2 is better than V1 on:**
- C2: output stage rate 6.4 → 2.4 FIT per rail.
- N1: a supply pin loses one window, not the whole rail.
- N2 / N4: lower pin-fault exposure, since a SOT-23-6 package is 2 FIT against 14 for the SOIC-14.
- C7: the sliver closes.
- Whole-rail front-end masks: 0.17 → 0, or 4.3 → 1.0 with allocation B.

**The two are equal on:**
- C4: reference drift is bounded in both; gross reference faults are announced in both.
- C2b class.
- C6.
- C8 / C9 (unchanged chain).

**V2 is worse on:**
- C1 latency: +27 µs typical on OV, no maximum anywhere.
- C5 rate: 2.8 against 2.0 FIT per rail.
- The neg-UV drift margin to H: +0.068 against +0.179 V.
- Its millivolt sensitivity to a single comparator offset.
- **The new overstress class (C5 span-bottom open, N3 INB–VDD short).** This one is decisive under the project rule: a
  dormant path to losing span OV that no test covers.

**Fix that path with F2 plus VDD-from-v5** and V2 is better in aggregate in every case. It is still not strictly better
on C1 or C5.

**What would settle the open questions:**
1. **TI:** a TPS3701 DDC FIT / FMD / pin-FMA document, including the pin FMA at VDD = 17 V and the INx input structure
   (clamp type, continuous current rating). Ask TI or E2E. This decides whether C5/N3 is real, and whether F2 is needed
   at all.
2. **Bench:** 17.4 V through 240 k and through 86.6 k onto INA / INB of about 5 TPS3701s at 85 °C, then check both
   channels' thresholds and outputs.
3. **Bench:** the tpd(LH) distribution at 10 mV overdrive.

## 8. Sources and numbers I could not source

- **Sources.** Every external number is checked against the downloaded text by `scripts/sources.py`
  (`results/sources.md`: page, regex, value). URLs, revisions and sha256 are in `dl/MANIFEST.json`. The documents are
  SBVS240C, SBVS187G, SLVS543S, SLCS006Z, SBVS204G, SBVS186H, SNVA914, SLCA004, SLVAEM2A, SFFS074, SBVA070A and
  SFFS944, plus four TI estimator pages.
- **Could not source:**
  1. **A TPS3701 FIT / FMD / pin FMA.** None is published; I used the TPS3700-Q1 proxy (TPS3702 and TPS3703 as checks).
  2. **An LM339B safety document.** I used the LM2901B-family proxy SLCA004.
  3. **A TL431 (non-Q1) document.** SNVA914 covers the -Q1 and does not name a package.
  4. **The magnitude distribution of "out of specification" modes,** for any part (so k_o is swept).
  5. **TPS3701 input clamp or overstress behaviour.**
  6. **A maximum propagation delay** for either comparator.
  7. **Resistor and MLCC rates** (class assumptions, as in c24).
  8. **JLC price and stock for the F2 tops** (193 k, 138 k).
- **Limits:**
  - **Electrical model.** DC, nominal values for the fault simulation, ±10 mV / ±6 mV ambiguity bands.
  - **Overstress outcome:** resolved both ways at k_u.
  - **Package FIT split over pins:** assumed.
  - **What RWL is for:** it ranks the variants; it is not a field prediction.
- **Reproducibility.** `sh scripts/run_all.sh` was run twice. Every file in `results/` came out byte-identical (sha256
  compared).

## 9. DECISIONS draft (paste)

```
S16 follow-up (2026-10-15): candidate B (TPS3701 per window) vs 1c-4420, fault-isolation FMEA
(validation-results/11-candidates/s16-fmea-b-2026-10-15/). Kept: 1c-4420. B is not adopted.
- Reference drift is bounded in both designs: the companion UV/OV announces before any threshold passes its hard
  limit (TL431 and TPS3701 alike). The S16 C4 objection holds only against the qualified basis, and equally for both.
- B as drawn adds a dormant path: an open span-divider bottom, or the INB-VDD pin short, puts 17 V on a 7 V input
  (SBVS240C p.4); TI documents nothing about overstress, so span OV can be lost silently. Rule: regression.
- B amended (split span bottoms 2 x 10 k / 2 x 6.2 k, tops 193 k / 138 k; both TPS3701 VDD on the local 5 V) removes it
  and beats 1c-4420 in all nine exposure cases: 16.7 vs 19.3 FIT-rails (-13 %); front end -42 %; no whole-rail
  front-end mask. Still worse: OV detection +27 us typ (no maximum published), C5 rate 2.8 vs 2.0 FIT/rail.
- Cost about +$1.49/board over 1c-4420 plus a three-island layout change: take it only if those islands are re-laid.
- If B is ever built: amended form; decouplers C176-C178 (C169-C175 are stage-44 caps); U47-U49.
- Open: TI TPS3701 FMD / pin FMA and INx clamp rating; bench tpd(LH) at 10 mV; no proof test covers any monitor's
  dormant masking in any variant (B8 screens only the HS veto corridor).
```


## Integration note (2026-10-15)

Filed from scratch. The downloads `dl/` are not in git; the durable copy is `runs-native21/s16-fmea-b-dl/` (copy it back to `dl/` before `sh scripts/run_all.sh`). Hashes: `results/datasheet-manifest.json`. Recorded as DECISIONS 59.
