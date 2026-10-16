# FMEA re-run on s47 (2026-10-15)

DECISIONS 59 method re-run on the stage 46/47 parts at their hot-copper temperatures, plus a U5 (REF25) block and B13 proof-test hooks. Analysis lane, reviewed at integration.

Re-run: `scripts/run_all.sh` expects a `s16copy/` beside `scripts/` (a copy of the DECISIONS 59 study with its datasheets). It is kept out of git at `runs-native21/s47/fmea-s16copy/`; symlink it here as `s16copy` to reproduce. Downloads: `runs-native21/s47/fmea-dl/`.

# Stage-47 FMEA: the DECISIONS 59 monitor FMEA on the current parts, the U5 (REF25) block, and the B13 hooks

Desk study, 2026-10-15/16. The PS worktree (`ps-integrate/zapote/power-stage-120v`) and the firmware were read only;
nothing in any worktree was edited. Everything reruns offline:

```
sh scripts/run_all.sh   # 1. reruns the DECISIONS 59 study copy (s16copy/), 2. sources47.py, 3. fmea47.py -> results/
```

Two full runs gave byte-identical `results/`.

## Summary

1. **The monitor FMEA gives the same result as DECISIONS 59 (D59), on D59's own basis.**
   - On the TI functional-safety FIT basis, S47 (1c-4420 with TL431BQ + LM2901B) scores **19.29 FIT·rails**. D59 scored
     1c-4420 at 19.29. The front end is 6.29.
   - All eight non-estimator D59 exposure cases agree to within 0.001.
   - **Neither the Q grades nor the LM2901B changes any failure-mode assumption.**
2. **D59 did not use temperature-dependent rates.** Its base case is temperature-free. Its only temperature-linked row
   was the TI estimator at 55 °C, and this run reproduces that row (16.78).
   - Moved to the modelled temperatures, both sources put S47's front end at 39–56 FIT·rails. The front end then
     outweighs the 13.0 FIT·rails chain. In D59 it was the other way round.
   - **The two sources disagree on candidate B.** On TI's estimator, B is about 4× better. On SN 29500, B is about 3×
     worse. TI itself says estimator FITs must not be compared across parts.
3. **U5 has fail-dangerous modes that nothing on the board detects:**
   - **Cathode or anode pin open.** REF25 rises to 3.05–3.35 V. OVP moves from 280 V to 341–375 V nominal, OCP to
     113–124 A.
   - **VR drifting high.** Both thresholds rise together and nothing announces it. A drift of only +0.20 % already
     breaks the 288.02 V OVP rule.
   - Short, drift low and IRMIN are fail-safe.
   - **U5 is stable** at the actual load: there is no capacitor on REF25, and TI states stability with any capacitive load.
4. **B13: a minimal hook set exists, but it does not give field coverage of the monitor front end.**
   - **H1, a REF25 watchdog on U14's spare INB/OUTB.** Two resistors. It converts U5 open (and drift above 2.61 V) into
     an announced fault, continuously.
   - **H2, BIAS_GOOD read back on the spare J4 pin 1,** with a firmware power-on self-test (POST).
   - **H3–H5, end-of-line (EOL) test pads:** per-tap forcing, the LS 3P2V rail raise, REF25 and the OVP/OCP functions.
     These screen about 91–94 % of monitor dormant FIT present at manufacture, and 0 % of random field failures.
   - The only field self-test of the monitors (H6) needs an isolator swap and switches in three islands, for 45 % coverage.
5. **D59's conclusion holds:** keep 1c-4420 (now on its 125 °C grades), and build amended candidate B only if the islands
   are re-laid.

## 1. Basis and controls

