# Independent layout review: controller C53 (commit eb8218075, frozen export)

Reviewed 2026-11-27 from the frozen export only. Coordinates are world mm (X = kx − 58, Y = 110 − ky) unless marked "kicad".
All measurements come from scripts in `_review_scratch/` (pcbnew geometry dump `dump.py` → `geom.json`, then shapely):
`netgraph.py` (per-net copper islands and the vias joining them), `couple.py` (parallel-run coupling), `gatetest.py`
(CPL gate mutation test), `plot.py` (region renders). The export itself is untouched.

## Verdict

No proven dead-board error, but **do not order yet**. Two items (M1, M2) are unresolved orientation / pin-numbering
questions that could scramble connectors and cost nothing to close. Three more (M3–M5) are power-path defects in the C51
additions that every gate misses, because the gates name only the four older power nets.

## MAJOR (fix or close before ordering)

### M1. J4 pin numbering: KiCad and JLC footprints disagree, and the sales drawing was never used to settle it
- **Evidence:** `evidence/land-patterns.json` fits J4 (C277731) at 0.0 mm RMS, but `cpl_rotation_gate` returns
  "JLC numbering 180° from ours" (`fab/fab-notes.md` line 24). `PREVIEW-2026-10-19.md` says that at KiCad's rotation JLC's
  body sits where ours does, and at +180 it hangs off the edge. A right-angle header cannot be turned, so the two libraries
  number the same physical part differently: JLC pin 1 is KiCad pin 16.
  Board: pins 1–8 in the row at X −28.57 (nearest the pegs), pin 1 at Y 31.9; pins 9–16 at X −25.56.
  The KiCad footprint cites the 2-circuit drawing `430450201_sd.pdf`, not the 16-circuit one (`evidence/fab-loose-ends/README.md` §3).
- **How:** read the pad records and the gate output; reran the gate (`gatetest.py`).
- **Not established:** which library is right. KiCad's is the likelier one, but if it is wrong all 16 J4 circuits are transposed
  (v3v3 out, PERMIT, four PWMs).
- **Fix:** read circuit 1's position relative to the pegs on `430451600_sd.pdf` (the owner has it) and record it in DECISIONS.
  No copper change if KiCad is right.

### M2. Eight THT connectors go out with a known 180° disagreement, and the CPL gate cannot fail on THT
- **Evidence:** J1, J2, J3, J7, J9, J14, J15 (and J4): placing JLC's pad record at the CPL rotation puts JLC pad 1 on our last
  pin (my end-to-end check: 2.0–27.7 mm error on these, ≤ 0.35 mm on the 330 SMD lines that have a JLC pad record; R32 has none). J10, J12, J13 agree.
  `fab.py` lines 122–124 only list THT mismatches.
- **How:** `gatetest.py` applied wrong offsets to a copy. Every SMD mutation was caught (D1, D9, C1, C9, U3, U4, U20, U30, L1, L2, Q1…).
  Not caught: any THT rotation, including J4 +90 and J7 +180, and R32 +90 (no JLC pad record; two-pad "R" exemption).
- **Consequence:** an XH header fits its holes both ways. Reversed, J7 swaps +5 V with CS_EXP#, J15 swaps 12 V / FG / PWM.
  J9 is deliberately turned 180°, which makes a "same as the others" insertion more likely.
- **Fix:** settle it in JLC's preview before paying: the XH pin row is 2.35 mm from one wall and 3.40 mm from the other, so a
  reversed body sits 1.05 mm off the silk outline. Add an order remark ("THT connectors per silkscreen outline and pin-1 mark"),
  or leave the 11 THT parts off the JLC BOM and hand-solder them. Make the gate fail on an unreviewed THT mismatch.

