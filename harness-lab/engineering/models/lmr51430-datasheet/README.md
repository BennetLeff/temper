# LMR51430XDDCR datasheet model

This package is a reusable, runnable ngspice behavioral model for the current
Temper `BuckConverter3V3` regulator, U3 `LMR51430XDDCR` (500 kHz PFM X,
DDCR). It is intended for circuit development, with accuracy assessed
separately for each claim. It is not a TI model and is not a qualification
gate.

The subcircuit terminal order is `VIN SW GND FB EN CB`, mapping to TI pins
`3, 2, 1, 4, 5, 6`. The model has no desired output, inductor, output
capacitor, or load inside it. Put those in the surrounding deck so feedback,
power flow, and the actual Temper BOM can be inspected independently.
The external simulator ground must be node `0`; the model intentionally uses
ngspice's global node `0` for its logic and power reference.

Public overrides use ngspice instance parameters, for example:

```spice
X_U3 vin sw 0 fb en cb LMR51430XDDCR PARAMS: VREF=0.600 FSW=500k RHS=0.12
```

The source anchor is TI's [LMR51430 SLUSEF4A Rev. A datasheet](https://www.ti.com/lit/ds/symlink/lmr51430.pdf), retained by the audit at `harness-lab/audits/buck-20260909/sources/ti-lmr51430.pdf`.

The model is based on the corrected `measured-v3/model.lib` from the retained
2026-09-09 audit. The audit source and its rejected revisions are immutable;
this package is a new consumer-facing copy. `parameter-provenance.json` is the
source ledger: it separates datasheet-backed typical values from assumptions
for unpublished compensation, zero-current smoothing, numerical grounding, and
parasitics, and records the current Atopile/BOM mapping.

The current Temper mapping is:

| Reference | Part | Model use |
| --- | --- | --- |
| U3 | LMR51430XDDCR | subcircuit |
| L2 | SRP1265A-5R6M, 5.6 uH, 10 mΩ max | external inductor |
| C9 | CL32B106KBJZW6E, 10 uF | external input capacitor; 4.54 uF effective sensitivity is a BOM assumption |
| C10/C13 | C0603C104K5RACTU, 100 nF | external bootstrap/output HF capacitors |
| C11/C12 | GRM32ER71E226KE15L, 22 uF each | external output capacitors; 22.01 uF conservative effective sensitivity is a BOM assumption |
| R16/R17 | 100 kΩ / 22.1 kΩ, 1% | external feedback divider |

The model exercises finite-resistance high- and low-side power paths, an
external switch-current probe, feedback regulation, soft-start, EN and VIN
hysteresis, peak-current termination, pulse skipping, and low-side turnoff
near zero current. The PI command gains (`KP`, `KI`, `CCTRL`) are assumed
because TI does not publish the internal compensation. The 1 TΩ integrator
leak is numerical grounding, not a device parameter.

The `T_OFF_MIN=150 ns` periodic reset and the `RSNUB=1 Ω`, `CSNUB=1 nF`
switch-node stabilizer are exposed parameters. The former is a simplified
timing mechanism and limits this implementation's maximum duty at 500 kHz;
it should not be read as a complete reproduction of the device's duty-cycle
or frequency-foldback behavior. The snubber is energy-bearing numerical
stabilization and must not be used to infer converter efficiency.

The retained audit demonstrated nominal divider agreement, finite input power,
inductor volt-second balance, timestep comparison, and EN restart. Those are
model-development checks. They do not support claims about transient accuracy,
stability, efficiency, thermal behavior, fault behavior, EMI, or hardware
performance. In particular, the model does not include the detailed bootstrap
driver, dead time, thermal shutdown, hiccup/current-limit timing, capacitor
DC-bias behavior, or inductor saturation.

For the source record and exact prior runs, see
`harness-lab/audits/buck-20260909/model-simulation.md` and its retained TI PDF.

Current-package evidence from bounded ngspice 45.2 runs is retained outside
the repository in `/tmp/lmr51430-paramcheck-20260910/`: the default run log is
`base/run.log` (at 1.5 ms: `ref_end=0.2244652 V`, `vout_end=1.233718 V`;
SHA-256 `2022c8032240c235c569519b49c5cfea49a60ef704b945fb885d19ed4ad80996`)
and the same deck with `PARAMS: VREF=0.5` is `override/run.log` (at 1.5 ms:
`ref_end=0.1870543 V`, `vout_end=1.036593 V`; SHA-256
`34cbd0e1dc823ff888478c3fd8bce8c6bddff40544b68519ecce9aac90f57c1`).
The changed internal reference and output demonstrate that the public
override changes model behavior, rather than merely parsing.
