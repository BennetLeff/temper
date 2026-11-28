# Controller PCB layout (L3 + stage 16 + L4: enclosure R33/R41, R36 rim NTC, blower supply from PS3, thermal trip ladder, block-validator fixes)

This is the layout of the integrated SELV controller: 284 parts, 6 layers (C53), 206 × 76 mm, placed and routed by scripts from `frozen/default.net`, with a JLCPCB fab package. Nothing was drawn by hand in the KiCad GUI.

**Status: DRC-clean candidate, not released** (ordering is the owner's decision). KiCad DRC: 0 errors, 0 unconnected, schematic parity 0; JLC DFM PASS; all 21 enclosure/layout checks PASS; gerbv fab review PASS. Not fabricated. Every number below comes from a file in `evidence/` that `python3 layout/make.py` regenerates: `drc.json`, `jlc-dfm.json`, `layout-check.json`, `fab-review.json`, `silk-designators.json`, `verify.json`; the routing-robustness proof is `evidence/convergence.json` (`layout/convergence.py`).

**Enclosure revision:** R31 outline, holes and connectors (`output/temper-manufacturing-r31/design/r31/CONTROLLER-SPEC.md`, "R31" section, with R30's mounting and heights) plus the **R33 controller delta** (`output/temper-manufacturing-r33/design/r33/DECISIONS.md` §3; the R35 HANDOFF restates it unchanged):
- J5, J6 and J8 are deleted; one 12-way JST B12B-XH-A **J7** at X29.8–62.2, Y57.1–62.9 carries the UI bus (DECISIONS C26);
- the module is the **ESP32-S3-WROOM-1U-N8** at X141–159, Y50–69.5, with a U.FL to an off-board chip antenna, so there is no antenna keep-out.

**R36 / R38:** the rim NTC on the sensor cartridge adds an ADC1 channel and **J12** (B2B-XH-A) at (126, 86) (DECISIONS C27, C31). The enclosure session (R38) accepted J12 at (126, 86) and the U.FL at (156, 67).

**C1 change set (DECISIONS C37–C41, 2026-10-15, branch controller-c1-crs):** 37 parts added and the 0 Ω OVP tie removed (248 → 284); every existing explicit pose is kept except u_buf3 (1.2 mm left) and c_rtd_input (now a 1206, 1.1 mm right). C45 (CR-8) adds r_hs_adc_bot at the module's HS_ADC pad (285 parts).
- **RTD protection and filter (C37):** the J3 TVS and 220 nF take the strip between the MAX31865 and J3, directly in front of their pins. The J3.4 pair sits right of J3 behind the Ø8 hole keep-out, and c_j_fp left of the strip. The two-stage filter sits in two rows right of the MAX31865, in front of the keep-out: R2n, R2p, R1n, R1p in the rear row (Y 74.4), the 1206 C1 in front of R1, the 499 k pull-ups at the ends of the front row. c_cm_n is beside pin 11. The new sense nodes (`rtd_sense_*_ext`, `rtd_sense_*_mid`) are RTD analog nets (F.Cu / In2.Cu, return vias). Pad distances to J3: `layout-check.json` `rtd_j3_protection`.
- **Rim trip and runaway OR (C38):** U40 / U41 at (116.5, 56.5) / (116.5, 61.5), in the free column between the keep-apart band and the RTD block.
- **Capacitive-mode detector (C39, C44):** U42–U46 at the front edge right of the X65 hole, X 76–90 / Y 21–27, south of the MCU-to-J4 signal bus, with the PWM series resistors R1 / R2 beside the inverters. The board text moved from X98 to X115 to make room. A first placement inside the bus (X 96–110 / Y 36–42) routed once but left one pair open in the next run (C44).
- **Runaway divider and RTD pull-ups (C44):** r_runaway_top / r_runaway_bot, rtd_pan.r_rail_ok_pullup, r_fault_pullup, r_high_bottom, r_window_ok_pulldown, r_avdd_top and r_avdd_bottom are pinned at their C36 poses. With U41 in that column the auto-placer had moved r_runaway_top to 7.8 mm from L2 (partition gate ≥ 10 mm) and r_runaway_bot to the rear edge.
- **J12 (C40):** 3-way B3B-XH-A at the same centre. **J11 (C41):** TC2050-IDC-NL land at (138, 19); its symbol and footprint are excluded from the BOM and CPL.

**L3 schematic changes laid out here** (DECISIONS C28–C32):
- **Blower supply (C28):** the 12 V fan buck became an adjustable 5.03–12.40 V supply (≥ 1.5 A) on **J10** (B3B-XH-A, fixed at (139, 86)): pin 1 V_BLOWER, 2 GND, 3 FG (tach). Speed is a filtered PWM from GPIO46 injected into the feedback node (duty 0 = full speed); on/off is expander P15 (FAN_OFF). The inductor is now a Sunlord SWRB1205S 10 µH (12.5 mm, 6.0 mm tall; project footprint `layout/footprints/Temper_Controller.pretty/L_Sunlord_SWRB1205S.kicad_mod`).
- **NTC filters (C29):** 10 k / 100 nF (159 Hz) on the heatsink, coil and rim NTC inputs, ahead of the buffers. The RTD front end is unchanged (byte-locked library; change request in C29).
- **Rim NTC (C31):** 100 k / 300 °C glass NTC with a 1.00 kΩ 0.1 % pull-up.
- **Thermal trip ladder (C32):** heatsink comparator 11.5 k / 8.06 k (trip 101.4 °C nominal), coil comparator 90.9 k / 7.06 k / 140 k at 0.1 % with a 104GT-2 class coil NTC (trip 175.7 °C nominal). Evidence: `docs/evidence/2026-10-12-thermal-trip-ladder-l3.md`.

**Stage 16 (DECISIONS C33, 2026-10-12):** the blower buck U2 now runs from a separate chassis-mounted SELV supply, PS3 (Mean Well IRM-60-15ST at world (−139, 95), enclosure R41).
- **J13** (JST B2P-VH, 2-pos, 3.96 mm, top entry) is at body centre (88, 85.65), flush with the edge, 0.35 mm from R41's approved (88, 86) at the rear edge.
  - Pin 1 V15_BLW, pin 2 return.
  - Its 16.5 mm mated height uses R41's local allowance, Z ≤ 54 within ±6 mm of (88, 86).
- U2's VIN, EN-divider top and input capacitors moved from v15_selv to V15_BLW, and a 100 µF bulk capacitor is added.
- PS3's return ties to selv_gnd at J13.2 only.
- A 20 k / 4.7 k BLW_PG divider feeds expander P16.

**L4 (DECISIONS C34, 2026-10-12): layout fixes from the block-validator re-run** (`evidence/block-validators/`, C30). Every remaining validator finding is a justified waiver in `evidence/block-validators/WAIVERS.md`.
- **Stack-up** sums to the 1.6 mm board (core entered as 1.0588 mm; C53's six-layer stack enters each core as 0.5708 mm).
- **Thermal-sense spacing:** the unit's 0.20 mm floor on every thermal-block net (net class Thermal) and between selv_gnd and v3v3 (custom rule, `pcb/controller.kicad_dru`).
- **RTD input filter:** `c_rtd_input` (C31) sits across the MAX31865's RTDIN+/RTDIN− end, about 2.1 mm from pins 10/11 (rule ≤ 3 mm).
- **RTD analog return:** the eight RTD analog nets run only on F.Cu / In2.Cu over the solid In1 ground plane, never over an In1 antipad, and change layer only within 2.5 mm of a ground via; 96 selv_gnd stitching vias (3 mm grid) cover the RTD region; In1's clearance is 0.20 mm. A local RTD_AVDD F.Cu pour serves the MAX31865 VDD pin and its bypass.

**All enclosure numbers live in one table, `layout/world.py`**; a new revision is an edit there plus a re-run. The L1 layout (R31) is in git history at `97c36e2a9`.

## Rebuild

From `zapote/controller` (KiCad 10.0.4 and its bundled Python; system Python 3 with numpy, scipy, shapely and Pillow; gerbv for the fab review; offline; no Rust or workspace build):

```sh
python3 layout/make.py             # place, plane fan-out, route, DRC, DFM, enclosure check, fab, fab review
python3 layout/make.py --no-route  # same, reusing pcb/controller-routed.kicad_pcb (routing is the slow step)
python3 tools/verify_controller.py # schematic verification
python3 layout/convergence.py --runs 3 --out <dir>  # routing-robustness proof: 3 full runs from a clean start
evidence/block-validators/run.sh <bin>              # interlock / thermal / RTD block validators (needs a zapote-harness build; README there)
```

| Script | Does |
|---|---|
| `layout/world.py` | **The parameter table:** outline, holes and keep-outs, connector centres, the J7 and module boxes, the U.FL position and clear radius, J4 body and mating side, heights, and the world ↔ KiCad transform |
| `layout/floorplan.py` | Region placement (ICs, power stages) and the anchor rules for passives. Keys are **atopile instance paths** (not designators), so a schematic edit that renumbers designators cannot silently move a group; `build_board.py` fails on a key that is not in the netlist |
| `layout/build_board.py` | Board from the netlist: stack-up, outline, holes and Ø8 keep-outs, placement (explicit + anchored passives, nothing within 3 mm of the U.FL), planes, buck pours, plane fan-out, silk text, project rules |
| `layout/fanout.py` | A via beside every SMD pad on `selv_gnd` / `v3v3` into its plane, keeping an escape lane for each neighbouring signal pin |
| `layout/build_schematic.py` | A netlist rendering (`pcb/controller.kicad_sch`) so KiCad's DRC can run schematic parity |
| `layout/route.py` | Routing driver: KiCad DRC gives the open pairs, `export_geom.py` dumps the copper, `gridroute.py` routes; up to three rounds. Then the **repair** step: for each pair still open it rips the unlocked copper within 3, then 5, then 8 mm of its ends and routes the stuck nets first. Then `cleanup.py`, more rounds if needed; the repair-and-cleanup cycle repeats up to three times. Finally the outer GND pours, the designators, and a last pass that deletes whatever KiCad's DRC still lists as dangling after the pours |
| `layout/plane_islands.py` | Turns KiCad's "zone to zone" unconnected reports (the In2 v3v3 pour cut into islands by In2 tracks) into routable pairs: the nearest v3v3 vias of two islands |
| `layout/cleanup.py` | Removes copper that partial rips leave. The graph pass treats each track piece as a hyperedge on everything its ends lie in, as KiCad does; it deletes pieces that only close a loop and peels dangling chains. A second pass deletes exactly what KiCad's DRC lists as via/track dangling. Plane and pour nets are left alone |
| `layout/export_geom.py`, `layout/gridroute.py` | Copper dump (KiCad Python) and the router: F.Cu/In2.Cu/B.Cu on a 0.1 mm raster (preferred directions F along X, B along Y), clearance maps per width, A* with through vias and no corner cutting, exact shapely checks on pad escapes and pulled-tight segments, transactional negotiated rip-up, and a final exact legalisation of every segment and via against all copper, keep-outs and holes. The interlock block's box is a keep-out for MCU nets |
| `layout/silk.py` | Designators on silk where they fit (1.0 mm), otherwise F.Fab only |
| `layout/jlc_dfm_check.py` | JLC 1 oz multilayer limits (adapted from `power-stage-120v/tools/jlc_dfm_check.py`) |
| `layout/check_layout.py` | Enclosure constraints and the layout rules of the brief → `evidence/layout-check.json`; part groups by atopile path |
| `layout/convergence.py` | N consecutive full `make.py` runs, each after moving `pcb/route/` away; writes `evidence/convergence.json` (per run: exit code, wall time, DRC counts and violation types) |
| `layout/fab.py`, `layout/review_fab.py` | Gerbers, drill, BOM/CPL, assembly drawing; independent gerbv review of the Gerbers |

**Router choice.** Freerouting 2.1.0 was tried on L1: its passes stalled for 10–16 min at a time, its CLI ignores the pass limit (`RouterSettings.stop_pass_no` is fixed at 999), and its best runs left 6–9 connections open. `gridroute.py` keeps the whole flow in this repository, with KiCad's DRC as the authority.

## Coordinates

World (appliance) mm, X right, Y rear, viewed from above. KiCad frame: **kx = X + 58, ky = 110 − Y** (`layout/world.py`). The board's rear-left corner, world (−38, 90), is KiCad (20, 20); the front-right corner, world (168, 14), is KiCad (226, 96). This is a translation plus the y-flip of KiCad's y-down screen; the top side stays on top (no mirror). Gerber Y = −ky, so world Y = 110 + Gerber Y. Every part's world pose is in `pcb/placement.json`.

## Stack-up: 6 layers, 1 oz outer (C53)

JLC JLC06161H-3313, 1.6 mm (jlcpcb.com/impedance, read 2026-11-26): F.Cu 1 oz (0.035) / 3313 prepreg 0.0994 (εr 4.1) / In1.Cu 0.5 oz (0.0152) / core 0.55 (εr 4.6) / In2.Cu 0.5 oz / 2116 prepreg 0.1088 (εr 4.16) / In3.Cu 0.5 oz / core 0.55 / In4.Cu 0.5 oz / 3313 prepreg 0.0994 / B.Cu 1 oz. JLC's figures sum to 1.5384 mm, 1.5584 mm with the masks, so the board file enters each core as 0.5708 mm and the stack-up sums to exactly 1.6000 mm (zapote `DRC.BOARD.STACKUP`). JLC's finished thickness is 1.6 mm ± 10 %, and nothing here depends on the core figures.

| Layer | Use |
|---|---|
| F.Cu | All parts; signals; buck VIN/SW pours; `selv_gnd` pour in the gaps |
| In1.Cu | Solid `selv_gnd` plane, cut only by the six Ø8 snap-in keep-outs and the via antipads (0.20 mm clearance, C34) |
| In2.Cu | `v3v3` pour (same cuts); also a routing layer, the pour refilling around its tracks. The RTD analog nets use F/In2 only. |
| In3.Cu | Signals (C53). No tracks over the two RTD stitch regions (`rtd1/2_in3_keepout` rule areas, vias allowed), so nothing crosses between the RTD analog copper and In4. |
| In4.Cu | Solid `selv_gnd` plane: B.Cu's reference (C53) |
| B.Cu | Signals; `selv_gnd` pour in the gaps |

**Finish and vias:** ENIG. JLC's capability page: FR-4 boards of 6 or more layers "do not support HASL". Vias are epoxy-filled and capped, JLC's default for 6+ layers and free per its via-covering article (updated 2026-11-10). The vias carry no mask opening, as before.

**Why six (C53):** C51's rule. The four-layer board (route 3) closed on 1 of 3 clean runs, and C51 set six layers as the step when four does not reach 2 of 3 (evidence/c53-four-layer/).

**Why planes first:** the board carries three sensitive analog front ends (the RTD MAX31865 and the ±1 µA thermal-sense nodes, the D-11 bus receiver into the ESP32 ADC, the AD8436 tank RMS) next to an ESP32 radio module, two 500 kHz bucks and two SPI buses. A continuous ground plane 0.1 mm under every F.Cu signal (and In4 under B.Cu) gives every return path a defined image, and the In2 3.3 V plane gives about 100 decoupling capacitors a one-via return each.

**Why 1 oz, and outer only for current:** the largest currents are the blower output (≥ 1.5 A on V_BLOWER, C28) and the v15_selv feed (D9, ≤ 1 A). Both run on 0.8 mm outer tracks, which IPC-2221's external-layer formula (I = 0.048·ΔT^0.44·A^0.725, A in mil²) puts at 2.0 A for a 10 K rise on 1 oz copper. The inner layers are 0.5 oz, where the internal formula gives about 0.6 A for the same track. So V_BLOWER, sw_12, v15_selv and V15_BLW are routed on F/B only (gridroute.py `OUTER_ONLY`), and `check_layout.py`'s `power_layers` gate fails any inner-layer track on them (C53).

**RF and impedance:** no RF line on the board. The WROOM-1U's U.FL is on the module and the antenna is off-board on coax (R33), and no net is impedance-controlled.

**One ground.** The schematic has one return net, `selv_gnd`, and no separate analog ground, so the board has one solid plane and the analog/digital partition is done by placement. A split would force every analog-to-ADC signal across a gap.

## Rules (JLC capability with margin)

JLC figures re-read 2026-10-09 from jlcpcb.com/capabilities/pcb-capabilities (multilayer, 1 oz): track/space 0.09/0.09 mm, PTH ring 0.15 mm minimum (0.20 recommended), via 0.15/0.25 mm, via hole-to-hole 0.2 mm, pad hole-to-hole 0.45 mm, NPTH ≥ 0.5 mm, copper to a routed edge ≥ 0.2 mm, silk text ≥ 1.0 mm.

| Rule | This board | Margin over JLC |
|---|---|---|
| Track | 0.15 mm signal, 0.3 mm v3v3 / plane stubs, 0.4 mm v15/SW (0.8 mm v15_selv, V_BLOWER and the blower SW node where routed, outer layers only, C53) | ≥ 1.7× |
| Clearance | 0.15 mm; **0.20 mm** for the thermal-sense block's nets (net class Thermal) and between selv_gnd and v3v3 (custom rule, `pcb/controller.kicad_dru`), C34 | 1.7× / 2.2× (JLC 0.09 mm) |
| Via | 0.6/0.3 mm | ring 0.15 mm = 3× JLC's via rule |
| PTH ring | ≥ 0.20 mm (gate) | JLC recommended |
| Hole to hole | 0.5 mm | 2.5× (vias) / 1.1× (pads) |
| Copper to edge | 0.5 mm | 2.5× |
| Thermal relief | planes and pours connect PTH pads with reliefs (0.3 mm gap, 0.4 mm spokes, at least 1 spoke resolved); SMD pads solid | — |

`layout/jlc_dfm_check.py` is the power board's gate with its limits moved from 2 oz to these 1 oz values, plus an NPTH check. One footprint change: U20 (SN74LVC1G74DCU, VSSOP-8, 0.5 mm pitch) gets 0.28 mm pads instead of the library's 0.35 mm, which leave only 0.15 mm between pads; TI's DCU land is 0.25–0.30 mm wide. The WROOM courtyard is the module body + 0.25 mm.

## Floorplan (R33 + L3)

```
 rear Y90 ┌──────────────────────────────────────────────────────────────────────────────────────────────┐
          │J9 M12  J2 sink  o(-26,74)  thermal-sense    J1 coil  o(75,86) blower buck J12 J10  J3 RTD        │
          │                 interlock U20-U25 + U9   trip glue  +5V LDO   (U2,L2)    RTD front end + U10 │
     ┌────┤                                         [  J7 UI bus  ]                ┌─────U.FL┐ o(164,80)│
  J4 │ -X │ D-11  ct_mon            ESD + 100R                                     │ WROOM-1U│          │
     │    │                                                          U8 expander   │  X141-159│          │
     └────┤ AD8436 MCP3202                                                         └─────────┘          │
          │ U37 PERMIT        3.3V buck (U1,L1)        TEMPER CONTROLLER / SELV        J11 dbg          │
 front Y14└──o──────────────────────────────────o(65,18)─────────────────────────────────────o(164,18)──┘
          X-38                                                                                     X168
```

- **Fixed by the enclosure** (checked by `check_layout.py`): the outline, the six Ø4.0 snap-in holes with Ø8 copper/part keep-outs, the connectors at their R31 centres, J7 on its R33 box, J4 in its body envelope at the left edge mating −X, and the WROOM-1U on its R33 box with its U.FL end at the rear.
- **J4 side (left):** J4.9/J4.10 (PERMIT, bus_fault) sit at the header's front end. The PERMIT gate U37 (latch AND RUN_EN, C23) and its 10 kΩ pull-down sit in front of J4, next to J4.9. The D-11 receiver (U5, LM4040, 0.1 % resistors) sits at J4.11/12, the ct_mon buffer U6 at J4.14, the PWM pull-downs and the ct_zc/line_zc 1 kΩ at J4. The tank-RMS converter (AD8436) and its MCP3202 use the front-left corner the R31 module occupied, next to the ct_mon buffer.
- **Interlock block** (U20 latch, U21 watchdog, U22 HC30, U23/U24 LVC14, U25 and their pull-ups/bypasses) is grouped behind the J4 analog parts, with the trip glue (U3 rail window, U11 SENSOR_LIVE, U12 RAIL_FAULT) to its right. The read-back buffer U9 sits just in front of the block (X22), so its outputs, the only interlock-to-MCU nets, leave toward the module without entering the block.
- **ESP32-S3-WROOM-1U** on the R33 box at the right; the EN RC, decoupling, ADC anti-kick RCs and the UI chip-select pull-ups at its pads; nothing within 3 mm of the U.FL. The expander U8 sits to its left, between it and the read-back buffer.
- **J7 UI bus:** the six 100 Ω series resistors and the two SRV05-4 arrays in front of the header; the +5 V LDO U16 and its droppers beside it.
- **3.3 V buck** (U1, L1) at the front (X 28…50); v15 runs to it from J4.1 and the v3v3 plane carries its output back to J4.3.
- **Thermal-sense block** between J2 (X−20) and J1 (X55) at the rear, with its buffer U7.
- **RTD front end** (MAX31865, REF2025, window comparators, TPS389001, Rref) between the module and J3, with the runaway comparator U10.
  - C34: the 1 nF differential filter C31 (`rtd_pan.c_rtd_input`) at (154.5, 76.5), rotated 90°, across the ADC's RTDIN+/RTDIN− end (pad to pin about 2.1 mm).
  - C34: selv_gnd stitching vias on a 3 mm grid over world X 115–167, Y 55–89 (not under the module; 96 on this board), so every RTD analog layer change has a ground via within 2.5 mm.
  - C34: a local RTD_AVDD pour on F.Cu over the MAX31865 VDD pin and its bypass (zone RTD_AVDD_F, added with the outer pours).
- **Blower buck** (U2, L2 = SWRB1205S, C28) at X 81…102 (stage 16: U2 at (86, 75.25), L2 at (95.75, 70.9), 5.5 mm further forward than L3 so J13 fits at the rear edge behind U2), behind the +5 V LDO. Its feedback divider (0.1 %) and the 56.2 k injection resistor sit in the strip between U2/L2 and J13, beside the FB pin. The GPIO46 filter RC and the FAN_OFF transistor are auto-placed nearby; V_BLOWER runs at 0.8 mm to J10. A keep-apart band X 102.8…112.8 (`floorplan.py` CHANNELS) holds parts out so L2 stays ≥ 10 mm from the RTD analog parts. The tach pull-up (10 k), TVS and 1 k / 1 nF RC into GPIO3 sit at J10.
- **PS3 feed (stage 16, C33):** V15_BLW runs entirely in F.Cu pours (`floorplan.py` BLW_FEED), so the 2.72 A PS3 current never depends on a routed track:
  - a 1.7 mm band from J13.1 (thermal-relieved, 0.6 mm spokes) down the left of U2 into its VIN pour;
  - a 2.0 mm strip over the 100 µF bulk capacitor's + pad (C9, at (72.6, 72)) and the three input capacitors.
  - Routing channels keep auto-placed parts out of both.
  - The BLW_PG divider sits at J13, so only its ≤ 3.9 V node runs to the expander.
  - **Return:** J13.2 drops into the In1 plane beside the buck. The 15 V supply current enters and leaves there, instead of crossing the board from J4 as in L3.
- **Rim NTC channel** (R36/C31): TVS at J12; the 1.00 k pull-up, the 10 k / 100 nF filter and the TLV9061 follower (u_buf3) at (118.3, 81.0) beside it (C40: 1.2 mm left of its L3 spot for the 3-pin J12); the ADC anti-kick RC at the module.
- **Module channels (L3):** a band in front of the module (X 137…163, Y 41…49.6) and a strip along its left pin column (X 134.5…140.4) are kept free of auto-placed parts except decoupling capacitors. The module's right-column nets all leave to the left round its front edge; the nets that stayed open in L2's failed runs were all module nets at these pins.

## Analog / digital partitioning

| Separation (courtyard to courtyard, `evidence/layout-check.json` partition) | mm |
|---|---|
| Blower buck (L2/U2) → RTD front end (required ≥ 10, ENCLOSURE-HANDOFF item 6) | 10.5 |
| Blower buck → thermal-sense block | 48.2 |
| Blower buck → J4 analog (D-11, ct_mon, AD8436) | 69.9 |
| 3.3 V buck (L1/U1) → RTD front end | 76.7 |
| 3.3 V buck → thermal-sense block | 52.0 |
| 3.3 V buck → J4 analog | 36.0 |

L2 (10.1 mm) → L3 (10.4 mm) → stage 16 (10.5 mm) for the blower buck to the RTD parts, with the larger SWRB1205S inductor: the keep-apart band holds it. The blower buck is 48.2 mm from the thermal-sense block (L2: 54.1 mm) because it is wider; the thermal-sense nodes now also have the 159 Hz RC ahead of their buffers.

- **Switchers:** both bucks are compact. The VIN pour holds the input capacitors' supply pads against the VIN pin; the GND pin drops through its own via into In1 beside the input capacitors' ground vias; the SW node leaves its corner pin straight down into a pour band that runs to the inductor, so the BST/SS/FB pins keep their side free for the bootstrap capacitor and the SS/FB parts.
- **Blower speed input:** the GPIO46 PWM is filtered to DC (12.1 k / 1 µF) before it reaches the 56.2 k injection resistor at the FB node, so no PWM edge reaches the feedback pin; the FB divider is at the pin.
- **High-impedance nodes** (HS_SENSE, COIL_SENSE, RIM_SENSE, the RTD sense pair, M12) run over the unbroken In1 plane, and none passes over a switch node.
- **RTD analog return (C34):** the RTD analog family (sense and force pairs, bias, refin_n, the window input, vbias) is routed only on F.Cu and In2.Cu, whose reference is the In1 ground plane; never over an In1 antipad, including two antipads that merge because they are closer than the plane's 0.25 mm minimum width; with a ground via within 2.5 mm of each of their vias. Every other via keeps its antipad 0.125 mm off them. The RTD block validator's analog-return corridor check passes on every trace.
- **MCU nets and the interlock:** the router treats the box of the six interlock logic ICs (world X-20.6…23.11, Y57.77…70.88) as a keep-out for MCU nets. `check_layout.py` confirms that no MCU net crosses it or the PERMIT-gate box, except the nets that end there by design (BUS_FAULT_RB, IL_RESET_N, IL_WDI, PERMIT_RB, RAIL_OK_RB, RUN_EN).

## Interlock trip path

Routed lengths (`evidence/layout-check.json` interlock): PERMIT 70.6 mm (U37 → J4.9 plus the read-back branch to U9), PERMIT_LATCH 49.3, bus_fault 93.7, all_good 36.9, reset_clock 43.1, latched_fault 56.2, RAIL_FAULT 34.3, SENSOR_LIVE 17.0, HS_FAULT 88.2, COIL_FAULT 97.6, RTD_HW_FAULT (`line`) 195.0, RUNAWAY_FAULT 148.9, RUN_EN 208.6 mm.

The latch block's internal nets stay short. The long ones each have a geometric reason:
- the RTD trip inputs (RTD_HW_FAULT, RUNAWAY_FAULT) come from the RTD block beside J3 at the far right, and the thermal trip inputs from the thermal block;
- RUN_EN runs from the module (now at the far right, R33) to the PERMIT gate at J4.9 (far left), and as an MCU net it must go round the interlock box.

Each trip input fails safe on a break (pull-up to the fault level at the interlock input). RUN_EN has a 4.7 kΩ pull-down at the gate, so a break removes permission. None is reachable by firmware (`verify_controller.py` trip checks).

## Decoupling

Every IC supply pin (the "vcc" pins of `verify_controller.py`'s part models) has a capacitor to `selv_gnd` on the same net within 2.53 mm (worst of 38 supply pins, U14.16; limit 5 mm). Each capacitor's ground pad has its own via to In1 and each 3.3 V pad its own via to In2.

## Results

| Gate | Result | Evidence |
|---|---|---|
| KiCad DRC errors | **0** | `evidence/drc.json` |
| Unconnected items | **0** | `evidence/drc.json` |
| Schematic parity | 0 | `evidence/drc.json` |
| DRC warnings | 27: connection_width 11, silk_edge_clearance 10, copper_sliver 3, lib_footprint_mismatch 2, track_dangling 1. connection_width is thin necks in zone fills and copper_sliver slivers of zone fill; silk_edge_clearance is designators near the board edge; lib_footprint_mismatch is the two intended footprint edits (U20 pads, WROOM courtyard). track_dangling is a 2.4 mm v3v3 B.Cu dead-end branch beside U31 (197.8–198.3, 36.2–38.4), left by a rip-up: cleanup.py skips the plane nets, whose tracks may end in a pour. It carries no connection | `evidence/drc.json` |
| JLC DFM (1 oz limits) | PASS: 1312 vias (the C34 RTD stitching grid and the C53 selv_gnd grid and power companions included), 5778 tracks, 67 plated pads, 5 NPTH (J4's 2, J11's 3 TC2050 holes), min track 0.15 mm | `evidence/jlc-dfm.json` |
| Enclosure + layout check | PASS on all 21 checks (C53 adds rtd_j9_protection, power_widths, power_layers, power_paths, power_vias, v3v3_islands, gnd_stitch, stranded_vias). rtd_j3_protection: J3 cap / TVS edge gaps 2.83–5.45 mm, reported; the CR's 3 mm is set by the XH body, C37. Partition: L2 to the RTD front end 10.5 mm, L3 22.0 mm | `evidence/layout-check.json` |
| Fab review (gerbv) | PASS: 1379 PTH hits (67 component, 1312 via), 5 NPTH, outline 206.0 × 76.0 mm | `evidence/fab-review.json` |
| Designators | 199 on silk, 147 on F.Fab only (all on the assembly drawing) | `evidence/silk-designators.json` |
| `tools/verify_controller.py` | PASS, 270 checks in 17 sections; 50/50 mutation tests (`tests/test_verify_mutations.py`) | `evidence/verify.json` |
| CPL rotations | audit rerun (C44, C45): 16 CORRECTED (U42 SN74LVC74APWR added, 270°), 224 OK, 44 NEEDS-PREVIEW (listed in `fab/fab-notes.md`); all 284 CPL lines equal the proposal | `evidence/fab-loose-ends/cpl-rotation/audit.json` |
| Routing robustness | **2 of 3 full runs from a clean start close the C51 six-layer board** with all gates passing (C53 set 11, routing code 1be33819a; the board of record is run 2, sha256 `e82e6140…`). Run 1 left HS_FAULT and hs_buf_out open after its last ECO pass. The C51 rule is at least 2 of 3. Earlier sets are recorded in DECISIONS C53 | `evidence/convergence.json`, `evidence/c53-set11/` |
| Block validators (C53, set 11 board) | interlock 68 pass / 7 fail / 5 indeterminate, thermal-sense 87 / 10 / 7, RTD 5 / 40 / 5, the same as the superseded C53 board (C47: 69 / 6 / 5, 88 / 9 / 7, 5 / 33 / 5). The new fails are the C51/C52 part swaps and the six-layer manufacturing contract (W8). Every FAIL and INDETERMINATE is waived line by line | `evidence/block-validators/` (`WAIVERS.md`, `summary.json`) |

**Convergence (routing robustness).** `python3 layout/convergence.py --runs 3 --out <dir>` moves `pcb/route/` away before each run, so no run reuses copper, then runs the whole `make.py`.

**C53 proof (C51, six layers; set 11 on routing code 1be33819a; current `evidence/convergence.json`, runs in `evidence/c53-set11/`):**

| Run | Result | Rounds | ECO passes | Time | Warnings |
|---|---|---|---|---|---|
| 1 | DRC not clean: HS_FAULT and hs_buf_out open after the last ECO pass | 51 | 3 | 7931 s | 44 |
| 2 | ALL GATES PASS (board of record); pv_repair added a v15_selv via's companion | 52 | 3 | 8422 s | 27 |
| 3 | ALL GATES PASS; pv_repair added a V12_FAN2 via's companion | 44 | 1 | 6906 s | 31 |

The passing runs had 0 errors, 0 unconnected and parity 0, with warnings of the kinds listed above only. The runs take
two to three times as long as the superseded set's (about 3300 s): the post-review gates (power_vias, v3v3_islands,
power_widths) add the ECO passes and pv_repair. Sets 7 to 10 on the way to this code failed. Each cause was fixed and
replayed on the saved boards first (DECISIONS C53):
- set 7: island drop and the V15_BLW neck;
- set 8: ECO model shorts;
- set 9: single-barrel V_BLOWER vias;
- set 10: U2 pin escape.

The superseded C53 set (run 1 of record, 2 of 3, before the layout-review fixes) is in `evidence/c53-six-layer-final/`.

**C47 proof (history; C1 + CR-8, 285 parts):**

| Run | Exit | Wall time | DRC errors / unconnected / parity | Warnings |
|---|---|---|---|---|
| 1 | 0, ALL GATES PASS | 5867 s | 0 / 0 / 0 | 42: connection_width 26, silk_edge_clearance 14, lib_footprint_mismatch 2 |
| 2 | 0, ALL GATES PASS | 3670 s | 0 / 0 / 0 | 35: connection_width 19, silk_edge_clearance 14, lib_footprint_mismatch 2 |
| 3 | 0, ALL GATES PASS | 3319 s | 0 / 0 / 0 | 34: connection_width 18, silk_edge_clearance 14, lib_footprint_mismatch 2 |

The committed board and fab package are run 3's. Block validators on each run's board: identical verdict counts (69 / 6 / 5, 88 / 9 / 7, 5 / 33 / 5). The informative RTD layer-roles run has 69 / 91 / 61 clock-return findings; that routing detail varies per run.

**L3 proof (history):** runs 1, 2 and 3 each ended "ALL GATES PASS" (exit 0, about 753 s each), each with 0 errors, 0 unconnected, parity 0, and the same 22 warnings listed above. That L3 proof's committed board was run 3 (315 open pairs after placement; one 3 mm repair; closed in round 7; the three runs' logs were identical). The boards differ slightly between runs (KiCad's DRC lists pairs in varying order), but all close.

**Stage 16 convergence** (`evidence/convergence.json`, same tool, after the J13 / V15_BLW change): runs 1, 2 and 3 each ended "ALL GATES PASS" (exit 0; 1490, 1485 and 1467 s), each with 0 errors, 0 unconnected, parity 0. Warnings were 28, 29 and 29, all of the four kinds above. The committed board is run 3. Its round log (`evidence/route-log.json`):
- 315 pairs open after placement; 18 after round 1; 4 after round 2.
- A 3 mm repair, then a 5 mm repair (HS_FAULT_RB, the thermal comparator input `inn`, v3v3).
- 0 open after round 8. The final cleanup reopened 3, which rounds 10–11 closed.
Runs take about twice as long as L3's because of the extra repair cycles around the moved buck cluster.

**L4 convergence** (`evidence/convergence.json`, same tool, after the C34 changes): runs 1, 2 and 3 each ended "ALL GATES PASS" (exit 0; **3194, 6046 and 2630 s**), each with 0 errors, 0 unconnected, parity 0 and 25, 29 and 29 warnings (connection_width, silk_edge_clearance, lib_footprint_mismatch). Each run's board was also put through the three block validators: identical counts on all three (interlock 70 / 5 / 5, thermal 88 / 9 / 7, RTD 5 / 18 / 5). The committed board is run 3: 315 pairs open after placement, 10 after round 1, then 4 local repairs and 2 cleanup cycles, closed in round 18. The runs are about twice as long as stage 16's (run 2 used all three repair cycles before closing): the RTD analog nets now have fewer layers and fewer legal via sites, and rtd_sense_p / rtd_sense_n were among the five nets left open for the first repair in every run (with RAIL_OK_RB, hs_buf_out, runaway_healthy). The margin is thinner than stage 16's; a fourth repair cycle is the first lever if a later change makes a run miss.

What changed from L2, where three of four runs closed:
- **Long pairs first:** `gridroute.py` routes pairs ≥ 60 mm (the PWM lines, read-backs and trip inputs that cross the board) first, longest first, before the short local ones fill the channels. An earlier L3 set without this left pwm_hb open in one of three runs.
- **Module channels:** the band in front of the module and the strip on its left (Floorplan) stay free of placed parts.
- **Repair cycles:** the local rip-and-reroute (3, 5, 8 mm) and cleanup repeat up to three times while pairs stay open.
- **Final dangling pass:** after the outer pours and silk, `route.py` deletes what KiCad's DRC still lists as dangling (exact net, layer and length match). L3 runs before this pass each kept one dangling COIL_FAULT stub as a warning; the proof runs have none.
- A run that does not close still stops `make.py` with "DRC not clean"; it never produces a fab package.

**Enclosure constraints (R31 + R33 + R36/R38), all checked by `layout/check_layout.py`:**
- outline X−38…168 / Y14…90, 1.6 mm, 6 layers: exact;
- six Ø4.0 holes at the R31 positions: exact; Ø8 keep-outs free of courtyards, pads, tracks, vias and fills;
- J1, J2, J3, J7, J9, J10, J12 body centres: 0.0 mm worst error; J7 body edges within 0.074 mm of the R33 box X29.8–62.2 / Y57.1–62.9; J3 body along the rear edge; J10 (now 3-way, C28) at its R31 centre (139, 86); J12 at (126, 86) (accepted, R38);
- J4 courtyard X-38.01…-24.29 / Y27.795…57.005, mating −X at the left edge;
- WROOM-1U body X140.95…159.05 / Y50.25…69.55 (inside the R33 box, max edge offset 0.25 mm), U.FL end at the rear, no other part within 3.0 mm of the U.FL;
- **U.FL position:** Espressif Figure 10-2 puts the receptacle at (156.0, 67.04) on the R33 body box, not R33's (150, 67). R38 accepted (156, 67); `layout-check.json` still lists the R33 figure as an enclosure delta for traceability;
- J13 (stage 16): body centre (88, 85.65), 0.35 mm from R41's (88, 86) and flush with the rear edge;
- heights (drawing-based, ENCLOSURE-HANDOFF table): mated XH 9.8 mm, J4 + plug 10.29 mm (series figure), J11 0 mm (TC2050 land, C41), all under the 15.4 mm allowance; J13 mated 16.5 mm (JST eVH p.1) inside R41's local allowance (29.4 mm above the board within ±6 mm of (88, 86)); C1 6.2, L1 4.5, L2 (SWRB1205S) 6.0, WROOM-1U 3.2 mm under the 6.4 mm allocation.

## Open items

1. **Release:** the board is a candidate, not released. Ordering is the owner's call.
2. **PS3 (stage 16, C33)** replaces DECISIONS open item 13: PS1 now carries 4.83 W of 21 W. PS3's own items are in the power-stage PLAN-16 §6, chiefly:
   - bench gate G-B1: blower start current and PS3 hiccup margin;
   - the inlet `aux_max_a` change in firmware;
   - the BLW-AC mains harness's reinforced routing.
   J13's LCSC number C20571196 comes from PLAN-16 and was not re-queried here.
3. **Firmware change requests** (`docs/evidence/2026-10-12-thermal-trip-ladder-l3.md`): OVER_TEMP_THRESHOLD 80 → 95 °C with its tests; the coil and rim NTC curves to the 104GT-2 table; the blower PWM sense (duty 0 = full speed) and FAN_OFF on P15; a dead tach forces a derate.
4. **Block validators** (DECISIONS C30, C34): re-run on this board (`evidence/block-validators/`). Every remaining finding is a contract deviation of the integration (host connectors absent, the C32 trip resistors, DRDY on the expander) or a unit layer role the controller does not use, each justified in `WAIVERS.md`. Open: the RTD SPI nets' return under the controller's own layer roles (DECISIONS open item 14).
5. **RTD filter** (C29): the RTD library is byte-locked, so its differential RC is a change request to the RTD block, not a layout change here.
6. **Sensors with the enclosure:** the coil NTC changes to a 104GT-2 class glass bead (300 °C) and the rim NTC is the same part; the enclosure owns their mounting (ENCLOSURE-HANDOFF).
7. **J4 drawing (header read 2026-10-12, owner-supplied 430451600_sd.pdf; not committed):** the 43045 dual-row right-angle header, 16 circuits.
   - Width A is 27.65 mm; the 2 × 8 pin span B is 21.00 mm and the peg spacing C is 16.70 mm.
   - Depth is 12.24 mm overall (mating face to tail rear), with a body of 9.91 mm.
   - Housing height above the PCB is 7.37 mm, 8.77 mm at the latch ramp (+1.40). Tails 3.18 mm, pegs Ø3.00 ±0.05 holes, recommended PCB 1.57 mm, LCP UL94 V-0.
   - The layout courtyard (`world.J4_BODY`, Y27.8–57.0 = 29.2 mm, X−38 to −24.3 = 13.7 mm) contains it.
   - The pin field is centred at world Y42.40 (pads Y31.90–52.90), so the header spans Y28.575–56.225, inside the enclosure's current body envelope (R43: Y27.8–57.0, 10.4 mm tall). The Y29.6–54.4 figure in `world.py`'s comment is stale R31 text and does not reflect the enclosure source.
   - **Plug (43025-1600, Molex catalog page F-125 via Jameco 883000, owner-supplied 2026-10-12):** 24.85 mm wide, 6.86 mm tall, 14.00 mm long without wires.
     - It sits inside the header's 7.37 mm body, so the mated height is ≤ the series 10.29 mm.
     - Insertion depth isn't on the catalog page. The conservative bound (zero insertion) puts the plug end at X ≥ −52.0, against the enclosure's X−50.
     - The enclosure either allows X−52 plus wire bend room, or the 430251600_sd product drawing is needed.
8. **CPL rotations:** KiCad's rotations are written as-is; check each package in JLC's placement preview before ordering.
9. **Consigned / low-stock parts** (DECISIONS open item 7): none after the C35/C36 sourcing swaps (R31, R39, R53, U14 A grade, U22; J13 code fix); `fab/fab-notes.md` lists the swaps and the NEEDS-PREVIEW CPL lines. Fab ZIP sha256 `978ef705…`, frozen netlist `8471186c…` (`frozen/build-receipt.json`; C53 set 11 board).
10. **Long lines:** RUN_EN and the RTD trip inputs cross most of the board (Interlock trip path). All fail safe on a break; a bench noise check on them is worth adding.
11. **In2 use:** In2 carries some signal tracks where F/B were full; the v3v3 pour refills around them, and `plane_islands.py` re-joins any v3v3 island; DRC shows v3v3 as one connected net.
12. **Firmware pins.h:** RUN_EN 14; RTD_DRDY expander P07; SUP_RUN_OK expander P14; FAN_OFF expander P15; BLW_PG expander P16 (input, 1 = PS3 present); FAN_PWM GPIO46 (feedback injection, duty 0 = full speed); FAN_TACH (J10 FG) GPIO3 (PCNT); UI SPI 40/41/44/47/48/45; I²C SDA 37 / SCL 0; RIM_ADC 9.

