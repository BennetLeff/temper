# Heatsink and spreader bar: drawing notes (native-21, enclosure R32)

Status: notes for the sink and bar drawings, 2026-10-09.
- **Geometry:** the enclosure (R32, `output/temper-r32-studies/R32-PLAN.md`; R31 for the pose) owns it. These notes set what the power stage requires of it.
- **World frame:** R31: x − 141, 236 − y, 26 + z from the board.
- **Decisions:** DECISIONS.md 2026-10-08 (M11), 2026-10-09 (sink mounting, PE bond, R31 / BR1, R32 package).

## Sink (S8, enclosure R32; DECISIONS 2026-10-09 R32 package)

1. **Profile:** 6063 extrusion, 8 mm base, 15 × 1.5 mm fins on a 3.0 mm gap (67.5 mm stack), 40 mm fin depth, fins along X. Envelope X −149..−32, Z 15.5..83.
   - Bracket hook: bottom fin ≥ 1.5 mm, rear edge Y 292 ± 0.5.
   - Thermal requirement (D-18 as amended): R_SA ≤ 0.29 °C/W at ≥ 13 CFM delivered.
2. **Front face:** machined, Y 244.3 ± 1 (the sink floats and is locked after the comb is torqued), over Z 35.6–83. Flatness ≤ 0.05, Ra ≤ 1.6.
3. **Bond holes:** 4 × M4 **blind, cut thread** (not thread-forming), at X −45 / −75 / −105 / −135, Z in the dry band 72–82. Engagement ≥ 7 mm (1.75 d), with no break-through.
   - Fasteners: stainless ISO 4762 M4 with DIN 6797 toothed lock washers (§28.3).
   - Tapped 6063 with a stainless screw: IEC 60335-1 §28.1 restricts the *screw* material, not the threaded part. **The certifier is to confirm this.**
   - Wire-thread inserts are held in reserve if threads strip in the Table 14 cycling or E1b drifts after the §15.3 humidity test.
4. **Finish:** chem film (MIL-DTL-5541 Class 3, conductive) on the sink and the bar, with no masking.
5. **Thermal interface:** compound only below Z 70. The bond lands at Z 72–82 are a dry band and clamp bare-on-bare.
6. **Clearance:** no part of the sink, its fasteners or its brackets comes within 8 mm of native-21 HOT copper (through air, 3D).

## Spreader bar (6061 / 6082, machined)

1. **Stack face:** the tile face sits at Y 234.47. That is +0.3 mm from R30, for the TO-247 body's 5.0 mm nominal (Infineon drawing Z8B00003327: 4.70–5.30 mm); the comb preload takes the tolerance.
2. **Bond holes:** 4 × Ø4.5 clearance holes matching the S8 sink holes, with a DIN 6797 A4.3 toothed washer under each M4 head. Chem film, no masks (R32).
3. **Comb screws:** 3 × M3 into the bar (clamp only, not a bond path). Comb acceptance is 45–102 N per TO-247, capped at Infineon's published maximum clip force if that is lower.
4. **PE ear at the X 149 end:** Ø4.3 through, chem film.
   - Stack: M4 × 16 A2, a DIN 6797 A4.3 washer each side, the ring lug, M4 nyloc, 1.2 N·m.
   - Strap: 14 AWG G/Y 105 °C to the base stud.
5. **Grease boundary:** Z ≤ 70 on the rear face. Show it on the drawing.

## BR1 interface

- **Pad:** Bergquist GAP PAD HC 3.0, **0.040" (1.0 mm)**, cut 30.3 × 17.5 mm. It sits between BR1 and its tile, compressed to about 0.67 mm (0.47–0.87 over BR1's 4.4–4.8 mm body).
- **Strip:** the FR-4 strip is relieved 0.5 mm over BR1, so it loads the pad through the body and never drives BR1 onto the tile.

## Acceptance

- **Ground bond (E1b):** from a bare sink fin to the inlet PE pin, ≤ 0.1 Ω at 25 A for 120 s (IEC 60335-1 §27.5). Run it on every unit as part of the production ground-bond test.
- **Visual:** the toothed washers are seated. Before soldering, the MOSFETs and BR1 go in the seat-before-solder fixture (coplanar within 0.05 mm, square within 0.3°, with a 0.665 mm step at BR1).
