# A pad that places no copper was reported as `F.Cu` — 2 pads, and what they cost

`pcb/temper.kicad_pcb` sha256
`26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b`, verified
identical before and after every measurement below; never opened for write.

## 1. The defect

`parse_engine.rs`'s `extract_components_pure` picks a pad's copper layer like
this (unchanged in this commit — see §6 for why):

```rust
let copper: Vec<&String> = pad_layers.iter()
    .filter(|l| l.contains(".Cu") && !l.contains('*')).collect();
copper.first().map(|s| (*s).clone()).unwrap_or_else(|| "F.Cu".to_string())
```

The `unwrap_or("F.Cu")` is reached exactly when the pad declares **no copper
layer at all**. It then reports a copper layer for a pad that has none.

Reproduced on the committed board before the fix:

```
K1 pad A1   (layers *.Cu *.Mask)   Pin.layer = "all"    <- correct
K1 pad 13   (layers "F.Fab")       Pin.layer = "F.Cu"   <- WRONG
K1 pad 14   (layers "F.Fab")       Pin.layer = "F.Cu"   <- WRONG
```

`K1` is `temper:Relay_SPST_Omron-G4A-E`. Its own `descr` states these two are
the #250 Faston quick-connect tabs and that they "have zero PCB copper
connection on this variant … they mate externally with a push-on spade
connector, not a PCB trace. Modeled here as SMD (no-drill) landing pads purely
for netlist/footprint pin-count parity and courtyard/placement-clearance
purposes". The board and the footprint agree. Only the parser disagreed.

## 2. Every affected pad, on every board in the differential corpus

Scanned straight from the `.kicad_pcb` bytes (every `(pad …)` token, its
`(layers …)` set), independent of the parser:

| board | pads | non-copper | which |
|---|---:|---:|---|
| `pcb/temper.kicad_pcb` | 527 | **2** | `K1.13`, `K1.14` — `(layers "F.Fab")` |
| `power_pcb_dataset/corpus/rp2040_designguide` | 203 | **4** | 4 unnumbered pads, `(layers "B.Paste")` |
| `power_pcb_dataset/corpus/bitaxe_ultra` | 444 | 0 | — |
| `power_pcb_dataset/corpus/piantor_right` | 310 | 0 | — |
| `power_pcb_dataset/corpus/temper` | 113 | 0 | — |
| `power_pcb_dataset/corpus/minimal` | 14 | 0 | — |

**On the production board the answer is 2 of 527, both on `K1`, and no other
footprint is affected.** Its full layer-set histogram:

```
378  ("F.Cu", "F.Mask", "F.Paste")
 94  ("*.Cu", "*.Mask")
 49  ("F.Cu", "F.Paste", "F.Mask")
  4  ("F.Cu", "F.Mask")
  2  ("F.Fab")            <- K1.13, K1.14
```

Two further spellings the corpus exercises and the classifier must get right:
`F&B.Cu` (4 pads on bitaxe, 21 on piantor — both outer coppers, IS copper) and
bare `*.Cu` with no mask (9 on rp2040, 4 on bitaxe).

## 3. kicad-cli never had this defect, and the discrepancy is exactly 2 pads

`kicad-cli 10.0.5 pcb drc --all-track-errors` on the committed board:
**883 violations, 339 unconnected items.** Not one of them names `K1` pad `13`
or `14`.

That is not silence for lack of looking. The two pads are 6.35 × 1.2 mm
rectangles whose centres are 6.35 mm apart, so their long edges **abut exactly
(0.000 mm)**, on two different mains nets. Real copper like that is a dead
short, and kicad-cli reports 39 `shorting_items` and 382 `clearance`
violations elsewhere on the same board. It also lists every *other* pad on
both of those nets:

```
power_in.ntc-no : U1.2, U2.1, RT1.2      (K1.13 absent)
w1_2            : RT1.1, L1.4            (K1.14 absent)
```

kicad-cli reads the board directly and simply does not see them as copper.
**The repo's parser and kicad-cli disagreed on the copper pad count of this
board by exactly 2, and the parser was wrong.**

