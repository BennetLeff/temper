# Rev G independent layout review

Reviewer: independent PCB review (Fable subagent), 2026-11-09.
Scope: the frozen export in `build/rev-g-review/` only. Nothing outside it was read or trusted; every
claim below was re-derived from the files named. Work products (board dumps, scripts, DRC/ERC JSON,
renders) are under `build/rev-g-review/work/`.

Coordinates are KiCad board coordinates in mm (origin top-left of the sheet; board outline x 50..150,
y 45..155; the BNC row is at y = 51, the front edge at y = 45).

## Verdict

No BLOCKER. Two MAJOR layout items in the new band, both fixable in minutes without moving parts:
the TVS ground returns (a single 0.2 mm track to the BNC shell pin, no plane via) and the B.Cu GND pour
inside the 3.5 mm standoff radius of the two rear mounting holes (a Rev F carry-over the intent asks to
have flagged). Everything structural checks out: the board netlist equals both design.json and the
schematic netlist node for node, every protection part is on the intended nets with the datasheet pin
functions, the firmware pin map and jackguard constants agree with the resistors, the three new land
patterns match their datasheets, DRC/ERC are clean apart from library-path warnings, JLC's rules are
met with my own geometry checks, and the 10 mm move of the Rev F lower board left no stale or broken
copper. Fix the two MAJORs (and decide the MINORs), re-export, and it is orderable.

## Findings, ranked

### MAJOR-1 — TVS ground return is one 0.2 mm track to the BNC shell pin, no via to the GND plane

- Where: D21 pad 2 (69.2, 58.2), D22 pad 2 (91.2, 58.2), D23 pad 2 (113.2, 58.2), D24 pad 2
  (135.2, 58.2); nets GND. Tracks F.Cu 0.2 mm: pad 2 -> (x, 56.8) -> BNC shell pad 2 at (x+1.8, 55.0),
  about 3.9 mm per jack.
- Evidence: `work/analyze.out` "GND return" section and the trace walk in the session log. The
  nearest GND via to each TVS GND pad is 8.9-11.0 mm away (D22: (84.775, 64.35); D21/D24: 10.8 mm).
  There is no GND copper on F.Cu, B.Cu or In2 in the band: the rule area "pour keep-out 1 (analog
  core / band)" covers y 45..114 on B.Cu and In2 (`work/zones_silk.py` output), so In1 and the
  shell pins are the only ground. The shell pin reaches In1 through four 0.3 mm thermal spokes
  (In1 zone: spoke 0.3, gap 0.25). The TVS GND pad itself has no plane connection.
- Why it matters: the intent says "the TVS-to-GND return should be short and direct". Short, yes
  (3.9 mm); direct, no: a 0.2 mm minimum-width track with a 45-degree jog, then a PTH barrel and
  thermal spokes. For an IEC 61000-4-2 contact discharge (30 A in ~0.8 ns) the return loop of
  roughly 2-3 nH adds on the order of 60-100 V of L di/dt above the H4V5HD3B clamp at the JK_x node
  for the first nanosecond. The TLP172AM behind it is rated V_OFF = 60 V (datasheet p. 3), so the
  overshoot, not the clamp level, sets the margin for the open switch. The 0.2 mm track survives the
  pulse thermally (adiabatic fusing current at 20 us is ~450 A); the problem is inductance and a
  single point of failure.
- Fix: widen the pad-2 return to >= 0.5 mm, and add one or two 0.3/0.6 GND vias right against pad 2
  (In1 is 0.2 mm below F.Cu and continuous there), while keeping the link to the shell pad. The
  same applies to all four TVS. No part moves; there is free F.Cu around each pad 2.

### MAJOR-2 — B.Cu GND pour inside the 3.5 mm standoff radius of the two rear mounting holes

