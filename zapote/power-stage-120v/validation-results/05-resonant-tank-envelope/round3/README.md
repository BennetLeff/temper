# Task 05 round 3 — resonant tank envelope

- **Board:** `native-15/section.kicad_pcb`, SHA-256 `a3ac1249f5052afe52944804cdc3f6ef0e8f895668360e79c1fa7b6fb7322155`.
- **Date / tools / operator:** 2026-09-27; kit commit `44417ae1489fd00e2d652fd3b2c1582b76d17630`; ngspice 45.2, Miniforge Python 3.12.12; Codex GPT-6.
- **Evidence class:** simulation/model-based for grid, shunt and trip; source audit for CDE rating; physical test required for pan/coil, hot capacitors and trip.
- **Verdict:** **BLOCKED for tank-capacitor acceptance.** The 135-case *ideal frequency-control grid* and all-gates-off trip model are complete. Exact CDE current and hot voltage limits over the actual 30.74–57.65 kHz range are unavailable; qualified board ZVS thresholds are unavailable. The grid includes requested-power states that cross A3's static protection thresholds and cannot be treated as sustained thermal operating points without dynamic timing.

## Summary

All **135/135** combinations of five pan classes, three paired L/R corners, three line voltages and three powers reached a frequency-control solution above loaded resonance and below 60 kHz. The evaluated-grid maximum is **44.696 A line RMS**, **90.617 A peak tank current**, and **822.297 V peak tank-capacitor voltage**. The maximum nominal C21/C22 share is **18.209 A RMS each**. These are grid extrema, not continuous-pan-range bounds or protected steady operation.

In the all-gates-off trip model, the 822.297 V capacitor state and simultaneous −0.272 A inductor current transfer energy through explicit idealized body-diode paths into the finite bus bank. With minimum C5/C6 and C38–C41 capacitance, the bus peaks at **273.747 V** from an initial **152.730 V**. This slightly exceeds A3's minimum *static* OVP threshold of 272.087 V, although it is below nominal 279.970 V; dynamic F3 timing belongs to B2. The residual tank capacitor is **−229.317 V at 500 µs** and the conditional 60 V bleed time is **1.362 s**.

## Method and assumptions

The `find_freq.py` search uses the starter kit's ideal square-wave R-L-C deck and the current `coil_mc.rs` pan classes. `LLOAD=70 µH × kl` is **loaded coil inductance**, the quantity that resonates with the present **0.54 µF** C21/C22/C23 bank. It is not free-air L, and historical 300 nF/88 µH design values were not imported. The five pan envelopes, their paired low/mid/high L and R corners, 108/120/140 V line and 1710/855/300 W targets yield 135 cases. The deck models the rectified 60 Hz line envelope, skin-effect R scaling, and ideal alternating diagonal bridge voltage; it omits MOSFET drops, finite dead time, phase shift and burst control. Each retained run has parameters, `.meas` results and full ngspice replay log in `outputs/runs/`. The kit model hash is `02ac6634f47c25be04e8de3c6eec4ec8cf403b659001b7f176c8f98bb6e9ce3b` and `outputs/smoke-test.txt` ends `SMOKE PASS`.

R5 lies between `leg_ret` and `hv_ret` in `frozen/default.net`; Q3/Q6 sources join `leg_ret`. During each diagonal state its signed waveform is `s(t)·i_tank(t)`, with `s` the bridge-drive sign, so its RMS equals tank RMS. During an all-gates-off dead-time interval, one high-side and one low-side body diode conduct and the low-side path still crosses R5. This topological magnitude factor is still one. The **change to the tank current waveform** caused by 348 ns finite dead time is not computed by the ideal grid. Phase-shift zero states could circulate through two low-side devices with little external R5 current, so the reported shunt value applies to the modelled frequency-control mode. `shunt_waveform.py` and `switching_events.py` use trapezoidal **time-weighted** integration on ngspice's adaptive time samples, not an arithmetic sample mean; the latter is retained only as a diagnostic.

