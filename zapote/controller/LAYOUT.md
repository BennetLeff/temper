# Controller PCB layout (L3 + stage 16: enclosure R33/R41, R36 rim NTC, blower supply from PS3, thermal trip ladder)

This is the layout of the integrated SELV controller: 248 parts, 4 layers, 206 × 76 mm, placed and routed by scripts from `frozen/default.net`, with a JLCPCB fab package. Nothing was drawn by hand in the KiCad GUI.

**Status: DRC-clean candidate, not released** (ordering is the owner's decision). KiCad DRC: 0 errors, 0 unconnected, schematic parity 0; JLC DFM PASS; all 12 enclosure/layout checks PASS; gerbv fab review PASS. Not fabricated. Every number below comes from a file in `evidence/` that `python3 layout/make.py` regenerates: `drc.json`, `jlc-dfm.json`, `layout-check.json`, `fab-review.json`, `silk-designators.json`, `verify.json`; the routing-robustness proof is `evidence/convergence.json` (`layout/convergence.py`).

**Enclosure revision:** R31 outline, holes and connectors (`output/temper-manufacturing-r31/design/r31/CONTROLLER-SPEC.md`, "R31" section, with R30's mounting and heights) plus the **R33 controller delta** (`output/temper-manufacturing-r33/design/r33/DECISIONS.md` §3; the R35 HANDOFF restates it unchanged):
- J5, J6 and J8 are deleted; one 12-way JST B12B-XH-A **J7** at X29.8–62.2, Y57.1–62.9 carries the UI bus (DECISIONS C26);
- the module is the **ESP32-S3-WROOM-1U-N8** at X141–159, Y50–69.5, with a U.FL to an off-board chip antenna, so there is no antenna keep-out.

**R36 / R38:** the rim NTC on the sensor cartridge adds an ADC1 channel and **J12** (B2B-XH-A) at (126, 86) (DECISIONS C27, C31). The enclosure session (R38) accepted J12 at (126, 86) and the U.FL at (156, 67).

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

**All enclosure numbers live in one table, `layout/world.py`**; a new revision is an edit there plus a re-run. The L1 layout (R31) is in git history at `97c36e2a9`.

## Rebuild

From `zapote/controller` (KiCad 10.0.4 and its bundled Python; system Python 3 with numpy, scipy, shapely and Pillow; gerbv for the fab review; offline; no Rust or workspace build):

```sh
python3 layout/make.py             # place, plane fan-out, route, DRC, DFM, enclosure check, fab, fab review
python3 layout/make.py --no-route  # same, reusing pcb/controller-routed.kicad_pcb (routing is the slow step)
python3 tools/verify_controller.py # schematic verification
python3 layout/convergence.py --runs 3 --out <dir>  # routing-robustness proof: 3 full runs from a clean start
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

## Stack-up: 4 layers, 1 oz outer

JLC JLC04161H-7628, 1.6 mm: F.Cu 1 oz (0.035) / 0.21 prepreg / In1.Cu 0.5 oz / 1.065 core / In2.Cu 0.5 oz / 0.21 prepreg / B.Cu 1 oz.

| Layer | Use |
|---|---|
| F.Cu | All parts; signals; buck VIN/SW pours; `selv_gnd` pour in the gaps |
| In1.Cu | Solid `selv_gnd` plane, cut only by the six Ø8 snap-in keep-outs |
| In2.Cu | `v3v3` pour (same cuts); also a third routing layer where F/B are full, the pour refilling around those tracks |
| B.Cu | Signals; `selv_gnd` pour in the gaps |

**Why four:** the board carries three sensitive analog front ends (the RTD MAX31865 and the ±1 µA thermal-sense nodes, the D-11 bus receiver into the ESP32 ADC, the AD8436 tank RMS) next to an ESP32 radio module, two 500 kHz bucks and two SPI buses. A continuous ground plane 0.21 mm under every F.Cu signal gives every return path a defined image, and the In2 3.3 V plane gives about 100 decoupling capacitors a one-via return each. On two layers the ground would be a pour broken by every crossing. **Why 1 oz:** the largest currents are the blower output (≥ 1.5 A on V_BLOWER, C28) and the v15_selv feed to the blower buck. Both run on 0.8 mm outer tracks, which IPC-2221's external-layer formula (I = 0.048·ΔT^0.44·A^0.725, A in mil²) puts at 2.0 A for a 10 K rise on 1 oz copper; 1 oz is JLC's standard 4-layer copper.

**One ground.** The schematic has one return net, `selv_gnd`, and no separate analog ground, so the board has one solid plane and the analog/digital partition is done by placement. A split would force every analog-to-ADC signal across a gap.

## Rules (JLC capability with margin)

JLC figures re-read 2026-10-09 from jlcpcb.com/capabilities/pcb-capabilities (multilayer, 1 oz): track/space 0.09/0.09 mm, PTH ring 0.15 mm minimum (0.20 recommended), via 0.15/0.25 mm, via hole-to-hole 0.2 mm, pad hole-to-hole 0.45 mm, NPTH ≥ 0.5 mm, copper to a routed edge ≥ 0.2 mm, silk text ≥ 1.0 mm.

| Rule | This board | Margin over JLC |
|---|---|---|
| Track | 0.15 mm signal, 0.3 mm v3v3 / plane stubs, 0.4 mm v15/SW (0.8 mm v15_selv, V_BLOWER and the blower SW node where routed) | ≥ 1.7× |
| Clearance | 0.15 mm (all net classes) | 1.7× (JLC 0.09 mm) |
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
- **Blower buck** (U2, L2 = SWRB1205S, C28) at X 81…102 (stage 16: U2 at (86, 75.25), L2 at (95.75, 70.9), 5.5 mm further forward than L3 so J13 fits at the rear edge behind U2), behind the +5 V LDO. Its feedback divider (0.1 %) and the 56.2 k injection resistor sit in the strip between U2/L2 and J13, beside the FB pin. The GPIO46 filter RC and the FAN_OFF transistor are auto-placed nearby; V_BLOWER runs at 0.8 mm to J10. A keep-apart band X 102.8…112.8 (`floorplan.py` CHANNELS) holds parts out so L2 stays ≥ 10 mm from the RTD analog parts. The tach pull-up (10 k), TVS and 1 k / 1 nF RC into GPIO3 sit at J10.
- **PS3 feed (stage 16, C33):** V15_BLW runs entirely in F.Cu pours (`floorplan.py` BLW_FEED), so the 2.72 A PS3 current never depends on a routed track:
  - a 1.7 mm band from J13.1 (thermal-relieved, 0.6 mm spokes) down the left of U2 into its VIN pour;
  - a 2.0 mm strip over the 100 µF bulk capacitor's + pad (C9, at (72.6, 72)) and the three input capacitors.
  - Routing channels keep auto-placed parts out of both.
  - The BLW_PG divider sits at J13, so only its ≤ 3.9 V node runs to the expander.
  - **Return:** J13.2 drops into the In1 plane beside the buck. The 15 V supply current enters and leaves there, instead of crossing the board from J4 as in L3.
- **Rim NTC channel** (R36/C31): TVS at J12; the 1.00 k pull-up, the 10 k / 100 nF filter and the TLV9061 follower (u_buf3) at (119.5, 81.5) beside it; the ADC anti-kick RC at the module.
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
| DRC warnings | 29: connection_width 14, silk_edge_clearance 12, lib_footprint_mismatch 2, copper_sliver 1. connection_width is thin necks in zone fills; silk_edge_clearance is designators near the board edge; lib_footprint_mismatch is the two intended footprint edits (U20 pads, WROOM courtyard); copper_sliver is one acute corner in a ground pour. No dangling track or via | `evidence/drc.json` |
| JLC DFM (1 oz limits) | PASS: 811 vias, 3246 tracks, 66 plated pads, 2 NPTH, min track 0.15 mm | `evidence/jlc-dfm.json` |
| Enclosure + layout check | PASS on all 12 checks (stage 16 adds power_widths: V_BLOWER ≥ 0.8 mm; V15_BLW's J13.1, bulk and input-cap pads in one F.Cu pour region) | `evidence/layout-check.json` |
| Fab review (gerbv) | PASS: 877 PTH hits (66 component, 811 via), 2 NPTH, outline 206.0 × 76.0 mm | `evidence/fab-review.json` |
| Designators | 186 on silk, 62 on F.Fab only (all on the assembly drawing) | `evidence/silk-designators.json` |
| `tools/verify_controller.py` | PASS, 182 checks in 13 sections; 33/33 mutation tests (`tests/test_verify_mutations.py`) | `evidence/verify.json` |
| Routing robustness | **3/3 consecutive full runs from a clean start close the board** with all gates passing | `evidence/convergence.json` |

**Convergence (routing robustness).** `python3 layout/convergence.py --runs 3 --out <dir>` moves `pcb/route/` away before each run, so no run reuses copper, then runs the whole `make.py`. Result (`evidence/convergence.json`): runs 1, 2 and 3 each ended "ALL GATES PASS" (exit 0, about 753 s each), each with 0 errors, 0 unconnected, parity 0, and the same 22 warnings listed above. That L3 proof's committed board was run 3 (315 open pairs after placement; one 3 mm repair; closed in round 7; the three runs' logs were identical). The boards differ slightly between runs (KiCad's DRC lists pairs in varying order), but all close.

**Stage 16 convergence** (`evidence/convergence.json`, same tool, after the J13 / V15_BLW change): runs 1, 2 and 3 each ended "ALL GATES PASS" (exit 0; 1490, 1485 and 1467 s), each with 0 errors, 0 unconnected, parity 0. Warnings were 28, 29 and 29, all of the four kinds above. The committed board is run 3. Its round log (`evidence/route-log.json`):
- 315 pairs open after placement; 18 after round 1; 4 after round 2.
- A 3 mm repair, then a 5 mm repair (HS_FAULT_RB, the thermal comparator input `inn`, v3v3).
- 0 open after round 8. The final cleanup reopened 3, which rounds 10–11 closed.
Runs take about twice as long as L3's because of the extra repair cycles around the moved buck cluster.

What changed from L2, where three of four runs closed:
- **Long pairs first:** `gridroute.py` routes pairs ≥ 60 mm (the PWM lines, read-backs and trip inputs that cross the board) first, longest first, before the short local ones fill the channels. An earlier L3 set without this left pwm_hb open in one of three runs.
- **Module channels:** the band in front of the module and the strip on its left (Floorplan) stay free of placed parts.
- **Repair cycles:** the local rip-and-reroute (3, 5, 8 mm) and cleanup repeat up to three times while pairs stay open.
- **Final dangling pass:** after the outer pours and silk, `route.py` deletes what KiCad's DRC still lists as dangling (exact net, layer and length match). L3 runs before this pass each kept one dangling COIL_FAULT stub as a warning; the proof runs have none.
- A run that does not close still stops `make.py` with "DRC not clean"; it never produces a fab package.

**Enclosure constraints (R31 + R33 + R36/R38), all checked by `layout/check_layout.py`:**
- outline X−38…168 / Y14…90, 1.6 mm, 4 layers: exact;
- six Ø4.0 holes at the R31 positions: exact; Ø8 keep-outs free of courtyards, pads, tracks, vias and fills;
- J1, J2, J3, J7, J9, J10, J12 body centres: 0.0 mm worst error; J7 body edges within 0.074 mm of the R33 box X29.8–62.2 / Y57.1–62.9; J3 body along the rear edge; J10 (now 3-way, C28) at its R31 centre (139, 86); J12 at (126, 86) (accepted, R38);
- J4 courtyard X-38.01…-24.29 / Y27.795…57.005, mating −X at the left edge;
- WROOM-1U body X140.95…159.05 / Y50.25…69.55 (inside the R33 box, max edge offset 0.25 mm), U.FL end at the rear, no other part within 3.0 mm of the U.FL;
- **U.FL position:** Espressif Figure 10-2 puts the receptacle at (156.0, 67.04) on the R33 body box, not R33's (150, 67). R38 accepted (156, 67); `layout-check.json` still lists the R33 figure as an enclosure delta for traceability;
- J13 (stage 16): body centre (88, 85.65), 0.35 mm from R41's (88, 86) and flush with the rear edge;
- heights (drawing-based, ENCLOSURE-HANDOFF table): mated XH 9.8 mm, J4 + plug 10.29 mm (series figure), J11 8.54 mm, all under the 15.4 mm allowance; J13 mated 16.5 mm (JST eVH p.1) inside R41's local allowance (29.4 mm above the board within ±6 mm of (88, 86)); C1 6.2, L1 4.5, L2 (SWRB1205S) 6.0, WROOM-1U 3.2 mm under the 6.4 mm allocation.

## Open items

1. **Release:** the board is a candidate, not released. Ordering is the owner's call.
2. **PS3 (stage 16, C33)** replaces DECISIONS open item 13: PS1 now carries 4.83 W of 21 W. PS3's own items are in the power-stage PLAN-16 §6, chiefly:
   - bench gate G-B1: blower start current and PS3 hiccup margin;
   - the inlet `aux_max_a` change in firmware;
   - the BLW-AC mains harness's reinforced routing.
   J13's LCSC number C20571196 comes from PLAN-16 and was not re-queried here.
3. **Firmware change requests** (`docs/evidence/2026-10-12-thermal-trip-ladder-l3.md`): OVER_TEMP_THRESHOLD 80 → 95 °C with its tests; the coil and rim NTC curves to the 104GT-2 table; the blower PWM sense (duty 0 = full speed) and FAN_OFF on P15; a dead tach forces a derate.
4. **Block validators** (DECISIONS C30): the interlock, thermal-sense and RTD validators need a workspace build, which this task does not do. The thermal-sense 64-corner method is ported into `verify_controller.py` (check_thermal) and passes on the L3 values; the Rust validators should still be re-run in a workspace build.
5. **RTD filter** (C29): the RTD library is byte-locked, so its differential RC is a change request to the RTD block, not a layout change here.
6. **Sensors with the enclosure:** the coil NTC changes to a 104GT-2 class glass bead (300 °C) and the rim NTC is the same part; the enclosure owns their mounting (ENCLOSURE-HANDOFF).
7. **J4 drawing (header read 2026-10-12, owner-supplied 430451600_sd.pdf; not committed):** the 43045 dual-row right-angle header, 16 circuits.
   - Width A is 27.65 mm; the 2 × 8 pin span B is 21.00 mm and the peg spacing C is 16.70 mm.
   - Depth is 12.24 mm overall (mating face to tail rear), with a body of 9.91 mm.
   - Housing height above the PCB is 7.37 mm, 8.77 mm at the latch ramp (+1.40). Tails 3.18 mm, pegs Ø3.00 ±0.05 holes, recommended PCB 1.57 mm, LCP UL94 V-0.
   - The layout courtyard (`world.J4_BODY`, Y27.8–57.0 = 29.2 mm, X−38 to −24.3 = 13.7 mm) contains it.
   - **The enclosure's R31 header envelope (Y29.6–54.4 = 24.8 mm) is 2.85 mm narrower than the real header** and must grow (relayed to the enclosure session).
   - Still unread: the mated height (10.29 mm is Molex's series figure) and the plug's −X overhang (R31: to X−50). Both need the **43025-1600 plug** drawing.
8. **CPL rotations:** KiCad's rotations are written as-is; check each package in JLC's placement preview before ordering.
9. **Consigned / low-stock parts** (DECISIONS open item 7): AD8436BRQZ (JLC stock 0) and the near-zero-stock ported parts; `fab/fab-notes.md` lists them.
10. **Long lines:** RUN_EN and the RTD trip inputs cross most of the board (Interlock trip path). All fail safe on a break; a bench noise check on them is worth adding.
11. **In2 use:** In2 carries some signal tracks where F/B were full; the v3v3 pour refills around them, and `plane_islands.py` re-joins any v3v3 island; DRC shows v3v3 as one connected net.
12. **Firmware pins.h:** RUN_EN 14; RTD_DRDY expander P07; SUP_RUN_OK expander P14; FAN_OFF expander P15; BLW_PG expander P16 (input, 1 = PS3 present); FAN_PWM GPIO46 (feedback injection, duty 0 = full speed); FAN_TACH (J10 FG) GPIO3 (PCNT); UI SPI 40/41/44/47/48/45; I²C SDA 37 / SCL 0; RIM_ADC 9.

