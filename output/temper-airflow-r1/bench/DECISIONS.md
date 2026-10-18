# Jet bench decisions (2026-10-15)

Numbers come from `plate-design.json`, `setpoints.json`, `cad/rig-cad.json`, `selftest.json`,
`logger-selftest.json` and `bom.json`.

## J1. Plate: 6061, 3 mm, the strip's exact footprint. No FR-4 coupon.

**Al 6061 at 3 mm:**
- Spreading length √(kt/h) is 70.8 mm at h 100, against the 11 mm jet pitch.
- Under a stress pattern (±60 % ripple at the jet pitch × ±40 % ramp along x, both signs), the mean of three
  thermocouples (x 15/45/75) gives the isothermal h within 0.5 % at h 100 and 1.2 % at h 240. That is what Martin
  and the board model mean by h_top.
- fit.py carries this as a uniform systematic.

**Cu 2 mm:** halves that error (0.8 %) for more money and machining. Not needed.

**FR-4 2 oz coupon, rejected:**
- Spreading length 16.7 mm, longer than the pitch, so local h is smeared out.
- Plate spread up to 41 % of the rise.
- Its uniform-flux h differs from the isothermal h by up to 1.6 %, with no better area mean.
- Local maps would need IR on a thin foil, which is outside this kit.

## J2. Guarded plate, not a foam-backed plate with a loss calibration

**Unguarded:**
- The plate sunk flush in XPS loses 3.9 % of hA at h 100 (2D finite differences).
- That rises to 11.5 % if the foam top beside the plate is jet-cooled. At still air it is 39–115 % of hA.
- A still-air baseline cannot separate this from h, because still-air h is itself unknown. A two-insulation method
  needs a second build and still leaves the edge term.

**Guarded:**
- A 6061 tray around and under the plate (1 mm gap, RTV seam, 3 mm rim) is held at plate temperature by a PI loop.
- The plate's balance then sees only G_gap × (T_p − T_g). G_gap is 0.13 W/K from its paths, with the anchored leads
  and the RTV bead dominating; it is measured on the day by the +3 / +6 K guard-offset runs.
- At a 0.1 K null the residual is 0.36 % of the plate power at h 100 before correction.
- Self-test: G_gap recovered within 15 % (0.1115 against a true 0.11), and per-run h within 0.3 %.

## J3. Heaters: TO-220 thick-film resistors

- 2 × 10 Ω in series, centred at x 30 and 60. A plate this conductive does not care where the heat enters (J1).
- 3.7 W at h 100 and 8.9 W at h 240 for a 25 K rise, at 8.6 V / 0.43 A and 13.4 V / 0.67 A: all inside the INA226
  module's 0.82 A.
- Kapton film heaters in a 90 × 16.5 size are not a stock part, and an etched-trace PCB adds a design and order step.
- The guard uses the same resistors from 12 V PWM (7.2 W maximum).

## J4. Obstructions replicated, because they bound the spent-jet path

Under the box, the channel is closed on both sides and the −x end:
- **−y side:** TO-247/BR1 fronts at y 6.9 to z 9, the FR-4 pressure-strip face at y 9.5 from z 9 to 23 (1.0 mm slit
  to the box), and the two locating ribs.
- **+y side:** C38–C41 bodies at y 23.7, 18 × 9 × 17.5 mm, with 3.8 mm gaps (1.2 mm slit to the box).
- **−x end:** F3 leg B, only 2 mm above the board.

The spent air must leave by the +x end, the cap gaps and the two slits, so the rig reproduces all of them
(`cad/rig-cad.json` checks the gaps).

**Simplifications:**
- The package gaps in the −y wall end on the AlN tile (dead ends), so the wall is continuous.
- The board beyond x 94 and y 27.5 is a flat unheated deck.

**HANDOFF inconsistencies found:**
- **Box walls.** Item 1's "10.5 × 7 inside, 1.0 mm walls" does not fit its own 12 mm Y envelope, which allows 0.75 mm
  side walls.
- **Leg B.** Item 2's "12 × 14 inside" does not fit leg B's 12 mm Y envelope.
- **What the rig keeps.** It keeps the envelopes, because they bound the channel, and a 10 × 14 leg-B bore. Upstream
  of the manifold this does not matter, since the set variable is manifold pressure (J5).
- **R45 must pick one.**

## J5. The set variable is manifold pressure, Re-matched. Blower volts are not.

**Why not volts:** the rig has no sink or coil branch and no bay vent, so blower volts do not map to jet flow. The
push hood is represented by a stand-in box, the product blower and a taped bleed. Its only job is a steady,
low-velocity supply at the needed pressure.

**How the transfer works:**
- The same holes give the same Cd, so v = Cd·√(2Δp/ρ) in both rig and product. Matching Re at film properties gives
  Δp_rig = Δp_prod·(ρ_r/ρ_p)(ν_r/ν_p)², with Cd cancelling.
- Δp_prod is delivery.py's jet-orifice drop at each drive: 15.10 Pa at the floor, 20.96 at 0.55 and 61.59 at full.
  It is only weakly Cd-dependent: Cd 0.58 / 0.72 moves it to 22.04 / 19.80 Pa at 0.55, whereas the flow itself moves
  more. fit.py propagates this.
- Product film is 77.1 °C: jets at 50 °C (D-18) and the strip at 104.1 °C, the FET-row maximum of the c28 h 100 run.

**Rig targets at 24 °C:** 11.10 / 15.40 / 45.26 Pa. Re (film) is 519 / 611 / 1047. delivery.py's Re at 50 °C
properties is 571 / 671 / 1152.