The trip deck sets **all four gates off**, with four explicitly labelled **idealized diodes**: high-side switch node → bus and low-side `leg_ret` → switch node. It includes R5, the series pan/coil R-L, 0.54 µF tank capacitor, four 470 kΩ bleed resistors and six separate bus capacitors: C5/C6 at 2.7 µF ±5% each, C38–C41 at 0.1 µF ±10% each. The starting `Vcap`, `Itank` and bus voltage come from the **same raw point** of the grid case with maximum |Vcap|, preserving simultaneous initial energy. The three capacitance cases are 5.49/5.80/6.11 µF. The model omits rectifier replenishment, D3 clamp, MOSFET nonlinear capacitance/recovery, capacitor ESR/ESL and layout parasitics; its bus peak is therefore a lumped model result, not an upper bound on F3 overshoot. At 500 µs, residual current is negligible; the subsequent 1.88 MΩ × 0.54 µF exponential gives the time to the task's 60 V screen.

## Results

| Quantity | Evaluated result | Evidence |
| --- | ---: | --- |
| Grid count and frequency | 135 cases; 30.739–57.647 kHz | `outputs/cases.csv`, `outputs/grid-summary.json` |
| Maximum tank line RMS / peak | 44.696 / 90.617 A | `outputs/grid-summary.json` |
| Maximum C21/C22 nominal current share | 18.209 A RMS each | capacitance split 0.22/0.54 of tank RMS; `outputs/cases.csv` |
| Maximum capacitor voltage | 822.297 V peak | `outputs/grid-summary.json` |
| R22–R25 maximum per-resistor voltage / mean power | 205.574 V peak / 22.63 mW | nominal equal quarter-bank division, `outputs/grid-summary.json` |
| R5 maximum time-weighted line / ≥90%-crest RMS | 44.696 / 61.127 A; same low-coupling 108 V / 1710 W case | `outputs/shunt-grid.csv`, retained raw in `outputs/shunt/` |
| Trip bus peak, minimum / nominal / maximum bus C | 273.747 / 269.542 / 265.573 V | `outputs/trip/summary.json` |
| Trip residual tank capacitor at 500 µs | −229.317 / −215.666 / −203.147 V | same tolerance order and source |
| Trip 60 V bleed time | 1.362 / 1.299 / 1.239 s | same; post-freewheel RC extrapolation |

The trip peak changed only **0.00058%** with a 50 ns → 25 ns maximum-step refinement (`outputs/trip/timestep-check.json`). Independent time integration of pan/coil and R5 `I²R`, four diode `i·v`, tank-bleed and bus-leak powers closes the minimum-bus-cap energy balance: **0.02669809 J** storage decrease versus **0.02670142 J** integrated loss, a **3.33 µJ** difference or **0.00135%** of initial stored energy. The other two tolerance cases close within 0.002% (`outputs/trip/summary.json`). `outputs/trip/*/waveform.npz` and compressed raw ngspice files retain bus, tank capacitor, inductor and R5 waveforms.

`outputs/grid-summary.json` screens the **instantaneous** ideal-grid peak against A3's static CT range **50.558–60.014 A** and R5 OCP range **38.438–85.551 A**, with nominal values 55.165 and 60.976 A. The A3 threshold snapshot is pinned in `sources/a3-thresholds.json` and hashed in that summary. This does not model detector delay or prove which requested powers are sustainable. The grid stresses above static thresholds remain in the evidence but are not thermal duty points until A3's dynamic chain is applied.

Three unconstrained low-coupling 1710 W cases exceed the task's **88 A T1 screen**, reaching 90.617 A peak. Coilcraft's 88 A figure is a sensed-current **thermal reference**, not an absolute instantaneous peak rating; the grid alone cannot establish CT thermal failure, especially where the protection chain would interrupt the waveform.

