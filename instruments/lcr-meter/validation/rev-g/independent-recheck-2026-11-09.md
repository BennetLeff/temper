# Rev G re-check of the MAJOR-1 fix (second frozen export)

Reviewer: independent PCB review (Fable subagent), 2026-11-09. Scope: `build/rev-g-review-2/` only.
`temper-lcr-reviewed.kicad_pcb` is byte-identical to the board reviewed in `build/rev-g-review/cad/`
(`cmp`), so the diff below is exactly the change since REVIEW.md. Work products are in
`build/rev-g-review-2/work/` (board dumps `board_old.json` / `board_new.json`, `conn2.py`,
`drc_new2.json`, `render_d21.png`).

## Verdict

MAJOR-1 is resolved. Each TVS GND pad now has a 0.5 mm return to the BNC shell pin and a 0.5 mm
link to a new 0.3/0.6 via 1.1 mm east that lands in the continuous In1 GND plane (full copper on
every ring sampled out to 1.2 mm, no island, no thermal relief: vias connect to the plane solid in
KiCad, and the fill confirms it). Nothing else moved: the only copper changes are the 8 old 0.2 mm
GND segments replaced by 12 new 0.5 mm segments and the 4 vias; footprints, large zones, outline,
nets and design rules are identical; the remaining file differences are a title block, two updated
fab-note strings and regenerated teardrops. DRC with the project file is unchanged (199 library-path
warnings, 0 violations, 0 unconnected). Nothing new arose beyond a cosmetic silk-over-via note.

## 1. Complete diff, reviewed board -> new board

Copper (from `work/board_old.json` vs `work/board_new.json`, set comparison of every segment, via,
footprint and zone):

Removed (8 tracks, all F.Cu, GND, 0.2 mm):
- (69.2, 58.2)-(69.2, 56.8) and (69.2, 56.8)-(71.0, 55.0)   [D21 -> J3 shell pad 2]
- (91.2, 58.2)-(91.2, 56.8) and (91.2, 56.8)-(93.0, 55.0)   [D22 -> J7]
- (113.2, 58.2)-(113.2, 56.8) and (113.2, 56.8)-(115.0, 55.0) [D23 -> J8]
- (135.2, 58.2)-(135.2, 56.8) and (135.2, 56.8)-(137.0, 55.0) [D24 -> J9]

Added (12 tracks, all F.Cu, GND, 0.5 mm):
- the same eight paths at 0.5 mm width, plus
- (69.2, 58.2)-(70.3, 58.2), (91.2, 58.2)-(92.3, 58.2), (113.2, 58.2)-(114.3, 58.2),
  (135.2, 58.2)-(136.3, 58.2)   [pad 2 -> new via]

Added (4 vias, GND, drill 0.30, pad 0.60, F.Cu-B.Cu, tented both sides):
- (70.3, 58.2), (92.3, 58.2), (114.3, 58.2), (136.3, 58.2)

Removed vias: none. Total tracks 1896 -> 1900, vias 460 -> 464.

