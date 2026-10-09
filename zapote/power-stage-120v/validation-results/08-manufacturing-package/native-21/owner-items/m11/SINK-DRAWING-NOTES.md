# Heatsink and spreader bar: drawing notes (native-21, enclosure R31)

Status: notes for the sink and bar drawings, 2026-10-09.
- **Geometry:** the enclosure (R31, `output/temper-manufacturing-r31`) owns it. These notes set what the power stage requires of it.
- **World frame:** R31: x − 141, 236 − y, 26 + z from the board.
- **Decisions:** DECISIONS.md 2026-10-08 (M11), 2026-10-09 (sink mounting, PE bond, R31 / BR1).

## Sink

1. **Part:** a catalogue aluminium extrusion, cut to length.
   - The only machining is the four bond holes below, plus the bracket hook seats if the bracket design needs them.
   - No fin removal, no bosses.
2. **Bond holes:** 4 × M3 **cut thread** (not thread-forming; IEC 60335-1 §28.2), along Y through the base wall from its front face (world Y 244.3).
   - Positions: X −45 / −75 / −105 / −135. Z is the centre of the fin channel nearest Z 80 for the selected profile (Z 80.0 for the modelled 1.5 / 3.0 mm fin pitch with the top fin flush at Z 83).
   - Minimum base wall at each hole: 4.0 mm, giving ≥ 4.0 mm engagement (1.33 d).
   - Where the tap breaks into the channel: deburr, then clean the channel free of chips (air plus solvent) before anodize or chem film.
3. **Bond lands:** mask each hole with a Ø8 mm land on the front face, bare metal, no anodize. Also mask any surface the enclosure's hook brackets bear on, if those are to be conductive; they are not counted as a bond.
4. **Thermal interface:** the bar-to-sink joint gets thermal compound only below Z 70. The four bond lands are a dry band and clamp bare-on-bare to the bar's masked rear lands.
5. **Clearance:** no part of the sink, its fasteners or its brackets comes within 8 mm of native-21 HOT copper (through air, 3D). R31 measures ≥ 20.1 mm.

## Spreader bar (6061 / 6082, machined)

1. **Stack face:** the tile face sits at Y 234.47. That is +0.3 mm from R30, for the TO-247 body's 5.0 mm nominal (4.83–5.21 mm); the comb preload takes the tolerance.
2. **Bond holes:** 4 × Ø3.4 clearance holes matching the sink holes.
   - Front face: Ø8 × 0.6 spot face, so each DIN 6797 A3.2 toothed washer sits flush on bare metal.
   - Rear face: Ø8 masked land.
   - Fasteners: M3 × 12 A2 socket head (ISO 4762), 1.0 N·m.
3. **PE ear at the X 149 end:** Ø4.3 through.
   - Mask Ø10 on both faces.
   - Stack: M4 × 16 A2, a DIN 6797 A4.3 washer each side, the ring lug, M4 nyloc, 1.2 N·m.
   - Strap: 14 AWG G/Y 105 °C to the base stud.
4. **Grease boundary:** Z ≤ 70 on the rear face. Show it on the drawing.

## BR1 interface

- **Pad:** Bergquist GAP PAD HC 3.0, **0.040" (1.0 mm)**, cut 30.3 × 17.5 mm. It sits between BR1 and its tile, compressed to about 0.67 mm (0.47–0.87 over BR1's 4.4–4.8 mm body).
- **Strip:** the FR-4 strip is relieved 0.5 mm over BR1, so it loads the pad through the body and never drives BR1 onto the tile.

## Acceptance

- **Ground bond (E1b):** from a bare sink fin to the inlet PE pin, ≤ 0.1 Ω at 25 A for 120 s (IEC 60335-1 §27.5). Run it on every unit as part of the production ground-bond test.
- **Visual:** the masked lands are bare. The toothed washers are seated flush. The chips are cleared from the channel at each bond hole.
