# Rev G100 independent layout review

Reviewer: independent (Fable subagent), 2026-11-09. Scope: the frozen export in this folder only
(`cad/`, `gerbers/`, BOM/CPL, `rev-g/`, `intent/README.md`, datasheets). Nothing outside the folder
was read. Every claim below was re-derived with the scripts in `work/`; the script and its output
file are named with each finding. Board coordinates are KiCad millimetres (outline x 50–150,
y 45–145; y grows southward, BNC row is north).

## Verdict

**NOT ORDERABLE from this export.** The CAD is close (DRC/ERC/parity clean, netlist identical to
Rev G minus J5, the analog core and jack band are byte-identical copper), but:

1. the Gerber/drill set in `gerbers/` was exported from an earlier board state than
   `cad/temper-lcr.kicad_pcb` — it lacks one USB_VBUS via and its drill hit, carries a narrower
   (0.2 mm) VBUS run on B.Cu than the board (0.5 mm), and has an In2 track at 0.35 mm from the
   edge where the board (and the fab note) say 0.4 mm. Regenerate and re-diff before ordering.
2. the 5 V trunk on B.Cu wraps around mounting hole H3 at 2.5–2.95 mm from the hole centre,
   inside the standoff footprint the intent reserves (3.5 mm).
3. one of the two USB-C VBUS pad pairs (A4/B9) reaches U16 through a 0.2 mm track, which carries
   ~0.74 A at 10 °C, not the 1.17 A the intent requires for each pair.

Fix those three (all are a few minutes of layout), re-export, and re-run `work/gerbercmp.py` and
`work/drillcmp.py`; the remaining findings are MINOR/NOTE and can be taken or waived.

## Findings

### BLOCKER

**B1. Frozen Gerbers and drill files do not match the board file.**
- Location: via at (61.225, 135.9) [USB_VBUS]; B.Cu run (57.2, 126.2)–(61.225, 126.2)–(61.225, 135.9);
  In2 track at y ≈ 144.55 (x 58.3–88.3, RUN); In2 5 V trunk x = 99 (y 127–144); fab-note text.
- Evidence: `work/gerbercmp.py` (semantic Gerber compare, frozen vs. re-export of `cad/` with the
  same origin/extensions) → `work/gerbercmp2.out`; `work/drillcmp.py` → `work/drillcmp.out`.
  - F_Cu / In1 / In2 / B_Cu: one 0.6 mm flash at Gerber (11.225, 9.1) = board (61.225, 135.9) is
    in the re-export and absent from the frozen files. PTH drill: frozen 449 holes, board 450;
    the missing hit is that via. The fab note on Dwgs.User says 456 holes; the frozen drill set has 455.
  - B_Cu: frozen has a 0.2 mm draw (7.2, 18.8)–(19.0, 18.8) [board y = 126.2]; the board has that
    run at 0.5 mm plus the 0.5 mm vertical to the new via.
  - In2_Cu: frozen has a 0.2 mm track whose lower edge sits 0.35 mm from the south edge
    (Gerber y 0.45, w 0.2); the board has it at 0.15 mm wide, y 144.525 → 0.40 mm. Frozen In2
    trunk at x = 99 is 0.6 mm wide; the board has 0.9 mm. GND pour outlines differ accordingly.
  - User_Drawings (fab notes): 16 vs 28 stroke differences in the drill-summary lines (the counts
    were edited after the Gerbers were cut).
  - Frozen IPC-D-356 also lacks the via record (`gerbers-check2/temper-lcr.d356` vs frozen: 1 record).
  - Mask, paste, silk, edge cuts: identical.
- Why it matters: the files that would be uploaded describe a different board than the one that
  passed DRC. The missing via breaks nothing electrically in the frozen set (that VBUS path also
  exists at 0.2 mm), but the frozen set violates the 0.4 mm copper-to-edge promise written on its
  own fab drawing and carries a thinner VBUS run than the board was reviewed with.
- Fix: re-export Gerbers, drills and D356 from `cad/temper-lcr.kicad_pcb`, then re-run
  `work/gerbercmp.py` on every layer and `work/drillcmp.py`; both must report IDENTICAL / equal hole
  sets. Treat any export whose diff is non-empty as not orderable.

