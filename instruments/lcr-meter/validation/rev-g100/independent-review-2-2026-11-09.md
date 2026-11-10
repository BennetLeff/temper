# Rev G100 independent layout review (frozen export `build/rev-g100-review2/`)

Reviewer scope: only the files in this folder. Every claim below was re-derived with a script in `work/`;
the script and its output file are named per finding. Board coordinates are KiCad mm (outline x 50–150, y 45–145).

## Verdict: ORDERABLE (no blockers)

No defect was found that would make the fabricated or assembled board wrong: the Gerber / drill / IPC-356 set
is the board file, the netlist matches `design.json` pin for pin, polarities and IC pinouts are right, the
JLC rule set passes with zero violations, and the analog core is Rev G's copper.

Two MAJOR findings are places where the layout does not meet the intent's own stated supply-copper
requirement (1.17 A at ≤ 10 °C) on the fault path. Both are small re-routes; I recommend fixing them and
re-exporting before the order, since the re-export is cheap and the intent calls them a must. Neither affects
normal operation (the current involved only flows in a downstream short, at the TPS2553 limit).

## Findings

### BLOCKER
None.

### MAJOR

**M1. USB_VBUS entry copper is 0.2 mm wide for 4.62 mm on the J1 A4/B9 pair.**
Location: F.Cu, from J1 pad A4/B9 (57.67, 129.6) through (58.29, 129.6) → (58.49, 129.12) → (58.49, 127.45) →
(57.96, 126.92) → via (57.2, 126.2). Evidence: `work/net_checks.py` → `work/net_checks.out` ("USB_VBUS J1 -> U16 IN
path"), `work/misc2.out` ("0.2 mm copper length: pad A4 4.62 mm, pad A9 0.91 mm").
The intent treats each VBUS pin pair as its own 1.17 A source. 0.2 mm of 1 oz outer copper carries
≈ 0.74 A at 10 °C by the IPC-2221 external fit (I = 0.048·ΔT^0.44·A^0.725); at 1.17 A the rise is ≈ 28 °C.
The A9/B4 pair is fine (0.9 mm of 0.2 mm, then 0.4 mm). Fix: widen the A4-side run to 0.4 mm from
(58.49, 129.12) northwards (there is clear F.Cu east of the pad row), or tie A4/B9 to the 0.4 mm A9/B4 copper
on F.Cu so both pairs share the wide path.

**M2. The 5V trunk to the switcher runs 13 mm on In2.Cu at 0.9 mm, 0.5 oz, in series.**
Location: In2.Cu (51.2, 136.8) → (51.2, 143.3) → (51.9, 144.0) → (57.4, 144.0); fed by vias (51.2, 136.8) /
(51.2, 137.6) from the B.Cu 0.6 mm run down x = 51.2, and leaving by vias (56.6, 144.0) / (57.4, 144.0) onto the
B.Cu 0.6 / 1.0 mm run along the south edge to L1. Evidence: `work/net_checks.out` ("5V tracks", "supply copper"
table: `5V In2.Cu min w=0.90 … I(10C)=0.67 A`), `work/misc3.out` (no parallel F.Cu / B.Cu / zone 5V copper in
x < 58, y > 136, so the inner run is in series).
Cross-section 0.9 mm × 17.5 µm = 24 mil²: ≈ 0.67 A at 10 °C by the inner IPC-2221 fit, ≈ 0.8 A by the IPC-2152
in-air chart, both below the 1.17 A the intent requires. The adjacent In1 GND plane helps, but not to 10 °C at
1.17 A. Fix: widen the In2 run to ≥ 1.8 mm (the corridor is free), or carry 5V on B.Cu around the USB-C
connector instead of dropping to In2.

### MINOR

**m1. CPL rotation offsets are inconsistent within a package.** `work/netlist_check.py` → `work/netlist_check.out`
("CPL vs board": 26 rows differ from the board rotation), `work/misc2.out` ("CPL rotation offsets by footprint").
SOT-23-5: U3 / U15 (AP2112K) +270°, U5 (OPA197) +180°. SOT-23-6: U16 / U17 (TI) +180°, D1 (SRV05-4) +270°.
The pattern (TI parts 180°, others 270°) is consistent with per-LCSC-part orientation data rather than a mistake,
but one of each pair is wrong if it is a package-level correction. Confirm in JLC's placement preview for U5,
D1, U16, U17, U3, U15 before paying; a rotated regulator is a dead board.

**m2. B.Cu GND pour inside the M3 standoff footprint at H3 (54, 141) and H4 (146, 141).** `work/geometry_checks.py`
→ `work/geometry_checks.out`: the B.Cu GND fill comes to 1.8 mm from both hole centres (0.2 mm from the 3.2 mm
hole), and a GND via sits 3.3 mm from H4 at (143.02, 138.98). H1 / H2 (y = 54) are clear. The intent asks for
≥ 3.5 mm or a flag: flagged. A GND standoff on a GND pour is benign; if the standoffs are not to be GND, add a
B.Cu keep-out of r 3.5 mm at H3 / H4.

**m3. The board file's own design rules do not describe the board.** `work/drc/drc.json` (kicad-cli DRC on the
shipped board, severity-all): 549 errors against the file's constraints (min track 0.2, via 0.5 / annular 0.1,
hole clearance 0.25, edge 0.5, default netclass clearance 0.2): 340 clearance, 70 track width (0.15 mm GND
around U1), 41 via diameter / 41 annular (0.45 mm vias), 47 hole clearance, 10 copper-edge (0.40–0.45 mm).
None of these breaks JLC: with the JLC profile applied (`work/jlc_drc.py`, `work/jlc/drc-jlc.json`, custom rules
in `work/jlc/temper-lcr-jlc.kicad_dru`) the DRC is clean. Fix: put the JLC limits (and the 0.4 mm edge promise)
into the project so KiCad's DRC means something for the next editor.

