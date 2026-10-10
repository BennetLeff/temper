# Controller PCB layout (L1, enclosure R31)

This is the first layout of the integrated SELV controller: 225 parts, 4 layers, 206 × 76 mm, placed and routed by scripts from `frozen/default.net`, with a JLCPCB fab package. Nothing was drawn by hand in the KiCad GUI.

**Status: NOT complete — 6 connections are still unrouted** (listed under Results), so the board is not DRC-clean and the fab package is marked *not for order*. Everything else passes: 0 DRC errors, schematic parity 0, JLC DFM PASS, every enclosure check PASS, gerbv fab review PASS. Not fabricated. Every number below comes from a file in `evidence/` that `python3 layout/make.py` regenerates: `drc.json`, `jlc-dfm.json`, `layout-check.json`, `fab-review.json`, `silk-designators.json`.

**Enclosure revision:** R31 (`output/temper-manufacturing-r31/design/r31/CONTROLLER-SPEC.md`, "R31" section, with R30's mounting and heights). R31 mirrors the assembly about X = 0, so J4 is on the left edge mating −X, the WROOM sits behind the lens window, and J7 is merged into a 4-pin J8 (DECISIONS C24, C25). **All enclosure numbers live in one table, `layout/world.py`**; a new revision is an edit there plus a re-run.

## Rebuild

From `zapote/controller` (KiCad 10.0.4 and its bundled Python; system Python 3 with numpy, scipy, shapely and Pillow; gerbv for the fab review; offline; no Rust or workspace build):

```sh
python3 layout/make.py             # place, plane fan-out, route, DRC, DFM, enclosure check, fab, fab review
python3 layout/make.py --no-route  # same, reusing pcb/controller-routed.kicad_pcb (routing is the slow step)
python3 tools/verify_controller.py # schematic verification
```

| Script | Does |
|---|---|
| `layout/world.py` | **The parameter table:** outline, holes and keep-outs, connector centres, J4 body and mating side, WROOM box and antenna keep-out, heights, and the world ↔ KiCad transform |
| `layout/floorplan.py` | Region placement (ICs, power stages) and the anchor rules for passives; connector/J4/module poses are read from `world.py` |
| `layout/build_board.py` | Board from the netlist: stack-up, outline, holes and Ø8 keep-outs, placement (explicit + anchored passives), planes, buck pours, plane fan-out, silk text, project rules |
| `layout/fanout.py` | A via beside every SMD pad on `selv_gnd` / `v3v3` into its plane, keeping an escape lane for each neighbouring signal pin |
| `layout/build_schematic.py` | A netlist rendering (`pcb/controller.kicad_sch`) so KiCad's DRC can run schematic parity |
| `layout/route.py` | Routing driver: KiCad DRC gives the open pairs, `export_geom.py` dumps the copper, `gridroute.py` routes; up to three rounds; then the outer GND pours and the designators. `--continue` resumes on `pcb/route/work.kicad_pcb`; `--eco` adds rip-and-reroute cycles (it did not converge here and is off by default) |
| `layout/export_geom.py`, `layout/gridroute.py` | Copper dump (KiCad Python) and the router: F.Cu/In2.Cu/B.Cu on a 0.1 mm raster (preferred directions F along X, B along Y), clearance maps per width, A* with through vias and no corner cutting, exact shapely checks on pad escapes and pulled-tight segments, transactional negotiated rip-up, and a final exact legalisation of every segment and via against all copper, keep-outs and holes. The interlock block's box is a keep-out for MCU nets |
| `layout/silk.py` | Designators on silk where they fit (1.0 mm), otherwise F.Fab only |
| `layout/jlc_dfm_check.py` | JLC 1 oz multilayer limits (adapted from `power-stage-120v/tools/jlc_dfm_check.py`) |
| `layout/check_layout.py` | Enclosure constraints and the layout rules of the brief → `evidence/layout-check.json` |
| `layout/fab.py`, `layout/review_fab.py` | Gerbers, drill, BOM/CPL, assembly drawing; independent gerbv review of the Gerbers |

**Router choice.** Freerouting 2.1.0 (`/Users/bennet/tools/freerouting.jar`) was tried first. On this board its passes stalled for 10–16 min at a time in four runs (also with its original settings), its CLI ignores the pass limit (`RouterSettings.stop_pass_no` is fixed at 999), and its best runs left 6–9 connections open. `gridroute.py` is deterministic and keeps the whole flow in this repository, with KiCad's DRC as the authority. It also leaves 6 connections open (Results); a full run takes about 2 h on this machine.

## Coordinates

World (appliance) mm, X right, Y rear, viewed from above. KiCad frame: **kx = X + 58, ky = 110 − Y** (`layout/world.py`). The board's rear-left corner, world (−38, 90), is KiCad (20, 20); the front-right corner, world (168, 14), is KiCad (226, 96). This is a translation plus the y-flip of KiCad's y-down screen; the top side stays on top (no mirror). Gerber Y = −ky, so world Y = 110 + Gerber Y. Every part's world pose is in `pcb/placement.json`.

## Stack-up: 4 layers, 1 oz outer

JLC JLC04161H-7628, 1.6 mm: F.Cu 1 oz (0.035) / 0.21 prepreg / In1.Cu 0.5 oz / 1.065 core / In2.Cu 0.5 oz / 0.21 prepreg / B.Cu 1 oz.

| Layer | Use |
|---|---|
| F.Cu | All parts; signals; buck VIN/SW pours; `selv_gnd` pour in the gaps |
| In1.Cu | Solid `selv_gnd` plane, cut only by the antenna keep-out and the six Ø8 snap-in keep-outs |
| In2.Cu | `v3v3` pour (same cuts); also a third routing layer where F/B are full, the pour refilling around those tracks |
| B.Cu | Signals; `selv_gnd` pour in the gaps |

**Why four:** the board carries three sensitive analog front ends (the RTD MAX31865 and the ±1 µA thermal-sense nodes, the D-11 bus receiver into the ESP32 ADC, the AD8436 tank RMS) next to an ESP32 radio, two 500 kHz bucks and SPI/OLED clocks. A continuous ground plane 0.21 mm under every F.Cu signal gives every return path a defined image, and the In2 3.3 V plane gives about 100 decoupling capacitors a one-via return each. On two layers the ground would be a pour broken by every crossing. **Why 1 oz:** the largest current is ≈ 0.9 A (v15_selv at peak, README power tree), which 1 oz carries on 0.4 mm outer tracks; it is JLC's standard 4-layer copper.

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

The signal rules started at 0.2/0.2 mm and were tightened to 0.15/0.15 mm (still 1.7× JLC's 1 oz multilayer minimum) to give the router capacity around the module. `layout/jlc_dfm_check.py` is the power board's gate with its limits moved from 2 oz to these 1 oz values, plus an NPTH check. One footprint change: U20 (SN74LVC1G74DCU, VSSOP-8, 0.5 mm pitch) gets 0.28 mm pads instead of the library's 0.35 mm, which leave only 0.15 mm between pads; TI's DCU land is 0.25–0.30 mm wide. The WROOM library courtyard (which also encloses the antenna keep-out) is replaced by the module body + 0.25 mm; its antenna rule area is kept unchanged.

## Floorplan (R31)

```
 rear Y90 ┌────────────────────────────────────────────────────────────────────────────────────────────┐
          │J9 M12  J2 sink  o(-26,74)  thermal-sense block      J1 coil   o(75,86)   12V buck  J10  J3 RTD │
          │J5 enc  UI(U16,U17)           U7         J6 OLED                          (U2,L2)  RTD front  │
     ┌────┤        interlock U20-U25 ............. trip glue                                   end + U10 │
  J4 │ -X │ U37   D-11  ct_mon  AD8436  MCP3202  U9   U8                                     o(164,80)  │
     │    │ PERMIT       J8 buttons                                                                      │
     └────┤        ┌WROOM┐            3.3V buck (U1,L1)        J11 dbg     TEMPER CONTROLLER / SELV        │
 front Y14└──o─────┴ant.─┴──────────────────────────o(65,18)───────────────────────────────o(164,18)─────┘
          X-38    X-20 X-2                                                                       X168
```

- **Fixed by the enclosure** (checked by `check_layout.py`): the outline, the six Ø4.0 snap-in holes with Ø8 copper/part keep-outs, the connectors at their R31 centres, J4 in its body envelope at the left edge mating −X, and the WROOM at X−20…−2 / Y14…39.5 with its antenna at the front edge.
- **J4 side (left):** J4.9/J4.10 (PERMIT, bus_fault) sit at the header's front end. The PERMIT gate U37 (latch AND RUN_EN, C23) and its 10 kΩ pull-down sit in front of J4, next to J4.9; the 4 mm strip between J4 and the module is kept free of parts (`floorplan.CHANNELS`) because it is the only escape for the module's left-side pins. The D-11 receiver (U5, LM4040, 0.1 % resistors) sits at J4.11/12, the ct_mon buffer U6 at J4.14, the PWM pull-downs and the ct_zc/line_zc 1 kΩ at J4, and the AD8436 and its MCP3202 beside them.
- **Interlock block** (U20 latch, U21 watchdog, U22 HC30, U23/U24 LVC14, U25 and their pull-ups/bypasses) is grouped behind the J4 analog parts, with the trip glue (U3 rail window, U11 SENSOR_LIVE, U12 RAIL_FAULT) on its right. The read-back buffer U9 sits inside the block row; its outputs are the only interlock-to-MCU nets. The area directly behind the module is a reserved routing channel for the module's rear-row pins.
- **ESP32** at the front edge behind the lens window (fixed); the expander U8 and the I²C/strap pull-ups to its right; the 33 Ω PWM resistors and the ADC anti-kick RCs at its pads. The AD8436 (U14) and its MCP3202 (U15) sit right of the module, ≥ 9.6 mm from the 3.3 V buck.
- **3.3 V buck** (U1, L1) at the front (X 28…50), right of the antenna keep-out; v15 runs to it from J4.1 and the v3v3 plane carries its output back to J4.3.
- **Thermal-sense block** between J2 (X−20) and J1 (X55) at the rear, with its buffer U7.
- **RTD front end** (MAX31865, REF2025, window comparators, TPS389001, Rref) beside J3 at the rear right, with the runaway comparator U10 (both its inputs are RTD nodes; its output is a digital trip line with the interlock's 10 kΩ pull-up, so a break reads as a fault). The **12 V fan buck** (U2, L2) sits beside J10.
- **UI:** the encoder buffer U17, the 5 V LDO U16 and its droppers beside J5; the button series resistors at J8.

## Analog / digital partitioning

| Separation (courtyard to courtyard, `evidence/layout-check.json` partition) | mm |
|---|---|
| 12 V fan buck (L2/U2) → RTD front end (required ≥ 10, ENCLOSURE-HANDOFF item 6) | 12.5 |
| 12 V fan buck → thermal-sense block | 77.1 |
| 12 V fan buck → J4 analog (D-11, ct_mon, AD8436) | 98.8 |
| 3.3 V buck (L1/U1) → RTD front end | 94.7 |
| 3.3 V buck → thermal-sense block | 52.0 |
| 3.3 V buck → J4 analog | 9.6 |

- **Switchers:** both bucks are compact. The VIN pour holds the input capacitors' supply pads against the VIN pin; the GND pin drops through its own via into In1 beside the input capacitors' ground vias; the SW node leaves its corner pin straight down into a 2.1 mm pour band that runs to the inductor, so the BST/SS/FB pins keep their side free for the bootstrap capacitor and the SS/FB parts.
- **High-impedance nodes** (HS_SENSE, COIL_SENSE, the RTD sense pair, M12) run over the unbroken In1 plane, and none passes over a switch node or the antenna keep-out.
- **MCU nets and the interlock:** the router treats the box of the six interlock logic ICs (world X−20.6…23.1, Y57.8…70.9) as a keep-out for MCU nets, and `check_layout.py` confirms that no MCU net crosses it or the PERMIT-gate box, except the nets that end there by design (IL_RESET_N, IL_WDI, RUN_EN and U9's read-back outputs).

## Interlock trip path

Routed lengths (`evidence/layout-check.json` interlock): PERMIT 62.4 mm (U37 → J4.9 plus the read-back branch to U9), PERMIT_LATCH 50.2, RUN_EN 32.1, bus_fault 47.0, all_good 38.5, reset_clock 48.3, latched_fault 19.4, RAIL_FAULT 30.9, SENSOR_LIVE 17.1, HS_FAULT 46.2, COIL_FAULT 75.6, RTD_HW_FAULT (`line`) 204.7, RUNAWAY_FAULT 176.0 mm.

The inputs from distant blocks (RTD_HW_FAULT and RUNAWAY_FAULT from the RTD block beside J3, HS_FAULT/COIL_FAULT from the thermal block) are long because R31 puts J3 at the far right and J4 at the far left; each fails safe on a break (pull-up to the fault level at the interlock input) and none is reachable by firmware (`verify_controller.py` trip checks).

## Decoupling

Every IC supply pin (the "vcc" pins of `verify_controller.py`'s part models) has a capacitor to `selv_gnd` on the same net within 2.94 mm (worst of 36 supply pins; limit 5 mm). Each capacitor's ground pad has its own via to In1 and each 3.3 V pad its own via to In2.

## Results

| Gate | Result | Evidence |
|---|---|---|
| KiCad DRC errors | **0** | `evidence/drc.json` |
| Unconnected items | **6 — NOT routed** (below) | `evidence/drc.json` |
| Schematic parity | 0 | `evidence/drc.json` |
| DRC warnings | 31: connection_width 15 (zone necks), silk_edge_clearance 11, lib_footprint_mismatch 2 (the two intended footprint edits: U20 pads, WROOM courtyard), silk_overlap 2, silk_over_copper 1 | `evidence/drc.json` |
| JLC DFM (1 oz limits) | PASS: 677 vias, 2638 tracks, 68 plated pads, 3 NPTH, min track 0.15 mm | `evidence/jlc-dfm.json` |
| Enclosure + layout check | PASS on all 11 checks | `evidence/layout-check.json` |
| Fab review (gerbv) | PASS: 745 PTH hits, 3 NPTH, outline 206.0 × 76.0 mm | `evidence/fab-review.json` |
| Designators | 157 on silk, 68 on F.Fab only (all on the assembly drawing) | `evidence/silk-designators.json` |
| `tools/verify_controller.py` | PASS, 118 checks | `evidence/verify.json` |

**The 6 unrouted connections** (world mm): ENC_A U17.6 (−16.9, 75.0) → U4.24 (−15.4, 39.3); ENC_B U17.4 (−16.9, 73.0) → U4.25 (−16.7, 39.3); SUP_RUN_OK_RB U4.30 (−19.8, 34.2) → U9.14 (−1.6, 65.5); HS_FAULT_RB U9.5 (−7.4, 66.8) → U8.15 (38.9, 47.7); RTD_FAULT_RB U9.7 (−7.4, 65.5) → U8.14 (38.9, 47.1); rtd_healthy U23.10 (−14.7, 69.5) → U22.5 (8.7, 64.1). All six sit in the dense band between the module's rear row and the interlock block; the router's rip-up and ECO cycles did not converge there (two ECO attempts went from 6 to 8–11 open). Finishing them by hand in KiCad is a short job, or the floorplan can give that band more room (move U8, U17 and the UI parts right, into the empty X 40…130 area).

**Enclosure constraints (R31), all checked by `layout/check_layout.py`:**
- outline X−38…168 / Y14…90, 1.6 mm, 4 layers: exact;
- six Ø4.0 holes at the R31 positions: exact; Ø8 keep-outs free of courtyards, pads, tracks, vias and fills;
- J1, J2, J3, J5, J6, J8, J9, J10 body centres: 0.00 mm error each; J3 body along the rear edge;
- J4 courtyard X−38.01…−24.29 / Y27.80…57.01 (≤ 0.01 mm from the brief's box), mating −X at the left edge, pin 1 at (−28.57, 31.90);
- WROOM body X−20.05…−1.95 / Y14.0…39.6 (≤ 0.1 mm), antenna end at the front edge; Espressif keep-out (X−35…13, Y ≤ 20.05) intact and free of copper on every layer;
- heights: XH 7.0 mm and Micro-MaTch 4.3 mm under the 15.4 mm allowance (R30 board top Z24.6); C1 6.2, L1/L2 4.5, WROOM 3.25 mm under R28's 6.4 mm allocation.

## Open items

1. **Finish the routing (blocking).** Six connections are open (Results). Until they are routed the board must not be ordered; `fab/fab-notes.md` says so.
2. **Antenna keep-out vs hole (−34, 18) — enclosure.** Espressif's keep-out (KiCad's WROOM rule area: 15 mm beyond the antenna end and both module sides) contains the R31 hole at (−34, 18), 14 mm from the module's side. The layout keeps the keep-out free of copper on every layer, the hole is a copper-free milled cutout, and the R30 support is an all-nylon snap-in, so there is no metal there. Moving the hole ≥ 19 mm from the module side (X ≤ −39, off the board) is not possible on this outline, so the enclosure should confirm the nylon-only condition. Range is unqualified anyway (bench test E4).
3. **J4 envelope.** The courtyard matches the R31 box, but Molex's drawing for the 43045-1600 height and the mated plug (R31: plug to X−50; it mates native-21's J4 at X−109…−83, Y51…58.4, Z37.6…47.4) is still unread (DECISIONS C17).
4. **Long trip lines.** RTD_HW_FAULT (205 mm) and RUNAWAY_FAULT (176 mm) cross the whole board because R31 places J3 at the far right and J4 at the far left. Both fail safe on a break; a bench check of noise pick-up on them is worth adding.
5. **Heights not from drawings:** J4 with its plug, J11 (bring-up only) and the mated XH plugs.
6. **CPL rotations:** KiCad's rotations are written as-is; check each package in JLC's placement preview before ordering.
7. **Consigned / low-stock parts** (DECISIONS open item 7): AD8436BRQZ (JLC stock 0) and the near-zero-stock ported parts; `fab/fab-notes.md` lists them.
8. **Block validators:** re-run the interlock, thermal-sense and RTD validators on this layout (DECISIONS item 9); not done here (no Rust builds in this task).
9. **WROOM exposed-pad vias:** the library footprint's nine 0.2 mm vias in pad 41 are tented on the bottom by design; the fab review treats them as vias.
10. **In2 use:** In2 carries some signal tracks where F/B were full; the v3v3 pour refills around them and v3v3 stays one connected net (DRC). An In2 signal sits 1.07 mm from In1 GND and 0.21 mm from B.Cu, so its return path is the B.Cu pour; acceptable for these slow lines.
11. **Firmware (C23):** RUN_EN on GPIO14 and RTD_DRDY on TCA9555 P07 need the pins.h update.
