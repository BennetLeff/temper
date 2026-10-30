# Datasheet audit, Rev F (2026-10-29 / 30)

Seven independent reviews checked every part on the board against its manufacturer datasheet before the first
order. Each review covered one subsystem. All seven had the same brief ([BRIEF.md](BRIEF.md)): abs max at
worst-case corners, recommended conditions, every pin, required external parts, sequencing, footprint, thermal,
ESD, and debug features worth adding.

- **Audited board:** SHA256 `811927569d2b…9f140da52f15`.
- **Audit input:** the netlist snapshot in [parts.txt](parts.txt) and [nets.txt](nets.txt), from `dump_netlist.py`. These files describe the board as audited, not as fixed.
- **Reports:** [power-entry](power-entry.md), [switcher](switcher.md), [ldos](ldos.md), [mcu-digital](mcu-digital.md), [codec](codec.md), [afe](afe.md), [relays-connectors](relays-connectors.md).
- **Datasheets:** the vendor PDFs the reviewers fetched were saved outside the repository (vendor PDFs are not committed). Each report lists its datasheets with revision and URL.

## Outcome

No part is used beyond a datasheet limit in intended use, except the known USB 2.0 unconfigured-draw FLAG (PE-2).

The reviews found one real board failure, PE-5 / S1:

- **The failure:** with ENP and ENN tied to 3V3, both TPS65131 converters start together. They demand 1.6–2.4 A against the TPS2553's 0.99 A minimum limit, so 5 V collapses below the converter UVLO and the board hiccups.
- **Wider than reported:** a full power-up model (`../power-spurs/startup_surge.py`) shows the boost can start at a 5 V of only 2.1 V, while U16 is still charging the 5 V node. Any fix that starts the converters from 3V3 directly fails for the same reason.

Fixed on the board:

| Change | Finding | Datasheet basis | Evidence |
|---|---|---|---|
| U17 LM3880MF-1AA sequencer. FLAG1 drives ENP and FLAG2 drives ENN, open-drain, with R119/R120 100 k pull-ups to 3V3. C116 100 nF is on U17 EN; C118 100 nF bypasses U17 | PE-5, S1, S2 | TPS65131 SLVS493E 6.1: EN abs max VIN + 0.3 V; 6.5: VIL 0.4 / VIH 1.4 V, UVLO 2.1–2.7 V; 7.3.5: soft-start. LM3880 SNVS451M: 8.1.1 pull-ups; 8.3 EN not tied to VCC; Table 10-2 (AA: 10 ms ±15 %) | `../power-spurs/startup_surge.json`: 128 / 128 corners pass, 5 V ≥ 3.86 V after the first enable |
| C117 330 µF 10 V polymer on 5 V (Nichicon PCG1A331MCL1GS) | PE-5, S1 | Carries each converter's start-up surge above the U16 limit. PCG catalog: ±20 %, 23 mΩ, one reflow at 260 °C | `startup_surge.json`: with U17 but without C117, 32 / 128 corners pass |
| R110 stays 24 k (U16 limit 0.99 A minimum) | PE-5 | Raising the limit to 1.8 A (R110 15 k) was tried: 27 segments and 5 vias then failed the IPC-2152 10 °C rule | `../power-spurs/current_check.json` |
| C113 1 → 4.7 µF on USB_VBUS at U16 IN, then R121 1.5 Ω in C113's ground leg | PE-1 | TPS2553 SLVS841F 10.2.1.2.4: "Additional input capacitance may be needed" against hot-plug ringing (IN abs max 7 V). VBUS capacitance stays under the USB 10 µF limit. A ceramic alone rings with the cable: an ngspice sweep showed 78 / 96 USB-A plug-in corners over 7 V with C113 4.7 µF straight to GND. D1 (SRV05-4, VBR ≥ 6.0 V, no maximum) cannot be counted on | `../power-spurs/hotplug_spice.json`: with R121, 0 / 96 over 6.5 V, worst 6.24 V; bring-up: scope the VB pad |
| R101 2.2 → 1 Ω (VRLY feed) | RC-01 | TQ2SA must-operate 3.75 V (≈ 4.05 V warm): four RESET coils at the 4.40 V USB minimum see 4.10 → 4.19 V | `../../docs/rev-e-range-switching.md` |
| C62 (codec VREF) 1 µF X5R 50 V → 2.2 µF X5R 16 V, same land | C-02 | TAC5112 SLASF24A 7.3.5: "minimum 1uF". The old part is about 0.65 µF at 2.75 V, −10 % and 85 °C; the new one is about 1.3 µF | firmware: VREF_QCHG (list below) |
| Test pads TP15–TP21: I2S BCLK, FSYNC, DOUT, DIN at the codec end with a GND pad; USB_VBUS at U16 IN with a GND pad | C-07, D-1, MCU D1, PE-1 | digital and supply nets only | `../../cad/tools/rev_f_routes.py` TESTPOINTS |
| `regulator_check.py` counted C94/C99, which sit behind R95/R96, as converter output capacitance | L4 | Output-cap rows now count C89–C92 only (break-even retention 0.266 / 0.324) | `../power-spurs/regulator_check.json` |
| `package_cad.py` now requires a placement-library audit for polarized capacitors (CP_*), not only for non-R/C parts | (new during the fix) | C117's + land is pad 1 (EasyEDA C433208 "+" mark), CPL offset 0° | `../../sources/placement-rev-c.json` |

