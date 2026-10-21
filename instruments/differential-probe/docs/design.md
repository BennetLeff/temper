# Circuit and assembly decisions (Rev C)

This page describes the Rev C circuit. The reasons for each change from Rev B, and the options rejected, are in the [Rev C record](revc.md). The Rev B version of this page is in git at `ca79d882f`. Its detailed calculations remain in [circuit-revb.md](circuit-revb.md).

## Signal path

### Divider

Each leg has 10 MΩ above its tap: five sections, each one 2 MΩ Uni-Royal HV121WF2004T4E (1%, ±100 ppm/°C, 1 W, 3000 V working) in parallel with one 33 pF / 3 kV NP0 (Yageo CC1812JKNPOEBN330). Stackpole HVCB2512BDE2M00 (0.1%, 25 ppm/°C, 2 W) is a drop-in upgrade; see [cost-down](cost-down.md) for the trade.

With `Rbottom = 10 MΩ / 1999 = 5002.501 Ω`, the DC attenuation is 2000:1. Matching time constants needs a total low-leg capacitance of 13.1934 nF, including component, clamp, buffer and layout capacitance. The ideal high-frequency input capacitance is about 6.6 pF.

### DC trim

R11/R31 are 4.87 kΩ, 0.1%, 25 ppm/°C (Yageo RT0603BRD074K87L). RV1/RV2 are 500 Ω 25-turn pots (Bourns 3296W-1-501LF) with the wiper tied to one end; the nominal setting is 132.501 Ω, at 20 Ω per turn.

All worst-direction corners of the 1% upper string and 0.1% bottom resistor need 77.606–187.396 Ω, inside the pot's usable 5–450 Ω (`tools/check.rs`). A 0.1% HVCB string needs 122.6–142.4 Ω, so the upgrade needs no trim change.

### Low-leg capacitance

The low leg is a fixed 10 nF 1% C0G (C41/C51), two select-on-test 1% C0G positions, and a GKG60015 12–60 pF top-adjust trimmer (CT1/CT2). The select-on-test positions are:

| Position | Nominal | Choose from (E24) |
|---|---|---|
| S1: C42/C52 | 3.0 nF | 1.8–3.9 nF |
| S2: C43/C53 | 160 pF | 0–360 pF |

Selection is two-stage, with a re-measurement before each choice. [`checks.txt`](../validation/checks.txt) records the no-gap proof over the archived −8.26/+4.20% requirement spread at worst-case part tolerance. Nominal parts leave 33.4 pF for the trimmer plus parasitics.

The trimmer rotor is tied to GND and the stator to the tap. Its N2200 ±800 ppm/°C temperature coefficient adds little because it is a small part of the total.

Adjusting the bank:

- **Fine adjustment** is through the lid holes. Use an insulated tool and low-voltage excitation, and withdraw the tool before reading.
- **S1/S2 changes** need the DUT disconnected and the enclosure opened.

The archived ladder model shows that one trimmer cannot correct arbitrary distributed parasitics across the band.

### Input buffers

U1 (OPA2810, one channel per leg) buffers each tap through 220 Ω, 1% (R12/R32) into its high-impedance input.

The JFET input stage holds to VS+ − 2.5 V typical (−3 V over temperature). That is about +1.8 V on the +4.8 V rail. The extended ±3 kV tip voltage puts ±1.5 V on the tap, inside that.

### Subtractor and ×5 stage

U3 channel 2 is the fixed ×2 subtractor. Its 499 Ω inputs are R61/R62; R63 (1 kΩ) is the reference arm and R65 (1 kΩ) the feedback. The gain is 2.004.

U12 (OPA810) is the noninverting ×5 stage: 499 Ω (R67) to ground and 2 kΩ (R68) feedback, giving 5.008. Both feedback networks stay connected in either range. R100 (49.9 Ω) isolates the fine-stage input from U3's output.

