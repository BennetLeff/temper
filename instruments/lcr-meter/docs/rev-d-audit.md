# Rev D board audit: decoupling, simplification, part choices (2026-10-20)

Scope: every functional group on the Rev D board (`eb2b4cf8…`), checked against the vendor layout guidance in `sources/`, the native board geometry, and the in-box studies (`validation/`). Each finding cites the measurement that supports it. Tier 1 was applied the same day; see **Applied** below for what changed, what was withdrawn and why. The findings sections keep the original audit text.

How to read the tiers:
- **Tier 1, before ordering Rev D.** Local hand-routed edits that bring the board into line with explicit vendor requirements, or cheap changes with clear payoff. No architecture change.
- **Tier 2, Rev E.** Larger changes worth doing if the board is re-laid out: they cut cost or parts, or add agent control, but each needs new evidence.

## Applied (2026-10-20)

Rebuilt board: DRC 0, unconnected 0, schematic parity 0, ERC 0; `validation/independent_check.py D` 576 pins, 0 findings; `cad/audit_dfm.py` 54 intended filled/capped via-in-pad sites, none unexpected. All routing is hand-specified segments (`cad/tools/edit_lib.py`). Numbers below are from the regenerated `validation/layout-audit-rev-d.json`.

| # | Item | Result |
|---|---|---|
| 1 | Exposed-pad vias | Vias in pad: U1 1 → 8, U8 1 → 5, U9 1 → 5, U10 1 → 5, U11 0 → 6, U12 0 → 6, U13 1 → 9 (0.55/0.25 mm, POFV). The U1 grid skips the corner over the In2 QSPI1 diagonal. `audit_dfm.py` now expects U11.9 and U12.9 |
| 2 | ADS9224R | C72/C73 → 10 µF X7R 0805 (C95841) at 1.56 mm from REFP. REFM runs pin → cap ground pad on F.Cu (0.3 mm), then the via at the cap's far end. C76/C77 → 1 µF 0603 at 1.67 / 2.46 mm from pins 12 / 29. **Not done:** C78 (DVDD, pin 28) stays at 7.0 mm; the pin-side row is full with the reference and AVDD caps, so it needs an 0402 or a bottom-side part |
| 3 | LDO support parts | Both LDOs re-placed per TI's layout: CIN 100 nF and NR on the input side, COUT and the divider + CFF on the output side, each with its own ground via. FB nodes REGP_FB 13.2 → 5.2 mm and REGN_FB 12.0 → 5.3 mm of trace (most of it runs between the divider parts; pin to first pad is about 2 mm). NR 3.6/5.2 → 2.1 mm. The LDOIN_N In2 run moved from y 133.7 to y 138 to clear the PowerPAD vias |
| 3b | Converter feedback (Tier 2 item 8, partial) | R81/R82/C87 packed into one column 1.5 mm from pin 22's trace; the FBN divider turned so its node is one F.Cu column fed by a single straight B.Cu run under the In1 plane. CONV_FBP 13.1 → 9.1 mm, CONV_FBN 16.8 → 12.3 mm. The inductors, diodes and output caps are not moved |
| 4 | RP2040 | C5 (shared by pins 42–44, 48, 49) → 1 µF 0603 X5R (C15849), so VREG_VIN has 1 µF at 2.6 mm and the other pins keep a cap at 2.7–3.8 mm. **Not done:** no 100 nF at DVDD pin 50; the USB/QSPI/UART fan-out fills that side. Pin 50 relies on C8 (1 µF, 6.3 mm) |
| 5 | Source settling | C36 → 100 nF 0805 (C49678). Firmware settle → max(150 ms, 20 cycles) |
| 6 | Part swaps | Applied: D4 red LED (C2286), FB1/FB2 GZ2012D101TF (C1015), U2 W25Q128JVSIQ (C97521), C84 CL10B224KA8NNNC (C21120), the 14 V caps C89–C92, C94, C95, C99, C100 and the converter input caps C80/C82 → CL32B106KBJNNNE (C138687), C18 → CL21A106KAYNNNE 0805 (C15850), C103 → CL31A226KAHNNNE 1206 (C12891). Extended lines 34 → 30, including the new 10 µF X7R reference-cap line (C95841); about $12 of feeder fees per order instead of the ~$31 estimated, because the divider swaps were withdrawn (below). Catalog SMT parts $72.95 per board (was $73.18) |
| 7 | `BOOT` | Firmware `BOOT` → `OK`, then `reset_usb_boot()`. Host 0.7.0 adds `temper-lcr boot PORT` |

