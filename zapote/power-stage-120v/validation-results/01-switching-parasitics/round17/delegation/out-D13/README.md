# D-13 — switching at hot junction

**Hot switching changes the nominal-model verdicts and destroys 307 ns S1 ZVS at 150 °C; 1.9 V remains conservative relative to the typical-model threshold but cannot be relaxed on that basis, F7 still fails S4, and F6 at 150 °C is numerically indeterminate.**

## Results

The main campaign completed **278 of 336** runs; **58 are indeterminate**: both baseline 150 °C S4 DIR1/ESL10 points (348/443 ns), and all 56 F6 150 °C points. Counts below exclude indeterminate runs from every pass/fail calculation. Full individual cases and all dead-time rows are in [TABLES.md](TABLES.md); machine-readable results are in `summary.json` and `decisions.json`.

| remedy / nominal DT | Tj °C | attempted / indeterminate | max off V | model / 1.9 V off failures | max die VDS V | nominal S1 ZVS |
|---|---:|---:|---:|---:|---:|---:|
| baseline / 348 ns | 27 | 20 / 0 | 4.523586 | 4 / 20 | 511.1413 | 12/12 |
| baseline / 348 ns | 100 | 20 / 0 | 4.480325 | 7 / 20 | 512.8953 | 12/12 |
| baseline / 348 ns | 150 | 20 / 1 | 4.440149 | 15 / 19 | 513.7754 | 12/12 |
| F6 / 348 ns | 27 | 20 / 0 | 0.511685 | 0 / 0 | 482.2470 | 12/12 |
| F6 / 348 ns | 100 | 20 / 0 | 0.283947 | 0 / 0 | 474.8672 | 12/12 |
| F6 / 348 ns | 150 | 20 / 20 | — | no verdict | — | — |
| F7 / 443 ns | 27 | 20 / 0 | 4.182724 | 4 / 4 | 510.9661 | 12/12 |
| F7 / 443 ns | 100 | 20 / 0 | 4.134434 | 4 / 4 | 512.1218 | 12/12 |
| F7 / 443 ns | 150 | 20 / 1 | 4.101881 | 3 / 3 | 513.0911 | 12/12 |

All completed main cases satisfy the applicable die-VDS screen (520 V for S1/S4, 585 V for S2) and ±30 V dynamic gate screen. This does not rescue off-gate or missing-result failures. F6 at 27/100 °C passes all three off-gate comparisons across all 112 attempted cases at those temperatures; the 150 °C run supplies no F6 verdict.

Against the measured threshold at each temperature, 3 matched baseline verdicts change from pass to fail at 100 °C and 12 at 150 °C. At 150 °C these are eight nominal S1 and four nominal S2 points. All twelve S1 307 ns points also lose ZVS at 150 °C; nominal 348/443 ns retains it. The fixed 1.9 V screen changes no verdict in the matched completed temperature pairs. These are derived in `temperature-comparison.json`.

At 150 °C, among 54 completed baseline cases, the typical-model screen rejects 34 and 1.9 V rejects 38. Thus 1.9 V is stricter for four observed cases; none passes 1.9 V while failing the typical-model screen. Conversely, 3.0 V rejects only 26, admitting eight cases that fail the typical-model hot judgement. **This establishes conservatism only relative to the nominal model**, not to the device population. The nominal-model screen is 2.487940 V at 150 °C, while the 1.9 V rule deliberately starts from the lower datasheet minimum.

F7 fixes the completed S1/S2 off-gate cases at 443 ns, but every completed S4 case still fails all three off-gate screens: 4/4 at 27 °C, 4/4 at 100 °C, 3/3 at 150 °C plus one indeterminate case. It is not a universal S4 remedy. The Eoff/Eon/EΣ observations are tabulated per case in `TABLES.md`; they are overlap proxies, not an efficiency qualification.

## Method and temperature mechanism

This is a simulation study on the unchanged `d2/legA-h0-best.matrix.txt` four-port FEM matrix. The source revision is `a5eddd2bec65d0dd026bdd47087947b0b22cbfd6`. No board, shared deck, vendor model or solver option was edited. `run.py` copies D-6's `baseline.cir` and `off1_c1_neg2.cir` into `decks/` and adds `.temp {TJ}` after the generated parameter include. The latter is F6: nominal 1 Ω discharge path, ideal 1 nF external Cgs, stiff −2 V off bias and +15 V on drive; the generic diode, its finite drop, and omitted new layout parasitics remain D-6 assumptions.