### M3. Face-fan buck (U51 / L3 / J15) was routed as signal copper
- **Evidence (F.Cu / B.Cu, all 0.15 mm unless stated):**
  - `sw_fan2`: U51.5 → L3.1 is 9.1 mm of 0.15 mm track with no pour; the bootstrap cap C121 hangs off it through two vias
    at (82.55, 52.85) and (82.55, 50.45) and 2.4 mm of B.Cu.
  - `V12_FAN2`: L3.2 → J15.2 is about 45 mm of 0.15 mm track through three single 0.6/0.3 vias
    (86.65, 57.45), (86.65, 59.85), (101.05, 59.85); J15.2 is entered by one 0.15 mm track on B.Cu.
  - U51 VIN: fed from the B.Cu 1.0 mm V15_BLW trunk through single vias (81.65, 57.35) → (79.35, 56.15) → (79.35, 53.95)
    and 0.25 mm tracks. The 100 nF C123 reaches VIN only through two more vias and 3.1 mm of B.Cu, so it does little.
    C122's ground pad is 4.06 mm from U51.4.
- **How:** `netgraph.py sw_fan2 V12_FAN2 V15_BLW`; render `ffbuck.png`.
- **Why it matters:** J15 is allocated 0.67 A. IPC-2221 external, 1 oz, 0.15 mm: 0.60 A for 10 K (calculated, same formula
  LAYOUT.md uses); about 0.15 Ω and 0.1 V in the output run. A stalled or shorted fan below the TPS62933's 3 A-class limit
  turns the trace into the fuse (inferred, not simulated).
- **Why the gates pass:** `OUTER_ONLY`, `power_layers`, `power_widths` and the Power net class list only V_BLOWER, sw_12,
  sw_3v3, v15_selv, V15_BLW. `sw_fan2` and `V12_FAN2` are class Default. LAYOUT.md's claim that V15_BLW "never depends on a
  routed track" is no longer true for the U51 branch.
- **Fix:** add both nets to the Power class and to the gates; give U51 the U2 treatment (VIN and SW pours in `floorplan.py`,
  C123 at pins 3/4 on F.Cu, ≥ 0.5 mm to J15 with two vias per layer change); gate minimum width on every buck net.

### M4. V_BLOWER (1.42 A typical, 2.70 A max) passes four single 0.6/0.3 mm vias in series
- **Evidence:** L2.2/C16/C17 (F) → via (112.15, 67.35) → B 10.9 mm → via (112.15, 78.25) → F 7.8 mm → via (119.75, 78.65)
  → B 7.2 mm → via (121.95, 84.95) → F 15 mm → J10.1. Width is 0.8 mm throughout (rule met).
  All 1105 vias on the board are 0.6/0.3; the Power class's 0.8/0.4 via in `controller.kicad_pro` is never used.
  `power_widths` reports `vias: 6` but gates nothing on it.
- **How:** `netgraph.py V_BLOWER`.
- **Assessment:** about 1.5 mΩ and 10 mW per via at 2.7 A (calculated, 20 µm plating assumed), so this is a reliability and
  margin issue, not an immediate failure: one barrel carries the whole blower supply four times over.
- **Fix:** two or three vias per transition, or 0.8/0.4 vias, or fewer layer changes; gate "single via in a > 1 A path".

### M5. The ESP32 module's 3V3 pin sits on a v3v3 island fed through one accidental link
- **Evidence:** In2 `V3V3_plane` fills as 8 separate polygons. The second largest (128.7 mm², X 126.6–146.9, Y 59.6–78.5)
  carries U4.2, C89 (22 µF), C90, R109, C30 and C32. Its only tie to the main plane is via (141.95, 75.04) at C32.1 →
  F.Cu 0.4 mm × 1.5 mm + 0.3 mm × 1.3 mm past U29.4 → one via to the main pour. Five other islands hang on one or two
  similar links (U10/U34/C36, U35/C37, U40/R99, U12).
- **How:** `netgraph.py` graph search from each In2 island to the main polygon.
- **Assessment:** DC drop is a few mV and one via is enough for the module's peak current, so it works. But the module's supply
  is a single point, its current crosses the REF2025 / MAX31865 DVDD bypass node, and LAYOUT.md's "In2 3.3 V plane gives
  each capacitor a one-via return" is false here. Borderline MAJOR / MINOR; listed here because the fix is small.
- **Fix:** move the In2 signal tracks that ring the island, or add three or four v3v3 bridges; make `plane_islands.py` report
  island area and link count and fail on a single-link island that carries an IC supply pin.

