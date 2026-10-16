# S23: OCP comparator common-mode fix (2026-10-16)

Analysis lane, reviewed at integration. Datasheets and the JLC cache live outside git at `runs-native21/s23cmp/dl/`. The recommended B′-1.02 V resistor change is built in stage 49.

# S23 / DECISIONS 64: U6 (OCP) and U7 (OVP) comparator options on s48

This is analysis only. PS (`ps-integrate/zapote/power-stage-120v`, HEAD 05a3d9138, board s48 2b46d90e) was treated as read only. Every PS module was imported with `dont_write_bytecode` set, no PS `main()` was called, and `git status` was unchanged afterwards.

- **Scripts:** `scripts/` (run each with `python3 -I`, from any working directory).
- **Results:** `results/`.
- **Datasheets:** `runs-native21/s23cmp/dl/<part>/` (PDF and pdftotext `.txt`). Page numbers are PDF pages. `s23_bands.py` re-finds each cited string and records its page in `results/s23_bands.json` → `citations`.

## 0. Answer

1. **Option A fails.** No drop-in SOT-23-5 comparator passes.
   - Only one candidate has VIO guaranteed over the full input CM range and temperature: the **TS3021A**.
   - It fails on several counts:
     - JLC stock is 23.
     - Its operating VCC maximum is 5.0 V, but HOT5 reaches 5.11 V.
     - Its 300 nA IIB costs 1–2 A on the band.
     - It still misses the c28 floor, by −0.99 A.
   - Every other part either has no full-range or over-temperature basis, or has a larger VIO (6–10 mV), which fails by 5–13 A.
2. **Option B as posed fails.** Re-centring toward VCC/2 makes the band worse.
   - With only REF25 and the shunt, raising the trip VCM requires attenuating the shunt weight. dI/dVOS goes 2.0 → 2.9 → 5.2 A/mV.
   - c28 R0 margin goes +0.67 → −7.47 A at 1.6 V and −21 A at 2.0 V.
   - Using HOT5 to lift both inputs adds a divider-mismatch × HOT5 term of a few mV, which is larger than the 1.4 mV it removes.
3. **The opposite direction works (B′).** Moving the trip VCM down to about 1.0 V raises the shunt weight.
   - This is a BOM-only change: R33, R34 and R35 change value, on the same 0603 pads.
   - The nominal trip is held at 92.593 A.
   - The OCP top falls by 3.3 A, so the 1600 V double-fault bank voltage improves by about 43 V.
   - The CM allowance the floor can absorb rises from 0.335 mV to 2.19 mV at c28.
4. **Recommendation: B′-1.02 V plus the Option C bench run at the new VCM.**
   - Values: R32 10 k (unchanged), R33 7.5 k, R34 16 k, R35 11 k, all RT0603BRD 0.1 % / 25 ppm.
   - B′ passes the review's R1 reading (60 dB applied hot) at both networks: +2.34 A release, +1.22 A c28.
   - B′ does not by itself create a datasheet guarantee. The bench run supplies it, with a pass limit of 2.16 mV against a typical delta of about 0.3 mV.
   - Option C on the as-built divider would need a limit of 0.305 mV (0.095 mV in the physical HOT5 window). That is not a credible pass.

## 1. Task 1: U6 / U7 re-confirmed on s48

Source: `scripts/s23_netcheck.py` → `results/s23_netcheck.json`. Netlist sha256 1f85ad2d…; BOM sha256 e092da76….

| | Pin 1 OUT | Pin 2 GND | Pin 3 IN+ | Pin 4 IN− | Pin 5 VCC |
|---|---|---|---|---|---|
| U6 | ocp_ok_hot (→ U8.1 only) | ocp_kelvin_p | ocp_node (R32.2, R33.1, C30) | ocp_thresh (R34.2, R35.1, C31) | hot5 |
| U7 | ovp_ok_hot (→ U8.3 only) | ocp_kelvin_p | ovp_thresh (R36.2, R37.1, C33) | vsense_in (R29.2, R30.1, C27, U4.2) | hot5 |

