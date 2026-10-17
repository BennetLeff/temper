# D3 DC-link clamp: alternative circuits from stocked parts

**Scope.** This covers native-21 / stage 13b (`zapote/power-stage-120v`) as of 2026-10-09. The clamp D3 is Microchip MRT130KP295CV: 0 stock everywhere, 42 weeks (ALTERNATES-2026-10-09.md §4).

**How it was done.**
- The repo was read only. Nothing was committed, carted, quoted or logged in.
- Datasheets were saved only under `alt-d3/dl/`.
- Scripts are in `alt-d3/scripts/` and their outputs in `alt-d3/out/`.
- Everything here is estimates: lumped simulation plus datasheet arithmetic. **No hardware was tested.**

## Verdict

**Recommended: option A. Two Good-Ark 30KPA150CA in series** (P600 axial, 30 kW), with the string midpoint tied to the existing R3/R4 bleed midpoint `BUSBLEED_MID`.

| What the brief requires | Status |
| --- | --- |
| Stocked parts | ✔ Digi-Key: 1,914 in stock, $6.727 each at 10. |
| Stand-off | ✔ The string's stand-off is 300 V. |
| Published clamp at the sizing current | ✔ 466.8 V max at 129.8 A (10/1000 µs), Good-Ark datasheet p.3. That covers the ≤ 109 A of a 1 kV differential surge and the ≤ 82 A of the returned-tank event. |
| Energy and pulse rating | ✔ 0.27–0.68 of the derated rating in every case, including the DC-LINK-CLAMP 2 J rectangular-pulse target. |
| Surge coordination with RV1 | ✔ Better than the basis: string V(BR) min is 335 V against 300 V. |

**Is it better than the single MRT130KP295CV?** Not strictly.
- **Better:**
  - stand-off and V(BR) margin;
  - surge coordination;
  - availability;
  - cost: about $13 per board against $46;
  - pulse-energy headroom.
- **Worse:**
  - absolute clamp level: 467 V at 130 A, against 410 V at 282 A;
  - one more part;
  - a footprint/copper ECO.
- It meets ≤ 520 V at the bus, and the margin does not depend on loop inductance (see §1.4).
- **Combined with the C5/C6 fallback** (B32676G1905K000 × 2, 18.4 µF), the bus stays ≤ 395 V in every modelled case. That combination **is better** than the original in every respect except part count.

### Ranking

| # | Option | Parts (per board) | Bus peak, worst modelled case (5.8 µF) | Published clamp at sizing current | Stock (Digi-Key, 2026-10-09) | Board change | Verdict |
|---|---|---|---|---|---|---|---|
| **1** | **A: 2 × 30KPA150CA (Good-Ark) series, midpoint to BUSBLEED_MID** | 2 (+1) | 400 V tank+line, 445 V 1 kV surge, 488 V 2 kV surge with MOV upturn | 466.8 V @ 129.8 A ✔ (1 kV); 2 kV exceeds the point by 16 % | 1,914 | New 2 × P600 footprints in the D3 row; R4 moves 3.5 mm | **Recommend** |
| 2 | C: bus C 5.8 → 18.4 µF (C5/C6 → B32676G1905K000), plus option A or an AK3-380C-Y backstop | 2 changed (+1 or +0) | 387 V tank+line, 386 V 2 kV surge **with no clamp** | n/a (the clamp barely conducts) | 547 | None for C5/C6 (same pads); A as above | Best overall **if** the C5/C6 deviation is taken anyway |
| 3 | D: diode-coupled electrolytic absorber, 2 × UCY2W470MHD + 600 V fast diode + bleed | 5 (+4) | ≤ 380 V everywhere (2 × 47 µF, ESR 1 Ω est.) | No voltage threshold; energy-bounded; ESR unpublished | 171 (cap) | New Ø12.5 caps and diode in the free area | Viable, weaker evidence |
| 4 | 2 × Littelfuse 30KPA160CA | 2 (+1) | 428 V tank+line | 505.2 V @ 120 A; **535 V hot at 85 °C** | 665 | Same as A | Second source for A only |
| 5 | 3 × Littelfuse 30KPA102CA | 3 (+2) plus balancing | — | 496.8 V @ 183 A (covers 2 kV); 527 V hot | 3,492 | 3 × P600, two midpoints | Coverage good, hot clamp over 520 V |
| 6 | Littelfuse AK3-380C-Y (single) | 1 | 404 V | ≤ 520 V @ 3 kA 8/20 (bounds 100 A with 0 V margin; 551 V hot) | 71 | ECO at 24.15 mm pitch; R4 collision | Fallback in DECISIONS; weakest bound |
| ✘ | Single 30KPA300CA; SMDJ/5.0SMDJ/8.0SMDJ strings; 15KPA/20KPA pairs; active clamp; bus MOV; crowbar | — | — | Fail, or no published point | — | — | Rejected (§2.3, §3) |

