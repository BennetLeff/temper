# sensor-r3 PCB requirements: C1 pan-sensor channels

**What C1 uses.** C1 needs no new circuit type. It uses:
- the existing MAX31865 4-wire Pt100 channel;
- the rim-NTC channel on the zapote/controller board.

There is no heater and no pulse driver (P1).

**How the requirements are proved.** Each one is gated by
`checks.py` → `checks.json`; the gate names are in the right-hand column.
The decisions behind them are in `DECISIONS.md`, and the board changes in
`CHANGE-REQUEST.md`.

**Status.** All 11 gates pass for the proposed circuit.

## 1. Pt100 channel (MAX31865, 430 Ω Rref, 4-wire)

| # | Requirement | Proposed result | Gate |
|---|---|---|---|
| R1.1 | Range −20 to 320 °C, with Rref ratio headroom | R(320)/Rref_min = 0.511; bias ≤ 3.92 mA (limit 5.75); lead 1.80 Ω/conductor (limit 50) | 1a |
| R1.2 | Resolution ≤ 0.05 K | ≤ 0.037 K (LSB = Rref/2¹⁵ at 320 °C) | 1a |
| R1.3 | Front-end error ≤ ±0.3 K, 40–250 °C, after a single-point calibration, at worst-case Rref tolerance and tempco and a 0–85 °C board | Board-controlled terms 0.26 K linear; all terms 0.30 K RSS; strict linear 0.58 K (MAX31865 offset bound, `DECISIONS.md` D3) | 1b |
| R1.4 | Rref: 430 Ω, ≤ 0.05 %, **≤ 5 ppm/K**, thin film | Susumu RG2012V-431-W-T1 | 1b |
| R1.5 | Calibration: gain only, one 50 ppm reference resistor at 175.86 Ω (R(200 °C)) on J3, board at 25 °C. Firmware subtracts the fixed loading: R_true = R_meas − (7.86e-4·R_meas − 0.0331 Ω) | in `checks.json` info | 1b |
| R1.6 | Sample rate ≥ 16 Hz, continuous; VBIAS on continuously | 60 Hz notch, auto mode (CONFIG 0xC0): ≥ 56.8 Hz | 2 |
| R1.7 | Self-heating ≤ 0.1 K at h_c 888 (G_bond 0.0612 W/K, G_c 0.0403 W/K), or a firmware constant | 0.090 K worst (Pt film toward the disc); firmware constant 0.061 K, residual ±0.025 K | 3 |

## 2. Coil pickup and filtering

| # | Requirement | Proposed result | Gate |
|---|---|---|---|
| R2.1 | Pickup residual at RTDIN± < 1 LSB (39 µV), 20–100 kHz. Sources: pan injection (tank_cm × 2, 1.18 pF) and magnetic (20 mT eye, 1 mT harness). No credit for the sinc3 filter. | ≤ 0.11 LSB (captured: 779 LSB) | 4 |
| R2.2 | 1 V common mode at 40 kHz (150 Ω CDN at J3, tolerance corners) < 1 LSB | 0.51 LSB (2.45 LSB at 20 kHz, below the coil band) | 4 |
| R2.3 | Runaway-threshold shift from pickup ≤ 1 K | 0.03 K (captured: 44 K) | 4 |
| R2.4 | Open sense lead caught by hardware within 100 ms | S+ 33 ms, S− 13 ms | 4 |
| R2.5 | Sense filter, per line: 1.00 k, 0.1 % → 100 nF C0G across the pair → 1.00 k → 100 nF C0G across RTDIN± + 1 nF C0G to GND. No series R in FORCE±. | CR-1 | 4 |
| R2.6 | Wiring: (S+, S−), (F+, F−), (NTC, return) as twisted pairs. Pitch ≤ 5 mm in the post, harness lay ≤ 25 mm. Foil shield with drain at the controller SELV ground only (J12.3), never inside the coil eye. | cable and CAD | 4, 9 |

## 3. Fault detection

