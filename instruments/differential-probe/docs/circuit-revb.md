# Rev B circuit changes and validation

Rev B implements accessible per-leg AC adjustment, fixed amplifier feedback, output range selection, and warnings for the initial operating limits. Schematic ERC has zero errors/warnings. The exported KiCad XML/BOM and independent assertions agree on 140 components, 135 board footprints, five offboard components, 364 pins and 88 connectivity groups.

## Fine compensation

CT1/CT2 are **EW Electronics GKG60015**, 12–60 pF, 100 V, top-adjust ceramic trimmers. This active catalog part gives nearly the requested 5–60 pF span; the minimum is 12 pF. The coarse bank changes C45/C55 from 82 to 47 pF, giving 13.158 nF. The ideal 13.1934 nF total requires 35.4 pF from the trimmer before assembly strays. Select the coarse bank once the assembled ladder response is known, then use the trimmer for the final adjustment with the fixed shield fitted.

The April 2026 EW manufacturer drawing is archived as `sources/GKG60015-EW-2026.pdf`. It is an image-only PDF; no empty text extraction is presented as evidence. The older Sprague-Goodman SG-305J drawing, also archived, provides the same GKGxxx15 mechanical and rotor/stator identification. The custom footprint maps project pin **1 to the right stator (+2.5, 0 mm), TAP_P/TAP_N**, and project pin **2 to the left rotor (−2.5, 0 mm), GND**, viewed from the component side with the manufacturer orientation. These are assigned project pin numbers; the manufacturer's terminals are identified by rotor/stator function.

Body diameter is 6.0 ±0.2 mm, maximum seated height 5 mm, hole pitch 5 mm, recommended holes 1.2 mm. The footprint uses 2 mm lands and a 7.5 ×7 mm courtyard. Its origin is the adjustment axis and should coincide with the insulated-tool access axis in the lid. The supplied VRML body is a low-fidelity envelope, not a detailed mechanical release. Keep the drawing orientation when hand assembling so rotor grounding is preserved.

This trimmer is not C0G: its specified TCC is −2200 ±800 ppm/°C and Q ≥200 at 1 MHz. At 35.4 pF it contributes approximately −5.9 ±2.1 ppm/°C to the total 13.1934 nF low-leg capacitance. That is an explicit temperature/CMRR qualification item. Use an insulated tool and repeat the reading after withdrawing it; adjustability does not establish the 60 dB goal.

## Fixed gains and output selection

U3 is now **OPA810IDR**, configured as a fixed ×2 subtractor. R61/R62 remain 499 Ω; R63+R64 and R65+R66 remain 998 Ω. The former SW1 connections to SUM_P/SUM_N are removed. C62/C63 are removed because those optional compensation positions belonged to the former high-speed switched-feedback arrangement.

U12 is another OPA810IDR, with a fixed noninverting gain of five. R67 is 499 Ω to ground; R68+R97+R98+R99 are four 499 Ω resistors in series, 1996 Ω feedback. R100, 49.9 Ω, feeds its noninverting input from RAW_OUT. C96/C97 are its local supply bypasses. OPA810 has 70 MHz gain-bandwidth and wider differential-input overload capability than conventional antiparallel input clamps; see the archived TI data sheet, section 7.3.1. U1/U2 remain the existing ADA4817 input buffers.

The original gold-contact C&K 7201SYZBE is retained as an output selector using only one pole:

| SW1 terminal | Connection |
|---|---|
| 1 | WIDE_SEL from RAW_OUT through R101, 49.9 Ω |
| 2 | SELECTED, common output to the shared filter and U6 sense divider |
| 3 | FINE_SEL from FINE_OUT through R102, 49.9 Ω |
| 4, 5, 6 | Unconnected |

The manufacturer's generic technical data states that switches are break-before-make unless noted otherwise; confirm the supplied switch contacts during low-voltage bring-up. R101/R102 also limit momentary output contention if contacts overlap. R103, 1 MΩ, defines a DC return while the selector is open. No feedback loop opens during range change. Data during contact bounce and settling are invalid; the assembly still needs a measured switching/recovery test.

The unused ×5 stage can saturate in wide-range operation. Its input is isolated through R100; it does not drive the selected output in that state, and its saturation alone does not trigger U6. Bench testing must confirm that real supply and PCB coupling do not disturb the selected wide path.

R71/R72 remain 10 kΩ each to sense the selected output at half amplitude. Alongside R103 they load the selected path by 19.608 kΩ. R101/R102 introduce a nominal 0.254% DC insertion loss, common to the ranges, which calibration must include. With the 1 MΩ scope and R70, loaded nominal ratios are approximately **1002.595:1 and 200.519:1**, before calibration.