---

## 1. What the clamp must absorb

### 1.1 Returned tank energy at the worst shunt-OCP trip

**Method.** `scripts/returned_energy.py` extends the repo's `tools/bus_voltage_sim.py`:
- **Drive.** Full-bridge square wave at **f_res**. This is the double-fault case: the CT path has failed, so only the shunt band applies, and the controller is below its 1.05·f_res floor. A drive at 1.05·f_res was also run.
- **Trip.** A trip at every threshold across the shunt band 47.32–97.77 A, then gates off **1.5 µs** later. That is D-31's 815 ns shunt chain plus an allowance for the sense RC.
- **Ring-down.** Body diodes return |i| to the bus until |v_Cr| ≤ V_bus.
- **Tank parameters.** Cr 0.45/0.50/0.55 µF. L and R from round-4: no-pan 70 µH and 77 µH (+10 %), offset pan 63 µH, ferrous 48 µH.
- **Bus start.** V0 = 198 V (127 V +10 % crest) and **286 V** (static OVP corner).

| Tank (round-4 basis) | Worst current at gate-off | Tank energy at gate-off | ½·L·(97.77 A)² for reference |
|---|---:|---:|---:|
| Ferrous pan, 48 µH | 105 A | 0.27 J | 0.23 J |
| Offset pan max, 63 µH | 112 A | 0.42 J | 0.30 J |
| No pan, 70 µH | 112 A | 0.46 J | 0.34 J |
| **No pan +10 %, 77 µH** | **110 A** | **0.475 J** | 0.37 J |

**Energy into the bus.** At most **0.46 J**, because Cr keeps part of it. The 2 J figure in DC-LINK-CLAMP.md is about 4× what this basis can return. It remains a requested minimum, and option A meets it (§2.2).

**Bus peak with no clamp, worst trip state** (`out/returned_energy.txt`; closed form in `out/closed_form.txt`):

| Bus C | V0 = 198 V | V0 = 286 V |
|---|---:|---:|
| 5.8 µF (basis) | 429 V | **490 V** |
| 4.72 µF (B32656G…M at −20 %) | 470 V | **526 V** ✘ |
| 18.4 µF (B32676G1905K × 2) | 293 V | 359 V |

With the basis capacitors the tank event alone stays under 520 V with no clamp, but with only 30 V margin, and it fails at −20 % C.

### 1.2 Line inductance at gate-off: the tank case grows

When the bridge stops at the line crest, the mains source inductance keeps pushing current into the 5.8 µF bus, because the bus is unfiltered.

**Model.** L_line 250 µH at 21 A (15 A rms × √2) and 500 µH at 30 A, with the CMC differential-mode stray of 18 µH typ inside these (task-07 README, TDK p.4). The source impedance is **not specified** in the repo, so this is a sensitivity range, not a bound.

| Case (no-pan 77 µH, V0 198 V) | No clamp | MRT basis | **Option A** |
|---|---:|---:|---:|
| No line L | 428 V | 321 V | 375 V, 39 A, 0.20 J |
| 250 µH / 21 A | 484 V | 326 V | 388 V, 52 A, 0.35 J |
| 500 µH / 30 A | **578 V** ✘ | 331 V, 79 A, 0.89 J, 128 µs | **400 V, 64 A, 0.73 J, 93 µs** |

This combined case gives the longest, highest-energy clamp pulse. Neither DC-LINK-CLAMP.md nor ORACLE-ANSWER.md models it. It should be added to the task-02 F3 row.

