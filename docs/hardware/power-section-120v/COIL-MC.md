---
title: Coil/pan Monte Carlo — design robustness and what to measure
date: 2026-09-25
status: design screen over ASSUMED priors (no coil measured yet)
calculation: coil_mc.rs → coil-mc-output.txt (6/6 self-tests, seed 20260925, 20,000 samples per detailed run)
---

# Coil/pan Monte Carlo

## What this can and cannot tell us

It **can** rank coil targets and topologies across a plausible spread of
coils and pans, and name the uncertain input that drives failures, which
is the one worth measuring first. It **cannot** certify parts. The
priors are engineering assumptions anchored on four published points. They
are not an observed pan population, and "100 % pass" means "robust under these
assumptions". Worst-case corners still size the switches and capacitors.

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

**Limits.**
- phase ≥ 20° (ZVS margin)
- tank peak ≤ 85 A (below the OCP band)
- resonant capacitor ≤ 650 V peak
- 20–60 kHz

**Search.** A grid search over the free choices (coil L_no-pan and the capacitor's
reference resonance, 22–52 kHz) runs at 114 V, followed by detailed runs at 114 V and 127 V.

## Results

| Design | Intended cookware at full power, 114 V / 127 V | Median efficiency | What fails |
| --- | ---: | ---: | --- |
| **Full bridge, ~45–90 µH plateau** (e.g. 70 µH, capacitor tuned to 32 kHz) | **100 % / 99.6 %** | 87.9 % | Rare capacitor-voltage limit |
| Full bridge, best-ranked point 45 µH / 42 kHz | 100 % / 99.3 % | 88.5 % | — but its lowest continuous power at 60 kHz is 395 W (median) vs 148 W at 70 µH |
| Full bridge, kit-like stock coil 87 µH, 35 kHz | 88 % / 83 % | 88.8 % | Capacitor voltage, on low-R clad pans |
| Full bridge, stock coil 123 µH | 23 % / 15 % | 89.5 % | Capacitor voltage and impedance |
| Half bridge, best grid point 36 µH / 22 kHz | 73 % / 65 % | 86.8 % | Peak current (clad) and phase margin (cast iron); runs at 22 kHz, next to the audible range |
| Half bridge, earlier hand design 33 µH / 35 kHz (POWER-SECTION.md) | 69 % / 72 % | 88.1 % | Cast iron: impedance too high; clad: peak current |
| Half bridge, stock 87 µH | 0 % | — | Impedance far too high |

No design put any pan outside the limits ("unsafe" 0 % everywhere).
Failures show up as reduced power, not as over-stress.

### Findings

1. **The half-bridge recommendation in POWER-SECTION.md is not robust.** A 120 V half bridge is
   squeezed from both sides:
   - high-resistance pans (cast iron) need more drive voltage than it has
   - low-resistance pans (clad) need more current than the 85 A limit allows

   No coil/capacitor choice escapes this; the best is about 73 %.
2. **A full bridge removes the squeeze.** Twice the drive voltage lets the coil have four times the
   impedance at half the current. Robust designs then form a broad
   plateau (about 45–90 µH) instead of a knife-edge.
   - Per LOSS-REFACTOR.md (B1 = A6), four single CFD7s in a full bridge lose the same as four paralleled
     CFD7s in a half bridge. **Same switch count, same loss.**
   - The extra cost is one more gate-drive channel (a second UCC21550 board).
   - Tank, current-transformer and capacitor currents halve.
3. **Within the full-bridge plateau, prefer the upper-middle (about 65–80 µH).** Lower inductance buys
   about 0.5 % efficiency but raises the lowest continuous power (the burst
   handoff) from about 150 W to about 400 W. Coarser bursts work against
   room-temperature holding.
4. **What drives failure is pan resistance and coupling, not coil tolerance.**
   Coil L and coil resistance halves change the pass rate by a few points. Pan resistance and
   coupling change it by 10–20 points, most of all for clad pans, which have **no
   measured anchor**. Winding resistance mainly sets efficiency, not feasibility.

## What to measure first (ranked by how much it moves the decision)

1. **Your actual cookware on one coil:** R_pan and L_loaded for each pan, especially
   tri-ply/clad, which has no anchor now. These pan ratios transfer to any coil
   turn count.
2. **Coil winding resistance with no pan:** sets efficiency (LOSS-REFACTOR.md), not feasibility.
3. **Resonant capacitor AC rating at 30–50 kHz**, the binding limit in most
   remaining full-bridge failures (the 650 V screen is itself an assumption).

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
- The capacitor limit is a single 650 V peak screen for both topologies. The half
  bridge includes the Vbus/2 DC bias on its split capacitors; the full-bridge
  series capacitor carries pure AC.
- Pan classes are independent draws. Temperature dependence of pan
  resistivity and permeability (and Curie effects near 700 °C+, not reached in
  cooking) is ignored.
- Grid points use 4,000 samples, so ties within about 1 % are noise.
