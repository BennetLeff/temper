# Candidate 36: shunt constants for the controller owner (conditional), 2026-10-15

Status: request, power-stage side, **conditional: nothing changes unless R5 becomes 0.5 mΩ**. Candidate 36 evaluated
R5 → Bourns CSS2H-2512R-L500F (0.5 mΩ) and did **not** adopt it (`README.md` section 4,
`results/shunt_half.json`). Nothing on the controller branch or in `firmware/` is edited from here. This file lists
what would have to change if a later OCP rework adopts the 0.5 mΩ shunt.

## What reads R5 today
The controller has no analog reading of R5. R5 reaches it only through the power board's hardware OCP comparator
(U6), whose output is ORed into J4.10 `bus_fault` (controller `README.md` J4 table: "bus_fault enters the interlock OCP
input"). So **no firmware or controller constant scales with R5 today**. That is why the change is a power-board
question first.

## If R5 becomes 0.5 mΩ (any later candidate)
1. **Recorded OCP band (documentation constant).** The controller cites the shunt-OCP band in
   `zapote/controller/evidence/rms-alternatives/README.md:33` ("shunt OCP 66.30-118.74 A", the stage-15 figure; the
   s38 board gives 67.77-116.44 A after the Kelvin shift). With 0.5 mΩ and the threshold divider re-chosen for the same
   nominal trip, the band widens to about 37-129 A, or 77-167 A if the divider is chosen to hold the 64.17 A floor
   (`results/shunt_half.json`). Any controller fault-coordination text that assumes the hardware OCP trips by 118 A
   must be re-read against the new upper edge.
2. **Pending AMC1301 input-current measurement on R5 (temper-8d S13 request, `OPEN-ITEMS.md` S13).** If that channel
   is built, its firmware scale is A per mV = 1 / R5: 1.0 A/mV at 1 mΩ, **2.0 A/mV at 0.5 mΩ**. The 59.2 A envelope
   peak would give 29.6 mV at its input (59.2 mV at 1 mΩ). Resolution and input-offset error, counted in amps, double;
   that candidate re-reads the AMC1301 offset and range limits on the datasheet (not read here).
3. **Commissioned still-air ceiling (DECISIONS 46 / 51 request, unchanged by this file).** The B3 release gate is not
   met at 22 A on s38. Candidate 36's copper result is in `README.md`. The ceiling request stays with the owner until
   candidates 36 and 39 have both landed.

## Not asked
- No pin, connector, or J4 net change.
- No change to PWM, PERMIT, or interlock timing. The OCP comparator's RC (R32 ∥ R33 = 5 kΩ, C30 100 pF, τ 0.5 µs)
  does not depend on R5.
