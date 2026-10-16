# Band terms on s47: TLV3201 common mode, the Kelvin census, and the stacked bus event

Analysis only. PS = `ps-integrate/zapote/power-stage-120v` at HEAD `2f7241f61`, read only. Its `ledger.json` is
byte-identical to HEAD (sha256 `baf725f1…`). Every PS module was imported read-only (`dont_write_bytecode`), and no
PS `main()` that writes was called. `git status` on the ledger folder was clean after every run.

**Datasheets** were read with `pdftotext -layout` / `python3 -I`, plus 300 dpi page renders for the figures. Page
numbers are PDF pages and match the printed footers.

| File | Document | sha256 (first 16) |
|---|---|---|
| `runs-native21/s47/u3-dl/tlv3201.pdf` | TI SBOS561C (May 2024) | 1777bba814c74772 |
| `u3-dl/ca-is3720_v105_cn.pdf` / `ca-is372x_en.pdf` | Chipanalog v1.05 / v1.02 | d189c76c1fe68084 / de9f63ecb923fb2c |
| `u3-dl/amc1311.pdf`, `tps3700.pdf`, `tps709.pdf`, `sn74lvc1g10.pdf`, `sn74lvc1g17.pdf` | SBAS786C, SBVS187G, SBVS186H, SCES486E, SCES351Y | as in the S19/S20 review |
| `band-dl/30kpa/30KPA28A-30KPA320CA.pdf` | Good-Ark Doc.US30KPA28A-30KPA320CAxSM5.0 (Jan 2020), the fitted maker | 7700d2c23b98a681 (the ledger's) |
| `band-dl/30kpa-littelfuse/30KPA_littelfuse_lcsc_C19111562.pdf` | Littelfuse 30KPA series: the same 30KPA150CA row, second maker | 1fe25d7c0973063d |
| `band-dl/tdk-b3267x/MKP_B32674_678.pdf` | TDK B3267*D/G/J/T, 6/26, fetched 2026-10-16 | 9af4b66292b23461 (the ledger's) |

## Verdicts

1. **The 64.17 A OCP floor is not demonstrated.**
   - **The term is missing from the model.** The band model has no common-mode term: `thresholds.py` VIO is ±4 mV
     at VCM = VCC/2, and nothing in it depends on VCM or VCC.
   - **No datasheet number bounds it.** U6 trips at VCM 1.19–1.22 V, and VCC/2 is about 2.5 V. TLV3201 CMRR has a
     minimum only at 25 °C, and no curve guarantees VIO at that VCM over temperature.
   - **On the review's reading** (60 dB applied hot) the floor fails after the corrected Kelvin census:
     - −0.47 A on the release network;
     - **−1.75 A on the c28 network.** That is the coherent pairing for the 28 A rule.
   - **On TI's typical VOS-vs-VCM curve** it passes: +1.67 / +0.38 A.
   - **The failure direction is safe.** It is a nuisance trip, which latches safe.
   - **It does not bind at the shipping ceiling.** At 17.5 A the floor rule gives 43.7–52.3 A. On the release network
     readings R1–R3 keep ≥ 10 A of margin, and even the spec-literal 5.4 mV reading keeps ≥ 3.5 A.
   - **Governing rules.** For the 17.5 A release, the floor at 17.5 A governs. The 64.17 A rule governs the
     commissioning step to 28 A (DECISIONS 10 / 13), and it is now open for that step.
   - **OVP (U7, also a TLV3201):** VCM 2.32–2.35 V. It moves at most 0.03–0.05 V (top 287.65 V < 288.02 V). Only the
     spec-literal reading crosses 288.02 V (+0.09 / +0.27 V).
2. **Kelvin census:** 15.371 mA, 2.3056 mV, **trip shift −2.391 A**, against the committed 13.648 mA / −2.123 A.
   - The ISO7710 → CA-IS3720HW change alone accounts for −0.264 A.
   - The bound (all current at the maximum transfer) is −2.437 A.
   - **Band after the shift:** 66.48–117.45 A at release (+2.31 A over 64.17 A) and 65.18–119.09 A at c28 (+1.01 A).
3. **Stacked bus event, re-run on the current tank state.**
   - **The worst case is the CT-failed fault.** With the CT dead, the shunt OCP alone ends a tank overcurrent: trip
     ≤ 119.09 A, turn-off ≤ 155.7 A, tank energy at gate-off **0.897 J**.
   - **With the CT healthy:** trip ≤ 76.09 A, turn-off 110.2 A, 0.486 J.
   - **Shoot-through:** there is no gate-off protection for it (prevention only, DECISIONS 2026-10-05 item 3), and it
     returns no tank energy.
   - **The OVP delay is coherent.** The bus is 35.4 V over the band top at gate-off, but the line current has fallen
     to 25.95 A. The bus peak therefore rises only 7.7 V. Adding a flat 36 V double-counts.
   - **Stacked peak with no clamp: 512.4 V** (504.7 V without the OVP delay). It was 451.6 V.
   - **Per row:**

| Row (max ratio) | No clamp, 512.4 V | With D3 credit | Verdict |
|---|---:|---:|---|
| C12 / C13 / C19 / C20, 1 kV (0.5) | **0.512** | 0.489 at the published point, hot (0.40–0.44 on the V–I models) | **Pass only with clamp credit** |
| C5 / C6, VR 750 V (0.8) | 0.683 | — | Pass |
| C5 / C6 "hot", Vop 570 V at 105 °C (0.8) | **0.899** | 0.858 at the published point; 0.769 on the hot straight-line model (not published) | **Violation under the ledger's rule as written.** Pass on TDK's transient rating (0.599 of 1.5 × 570 V, p.14) and at the release case temperature (750 V) |
| C38–C41, 1000 / 687.5 V (0.8) | 0.512 / 0.745 | — | Pass |
| BR1, VRRM 1000 V (0.8) | 0.512 | — | Pass |
| 2EDR8259X barrier, VIORM 1767 V (0.5) | 0.290 | — | Pass |
| R3 / R4, 256.2 V against the 400 V overload (1.0) | 0.640 | — | Pass |
| D3 / D17 pulse power at the event, per device (1.0) | 0.81 (near-ideal-clamp bound, 27.7 kW against 34 kW); 0.45 on the V–I lines | | Pass |

**Gate on copies:**
- base: PASS (3 VERIFIED / 91 PARTIAL / 0 VIOLATION).
- `strict` (stresses re-based, every rule as written): **FAIL**. Two VIOLATIONs: CC1206JKNPOCBN102 and
  B32676G1905K000.
- `reformed` (the two rule decisions in §3.6): PASS (3 / 91 / 0).

---

## 1. TLV3201 common-mode term

### 1.1 Trip-node common mode (frozen netlist `native-21/frozen/default.net`)

| Comparator | Pins | Trip-node VCM (above GND = ocp_kelvin_p), every band vertex |
|---|---|---|
| U6 (OCP) | 1 OUT ocp_ok_hot, 2 GND ocp_kelvin_p, 3 IN+ ocp_node, 4 IN− ocp_thresh, 5 VCC hot5 | ocp_thresh = REF25 × R35/(R34+R35) = **1.1923–1.2152 V** |
| U7 (OVP) | 3 IN+ ovp_thresh, 4 IN− vsense_in, 2 / 5 as U6 | ovp_thresh = REF25 × R37/(R36+R37) = **2.3174–2.3493 V** |

- At the trip both inputs are at the threshold node. The ranges are the min / max over every vertex that
  `exact_corners` visits (`band_cmrr.py` records them).
- The comparator ground, R35.2, R37.2 and U5.2 all sit on `ocp_kelvin_p` within 2.3 mV of each other (the Kelvin plane,
  §2), which is negligible for VCM.
- VCC = HOT5. The Q1-grade guaranteed range is 4.89–5.11 V, so VCC/2 = 2.445–2.555 V. The physical window is
  4.632–5.5 V (the S19 review).
- **|VCM − VCC/2| at worst:** OCP 2.555 − 1.1925 = **1.3625 V** (1.5575 V in the physical window); OVP **0.2376 V**
  (0.4326 V).

### 1.2 What the datasheet guarantees (SBOS561C)

| Item | Text | Page |
|---|---|---|
| VIO, TLV3201 | "VCM = VCC / 2": 1 typ, 3 max mV; "TA = –40 °C to 125 °C": 4 mV max | 6.5 p.5 (VCC 5 V); 6.7 p.6 (VCC 2.7 V) |
| CMRR | "–0.2V < VCM < 5.2V": 60 min, 70 typ dB (VCC 5 V); "–0.2V < VCM < 2.9V": 56 / 68 dB (VCC 2.7 V) | 6.5 p.5; 6.7 p.6 |
| Table condition | "at TA = 25 °C and VCC = 5V (unless otherwise noted)". The CMRR row has **no** TA −40..125 °C line; VIO, IIB, IIO, VCM range, VOL / VOH and IQ do | p.5 |
| PSRR | 65 min dB, "VCM = VCC / 2, VCC = 2.5V to 5.5V" | p.5 |
| Hysteresis | 1.2 mV, typical only | p.5 |
| Fig. 6-5, VOS vs VCM, VCC 5.5 V (Fig. 6-4: 2.7 V) | 5 typical units at 25 °C. Flat from about 0.6 V to about 4.5 V. Steps of up to about 2.4 mV near 0.5 V and VCC − 0.7 V: the input-pair transitions, which set the CMRR spec. Between VCM 1.2 V and 2.75 V each unit moves ≤ 0.3 mV (read by eye) | p.7 |
| Fig. 6-7, CMRR vs temperature, typical | VCC 5 V: 74.5 dB at 25 °C, 73.5 at 75 °C, 70 at 95 °C, 67 at 110 °C, 64.5 at 125 °C. VCC 2.7 V: 68 → 60.5 dB (read by eye) | p.8 |

- **No over-temperature CMRR minimum exists.**
- **No guaranteed VIO exists at any VCM ≠ VCC/2 over temperature.** The only guaranteed CMRR figure is a 25 °C ratio
  over the whole −0.2..5.2 V range.

### 1.3 Is it already in the band model?

**No.** `round3/thresholds.py`:
- `exact_corners` sweeps `vos ∈ (−0.004, 0.004)` ("TLV3201_4mV … SBOS561C pp.5-6") plus `input_bias_v` (5 nA × source
  resistance).
- `thresholds()` has no VCM or VCC argument.
- `bands47.py` inherits this unchanged.

So the ±4 mV is the VCM = VCC/2 figure only. The PSRR and hysteresis terms are not in the model either.

### 1.4 Arithmetic (`scripts/band_cmrr.py`)

**Method.**
- **Sensitivity:** dI_trip/dVOS = (1 + R33/R32)/R5 = 2 A/mV.
- **Per vertex:** each vertex gets an adverse offset of k × |VCM(vertex) − VCC/2|, at the HOT5 corner farther from
  VCM, plus the PSRR term 10^(−65/20) × (HOT5 − 5 V) above 5 V.
- **Engine:** the bands47 engine on the solved B3 network.
- **Controls:** the controls reproduce bands-s47 (68.87–117.45 A, 272.64–287.45 V at release; 67.57–119.09 A,
  272.47–287.62 V at c28).

**Readings** (none is a guarantee at temperature):

| Reading | k | Basis |
|---|---|---|
| R1 | 1.000 mV/V | 60 dB min applied hot, linear in VCM (the review's term) |
| R2 | 1.48 mV/V at U6 88.5 °C; 2.06 mV/V at 103.9 °C | R1 less Fig. 6-7's typical fall (74.5 → 71.1 / 68.2 dB) |
| R3 | 0.19 mV/V | Fig. 6-5 typical mid-range: 0.3 mV over 1.2 → 2.75 V |
| R4 | flat 5.4 mV | Spec-literal: 5.4 V range × 10^−3 |

**OCP low corner, Q1 HOT5 window, PSRR on.** "After" uses the corrected Kelvin census, −2.391 A (§2); the value with
the committed −2.123 A is in brackets.

| Network | R0 (no CM) | R1 (review) | R2 | R3 (typical) | R4 (literal) |
|---|---:|---:|---:|---:|---:|
| Release c17.5 @ 61: term (mV) | 0.062 | 1.424 | 2.067 | 0.326 | 5.462 |
| Release: band before Kelvin (A) | 68.75–117.58 | 66.09–120.33 | 64.84–121.62 | 68.23–118.11 | 58.16–128.60 |
| Release: low after (margin to 64.17) | 66.35 (+2.18) | **63.70 (−0.47)** [63.97, −0.20] | 62.44 (−1.73) | 65.84 (+1.67) | 55.77 (−8.40) |
| c28 @ 55: low after (margin) | 65.06 (+0.89) | **62.42 (−1.75)** [62.69, −1.48] | 59.61 (−4.56) | 64.55 (+0.38) | 54.53 (−9.64) |
| c28: top (A) | 119.21 | **121.98** | 124.91 | 119.75 | 130.29 |

**Notes:**
- The bracketed R1 values reproduce the review's −0.19 / −1.47 A.
- In the physical HOT5 window (to 5.5 V), R1 gives −1.28 A (release) and −2.56 A (c28).

**OVP (U7) under R1 + PSRR:**
- Top: 287.478 V at release, 287.652 V at c28; physical window 287.529 / 287.703 V. All are under 288.02 V.
- Low corner: ≥ 272.39 V, above 269.37 V.
- R4 gives 288.112 / 288.287 V, over 288.02 V by 0.09 / 0.27 V.

**Hysteresis** (1.2 mV typical; Fig. 8-3 p.13 puts the trip points at VTH + VOS ± VHYST):
- It raises both trip points and never lowers the OCP low corner.
- The OCP top moves +1.2..2.4 A typical. The OVP top moves +0.07..0.15 V, which still clears 288.02 V.

### 1.5 Which floor governs (`scripts/floor_ceiling.py`)

**Rule:** floor = envelope peak + coil-pickup stack + 2 A (stage-15 PLAN §1, DECISIONS 13).

**Envelope peak at 17.5 A.** Round 6 has no 17.5 A row. The pk/RMS ratio, fitted linearly over the 22–30 A rows of
`board-side-protection.csv`, gives 2.211 at 17.5 A, so the peak is **38.70 A**. The firmware peak trip is 2.17 × 17.5 +
3 = 40.975 A (DECISIONS 61).

**Pickup.** The 28 A values bound 17.5 A, because I_pk·f is lower there.

| Basis | Floor at 28 A | 17.5 A, envelope | 17.5 A, firmware trip |
|---|---:|---:|---:|
| Pickup A, 3.00 A (DECISIONS 9 as written) | **64.17** | 43.70 | 45.98 |
| Pickup B, 3.99 A | 65.16 | 44.69 | 46.97 |
| Pickup C, 9.31 A | 70.48 | 50.01 | 52.29 |

**Margins at 17.5 A (census Kelvin):**
- Basis A: R1 +20.0 A at release / +18.7 A at c28; R2 +18.7 / +15.9 A; R4 +12.1 / +10.8 A.
- Worst case (pickup C, firmware trip): R4 +3.5 / +2.2 A.

**What R1 supports.** Inverting the floor rule, the R1 band supports a ceiling of about 27.7 A on the release network
and about 27.1 A on the c28 network.

**Reading.** The 64.17 A rule pairs the 28 A envelope with the release network temperature, which is a mixed basis. The
coherent 28 A case is the c28 network, where R1 gives −1.75 A.
- At the 17.5 A shipping ceiling nothing is violated under any reading.
- Before the ceiling rises above about 27 A, U6's VIO needs a guaranteed basis at VCM 1.2 V and 105 °C. Options:
  - a bench measurement of U6 at VCM 1.2 V, hot;
  - a comparator whose VOS is specified over its CM range and temperature;
  - re-centring the trip common mode toward VCC/2.
- **Retuning R34 is not free.** 12.7 k fixes the floor, but the stage-15 PLAN showed the bank going over 1600 V in the
  CT-failed fault.

## 2. Kelvin census (`scripts/kelvin_census.py` → `results/kelvin_census.md`)

**Method and controls.**
- **Membership** comes from the netlist: every node on `ocp_kelvin_p` (31), and every HOT5 consumer (whose current
  returns through it). The script asserts that every non-capacitor member is counted.
- **Transfers** come from `kelvin/plane-native21s47.json` (board 63aba33f, sink R5.2, probe R35.2, 125 °C copper):
  148.75–152.90 mΩ, and −1.037 A/mV.
- **Control:** the committed `CENSUS21` reproduces `budget-native21s47.json` (2.0469 mV, −2.123 A).

| Pad | mA max | mV at R35.2 | Datasheet basis |
|---|---:|---:|---|
| U4.4 (GND1) | 9.700 | 1.4550 | AMC1311B IDD1 9.7 mA, 4.5 < VDD1 < 5.5 V, SHTDN low (SBAS786C 6.10 p.11); SHTDN pull ≤ 70 µA is inside it |
| **U9.1 / U9.7 (GNDA)** | **4.100** | **0.6150** | **CA-IS3720H IDDA 4.1 mA, "VIN = 0V (CA-IS3720H)"**: the healthy state, with bus_fault_hot low. 5 V ±10 %, TA −40..125 °C (v1.05 7.9.1 p.11; EN v1.02 p.11). Was the ISO7710's 2.4 mA. The INA pull-up current (IIL ≤ 20 µA, p.10) is inside this test and returns at U8.2 |
| U14.2, R50 pull-up | 0.530 | 0.0789 | 10 k from 5.25 V. Only while OUTA asserts on HOT5 UV (SBVS187G Table 1 p.10); 0 in normal running, a +0.08 A credit not taken |
| U5.2 | 0.379 | 0.0570 | R31 current at HOT5 5.25 V, VR min 2.4838 V (SNOS455H 5.6 p.7), less the two threshold strings. It still includes the R32 / R33 string (~0.13 mA), which actually returns via ocp_kelvin_n → R5.3 (conservative) |
| R30.2 | 0.213 | 0.0321 | Bus divider at 400 V, as committed. U4 IIB ±15 nA (p.10) is inside it |
| R35.2 | 0.104 | 0.0158 | R34 / R35 string at 2.5162 V. Now returned at its own pad (152.90 mΩ, the maximum) |
| U3.2 | 0.100 | 0.0149 | TPS70950 IGND over-bound, kept (2.25 µA max at 0 mA; 350 µA typ at 150 mA; SBVS186H 6.5 p.5) |
| U6.2 / U7.2 | 0.065 each | 0.0097 each | TLV3201 IQ 65 µA, −40..125 °C (SBOS561C 6.5 p.5) |
| R49.2 | 0.046 | 0.0069 | 105 k + 10 k UV divider |
| U8.2 | 0.010 + 0.015 | 0.0038 | LVC1G10 ICC 10 µA plus 3 × II 5 µA (SCES486E p.4) |
| R37.2 | 0.017 | 0.0025 | R36 / R37 string |
| U14.2, IDD | 0.013 | 0.0019 | TPS3700 IDD 13 µA at VDD 18 V (SBVS187G 6.5 p.6), from V15_LS |
| U15.3 | 0.010 + 0.005 | 0.0022 | LVC1G17 ICC 10 µA, II 5 µA (SCES351Y p.6) |
| **Total** | **15.371** | **2.3056** | **Trip shift −2.391 A** (committed −2.123; Δ −0.268 A, of which U9 is −0.264 A); bound −2.437 A |

**Not counted** (no DC return):
- 14 MLCCs on the net: nA-class insulation leakage.
- TLV3201 IIB ≤ 5 nA.
- TPS3700 I(INB−) ≤ 15 nA; OUTB is unloaded.

**HOT5 sensitivity:** at 5.5 V the shift is −2.402 A.

**Corrected band:**

| Network | Band | Margin to 64.17 A |
|---|---|---|
| Release | 66.48–117.45 A | +2.31 A (bound +2.26 A) |
| c28 | 65.18–119.09 A | +1.01 A (+0.96 A) |

`kelvin_budget.py` CENSUS row U9.1 should change to 4.1 mA, cited "CA-IS372x v1.05 7.9.1 p.11, IDDA, VIN = 0 V,
CA-IS3720H".

## 3. Stacked bus event (`scripts/bus_event.py` → `results/bus_event.md`)

### 3.1 Which protection ends an overcurrent, and at what current

**Method.** The committed bank-ov model is re-run (`bank_ov_double_fault.py`, imported):
- L 66.5 µH ±10 %, bank 0.50 µF ±10 %, R 0.05..1.6 Ω, 35 frequency offsets;
- buses 198 / 280 / 287.62 / 323.04 V;
- T_D 2.267 µs.

`run_trip` is copied unchanged except that it returns the signed (i, v_C) at gate-off, so tank energy =
½Li² + ½Cv². **Control:** 118.74 A on 198 / 280 V reproduces the committed maximum I_off of 155.4 A.

| Ending protection | Trip (A) | Max I_off (A) | Max tank energy at gate-off (J) | Worst run |
|---|---:|---:|---:|---|
| CT window U10 / U11 (CT healthy) | 76.09 | 110.2 | 0.486 | L max / C min, 323 V bus |
| **Shunt U6 (CT failed; firmware peak and RMS trips are blind too, bank-ov README)** | **119.09** | **155.7** | **0.897** | L max / C max, R 0.15, 280 V, 25.09 kHz: i −151.0 A, v_C 479 V |
| Shunt with the R1 CMRR top (Q1 / physical HOT5) | 121.98 / 122.83 | 159.7 / 161.0 | 0.946 / 0.964 | |

- **Shoot-through:** no gate-off claim covers it (495 A in about 55 ns, DECISIONS 2026-10-05 item 3; F1 / BR1
  sacrificial, item 22). It discharges the bus, returns no tank energy, and is not a bus-OV case.
- **No desaturation detection** exists in the source (`elec/src/*.ato`).
- **Turn-off current:** ½·L_max·I_off² at 155.7 A is 0.887 J. The bank-ov record's 0.884 J is the same figure at
  155.4 A. Using the 119.09 A threshold as the turn-off current would ignore the 2.267 µs growth, so it is not the
  worst case.

### 3.2 Closed form (r2-cost `bus_peak_no_clamp.py:17-22`)

**Inputs:** C 14.9 µF, Vs 198 V, 500 µH / 30 A, V0 287.62 V, no clamp. **Control:** E_t 0.475 J gives 451.6 V, the
ledger value.

| E_t | Vpk | C12 (0.5) | C5C6 (0.8) | C5C6 hot (0.8) | C38–41 hot | BR1 | 2EDR | R3R4 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 0.475 J (stale) | 451.6 | 0.452 | 0.602 | 0.792 | 0.657 | 0.452 | 0.256 | 0.565 |
| 0.486 J (CT top) | 453.0 | 0.453 | 0.604 | 0.795 | 0.659 | 0.453 | 0.256 | 0.566 |
| **0.897 J (119.09 A)** | **504.7** | **0.505** | 0.673 | **0.885** | 0.734 | 0.505 | 0.286 | 0.631 |
| 0.946 J (R1 top) | 510.7 | 0.511 | 0.681 | 0.896 | 0.743 | 0.511 | 0.289 | 0.638 |

### 3.3 OVP-delay overshoot

**Sense filter.** R_th = 4 × 470 k ∥ 15.8 k, with C27 C0603C102J5GACTU (1 nF C0G ±5 %;
`power_stage_120v.ato:513-516`, designator :1016).
- Nominal: 15.668 kΩ, τ 15.67 µs.
- Maximum (R +1 % / +0.1 %, C +5 %): 15.685 kΩ, **τ 16.47 µs**.

**Chain:** T_D 2.267 µs.

**dV/dt at the band top** with the 30 A line current: 30 / 14.9 µF = **2.013 V/µs**.
- **Naive** (30 A held flat for τ + T_D): 2.013 × 18.74 = **37.8 V** (36.3 V nominal).
- **Coherent** (the line ring through the filter, simulated):
  - Filter lag 16.53 µs; gate-off at **V0' 323.04 V, I0' 25.95 A**, so the overshoot is **35.4 V** (34.1 V nominal).
  - The line current decelerates at (V − Vs)/L.
  - The ring alone, with no tank energy, peaks at 393.5 V wherever the gate goes off.

**Stacked, coherent** (closed form from (V0', I0'), τ max):
- 0.475 J: 457.9 V (C5 / C6 hot 0.803).
- 0.486 J (CT top): 459.3 V (0.806).
- **0.897 J: 512.4 V** (C12 0.512, C5 / C6 hot 0.899).
- 0.946 J: 518.4 V.

The naive stack would give 525.7 V for 0.897 J. **The delay is worth +7.7 V at the peak, not +36 V.**

### 3.4 Time-domain gate-off, with and without D3

**Model.** Starting from the 0.897 J state: tank through the body diodes into 14.9 µF, the line ring, and the clamp
(2 ns step).

**Clamp V–I.** Good-Ark gives only:
- VBR min 167.6 V at 5 mA;
- VC max 233.4 V at IPP 129.8 A (10/1000 µs, per device, 25 °C, p.3);
- the Fig. 1 derating (linear to 0 at 175 °C) and the Fig. 4 Ppk-vs-td curve (p.4).

It gives no V–I curve, no VBR max and no tempco. The Littelfuse sheet's identical 30KPA150CA row gives VBR max 184.36 V
(p.2) and a typical αT of 0.1 %/K (p.1).

**Results** (OVP-delayed start; the V0 287.62 V start is within 1.5 V):

| Clamp model | Vbus pk (V) | Clamp I pk (A) | Clamp E (J, string) | Time above half peak (µs) | Per-device P / Fig. 4 (exp / rect 0.66), derated to 68 % at 73 °C |
|---|---:|---:|---:|---:|---|
| None | 505.7 | — | — | — | — |
| Line from VBR min 335.2 V to 466.8 V @ 129.8 A | 407.9 | 71.7 | 1.10 | 42.0 | 0.24 / 0.36 |
| Line from VBR max 368.7 V to 466.8 V | 422.8 | 71.6 | 0.92 | 31.9 | 0.22 / 0.34 |
| The same line hot, × 1.048 (73 °C, typical αT) | 438.4 | 65.7 | 0.79 | 25.0 | 0.19 / 0.29 |
| Near-ideal 323 V (VBR min at −10 °C): bounds the clamp current | 331.4 | 167.1 | 1.29 | 25.7 | 0.38 / 0.57 (27.7 kW: 0.81 of the ledger's 34 kW rating) |

**Published bound with clamp credit.**
- On every V–I line through the published points the clamp current is 62–74 A, at or below IPP 129.8 A. A stiffer clamp
  holds the bus lower.
- So **Vbus ≤ VC max 466.8 V** at 25 °C, and 489.2 V at 73 °C with the typical tempco.
- **C12 at 489.2 V: 0.489.** This holds for any tempco ≤ 0.148 %/K.
- **C5 / C6 hot: 0.858**, and 0.819 at 25 °C.

**D3's own ratings hold.**
- At most 0.67 J per device.
- Pulse power ≤ 0.81 of the ledger's derated 34 kW rectangular rating (near-ideal bound), and about 0.45 on the V–I
  lines.
- IPP is exceeded only by the non-physical near-ideal clamp, and only at a 26 µs pulse that Fig. 4 covers (rect 0.57).

### 3.5 Rows (stress 512.4 V; see the verdict table at the top)

**Margins:**
- **C12 family:** over 0.5 by 12.4 V with no clamp. With D3 at its published point (hot) it is 10.8 V under.
- **C5 / C6 hot:** 456 V is exceeded by 56 V with no clamp and by 33 V at the published D3 point. It holds only on the
  straight-line V–I (438 V hot). The ALT-D3 §5 bench test T1 (inductor dump into 5.8 µF at 286 V, 115 / 160 A) measures
  exactly this.
- **TDK p.14 NOTE 1** permits 1.5 × VR for 30 ms, 1000 times per life. Taken on the 105 °C derated Vop (p.13: 1.2 %/°C
  from 85 °C), that is 855 V, so the < 0.3 ms event is 0.599 of it.
- **The release-case C5 temperature** is 83.6 °C (ledger row), at which the continuous VR 750 V applies: 0.683.
- **The 520 V die-VDS screen:** 512.4 V with no clamp (518.4 V on the R1 top) is just under it. With typical hysteresis
  on the top as well, it is about 524 V; with D3 credit, ≤ 489 V.

### 3.6 Ledger patch (`scripts/ledger_event.py`, run on copies)

**Both variants:**
- Re-base the stress in all seven entries: 451.6 → 512.4 V, and R3 / R4 225.8 → 256.2 V.
- Condition text names E_t 0.897 J, the OVP-delayed (V0', I0') and τ.
- Evidence cites committed paths: bank_ov_double_fault.py, bus_peak_no_clamp.py:17-22, bands-s47.md:24,
  fault_check.py, power_stage_120v.ato:505-516.
- Add D3's "Pulse power, gate-off event" check (0.814).

**Variant `strict`:** C12 / C13 / C19 / C20 and C5 / C6 become **VIOLATION**. **Gate FAIL**
(`results/gate-report-strict.json`).

**Variant `reformed`:** two decisions for the integrator (proposed DECISIONS text below). **Gate PASS.**
- **C12 family:** new violation-severity check "bus worst with D3" at 489.2 V (0.489). The no-clamp check becomes a
  gap (0.512), plus a bench gap.
- **C5 / C6:** new rating "Transient overvoltage at 105 C (1.5 x Vop, 30 ms, 1000 per life)" = 855 V (TDK p.14
  NOTE 1, p.13), with check "Vbus event vs transient rating" (0.599, max 0.8). "Vbus worst hot" becomes a gap (0.899),
  plus a bench gap that counts events over life (≤ 1000).

**Diffs:** `results/ledger_event-{strict,reformed}.diff`. The script refuses to re-patch its own output.

**Re-run on the newer HEAD.** During the analysis PS HEAD moved to `8d4fbf7f0`, which brought S21 temperature ratings
for 73 lines (ledger changed; none of the inputs above changed). The patch applies unchanged to that ledger (copies in
`*-8d4fbf7/`) with the same outcome:
- base PASS;
- strict FAIL, 2 VIOLATIONs;
- reformed PASS (3 VERIFIED / 91 PARTIAL / 0 VIOLATION).

**Landing.** Commit `scripts/` and `results/` into the unit (e.g.
`validation-results/11-candidates/s20-286v-recite/band-terms/`). Then re-run with `--landed <that folder>`, so the
evidence also cites `bus_event.py` / `bus_event.json`, and run `gate.py` and `tests/test_gate.py`.

**Proposed DECISIONS text (reformed):**
> The stacked gate-off event is re-based to the s47 tank state: 512.4 V, no clamp. D3 / D17 are fitted and published
> to 466.8 V at 129.8 A, so the C12 family's 50 % rule is held with D3 credit (489.2 V hot). C5 / C6 are held to TDK's
> transient overvoltage allowance for the sub-millisecond event, and keep the continuous-Vop screen as a bench gap.
> Reverses if: ALT-D3 §5 T1 shows the string over 456 V at 75 A / 73 °C, or the event count over life approaches 1000.

## 4. Files and reproduce

**Location:** `/Users/bennet/.claude/jobs/fbfc46b4/tmp/band-terms/`

**`scripts/`:** `netq.py` (netlist parser), `kelvin_census.py`, `band_cmrr.py`, `floor_ceiling.py`, `bus_event.py`,
`ledger_event.py`.

**`results/`:**
- `kelvin_census.{json,md}`, `band_cmrr.{json,md}`, `floor_ceiling.json`, `bus_event.{json,md,log}`;
- `ledger_event-{strict,reformed}.{json,diff}`, `gate-report-{base,strict,reformed}.json`.

**Ledger copies:** `base/ledger.json` (HEAD, sha `baf725f1…`), `strict/ledger.json`, `reformed/ledger.json`.

**Figure crops** (Figs. 6-5 / 6-7 at 300 dpi): `fig/`.

```sh
B=/Users/bennet/.claude/jobs/fbfc46b4/tmp/band-terms; U=/Users/bennet/Desktop/temper/worktrees/ps-integrate/zapote/power-stage-120v
cd /tmp
python3 -I $B/scripts/kelvin_census.py && python3 -I $B/scripts/band_cmrr.py && python3 -I $B/scripts/floor_ceiling.py
python3 -I $B/scripts/bus_event.py                      # ~8 s
for v in strict reformed; do
  python3 -I $B/scripts/ledger_event.py --src $B/base/ledger.json --out $B/$v/ledger.json --variant $v --json $B/results/ledger_event-$v.json
  python3 -I $U/native-21/verification/datasheet-ledger/gate.py --ledger $B/$v/ledger.json --root $U --report $B/results/gate-report-$v.json
done
```

**Limits:**
- R2 and R3 are typical-curve readings by eye.
- The clamp V–I lines are assumptions bracketed by the published points and by the second maker's VBR max.
- The time-domain model is lumped, with ideal diodes and no strays; it gives 505.7 V against the closed form's 512.4 V.
- The line source 500 µH / 30 A is the committed sensitivity, not a measured bound.
- The bridge's draw during the OVP delay is ignored, which only raises dV/dt.