**Withdrawn after checking (the §1 and §7 claims were wrong):**
- **Converter dividers to TI's example values.** `validation/power-spurs/regulator_check.py` had the Rev C values hard-coded (1.62 MΩ / 1.78 MΩ). It now reads `design.json`. At the full tolerance stack, 1 MΩ / 91 kΩ gives VPOS up to 15.105 V, over TI's 15 V recommended maximum. The audit said it stayed under. No basic or preferred 0603 pair puts the ratio in the 10.38–10.91 window that keeps VPOS ≤ 15 V and U11 headroom ≥ 1 V. R81–R84, C87 and C88 keep their Rev D values (1.62 MΩ / 150 kΩ / 4.3 pF; 1.74 MΩ / 150 kΩ / 4.3 pF).
- **LDO dividers 0.1 % → 1 %.** The ±12 V set points are not references, but 1 % widens the LDO output to 12.54 V max. That leaves U12 0.74 V of headroom at the worst VNEG, under the 1 V the PSRR curves assume. R85–R89 stay 0.1 %.
- **C80/C82 → 25 V 0805.** At 5 V the 0805 does not keep TI's 4.7 µF at INP and INN after tolerance and temperature. They use the 50 V 1210 line already on the board for the 14 V caps, so no line is added.
- **D1 USBLC6 → SRV05-4 (C7420376).** The LCSC listing is now R+O, not the part researched. Its datasheet link returns an HTML page and the EasyEDA symbol API refused the request, so the pinout could not be checked against a primary source. A wrong ESD pinout can short VBUS. USBLC6-2SC6 stays.

**Found while checking (Rev D as designed, not caused by these edits).** With the real R83 (1.74 MΩ) and the 1 Ω R96 that Rev D fits, U12 headroom at the full tolerance stack and 2× the estimated load is 0.949 V. That is above the 0.6 V dropout and below the 1 V PSRR-curve condition (`regulator_check.json`, "Option R5" row, which now describes the fitted part). The stale 1.78 MΩ value had shown 1.256 V. At the estimated load, headroom is 0.99 V. Measure −12 V ripple at bring-up.

## Summary

| # | Tier | Change | Why | Cost/effort |
|---|---|---|---|---|
| 1 | 1 | Multiple vias in every exposed pad (U1, U8, U9, U10, U13) and in the U11/U12 PowerPADs (currently none) | TI requires "multiple vias directly under the device" for both LDOs; POFV is already paid, so extra vias are free | Hand edits; no new parts |
| 2 | 1 | ADS9224R: 10 µF X7R 0805 reference caps tight to REFP/REFM with REFM joined to the cap before any via; 1 µF AVDD/DVDD caps beside their named pin pairs | Three explicit datasheet instructions the board does not follow, on the most expensive and most accuracy-critical part | Re-place 6 caps around U10 |
| 3 | 1 | LDO support parts (CNR, CFF, divider, COUT) tight to U11/U12 | TI: "every capacitor … as close as possible"; FB nodes are 12–13 mm long now | Re-place ~12 parts |
| 4 | 1 | RP2040: 1 µF at VREG_VIN (pin 44); 100 nF at DVDD pin 50 | Raspberry Pi guide asks for both; nearest are >6 mm and >10 mm | +1–2 parts |
| 5 | 1 | C36 1 µF → 100 nF; firmware settle 1000 ms → 150 ms | Settling is 2.0 s of every 2.1 s measurement point at 50 kHz; ~8× faster sweeps for agent loops | One value + firmware |
| 6 | 1 | Move 10 extended lines to basic parts where electrically equivalent; fix the dim status LED; replace the low-stock flash | 34 extended lines ≈ $104 of feeder fees per order, more than the parts on one board. Saves ~$31 per order | §7 table |
| 7 | 1 | Firmware `BOOT` command (reset to USB bootloader) | An agent can reflash without pressing BOOTSEL | Firmware only |
| 8 | 2 | Compact the TPS65131 power island per TI's layout example | Inductors, diodes and output caps sit 6–10 mm from the IC; FB dividers 8–10 mm | Re-layout of the power island |
| 9 | 2 | Shrink the board (parts cover 14 % of 140 × 100 mm) | Shorter loops everywhere; smaller fab price tier | Full re-layout |
| 10 | 2 | Firmware-selected ranges (relays or switches) instead of six jumpers | The one thing an agent cannot do today is change range | New circuit + stability evidence |
| 11 | 2 | Replace AD9833 + OPA810 gain stage with a DAC clocked by the RP2040 | Removes the second most expensive part and the spur source that sets the marginal coil-R corner | New source chain + evidence |
| 12 | 2 | Evaluate an audio-codec acquisition chain (Rev E architecture option) | Noise is 30–2000× better than needed; a codec could replace ADC + FDAs + DDS | Architecture change; loses >~86 kHz |

