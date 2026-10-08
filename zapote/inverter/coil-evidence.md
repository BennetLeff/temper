# Coil and tank evidence — U1 in progress

The historical full-board `elec/src/main.ato` sets a 47 kHz switching point and documents dependence on a loaded inductance around 59.8 µH. Its former 150 µH free-air assumption and coupling estimate can numerically cancel to a similar loaded resonance. The project learning `docs/solutions/design-patterns/resonant-tank-only-loaded-inductance-resonates-2026-07-28.md` shows why checking only the free-air coil value gives a misleading verdict.

| Quantity | Current status | Required evidence |
| --- | --- | --- |
| Physical cooker coil geometry and build | `CUSTOM_LITZ_COIL` is a placeholder in historical source. | Winding, material, ferrite, dimensions, resistance and thermal limits for an actual part or build drawing. |
| Unloaded inductance | Historical source and research cite differing assumed/candidate values. | Measurement versus frequency and temperature for the selected coil. |
| Loaded inductance | ~59.8–59.9 µH is a consistency calculation for two historical parameter sets, not a guaranteed cooker range. | Measurements/models across approved pan materials, sizes, positions and temperature; include no-pan state. |
| Coupling and loss | Historical coupling fits are not an accepted 20–50 kHz product envelope. | Pan-dependent loss and phase data at the intended frequency/current range. |
| Tank capacitance and stress | Historical example uses 300 nF in a resonance calculation. | Exact part tolerance, RMS/pulse current, voltage and temperature at all selected points. |
| Control frequency | Historical 47 kHz is contingent on loaded-coil assumptions. | Selected operating window, start/stop behavior, ZVS margin and controller capability on the real coil/pan envelope. |

U2 can compare a modeled candidate only after these inputs are bounded. A simulation using a labeled provisional coil can explore sensitivities but cannot accept the standalone inverter's operating range.

## Historical source and status matrix

| Parameter | Source-bound value or claim | Transfer limit |
| --- | --- | --- |
| Coil construction | `elec/src/modules.ato::ResonantTank.inductor_conn` declares 88 µH ±10% and `CUSTOM_LITZ_COIL`. `docs/hardware/TANK_COIL_SPECIFICATION.md` sets a ≤200 mm flat, ferrite-backed supplier target. | No purchased coil, as-built drawing, winding/strand/ferrite, bracket gap or measured unit-to-unit spread is recorded. The declaration is an incoming target, not installed-coil evidence. |
| External comparison | The coil specification §5 reads ~87 µH unloaded and ~60 µH loaded at 40 kHz from Infineon EVAL-IHW25N140R5L Fig. 16, for one unnamed 2 kW kit coil and its vessel. The ratio is about 0.68. | Manufacturer **chart reading**, not a guaranteed value or Temper pan-set bound. It is a useful comparable application, not a selected source part. |
| Former model | Historical `main.ato`: 150 µH × 0.399 = 59.85 µH. Later candidate: 88 µH × 0.68 = 59.84 µH. The 150 µH/coupling estimates were drawn from incompatible geometry/frequency contexts (`docs/solutions/design-patterns/resonant-tank-only-loaded-inductance-resonates-2026-07-28.md`). | The products agree by compensating errors. That agreement cannot validate either factor independently. |
| Incoming reference-pan screen | `TANK_COIL_SPECIFICATION.md` requires 79.2–96.8 µH unloaded at 40 kHz, **≥53.43 µH loaded** with one identified 180–220 mm ferromagnetic pan at production gap, plus loaded/unloaded ratio ≥0.60. The floor derives from the old 44 kHz PLL minimum, 1.05 margin and 270 nF capacitance floor. | A conditional one-pan test under **old** circuit limits. It does not bound other pans, offsets, hot conditions or Rev38 operation. The ratio screen alone is insufficient: 79.2 µH × 0.60 = 47.52 µH fails the absolute loaded-L floor. |
| Tank capacitor/topology | `modules.ato` puts three parallel CDE `942C16P1K-F` 100 nF parts (300 nF total, ±10%, hence 270–330 nF) **in series** with the coil: switch node → capacitors → coil → CT → old doubler midpoint. | Candidate parts only. Rev38 has no midpoint; capacitor DC bias, voltage, RMS/pulse current and heat must be solved for the new return topology. Published 100 kHz current or old 47 kHz interpolation cannot be copied to an unmeasured waveform. |
| Old power/current | `main.ato` claims 47 kHz and 37.56 kHz nominal loaded resonance; `TANK_COIL_SPECIFICATION.md` §3/§8 quotes 20.7 A rms from an ngspice harness versus 22.5 A rms from a first-harmonic solve, and 28.7–31.9 A peak. It flags the old `LitzPad_15A` / 25 A peak declaration conflict. Its §7 says one prior pan model was ~10× under-damped and yielded 109.5 A. | Neither current nor ZVS/power is a validated Rev38 bound. Coil termination ampacity and actual model calibration are open. |

