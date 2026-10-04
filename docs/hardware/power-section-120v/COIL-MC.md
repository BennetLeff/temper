---
title: Coil/pan Monte Carlo — design robustness and what to measure
date: 2026-09-25
status: design screen over ASSUMED priors (no coil measured yet)
calculation: coil_mc.rs → coil-mc-output.txt (11/11 self-tests, seed 20260925, 20,000 samples per detailed run)
---

# Coil/pan Monte Carlo

**2026-10-04 current-envelope correction:** the 45 A value below remains a
historical comparative screen, not a released normal-operation allocation.
The independent shunt detector has a conditional static band of
**38.44–85.55 A** at +85 °C board with an assumed +50 °C R5 rise; the broader
CT temperature/tolerance calculation gives **50.56–60.01 A**. The older
50.93–59.51 A CT-only result does not supersede the shunt constraint.
The threshold parts and relevant net endpoints are unchanged on native-18
and the HOT5 candidate. All full-power percentages below omit shunt dynamic
behavior and therefore cannot demonstrate implementable power. No new
current limit is selected. See the [reconciliation and next-build gates](../../research/mit-product-design/readiness/power/README.md).

## What this can and cannot tell us

It **can** rank coil targets and topologies across a plausible spread of
coils and pans, and name the uncertain input that drives failures, which
is the one worth measuring first. It **cannot** certify parts. The
priors are engineering assumptions anchored on four published points. They
are not an observed pan population. The output's `model_full_power_pct` is a
comparative ranking under assumed phase, current and capacitor screens, not a
pass rate for a selected part or cookware population. Deterministic endpoint
probes below expose some missed combinations; measured corners must size the parts.

## Model

The model is closed-form first-harmonic, line-cycle averaged, on the unfiltered 114 V / 127 V bus. It
uses the same equations as `power_section.rs` (the two agree at resonance in the self-tests).

Priors are turns-independent ratios, so one measured coil informs every turn count:

| Input | Prior | Anchor |
| --- | --- | --- |
| Pan class (weight) | cast iron 25 %, carbon/430 steel 25 %, clad/tri-ply 25 %, low-R (Silargan-like) 10 %, offset/small 15 % | Weights are a guess; rerun if your cookware differs |
| Coupling k_L = L_loaded / L_no-pan | per class, e.g. cast iron 0.74–0.86, steel 0.66–0.80 | Infineon kit chart 0.69; MDPI 180 mm study 0.63–0.82 |
| Pan resistance r = R_pan / L_no-pan at 40 kHz (Ω/µH) | per class, e.g. cast iron 0.036–0.052, steel 0.029–0.041 | Kit 0.0334; MDPI cast iron 0.0445, stainless 0.0347, Silargan 0.0246 |
| Clad/tri-ply | k_L 0.66–0.82, r 0.018–0.032 | **No measured anchor: a guess** |
| Coil winding R_coil / L_no-pan | log-uniform 0.0015–0.0060 Ω/µH | Kit 0.0039 |
| Coil L tolerance / capacitor tolerance | 5 % / 3 % (1σ) | Typical manufacturing |
| R_pan vs frequency | ∝ √f | Skin-effect assumption |

**Requirement.** Full 15 A input power on intended cookware (cast iron, steel, clad).
Other pans only need to stay within limits at reduced power, as commercial cookers do.

**Comparative screens, not qualified limits.**
- phase ≥ 20° (ZVS margin)
- tank peak ≤ 45 A, retained solely for comparison with the prior model correction. The old 85 A screen exceeded the tank-CT band, but 45 A still overlaps the independent shunt's conditional static trip band. This is not an implemented firmware regulator or a guaranteed dynamic trip margin.
- resonant capacitor ≤ 650 V line-crest peak (**assumed ranking knob**; the
  selected 942C12P22K-F / 942C12P1K-F bank has no verified hot 30–50 kHz
  continuous voltage/current envelope)
- 20–60 kHz

**Search.** A grid search over the free choices (coil L_no-pan and the capacitor's
reference resonance, 22–52 kHz) runs at 114 V, followed by detailed runs at 114 V and 127 V.

The selected full bridge has four **single** IPW65R018CFD7 switches. The
model now uses 35 mΩ hot **per position** as a provisional 650 V CFD7-class
loss proxy. The previous model mistakenly used 17.5 mΩ per full-bridge
position (the two-parallel 600 V half-bridge comparison), understating bridge
loss. The half-bridge comparison retains two parallel 600 V devices per
position so both topologies use four switches. The selected-part hot
resistance and switching loss still need datasheet and bench closure.

## Comparative results

| Design | Intended cookware at full power, 114 V / 127 V | Median efficiency | What fails |
| --- | ---: | ---: | --- |
| **Selected full bridge, 70 µH / 0.54 µF** | **14.8 % / 4.3 %** | 88.7 % / 88.2 % | Predominantly current-limited. Voltage rating remains unqualified. At 114 V, conditional p95 cap crest is 401 V and estimated switching-ripple line-cycle RMS is 200 V. |
| Full bridge, best sampled grid point 140 µH / 22 kHz | 82.0 % / 75.4 % | 86.6 % / 87.1 % | Comparative alternative only; this is not approval to change the coil or bank. |
| Full bridge, kit-like stock coil 87 µH, 35 kHz | 54.8 % / 38.0 % | 88.8 % / 89.1 % | Current and comparative capacitor screen. |
| Full bridge, stock coil 123 µH | 23.1 % / 15.3 % | 88.9 % / 89.4 % | Comparative capacitor screen and impedance. |
| Half bridge, sampled grid and earlier 33 µH / 35 kHz design | 0 % / 0 % | — | No modeled full-power points under the same 45 A current screen; historical 85 A comparisons do not transfer. |
| Half bridge, stock 87 µH | 0 % | — | Impedance far too high |