| # | Requirement | Proposed result | Gate |
|---|---|---|---|
| R3.1 | Every single fault is detected or reads high. Faults covered: open of each lead or of the element; shorts of each lead pair, of each lead to GND, and of each lead to the adjacent RIM_SENSE conductor; element short; +10 Ω on any contact. | Met. Exception: element-parallel leakage of 1–7 kΩ reads low | F |
| R3.2 | MAX31865 threshold registers: low = R(−40 °C) = 84.27 Ω, **word 12844**; high = R(360 °C) = 233.21 Ω, **word 35544** (today 1526 / 45722 = 10 / 300 Ω) | firmware | F |
| R3.3 | Hot-zone insulation between leads and across the element ≥ 10 MΩ at 300 °C (1.04 MΩ gives 0.1 K) | CAD | F |
| R3.4 | Manual fault-detection cycle only at power-up or with the coil off. Wait 5 ms between steps (input τ > 100 µs makes the automatic cycle invalid). | firmware | 2 |
| R3.5 | Stale data: read every 20 ms; a fault if the code doesn't change in 3 reads while the bias is on (DRDY is on TCA9555 P07) | firmware | 2 |

## 4. Rim NTC (Semitec 104GT-2, J12)

| # | Requirement | Proposed result | Gate |
|---|---|---|---|
| R4.1 | Resolution ≤ 0.3 K, 100–250 °C | ≤ 0.057 K (ADC1 GPIO9; ATTEN0 below 0.80 V, ATTEN2 below 1.55 V, otherwise ATTEN3) | 5 |
| R4.2 | Ratiometric correction | V_node / v3v3, with v3v3 from MCP3202 CH1 (LM4040A25) | 5 |
| R4.3 | Open detection | Saturated below 93 °C: a fault if the Pt100 estimate has been ≥ 150 °C for 600 s with the rim still saturated | 5 |
| R4.4 | Short detection | Node < 0.25 V → rim fault (this also catches an RTD lead shorted to RIM_SENSE) | 5, F |
| R4.5 | Plausibility threshold for "Pt100 below rim" | **25 K** (rim worst error 10.2 K at 250 °C) | 5 |
| R4.6 | ESD part on RIM_SENSE: stand-off ≥ v3v3 max (3.367 V) | ESD5Z5.0T1G (CR-6) | 9 |

## 5. Protection and insulation

| # | Requirement | Proposed result | Gate |
|---|---|---|---|
| R5.1 | IEC 61000-4-2 level 4 (±8 kV contact, ±15 kV air) at the cartridge connector as the design target. UL 858 / UL 60730 governs; the protective circuit may trip and must not be damaged or read unsafe. | ESD5Z3.3 on J3.1–4; 220 nF per pin holds the charge to 5.5 V / 10.2 V; MAX31865 pins are rated ±45 V | 6 |
| R5.2 | Protection leakage error | 0.017 K at 250 °C | 6 |
| R5.3 | Tank to cartridge/cable: reinforced insulation | Clearance ≥ 3.0 mm, creepage ≥ 8.0 mm, solid ≥ 2 mm (CAD G11) | 7 |

## 6. Hardware trips

| # | Requirement | Proposed result | Gate |
|---|---|---|---|
| R6.1 | RTD runaway (the only under-cap sensor in hardware): above 250 °C max setpoint + 5 K + 15 K, below 325 °C | 299.2–321.9 °C (divider referred to S−; captured with C1 leads: 237.5–316.3) | 8 |
| R6.2 | Rim trip ORed into RUNAWAY_FAULT, between 250 and 300 °C | 262.3–288.1 °C; bench precondition: T3 rim maximum ≤ 252 °C | 8 |

## 7. Cable, leads, connector (UL basis)

| # | Requirement | Part | Gate |
|---|---|---|---|
| R7.1 | Harness: 3 twisted pairs, FEP, ≥ 200 °C, ≥ 300 V, UL AWM | Alpha Wire 55493 (24 AWG, foil, UL AWM 20229, −80 to +200 °C). OD to confirm. | 9 |
| R7.2 | Pigtail: ≥ 260 °C | M22759/12-26 PTFE, nickel-plated copper, 600 V | 9 |
| R7.3 | First 20 mm of the Pt leads: low-k, low thermo-EMF against copper | Manganin Ø0.08: 1.71 Ω, 0.022 mW/K for four leads; 0.004 K at a 2 K splice difference (constantan: 0.092 K) | 9 |
| R7.4 | Inline connector, ≥ 105 °C, user-touchable side recessed | Molex Micro-Fit 3.0 43025-0600 (harness, female) / 43020-0600 (cartridge, male) | 9 |