| Item | Value | Source |
|---|---|---|
| C0: D59 study copy reruns byte-identical | 14 / 14 result files | `s16copy/` vs PS `s16-fmea-b-2026-10-15/results/` (sha256) |
| Frozen BOM | U17/U19/U21 TL431BQDBZR; U29–U31 LM2901BIDR; U5 LM4050AEM3-2.5/NOPB; U14 TPS3700DDCR; R31–R37, C30/C31/C33 as in the source | `native-21/frozen/default.csv` |
| REF25 node | R31.2, U5.1, R32.1, R34.1, R36.1. **No capacitor.** U5.3 floats alone on `u_ref-nc` | `native-21/frozen/default.net` |
| Temperatures, release case c17.5_h10 @ 61 | U29 102.6, U30 96.5, U31 101.3 / U17 92.4, U19 81.9, U21 85.3 / U5 89.1 °C | B3 `margins.json`, board 63aba33f… |
| Temperatures, ratchet case c28_h10 @ 55 | U29 106.0, U30 94.2, U31 102.7 / U17 94.8, U19 80.8, U21 84.5 / U5 104.7 °C | same |
| Every new datasheet number | regex-checked on its page | `results/sources47.md` (36 entries, all found) |

The method is D59's, unchanged:
- **Metric.** RWL = Σ FIT × P(mask) × rails hidden. Front-end modes count thresholds / 4.
- **Fault simulation and drift bound.** D59's DC fault simulation, with the companion-announces drift bound.
- **Scales.** The c24 S/O/D scales.
- **Parameters.** k_u = 0.5 and k_o = 0 in the base case, both swept.

The single change for the new parts is that the drift bound is evaluated at 100 K of TCR (the 125 °C basis), not 60 K.

## 2. Task 1: monitors (C1–C7 and the N rows) on the current parts

### 2a. Failure-mode assumptions: no change

**LM2901B.** It shares the LM339B's data sheet SLCS006Z.
- The values are the same, now held over −40..125 °C (6.8 p.8):
  - VIO ±5.5 mV;
  - IB −50 nA;
  - VCM (V−) to (V+) − 2.0 V;
  - VOL ≤ 550 mV at 4 mA.
- The "only one input needs to be in range" note is unchanged (6.8 note 1 p.8).
- TA is −40..125 °C and VS min 2 V (6.4 p.6), so the C7 sliver is unchanged.
- Output leakage is specified only at 25 °C (100 nA, p.8). Leakage can only pull `good` low (announce); it cannot mask.
- The taps sit at ≤ 1.9 V against a 15 V input ceiling (P − 2 V).
- **The rates source is now direct, not a proxy.** SLCA004 names the LM2901B:
  - FIT 16 (die 2, package 14): Table 1-1 p.3;
  - FMD: Table 1-3 p.4;
  - pinout: Fig. 1-2 p.5, which is the mapping the fault simulation already uses.

**TL431BQ.**
- Vref 2.483–2.507 V and VI(dev) 34 mV max, over −40..125 °C (SLVS543S 6.13 p.14). These are the same numbers as the
  BI grade.
- Same DBZ pinout.
- FIT/FMD source unchanged: SNVA914 p.1, TL431-Q1, 6 FIT, open 25 / short 35 / out of specification 40 %.
- The cathode node has no capacitor, so the stability question is unchanged.

The fault simulation's 61 single faults therefore carry over to S47 unchanged.

### 2b. C4 reference drift at the 125 °C basis

C4 means a reference drift: the TL431 (or R79/R80) moves all four thresholds of a rail together.

| Drift / masked threshold | Worst dormant threshold | To H | To Q | D59 (60 K) |
|---|---:|---:|---:|---:|
| up: span OV | 20.035 V | +0.965 | −1.035 | 19.96 V |
| up: neg OV | 2.468 V | +3.032 | −0.068 | |
| down: span UV | 14.398 V | +1.998 | −1.102 | 14.45 V |
| down: neg UV | 1.681 V | **+0.175** | −0.073 | 1.684 V (+0.179) |

No drift masks a threshold past its hard limit H silently. C4 stays announced. The result is identical with the negative
rail at 100 K as well.

### 2c. Exposure, FIT·rails