**Package and pinout.**
- BOM line `TLV3201AIDBVR, "U6,U7,U10,U11,U12", Package_TO_SOT_SMD:SOT-23-5` (LCSC C105188).
- The pinout is the op-amp style DBV order: OUT, V−, IN+, IN−, V+.
- A drop-in needs exactly this order. That excludes the LMV331 order and the TLV1811L reversed-supply variant.

**Output.**
- ocp_ok_hot and ovp_ok_hot each carry only the comparator output and one SN74LVC1G10 CMOS input. There is no pull-up.
- So the comparator must be push-pull. Open-drain parts would need a new resistor and copper.

**Trip common mode** (every band vertex):
- U6: ocp_thresh = REF25 × R35/(R34+R35) = **1.1924–1.2150 V** (c28: 1.1922–1.2153).
- U7: **2.3174–2.3493 V**.

**Supply.** HOT5 Q1 window 4.89–5.11 V; physical window 4.632–5.5 V.

**U6 local temperature on the HOT island.**

| Source | Release c17.5 @ 61 | c22 | c28 @ 55 |
|---|---:|---:|---:|
| S21 `b3-ratings/temp-ratings-2026-10-15/results.json`, U6 est | **89.9 °C** | 90.6 °C | **104.4 °C** |
| S21, U7 est | 90.4 °C | — | 104.6 °C |
| bands47 estimator on the s48 runs (board 2b46d90e), U6 | 89.8 °C | — | 104.33 °C |

- The c28 case is the still-air solve. In it, R5's element is 194.6 °C, against a 170 °C limit in margins.json.
- So TA ≥ 125 °C is required.

**Response-time budget.**
- `stage15-28A/fault_check.py`: T_FRONT 555 ns, T_CHAIN 573.2 ns, T_Q_EXTRA 0.988 µs, T_GATE 150 ns, so T_D = 2.267 µs.
- task-02 README: the front end is "500 ns RC + 55 ns comparator".
- TLV3201 tPD, high to low: 45 typ / 50 max ns at 20 mV overdrive, CL 15 pF, 25 °C (SBOS561C 6.6 p.5).
- **Cost of a slower part** (fault_check I_off form at 280 V, OCP top 119.1 A, CT failed): the coil slope bound is 42.7 A/µs.
  - Each extra 10 ns of comparator delay adds 0.43 A to I_off.
  - +45 ns adds 1.92 A.
  - +100 ns adds 4.27 A, which feeds the stacked bus event where C12 is already 0.512 without clamp credit.
- Budget used here: tPD ≤ TLV3201 (about 50 ns at 20 mV).

## 2. Option A: drop-in comparators

### 2.1 Screen

The "basis" column asks whether VIO is guaranteed over the full input CM range and over temperature, or alternatively whether CMRR has a minimum over temperature.

