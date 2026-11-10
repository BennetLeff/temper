# Rev G100 re-check, 2026-11-10 export (relay copper, 3V3A, stubs, RUN, fab note 4)

Independent re-check of `cad/` against `prev/`. KiCad 10.0.4 (`pcbnew` read-only, `kicad-cli`). Scripts and
outputs are in `work/`; every number below is reproducible from them.

## Verdict: FINDINGS (two, both minor craft; neither is a fab or electrical blocker)

| # | Where | What |
|---|-------|------|
| F1 | F.Cu, VRLY, D6.1 (91.2575, 118.65), D7.1 (106.2575, 118.65), D8.1 (121.0575, 118.65) | 0.6 mm stubs enter SOD-323 pads that are 0.45 mm across; the opposite pads of the same diodes are fed by 0.2 mm |
| F2 | F.Cu, RUN, (83.8, 140.825) to (84.875, 141.85) | the re-entered RUN diagonal is 43.6 degrees, not 45, and three segments meet 0.05 mm short of SW2.1's pad edge |

Everything else differs only as the six stated items say, and every check below passed.

### F1: VRLY 0.6 mm stubs wider than the D6 / D7 / D8 pads

- Layer F.Cu, net VRLY. Tracks (91.2575, 118.65)-(91.2575, 119.6), (106.2575, 118.65)-(106.2575, 119.6),
  (121.0575, 118.65)-(121.0575, 119.6), all 0.6 mm, 0.95 mm long, from a 0.6 mm via on the B.Cu trunk at
  y 119.6 up into pad 1 of D6, D7, D8 (1N4148WS, `LCR:D_SOD-323`, pad 0.6 x 0.45 mm, footprint rotated 90 so
  the pad is 0.45 mm across the track). The track overhangs the pad by 0.075 mm each side; the overhang is under
  mask (mask expansion 0), so no exposed copper, but pad 2 of each diode (RLY_SET_MED / _LO / _HI) is fed by
  0.2 mm copper. Before the change all three stubs were 0.2 mm.
- Evidence: `work/clearance_check.py` -> `work/clearance_check.json` (`wider_than_pad: true` on the three
  entries; "tracks wider than their pad across the entry: [(91.2575, 118.65), (106.2575, 118.65),
  (121.0575, 118.65)]"); pad geometry and both boards' entry widths from the inline pcbnew dump in the
  review transcript (D5-D9 block).
- Why it matters: these stubs carry only the coil's flyback current for a few ms; their width adds nothing to the
  RESET coil voltage (the 0.95 mm stub at 0.2 mm is about 10 mohm). A 0.6 mm neck on one pad of a SOD-323 and a
  0.2 mm neck on the other is the classic thermal-asymmetry / tombstone setup at reflow, and the track is wider
  than the land, which the review brief names as a finding. D9.1 (146.5, 83.05) has the same asymmetry
  (0.6 in on pad 1, 0.2 on pad 2) but its pad is 0.6 mm across the entry, so not wider; D5 is symmetric (0.6 on
  both pads).
- Suggested hand fix: set the three stubs (and, for symmetry, the last 1.15 mm into D9.1 from (145.3515, 83.05))
  back to 0.2 mm, keeping the 0.6 mm elsewhere. Zero effect on the drive budget: the nodal solve
  (`work/copper_drop.py`) shows these stubs carry 28 mA at most for a few mohm.

### F2: RUN re-entry at SW2.1

- Layer F.Cu, net RUN. New tracks: R9.1 (83.25, 140.825) -> (83.8, 140.825) -> (84.875, 141.85) ->
  (84.875, 141.9) -> (84.875, 142.9) = SW2.1 pad centre. The east branch (84.875, 141.4) -> (84.875, 141.85)
  also lands on (84.875, 141.85). SW2.1 is 1.05 x 2.0 mm at (84.875, 142.9), so its top edge is y 141.9.
- The diagonal is dx 1.075, dy 1.025: 43.6 degrees (the old one was 60.8). The three-way node sits at
  y 141.85, 0.05 mm above the pad edge, in free copper (the 0.2 mm tracks overlap the pad anyway, so it is
  electrically a pad junction; DRC is clean).
