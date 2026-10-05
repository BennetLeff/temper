# D-22 method and scope of the evidence

Base revision: `fda5ab9ece24ef1ee6f2317604c5ca73367d5201`, branch `codex/power-stage-120v-build`. The baseline circuit is D-19's `periodic-sweep.cir`. Its matrix, component values, vendor device model, temperature, sources, operating point and initial conditions are unchanged. The two leg instances both use the **leg-A** matrix, as in D-19: this is not an independent leg-B/cross-leg model qualification. No hardware, firmware, board or netlist has been edited.

## Source reproduction and numerical changes

`reproduce.py` executes D-19's original runner at 170 V / R=2 Ω / ESL=1.06 nH, 35 kHz with 0.5 ns maximum step and 24 cycles, then 60 kHz with 2 ns and 48 cycles. It compares the complete complex source FFTs against D-19. Both were bit-identical (`reproduction.json`) **before** numerical diagnostics began. The same baseline script retains the original two-pass measurement/ASCII-raw workflow.

`periodic.py` then uses a single binary-raw pass to avoid running every case twice. Completed runs require the requested final time and two full final cycles, finite samples and nondecreasing time. A relative RMS difference below 0.1% between the last two cycles is the first settling screen, not the full spectral convergence test. It saves both cycles' complex FFTs. Its shared settings are D-19's Gear method, `reltol=1e-3`, `abstol=1e-9`, `vntol=1e-6`, `itl1=500`, `gmin=1e-10`, with D-14/D-19's explicit **`.options itl4=100000`** override retained. Maximum timestep is the campaign variable; altered settings in the diagnostic screen are listed separately in each result's identity.