| MPN | Maker | Package / pinout | Out | VIO max and condition (page) | CM basis | Other | JLC stock / price | Verdict |
|---|---|---|---|---|---|---|---|---|
| TLV3201AIDBVR (as built) | TI | SOT-23-5 ✓ | PP | 4 mV, VCM = VCC/2, −40..125 (SBOS561C p.5) | CMRR 60 dB at 25 °C only | IQ 65 µA, tPD 50 ns | C105188: 3221, $0.6135 | the S23 gap |
| TLV3201-Q1 | TI | **SC70 only** | PP | 6 mV, VCC/2 (SBOS856A) | same | | — | no DBV |
| **TS3021AILT** | ST | SOT-23-5 ✓ (OUT, Vcc−, IN+, IN−, Vcc+, p.1) | PP | **4 mV −40..125 °C, "full Vicm range"** (DocID12485 Rev 8 Table 5 p.8) | **yes** | **VCC operating 2–5 V at −40..125 °C** (Table 2 p.3; HOT5 reaches 5.11 V; abs max 5.5 V). IIB 300 nA / IIO 100 nA, ICC 135 µA. TPHL 55 typ / 95 max, TPLH 105 max ns (20 mV, 50 pF) p.8. Temperature limits "guaranteed through correlation and simulation" (note 1) | **C5199085: 23**, $1.576 | fails: stock, VCC, c28 band (§2.2), +45 ns |
| TS3021ILT (non-A) | ST | ✓ | PP | 7 mV full Vicm, −40..125 (p.8) | yes | as above | C1509142: 1780, $0.341 | 7 mV fails the band |
| MAX9140AAUK+T | ADI | SOT-23-5 ✓ | PP | 6.0 mV (A grade, −40..125), header VCM = 0 V (19-2064 Rev 10 p.2) | CMRR 850 µV/V max over temp, "full common-mode range" (Note 7 p.3) | IIB 350 nA, ICC 400 µA; tPD 40 ns typ, no max | C3659233: 0 | fails band and stock |
| MAX999AAUK+T | ADI | SOT-23-5 ✓ | PP | 6.0 mV at VCM −0.1 / 5.1 V, −40..125 (19-1129 Rev 8 p.2) | CMRR 1.0 mV/V max over temp (p.3) | **IIB ±30 µA**, ICC 7 mA, tPD 10 ns | C5328755: 3 | fails badly (IIB) |
| NCS2250SN2T1G | onsemi | TSOP-5 ✓ (OUT, VSS, IN+, IN−, VDD, p.1) | PP | 6 mV, mid-supply, boldface −40..125 (NCS2250/D Rev 5 Table 6 p.4) | CMRR 59 dB min over temp (p.4) | IDD 250 µA, tPD 64 ns max at 100 mV, 90 typ at 20 mV | C603840: 0 (SC-88A: 453) | fails band and stock |
| TLV3601DBVR | TI | ✓ | PP | 5 mV, header VCM = VEE + 300 mV (SNOSDB1E p.7) | CMRR 80 typ only | ICC 7 mA | C5213958: 1166 | no basis |
| TLV3601-Q1 | TI | SC70 | PP | same family | | | — | no DBV |
| TLV7011 / TLV7031 | TI | ✓ | PP | ±8 mV, VCM = VS/2 (p.7) | CMRR typ | tPD 260 ns / µs | — | fails |
| TLV1811DBVR / -Q1 | TI | ✓ (L variant reversed) | PP | 4 mV, VS = 12 V, VCM = VS/2 (SNOSDC8E p.8) | no CMRR spec | tPD 450–900 ns | C5373003: 30728 | no basis, slow |
| LMV7219M5X | TI | ✓ | PP | 8 mV, TJ −40..85 °C, TPCB ≤ 105 °C (SNOS458I p.5) | CMRR 55 dB to 85 °C | IS 2.4 mA | C283912: 13254 | fails temp and band |
| LMV7239M5X / -Q1 | TI | ✓ | PP | 8 mV "at temp extremes", VCM = V+/2 (p.5) | CMRR 52 dB at 25 °C | tPD 82 ns typ | C467167: 4033 | fails band |
| LMV7271 | TI | ✓ | PP | — | | tPD 880 ns | — | slow |
| MCP6561T-E/OT | Microchip | ✓ | PP | ±10 mV at VCM = VSS, 25 °C (p.3) | CMRR 54 dB at 25 °C | | C117501: 3274 | fails |
| TS3011ILT | ST | ✓ | PP | 8 mV −40..125 (p.4) | CMRR 50 dB | | 0 | fails |
| ADCMP600BRJZ | ADI | ✓ | PP | 5 mV at 25 °C, VCCI 2.5 V (Rev A p.3) | CMRR 50 dB | IIB ±5 µA, IVCC 4 mA | C93798: 781 | fails |
| LTC6752 (S5) | ADI | TSOT-23-5 | CMOS | 8.5–9 mV over temp (6752fc p.3/5) | | **supply 2.45–3.5 V** (abs max 3.6 V) | 19–35 | fails |
| TLV3501, TLV3012, TLV1805 | TI | **SOT-23-6** | | | | | | not drop-in |
| TP1961-TR | 3PEAK | ✓ | PP | ±10 mV at VCM = 1.2 V, 27 °C | CMRR typ | | C124557: 12814 | fails |
| TP2011-TR | 3PEAK | ✓ | PP | 4 mV | | −40..85 °C | 1190 | fails temp |
| RS8901XF / COS3201TR (not on the list; TLV3201-class clones) | Runic / Cosine | ✓ | PP | 3 / 5 mV at VCM = VS/2, 25 °C | CMRR typ | | 51040 / 21221 | no basis |
| Nexperia NCX2200 | Nexperia | TSSOP-5 / XSON | PP | 9 mV, −40..85 | | 800 ns | 0–355 | fails |

