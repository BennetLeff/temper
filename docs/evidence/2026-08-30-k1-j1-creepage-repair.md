<!-- provenance: commit=62ed191892aece64105d58e613c6e7c2b97899f8 dirty=false (clean parent used for every measurement; all candidate board mutations and reports lived outside the tracked worktree under /tmp/compound-engineering-1000/) -->

# K1-J1 creepage repair: bounded J1 candidates are infeasible

**Verdict: STOPPED, EVIDENCE ONLY.** The two placements authorized by the
bounded repair plan both remove the K1-J1 reinforced-creepage violation and
restore all four RTD nets, but both create direct copper shorts, new functional
safety violations, courtyard overlaps, body collisions, and uncapped DRC
regressions. Neither candidate is safe to write to the production board.

The tracked board and project-local J1 footprint therefore remain unchanged.
The next board-design step is the deferred domain-first local refloorplan; it
must make room around J1 before moving the connector and its approach copper.

Measurements were performed over 2026-08-30/31 local time. All scratch boards
and transient JSON reports lived under `/tmp/compound-engineering-1000/` and
are intentionally not repository artifacts.

## 1. Scope and stop rule

The governing plan is
`docs/plans/2026-08-30-2314-fix-k1-j1-creepage-repair-plan.md`. Its finite
search budget permits exactly two J1 translations, both at the existing
rotation:

1. `(95.0, 237.0) -> (95.0, 242.0)` (+5.0 mm Y)
2. `(95.0, 237.0) -> (95.0, 242.5)` (+5.5 mm Y)

It explicitly prohibits reopening the exhausted K1-only sweep and requires an
evidence-only pull request if both J1 candidates are vetoed. A candidate must
clear the K1-J1 pair without adding a safety signature, worsening an existing
signature, raising an uncapped DRC category, breaking connectivity, or causing
a mechanical collision.

## 2. Instrument conditions

- Clean-parent commit: `62ed191892aece64105d58e613c6e7c2b97899f8`
- Production board SHA-256:
  `00a27419b82101e3518ddbf9d174f8359d76940c495ca1e5bd3d9cc32d7ac4d9`
- KiCad CLI: 10.0.5
- Generated `pcb/temper.kicad_dru` present for every DRC run
- Each scratch board had basename-matched `.kicad_pro`/`.kicad_dru`
  sidecars, `fp-lib-table`, and a sibling copy of `pcb/libs/`
- `make netlist`: passed before board/netlist checks
- `env -u CONDA_PREFIX make extensions-check`: 10/10 fresh immediately
  before every reported Rust-backed geometry measurement
- REQ-SAFE coverage: 158/168 components (94.0476%), zero classified
  components without pad geometry, on all four boards
- DRC used `temper_placer.validation._drc_api.run_drc()`, which supplies
  `--all-track-errors` and the repository's single-threaded KiCad environment
- DRC identities use `(rule, sorted(items))`; sorting removes KiCad's net/item
  order swap. Each board was measured three times and the intersection was
  compared. Warning categories are also compared by count because the current
  `DrcWarning` API does not expose raw `items`.

The parent and all scratch boards report `silk_overlap = 199`, a KiCad
saturation cap rather than a count. It is recorded as censored and is not used
in any verdict. The hard vetoes below occur in uncapped categories.

## 3. J1 land-pattern authority

The checked-in project-local footprint is a hand-built approximation. Its own
description says pad/drill precision does not affect the HV barrier, but J1 is
now the closest SELV copper to K1, so that statement is false for the current
board.

The candidate boards used the current official KiCad
`Connector_JST:JST_XH_B4B-XH-A_1x04_P2.50mm_Vertical` land pattern, checked
against JST's XH-series drawing:

- JST drawing: <https://www.jst-mfg.com/product/pdf/eng/eXH.pdf>
- KiCad footprint: <https://github.com/KiCad/kicad-footprints/blob/master/Connector_JST.pretty/JST_XH_B4B-XH-A_1x04_P2.50mm_Vertical.kicad_mod>
- 2.50 mm pitch, 7.50 mm pin span for four positions
- official KiCad pads: 1.70 x 1.95 mm, 0.95 mm drill
- official fabrication envelope: `(-2.45, -2.35)` to `(9.95, 3.40)` mm
- official courtyard: `(-2.95, -2.85)` to `(10.45, 3.90)` mm

The validated scratch footprint hashes to
`578ba6321290aead39a60428eed317d8e0eb2b23759774ccc9090a41e82a8285`.
The checked-in approximation hashes to
`aa0df7dde7a78aa2ea851aa9998f6806b92eb8a117d0dd73f6862ee444c784b8`.