## 1. Power (52 parts, $11.43)

TPS65131 boost/inverter → R95/R96 → TPS7A4901 / TPS7A3001 (±12 V); AP2112K (3V3); FB1 → 5VA.

**Decoupling and layout**

| Finding | Evidence | Recommendation |
|---|---|---|
| U11/U12 PowerPADs have **no vias** | `layout-audit-rev-d.json` `exposed_pads`: pad 9 of both, 0 vias in pad. TPS7A49 §10.1 / TPS7A30 §10.1: "The PowerPAD must be connected to any internal PCB ground planes using multiple vias directly under the device." | 3–5 vias (0.25–0.3 mm) in each PowerPAD. POFV is already ordered |
| LDO support parts are far from the LDOs | CNR 4.5 mm, CFF 8.9 mm, divider 5–6.4 mm, COUT 6.0–7.8 mm, CIN 9.4–10.0 mm. REGP_FB and REGN_FB are 12–13 mm long. TI: "Every capacitor (CIN, COUT, CNR/SS, and CFF) must be placed as close as possible to the device" | Re-place around each LDO; keep the FB node under ~3 mm |
| U13 (TPS65131) power parts are spread | L1 8.6 mm, L2 10.3 mm, D2/D3 7.1/7.6 mm, output caps 6–10 mm from the diodes; EP has 1 via. TI §10.1: inductors, diodes and output caps "as close as possible to the IC", "feedback dividers as close as possible to the control pin" | Tier 2: compact per TI's layout example. Tier 1: add EP vias |
| Converter FB nodes are long and high impedance | CONV_FBP 13 mm, CONV_FBN 17 mm, 1.6–1.7 MΩ dividers | Move dividers to the IC (with item 6 below they become 1 MΩ/1.5 MΩ, also per TI's example) |

**Simplification and parts**

- **Converter dividers to TI's example values, all basic.** TI's application example uses R1 = R3 = 1 MΩ with 6.8 pF feed-forward. Positive: R81 1 MΩ (C22935) / R82 91 kΩ (C23265) → 14.54 V (now 14.31 V), C87 6.8 pF C0G (C1679). Negative: R83 1.5 MΩ (C4172) / R84 130 kΩ (C22795) → −14.00 V (now −14.07 V), C88 4.7 pF C0G (C1669); the R·C zero stays at ~7 µs. That removes three extended lines (C482643, C422975, C519375). Positive tolerance corner stays under TI's 15 V maximum; LDO headroom rises. Rerun `validation/power-spurs/run_all.py` with the new set points.
- **C84 220 nF → CL10B224KA8NNNC (C21120, basic, 25 V X7R)**: CONV_REF is 1.213 V. TI's example uses 220 nF X5R 6.3 V.
- **LDO dividers R85–R89 0.1 % → 1 % basic.** The ±12 V set points are not references; 1 % is 0.12 V. 91 kΩ C23265, 10 kΩ C25804, 1 kΩ C21190. Removes two extended lines (C326721, C95204).
- **10 µF 50 V 1210 on 5 V / 3V3 (C18, C80, C82)**: a 50 V 1210 is unnecessary at 5 V; a basic 0805 25 V part saves ~$0.26 each. It saves no feeder line while the switcher and LDO positions keep C337485.
- Keep: TPS65131, both LDOs, R95/R96, SS14 diodes, FNR5040 inductors (the spur analysis depends on them), AO3401A reverse-polarity FET.

## 2. Digital (43 parts, $5.05)

RP2040, W25Q16 flash, 12 MHz crystal, USB-C, USBLC6, SWD/UART headers, LED, two buttons.

| Finding | Evidence | Recommendation |
|---|---|---|
| VREG_VIN (pin 44) has no nearby 1 µF | Nearest 1 µF (C10) >6 mm; RP2040 hardware guide §2.1.3: "We must place 1 μF capacitors close to both the input (VREG_IN) and the output (VREG_OUT)" | Move C10 (or add 1 µF) beside pin 44 |
| DVDD pin 50 has no close 100 nF | Nearest is the 1 µF C8 at 6.3 mm; the 100 nF C9 is 5.8 mm from pin 23 and 11.2 mm from pin 50. Guide: "100 nF capacitor per power pin" | Add 100 nF at pin 50 |
| One 100 nF (C5) serves pins 42, 43 (ADC_AVDD), 44, 48, 49 | 2.6–3.0 mm to each | Acceptable (the Pi minimal design also shares); ADC_AVDD now feeds the rail monitors, which read ratiometrically |
| EP (pin 57) has one via | `exposed_pads` | Add vias (item 1) |

Agent drivability: add a firmware `BOOT` command that calls `reset_usb_boot()`. An agent can then flash new firmware with one CDC command and a file copy, without BOOTSEL. Keep both buttons for recovery from a blank or broken image.

Simplification: J4 + J5 (SWD, two 2-pin headers) can become one 3-pin header (SWCLK, GND, SWDIO), and J6 (UART) can be left unfitted: USB CDC is the instrument interface. Both are hand-fit, so this saves hand work, not feeder fees.

## 3. Source (19 parts, $16.16)

AD9833 DDS (24 MHz from the RP2040) → two RC sections → 1 µF/100 kΩ coupling → OPA810 ×6 → U6A follower.

| Finding | Evidence | Recommendation |
|---|---|---|
| Settling dominates measurement time | Firmware waits ≥1000 ms per capture, and again for the source-off capture, for the 1 µF/100 kΩ coupling (τ = 100 ms). At 50 kHz a capture takes 33 ms, so a point is ~2.1 s, of which 2.0 s is waiting | **C36 → 100 nF** (τ = 10 ms, corner 16 Hz: 98.7 % amplitude at 100 Hz, phase absorbed by the ratiometric measurement and calibration; OPA810 bias is 2 pA, so no offset). Firmware settle → max(150 ms, 20 cycles). About 8× faster sweeps |
| AD9833 is $12.77, the second most expensive part | BOM | See Tier 2 item 11 |
| AD9833 spurs set the marginal coil-R corner | VI study §2.3: 21 mΩ at the −60 dBc datasheet SFDR at 50 kHz (avoidable by frequency choice; the host grid already avoids it) | Tier 2 item 11 removes the source of the term |
| AD9833 VDD 100 nF at 5.5 mm | `decoupling["U4.2"]` | Move C32 beside pin 2 if the DDS stays |

## 4. AFE (29 parts, $12.71)

TIDA-060029 core: OPA2810 source buffer, followers, TIA; six range jumpers; R94.

Decoupling is the best on the board: 10 nF at 2.0–2.1 mm, 100 nF at 3.3–4.7 mm, 1 µF at 5–11 mm, all inside TI's < 0.1″ for the 10 nF. Stability has extracted-parasitic evidence (51.3° minimum). No Tier 1 change.

**The one gap for agent use is range selection.** Six jumpers mean a person must move shunts with power off. Rev D's R94 removed the reason relays were ruled out before (cable/relay capacitance on LO is now benign). A two-pole selection per range (source and feedback resistor together) under GPIO control is the highest-value Tier 2 addition. It needs new stability evidence for switch capacitance on the summing node and switch Ron in the RF path; candidates are in the sourcing table. Twelve RP2040 GPIOs are free (0, 1, 14–20, 22–24).

## 5. Acquisition (41 parts, $30.89)

ADS9224R (two 16-bit SAR channels, 1 MSPS) driven by two THS4551 FDAs.

| Finding | Evidence | Recommendation |
|---|---|---|
| REFM is not joined to the reference cap before a via | REFM_B (pin 9) goes to its own via at (142.5, 94.2); C73's ground pad to another at (143.8, 90.0); REFM_A (pin 32) has no top-copper link to C72. ADS9224R §10.1.4: "Connect the REFM_x pins to the decoupling capacitor before a ground via" | Join REFM pin → cap ground pad on F.Cu, then via |
| Reference caps are 22 µF in 1210 | §10.1.4: "a 10-µF, X7R-grade … Select 0603- or 0805-size capacitors to keep ESL low" | 10 µF X7R ≥10 V 0805 at pins 31/32 and 9/10 |
| AVDD/DVDD caps are 3.5–7 mm away | §10.1.3: "within 20 mil from the respective pins"; pin table names the pairs 12–11, 29–30, 28–27 | Move C76, C77, C78 beside those pins |
| EP has one 0.25 mm via | `exposed_pads`; §10.1.2 asks for < 1 nH grounding | 4–9 vias in the EP |
| FDA VOCM (ADC_CM) runs ~11 mm to U8/U9 without local caps | THS4551 §9.4: 0.1 µF on VOCM is advised when floated; here it is driven by REFby2, a buffered output | No change needed. TI's EVM uses 100 Ω + 100 nF per driver; restore it if the first board shows common-mode noise |
| 4.32 Ω output resistors (extended, 4 parts) | No basic 4.32 Ω; 4.7 Ω is basic (C23164) | Only with an FDA stability rerun (`fda-independent`); saves one line |

## 6. Tier 2: architecture options

**Source (item 11).** An I2S or SPI DAC clocked from the RP2040 keeps coherent sampling (both clocks divide 120 MHz exactly), gives arbitrary and multi-tone excitation, and can be DC-coupled from a zero-centred output. That removes the coupling settle entirely and, at full-scale 2 Vrms, possibly the OPA810 gain stage. See the sourcing section for candidates and the checks still needed.

**Acquisition (item 12).** The virtual-instrument study shows electronic noise 30–2000× below what the targets need, and the ADC at 36 % of a negligible budget. Temper's frequencies (1–1.5 kHz and 27–60 kHz) fit inside a 192 kHz audio codec's passband (~0.45·fs ≈ 86 kHz). A codec's decimation filter rejects everything above ~0.55·fs, so the harmonic-aliasing hazards the host now guards against would disappear. One stereo codec (ADC + DAC) could replace the ADS9224R, both THS4551s, the AD9833 and the OPA810 (≈ $45 and ~30 parts). Costs: the instrument stops at ~86 kHz (firmware now allows 100 kHz); the FDA difference stages need a replacement; all acquisition evidence is redone. Worth a spike only if a Rev E happens; not for this order.

**Power from USB (single cable).** The estimated load (±37 mA on ±12 V via the boost, plus 5VA and 3V3) is roughly 0.35–0.4 A at 5 V, inside USB 2.0's 500 mA. The obstacle is 5VA: ADC AVDD and the FDAs are fed from raw 5 V through a ferrite, so a PC's VBUS noise would reach them. A local LDO for 5VA from the +14 V raw rail (another TPS7A4901, same BOM line) would remove that dependency. Then the DC jack, Q1, the VBUS divider and the external supply could go. Agent benefit: one cable. Needs a power-spur rerun.

**Board size (item 9).** Courtyards cover 14 % of the board: power spans 69 × 43 mm for 662 mm² of parts. A compact re-layout would shorten every loop above and drop below JLC's 100 × 100 mm price tier. It is a full hand re-route.

## 7. Sourcing

Basic/preferred status from JLC's full Basic (351) and Preferred (1,235) lists, downloaded 2026-10-20; prices and stock are JLC quantity-1 values on that date. No connector of any kind is Basic or Preferred, so the USB-C receptacle stays extended (the barrel jack is hand-fitted, so it never incurs the fee).

**Tier 1 line swaps (each removes a ~$3-per-order fee):**

| Now | Replace with | LCSC | Why it is safe | Lines saved |
|---|---|---|---|---:|
| Green 0603 LED (C22371297) | KT-0603R red 0603 LED | C2286 basic | Same footprint. **Also a fix:** the green part's Vf ≈ 3.1 V leaves only 0.2–0.5 mA through R12 from 3.3 V; red runs at ~1.3 mA | 1 |
| BLM21PG121SN1D bead ×2 (C79382) | Sunlord GZ2012D101TF 0805 | C1015 basic | Same 0805 pads; 150 mΩ, 800 mA; FB1 at 60 mA drops ~9 mV | 1 |
| W25Q16JVSSIQ (C131025) | W25Q128JVSIQ | C97521 basic | Same SOIC-8 208 mil; the flash in Raspberry Pi's own minimal design. **Current part has only 559 in stock.** +$1.43 per board, so at 2 boards the fee saving roughly breaks even; the reason is stock | 1 |
| USBLC6-2SC6 (C7519) | SRV05-4 | C7420376 preferred | 1.0 pF I/O capacitance; same pin roles per its datasheet (pin 5 rail, pin 2 GND). Check the pinout once more against the footprint at the swap | 1 |
| R85–R89 0.1 % (C326721, C95204) | 1 % basic 91 k / 10 k / 1 k | C23265, C25804, C21190 | ±12 V are not references | 2 |
| R81/R83/C87/C88 (C482643, C422975, C519375) | 1 M / 91 k / 6.8 pF and 1.5 M / 130 k / 4.7 pF | C22935, C23265, C1679, C4172, C22795, C1669 | TI's application-example values; see §1. Rerun the power-spur analysis | 3 |
| C84 220 nF (C107083) | CL10B224KA8NNNC | C21120 basic | 25 V X7R on a 1.213 V node | 1 |

That is 10 lines, about $31 per order, for net BOM change under $3 per board.

**Same line count, better part:** the 14 V nodes' UMK325AB7106KM-P (10 µF 50 V 1210) keeps only ≈4.2 µF at 14 V (Taiyo Yuden DC-bias data, −58 %). Samsung CL32B106KBJNNNE (C138687, 50 V X7R 1210, same price) keeps ≈7.3 µF. Swap it on C89–C92, C94, C95, C99 and C100. Move C18, C80 and C82 (5 V / 3V3) to CL21A106KAYNNNE (C15850, basic, 5.0 µF at 5 V).

**Reference caps (§5):** no 10 µF X7R part is basic. Use Samsung CL21B106KOQNNNE (C95841, 16 V X7R 0805, 248 k stock), one per reference as TI specifies. It keeps ≈5.2 µF at 4.1 V, which is what any 0805 part that meets TI's guidance does. C103 (5VA bulk) can then become a basic 22 µF 1206 (C12891), retiring the 1210 22 µF line.

**Optional, need a footprint change:** tactile switches → XUNPU TS-1088 (C720477, basic, 4 × 3 mm); AP2112K → XC6206P332MR (C5446, basic, SOT-23-3; PSRR 50 dB vs 65 dB at 1 kHz). Each saves one line. **Keep** the ABM8-272-T3 crystal: Raspberry Pi tuned the 1 kΩ series resistor for ESR ≤ 50 Ω and CL = 10 pF, and the basic 12 MHz part (C9002) is 80 Ω / 20 pF, so it would need a start-up test over temperature.

**Source alternatives (§6, item 11):**

| Option | LCSC | Price | Verdict |
|---|---|---|---|
| AD9833BRMZ (now) | C9652 | $12.77, 1,225 stock | Works; spur source |
| AD9837BCPZ | C138562 | $7.24 | **Reject:** B grade rated to 16 MHz; this board clocks the DDS at 24 MHz |
| PCM5102APWR I2S DAC | C107671 | $1.45, 2,609 stock | **Best candidate.** 2.1 Vrms, THD+N −93 dB (1 kHz), 8–384 kHz. Clock detection accepts 384 kHz ±4 %, so 375 kHz (= 120 MHz/320, coherent) should work *with the 24 MHz master clock wired*. Unknowns to bench-check: THD at 50 kHz, out-of-band noise, charge-pump spurs (~1.5 MHz, unverified), and image filtering at fs ± f (needs a ~100–150 kHz analog low-pass). Removes the OPA810 stage and the AC coupling: about $14 per board |

If the AD9833 stays, its 9th/11th harmonics at 450/550 kHz pass the 482 kHz RC sections almost untouched. Turning the OPA810 ×6 stage into a two-pole low-pass at ~150 kHz would add attenuation where the spur term comes from (estimate, not simulated).

**Range switching (§4):** Omron G6K-2F-Y-5V DPDT signal relays (C2982926, $1.18, extended), one per range, so three relays plus a basic AO3400A driver (C20917) and 1N4148WS flyback diode (C2128) each. The contacts are ≤100 mΩ, their capacitance is about 1 pF (unverified), and insulation is ≥1000 MΩ. Relays beat analog switches here:
- The TMUX6209 has 4–6 Ω Ron and 15–68 pF off-capacitance on the summing node. Its off-feedthrough also gives an estimated several-percent quadrature error on the 100 kΩ range at 60 kHz. Only 266 are in stock.
- The CD4052B is limited to 20 V absolute maximum, so it can't sit on ±12 V.

Relays add about $4.5 per board and four lines.

## Method

`cad/tools/audit_layout.py` (KiCad Python, read-only) writes `validation/layout-audit-rev-d.json`, the source of every distance, via count and area above. It measures supply-pin-to-capacitor distances, return-via distances, vias per exposed pad and courtyard area per sheet on the native board. Vendor text is quoted from `sources/ti/*.txt` and `sources/new/RP2040-hardware.txt`. Basic/extended status is from jlcsearch (stock figures there are often empty).
