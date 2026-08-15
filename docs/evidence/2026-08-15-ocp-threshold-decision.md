# Firmware OVER_CURRENT_THRESHOLD — data-driven decision (2026-08-15)

<!-- provenance: commit=7f6a6bd5c3cf9ce8adc1cd9ab67b677239d34792 dirty=false (base = origin/main at measurement time; all analysis and this doc committed on branch investigate/ocp-threshold-decision) -->

**Date:** 2026-08-15
**Method:** git archaeology + committed-document cross-reference. No simulation
was run and no hardware was touched; every number below is traced to a
committed file and line. The firmware interlocks citation audit
(`docs/evidence/2026-08-15-firmware-interlock-citations.md`, branch
`fix/firmware-interlock-citations`) identified `OVER_CURRENT_THRESHOLD = 35.0 A`
as uncited and basis-ambiguous; this document resolves the question with the
repo's current committed evidence — including the coil specification
(2026-07-29) that supersedes the pre-coil-spec figures that audit worked from.

**Scope:** a decision on `OVER_CURRENT_THRESHOLD` only. No firmware value is
changed here — the value change is an owner decision (the interlocks branch's
own conclusion), and this document supplies the data and the recommendation
that decision should rest on. `pcb/temper.kicad_pcb` is not touched.

---

## 1. The sensing chain (as committed today)

| Element | Value | Source |
|---|---|---|
| Sensor | CT **CST3015-100ED**, 1:100, **88 A sensed rating** | `elec/src/modules.ato:1615-1650`; supersedes the 47 A-rated CST2010-100L |
| Burden | **4.99 Ω ±1%** (0.25 W) → **49.9 mV per primary amp** | `modules.ato:1647-1650` |
| Filter | 100 nF C0G across burden → RC = 499 ns → **319 kHz corner** | `modules.ato:1665-1679`; `docs/evidence/2026-07-26-ocp01-vs-full-power-current.md` ("noise filter, not an averager") |
| Bias | **1.65 V mid-rail** (10 kΩ/10 kΩ divider) on `I_SENSE` for the ESP32 ADC | `modules.ato:1681-1697` |
| Fan-out | `I_SENSE` → ESP32-S3 ADC (`mcu.adc_i_sense`) **and** OCP-01 comparator | `elec/src/main.ato:833-834` |
| OCP-01 comparator | TLV3201, ref 2.4925 V (3.3 × 10k/13.24k) → trip **49.9 A nominal / 50.1 A simulated**, worst case **48.77–51.16 A** over ±1% + tempco | `modules.ato:1618-1629`, `docs/hardware/PROTECTION_CHAIN_REVIEW.md` |
| OCP-01 acceptance | **45–55 A peak, <1 µs**, latched | `docs/FUNCTIONAL_TEST_CRITERIA.md` §2.1 |
| Firmware read | `read_dc_bus_current()` — declared `extern`, **no ESP32 implementation** (only the test mock) | `firmware/main/state_machine.c:75`, `firmware/components/safety/safety.c:112,124`; interlocks doc §6.3 |

**There is no rectifier and no averaging anywhere in the sense path.** The
BOM's "Precision Rectifier (OCP)" section is class A — costed, never wired
(`docs/evidence/2026-07-26-ocp01-vs-full-power-current.md`). The 100 nF filter
has a 319 kHz corner; at the 47 kHz tank fundamental it attenuates by ~1%.
The comparator and the ADC both see the **raw bipolar tank waveform** riding
on the 1.65 V mid-rail.

**ADC measurable range (computed from the committed values):**
`V_I_SENSE = 1.65 V ± (I_primary/100) × 4.99 Ω`. Full-scale swing ±1.65 V
corresponds to **±33.07 A peak**; the ESP32-S3 ADC's practical linear top
(~3.1 V at 11 dB attenuation) is reached at **~29 A peak**. The burden/bias
scaling was derived for the comparator's 50 A trip, not for the ADC's 0–3.3 V
range, so the ADC path **cannot measure tank current above ~29–33 A peak**
and saturates there. This matters twice: for the current threshold (below) and
because the 1800 W operating peak (31.9 A, §3) nearly fills the ADC's range.