- Evidence: `work/board_diff.py` -> `work/track_diff.txt` (RUN rows); pad dump in the transcript.
- Suggested hand fix: start the diagonal at (83.8, 140.825) and end it at (84.875, 141.9) (dx = dy = 1.075,
  exact 45), end the east-branch vertical at (84.875, 141.9) as before, and keep the single 1.0 mm axial entry
  (84.875, 141.9) -> (84.875, 142.9) into the pad centre. The junction then sits on the pad edge.

## Observations (not findings)

- Fab note 4 now says the exposed-pad thermal vias "sit under paste windows". Checked against the footprints
  (`work/` transcript, EP block): U13 9/9 and U14 4/4 via centres are inside F.Paste windows; U11 and U12 4 of 6
  (2 straddle a window edge); U1 3 of 8 (4 straddle, 1 sits between windows). All are inside the pasted EP
  area, so the intent of the note (plug them, they are in paste) holds; the wording is loose for U1. "No other
  via touches an SMT land" verified: 0 vias collide with any SMD pad other than the five EPs.
- Teardrops were regenerated (1182 -> 1140): the widened tracks lost theirs where track width reached the
  via/pad size (VRLY F.Cu 32 -> 9, VRLY In2 8 -> 1, RLY_RST F.Cu 13 -> 8, VRLY B.Cu 8 -> 5, RLY_RST B.Cu 4 -> 2,
  3V3A In2 10 -> 8). No other net's teardrops changed.
- The 45-degree chamfers that moved with the widening (RLY_RST B.Cu (102, 68.2)/(102.6, 67.6) ->
  (102, 69.4)/(103.8, 67.6); VRLY In2 (131.4, 113.6)/(132, 113) -> (130.2, 113.6)/(132, 111.8); VRLY F.Cu
  (144.6, 82.45)/(145.2, 83.05) -> (144.6, 82.2985)/(145.3515, 83.05); 3V3A (70, 89.6)/(70.6, 90.2) ->
  (69.4, 89.6)/(70.6, 90.8)) are all exact 45 and are part of items 1 and 2.
- The widened In2 trunk end at (100, 71) is 0.5 mm from C2M_DIV (In2, y 70.1): the same 0.5 mm the existing
  0.6 mm via at (100, 71) already had, so no new approach to an analog net (see Risks).

## What was verified

### 1. Item-by-item board diff (`work/board_diff.py` -> `work/board_diff.json`, `work/board_diff.txt`, `work/track_diff.txt`)

Canonical signatures of every track, via, arc, footprint (position, rotation, layer, attributes, every pad's
net / position / size / shape / drill / layers / local overrides, graphics, fields), zone (settings, outline,
fill per layer), teardrop and board drawing, compared as multisets.

- Nets: 181 in both, same names. Board setup / design rules identical; `.kicad_pro` byte-identical.
- Footprints: 282, all identical (0 differences). Vias: 435, identical. Arcs: none.
- Tracks: 1941 -> 1945; 68 removed, 72 added, all on VRLY (56), RLY_RST (24), 3V3A (6), RUN (8), USB_VBUS (1
  removed), LDOIN_N (1 removed). Every one maps to items 1-4; nothing else moved.
- Zones (23 real zones): settings and outlines identical; only the GND fills on B.Cu and In2.Cu differ (item 6).
  F.Cu and In1.Cu fills identical. Rule areas (20) identical.
- Drawings: 66, only the two fab-note-4 lines on User.Drawings differ (item 5), text at the same position/size.
- `design.json` differs only in the same two note lines; `routing.json` tracks/vias equal the board exactly in
  both (1941 / 1945 segments, 435 vias), zones and keepouts identical, `craft_exceptions` lost the one
  `LDOIN_N U12.5 pad_entry` entry that the removed stub had caused (item 3).