**m4. Craft rules in the re-routed south.** `work/craft_checks.py` → `work/craft_checks.out`.
No T-junctions (the 7 candidates are sub-µm endpoint rounding, see "T-junction segment detail"). 149 bends in
the south are not 0 / 45 / 90° (5°–85°, mostly short alignment segments; Rev G's copper has 62 of the same);
four pad entries are off-axis and not declared in `routing.json` `craft_exceptions`: C110.1 GND (91.775, 136.675),
C3.1 3V3 (72.657, 127.93), SW1.2 GND (89.85, 138.0), SW2.1 RUN (84.375, 141.9, 119° into the pad); 32 track
segments are shorter than 0.05 mm (`work/misc2.out`). Cosmetic; the 45° rule as written is not met.

**m5. Reference designators.** `work/geometry_checks_refs.out`. No F.Fab reference on J3, J7, J8, J9, K1–K4, D4,
U14 (intent: always on F.Fab). 72 parts have no visible silk reference, including U13, U16, SW2 and J1 where
there is room. Silk references overlap at C11 / U1 (67.5, 136.5), R62 / C45 (82–84, 85.2), U6 / R104 (82–83.7,
78.2); visually also R74 / Q2 and C12 / C9 (`renders/pcb-front.png`).

**m6. R13 (QSPI CLK series resistor) is mid-line, not at the U1 end.** `work/net_checks.out` ("QSPI"): QSPI_CLK
U1 → R13 7.07 mm, QSPI_CLK_FLASH R13 → U2 7.70 mm; R13 at (73.5, 143.5), U1 (74, 133.5), U2 (62.1, 141.45).
Electrically short at the RP2040's QSPI rate, so a note rather than a fault; move R13 next to U1 pad 52 if the
area is touched again. The other QSPI lines are 16–31 mm with 2–3 vias each (CS 30.9 mm on three layers).

**m7. C15 is 4.1 mm of 0.4 mm track from U16 IN, with C113 in between.** `work/net_checks.out` ("post-audit
items"). Better than Rev G (7 mm) and acceptable for a 100 nF, but not "beside". TP20 is at (61.2, 137), away
from U16, as intended.

### NOTE

**n1. 14 teardrop zones have no fill** (TIA_OUT F.Cu (110.9, 81.4), RLY_SET_REF F.Cu (147.9, 85.6), I2S_DOUT /
I2S_BCLK B.Cu (59.6, 107.4) / (59.1, 104.4), −12V B.Cu at D29's via (136.2, 97.6) and (89.1, 84.6 / 86.8),
TIA_OUT / JACK_LC / JACK_HC In2, …): `work/misc2.out` ("zones: fill sanity"). The Gerbers carry nothing for them;
connectivity is by the tracks (0 unconnected items). Fill or delete.

**n2. 12V has two 0.2 mm, 0.5 oz In2 via-to-via jumpers** (84.4, 90.3–92.5) and (108.2, 89.9–92.5), 2.2 and
2.6 mm long, in Rev G copper: `work/misc_checks.out`. ≈ 0.23 A at 10 °C by the inner fit against the intent's
0.5 A if they are in series on the +12 V feed; short enough that the end vias sink the heat. Inherited.

**n3. 3V3 copper in the Rev G region changed.** `work/analog_compare.py 107` → `work/analog_compare.out`: the only
non-GND, non-D29 copper differences north of y 107 are the 3V3 run (58.95, 102) → (64.8, 103.7) and a new 16.3 mm
3V3 feed up x = 62.1 to R73. A supply net, so within the intent's "signal nets unchanged", but it is not in the
intent's exception list. Everything else north of y 107 (678 segments, 145 vias, all placements) is identical.

**n4. D29 adds one new via, not two.** The −12V via (136.2, 97.6) is new; the GND return goes through the via at
(137.9, 103.6), which exists on Rev G as well (`work/analog_compare.out`, `work/misc_checks.out`). D29 itself is
right: pad 1 (cathode, silk bar side of `LCR.pretty/D_SMA`) on GND, pad 2 on −12V, 5 mm from C100.

**n5. Stale metadata.** `design.json` `board.ref_text` / `board.silk` still hold Rev G positions for the moved parts
(e.g. HB / FLT labels, U1, SW1); the board's silk is in the right places (`work/misc_checks.out`, "board silk
texts"). The JLC BOM comment for K1 / K3 / K4 reads "TQ2SA-L2-5V 5k" and SW2 reads "BOOTSEL" (same LCSC part
in each case, cosmetic).

**n6. Copper-to-edge is exactly at the 0.4 mm promise** at D4's pads (54 / 56, 45.95) and the RUN track on In2
along y = 144.525 (`work/geometry_checks.out`). Meets the fab note; no margin.

## Checked and found fine

- **Export set = board file.** `work/compare_exports.py` → `work/compare_exports.out`: after a fresh kicad-cli
  export into `work/reexport/`, every Gerber layer (copper ×4, paste, silk ×2, mask ×2, Dwgs.User, Edge.Cuts) is
  identical primitive-for-primitive (aperture-resolved, origin-normalised), PTH 461 / NPTH 6 holes identical
  (J1's four 0.6 × 1.4 / 1.7 slots are written as routed slots in the shipped drill), IPC-D-356 1217 records
  identical. Note: `--board-plot-params` would add drill marks (stored `drillshape 1`); the shipped set correctly
  has none.
- **JLC rules.** `work/jlc/drc-jlc.json`: 0 violations with the `jlcpcb-4layer-1oz.json` limits plus the PTH /
  NPTH hole-to-copper and pad rules as custom rules; 0 unconnected; silk text all ≥ 1.0 mm / 0.15 mm; no
  silk-over-pad, no courtyard overlaps. Outline 100.05 × 100.05 with 4 × M3 at Rev F positions.
- **Netlist.** `work/netlist_check.out`: 253 design.json parts, 0 pin/net mismatches, 0 value / footprint
  mismatches, no single-pad nets; NC pads are the expected ones (U1 GPIO0/1/12/16–21/24, relay NC1/NC2, LDO
  NC/DNC, U13 BSW/NC, U14 unused, U16 FAULT, U17 FLAG3, J1 SBU). `work/design_diff.out`: G100 vs Rev G differs
  only by J5 removed, D29 added, the listed value changes (R101 0.33 Ω, R132/R133 270 Ω, C85 C0G, six 2.2 µF)
  and the listed placements.
- **Pin 1 / polarity.** `work/misc_checks.out` against the datasheets: TPS2553 (IN 1, GND 2, EN 3 tied to IN,
  ILIM 5, OUT 6), AP2112K ×2, TPS7A49 / TPS7A30 (EN to IN is allowed, §Pin Functions), LM3880, TPS65131 all 24
  pins, OPA2810 ×2, OPA197, SRV05-4, BAT54S, BAV99 (anti-parallel on DUT_LO), TLP172AM ×4 (1 anode, 3 cathode,
  4/6 drain; series LED string ISO_S1 → U19 → U18 → Q7, ISO_S2 → U20 → U21 → Q7), SS14 ×3 (cathode = pad 1 =
  silk bar), H4V5HD3B / H3V3LD5B are bidirectional (no polarity), LEDs cathode to GND, C117 pad 1 = 5V, Y1.
- **CPL / BOM.** All 248 CPL positions match the board (origin 50,45, Y up); every CPL row has a BOM row with an
  LCSC part and vice versa; BNCs J3/J7/J8/J9 and DNP J4 are absent from both, as intended.
- **Post-audit items.** TVS D21–D24 each have two GND vias on the pad (`work/net_checks.out`); U16 OUT leaves
  through two vias (54.46, 117.75) / (55.06, 118.35); U11 / U12 pin 4 are bridged to the EP on F.Cu (0.25 mm
  tracks plus fill, `work/misc_checks.out`); no USB_VBUS copper on any layer inside J1's shell footprint; TP22 GND
  is 3.1 mm from J4; TP8 / TP9 are 5–7 mm from SW1 / SW2; SW1 / SW2 and D19 / D20 are top-side with nothing tall
  nearby.
- **Switcher distance.** U13 / L1 / L2 / D2 / D3 are 50–94 mm from U7, U14, U6, U5, C104 and the range resistors.
- **USB.** D+ 44.8 mm, D− 51.7 mm, skew 6.9 mm ≈ 41 ps (< 100 ps); R3 / R4 at the U1 end; J1 → U16 copper ≈ 15 mm.
- **Supply copper otherwise.** RAW_P / RAW_N / ±12V / 3V3 / VRLY are ≥ 0.2 mm on 1 oz outer layers (≈ 0.74 A at
  10 °C ≥ their 0.5 / 0.6 A), the 3V3 In2 0.27 mm run only feeds U17 and its dividers, 3V3 leaves U3 at 0.2 mm
  for 2.2 mm then 0.3 mm.
- **Planes.** In1 is one GND polygon; OPA2810 / TIA keep-outs are present on In1 / In2 / B.Cu as in `routing.json`.

## Work folder
`work/dump_board.py` (pcbnew dump → `board.json`, `revg.json`), `compare_exports.py`, `netlist_check.py`,
`design_diff.py`, `jlc_drc.py` (+ `jlc/`), `geometry_checks.py`, `analog_compare.py`, `craft_checks.py`,
`net_checks.py`, `drc/` (board-rule DRC), `reexport/`, and the `*.out` files quoted above.

---

## Dispositions (designer, 2026-11-09)

| Finding | Disposition |
|---|---|
| M1 (J1 A4/B9 exit 0.2 mm) | **Accepted**, as G-PE-8 in `../datasheet-audit-rev-g100/FINDINGS.md`. The 0.52 mm channel between J1's pads and CC1 holds only a 0.2 mm track, and B.Cu is closed by the VBUS feed at y 126.2. Reaching 1.17 A there takes two faults together: a whole VBUS pad pair (two contacts) not mating, since the plug ties all four VBUS contacts, and a downstream short at U16's limit. The normal 0.46 A is within the 0.74 A the reviewer gives the track. The intent's "each pair is its own source case" overstated the requirement |
| M2 (In2 corner 0.9 mm) | **Fixed:** In2 1.6 mm, all the room between the 0.4 mm edge rule and H3's hole. Two vias at each end, moved to keep B.Cu ≥ 3.5 mm from H3 |
| m1 (CPL rotations) | Per-LCSC offsets from `sources/placement-rev-c.json`. JLC's placement preview, already a listed step before ordering, checks them |
| m2 (B.Cu GND pour 1.8 mm from H3 / H4) | Accepted, as on Rev F / G: insulating standoffs (`docs/rev-g100-plan.md` §4). H1 / H2 sit beside the analog band, where the pour stays |
| m3 (549 DRC errors on the board's own rules) | An export error: the folder left out `temper-lcr.kicad_pro`, which holds the board's rules. With it the gate DRC reports 0 |
| m4 (craft) | The bend style is inherited from Rev G. The four entries pass the craft pass's own land-entry rule (pre-DRC 0) |
| m5 (references) | `cad/assembly_preview.py` moves every reference onto F.Fab for `assembly-top.pdf`, so all 253 are on the assembly drawing. KiCad's silk-overlap DRC is 0 |
| m6, m7 | Accepted (R13 lumped at QSPI rates; C15 4.1 mm, against 29 mm before) |
