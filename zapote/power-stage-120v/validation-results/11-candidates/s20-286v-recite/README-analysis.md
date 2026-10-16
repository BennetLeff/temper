# U3 HOT5 LDO and the ledger's 286 V rows (S19 / S20), board of record s47

Analysis only. Nothing was written into any worktree. Inputs were read from `ps-integrate` at `651640bb7`, and its
working-tree `ledger.json` is byte-identical to that commit (sha256 `6bec3cfa…`). The B3 run files and `margins.json`
are on the integration board `63aba33f`. `bands_hot5.py` reproduces `bands-s47.md` exactly on those runs: 68.87–117.45 A
and 272.64–287.45 V at release, 287.62 V at c28.

Datasheets are in `runs-native21/s47/u3-dl/`. They were read with `pdftotext -layout` and `python3 -I`. Page numbers are
PDF pages, and they match the printed footers.

| File | Document | sha256 (first 16) |
|---|---|---|
| tps709.pdf | TI SBVS186H (Jul 2021) | 8c14e3efae738a27 |
| tps709-q1.pdf | TI SLVSCE6D (Aug 2025) | bd01fad0eb2defdd |
| tlv3201.pdf | TI SBOS561C (May 2024) | 1777bba814c74772 |
| tps3700.pdf | TI SBVS187G (Feb 2019) | 3bb7daed20b154bf |
| amc1311.pdf | TI SBAS786C (Jun 2022) | 4a80cec704b1f432 |
| sn74lvc1g10.pdf / sn74lvc1g17.pdf | TI SCES486E / SCES351Y | 4902c877… / c76fa723… |
| ca-is3720_v105_cn.pdf | Chipanalog v1.05 (2023-09-01), copied from `temp-ratings-dl` | d189c76c1fe68084 (the ledger's reference) |
| ca-is372x_en.pdf | Chipanalog v1.02 EN, same tables | de9f63ecb923fb2c |

## Verdicts

- **Q1 (U3): part change, and a netlist change before that.**
  - **New violation, on all four TPS70950s (U3, U37, U38, U39): EN is tied to IN.**
    - SBVS186H 7.4 p.13 says: "Do not connect EN to VIN. The EN pin is clamped by a 6.5-V Zener diode. Do not exceed
      the 7-V absolute maximum rating on the enable pin or excessive current flowing into the Zener clamp will destroy
      the device." The abs max is VEN 7 V (6.1 p.4), and the recommended range is 0–6.5 V (6.3 p.4).
    - U3's EN sits at V15_LS, ≤ 15.46 V (`power_stage_120v.ato:479-480`). U37–U39 sit at the rail span, ≤ 17.43 V
      (`f6_bias.ato:193-196`). `native-21/ECO.md:65` records "IN and EN use V15_LS".
    - The fix: float EN (TI: a 300 nA pull-up enables the part, 7.4 p.13), or feed it from a divider that stays under
      6.5 V.
  - **TJ at the release case is inside 125 °C:** 112.8 °C, +12.2 K. At c28 (the ratchet case) it is 130.5 °C, −5.5 K.
  - **HOT5 accuracy is unspecified above 85 °C on the catalog part,** and its local temperature is 106.7 °C at release.
    No band moves inside the guaranteed envelope. Even so, the U5 and supervisor ledger rows rest on a HOT5 window that
    has no datasheet basis at this temperature.
  - **Candidate: TPS70950QDBVRQ1** (LCSC C485909, 11,607 at JLC). It guarantees ±1 % to 125 °C, has the same DBV pinout
    and costs +$0.39 per instance at 500. It does not cure EN: its EN abs max is also 7 V.
- **Q2 (286 V rows): ledger gap; re-cited by the patch. No row crosses its max_ratio at the s47 band top.**
  - 286 V is a pre-round-3 hand estimate of the OVP trip corner. It is not a bus maximum, not a datasheet limit, and not
    a protection-record value.
  - The patch moves 20 checks in 13 entries to **287.62 V**, the higher of release and c28. The CST3015 volt-time row
    moves to 119.09 A. The gate PASSES on the copy.
  - The tightest rows are D3 / D17 standoff 0.959 (max 1.0), C5 / C6 "Vbus worst hot" 0.792 (max 0.8), and ISO6721
    VIOWM 0.452 (max 0.5).
  - **Two event-row inputs are still stale, and either one crosses a row.** The tank energy E_t = 0.475 J comes from the
    stage-13b 97.77 A band. At the bank-ov record's 0.884 J, C12 / C13 / C19 / C20 reach **0.503 > 0.5** and C5 / C6 hot
    reaches **0.883 > 0.8**. Separately, an OVP-delay overshoot of ≥ 7.9 V at gate-off makes C5 / C6 hot cross.

---

## Q1. U3 TPS70950DBVR (HOT5)

### 1.1 The two claims, verified

| Claim | Datasheet text | Cite |
|---|---|---|
| Rated TJ 125 °C | "TJ Operating junction temperature −40 … 125 °C" (recommended operating); abs max TJ −55..150 °C | SBVS186H 6.3 p.4; 6.1 p.4 |
| ±1 % only to 85 °C | 6.5 header: "at ambient temperature (TA) = –40°C to +85°C, VIN = VOUT(typ) + 1 V …, IOUT = 1 mA"; "DC output accuracy VOUT ≥ 3.3 V −1 % … 1 %"; line regulation 10 mV max (VIN to 30 V); load regulation 50 mV max (100 µA–150 mA) | SBVS186H 6.5 p.5 |

Note that the accuracy limit is stated in ambient (TA) terms. The B3 pad estimate is the closest available proxy for
U3's ambient: 106.7 °C at release, 124.3 °C at c28.

Probe values (`u3_junction.py`, from `b3-ratings/runs/*_p0p25/p0p5.json` with the gate estimator, board 63aba33f) agree
with `monitor-sweep-s47.json` (106.7 / 124.3 °C):

| Case | U3 pad | U37 pad | U38 / U39 pads |
|---|---:|---:|---:|
| c17.5_h10 @ 61 (release) | 106.66 | 99.36 | 84.6 / 84.2 |
| c22_h10 @ 55 | 108.75 | 96.13 | 79.1 / 79.4 |
| c28_h10 @ 55 | 124.32 | 102.29 | 79.9 / 81.5 |

### 1.2 Every HOT5 consumer (`native-21/frozen/default.net`, net `hot5`) and what HOT5 accuracy does there

U3 itself: pin 1 IN = v15_ls, 2 GND = ocp_kelvin_p, **3 EN = v15_ls**, 4 NC, 5 OUT = hot5. Caps C26 (10 µF 1210), C28,
C32, C34, C35, C36, C49 (100 nF) and C149 (1 µF) carry no requirement.

| Ref | Part | Pin on HOT5 | What HOT5 does there | Datasheet window | Physical HOT5 need |
|---|---|---|---|---|---|
| R31 → U5 | 5.6 k 1 % → LM4050AEM3-2.5 | R31.1 | Bias feed. U5 must stay in IRMIN 65 µA..1 mA for the band's 1.2 mV L term (SNOS455H 5.6 p.7) | IR = (HOT5 − VR)/R31 − loads | **4.320 .. 8.03 V** (1.3) |
| U6 | TLV3201 (shunt OCP) | 5 VCC | Supply only. The threshold is REF25 × R35/(R34+R35). VIO ≤ 4 mV at VCC 5 V and 2.7 V, TA −40..125 °C (SBOS561C 6.5 p.5, 6.7 p.6). PSRR ≥ 65 dB, 2.5–5.5 V (p.5) | VS 2.7–5.5 V (6.3 p.4) | 2.7 .. 5.5 V; above 5.0 V a PSRR term (1.5) |
| U7 | TLV3201 (bus OVP) | 5 VCC | Same; the threshold is REF25 × R37/(R36+R37) | as U6 | as U6 |
| U8 | SN74LVC1G10 NAND | 5 VCC | Logic supply; its inputs are push-pull or Schmitt-buffered | VCC 1.65–5.5 V (SCES486E p.3); ICC 10 µA (p.4) | 1.65 .. 5.5 V |
| U9 | CA-IS3720HW side A | 3 VDDA | Isolator input supply; the H default output covers HOT5 loss | VDDA 2.375–5.5 V (v1.05 7.3 p.6); UVLO− 1.88–2.325 V | 2.375 .. 5.5 V |
| U4 | AMC1311B | 1 VDD1 | Bus-voltage amplifier supply to the firmware. Gain and offset are specified over VDD1 3.0–5.5 V (B grade) | 3.0–5.5 V (SBAS786C 6.3 p.6; 6.10 p.10) | 3.0 .. 5.5 V |
| R48 / R49 → U14 | 105 k / 10 k → TPS3700 INA+ | R48.1 | **The quantity measured:** the HOT5 UV threshold. U14 runs from V15_LS, not HOT5 | VIT− 387–400 mV, VIT+ 396–404 mV, I(INA+) ±25 nA (SBVS187G 6.5 p.6); INA+ > VIT+ → OUTA high (Table 1 p.10) | **> 4.632 V** (no nuisance trip), > 4.678 V (release at power-up) (1.4) |
| R50 → U15 | 10 k pull-up → SN74LVC1G17 | R50.1, U15.5 | Pull-up and Schmitt supply, so the levels are ratiometric to HOT5 | VCC 1.65–5.5 V (SCES351Y p.5) | 1.65 .. 5.5 V |

- **Physical requirement:** HOT5 in **4.678 .. 5.5 V**, set by the UV supervisor and the 5.5 V IC ceilings.
- **Recorded requirement:** `audit.rs` and the U5 ledger rows hold **4.75 .. 5.15 V**.
- **Thresholds that use HOT5 as a reference or pull-up:** only the HOT5-UV supervisor and the U15 pull-up (ratiometric).
  No OCP or OVP threshold does (1.5).

### 1.3 U5 window arithmetic (LM4050AEM3, R31 5.6 k ±1 %)

- **Loads at VR max 2.5162 V** (0.1 % strings −0.1 %, KELVIN_N at −0.15 V):
  - OCP: (2.5162 + 0.15) / 19.98 k = 133.4 µA;
  - threshold: 2.5162 / 24.276 k = 103.6 µA;
  - OVP: 2.5162 / 149.85 k = 16.8 µA;
  - **total 253.9 µA**.
- **IRMIN floor:** HOT5 ≥ (65 + 253.9) µA × 5.656 k + 2.5162 = **4.320 V**.
- **At the guaranteed 4.89 V:** IR = (4.89 − 2.5162) / 5.656 k − 253.9 µA = 165.8 µA. At the audit's 4.75 V it is
  141.1 µA, which reproduces the ledger's 0.1411 mA.
- **1 mA ceiling, every load open:** HOT5 ≤ 1 mA × 5.544 k + 2.4838 = **8.03 V**, above the 7 V VOUT abs max. U5 cannot
  leave its window for any HOT5 the LDO can make.

### 1.4 HOT5 UV supervisor (TPS3700, 105 k / 10 k RT0603 0.1 % 25 ppm, ±100 K drift)

- **Falling trip:** VIT− × k − I·R = **4.420 .. 4.632 V**.
- **Rising release:** **4.522 .. 4.678 V**.
- Here k = 1 + R48/R49 at its corners (11.427..11.574), and I·R = 25 nA × 105 k = 2.6 mV.
- FAULT-INTERFACE.md's nominal 4.60 / 4.54 V lies inside these bands.

### 1.5 Do the OCP / OVP bands depend on HOT5?

No. thresholds.py:

- **OCP:** I = [REF·R33/R32 − (REF·R35/(R34+R35) + VOS)(1 + R33/R32)] / R5.
- **OVP:** V = (REF·R37/(R36+R37) − VOS) × (ΣR26..29 + R30) / R30.

Neither contains HOT5. HOT5 can reach them through only three paths:

1. **U5's IR,** through the 1.2 mV current-regulation term. That term is valid for HOT5 4.32..8.03 V (1.3), so there is
   no movement.
2. **TLV3201 PSRR.** The 4 mV VIO is tabulated at VCC 5 V and at 2.7 V, so it bounds 2.7..5.0 V. Above 5.0 V, the adverse
   term is 10^(−65/20) × (HOT5 − 5) = 0.562 mV/V.
   - At the guaranteed top of 5.11 V it is 0.062 mV: OCP low −0.12 A, OVP top +0.008 V.
   - At 5.5 V it is 0.28 mV: −0.55 A / +0.035 V.
3. **The TLV3201 CMRR offset from VCC/2.** This is a pre-existing term that thresholds.py does not model. HOT5 sets VCC/2
   (1.6, finding c).

From `bands_hot5.py` (LM4050AEM3, solved network; the controls reproduce bands-s47):

| Case | HOT5 envelope | Terms | OCP band before Kelvin (A) | Low after −2.123 A (margin to 64.17) | OVP band (V) |
|---|---|---|---|---|---|
| c17.5 release | control | thresholds.py | 68.87–117.45 | 66.74 (+2.57) | 272.64–287.45 |
| c17.5 | 4.89–5.11 (Q1 guaranteed) | + PSRR | 68.75–117.58 | 66.62 (**+2.45**) | 272.63–287.45 |
| c17.5 | 4.632–5.5 (physical window) | + PSRR | 68.32–118.02 | 66.19 (+2.02) | 272.60–287.48 |
| c28 | control | thresholds.py | 67.57–119.09 | 65.45 (+1.28) | 272.47–287.62 |
| c28 | 4.89–5.11 | + PSRR | 67.45–119.21 | 65.33 (+1.16) | 272.46–287.63 |

- **Reading:** inside any HOT5 the circuit can tolerate, OVP moves ≤ 0.035 V and OCP ≤ 0.55 A. Inside the guaranteed
  envelope, OCP moves only 0.12 A.
- **The OVP band depends only on U5** (and the divider network and the U7 offset).
- **No band rule is broken by HOT5.**

### 1.6 Junction temperature

**Vin.** V15_LS − OCP_KELVIN_P = span (V15_LS − N_LS) − neg (LEG_RET − N_LS). With the S16 rail model
(`s16-fmea-b-2026-10-15/scripts/bands.py:35-37`: span 16.575..17.425 V, neg 1.9654..2.0757 V), that is
**14.50 .. 15.46 V**. At the span-OV detection corner (18.643 V, DECISIONS 62) it is 16.68 V.

**Load** (maximum / typical, mA; datasheet maxima over temperature):

| Consumer | max | typ | Source |
|---|---:|---:|---|
| U4 AMC1311B IDD1 (4.5 < VDD1 < 5.5 V) | 9.7 | 7.1 | SBAS786C 6.10 p.11 |
| U9 CA-IS3720HW IDDA, H, VIN = 0 V (healthy: bus_fault_hot low), 5 V ±10 %, −40..125 °C | 4.1 | 2.5 | v1.05 7.9.1 p.11 |
| U6 + U7 TLV3201 IQ, −40..125 °C | 0.13 | 0.08 | SBOS561C 6.5 p.5 |
| U8 + U15 LVC ICC | 0.02 | — | SCES486E p.4; SCES351Y p.6 |
| R31 (all of U5 plus the REF25 loads) at 5.11 V, R31 −1 %, VR min | 0.474 | 0.446 | |
| R48 + R49 | 0.044 | 0.044 | |
| R50, only while OUTA asserts | 0.512 | 0 | |
| **Total** | **14.98** | **10.17** | |

**Dissipation.** P = (Vin − VOUT) × I + Vin × IGND (bounded at 0.1 mA, `kelvin_budget.py` CENSUS21):

- maximum: (15.46 − 4.89) × 14.98 mA + 1.5 mW = **0.160 W**;
- typical: 10 V × 10.17 mA = 0.102 W;
- at the span-OV corner: 0.178 W.

The B3 run deposits **0.1 W** at U3 (`runs/heat_c17.5.json`; its own note says "≤ 19 V drop × 13.6 mA"), so the pad is
slightly under-solved.

**TJ = pad + ψJB × P,** with ψJB = 38.7 K/W (SBVS186H 6.4 p.4; RθJB 39.5). The Q1 new chip is 40.7 (SLVSCE6D 5.4 p.4).

| Case | Pad | TJ, typ P | **TJ, max P** | Margin to 125 °C | Bound: + (RθJA − ψJB) × (P − 0.1 W) |
|---|---:|---:|---:|---:|---:|
| c17.5 @ 61 (release) | 106.7 | 110.6 | **112.8** | **+12.2 K** | 123.2 (still ≤ 125) |
| c22 @ 55 | 108.8 | 112.7 | 114.9 | +10.1 K | 125.3 |
| c28 @ 55 (ratchet) | 124.3 | 128.3 | **130.5** | **−5.5 K** | 140.9 |

- The last column is a deliberately loose bound on the unsolved extra 0.06 W. It uses the JEDEC-board RθJA 212.1 K/W.
- Q1 grade: +0.4 K on each row.
- c28 is over 125 °C on either grade. It is a ratchet case (DECISIONS 61), like the other rated-part ratchet rows.

### 1.7 HOT5 error above 85 °C

- **Guaranteed, catalog TPS70950DBVR:** none. 6.5 p.5 stops at TA 85 °C, and the part sits at 106.7 °C.
- **Guaranteed, TPS70950QDBVRQ1 (SLVSCE6D 5.5 p.5,** "at –40°C ≤ TJ, TA ≤ 125°C"): ±1 % + line 10 mV + load 50 mV
  (signs taken adverse both ways) gives **4.89 .. 5.11 V** to 125 °C.
  - Headroom to the physical window (4.678..5.5 V): −0.21 / +0.39 V.
  - Headroom to the audit window (4.75..5.15 V): −0.14 / +0.04 V.
- **Typical only (catalog), SBVS186H Figures 6-2 / 6-3 p.6:** the TJ −40/25/85/125 °C line-regulation curves at 10 mA
  lie inside plot windows of 3.29–3.31 V (±0.3 %) and 6.49–6.51 V (±0.15 %). So the typical drift to 125 °C is
  ≲ ±15 mV at 5 V. That is typical, not a bound.
- **Consequence:** with the catalog part, the 4.75–5.15 V window that audit.rs and the U5 ledger rows assume has no
  datasheet basis above 85 °C. The physical margins are large (1.3–1.5), so nothing is predicted to move. The Q1 grade
  restores a guaranteed basis.

### 1.8 Candidate part

- **TPS70950QDBVRQ1 (TI TPS709-Q1, SLVSCE6D):**
  - AEC-Q100 grade 1, TA −40..125 °C (p.1). EC over −40 ≤ TJ, TA ≤ 125 °C (5.5 p.5), the same ±1 % / 10 mV / 50 mV.
  - DBV SOT-23-5: IN 1, GND 2, EN 3, NC 4, OUT 5 (Figure 4-1 / Table 4-1 p.3), identical to TPS709 DBV (SBVS186H 5 p.3)
    and to `HotLdo` (`f6_parts.ato:316-325`).
  - Orderable: TPS70950QDBVRQ1, Active, marking SLX (addendum p.25).
- **JLC** (`u3-dl/jlc-raw/detail_C485909.json`, read 2026-10-16 04:36 UTC):
  - C485909, Extended, **11,607 in stock**, $0.7048 at 500, against C96028 TPS70950DBVR at $0.3117 / 5,886 stock;
  - **+$0.39 per instance** (+$1.57 per board for all four);
  - stock covers 500 boards × 4 = 2,000;
  - the JLC attribute reads "−40℃~+125℃@(Tj)".
- **No E-grade exists.** SBVS186H Table 11-1 p.17 lists only TPS709xx(x) yyy z and the M3 suffix ("same electrical
  specs"). TPS709A / TPS709B are different DBV pinouts (Figures 5-2 / 5-3 p.3), so they are not drop-ins.
- **Neither grade allows EN on IN.** TPS709-Q1 5.1 p.3 also has VEN 7 V abs max, with the "below 6.5 V" pin note (p.3).

### 1.9 Found on the way (Q1)

a. **EN tied to IN: VIOLATION** (above). `scripts/u3ledger.py` writes the entry; the gate FAILS on that copy, by design
   (section 3).

b. **Stale Kelvin census.** `kelvin_budget.py` CENSUS row U9.1 still carries the ISO7710's 2.4 mA. U9 has been
   CA-IS3720HW since stage 31, with IDDA 4.1 mA max (H, input low, v1.05 p.11).
   - +1.7 mA × 150.0 mΩ = +0.255 mV, which is a further −0.26 A of trip shift (2.123 A / 2.047 mV).
   - The s47 OCP floor margin goes from +2.58 to about **+2.31 A**.

c. **TLV3201 CMRR offset is not in thresholds.py.** VIO is specified at VCM = VCC/2 (SBOS561C p.5). The OCP comparator
   trips at VCM = 1.204 V, so it is 1.35 V away at HOT5 5.11 V. The CMRR is ≥ 60 dB, but only at 25 °C, VCC 5 V (p.5).
   - That adds up to 1.35 mV, or −2.7 A at the OCP low corner. The release floor margin becomes **−0.19 A** (c28:
     −1.47 A). OVP moves ≤ 0.03 V.
   - The CMRR figure is a 25 °C minimum, used here at temperature, so this is a flag for the band owner. It is not yet
     a counted violation.
   - Separately, TLV3201's 1.2 mV input hysteresis is typical only (p.5) and is outside the band model.

d. **U37** (monitor-LS 5 V) is also above 85 °C (99.4 °C pad). Its consumers were not analysed.
   SN74LVC1G132DBVR's ledger entry already assumes "LS 5 V tolerance (TPS70950) ±5 %".

---

## Q2. Ledger rows that quote 286 V

### 2.1 What 286 V is

- **Origin: `DC-LINK-CLAMP.md:28`.** "The static upper OVP corner is approximately 286 V using REF25=2.520 V, 0.1%
  threshold resistors, the 1% high-side bus divider, 0.1% bottom resistor and +5 mV comparator threshold error."
  - It is a hand corner with no TCR term. Check: 2.520 × 140.14 / 150.13 + 5 mV = 2.3573 V, times
    (1.8988 M + 15.784 k) / 15.784 k = 121.30, gives 285.95 V.
- **ALT-D3.md:60 (2026-10-09)** used it as a starting condition: "Bus start … 286 V (static OVP corner)". The ledger rows
  then cited ALT-D3:60, and r2-cost's `bus_peak_no_clamp.py` used V0 = 286 V.
- **It was already superseded when ALT-D3 used it.** Round 3 (2026-09-27, `02-protection-timing/round3/README.md:30`)
  had the committed OVP static band at **272.09–288.02 V**, with TCR. `simplify-2026-10-15/ovp_band.py` turned 288.02 V
  into the "must not rise" rule, stated as "the bus maximum that D3 / C5C6 / ALT-BIAS ratings use".
- **So 286 V is an early, optimistic estimate of the OVP trip band top.** It is not a design bus maximum, not a
  datasheet-derived limit, and no protection record defines it.
- **The s47 band top** is 287.45 V at release and 287.62 V at c28 (bands-s47.md:22, :24). The bound row is 288.24 V
  (:25). The rule is 288.02 V.

### 2.2 How it relates to the trip band, the delay and overshoot

- **The OVP is a static restart-inhibit comparator** (`power_stage_120v.ato:595-596`: "Hardware restart inhibit through the controller latch"). The bus can sit just below the trip
  band top indefinitely. The band top is therefore the correct maximum for continuous ratings: DC VR, working voltage,
  TVS standoff, VIORM / VIOWM. Trip-delay overshoot is a transient and does not apply to them.
- **No record defines an OVP trip delay or overshoot.** B2 (`round3/b2-gate-off/README.md:21-23`) states that crossing
  the OVP threshold cannot prevent returned tank energy from charging the bus.
- **The records' transient bus maximum** is r2-cost's stacked closed form (`bus_peak_no_clamp.py:17-22`): V0 = the
  static OVP corner, plus the tank energy at gate-off, plus a 500 µH / 30 A line ring, at C −19 %, with no D3 credit.
- **What I could quantify of the delay:**
  - U7's sense filter is R_th (1.88 M ∥ 15.8 k) = 15.67 kΩ × C27 1 nF = **15.67 µs**. Add the 2.27 µs chain bound
    (`fault_check.py` T_D) for t_d = 17.94 µs.
  - If the 30 A line current kept charging 14.9 µF through t_d, V0 at gate-off would be +36.1 V. That ignores the
    bridge's own draw, so it is an upper sensitivity, not a committed bound.

### 2.3 Rows, re-cited (`scripts/ledger286.py`, V_OVP = 287.62 V, I_TOP = 119.09 A)

Static rows (V_OVP, or V_OVP / 2, / 4, / √2):

| Entry (refs) | Check | Old → new value | Limit | Ratio old → new | max |
|---|---|---|---:|---|---:|
| B32676G1905K000 (C5, C6) | Vbus static | 286 → 287.62 V | 750 | 0.3813 → 0.3835 | 0.8 |
| CC1206JKNPOCBN102 (C12, C13, C19, C20) | bus static OVP | 286 → 287.62 V | 1000 | 0.2860 → 0.2876 | 0.5 |
| 30KPA150CA (D3, D17) | standoff | 286 → 287.62 V | 300 | 0.9533 → **0.9587** | 1.0 |
| AMC1311BDWVR (U4) | barrier | 286 → 287.62 V | 2120 | 0.1349 → 0.1357 | 0.5 |
| AMC1311BDWVR (U4) | input clip (row renamed "VSENSE at the OVP band top") | 2.3836 → 2.3971 V | 2.516 | 0.9474 → 0.9527 | 1.0 |
| CA-IS3720HW (U9, U32) | barrier | 286 → 287.62 V | 1414 | 0.2023 → 0.2034 | 0.5 |
| ISO6721FBDR (U43, U44) | barrier | 286 → 287.62 V | 637 | 0.4490 → 0.4515 | 0.5 |
| ISO6721FBDR (U43, U44) | working | 202.2 → 203.38 Vrms | 450 | 0.4493 → **0.4520** | 0.5 |
| 2EDR8259XXUMA1 (U1, U2) | working | 202.2 → 203.38 Vrms | 1250 | 0.1618 → 0.1627 | 0.5 |
| RC1206FR-07220KL (R3, R4) | V | 143 → 143.81 V | 200 | 0.7150 → 0.7190 | 0.8 |
| RC1206FR-07470KL (R22–R29) | divider | 71.5 → 71.91 V | 200 | 0.3575 → 0.3595 | 0.8 |

Event rows (stacked closed form, V0 = 287.62 V; the script's 286 V control reproduces 450.7 V): 451 → **451.6 V**.

| Entry | Check | Limit | Ratio old → new | max |
|---|---|---:|---|---:|
| CC1206JKNPOCBN102 | bus no-clamp worst | 1000 | 0.4510 → 0.4516 | 0.5 |
| B32676G1905K000 | Vbus worst | 750 | 0.6013 → 0.6021 | 0.8 |
| B32676G1905K000 | Vbus worst hot (105 °C case) | 570 | 0.7912 → **0.7923** | 0.8 |
| B32652A0104K000 (C38–C41) | V / V hot | 1000 / 687.5 | 0.4510 → 0.4516 / 0.6560 → 0.6569 | 0.8 |
| GBJ2510-F (BR1) | V reverse | 1000 | 0.4510 → 0.4516 | 0.8 |
| 2EDR8259XXUMA1 | barrier | 1767 | 0.2552 → 0.2556 | 0.5 |
| RC1206FR-07220KL | V transient (V/2: 225.5 → 225.8 V) | 400 | 0.5637 → 0.5645 | 1.0 |

Band-top current row (coordinator's addition):

| Entry | Check | Old → new | Ratio | max |
|---|---|---|---|---:|
| CST3015-200ED (T1) | volt-time (stress renamed "Volt-time at the shunt-band top") | 67.6 V·µs at 118.74 A → **67.8 V·µs at 119.09 A** | 0.0530 → 0.0531 | 0.5 |

- The CST3015 value uses `ct_options.py:36-39`: 119.09 / 200 × (3.0 + 5.94) Ω / (π × 25 kHz). The 118.74 A control
  reproduces 67.6.
- At the simulated turn-off current of 155.4 A it would be 88.4 V·µs (0.069). That still passes.

**Evidence strings** (all resolve under the unit root at 651640bb7; the gate checks each one):
`c47-ref25-grade/results/bands-s47.md:22; …:24`, `r2-cost/scripts/bus_peak_no_clamp.py:17-22`,
`g04-g09-tank-detect/scripts/ct_options.py:36-39`, and `elec/src/power_stage_120v.ato:491-516` / `:351-358` / `:493`.

**Related text edits:** the gap texts in RC1206FR-07220KL ("286 V static") and RC1206FR-07470KL ("11 mW each at 286 V")
are updated. The LM4050AEM3 entry's S20 gap is removed and replaced by a closing note. Each touched entry gets a dated
S20 note. The script is idempotent: a re-run on its own output is byte-identical.

### 2.4 Sensitivity and crossings (`scripts/q2_sensitivity.py`)

- **Static rows at 287.45 / 287.62 / 288.02 (rule) / 288.24 V (hottest bound):** no row crosses. The worst are D3 0.9608
  and ISO6721 VIOWM 0.4529 at 288.24 V.
- **Event rows:**

| Stacked case (V0 base 287.62 V) | Vpk | C12-family (max 0.5) | C5 / C6 hot (≤ 456 V) | others |
|---|---:|---|---|---|
| E_t 0.475 J (as patched) | 451.6 | 0.452 | 0.792 | pass |
| E_t 0.475 J + 36.1 V OVP-delay line charge | 472.6 | 0.473 | **0.829 > 0.8** | pass |
| E_t 0.884 J (bank-ov, 118.74 A top) | 503.1 | **0.503 > 0.5** | **0.883 > 0.8** | pass (C38–C41 hot 0.73, BR1 0.50, 2EDR 0.28) |
| E_t 0.884 J + 36.1 V | 523.1 | **0.523** | **0.918** | pass; above the 520 V die-VDS screen |

- **C5 / C6 "Vbus worst hot" crosses if V0 at gate-off rises 7.9 V above the band top.**
- **E_t 0.475 J is a stale band-top input.** It is ALT-D3 §1.1's worst tank energy for the stage-13b shunt band
  47.32–97.77 A with a 1.5 µs delay. The current band top is 119.09 A with T_D 2.267 µs, and the bank-ov record gives
  coil energy 0.884 J at I_off 155.4 A (`bank-ov-double-fault/README.md:84`, L max 73.15 µH; the ALT-D3 basis used
  77 µH).
- These rows assume no D3 clamp credit. D3 / D17 are fitted (V(BR) min 335 V string; 466.8 V at 129.8 A, ALT-D3), so
  the clamp is the real backstop. It is sized at 129.8 A, below the 155 A turn-off current.
- **I did not re-base E_t in the patch.** It changes the physics basis rather than a citation, and it turns two
  violation-severity checks to VIOLATION. A re-run of `bus_peak_no_clamp.py` with the bank-ov tank state, or a decision
  to take D3 clamp credit, should decide it.

## 3. Gate runs (copies only; `gate.py --ledger COPY --root <unit> --report <scratch>`)

| Copy | Result | Counts (V / P / U / X) |
|---|---|---|
| `base/ledger.json` (= 651640bb7) | PASS | 3 / 39 / 52 / 0 |
| `patched/ledger.json` (ledger286.py) | **PASS** | 3 / 39 / 52 / 0 |
| `u3/ledger.json` (patched + u3ledger.py) | **FAIL**, as intended: "VIOLATION: TPS70950DBVR … EN pin tied to IN" | 3 / 39 / 51 / 1 |

- **Effect of u3ledger.py:** the TPS70950DBVR line becomes SAFETY class, since HOT5 supplies the firmware-independent
  OCP / OVP chain.
- **Its checks:**
  - EN U3 2.209 and EN U37–U39 2.489: violations;
  - TJ release 0.902: passes;
  - TJ c28 1.044 and accuracy range 1.255: gaps;
  - load 0.075.
- `git status` on the ledger directory is clean after all runs.

## 4. Files

- `results.md`: this file.
- `scripts/`:
  - `u3_junction.py` (→ `results/u3_junction.json`);
  - `bands_hot5.py` (→ `results/bands_hot5.json`; imports `bands47.py` read-only);
  - `ledger286.py` (the S20 patch);
  - `q2_sensitivity.py` (→ `results/q2_sensitivity.json`);
  - `u3ledger.py` (the S19 entry);
  - helpers `netq.py`, `pg.py`, `jlc.py` (cache in `u3-dl/jlc-raw`).
- `base/ledger.json` (651640bb7), `patched/ledger.json`, `u3/ledger.json`.
- `results/ledger286.json` (row table), `results/ledger286.diff`, `results/gate-report-*.json`.

**Reproduce:**

```sh
S=/Users/bennet/.claude/jobs/fbfc46b4/tmp/u3-286; U=/Users/bennet/Desktop/temper/worktrees/ps-integrate/zapote/power-stage-120v
python3 -I $S/scripts/u3_junction.py; python3 -I $S/scripts/bands_hot5.py; python3 -I $S/scripts/q2_sensitivity.py
python3 -I $S/scripts/ledger286.py --src $S/base/ledger.json --out $S/patched/ledger.json --json $S/results/ledger286.json
python3 -I $U/native-21/verification/datasheet-ledger/gate.py --ledger $S/patched/ledger.json --root $U --report $S/results/gate-report-patched.json
python3 -I $S/scripts/u3ledger.py --src $S/patched/ledger.json --out $S/u3/ledger.json
```

**To land:** copy `ledger286.py` into `c47-ref25-grade/scripts/` (or an S20 folder), run it on the unit ledger, and run
`gate.py` and `tests/test_gate.py`. Landing `u3ledger.py` makes the gate FAIL until EN is fixed in the source. That is
intended.