Item checks: (1) VRLY / RLY_RST widths now 0.5-0.6 with exactly the stated 0.2 exceptions (VRLY In2
(100, 113.6)-(103, 113.6) and (123.4, 113.6)-(125, 113.6); RLY_RST B.Cu (129.5, 67.6)-(130.3, 67.6)) and the
0.3 mm VRLY B.Cu (100, 119.6)-(121.058, 119.6). (2) 3V3A In2 (64.25, 89.6) -> (70.6, 106.75) is 0.4 mm; all
3V3A In2 copper is 0.4, all F.Cu 0.2. (3) USB_VBUS F.Cu (59.2, 115.05)-(60.075, 115.05) and LDOIN_N F.Cu
(145.15, 110.975)-(145.4291, 111.2541) removed, nothing added. (4) RUN as in F2. (5) note text as stated.

### 2. Clearances of every changed track (`work/clearance_check.py` -> `work/clearance_check.json`)

Edge-to-edge distance to every other-net track, via, pad, zone fill and teardrop on the same layer, by
bisection on `SHAPE::Collide`. Minimum over all 72 tracks: 0.200 mm (board rule 0.15, JLC 0.09; JLC via-hole
to copper 0.2 also met: the 0.2 mm VRLY In2 sections sit 0.35 mm from the hole edges of the RLY_RST via
(102, 113) and GND via (124.175, 114.2)). Closest pairs: VRLY F.Cu stubs to RLY_RST F.Cu x 102 at 0.25;
VRLY F.Cu (95.22, 99.92) to RLY_SET_MED at 0.30; B.Cu / In2 copper to the refilled GND pour at 0.2005.

Pad / via entries: every changed-track end that lies in a pad is at the pad centre and no wider than the pad
across the entry except F1. 37 ends on vias: none wider than the via (0.6 on 0.6 mm vias at most).

### 3. Jack band (`work/jack_band.py` -> `work/jack_band.json`)

Minimum clearance from every JK_* track, via, pad and teardrop to every other net, per layer and net, before
and after: all 25 (layer, net) minima identical; overall minimum 0.20 mm in both (B.Cu RLY_RST track
(131.5, 57.5)-(131.5, 76.0) to a pre-existing JK_HCUR via, unchanged). The only changed copper within 3 mm of
JK_* is the RLY_RST B.Cu y 67.6 run: 0.5 mm section ends at x 129.5, 0.73 mm from the JK_LCUR via (130.5, 66.8);
the 0.2 mm tail keeps 0.42 mm to it, as before.

### 4. DRC (`work/drc/drc-prev.json`, `drc-cad.json`, `drc-cad-jlc.json`)

`kicad-cli pcb drc --severity-all --all-track-errors --format json`, board rules: prev and cad each report
199 warnings, all `lib_footprint_issues` ("configuration does not include the footprint library 'LCR'"; the
export has no fp-lib-table), the same set in both; 0 errors, 0 unconnected, 0 isolated copper, 0 starved
thermals, 0 slivers. Scratch copy `work/jlc-scratch/` with JLC limits written into the project rules and
netclass (clearance 0.09, track 0.09, via 0.25/0.05, hole-to-hole 0.2, hole clearance 0.2, edge 0.2, silk
0.15 / 1.0 / 0.15): same 199 warnings, nothing else.

### 5. Connectivity

0 unconnected items in both boards (DRC); all pad nets identical (footprint diff); the two removed stubs left
U12.5 and C113.1 connected. Each net's pad set and connectedness are therefore unchanged.

### 6. Gerbers (`work/gerbers-A..D/`)

Fresh `kicad-cli pcb export gerbers -l F.Cu,In1.Cu,In2.Cu,B.Cu,F.Paste,F.Silkscreen,B.Silkscreen,F.Mask,
B.Mask,Edge.Cuts,User.Drawings --use-drill-file-origin` (aux origin (50, 145), X2, netlist attributes, Protel
extensions, precision 6) is identical to `gerbers/` for all 11 layers and the job file, ignoring creation-date
lines. `export drill --excellon-separate-th --drill-origin plot --excellon-oval-format route` is identical to
both `.drl` (the 4 oval slots as routed G00/M15/G01/M16). `export ipcd356` is identical to `.d356`; it also
uses the aux origin (via (74.75, 113.75) appears as X+009744 Y+012303). Gerbers, drills and netlist share one
origin, as fab note 9 promises.

### 7. Numbers

