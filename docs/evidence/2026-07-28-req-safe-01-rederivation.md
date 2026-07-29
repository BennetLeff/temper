<!-- provenance: commit=320e3c816fe3212ded0e934a6fa6098c121bf170 dirty=false (measured on a clean checkout of the merge commit for PR #388; this doc is the only file added) -->

# REQ-SAFE-01: the 9 clearance/creepage violations, re-derived on exact pad geometry

Branch `docs/req-safe-01-rederivation`, from `origin/main` (`320e3c81`, the
merge of PR #388 "fix/pad-geometry-model"). Investigation only -- no board,
test, threshold, or validator was changed.

## Headline: the checker does not use pad geometry at all

The premise this task was handed -- "these numbers were computed on a pad
model that has since been proven wrong (`radius = max(width, height)/2`)" --
is **not what is happening**. The REQ-SAFE-01 clearance/creepage checker has
never used *any* pad model. It measures the straight-line distance between
the two components' **origins**.

`packages/temper-placer/src/temper_placer/requirements/validators/clearance.py`,
`_check_distance` (the single shared core behind `check_domain_clearance`,
`check_creepage_path`, and `verify_iec60335_compliance`):

```python
for comp_a, comp_b in _domain_boundary_pairs(placement, domain_a, domain_b, nets_domain):
    pos_a = comp_a["position"]
    pos_b = comp_b["position"]
    dist = _distance(pos_a, pos_b)
    if dist < min_mm:
```

`comp["position"]` is `Component.initial_position` from
`temper_placer.io.kicad_parser.parse_kicad_pcb` -- the centre of the
footprint's pad bounding box (`_real_board_fixture.py:302-306`). No pad
width, height, shape, or rotation enters the computation anywhere.

Confirmed mechanically:

```
$ grep -rn "pad_geometry\|pad_bounding_radius\|pad_axis_radius\|pad_support_radius\|pad_polygon" \
      packages/temper-placer/src/temper_placer/requirements/ \
      packages/temper-placer/tests/requirements/
NO PAD GEOMETRY IN requirements/
```

(`tests/requirements/validators/clearance.py` is a pure re-export shim onto
the production module above, so there is no second copy with a different
model.)

Three consequences:

1. **PR #388 moves these 9 numbers by exactly 0.000mm.** The corrected
   geometry is not on this code path, and neither was the old
   `max(w,h)/2` formula. Re-running the failing test on `320e3c81` (i.e.
   *with* #388 merged) reproduces all 9 violations bit-identically -- see
   "Reproduction" below.
2. The old model here is *worse* than `max(w,h)/2` would have been.
   `max(w,h)/2` at least over-reported a pad's extent on its short axis;
   origin-to-origin distance ignores copper extent entirely.
3. The error is in the **unsafe** direction. Pads extend outward from a
   component's origin, so origin-to-origin distance is an **upper bound** on
   the true copper-to-copper distance. Every number the checker prints is
   optimistic. It cannot over-report a violation; it can and does hide them.

Per this task's hard constraint, this is reported and **not fixed here**.
Everything below is the measurement that quantifies what fixing it would
surface.

## Reproduction (the control)

`elec/build/` is gitignored, so `make netlist` was run first -- without it
the fixture raises `RealBoardUnavailable` and the test skips rather than
runs.

```
$ make netlist            # -> elec/build/default.net, digest a86a8b2fd183
$ python -m pytest packages/temper-placer/tests/requirements/safety/test_clearance.py -x -q
AssertionError: 9 REQ-SAFE-01 clearance/creepage violations on the real board
(components matched: 158).
1 failed, 19 passed
```

All 9 messages match the CI log verbatim, boundary `DC_BUS<->LV_CONTROL`,
insulation REINFORCED, 158 components matched. Spot-check of the arithmetic:
C17 origin `(20.380, 168.860)`, R32 origin `(24.560, 169.830)`;
`hypot(4.180, 0.970) = 4.291mm` -- exactly the reported figure. This confirms
the measured quantity is origin-to-origin Euclidean distance and nothing else.

## Method for the corrected model

- **Pad copper**: `temper_placer.core.pad_geometry.pad_polygon` (the PR #388
  model), evaluated per pad in world coordinates at `quad_segs=32`, using
  each pad's real `width`, `height`, `shape`, `roundrect_rratio` and
  rotation as parsed from `pcb/temper.kicad_pcb`. Pad world centre =
  `Component.initial_position + R(theta) * Pin.position`, with `R(+theta)`
  -- the convention used by this repo's own parser
  (`io/_parse_modules.py:133`) and writer (`io/_write_modules.py:72`).
- **Distance** = Shapely polygon-to-polygon distance, restricted to pads
  whose *own net* is classified into the relevant domain (a DC_BUS component's
  GND pad is not DC_BUS copper). The all-pads figure is reported alongside.
- **Conservatism**: `pad_polygon` circumscribes the true arc, so a reported
  distance is short of the truth by at most `r * (1/cos(pi/64) - 1)` per
  round pad -- below 0.005mm here. No verdict in this document is within
  0.4mm of its threshold, so approximation never decides an outcome.

**Pipeline validation against PR #388's own numbers.** The same pipeline,
applied to the two isolators PR #388 reports, reproduces its figures:
T1 pad 1 (`tank-out`, DC_BUS) to pad 4 (`gnd`, LV_CONTROL) = **9.100mm**,
exactly PR #388's `9.100`. K1 pad 13 (`power_in.ntc-no`, DC_BUS) to pad A1
(`power_in.bypass_relay-coil1`, LV_CONTROL) = 7.9989mm by polygon, and
**8.000mm exactly** by hand (pad 13 is `rect` 6.35x1.2 at y=152.825, so its
lower edge is y=152.225; pad A1 is a 1.8mm round PTH at y=143.325, top edge
y=144.225; 152.225 - 144.225 = 8.000), matching PR #388's `8.000`. The
0.0011mm delta is exactly the circumscribing-polygon inflation of a 0.9mm
radius. The geometry pipeline used below is therefore the same geometry
#388 already validated.

## Clearance vs creepage on this board

They are **numerically equal here**, and differ only in required minimum
(6.0mm vs 8.0mm).

`pcb/temper.kicad_pcb` contains exactly one `Edge.Cuts` item: a rectangular
`gr_poly` `(20,20)-(172,254)`. There is **no isolation slot, groove, or
cutout anywhere on the board**. Creepage is the shortest path along the
insulating surface; with an unbroken flat surface, that path is the straight
line, so creepage equals clearance for any two points on the same copper
layer. Every pad in the table below is on `F.Cu` or is a through-hole pad
(all layers), so all pairs share a surface and the 2D distance is the correct
figure for both metrics.

This is itself worth stating plainly: **the 8.0mm creepage requirement is
strictly harder than the 6.0mm clearance requirement on this board**, and no
routing of a slot currently exists to relieve it.

## Part 1 -- the 9 reported violations, re-derived

`old` = what the checker reports today (origin-to-origin). `new` =
domain-restricted copper-to-copper on exact pad geometry.

| # | pair | metric | old (mm) | new (mm) | required (mm) | verdict change |
|---|------|--------|---------:|---------:|--------------:|----------------|
| 1 | C17-R32 | clearance | 4.291 | **0.904** | 6.0 | still violation (worse by 3.387) |
| 2 | C17-R32 | creepage | 4.291 | **0.904** | 8.0 | still violation (worse by 3.387) |
| 3 | C17-R26 | creepage | 6.671 | **3.324** | 8.0 | still violation (worse by 3.346) |
| 4 | C17-U13 | creepage | 7.713 | **4.023** | 8.0 | still violation (worse by 3.690) |
| 5 | C22-C16 | creepage | 7.312 | **5.293** | 8.0 | still violation (worse by 2.019) |
| 6 | C22-U15 | creepage | 6.110 | **4.594** | 8.0 | still violation (worse by 1.516) |
| 7 | R30-R1  | creepage | 6.427 | **1.095** | 8.0 | still violation (worse by 5.333) |
| 8 | R30-R32 | creepage | 6.973 | **2.607** | 8.0 | still violation (worse by 4.366) |
| 9 | R30-R73 | creepage | 7.910 | **2.746** | 8.0 | still violation (worse by 5.164) |

**No verdict flips to "clear". All 9 get worse, every one of them.** There is
no good news in this table. The mean error of the origin-to-origin proxy on
these 9 pairs is 3.6mm, always optimistic.

Six of the nine (#1, #2, #3, #7, #8, #9) additionally drop below the *BASIC*
insulation minima (3.0mm clearance / 4.0mm creepage) that the same matrix
applies to this boundary -- i.e. they would fail even if the boundary were
downgraded from REINFORCED, which this task forbids and which the numbers
now independently show would not help.

Closest-pad detail (which copper is actually near what):

| pair | closest domain-classified pads | distance |
|------|-------------------------------|---------:|
| C17-R32 | C17.2 `hb.gate_hs.driver-p2` (roundrect 1.15x2.7) <-> R32.1 `+3V3` (roundrect 0.8x0.95) | 0.904 |
| R30-R1  | R30.2 `tank-out` (PTH 8x8) <-> R1.1 `+15V` (PTH 1.6x1.6) | 1.095 |
| R30-R73 | R30.2 `tank-out` (PTH 8x8) <-> R73.1 `+3V3` | 2.746 (all-pads 2.494) |
| R30-R32 | R30.1 `tank.c_tank1-p2` (PTH 8x8) <-> R32.1 `+3V3` | 2.607 |
| C17-R26 | C17.1 `hb.gate_hs.driver-p1-1` <-> R26.1 `PWM_LS` | 3.324 |
| C17-U13 | C17.1 <-> U13.3 `gnd` | 4.023 (all-pads 3.468) |
| C22-U15 | C22.1 <-> U15.4 `RTD_HW_FAULT` | 4.594 (all-pads 2.915) |
| C22-C16 | C22.1 <-> C16.1 `+15V` | 5.293 |

R30 is the dominant offender and the reason the proxy fails so badly there:
it is a `lib:LitzPad_15A`, 18x8mm, with two **8mm-diameter** through-hole
pads at +/-2.5mm from its origin. Its copper reaches **6.500mm** from the
origin the checker measures from. R1 is a 22.42mm axial THT resistor
reaching 5.880mm. The proxy is blind to all of it.

## Part 2 -- newly exposed violations

Correcting the model does not just move the 9; it surfaces pairs the proxy
never flagged. Full sweep over every pair the validator enumerates
(`_domain_boundary_pairs`), same domains, same thresholds:

| boundary | insulation | pairs | violations OLD | violations NEW |
|----------|-----------|------:|---------------:|---------------:|
| MAINS<->LV_CONTROL | basic (3.0/4.0) | 570 | 0 / 0 | 0 / 0 |
| MAINS<->LV_CONTROL | reinforced (6.0/8.0) | 570 | 0 / 0 | 0 / 0 |
| DC_BUS<->LV_CONTROL | basic (3.0/4.0) | 5806 | 0 / 0 | **5 / 8** |
| DC_BUS<->LV_CONTROL | reinforced (6.0/8.0) | 5806 | **1 / 8** | **13 / 19** |
| MAINS<->ISOLATED | reinforced | 0 | -- | -- |
| LV_CONTROL<->LV_CONTROL | functional (0.5/1.0) | 6441 | 0 / 0 | 0 / 0 |

(cells are `clearance / creepage` pair counts)

The failing count goes from **9 violation records to 32**. At the REINFORCED
boundary the pair count rises from 8 to 19, and the *clearance* pair count --
the more serious metric, and the one the board currently fails only once --
rises from **1 to 13**.

**The 11 newly exposed pairs**, none of which the checker reports today:

| pair | new (mm) | old (mm) | error | fails |
|------|---------:|---------:|------:|-------|
| C22-L2  | **1.969** | 10.341 | -8.372 | clearance + creepage (also BASIC) |
| R30-R54 | **3.662** | 10.763 | -7.101 | clearance + creepage (also BASIC) |
| R30-U13 | **3.790** | 12.233 | -8.443 | clearance + creepage (also BASIC) |
| R30-R46 | **5.694** | 12.035 | -6.342 | clearance + creepage |
| R30-R26 | **5.830** | 13.022 | -7.192 | clearance + creepage |
| R30-C30 | **6.362** | 13.190 | -6.828 | creepage |
| C17-R73 | **6.514** |  8.198 | -1.683 | creepage |
| C17-R54 | **6.657** | 10.052 | -3.395 | creepage |
| C22-R77 | **6.720** |  8.941 | -2.221 | creepage |
| C22-C12 | **6.741** |  9.309 | -2.568 | creepage |
| C22-C37 | **7.599** | 10.092 | -2.493 | creepage |

The worst of these, **C22-L2 at 1.969mm**, is reported today as **10.341mm**
-- 8.4mm of false margin, and 5.3x the true figure. L2's copper reaches
8.233mm from its origin. Three of the eleven breach even the BASIC minima.

**Rotation-convention caveat (2 of 19 pairs).** World pad centres require
rotating the local pad offset by the footprint angle. This repo's parser and
writer both use `R(+theta)`; KiCad's own internal convention is `R(-theta)`.
The two agree for every footprint at 0/180 degrees and for symmetric two-pad
passives, which covers **all 8 originally-reported pairs** -- Part 1 is
convention-independent. Running the full sweep under both conventions gives
**19 violating pairs either way**, with 17 pairs identical; `C22-L2`
(1.969mm) appears only under `R(+theta)` and `R30-L2` only under
`R(-theta)`. Both are violations of similar severity, so the *conclusion* is
unaffected, but which of the two is real depends on settling the convention.
Empirical evidence weakly favours `R(+theta)` (of pads on 90/270-rotated
footprints, 5 touch their own net's routing under `R(+theta)` vs 1 under
`R(-theta)`); this is weak because the board's routing is largely detached
from its pads (only 68.6% of pads on routed nets touch their net's copper
even on unrotated footprints). **Flagging this as a separate open question.**

## Part 3 -- what a designer must actually do

Classification per surviving violation. Three categories were tested for, not
assumed.

### (a) Placement problems -- 17 of 19 pairs

Fixable by moving parts. The board is 152x234mm with origins spanning
x 1.0-149.9, y 1.2-232.8 -- it is densely packed but not full, and the
required moves are modest (0.4mm to 7.1mm of extra separation).

The measurement that supports the classification: for each pair, the extra
separation needed at the 8.0mm creepage requirement, and the origin-to-origin
distance a *correct* checker would have to enforce (= copper gap plus both
components' copper reach).

| pair | copper gap | must gain | reach A | reach B | required origin distance |
|------|-----------:|----------:|--------:|--------:|-------------------------:|
| C17-R32 | 0.904 | 7.096 | 2.863 | 1.365 | 11.387 |
| R30-R1  | 1.095 | 6.905 | 6.500 | 5.880 | 13.333 |
| C22-L2  | 1.969 | 6.031 | 1.336 | 8.233 | 16.372 |
| R30-R32 | 2.607 | 5.393 | 6.500 | 1.365 | 12.366 |
| R30-R73 | 2.746 | 5.254 | 6.500 | 1.365 | 13.164 |
| C17-R26 | 3.324 | 4.676 | 2.863 | 1.365 | 11.346 |
| R30-R54 | 3.662 | 4.338 | 6.500 | 1.365 | 15.101 |
| R30-U13 | 3.790 | 4.210 | 6.500 | 2.166 | 16.443 |
| C17-U13 | 4.023 | 3.977 | 2.863 | 2.166 | 11.690 |
| C22-U15 | 4.594 | 3.406 | 1.336 | 2.166 |  9.516 |
| C22-C16 | 5.293 | 2.707 | 1.336 | 1.336 | 10.019 |
| R30-R46 | 5.694 | 2.306 | 6.500 | 1.365 | 14.342 |
| R30-R26 | 5.830 | 2.170 | 6.500 | 1.365 | 15.192 |
| R30-C30 | 6.362 | 1.638 | 6.500 | 1.336 | 14.828 |
| C17-R73 | 6.514 | 1.486 | 2.863 | 1.365 |  9.683 |
| C17-R54 | 6.657 | 1.343 | 2.863 | 1.365 | 11.395 |
| C22-R77 | 6.720 | 1.280 | 1.336 | 1.365 | 10.221 |
| C22-C12 | 6.741 | 1.259 | 1.336 | 2.863 | 10.568 |
| C22-C37 | 7.599 | 0.401 | 1.336 | 1.336 | 10.493 |

The actionable structure: **only four HV parts generate all 19 pairs** --
R30 (8 pairs), C22 (6), C17 (5), plus R1/L2 as counterparties. R30 alone
accounts for 8, purely because its 6.5mm copper reach means any SELV part
must sit **>=14.5mm from R30's origin** to make 8.0mm of creepage. The
placer was solved against a constraint that thought 8.0mm from R30's *origin*
was sufficient. Re-solving with copper-extent-aware constraints is the fix;
this is precisely what `pad_geometry.pad_axis_radius` exists to provide, and
what the CP-SAT domain-clearance encoder
(`placer/cp_sat/domain_clearance.py`) would need to consume.

### (b) Footprint problems -- 5 parts, not fixable by moving anything

These are **intra-footprint** HV-to-SELV pad pairs: a single part whose own
pads breach the barrier. The validator can never see these -- it only pairs
distinct components (`_domain_boundary_pairs` skips `comp_a.ref ==
comp_b.ref`). They are invisible to CI today, at any placement.

| part | HV pad | SELV pad | gap | verdict at 6.0/8.0 |
|------|--------|----------|----:|--------------------|
| C6 | `PWR_RTN` | `gnd` | **3.198** | fails clearance AND creepage |
| K2 | `PWR_RTN` | `discharge.k_dis1-coil1` | **3.557** | fails clearance AND creepage |
| K3 | `DC_BUS_RTN` | `discharge.k_dis2-coil1` | **3.557** | fails clearance AND creepage |
| U3 | `PWR_RTN` (pin 2) | `gnd` (pin 5) | **6.018** | passes clearance by 0.018mm, **fails creepage** |
| U7 | `hb.gate_hs.driver-p2` (pin 14) | `+3V3` (pin 3) | **7.250** | passes clearance, **fails creepage** |
| K1 | `power_in.ntc-no` (13) | `power_in.bypass_relay-coil1` (A1) | 8.000 | passes both, **zero margin** |
| T1 | `tank-out` (1) | `gnd` (4) | 9.100 | passes both |
| PS1 | `PWR_RTN` (2) | `+15V` (3) | 35.496 | passes both |

No placement change can alter any of these -- the distance is fixed by the
part's own pad pattern. The remedy is a **different part or a different
footprint** (wider-body optocoupler/driver, larger relay pitch), or a
documented deviation. U3 and U7 are the interesting cases: both clear the
6.0mm clearance bar and fail only the 8.0mm creepage bar, which is exactly
the gap an isolation slot milled under the part is normally used to close --
and this board has none (see below). K1 at exactly 8.000mm has zero margin
against a REINFORCED requirement, which is not a design state anyone should
sign off on even though it technically passes.

### (c) Board-outline / stackup problems -- 1, and it is the enabling one

**The board has no isolation slot.** A single rectangular `Edge.Cuts` outline,
no cutout anywhere. On a slotted board, creepage across a barrier is
lengthened by routing the path around the slot, which is the standard way to
make 8.0mm of creepage in less than 8.0mm of lateral space, and the only way
to rescue U3 (6.018mm) and U7 (7.250mm) from category (b) without changing
the parts. Cutting a slot is an outline change, not a placement change.

The repo already has the machinery for this and it is not being applied to
this board: `io/isolation_slot_geometry.py`, and the Rust DRC rule
`packages/temper-drc-rs/src/rules/routing/isolation_slot.rs` that
`check_creepage_path`'s own docstring points at for "real board geometry".

### Secondary finding, flagged not concluded: routed copper is worse than pads

Everything above is pads-only, which is the like-for-like comparison against
a component-pair checker. Including the board's routed copper
(1229 domain-classified track segments + 12 vias, layer-aware so that a
B.Cu track under an F.Cu pad is not counted as contact) gives a **minimum
same-layer HV-to-SELV separation of 0.000mm on F.Cu** -- an
`power_in.ntc-no` (DC_BUS) track running into K1's `power_in.bypass_relay-coil1`
(LV_CONTROL) pad near (153.64, 163.51) -- and 0.023mm on B.Cu
(U6.1 `GATE_LS` to an `i2c_scl_ui` track). Pads alone give 0.904mm.

This is reported with a caveat and not folded into the tables: the board's
routing is in a questionable state (only 68.6% of pads on routed nets touch
their own net's copper), so these may be artifacts of incomplete routing
rather than a final result. It is flagged because if it is real, no amount of
re-placement fixes it, and because the copper-vs-origin blindness documented
above applies to the router's output just as much as to the placement.

## Summary of what changes if the checker is corrected

| | today | on exact pad geometry |
|---|------:|----------------------:|
| REQ-SAFE-01 violation records | 9 | **32** |
| violating component pairs (REINFORCED) | 8 | **19** |
| clearance-metric pairs (6.0mm) | 1 | **13** |
| pairs also breaching BASIC (3.0/4.0mm) | 0 | **8** |
| intra-footprint violations | 0 (unmeasurable) | **5** |
| verdicts that improve | -- | **0** |

## Reproducing this document

Run `make netlist` first (`elec/build/` is gitignored; without it the fixture
raises `RealBoardUnavailable` and the test skips silently rather than runs).
The analysis is then reproducible with a short harness that does exactly
three things, all against production code with no fixture of its own:

1. `load_real_board_placement()` from
   `tests/requirements/safety/_real_board_fixture.py` for the 158 classified
   components and the net-to-`VoltageDomain` map;
2. `parse_kicad_pcb("pcb/temper.kicad_pcb")` for each pad's real
   `width`/`height`/`shape`/`roundrect_ratio`/`layer` and local offset, plus
   `kiutils` for the raw footprint angles;
3. `pad_geometry.pad_polygon(...)` per pad at `quad_segs=32`, placing it at
   `initial_position + R(+theta) * Pin.position`, then Shapely
   polygon-to-polygon distance over the same pairs
   `_domain_boundary_pairs()` enumerates.

The throwaway harness scripts were deliberately not committed. Every number
above comes from `pcb/temper.kicad_pcb` and `elec/build/default.net` (digest
`a86a8b2fd183`), not from a synthetic fixture.

## Constraints honoured

- `pcb/temper.kicad_pcb` not modified (no placement change, no keepout).
- No test weakened, skipped, xfailed, or allowlisted. The test still fails
  with the same 9 violations.
- 6.0mm clearance / 8.0mm creepage / REINFORCED unchanged.
- The checker was **not** fixed, per the hard constraint -- it is
  characterised here and the decision on who changes it is left open.