### 1.3 Mains surge through RV1 and the CMC

**Method.** `scripts/surge.py` uses a fitted IEC 61000-4-5 combination-wave generator (`cwg_fit.py`):
- Voc 1.20/50.0 µs, Isc 8.04/19.9 µs, Z 1.998 Ω;
- 18 µF line-line coupling;
- CX1 1 µF ∥ RV1, with the MOV as a power law from V1mA to 455 V at 100 A (parts.ato "Vc 455 V"), corners V1mA 297 V (hi) and 243 V (lo);
- CMC differential-mode stray 18 µH, CX2 1 µF, bridge, bus;
- applied at the +198 V crest with aiding polarity.

`--sens` adds 0.1 Ω of MOV upturn resistance.

| 5.8 µF bus, hi-MOV | No clamp | MRT basis | **Option A** | AK3-380C | 18.4 µF, no clamp |
|---|---:|---:|---:|---:|---:|
| 1 kV DM | **544 V** ✘ | 359 V, 152 A | **439–445 V, 102–109 A, 0.65 J, ~25 µs** | 407 V, 154 A | 356 V |
| 2 kV DM | 604 V ✘ | 371–382 V, 182–210 A | 465–488 V, 128–150 A, ≤ 1.0 J | 408 V, 176–205 A | 386 V |
| 4 kV DM (stress) | 640 V ✘ | 379 V, 203 A | 481 V, 144 A, 0.97 J | 409 V, 195 A | 410 V |

The 4 kV runs with 0.1 Ω upturn are numerically unreliable (the MOV iteration did not settle) and are not used.

**Which surge level applies?** The lab still has to choose it (DC-LINK-CLAMP.md). EN/IEC 55014-2 category IV household equipment typically applies **1 kV line-line / 2 kV line-earth**; 2 kV line-line is shown as margin.

**Coordination.**
- The basis TVS (V(BR) 300 V) takes **150–210 A**. Option A (335 V) takes **100–150 A**, and AK3 (401 V) takes 150–200 A.
- AK3's flat slope gives a lower voltage but more current.
- Option A shifts duty to the 135 J MOV, which carries 245–750 A whichever clamp is fitted.

### 1.4 What sizes the clamp

- **Peak current is sized by the mains surge.** That is about 110 A at 1 kV and up to 150 A at 2 kV for a 335 V string, in pulses of about 15 µs to half value. The tank event peaks at ≤ 82 A.
- **Pulse duration and energy are sized by the returned-tank event plus line inductance.** That is up to 0.9 J (basis) or 0.73 J (A), lasting about 90–130 µs.
- **Loop inductance hardly matters for these events.** Both have di/dt ≲ 15 A/µs, so 30 nH of clamp loop adds < 0.5 V. Nanosecond commutation spikes are carried by C38–C41 and D-31's die-VDS result, ≤ 350 V, not by D3.
- **So the 520 V screen is set by the clamp's V–I curve and temperature,** not by layout. This is why a 467 V @ 130 A string is acceptable.

---

## 2. TVS strings from stocked parts

### 2.1 Candidates (`scripts/ratings.py` → `out/ratings.json`)

**Hot clamp.** The table applies +0.1 %/K, the MRT130KP maximum (DS00005551B p.5 note 6). Good-Ark and Littelfuse publish **no** tempco: that is an open item.

| Option | Stand-off (≥ 286 V) | V(BR) min 25 °C / −10 °C | Vc max @ Ipp (published) | Vc at 85 / 100 °C | Point covers 1 kV / 2 kV / tank | Source |
|---|---|---|---|---|---|---|
| MRT130KP295CV (basis) | 295 (+9) | 300 / 290 | 410 V @ 282 A, 6.4/69 µs | 435 / 441 | ✔/✔/✔ | DS00005551B p.5 |
| **2 × 30KPA150CA** | **300 (+14)** | **335 / 323** | **466.8 V @ 129.8 A, 10/1000 µs** | 495 / 502 | ✔/✘(+16 %)/✔ | Good-Ark p.3 |
| 2 × 30KPA160CA | 320 (+34) | 357 / 345 | 505.2 V @ 120 A | **536** / 543 | ✔/✘/✔ | Digi-Key param.; Good-Ark p.3 same row |
| 2 × 30KPA144CA | 288 (+2) | 322 / 310 | 446.4 V @ 135.8 A | 473 / 480 | ✔/✘/✔ | Good-Ark p.3. **Not stocked** (Littelfuse/Yageo 0, MDE marketplace only) |
| 3 × 30KPA102CA | 306 (+20) | 342 / 330 | 496.8 V @ 183 A | **527** / 534 | ✔/✔/✔ | Good-Ark p.2 |
| AK3-380C-Y | 380 (+94) | 401 / 387 | 520 V @ 3 kA, 8/20 µs | **551** / 559 | ✔/✔/✔ (0 V margin) | Digi-Key; MCC AK3 p.2 |
| 1 × 30KPA300CA | 300 (+14) | 334 / 322 | 484 V @ **62 A** | 513 / 520 | ✘/✘/✘ | Good-Ark p.3 |

