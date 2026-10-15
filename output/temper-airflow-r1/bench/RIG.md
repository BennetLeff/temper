# RIG: build the jet bench

**Frame:** native-21 model x/y in mm (as HANDOFF.md). z is measured above the board top, which here is the test
plate's top face. Every part named below has a STEP file in `cad/` (and an STL if printed). `cad/rig-cad.json`
records the geometry checks:
- jet floor 6.000 mm above the plate;
- box 1.0 mm from the pressure-strip face and 1.2 mm from the film caps;
- plate-to-guard gap 1.0 mm;
- jets open, no part overlaps.

```
 section at x = 45 (looking +x)          z
                                         23 ┬ pressure strip face (y 9.5)
   -Y wall ▓▓▓▓▓│                            │
                │1.0  ┌─tap──┐  1.2│▓▓▓ film cap block (y 23.7, h 17.5)
                │     │manif.│     │▓▓▓
         y 6.9 ▓│     │10.5x7│     │▓▓▓     15 ┬ box top
           ▓▓▓▓▓│     └─o────┘     │▓▓▓      6 ┴ jet floor underside (jets at y 14.0)
           ▓▓▓▓▓│    plate 6061 90 x 16.5 x 3 │▓▓▓      0 ─ plate top = guard rim top
        ═══guard tray (1 mm gap, RTV seam, 3 mm rim)═══
        ░░░░░░░ XPS 50 mm ░░░░░░░░░░░░░░░░░░░░░░░░░
```

## 1. Machined parts (JLCCNC, 6061-T6)

| Part | File | Notes for the quote |
|---|---|---|
| Test plate | `cad/plate.step` | 90.0 × 16.5 × 3.0 mm, ±0.05 on width. Top face fine-milled, Ra ≤ 1.6 µm, flat ≤ 0.05 mm, no anodise and no paint (ε 0.08 ± 0.04 assumed, DECISIONS J8). Three Ø1.0 × 2.0 mm blind holes from below at x 15 / 45 / 75, y 15.25. Break the edges ≤ 0.1 mm. |
| Guard tray | `cad/guard_tray.step` | Pocket 92 × 18.5 × 10 deep, giving a 1.0 mm gap all round the plate. Ears with Ø3.4 holes. Four Ø2.5 holes, tapped M3, for the plate supports. Wire exits Ø4/Ø5. Two Ø1.0 × 10 mm thermocouple holes up into the +y rim at x 15 and 75. |

## 2. Printed parts (PETG or ASA, 0.4 mm nozzle, 100 % infill)