**Copies of the ADI datasheets.**
- `analog.com` blocks curl and WebFetch, so the files were opened in Chrome.
- The ADCMP600 PDF is saved in the dl folder.
- Chrome blocked the automatic download for MAX9140, MAX999 and LTC6752. Their rows were taken from pdf.js text in the browser. The quoted rows are in `dl/<part>/excerpt.txt`, with source URL, byte size and document revision.

### 2.2 Band for the parts with a guaranteed basis

**Method.** Source: `scripts/s23_bands.py` → `results/s23_bands.{json,md}`.
- **Engine:** the committed bands47 engine on the s48 B3 solve. Every exact_corners vertex is used, with the candidate's VIO, CM term (per vertex VCM), PSRR term outside the supply span its VIO is specified at, and input bias.
- **Bias:** two forms.
  - "committed": IIB × the Thevenin sum, which is thresholds.py's method.
  - "lp": the worst case of I+R+ − I−R− under the IIB and IIO limits.
- **Kelvin shift:** the s48 census with the U6.2 / U7.2 rows replaced by the candidate's IQ max.

**Controls.**
- The TLV3201 R0 row without PSRR equals bands47.band on this board: 68.63–117.70 A (release) and 67.37–119.30 A (c28).
- The Kelvin census reproduces budget-native21s48: 15.505 mA, −2.41 A.

**Results:** Q1 HOT5 window, floor 64.17 A, OVP top limit 288.02 V, bank = Z0,max (12.75 Ω) × OCP top ≤ 1600 V.

| Part (reading, bias) | Kelvin (A) | Release: low (margin) | c28: low (margin) | c28: top / bank | OVP top (c28) / margin |
|---|---:|---|---|---|---|
| TLV3201, R0 (no CM term) | −2.41 | 66.10 (+1.93) | 64.84 (+0.67) | 119.43 A / 1523 V | 287.649 / +0.371 |
| TLV3201, R1 (60 dB hot, the review) | −2.41 | 63.45 (**−0.72**) | 62.20 (**−1.97**) | 122.19 / 1558 | 287.675 / +0.345 |
| TLV3201, R3 (Fig 6-5 typical) | −2.41 | 65.59 (+1.42) | 64.33 (+0.16) | 119.96 / 1529 | 287.654 / +0.366 |
| TLV3201, R4 (spec-literal 5.4 mV) | −2.41 | 55.52 (−8.65) | 54.31 (−9.86) | 130.51 / 1664 | 288.309 / −0.289 |
| **TS3021A, full range, lp bias** | −2.431 | 64.43 (+0.26) | 63.18 (**−0.99**) | 121.15 / 1545 | 287.989 / +0.031 |
| TS3021A, full range, committed bias | −2.431 | 59.53 (−4.64) | 58.31 (−5.86) | 126.28 / 1610 | 288.558 / −0.538 |
| MAX9140AA, lp bias | −2.513 | 58.03 (−6.14) | 56.82 (−7.35) | 127.78 / 1629 | 288.555 / −0.535 |
| NCS2250 | −2.467 | 59.19 (−4.98) | 57.97 (−6.20) | 126.59 / 1614 | 287.912 / +0.108 |
| MAX999AA (±30 µA IIB), lp bias | −4.55 | −309.6 | −312.1 | — | −57 |