### MAJOR

**M1. 5 V trunk on B.Cu inside the H3 standoff footprint.**
- Location: H3 at (54, 141). B.Cu 5 V tracks x = 51.2 (y 117.1–143.55, w 0.6) at 2.5 mm from the
  hole centre; y = 144.25 (x 51.9–92, w 0.6) at 2.95 mm; chamfer (51.2,143.55)–(51.9,144.25) at 3.48 mm.
- Evidence: `work/geom_checks.py` → `work/geom_checks.out` section "M3 mounting holes".
  H1, H2: nothing within 3.5 mm on either outer layer. H4: only GND (pour 1.8 mm, via 3.3 mm).
- Why it matters: the intent asks for B.Cu copper ≥ 3.5 mm from M3 hole centres "for the standoff,
  or flag it". A 5–6 mm hex standoff or washer sits on this 5 V track through soldermask only; mask
  wear or a burr shorts 5 V to the chassis/GND standoff. It is the trunk that feeds the whole board.
- Fix: route the west-edge trunk at x ≥ 57.5 past H3 (or jog it onto F.Cu / In2 for the 8 mm around
  H3), keeping all B.Cu copper outside r = 3.5 mm. Alternatively keep an insulating washer on H3
  and record the waiver, but this is the only hole with a non-GND net inside the standoff.

**M2. USB-C VBUS pad A4/B9 reaches U16 through a 0.2 mm track (1.17 A case fails).**
- Location: F.Cu (58.29, 129.6) → (58.49, 129.12) → (58.49, 127.45) → (57.96, 126.92) → (57.2, 126.92),
  w 0.2, then via (57.2, 126.2) onto the 0.5 mm B.Cu run.
- Evidence: `work/power_paths.py` → `work/power_paths.out`: widest-path bottleneck J1.A4/B9 → U16.1/3
  is 0.20 mm (1 oz); J1.B4/A9 → U16 is 0.40 mm. IPC-2221 external at 10 °C: 0.74 A for 0.2 mm.
  At 1.17 A a 0.2 mm 1 oz track reaches ≈ 28 °C rise (IPC-2221), more by IPC-2152.
- Why it matters: the intent states each VBUS pin pair is its own source case (a plug may contact
  one only) and the copper must take the TPS2553 limit maximum, 1.17 A, at ≤ 10 °C.
- Fix: widen the A4/B9 escape to ≥ 0.45 mm (there is room between the J1 pad row and the B.Cu
  via), or tie the two VBUS pads together on F.Cu with a ≥ 0.5 mm strap so either pad feeds the
  0.5 mm run. Note the related NOTE N4 on the 0.4 mm bottlenecks.

**M3. 12 V distribution passes through 0.2 mm, 0.5 oz In2 jogs (0.5 A case fails) — inherited Rev G copper.**
- Location: In2.Cu (84.4, 90.3)–(84.4, 92.5) and (108.2, 89.9)–(108.2, 92.5), w 0.2, in the analog core.
- Evidence: `work/power_raw.out`: every path U11.1 → U6.8 / U7.8 / U5.5 has its bottleneck on one
  of these two segments, effective 0.10 mm (1 oz-equivalent). IPC-2221 internal at 10 °C: 0.23 A
  (0.45 A even with the external coefficient). The intent asks for 0.5 A on 12 V.
- Why it matters: at the stated 0.5 A fault current these 2.2–2.6 mm inner-layer jogs run far past
  10 °C. This copper is in the region the intent says must stay Rev G's, so it is a conflict between
  two requirements rather than a G100 regression; it is listed so the owner decides.
- Fix (when the analog core is next touched): move the two jogs to F.Cu/B.Cu at 0.3 mm, or widen
  them to ≥ 0.5 mm on In2. Or waive with the real 12 V load written down (two OPA2810 and U5:
  a few tens of mA; the 0.5 A figure is a limit, not a load).

### MINOR