The analog copper is unchanged: all 562 items are identical to the extracted board `6ae693082` (`../layout-parasitics/copper-delta.json`). So the extraction and the loop-stability results carry over.

## Dispositions

Severities are the reviewers'. "Bring-up" means a check in `docs/bring-up-rev-e.md`. "Firmware" means the list below.

| ID | Severity | Disposition |
|---|---|---|
| PE-1 | RISK (high) | Fixed: C113 4.7 µF damped by R121 1.5 Ω (`hotplug_spice.py`). Bring-up: scope U16 IN on hot-plug with 1 m and 2 m cables and a USB-A to C cable at the new VB pad |
| PE-2 | VIOLATION (known FLAG) | Accepted for Rev F, as already argued in `regulator_check.json`: the board draws about 0.46 A from attach. C117 adds an inrush of about 2 ms at the U16 limit. TPS2553 SLVS841F 11.2: a bus-powered function above 44 Ω ∥ 10 µF must limit inrush, and U16 is that limiter |
| PE-3 | RISK | Firmware: bus-powered, 500 mA max power |
| PE-4 | RISK | Bring-up: scope U16 IN/OUT and a USB meter during power-up |
| PE-5 | RISK | Fixed: U17 + C117 (table above) |
| PE-6, PE-8 | RISK (low) | Accepted; noted as possible reset causes in bring-up |
| PE-7 | MISSING (low) | Accepted: U16 FAULT stays unconnected. No free board area near U16; the USB meter and the VB pad show a limit event |
| S1, S2 | RISK | Fixed: U17 (table above) |
| S3 | RISK (low) | Doc: the −15 V margin wording in `regulator_check.py` is reversed; no hardware change |
| S4, S5 | RISK (low) | Bring-up: scope SW_P / SW_N at VIN 5.5 V for peak and DCM ring |
| S6 | RISK (low) | Bring-up: probe FBN at R111 |
| S7 | RISK (low) | Accepted |
| S16, L5 | RISK (low) | Accepted: monitor pins go slightly beyond −0.5 V at power-down through 100 k. Firmware holds the DAC and relays until MON12 / MON_N12 are in their windows |
| S17 | MISSING (doc) | Already handled: `docs/bring-up.md` opens by sending Rev E/F boards to `docs/bring-up-rev-e.md`; its Rev D rail numbers stay as history |
| L1, L3, L8, L9 | RISK (low) | Bring-up: 12 V ripple at the lowest RAW_P; do not short rails with a live probe ground |
| L4 | RISK (low) | Fixed in `regulator_check.py` |
| L6 | RISK (low) | Firmware: MON-window sequencing |
| L7 | RISK (low) | Bring-up: measure I(3V3) and U3 case temperature in the closed box |
| M1 | RISK (assembly) | JLC placement preview: check Y1 pin 1 by pad geometry (the chamfer is unreliable) |
| M2, M3 | MISSING (minor) | Accepted; revisit at the next respin of the U1 area |
| R1 | RISK (low) | Accepted |
| R2 | RISK (low) | Doc: J5/J6 are 3.3 V only |
| R3 | RISK (low) | Bring-up: scope 3V3, RUN and QSPI_CS together |
| R4 | RISK (low) | Enclosure: SW1/SW2 must be reachable |
| R5, C-12 | RISK (low) | Firmware: GPIO drive strength / slew if bring-up shows slow or ringing I2S edges |
| C-01 | RISK | Mostly settled by TI SBAA634A Table 2-3 (2026-10-30): at 40 k, CM_TOL 1 gives SNR 101 dB / THD+N -97 dB vs 102 / -97 in mode 0 and 100 / -96 in mode 2 (1 kHz, EVM). Bring-up: confirm at 27-60 kHz wideband (codec.md addendum) |
| C-02 | RISK | Fixed: C62 2.2 µF. Firmware: VREF_QCHG |
| C-03, C-13 | RISK | Accepted (fault-only / covered by the K4 reference check). C-13: SBAA634A gives CMRR 47 dB at 40 k (not 60 dB), so the term is about 4.5x the audit's estimate; calibration still removes it |
| C-04 | RISK | Firmware: INCAP_QCHG = 1, and a capture skip of ≥ 0.3 s after any ADC power-up |
| C-05, C-06 | RISK | Bring-up 3.3: read CLK_DET_STS0 / CLK_ERR_STS. Fallback: PASI_FS_RATE_NO_LIM. 187.5 kHz lies in the auto 192 kHz bucket (174.64–193.92 kHz) |
| C-07 | MISSING | Fixed: I2S test pads |
| C-08 | RISK (low) | Assembly: X-ray U14 (EP vias inside the paste apertures) |
| AFE-01 … AFE-04 | RISK (high consequence) | Deferred to Rev G as a study: the DUT jacks have no protection. The study would cover a residual-voltage sense, series R at the follower inputs, and clamps on the jack side, never on TIA_SUM. Any change to the verified TIA/follower nodes needs re-extraction and the stability matrix. Rev F: the silk says DISCHARGED / DUT ONLY; bring-up states the real limit of about 5 V residual |
| AFE-05, AFE-06 | RISK (accuracy) | Bring-up: amplitude sweep at 60 kHz, and ratio drift in a warm box (BAT54S Cj / leakage) |
| AFE-07 … AFE-09 | RISK | Bring-up: AVDD on a +12 V step; connect no DUT until range = 100 k |
| RC-01 | RISK | Fixed: R101 1 Ω |
| RC-02 | OK-NOTE | TQ catalog p.16 asks for pulses of ≥ 10 ms; firmware uses 20 ms |
| RC-04, RC-07 | RISK (low) | Firmware: relay state "unknown" until the first RANGE command; optional K3 wetting cycle before calibration |
| RC-08 | RISK | Bring-up 8: measure a loose TQ2SA's capacitances |
| RC-09 | RISK (process) | `manufacturing/FABRICATION.md`: single reflow, no ultrasonic cleaning, no silicone near K1–K4 |
| RC-10 | RISK | JLC placement preview: K1–K4 rotation and stripe vs pad 1 |
| RC-11 | RISK (low) | Enclosure clamps the BNC flange |
| RC-12 | MISSING | Same as AFE-01 (Rev G) |

