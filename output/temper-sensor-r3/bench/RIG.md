# Bench rig: C1-surrogate probe, jig and logger

This is the hardware for the cookware contact survey (`PROCEDURE.md`). The
survey measures each pan's dry contact conductance h_c. `fit.py` then turns
h_c into C1's contact lag τ63 and gates it against 1.2 s, the bar in
`../DECISIONS.md` §5. Numbers below come from `jig.py` → `jig.json`,
`surrogate.py` → `surrogate.json` and `bom.py` → `bom.json`.

## 1. The surrogate probe

The probe copies C1 where the contact is decided:
- the face: Ø8 disc, contact Ø7.6, lapped Ra ≤ 0.1 µm, flat ≤ 1 µm;
- a mount that follows the pan's tilt;
- the spring force, 1.2–1.8 N;
- the proud height, 0.60 mm.

It does not need C1's heat capacity, because the fit measures h_c, not τ63.

| Part | Choice | Why |
|---|---|---|
| Contact disc | **Option A:** Si3N4 0.32 mm (e.g. Innovacera SN-90), laser-cut Ø8, 0.2 × 45° chamfer, top lapped to Ra ≤ 0.1 µm. **Option B:** 99.6 % polished thin-film alumina 0.254 mm (e.g. CoorsTek ADS-996 class), laser-cut Ø8. | A is C1 itself: C_cap 40.4 mJ/K, 0.0 % off. B is +20.2 % (48.6 mJ/K), outside ±15 %, so `fit.py` applies the model correction: it fits h_c with the probe's own C_cap, measured by weighing. Option C, as-fired 96 % alumina, is within 15 % (+13.8 %), but its rougher face would change h_c, which is the quantity being measured. Don't use it. (`surrogate.json`) |
| Element | IST P0K1.202 family Pt100, class F0.15, Pt/Ni wire (e.g. P0K1.202.6W.A.007, rated to 600 °C). Supplier listings give a 2.0 × 2.0 mm footprint. | Same family as C1. Its time constant is calibrated (§4), so the exact chip size doesn't matter. |
| Bond | EPO-TEK 930-4 boron-nitride epoxy, 0.10 mm bondline, cured per datasheet. Element centred under the disc. Post rim bonded to the disc. | Same as C1. A survey at 150–230 °C is within its intermittent rating. |
| Leads | 4-wire: two 30 AWG PTFE-insulated wires welded or crimped to each element lead within 5 mm of the chip, out through the post's Ø3 bore and its side exit. | 4-wire removes lead resistance. |
| Post | Turned PEEK (Vespel if available) per `jig-post.step`: Ø8 neck with 0.5 mm wall, 8.48 mm long; Ø12 shoulder (its top face is the up-stop); Ø6 foot with a 90° cone for a Ø3 ball. Pack the neck cavity under the chip loosely with ceramic fibre. | The bench neck wall is 0.5 mm, not C1's 0.25. The leak is a small fraction of the contact conductance (0.8 mW/K against about 40 mW/K at h 888). The fit carries it with a ±50 % allowance, worth 0.010 s at h 888 (DECISIONS D6). |
| Holder | 6061 per `jig-holder.step`: flange registered on the plate underside (3 × M3 on PCD 34), a 4 mm guide bore Ø8.3, and a counterbore Ø12.6 for the shoulder. | The loose guide (0.15 mm radial) leaves 37.5 mrad of free rocking about the ball, so the face follows the pan, like C1's rocking post (G5). |
| Spring | Stainless compression spring, OD ≈ 5.5, free length ≈ 16, rate 0.2–0.4 N/mm, on an M10×1 plug (1 mm per turn). | At rate 0.3: 1.32 N at rest, **1.50 N with the disc pushed flush**, 1.92 N at full stroke. One plug turn moves the force 0.3 N. Set and check it on the force scale (§3). |
| Plate ("glass") | A 4 mm glass-ceramic offcut, about 300 × 300, with an Ø18 diamond-cored bore. Fallback: 6 mm calcium-silicate board, machined flat. | Same surface, thickness and bore as the product. Glass-ceramic takes a 250 °C pan without thermal-shock risk. |
| Proud height | Built 0.80 mm with no shims. Add 0.20 mm of shim stock under the flange for 0.60 mm, and check it with the dial indicator. | Shims can only lower the disc. 0.5/0.7 mm runs use ±0.1 mm. |

`jig.json` checks the stack-up:
- 0.60 mm proud is reachable;
- stroke to the hard stop is 2.5 mm, against ≥ 1.2;
- rocking is ≥ 5 mrad;
- force at flush is inside the window;
- the spring is not solid at full stroke.

## 2. Pan reference

A fine type-K bead (30–36 AWG) on the pan base, read by a MAX31856. Place it
**inside the plate bore, 6.5 mm from the contact centre**: outside the Ø7.6
contact, inside the Ø18 bore, so no plate sits under either point.
(Revised 2026-10-15; this used to be 15 mm, over the plate. See DECISIONS L6
and `plate_check.py`.)