**m1. Re-placed 3V3 feed from the LDO is 0.2 mm wide (0.6 A case marginal).**
- Location: F.Cu from U3.5 (57.99, 120.95): (58.7, 120.95)–(58.85, 120.7)–(60.0, 120.7), and the run
  (64.6, 122.425)–(66.2, 122.425)–(66.2, 125.95) toward U1; 91.6 mm of 0.2 mm F.Cu on 3V3 in total.
- Evidence: `work/power_paths.out` (bottleneck 0.20 mm to U1, U2.8, U14.6, TP8). IPC-2221 external
  at 0.6 A: ≈ 6 °C rise (passes 10 °C); the IPC-2152 universal curve gives ≈ 11 °C.
- Fix: 0.3 mm from U3.5 to the first branch (there is space; the 3V3 run past C17 is already 0.3).

**m2. Craft rules not met in the hand-routed south, and not covered by `routing.json` craft_exceptions.**
- Evidence: `work/craft_checks.py` → `work/craft_checks.out` (south-region list reproduced in the
  session log; totals for the whole board: 147 off-45° segments, 76 three-way track nodes without a
  pad or via, 2 T-junctions, 74 off-centre land entries, 17 off-axis entries, 9 stubs; Rev G:
  146 / 76 / 2 / 73 / 17 / 9). Of the 35 recorded exceptions, 6 are corner90 and 29 pad_entry; none
  cover the items below.
  - Off-45° segments south of y 107 (≈ 95): mostly ≤ 1 mm jogs, e.g. 3V3 (58.7, 120.95)–(58.85, 120.7)
    at 59°, GND (119.6, 134.125)–(120.2, 133.0) w 1.0 at 62°, USB_DP (79.597, 139.065)–(78.525, 140.325).
  - Three-way branch nodes without a via/pad (≈ 45 south), e.g. USB_VBUS (61.225, 134.525),
    (57.75, 116.85); 3V3 (62.1, 120.4), (62.225, 103.525); 5V (98.7, 126.5), (139.9, 143.975).
  - T-junction / micro-segment: I2S_DOUT B.Cu (79.386, 134.9655)–(79.386, 134.989), a 23 µm piece
    with two tracks meeting its interior (DRC accepts it; it is a routing artefact).
  - True dangling stubs (end touches no copper): 3V3 (66.95→67.22, 127.35); USB_VBUS
    (59.2→60.075, 115.05), 0.25 mm beyond the C113.1 land; JACK_HC (69.8,135.45)→(69.6,135.65);
    I2S_DOUT B.Cu (79.386,134.9655) and (79.7093,135.3123). Verified with shapely against pads,
    vias and teardrop fills (session log).
  - Off-centre land entries south, e.g. U3.5 enters 0.61 mm off centre along the pad; U11.5/8 and
    U12.5/8 enter 0.62–0.65 mm off centre; SW2.1 entered at the pad end; J1.A4/B9 entry 0.34 mm off.
- Why it matters: the intent lists these as rules; the exception list is supposed to be the complete
  record of deviations. Electrically none of these is a fault (DRC clean).
- Fix: either clean the listed items (delete the five stubs and the 23 µm segment; straighten the
  short jogs) or add them to `craft_exceptions` with a reason, so the record is honest.

**m3. QSPI CLK series resistor R13 is at the midpoint, not the U1 end.**
- Location: R13 (73.5, 143.5); U1 CLK pad 52 at (75.0, 136.94) is 6.7 mm away, U2 CLK pad 6 at
  (65.69, 142.09) is 7.9 mm away. QSPI_CLK 7.07 mm, QSPI_CLK_FLASH 7.70 mm (`work/signals.out`).
- Why it matters: a source terminator belongs within a few mm of the driver; here the U1-side stub
  is as long as the flash side, so it does little. QSPI1/QSPI2 are 27–25 mm with 2 vias each on
  In2, QSPI0 17 mm, QSPI3 16 mm — longer than "short" for a 14 mm chip-to-chip distance.
- Fix: put R13 within ~2 mm of U1.52 (R7/R8 can shift east), and bring QSPI1/2 back to F.Cu.