`diagnostic.json` records a short startup/commutation screen on two failed D-19 configurations. This screen cannot qualify settled emissions. Smaller steps completed its windows; tighter `reltol=1e-4 trtol=1` aborted; `itl4=1000000` reached the declared 600-second timeout. The abort location (bus or an internal body-diode node) alone does not identify a defective component. No added numerical shunts, altered GMIN, damped physical parts, model edits, supply ramp, initial-condition override or changed gate waveform was used to obtain source completion. See [ngspice 45 manual, pp. 315–318](https://ngspice.sourceforge.io/docs/ngspice-45-manual.pdf) for numerical option definitions.

Each periodic result records all case parameters, exact generated deck, vendor hash, common-options hash, simulator-binary hash, elapsed time and process outcome. Aborted, timed-out, incomplete and unsettled runs remain in the evidence and have **no qualified margin**. Changing a cache's inputs raises an error rather than reusing its output silently.

The full envelope is 170/198 V × 35/60 kHz × R=2/100 Ω × ESL=1.06/10 nH. R=100 Ω is the inherited light-load diagnostic. These are fixed RLC scenarios, not a measured pan or a validated 1.8 kW controller operating map. At 170 V / 60 kHz / 1.06 nH / 0.5 ns, the estimated input power is 104.68 W for R=2 Ω and 295.84 W for R=100 Ω (`periodic-runs/*/result.json`): the inherited “light-load” label is not a monotonic power label across frequency. The 15 A RMS input check is a separate component-sizing requirement; it is not inferred from these simulated tank powers.

## The 6.72 dB issue and settling

`resampling.py` reprocesses the same D-19 raw captures on 32768-, 131072- and 524288-point periodic grids. Increasing the FFT interpolation grid sixteenfold leaves the 60 kHz / 2 ns versus 0.5 ns discrepancy at **6.7213 dB**; the largest individual resampling change is **0.0373 dB**. The discrepancy is therefore not resolved by increasing the FFT grid. It occurs near 29.76 MHz, at appreciable receiver levels, and cannot be dismissed as a cancellation line far below the limit.

Subsequent comparisons use 524288 samples and complex source phase, with exact AC solves at every switching harmonic. `numeric_compare.py` compares each LISN terminal separately through the same transfer function. It checks original nominal/combined filters and proposed-filter sensitivities. A terminal-wise comparison can be slightly larger than D-19's comparison of the larger terminal at each frequency; that is not inconsistent.

`NUMERICS.md` states the predeclared 0.2 dB target for lines within 40 dB of the AV limit. For weaker lines the script checks complex voltage difference relative to that floor, avoiding an uninformative relative error at a near-zero line. It records every line, including failures. The last-versus-prior-cycle comparison uses the same criterion, so a passing time-domain RMS settling screen cannot conceal spectral drift. Finite refinement agreement is numerical evidence, not a mathematical error bound.

## Receiver, modes and detector interpretation

The round-3 LISN, PE bond, rectifier, coil-to-PE, tab-to-heatsink and original filter models are retained. The receiver is **`v(lisn_l)-v(pe)` and `v(lisn_n)-v(pe)`**. D-19's switch-node voltage sources and bus-current source are combined coherently; their powers are not added as if independent noise. Peak Fourier coefficients become RMS voltage by dividing by √2.

For complex terminal voltages L and N, CM=(L+N)/2 and DM=(L−N)/2. The **total terminal voltage** is judged against the limit; independently reported mode minima must not be subtracted or treated as separate compliance results. Terminal cancellation in one condition does not establish immunity to asymmetry.

The detector estimates assume indefinitely periodic fixed-frequency operation, isolated harmonics and an ideal 9 kHz receiver channel. At 35/60 kHz harmonic spacing the ideal channel contains at most one line; the envelope of that line is constant, so a calibrated QP and AV detector give its CW RMS level. This is a **CW-equivalent QP/AV estimate**, not a time-domain CISPR receiver simulation. The sinusoidal-detector equivalence is described in Rohde & Schwarz, *Spectrum Analyzer Measurements*, application note 1MA201_9e, p. 28 ([source](https://www.rohde-schwarz.com/tr/file/1MA201_9e_spectrum_analyzers_meas.pdf)). Mains modulation, startup, bursts, jitter, frequency updates, actual IF selectivity and receiver dwell can change the result and require receiver measurements.

Task 07's limits are [47 CFR §18.307(a), (e), (g)](https://www.ecfr.gov/current/title-47/chapter-I/subchapter-A/part-18/subpart-C/section-18.307), using the tighter boundary value and [§18.301 ISM-band exclusions](https://www.ecfr.gov/current/title-47/chapter-I/subchapter-A/part-18/subpart-C/section-18.301). In the requested band:

| Frequency | QP dBµV | AV dBµV |
| --- | ---: | ---: |
| 150–500 kHz | 66→56 logarithmically | 56→46 logarithmically |
| 500 kHz–5 MHz | 56 | 46 |
| 5–30 MHz | 60 | 50 |

Raw line CSVs retain the excluded frequencies with a `regulated` flag. Margin minima use only regulated lines. The scope begins at 150 kHz; the separate lower-frequency induction-cooker limits are not assessed here.

## Transfer and physical qualifications

`qualify_filter.py` solves every harmonic directly, including the below-150-kHz harmonics needed for loss estimates. It checks component tolerance, old/new choke inductance, differential leakage, coil coupling, asymmetric tabs, capacitor ESL/ESR, winding capacitance/loss, resistor ESL and PE-bond sensitivity. `filter-scenarios.json` is the complete finite grid. Typical RF fits and exploratory parasitic ranges are estimates, not guaranteed manufacturer bounds or an exhaustive tolerance proof. The inherited [round-3 choke fit](../../../../07-conducted-emi/round3/outputs/tdk_choke_fit.json) converts the parallel-winding curve to per-winding parameters; extending that simple RLC fit to 30 MHz remains physically unqualified.

The source and AC receiver are a **one-way model**: the proposed filter does not feed back into the nonlinear switching circuit. Rectifier conducting state and junction capacitance are fixed, and the manufacturer's 4 V junction-capacitance point is not a qualified 170/198 V value. Common-mode coupling, physical Y return geometry, fan supply emissions and the eventual enclosure remain unmeasured. The damped passive-port calculation does not qualify input-filter/control-loop interaction. These limits remain even if every source run and numerical comparison passes.

`replay.py` independently reconstructs FFTs from every completed binary raw capture and optionally reruns the stored final AC decks (`--ac`). Unit tests reject truncated capture/time windows and verify phase interference and PE-reference invariance. The licensed vendor library is restored only with the approved fetcher and smoke test; it is absent from committed evidence.

Runtime accounting uses Python `time.monotonic()` for each attempt and the subprocess timeout. It is not a CPU-time measurement or a promise of calendar duration across host suspension. Native ngspice timing output is retained verbatim and can use a different clock.