OCP-02 (2 mΩ shunt + INA240 + LM393, 55–65 A, <5 µs) is **designed but not
implemented** — no circuit exists (`docs/hardware/OCP02_DESIGN.md`,
`docs/STRATEGY.md` §"OCP-02 still unwired"). It is not a candidate sense for
the firmware today.

---

## 2. The operating point (committed 2026-07-28/29 — supersedes the pre-coil-spec figures)

The interlocks audit's current-band numbers (35.4 A RMS / 50.0 A peak at
R_eff = 1.44 Ω, 56.6 A peak at R_eff = 1.12 Ω) come from the pre-coil-spec
state of the repo. The coil is now specified:

| Quantity | Committed value | Source |
|---|---|---|
| Coil, unloaded | **88 µH ±10 %** (79.2–96.8 µH), Litz, ≤ 200 mm OD | `docs/hardware/TANK_COIL_SPECIFICATION.md` §1 (ISSUED 2026-07-29) |
| Coil, loaded | **L_loaded ≥ 53.43 µH** (target 59.8 µH), ratio ≥ 0.60 (spec'd at 0.68) | same, §1/§2 |
| Tank | C_tank 300 nF (3× CDE 942C16P1K-F), f_sw 47 kHz, PLL 44–50 kHz | same, §4; `elec/src/main.ato` |
| **1800 W tank current** | **22.5 A rms / 31.9 A peak** (independent first-harmonic solve, R_eff 3.55 Ω @ 46.6 kHz); ngspice harness: 20.7 A rms / 28.7 A peak (R_eff 4.2 Ω) | `docs/evidence/2026-07-28-coil-selection-research.md` §4.2; `TANK_COIL_SPECIFICATION.md` §3/§8 |
| Peak current vs OCP-01 | 31.9 A peak vs 50.1 A trip = **36 % margin** (committed) | `2026-07-28-coil-selection-research.md` §4.2 |

The 22.5 A RMS design current is committed in `elec/src/modules.ato:585-593`.

**R_eff is NOT computable from the repo; it must be measured.** Committed
values bracket it:

| R_eff (Ω) | Origin | Status |
|---|---|---|
| 3.55 | First-harmonic solve at the committed 300 nF / 46.6 kHz / 1800 W point | DERIVED (committed operating point) |
| 3.25 | Infineon EVAL-IHW25N140R5L Fig. 16, R-with-vessel at 40 kHz | Chart reading ±5 %, in-band |
| ~2–2.2 | √f-scaled literature planning value (Infineon 90–150 kHz → 35 kHz) | Assumption, disclosed |
| 1.12 | Back-calculated from the uncited "typical 1.8 kW hob runs 40 A RMS" | **UNCITED**, not corroborated (`2026-07-27-coil-pan-coupling-prior-art.md`) |

The coil spec itself says (§8.3): *"No bench measurement of this project's own
coil and pan exists. That single measurement would replace §5's chart readings
and §2's threshold with real numbers, and is the highest-leverage physical
experiment this project has."* The measurement procedure (reference pan, gap,
40 kHz LCR + R reading) is already written in `TANK_COIL_SPECIFICATION.md` §2.

---

## 3. What the 35 A value actually is

`OVER_CURRENT_THRESHOLD = 35.0 A` was introduced in the initial 2025-12-14
sync (commit `04fe05232`), never cited, never revisited
(interlocks doc §1). `FIRMWARE_REQUIREMENTS.md` REQ-FW-SAFETY-03 pins it as
"35A DC bus".

**Three readings, all incoherent with the sense path:**