Simply substituting the validated land pattern at the existing placement does
not add a safety signature, but it changes the exact K1.4-J1.4 copper gap from
9.686463929644992 mm to 9.594676710156559 mm because the official pad is taller.
That 0.091787219488433 mm reduction proves the footprint mismatch is material
to creepage analysis. It must be synchronized as part of a future accepted
board repair, not silently committed by this stopped run.

## 4. Candidate construction

Each candidate was built from the validated J1 footprint. The old J1 approach
segments for `rtd_force_p`, `rtd_sense_p`, and `rtd_sense_n` were removed and
replaced with short local routes to their retained trunks. `rtd_force_n`, which
is unrouted on the parent, was completed from U8.12 through one via and a B.Cu
run to J1.4. No production-board bytes were changed.

| Board | J1 position / rotation | SHA-256 |
|---|---|---|
| checked-in parent | `(95.0, 237.0) / 0 deg` | `00a27419b82101e3518ddbf9d174f8359d76940c495ca1e5bd3d9cc32d7ac4d9` |
| validated-footprint baseline | `(95.0, 237.0) / 0 deg` | `5ef29bfda80ac96cd490bed0b8881835f807eba3fa60b2b126eefc16eaf26e8a` |
| candidate 1 | `(95.0, 242.0) / 0 deg` | `335d88680ed7da0f888698d8c9f8980a5ea04e2c9de32ef005c9d4dcb3aaa7ea` |
| candidate 2 | `(95.0, 242.5) / 0 deg` | `f0d77c40d4cd7514b960a9d3f897709c874b7ac4b7a40b5e68d01241000d0e54` |

## 5. Safety geometry

The canonical Rust-backed pad geometry and the independent cross-domain
measurement agree on the closest K1-J1 pair, K1.4 (`w1_2`) to J1.4
(`rtd_force_n`):

| Board | K1-J1 gap | 13.1 mm nominal target | K1 internal gap |
|---|---:|---|---:|
| parent | 9.686463929644992 mm | fail | 17.800 mm |
| validated-footprint baseline | 9.594676710156559 mm | fail | 17.800 mm |
| candidate 1 | 13.633236903180160 mm | pass | 17.800 mm |
| candidate 2 | 14.067148771058212 mm | pass | 17.800 mm |

The connector move therefore solves the named reinforced pair in isolation.
It does not solve the board region.

Full pad-only REQ-SAFE results:

| Board | Total | Reinforced inter creepage | Reinforced inter clearance | Reinforced intra creepage | Functional inter creepage | Functional inter clearance | Basic inter creepage |
|---|---:|---:|---:|---:|---:|---:|---:|
| parent | 57 | 27 | 1 | 3 | 25 | 0 | 1 |
| validated baseline | 57 | 27 | 1 | 3 | 25 | 0 | 1 |
| candidate 1 | 61 | 26 | 1 | 3 | 28 | 2 | 1 |
| candidate 2 | 61 | 26 | 1 | 3 | 28 | 2 | 1 |

Both candidates resolve the one K1-J1 reinforced-creepage signature but add
the same five functional signatures:

| Pair | Metric | Candidate 1 | Candidate 2 | Required |
|---|---|---:|---:|---:|
| J1.1-R45.2 | creepage | 1.460 mm | 0.960 mm | 1.8 mm |
| J1.2-R66.1 | clearance | 0.000 mm | 0.000 mm | 0.5 mm |
| J1.2-R66.1 | creepage | 0.000 mm | 0.000 mm | 1.8 mm |
| J1.3-U22.4 | clearance | 0.000 mm | 0.000 mm | 0.5 mm |
| J1.3-U22.4 | creepage | 0.000 mm | 0.000 mm | 1.8 mm |

This is safety-debt substitution, which the plan forbids. Candidate 2 is
strictly worse than candidate 1 at J1-R45.

KiCad DRC supplies a separate routed-copper veto that the pad-only REQ-SAFE
table cannot express. Both candidates repeatedly report J1.4
`rtd_force_n` against the In3.Cu `discharge.r_snub1-p2` track at 10.2500 mm
creepage versus the required 12.6000 mm. The next layout must protect this
inner-layer high-voltage approach as well as the named component pairs.

## 6. Connectivity

`temper_placer.router_v6.pad_connectivity_audit.audit_pcb_file()` produced:

| Board | force+ | sense+ | sense- | force- | Fake completions on affected nets |
|---|---|---|---|---|---:|
| parent | 2/2 connected | 2/2 connected | 2/2 connected | **1/2 broken** | 0 |
| validated baseline | 2/2 connected | 2/2 connected | 2/2 connected | **1/2 broken** | 0 |
| candidate 1 | 2/2 connected | 2/2 connected | 2/2 connected | 2/2 connected | 0 |
| candidate 2 | 2/2 connected | 2/2 connected | 2/2 connected | 2/2 connected | 0 |

