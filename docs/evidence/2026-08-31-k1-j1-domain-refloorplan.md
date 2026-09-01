<!-- provenance: commit=faac70f39db924dcbeb162be9fc27284f747a909 dirty=false (all measured production inputs were byte-identical to this clean parent; the untracked implementation plan and every candidate artifact were outside the measurement inputs) -->

# K1-J1 domain-first local refloorplan: the right/bottom family is safety-infeasible

**Verdict: STOPPED, EVIDENCE ONLY.** A corrected, predeclared local family
contained 972 placements of J1, R45, R58, R66, SW1, and U22. Authoritative
body/courtyard geometry rejected 912. Every one of the remaining 60 placements
cleared the 13.1 mm nominal K1-J1 target and the mechanical polygon screen, but
every one added reinforced creepage violations against fixed R14/high-voltage
copper and new or worsened functional creepage findings. No candidate was
eligible for routing.

The production board, project-local J1 footprint, netlist authority, and DRC
ceiling remain byte-identical to `origin/main`. This result rejects only the
declared right/bottom packing family; it is not proof that every local or
board-wide topology is infeasible.

## 1. Authority and baseline

The implementation branch begins at `origin/main` commit
`faac70f39db924dcbeb162be9fc27284f747a909`, which contains PR #1550's
rejection evidence. The governing plan is
`docs/plans/2026-08-31-1100-fix-k1-j1-domain-refloorplan-plan.md`.

| Item | Identity / result |
|---|---|
| Production board | `00a27419b82101e3518ddbf9d174f8359d76940c495ca1e5bd3d9cc32d7ac4d9` |
| Authoritative-footprint scratch baseline | `5ef29bfda80ac96cd490bed0b8881835f807eba3fa60b2b126eefc16eaf26e8a` |
| Embedded authoritative J1 footprint | `578ba6321290aead39a60428eed317d8e0eb2b23759774ccc9090a41e82a8285` |
| `kicad-cli` | 10.0.5 |
| Extensions | 10/10 fresh immediately before baseline measurement |
| Footprint drift | 168/168 matched |
| Containment | pass; unchanged DNF-staged C37/R65/T2 reported separately |

`make netlist` and the KiCad DRU generator completed before measurement. Three
baseline DRC runs were identical:

| Category | Run 1 | Run 2 | Run 3 |
|---|---:|---:|---:|
| Total errors | 406 | 406 | 406 |
| Total raw warnings | 402 | 402 | 402 |
| `clearance` | 209 | 209 | 209 |
| `creepage` | 100 | 100 | 100 |
| `courtyards_overlap` | 4 | 4 | 4 |
| `shorting_items` | 39 | 39 | 39 |
| raw `silk_overlap` | 199 (capped) | 199 (capped) | 199 (capped) |

The capped silk value is only a saturation signal; the unchanged production
ceiling's validated uncapped value remains 13,061. No candidate reached the DRC
stage, so this study makes no candidate-versus-baseline DRC claim and does not
touch `power_pcb_dataset/drc_ceiling.json`.

The live production REQ-SAFE census is 57 findings with 158/168 components
classified (94.0476%) and no classified component lacking pad geometry. That is
an improvement over the committed 61-finding pin, recorded here rather than
silently repinned in an unrelated layout study. Connectivity is 2/2 for
`rtd_force_p`, `rtd_sense_p`, and `rtd_sense_n`; `rtd_force_n` is inherited
broken at 1/2 with no copper. The board-wide keepout gate remains red solely
because `MAINS_SELV_ISOLATION_BARRIER` is absent across F.Cu, In3.Cu, In4.Cu,
and B.Cu. This local study neither weakens nor claims to close that separate
barrier requirement.

On the authoritative-footprint baseline, the exact K1-J1 minimum is
9.594676710156559 mm between K1.4 (`w1_2`) and J1.4 (`rtd_force_n`). J1.4 has
no connected approach copper on that baseline. Its exact pad-to-track minimum
to the fixed high-voltage corridor is 10.152471950642665 mm, between J1.4's
oval copper (center `(102.5, 237.0)` mm, size `1.7 x 1.95` mm) and the 0.5 mm
wide In3.Cu `discharge.r_snub1-p2` segment from `(113.55, 219.85)` to
`(113.55, 234.75)` mm (the adjoining segment ending at `(113.85, 235.05)` has
the same minimum). The calculation uses the sanctioned rotation-resolved pad
core and subtracts the pad and track radii; it is a baseline pad-to-track
measurement, not a routed-connectivity claim.

## 2. Declared local family

The corrected family was declared before candidate materialization in the
scratch `corrected/declaration.json` artifact:

- fence: x = 90.0..108.5 mm, y = 239.0..253.0 mm;
- movable footprints: J1, R45, R58, R66, SW1, and U22;
- fixed objects: K1, U8, R14, the `discharge.r_snub1-p2` In3.Cu route, board
  outline, and every unrelated board object;
- J1 rotation: 180 degrees, placing J1.4 to the west, away from the fixed
  high-voltage route;
- declared Cartesian size: 972 placements;
- placement screen ceiling: 96; routed promotion ceiling: 24.

Every individual slot first cleared all extracted fixed F.Fab bodies and all
168 courtyards. F.Fab coverage was 159/168; the nine missing references (F1,
L2, R30, RT1, TP1-TP4, and U27) are outside the declared fence, while all six
movable footprints have F.Fab bodies. Exact movable-to-movable polygon
filtering rejected 912/972 combinations and retained 60. All 60 were
materialized, so the corrected family's post-geometry space was covered
completely while remaining below the 96-screen ceiling. Every materialized
board preserved 4,553 trace signatures, 169 via signatures, 525 pads, 168
footprints, and every fixed footprint position.