**m4. Crystal and XIN/XOUT routing are loose — inherited (Y1, C12, C13, R10, U1 unchanged from Rev G).**
- Location: Y1 (75, 123) is 7 mm from U1 XIN/XOUT pads (74.6/74.2, 130.06). XOUT runs 8.3 mm on In2
  with 2 vias; XIN is 11.1 mm and C12 (68.5, 124.5) sits 6 mm from the crystal; ISO_DRIVE (In2)
  crosses under the crystal footprint.
- Evidence: `work/signals.out` "Crystal".
- Fix (next time the RP2040 corner is touched): crystal and both load caps within 3 mm of pins
  20/21, same layer, GND under; no foreign signal under the crystal.

**m5. RP2040 1V1 decoupling is far from the pins — inherited.**
- Location: C8 1 µF (69.2, 139.5) is 4.6 mm from VREG_VOUT pin 45; C9 100 nF (69, 127.5) is 5.8 mm
  from DVDD pin 23 and 6.1 mm from pin 50. 3V3 pins have caps at 2.6–3.8 mm (acceptable).
- Evidence: `work/signals.out` "RP2040 power pins".
- Fix: a 100 nF at each DVDD pin (23, 50) within 1.5 mm; keep C8 at pin 45.

**m6. Footprint silk outlines are 0.12 mm wide; JLC's stated minimum is 0.15 mm.**
- Evidence: `work/geom_checks.out` SILKLINE lines (every chip, SOT, SOD, SOIC outline); frozen
  `F_Silkscreen.gto` uses a 0.12 mm aperture for 9 236 strokes. Text is 1.0 mm / 0.15 mm (OK).
- Fix: bump footprint silk lines to 0.15 mm (library-wide), or accept that JLC will thicken them.

**m7. Ten footprints have no reference on F.Fab; 44 have none on silk.**
- F.Fab missing (intent: "always on the assembly drawing"): J3, J7, J8, J9, K1, K2, K3, K4, D4, U14
  (`work/geom_checks.out` NOFABREF). Silk missing (intent: "where it fits"): 44 refs, including
  J1, U13, SW2, R13, C18, C110, R121 (NOSILKREF list in the same file).
- Fix: add `${REFERENCE}` F.Fab text to the BNC, TQ2SA, TAC5112 and side-LED footprints; the silk
  list is informational unless the owner wants SW2 and J1 labelled (SW1 has "SW1"; SW2 has nothing).

### NOTE

**N1. Unchanged regions: copper north of y ≈ 107 is identical to Rev G except one 3V3 jog.**
- `work/cmp_copper.py` → `work/cmp_copper.out`: north of y 107, 0 via differences, 0 zone outline
  differences other than three 3V3 teardrops, 8 track differences, all one feature: the 3V3 track
  at y 103.5–103.7 (x 58.95–64.8, near U14) was re-drawn to pass through the existing via centre at
  (63.5, 103.525) and to accept the new 3V3 drop (62.1, 104.1)→(62.1, 120.4). Also the 5 V B.Cu trunk
  (54.462, 99.6→116.4) and JACK_HC/JACK_LC In2 verticals now end at new y's (same x, same width).
  Filled pours differ only in the six teardrops around moved parts. The analog core and jack
  protection band are Rev G's copper.

**N2. Parts moved beyond the intent's list:** TP6 (−3.5 y), TP7 (+3.1, −8.2), TP20/TP21 (−3.0, −26),
TP9 (+2.6, −2.6), H3/H4/FID3 (−10, with the shorter board). All test pads / holes; the four
mounting holes are at the specified (54,54) (146,54) (54,141) (146,141). `work/cmp_parts.out`.

**N3. Switcher-to-victim distance shrank by ~10 mm.** U13→U7 59.6 mm (Rev G 68.9), L1→U7 63.5 (73.2),
D3→U7 54.6 (63.6), U13→U14 82.1 (87.0), U13→U6 78.0 (85.8) (`cmp` output in session log). Still
> 50 mm with the In1 plane between; acceptable, but it is the one knob that moved the wrong way.