Mount it one of two ways:
- **Preferred, on pans you own for the survey:** drill Ø1.0 × 1.0 mm deep
  into the base, insert the bead, and peen the rim over it.
- **On borrowed pans:** tape the bead flat to the base with polyimide tape,
  inside the bore annulus, clear of the disc. Route the leads out along the
  base to the bore edge.

The fit uses only the reference's **slope** over the 9 s window. Its offset
is a free parameter, so the taped mount is acceptable (DECISIONS D8).

**Also:** before the first set-down of a session, warm the plate by resting a
hot pan on it for a few minutes. It cuts the plate-induced gradient further.

## 3. Set-up checks before any run

1. **Disc mass** on the 0.001 g scale, entered in `probe.json` as `disc.mass_mg`.
2. **Element mass (optional):** weigh 5 spare elements together, leads
   trimmed, and use the result for `element.C_el_J_K`. That shrinks the
   largest uncertainty term (DECISIONS D6).
3. **Proud height:** 0.60 ± 0.02 mm (dial indicator).
4. **Tip force at flush:** press the disc flush with a flat bar resting on
   the force-scale pan. It must read 1.40–1.60 N (143–163 g) for
   `dry_nominal`, 1.20 N for `dry_force_low` and 1.80 N for `dry_force_high`.
5. **Paste calibration** (`PROCEDURE.md` §3), giving `tau_int_s`.

## 4. Logger

**Hardware:**
- ESP32-S3-DevKitC-1, with an Adafruit 3328 (MAX31865, PT100, 4-wire) and an
  Adafruit 3263 (MAX31856, type K) on one SPI bus.
- Wiring is in the header of `logger_fw/logger_fw.ino`.
- Both converters run in auto-conversion mode: the Pt100 at about 60 Hz
  (60 Hz notch, 16.7 ms continuous conversion), the thermocouple at about
  10 Hz.
- Each record carries the ESP32 microsecond timestamp, so the two channels
  share one clock. No separate sync is needed.
- The BOOT button writes a marker record.

**Host:** `logger.py` (needs `pyserial`) writes one CSV per set-down with
the metadata `fit.py` needs, prints a live readout, and warns below a 20 Hz
Pt100 rate or on any MAX31865 fault. `python logger.py --selftest` checks
the parser without hardware.

## 5. Cost

All prices are estimates from `bom.py` → `bom.json`, list prices, not quoted.

| Kit | Estimate | What it includes |
|---|---|---|
| **Lean (recommended)** | **About $313** must-buy, plus $65 optional | Everything in §6 |
| Reference | About $1,285 | The C1-exact Si3N4 disc lot ($250 quote), shop machining ($250) and full metrology |

Both exclude the oven and the cookware.

## 6. Lean kit (DECISIONS L1–L7)

| Part | Lean choice | Why it doesn't change the answer |
|---|---|---|
| Logger | ESP32-S3 devkit + Adafruit MAX31865 + generic MAX31856 + generic type-K bead ($48) | It's a one-off instrument. A JLC board costs more and is slower (L1). |
| Disc | 99.6 % polished alumina 0.254 mm, cored Ø8 from one 25.4 mm substrate with a diamond core bit (8.0–8.3 mm *inside* diameter), chamfered by hand on a diamond plate | This is option B, already the self-test case. The fit uses the weighed heat capacity and the measured contact diameter. The face finish is the same class (Ra ≤ 0.1 µm). |
| Element | IST P0K1.202, 2 (1 + 1 spare) | Same as the reference kit. A cheaper, bigger M222-class chip failed the self-test tolerance at the bar (L3). |
| Bond | High-temperature conductive epoxy (Omega OB-200 class). Verify ≥ 230 °C before buying. | The bond's conductance shows up only in τ_int, which the paste calibration measures. |
| Post | PEEK, JLCCNC from `jig-post.step` | It touches the disc, so it needs a high-temperature polymer. |
| Holder | 6061, JLCCNC from `jig-holder.step` | Under the plate; stays well below 100 °C. |
| Spring plug | M10 × 1 fine-thread stainless set screw | Replaces a turned part. |
| Plate | Replacement glass-ceramic panel for a portable induction cooker, ~280 × 280 × 4 mm, with an Ø18 diamond-cored bore | Same material as the product. Porcelain tile or calcium-silicate board also pass if checked flat. **Never metal** (L6). |
| Metrology | Must buy: a 0.001 g scale. Own or borrow: kitchen scale (force), digital caliper in step mode (proud height), steel rule + feelers (pan flatness), oven mitts, a drill press or stand. Optional: dial indicator, roughness comparator. | Pan Ra class is metadata only; the fit measures h_c directly. |
