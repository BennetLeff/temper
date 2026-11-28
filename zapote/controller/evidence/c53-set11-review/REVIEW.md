# Independent layout review: controller C53 set 11 (export of 5d3ff39c2)

> Archived copy (2026-11-28) of the independent report on the frozen export of commit 5d3ff39c2 (board `e82e6140…`). Paths in it are relative to that export. Its scripts are in `scripts/`. Dispositions: DECISIONS C53, set 11 review.

Reviewed 2026-11-27/28 from the frozen export `build/review-s11/controller/`.
Board `pcb/controller.kicad_pcb`, sha256 `e82e6140…7d` (matches the brief).
Every number below was measured from the board file, the fab package or the frozen netlist with the scripts in
`build/review-s11/_review_scratch/`. Nothing in the export was modified.

**Frames.** Coordinates are KiCad board mm (kx, ky) unless marked "world". World X = kx − 58, world Y = 110 − ky.

## Verdict: do not order yet

One item stops the upload, and it is a CPL edit, not a copper change:

- **B1.** The CPL places eight through-hole connectors 180° from JLC's own library parts. Seven of them (the XH and PH
  headers) fit their holes either way, so they can be soldered in reversed.

After B1 is corrected the board is orderable in my judgement, with two things I would still do first:

- **M1.** Give the 3.3 V buck output more than one via. It is a local, additive copper change.
- **M2.** Order with epoxy-filled and capped vias. The layout depends on it.

I found no short, no open, no clearance or hole violation, and no footprint that disagrees with its part.

## BLOCKER

### B1. CPL rotation is 180° wrong for J1, J2, J3, J7, J9, J14, J15 (and J4)

**What.** For these parts JLC's library footprint is our KiCad footprint turned 180°: the body outline and pin 1
together, not only the pad numbers. The CPL carries KiCad's rotation unchanged for them, so JLC's part sits
reversed on our lands.

| Ref | LCSC | CPL rot | Body mismatch at CPL rot | Body / pin-1 mismatch at CPL + 180° |
|---|---|---|---|---|
| J1, J2 | C158012 B2B-XH-A | 0 | 1.05 mm, pin 1 at the far end | 0.00 / 0.00 mm |
| J3 | C144395 B4B-XH-A | 0 | 1.05 mm | 0.00 / 0.00 mm |
| J9 | C144395 B4B-XH-A | 180 | 1.05 mm | 0.00 / 0.00 mm |
| J15 | C157991 B5B-XH-A | 0 | 1.05 mm | 0.00 / 0.08 mm |
| J7 | C158027 B12B-XH-A | 0 | 1.05 mm | 0.01 / 0.22 mm |
| J14 | C131337 B2B-PH-K-S | 0 | 1.10 mm | 0.41 / 0.00 mm |
| J4 | C277731 43045-1600 | 90 | body on the inboard side of the pins | pin 1 0.00 mm, body on the edge side |

J10, J12 (C144394) and J13 (C160315) agree with JLC at the CPL rotation (0.12 / 0.00 mm and 0.00 / 0.00 mm). They
are correct as written.

**Why it matters.**
- An XH or PH header has a symmetric pin row, so it drops into the holes reversed. The pins sit 2.35 mm from one
  wall and 3.40 mm from the other; that 1.05 mm asymmetry is the mismatch in the table.
- A reversed header reverses the harness. DECISIONS C53 F2 already names the consequences: J7 reversed shorts v3v3
  to the UI board's ground, and J15 reversed puts 12 V on the fan's PWM pin. J14 swaps bay_node and ground.
- J1, J2, J3 and J9 reversed are electrically harmless (two-wire NTCs, symmetric 4-wire RTDs), but the key faces the
  wrong way for the enclosure harness.
- J4 cannot be inserted reversed (its two pegs are on one side only), so J4 is a preview and paperwork problem, not
  an electrical one.

