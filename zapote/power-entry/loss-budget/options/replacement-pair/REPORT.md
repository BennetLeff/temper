# Option 3: replacement MOSFET plus external gate driver

Research snapshot: 2026-09-17. Source revision: `80ae56830d9cc679b280736fde62461573bcafdd`. This is a bounded component and interface screen. It does not select a production part, alter the Atopile circuit, or claim a thermal or EMI result.

The arithmetic in the tables is reproducible with the standalone Rust source [`reproduce.rs`](reproduce.rs). It consumes the retained corrected-report switch-RMS moments as fixed inputs and computes only `I²R` and `Qg·V·f`; it does not duplicate the PFC solver. The source report SHA-256 is pinned in the program and below.

## Decision-shaped result

Two exact pairs remain technically plausible after checking the UCC28180 interface:

1. **IMZA65R048M1H + UCC27624DR**: lowest conduction screen of the two, Kelvin TO-247-4, but it needs a regulated **18 V** driver rail because Infineon recommends 18 V turn-on. The existing `AUX_15V_IN` is not enough. The UCC28180 GATE signal can drive the UCC27624 input directly after the existing 10 ohm damping resistor because the driver's input is rated to 26 V and has a low TTL threshold. The external driver then supplies 18 V to the MOSFET gate. This pair is conditional on adding and sequencing the 18 V rail and clamping the gate below 20 V.
2. **NTH4L060N065SC1 + UCC27524AD**: orderable 650 V Kelvin TO-247-4 SiC MOSFET with a 15 V datasheet RDS(on) test point and a 5 A/5 A driver. The existing 15 V bias can be used if its regulation and startup are proven; 15 V is within the MOSFET's specified -5 V to +18 V operating range, not a claimed recommended turn-on voltage. Its 74 nC gate charge is larger than IMZA's 33 nC, so a faster driver does not automatically make this pair lower loss. It is the more practical procurement experiment in this snapshot.

`C3M0060065K + UCC27524AD` was checked as a familiar reference alternative but is not retained as a leading pair: DigiKey showed zero stock and backorder, and its source point is 15 V/13.2 A at 400 V rather than the PFC waveform. It remains a technically plausible lab substitute if procurement accepts the lead time; the exact record is captured in the availability notes below rather than silently treating a zero-stock result as available.

## What the UCC28180 actually presents

The authored circuit connects `pfc.GATE -> 10 ohm -> q_boost.G`, with a 10 kohm gate pulldown. TI specifies UCC28180 GATE as a push-pull output with typical 1.5 A source and 2.0 A sink, a 15.2 V typical internal clamp, and a 11.2 V typical high at `VCC=12.2 V` (`10.8..12.0 V` in the table). The 15.2 V clamp is a typical value; the table's 20 V VCC high test point spans 14.5 V to 16.1 V. The output is held off during controller UVLO, and OVP disables GATE. There is no separate fault output on this 8-pin part.

The external buffer therefore receives a controller PWM signal, not a logic-domain 3.3 V guarantee. The interface must be measured for high level, rise/fall time, positive overshoot and negative ground-bounce at the driver input. The proposed TI drivers tolerate that signal with margin, but their EN pins default enabled through internal pullups. Hold EN low until the controller VCC is valid, or prove that the driver's input pulldown and the controller's UVLO behavior cannot produce a gate pulse during every startup, shutdown and fault sequence.

The output stage should be rewired as:

```text
UCC28180 GATE -- existing 10 ohm -- driver IN
driver OUT -- tuned gate resistor -- replacement MOSFET G
driver GND -- short Kelvin return -- MOSFET driver-source pin
MOSFET power-source pin -- high-current return -- shunt/control ground
```

The new SOIC-8 driver needs a 100 nF plus at least 1 uF local VDD bypass. The driver, bypass capacitors, gate resistor and MOSFET Kelvin source form the high-di/dt loop. The driver ground must not share the power-source copper before the Kelvin connection. The existing TO-247-3 footprint is insufficient for either replacement; both candidates are TO-247-4 parts with separate driver-source and power-source leads.