The hash-checked Infineon CFD7 library, version 1007 dated 2022-10-27, defines `IPW65R018CFD7_L1` at lines 308–324. Line 322 drives the internal junction node from the simulator's `TEMP`, referenced to node `w`, which line 323 ties to ground through 1 µΩ. Lines 311–312 feed that temperature to both technology-model temperature inputs and set `heat=0`: this is an imposed, uniform junction temperature, without self-heating. The channel equation at lines 147–150, epi resistance at 152–155, and diode series resistance at 158 explicitly use that temperature; the body diode at 156–157 also uses simulator device-temperature behavior. The explicit charge/capacitance equations at 130–145 have no direct temperature argument, so the brief's blanket statement that all capacitances change with junction temperature is too broad. Voltage trajectories and effective switching charge can change without an explicit capacitance temperature coefficient. The added F6 generic diode also sees `.temp`; linear components without temperature coefficients and the idealized driver do not acquire physical thermal behavior.

`provenance-*.json` records the complete model, matrix, deck, runner and options SHA-256 values, source revision, executable version and invocation. The exact source used for the main and threshold campaigns is retained in `runner-main-executed.txt`; `run.py` differs only by import ordering and a dictionary-literal lint fix. The refinement provenance identifies the updated entrypoint. Every retained ngspice log confirms `TEMP` at the requested value; the default `TNOM` stays at 27 °C. `fetch-models.log` records the prescribed archive/library hash checks, and `smoke-test.log` records the sim-kit smoke pass. No licensed vendor contents are committed.

The main campaign has 336 transients: baseline and F6, each at 27/100/150 °C, both directions, ESL 1.06/10 nH, S1 at 170/198/280 V and 37 A plus S2 at 280 V and 71 A at 307/348/443 ns, and S4 at 198 V and −20 A at 348/443 ns. The additional S4 443 ns points make F7 directly comparable: F7 is the baseline topology at 443 ns, not an independent duplicate simulation. F6 is additionally evaluated at 443 ns to retain a matched remedy/dead-time comparison. These are commanded deck separations, not guaranteed hardware minimum dead times.

`results-main.json` and `TABLES.md` contain individual die VDS, off-gate, incoming-device VDS/ZVS and energy observations. The energy definition is inherited unchanged from D-6: integrate positive die VDS times die terminal current over the outgoing interval T1…T1+DT and incoming interval T1+DT…T1+DT+0.75 µs. Eoff and Eon select the respective devices; EΣ includes both devices over both intervals. The current comes from the model's drain resistor (74.4 µΩ, library lines 309/315). This is an overlap-energy proxy including capacitive and diode terminal current plus conduction tails, not measured switching heat or full-bridge efficiency. Different DT values also change the first integration window.

## Threshold interpretation

`decks/threshold.cir` reproduces D-6's diode-connected DC condition, VDS=VGS and ID=2.91 mA, using the unmodified nominal model. `results-threshold.json` gives:

| imposed Tj °C | model VGS(th), V | model VGS(th) − 0.5 V |
|---|---:|---:|
| 25 | 4.062434 | 3.562434 |
| 27 | 4.045527 | 3.545527 |
| 100 | 3.424901 | 2.924901 |
| 150 | 2.987940 | 2.487940 |