Two unconstrained requested-1710 W, low-coupling pan cases put **202.161–205.574 V peak** across each of R22–R25 under ideal equal division. Yageo defines continuous working voltage as **DC or AC RMS** (printed p. 5); a peak above 200 V is therefore not itself a working-voltage failure. The maximum per-resistor RMS voltage is **103.133 V**, below 200 V. The largest line-averaged resistor dissipation is 22.63 mW, below half of the 0.25 W 70 °C nominal rating. Repetitive peak stress, local temperature and division error remain separate qualification inputs; the overload rating does not establish repetitive-operation acceptance.

## Capacitor-rating status

The exact [CDE 942C catalogue](sources/942C.pdf) p. 3 gives C21/C22 **10.3 A RMS** and C23 **9.2 A RMS** only at **70 °C and 100 kHz**. It gives typical ESR of 6/5 mΩ and ESL of 26/23 nH, not hot guaranteed frequency functions. Page 4's RMS-voltage curves are at **25 °C** and omit the exact 0.22 µF part. Neither exact-part ESR/DF versus frequency and temperature nor installed thermal resistance/allowable self-heating power is supplied, so `sqrt(Pmax/ESR(f,T))` and the hot `Vallow(f,T)·2πfC` term cannot be bounded. The 100 kHz current value is **not** compared directly against the 30.74–57.65 kHz grid as a pass/fail limit. `outputs/cde-rating-analysis.json` records the absent inputs and the cheapest CDE applications request.

## Sensitivity, handoff and physical checks

The 5.49–6.11 µF bus tolerance sweep moves the **lumped** trip bus peak by 8.174 V and the residual tank-capacitor magnitude by 26.170 V. Neither this three-point tolerance sweep nor the 135-point pan grid establishes monotonicity between evaluated points. The source `triply_clad_GUESS` class is an assumed pan class. Loaded coil inductance, resistance versus frequency/pan position, capacitor hot-spot temperature, bridge/dead-time waveforms and post-trip bus/tank waveforms need hardware measurement.

For B2/F3, consume `outputs/trip/summary.json` and its same-time initial state. For A6, consume `outputs/shunt-grid.csv` and only A3-approved sustainable operating cases; it reports line RMS separately from crest RMS. For B4, `outputs/switching-events.csv` supplies **91,905** ideal edges' bus voltage, current sign and magnitude; the ZVS threshold and verdict columns remain blank/`PENDING_A1`. **45,360** edges have bus voltage below A1's 120 V minimum and are explicitly marked `BELOW_A1_120V_REQUIRES_RUN`. Current A1 sensitivity failed its edge-resolution gate, so B4 also awaits B1's validated thresholds before using the 120–198 V points. Neither a constant threshold down to zero nor unvalidated interpolation is applied.

**Master-plan §5 status line:** 05 round 3 — **partial / blocked for capacitor acceptance**: full ideal grid, R5 waveform and finite-bus trip model completed; exact hot CDE current/voltage limits and qualified board ZVS thresholds remain absent, and protection timing constrains sustained operation.

## Reproduce

From `zapote/power-stage-120v/validation-plan/sim-kit`, restore the pinned vendor model (SHA above) and run `/Users/bennet/Miniforge3/bin/python3 smoke_test.py`, requiring `SMOKE PASS`. Then from this `round3/` directory:

```sh
/Users/bennet/Miniforge3/bin/python3 scripts/find_freq.py
/Users/bennet/Miniforge3/bin/python3 scripts/analyze_grid.py
/Users/bennet/Miniforge3/bin/python3 scripts/shunt_waveform.py offset_or_small_pan-low-108v-1710w
/Users/bennet/Miniforge3/bin/python3 scripts/run_trip.py
/Users/bennet/Miniforge3/bin/python3 scripts/check_trip_timestep.py
/Users/bennet/Miniforge3/bin/python3 scripts/switching_events.py
/Users/bennet/Miniforge3/bin/python3 scripts/plot_round3.py
```

The search creates 135 retained run folders and the event pass replays all 135 as raw waveforms. No board/source/placement files were changed.