## 4. The fix

`Pin.is_copper` and `PadData.is_copper` — derived from the pad's own
`(layers …)`, which the parse engine now carries verbatim as an injected
`declared_pad_layers` attribute. One classifier, `layer_token_is_copper`, used
by both: a token places copper iff it **ends with** `.Cu` (`F.Cu`, `B.Cu`,
`In1.Cu`, `*.Cu`, `F&B.Cu`). Suffix, not substring: `contains(".Cu")` would
accept a hypothetical `Foo.Cutout`.

For a pad object built by hand (no injected set) `is_copper` classifies
`layer`, so `Pin(..., layer="F.Fab")` is not copper and `Pin(..., layer="all")`
is.

`placer/cp_sat/tank_creepage.py`'s `_pin_layers` — the one live in-repo
"which copper layers does this pad occupy" predicate that is a *measurement*
rather than a routing decision — now returns the empty set for a non-copper
pad instead of `{"F.Cu"}`. **Measured: this moves no figure on the committed
board** (no tank-node pad is non-copper) and the 6 reds in
`test_tank_creepage.py` are byte-identical before and after, proven by
re-running the unmodified file in this tree.

## 5. Re-measured censuses

Every run below is in-process against the committed board, on the settled
pad-world composition (`world_centre = (FX,FY) + R(-THETA)·(LX,LY)`, world body
angle absolute — `41c8d5272`/`c67e41b5e`, cherry-picked as `86649a9a4`). The
five-residual and the-34 harnesses re-implement that composition themselves
from the convention statement; the HV↔HV harness imports
`temper_placer.geometry.pad_world`. **My branch is off `main`, which does not
carry `pad_world.py`** — the census runs happen in exported copies of the
branches that do, with this commit's parser patch applied to each.

Every published number reproduces exactly before the correction is applied,
so the delta is the correction and nothing else.

### 5a. The 25 833-pair HV↔SELV census (`analysis/enumerate-the-five` @ `52f37c4fe`)

Reads pads through kiutils and **never looked at `(layers …)` at all**, so it
took both phantoms as mains conductors.

| | published | corrected |
|---|---:|---:|
| HV pads × SELV pads | 109 × 237 = **25 833** | 107 × 237 = **25 359** |
| below its own figure | **35** | **33** |
| MAINS↔SELV below (fig 4.80, determinable) | **3**, min **4.0500** `K1.14↔J1.1` | **1**, min **4.7652** `U1.2↔C6.2` |
| DC_BUS↔SELV below (fig 8.00, determinable) | 1, min 7.1253 | 1, min 7.1253 |
| SELV↔SWITCHING below (floor 8.00) | 4, min 3.5781 | 4, min 3.5781 |
| SELV↔TANK below (floor 20.00) | 27, min 8.8500 | 27, min 8.8500 |

The two that vanish are `K1.14↔J1.1` **4.0500** (short 0.7500) and
`K1.14↔J1.2` **4.1831** (short 0.6169).

Model E re-solved here, not inherited (B `infeasible` 25.8 s, D `infeasible`
24.7 s, E `optimal` 168/168 38.0 s, seed 42; applied to a scratch board,
write 168 updated / 0 skipped, round-trip PASS, containment PASS, template
sha256 unchanged). **Model E: 5 → 5, unchanged.** All five named residuals
survive; none involves `K1`. So the published **35 → 5** is really **33 → 5**.

### 5b. The 34-newly-below classification (`worktree-agent-abfd3a541044aa954` @ `d01134515`)

Same kiutils loader, same absence of any layer filter.

| | published | corrected |
|---|---:|---:|
| pairs | 25 833 | 25 359 |
| figures moved by the R(−θ) correction | 19 640 | 19 386 |
| below 12.6 mm, superseded R(+θ) | 155 | 130 |
| below 12.6 mm, canonical R(−θ) | **122** | **98** |
| newly below (the unsafe direction) | **34** | **34** |
| verdict on the 34 | 2 violations / 24 compliant / 8 no requirement | **identical** |