The durable replay bundle is committed at
`docs/evidence/k1-j1-domain-refloorplan-20260831/`. It contains the corrected
declaration, complete 60-result manifest, negative certificate, authoritative
J1 baseline builder, corrected runner, and a deterministic replay recipe.
Canonical artifact identities:

| Artifact | SHA-256 |
|---|---|
| corrected declaration | `3edeb18206004e98d07903860c5ff1bf377e96c9b97b845d1ae2c98cce1a833f` |
| corrected manifest | `f7a56e454007eebf342357b5fad6892a681f8a41d0be5d0702540cce81e9e95b` |
| negative certificate | `3a72b4bb740687a52221e8efa449ba689b5e475e520846c5f646ef6c370e063e` |

The 60 full candidate boards remain transient under `/tmp`; each board's
placement and SHA-256 are retained in the committed manifest, so the compact
evidence survives temporary-directory cleanup without adding roughly 140 MB
of rejected board copies to the repository.

## 3. Placement acceptance result

All 60 geometry-valid placements passed the exact, rotation-resolved K1-J1
copper target at 13.304745870407777..13.77882654659717 mm. The closest pair in
every candidate is K1.4 (`w1_2`) to J1.1 (`rtd_force_p`). These are edge-to-edge
copper distances calculated after resolving KiCad child coordinates with
`world = footprint_position + R(-theta) * local_offset`, where
`R(-theta) = [[cos(theta), sin(theta)], [-sin(theta), cos(theta)]]`, and then
using the Rust-backed exact pad-distance kernel. All 60 added no F.Fab body or
courtyard overlap, then failed the full REQ-SAFE signature ratchet before
routing:

| Signature | Population | Measured range | Required / comparison |
|---|---:|---:|---:|
| J1-R14 reinforced creepage | 60/60 | 10.303625675302813..11.383111055730906 mm | 12.6 mm |
| R14-U22 reinforced creepage | 60/60 | 8.71360662977365..9.211078285214919 mm | 12.6 mm |
| R54-R66 functional creepage | 60/60 | 1.449999999999994..1.4545619428856988 mm | 1.8 mm |
| R54-U22 functional creepage | 60/60 | 1.3697819629243697..1.6506623903097657 mm | 1.8 mm |
| R66-U22 functional creepage | 60/60 | 0.9752358280698453..1.4751712248443865 mm | worsens 1.5074310215994462 mm baseline |
| R66-SW1 functional creepage | 48/60 | 1.2324827717314408..1.5144189719076562 mm | 1.8 mm |

The least-debt board, C008 (SHA-256
`3142e3d26760d28df726c1a2125a1809951ea3e51d5c4c7263036e8039ef045f`),
still has four new and one worsened safety signatures. Its K1-J1 gap is
13.77882654659717 mm, but J1-R14 is only 11.28763452759072 mm and R14-U22 is
8.71360662977365 mm. Containment passes; safety does not.

Because the cheapest mandatory safety gate rejected every placement, routed
promotions are 0/24. The moved J1 pads are intentionally disconnected on these
placement-only boards. Running connectivity, approach-copper, three-run DRC,
or uncapped DRC as if one were a routed candidate would manufacture downstream
evidence for a topology already forbidden from advancing.

## 4. Instrument corrections made before the verdict

The first calibration run is retained but excluded from the result for two
independent reasons.

First, it computed a rotated J1 gap from `parse_kicad_pcb().pads`. That view did
not resolve footprint rotation for this purpose, so it incorrectly reported
every 180-degree anchor below 13.1 mm. The corrected campaign uses the same
component-pad construction and Rust `pad_pair_distance` geometry path as
REQ-SAFE. The authoritative result is that all 60 corrected screens clear the
target.

Second, the calibration family pinned R45 and placed every U22 option into
fixed U8. It therefore generated 96 intrinsically colliding boards instead of
a meaningful neighborhood search. The corrected declaration pre-screens every
individual slot against fixed bodies/courtyards and gives both R45 and R58 two
local options. The calibration data is preserved as a caught setup defect, not
laundered into the negative certificate.

This is the same general measurement lesson as the rotation incidents already
documented in `docs/evidence/2026-08-18-pad-core-polygon-rotation-convention.md`:
self-consistent repo output is not an external geometry oracle, and a candidate
generator must validate its own option set before spending the screen budget.

## 5. Decision and next topology

No production artifact is changed. In particular:

- `pcb/temper.kicad_pcb` remains at its original hash;
- the checked-in proxy J1 footprint is not promoted because no candidate using
  the authoritative footprint passed;
- `power_pcb_dataset/drc_ceiling.json` remains bound to the unchanged board;
- no 120-sample campaign is required for an unchanged production board.

The right/bottom packing family is blocked by fixed R14/high-voltage copper,
not by the direct K1-J1 pair. The next design decision is therefore topology,
not a threshold adjustment: either relocate J1 away from R14 and the fixed HV
corridor (which brings board-edge/cable/enclosure work into scope), or expand
the movable set to include R14 and its associated high-voltage route as part of
the board-wide domain-first isolation-barrier refloorplan. Any future run must
declare that expanded authority before mutation and must keep 12.6 mm
reinforced creepage and the global barrier gate unchanged.
