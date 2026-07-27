# Tank Coil Inductance — Specification Attempt

**Date:** 2026-07-26
**Outcome:** **L cannot be specified from the current model.** The ZVS boundary
is decidable; delivered power is not, and power is the axis that decides the
value.

## The problem being solved

`elec/src/*.ato` contains **no inductance value for the coil** —
`inductor_conn` is an unplaced Litz placeholder. With `C_tank` fixed at 300 nF
(`c_tank1` + `c_tank2`, 150 nF each in parallel), the resonant frequency and
therefore the ZVS margin are undetermined by the committed design.

Frequency is the power-control variable (`main.ato:71` nominal 35 kHz, `:72`
tracking range 20–100 kHz), so the question is not "what L at 35 kHz" but
*what L puts the whole power range inside a band that stays above resonance*.

## What was measured

`simulation/harness/run_tank_coil_sweep.py`, extending the ZVS harness with a
pan-power measurement. Two sweeps, 81 grid points, 78 converged.

Sweeping L at the best ZVS-holding ratio, cast-iron pan:

| L (µH) | f_res | Max power with ZVS held | at ratio | ZVS margin |
|---|---|---|---|---|
| 70 | 34.7 kHz | 1305 W | 1.02 | 1.2% |
| 90 | 30.6 kHz | 1260 W | 1.02 | 1.4% |
| 110 | 27.7 kHz | 1217 W | 1.02 | 1.5% |
| 130 | 25.5 kHz | 1181 W | 1.02 | 1.5% |
| 150 | 23.7 kHz | 1148 W | 1.02 | 1.6% |

**Result that decides the outcome: 1800 W is unreachable at every L tested,
and the ZVS-holding optimum is always at ratio 1.02** — the closest-to-resonance
point that still switches softly.

## Why the power axis cannot be trusted

At L = 70 µH, ratio 1.02, the model reports **109.5 A RMS tank current
delivering 1305 W**, with 12.8 A reaching the pan. That is internally
consistent (12.8² × 8 Ω = 1310 W), but it is not physical:

| | Model | A real ~1.8 kW hob |
|---|---|---|
| Tank current | 109.5 A | ~40 A |
| Effective series R (P/i²) | **0.109 Ω** | ~1.12 Ω |
| Implied tank Q | **143** | ~14 |
| Circulating reactive power | 187 kVAR for 1.3 kW | — |

**The pan model absorbs roughly 10× too little.** `PANLOAD_TRANSFORMER` is
configured `k = 0.5`, `R_pan = 8 Ω`; the reflected resistance that results
gives a tank Q an order of magnitude above anything a real induction hob runs.
Delivered power and tank current from this model are therefore **not usable
figures**, and neither is any efficiency claim built on them.

Two consequences follow, and only the first is safe to act on.

**Safe:** the ZVS boundary is set by the *reactive* behaviour, which the model
does represent. ZVS holds for **f_sw ≥ ~1.02 × f_res** and collapses below it,
consistently across all L values and all four pan presets. That relationship is
ordinal-valid.

**Not safe:** any statement of the form "L = X µH delivers 1800 W" — including
the apparent conclusion that no L does. That may be entirely an artefact of the
under-absorbing pan.

## What this does establish

1. **ZVS requires operating at least ~2% above resonance.** With margin for
   pan-to-pan and manufacturing spread, design for **f_sw/f_res ≥ 1.05** at
   full power rather than 1.02.
2. **The declared numbers are inconsistent with each other.**
   `f_resonant_nominal = 25 kHz` (`main.ato:74`) requires **L = 135 µH** at
   300 nF. The 80 µH the simulation defaults to gives 32.5 kHz. Nothing in the
   design says which is intended.
3. **Whatever value is chosen must be written down.** That is the actual
   defect; the margin figure is a symptom.

## Interaction worth checking regardless of the model

OCP-01 now trips at **50.1 A** of tank current (via the CT). Every
ZVS-holding operating point in this sweep draws **more** than that — 109.5 A at
the best point, and still 55.8 A at ratio 1.12. Even allowing that the model's
currents are ~10× too high for the power delivered, **the relationship between
full-power tank current and the OCP-01 trip point has never been checked**, and
if real tank current at 1800 W exceeds 50 A the cooker trips its own protection
before reaching full power.

This is checkable independently of the pan model, from the real coil and pan
parameters, and it should be checked before the coil is ordered.

## What is needed to finish this

The blocker is the pan model, not the sweep:

- **Calibrate `pan_load.sub`** against a real coil and pan — coupling
  coefficient and reflected resistance measured, not assumed. This is exactly
  the calibration inversion in `METHODOLOGY.md` §11: the first physical
  measurement should be designed to produce these numbers.
- Or **derive the coil analytically** from the intended geometry (diameter,
  turns, Litz spec, pan spacing) and treat the simulation as a check rather
  than the source.

`docs/COIL_BRACKET_DESIGN.md` may already fix geometry, which would constrain
L mechanically and make this an analytical problem rather than a search.

## Falsifier, stated in advance and triggered

*"This recommendation fails if the pan model's coupling is not representative,
because then the power axis is meaningless and only the ZVS boundary
survives."*

It failed. The implied Q of 143 against a realistic ~14 is the evidence, and
the specification is withheld rather than issued on an unusable power axis.

All models remain `calibrated: false`; the IGBT model is behavioural with fixed
capacitances.