**Option A's clamp at the 1 kV current.** On the straight line from V(BR) min to the published point, 109 A gives 446 V, or about 472 V at 85 °C.

**The 2 kV case.** It exceeds the published point by 16 %. Extrapolated, it reaches 488 V (simulation) or about 516 V at 85 °C. That is inside 520 V, but **not published-backed**. If the lab sets 2 kV line-line:
- use option 5 (3 × 30KPA102CA, published to 183 A), but its hot Vc goes over 520 V; or
- use option C (18.4 µF), which keeps the string under 41 A at 2 kV.

### 2.2 Energy and pulse rating (30KPA150CA)

The ratings come from two Good-Ark p.4 curves:
- **Fig. 4** (peak pulse power against td, digitised): 1 µs 380 kW, 10 µs 165 kW, 100 µs 65 kW, 1 ms 28 kW.
- **Fig. 1** derating: linear to 0 at 175 °C, which gives **60 % at 85 °C**.

Rectangular pulses get Microchip's 0.66 factor, because Good-Ark gives none.

| Pulse (per device) | Peak power | Derated rating at 85 °C | Ratio |
|---|---:|---:|---:|
| 1 kV surge, 109 A, td ≈ 15 µs | 24 kW | 84 kW | 0.29 |
| 2 kV surge, 150 A, with upturn | 37 kW | 84 kW | 0.44 |
| Tank + 500 µH line, 64 A, td ≈ 60 µs | 13 kW | 48 kW | 0.27 |
| **DC-LINK-CLAMP 2 J requirement**, 100 A rectangular 49 µs | 23.5 kW | 34 kW | **0.68** |
| Bench T2 (§5), 115 A, t50 43 µs, 2.3 J | 26 kW | 55 kW | 0.47 |

**Energy per device** is ≤ 0.5 J per event, against roughly 40 J for a 30 kW 10/1000 µs pulse.

**Repetition.** The rating is at 0.01 % duty (p.1). An IEC 61000-4-5 sequence of one per minute is far inside that, and so is the OCP restart inhibit.

### 2.3 Families rejected by the published data

- **SMD: SMDJ (3 kW), 5.0SMDJ (5 kW), 8.0SMDJ (8 kW).**
  - The 10/1000 µs Ipp of a 150 V-class device is Ppp/Vc ≈ Ppp/243 V: about 12, 21 and 33 A.
  - None publishes a clamp point near 100 A, and paralleling 4–8 parts has no guaranteed current sharing. Rejected.
  - The surface-mount 30 kW part, Littelfuse **SM30KPA150CA-HRA**, has 0 stock and costs $153 at 500.
- **15KPA/20KPA pairs (15 or 20 kW).** At 150 V class their Ipp is 62 or 82 A, below the sizing current.
  - 3 × 20KPA100 would reach about 123 A, but needs two midpoints, like option 5.
- **5KP (5 kW).** MCC 5KP150CA-TP has 1,008 in stock but only 20.6 A Ipp. Rejected.
- **AK series.** AK3 comes only in 30/58/66/76/380/430 V (MCC AK3 p.2), so a series string would need 4–5 low-voltage parts. Rejected.
  - AK3-380C-Y is ranked 6 above. AK6/AK10 are larger radials (AK10-380C-Y $96, ALTERNATES §4).