The chain term is 13.0 in every row. D59's values are in brackets.

| Case | S47 total (D59 V1) | S47 front end | V2 as drawn (D59) | V2+F2+v5 amended (D59) |
|---|---:|---:|---:|---:|
| Base (TI FS FITs) | **19.29** (19.29) | 6.29 | 16.83 (16.83) | **16.68** (16.68) |
| k_u = 1 | 27.23 (27.23) | 6.33 | 25.18 | 24.58 |
| k_u = 0 | 11.35 (11.35) | 6.25 | 8.48 | 8.78 |
| k_o = 0.5 | 31.59 (31.59) | 8.39 | 28.53 | 28.38 |
| Allocation B | 22.53 (22.53) | 9.53 | 18.93 | 18.53 |
| TPS3703 FMD | 19.29 (19.29) | 6.29 | 15.93 | 15.78 |
| Passives ×5 | 31.19 (31.19) | 11.39 | 31.73 | 30.98 |
| Worst | 59.78 (59.78) | 19.48 | 58.92 | 55.43 |
| TI estimator at 55 °C (D59 row, control) | 16.78 (16.78) | 3.78 | 15.07 | 14.92 |
| **New: TI estimator, own rows, at c17.5 temperatures** | **64.80** | **51.80** | 15.78 | 15.63 |
| New: same at c28 | 68.69 | 55.69 | 15.84 | 15.69 |
| **New: SN 29500 reference × Arrhenius, c17.5** | **52.17** | **39.17** | 165.88 | 165.73 |
| New: same at c28 | 55.08 | 42.08 | 177.76 | 177.61 |

**How the temperature rows are built.**
- **TI estimator.** TL431BQDBZR and LM2901BIDR each carry 8.0 FIT at 55 °C (HTOL, 1,463 units, 0 fails, Ea 0.7 eV).
  The TPS3701DDCR carries 0.1 FIT (183,306 units).
- **Moving to the local temperature.** Each rate is moved from 55 °C with TI's Arrhenius calculator. TI's own example
  on that page, 16.7 → 69.2 FIT from 55 → 75 °C, is reproduced in `sources47`.
- **The SN 29500 row.** It uses the FS documents' reference rates, moved with the same 0.7 eV:
  - TL431: 3 FIT at 45 °C (SNVA914 p.1);
  - LM2901B: 6 FIT at 55 °C (SLCA004 Table 1-2 p.3);
  - TPS3700-Q1: 20 FIT at 55 °C (SLVAEM2A Table 2-2 p.3).

  SN 29500-2's own π_T model was not available. 0.7 eV pure Arrhenius is TI's calculator method, and it is an upper
  figure.
- **B's TPS3701.** It is placed at each island's comparator temperature, less the LM2901B's 3.14 K self-heat.
- **Passives and chain.** Both stay at base. Chain parts have no B3 rows; the chain is the same in every variant, so it
  cancels in the comparison.

**Per-part FIT at c17.5** (FS base / estimator at T / SN 29500 at T):

| Part | Temp | FS base | Estimator at T | SN 29500 at T |
|---|---:|---:|---:|---:|
| U29 | 102.6 °C | 16 | 184 | 138 |
| U31 | 101.3 °C | 16 | 171 | 128 |
| U30 | 96.5 °C | 16 | 129 | 97 |
| U17 | 92.4 °C | 6 | 101 | 82 |
| U21 | 85.3 °C | 6 | 65 | 53 |
| U19 | 81.9 °C | 6 | 52 | 43 |

**Reading the temperature rows.**
- **The current design is far more exposed at its modelled temperature than in D59.** The front end goes from 6.3 to
  39–52 FIT·rails, about 6–8×. Both sources agree on that, and the front end now outweighs the chain.
- **They point in opposite directions on B.**
  - On the estimator, B looks far better (2.6 against 51.8 front end). That comparison is the one TI warns against:
    "it is not recommended to compare failure rates", given 1,463 against 183,306 units.
  - On SN 29500, B is 3× worse, because the TPS3701's 20 FIT reference sits against the LM2901B's 6.