- Where: H3 (54, 151) and H4 (146, 151), M3 NPTH 3.2 mm. B.Cu GND fill edge at 1.80 mm from each
  hole centre (`work/zones_silk.py`: "GND zone B.Cu: min distance of fill edge to hole (54,151) =
  1.80 mm", same for (146,151)). The In1/In2 fills are also at 1.80 mm but are internal. The two
  front holes H1/H2 have no B.Cu pour (keep-out) and no B.Cu copper inside 3.5 mm except the JK_HPOT
  track at exactly 3.50 mm from (146, 54).
- Intent: "keep B.Cu copper >= 3.5 mm from hole centres for the standoff, or flag it". Rev F had the
  same 1.85 mm (`work/revf_holes.py`), so this is a carry-over, not a regression. It is GND copper
  under solder mask, so a metal standoff that cuts the mask only grounds the standoff; a 5.5-6 mm
  hex standoff sits on mask over GND.
- Fix: a 3.5 mm-radius B.Cu copper keep-out (rule area, copper pour only) around H3 and H4, or an
  explicit decision in DECISIONS that GND under the standoffs is accepted. Also note the 5V B.Cu track
  at 3.3 mm from (54, 151) and the GND via at 3.3 mm from (146, 151) (`work/analyze.out`), both inside
  the radius by 0.2 mm.

### MINOR-1 — JK_HPOT runs 51 mm on B.Cu along y = 53.0, through the BNC row, 1.0 mm from the LPOT and LCUR centre pins

- Where: B.Cu 0.2 mm, J7 pin 5 (89, 51) -> (91, 53) -> (142, 53) -> (142.4, 53.4) -> (142.4, 71.81)
  -> via (142.78, 72.19) -> K4 pad 4 (NO1). Clearance to J8 pin 5 (JK_LPOT, (111, 51), 1.8 mm pad)
  and J9 pin 5 (JK_LCUR, (133, 51)) is between 1.0 and 1.5 mm, to the shell pads 0.8-1.0 mm
  (`work/k4.py`).
- Why: this is a new connection (K4 pins 3/4 were unused in Rev F). HPOT is the driven voltage and
  LCUR is the TIA current input, so coupling capacitance here injects an error current directly into
  the measurement. The geometry is a fraction of a pF (0.2 mm track, 1 mm from a barrel, ~2 mm
  overlap), so tens of nA/V at 100 kHz, fixed and removable by open compensation, but it is the one
  new trace that runs beside every other jack's centre pin. It also lies under the hand-fitted
  connector bodies, which is fine for assembly.
- Fix (optional): route it in the band instead, e.g. B.Cu at y ~ 58-59 beside the JK_HCUR run
  (y = 56.9), or on In2 under the In1 plane, and keep >= 2 mm from the other centre pins.

### MINOR-2 — Series resistors are thick film (CRCW...HP), intent says thin film

- Where: R122, R125 = CRCW080510R0FKEAHP (C844598); R123, R124 = CRCW0603100RFKEAHP (C844725)
  (`bom-jlcpcb.csv`, `bom-complete.csv`, `cad/design.json`).
- Evidence: intent README: "10 ohm 0805 thin film ... 100 ohm 0603 thin film". Vishay Draloric
  CRCW-HP is the thick-film "high power" series (vendor naming; the datasheet is not in the export).
  The protect-sheet note in the schematic itself says "CRCW0805-HP / CRCW0603-HP", so the schematic
  and BOM agree with each other and disagree with the README.
- Impact: at 10 and 100 ohm the voltage coefficient and excess noise of thick film are irrelevant,
  and thick-film pulse withstand is better than thin film for the surge role. This is a documentation
  mismatch, not a circuit problem. Fix: correct the README (or swap to a thin-film MPN if the choice
  was deliberate for a reason the README does not state).

### MINOR-3 — CPL rotations for the four TLP172AM cannot be verified from the export

- Where: `cpl-jlcpcb.csv`: U18 90, U19 270, U20 270, U21 90 (board rotations 180/0/0/180, i.e. a
  -90 degree correction); D28 and Q7 0 (board 180, +180 correction); D21-D27 0/180 unchanged.
- Evidence: the corrections are consistent per package family and the SOT-23 +180 convention is the
  usual KiCad-to-JLC one, but the SO-4 (Toshiba 11-4M1S) orientation in JLC's library for C2152276 is
  not in the export, and Rev F was never built, so no convention here is bench-proven. The TVS are
  bidirectional, so their rotation is harmless; U18-U21 (anode/cathode vs drains) and D28/Q7 are the
  parts where a 180-degree error would be fatal to function.
- Fix: in JLC's placement preview (part of the order flow, not a vendor contact) confirm that U18-U21
  show pin 1 at the footprint's pin-1 mark (pad 1 is the -x, -y pad; the silk triangle sits beside
  it) and that Q7/D28 pin 1 matches. Nothing to change in the files unless the preview disagrees.

