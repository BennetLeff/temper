# M11 heatsink stack: build-order sweep (2026-10-18)

`check_stack_build.py` sweeps each part of the HOT-to-PE heatsink stack into its seat along a stated direction, against everything installed before it. The
enclosure checker (`output/temper-manufacturing-r43/src/check_assembly_sequence.py`, PASS_SCOPED_SEQUENCE_SCREEN, re-run on a copy 2026-10-18) moves the
**finished** stack up 120 mm into the enclosure as one rigid subassembly; this checks how the stack itself goes together on the bench.

Run (R43 is read-only; nothing is written there): `uv venv -p 3.12 cadenv && VIRTUAL_ENV=cadenv uv pip install build123d==0.11.1`, then
`cadenv/bin/python check_stack_build.py --controls --explore` (about 20 minutes). Result: `result.json`.

## Result: the proposed order is clear (status CLEAR)
Direction = where the part arrives from (+Z = above, moving down). Board and FET proxy envelope fixed on the bench first.

| Step | Parts | Arrives from | Clear |
|---|---|---|---|
| 1 | AlN tiles A and B on the tab faces (held by hand or tape until clamped) | above (+Z), 60 mm | yes |
| 2 | BR1 gap pad | above | yes |
| 3 | FR-4 pressure strip behind the FET bodies | above | yes |
| 4 | Spreader bar with the sink envelope (one PE metal subassembly) | the sink side (+Y), 80 mm | yes |
| 5 | Clamp comb | above | yes |
| 6 | Bar bond screws M4 (they lie along Y) | the board side (-Y), 60 mm | yes |

**Controls (the checker is only trusted because these behave):** tile A from the board side runs through the FET bodies: blocked. The strip from the tile side
runs through the FET bodies: blocked. Tile A from above with only the board installed: clear.

**Free arrival directions** for each part, with the proposed predecessors installed (`result.json` `explore`):
tile A: above, the sink side, or -X; tile B: above or the sink side; gap pad and strip: **above only**; bar and sink: any except the board side; comb: above, -X or -Y;
screws: **the board side only** (from above or from either end they hit the sink).

## What this does and does not show
- The strip and the gap pad can only go in from above, so the stack cannot be built with a cover or a heatsink duct over the FET row. The screws need access along Y from the
  board side, and their clearance over the comb is only 0.9 mm (screw bottom Z 73.5, comb top 72.6) in CAD.
- The FETs are the R43 components **envelope proxy**, not the TO-247 outline; the sink is a solid envelope (no tapped holes, so the screw seat is an accepted overlap, allowed up to its seated volume).
- Not modelled: the comb spring's deflection, paste or tape, the tools and the driver's reach, tolerance stack-up, and the order the real build would use. The tiles have nothing holding them
  until the bar and comb are on (step 1 relies on hand or tape): a fixture or tape is a build-procedure decision, not in the CAD.
- R43's own checker skips every pair its metadata accepts as overlapping at the seat; that makes sweeps against those pairs blind. This one allows the seated volume (+0.5 mm3) and no more. The R43 checker
  is unchanged (frozen revision).