- **So temperature does not move the D59 ranking either way.** The base case remains the decision basis.

## 3. Task 2: U5 (REF25), new block

### What U5 sets

Both protections scale with REF25:
- **OCP:** U6 trips at I = REF × (1 − 2 × 11.7/24.3) / 1 mΩ = **37.04 A per volt** (92.6 A at 2.5 V).
- **OVP:** U7 trips at REF × 140/150 × 119.99 = **111.99 V per volt** (280.0 V at 2.5 V).
- **s47 bands** (`bands-s47.md`): OCP 68.87–117.45 A, OVP 272.64–287.45 V, at VR 2.4838–2.5162 V. VR is ±15 mV plus 1.2 mV
  over the extended range (SNOS455H 5.6 p.7).

### Reliability data

**FS (SNOAA49A, LM4050-N-Q1: same die family and data sheet SNOS455H):**
- 4 FIT: die 3, package 1 (Table 2-1 p.3). SN 29500: 20 FIT at 55 °C (Table 2-2 p.3).
- **TI's die FMD has no open and no short mode** (Table 3-1 p.4):
  - VR out of specification 40 %;
  - dynamic impedance out of specification 20 %;
  - IRMIN above maximum 40 %.
- Open and short appear only in the pin FMA (Tables 4-3 / 4-4 p.6).
- The revision history on p.7 says "changed total FIT from 5 to 6", which contradicts Table 2-1's 4. 6 FIT is carried
  as a sensitivity.

**TI estimator.**
- It serves no row for LM4050AEM3-2.5/NOPB (empty table, empty .xlsx).
- Its 3k-reel twin LM4050AEM3X-2.5/NOPB gives 0.1 FIT at 55 °C (101,758 units). That is 1.03 FIT at 89.1 °C and 2.6 FIT
  at 104.7 °C.
- SN 29500 × Arrhenius gives 206 / 519 FIT, an upper figure.

### Modes