- In the physical HOT5 window (to 5.5 V), every margin is a further 0.4–1.0 A lower. See the md file.
- The TS3021A's PSRR term above 5 V (58 dB × 0.11 V = 0.14 mV) is outside its rated VCC. It is included, but it does not make 5.11 V a rated condition.

**Verdict.**
- No Option A part closes S23.
- The only part with a guaranteed basis that comes close, the TS3021A, misses c28 by 0.99 A, has 23 in stock, is out of rating at HOT5 above 5.0 V, and adds up to 45 ns of delay (+1.9 A I_off).

## 3. Option B: re-centre toward VCC/2, and the reverse (B′)

### 3.1 Why re-centring up fails

At the trip, ocp_node = k′·REF − w·I·R5 equals ocp_thresh = k·REF, where k′ = R33/(R32+R33), w = 1 − k′ and k = R35/(R34+R35). With only REF25 and the shunt available:
- VCM ≈ k·REF.
- Holding the trip forces k′ − k = w·I·R5/REF.
- So raising VCM forces w down, and dI/dVOS = 1/(w·R5) rises. Every comparator and divider-ratio error grows by the same factor.

Engine sweep, nominal trip held, same part classes (`results/s23_bands.md` "B" rows):

| VCM at trip | R32 / R33 / R34 / R35 (Ω) | dI/dVOS | c28 R0 | c28 R1 | Top (R1) / bank |
|---:|---|---:|---:|---:|---|
| 0.80 | 13114 / 6886 / 16524 / 7776 | 1.525 | +7.31 | +4.70 | 115.1 / 1467 |
| 1.00 | 11571 / 8429 / 14580 / 9720 | 1.728 | +4.15 | +1.52 | 118.5 / 1510 |
| 1.20 (as built) | 10 k / 10 k / 12.6 k / 11.7 k | 2.0 | +0.67 | −1.97 | 122.2 / 1558 |
| 1.60 | 6943 / 13057 / 8748 / 15552 | 2.881 | −7.47 | −10.17 | 130.9 / 1669 |
| 2.00 | 3857 / 16143 / 4860 / 19440 | 5.185 | −21.27 | −24.12 | 145.7 / 1858 |
| 2.30 | 1543 / 18457 / 1944 / 22356 | 12.96 | −55.5 | −58.9 | 182.4 / 2325 |

**Other re-centring routes.**
- **Lift both inputs from HOT5 with matched pull-ups.** The residual is Δw × HOT5. With 0.1 % parts, Δw is about 0.25 × 0.2 %, roughly 2.5 mV per side, which is more than the 1.4 mV R1 term it removes. It also makes HOT5 tolerance enter the trip.
- **A 4.096 V reference** (LM4050-4.1 in the same SOT-23 footprint, with R31, R34–R37 and R144/R145 rescaled):
  - VCM is about 2.0 V and the CM term falls by about 0.8 mV.
  - But divider-ratio errors scale with REF (+0.8 mV).
  - The U5 headroom at the 4.632 V HOT5 floor falls to 0.53 V.
  - Six or more parts change. Not minimal, and no net gain.
- **Lower the comparator VCC so VCC/2 is about 1.2 V.** The TLV3201 minimum is 2.7 V, and U8 runs at HOT5 levels. Not viable.

### 3.2 B′: lower the VCM (BOM only)