## Pair A — Infineon IMZA65R048M1H + TI UCC27624DR

Infineon's Rev 2.2 datasheet (2025-01-20) specifies 650 V, a PG-TO247-4 Kelvin package, 48 mOhm typical / 64 mOhm maximum at 25 C and 18 V/20.1 A, 67 mOhm typical at 175 C, `Qg=33 nC`, `Qgd=8 nC`, `R_G(int)=6 ohm`, and `Eoss=11.7 uJ` at 400 V. The operating range is -2 V to +20 V and the recommended turn-on voltage is **18 V**. The Infineon evaluation-board note shows this exact part with unipolar 18 V and 6.8 ohm on/off gate resistors at 16 A. Those values are a starting point, not a board qualification.

UCC27624DR is a dual non-inverting 5 A/5 A low-side driver. TI Rev E (SLUSE44E, revised 2026-03) specifies 4.5–26 V VDD, input operation -10–26 V, typical input thresholds 2.0/1.0 V with 1 V hysteresis, 4.1/3.8 V UVLO, 5/0.6 ohm typical pullup/pulldown resistance, and 6 ns/10 ns rise/fall at the stated 1.8 nF test load. Its input pulldown is about 120 kohm; EN is active high with an approximately 200 kohm internal pullup. The UCC28180 high-level signal is therefore inside the driver's input range, but the measured clamp/overshoot still has to be checked.

This pair needs an 18 V bias source for the driver output. Feeding the driver from the existing 15 V rail would be electrically inside UCC27624's range but below the MOSFET's recommended 18 V turn-on and would invalidate the selected RDS(on) conditions. Use a regulated 18 V source, enforce a gate clamp/overshoot limit below 20 V at the Kelvin source, and sequence EN. A unipolar 0/18 V output is consistent with the Infineon application note; a negative rail is not needed for this device but undershoot must remain above -2 V.

### Pair A loss screen

The only disjoint terms computed here are conduction and total gate-network charge. The CCM source moments are from the corrected Rust report at 180 uH and 15 A input; they are not measured waveform moments.

| Line | switch RMS | conduction, 25 C typ 48 mOhm | conduction, 25 C max 64 mOhm | conduction, 175 C typ 67 mOhm |
|---:|---:|---:|---:|---:|
| 108 V | 12.253 A | 7.207 W | 9.609 W | 10.060 W |
| 120 V | 11.909 A | 6.808 W | 9.077 W | 9.503 W |
| 132 V | 11.555 A | 6.409 W | 8.545 W | 8.946 W |

At 18 V and 129,107.392 Hz, `Qg*V*f` is `33 nC * 18 V * f = 0.076690 W`. That is gate-network energy, not an additional MOSFET die term; the driver supply current also carries this load and must not be double counted. Eoss at 389.615 V and turn-on/turn-off overlap are left null. The 400 V Eoss point and the datasheet curves do not support a bound at the PFC bus, and no measured PFC Eon/Eoff exists.

The 100 C and 125 C columns are intentionally null. The datasheet prints a 175 C typical value and a normalized curve; it does not provide a guaranteed 100/125 C point that can be substituted into a production loss claim. Read the curve or measure hot RDS(on) during the same switching test.

## Pair B — onsemi NTH4L060N065SC1 + TI UCC27524AD

onsemi's Rev 3 (2023-01) datasheet specifies the 650 V EliteSiC M2 TO-247-4LD, `RDS(on)=60 mOhm typ at 15 V/20 A/25 C`, 44 mOhm typ and 70 mOhm max at 18 V/20 A/25 C, 50 mOhm typ at 18 V/20 A/175 C, `Qg=74 nC`, `Qgd=23 nC`, `R_G=3.9 ohm`, and a specified operating range of -5 V to +18 V. The 15 V value is an RDS(on) test point, not a manufacturer-recommended turn-on voltage. It also gives a switching reference point of `Eon=45 uJ`, `Eoff=18 uJ` at 400 V, 20 A, -5/18 V, `RG=2.2 ohm`. That point is useful for a test-plan anchor; it is not the PFC loss because current, temperature, gate waveform and commutation differ.