| STL | Orientation | Notes |
|---|---|---|
| `duct_lower` | Split face (z 10.5) down | Jet floor, lower walls and lower legs. The floor underside, which faces the plate, prints as the top surface, so enable ironing. |
| `duct_upper` | Split face down | Lid, with three bosses: tap `p_mid` at x 44, tap `p_end` at x 86, jet-air thermocouple port at x 66. Also the end tab and the leg-A flange. |
| `wall_minus_y` | On its −y face | TO-247/BR1 fronts at y 6.9 (z 0–9) and the pressure-strip face at y 9.5 (z 9–23), x −4..113. Includes the hanger arm at x 89–95. |
| `film_cap_1..4` | Base down | 18 × 9 × 17.5 mm C41/C40/C38/C39 bodies, with a locating peg. |
| `deck` | Flat | 163 × 53 × 6 mm. Window and ear recesses for the tray, peg holes. |
| `hood_box`, `hood_lid` | Open side up | Push-hood stand-in, with a 12 × 14 feed hole at x −36..−24, z 3..17 (R45-C-PUSH-HOOD). Blower opening 40 × 30 (gasket it to your blower's outlet), baffle, Pt100 port, five Ø8 bleed holes in the lid. |

**Jets:**
- Printed holes come out undersize. Open all eight to Ø3.0 with a new HSS drill in a pin vise, from the inside
  while the duct is still in halves.
- Deburr both edges with a few hand turns of a countersink. Remove the burr only and keep the edges sharp: the R45
  prototype holes are drilled G11, and the rig's Cd should match theirs (DECISIONS J5).
- The Ø3.0 drill shank must pass every hole.

**Close the duct:** glue the halves with thin epoxy and 2 mm dowels in the leg-A lugs. Wick CA along the outside
seam. Then glue a 1/8 in brass stub into the `p_mid` socket (and into `p_end` if you log end pressure too; otherwise
plug it).

## 3. Plate and guard assembly

1. **Plate heaters.** Bond two TO-220 resistors (10 Ω, isolated tab) tab-down to the plate underside with thermal
   epoxy. Centre them at x 30 and x 60, y 15.25, with the leads pointing +x.
2. **Plate cut-out.** Bond one KSD9700 70 °C cut-out at x 3–12. Wire it in series: the two resistors (20 Ω) plus the
   cut-out.
3. **Plate thermocouples.** Pot three beads (T_p1 to T_p3, from one 5-pack lot) into the Ø1.0 holes with thermal
   epoxy. Check each bead's isolation to the plate: more than 1 MΩ.
4. **Weigh the plate assembly.** Set `plate.C_J_K` in `bench.json` to Σ m·cp, using 6061 at 896 J/kgK and resistor
   and epoxy at about 800 J/kgK. The value is used only by the transient cross-check.
5. **Guard heaters and cut-out.** Bond two TO-220 resistors to the tray underside at x 20 and x 70, plus a KSD9700
   in series. Pot the guard thermocouples T_g1 and T_g2 into the rim holes.
6. **Thermal anchors.** Run every plate lead and thermocouple along the pocket floor for at least 10 mm and bond it
   there before it leaves through the floor holes. This anchors it to the guard, so lead conduction is nulled.
7. **Plate supports.** Thread four nylon M3 set screws through the pocket floor, set the plate on them, and adjust
   until the plate top is flush with the rim. Check with a straightedge and feelers: step ≤ 0.02 mm.
8. **Seal the seam.** Mask with Kapton tape, run high-temperature RTV into the top of the 1 mm seam, strike it flush,
   and peel the tape.

## 4. Stack-up

1. Cut a pocket in the 50 mm XPS slab for the tray body and the guard resistors, about 100 × 30 × 20 mm deep. The
   tray's ears sit in the deck's recesses, and the deck lies on the foam.
2. Screw the ears to the deck (M3 into PETG). The plate top, rim top and deck top must be coplanar within 0.1 mm.
3. **Wall block:** pegs into the deck, bearing on the guard's −y rim.
4. **Duct:**
   - The elbow foot sits on the deck at x −37..−23. The end tab goes under the wall's hanger arm with an M2 screw.
   - The two ribs bear on the strip face, which sets the 1.0 mm gap.
   - **Jet height:** with the film-cap blocks not yet fitted, slide the Ø6.0 drill shank in along y under the floor at
     x 10, 45 and 80. It must pass, and Ø6.1 must not. Shim the foot or tab to suit; the target is 6.0 ± 0.1 mm.
5. **Film-cap blocks:** pegs into the deck.
6. **Hood stand-in:** stands on the bench (its bottom at z −56) with the leg-A flange screwed to its +y wall over a
   foam gasket. Put foam tape between the blower outlet and the 40 × 30 opening. Push the Pt100 probe through its
   port into the hood air. Tape over bleed holes to trim (PROCEDURE C).
7. **Jet-air thermocouple:** T_air goes through the Ø1.2 port with the bead at the manifold centre (z ≈ 10.5), sealed
   with RTV. The exit-air bead (T_exit, optional) hangs 5 mm beyond the duct's +x end at z 3.

## 5. Wiring

| Signal | ESP32-S3 | Device |
|---|---|---|
| SPI SCK / MISO / MOSI | 12 / 13 / 11 | All MAX318xx |
| MAX31865 CS | 10 | Pt100, hood air (the sensor-r3 converter; 4-wire jumpers set) |
| MAX31856 CS, channels 0–6 | 9, 14, 15, 16, 17, 18, 21 | T_p1, T_p2, T_p3, T_g1, T_g2, T_air, T_exit (`bench.example.json` → `tc_channels`) |
| I²C SDA / SCL | 1 / 2 | INA226 (0x40), SDP810 (0x25); 4.7 kΩ pull-ups to 3V3 if the modules lack them |
| Guard PWM | 7 | Logic-level MOSFET module → guard heater (20 Ω + KSD9700) from 12 V; at most 7.2 W |
| Marker | BOOT (0) | Press at a transient step |

**Plate heater:** bench supply (current limit 0.8 A) → INA226 VIN+ → shunt → VIN− → KSD9700 → resistors → return.
The INA226 reads bus voltage at VIN−. Measure the round-trip lead resistance from there to the resistor terminals
with the DMM and enter it as `r_lead_ohm` (the 0.03 Ω default is a placeholder). At 0.43 A (h 100) the leads carry
about 0.1 % of the power.

**SDP810:** the "+" port goes to the `p_mid` stub, and the "−" port stays open to room air beside the rig (the
channel exhausts to the room).

**Blower:** 12 V adapter → buck module → BFB1012VH-F00. The volts only trim the hood pressure. The set variable is
the manifold pressure.

## 6. Pre-bench checks

1. Heater resistance 20.0 Ω ± 2 % cold. Both KSD9700s closed.
2. Every thermocouple reads room temperature within ±1 K raw. No faults in `jet_logger.py` output.
3. SDP810 reads within ±0.2 Pa with the blower off.
4. INA226 against the DMM at about 0.4 A: within 0.5 % on V and I (PROCEDURE B).
5. Jet height 6.0 ± 0.1 at three stations. Ribs touching the strip face. Film-cap blocks seated.
6. `python3 jet_logger.py --selftest` and `python3 fit.py --selftest` both print PASS on the bench laptop.