1. **As PEAK tank current** (what the sense path actually delivers): 35 A peak
   is only **9.7 % above the committed 1800 W operating peak (31.9 A)** — a
   thin margin for an interlock. Under the literature planning R_eff
   (2–2.2 Ω → 40.5–42.4 A peak at 1800 W) it **nuisance-trips at 1225–1350 W**;
   under the uncited 1.12–1.44 Ω figures it trips at **686–882 W** (the
   interlocks audit's "700–900 W"). It is also **above the ADC's measurable
   range (~29–33 A peak)** — the firmware could never observe 35 A on the
   CT→ADC path as built, so the interlock is unimplementable at that value.
2. **As RMS** (only defensible if the firmware filters/averages): 35 A RMS =
   **49.5 A peak**, i.e. essentially the hardware trip (50.1 A nominal,
   48.77 A worst-case low) — the "software-first" layer becomes **redundant**;
   at the hardware's worst-case corner (48.77 A) the hardware fires first. And
   there is **no RMS basis** — no rectifier, no averager, no firmware filter.
3. **As "DC bus"** (the requirement's label): the CT senses **tank** current,
   not the DC bus; the 1800 W bus average is 1800/300 ≈ **6 A**. 35 A is not a
   bus current on any basis.

**Why the value exists:** 35 ≈ 50.1/√2 = 35.4 A, the RMS-equivalent of the
hardware trip. The value is the *protection threshold* converted peak→RMS and
then used as if it were an *operating limit* — the exact category error
documented in
`docs/solutions/best-practices/calibration-point-must-equal-design-point-2026-07-28.md`
("a protection-trip threshold converted to RMS is still a threshold").
It does not match the sensor, the circuit, or the requirement it claims to
serve, and it was never cited to any of them.

---

## 4. The decision

### 4.1 Basis: PEAK. Always. The 35 A confusion is a peak/RMS mixing artifact.

The firmware OCP threshold must be specified in **peak instantaneous tank
current**, for four independent reasons:

1. The sense path delivers the instantaneous bipolar waveform (no rectifier,
   no averager — §1).
2. The hardware it is layered above trips on peak (50.1 A peak, 45–55 A peak
   acceptance window).
3. The firmware's own sibling discriminator (`IGBT_SHORT`, 50 A) is peak.
4. An RMS basis would require adding rectification/averaging or a firmware
   filter — none exist, and the hardware <1 µs budget argues against adding
   one to the fast path.

### 4.2 The value: 35 A is WRONG. The replacement is 40 A peak (band 38–42 A).

35 A is wrong, not merely "not obtainable": uncited, basis never stated,
marginal-to-nuisance across the committed R_eff uncertainty, and unmeasurable
on the ADC path as built (§3). The correct value is bounded by two committed
hard numbers — the operating point and the hardware window — so a decision
does not have to wait on the R_eff measurement:

| Constraint | Value | Direction |
|---|---|---|
| Max operating peak at 1800 W (committed) | **31.9 A peak** | threshold must be **above** |
| Hardware OCP acceptance floor | **45 A peak** | threshold must be **below** (software-first layering) |
| Hardware OCP nominal / worst-case | 50.1 A / 48.77 A peak | threshold must fire first |
| IGBT continuous rating (IKW40N120H3) | 40 A | hardware OCP = 125 % of rated; firmware at 100 % of rated = "softer, earlier" layer |

**Recommended: `OVER_CURRENT_THRESHOLD = 40 A peak`** (defensible band
38–42 A peak):

- **+25 % above** the committed 1800 W operating peak (31.9 A → 8.1 A of
  headroom for transients, pan placement, and model error);
- **−11 % below** the 45 A hardware acceptance floor (5 A of separation — the
  software layer always engages before the hardware window is entered);
- **−20 % below** the 50.1 A hardware nominal trip; always below the 48.77 A
  worst-case corner;
- **equal to** the IGBT's 40 A continuous rating — coherent with the
  documented "125 % of rated" hardware philosophy;
- RMS equivalent: **28.3 A rms** (only meaningful once an averaging mechanism
  exists — do not write it as the firmware constant).

**Falsifier, stated explicitly:** if the bench-measured R_eff comes back
below **~2.25 Ω**, the 1800 W operating peak exceeds 40 A
(`I_pk = √(2·1800/R_eff)`), and **no** firmware threshold can simultaneously
(a) clear 1800 W without nuisance-tripping and (b) sit below the 45 A
hardware floor. At R_eff = 2.2 Ω the window closes to ~1 A; at R_eff = 2.0 Ω
it is already inverted. That is the known, still-open conditional conflict
from `2026-07-26-ocp01-vs-full-power-current.md`, now narrowed to a specific
R_eff threshold. If it fires, the owner must move the 1800 W target or the
OCP-01 window — not the firmware threshold.

The committed values (3.25–3.55 Ω) sit 1.4–1.6× above the falsifier, so the
recommendation holds on current evidence with comfortable margin.

### 4.3 Why not other candidates

| Candidate | Verdict |
|---|---|
| **35 A (as built)** | wrong — §3 |
| 38 A peak | defensible, low end of the band: +19 % above operating, −15.6 % below floor |
| **40 A peak** | **recommended** — round, at the IGBT's continuous rating, symmetric ~25 %/~11 % margins |
| 42 A peak | defensible, high end: +32 % above operating, −7 % below floor (thinner software margin) |
| 45 A peak | **no** — sits at the hardware acceptance floor; zero software margin; the layers touch |
| 50 A peak | **no** — that is the hardware trip; the firmware layer would be redundant (and equals `IGBT_SHORT`) |

### 4.4 R_eff: measured, not computed — but the decision does not wait on it

R_eff cannot be derived from committed data to the precision needed: it
depends on the coil's unplaced geometry (no MPN; `CUSTOM_LITZ_COIL`), the pan
material/spacing, and frequency, and the committed model values disagree with
each other by 1.6× (3.25–4.2 Ω committed vs ~2–2.2 Ω literature planning).
The **bounds** it must satisfy are already committed, which is what pins the
threshold band. The measurement (coil + reference pan, per
`TANK_COIL_SPECIFICATION.md` §2, extended to read R at 40 kHz) is the single
highest-leverage physical experiment in the project (§2) and should be run
before the threshold is ratified in firmware — but it ratifies 40 A peak; it
does not gate the decision that 35 A is wrong.

---

## 5. Hardware findings this decision surfaced (not fixed here)

1. **The CT→ADC path cannot measure above ~29–33 A peak.** The 1.65 V
   mid-rail bias and 4.99 Ω burden (scaled for the comparator's 50 A trip)
   saturate the ESP32-S3 ADC around 29–33 A peak. The recommended 40 A peak
   threshold is **not observable** on this path as built, and the committed
   1800 W operating peak (31.9 A) already nearly fills the ADC's range — the
   firmware would be clipping during normal full-power operation. Implementing
   the software OCP at any useful threshold requires a sense-path change for
   the ADC tap (attenuator/divider, or a dedicated lower-gain stage) — a board
   change, flagged for the board owner, **not** made here.
2. **`read_dc_bus_current()` has no implementation.** The interlock is
   currently theoretical: the symbol exists only in the test mock. Until the
   ESP32 ADC driver exists, every threshold above is unreachable on real
   hardware (interlocks doc §6.3).
3. **REQ-FW-SAFETY-03 is stale on two axes**: "35A DC bus" (wrong sensor,
   wrong quantity — the CT senses tank current, the bus average is ~6 A) and
   its validation references (`sim_ocp_response.cir` does not exist;
   `test_over_temp_shutdown` is not the real test name). Both should be
   corrected in the same change that ratifies the new threshold.

---

## 6. Convention going forward (prevents recurrence)

1. **All firmware current thresholds are PEAK amps**, stated explicitly —
   `OVER_CURRENT_THRESHOLD_PEAK_A = 40.0` style naming, with "peak" in the
   comment, never a bare amp number.
2. **The hardware OCP spec already says "50A Peak"**
   (`FUNCTIONAL_TEST_CRITERIA.md` §2.1); the firmware must match that
   convention so a future reader cannot re-derive 35 = 50/√2.
3. **RMS appears only where an averaging mechanism exists.** Today there is
   none; if one is ever added, it gets its own constant and its own doc, and
   it stays out of the fast OCP path (the <1 µs hardware budget).
4. **A threshold that cannot be measured by its own sensor is not a
   threshold.** The ADC range check (§5.1) belongs in the same review as the
   value, in the same PR.
5. **Never express the firmware value as an RMS equivalent of a hardware
   trip.** That is how 35 A was born (50.1/√2 = 35.4); it is a threshold
   wearing an operating-value label (calibration-point doc).

---

## 7. Bottom line

- **35 A is peak-or-RMS?** It was never stated. Read against the sense path
  it acts as a **35 A peak** trip (the firmware compares raw samples with no
  filtering); the value's origin is the **RMS-equivalent of the 50.1 A
  hardware trip** (35.4 A). Both readings are wrong for different reasons.
- **Is 35 A correct?** **Wrong.** Uncited; basis never stated; as peak it is
  9.7 % above the committed 1800 W operating peak and nuisance-trips at
  1225–1350 W under literature R_eff (686–882 W under the uncited low-R_eff
  figures); as RMS it is redundant with the hardware and above its worst-case
  floor; as "DC bus" it is the wrong sensor and the wrong quantity; and it is
  unmeasurable on the ADC path as built.
- **What should it be?** **40 A peak** (band 38–42 A peak; RMS equivalent
  28.3 A), conditioned on the committed operating point: +25 % above the
  31.9 A peak 1800 W operating current, −11 % below the 45 A hardware floor,
  at the IGBT's 40 A continuous rating. **Falsifier: bench R_eff < ~2.25 Ω.**
- **Peak or RMS convention?** **Peak**, everywhere in firmware, stated
  explicitly.
- **Maximum operating current at 1800 W?** 22.5 A rms / **31.9 A peak**
  (committed first-harmonic solve, R_eff 3.55 Ω); ngspice harness: 20.7 A rms
  / 28.7 A peak.
- **Margin below the 50 A hardware trip?** The firmware sits below the 45 A
  acceptance **floor** (not just below 50 A) to preserve software-first
  layering: 40 A peak = 11 % below the floor, 20 % below the 50.1 A nominal
  trip.
- **R_eff?** Must be measured (coil + reference pan); cannot be computed from
  committed data. The committed values (3.25–3.55 Ω) support the
  recommendation with 1.4–1.6× margin to the falsifier.

## Related

- `docs/evidence/2026-08-15-firmware-interlock-citations.md` — the audit that
  flagged 35 A as uncited (branch `fix/firmware-interlock-citations`)
- `docs/evidence/2026-08-15-safety-constant-census.md` §4a — the census rows
  for `state_machine.c:397,401` (UNCITED)
- `docs/evidence/2026-07-26-ocp01-vs-full-power-current.md` — the original
  peak/RMS and R_eff conditional analysis (pre-coil-spec figures)
- `docs/hardware/TANK_COIL_SPECIFICATION.md` — the 88 µH coil spec and the
  R_eff measurement procedure (ISSUED 2026-07-29)
- `docs/evidence/2026-07-28-coil-selection-research.md` §4.2 — the 22.5 A rms
  / 31.9 A peak / R_eff 3.55 Ω operating point
- `docs/solutions/best-practices/calibration-point-must-equal-design-point-2026-07-28.md`
  — the protection-threshold-vs-operating-point category error 35 A instantiates
- `docs/hardware/PROTECTION_CHAIN_REVIEW.md`, `docs/hardware/SAFETY_INTERLOCK_DESIGN.md`
  — OCP-01 45–55 A peak acceptance, 50.1 A trip, 125 %-of-rated framing
