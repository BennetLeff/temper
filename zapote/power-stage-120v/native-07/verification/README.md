# Native-07 verification, 2026-09-26

Board SHA-256: `68fb52346a16a809ddd19ee685337217685d0fb17dc6061b291baaf004ffbb18`.
Native-07 is native-06 plus two BUS_P copper changes made for D4 condition 1
(see [DECISIONS.md](../../DECISIONS.md)). It is replayed from the unchanged
native-05 placement with `tools/route_board.py`; no part moved. This is not a
fabrication or powered-operation release.

## Changes from native-06 (`routes/routes-01.json`)

1. **Local row.** The LEG_RET via row by R5 moves from y 7.4 to y 4.3; its F.Cu
   pour extends to y 3.4 and stays clear of Kelvin pad R5.2. The via holes in the
   In2 BUS_P plane now merge with the TO-247 pin holes, so the 3.2 mm BUS_P branch
   at x 125.75 is gone.
2. **Western neck.** A B.Cu BUS_P pour (x 56–84, y 0.6–11.5) runs parallel to
   the In2 neck at x ~74. It is stitched to In2 by three 1.6/0.8 mm vias at each
   end (x 58.5 and 81.5, y 2.5/4.5/6.5).

## Results

| Check | Result | Evidence |
| --- | --- | --- |
| Full KiCad DRC, fill + three repeats | 0 copper/clearance/courtyard findings; 0 schematic mismatch; 28 library + 3 silk warnings (unchanged); board bytes unchanged across repeats | `drc-fill.json`, `drc-1.json`–`drc-3.json` |
| Opens | Only the intended R5 Kelvin split. The pad clusters are identical to native-06 | `connectivity.json` |
| Source/native identity | PASS: 114 parts, 313 source pins | `source-parity.json` |
| Saved track/via identity | PASS: 560 tracks, 147 vias (native-06 had 141) | `copper-identity.json` |
| Stackup gate | pass, 4 layers | `stackup.json` |
| All-layer 8 mm barrier | 0 hits | `barrier.json` |
| Hardware surface | 0 hits, normal and bring-up | `hardware-surface.json` |
| Board tests | 43/43, with the native parity and copper-identity binaries on the path | — |

## Power screen (same method as native-06's power review)

The screens use nominal IPC-2221B at a 20 °C rise, with 70 µm treated as 2 oz. They
are width screens, not thermal or via ratings.

| Path | native-06 | native-07 |
| --- | --- | --- |
| In2 BUS_P local row (19 A assumed, DC sheet solve) | worst: 5.86 A in 3.197 mm at x 125.75; demand/screen **0.945** | worst: 12.12 A in 10.87 mm at x 130.25; demand/screen **0.805**. Upper branch now carries 6.88 A in a wider section |
| Western BUS_P neck (15 A) | In2 only, 11.70 mm at x 73.9; **0.945** | In2 + B.Cu between the stitch banks; worst x 61.1 (7.3 + 7.3 mm in the y 0.5–15 window, which undercounts In2); demand/screen **0.443** |
| SW_B B.Cu tank strip | 8.4995 mm | unchanged |

Scripts: `power-probes/final49-bus-sheet.py` (local row), `geometry_via_screen.py`
(In2-only western and tank sections), and `west_parallel_screen.py` (In2 plus
B.Cu). They read `../copper.json`. The outputs are `bus-sheet.txt`,
`geometry-via.json` and `west-parallel.json`.

## Limits

The parallel screen sums each layer's independent screen. It does not model
how current actually shares between In2 and B.Cu, and it gives no via-bank
current rating. The finished copper and plating, thermal/current qualification,
and every native-06 open item still apply. Copper previews were not regenerated.