### NOTE-1 — H4V5HD3B is the "High Capacitance" family: 100 pF typ at 0 V on every jack

- `datasheets/h4v5hd3b.pdf` p. 1/2: "Bi-directional 4.5V High Capacitance ESD", Cj 100 pF typ
  (VR = 0 V, 1 MHz). It is the part the intent names, so this is by design; recorded because the
  README calls it only "a bidirectional TVS". The second-stage H3V3LD5B is 12.5 pF typ / 25 pF max.
  Shunt C on the CUR/POT jacks loads the source and is removed by open compensation; at LCUR/LPOT it
  sits at the virtual ground, so it carries little signal current.

### NOTE-2 — T-junctions on the new HPOT, LPOT, DUT_HI, DUT_LO and VRLY tracks

- (62.4, 62.87) DUT_HI; (122.6, 65.2) DUT_LO (stub to D28 pad 3); (87.475, 65.4) and (87.475, 67.2)
  HPOT (stubs to C119, D26); (116.3, 65.6) and (116.3, 67.4) LPOT (stubs to C120, D27); (100.0, 69.92)
  and (101.4, 69.92) VRLY. The intent lists "no T-junctions" as a craft rule. The whole board has 80
  T-junctions and Rev F also had exactly 80, including ones on HPOT/LPOT/DUT_LO/DUT_HI in the old
  band, so this is the existing standard, not a regression. The stubs are 0.6-1.4 mm long.

### NOTE-3 — Jack-row resistors sit 0.02-0.05 mm (courtyard to courtyard) from the hand-fitted BNC flanges

- R129 (141.5, 51.0) courtyard x 140.02..142.98 vs J9 courtyard 126..140 (14 mm wide rectangle);
  R126 (59.2, 53.0) courtyard x 58.45..59.95 vs J3 courtyard 60..74. No overlap (KiCad DRC and my
  polygon test agree), but check the real KYWE-295 flange width against the 14 mm courtyard before
  relying on it. R105/R106 between connectors have 3.9 mm on each side.

### NOTE-4 — Long In2 sense and LED runs behind the jacks