**The 34 and every one of their verdicts are untouched.** What changes is the
`122` (→ 98: twenty-four of them were phantom pairs) and §6's sidebar, which
named `K1.14↔J1.1` at 4.0500 mm and `K1.14↔J1.2` at 4.1831 mm as "the mains
barrier's worst determinate shortfalls on this board". **That sidebar
evaporates.**

### 5c. The HV↔HV functional census (`hvhv/functional-pairings` @ `f2a32e943`)

This one had already found the defect and filtered it locally, with a regex
over the board text. Both arms reproduce:

| | `--include-non-copper` | published (filtered) |
|---|---:|---:|
| declared-HV pads | 109 | 107 |
| pairs | 5 596 | 5 386 |
| below own figure | **70** | **69** |
| …on a determinate pairing | **17** | **16** |
| MAINS↔MAINS (fig 2.20, determinable) | 312 pairs, **1** below, min **0.000** `K1.13↔K1.14` | 260 pairs, **0** below, min **5.500** `RT1.1↔RT1.2` |

**Its published figures stand unchanged.** What this commit adds is that the
exclusion no longer needs a local regex: the census's own regex set and
`Pin.is_copper` agree exactly, `{(K1,13), (K1,14)}`.

## 6. What could NOT be fixed, and why I stopped rather than force it

**`Pin.layer` still reports `"F.Cu"` for `K1.13`/`K1.14`.** Two pinned
`_*_py_oracle` files encode that fallback:

1. `tests/io/_parse_engine_py_oracle/_parse_modules.py:96` —
   `layer = copper_layers[0] if copper_layers else "F.Cu"`, asserted
   **bit-exact** against the Rust engine by
   `test_parse_engine_rust_differential.py` over a 6-board corpus that
   includes `pcb/temper.kicad_pcb` itself.
2. `tests/core/_netlist_py_oracle.py` — pins `Pin`'s 12-field list
   name-by-name, default-by-default, in `test_netlist_rust_differential.py`.

