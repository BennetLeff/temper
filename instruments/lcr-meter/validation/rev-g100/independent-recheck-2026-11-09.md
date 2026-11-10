# Rev G100 re-check: 5V corner re-route at H3

Date 2026-11-09. Independent re-check of `cad/` + `gerbers/` against `prev/` (the board as reviewed before).
Everything below was re-derived with the scripts in `work/` (KiCad 10.0.4 pcbnew Python for geometry export,
system Python 3.12 + shapely 2.1 for analysis, `kicad-cli` for DRC and re-export). Raw outputs are in `work/*.json`.

## Verdict

**The fix is clean. The board is orderable.** The only copper that changed is the 5V run around H3; it is
continuous, carries 1.17 A at ≤ 10 °C by IPC-2152, keeps B.Cu copper ≥ 3.5 mm from H3, keeps copper ≥ 0.4 mm from
the edge on every layer, clears the H3 hole and every other net, passes the project DRC with 0 errors and the JLC
profile with 0 failures, and the shipped Gerber / drill / D-356 set is a byte-identical re-export of `cad/`.
Two zero-margin items and two pre-existing notes are listed under Findings; none blocks the order.

## 1. Diff prev → current (`work/dump_board.py`, `diff_boards.py`, `copper_delta.py`, `gnd_delta_pieces.py`)

| What | prev | cur | Difference |
|---|---|---|---|
| Footprints (282), pads, values, positions, DNP | — | — | identical |
| Nets (180), netclasses, layer set, board rules | — | — | identical |
| Graphics / text / Edge.Cuts (66 items) | — | — | identical |
| Schematics, symbol lib, footprint lib | — | — | byte-identical (`cmp`) |
| Zone outlines / settings (1205 layer-zones) | — | — | identical |
| Tracks | 1939 | 1941 | 7 removed, 9 added, **all net 5V, all inside x 51–58 / y 136–145** |
| Vias | 435 | 435 | 3 moved (5V): (51.2,136.8)→(51.2,138.4); (56.6,144.0)→(57.0,143.4); (57.4,144.0)→(57.0,144.2) |
| GND fill | — | — | only re-flows around the moved copper; every changed piece > 1e-4 mm² has its bbox inside x 50.5–58, y 136–144.5 (In1 +0.19 mm², In2 −5.5 mm², B.Cu −1.1 mm²) |

Per-net copper symmetric difference per layer is non-zero only for 5V (corner) and GND (corner re-flow).
Nothing beyond the corner re-route changed. `routing.json` / `design.json` differ only in the same 5V segments.

## 2. The fix (`work/analyze_geom.py`, `ampacity.py`)

**New corner geometry (net 5V):** B.Cu 0.6 mm at x 51.2 now ends at y 138.4 → vias (51.2,137.6) and (51.2,138.4)
→ In2.Cu **1.6 mm** (51.2,137.6)–(51.2,143.0) → 45° (52.0,143.8) → (57.0,143.8) → vias (57.0,143.4) and
(57.0,144.2) → B.Cu 0.6 mm (57.05,144.25)–(92.0,144.25). Two vias at each layer change (as the intent asks).

**Continuity:** the 5V net graph (113 items) is one connected component from U16 pad 6; shortest path
U16.6 → L1.1 (111 mm of track) and → U13.5 both run through the corner; no unreached item.

**Current capacity at 1.17 A, 10 °C rise.** Method: IPC-2152 is the standard the intent names; I use the
Brooks–Adam curve fit of the IPC-2152 data for FR-4 (ΔT = 215.3·I²·W^-1.15·Th^-1, W mil, Th oz, *no* credit
for the adjacent GND plane / pours, so conservative) and cross-check with the IPC-2221 external curve
(I = 0.048·ΔT^0.44·A^0.725), which IPC-2152 found applies to internal conductors as well in a board with planes.
The legacy IPC-2221 internal 50 % derate is shown for reference only — IPC-2152 retired it.

| Conductor on the path | A (mil²) | IPC-2152 fit ΔT @1.17 A | IPC-2221 ext. I @10 °C | (2221 int.) |
|---|---|---|---|---|
| **In2 1.6 mm, 0.5 oz (the fix, 10.4 mm)** | 43.4 | **5.0 °C** | **2.03 A** | 1.02 A |
| prev In2 0.9 mm, 0.5 oz | 24.4 | 9.7 °C | 1.34 A | 0.67 A |
| B.Cu 0.6 mm, 1 oz (21 mm west run, 35 mm south run) | 32.6 | 7.8 °C | 1.65 A | — |
| B.Cu 1.0 mm / F.Cu 1.0 mm to L1 | 54.3 | 4.3 °C | 2.39 A | — |
| 2 × via 0.3 drill, 18 µm plating (each end) | 52.6 | — | 2.34 A | — |
| F.Cu 0.5 mm at U16 pad (0.9 mm long, pre-existing) | 27.1 | 9.6 °C | 1.45 A | — |
| B.Cu 0.4 mm neck at (54.46,116.4–117.75) (1.35 mm long, pre-existing) | 21.7 | 12.4 °C | 1.23 A | — |

The In2 run is now the *widest* cross-section on the path (1.6× the B.Cu 0.6 mm runs that feed it), so the
fix removed the bottleneck rather than moving it. Corner run DC resistance 6.4 mΩ (7 mW at 1.17 A).
Only under the retired IPC-2221 internal derate would 1.6 mm fall short (needs 1.94 mm; the slot between the
H3 hole clearance and the 0.4 mm edge rule allows at most 1.8 mm).