**N4. 0.4 mm bottlenecks on the 1.17 A paths pass IPC-2221, miss the IPC-2152 universal curve.**
B4/A9 → U16 (0.4 mm F.Cu, (61.1,134.4)–(58.4,134.4) and (61.225,134.525–137.0)); 5 V trunk B.Cu
(54.462, 116.4–117.75) 1.35 mm long; 5 V fan-in to U13 pins 5/6 (138.75–138.775, 137–139), 0.4 mm.
IPC-2221 external: 1.23 A at 10 °C (≈ 8.8 °C at 1.17 A); the 2152 chart wants ≈ 0.6 mm. All are
≤ 2.5 mm long and sit on wide copper, so they will not reach 10 °C; recorded because the intent
cites 2152. Each layer transition on the 5 V trunk is a single 0.3 mm via (≈ 0.55 mm 1 oz
equivalent); fine for 1.17 A. LDOIN_P from R95 to U11 is 0.2 mm for 13 mm (0.74 A at 10 °C vs 0.5 A
required; ≈ 4 °C at 0.5 A). `work/power_paths.out`, `work/power_raw.out`.

**N5. Hot-plug.** Copper J1 → U16 is ≈ 29.5 mm (B4/A9) / 15 mm (A4/B9), 0.2–0.5 mm over a plane
0.2 mm away: ≈ 0.3 nH/mm → ≈ 10 nH including two vias, ~1–2 % of a 0.5–1 µH cable. C113 4.7 µF
through R121 1.5 Ω: with 1 µH cable Z0 = 0.46 Ω, ζ ≈ 1.6 (overdamped); C15 100 nF resonates with
1 µH at 500 kHz (Z0 3.2 Ω) and the 1.5 Ω branch damps it to ζ ≈ 1.07. Peak at U16 IN stays within a
few hundred mV of the source; 6.5 V (TPS2553 recommended max, `datasheets/TPS2553.txt` line 28) is
not approached. Netlist confirms C113.2 → VBUS_DAMP → R121 → GND.

**N6. USB D+/D−.** Lengths 44.8 / 51.7 mm, skew 6.9 mm ≈ 45 ps (< 100 ps). Not routed as a pair:
D+ uses F.Cu + In2 + B.Cu with 4 vias, D− F.Cu + B.Cu with 2; widths 0.15/0.2 mm. Fine for
Full-Speed; D1 is in the flow (pads 1/6 and 3/4), R3/R4 are 4.3–5.6 mm from pins 46/47.

**N7. QSPI decoupling.** C11 (100 nF) 3V3 pad is 1.9 mm from U2.8 and in line (supply → C11 → pin);
C8 1 µF is 4.6 mm from pin 45. U1 EP has 8 GND vias; U11/U12 EPs 6 each, U13 9, U14 4 — the only
vias touching SMT lands, matching fab note 4.

**N8. CPL rotations differ from board rotation for 26 parts** (U2, U3, U5, U6, U7, U11, U12, U15,
U16, U17, U18–U21, D1, D11–D14, D28, Q2–Q7). These look like per-part JLC orientation offsets and
cannot be verified from the export; check them in the JLC assembly preview before confirming.
CPL positions match the board to < 0.01 mm (origin lower-left, y flipped); BOM and CPL designator
sets are identical; J3/J7/J8/J9 (hand-fit) and J4 (DNP) are correctly excluded from the JLC files
and present in `bom-complete.csv`. Cosmetic: the SW row's Comment says "BOOTSEL" for both SW1 and
SW2 (`work/cmp` output in session log).

**N9. Hole clearances at the vendor limit.** J1's NPTH peg to the GND pours on In1/In2/B.Cu is
exactly 0.200 mm (JLC NPTH-to-copper min 0.2); its peg to the shield slot wall is 0.37 mm (JLC
hole-to-hole 0.45) — both inside the standard HRO TYPE-C-31-M-12 footprint, routinely built by JLC.
Via-to-via wall min 0.25 mm (≥ 0.2); via hole to other-net copper min 0.225 mm (≥ 0.2); PTH hole
to other-net copper ≥ 0.28/0.3 on all layers. `work/geom_checks.out`.