UCC27524AD is a dual non-inverting 5 A/5 A SOIC-8 driver. Rev C (2024-06) specifies 4.5–18 V VDD, input operation -2–18 V (absolute -5–20 V), typical input thresholds 2.1/1.2 V with 0.9 V hysteresis, 4.2/3.9 V UVLO, 5/0.6 ohm typical pullup/pulldown resistance, and 7 ns rise/6 ns fall for the selected SOIC D package at the stated test load. EN is active high with an internal 200 kohm pullup; hold it low during controller and AUX startup. The existing 15 V bias is within both the driver's and MOSFET's specified VGS operating limits, but actual AUX regulation and gate overshoot remain unproven.

Start at 2.2 ohm at the MOSFET gate because that is the onsemi datasheet test condition, then sweep upward until VDS overshoot, VGS ringing and EMI are acceptable. The 10 ohm resistor on the UCC28180 side remains input damping; it is no longer the power-gate resistor. Keep a 10 kohm external gate pulldown at driver OUT/G.

### Pair B loss screen

| Line | switch RMS | conduction, 15 V/25 C typ 60 mOhm | conduction, 18 V/25 C typ 44 mOhm | conduction, 18 V/25 C max 70 mOhm | conduction, 18 V/175 C typ 50 mOhm |
|---:|---:|---:|---:|---:|---:|
| 108 V | 12.253 A | 9.009 W | 6.606 W | 10.510 W | 7.507 W |
| 120 V | 11.909 A | 8.510 W | 6.240 W | 9.928 W | 7.091 W |
| 132 V | 11.555 A | 8.011 W | 5.875 W | 9.346 W | 6.676 W |

Using the 15 V existing rail, the gate-network charge term is `74 nC * 15 V * f = 0.143309 W`. At 18 V it is 0.171971 W, but that 18 V number is a datasheet reference condition rather than the proposed Pair B operating point. The source switching point would equal `(45+18) uJ * 129,107.392 Hz = 8.133766 W` if it repeated at 20 A and 400 V every cycle; this is recorded as a conditional source point only and must not be added to an unknown PFC overlap or Eoss term. Eoss at 389.615 V, and 100/125 C conduction, remain null pending curve extraction or measurement.

## Availability and footprint impact

Distributor results were observed on 2026-09-17 through indexed DigiKey/Mouser pages and are **indicative cached observations**, not live allocation evidence:

| Item | Distributor observation | Interpretation |
|---|---|---|
| IMZA65R048M1HXKSA1 alias | Mouser: 42 in stock, $11.00 qty 1 | Recheck exact package/order suffix before BOM freeze |
| UCC27624DR | DigiKey: 1,038 in stock, $1.46 cut tape qty 1 | Recheck live |
| NTH4L060N065SC1 | DigiKey: 447 in stock, $12.83 qty 1 | Best procurement signal in this screen; recheck live |
| UCC27524AD | DigiKey: 5,212 in stock, $2.97 tube qty 1 | Recheck live |
| C3M0060065K | DigiKey: 0 in stock, $9.64 listed, backorder / 30 expected 2026-09-16 | Do not call available; retained only as a rejected procurement alternative |

Both pairs require an additional SOIC-8 placement, two local bypass capacitors, driver-to-gate resistor(s), and a TO-247-4 footprint. Pair A also requires an 18 V bias rail and a gate clamp/verification step. Pair B can use the present 15 V bias but still requires a new Kelvin-source routing and explicit EN sequencing. The Atopile source currently has no external producer for `AUX_15V_IN`; that missing supply is a system blocker for either pair's driver bias, even where its voltage is nominally compatible.

## Decisive qualification test