The OK-NOTE rows (PE-9…16, S8…15, L2, L10…12, N1…9, C-09…11, C-14…15, AFE-10…14, RC-03, 05, 06, 13…16) need no action.

## Firmware items

Items 1–4 are done in `../../firmware-rev-e/` (commit f13087113, 2026-10-30): host tests pass for both sample rates, and the images were rebuilt with Pico SDK 2.2.0 and Arm GNU 14.2.rel1. Nothing has run on a board. The SDK hard-codes 250 mA, so the firmware has its own USB descriptors (bus powered, 500 mA). A clock-error fallback shows in a new `STATUS` command. The K3 wetting cycle (item 4) and the drive strength (item 5) remain open.

1. USB: bus-powered, `USBD_MAX_POWER_MA=500`; drop `PICO_STDIO_USB_DEVICE_SELF_POWERED` (PE-3).
2. Codec: VREF_QCHG for the 2.2 µF C62 (C-02); INCAP_QCHG = 1 and a capture skip of ≥ 0.3 s (C-04); the clock-error fallback (C-05).
3. Analog start: keep the DAC idle and the relays at rest until MON12 / MON_N12 read in-window (L5, L6, S16). U17 releases ENN about 20–60 ms after power-up.
4. Relays: report state "unknown" until the first RANGE command (RC-04).
5. I2S drive strength / slew if bring-up shows slow or ringing edges (R5, C-12).

## Debug features

- **Added:** I2S and USB_VBUS test pads with GND pads (TP15–TP21).
- **Already present:** rail test pads TP1–TP9, coil-line pads TP10–TP14, rail and heartbeat LEDs.
- **Declined:**
  - Series-R footprints on I2S: firmware drive strength covers the risk.
  - Tag-Connect land: the SWD header J4 exists.
  - 1V1, VREF and DREG pads: probe C8, C62 and C63 directly.
  - Snubber footprint across D3: no room; scope first.
  - Any pad or footprint on analog nodes: added capacitance costs loop margin.