U12 is kept as a separate package because it is the stage that saturates in wide range (see [revc.md §4](revc.md#4-one-amplifier-family-opa2810--opa810)). Saturating the unused U12 changes the wide output by 16.8 nV in the vendor model. That model cannot represent inter-channel coupling.

### Range selection

SW1 (PCB-mount E-Switch 100SP1T1B5M7RE gold SPDT) selects WIDE_SEL (pin 1) or FINE_SEL (pin 3) onto SELECTED (pin 2). Each source has its own 49.9 Ω isolation resistor, and the selected signal feeds the common filter. R103 (1 MΩ) returns SELECTED to ground while the contacts are open.

Range selection does not open any feedback loop, but the changeover is not a valid measurement interval. Verify break-before-make behaviour and settling on the received switch.

### Output filter and driver

The filter has two poles, both from JLC Basic C0G parts:

- **First pole, before the driver.** R69 = 220 Ω ([fee consolidation](fee-consolidation.md), F3) and C61 = 47 pF C0G (Samsung CL21C470JBANNNC). With the selector's 49.9 Ω and the warning-divider load the source resistance is 269.77 Ω and the pole is 12.55 MHz.
- **Second pole, at the BNC.** C62 = 330 pF C0G (Samsung CL10C331JB8NNNC) shunts OUT, after R70 (49.9 Ω), to GND through the bridged solder jumper JP1. With the 1 m cable and scope input (lumped 120 pF) the pole is 7.09 MHz.

**Bandwidth jumper.** JP1 is closed by its copper bridge as built. Cutting the bridge removes C62 and gives the ~11 MHz mode; a solder blob restores it. The mode changes the 35–60 kHz phase by about 0.36°, so calibrate in the mode you measure in and record it.

The TI vendor model (full chain with a lumped divider, 1 MΩ ‖ 120 pF scope load; [`validation/spice/results.txt`](../validation/spice/results.txt)) gives:

| Range | JP1 | −3 dB | Phase at 60 kHz |
|---|---|---|---|
| Wide | bridged (default) | 5.768 MHz | −1.000° |
| Fine | bridged (default) | 5.273 MHz | −1.241° |
| Wide | cut | 10.856 MHz | −0.644° |
| Fine | cut | 8.471 MHz | −0.886° |

Neither range peaks in either mode. Calibrate each range separately. The study sweep ([`tools/output_filter_study.py`](../tools/output_filter_study.py), [`output-filter-study.txt`](../validation/spice/output-filter-study.txt)) reports 5.83 / 5.32 MHz for the same circuit because it takes the first grid point past −3 dB; `results.txt` interpolates.

**Noise.** The study integrates the vendor-model output noise and refers it to the tips (divide by the gain), over 10 Hz–200 MHz ("full band"), to 20 MHz and to 5 MHz, in mV rms:

| Filter | Range | Full band | To 20 MHz | To 5 MHz |
|---|---|---:|---:|---:|
| Before (C61 100 pF, no C62) | Wide | 373 | 143 | 72 |
| Before | Fine | 141 | 114 | 70 |
| **Now (C61 47 pF, C62 330 pF)** | Wide | **172** | 127 | 72 |
| **Now** | Fine | **116** | 109 | 71 |
| JP1 cut (C61 47 pF only) | Wide | 438 | 198 | 77 |
| JP1 cut | Fine | 198 | 158 | 76 |

**Finding: the driver's unfiltered noise tail dominated the full-band noise.** Before the change the only pole sat ahead of U3A, so U3A's own noise reached the BNC unfiltered up to its ~140 MHz bandwidth. Replacing U3A with an ideal buffer in the model drops the wide full-band figure from 373 to 157 mV; making U3B or U1 ideal instead changes it by only 10–18 mV (study section B). C62 after the driver filters that tail, which more than halves the wide full-band noise with the bandwidth unchanged. Below 5 MHz nothing changed (72 mV), because there the noise is the input stages' and the divider's. A scope's 20 MHz bandwidth limit already removed most of the tail; the change matters at full scope bandwidth.

These are model figures (ideal lumped divider, no layout parasitics, no cable transmission line), not measurements.

Loaded DC ratios are 1000.59:1 and 199.80:1 before calibration. U3 channel 1 is the unity-gain coax driver, and R70 is the 49.9 Ω series output resistor. Use the scope's 1 MΩ input: a 50 Ω termination roughly halves the signal and invalidates the calibration.

## Protection and indication

### Clamps

D1/D2 (BAV199 pairs) clamp the buffer inputs directly to the ±4.8 V rails. D3 clamps the output after R70. These are overload clamps, not precision limiters.

The worst single-fault clamp current (one bottom bank open, 3 kVpk at 60 kHz) is 7.5 mA peak. The minimum rail load is about 14.7 mA, so neither LDO output is back-driven.

The BAV199 forward voltage (about 0.9 V) exceeds the OPA2810's 0.5 V input-diode allowance, so the part's internal ESD diodes share some clamp current. R12/R32 keep the total below the 10 mA absolute maximum. Check this on the bench.

### Saturation of the unused stage

The fine range would need 7.5 V out for a 1.5 kV differential input, so U12 saturates first. In wide range, U12 can therefore be saturated while the selected output is valid.

### Warning comparators and thresholds

U5 (TLV1704) watches both buffered inputs in both polarities. U6 (TLV1702) watches SELECTED through the R71/R72 2:1 divider, so a saturated unused fine output does not by itself raise the output warning.

The TL431 references are gone. One ladder per polarity across the regulated rail sets both thresholds: 66.5 kΩ → LIM → 1 kΩ → OUT_LIM → 10 kΩ → GND. Their spread includes the rail tolerances (ADP7142 ±1.8%; ADP7182 ADJ −2.95/+1.97%) and 0.1% feedback resistors. The 66.5 kΩ and 10 kΩ ladder resistors are 0.1%; the 1 kΩ middle resistors (R88/R92) are 1% Basic parts, which costs 1.5 V on the per-tip bound ([fee consolidation](fee-consolidation.md), L1). `tools/budget.rs` takes each resistor's class from its MPN.

| Warning | Nominal | Conditional late-trip bound | Earliest trip |
|---|---|---|---|
| Per tip | 1,362.6 V | < 1,454.5 V | 1,266 V |
| Wide differential | 1,238.7 V | < 1,341.8 V | 1,132 V |
| Fine differential | 247.7 V | < 289.79 V | 206 V |

The budget holds only if all of these are true:

- Gain is at least 98% of nominal.
- Each buffer offset is within ±5 mV.
- The actual selected-path zero is within ±25 mV wide or ±130 mV fine.
- Both rails are inside their regulated range.

Scope zero subtraction does not remove an offset that the comparator sees.

### Latch

The open-drain comparator outputs (OV_N) drive Q1 and the CD4013 set input, and the LED stays on until reset (SW3, a thru-hole C&K PTS645 tactile switch pressed through a lid hole). This latch is an initial-envelope warning, not a fast protective trip: the comparators have roughly 560 ns typical delay.

### Trigger output (J4)

A second BNC, J4, gives the scope a trigger edge when the warning latches. It marks that the warning latched. **It is a trigger, not a peak-capture guarantee.**

- **Drive.** CD4013 flip-flop 2 (U7 pins 8–13) is set and reset with flip-flop 1: SET2 = SET, RESET2 = RESET, D2/CLK2 tied to −4.8 V. Its /Q2 output (TRIG_DRV) drives the base of Q3, an MMBT5401 PNP high-side switch, through R110 (22 kΩ). Q3 pulls TRIG_C to +4.8 V. R112 (470 Ω) feeds the BNC centre, R111 (10 kΩ) holds the output at 0 V when idle, and D10 (BAV199) clamps TRIG_C to GND and +4.8 V.
- **Isolation.** J4 connects only through R112 to TRIG_C. Nothing from the BNC reaches SET, RESET, OV_N or the comparators, so a shorted or back-driven trigger cable cannot disturb the warning LED. Pressing reset clears both flip-flops together.
- **Levels** (`validation/checks.txt`, worst-case rail and resistor corners): idle 0 V; latched 4.445–4.920 V into 1 MΩ and 0.418–0.484 V into 50 Ω. Set the scope trigger to a 2 V rising edge on a 1 MΩ input, or 0.25 V on 50 Ω.
- **Drive margin.** The Q3 base current is at least 0.355 mA. At the 11.1 mA short-circuit current that is a forced beta of 31 or less, against hFE ≥ 100. The CD4013 sinks at most 0.43 mA, against its 1.1 mA IOL at 0.5 V and 85 °C.
- **Abuse.** A shorted BNC puts at most 54 mW in R112 (125 mW rating). Continuous drive applied to J4 is tolerated from −7.5 V to +11.4 V. The negative limit is R112 power; the positive limit is current through D10 into +4.8 V staying below that rail's 14.7 mA minimum load, with no diode drop credited.
- **Latency estimate.** This is a charge-control estimate after the comparator output falls, using 25 °C datasheet maxima where they exist:

| Stage | Time |
|---|---|
| Q1 drives SET past 70 % VDD (base current ≥ 0.166 mA, Miller charge on Cob ≤ 6 pF at 10 V, Ceb assumed 30 pF) | 620 ns |
| CD4013 set to /Q plus output transition (VDD = 5 V maxima, slower than the 9.6 V used here) | 600 ns |
| Q3 turn-on (base current ≥ 0.355 mA) | 289 ns |
| Output to 90 % on 1 MΩ ∥ 122 pF through R112 | 134 ns |
| **Total** | **1.64 µs** |

The TLV1704 adds 460 ns typical tpHL before this; it has no maximum. The 30 pF Ceb is an assumption: twice the 15 pF maximum of the MMBT5401M3, because the SOT-23 datasheet gives none. So the total is an estimate, not a bound. Qualification measures it ([qualification.md §3](qualification.md)).

New parts and ratings (functional low-voltage circuit; no safety approval is claimed or needed for any of them):

| Ref | Part | Ratings used | Approval basis |
|---|---|---|---|
| J4 | Amphenol 031-5431-10RFX, as J3 | 50 Ω PCB right-angle bulkhead BNC | None (non-safety signal connector; same part as J3) |
| Q3 | JSCJ MMBT5401 (LCSC C8326), as Q1 | VCEO −150 V, IC −0.6 A, PC 0.3 W, hFE 100–300 at −10 mA, VCE(sat) ≤ 0.2 V at −10/−1 mA, fT ≥ 100 MHz | None |
| R110 | Uni-Royal 0805W8F2202T5E 22 kΩ (C17560, JLC Basic) | 1 %, 100 ppm/°C, 125 mW, 150 V | None |
| R111 | Yageo RT0805BRD0710KL 10 kΩ (already on the board) | 0.1 %, 25 ppm/°C, 125 mW | None |
| R112 | Uni-Royal 0805W8F4700T5E 470 Ω (C17710, JLC Basic) | 1 %, 100 ppm/°C, 125 mW, 150 V | None |
| D10 | Nexperia BAV199,215, as D1–D3 | 75 V continuous / 85 V repetitive reverse, 160 mA continuous forward, 4 A surge, ≤ 5 nA leakage at 75 V | None |

## Supply, grounding and assembly

### Batteries and regulators

Two 9 V batteries sit in PCB-mount MPD BH9VPC holders on the underside. They feed ADP7142/ADP7182 regulators through the PCB-mount silver-contact E-Switch 100DP1T1B1M7QEH power switch and SS14 reverse-polarity diodes. Nominal rails are +4.800 V and −4.807 V.

| | Typical current per rail |
|---|---|
| Amplifiers: four OPA2810 channels + one OPA810 | ~18 mA |
| Rev B for comparison | ~50 mA |
| Lit LED | about 0.8 mA extra |
| Latched trigger output (J4) | about 0.9 mA extra into 1 MΩ, up to 11 mA into 50 Ω or a short; 0 when idle |

Verify the actual current and the regulator temperature. There is no low-battery indicator: record both rails before and after measurements.

The 10 µF, 25 V, 1210 X7R regulator capacitors need an effective-capacitance check at bias. Each amplifier, comparator and latch supply has local 100 nF bypassing, with plane vias at each pin.

### Grounding

GND is the BNC shell, scope earth and enclosure. Battery power does **not** make this a galvanically isolated input. Keep the scope's protective earth intact. The grounded mounting holes H1/H2 and the two BNC shells bond the board to the enclosure at the output end.

### HV ladder ratings

At 3 kV DC on one tip, ideal leg dissipation is 0.90 W: 0.180 W and 600 V per 2 MΩ body. At 3 kV peak sinusoidal it is about 0.45 W per leg. At 60 kHz and 3 kV peak, 6.6 pF draws about 5.28 mArms. A 70 V/ns edge implies about 0.46 A of instantaneous displacement current before stray capacitance is added. None of these numbers replaces voltage-coefficient, temperature, transient-sharing or insulation qualification.

## Pin and footprint checks

Custom symbols use the selected package pinout, not a generic op-amp pinout:

| Part/package | Critical mapping |
|---|---|
| OPA2810, SOIC-8 | 1 OUT1, 2 −IN1, 3 +IN1, 4 −VS, 5 +IN2, 6 −IN2, 7 OUT2, 8 +VS |
| OPA810, SOIC-8 | 2 −IN, 3 +IN, 4 −VS, 6 OUT, 7 +VS; 1/5/8 NC |
| ADP7142, TSOT-5 | 1 VIN, 2 GND, 3 EN, 4 ADJ, 5 VOUT |
| ADP7182, TSOT-5 | 1 GND, 2 VIN, 3 EN, 4 ADJ, 5 VOUT |
| BAV199, SOT-23 | 1 outer anode, 2 outer cathode, 3 series junction |
| MMBT5401, SOT-23 | 1 B, 2 E, 3 C |
| CD4013B, SOIC-14 | flip-flop 2: 8 SET2, 9 D2, 10 RESET2, 11 CLK2, 12 /Q2, 13 Q2 |
| BH9VPC | 1 = +, 2 = − (MPD rev J PCB layout) |
| E-Switch 100 M7 DPDT | 2 and 5 common; 3 and 6 unused |

TI's two OPA2810 model files order their pins differently. The PSpice file used here is `IN+ IN- OUT VCC VEE`; the TINA file puts OUT last.

The BNC, toggle and holder footprints are generated from manufacturer dimensions in `tools/build.rs`. Their "MP" support pins carry no net.

The PTS645 reset switch (thru-hole, `SW_Tactile_CK_PTS645_THT`) has duplicate pad numbers 1 and 2 for its internally common terminals. Both RESET copies are joined by a track; both +4V8 copies connect to the In2 pour.

The pad-number audit finds missing or extra pad numbers. It does not certify land-pattern geometry; see [revc.md §7](revc.md#7-pcb-mount-panel-parts) for the dimensions still to confirm on samples.

## Reference sources

- [OPA2810](https://www.ti.com/lit/ds/symlink/opa2810.pdf) and its [PSpice model SBOMB66](https://www.ti.com/lit/zip/SBOMB66); [OPA810](https://www.ti.com/lit/ds/symlink/opa810.pdf).
- [ADP7142](https://www.analog.com/media/en/technical-documentation/data-sheets/ADP7142.pdf), [ADP7182](https://www.analog.com/media/en/technical-documentation/data-sheets/ADP7182.pdf).
- [TLV170x](https://www.ti.com/lit/ds/symlink/tlv1704.pdf), [CD4013B](https://www.ti.com/lit/ds/symlink/cd4013b.pdf), [BAV199](https://assets.nexperia.com/documents/data-sheet/BAV199.pdf).
- [Uni-Royal HV thick-film chip resistors](https://www.mouser.com/datasheet/2/1365/HighVoltageHV-2525183.pdf), [Yageo HV NP0 MLCC](https://www.yageo.com/upload/media/product/productsearch/datasheet/mlcc/UPY-HV_NP0_100V-to-5kV.pdf), [Stackpole HVC](https://www.seielect.com/Catalog/SEI-HVC.pdf) (drop-in upgrade), [RNCF](https://seielect.com/Catalog/SEI-RNCF.pdf), [Bourns 3296](https://www.bourns.com/docs/product-datasheets/3296.pdf).
- [E-Switch 100 series](https://www.e-switch.com/wp-content/uploads/2022/06/100.pdf), [Amphenol 031-5431-10RFX](https://www.amphenolrf.com/en-us/assets/file/4065791754/), [MPD BH9VPC](https://www.memoryprotectiondevices.com/datasheets/BH9VPC/BH9VPC-datasheet.pdf), [Hammond 1455N2201](https://www.hammfg.com/files/parts/pdf/1455N2201.pdf).
- [Altium differential probe project](https://resources.altium.com/p/differential-oscilloscope-probe-project): the architectural starting point; its attenuator is replaced.

Every other component link is in the generated BOM.