FIT A puts the FMD on the total FIT (D59's base). FIT B puts the die FMD on the die FIT and spreads the package FIT over
the pins.

| Id | Mode | FIT A | FIT B | Effect on OCP / OVP | Class | Detection today | S-O-D RPN |
|---|---|---:|---:|---|---|---|---|
| U1 | VR out of spec, **high** (half of 40 %) | 0.8 | 0.6 | Both thresholds rise; no companion announces | **fail-dangerous** (magnitude unknown) | **none** | 5-3-9 135 |
| U2 | VR out of spec, low | 0.8 | 0.6 | Both fall: more protective. Nuisance only at −36 % (OCP under the 59 A envelope) or −39 % (OVP under the 170 V bus) | fail-safe | announced only if large | 3-3-5 45 |
| U3 | Dynamic impedance out of spec (20 %); carries any oscillation | 0.8 | 0.6 | VR moves with the 0.11–0.48 mA current. Ripple reaches the thresholds through 6.1 k‖1 nF and 9.3 k‖1 nF and OCP_NODE through 5 k‖100 pF, so it is a nuisance risk, not a mask | half fail-dangerous (k_o) | none | 5-3-9 135 |
| U4 | IRMIN above spec (40 %) | 1.6 | 1.2 | If above the 0.145 mA minimum available, VR sags: thresholds fall | fail-safe | announced only if large | 3-3-5 45 |
| U5o | **Cathode pin open** | 0 | 0.167 | REF25 rises to **3.05–3.35 V**. OVP 341–375 V nominal (band 334–383 V) against the 288.02 V rule and the 295 V D3 stand-off. OCP 113–124 A nominal (band top 156 A) against 117.45 A | **fail-dangerous** | **none** | 7-2-9 126 |
| U6o | **Anode pin open** | 0 | 0.167 | Same as U5o. With the anode open there is no DC path through U5. TI's "held low" (Table 4-3) assumes its 2.2 k-fed test circuit (p.5) and does not describe this node | **fail-dangerous** | **none** | 7-2-9 126 |
| U7o | Pin 3 (NC) open | 0 | 0.167 | none: pin 3 floats by design (SNOS455H 8.1 p.15) | – | – | – |
| U8s | Cathode–anode short | 0 | 0.167 | REF25 = 0. OVP_THRESH 0 < VSENSE_IN, so OVP trips at once. OCP trips at any bus current above 2 × VOS / 1 mΩ | fail-safe | announced (BUS_FAULT at power-up) | 3-2-1 6 |
| U9s | Anode–NC short | 0 | 0.167 | none (TI class D) | – | – | – |
| U10s | NC–cathode short | 0 | 0.167 | "Iq can increase" (TI class C), through the pin-2/3 parasitic Schottky: REF unchanged or clamped low | fail-safe | announced if clamped | 3-2-5 30 |

**How close the limits are for U1 (drift high).** The band top scales with REF, so the drift at which each limit is
reached is:
- 288.02 V OVP rule: **+0.20 %** over VR max (REF 2.5212 V);
- 118.74 A R5 pulse row: +1.10 %;
- 295 V D3 stand-off: +2.63 %.

Nearly any upward out-of-specification drift is dangerous. It is the TL431-style drift without the companion threshold
that bounds C4.

**Dormant fail-dangerous FIT:**

| Basis | FIT |
|---|---:|
| Allocation A, k_o = 0 (D59 base) | 0 |
| Allocation B, k_o = 0 | 0.33 |
| Allocation B, k_o = 0.5 | 0.78 |
| Allocation B, k_o = 1 | 1.23 |
| Allocation B, k_o = 1, at the SN 29500 rate | 63 |

Assembly opens at U5 (its three solder joints) are not in any FIT figure, yet they are the likeliest way to reach U5o or
U6o.

**Diverse layers that remain.**
- The firmware VBUS over-range latch at 231 V (`n21_signal.h:21`, DECISIONS 2026-10-03 entry). It runs on the AMC1311
  path with the controller's own LM4040, independent of U5. It backs the OVP function but does not detect U5.
- The D3 TVS clamps the bus.
- **The shoot-through OCP has no diverse layer except F1.**

### Stability verdict: stable

- SNOS455H states "stability with any capacitive load" (p.1), "internally compensated to be stable without the use of
  an output capacitor" (7.3 p.14), and "if … a bypass capacitor is used, the LM4050-N remains stable" (8.1 p.15).
- **The frozen netlist puts no capacitor on REF25.** The only capacitance the cathode sees directly is pad and trace
  parasitics.
- The 2.1 nF of filter capacitance sits behind ≥ 10 kΩ: C30 100 pF via R32, C31 1 nF via R34 12.6 k, C33 1 nF via R36 10 k.
- Oscillation is not a credible mode. It is carried inside U3.

### Fail-dangerous with no detection (flags)

1. **U5o / U6o:** U5 open, by a random pin failure or an assembly defect.
2. **U1:** VR drifting high.
3. **The monitor front-end dormant rows, unchanged from D59 in every variant:** C2, C5, C6, N1, N2, N4, and C2b at k_o.
   Plus the chain rows: ISO6721FB OUTB stuck high, BAT54 open, U40 stuck high / Y–VCC, R_bleed open, and U22/U23
   stuck low.

## 4. Task 3: B13 hooks for every latent fail-dangerous mode

Constraint found in the source: **firmware cannot command anything on the HOT, LS or HS side.**
- U32 and U9 are CA-IS3720HW parts with 2 forward channels and none in reverse.
- The ISO6721FB reverse channels are unused: INA is tied to n_ls and OUTA is open.
- J4 carries only BUS_FAULT, VBUS, CT and ZC back to the controller. BIAS_GOOD reaches no J4 pin, and J4.1 has been
  unconnected since stage 38.

The coverage figures below are for one rail of S47's allocation-B dormant FIT × thresholds (12.70 per rail), and for
the 13.0 FIT·rails chain.

| Hook | Type | What | Covers | DC (field) | DC (production) | Cost |
|---|---|---|---|---:|---:|---|
| **H1 REF25 watchdog** | cheap HW, continuous | 54.2 k / 10 k (0.1 %) from REF25 into U14 INB (pin 4, today on ocp_kelvin_p). U14 OUTB (pin 6, today alone) wired to HOT5_UV_RAW, so it shares R50 and drives BUS_FAULT | U5o/U6o; U1 above the trip | **100 % of U5o/U6o**; U1 only above 2.527–2.610 V | 100 % (U5 open) | 2 × 0603 + copper |
| **H2 BIAS_GOOD readback** | cheap HW + firmware POST | BIAS_GOOD → 1 k → J4.1 → GPIO with a 100 k pull-down. POST: BIAS_GOOD = 0 before the bias is up and 1 after; = 1 while PERMIT is requested | U40 Y open, always. U40 stuck high / Y–VCC only if the MCU samples before the heartbeat starts (sequencing to confirm at bring-up). Automates B8 | chain 13.8 %, or 36.9 % with sequencing | B8 automated | 1 R + trace + GPIO |
| **H3 per-tap forcing** | EOL | 12 tap pads (+ B8), observed on J4.1 (H2) | comparator die, pins, tap caps | 0 | **90.6 %** | 12 pads + fixture |
| **H4 LS rail raise** | EOL | ground TPS7A4700 3P2V (pin 6) from a pad, giving 20.2 V | every LS span-OV mask, dividers included | 0 | 27.8 % alone, **93.7 % with H3** | 1 pad |
| **H5 REF25 / OVP / OCP functional** | EOL | REF25 pad 2.4975–2.5025 V at 25 °C (5.6 p.7); OVP ramp to 288 V on a DC source; OCP injection at the Kelvin pads | U5 assembly defects, wrong part, network | 0 | ~100 % of U5 / OVP / OCP manufacturing defects | 1–3 pads + HV DC source |
| H6 field halfref shift (not recommended) | HW + firmware | U32 → CA-IS3721HW (1 forward / 1 reverse; pinout not checked), the ISO6721FB spare reverse channels, 2 switched resistors per monitor | only faults that mask both thresholds of a group (N1, N2, …). The wired-AND `good` node passes on any one live channel | 44.8 % | – | isolator swap + 6 switches + three islands |

**H1 sizing** (`fmea47.json` → `U5.watchdog`):
- **Trip window.** It trips at 2.527–2.610 V, from VIT+ 396–404 mV (SBVS187G 6.5 p.6), IINB ±15 nA, and a 0.1 %/25 ppm
  ratio over 100 K.
- **No false trips.** The window sits 10.4 mV above VR max.
- **U5 open is caught.** With the watchdog's own load, U5 open gives 2.88–3.18 V, 0.27 V above the trip. INB is ≤ 0.50 V
  (7 V absolute maximum, 6.1 p.5).
- **U5 bias current.** The minimum falls from 0.145 to 0.106 mA, still above IRMIN 65 µA.
- **What it cannot catch.** Drift up to 2.61 V goes undetected; at that REF the OVP top is 298.2 V and the OCP top
  121.8 A.
- **Side effect.** U14 pins 4–5 (INB–VDD) are adjacent. With VDD on V15_LS, that short would put about 15 V on INB, where
  today it collapses V15_LS (announced). **Moving U14 VDD to HOT5 removes it:**
  - with VDD on HOT5 the short puts only 5 V on INB, inside the rating;
  - below UVLO, OUTA is driven low (note 3 p.6);
  - below V(POR), the HOT side is unpowered and the CA-IS3720HW defaults high.

  Moving VDD changes the reviewed HOT5-UV supply, so the supply-sequencing review needs to agree first.

**Recommended minimal set: H1 + H2 + H3/H4/H5, one copper pass.** Make it the next layout stage that touches the bias
and HOT islands, as B13 already asks. Firmware adds a POST step for H2.

**What the set achieves:**
- **U5.** The flagged fail-dangerous U5 open becomes announced in the field. The remaining U5 residual is drift-high
  within 2.516–2.61 V.
- **Chain.** Field coverage of 14–37 %. B8 becomes automatic.
- **Monitor front end.** Manufacturing defects are screened at ~94 %.

**What it does not achieve:** field coverage of random monitor front-end faults stays 0 % in this design and in either
form of B. That residual is 6.29 FIT·rails on the base basis, and 39–52 at temperature. Closing it needs H6-class hardware
or a different architecture, and it is not cheap.

## 5. Task 4: totals against D59, and whether its conclusion holds

**On D59's basis the S47 totals equal D59's 1c-4420 row in every case:** base 19.29, worst 59.78, estimator at 55 °C
16.78. The same holds for B: 16.83 as drawn and 16.68 amended.
- **The B advantage is unchanged:** about 2.6 FIT·rails (13 %).
- **B's price premium falls slightly, to about +$1.37.** That is D59's +$1.49 less stage 46's +$0.12, not re-priced. B's
  TPS3701 is already rated to TJ 125 °C (SBVS240C Table 6.5), so B needs no grade change.

**The U5 block is new for both variants and identical in both.** It adds 0 FIT under D59's convention, or 0.33–1.23 FIT
under allocation B. It does not change the ranking.

**At the modelled temperatures the ranking depends on the source** (§2c):
- TI estimator: B better by about 4×, a comparison TI says not to make.
- SN 29500: B worse by about 3×.

So temperature gives no robust signal for B either. **D59's conclusion stands:** keep 1c-4420, now on TL431BQ / LM2901B,
and build amended candidate B (split span bottoms, VDD from v5) only if those islands are re-laid.

What changes from D59:
- **The chain no longer dominates.** At temperature the front end dominates the current design's exposure.
- **U5 is a second dormant single point with no proof test.** H1 closes it cheaply.

## 6. Limits and notes

- **Not sourced:**
  - SN 29500-2's own temperature factor (0.7 eV Arrhenius used, an upper figure);
  - a TI estimator row for the exact LM4050AEM3-2.5/NOPB (its X-reel twin used);
  - a TPS3701 FS document (D59's TPS3700-Q1 proxy kept);
  - the out-of-specification magnitude distribution of any part (k_o swept);
  - R31's TCR (100 ppm/K assumed for the 1 % thick film; it only moves the U5-open voltage by ±0.7 %);
  - the CA-IS3721HW pinout (H6 only).
- **Gaps in TI's own data:**
  - SNOAA49A contradicts itself on the FIT (4 in the table, 6 in the revision history);
  - its anode-open entry does not fit this circuit.
- **What the numbers are.** They are ranking metrics, not field predictions.
  - The chain stays at base FIT because its parts have no B3 rows.
  - The OCP/OVP band corners under U5 open are scaled from the s47 corners in proportion to REF. They are estimates; the
    nominal values are exact.
- **Housekeeping:**
  - The first control run reached the durable `runs-native21/s16-fmea-b-dl/` through a symlink. Its `manifest.py`
    rewrote `MANIFEST.json` there with byte-identical content (`cmp` against the committed `datasheet-manifest.json`);
    only the mtime changed.
  - From then on the study used a private copy, `s16copy/dl/`.
  - Downloads are in `runs-native21/s47/fmea-dl/` (hashes: `results/fmea-dl-manifest.txt`).

**Files:**
- `scripts/fmea47.py`, `scripts/sources47.py`, `scripts/run_all.sh`;
- `results/fmea47.{json,md}`, `results/sources47.{json,md}`;
- `s16copy/`: the D59 study copy and its rerun.
