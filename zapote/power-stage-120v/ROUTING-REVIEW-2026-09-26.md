# Routing checkpoint review, 2026-09-26

Reviewed local commits `b67c5adf9` and `10121aec5` with parallel Sol xhigh
reviews of rule generation, power routing, and geometry/replay evidence.
The owner approved **240 × 160 mm and four layers** during this review;
DECISIONS.md records that decision. Revised placement D4 remains open.
No source circuit, placement or routing was edited during this review.

This is the historical checkpoint review, not the disposition of the later
regenerated board. The implemented corrections and current acceptance evidence
are in [ROUTING.md](ROUTING.md) and [PLACEMENT-REVIEW.md](PLACEMENT-REVIEW.md).

## Disposition

**Do not approve the courtyard exemption as implemented.** A KiCad mutation
demonstrates that it suppresses a real tank-spacing violation. Fix the
parser and narrow the exemption before relying on a clean DRC result.
Revise leg A's high-side gate/return routing before accepting batch 04.
The HOT auxiliary routes (batch 05) are still incomplete.

## Findings

1. **Foreign tracks become component nets.** In `tools/write_rules.py`,
   `footprint_nets()` splits at footprint starts without finding their
   closing parentheses. On a KiCad-saved board the last footprint, J5,
   absorbs trailing tracks and zones. J5 physically has only `res_a`, but
   an added `vdiv_1` track becomes one of its alleged nets. A 0.25 mm
   `vdiv_1` track 1.8446 mm from J5's RES_A pad then passes clearance under
   regenerated rules. The identical board with rules generated before the
   foreign track was added reports the expected 5.0 mm tank-rule failure.
   Read actual pad nets from a bounded footprint representation; test the
   rule through KiCad on both generated and KiCad-saved boards.

2. **Courtyard intersection is broader than containment.** The new rule
   selects whole objects using `intersectsCourtyard()`. A long segment can
   touch the courtyard and continue outside it; the expression does not
   restrict the relaxed spacing to the part of that segment inside the
   courtyard. Do not treat arbitrary same-net copper as covered by the
   component's insulation rating. Define and verify a bounded escape
   geometry with a mutation outside its allowed region.

3. **Leg A high-side drive is not paired with its source return.**
   `tools/routes.py:335-342` sends OUTA along x=155.5, y=17–30.5 mm. For
   y≈20–30.5 the SW_A F.Cu return ends at x=147, about 8.5 mm away;
   SW_A B.Cu ends at y=19.8. The B.Cu below part of the run is SW_B,
   although intervening planes limit direct coupling. This is a loop-area
   finding, not a measured interference claim. Route OUTA and SW_A as a
   close pair or adjust nearby placement to make that possible. This
   follows the existing routing plan and [TI's gate-drive guidance](https://www.ti.com/document-viewer/lit/html/SSZT533/GUID-8E8A4702-76CD-495F-A121-6F12027C6292).

4. **Replay accepts the wrong placement/stackup.** The documented
   `route_board.py native-04 ...` command exits successfully and emits
   receipts when native-04 still enables only F.Cu and B.Cu. Its result
   nevertheless contains 32 In1 and 17 In2 tracks on disabled layers.
   Validate input identity and enabled copper layers before replay; update
   the command to the regenerated four-layer placement. The untracked
   author-worktree `native-05` was also byte-identical to old native-04.

5. **Barrier evidence needs explicit coverage checks.** `copper_dump.py`
   serializes a PCB_ARC as its straight endpoint chord: an injected BUS_P
   arc passing directly under SELV U1.1 reports zero barrier hits. It also
   silently omits unfilled zones: removing all 23 fills still reports zero
   hits. Reject unsupported geometry and require filled-zone evidence, or
   implement the missing geometry. Neither condition occurs in the fresh,
   filled, straight-track checkpoint measured below.

## Remaining power-routing evidence

The filled 35 µm HV_RET inner plane narrows to about 5.9 mm at x=99 and to
separate 5.7/2.2 mm intervals at x=136. Its current sharing and thermal
margin need calculation or additional parallel copper; this review does
not establish a thermal failure. Layer-count approval does not qualify
those necks for the required current.

R5 Kelvin pad 2 remains separate from the nearby F.Cu current pour and no
copper bypass around R5 was found. Batch 05 must preserve that separation.
The proposed SW_B via at (102.1,33.0) is plausible, but a straight F.Cu
connection from C18.2 crosses the existing gate trace; route around it and
recheck the completed copper.

## Reproduced evidence and limits

Freshly generated the current placement with `tools/build_native.py`, then
replayed all four committed route batches using `tools/route_board.py`.
Refilled and saved with KiCad 10 using `--all-track-errors`,
`--schematic-parity`, `--severity-all`, and the full generated rules including
creepage. No clearance-only filter was used.

- Full DRC: 28 footprint-library mismatches, three silkscreen overlaps,
  74 unconnected items, zero schematic parity issues. No reported spacing
  violations under the current rule file; findings 1–2 limit that result.
- On an identical board copy, regenerating rules from actual physical pad
  nets instead of the faulty parser produces the same DRC result: no
  additional current spacing violation. This does not remove the proven
  false-pass or justify using that parser for the remaining routes.
- Filled-board stackup gate: PASS, four copper layers, 1.600000 mm total.
- Copper census: 333 netted pads, 294 straight tracks, 69 through vias,
  25 filled polygons from 23 zones, across all four copper layers.
- Barrier checker: zero hits for that filled snapshot; injected track,
  via and zone intrusions are detected.
- Selected native/tool tests: 32 passed, two failed. Failures compare old
  native-04 poses and assert the old two-layer stackup. Update these against
  the correct reviewed artifact, not merely to silence the assertions.

Filled replay board SHA-256:
`779fa7fda88291c624252a1aec558f95b8a51cf0aa4662245d40fe7d49759662`.
Local evidence is under `/tmp/ps-routing-review/` (temporary, not a release
artifact): `replayed-full-drc.json`, `replayed-filled-stackup.json`,
`tests.log`, `foreign-j5/`, `geometry-review.md`, and `power-review.md`.
One fresh full DRC run establishes this checkpoint result; it is not a
three-run final acceptance check. Full checks must follow the rule and
routing corrections. No fabrication or powered-operation release follows
from this review.
