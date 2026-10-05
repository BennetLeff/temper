# Resonant bank and power-model correction

**2026-10-04 reconciliation:** this record documents the initial correction.
The [power readiness review](../readiness/power/README.md) subsequently checked
the separate shunt detector: its conditional static range is 38.44–85.55 A at
+85 °C board with an assumed +50 °C R5 rise, while the broader CT calculation
gives 50.56–60.01 A. The 45 A screen below is retained for historical numerical
comparison only. It is not a demonstrated normal operating range. The two
detectors see different waveforms, so static threshold comparison also does
not predict the complete dynamic trip response.

**Scope and source.** The seven files in `docs/hardware/power-section-120v/` were copied from `worktrees/ps-oracle` at `fda5ab9ece24ef1ee6f2317604c5ca73367d5201`, then corrected here. The actual source concept remains `zapote/power-stage-120v`: a full bridge of four single IPW65R018CFD7 switches and a 0.54 µF series bank of two 942C12P22K-F and one 942C12P1K-F. The copied historical half-bridge and 600 V rows are alternatives, not the selected BOM.

## Reproduced defect

The prior `coil_mc.rs` treated 650 V capacitor line-crest peak as a passing constraint and printed `unsafe_any_pan_pct = 0.0`. It assigned 17.5 mΩ hot to each full-bridge switch position, a value derived from **two** parallel 600 V devices while the selected bridge has **one** 650 V device per position. Its 114 V best full bridge was 45 µH/42 kHz with 88.5% median modeled efficiency; the provisional 70 µH class was described as ~87.9% efficient. All of those were conditional model numbers, not demonstrated hardware limits.

The [CDE 942C catalog](https://www.cde.com/resources/catalogs/942C.pdf), PDF p. 3, lists the selected 0.1 and 0.22 µF 1200 Vdc variants at **430 Vac at 60 Hz**. PDF p. 1 gives the 60 Hz catalog basis and temperature derating above 85 °C; p. 4 supplies frequency curves at 25 °C for other capacitance curves (0.1, 0.33, 0.9 µF). Those pages do not supply a verified assembled-bank voltage/current/temperature limit for the selected 0.22 µF elements at hot 30–50 kHz. Thus 650 V is not a legitimate pass/fail bound. For scale, 650 V crest corresponds to 459.6 V RMS for a constant-amplitude carrier sine at the line crest, versus 325 V estimated line-cycle RMS with the model's ideal rectified-sine envelope. Neither is an allowable operating rating at the actual frequency.

## Corrected behavior

`coil_mc.rs` now labels the 650 V threshold as an **unqualified comparative screen** and removes the `unsafe` field and claim. It calculates line-crest capacitor voltage and idealized line-cycle AC RMS at operating points. It models four single 650 V switches with a provisional **35 mΩ hot per position** proxy, without calling that resistance a verified selected-part limit. It reports a selected 70 µH / 0.54 µF point and enumerates 160 simultaneous parameter endpoints for each of 108, 114, 127 and 140 V RMS line. These are deterministic probes over assumed bounds; they do not establish a physical worst case.

**Initial parent verification found another consequential stale assumption:** the model's 85 A peak allowance exceeded native-18's older documented 50.93–59.51 A CT trip band. A 140 V carbon/steel probe (`L0=70 µH`, `kL=0.80`, `r40=0.029 Ω/µH`, `q=0.0015 Ω/µH`, `C=0.54 µF`) claimed full power at **61.64 A peak**. The regression test failed before correction. The initial correction used **45 A**, copied from the circuit source's normal-operation comment. The subsequent shunt reconciliation above establishes that this is only a historical comparative screen, not a supported controller allocation. The previous inference that it resolved compatibility with the protection architecture is withdrawn; no firmware limit has been changed.

With that correction, at 114 V the selected point reports **14.8% modeled full-power among assumed intended-pan draws**, **88.7% median efficiency among those full-power draws**, 401 V p95 capacitor line-crest peak and 200 V estimated switching-ripple line-cycle RMS. At 127 V: **4.3%**, 88.2%, 400 V and 200 V. The best sampled grid point moves to 140 µH/22 kHz (82.0% at 114 V); it is an alternative to investigate, not an approved coil replacement. Endpoint full-power counts are **25/160, 20/160, 12/160, 5/160** at 108/114/127/140 V. Conditional maxima exclude reduced-power cases and faults, so they are not bounds on actual bank stress. Do not raise OCP thresholds merely to recover the former model pass rate. Measure real coil/pan impedance and reconcile the power requirement first.

The `power_section.rs` B1 row still gives 25.4 W bridge loss on the inherited 35 mΩ proxy. It uses different fixed coil/pan assumptions and cannot override the current D18 cooling allocation or the new model's power limitation.

For the **three parallel capacitors**, an ideal sinusoidal current divider gives each 0.22 µF element 0.22/0.54 = 40.7% of bank current, and the 0.1 µF element 18.5%. At B1's modeled **18.7 A tank RMS**, that is 7.62 A, 7.62 A and 3.46 A. Enumerating independent ±10% capacitance endpoints, the maximum share of either 0.22 µF branch is 0.242/(0.242+0.198+0.09) = 45.7% or **8.54 A** at the same bank current; the maximum 0.1 µF share is 0.11/(0.11+0.198+0.198) = 21.7% or **4.07 A**. This is an arithmetic sensitivity probe only. Actual high-frequency ESR/ESL, conductor geometry, heating, frequency-dependent capacitance and waveform harmonics can redistribute current; B1's 18.7 A itself is a nominal proxy, not a high-line/current extreme. Every parallel element sees essentially the bank voltage in the ideal model.

The result is a corrected **decision status**: the selected capacitor bank and switch losses are **unqualified**. Do not use the Monte Carlo ranking or old 650 V screen for BOM release, PCB release, cooling signoff or firmware protection limits.

## Closure evidence required

1. Obtain CDE's allowable continuous voltage, RMS current, pulse/reversal and case-temperature envelope for **both exact part numbers** at the actual waveform and 20–60 kHz operating range. Confirm parallel current sharing and thermal mounting conditions. If the bank fails that envelope, change the bank or the permitted control range and rerun the model.
2. On the selected coil and intended cookware, measure L and R versus frequency, pan offset and temperature. Run a validated waveform model at low/high line, startup, detuning, pan removal, deep phase shift, shutdown and relevant control faults.
3. On a guarded prototype, measure each capacitor element's voltage, RMS ripple current and case temperature, and each switch's actual current, VDS/VGS transients and heat across those corners. Compare to verified part limits with an explicit margin.

The model correction is complete. Component qualification cannot be closed from source alone.

## Reproduction

Standalone `rustc --edition=2021 --test` checks: original `coil_mc.rs` 6/6, corrected **11/11**; corrected `power_section.rs` **6/6**. The new high-line/current regression was observed failing before the 45 A correction. The historical half-bridge test was updated to reject its old 85 A-dependent full-power expectation; a selected full-bridge/cast-iron case still passes. `rustc --edition=2021 -O` regenerated the text outputs with default seed `20260925` and 20,000 samples per detailed run. These checks validate arithmetic and report identity; they do not validate the physical assumptions.