Correcting `Pin.layer`, or adding a 13th `Pin` field, breaks one or both.
The repo has a documented lockstep-divergence procedure for exactly this
(`_parse_nets.py`'s two `DELIBERATE DIVERGENCE` banners), but it is a
deliberate re-pinning of a safety oracle and is **not mine to perform**.

So `is_copper` routes around `layer` instead, using the mechanism the `Pin`
pyclass was already given `dict` for — the parse path injecting an attribute
that exists on no `Pin` definition, exactly as it already injects
`board.traces`. `__repr__`, `__eq__`, `dataclasses.fields()` and both
differentials are untouched by construction, and both differentials are green
(56 + 73 passed).

**This needs a human decision:** the pinned oracle encodes a defect, and until
someone lands the lockstep divergence, `Pin.layer` remains a trap for any
consumer that has not heard of `Pin.is_copper`.

## 7. Both directions, honestly

**Removing a phantom pad cannot reveal a new violation in any of these
censuses.** A pad-pair distance depends only on the two pads in it, so
dropping pads is monotone: the below-figure count can only fall. Proved
structurally, and observed — 35→33, 70→69, 122→98, 34→34, model-E 5→5. No
pair anywhere went from clear to below.

What does get worse:

1. **The worst determinate MAINS↔SELV shortfall on this board is now a real
   one.** It was reported as `K1.14↔J1.1`, 4.0500 mm against 4.80 — a
   0.7500 mm shortfall on a pad that places no copper. It is
   `U1.2↔C6.2` (`power_in.ntc-no` ↔ `gnd`), **4.7652 mm against 4.80, short
   by 0.0348 mm**. That pair was ranked 35th of 35 — last, least severe — and
   is now 1st of 1. It was always there, outranked by a phantom. It is also
   one of the two genuine violations `d01134515` already identified, so
   nothing new is being claimed about it; only its rank changes.

2. **Two mains nets declare a terminal that no copper can reach.**
   `power_in.ntc-no` has 4 declared pads, 3 of them copper; `w1_2` has 3, 2 of
   them copper. Neither net is orphaned — both keep ≥2 real copper pads — but
   the netlist asserts a PCB connection to the relay contacts that the
   footprint cannot make, and kicad-cli does not even list them as
   unconnected because it never saw them. As drawn, **the mains bypass-relay
   contacts are wired only in the netlist**; the footprint's own `descr` says
   they must be wired externally with spade connectors. That was previously
   invisible because the parser reported copper there. It is a design/netlist
   question, not a geometry one, and it is not resolved here.

3. **The count fell, and that is a corrected measurement, not an improved
   board.** Nothing about `pcb/temper.kicad_pcb` got safer. No threshold,
   ceiling, ratchet, allowlist or expectation was touched.

## 8. Still open — reported, not changed

Every live site that reads `pin.layer` to decide where a pad's copper is, and
so still rasterises or targets `K1.13`/`K1.14` as `F.Cu` copper:

```
router_v6/obstacle_map.py:92-99            pad polygon -> layer_obstacles[pin.layer]
router_v6/_astar_nlayer.py:957-960         landing target_layers
router_v6/constraints_spatial_index.py:317 p.layer == layer or p.is_pth
router_v6/bottleneck_geometry.py:671-676   pin_layer -> layer index
router_v6/pad_connectivity_audit.py:311-367
router_v6/_ground_plane.py:770
router_v6/_power_islands.py:465
io/real_board.py:344
```

These are routing decisions, not measurements: correcting them changes what
the router emits and therefore the board's DRC counts. That deserves its own
evidence-first change and is deliberately not bundled here.

## 9. Provenance

- Board sha256 verified identical before and after: unchanged, never opened
  for write.
- No clearance, creepage, copper-weight, loop-area, ampacity or DRU threshold
  changed. No ratchet raised, ceiling re-baselined, allowlist broadened, or
  oracle deleted, re-pinned or weakened. No test skipped, xfailed, deleted or
  relaxed.
- New test `tests/io/test_pad_copper_classification.py`, 22 cases: **22 failed
  before the fix, 22 pass after**, verified by rebuilding the extension from
  unmodified `main` and back.
- Pre-existing reds, proven pre-existing by re-running the same tests against
  an extension built from unmodified `main` in this tree: 8 in `tests/io` +
  `tests/core` (`test_fab_body_extraction` R4/C4 body-overlap baseline,
  2 × `test_finepitch_production_board` KiCad-7 footprint dir, 
  `test_kicad_metadata_board_dimensions`, 2 × `test_netclass_loader`,
  2 × `test_design_rules_rust_differential`) and 6 in
  `tests/placer/cp_sat/test_tank_creepage.py`. Identical lists before and
  after.

## 10. Set-level proof that nothing was newly revealed, and the two that were

Section 7 argues monotonicity. This section *measures* it: the full
below-figure **row sets** are compared, not just their counts.

```
HV<->SELV (25 833-pair census)     unfiltered 35 rows   filtered 33 rows
  ONLY when phantoms included:  K1.14 J1.1 MAINS<->SELV 4.0500
                                K1.14 J1.2 MAINS<->SELV 4.1831
  ONLY after the fix:           (none)

HV<->HV (5 596-pair census)        unfiltered 70 rows   filtered 69 rows
  ONLY when phantoms included:  K1.13 K1.14 0.000
  ONLY after the fix:           (none)
```

Every surviving row keeps a byte-identical measured distance (the comparison
key includes it). **No pair anywhere goes from clear to below.**

What *is* revealed is the true nearest neighbour, where a phantom had been
standing in front of a real pad. Exactly two of the fourteen
closest-pair-per-pairing entries move; the other twelve are byte-identical:

| pairing | closest, phantoms in | closest, corrected | effect |
|---|---|---|---|
| `MAINS<->SELV` (fig 4.80, determinable) | `K1.14<->J1.1` **4.0500** | `U1.2<->C6.2` **4.7652** | a REAL pair surfaces, still below its figure by **0.0348 mm** -- it was ranked 35th of 35, now 1st of 1 |
| `MAINS<->MAINS` (fig 2.20, determinable) | `K1.13<->K1.14` **0.000**, 1 below | `RT1.1<->RT1.2` **5.500**, 0 below | the pairing's only determinate failure was the phantom pair |

`U1.2<->C6.2` is not a new violation -- `d01134515` already graded it a genuine
one. What changes is that it is now *the* worst determinate mains shortfall on
this board, no longer outranked by a fabrication marker.

Checked and found neutral: `io/real_board.py`'s `_copper_reach_mm` for `K1` is
**14.4283 mm either way** -- the NPTH mounting pads at (+-11, +-6.25) dominate,
so the phantoms never inflated that bound.

## 11. Full pre-existing-failure baseline

Every red below was re-run against an extension built from **unmodified
`origin/main`** in this same tree, then again with the fix, and the lists are
identical. Recorded here so nobody re-derives them.

`tests/io` + `tests/core` (8):

```
test_fab_body_extraction.py::TestMeasuredBodyOverlapMatchesPR1158::test_real_body_collisions_match_measured_baseline
test_finepitch_production_board.py::TestKicadFootprintLibrary::test_kicad7_footprint_dir_exists
test_finepitch_production_board.py::TestKicadFootprintLibrary::test_kicad7_footprint_dir_contains_footprints
test_kicad_metadata_board_dimensions.py::test_real_board_dimensions_match_corrected_outline
test_netclass_loader.py::TestNetclassLoader::test_class_pairs_loaded
test_netclass_loader.py::TestGateDriveSplit::test_every_class_pairs_entry_for_one_half_has_an_equivalent_for_the_other
test_design_rules_rust_differential.py::test_module_constants_identical
test_design_rules_rust_differential.py::test_create_temper_design_rules_identical
```

`tests/placer/cp_sat/test_tank_creepage.py` (6): the two
`TestTankBusCopperMetric` cases and all four `TestTankBusEnforcement` cases.
These are the ones `_pin_layers` could plausibly have moved; they did not.

Real-board golden/connectivity reds (6):

```
placer/cp_sat/test_regression_drc.py::test_golden_board_drc_regression
placer/cp_sat/test_regression_drc.py::test_production_board_drc_regression
placer/cp_sat/test_regression_drc.py::test_production_board_routing_drc_regression
router_v6/test_strip_copper.py::TestStripExistingCopper::test_matches_real_production_board_zone_count
router_v6/test_ground_plane.py::...::test_gnd_plane_improves_real_board_pad_connectivity
router_v6/test_power_islands.py::...::test_power_islands_are_expressible_and_measurably_improve_connectivity
```

FLAKY, NOT BASELINED EITHER WAY:
`tests/geometry/test_geometry_pbt.py::test_polygon_area_translation_invariant`
failed on the `main` baseline and on one earlier sweep, and PASSED on the
final post-fix run of the same selection. It is a Hypothesis property test
with a shared example database (falsifying example `dx=91813, dy=93559`,
|delta| = 1.04e-06 -- float cancellation under large translation). It
exercises polygon area in `temper-geometry`, a crate this change does not
touch at all (`git diff origin/main --name-only | grep geometry` is empty), so
it cannot be caused here -- but it is reported as flaky rather than claimed
green.

NOT RUN TO COMPLETION: the full `tests/placer` + `tests/router_v6` sweep
(6000+ cases) was killed by its own wall-clock timeout twice before printing a
summary. Its per-file progress showed the same 6 `test_tank_creepage` F's and
3 `test_regression_drc` F's baselined above, and the router subsets most
exposed to pad-layer reads were run to completion separately
(`-k "obstacle or pad or terminal or connectivity"`: 445 passed, 2 failed,
both baselined above; `tests/geometry` + `tests/requirements`: 3474 passed).
**The full sweep is a gap, and it is labelled as one rather than claimed.**
