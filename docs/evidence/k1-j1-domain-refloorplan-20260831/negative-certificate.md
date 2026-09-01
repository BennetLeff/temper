# K1-J1 corrected bounded-family result (scratch only)

Verdict: no U3 routed promotion is admissible. Production and tracked files
were not edited.

## Instrument correction

The first `manifest.json` is retained as an invalidated calibration run. Its
family pinned R45 and gave U22 no fixed-obstacle-clear option. It also first
computed rotated pad locations from `parse_kicad_pcb().pads`; that view is not
footprint-rotation-resolved. `search.py` was corrected to use the same
`_component_pads` + Rust `pad_pair_distance` path as REQ-SAFE before the
calibration data was used for a verdict.

## Corrected declared family

- Fence: x=90.0..108.5 mm, y=239.0..253.0 mm.
- Movable census: J1, R45, R58, R66, SW1, U22. U8, K1, the In3.Cu HV route,
  board edge, and every other board object remained fixed.
- Declared before materialization in `corrected/declaration.json`.
- Cartesian size: 972 placements. Every individual slot is body/courtyard
  clear against all fixed footprints.
- Exact movable/movable polygon filtering rejected 912/972 and retained 60
  combinations. All remaining 60/60 were materialized and screened (within
  the 96-placement budget), so the corrected family is fully covered after
  the authoritative geometry prefilter.
- All 60 preserve 4,553 trace signatures, 169 via signatures, 525 pads, 168
  footprints, and every fixed footprint position exactly.
- All 60 have zero new F.Fab body overlaps and zero new courtyard overlaps by
  authoritative polygon audit.

## Acceptance matrix

| Gate | Result |
|---|---|
| Authoritative J1 geometry | pass; authority-board footprint retained |
| K1-J1 exact copper gap | pass on all 60; 13.304745870407777..13.77882654659717 mm |
| Fixed-object / movable mechanical geometry | pass on all 60 |
| Full REQ-SAFE signature ratchet | **fail on all 60** |
| Routed promotions | 0/24; placement safety veto occurs first |
| Four RTD nets / approach route | not promoted or claimed; retained copper is disconnected from moved J1 |
| Three-run DRC / uncapped recovery | not run; no candidate reached the routed-promotion gate |
| Containment (least-debt C008) | pass, aside from unchanged DNF-staged C37/R65/T2 |

Every corrected candidate adds J1-R14 reinforced DC_BUS/LV_CONTROL creepage
(10.303625675302813..11.383111055730906 mm), R14-U22 reinforced creepage
(8.71360662977365..9.211078285214919 mm), R54-R66 functional creepage
(1.449999999999994..1.4545619428856988 mm), and R54-U22 functional creepage
(1.3697819629243697..1.6506623903097657 mm). Every candidate also worsens
the existing R66-U22 functional creepage to
0.9752358280698453..1.4751712248443865 mm. Forty-eight of 60 additionally
add R66-SW1 functional creepage at 1.2324827717314408..1.5144189719076562 mm.

Least-debt candidate C008 (`3142e3d26760d28df726c1a2125a1809951ea3e51d5c4c7263036e8039ef045f`):

- K1-J1 = 13.77882654659717 mm.
- J1-R14 = 11.28763452759072 mm versus 12.6 mm reinforced requirement.
- R14-U22 = 8.71360662977365 mm versus 12.6 mm reinforced requirement.
- R54-R66 = 1.449999999999994 mm (new functional finding).
- R54-U22 = 1.6506623903097657 mm (new functional finding).
- R66-U22 = 0.9752358280698453 mm, worsened from 1.5074310215994462 mm.

The bounded family therefore cannot be routed without first changing its
placement topology. This is a budget-limited negative result, not proof that
the whole neighborhood is infeasible. R45 and R58 each had two moved/local
options, but the corrected family still explored only the declared local slot
sets. The next topology decision must move beyond this right/bottom packing --
most directly, relocate J1 away from fixed R14/HV copper or expand scope to
move R14/the associated high-voltage route -- rather than weakening REQ-SAFE.