- **Bourns PTVS3-380C-TH.** Its 520 V at 3 kA is listed **typical** (Bourns REV 11/25 p.1), so no maximum is published. Rejected as a clamp bound.

### 2.4 Voltage sharing (option A)

The midpoint goes to `BUSBLEED_MID`: R3/R4, 2 × 220 kΩ 1 % (Thévenin 110 kΩ).

| Condition | Volts per device |
|---|---|
| Normal crest | 99 V |
| OVP corner | 143 V ± 2.9 V (resistor tolerance) |
| Plus leakage mismatch at 25 °C (IR ≤ 2 µA @ VRWM, p.3) | ± 0.2 V |
| Plus assumed hot mismatch (≤ 100 µA, unpublished) | ± 11 V, so worst **157 V** |

- At worst, 157 V is above the 150 V VRWM but below V(BR) min of 167.6 V (162 V at −10 °C).
- The cost is extra leakage, not damage, and it occurs only at the restart-inhibit corner.
- **Mitigation if the bench finds more:** a dedicated 2 × 100 kΩ 2512 balancing pair. With no extra resistors, the part delta stays +1.

**Failure mode.** A TVS fails short.
- If one device shorts, the other sees 198–286 V and fails short too. The bus is then shorted and F1 clears, the same end state as a shorted MRT.
- A single shorted device is silent: stand-off halves. Add a production and bring-up check of the midpoint at about half the bus.

---

## 3. Other topologies

### 3.1 Larger bus capacitance (option C)

**Effect of 18.4 µF (2 × B32676G1905K000, 9 µF / 750 V, same 4-pin pads).**
- **Tank event:** at most 359 V, and the clamp does not conduct.
- **Tank plus 500 µH line:** 387 V.
- **1 / 2 / 4 kV DM surge, no clamp:** 356 / 386 / 410 V.

**This removes the clamp's role in every modelled event** and leaves it as a backstop for unmodelled ones: a lab level above 4 kV, ring waves, repeated faults, or source impedance outside the range above.

**Re-validation.** This is ALTERNATES §1's list in full:
- PF and harmonics;
- inrush and fuse I²t;
- the D-32/LINE_ZC valley;
- bleed time τ (R3/R4: 2.55 s → 8.1 s);
- the EMI C_BULK;
- the 85 V/µs dV/dt;
- F6 and the leg decks.

**Recommendation.** Do it **only if** the C5/C6 shortage forces that deviation anyway. In that case keep option A as the backstop: it conducts ≤ 17 A in the tank cases and ≤ 41 / 58 A in 2 / 4 kV surges. An unchanged AK3-380C-Y would also serve, but needs its own ECO.

### 3.2 Diode-coupled absorber (RCD peak-hold, option D)

**Circuit.**
- A 600 V fast diode from BUS_P to a reservoir capacitor returned to HV_RET.
- A bleed resistor across the reservoir.
- The reservoir charges to the line crest and stays out of the 33 kHz loop, so the unfiltered-bus behaviour, PF and D-32 are unchanged.

**Result.**
- With realistic electrolytic ESR, the 2 × 47 µF / 450 V case keeps the bus ≤ 380 V in every case (`out/absorber_esr.json`).
- The ESR comes from Nichicon UCY tan δ 0.24 at 120 Hz: about 6.8 Ω at 120 Hz, and an assumed 1–2 Ω at 100 kHz.
- 22 µF at 2 Ω reaches 460 V at 2 kV.

**Parts.**
- 2 × Nichicon **UCY2W470MHD**: 47 µF / 450 V, Ø12.5 × 41.5 mm, 105 °C 12,000 h, 171 in stock, $2.70 at 10. Digi-Key read 20:21Z.
- A 600 V ultrafast diode in TO-220AC: STTH8R06D; its stock was ambiguous on the page.
- Bleed 2 × 220 kΩ, τ ≈ 41 s. The service-discharge requirement needs review.

**Why it ranks third.**
- It has no voltage threshold, so an over-energy event has no hard limit.
- Electrolytic ESR at cold and its pulse-current behaviour are **unpublished**.
- It adds about 4 parts and stored energy (2 × 3.3 J at 373 V).
- Its plug-in inrush rises: an estimated 0.3 A²s, against KLDR's 226 A²s.

