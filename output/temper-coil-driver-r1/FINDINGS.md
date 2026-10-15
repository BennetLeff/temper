# Findings

**Tags:**
- **seen**: visible in the named frame under
  `~/temper-media/Sue70X7ZeS0/frames/` (`focus/best4k/`, `crops/`).
- **said**: in the transcript at the given timestamp.
- **patent**: US12712433B1 full text.
- **inferred**: our reading.
- **model**: computed by a script in this folder.

## Coil

| # | Finding | Basis |
|---|---|---|
| C1 | **Ferrite backing:** eight radial bars in an 8-spoke moulded carrier. Kapton- and RTV-tacked on the prototype; wide grey slabs in production. | seen `coil_f0971.25`, `coil_f0220.75` |
| C2 | **Bar geometry:** bars over r ≈ 37–108 mm, length ≈ 70 mm, width ≈ 23 mm (possibly two bars side by side). Carrier OD ≈ 262 mm, scaled from the "9-inch" winding OD. | model `measure_frames.json`, ±15–25 % |
| C3 | **Temper already matches:** spec rows 12 and 16 call for ≥ 8 bars, ≥ 20 mm wide, over r 32–118. | spec |
| C4 | **Turns and current:** about 10–12 turns at about 97 A rms (an upper bound, assuming unity power factor). Visible bundles are 3.5–4 mm wide, orange-served, at a 6–8 mm pitch. | inferred |
| C5 | **Two winding sections:** a circumferential rib suggests two, like the Control Freak and temper. | seen, inferred |
| C6 | **Coil NTC:** a clip-housed twisted-pair NTC on a spoke, the "UL-side" auxiliary sensor. | seen; said 15:37 |
| C7 | **Coil leads:** white silicone cables with crimped ring lugs. The termination process went from solder to hot bar to hot crimp. | said 16:37 |
| C8 | **Shield disc:** an aluminium disc under the coil-centre PCB, matching the patent's "second EMI shield" between coil and processor. | seen, patent |

## Coil-centre electronics

| # | Finding | Basis |
|---|---|---|
| E1 | **Arc board:** in production, a QFP MCU, a 12-pin board-to-board connector and a ribbon to the LED ring. The 2024 prototype had two RJ45-style jacks for the CAN daisy chain. | seen |
| E2 | **Sensor front-end daughterboard:** six sensor pads, barrier lines between channels, two SMD inductors and an SOIC-8, which suggests isolated or driven channels. | seen crop `coil_subboard_894` |
| E3 | **Local sensing:** sensing is done locally to reduce noise in the high-EMI region under the coil. | patent |
| E4 | **Certification split:** the certified per-burner MCU ("UL 6730", probably UL 60730) is separate from the OTA-updatable main computer. | said |

## Drive board

| # | Finding | Basis |
|---|---|---|
| D1 | **Heatsink:** a finned tunnel heatsink with internal fins and ducted lengthwise airflow. The TO-247s are clipped to its outer walls. | seen |
| D2 | **Device count:** about 16 TO-247 per board, so about two in parallel per switch position. | seen, inferred |
| D3 | **Mounting:** a screwed spring clip per device, with a white insulating wrap on the heatsink flank. | seen |
| D4 | **Bulk capacitors:** at least 8 polymer/hybrid electrolytics marked "160V". | seen |
| D5 | **Resonant bank:** three grey box film capacitors, about 34–40 mm, markings illegible; probably the resonant bank. | seen, inferred |
| D6 | **Coil terminals:** press-fit tapped blocks silkscreened "COIL". Temper already uses REDCUBE THR. | seen |
| D7 | **Logic connector:** a shrouded 2×8 header carrying PWM, sense and rails, the same pattern as temper's J4. | seen, inferred |
| D8 | **Heatsink NTCs:** ring-lug NTCs, one per heatsink section. | seen |
| D9 | **Unidentified:** black blocks on the older board (low confidence). | seen |

## Patent (US12712433B1)

| # | Finding |
|---|---|
| P1 | **EMI shield between coil and pan:** a Cu/Al radial comb joined at a ring and grounded so displaced charge returns. Its purpose is to intercept common-mode capacitive coupling and avoid bulky filters. |
| P2 | **Second shield:** a second shield and frame between the coil and the processor, which also acts as a heat sink. |
| P3 | **Spread spectrum:** a frequency-varying carrier at 20–100 kHz, plus adaptive EMI handling when pan contact is poor. |
| P4 | **Sensing chain:** ACS773 for DC bus current (regulation, OCP, efficiency); ACS37612 for coil current (OCP, characterisation, levitation suppression); AMC1350 for bus voltage. |
| P5 | **Pan handling:** presence, size and material from reflected impedance. Power is limited by the computed magnetic force on light pans. |
| P6 | **Claims:** all 20 require one DC source supplying different outputs to two appliances. The shield and the n-FET bridge appear only as dependent claims. This is a divisional of 19/292,752, whose claims are unread. Not legal advice. |

## System context

- **Main computer:** a tablet-class SoC with a Wi-Fi module, USB-C, RJ45 and a
  display FFC.
- **Supply and cooling:** the low-voltage supply is an ODM board ("TONLY") with
  a UL mark. Cooling uses laptop-style blowers.
- **QA:** a pan library built from customer feedback. Validation uses
  thermocouples welded into pans, logged over USB.

## Computed

| # | Result | Script |
|---|---|---|
| T1 | **Pan-R placement:** for a pan earthed through 91 pF, margin is 2.62 dB with the pan R upstream vs 8.37 dB with it physically placed. Nominal is unchanged at 10.48 dB. | `emi_split_cap.py` |
| T2 | **Bank split:** no gain under the physical placement. With asymmetric coupling it loses margin: 70/30 drops from 8.06 to 4.99 dB, and one-sided 100 pF from −0.75 to −3.04 dB. | `emi_split_cap.py` |
| T3 | **Comb shield:** returning ≥ 75 % of the coil capacitance to bus_n gives 10.7–11.1 dB in all coupling cases. | `emi_split_cap.py` |
| T4 | **Touch current, unweighted, through an earthed pan:** I = I_tank·C_wp/(2·C_res). That is 2.25 mA at the 22 A ceiling and 2.86 mA at 28 A with the one-sided bank; about 0 when split. Frequency weighting is not applied. | `tank_cm.py` |
| T5 | **Dither, line-locked at 120 Hz, ±1 kHz:** the fs line drops 8.5 dB QP / 11.0 dB AV and the 2fs line 10.5 / 13.5 dB. At a 1 kHz dither rate the fs line drops less than 2 dB. | `dither_qp.py` |
| T6 | **Input current:** measured on R5, the error is about 1.3–2.5 %, raising the hold from 11.09 A to 11.9–12.05 A. | `input_current_budget.py` |

## Not knowable from the footage

- Device and resonant-capacitor part numbers.
- Turns, inductance and litz strand count.
- Where the shield physically sits.
- MCU part numbers and PCB layer count.
- Whether the shipped product uses spread spectrum.
