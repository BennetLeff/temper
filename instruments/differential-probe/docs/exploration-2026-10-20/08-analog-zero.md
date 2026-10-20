# Analog zero before range selection

Research, 2026-10-20. **Verdict: prototype one shared differential-zero control at U3’s reference arm.** It can remove the dominant differential buffer offset in both ranges and improve U6’s actual analog zero. It cannot correct individual tip-warning offsets, cancel every later-stage offset, or replace temperature qualification. No CAD/BOM changes or bench results are implied.

Basis: [Rev B circuit](../circuit-revb.md), [qualification](../qualification.md), [authoring source](../../tools/build.rs), and [exported netlist](../../validation/netlist.xml). Probe PCB SHA-256: `b0c15add2b69967cee0593962e1b3b22795725ed36ccbfc408b05c3fb4002b65`. The general hardware-baseline check separately passed 69 inputs for stage15b; that board is distinct from this probe and its stage53 application. This is a narrow architecture study, not a full electrical or manufacturing review. Existing nominal SPICE fixtures exclude ADA4817 offsets and the proposed trim; they do not validate it.

## What “±5 mV becomes ±10 V” means

Each buffer follows a 2000:1 tap. A 5 mV buffer error therefore represents 10 V at that tip. For buffer errors `eP` and `eN`, differential input error is `2000(eP−eN)`: independent ±5 mV limits permit **±20 V differential error**, not ±10 V. Ideal wide/fine output errors are respectively `2(eP−eN)` and `10(eP−eN)`, reaching ±20/±100 mV before later offsets and loading.

Keep differential error separate from common-mode offset `(eP+eN)/2`. Equal +5 mV offsets cancel in subtraction but move both U5 tip-warning readings. The [ADA4817 Rev. I](https://www.analog.com/media/en/technical-documentation/data-sheets/ADA4817-1_4817-2.pdf), Tables 1–2, gives 2 mV maximum offset at 25°C; the selected SOIC has 6 mV maximum over its full temperature range and 80 µV/°C maximum drift. Thus Rev B’s ±5 mV buffer limit is an acceptance condition, not an unconditional device guarantee. Its positive input limit is supply minus 2.8 V: at +4.8 V, a +1.5 V extended-range tap has approximately 0.5 V nominal margin.

## Why location matters

The netlist connects U5 directly to BUF_P/BUF_N. U6 senses SELECTED through R71/R72, upstream of R69/C61 and U4. Scope subtraction or adjustment after U4 cannot change either detector’s reading. Adjustment between SELECTED and U4 likewise leaves U6 unchanged. Injection at SELECTED could affect U6, but applies one fixed output correction to errors that differ fivefold between ranges; it also fights a roughly 49.9 Ω source and changes loading.

Rev B requires individual buffers within ±5 mV and measured SELECTED zero within ±25 mV wide / ±130 mV fine. Those limits support its conditional late-trip calculation. An output trim does not waive them. Correcting U5 requires per-leg correction before its sense points, or separately justified detector calibration; both are larger changes requiring new budgets.

## Minimal useful architecture

Replace only the grounded end of U3’s noninverting 998 Ω arm, R63+R64, with a quiet, buffered `VZERO`. Retain both 499 Ω input arms and both 998 Ω gain arms. For an ideal low-impedance reference:

`RAW_OUT = 2(BUF_P−BUF_N) + VZERO + 3·Vos(U3)`.

This control precedes both gain paths. U12 multiplies the corrected RAW_OUT by five, so both selected outputs and U6 benefit. U12’s own offset and U4’s downstream offset remain independent; exact zero in both ranges with one knob is generally impossible.

Use a provisional **±30 mV reference span**, not a pot across the signal. Qualified buffer offsets demand ±20 mV RAW_OUT correction. [OPA810 Rev. E](https://www.ti.com/lit/ds/symlink/opa810.pdf), §6.5, specifies 500 µV maximum SOIC offset at 25°C and 10 µV/°C maximum drift; U3’s noise gain is three. A conservative 60°C displacement gives `20 + 3(0.5+0.6) = 23.3 mV`, leaving 6.7 mV trim margin. This is conditional arithmetic, not a tolerance-complete guarantee at the actual ±4.8 V rails. U12 has noise gain five; U4 has unity noise gain.

Target ≤100 µV repeatable adjustment at VZERO: approximately 0.1 V input-referred and 0.5 mV fine-output adjustment. A 60 mV span needs at least 600 distinguishable settings. Allocate, for example, ≤1 mV RAW_OUT reference drift across the temperature excursion; over 60°C that is ≤16.7 µV/°C including reference, divider and buffer errors. Buffer drift still remains: a room-temperature zero cannot promise this overall stability.

## Noise, failure and loading constraints

Generate the small bipolar span from quiet references with fixed attenuation, filter the control, then buffer it. Do not load the existing clamp references without analyzing their disturbance during overload. Keep pot wiring behind the low-voltage shield. Arrange a fixed default return and bounded endpoints so an open wiper approaches a defined small correction rather than a rail; prove startup and open-component behavior. Any filter capacitance at a buffer output needs stability assessment.

Reference source impedance adds to the 998 Ω arm and spoils resistor-ratio matching. First-order analysis gives common-mode feedthrough approximately `0.000668·Zref` V/V, with Zref in ohms. Restricting this contribution to one tenth of a 60 dB CMRR error budget requires approximately **|Zref| ≤0.30 Ω** across the measurement band; parasitic capacitance also matters. Reference noise appears once at RAW_OUT and five times in fine range. A prototype target of <1 nV/√Hz at RAW_OUT in-band corresponds to <1 µV/√Hz input-referred; measure broadband and low-frequency noise separately. Preserve gain, thermal symmetry and RF return geometry.

## Next test and acceptance

Short both tips to earth, warm up, then measure BUF_P, BUF_N, RAW_OUT, SELECTED and BNC output in both ranges before scope subtraction. Sweep trim endpoints, supplies and temperature; inject open-wiper/default faults. Confirm the existing three offset acceptance limits, both polarities of all warning thresholds, gain/phase, noise and tied-tip CMRR with the shield fitted. Repeat overload/recovery and unused-fine-stage saturation tests. Check every amplifier’s input/output headroom throughout the extended envelope; zeroing millivolts does not recover a saturated stage. Retain one control only if both ranges meet measured residual-zero requirements without degrading CMRR or warning margins.
