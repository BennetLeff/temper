# OCP-01 trip point versus the current 1800 W actually requires

**Date:** 2026-07-26
**Method:** analytical, from committed values. No simulation, no pan model —
this deliberately avoids `pan_load.sub`, whose reflected resistance was found
~10× too low (`2026-07-26-tank-coil-L-sweep.json`).
**Finding:** OCP-01 and EFF-02/PWR-02 are in tension. Reaching 1800 W without
tripping demands better-than-typical coil-to-pan coupling.

## OCP-01 trips on instantaneous current, not RMS

The sense path, read from `elec/src/modules.ato` (`CurrentSensing`):

```
tank ──► CT 1:100 ──► burden 4.99 Ω ──► i_sense.line ──► comparator INP (ref 2.500 V)
                                    └─► 100 nF to reference
```

**There is no rectifier and no averaging.** The BOM's "Precision Rectifier
(OCP)" section is class A in the audit — costed, never wired. The comparator
therefore sees the raw bipolar tank waveform.

The 100 nF across the burden gives RC = 499 ns, a **319 kHz** corner. At the
35 kHz tank fundamental it attenuates essentially nothing: it is a noise
filter, not an averager.

| | |
|---|---|
| Trip current | **50.1 A peak** |
| Equivalent RMS (sinusoid) | **35.4 A** |

## The conflict

Power into the pan is `P = I_rms² × R_eff`, where `R_eff` is the reflected pan
resistance seen by the tank. Holding `I_rms` at the trip limit:

| Trip (peak) | = RMS | `R_eff` needed for 1800 W |
|---|---|---|
| 45.0 A (spec min) | 31.8 A | **1.78 Ω** |
| **50.1 A (as built)** | **35.4 A** | **1.43 Ω** |
| 55.0 A (spec max) | 38.9 A | **1.19 Ω** |

A typical 1.8 kW induction hob runs roughly **40 A RMS**, implying
`R_eff ≈ 1.12 Ω`. At that coupling:

```
1800 W at 1.12 Ω  ->  40.0 A RMS  ->  56.6 A peak  ->  EXCEEDS the 50.1 A trip
```

**Even at the top of the OCP-01 window the design needs better-than-typical
coupling to reach full power.** This is not a value that can be tuned away —
`R_eff` is set by coil geometry, pan material and spacing.

Tank RMS required at 1800 W, by coupling:

| `R_eff` | I_rms | I_peak | vs 50.1 A trip |
|---|---|---|---|
| 0.75 Ω | 49.0 A | 69.3 A | **trips** |
| 1.00 Ω | 42.4 A | 60.0 A | **trips** |
| 1.12 Ω *(typical)* | 40.0 A | 56.6 A | **trips** |
| 1.25 Ω | 37.9 A | 53.7 A | **trips** |
| 1.44 Ω | 35.4 A | 50.0 A | ok |
| 2.00 Ω | 30.0 A | 42.4 A | ok |

Low-resistivity or non-ferrous pans, and poorly-centred or undersized pans, all
push `R_eff` down — so the failure mode is *nuisance overcurrent trips on
exactly the cookware and placements a user will try*.

## Second issue: the spec does not say peak or RMS

`OCP-01: Primary OCP 45-55A, <1µs` (`docs/STRATEGY.md`) does not state which.
The reading changes the verdict on the fix landed earlier today:

- **Peak** — implementation trips at 50.1 A peak → **compliant**
- **RMS** — implementation trips at 35.4 A RMS → **below the 45 A minimum**,
  the same class of violation as the original 37.6 A

**Peak is almost certainly intended.** OCP-02 is specified 55–65 A against a
40 A-continuous IGBT; read as RMS that would be 78–92 A peak, far outside the
device. Only the peak reading is coherent across both gates.

This is the same ambiguity found in UVL-02, resolved the same way — by
requiring consistency across sibling gates. **It should be written into
`FUNCTIONAL_TEST_CRITERIA.md` explicitly** rather than left to inference twice.

## What this does and does not depend on

**Does not depend on** the pan model, the coil inductance, or the simulation —
only on the committed burden, CT ratio and comparator reference, plus the
definition of power.

**Does depend on** `R_eff`, which is unknown because the coil is unspecified
(`docs/hardware/TANK_COIL_SPECIFICATION.md`). The conflict is therefore
*conditional*: it bites if `R_eff < 1.43 Ω`, and nothing in the design
currently establishes what `R_eff` is.

## Resolutions, none free

| Option | Cost |
|---|---|
| Design the coil for `R_eff ≥ 1.43 Ω` | Constrains coil geometry and supported cookware; must be verified on a bench |
| Raise the OCP-01 trip | Spec caps it at 55 A, which still needs `R_eff ≥ 1.19 Ω` — buys little |
| Add rectification/averaging so OCP trips on RMS | New circuit; the BOM already costs one that was never built. Slows response, which fights the <1 µs budget |
| Lower the 1800 W target | Changes EFF-02/PWR-02 |

**Recommended next step:** measure `R_eff` for the intended coil and a
reference pan set. It is the single unknown that decides whether this is a real
problem or a comfortable margin, and it is the same measurement the coil
specification is blocked on.