**How I checked.** `_review_scratch/jlcfp/fetch.py` read the nine connector footprints from JLC's EasyEDA library
(pro.easyeda.com, the same source as `evidence/c52/fetch_pro_pads.py`). `jlcfp/chir.py` takes each record's pads and
its component-shape outline (layer 48), and compares them with the KiCad footprint's pads and F.Fab outline at the
four 90° offsets, both centred on the pad field. `cplfit.py` separately refits every CPL line against the committed
pad records: 333 SMD lines agree, the eight THT lines above need +180°.

**This reverses a project conclusion.** `layout/fab.py` and `PREVIEW-2026-10-19.md` treat the 180° as "a pad-numbering
difference" and keep KiCad's rotation because "with +180 JLC's J4 body hung off the board edge". The measurement
explains that observation differently:
- JLC's J4 footprint has its origin at the centre of the 2 × 8 pin field, and its body reaches 10.70 mm from there.
- The CPL puts J4 at kx 28.400. The pin-field centre is kx 30.935, which is 2.535 mm further inboard.
- So at the correct +180° the body is drawn to kx 17.7, which is 2.3 mm past the edge at kx 20. With the CPL X at
  30.935 it would reach kx 20.2, flush with the edge, as our footprint has it (mating face kx 20.515).
- At the CPL's present rotation JLC's body lies inboard of the pins (kx 25.3 to 39.1), which "sits inside the
  outline" but faces the wrong way.

**What I could not establish.**
- How JLC's through-hole operators act on a CPL rotation that disagrees with the silk. DECISIONS F2 says they follow
  the render. If so, the present CPL gives seven reversed headers.
- The real parts against a JST or Molex drawing. What I have is two independent libraries (KiCad's and JLC's) that
  agree on pin 1 relative to the body for every one of these connectors. That also supports open item M1 of the
  previous review (J4 numbering), but it is not the Molex drawing.

**Fix.** CPL only, no copper:
1. Add +180 to `CPL_ROTATION_OFFSET` for C158012, C144395, C157991, C158027, C131337 and C277731, and take those
   codes out of the keep-KiCad-rotation path (`THT_REVIEWED`).
2. Write J4's CPL position as the pin-field centre (kx 30.935, ky 67.600; the file has 28.400).
3. Regenerate the CPL and fab-notes. In JLC's preview each header's body should then sit on its silk outline with
   no manual rotation. Keep the arrival check on J7 and J15.

## MAJOR

### M1. The whole 3.3 V rail leaves the buck through one via

**What.** L1 pad 2 (v3v3, at (106.55, 91.60)) has exactly one connection: a 0.40 mm F.Cu track 1.3 mm long to a
single 0.6/0.3 mm via at (107.69, 92.19) into the In2 pour. There is no v3v3 copper on F.Cu joining L1 to its output
capacitors. C6, C7 and C8 (22 µF each) reach the rail only through their own single vias at (109.42, 92.28),
(110.10, 89.98) and (110.26, 94.69).

**Evidence.**
- `v3path.py v3v3 L1.2 U4.2,J4.3,J7.2,J11.1`: that via is a single point of failure on the path to every load.
- `mincut.py v3v3 L1.2 U4.2`: the minimum cut between L1 and the rail is that one via.
- Render: `_review_scratch/r_u1.png`.

**Why it matters.**
- `evidence/verify.json` gives the rail's peak as 1041 mA (581 mA on the board plus the OLED and UI allocation on
  J7.2). The project's own rule from the previous review (M4) is two barrels at every layer change carrying more
  than 1 A. The `power_vias` gate does not list v3v3, so it never looked here.