**Cd caveat:** the cancellation holds only if rig and product holes match. Hence drilled and deburred, not chamfered,
like R45's machined G11 prototype. The R45 A1/A3 bench can measure the product's own manifold Δp with the same
SDP810, which closes the loop on the real enclosure.

## J6. Flow: Δp + Cd by default; a flow meter is optional and worth about 1.4 points of U95

- **Without a meter:** Cd 0.65 ± 0.05 (1σ) is used for the reported Re and CFM, and for delivery's network
  sensitivity. U95 at drive 0.55 is 3.4 %.
- **With a thermal mass flow meter** (in line or as separate `flowcal` runs): Cd is measured (the self-test recovers
  0.683 against a true 0.68) and U95 falls to 2.0–2.4 %.
- **Rotameters ruled out:** their pressure drop at 12–25 L/min is comparable to the blower's.

## J7. Reference temperature: jet air in the manifold

- The spent air is heated hard: NTU = hA/(ṁcp) is 0.46–0.96 across the drives.
- So h is referenced to the jet supply temperature (a thermocouple in the manifold), as Martin and delivery.py are.
- The exit-air thermocouple is only a rough energy-balance check.
- The ceiling sweep uses bay air (55/61 °C) where the jets actually carry 50 °C hood air, which is conservative (D4).
- **Still air:** the reference is the hood Pt100 (room).

## J8. Radiation: bare machined aluminium, subtracted

- ε 0.08 ± 0.04 gives h_rad 0.54 W/m²K at 37 °C, under 1 % of h 100. It is subtracted, with its uncertainty, in
  fit.py.
- Painting the plate black (ε 0.9) would add about 6 W/m²K that the model does not count. The measured h is
  convective; the product's solder-mask radiation is unclaimed margin.

## J9. Limits of the replica (not inside U95)

- **Smooth plate.** No SMD bodies; their heights are about 1 mm or less. Bound it with the optional bumps run.
- **Unheated surroundings, and room-temperature jets.** The jets are transferred by Re matching, with the property
  reference drawn anywhere between jet and film temperature.
- **Continuous −y wall.**
- **Open +x end.**
- **H 6.0 ± 0.1.** The height runs at 5.5 / 6.5 measure d ln h/dH directly. Martin's figure is −0.018 /mm; the
  self-test recovers an imposed −0.06 /mm within 0.001.

These are why a MARGINAL result should be treated as a FAIL until the enclosure soak (HANDOFF bench, 40 °C ambient,
28 A) confirms it.

## J10. Instrumentation

- **One MAX31856 per thermocouple:** 6 channels plus 1 optional. 0.0078 K resolution, and all plate, guard and
  jet-air beads come from one 5-pack lot, so relative gain error is ≤ 0.2 % (1σ).
- **In-situ zero:** an overnight soak with everything off, referenced to the hood Pt100. It is accepted only at
  ≤ 0.1 K/h room drift, which keeps the lag error ≤ 0.03 K. The self-test recovers ±0.4 K offsets within 0.03 K.
  A blower-on zero is not isothermal, because the blower heats its air.
- **INA226** for plate V and I, checked against a DMM.
- **SDP810-125Pa** for manifold Δp: zero 0.08 Pa, 3 % of reading, I²C.
- **Firmware** emits raw records. The host converts them, runs the guard PI (the PWM drops to 0 if the host is
  silent for 5 s) and writes 1 Hz CSVs. Offsets are applied in fit.py, so a later zero can re-correct old runs.
- **The firmware was not compiled here** (no Arduino toolchain), as with the sensor-r3 kit. Compiling it is the first
  bring-up step.

## J11. Uncertainty and the verdict rule

**Monte Carlo** (4000 draws) over every 1σ systematic in `bench.json`, shared across runs:
- G_gap, ε, area, power gain, per-channel offsets, thermocouple gain, Δp gain;
- the isothermality bias (J1), the property reference temperature, the product strip temperature ±10 K;
- Cd through delivery's network, and H ± 0.1 mm × d ln h/dH.

Each run's statistical noise is added on top and inflated by the Birge ratio when repeats scatter more than their
noise.

**Verdict at drive 0.55, per board-h-sweep case:**
- **PASS:** the 2.5 % bound ≥ required h_top.
- **MARGINAL:** the median clears it but the bound does not.
- **FAIL:** the median is below it.

**Ceiling:** `ceiling_by_h`, linear in h, held flat above h 150 (the sweep's top; bay 61 is U26-limited at 29.5 A
there). The 28 A Kconfig cap still applies.

**Self-test outcomes:**
- truth 125 → PASS;
- truth 100 → MARGINAL;
- truth 88 → FAIL;
- the true value lies inside U95 at every drive in every scenario.

**The PASS line for c28 at a 61 °C bay is a measured h of about 99.2–100.7** (Martin × 0.60). The design basis is
therefore the pass line itself.

## J12. Transient cross-check

After a plate-power step, the integral form θ + (G_gap/C)∫θ_g = (ΔP/C)t − (G/C)∫θ is linear in ΔP/C and G/C. The
power meter drops out, and the lagging guard is corrected. It rests on the weighed heat capacity C. In the self-test
it lands 2.6–3.5 % below the steady h, consistent with the synthetic plate's C being 2 % above the configured value.
It is a cross-check, not a verdict input.

## J13. Still air under the jet box is a finding, not just a baseline

The model floors h_top at 10 W/m²K, and the loss-of-airflow clamp (18 A) leans on still-air ceilings. With a lid
6 mm above the strip, natural convection may fall below 10. `fit.py report` prints the still-air convective h against
that floor. If it is below 10, the power stage re-derives the blower-failure clamp ceiling with the measured value.