R69 remains 97.6 Ω and C61 changes to **180 pF C0G**, KEMET C0805C181J5GACTU. Including the selected 49.9 Ω source resistor and its parallel loading, the RC source resistance is 147.373 Ω and the nominal pole is 5.9997 MHz. A single-pole amplifier estimate gives 5.648 MHz wide and 4.998 MHz fine overall bandwidth. The vendor-macromodel result below is more informative, but neither establishes the completed probe response.

## Warning thresholds and analog zero

R87/R91 become 25.5 kΩ with 10 kΩ bottoms, giving ±0.702817 V at U5: nominally **±1405.6 V per tip**. R89/R93 become 29.4 kΩ with 10 kΩ bottoms. Together with R71/R72, U6 trips at a nominal selected signal of **±1.266497 V**, corresponding to approximately **±1266.5 V wide / ±253.3 V fine** before insertion/calibration corrections. Early warning is intentional; the LED does not define the initial qualification limits or prove that every transient was captured.

The output threshold includes room for analog offsets that scope zero subtraction cannot remove from the comparators. The static late-trip budget in `tools/check.rs` uses:

- −25 to +85°C, matching the trimmer's rated range.
- TL431B upper reference 2.507 V plus 34 mV maximum temperature deviation and a 5 mV current/load allowance.
- 0.1% threshold/sense resistors plus 25 ppm/°C over a 60°C worst displacement from 25°C.
- TLV170x 5.5 mV full-temperature offset plus 0.2 mV bias/PSRR allowance.
- Measured buffer offsets within ±5 mV each, and calibrated signal gain no less than 98% nominal.
- Measured actual selected-path zero within ±25 mV wide and ±130 mV fine, before any scope subtraction. The fine allowance includes the amplified differential buffer offsets and OPA810 offset/drift contribution.

Those conditions give calculated late-trip bounds of **1490.7 V per tip**, **1364.2 V wide differential**, and **294.3 V fine differential**. The buffer/analog-zero/gain limits are required acceptance measurements, not guaranteed by this calculation alone. Reference disturbance during clipping, comparator propagation delay and latch timing require separate tests. This is an operating-limit warning, not a safety-rated peak detector.

## Vendor-model verification

The untouched TI OPA810 Rev A model, dated 2020-06-11, is archived in `sources/OPA810-model.zip` and `sources/opa810_a.lib`. The source URL is `https://www.ti.com/lit/zip/sbomb73`. `validation/spice/sha256.txt` records its digest and the testbench inputs. The model ran successfully with ngspice 45.2 using PSpice compatibility, without modifying the vendor library.

Both gain paths, output filter, actual sense loading, R70, 1 MΩ scope and a representative lumped 120 pF cable/input capacitance are included. BUF_P/BUF_N are ideal sources; all rails are ideal **+4.8000 / −4.8068 V**. Fixed switch positions are represented by 0.01 Ω closed / 1 TΩ open contacts. These fixtures do not simulate contact transitions or bounce.

| Nominal-model result | Wide | Fine |
|---|---:|---:|
| Low-frequency gain from buffered differential input | 1.994831 | 9.974207 |
| Normalized −3 dB bandwidth | 5.5481 MHz | 5.0916 MHz |
| Phase at 35 kHz | −0.5356° | −0.6762° |
| Phase at 60 kHz | −0.9182° | −1.1592° |

The phase result makes range-specific calibration necessary even before the HV divider/buffer contribution is added. The qualification criterion remains measured residual phase after the stated correction, not an assertion of uncorrected ≤1° in both ranges.

A 60 kHz, 1500 Vpk differential-equivalent transient on the wide range overdrives the unused fine stage. Comparing that circuit against one with the fine-stage input disconnected gives a maximum modeled wide-output difference of 8.55 nV after the first 20 µs. This is only nominal model evidence for branch isolation. The model reports fine clipping around +4.925/−4.914 V, about 0.12 V outside the ideal rails: those clip levels are a model limitation, not a physical prediction or a recovery guarantee.

The fixtures exclude HV divider and ADA4817 response, real supply impedance/coupling, layout and lead parasitics, component tolerances/temperature, clamp/reference networks and switch transitions. Bench stability, CMRR, bandwidth, overload/recovery and voltage qualification remain unexecuted.

Reproduce from `instruments/differential-probe`:

```sh
ngspice -n -D ngbehavior=ps -b validation/spice/ac.cir > validation/spice/ac.log 2>&1
ngspice -n -D ngbehavior=ps -b validation/spice/unused-fine-saturation.cir > validation/spice/unused-fine-saturation.log 2>&1
rustc --edition 2021 tools/check_spice.rs -o /tmp/temper-probe-spice-check
/tmp/temper-probe-spice-check
```

Raw tables, simulator logs and `results.txt` are retained in `validation/spice/`. `make export check` regenerates the schematic exports, BOM, ERC and circuit checks. Board generation and DRC are separate integration checks.