- One barrel carries the load plus the inductor ripple, and each output capacitor's ripple current makes two via
  passes (L1's via, then its own). One cracked or under-plated barrel takes down every 3.3 V part on the board and
  the power stage's logic supply on J4.3.
- Electrically one good barrel does carry 1 A (about 0.019 mm² of plating, roughly a 0.5 mm 1 oz track). This is a
  margin and reliability finding, not a dead board.

**What I could not establish.** JLC's actual barrel plating thickness; I used 20 µm.

**Fix.** Additive and local, so it meets the "better on every count" bar for a post-review change:
- an F.Cu v3v3 pour over L1.2, C6.1, C7.1 and C8.1 (the pads are 1.5 to 2.5 mm apart with only ground pour between);
- three or four vias from that pour into In2;
- add `v3v3` (source L1.2) to `power_vias.NETS` and `PV_LOADS` so the gate covers it.

### M2. The layout only assembles cleanly with epoxy-filled, capped vias

**What.** 387 of the 1312 vias have their drilled hole touching or inside an SMD pad (`viainpad.py`; most are the
fan-out vias 0.12 mm off a 0603 pad edge). A further 162 via rings come within 0.1 mm of a pad with no mask dam.

**Why it matters.** With plain tented vias these wick solder off the pads: tombstoned 0603s and starved SOT joints.
The board file itself says `capping no`, `filling no`; the requirement lives only in `fab/fab-notes.md` and in
DECISIONS (accepted as m8).

**What I could not establish.** That JLC applies filled-and-capped by default and at no charge for this six-layer
order. I did not read JLC's page.

**Fix.** An order-form line in the rewritten ORDER.md, checked on JLC's order summary before paying: via covering
"Epoxy Filled & Capped". If that option is refused or changed, do not order this layout.

## MINOR

### m1. The ESP32 module's supply island hangs on two 0.3 mm tracks
- In2's v3v3 pour is one main area plus 17 islands, all of them at kx > 170 or around U50 (`planes.py`,
  `v3islands.py`). LAYOUT.md's "In2 3.3 V plane" does not exist in the right-hand quarter.