The old `unsafe_any_pan_pct = 0` field has been removed. A model that
limits its own voltage by moving frequency cannot conclude zero over-stress,
especially when its limit has no selected-part justification.

### Selected-bank endpoint probes

The source now enumerates 160 simultaneous endpoint combinations per input
line: five assumed pan classes, coil inductance ±10%, class coupling and pan
resistance endpoints, winding resistance endpoints, and capacitance ±10%.
These are deliberately adversarial inputs, not probabilities or validated
physical extremes.

| Line RMS | Modeled full power / 160 | Max cap crest among full-power cases | Estimated max line-cycle RMS | Max modeled crest at 60 kHz, all 160 |
| --- | ---: | ---: | ---: | ---: |
| 108 V | 25 | 431 V | 216 V | 125 V |
| 114 V | 20 | 416 V | 208 V | 132 V |
| 127 V | 12 | 428 V | 214 V | 147 V |
| 140 V | 5 | 423 V | 211 V | 162 V |

The maxima at full-power points are conditional on the **arbitrary** 650 V
screen. They do not bound startup, detuning, pan removal, a control fault,
switching harmonics, or transient energy. The 60 kHz column is a controlled
frequency probe, not a worst-case voltage claim.

### Findings

1. **The former near-100% claim cannot justify the selected coil.** Its 85 A screen was incompatible with the later protection design. A reproduced 140 V carbon/steel case was accepted at 61.64 A, above even the 59.51 A high end of the CT's modeled DC trip range. A regression test now rejects that full-power claim.
2. **Most assumed pans need reduced power under the current allocation.** This is a model/requirements mismatch, not a measured cooker failure. Do not raise the protection threshold to force the old ranking to pass. Measure coil/pan impedance and decide permitted power before changing the coil, capacitor bank, current transformer or protection.
3. **The best grid point is a hypothesis, not a selected replacement.** The 140 µH/22 kHz result depends on inherited pan ratios, guessed clad data and unqualified capacitor/loss screens. Lower continuous-power behavior, acoustics, ZVS, thermal and transient stress still matter.
4. **Reported efficiency and capacitor percentiles are conditional on modeled full power.** Most draws now fail that condition. Those statistics do not describe the excluded reduced-power points. `NaN` means no qualifying samples, not zero stress or loss.

## What to measure first (ranked by how much it moves the decision)

1. **Your actual cookware on one coil:** R_pan and L_loaded for each pan, especially
   tri-ply/clad, which has no anchor now. These ratios can inform a turn-count
   hypothesis, but a changed winding, ferrite, diameter or gap needs its own
   measurement; they do not qualify an arbitrary replacement coil.
2. **Coil winding resistance with no pan:** sets efficiency (LOSS-REFACTOR.md), not feasibility.
3. **Resonant capacitor AC rating at 30–50 kHz**, including 942C bank-element
   sharing, ripple current, case temperature and transient duty. The 650 V
   screen is an assumption and cannot be used to release the selected bank.

## RCA RC-12A3 teardown

The RC-12A3 is a 120 V, 60 Hz, 1,200–1,300 W Mexican-market unit, so its
coil is built for less power than the target. That doesn't matter here:
its measured **ratios** (k_L, R_pan/L, R_coil/L) replace the priors directly.

**Safety:** work unplugged. Its bus capacitor is small, but confirm it reads below
1 V before touching anything. Do not power the opened unit.

Record:
1. **Topology:** count the IGBTs (one means quasi-resonant, two a half bridge), and note their part
   numbers, the resonant capacitor(s) (value, voltage, parallel across the
   coil or in series), the bus capacitor value, and the bridge rectifier.
2. **Coil:** diameter, turns if countable, litz strand count and diameter,
   ferrite bar count and size, and glass-to-coil gap.
3. **Measure each (no pan, and each of your pans centered, plus one pan offset
   by ~3 cm):** L and R at 20, 30, 40, 50 and 60 kHz. An LCR meter that reaches
   100 kHz is enough for this screen. Note the test level; small-signal
   values understate a steel pan's behavior at full power.
4. **Protection parts:** thermal fuse(s), NTC placement and value, and the current
   sensing method (CT or shunt).
5. **Benchmark, before opening it (as sold, closed):** wall watts at max setting with a
   plug-in power meter, and a timed water-heating test (1 L, 20→80 °C)
   for delivered power and efficiency.

Put the measurements into `coil_mc.rs` as narrowed prior ranges (or a
new "measured" pan class) and rerun. The plateau either holds or moves.

## Model limits

- First harmonic only, ignoring bus-capacitor filtering near zero crossings; turn-off losses and
  dead-time effects on phase are not modeled here.
- The capacitor limit is an unqualified 650 V line-crest peak comparison. The
  selected 942C 1200 Vdc parts are cataloged at 430 Vac **at 60 Hz**; the
  catalog's 25 °C frequency curves do not directly qualify the exact 0.1 and
  0.22 µF elements under this assembled bank's hot 30–50 kHz waveform. At a
  650 V crest the carrier sine would have 459.6 V RMS at the line crest, while
  the idealized full-line waveform has 325 V RMS. Neither value is a rating
  margin without waveform, frequency and temperature data. The half bridge
  includes bus/2 DC bias on its split capacitors; its reported RMS strips
  this bias and is therefore an AC-component estimate only.
- Pan classes are independent draws. Temperature dependence of pan
  resistivity and permeability (and Curie effects near 700 °C+, not reached in
  cooking) is ignored.
- Grid points use 4,000 samples, so ties within about 1 % are noise.