The model-relative criterion is strictly `off_V < measured model threshold − 0.5 V`; the same observations are also judged against strict 3.0 V and 1.9 V screens. These are intentionally different comparisons. The 1.9 V screen in [D-6](../out-D6/README.md#criterion-at-hot-junction) starts from a 3.5 V datasheet minimum at 25 °C and subtracts a typical-model thermal shift and 0.5 V allowance. Our nominal model starts at 4.062434 V at 25 °C, so a hot-model pass cannot establish that the minimum-based screen is unnecessarily strict for production devices. Neither extrapolation is a guaranteed hot minimum, and a milliampere DC threshold does not itself establish destructive shoot-through onset.

## Numerical controls and raw evidence

Solver settings remain Gear, reltol=1e-3, abstol=1e-9, vntol=1e-6, itl1=500, itl4=200, gmin=1e-10, PSpice compatibility `psa`, with 0.2 ns maximum timestep. The separate D-14 solver work is not incorporated. The refinement subset repeats high-bus S1, S2 and S4 at 348/443 ns, both directions and all temperatures/remedies, ESL 10 nH, at 0.1 ns maximum timestep: 72 attempts. Any aborted, incomplete, missing-measurement or timeout run is indeterminate and receives no pass.

`raw/<case>/run.log`, `params.inc`, `.spiceinit` and `result.json` retain raw simulator output and exact inputs; the canonical deck is in `decks/`. These are raw measurement logs, not waveform exports. `analyze.py` verifies counts, per-run result equality, finite metrics and simulator temperature receipts, then emits summaries, original-grid reproduction, temperature changes and refinement comparisons. The 88 original main/refinement aborts are listed in `indeterminate.json`. The raw tree is preserved locally and committed as `raw-evidence.tar.gz`; `raw-evidence-sha256.json` gives every relative member and its SHA-256. `pack.py` rejects vendor files and symlinks and verifies every archived byte. To inspect a fresh checkout, run `tar -xzf raw-evidence.tar.gz` in this output directory before `analyze.py`.

The 27 °C baseline reproduces all 56 matching `grid-best`/`grid-best-longdt` rows: maximum absolute differences are 0.000002 V off-gate and 0.0006 V die VDS, with every ZVS classification unchanged (`baseline-comparison.json`). This includes the original-grid cases at 307/348 ns and the newer 443 ns cases.

The half-step subset completes 42 of 72 attempts; 30 are indeterminate. Forty pairs complete at both steps, with maximum absolute changes 0.01094352 V off-gate, 2.1584 V die VDS and 0.18393183% EΣ; all three off-gate criteria, VDS, gate rating and ZVS verdicts agree. The remaining two successful fine-step runs are the baseline hot S4 cases that aborted at 0.2 ns. Their successful finer runs are retained separately and do not overwrite the primary failures. **Full timestep convergence is not established**, especially for F6 at 150 °C (`refinement-comparison.json`).

Four separately identified exploratory probes test whether D-14's iteration-cap idea transfers to hot F6: S1 198 V/37 A and S4 198 V/−20 A, DIR0, DT348 ns, ESL10 nH, Tj150 °C, at itl4=1000 and 10000. **All four still abort.** Only the Newton iteration allowance changes; no tolerance or circuit change is made. `exploratory.py`, `provenance-exploratory.json`, `results-exploratory.json`, separate decks and logs retain these observations. They do not qualify a solver setting or replace the original campaign. Main F6 hot failures name the generic discharge diode; diagnosing that model/solver interaction remains necessary before claiming hot F6 performance.

## Reproduce

From the repository root, using ngspice 45.2 on PATH and the Miniforge Python environment:

```sh
zsh zapote/power-stage-120v/validation-plan/sim-kit/models/fetch_models.sh
/Users/bennet/Miniforge3/bin/python3 zapote/power-stage-120v/validation-plan/sim-kit/smoke_test.py
cd zapote/power-stage-120v/validation-results/01-switching-parasitics/round17/delegation/out-D13
/Users/bennet/Miniforge3/bin/python3 run.py --mode threshold
/Users/bennet/Miniforge3/bin/python3 run.py --mode main --workers 2
/Users/bennet/Miniforge3/bin/python3 run.py --mode refine --workers 2
/Users/bennet/Miniforge3/bin/python3 exploratory.py
/Users/bennet/Miniforge3/bin/python3 analyze.py
/Users/bennet/Miniforge3/bin/python3 pack.py
```

The runner performs fresh simulations and overwrites the requested campaign's own outputs. Restore the model first: no licensed copies are retained in run directories. No Rust extension or board rerun is needed for these simulations.

## Limits

The results apply to this matrix, nominal vendor device, imposed temperatures, idealized driver and remedy circuitry. They do not include process corners, actual hot driver impedance, separate device temperatures, thermal runaway, newly routed F6 mutual inductances, real negative-bias startup behavior, or measured recovery qualification. The FEM crop/extrapolation assumptions and missing bulk-to-gate couplings remain inherited uncertainties. A passing finite case set is not a continuous operating-region bound. The guaranteed hot-threshold and bench qualifications identified by D-6/D-8 remain open.