- JACK_LC: 174 mm on In2, from R129's via (143.5, 51) along y = 56.4 across the whole jack row
  (1.4 mm from the shell pins, 5.4 mm from the centre pins, under In1) then down x = 51.6 to
  (66.2, 119.6). JACK_HC: x = 53.0 beside it. STATUS (In2, x = 51.0) runs 0.4 mm edge-to-edge beside
  JACK_LC for 60 mm. Both senses are 107 kohm nodes with 100 nF (C121/C122 at x = 55.4, the jack
  end, not the MCU pin as jackguard.h's comment says), so the coupled charge from a STATUS edge is
  ~0.1 mV. ISO_SINK (64 mm, y = 59.4) and ISO_S2M (37 mm, y = 64.4) carry 7-8 mA DC LED current on
  In2 under the band; they switch only when the guard opens/closes. None of this affects the
  measurement, listed so nobody is surprised by the routing when they open the board.

### NOTE-5 — Document hygiene

- Schematic title blocks still read "Rev: E", date 2026-10-20 (all sheets, including protect).
  The silkscreen says "TEMPER LCR REV G" and the User.Drawings fab notes say Rev G.
- `gerbers/temper-lcr-job.gbrjob`: Revision "rev?", Finish "None" while the fab notes say ENIG.
  Metadata only; JLC takes the finish from the order form.
- `cad/design.json` K4 pinout: COM1/NO1 (pins 3/4) are used for the first time; the intent gives the
  same pin numbers and Rev F used pins 7/8 the same way, so this is consistent, but the TQ2SA
  datasheet is not in the export and was not re-checked.

## What was checked and found fine

Netlist and intent
- Board pad nets vs `cad/design.json`: 253 parts, 0 mismatches; placement and rotation of every part
  equal design.json `pcb` to 0.01 mm. Board-only refs are TP1-21, FID1-3, H1-4.
- Board vs schematic: `kicad-cli sch export netlist` parsed and compared node by node: 747 nodes,
  0 mismatches; kicad-cli DRC schematic parity: 0 issues.
- TLP172AM pin functions (datasheet p. 2: 1 anode, 3 cathode, 4/6 drain): U18 1=ISO_S1M 3=ISO_SINK
  4=JK_HCUR 6=ISO_HCUR; U19 1=ISO_S1 3=ISO_S1M 6=JK_HPOT 4=ISO_HPOT; U20 1=ISO_S2 3=ISO_S2M 6=JK_LPOT
  4=ISO_LPOT; U21 1=ISO_S2M 3=ISO_SINK 4=JK_LCUR 6=ISO_LCUR. Both drains are interchangeable.
- LED strings: VRLY -> R132 300R -> U19 (HPOT) anode->cathode -> U18 (HCUR) -> ISO_SINK;
  VRLY -> R133 300R -> U20 (LPOT) -> U21 (LCUR) -> ISO_SINK. Matches "HPOT then HCUR, LPOT then
  LCUR". I_F = (5 V - 2 x 1.27..1.4 V) / 300 R = 7.3-8.2 mA, inside the TLP172AM recommended 5-25 mA.
- Q7 AO3400A: pin 1 G = ISO_G, 2 S = GND, 3 D = ISO_SINK; R134 100R ISO_DRIVE-ISO_G, R135 100k
  ISO_G-GND. U1 pin 18 = GPIO15 = ISO_DRIVE (pins.h PIN_ISO_DRIVE 15).
- BAV99 (Nexperia pinning table: 1 A1, 2 K2, 3 K1/A2): pins 1, 2 GND, pin 3 DUT_LO = antiparallel
  pair DUT_LO-GND. H4V5HD3B/H3V3LD5B are bidirectional; polarity immaterial.
- Senses: R126 1.5M JK_HCUR-JACK_HC, R127 240k JACK_HC-3V3, R128 240k JACK_HC-GND, C121 100n;
  JACK_HC on U1 pin 40 = GPIO28 (ADC2). R129/R130/R131/C122 the same for JACK_LC on pin 41 = GPIO29.
  jackguard.h: R_TOP*G = 1 + 1.5M/240k + 1.5M/240k = 13.5 (JG_RTOP_G_PPM 13500000) and
  R_TOP/R_BIAS = 6.25 (JG_RTOP_RBIAS_PPM 6250000) are exactly right for these values; the ADC span
  covers jack voltages -20.6..+24 V.
- R105/R106 1k on the jack side, K4 3/8 = JK_HCUR, 4 = JK_HPOT, 7 = REF_A, R107 1k REF_A-JK_LCUR, J6
  removed, U1 pins 40/41 no longer UART: all as intended. The remaining changed pins between Rev F
  and Rev G design.json are exactly J3/J7/J8/J9 pin 5, K4, R105/R106/R107 and U1 18/40/41.

Band placement and routing
- TVS inline, not on stubs: the JK_x track runs from the BNC centre pin straight through D2x pad 1
  (7.2 mm) and on to the photoMOS drain pad (2.1 mm), entering every pad on its axis.
- Second stage at the Rev F node: D25 pad 1 is 1.4 mm from R122 pad 2 on DUT_HI; D26 and C119 are
  inline on HPOT 6.7 mm before U6 pin 5; D27 and C120 inline on LPOT 10 mm before U7 pin 5; D28 pad 3
  is 1.4 mm off the DUT_LO trunk. Second-stage GND pads each have a GND via at 0.9-1.5 mm.
- DUT_LO: F.Cu only, 42 mm, no vias, no other-net copper within 0.6 mm on F.Cu, solid In1 under it,
  no B.Cu/In2 copper under it except the JK_LCUR B.Cu segment at x = 130.5 (different layer, plane
  between). HPOT and LPOT: F.Cu only, no vias; nearest foreign copper is the adjacent OPA2810 pin.
- Jack-side nets vs others: minimum clearance 0.20 mm (JK_HCUR B.Cu to the RLY_RST via at
  (130.9, 70.92)), otherwise >= 0.3 mm; JK_HPOT via (142.78, 72.19) is 0.4-0.5 mm from K4 pad 5.
  Input-to-output distance across each TLP172AM is the 6.3 mm pad-row pitch.
- JK_HCUR's 63 mm B.Cu run along y = 56.9 to K4 is the Rev F DUT_HI route, now on the jack side of
  the switch; 0.8 mm from the shell pads, no centre-pin proximity.

Manufacturability
- Toshiba_11-4M1S vs datasheet p. 10 (7.0 +/- 0.4 lead span, 2.54 pitch, 0.4 lead, 0.5 min foot):
  pads 1.8 x 0.6 at +/-3.15 / +/-1.27 cover the foot with 0.55 toe and 0.75 heel; pad 1 at the
  chamfered/triangle corner, 6 opposite 1, 4 opposite 3, as on the package drawing.
- D_SOD-323_HJC vs HJC "Suggested Pad Layout": J 0.8, K 1.4, M 0.8 -> 0.8 x 0.8 pads at +/-1.1,
  exact. D_SOD-523 vs HJC: X 0.55-0.65, Y 0.65-0.75, Z 1.37-1.47 -> 0.6 x 0.7 at +/-0.7, exact.
  SOT-23 (D28, Q7) is the KiCad standard pattern, within the Nexperia reflow footprint.
- Pad-to-silk: 0 pairs under 0.15 mm (JLC) board-wide; courtyard overlaps: none.
- CPL: Mid X/Y = footprint anchor, lower-left origin, y flipped; coordinates verified for all new
  parts. BNCs correctly absent (hand fit). BOM LCSC numbers present for every new part.
- Via-in-pad: only the exposed-pad thermal vias of U1/U11/U12/U13/U14, as the fab note states;
  no via touches any other SMD land (polygon test, both revs).
- JLC rules (own geometry checks, `work/analyze.py`): hole-to-hole 0 below 0.45 (pad) / 0.2 (via);
  PTH hole to foreign track >= 0.28: 0 below; via hole to foreign track >= 0.2: 0 below; copper to
  edge: board rule 0.3 mm (JLC 0.2) and DRC clean; all vias 0.30 drill with 0.45/0.55/0.60 pads
  (ring >= 0.075); tracks >= 0.15 mm. Drill files: 460 vias + 4 x 1.0 + 4 x 1.2 + 16 x 1.4 PTH, J1
  slots as routed G00/G01 paths, 4 x 3.2 + 2 x 0.6 NPTH; matches the fab-note summary.
- Mounting holes H1-H4 are NPTH 3.2 mm (no ring); the front two have no B.Cu copper inside 3.5 mm
  except the JK_HPOT track at exactly 3.50 mm from (146, 54).

Rev F regressions
- Every footprint common to both revs moved by exactly (0, +10) if its Rev F y >= 57, else (0, 0);
  only R105 and R106 moved elsewhere (jack-side rewire), J6 removed.
- Six Rev F tracks straddled y = 57 (HPOT, LPOT, DUT_HI x2, DUT_LO, STATUS); all were rerouted, none
  left as stale copper. Rev F tracks absent from Rev G after the shift are only on the rewired nets
  plus small reroutes of GND/3V3 near J1/U1 and the K1 VRLY feed, all still connected (DRC: 0
  unconnected). Zones: the three GND pours and all rule areas are present with the same settings.

DRC / ERC (`work/drc.json`, `work/erc.json`, kicad-cli 10.0.4, all severities, schematic parity)
- DRC: 199 `lib_footprint_issues` warnings (footprint libraries not on the path in the frozen export),
  0 other violations, 0 unconnected, 0 parity. Project rule severities: all "error", none ignored.
- ERC: 265 `lib_symbol_issues` + 257 `footprint_link_issues` warnings (same library-path cause),
  nothing else.