Footprints: 281 -> 281, zero differences (reference, value, footprint id, layer, position,
rotation, every pad's number/net/position/size compared).

Zones: the 20 large zones (3 GND pours, 17 rule areas) are identical in net, layers, name,
priority, settings and outline. The small zones (KiCad teardrops) went 1147 -> 1155: 12 new
teardrops at the new via/track ends (listed in the session log, all GND at the four sites) and the
rest regenerated with re-ordered vertices on the same nets/places; none is larger than 2.2 mm.

Board outline, netlist (net names/codes) and design settings: identical. `cad/temper-lcr.kicad_pro`
rules, severities and netclasses: identical to the reviewed project.

Non-copper text differences in the .kicad_pcb (`diff` with uuids stripped):
- new `(title_block (title "Temper TIDA-060029 LCR bench instrument") (date "2026-11-09") (rev "G")
  (company "Temper"))` — NOTE-5 addressed on the board side;
- fab notes on User.Drawings: "494 holes" -> "498 holes", "395 x 0.30 mm drill, 0.60 mm pad" ->
  "399 x ..." — both correct for the new via count (verified against the drill file below);
- everything else in the diff is segments/polygons re-ordered by the save, same content.

Gerbers/drill (new vs reviewed export): PTH.drl T1 (0.30 mm) 460 -> 464 hits, other tools
unchanged (4 x 1.0, 4 x 1.2, 16 x 1.4, J1 slots routed); F_Cu flashes 1231 -> 1235; In1_Cu flashes
488 -> 492 (the four via pads on the plane layer); IPC-D-356 VIA records 460 -> 464; F_Mask flashes
777 -> 777 (new vias tented, consistent with the "covering plugged" fab note and the other vias).

## 2. New vias actually reach the In1 GND plane

`work/conn2.py` refilled the zones and tested the In1 fill polygon:
- The In1 GND fill is one outline of 10451 mm2 (no islands anywhere on In1).
- Each of the four via centres lies inside that single outline and inside none of its holes.
- Copper around each via: 24/24 sample points at radii 0.35, 0.45, 0.6, 0.9 and 1.2 mm are inside
  the In1 fill, i.e. the via pad is embedded in solid plane with no antipad and no spokes (KiCad
  gives vias a solid zone connection; the fill confirms it). Nothing is starved.
- Connectivity: each via's connected track is exactly its 0.5 mm link to the TVS pad 2; the pad 2 ->
  shell-pin path remains in parallel. DRC: 0 unconnected items.

## 3. Clearances of the new vias and tracks

Nearest non-GND copper to each via (copper-to-copper / hole-to-copper, from the dumps):
- (70.3, 58.2): JK_HCUR B.Cu run y = 56.9 (0.2 mm wide): 0.90 mm copper, 1.05 mm from the hole.
- (92.3, 58.2) and (114.3, 58.2): ISO_SINK In2 run y = 59.4: 0.80 mm copper, 0.95 mm hole; JK_HCUR
  B.Cu y = 56.9: 0.90 / 1.05 mm.
- (136.3, 58.2): ISO_SINK In2 y = 59.4: 0.80 / 0.95 mm (the JK_HCUR run ends at x = 130.9).
- The JACK_LC In2 run at y = 56.4 is 1.8 mm centre-to-centre from every new via (1.4 mm copper).
- No non-GND pad within 1.0 mm of any new via; no other via hole within 1.0 mm. The nearest pad is
  D2x pad 2 itself (GND, 1.1 mm, connected by the new track).
- New 0.5 mm tracks vs non-GND pads: none within 1.0 mm (pad 1 of each TVS is 1.55 mm away, the JK_x
  F.Cu track 1.85 mm). JLC limits (0.09 copper, 0.2 via-hole-to-track, 0.15 pad-to-pad) are met by
  a wide margin; the board rule of 0.15 passes DRC.

Courtyards: no via centre is inside or within 0.35 mm of any courtyard. The D2x courtyard right
edge is at diode centre +1.85 (D21: x = 69.95); the via pad edge is at x = 70.0, so 0.05 mm clear,
the same at D22, D23 and D24. The via is outside the part's keep-out, not under its body.

Silk: the new 0.5 mm north segments cross the right end of the D2x silk outline (y = 57.35 line) and
the BNC bracket line (y = 56.8-57.6 region), as the 0.2 mm tracks did; the reference text "D21".."D24"
(1 mm, at diode centre -1.85 in y) overlaps each new via's position. All of this is silk on
mask-covered copper (tracks and tented vias), which JLC prints as-is; no silk touches an exposed pad
(pad-to-silk check: 0 pairs under 0.15 mm board-wide). Cosmetic only; if you want it clean, nudge the
"D2x" reference text 1 mm west or north.

## 4. DRC (kicad-cli 10.0.4, `--severity-all --all-track-errors`, run in `work/cad-copy2/` with the
project file present)

- 199 `lib_footprint_issues` warnings (library paths not resolvable in the frozen export — identical
  to the reviewed board), 0 other violations, 0 unconnected items.
- Note for anyone repeating this: running DRC on the .kicad_pcb alone (no .kicad_pro beside it) uses
  KiCad default rules and reports 539 spurious errors (clearance 0.2, via 0.5, etc.); `work/drc_new.json`
  is that invalid run, `work/drc_new2.json` is the valid one.

## 5. Status

- MAJOR-1 (TVS ground return): RESOLVED. Loop is now pad 2 -> 0.5 mm, 1.1 mm -> via -> In1 plane
  0.2 mm below, with the 0.5 mm shell-pin path in parallel. Estimated return inductance drops from
  ~2-3 nH to well under 1 nH; the TLP172AM V_OFF margin concern is addressed.
- MAJOR-2 (B.Cu pour at H3/H4): accepted as a Rev F carry-over per the coordinator (insulating
  standoffs/washers at H3/H4, chassis bonded at the front panel only). Board unchanged there; consistent
  with that decision.
- NOTE-5: board title block now Rev G. The schematic title blocks (not in this export) were not
  re-checked.
- New issues: none. The only new observation is the cosmetic silk-over-tented-via under the "D2x"
  reference text.
- MINOR-1/2/3 and NOTE-1..4 from REVIEW.md stand as recorded (no change in those areas).