### 3.3 Active clamp or brake chopper

A comparator at about 340 V drives a 650 V MOSFET and power resistor.
- **Gate drive.** A ≥ 10 V HV_RET-referenced gate supply is needed. HOT5 is 5 V, and the leg supplies sit on LEG_RET.
- **Speed.** It must respond in < 1 µs for the surge.
- **Size and risk.** It adds 8–12 parts, and a MOSFET short would short the bus.

**Rejected for this prototype.** There is no stocked single-part advantage and it carries its own qualification.

### 3.4 MOV plus TVS

- **A DC-link MOV cannot meet 520 V.** For a working voltage ≥ 286 V DC, V1mA is ≥ about 360 V, and a typical Vc/V1mA of about 1.6 gives about 590 V at 100 A. Rejected as the clamp.
- **A lower RV1** (150 Vrms) would cut what reaches the bus. That leaves only 10 Vrms over the 140 V line maximum, and it changes the mains-side coordination and approval. Out of scope.
- **The existing RV1 + TVS pair is the MOV+TVS combination.** Option A improves it by raising the TVS onset from 300 to 335 V.

### 3.5 Crowbar

**Rejected.** An SCR across a stiff rectified bus is a deliberate short. It blows F1 on every surge, and the surge standard requires the product to keep working afterwards.

---

## 4. Option A: details

### 4.1 Parts

**Primary.**

| MPN | Manufacturer | Stock | Price | Lead time | Read |
|---|---|---|---|---|---|
| 30KPA150CA | Good-Ark Semiconductor | **1,914 in stock** | $9.82 / 1, $6.727 / 10, $5.401 / 50 | 16 wk | ≈20:13Z |

- Digi-Key part 4786-30KPA150CACT-ND, status Active: <https://www.digikey.com/en/products/detail/good-ark-semiconductor/30KPA150CA/22168209>.
- **Lot.** 5 boards × (2 + 2 spares) = **20 pcs ≈ $108**. The MRT basis was 15 pcs at a 100-piece MOQ × $46.22.
- **Datasheet:** Good-Ark Doc.US30KPA28A-30KPA320CAxSM5.0 (Jan 2020), <https://goodarksemi.com/docs/datasheets/transient_voltage_suppressors/30KPA28A-30KPA320CA.pdf>, read 20:11:03Z.
  - p.1: ratings and P600 dimensions.
  - p.3: the 30KPA150CA row: V(BR) min 167.6 V @ 5 mA, IR 2 µA @ 150 V, Ipp 129.8 A, Vc 233.4 V.
  - p.4: Fig. 1 derating, Fig. 4 Ppk–td.
  - **P600 body:** Ø8.6–9.1 × 8.6–9.1 mm; leads Ø1.22–1.32 mm.

**Same MPN, not stocked** (Digi-Key filter, ≈20:16Z):
- Littelfuse 0, with a 12-week lead;
- Yageo 0;
- Microchip 30KPA150CAE3 0;
- MDE 1,000, marketplace only, shipping in about 56 days.

**Second source with a penalty:**

| MPN | Manufacturer | Stock | Price | Lead time | Read |
|---|---|---|---|---|---|
| 30KPA160CA | Littelfuse | 665 | $25.40 / 1, $18.57 / 10 | 12 wk | ≈20:17Z |

- Digi-Key: <https://www.digikey.com/en/products/detail/littelfuse-inc/30KPA160CA/2520213>.
- Its clamp is 505 V @ 120 A, about 535 V hot. **Only in combination with option C.**

**Not usable here.** Mouser was bot-blocked and the Littelfuse sites returned 403 (as in ALTERNATES).

### 4.2 Footprint and placement on the stage-13b board

`scripts/board_area.py` and `scripts/placement_check.py` produced `out/board_area.txt` and `out/placement_check.txt`.

**What is there now.**
- D3 pads are at (254, 106) bus_p and (274, 106) hv_ret.
- R3 is at 249.5 (bus_p / busbleed_mid) and R4 at 283.0 (busbleed_mid / hv_ret).
- A `busbleed_mid` track runs along y 100.8 from x 248.04 to 281.54.
- The In1 hv_ret and In2 bus_p planes cover the row; their outline bounding boxes reach y 113.
- The area x 260–289, y 113–126 is empty apart from FID2 at (278, 128).