The routing concept is electrically complete, but connectivity cannot offset
shorted or mechanically colliding copper.

## 7. Three-run DRC comparison

Every category count repeated exactly across the three runs for each board.
The set intersection still records four unstable parent identities, six on the
validated baseline, zero on candidate 1, and four on candidate 2 because
KiCad can change item attribution while keeping counts fixed. To avoid calling
that attribution noise a board change, a difference is definitely new only
when it is in the candidate intersection and absent from the parent union. It
is definitely resolved only when it is in the parent intersection and absent
from the candidate union.

| Board | Errors | Warnings | Stable identities | Definitely new | Definitely resolved | Indeterminate new-like / resolved-like |
|---|---:|---:|---:|---:|---:|---:|
| parent | 406 | 402 | 352 | - | - | - |
| validated baseline | 406 | 402 | 351 | 0 | 0 | 0 / 1 |
| candidate 1 | 425 | 409 | 374 | **23** | 2 | 1 / 0 |
| candidate 2 | 426 | 410 | 373 | **24** | 2 | 0 / 1 |

The indeterminate entries appeared in the opposite board's three-run union
but not its intersection. They are evidence of unstable item attribution, not
evidence of a physical addition or removal.

Key uncapped category deltas:

| Category | Parent | Candidate 1 | Candidate 2 |
|---|---:|---:|---:|
| clearance | 209 | 212 | 211 |
| courtyards_overlap | 4 | 9 | 9 |
| hole_clearance | 33 | 34 | 34 |
| shorting_items | 39 | 46 | 47 |
| solder_mask_bridge | 4 | 9 | 10 |
| pth_inside_courtyard | 0 | 3 | 4 |

The definitely new identities name direct J1 shorts to R45, R66, and U22; five
J1 courtyard overlaps (R45, R58, R66, SW1, and U22); a J1 pad-to-existing-
route hole-clearance conflict; and solder-mask bridges. Candidate 2 also adds
an additional J1.4-U22 short/mask bridge compared with candidate 1.

Independently of that set classification, both candidates carry the repeated
12.6000 mm routed-creepage veto between J1.4 and the In3.Cu
`discharge.r_snub1-p2` track described in section 5.

`scripts/evaluate_regional_layout.py` independently rejects both boards:

- candidate 1: 406/402 -> 425/409 DRC errors/warnings, three new or worsened
  F.Fab body collisions
- candidate 2: 406/402 -> 426/410 DRC errors/warnings, three new or worsened
  F.Fab body collisions
- both: hard-veto rises in `shorting_items`, `clearance`, and
  `hole_clearance`; no routed-endpoint drift

## 8. Mechanical and barrier checks

`scripts/check_board_containment.py` confirms candidate 1's copper remains
inside the board outline. Containment is not enough: the official courtyard
and fabrication body collide with the populated neighborhood, as the DRC and
regional evaluator report.

`scripts/check_isolation_keepout.py` exits 3 on the parent, validated baseline,
and both candidates with the same normalized finding:

- named barrier `MAINS_SELV_ISOLATION_BARRIER` not found
- one violation
- ten other keepouts present
- required width 12.6 mm across F.Cu, In3.Cu, In4.Cu, and B.Cu

The localized experiment did not weaken or suppress this independent red
gate. It also does not claim enclosure compatibility; no authoritative
enclosure model exists.

## 9. Decision and next board-design step

Neither bounded candidate is acceptable. The production board, footprint
library, DRC ceiling, and provenance artifacts remain byte-for-byte unchanged,
so no 120-sample ceiling campaign is applicable to this evidence-only PR.

The next implementation must start from a **domain-first local refloorplan**,
not another blind connector nudge. At minimum it must jointly place J1 and its
immediate LV neighborhood (R45, R58, R66, SW1, U22, and the U8 approach
corridor), synchronize the authoritative J1 footprint before measuring, and
reserve a routed 13.1 mm nominal K1-to-J1 copper corridor. The refloorplan must
also keep J1.4 and its approach copper at least 12.6 mm from the In3.Cu
`discharge.r_snub1-p2` high-voltage route. Only after a collision-free
candidate clears exact REQ-SAFE and three-run set-based DRC should it receive
the repository's 120-sample DRC/provenance campaign.

This is not evidence that no local solution exists. It is evidence that the
two authorized single-part translations do not exist safely in the current
component neighborhood.
