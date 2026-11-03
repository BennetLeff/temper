# Gerber netlist check (Rev F)

DRC runs on `cad/temper-lcr.kicad_pcb`. JLC builds from the Gerber and drill files instead, so this check reads
those files and confirms their copper has the schematic's connectivity, with no shorts and no opens.

Run from `instruments/lcr-meter/`:

```sh
uv run --script validation/gerber-netlist/gerber_netlist_check.py --self-test
```

It needs `uv` and `kicad-cli` (used only to export the schematic netlist) and takes about 7 s. It writes
`gerber-netlist-check.json` and exits 0 only if the check passes and all three self-test mutations are caught.

## How it works

1. **Copper from the fab files only.** It reads the four copper Gerbers and `PTH.drl`/`NPTH.drl` from
   `manufacturing/temper-lcr-gerbers.zip`, the file uploaded to JLC. The zip is gitignored, so on a fresh checkout
   the script reads the tracked `manufacturing/gerbers/` instead (the bytes are the same). Gerbonara parses
   RS-274X and Excellon. The script turns every flash, draw and region into an exact shapely polygon and applies
   them in file order with their dark or clear polarity. Zone fills, thermal reliefs and teardrops all arrive
   as regions. Each layer is then unioned into separate copper pieces.
2. **Layers joined through plated holes.** A PTH hole, or routed slot, connects every copper piece its barrel
   touches on any layer. Union-find over the pieces gives the board's copper components.
3. **Labels.**
   - Pad and via positions, sides and drill sizes come from the IPC-D-356 file: the `.d356` inside the zip
     once `rebuild.sh` puts it there, otherwise `build/temper-lcr.d356`.
   - The net of record for each pad comes from the schematic netlist by (reference, pin), not from the board.
     The IPC net name is only cross-checked against it.
   - SMD pads map to the copper piece under their centre. Through pads and vias map through the drill hole at
     their centre.
   - The 21 TestPoint pads are board-only footprints with no schematic symbol. They take the schematic net that
     their IPC name resolves to.
4. **Assertions.**
   - No component holds pads of two nets (short).
   - Every schematic net with two or more placed pads lands in exactly one component (open).
   - Every pad has copper under it.
   - Every IPC through pad or via has a PTH drill of the right size, and every PTH drill has an IPC record.
   - Every via's IPC net agrees with the pads it shares copper with.
5. **Reported.** The check also reports copper with no pad (floating, or via-only), NPTH holes that cut
   copper, and the smallest gap between different-net copper on each layer.

The 40 `unconnected-(...)` nets are the only single-pin nets, and they are checked only for shorts.

**Geometry resolution.** No raster is used. Circles and arcs are polygonised as inscribed polygons with a chord
error of at most 0.5 µm. Copper can only shrink, by 0.5 µm or less, so polygonisation cannot invent a short.
It could hide a real bridge only if that bridge were under 1 µm, far below anything that etches. The smallest
different-net gap the check measures is 0.150 mm, 300 times the chord error.

Two internal sanity values are recorded in `geometry_sanity`:
- Region areas against the shoelace formula: worst relative difference 2e-10.
- Every RoundRect pad flash against its convex hull: worst 3e-15 mm². This confirms the rotated vector-line
  primitives in the macro are oriented correctly.

## Result (2026-11-03, board SHA256 4908921…a76ca)

| | |
|---|---|
| Copper pieces F / In1 / In2 / B | 542 / 177 / 185 / 183 |
| PTH holes (of which slots) / NPTH | 469 (4) / 6 |
| IPC records: pads / vias | 701 / 439 (all 469 PTH matched, no extra drills) |
| Copper components | 171 = 128 multi-pin nets + 40 single-pin nets + 3 fiducials |
| Nets checked for opens | 128 |
| **Shorts** | **0** |
| **Opens** | **0** |
| Pads off copper, IPC/schematic name mismatches, via net mismatches | 0, 0, 0 |
| Floating copper / via-only copper | 0 / 0 |
| NPTH holes cutting copper | 0 (closest copper 0.220 mm on F.Cu, 0.200 mm inner and B.Cu) |
| Min different-net gap F / In1 / In2 / B | 0.150 / 0.155 / 0.150 / 0.150 mm |

Every component carries pads, so there is no floating copper and no dangling via.

## Self-test (`--self-test`)

Each mutation edits a copy of the Gerber text in memory and reruns the full check.

| Mutation | Expected | Result |
|---|---|---|
| 0.10 mm draw on F.Cu between the two closest different-net SMD pads (U1-3 to U1-4, 0.40 mm apart) | short I2S_DIN + `unconnected-(U1-GPIO1-Pad3)` | FAIL, short reported: caught |
| F.Cu line 6268, the only track joining R107-2 and K4-7 (2.8 mm), turned from a draw into a move | open on REF_A | FAIL, open reported: caught |
| 0.5 mm flash on empty B.Cu at (38, 43) | one floating island there | reported: caught |

The open test cuts the longest single-segment two-pad track on purpose. An earlier pick was the 1.39 mm track
between R117-1 and D19-2, and the checker correctly kept it connected. The two pads' teardrop regions overlap
(y 36.93–37.73 and 37.44–38.31), so the copper still joins without the track.

## Not covered

- No LPC (clear polarity) or G02/G03 arcs appear in this copper. The code handles both, but neither is
  exercised by these files.
- The check proves connectivity, not clearances. The minimum-gap figures are a cross-check, not a DRC.
- The schematic netlist is exported fresh on every run and carries a timestamp, so its SHA256 changes between
  runs. The schematic file's SHA256 is the stable input.
- The IPC positions come from the board, so they only label the copper. A wrong label could not hide a short:
  a mislabelled pad lands on copper whose other pads carry their own schematic nets, and the conflict shows.

## IPC-D-356 netlist for JLC

`cad/rebuild.sh` now exports `manufacturing/gerbers/temper-lcr.d356`. `cad/archive_package.py` zips everything
in that folder except PDFs, so the file goes into `temper-lcr-gerbers.zip` with no other change.

JLC's own pages recommend sending an IPC-D-356(A) netlist with the Gerbers:
- <https://jlcpcb.com/blog/bare-pcb-quality-guide> (updated 2026-10-10): "Send it, and the shop tests your copper
  against your schematic. Send Gerbers alone, and the shop extracts a netlist from the artwork instead…" The
  same page says every board gets 100 % AOI and electrical testing, by flying probe or bed-of-nails.
- <https://jlcpcb.com/blog/clean-pcb-netlist-foundation> (updated 2026-10-28): submitting an IPC-D-356 netlist
  with the order lets JLC engineers "cross-validate the connectivity that was extracted from your Gerber files
  with your design intent."

I found no JLC help-centre page that says how to submit the netlist (a separate upload field, or a file name
inside the zip). A KiCad forum thread (<https://forum.kicad.info/t/verify-gerbers-with-netlist/35700>) reports
that JLC's free test compares Gerber-extracted connectivity and needs no netlist. So include the `.d356` in the
zip and add an order remark naming it. Do not assume JLC's test uses it unless they confirm.