- The module's island (142 mm², kx 187 to 204, ky 34 to 56) carries U4.2, C89 (22 µF) and C90. `mincut.py v3v3 J7.2
  U4.2` gives a minimum cut of 0.60 mm of copper: one B.Cu 0.30 mm track (191.6, 46.7)–(186.2, 49.8), 7.4 mm long,
  and one F.Cu 0.30 mm track near (194.2, 34.5).
- Estimated 12 to 15 mΩ through the short link, so the DC drop at a 350 mA transmit burst is a few mV, and the
  22 µF is on the island. I expect it to work.
- Fix when copper is next touched: make both links 0.8 mm, or pull the main pour up to the via at (191.6, 46.7).
- Other supply pins with a single thin link from the plane: U41.5 (0.30 mm), U3.2 (0.28 mm), and a single 0.40 mm
  stub each for U9.20, U52.3, U15.8, U5.8, U22.14, U21.5. All are low-current logic.

### m2. V12_FAN2 has a single-barrel layer change that the gate counts as three
- Path L3.2 → J15.2 (`v3path.py V12_FAN2 L3.2 J15.2 v`): F.Cu → vias (145.7, 52.5) and (146.6, 52.5) → 1.4 mm of
  B.Cu → **one** via at (145.70, 51.10) → F.Cu. The fan current returns to F.Cu through that single barrel.
- `power_vias` groups vias within 1.8 mm into one "site", so it reports this as a three-barrel site although the
  third barrel is in series with the other two.
- 0.67 A is under the gate's 1 A threshold, so nothing fails. On the nets above 1 A (V_BLOWER, V15_BLW) I found no
  single-barrel bridge, so the same flaw hides nothing there on this board.
- Fix: count barrels per layer change by connectivity, not by distance. Drop the 1.4 mm B.Cu hop at the next route.

### m3. V_BLOWER is 0.8 mm for a 2.70 A maximum
- Routed length L2.2 → J10.1 is 49 mm, all 0.8 mm on F.Cu/B.Cu, three barrels at each layer change (`power.py`).
- IPC-2221 external, 1 oz: 2.0 A for 10 K (LAYOUT.md's basis), about 19 K at the 2.70 A that `check_layout.py`
  itself uses. Resistance about 30 mΩ, 81 mV and 0.22 W at 2.70 A.
- Acceptable if 2.70 A is a start-up figure. LAYOUT.md still says "≥ 1.5 A". Widen to 1.2 mm where the route is free.

### m4. Pan Rref is not Kelvin-connected
- `kelvin.py`: U30.4/5 (BIAS, REFIN+) to R39.1 is 32.6 mm of 0.15 mm track with four vias, 147 mΩ. U30.6/7 (REFIN−,
  ISENSOR) to R39.2 is 13.8 mm on In2, 105 mΩ. Both carry the bias current and are inside the reference
  measurement, so Rref reads 430 Ω + 0.25 Ω.
- That is +0.059 %, about 0.3 K at 250 °C on a Pt100, comparable to R39's 0.1 % tolerance. The copper's drift over
  40 K adds about 0.05 K. Calibratable; not a functional fault.
- The same net (`p1`) also runs 194 mm (144 mm of it on In2) to reach R76, 32 mm away. It is a low-impedance node
  and I found only 6 mm of broadside overlap with an In3 net (`broadside.py`).
- Food channel (4.3 kΩ Rref): 196 + 38 mΩ, negligible.
- Fix at the next placement: R39 beside U30 pins 4 to 7, sense taps taken at R39's pads.

### m5. The module's EN capacitor is 48 mm from the EN pin
- C91 (1 µF, MCU_EN) is at (200.0, 92.5), beside J11. U4.3 is at (199.25, 44.23). R109 (10 k pull-up) is 7.6 mm from
  the pin. MCU_EN is 65 mm long with five vias.
- LAYOUT.md says the EN RC is "at its pads". The delay still works; the pin itself has no local filtering against
  coupled edges. Move C91 to the pin when placement is next opened.

### m6. Feedback and soft-start routing at the bucks
- U51 `fb`: 23.7 mm, four vias; 6.1 mm of it on B.Cu directly under the SW pour and L3 (In1 and In4 ground planes
  between). R153 (bottom resistor) is 6 mm from the pin.
- U2 `ss_12`: 9.7 mm on F.Cu, 5.0 mm of it under L2's body (accepted before as m12).
- U1 and U2 `fb`: 5.5 and 11.2 mm on F.Cu, no vias, clear of SW copper.
- Hot loops: each buck's input capacitors sit on the VIN pour 0.25 mm from the VIN pin; the GND pin touches the
  F.Cu ground pour and has two vias within 1.9 mm. In1/In4 coverage under each buck is 92 to 97 %.
- No change needed for a first build.

### m7. Long outer-layer ground islands tied down by one via
`planes.py`: F.Cu has 70 ground islands beside the main pour, B.Cu 20. Several are long and held by a single via:
- F.Cu 237 mm², kx 89.5–172.2 × ky 62.8–69.4 (83 mm long), 1 via;
- F.Cu 99 mm², kx 49.6–89.2 × ky 47.4–52.5, 1 via; F.Cu 57 mm², kx 36.3–64.1 × ky 40.9–45.0, 1 via;
- B.Cu 41 mm², kx 194.2–196.8 × ky 62.8–86.7 (24 mm long, beside the module), 1 via; B.Cu 30 mm², 1 via.

The `gnd_stitch` gate measures via density over the board, not vias per island. Each island lies 0.1 mm over a
solid plane, so the practical effect is small. Stitch both ends of any island over 15 mm, or drop islands with
fewer than two vias.

### m8. Slots in the ground planes
- `slots.py`: outside the six Ø8 keep-outs, In1 has 20 openings of 3 mm or more (largest
  5.0 mm at (179.6–184.6, 61.6–64.0)); In4 has 30 (largest 9.0 mm around J12's three pins, (178.6–187.7, 21.2–26.2)).
- The three-via power companion clusters each cut a 3.7 to 4.8 mm slot in both planes under their own track.
- The signals that cross them are slow (I2C, chip selects, RIM_SENSE, FAN_TACH). No action for this build.

### m9. U2 thermal margin at 2.70 A is not established
- U2's VIN and SW pins join their pours through 0.30 mm × 0.25 mm necks (pad width); the GND pin touches the F.Cu
  pour and has two vias. That is reasonable for SOT-583.
- My estimate is about 0.8 W in U2 at 12 V / 2.70 A. I did not read the TPS62933 datasheet for Rds(on) or θJA, so
  the junction temperature is **not established**.
- Add a bench step: run the blower output at its maximum current in a warm enclosure and read U2's case temperature.

### m10. Bring-up access
- The board has no test points, and every via is capped and under mask, so rails can only be probed on component
  pads and connector pins. Suggested points: v3v3 at J7.2 or C8.1; v15_selv at C1.1; V15_BLW at J13.1; V_BLOWER at
  J10.1; V12_FAN2 at J15.2; V5_UI at J7.1.
- J11 (TC2050-IDC-NL land at (196.0, 91.0), rot 90) is correct for a first flash: v3v3, EN, GPIO0, UART0_TX,
  USB D−/D+ and two grounds are routed (USB 37 and 40 mm on F/B). Pads carry no paste. Pins 9 and 10 are
  unconnected; there is no UART RX on the header (module pin 36 is UI_MISO), so flashing is over USB only.
- J11's front alignment hole is 0.69 mm (hole wall) from the board edge. Its courtyard overhangs the edge by
  0.38 mm, which is harmless.

### m11. Leftovers and stale text
- One dangling v3v3 stub on B.Cu, 2.4 mm, ending at (198.3, 38.4). No function, no hazard (DRC `track_dangling`).
- LAYOUT.md is out of date in places a builder would rely on:
  - "v15 runs to it from J4.1": J4.1 is `bias_good_j4`. The board's only 15 V input is J13, through D9.
  - "v15_selv … on 0.8 mm outer tracks": 76.5 mm of the D9 → U1 path is 0.25 mm (`v3path.py v15_selv D9.1 U1.3 v`),
    as the `power_paths` gate allows for 0.33 A.
  - "284 parts": the CPL has 342 placements.
- J9 is the only header at rot 180, so its pin 1 is at the +X end while J3's is at the −X end. Intended (DECISIONS
  C53); the harness drawing must say so.

### m12. BOM stock
18 of 96 BOM lines carry no stock reading (among them MAX31865AAP+T, EMC2301, SWRB1205S-100MT, UCD1E101MCL6GS, SS14,
PTFR0805B430RN9). Five read lines are thin: TPS3703A4330DSERQ1 18, AD8436ARQZ-R7 106, 74HC30PW 144, TLV9031DBVR 192,
MCP3202 197. fab-notes says "stock 0: none", which is only true of the lines that were read.

## Checked and found fine

| Area | What I did | Result |
|---|---|---|
| DRC | Reran `kicad-cli pcb drc` on a copy, with and without zone refill, with schematic parity | 0 errors, 0 unconnected, parity 0; 27 warnings, the same set LAYOUT.md lists. Fills are current |
| Rule settings | Read severities and limits in `controller.kicad_pro` / `.kicad_dru` | No electrical check is set to ignore. Clearance 0.15, edge 0.5, hole-to-hole 0.5, hole clearance 0.25 |
| Connectivity | `conn.py`: every net rebuilt from pads, tracks, vias and fills with shapely | 240 nets, each one piece. Pad nets equal the frozen netlist: 0 differences |
| Grazing contacts | `weak.py`: does any net depend on an overlap narrower than 0.10 mm | None |
| Gerbers | Re-exported all 13 layers and both drill files from the board | Identical to `fab/gerbers` except the creation timestamp |
| BOM | `cpl.py`: fab BOM against `frozen/default.csv` and the board | 342 designators, MPN and footprint agree on every line; only J11 and the three fiducials are board-only |
| CPL, SMD | `cplfit.py`: JLC pad records rotated by the CPL rotation, matched pad number to pad number | 333 lines fit; none needs a different rotation (R32 has no record; it is a two-pad resistor) |
| Polarised parts | C1, C9 (+ on pad 1, 15 V nets), D9 (cathode to v15_selv), 9 ESD diodes, D8, D10–D13, Q1, Q2 | Pad nets are right for the standard pinouts (from memory, not datasheets) |
| Footprints | Board pads against the project library copies, all 346 | Only U20 differs (the intended 0.28 mm pads) |
| Holes | `holes.py`: 1390 holes | Closest wall to wall 0.500 mm; none closer than 0.69 mm to the edge |
| Mounting holes | Six Ø4.0 in Edge.Cuts at the R31 positions | Nearest copper 4.00 mm from each centre on all layers; nearest courtyard 4.08 mm |
| Edges | Copper and pads to the outline | Copper 0.50 mm minimum; J4, J11 and J13 courtyards overhang by design |
| NPTH | J4 pegs (Ø3.0) and J11 (Ø0.99) | 0.25 mm to copper |
| Thermal reliefs | `spokes.py` on every plane-connected THT pad | 4 spokes on each layer, except J7's ground pins on F.Cu (2 to 3) and J4.3 on In2 (2). J13.1: four 0.6 mm spokes |
| V15_BLW feed | Pour width from the J13 pour to C9, C13, C14, C15 | Continuous copper ≥ 1.7 mm |
| Power vias | Bridge search on V_BLOWER, V15_BLW, v15_selv | No single-barrel layer change in a load path |
| Ground planes | In1, In4 | One main polygon each (two sub-mm² webs between connector pins); 14 120 and 13 990 mm² of 15 656 |
| RTD analog | Layers, vias, reference plane, In3 overlap, distance to SW copper | F.Cu/In2 only; sense and force nets have no parallel In3 run except rtd_sense_p_ext over UI_SCK for 7.9 mm, which is behind 220 nF |
| J4 footprint | Peg and row geometry | Pegs 16.70 mm apart, 4.32 mm ahead of row 1, rows 3.00 mm apart, mating face 0.515 mm inside the left edge |
| J11 | Pads, alignment holes, nets | See m10 |

## Not established

- Any connector against its manufacturer drawing (JST, Molex). See B1.
- IC pinouts against datasheets. I compared the netlist's pin nets with pinouts I know (MAX31865 SSOP, TPS62933,
  ESP32-S3-WROOM-1, EMC2301, TPS3823, REF20xx, SRV05-4, LM4040, TLV760) and saw no conflict, but I read no datasheet.
- JLC's stack-up figures, six-layer rules and via-fill terms: taken from LAYOUT.md, not re-read.
- Thermal behaviour of U2 at full load (m9).
- Firmware pin use and ORDER.md, both out of scope.

## Scripts

All in `build/review-s11/_review_scratch/`:
`dump.py` (board → `board.json`), `net.py`, `lib.py`, `conn.py`, `weak.py`, `power.py`, `v3path.py`, `mincut.py`,
`v3islands.py`, `planes.py`, `slots.py`, `holes.py`, `edges.py`, `spokes.py`, `necks.py`, `viainpad.py`, `rtd.py`,
`broadside.py`, `kelvin.py`, `cpl.py`, `cplfit.py`, `render.py` (the `r_*.png` crops), `jlcfp/fetch.py`,
`jlcfp/chir.py`; DRC reports in `drc/`.
Three measurements were run inline and have no saved script: the board-pads-against-library comparison (pcbnew
`FootprintLoad`), the Gerber re-export diff (kicad-cli, output deleted to save disk), and the buck fb/ss overlap
lengths in m6.
The JLC footprint records in `jlcfp/*.txt` are from the JLCEDA/EasyEDA official library (https://easyeda.com,
https://lceda.cn).