**Proposed layout:**

| Item | Position and net |
|---|---|
| D3A | 2-pad P600 axial, **12.70 mm** pitch, Ø3.2 / 1.6 drill (generate like F10). Pad 1 at (254.00, 106), BUS_P, reusing the existing hole position. Pad 2 at (266.70, 106), BUSBLEED_MID. |
| D3B | Same footprint. Pad 1 at (269.24, 106), BUSBLEED_MID. Pad 2 at (281.94, 106), HV_RET, on the In1 plane. |
| Midpoint pads | Joined with a 1.0 mm track. A 0.4 mm stub at x 267.97 runs up to the y 100.8 bleed track. |
| **R4** | **Moves** to (286.5, 103.5), rotated 90°. Pads: busbleed_mid at y 102.04, hv_ret at y 104.96 → existing hv_ret via at (286.6, 106). The bleed track extends from 281.54 to 286.5. |

**Clearance screen.** Minimum edge-to-edge clearance to other-net copper on the outer layers is **≥ 2.59 mm** (R4.1 to the hv_ret via). The diode pads are ≥ 3.40 mm from other nets.
- No body overlaps another courtyard.
- The hv_ret pad is 6.5 mm from the board edge, and R4's pad 2.6 mm.
- This is a geometric screen, not DRC. The provisional HOT-functional rules, D5 and fit_gate must be rerun.

**Bodies.** Each lies flat, Ø9.1 mm, about 1.2 mm taller than the MRT's Ø7.9. Check the enclosure envelope over (254–282, 101–111).

**Lead bend.** At 12.7 mm pitch there are 1.8 mm from body end to hole, the same as KiCad's stock D_P600 12.70 mm footprint. A 15.24 mm pitch does not fit without moving R3. Check on a formed sample, as F10 requires.

### 4.3 Source edits (proposed only; not made)

**parts.ato.** Add a new component `BusTvs30kpa150`:
- mpn `30KPA150CA`, manufacturer `Good-Ark Semiconductor`;
- footprint `temper:P600_Axial_P12.70mm_ReviewOnly`;
- docstring citing p.3 and p.4.

**power_stage_120v.ato.**
- `tvs_bus_a`: p1 ~ BUS_P, p2 ~ BUSBLEED_MID.
- `tvs_bus_b`: p1 ~ BUSBLEED_MID, p2 ~ HV_RET.
- Designators D3 / D3B, or the next free D number.

**audit.rs.**
- Line 291: MPN pin.
- Lines 757–763: tvs nets.
- `busbleed_mid` membership grows by two pins.
- Line 1466 negative test: change it to a wrong-suffix 30KPA, e.g. `30KPA150A` (unidirectional).

**Docs.** DC-LINK-CLAMP.md (candidate table, the surge and line-L cases above, Procurement), FOOTPRINTS.md (new F row), and DECISIONS.md.

**Owner approval.** Required: this is a clamp-family change under the DC-LINK-CLAMP "no silent substitution" rule.

### 4.4 Re-validation

1. Rerun the board gates on the ECO: DRC, D5 clearance, fit_gate, STEP/enclosure height, and the audit.
2. Add the line-inductance-at-trip case and the 1 kV / 2 kV DM surge cases (§1.2–1.3) to task 02 F3.
3. Bench: T1 and T2 below, with V(BR)-versus-temperature on 3 samples to close the tempco gap.
4. Bring-up: measure the midpoint at 198 V and at the 280 V OVP setting, hot.
5. Certification lab: the surge matrix, as DC-LINK-CLAMP.md already requires. Capture the TVS-string current alongside RV1 current.

### 4.5 Part count and risk

**Part count:** +1, or +3 if balancing resistors prove necessary. One part moves (R4).

**Risks:**
- A single stocked source (Good-Ark).
- Tempco is unpublished.
- At 2 kV line-line the current exceeds the published point by 16 %.
- The hot-leakage share at the OVP corner is assumed.
- The clamp is higher than the basis (≈ 446 V against ≈ 340 V at 109 A).

---