Source: `scripts/s23_optb.py` → `results/s23_optb.{json,md}`. It searches E192 values, keeps R32+R33 and R34+R35 near the committed loads and R32‖R33 at 4–6 k (C30's RC), and holds the nominal trip to within 0.25 A. JLC stock was checked for every value.

| Design | Changes | Nominal (A) | VCM | A/mV | Release R0 / R1 / R3 / R4 | c28 R0 / R1 / R3 / R4 | c28 R1, phys HOT5 | c28 top (R0) / bank | Bench allowance, c28 Q1 / phys (mV) |
|---|---|---:|---:|---:|---|---|---:|---|---|
| As built | — | 92.593 | 1.204 | 2.00 | +1.93 / −0.72 / +1.42 / −8.65 | +0.67 / −1.97 / +0.16 / −9.86 | −2.78 | 119.43 / 1523 | 0.335 / 0.125 |
| **B′ 1.02 V** | **R33 → 7.5 k, R34 → 16 k, R35 → 11 k** | **92.593** | **1.0185** | 1.75 | +4.99 / **+2.34** / +4.47 / −4.28 | +3.84 / **+1.22** / +3.34 / −5.37 | +0.51 | 116.04 / 1480 | **2.194 / 1.983** |
| B′ 0.94 V | R32 → 11 k, R33 → 7.32 k, R34 → 16.5 k, R35 → 10 k | 92.453 | 0.943 | 1.665 | +6.02 / +3.39 / +5.51 / −2.80 | +4.93 / +2.31 / +4.42 / −3.84 | +1.63 | 114.60 / 1461 | 2.961 / 2.745 |
| B′ 0.90 V | R32 → 11 k, R33 → 6.81 k, R34 → 15.8 k, R35 → 8.87 k | 92.383 | 0.899 | 1.619 | +6.64 / +4.00 / +6.13 / −1.94 | +5.57 / +2.95 / +5.07 / −2.95 | +2.30 | 113.76 / 1450 | 3.44 / 3.23 |

**Why 1.02 V and not lower.**
- On SBOS561C Fig 6-5 (p.7, VCC 5.5 V, five typical units; render at `dl/renders/tlv3201_p-07.png`), the low-side input-pair transition runs from about 0.3 V to 0.9 V. One unit (red) steps by about 0.8 mV around 0.8 V.
- At about 1.0 V every unit is within about 0.3 mV of its VCC/2 value.
- So 1.02 V stays out of the transition tail. 0.90 / 0.94 V buy margin but sit at its edge.

**B′-1.02 BOM** (same 0603 footprints, no copper or netlist change):

| Ref | Was | New | LCSC / JLC stock | $ @ ≥1000 (JLC) |
|---|---|---|---|---|
| R32 | RT0603BRD0710KL | unchanged | C95204 | — |
| R33 | RT0603BRD0710KL | **RT0603BRD077K5L** (7.5 k 0.1 % 25 ppm) | **C728597**: 20378 | 0.0242 (5k+), 0.0262 (600+) |
| R34 | RT0603BRD0712K6L | **RT0603BRD0716KL** (16 k) | **C326732**: 17962 | 0.0431 |
| R35 | TNPW060311K7BEEA | **RT0603BRD0711KL** (11 k, an existing BOM line) | **C728581**: 9816 | 0.0381 (600+) |

- The R34 12.6 k line disappears. TNPW 11.7 k stays for R145.

**Side effects checked:**
- **C30 filter.** R32‖R33 = 4.29 k, so τ is 429 ns (was 500 ns). The comparator overdrive slope rises ×1.14, so the 555 ns front end does not grow. C30 → 120 pF would restore τ to 514 ns if wanted. It is not needed.
- **C31 filter.** R34‖R35 = 6.52 k (was 6.07 k).
- **REF25 current** (audit.rs `min_reference_cathode_current_ua` form: HOT5 4.75 V, REF max 2.5162 V): 98.8 µA, against the 65 µA IRMIN (was 107.5 µA).
- **Constants to change.** `audit.rs` `ocp_offset_load` 20_000 → 17_500 and `ocp_threshold_load` 24_300 → 27_000. The `r_ocp_sense` / R33 MPN expectation, `bands47.CURRENT`, thresholds.py `validate_inputs` MPNs and `kelvin_budget.BAND_BEFORE` also need updating.
- **Kelvin census.** Unchanged: the U5.2 row bounds R31's whole current. The R32/R33 string current into ocp_kelvin_n rises from 0.13 to 0.148 mA, a negligible drop on the trace.
- **TLV3201 input bias.** 5 nA × 10.8 k = 54 µV, the same as before.
- **Hysteresis.** 1.2 mV typical × 1.75 A/mV = +2.1 A on the top: 118.1 A / 1506 V.
- **Coil pickup.** Its referred stack in amps is unchanged; it enters through the Kelvin traces.
- **U7 / OVP.** Untouched. Its VCM is 2.33 V, within 0.24 V of VCC/2. Under R1 the top is 287.675 V, which is < 288.02 V. Its allowance is 0.371 V / 0.12 V per mV = 3.1 mV.

**B′ alone is not a guarantee.**
- It passes the review's R1 and the typical R3 at both networks.
- The spec-literal R4 still fails (−5.37 A at c28).
- So the bench run (§4) is still needed to close S23. B′ turns that run from a sub-0.3 mV knife edge into a 2.2 mV pass window.

## 4. Option C: bench measurement

Source: `scripts/s23_bench.py` → `results/s23_bench.json`.

**Samples.**
- n = 30 TLV3201AIDBVR from at least 3 reels or date codes, 10 each, from the production source (JLC C105188).
- A further 5 U6s from built boards (desoldered after the board test) are a cross-check.

**Fixture.**
- Kelvin-connected SOT-23-5 socket on a 4-layer coupon.
- VCC from a precision supply, sensed at pin 5. GND is pin 2.
- IN− from a 0.01 % divider or DAC at VCM. IN+ = IN− + Δ from a 20-bit DAC through 10 k / 100 pF, matching the in-circuit source impedance.
- 6.5-digit DMM on the IN+ − IN− differential. Output load: 15 pF plus a 1 MΩ scope probe.

**Measurement.** Step Δ in 10 µV increments, settling 10 ms each.
- Record the falling trip (output high → low, IN+ falling through IN−). This is the OCP direction.
- Record the rising trip. VIO is the midpoint and VHYST the difference.
- The falling trip is the acceptance quantity.

**Conditions.**
- Case temperatures 25, 85, 105 and 125 °C, using a thermal-stream head with a thermocouple on the package and 5 min soak.
- VCC 4.89, 5.00, 5.11 and 5.50 V.
- VCM at VCC/2, at 1.0185 V (B′) and at 1.2037 V (as built), with each VCM's own VCC/2 reference.
- At 125 °C and 5.11 V, also sweep VCM from 0.6 to 1.4 V in 50 mV steps, to locate the input-pair transition hot.

**Statistic.** Δ_i = Vtrip,fall(VCM_trip) − Vtrip,fall(VCC/2), at the same unit, VCC and temperature. Take the adverse sign, the one that lowers the trip current.

**Measurement uncertainty.** U_meas = 0.03 mV: DMM, thermal EMF and fixture leakage. This is a budget, to be confirmed with a shorted-input run.

**Pass**, at each temperature ≥ 105 °C and each VCC:
- every unit's Δ ≤ limit; and
- mean + k·s ≤ limit, with k = **3.064** (one-sided 99 % / 95 % normal tolerance at n = 30). For comparison, 95/95 is 2.220. A zero-failure nonparametric 95/95 would need n = 59.

| Design | Limit, c28 Q1 | Limit, c28 phys HOT5 | Limit, release Q1 | Largest σ that passes, if mean 0.1 mV |
|---|---:|---:|---:|---:|
| As built (VCM 1.20 V) | 0.305 mV | 0.095 mV | 0.935 mV | 0.067 mV (c28 Q1); none in the phys window |
| **B′ 1.02 V** | **2.164 mV** | **1.953 mV** | **2.821 mV** | **0.674 mV** |

**Also record:**
- VHYST (only typical on the datasheet; it raises the top);
- tPD at 20 mV overdrive and 125 °C;
- the transition location.

**Fail action.** If the transition hot sits above about 0.9 V, keep B′ at 1.02 V only if Δ(1.0185 V) still passes. Otherwise fall back to the as-built divider and the 17.5 A ceiling.

## 5. Recommendation

**Adopt B′-1.02 V and close S23 with the §4 bench run.**

**Changes** (BOM only, same SOT-23-5 U6 / U7 TLV3201):
- R33 → RT0603BRD077K5L (C728597)
- R34 → RT0603BRD0716KL (C326732)
- R35 → RT0603BRD0711KL (C728581)

**Band table for the build lane** (s48 B3 solve, Kelvin −2.41 A, Q1 HOT5):

| Network | R0 band before Kelvin | Low after (margin) | R1 low (margin) | R3 | R4 | Top / bank (R0) | Top / bank (R1) | OVP band (unchanged) |
|---|---|---|---|---|---|---|---|---|
| Release c17.5 @ 61 | 71.57–114.60 A | 69.16 (+4.99) | 66.51 (+2.34) | +4.47 | −4.28 | 114.60 / 1461 V | 117.34 / 1496 V | 272.60–287.485 V |
| c28 @ 55 | 70.42–116.04 A | 68.01 (+3.84) | 65.39 (+1.22) | +3.34 | −5.37 | 116.04 / 1480 V | 118.80 / 1515 V | 272.44–287.649 V |

**If the owner wants no bench work:**
- B′ still moves both networks from −0.72 / −1.97 A to +2.34 / +1.22 A on the review's own reading.
- That is enough to commission to 28 A on that basis, recorded as "R1-basis, unguaranteed".
- The as-built divider supports only about 27 A (S23).

**Rejected:**
- Option A: no part qualifies (§2).
- B upward: worse in every case (§3.1).
- C on the as-built divider: the limit is 0.305 mV, or 0.095 mV in the physical window. Fig 6-5's typical units already show about 0.3 mV over 1.2 → 2.75 V.

## 6. Things that did not match

1. **The s48 band in the records is the s47 solve.**
   - `kelvin_budget.BAND_BEFORE["native21s48"]` = (68.87, 117.45), commented "band network is unchanged". The c48 README and OPEN-ITEMS S23 then state "s48 band after Kelvin 66.46 A".
   - The committed bands47 engine on the s48 board's own B3 solve (runs and margins.json, 2b46d90e) gives **68.63–117.70 A**. The low after the Kelvin shift is **66.22 A (+2.05)**. At c28: 67.37–119.30 A, so **64.96 A (+0.79)**.
   - The network ran hotter at s48: R34 97.5 °C, R5 124.1 °C at release.
2. **The R1 numbers are worse on s48.** −0.72 / −1.97 A (Q1, with PSRR), against S23's −0.47 / −1.75 A (s47). In the physical HOT5 window: −1.54 / −2.78 A.
3. **The c28 network is the still-air solve.** In margins.json R5's element is 194.6 °C against a 170 °C limit (−24.6 K). The c28 band therefore uses an R5 temperature the board does not meet without the S24 airflow. With airflow it would be cooler, and the c28 band slightly better.
4. **There is no Q1 TLV3201 in DBV.** TLV3201-Q1 (SBOS856A) is SC70 only, at 6 mV.
5. **TLV3201 stock is thin.** JLC C105188 has 3221 for the 5 designators × 500 boards = 2500 (U6, U7, U10, U11, U12).
6. **Most ADI datasheets are not saved as PDFs.** analog.com blocks scripted downloads. MAX9140, MAX999 and LTC6752 are quoted from in-browser pdf.js text (`excerpt.txt`), not from a saved PDF.