## MINOR

- **m1. U30 DVDD and its bypass are on different v3v3 islands.** U30.2's via (146.72, 73.1) enters the main pour; C30.1's via
  (144.84, 74.34) enters the M5 island. `rtd_decoupling` passes at 2.51 mm because it measures pad boxes, not copper.
  Fix with M5; make the gate require a shared copper island.
- **m2. J13.1 joins the V15_BLW pour through one 0.6 mm spoke** (F.Cu only, −X side; B.Cu pad unconnected), and it now carries
  the whole board (53.4 W per DECISIONS C51, about 3.6 A). LAYOUT.md says "spokes". DRC allows it (`min_resolved_spokes: 1`).
  Dissipation is negligible (0.25 mΩ, calculated). Fix: solid connection or four spokes; raise the DRC minimum to 2.
- **m3. `pwm_hb` runs 25.3 mm on In3 through the latch block** (X −20.6…23.1, Y 57.8…70.9). The `interlock` gate passes because
  it counts only nets on U4's own pads; the PWM nets sit behind 33 Ω resistors. HS_SENSE (13.1 mm B.Cu), RAIL_OK, bay_buf_out
  and coil_buf_out also pass through. No interlock net runs within 0.35 mm of `pwm_hb` (measured). The gate also samples only
  11 points per track, so a long track can step over the 4.5 mm PERMIT-gate box; my exact intersection found no such miss on
  this board. Fix: include firmware-driven nets behind series resistors; use a true segment/box intersection.
- **m4. In2 and In3 are 0.109 mm apart and 0.57 mm from their planes; different nets run broadside.**
  UI_MOSI / UI_CS_OLED_N 33.3 mm, pwm_hb / LINE_ZC_MCU 15.5 mm, pwm_lb / LINE_ZC_MCU 9.2 mm, pwm_hb / rx_a_out 9.4 mm
  (the D-11 bus-voltage receiver output), BLW_PG / UI_DC 10.9 mm. Inferred glitch on LINE_ZC is a few hundred mV for ~10 ns.
  Fix: router penalty for In2/In3 overlap, or keep PWM off In2/In3.
- **m5. RTD analog nets are auto-routed with no guard.** Unfiltered `rtd_sense_n_ext` is 114.6 mm with 8 vias and
  `rtd_sense_p_ext` 83.6 mm, because their taps (R77 at (113.8, 65.6), R48, R51) are 35–40 mm from U30. `p1` is 85 mm with
  5 vias and reaches X 111, about 9 mm from L2's courtyard and 0.72 mm from V_BLOWER. Parallel runs at 0.25 mm:
  `rtd_sense_p_ext` / UI_MOSI 12.3 mm (In2), `rtd2_bias` / RTD2_CS_N 14 mm (F), `r_high_top-inp` / pwm_hb 11.7 mm (B).
  `partition` measures parts only. The RC filter makes the error small (inferred). Fix: place the tap resistors at the front
  end; add RTD-to-digital spacing in the router.
- **m6. Ground stitching is thin away from the parts.** 327 GND vias, but 12 % of the board is more than 10 mm from one and the
  worst point is 25 mm ((167, 21)); the front strip X 3–106, Y 33–52 has one via per 20 × 19 mm cell. 39 signal vias are more
  than 8 mm from a ground via (RTD_SCK, UI and I2C vias at the module front, 8–13 mm). Fix: a 10 mm stitching grid.
- **m7. No fiducials** on a 206 mm board with 0.5 mm-pitch parts. Add three, or confirm JLC adds its own.
- **m8. 196 vias have their hole inside an SMD pad** (68 R, 33 C, 81 U, incl. J11.5 / J11.8 probe pads) and 244 more overlap a
  pad. Acceptable only with epoxy fill and cap: make that an explicit order-form item, not a default.
- **m9. Stock: 18 BOM lines have no reading** (MAX31865AAP+T, EMC2301, SS14, L2, C1/C9, J14, J15, U11-class…), and the rest
  date from October (TPS3703 read 18). `fab.py` treats "no reading" as fine, so fab-notes says "stock 0: none".