## 5. Bench qualification (`scripts/bench_pulse.py`)

Run both tests on 3 strings: 25 °C, then 85 °C on a hot plate with a thermocouple on the body. Allow a 60 s gap between pulses.

### Measurements

| Item | How |
|---|---|
| String current | Rogowski or 0.01 Ω coaxial shunt |
| String voltage | 1 kV differential probe |
| Midpoint voltage | Differential probe |
| V(BR) at 5 mA and leakage at 143 V per device, before and after | Source-measure unit |

### T1: inductor dump (returned-tank surrogate)

**Circuit:**
1. L = 75 µH air-core (the tank coil itself, no pan, is ideal).
2. Charge L to I0 from a 48–60 V supply through a 1200 V IGBT (~150 µs).
3. Open the IGBT. L freewheels through a 1200 V SiC diode into 5.8 µF (2 × 2.7 µF + 0.4 µF film, or any 1000 V film) ∥ DUT.
4. The capacitor is pre-charged to **286 V** from an HV supply through 100 kΩ.

| I0 | Energy in L | Expected |
|---|---:|---|
| 115 A | 0.50 J | 396 V, 60 A |
| 160 A | 0.96 J | 433 V, 97 A, 0.80 J in the DUT |

### T2: capacitor discharge (surge and the 2 J requirement)

**Circuit:** 20 µF / 1000 V film charged to Vc0, fired by an IGBT through 10 µH + 1.0 Ω (≥ 50 W pulse-rated) into the DUT alone.

| Vc0 | Expected |
|---|---|
| 520 V | 75 A, 1.4 J |
| **620 V** | **115 A peak at 12 µs, 43 µs to half, 452 V, 2.3 J** (meets the ≥ 2 J request) |
| 700 V | 148 A, 485 V, 3.1 J (2 kV-class stress) |

### Pass criteria

- **Peak string voltage:** ≤ 466.8 V × (1 + 0.001·(T − 25)) at each I ≤ 129.8 A, and **≤ 520 V at the bus capacitors** in T1.
- **Midpoint:** within 50 % ± 5 % of the string voltage during the pulse.
- **After 10 pulses per condition:**
  - ΔV(BR) ≤ 2 %;
  - leakage at 143 V ≤ 2 µA at 25 °C;
  - no visible damage.
- **Then:** repeat T2 at 620 V × 10 at 85 °C.

---

## 6. Evidence and limits

- **Simulation.** Lumped Euler with ideal diodes and no stray inductance.
  - The trip latency of 1.5 µs is assumed.
  - The line source inductance is unknown; 250–500 µH is a range, not a bound.
  - The MOV is a power law, with only a 0.1 Ω upturn sensitivity.
  - The CWG is fitted to waveform parameters, not to a specific generator.
  - The **inverter is idle** during the surge.
  - All results are estimates, not bounds.
- **Not run.** No ngspice; Python was enough. No hardware.
- **Scripts and outputs:**

| Script | Output | Run time |
|---|---|---|
| `returned_energy.py` | `returned_energy.{json,txt}` | ~4 min |
| `returned_candidates.py` | `returned_candidates.{json,txt}` | ~10 min |
| `closed_form.py` | `closed_form.txt` | — |
| `cwg_fit.py` | `cwg.json` | — |
| `surge.py` | `surge.{json,txt}` | — |
| `surge.py --sens` | `surge_sens.{json,txt}` | — |
| `absorber_esr.py` | `absorber_esr.json` | — |
| `ratings.py` | `ratings.json` | — |
| `bench_pulse.py` | `bench_pulse.json` | — |
| `board_area.py`, `placement_check.py` | board text outputs | KiCad 10 python, read-only |

- **Repo inputs:**
  - DC-LINK-CLAMP.md; DECISIONS.md (2026-10-05 D-31; 2026-10-09 R34/R35 band and blocked parts);
  - FOOTPRINTS.md F10; parts.ato:57–158; power_stage_120v.ato:318–376, 685–690;
  - ALTERNATES-2026-10-09.md §1 and §4;
  - round-4 tank basis README; out-D31 README;
  - 07-conducted-emi README (CMC 18 µH stray);
  - tools/bus_voltage_sim.py; ORACLE-ANSWER.md.