**N10. Tiny fill fragments.** ~45 zone-fill pieces under 0.05 mm² (teardrops on 0.15 mm tracks),
three under 0.005 mm²: RAW_P (128.61, 121.51), USB_VBUS (61.07, 135.91), In2 3V3 (141.07, 131.76).
All touch same-net copper (0 isolated fragments); cosmetic.

## Checked and found clean

- DRC (KiCad 10.0.4, severity-all, all track errors, schematic parity) with the LCR libraries
  resolved: 0 violations, 0 unconnected, 0 parity issues (`work/drc-lib.json`). ERC: 0 (`work/erc-lib.json`).
  Without the library table both report only "library not found" warnings (`work/drc.json`, `work/erc.json`).
- Netlist: board pad nets vs `cad/design.json`: 0 mismatches (test pads, fiducials and holes are not
  in design.json, as expected). Board vs Rev G board: 0 pad-net differences; only J5 (GND, 3V3)
  removed. `design.json` vs `design-rev-g.json`: only J5 and part positions differ (`work/cmp_nets.out`).
- Copper-to-edge on the board file: F.Cu 0.400 (D4 pads at the north edge), In1 0.500, In2 0.400,
  B.Cu 0.450 — the 0.4 mm promise holds in the CAD (not in the frozen Gerbers, see B1).
- Edge cuts 100.000 × 100.000; aux origin (50, 145) = lower-left as fab note 9 says.
- Drill summary on Dwgs.User (41/27/356 vias, 2+2 slots, 2×1.0, 4×1.2, 16×1.4, NPTH 2×0.6 + 4×3.2,
  456 holes) matches the board file exactly.
- B.Silkscreen is empty in the board and in the Gerber (fab note 3).
- Silk: every text 1.0 mm / 0.15 mm; 0 silk items within 0.15 mm of exposed front copper
  (pcbnew effective shapes, `work/silk_exact.out`); 0 overlapping silk texts; 0 text over another
  footprint's outline; silk over tented vias only (16, cosmetic).
- Courtyards: all 280 footprints have F.CrtYd; 0 overlaps; only J1's courtyard crosses the edge
  (the 0.2 mm shell overhang in fab note 7).
- Keep-outs: the OPA810 input/feedback plane void and the other analog keep-outs are identical to
  Rev G; only the switcher keep-out moved with the block.
- F.Mask, F.Paste, F.Silkscreen, B.Mask, Edge_Cuts Gerbers are semantically identical to a fresh export.
- Mounting holes at the Rev F pattern; H1, H2 have no copper within 3.5 mm on either outer layer.
- J5 removed; TP8 (3V3, (92, 141.6)) and TP9 (GND, (94.6, 141.6)) are 5–8 mm from SW1/SW2; J4
  (SWD) kept, DNP, excluded from BOM/CPL.
- SW1/SW2 (TS-1088, 3.9 × 3 × 2 mm top-actuated) have only 0603/0805 parts within 4 mm and the
  tallest nearby part (C117, 6.9 mm) is 31 mm away: pressable from above with the lid off. D19/D20
  are top-view 0603 LEDs with nothing taller than 0603 within 3 mm.
- Moved blocks moved rigidly: power entry (U16, R110, C113, R121, C16, U3, C17) exactly −24 mm;
  switcher block (U13, L1, L2, D2, D3, C80–C92, C116–C118, R80–R84, R111, R119, R120, U17) exactly −10 mm.
- USB D+/D− skew 45 ps; U16 IN hot-plug peak well under 6.5 V (N5, N6).

## Work products

All under `work/`: `dump_board.py` (pcbnew → `g100.json`, `revg.json`), `cmp_parts.py`, `cmp_nets.py`,
`cmp_copper.py`, `gerbercmp.py` (+ `gerbers-check2/` re-export), `drillcmp.py`, `geom_checks.py`,
`silk_exact.py`, `craft_checks.py` (+ Rev G run), `power_paths.py`, `power_raw.py`, `signals.py`,
`cadlib/` (copy of `cad/` with fp/sym-lib tables for the library-resolved DRC/ERC), and the
`.out`/`.json` results named above.