- **m10. Silk says "rev L2 (enclosure R33)"** at (115, 30); 147 of 343 designators are off the silk.
- **m11. The zip carries `*-drl_map.gbr`** files; remove them so JLC's importer cannot take them for layers.
- **m12. F.Cu tracks under L2's body:** RTD_SDO 13.4 mm, ss_12 4.7 mm (1.33 mm from the SW pour).

## NOTE

- LAYOUT.md's results section describes an older board: 284 parts / 1074 vias / 34 warnings / 13 checks / zip `9331ee6d…`.
  Actual: 343 footprints, 1105 vias, 21 warnings, 17 checks, zip sha256 `79126944…`. `jlc-dfm.json` still prints
  "JLC04161H-7628". The height table still names C1 as EEE-FK1E101P; the BOM part is UCD1E101MCL6GS (height not verified).
- `jlc_dfm_check.py` covers ring, drill, track width and size only; nothing six-layer-specific.
- 21 vias and 86 mm of F.Cu signal track lie under the WROOM body; fine only with capped vias. USB D+ / D− are routed as two
  unrelated singles (48.7 / 34.8 mm); adequate for full speed to J11.
- J11's lower alignment hole leaves a 0.7 mm web to the front edge; its courtyard overhangs the edge by 0.33 mm.
- JLC's minimum PCB quantity is 5, not 3.

## DRC warning classes (re-run, KiCad 10.0.4, also with `--refill-zones`)

0 errors, 0 unconnected, 0 parity, 21 warnings: identical to `evidence/drc.json`; stored fills are current.
- **connection_width (9):** pour necks 0.095–0.126 mm on F (6), In1, In4, B. Not structural: after removing zero-width fill
  slits, no In1 / In4 area depends on a neck under 0.6 mm. Cosmetic.
- **silk_edge_clearance (10):** hole circles, J11 and J13 outlines at the edge. Harmless.
- **lib_footprint_mismatch (2):** U20 pads 0.28 mm instead of 0.35 mm (all 8, positions unchanged); U4 has no pad
  difference (courtyard only). As claimed.
- **copper_sliver:** none reported.

## Checked and found correct

- Gerbers and drill regenerated from the board are identical to `fab/gerbers` and to the zip (18 files; six copper layers,
  job file 6 layers / 1.6 mm / ENIG, stack-up as stated). Drill: 67 component + 1105 via PTH, 5 NPTH; six Ø4.0 holes in Edge.Cuts.
- Board pad nets equal `controller-netlist.net` and `frozen/default.net`: 343 parts, 1059 nodes, no split, merge or missing node.
- BOM / CPL / board: 342 placed parts each exactly once, J11 excluded, footprints and MPNs agree, all top side.
  330 of 331 SMD lines land JLC's numbered pads on ours within 0.35 mm, rotation and position (R32 has no JLC record; pad-box centre assumed as JLC's origin).
- In1 and In4 are solid: 90 % copper, largest void about 5 × 3 mm (merged antipads), no slot under any track beyond 1.3 mm.
  Nothing floats; every pour island has a via or pad.
- RTD analog nets are on F.Cu / In2.Cu only; no In3 track in either keep-out; both bucks' parts ≥ 10 mm from RTD parts.
- V_BLOWER, sw_12, v15_selv, V15_BLW have no inner-layer track; V_BLOWER ≥ 0.8 mm; U1 and U2 hot loops, SW pours and FB
  routing are sound (input cap 1.3 mm from VIN, GND via 0.9 mm from pin 4, no SW via).
- Via hole-to-hole ≥ 0.506 mm; PTH rings ≥ 0.20 mm; no paste on THT or on the back; no silk on pads; no courtyard overlap;
  holes, outline and all ten connector centres match `world.py` and ENCLOSURE-HANDOFF; mounting-hole keep-outs clear.

## Not checked

- Block-validator binaries and `WAIVERS.md` line by line; schematic correctness; firmware pin map.
- The enclosure source documents (only `world.py` and ENCLOSURE-HANDOFF are in the export); part heights against datasheets.
- JLC's live capability pages, stock and placement preview (no network used).
