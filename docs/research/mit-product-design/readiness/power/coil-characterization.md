# Coil and cookware characterization — draft test brief

**Status: NOT RUN.** First obtain or make an unpowered coil/ferrite/glass fixture. This brief defines data needed for design decisions; it does not authorize energizing an open cooker. An engineering owner must review hot-fixture handling and any subsequent high-energy station.

## Define the specimen and fixture

Record coil serial/lot and vendor drawing; winding outer/inner diameters, turns, litz construction, lead length/dressing, terminal construction, measured DC resistance, ferrite material/placement and retention, support plate, glass thickness and all nearby conductive structure. Photograph and dimension the stack. R4's current CAD candidate has 200 mm coil OD, nominal 3 mm coil-top-to-glass-underside gap and 4 mm glass; **these are nominal geometry assumptions, not a selected coil or tolerance guarantee**. Actual coil/gap/manufacturing limits must be supplied by the mechanical and coil owners. Do not quietly reuse the former mistaken 1 mm gap.

Use nonconducting position references to repeat centered and offset pan positions. Record both radial directions; an asymmetric ferrite/support layout can make them differ. Record measured gap and placement uncertainty at each configuration. Re-seat the coil and pan for repeat measurements so fixture repeatability is visible.

Use a calibrated impedance analyzer or LCR instrument supporting **complex impedance at 20, 30, 40, 50 and 60 kHz** and open/short compensation at the coil terminal reference plane. Add a denser sweep around observed resonance or rapid impedance change; do not infer a valid control range from five isolated points. Capture instrument model/serial/calibration date, fixture/cable ID, compensation file, test voltage/current amplitude, frequency accuracy and impedance uncertainty. Save raw `R + jX` data; reported equivalent series L is `X/(2πf)` only where that representation is valid. A four-wire DC resistance instrument and independent temperature probes complement the AC measurement.

## Minimum useful matrix

| Axis | Initial proposed samples | Why |
| --- | --- | --- |
| Cookware | No pan; at least one identified cast iron, carbon/430 steel, clad/tri-ply, low-resistance compatible pan, and smallest intended pan | Distinguish the five modeled classes; clad currently has no measured anchor. This is discovery, not a market-wide sampling plan. |
| Position | Centered; +30 mm X and +30 mm Y offsets; intended edge-of-detection boundary once defined | Check reduced coupling and asymmetry. The 30 mm positions are characterization probes, not an allowed-use claim. |
| Stack | Nominal and mechanical minimum/maximum gap once approved | L and reflected loss depend on the complete stack, including glass and ferrite. Leave unapproved endpoints blank. |
| Temperature | Room temperature with actual value; controlled warm/hot endpoints approved for each specimen and fixture | The operating-temperature requirement is not finalized. Do not invent a safe hot temperature from a room-temperature measurement. Record coil, ferrite and pan temperature separately and time-align them. |
| Repeat | Three independent pan re-seats at the nominal stack as an initial repeatability check; increase sample/lot count when variance is known | A screening repeat is not process capability or qualification. |
| Frequency/amplitude | Five frequencies above plus local detail; at least two instrument-supported small-signal amplitudes | Detect amplitude dependence and fixture artifacts; low-energy tests do not predict full-power saturation automatically. |

`coil-runs.csv` records the specimen and setup once per run; `coil-points.csv` records each measured point. Both are empty templates: blank values mean unmeasured. Never insert nominal CAD values into measured columns. Use stable IDs for raw files and their SHA-256 digests; retain uncompensated/compensated exports and instrument settings.

## Analyze without overstating the result

1. Plot raw complex impedance versus frequency and amplitude with uncertainty for each configuration. Investigate discontinuities and any change comparable to instrument or fixture uncertainty before fitting a model.
2. Record no-pan winding/ferrite/fixture losses at matching frequency and temperature. `R_loaded − R_no_pan` is an **apparent reflected-loss estimate**, not an independent measurement of pan-only heating: ferrite/coil loss can change under a pan. State this limitation when constructing priors.
3. Report measured `L_loaded/L_no_pan` and apparent resistance ratios only for matched configurations. Turn-count scaling is a hypothesis; changed diameter/winding/ferrite/gap requires remeasurement.
4. Fit parameters and reserve measured configurations for correlation checks, including at least one offset/clad case. A model passes a correlation check only against a predeclared engineering error allowance with uncertainty; an arbitrary post-fit tolerance does not validate it.
5. Re-solve actual power points with bank/part limits and separate input, tank and pan power. Carry forward current/protection uncertainty; do not change OCP or selected parts from a ranking alone.

Before a later powered campaign, the engineer must select isolated voltage/current probes for expected common mode, bandwidth and fault transients; calibrate phase/delay between channels; provide hardware energy limiting and remote shutdown; and define an uncertainty budget. Measurements must capture actual tank peak/RMS, R5 current waveform, individual capacitor branch current and voltage, all switch VDS/VGS, power and temperature together. The parent qualification packet owns the electrical safety procedure and equipment acceptance.
