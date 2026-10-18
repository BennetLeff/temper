# Change request to zapote/controller: C1 pan-sensor channels (sensor-r3)

**From:** sensor-r3, PCB agent, 2026-10-14.
**To:** the controller owner (branch `controller-layout`, 300b8a934).

**What it rests on.**
- Evidence: `output/temper-sensor-r3/pcb/checks.py` → `checks.json` (all 11
  gates pass with these changes).
- Reasons: `DECISIONS.md` D1–D9.
- Nothing in the controller sources has been edited. The snippets below are
  proposals for you to merge.

## 1. Summary

| CR | Change | Why (numbers from `checks.json`) |
|---|---|---|
| CR-1 | New RTD block `RTDSensingC1` (an edited copy of `RTDSensing`). It adds a 2-pole sense filter, 220 nF + ESD5Z3.3 on each J3 pin, and 499 k pull-ups, window branch and low-window return on the connector side, plus 10 nF on the window node. | The captured channel sees 779 LSB of coil pickup and 44 K of ripple on the runaway threshold. Proposed: ≤ 0.11 LSB and 0.03 K. Open lead is caught in 33 ms (S+) and 13 ms (S−). Closes C29's deferral. |
| CR-2 | Rref back to **Susumu RG2012V-431-W-T1** (0.05 %, 5 ppm/K) for production | The C35 swap to RT 25 ppm costs 0.80 K at 250 °C on a 25 → 85 °C board. Proposed: 0.26 K for the board terms, 0.30 K RSS. |
| CR-3 | Runaway divider bottom (`r_runaway_bot.p2`) moves from selv_gnd to the RTD block's connector-side S− | With C1's 1.8 Ω manganin leads and the unspecified FORCE− switch (0.5–20 Ω), the captured band is 237.5–316.3 °C, which reaches below the 250 °C setpoint. Proposed: 299.2–321.9 °C. |
| CR-4 | J12 becomes a 3-pin B3B-XH-A: 1 RIM_SENSE, 2 GND (NTC return), 3 GND (harness drain) | The foil-shield drain lands at the controller only |
| CR-5 | Rim hardware trip: a TLV3201 on rim_filt vs v3v3·10k/96.6k, ORed with the RTD runaway into RUNAWAY_FAULT through an SN74LVC1G32 | Independent backstop for element-parallel leakage, which reads low and is electrically invisible. Band 262.3–288.1 °C. |
| CR-6 | `d_rim`: ESD5Z3.3T1G → **ESD5Z5.0T1G** | The node reaches 3.367 V, above the 3.3 V stand-off |
| CR-7 | Firmware constants (for the firmware owner) | §5 |

**Unchanged:**
- J3 pinout and footprint;
- the MAX31865 and its SPI;
- the window comparators' thresholds;
- RTD_DRDY on TCA9555 P07;
- GPIO9 rim channel and the ADC1 pattern;
- the interlock.

**Validator impact.** The RTD block's part census (36) and its
`zapote-rtd` contract change, so re-run the validator (C30). The
"byte-identical library copy" rule must move to `RTDSensingC1`.

## 2. Parts added or changed (exact part numbers)

