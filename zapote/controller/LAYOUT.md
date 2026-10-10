# Controller PCB layout (L2: enclosure R33, R36 rim NTC)

This is the layout of the integrated SELV controller: 231 parts, 4 layers, 206 × 76 mm, placed and routed by scripts from `frozen/default.net`, with a JLCPCB fab package. Nothing was drawn by hand in the KiCad GUI.

**Status: DRC-clean candidate, not released** (ordering is the owner's decision). KiCad DRC: 0 errors, 0 unconnected, schematic parity 0; JLC DFM PASS; all 11 enclosure/layout checks PASS; gerbv fab review PASS. Not fabricated. Every number below comes from a file in `evidence/` that `python3 layout/make.py` regenerates: `drc.json`, `jlc-dfm.json`, `layout-check.json`, `fab-review.json`, `silk-designators.json`, `verify.json`.

**Enclosure revision:** R31 outline, holes and connectors (`output/temper-manufacturing-r31/design/r31/CONTROLLER-SPEC.md`, "R31" section, with R30's mounting and heights) plus the **R33 controller delta** (`output/temper-manufacturing-r33/design/r33/DECISIONS.md` §3; the R35 HANDOFF restates it unchanged):
- J5, J6 and J8 are deleted; one 12-way JST B12B-XH-A **J7** at X29.8–62.2, Y57.1–62.9 carries the UI bus (DECISIONS C26);
- the module is the **ESP32-S3-WROOM-1U-N8** at X141–159, Y50–69.5, with a U.FL to an off-board chip antenna, so there is no antenna keep-out.

**R36 (coordinator relay):** a rim NTC on the sensor cartridge adds an ADC1 channel and **J12** (B2B-XH-A) for the NTC pair of the 6-conductor cartridge cable, at a **proposed** landing (126, 86) (DECISIONS C27).

**All enclosure numbers live in one table, `layout/world.py`**; a new revision is an edit there plus a re-run. The L1 layout (R31) is in git history at `97c36e2a9`.

## Rebuild

From `zapote/controller` (KiCad 10.0.4 and its bundled Python; system Python 3 with numpy, scipy, shapely and Pillow; gerbv for the fab review; offline; no Rust or workspace build):

```sh
python3 layout/make.py             # place, plane fan-out, route, DRC, DFM, enclosure check, fab, fab review
python3 layout/make.py --no-route  # same, reusing pcb/controller-routed.kicad_pcb (routing is the slow step)
python3 tools/verify_controller.py # schematic verification
```

| Script | Does |
|---|---|
| `layout/world.py` | **The parameter table:** outline, holes and keep-outs, connector centres, the J7 and module boxes, the U.FL position and clear radius, J4 body and mating side, heights, and the world ↔ KiCad transform |
| `layout/floorplan.py` | Region placement (ICs, power stages) and the anchor rules for passives. Keys are **atopile instance paths** (not designators), so a schematic edit that renumbers designators cannot silently move a group; `build_board.py` fails on a key that is not in the netlist |
| `layout/build_board.py` | Board from the netlist: stack-up, outline, holes and Ø8 keep-outs, placement (explicit + anchored passives, nothing within 3 mm of the U.FL), planes, buck pours, plane fan-out, silk text, project rules |
| `layout/fanout.py` | A via beside every SMD pad on `selv_gnd` / `v3v3` into its plane, keeping an escape lane for each neighbouring signal pin |
| `layout/build_schematic.py` | A netlist rendering (`pcb/controller.kicad_sch`) so KiCad's DRC can run schematic parity |
| `layout/route.py` | Routing driver (hash seed fixed, so the same placed board routes the same way): KiCad DRC gives the open pairs, `export_geom.py` dumps the copper, `gridroute.py` routes; up to three rounds. Then the **repair** step: for each pair still open it rips the unlocked copper within 3, then 5, then 8 mm of its ends and routes the stuck nets first. Then `cleanup.py`, more rounds if needed, and finally the outer GND pours and the designators |
| `layout/plane_islands.py` | Turns KiCad's "zone to zone" unconnected reports (the In2 v3v3 pour cut into islands by In2 tracks) into routable pairs: the nearest v3v3 vias of two islands |
| `layout/cleanup.py` | Removes copper that partial rips leave. The graph pass treats each track piece as a hyperedge on everything its ends lie in, as KiCad does; it deletes pieces that only close a loop and peels dangling chains. A second pass deletes exactly what KiCad's DRC lists as via/track dangling. Plane and pour nets are left alone |
| `layout/export_geom.py`, `layout/gridroute.py` | Copper dump (KiCad Python) and the router: F.Cu/In2.Cu/B.Cu on a 0.1 mm raster (preferred directions F along X, B along Y), clearance maps per width, A* with through vias and no corner cutting, exact shapely checks on pad escapes and pulled-tight segments, transactional negotiated rip-up, and a final exact legalisation of every segment and via against all copper, keep-outs and holes. The interlock block's box is a keep-out for MCU nets |
| `layout/silk.py` | Designators on silk where they fit (1.0 mm), otherwise F.Fab only |
| `layout/jlc_dfm_check.py` | JLC 1 oz multilayer limits (adapted from `power-stage-120v/tools/jlc_dfm_check.py`) |
| `layout/check_layout.py` | Enclosure constraints and the layout rules of the brief → `evidence/layout-check.json`; part groups by atopile path |
| `layout/fab.py`, `layout/review_fab.py` | Gerbers, drill, BOM/CPL, assembly drawing; independent gerbv review of the Gerbers |

**Router choice.** Freerouting 2.1.0 was tried on L1: its passes stalled for 10–16 min at a time, its CLI ignores the pass limit (`RouterSettings.stop_pass_no` is fixed at 999), and its best runs left 6–9 connections open. `gridroute.py` is deterministic and keeps the whole flow in this repository, with KiCad's DRC as the authority.

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

**Why four:** the board carries three sensitive analog front ends (the RTD MAX31865 and the ±1 µA thermal-sense nodes, the D-11 bus receiver into the ESP32 ADC, the AD8436 tank RMS) next to an ESP32 radio module, two 500 kHz bucks and two SPI buses. A continuous ground plane 0.21 mm under every F.Cu signal gives every return path a defined image, and the In2 3.3 V plane gives about 100 decoupling capacitors a one-via return each. On two layers the ground would be a pour broken by every crossing. **Why 1 oz:** the largest current is ≈ 0.9 A (v15_selv at peak, README power tree), which 1 oz carries on 0.4 mm outer tracks; it is JLC's standard 4-layer copper.

**One ground.** The schematic has one return net, `selv_gnd`, and no separate analog ground, so the board has one solid plane and the analog/digital partition is done by placement. A split would force every analog-to-ADC signal across a gap.

## Rules (JLC capability with margin)

JLC figures re-read 2026-10-09 from jlcpcb.com/capabilities/pcb-capabilities (multilayer, 1 oz): track/space 0.09/0.09 mm, PTH ring 0.15 mm minimum (0.20 recommended), via 0.15/0.25 mm, via hole-to-hole 0.2 mm, pad hole-to-hole 0.45 mm, NPTH ≥ 0.5 mm, copper to a routed edge ≥ 0.2 mm, silk text ≥ 1.0 mm.

| Rule | This board | Margin over JLC |
|---|---|---|
| Track | 0.15 mm signal, 0.3 mm v3v3 / plane stubs, 0.4 mm v15/v12/SW | ≥ 1.7× |
| Clearance | 0.15 mm (all net classes) | 1.7× (JLC 0.09 mm) |
| Via | 0.6/0.3 mm | ring 0.15 mm = 3× JLC's via rule |
| PTH ring | ≥ 0.20 mm (gate) | JLC recommended |
| Hole to hole | 0.5 mm | 2.5× (vias) / 1.1× (pads) |
| Copper to edge | 0.5 mm | 2.5× |
| Thermal relief | planes and pours connect PTH pads with reliefs (0.3 mm gap, 0.4 mm spokes, at least 1 spoke resolved); SMD pads solid | — |

`layout/jlc_dfm_check.py` is the power board's gate with its limits moved from 2 oz to these 1 oz values, plus an NPTH check. One footprint change: U20 (SN74LVC1G74DCU, VSSOP-8, 0.5 mm pitch) gets 0.28 mm pads instead of the library's 0.35 mm, which leave only 0.15 mm between pads; TI's DCU land is 0.25–0.30 mm wide. The WROOM courtyard is the module body + 0.25 mm.

## Floorplan (R33)

```
 rear Y90 ┌──────────────────────────────────────────────────────────────────────────────────────────────┐
          │J9 M12  J2 sink  o(-26,74)  thermal-sense    J1 coil  o(75,86)  12V buck   J10    J3 RTD       │
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
- **RTD front end** (MAX31865, REF2025, window comparators, TPS389001, Rref) between the module and J3, with the runaway comparator U10. The **12 V fan buck** (U2, L2) moved left to X 87…102 so it stays ≥ 10 mm from the RTD analog parts; its 12 V output runs to J10.

## Analog / digital partitioning

| Separation (courtyard to courtyard, `evidence/layout-check.json` partition) | mm |
|---|---|
| 12 V fan buck (L2/U2) → RTD front end (required ≥ 10, ENCLOSURE-HANDOFF item 6) | 10.1 |
| 12 V fan buck → thermal-sense block | 54.1 |
| 12 V fan buck → J4 analog (D-11, ct_mon, AD8436) | 75.9 |
| 3.3 V buck (L1/U1) → RTD front end | 78.7 |
| 3.3 V buck → thermal-sense block | 52.0 |
| 3.3 V buck → J4 analog | 36.0 |

The R33 floorplan moved the module and the RTD block, so these differ from L1. The 3.3 V buck's nearest analog neighbour is now 36.0 mm away (L1: 9.6 mm), and the fan buck sits 10.1 mm from the RTD analog parts (L1: 12.5 mm). It moved 23 mm left to give the RTD block room between the module and J3.

- **Switchers:** both bucks are compact. The VIN pour holds the input capacitors' supply pads against the VIN pin; the GND pin drops through its own via into In1 beside the input capacitors' ground vias; the SW node leaves its corner pin straight down into a 2.1 mm pour band that runs to the inductor, so the BST/SS/FB pins keep their side free for the bootstrap capacitor and the SS/FB parts.
- **High-impedance nodes** (HS_SENSE, COIL_SENSE, RIM_SENSE, the RTD sense pair, M12) run over the unbroken In1 plane, and none passes over a switch node.
- **MCU nets and the interlock:** the router treats the box of the six interlock logic ICs (world X-20.6…23.11, Y57.77…70.88) as a keep-out for MCU nets. `check_layout.py` confirms that no MCU net crosses it or the PERMIT-gate box, except the nets that end there by design (BUS_FAULT_RB, IL_RESET_N, IL_WDI, PERMIT_RB, RAIL_OK_RB, RUN_EN).

## Interlock trip path

Routed lengths (`evidence/layout-check.json` interlock): PERMIT 72.4 mm (U37 → J4.9 plus the read-back branch to U9), PERMIT_LATCH 49.3, bus_fault 89.2, all_good 37.0, reset_clock 41.6, latched_fault 54.4, RAIL_FAULT 34.1, SENSOR_LIVE 17.1, HS_FAULT 91.3, COIL_FAULT 97.3, RTD_HW_FAULT (`line`) 176.9, RUNAWAY_FAULT 148.4, RUN_EN 233.8 mm.

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
| DRC warnings | 27: connection_width 15, silk_edge_clearance 9, lib_footprint_mismatch 2, copper_sliver 1. connection_width is thin necks in zone fills; silk_edge_clearance is designators near the board edge; lib_footprint_mismatch is the two intended footprint edits (U20 pads, WROOM courtyard); copper_sliver is one acute corner in the B.Cu ground pour (fill minimum width 0.25 mm) | `evidence/drc.json` |
| JLC DFM (1 oz limits) | PASS: 723 vias, 2665 tracks, 64 plated pads, 2 NPTH, min track 0.15 mm | `evidence/jlc-dfm.json` |
| Enclosure + layout check | PASS on all 11 checks | `evidence/layout-check.json` |
| Fab review (gerbv) | PASS: 787 PTH hits, 2 NPTH, outline 206.0 × 76.0 mm | `evidence/fab-review.json` |
| Designators | 173 on silk, 58 on F.Fab only (all on the assembly drawing) | `evidence/silk-designators.json` |
| `tools/verify_controller.py` | PASS, 138 checks | `evidence/verify.json` |

**How the last connections were closed (L1 left 6 open).** The R33 floorplan takes the module out of the left half, which had been the congested band. Three routing tools in `route.py` then close the board:
- **Repair step:** it rips only the copper within 3–8 mm of each pair still open and routes the stuck nets first. The L1 ECO ripped whole crossing paths and cascaded.
- **`plane_islands.py`:** it turns KiCad's "zone to zone" reports (In2 v3v3 islands) into routable via pairs.
- **`cleanup.py`:** it removes the loops and dangling chains that partial rips leave. KiCad's own dangling list is the last word on dangling items.

**Enclosure constraints (R31 + R33 + R36 proposal), all checked by `layout/check_layout.py`:**
- outline X−38…168 / Y14…90, 1.6 mm, 4 layers: exact;
- six Ø4.0 holes at the R31 positions: exact; Ø8 keep-outs free of courtyards, pads, tracks, vias and fills;
- J1, J2, J3, J7, J9, J10, J12 body centres: 0.0 mm worst error; J7 body edges within 0.074 mm of the R33 box X29.8–62.2 / Y57.1–62.9; J3 body along the rear edge; J12 on its **proposed** R36 landing (126, 86);
- J4 courtyard X-38.01…-24.29 / Y27.795…57.005, mating −X at the left edge;
- WROOM-1U body X140.95…159.05 / Y50.25…69.55 (inside the R33 box, max edge offset 0.25 mm: the 19.2 mm module in the 19.5 mm box, flush with its rear edge), U.FL end at the rear, no other part within 3.0 mm of the U.FL;
- **U.FL position conflict (enclosure):** Espressif Figure 10-2 puts the receptacle 3.0 mm from the module's right edge, so on the R33 body box it is at (156.0, 67.04), not R33's (150, 67) (Δ 6.0 mm in X). The coax entry should move;
- heights (drawing-based, ENCLOSURE-HANDOFF table): mated XH 9.8 mm, J4 + plug 10.29 mm (series figure), J11 8.54 mm, all under the 15.4 mm allowance; C1 6.2, L1/L2 4.5, WROOM-1U 3.2 mm under the 6.4 mm allocation.

## Open items

1. **Release:** the board is a candidate, not released. Ordering is the owner's call.
2. **U.FL position (enclosure):** the coax entry moves to about (156, 67), per Espressif Figure 10-2 (Results).
3. **J12 landing (enclosure, R36):** the rim-NTC header is placed at the proposed (126, 86); the enclosure must confirm it or give a position.
4. **J4 drawing:** the 43045-1600 sales drawing (430451600_sd.pdf) could not be fetched; molex.com refuses this network. The mated height 10.29 mm is Molex's figure for the same right-angle THT series (43045-2001); the plug's −X overhang (R31: to X−50) is still unread.
5. **R32 controller additions not yet designed in** (DECISIONS open item 12): an adjustable 5.5–12 V ≥ 1.5 A blower output, and differential RC ≤ 1 kHz on the RTD/NTC inputs.
6. **CPL rotations:** KiCad's rotations are written as-is; check each package in JLC's placement preview before ordering.
7. **Consigned / low-stock parts** (DECISIONS open item 7): AD8436BRQZ (JLC stock 0) and the near-zero-stock ported parts; `fab/fab-notes.md` lists them.
8. **Block validators:** re-run the interlock, thermal-sense and RTD validators on this layout (DECISIONS item 9); not done here (no Rust builds in this task).
9. **Long lines:** RUN_EN and the RTD trip inputs cross most of the board (Interlock trip path). All fail safe on a break; a bench noise check on them is worth adding.
10. **In2 use:** In2 carries some signal tracks where F/B were full; the v3v3 pour refills around them, and `plane_islands.py` re-joins any v3v3 island; DRC shows v3v3 as one connected net.
11. **Firmware pins.h:** RUN_EN 14; RTD_DRDY expander P07; SUP_RUN_OK expander P14; UI SPI 40/41/44/47/48/45; I²C SDA 37 / SCL 0; RIM_ADC 9.
