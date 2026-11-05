# Board envelope for the enclosure redesign (2026-11-05)

The enclosure is being redesigned, so this checks no particular box. It lists what any box for the Rev F board has to accommodate, so the new design can be checked against it.

Run it with `~/.local/share/temper/cadenv/bin/python validation/enclosure-envelope/board_envelope.py` (OCP is needed). It writes `board-envelope.json`.

Method:
1. KiCad's Python dumps every footprint.
2. OCP reads each part's STEP model and places its bounding box like the footprint. The board has no model offsets or rotations, which the script asserts.
3. Each model is compared with the footprint's own F.Fab body outline.
4. Mounting-hole copper is measured on F.Cu and B.Cu.

Bounding boxes are conservative.

## What any box must take

**Board.** 100.0 × 100.0 × 1.6 mm, every part on the top side. The front edge is the BNC side (y min).

**Height.**
- **Above the board:** the four BNCs are tallest. Their flange is 13.55 mm on the SAMZO drawing, and the model gives 13.75 mm.
- **Next tallest:**
  - J4–J6 headers, 8.54 mm if fitted (they are DNP);
  - C117, 6.9 mm;
  - relays K1–K4, 5.6 mm;
  - L1 and L2, 4.0 mm;
  - J1, 3.26 mm on HRO's drawing (the model's 4.2 mm includes a floating logo).
- **Below the board:** the BNC legs reach 2.2 mm below the bottom face in the model. They are hand-soldered and can be trimmed. The DNP headers would reach 1.4 mm. J1's shell legs pass through the board too, but its model has no legs.
- **Rule:** standoffs of at least 3 mm, and at least 14 mm clear above the board. A 36 mm box has room to spare; anything over about 20 mm inside works.

**Past the edges.**

| Edge | Part | How far | Height above the board top | Note |
|---|---|---|---|---|
| Front | J3, J7, J8, J9 BNCs at x = 67, 89, 111, 133 (22 mm pitch) | Barrels reach 18.4 mm past the flange face; the flange stands 0.1 mm proud of the board edge | Axis at 6.78 mm; flange Ø13.55 | Wall clamped between flange and nut on the M12 thread, about 6.6 mm long. Wall + toothed washer + nut ≤ 6.6 mm; the nut's thickness is not on the drawing, so measure one |
| Front | D4, side-looking status LED, at x ≈ 55 | Lens flush with the edge (0.2 mm inside) | 0–0.6 mm | The wall needs a hole or light pipe right at board-top height |
| Left | J1 USB-C, centred at y = 122 (77 mm behind the front edge) | Shell flare at the edge, body 0.3 mm inside | Shell 3.26 mm tall; axis about 1.63 mm above the board top | See "J1 3D model" below. The cutout must pass the cable's overmold, unless wall + gap is less than the plug shell's reach. Measure the cable you will use |
| Back | SW1 BOOTSEL | 0.43 mm inside the edge | 2.0 mm | Pressed from the top (TS-1088); see access below |

**BNC panel.**
- Nut corners are 16.11 mm across (13.95 A/F), which leaves 5.89 mm between neighbouring nuts at 22 mm pitch. An open-ended spanner fits; a 14 mm socket must be under 22 mm in outer diameter.
- The barrels reach 18.4 mm past the flange. A board carrying its jacks therefore cannot be lowered into a one-piece tray with round front holes. Use one of these:
  - a separate front panel, fitted to the jacks first and then dropped into the tray with the board;
  - slots open at the top that the lid closes;
  - a U-cut front wall.

**Mounting holes.** Four M3 holes (3.2 mm NPTH) at (54, 54), (146, 54), (54, 141) and (146, 141): a 92 × 87 mm pattern. Every part is at least 3.93 mm from a hole centre: U3 at H3, then C81 at H4. An M3 head, a 7 mm washer and a 5.5 mm A/F standoff all fit.

**Mounting-hole copper: use insulating hardware at H3 and H4.**
- **H3 and H4:** the B.Cu GND pour reaches 1.8 mm from the hole centres, and an F.Cu GND track passes 3.3 mm from H4. A metal standoff or washer there sits on GND copper with only solder mask between.
- **H1 and H2:** clear. Nearest outer copper is 4.6 / 5.45 mm (H1) and 5.58 / 8.06 mm (H2).
- **Why it matters:** the chassis-grounding decision (rev-f-plan, 2026-10-29) bonds the box to circuit GND at the front panel only. A second bond at the back corners would close a loop around the analog core.
- **Fix:** nylon standoffs, or insulating shoulder washers at H3 and H4, with nylon at all four for simplicity. This is a box rule, not a board change.

**Access.**
- **BOOTSEL (SW1) and RESET (SW2)** are pressed from the top, 0.4 and 4.9 mm from the back edge. With the lid on, either put pinholes in the lid over (85.2, 143.1) and (93.0, 138.6), or re-enable the firmware's 1200-baud reset (audit R4). Then BOOTSEL is needed only to recover a bricked board, with the lid off.
- **Debug LEDs D15–D20** are 1.1 mm tall and visible with the lid off only. D4 is the one meant to show through the wall.

## J1 3D model is 1.2 mm behind the real part

J1's STEP model, which `cad/tools/models_3d.py` builds from EasyEDA's library, sits 1.18 mm further back than the footprint:
- Its shield-leg feet sit 1.18 mm behind the footprint's shield holes. Their 4.2 mm spacing is right.
- Its front face is at x = 51.5.

The footprint's F.Fab outline puts the 7.4 mm body at x = 50.3–57.7 with the flare at 50.04, which agrees with HRO's drawing (body 7.35 mm). So the receptacle is flush with the board edge. A board STEP export, or the renders, would show it recessed 1.5 mm.

**Use this file, not the STEP, for the USB-C cutout.** The fix is a per-part shift in `temper_boardkit.jlc.models_3d` (shared tooling). It is not made here.

The only other model off-centre from its fab outline by more than 0.3 mm is C117, by 0.61 mm. That is the polymer can's asymmetric terminals, which is harmless.

Drawing: [HRO TYPE-C-31-M-12 (2020-12-08)](https://datasheet.lcsc.com/datasheet/pdf/9e56b777c022540fcce7c7f67825f55e.pdf?productCode=C165948), sha256 `6ae33d50…a1a9e`, the same file the pinout ledger cites.