The only meaningful resonance expression for the stated simple series equivalent is `f_res = 1/(2π√(L_loaded C_tank))`. `L_unloaded` is a procurement and no-pan input, **not a substitute** for loaded inductance in a pan-heating frequency claim. L alone also cannot prove ZVS or power: loaded resistance, phase, bus waveform and commutation matter.

## Measurement campaign that can bound U2

Keep each coil revision/sample ID, pan ID, actual bracket and ferrite, gap, leads and terminals traceable. Take small-signal complex impedance or series-equivalent **L, R and phase** at 20, 30, 40, 47 and 50 kHz; then run a separately protected low-energy drive campaign for current-dependent and hot behavior. Record temperatures, current, voltage, uncertainty and instrument settings. The 1 V LCR incoming test cannot certify high-current behavior.

| Pan/build state | Required low-energy measurements | Later controlled-power evidence / purpose |
| --- | --- | --- |
| No pan, cold and hot coil; free air and installed bracket | L/R/phase sweep and fixture geometry | Bounded first pulses and no-pan phase/current; cannot infer no-pan safety from reference-pan L. |
| Reference 180–220 mm ferromagnetic pan, centered | Same sweep at measured production gap, cold and hot | Reproduce or reject the historical 53.43–65.8 µH hypothesis on **this** assembly; current, power and thermal soak. |
| Small/large and weak/strong coupling pans across allowed materials | Same sweep for each material/base thickness/diameter | Find both loaded-L extrema and damping extrema. They need not occur with the same pan. |
| Offset, lift, warped base and live pan removal | Sweep at geometric limits; log transition impedance | Peak current/capacitor voltage and detection-to-current-zero time during detuning. |
| Manufacturing and ambient corners | Multiple wound samples; cold/hot ferrite/winding and capacitor tolerance | L/R spread, coil hot spot, termination temperature and joint tolerance stack. |
| Open/short coil lead or tank capacitor, lost drive, shorted switch | Protected staged fault fixtures after analytic limits | Current interruption, voltage overshoot and energy containment independent of gate-disable assertion. |

For every row record coil/pan IDs, material, base diameter, gap/offset, winding and pan temperatures, test frequency/current, series L/R, impedance phase and measurement error. Distinguish measured minima/maxima from a model extrapolation. A no-pan state and at least one deliberately weaker-coupled pan must be included; a single favorable reference pan is not an operating envelope.

## Cases queued for U2 (not accepted operating points)

1. VB ramp from zero with inactive PWM, uncharged bootstrap and unknown but bounded initial series-capacitor voltage.
2. First permitted pulses into the least-damped **measured** state on a current-limited, bounded VB source.
3. Loaded-L minimum/maximum, loaded-R minimum/maximum and 270–330 nF historical capacitor corners, including combinations that occur on different pans; calculate phase/current/voltage for each.
4. No pan, lift and live removal; derive trip latency from switch and capacitor energy limits.
5. VB surge/ripple/sag and high/low gate-rail cases; independently assess switch voltage overshoot, reverse recovery, capacitor RMS/pulse and lost ZVS.
6. PERMIT low, stuck PWM, loss of either supply, bootstrap failure, one switch short and F2 opening while VB remains charged.

The existing ngspice harness and `main.ato` use an uncalibrated pan model and the old midpoint bus. Their numerical PASS conclusions cannot serve as independent Rev38 device-limit checks. U1 therefore yields a **measurement campaign and a parameter gap**, not a bounded product-wide `L_loaded` interval. U2 may run labeled sensitivity calculations, but part/frequency selection and U3 native construction wait for a chosen return topology, an accepted VB envelope, installed-coil/pan data and calibrated current/phase behavior.