- Coil voltage (`work/copper_drop.py` -> `work/copper_drop.json`): nodal solve of VRLY (source R101.2, 28.1 mA
  drawn at K1-K4 pin 10) and RLY_RST (sink Q2.3, 28.1 mA at K1-K4 pin 6) built from the `.kicad_pcb` copper
  (not routing.json), rho 1.72e-8 x (1 + 0.0039 x 40), 35 / 15.2 um, via barrel pi x 0.3 x 18 um. Worst-coil
  copper drop prev 18.25 + 15.19 = 33.44 mV; cad 6.32 + 7.14 = 13.46 mV; improvement 19.99 mV. Designer's
  `drive-budget-prev.json` / `drive-budget.json`: 18.33 + 15.52 -> 6.39 + 7.46, coil 4.1492 -> 4.1692 V
  (+20.0 mV). Agreement to 0.4 mV, so 4.169 V at VBUS 4.40 V stands (must-operate 3.75 V, 4.125 V at 45 C).
  Where it came from: the In2 x 100 trunk (84 mA x 89 mohm = 7.5 mV, now 2.5), the two In2 branches to K4
  (5.8 + 5.7 mV, now 1.3 + 1.8) and the F.Cu RLY_RST x 102 run (3.6 + 2.4 mV, now 1.4 + 1.0).
- 3V3A width: IPC-2152 fit A = (117.555 x dT^-0.913 + 1.15) x I^(0.84 x dT^-0.108 + 1.159), dT 10, I 0.6:
  A = 15.52 x 0.396 = 6.14 mil^2 = 3.96e-3 mm^2; at 15.2 um that is 0.261 mm (0.113 mm at 35 um). The old
  0.2 mm In2 run did not meet it; 0.4 mm does, and every 3V3A segment now does (In2 all 0.4, F.Cu 0.2).
  `evidence/current_check.json` reports the same 0.261 / 0.113 need and 0 fails.

### 8. New risks from the change (`work/neighbours.py` -> `work/neighbours.json`)

- VRLY is a DC supply that moves only by its own copper and R101 drop (tens of mV) during the 20 ms pulse; the
  4.2 V switched node is RLY_RST. Same-layer neighbours of the widened copper within 1 mm are relay-drive nets
  (RLY_SET_*, RNG_RESET, ISO_S2, 5V) and JK_LCUR at 0.62 mm on B.Cu (unchanged minimum). The nearest analog
  net is C2M_DIV at 0.5 mm from the trunk end / via at (100, 71), the same as before.
- Adjacent-layer crossings through the 0.21 mm prepreg: In2 C1M_DIV / C2P_DIV / C2M_DIV (y 68.9-70.1) cross
  the B.Cu RLY_RST x 102 run, now 0.6 wide: about 23 fF per crossing (was 8 fF), 0.1 pC into the divider nodes
  at a range change, which the firmware already settles across. In2 VRLY crosses B.Cu 12V, -12V, RLY_SET_HI;
  B.Cu VRLY crosses In2 RNG_SET_REF. No TIA, codec-input, source or JK net is newly adjacent.
- Pour: the B.Cu / In2 GND fills shrank only around the widened tracks; DRC reports no isolated copper or
  slivers, so no pour fragment was created.

---

## Dispositions (designer, 2026-11-10)

| Finding | Disposition |
|---|---|
| F1 VRLY 0.6 mm into the D6 / D7 / D8 lands (0.45 mm across) | **Fixed.** The three diode stubs, and the last run into D9.1, are back to 0.2 mm. They carry flyback current only, and the coil voltage is unchanged at 4.169 V (`drive-budget.json`) |
| F2 RUN re-entry 43.6° and junction | **Fixed.** The diagonal is now exactly 45°: (83.85, 140.825) → (84.875, 141.85). It meets the east branch at (84.875, 141.85), the point where the craft pass puts the pad-edge node, then enters SW2.1's centre along its axis |
| Note: fab note 4 wording for U1 | Accepted: every EP via is inside the pasted exposed pad, which is what the note is for |

Gates rerun: pre-DRC 0 and DRC 0; current check 0 FAIL; every screen 0 findings; analog core 403 / 403.