**Geometry (shapely on KiCad's own polygons):**
- B.Cu copper to H3 centre (54,141): nearest non-GND item 3.522 mm (B.Cu 0.6 track end / via at (51.2,138.4));
  via (57,143.4) 3.542 mm. ≥ 3.5 ✓ (prev: 4.10). The B.Cu GND pour comes to 1.80 mm (0.2 mm off the hole wall) at
  H3 and H4, unchanged from prev, see Findings.
- Copper to edge, minimum per layer: F.Cu 0.400 (pad D4.1, unchanged), In1 0.500, **In2 0.400** (the new 1.6 mm run:
  x 50.4 and y 144.6; prev In2 minimum was also 0.400, a RUN track), B.Cu 0.450 (5V south run, unchanged).
  No copper under 0.4 mm on any layer ✓. JLC limit is 0.2.
- Clearance to the H3 hole wall (3.2 mm NPTH): In2 1.6 mm run 0.400 mm on both legs; JLC NPTH-to-copper 0.2,
  project hole clearance 0.2 ✓. Vias: ≥ 1.92 mm.
- Clearance to other nets: In2 run to GND pour 0.2005 (zone clearance 0.2, rule 0.15) ✓; via (57,144.2) to RUN
  track 0.90; via (57,143.4) to U2.4 (F.Cu) 0.40; via hole to In1 plane 0.35 (JLC inner 0.3) ✓.
- Via-via hole spacing at each end 0.5 mm (JLC via-via 0.2, project 0.25) ✓.

## 3. DRC (`work/drc/`)

- Project rules (`cad/temper-lcr.kicad_pro`, `--severity-all`): **0 errors, 0 unconnected, 0 schematic-parity
  issues.** 199 warnings, all `lib_footprint_issues` ("library 'LCR' not in the configuration") — a CLI
  library-table artefact, not a board defect; the footprints are embedded and identical to prev.
- JLC profile: copied board + project to `work/jlc/` with the limits from `jlcpcb-4layer-1oz.json` (clearance
  0.09, track 0.09, via 0.25/0.05 ring, drill 0.15, hole-to-hole 0.45, hole-to-copper 0.30, edge 0.2, silk text
  1.0 / 0.15, silk-to-pad 0.15). KiCad has one hole-clearance number, so it was run at the strictest (0.30 /
  0.45) and the hits classified (`classify_jlc_drc.py`): 171 hole-clearance candidates are all via-hole or
  NPTH cases (limit 0.20; minimum actual 0.2005 NPTH, 0.225 via); 26 hole-to-hole candidates are all via–via
  (limit 0.20; minimum 0.25). **0 failures against JLC.** No track-width, clearance, annular, edge or silk hits.

## 4. Gerber / drill set (`work/gerbers-re/`, `drill-route/`)

Re-exported from `cad/temper-lcr.kicad_pcb` with `kicad-cli pcb export gerbers` (11 layers as in the job file,
`--use-drill-file-origin`, precision 6, X2), `export drill` (Excellon, plot origin, decimal, mm, separate PTH /
NPTH, oval format *route*) and `export ipcd356`. Ignoring the timestamp lines, **every file is identical** to
`gerbers/` (11 Gerbers, job file, PTH + NPTH drills, `.d356`). The drill origin is the board's aux origin
(50,145); the 3.2 mm H1–H4 holes are in the NPTH file.

## Findings

| # | Sev | Where | Evidence | Fix |
|---|---|---|---|---|
| 1 | note (zero margin) | In2 5V run, x 50.4 and y 144.6 | copper-to-edge exactly 0.400 mm, the board's promised minimum (JLC needs 0.2; project rule 0.3). The board already had a 0.400 item on In2 and F.Cu. | none needed; do not widen past 1.6 mm or nudge the run outward. |
| 2 | note (craft) | In2 (57.0,143.4)–(57.0,144.2) | two 0.6 mm stubs join the 1.6 mm end-cap mid-track (a T), fully inside the wide copper; DRC-clean, no dangling. Prev had the same construction. | optional: delete the two 0.6 mm In2 stubs; the end-cap already covers both vias. |
| 3 | MINOR, pre-existing | B.Cu 0.4 mm × 1.35 mm neck (54.46,116.4)–(54.46,117.75) and F.Cu 0.5 mm × 0.9 mm at U16.6 | the only conductors on the path narrower than 0.6 mm; 1.23 A / 1.45 A by IPC-2221 ext., 12.4 °C / 9.6 °C by the no-plane IPC-2152 fit. Both ≤ 1.4 mm long, bounded by the B.Cu 5V pour and 0.6 mm copper, so they run far cooler than the steady-state curves say. Unchanged from the reviewed board. | widen the neck to 0.6 mm at the next spin; no respin for it. |
| 4 | note, pre-existing | B.Cu GND pour at H3 and H4 | 1.80 mm from the hole centre (0.2 mm off the wall), under solder mask; identical to prev (also H2: JK_HPOT track at exactly 3.50 mm). The 3.5 mm rule is met by every non-GND item. | accept (a standoff touching GND pour is harmless) or add a 3.5 mm keep-out on B.Cu at H3/H4 if an isolated standoff is wanted. |

## Files

- `work/dump_board.py`, `diff_boards.py` — item-level board diff (`prev.json`, `cur.json`)
- `work/export_geom.py` (KiCad Python) → `geom-prev.json`, `geom-cur.json`; `analyze_geom.py` → `ana-prev.json`, `ana-cur.json`
- `work/copper_delta.py`, `gnd_delta_pieces.py` — per-layer, per-net copper symmetric difference
- `work/ampacity.py` — current capacity table; `classify_jlc_drc.py` — JLC hole-rule classification
- `work/drc/drc-project.json`, `drc-project-parity.json`, `drc-jlc.json`; `work/jlc/` — JLC-limit project copy
- `work/gerbers-re/`, `work/drill-route/` — re-exported fab set