Build a daughterboard or controlled power-stage coupon first. Keep the UCC28180 regulation and current-sense network unchanged, drive the selected buffer from GATE, and instrument the driver's input, output, MOSFET VGS at the Kelvin source, VDS, and instantaneous boost current. A double-pulse sweep must cover the **measured instantaneous drain-current range at the switching instants**, including inductor ripple and line-phase peak; the 11.55/11.91/12.25 A values in the loss report are duty-weighted RMS planning moments and must not be used as the DPT current setpoint. Then run CCM PFC at 108/120/132 Vrms under the 15 A input ceiling. Repeat with controlled case/junction temperature states at 25, 100 and 125 C, recording the fixture thermal state and junction-temperature evidence separately.

Pass requires: no driver input/output absolute-maximum violation; no MOSFET VGS excursion outside the selected part's operating range; controlled VDS overshoot below the 650 V rating with measured ringing; reproducible Eon/Eoff separated from Eoss; no unintended pulse while either controller or driver is below UVLO; acceptable conducted/radiated EMI; and a thermal result using the real heatsink/copper path. Reject a faster setting when its overshoot or EMI erases the switching-loss gain. Only after these captures should the Rust loss model receive a source-bound Eon/Eoff or Eoss curve. There is no total-loss ranking between these pairs until the switching data is measured under applicable current, voltage, gate-bias, temperature and commutation conditions; the RDS(on)-only screen cannot be compared with the existing 136 W conditional switching estimate.

## Primary source register

| Source | Exact revision / pages used | URL | Content hash |
|---|---|---|---|
| TI UCC28180 | Rev D, SLUSBQ5D, pp. 6-7, 26 | https://www.ti.com/lit/ds/symlink/ucc28180.pdf | Existing retained local source hash `e1e1588c6854b43742a667c76df26f06d9ac51231f0176c43b2a46b63c1b00be` |
| Infineon IMZA65R048M1H | Rev 2.2, 2025-01-20, pp. 1, 5-7, 9-11 | https://www.infineon.com/dgdl/Infineon-IMZA65R048M1H-DataSheet-v02_01-EN.pdf?fileId=5546d4626f229553016f85d9ac090535 | Not captured: official host returned an empty body to curl; retain this gap explicitly |
| onsemi NTH4L060N065SC1 | Rev 3, 2023-01, pp. 1-2 | https://www.onsemi.com/download/data-sheet/pdf/nth4l060n065sc1-d.pdf | `e1063468f3c85e75c1830382be534ad8d7647d7f69ba8d4fe4c4dc31b004f8c4` (`sources/NTH4L060N065SC1-Rev3-2023-01.pdf`) |
| TI UCC27624 | Rev E, SLUSE44E, revised 2026-03, pp. 1, 4-8, 25-26 | https://www.ti.com/lit/ds/symlink/ucc27624.pdf | `b42590ddafb28a608aae30f5a2c333851cf11ded63daa03fbdef6df93ecb8a51` (`sources/UCC27624-RevE.pdf`) |
| TI UCC27524A | Rev C, 2024-06, pp. 3-7, 14-15, 23-25 | https://www.ti.com/lit/ds/symlink/ucc27524a.pdf | `29272e1d506b8755086380dad1481a7984f8bf0521be9fc2ae6e781866392def` (`sources/UCC27524A-RevC.pdf`) |
| Infineon KIT_1EDB_AUX_SiC note | Rev 1.0, Figure 4 / p. 18; 18 V unipolar, 6.8 ohm example for IMZA65R048M1H | https://www.infineon.com/assets/row/public/documents/24/42/infineon-evaluation-board-kit-1edb-aux-sic-applicationnotes-en.pdf?fileId=8ac78c8c82ce5664018345b4a28f2994 | Not captured: parsed web source did not expose PDF bytes |

The Infineon source-hash gap is deliberate and visible: the official host returned a zero-byte body in this environment, so no digest is fabricated. It must be closed by retaining exact official bytes and SHA-256 before Pair A is promoted to a frozen design input.
