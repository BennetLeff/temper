# LMR51430XDDCR behavioral model: measured audit

Date: 2026-09-09. **Exploratory, not a qualified device model or hardware result.**
Luna authored and independently reviewed the model; the host corrected defects,
ran the simulations, and owns these measurements. The source is
[TI SLUSEF4A Rev. A](https://www.ti.com/lit/ds/symlink/lmr51430.pdf)
(November 2022), retained as `sources/ti-lmr51430.pdf`.

The final model regulates through its external feedback divider and draws its
power from VIN. The independent 3.314932 V divider calculation agrees with the
3.314861 V nominal simulation. The separate TI example produces 4.978407 V
against its divider's 4.979562 V target. These are useful model-development
checks. They do not establish real-device transient accuracy.

## Model and evidence identity

- Model: [`sources/model/LMR51430XDDCR_datasheet_approx.lib`](sources/model/LMR51430XDDCR_datasheet_approx.lib).
- Model SHA-256: `5b8b31bdd9e0f813e552fc340f7d4bcd528fede14fd0446e13944f11c6a3f369`.
- Datasheet SHA-256: `f7d8053844fb07ae773844f023373c0c570507ca61603fe28dda15364987296c`.
- Simulator: ngspice 45.2 with XSPICE, host `/opt/homebrew/bin/ngspice`.
- Current four-case receipt: [`measured-v3/receipt.json`](measured-v3/receipt.json).
- Timestep comparison: [`convergence-10ns/receipt.json`](convergence-10ns/receipt.json).
- EN hysteresis/restart: [`enable-probe/receipt.json`](enable-probe/receipt.json).

Each receipt binds the model snapshot, source and executed deck, simulator
version, log, and raw waveform hashes. The model bytes agree across these
three output directories. Logs, exact executed decks, receipts, and PNGs are
retained in Git; multi-gigabyte native `.raw` waveforms are retained locally
and ignored by Git. A clone can regenerate them; it must not treat a missing
raw file as available evidence merely because its digest appears here.

## What is implemented

The terminal order `VIN SW GND FB EN CB` maps to TI pins 3, 2, 1, 4, 5, 6.
The controller observes FB and SW current. The desired VOUT, external L, and
load are absent from the model. Finite-resistance HS and LS conductances,
a low-side body diode, and an external SW current probe form the power path.
An XSPICE SR latch starts a pulse at an oscillator edge and ends it at the
commanded peak current. A real clock source puts edges into the simulator's
breakpoint list. FB above the ramped reference suppresses subsequent pulses;
the low-side switch turns off near zero current.

Datasheet typical anchors used explicitly:

| Behavior | Value |
|---|---|
| Reference / oscillator | 0.600 V / 500 kHz |
| HS / LS on resistance | 0.12 / 0.07 ohm |
| Soft-start reference ramp | 4 ms after enable; reset when disabled |
| Minimum PFM peak / HS peak clamp | 0.48 / 4.76 A |
| Zero-current detection threshold | 0.02 A |
| EN rise / fall | 1.227 / 1.08 V |
| VIN UVLO rise / fall | 3.89 / 3.58 V |
| Minimum-on blanking / minimum-off constraint | 70 / 150 ns |

Unpublished internal compensation is represented by assumed `KP=5`,
`KI=10u`, `CCTRL=1n`. A 1 Tohm integrator leakage is numerical grounding.
These values are frozen across the reported cases. Comparator smoothing
is 2 mA; logic/DAC delays are 1 ns. The 1 ohm/1 nF switch-node snubber,
body-diode model, and 100 Mohm off paths are explicit numerical/parasitic
assumptions. Bootstrap drive is omitted: a 1 Gohm internal CB-to-SW leakage
and external 100 nF capacitor do not model a real driver.

EN and VIN each have a hysteretic switch. The EN probe measured enabled=1
at 1.15 V after the rising threshold had been crossed, then enabled=0 at
1.15 V after a fall below 1.08 V. During the disabled interval the maximum
HS gate and reference were both zero. After re-enabling near 7 ms, the
reference was 0.2992301 V at 9 ms and 0.600 V at 11.5 ms. This checks a
restarted ramp rather than an absolute-time ramp. UVLO uses the stated
thresholds but its falling-input/protection recovery behavior has not been
independently characterized.

## Circuit conditions

Temper cases tie EN to VIN, use 100 k/22.1 k feedback, nominal 5.6 uH,
8.5 milliohm inductor DCR, 10 uF input, and 44 uF output plus 100 nF HF
capacitance. Source resistance 0.1 ohm and output ESR 5 milliohm are assumed.
The nominal resistive load is 6.629864253 ohm, approximately 0.5 A.
Capacitances are nominal: no exact-part DC-bias/temperature floor has been
qualified. See [component audit](requirements-components.md).

Input variation starts at 13.5 V, steps to 16.5 V at 6 ms and back at 9 ms,
with 10 us edges. Load variation uses a 66.29864253 ohm baseline plus an
additional 0.45 A from 6–9 ms, with 1 us edges: approximately 0.05–0.5 A.
Those step sizes and slew rates are exploratory conditions, not approved
Temper requirements.

The TI application example uses 12 V, 6.8 uH, 44 uF, 100 k/13.7 k feedback,
2.2 uF input and 1.666666667 ohm load (nominal 3 A). The bench retains the
assumed 0.1 ohm source, 5 milliohm ESR, 8.5 milliohm DCR and 100 nF output
HF capacitor; it is not an exact reconstruction of TI's measured PCB.
The file is named `datasheet_holdout`, but it exposed a development defect
and was subsequently rerun. It is now a development cross-check, **not a
blind holdout or independent qualification receipt**.

## Actual native measurements

Gear integration, 25 °C, relative tolerance 1e-4, maximum timestep 20 ns,
12 ms transient. The table uses native `.meas` over 10–12 ms. Input and
output powers check the physical power path; they are not efficiency claims.

| Scenario | Mean VOUT (V) | VOUT range (V) | Mean IL (A) | Pin / Pout (W) |
|---|---:|---:|---:|---:|
| startup | 3.314861 | 3.307908–3.319623 | 0.500006 | 1.798234 / 1.657396 |
| input_variation | 3.309067 | 3.291980–3.322635 | 0.499264 | 1.767328 / 1.651613 |
| load_variation | 3.323327 | 3.312666–3.335023 | 0.049866 | 0.181322 / 0.166588 |
| datasheet_holdout | 4.978407 | 4.974148–4.983078 | 2.987124 | 16.154300 / 14.870720 |

The load case's table row is **after return to light load**. During 7.5–8.5 ms
at the high load it averaged **3.300357 V**. The load increase caused a
**2.871829 V minimum** in 6–6.5 ms; removal produced a **3.335503 V maximum**
in 9–9.5 ms. This substantial dip is a model result that requires comparison
with real-device waveforms; it must not be turned into a board failure or
an accepted transient specification.

At nominal load and in the TI example, 100 measured rising-edge intervals
span 200 us: **500 kHz**. After returning to 0.05 A, 100 intervals span
1.778 ms: about **56.2 kHz effective pulse rate**, showing pulse skipping.
This edge-span statistic is not a full-window frequency average. The ideal
CCM calculation gives 0.85784 A ripple in the TI example. At 10 ns the model
measures 2.554668–3.413478 A, or **0.858810 A**. That agreement is a useful
power-stage check, not calibration of the unknown control loop.

Native postprocessing of the retained 20 ns waveforms finds mean inductor
voltage of -41.7 uV for Temper and +42.1 uV for the TI example over 10–12 ms,
consistent with nearly balanced inductor volt-seconds. The exact commands
and outputs are retained as each case's `balance-check.cir` and
`balance-check.txt`. These are additional checks, not qualified measurements.

Gate-overlap metric max `GH*GL/25` is 0.002 during numerical transitions;
the model does not implement TI's detailed dead time. DCM inductor minima
near -47 mA involve the assumed snubber/parasitics after LS turns off.
They are not validation of the real device's reverse-current behavior.

## Numerical convergence check

Same model, same circuits, maximum timestep reduced from 20 to 10 ns:

| Scenario | 20 ns mean VOUT | 10 ns mean VOUT | Difference (mV) |
|---|---:|---:|---:|
| startup | 3.314861 | 3.314877 | 0.016 |
| datasheet_holdout | 4.978407 | 4.979029 | 0.622 |

The nominal startup current peak changes from 0.985986 to 0.978927 A;
the TI example peak changes from 3.422283 to 3.413478 A. Average regulation
is stable under this refinement. The voltage extrema and current valleys
are more sensitive, so the reported millivolt ripple is not a precision
prediction. Load-step transients have not received a timestep sweep.

## Reproduce and inspect

From this worktree's repository root, with ngspice 45.2 installed:

```bash
python3 harness-lab/audits/buck-20260909/run_scenarios.py /tmp/buck-fresh
python3 harness-lab/audits/buck-20260909/run_scenarios.py /tmp/buck-fresh-10ns --scenarios startup datasheet_holdout --max-step-ns 10
```

Output directories must be new. The runner checks all declared native
measurements for completeness and finite values, records timeouts/failures,
and never issues model qualification. Three mocked regression tests exercise
success, missing/nonfinite metrics, and timeout retention. These tests check
the runner, not device behavior.

For the extra EN probe, run `ngspice -b bench.cir` from a **copy** of
`enable-probe/enable_restart/`, keeping its sibling `model.lib` at the same
relative path. The executed deck includes all extra native measurements.
To plot any retained raw file with an isolated plotting environment:

```bash
uv run --no-project --with matplotlib python harness-lab/audits/buck-20260909/plot_waveforms.py /tmp/buck-fresh/startup/waveform.raw /tmp/buck-startup.png
```

[Startup plot](plots/startup.png) · [Load-step plot](plots/load-step.png).
The renderer plots actual adaptive samples, not a generated illustration.

## What remains outside this model

No internal compensation measurement, accurate PFM hysteresis, full current
limit/valley limit/hiccup, thermal shutdown, temperature dependence, actual
bootstrap drive, package/PCB parasitic extraction, EMI, or device-loss
calibration. Operation above 50% duty has not been validated; undocumented
slope compensation is not reproduced. Exact-part capacitor bias and
inductor saturation behavior are not included. Do not use it to sign off
stability, output ripple, fault safety, efficiency, or board temperature.

The normal harness remains blocked on 16 unresolved mandatory requirement
IDs, component qualification and independent model evidence. The simulation
stage can now be explored with a real runnable model; no approved model
registry entry or hardware-verification claim was manufactured.

Earlier errors and unsuccessful attempts are retained and labeled in
[rejected development history](rejected-v1/README.md). In particular, the
20 ns `measured-v2` revision used 10 Meg integrator leakage, giving a false
4.759 V result in the TI example; changing that numerical leak to 1 Tohm
restored the controller's DC gain without prescribing the output voltage.