| Ref (proposed name) | Qty | Value | MPN | Note |
|---|---|---|---|---|
| r_s1p, r_s1n, r_s2p, r_s2n | 4 | 1.00 kΩ 0.1 % 25 ppm 0603 | RT0603BRD071KL | already on BOM (rim pull-up) |
| c_s1 (between the mid nodes) | 1 | 100 nF C0G 50 V 1206 | GRM31C5C1H104JA01L | already on BOM (AD8436) |
| c_rtd_input (across RTDIN±) | 1 | 1 nF → **100 nF** C0G 50 V 1206 | GRM31C5C1H104JA01L | replaces C0603C102J5GACTU |
| c_cm_p, c_cm_n | 2 | 1 nF C0G 50 V 0603 | C0603C102J5GACTU | already in the RTD library |
| c_j_fp, c_j_sp, c_j_sn, c_j_fn | 4 | 220 nF X7R 50 V 0603 | CC0603KRX7R9BB224 | new value (Yageo CC family as CC0603KRX7R9BB104); check stock |
| d_j_fp, d_j_sp, d_j_sn, d_j_fn | 4 | ESD5Z3.3T1G | ESD5Z3.3T1G | already on BOM |
| r_rtdin_p_bias, r_rtdin_n_bias | 2 | 1 MΩ 5 % → **499 kΩ 1 %** | RC0603FR-07499KL | moved to the connector side |
| c_window | 1 | 10 nF C0G 50 V 0603 | GRM1885C1H103JA01D | window_rtdin_p to GND, τ 1 ms |
| r_ref | 1 | 430 Ω 0.05 % 5 ppm 0805 | RG2012V-431-W-T1 | CR-2 (the library's original part) |
| u_rim_trip | 1 | TLV3201 | TLV3201AIDBVR | on BOM |
| r_rim_th_top / r_rim_th_bot | 2 | 86.6 kΩ / 10.0 kΩ 0.1 % 25 ppm 0603 | RT0603BRD0786K6L / RT0603BRD0710KL | 86.6 k is new; check stock |
| c_rim_th | 1 | 100 nF X7R 0603 | CC0603KRX7R9BB104 | on BOM |
| u_runaway_or | 1 | SN74LVC1G32 | SN74LVC1G32DBVR | new component, same SOT-23-5 pinout as SN74LVC1G08 |
| c_runaway_or | 1 | 100 nF X7R 0603 | CC0603KRX7R9BB104 | on BOM |
| d_rim | 1 | ESD5Z5.0T1G | ESD5Z5.0T1G | CR-6, same SOD-523 footprint |
| J12 | 1 | B3B-XH-A(LF)(SN) | B3B-XH-A(LF)(SN) | CR-4, on BOM (J9) |

Net change: +22 parts (4 R, 9 C, 4 TVS, 2 thresholds, 1 comparator, 1 gate,
1 window C).

## 3. ato snippets

### 3a. `RTDSensingC1`: the changes against `RTDSensing` (modules.ato)

Copy `RTDSensing` to `RTDSensingC1` and make these edits. Everything not
shown stays as it is: MAX31865, REF2025, the window comparators, AND/NAND,
TPS3890, SPI resistors and the ferrite.

```ato
    # ---- sensor-r3 CR-1/CR-2: C1 cartridge front end ----------------------
    r_ref.value = 430ohm +/- 0.05%
    r_ref.mpn = "RG2012V-431-W-T1"              # 5 ppm/K (CR-2)

    # Connector-side sense nodes (J3.2 / J3.3) and filter mid nodes
    signal rtd_sense_p_ext
    signal rtd_sense_n_ext
    signal rtd_sense_p_mid
    signal rtd_sense_n_mid

    # J3 now lands on the connector-side nodes (pinout unchanged)
    j_rtd1.p1 ~ rtd_force_p
    j_rtd1.p2 ~ rtd_sense_p_ext
    j_rtd1.p3 ~ rtd_sense_n_ext
    j_rtd1.p4 ~ rtd_force_n
    # (delete: j_rtd1.p2 ~ rtd_sense_p ; j_rtd1.p3 ~ rtd_sense_n)

    # 2-pole differential filter, 1.00 k / 100 nF C0G / 1.00 k / 100 nF C0G
    r_s1p = new Resistor
    r_s1p.value = 1kohm +/- 0.1%
    r_s1p.mpn = "RT0603BRD071KL"
    rtd_sense_p_ext ~ r_s1p.p1; r_s1p.p2 ~ rtd_sense_p_mid
    r_s1n = new Resistor
    r_s1n.value = 1kohm +/- 0.1%
    r_s1n.mpn = "RT0603BRD071KL"
    rtd_sense_n_ext ~ r_s1n.p1; r_s1n.p2 ~ rtd_sense_n_mid
    c_s1 = new Capacitor
    c_s1.value = 100nF +/- 5%
    c_s1.dielectric = "C0G"
    c_s1.mpn = "GRM31C5C1H104JA01L"
    c_s1.footprint = "Capacitor_SMD:C_1206_3216Metric"
    rtd_sense_p_mid ~ c_s1.p1; c_s1.p2 ~ rtd_sense_n_mid
    r_s2p = new Resistor
    r_s2p.value = 1kohm +/- 0.1%
    r_s2p.mpn = "RT0603BRD071KL"
    rtd_sense_p_mid ~ r_s2p.p1; r_s2p.p2 ~ rtd_sense_p     # rtd_sense_p == adc.RTDIN_P
    r_s2n = new Resistor
    r_s2n.value = 1kohm +/- 0.1%
    r_s2n.mpn = "RT0603BRD071KL"
    rtd_sense_n_mid ~ r_s2n.p1; r_s2n.p2 ~ rtd_sense_n     # rtd_sense_n == adc.RTDIN_N

    # Across the converter pins: 100 nF C0G (was 1 nF), plus 1 nF C0G to GND per pin
    c_rtd_input.value = 100nF +/- 5%
    c_rtd_input.mpn = "GRM31C5C1H104JA01L"
    c_rtd_input.footprint = "Capacitor_SMD:C_1206_3216Metric"
    c_cm_p = new Capacitor
    c_cm_p.value = 1nF +/- 5%
    c_cm_p.dielectric = "C0G"
    c_cm_p.mpn = "C0603C102J5GACTU"
    adc.RTDIN_P ~ c_cm_p.p1; c_cm_p.p2 ~ power.gnd
    c_cm_n = new Capacitor
    c_cm_n.value = 1nF +/- 5%
    c_cm_n.dielectric = "C0G"
    c_cm_n.mpn = "C0603C102J5GACTU"
    adc.RTDIN_N ~ c_cm_n.p1; c_cm_n.p2 ~ power.gnd

    # Open-lead pull-ups: 499 k 1 %, on the connector side (no DC across the filter)
    r_rtdin_p_bias.value = 499kohm +/- 1%
    r_rtdin_p_bias.mpn = "RC0603FR-07499KL"
    rtd_sense_p_ext ~ r_rtdin_p_bias.p1          # (was adc.RTDIN_P)
    r_rtdin_n_bias.value = 499kohm +/- 1%
    r_rtdin_n_bias.mpn = "RC0603FR-07499KL"
    rtd_sense_n_ext ~ r_rtdin_n_bias.p1          # (was adc.RTDIN_N)

    # Window/runaway branch taps the connector side; 10 nF gives tau 1 ms
    rtd_sense_p_ext ~ r_window_sense_p.p1        # (was adc.RTDIN_P)
    c_window = new Capacitor
    c_window.value = 10nF +/- 5%
    c_window.dielectric = "C0G"
    c_window.mpn = "GRM1885C1H103JA01D"
    window_rtdin_p ~ c_window.p1; c_window.p2 ~ power.gnd
    r_low_bottom.p2 ~ rtd_sense_n_ext            # (was adc.RTDIN_N)

    # Cable-entry network on every J3 pin: 220 nF X7R + ESD5Z3.3 to GND
    c_j_fp = new Capacitor
    c_j_fp.value = 220nF +/- 10%
    c_j_fp.mpn = "CC0603KRX7R9BB224"
    rtd_force_p ~ c_j_fp.p1; c_j_fp.p2 ~ power.gnd
    c_j_sp = new Capacitor
    c_j_sp.value = 220nF +/- 10%
    c_j_sp.mpn = "CC0603KRX7R9BB224"
    rtd_sense_p_ext ~ c_j_sp.p1; c_j_sp.p2 ~ power.gnd
    c_j_sn = new Capacitor
    c_j_sn.value = 220nF +/- 10%
    c_j_sn.mpn = "CC0603KRX7R9BB224"
    rtd_sense_n_ext ~ c_j_sn.p1; c_j_sn.p2 ~ power.gnd
    c_j_fn = new Capacitor
    c_j_fn.value = 220nF +/- 10%
    c_j_fn.mpn = "CC0603KRX7R9BB224"
    rtd_force_n ~ c_j_fn.p1; c_j_fn.p2 ~ power.gnd
    d_j_fp = new EsdTvs3v3
    rtd_force_p ~ d_j_fp.K; d_j_fp.A ~ power.gnd
    d_j_sp = new EsdTvs3v3
    rtd_sense_p_ext ~ d_j_sp.K; d_j_sp.A ~ power.gnd
    d_j_sn = new EsdTvs3v3
    rtd_sense_n_ext ~ d_j_sn.K; d_j_sn.A ~ power.gnd
    d_j_fn = new EsdTvs3v3
    rtd_force_n ~ d_j_fn.K; d_j_fn.A ~ power.gnd
    # No series resistance in FORCE+/FORCE- (it would move the runaway trip).
```

**Layout rules for this block:**
- 220 nF and TVS within 3 mm of the J3 pads, each returned by its own via to
  selv_gnd.
- R1/C1/R2 laid out symmetrically, ending at the ADC pins; c_rtd_input stays
  within 3 mm of pins 10/11, as the C34 DRC requires.
- No digital traces under the filter.

### 3b. `controller.ato`

```ato
    rtd_pan = new RTDSensingC1                    # CR-1 (was RTDSensing)
    # (delete the C35 r_ref value/mpn override: RG2012V is in the block)

    # CR-3: runaway threshold referred to the connector-side S- (not GND)
    r_runaway_bot.p2 ~ rtd_pan.rtd_sense_n_ext    # (was selv_gnd)
    # u_runaway unchanged: INP ~ rtd_pan.window_rtdin_p, INN ~ runaway_th

    # CR-5: rim hardware trip, ORed into RUNAWAY_FAULT
    signal runaway_rtd
    signal rim_hot
    signal rim_trip_th
    u_runaway.OUT ~ runaway_rtd                   # (was runaway_fault)
    u_rim_trip = new TLV3201
    u_rim_trip.INP ~ rim_trip_th
    u_rim_trip.INN ~ rim_filt                     # high = rim NTC below threshold = hot
    u_rim_trip.OUT ~ rim_hot
    u_rim_trip.VCC ~ v3v3
    u_rim_trip.GND ~ selv_gnd
    r_rim_th_top = new Resistor
    r_rim_th_top.value = 86.6kohm +/- 0.1%
    r_rim_th_top.mpn = "RT0603BRD0786K6L"
    r_rim_th_top.p1 ~ v3v3; r_rim_th_top.p2 ~ rim_trip_th
    r_rim_th_bot = new Resistor
    r_rim_th_bot.value = 10kohm +/- 0.1%
    r_rim_th_bot.mpn = "RT0603BRD0710KL"
    r_rim_th_bot.p1 ~ rim_trip_th; r_rim_th_bot.p2 ~ selv_gnd
    c_rim_th = new Capacitor
    c_rim_th.value = 100nF +/- 10%
    c_rim_th.mpn = "CC0603KRX7R9BB104"
    c_rim_th.p1 ~ rim_trip_th; c_rim_th.p2 ~ selv_gnd
    u_runaway_or = new SN74LVC1G32
    u_runaway_or.A ~ runaway_rtd
    u_runaway_or.B ~ rim_hot
    u_runaway_or.Y ~ runaway_fault                # -> interlock.runaway_fault (unchanged)
    u_runaway_or.VCC ~ v3v3
    u_runaway_or.GND ~ selv_gnd
    c_runaway_or = new Capacitor
    c_runaway_or.value = 100nF +/- 10%
    c_runaway_or.mpn = "CC0603KRX7R9BB104"
    c_runaway_or.p1 ~ v3v3; c_runaway_or.p2 ~ selv_gnd

    # CR-4: J12 3-pin, drain on pin 3
    j_rim = new XhHeader3                         # (was XhHeader2)
    j_rim.designator = "J12"
    j_rim.p1 ~ rim_sense
    j_rim.p2 ~ selv_gnd
    j_rim.p3 ~ selv_gnd                           # harness foil drain, controller end only

    # CR-6: rim TVS stand-off above v3v3 max
    d_rim = new EsdTvs5v0                         # (was EsdTvs3v3)
```

### 3c. New components

These go in `components.ato` / `controller_parts.ato`.

```ato
component SN74LVC1G32:
    """Single two-input OR gate, Ioff partial-power-down (TI SCES219)."""
    footprint = "Package_TO_SOT_SMD:SOT-23-5"
    mpn = "SN74LVC1G32DBVR"
    manufacturer = "Texas Instruments"
    signal A ~ pin 1
    signal B ~ pin 2
    signal GND ~ pin 3
    signal Y ~ pin 4
    signal VCC ~ pin 5

component EsdTvs5v0:
    """onsemi ESD5Z5.0T1G, 5.0 V unidirectional TVS, SOD-523. Cathode = pin 1 (band)."""
    designator_prefix = "D"
    mpn = "ESD5Z5.0T1G"
    manufacturer = "onsemi"
    footprint = "Diode_SMD:D_SOD-523"
    signal K ~ pin 1
    signal A ~ pin 2
```

Verify the SN74LVC1G32 and ESD5Z5.0T1G pin tables against their datasheets
at capture. The 1G32's DBV pinout matches the 1G08 already in the library.

## 4. Cartridge cable and the 6-pin cartridge connector

**The chain:**
1. Cartridge: manganin leads (20 mm).
2. Splice block, potted.
3. Pigtail: M22759/12-26, three twisted pairs.
4. **Inline connector**, Molex Micro-Fit 3.0 2×3: plug 43020-0600 on the
   cartridge side, receptacle 43025-0600 (recessed female contacts) on the
   harness side.
5. Harness: Alpha Wire 55493, 3 pairs × 24 AWG, FEP/FEP, foil shield.
6. Controller J3 (XH 4-pin) and J12 (XH 3-pin).

| Micro-Fit pin | Net (`RTD_*` style) | Pair | Controller pin | MAX31865 / ADC |
|---|---|---|---|---|
| 1 | RTD_FORCE_P | B | J3.1 | FORCE+ |
| 2 | RTD_SENSE_P | A | J3.2 | RTDIN+ (via filter) |
| 3 | RIM_SENSE | C | J12.1 | GPIO9 via TLV9061 |
| 4 | RTD_FORCE_N | B | J3.4 | FORCE− |
| 5 | RTD_SENSE_N | A | J3.3 | RTDIN− (via filter) |
| 6 | RIM_RTN | C | J12.2 | selv_gnd |
| — | DRAIN (foil) | — | J12.3 | selv_gnd. Not carried through the inline connector; the shield stops at the harness end, outside the coil eye. |

**Pin plan.**
- Each pair sits in one column of the 2×3, so the pair stays adjacent through
  the connector: A = 2/5, B = 1/4, C = 3/6.
- The two RTD force pins are on the outer column.
- RIM_SENSE (3.3 V through 1 k) sits next to RTD_SENSE_P. A short between
  them reads high, or is caught by the hardware trips (fault check).

## 5. Firmware constants (CR-7, for the firmware owner)

| Item | Value |
|---|---|
| MAX31865 CONFIG | 0xC0 (VBIAS on, auto, 4-wire, 60 Hz notch); 0xC2 to clear faults |
| Low / high fault thresholds | word 12844 (84.27 Ω, −40 °C) / word 35544 (233.21 Ω, 360 °C); replace 1526 / 45722 |
| Loading correction | R_true = R_meas − (7.86e-4·R_meas − 0.0331 Ω) |
| Self-heating | subtract 0.061 K; never use it as a contact signal (P1) |
| Fault cycle | manual mode only; at power-up and with the coil off; ≥ 5 ms between steps |
| Read period / stale | 20 ms; a fault if the code doesn't change in 3 reads (DRDY on TCA9555 P07) |
| Rim ADC | ATTEN0 below 0.80 V, ATTEN2 below 1.55 V, otherwise ATTEN3; use V_node / v3v3, with v3v3 from MCP3202 CH1 |
| Rim faults | short: node < 0.25 V; open: saturated while the Pt100 estimate ≥ 150 °C for 600 s |
| Pt100-below-rim plausibility | 25 K (not 15 K) |

## 6. Acceptance on the bench

1. **Pickup (EM2/S3).** With a pan at 28 A, read the RTD standard deviation
   at a steady 200 °C with the coil on and with it off. The two must agree to
   within 1 LSB (0.037 K).
2. **Open-lead times.** Pull S+ and S− at 25 °C and at 250 °C. Hardware
   RTD_FAULT or RUNAWAY_FAULT must assert in ≤ 100 ms (model: 33 / 13 ms).
3. **Runaway trip.** Use a decade box at J3 with 0 and 20 Ω added in FORCE−.
   The trip must stay within 299–322 °C.
4. **Rim trip.** Log the rim under a 250 °C hold (T3). It must stay ≤ 252 °C;
   the trip band is 262–288 °C.
5. **ESD.** Apply ±8 kV contact and ±15 kV air at the harness receptacle. The
   circuit may trip, but no damage and no unsafe reading.
6. **Accuracy.** On three boards, run 0/25/85 °C board temperature against a
   175.86 Ω standard. The test also measures the MAX31865 offset drift, the
   one term that isn't datasheet-bounded.
