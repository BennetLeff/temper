<!-- provenance: commit=a0743083b4c63de43af20b8574f21cd24836686f dirty=true (base commit = origin/main after this branch was rebased onto it; the numbers below were first measured at 65fc5df7 and re-verified unchanged after the rebase -- the three PRs main advanced by, #389/#390/#391, touch only docs/evidence/, scripts/ and AGENTS.md, none of the code under measurement. dirty=true because the numbers are produced BY the fix on branch fix/clearance-copper-to-copper, which is the change under measurement. pcb/temper.kicad_pcb is byte-identical to the base commit -- verified with `git diff --stat origin/main -- pcb/`.) -->

# REQ-SAFE-01: the clearance checker now measures copper, not origins

Branch `fix/clearance-copper-to-copper`, rebased onto `origin/main`
(`a0743083`; originally cut from `65fc5df7`).
Netlist digest `a86a8b2fd183` (`make netlist` run first -- `elec/build/` is
gitignored and without it the real-board fixture raises
`RealBoardUnavailable` and the test **skips silently** rather than running).

## Answer to the only question that matters

**Yes. This design has more known safety violations tonight than it did this
morning: 9 violation records over 8 component pairs became 56 records over 24
pairs.**

Nothing on the board changed. `pcb/temper.kicad_pcb` is byte-identical to
`origin/main`. The violations were always there; the checker could not see
them. Every one of the 8 originally-reported pairs survives, every one of them
is worse, and **zero verdicts improve**.

## The defect

`requirements/validators/clearance.py::_check_distance` -- the single shared
core behind `check_domain_clearance`, `check_creepage_path` and
`verify_iec60335_compliance` -- computed:

```python
dist = _distance(pos_a, pos_b)      # math.dist of two component origins
```

`comp["position"]` is `Component.initial_position`: the centre of the
footprint's pad bounding box. No pad width, height, shape or rotation entered
anywhere; `grep` for pad geometry across `requirements/` returned nothing.

Copper extends **outward** from an origin, so origin-to-origin distance is an
**upper bound** on true copper-to-copper separation. Every clearance and
creepage number REQ-SAFE-01 has ever reported was optimistic, in the unsafe
direction. It could not over-report a violation. It could and did hide them.

Characterised in full first, in PR #389 /
`docs/evidence/2026-07-28-req-safe-01-rederivation.md`. This document is the
fix and its verification.

## What was changed

1. **`core/pad_geometry.pad_pair_distance` (new).** Exact copper-to-copper
   distance between two pads. Every KiCad pad shape this board uses is
   `core_rectangle ⊕ disk(r)` (that module's own decomposition, from PR #388);
   writing the Minkowski sum as a sublevel set, `S ⊕ D_r = {x : dist(x,S) ≤ r}`,
   gives directly

   ```
   dist(A ⊕ D_ra, B ⊕ D_rb) = max(0, dist(A, B) - ra - rb)
   ```

   and `dist(A, B)` between two rotated rectangles (or their degenerate
   segment/point forms, for `oval`/`circle`) is exactly computable. **No arc is
   ever polygonised, so there is no approximation error term.** This is not a
   second geometry model -- it is the same model evaluated exactly instead of
   through `pad_polygon`'s circumscribing buffer. Why it matters is in
   "K1 and the zero-margin trap" below.

2. **`requirements/validators/clearance.py`** (+ `_copper.py`, the geometry
   half, split out so `clearance.py` stays under the repo's 1000-line file
   cap). `_check_distance` now measures pad copper. Only pads whose *own net* classifies into the relevant domain
   count as that domain's copper (a DC_BUS part's GND pad is not DC_BUS
   copper). A cheap sound prune -- `origin_distance - reach_a - reach_b`, using
   `pad_bounding_radius` -- skips pairs that provably cannot violate; on the
   real board it eliminates 5,739-6,387 of each row's pairs, and its soundness
   is tested directly over a sweep straddling the threshold.

3. **Intra-footprint crossings are now visible** (see below).

4. **Creepage is a distinct metric with a declared model** (see below).

5. **`io/_parse_modules.py`** records the footprint's exact rotation in
   `attributes["_rotation_deg"]`. `Component.initial_rotation` is quantized to
   a 0-3 quadrant index and silently loses any non-multiple-of-90 angle. Every
   footprint on this board is at a multiple of 90, so this changes no number
   here -- it removes an assumption rather than relying on it.

6. **`tests/.../_real_board_fixture.py`** supplies real pads, per-footprint
   rotation, and the `Edge.Cuts` outline. Its own unclassified-component
   HV-proximity check carried the identical origin-distance defect and was
   fixed the same way, through the validator's `_CopperModel` rather than a
   second implementation.

7. **Failure output** is a worst-first table (pair, boundary, insulation,
   metric, measured, required, shortfall, model) plus the closest pad pair per
   violation, instead of ~56 repr'd dataclasses.

## Verification

### The control, reproduced first

Before trusting any new number, the old ones were reproduced on a pristine
`origin/main` checkout:

```
1 failed, 592 passed, 23 skipped, 1 xfailed
AssertionError: 9 REQ-SAFE-01 clearance/creepage violations on the real board
(components matched: 158).
```

Spot-check of the arithmetic: `C17` origin `(20.380, 168.860)`, `R32` origin
`(24.560, 169.830)`, `hypot(4.180, 0.970) = 4.291mm` -- exactly the figure CI
reports for that pair. The measured quantity was origin-to-origin Euclidean
distance and nothing else.

### Cross-check against the known-good isolator figures

PR #388's independently-derived isolator numbers, reproduced by this
implementation to the micron:

| isolator | pads | PR #388 | this implementation |
|---|---|---:|---:|
| T1 | 1 (`tank-out`) <-> 4 (`gnd`) | 9.100 | **9.100000** |
| K1 | 13 (`power_in.ntc-no`) <-> A1 (`power_in.bypass_relay-coil1`) | 8.000 | **8.000000** |

Pinned as tests (`test_clearance_copper.py::TestRealBoardIsolatorFigures`).

### K1 and the zero-margin trap

K1's HV<->SELV pad pair sits at *exactly* 8.000mm against an 8.000mm
REINFORCED creepage requirement -- zero margin. Hand-derivable: pad 13 is a
`rect` 6.35x1.2 centred at y=152.825, lower edge y=152.225; pad A1 is a 1.8mm
round PTH at y=143.325, upper edge y=144.225; `152.225 - 144.225 = 8.000`.

A first implementation of this fix used `pad_polygon` at `quad_segs=32` and
reported **7.9989mm** -- the circumscribing-polygon inflation of a 0.9mm
radius -- which **manufactured a violation out of nothing**, on a pair that is
genuinely compliant. That is what drove the switch to the exact
Minkowski formulation. No `quad_segs` fixes a zero-margin case; only exactness
does. `test_k1_passes_reinforced_creepage_with_exactly_zero_margin` fails if
anyone reintroduces a polygonised measurement.

(K1 at exactly 8.000mm with zero margin against a REINFORCED requirement is
not a design state anyone should sign off on. It is not a violation and is not
counted as one here, but it is one thermal-expansion tolerance from being one.)

### Test suites

| suite | `origin/main` | this branch |
|---|---|---|
| `tests/requirements/` + `test_pad_geometry` + `test_domain_clearance` + `tests/io` | 1 failed, 592 passed, 23 skipped, 1 xfailed | 1 failed, **625 passed**, 23 skipped, 1 xfailed |

**The single failure is the same test on both sides**:
`test_temper_board_clearance_compliance`. It failed before this change (with
9 violations) and fails after it (with 56). There are no other pre-existing
failures to account for and no new ones. The 33 additional passes are the new
unit tests. Re-run unchanged after the rebase onto `a0743083`.

The whole `packages/temper-placer` suite (`-m "not slow"`, 6,087 tests) has
**148 pre-existing failures** on both sides, none reachable from this diff --
they sit in `test_projections`, `mfem_runner`, `ucc21550`, `heuristics` and
`timing`. The only one whose *name* looks related,
`tests/geometry/test_geometry.py::TestOverlap::test_clearance_violation`, is
an unrelated API-drift failure in `temper_placer.geometry`
(`check_clearance_violation() takes 2 positional arguments but 9 were given`);
it reproduces identically at the branch base `65fc5df7`, and
`check_clearance_violation` appears zero times in this diff.

`ruff check` clean on every touched file. `check_vacuous_gates.py`,
`check_manifest_gate.py`, `check_evidence_provenance.py --check-shrink`,
`check_undeclared_imports.py`, `import_linter_gate.py` and
`tools/loc_cap_check.py` all pass.

`scripts/check_typecheck_gate.py` reports **421 errors in 43 files on both
`origin/main` and this branch**, with the same single unallowlisted violation
(`placer/cp_sat/isolation_barrier.py`, 2 errors, introduced by PR #388 and
untouched here). Verified by running the gate on a pristine `origin/main`
checkout, not asserted. This change adds zero type errors.

### The one red CI job, accounted for

`Golden Regression Check` fails on this PR with:

```
ERROR: Regression detected for temper_production:
       component_count: 168.0 vs baseline 170.0 (-2.0)
```

**Pre-existing, and unrelated.** The identical failure, with the identical
message, is present on `origin/main` at `320e3c81` (run 30404606887) and on
the five main commits before it -- the workflow has been red on `main`
continuously. `power_pcb_dataset/baselines/temper_production_baseline.yaml`
records 170 components; `pcb/temper.kicad_pcb` has 168 (confirmed directly:
`kiutils` reports 168 footprints, all on F.Cu). The baseline is stale relative
to the board.

The job runs on this PR only because it triggers on any change under
`packages/temper-placer/src/temper_placer/**`. This change cannot affect the
count: the only parser edit adds one key to an existing `attributes` dict and
touches no component-collection logic, and `pcb/` is untouched. Refreshing
that baseline is a separate concern and is deliberately not done here -- it
would mean editing a golden artifact to make a red job green, on a PR whose
entire point is that a safety gate should be allowed to go red honestly.

No test was weakened, skipped, xfailed, marked or allowlisted. Two were
*strengthened*: `test_mains_to_control_clearance` and
`test_surface_path_consideration` both asserted `X or not X` -- vacuously true
for any implementation whatsoever, including the one that returned clearance
under the name creepage. They now assert real properties.

## Results: every pair, old vs new

`old` = what the checker reported (origin-to-origin). `new` = exact
copper-to-copper. Sorted worst-first.

| pair | kind | old (mm) | new (mm) | error | fails |
|---|---|---:|---:|---:|---|
| C17-R32 | inter | 4.291 | **0.905** | -3.386 | clearance + creepage |
| R30-R1 | inter | 6.427 | **1.100** | -5.327 | clearance + creepage |
| C22-L2 | inter | 10.341 | **1.969** | -8.372 | clearance + creepage |
| R30-R32 | inter | 6.973 | **2.612** | -4.362 | clearance + creepage |
| R30-R73 | inter | 7.910 | **2.750** | -5.160 | clearance + creepage |
| C6 | **intra** | n/a -- invisible | **3.200** | n/a | clearance + creepage |
| C17-R26 | inter | 6.671 | **3.325** | -3.346 | clearance + creepage |
| K2 | **intra** | n/a -- invisible | **3.559** | n/a | clearance + creepage |
| K3 | **intra** | n/a -- invisible | **3.559** | n/a | clearance + creepage |
| R30-R54 | inter | 10.763 | **3.666** | -7.097 | clearance + creepage |
| R30-U13 | inter | 12.233 | **3.794** | -8.439 | clearance + creepage |
| C17-U13 | inter | 7.713 | **4.023** | -3.690 | clearance + creepage |
| C22-U15 | inter | 6.110 | **4.594** | -1.515 | clearance + creepage |
| C22-C16 | inter | 7.312 | **5.293** | -2.018 | clearance + creepage |
| R30-R46 | inter | 12.035 | **5.699** | -6.337 | clearance + creepage |
| R30-R26 | inter | 13.022 | **5.835** | -7.187 | clearance + creepage |
| U3 | **intra** | n/a -- invisible | **6.020** | n/a | creepage |
| R30-C30 | inter | 13.190 | **6.367** | -6.823 | creepage |
| C17-R73 | inter | 8.198 | **6.515** | -1.683 | creepage |
| C17-R54 | inter | 10.052 | **6.657** | -3.395 | creepage |
| C22-R77 | inter | 8.941 | **6.721** | -2.220 | creepage |
| C22-C12 | inter | 9.309 | **6.742** | -2.567 | creepage |
| U7 | **intra** | n/a -- invisible | **7.250** | n/a | creepage |
| C22-C37 | inter | 10.092 | **7.599** | -2.492 | creepage |

Every error is negative. The proxy was optimistic on all 19 inter-component
pairs, by a mean of **4.6mm** and a maximum of **8.4mm** (`C22`-`L2`, reported
at 10.341mm against a true 1.969mm -- 5.3x the real figure).

The 8 pairs the old checker did report all survive: `C17-R32`, `C17-R26`,
`C17-U13`, `C22-C16`, `C22-U15`, `R30-R1`, `R30-R32`, `R30-R73`. The other 11
inter pairs and all 5 intra parts are newly visible.

These figures agree with PR #389's independent polygon-based re-derivation to
within 0.006mm on every pair, the expected residual of that method's
circumscribing buffer.

## Boundary sweep

Cells are `clearance / creepage` violating-pair counts.

| boundary | insulation | inter pairs | OLD | NEW | intra parts | NEW intra |
|---|---|---:|---:|---:|---:|---:|
| MAINS<->LV_CONTROL | basic (3.0/4.0) | 570 | 0 / 0 | 0 / 0 | 0 | 0 / 0 |
| MAINS<->LV_CONTROL | reinforced (6.0/8.0) | 570 | 0 / 0 | 0 / 0 | 0 | 0 / 0 |
| DC_BUS<->LV_CONTROL | basic (3.0/4.0) | 5806 | 0 / 0 | **5 / 8** | 8 | **0 / 3** |
| DC_BUS<->LV_CONTROL | reinforced (6.0/8.0) | 5806 | **1 / 8** | **13 / 19** | 8 | **3 / 5** |
| MAINS<->ISOLATED | reinforced (6.0/8.0) | 0 | -- | -- | 0 | -- |
| LV_CONTROL<->LV_CONTROL | functional (0.5/1.0) | 6441 | 0 / 0 | 0 / 0 | 0 (by design) | -- |

| | before | after |
|---|---:|---:|
| violation records | 9 | **56** |
| violating pairs | 8 | **24** |
| clearance-metric pairs at 6.0mm | 1 | **13** |
| pairs also breaching BASIC (3.0/4.0mm) | 0 | **11** |
| intra-footprint violations | 0 (unmeasurable) | **5 parts / 11 records** |
| verdicts that improve | -- | **0** |

Eleven pairs breach even the **BASIC** 3.0/4.0mm minima -- i.e. they would
fail even if the boundary were downgraded from REINFORCED. Downgrading is
forbidden by this task and the numbers independently show it would not help.

## Creepage vs clearance: what was done

They were the same computation with different wording and different
thresholds. They are now different quantities with different code paths and a
**declared model recorded on every violation**.

- **Clearance** = shortest distance through air = the straight line between
  nearest copper. That is exactly what the pad-pair distance computes, so
  clearance is reported directly and is exact.
- **Creepage** = shortest path along the insulating surface, which must go
  *around* slots, cutouts and board edges. Routed through
  `_creepage_from_clearance`, which branches on the board geometry the
  placement declares:
  - **no cutouts** -- the surface is unbroken, the surface geodesic between two
    coplanar points **is** the straight line, so the figure is **exact**, not an
    approximation. Tagged `CREEPAGE_MODEL_UNBROKEN_SURFACE`.
  - **cutouts present** -- the true path detours and is strictly longer.
    **Slot-aware surface pathing is not implemented.** The straight line is
    returned as an explicit conservative *lower bound* (it can over-report a
    violation near a slot; it can never mask one), tagged
    `CREEPAGE_MODEL_STRAIGHT_LINE_LOWER_BOUND` on every violation **and** logged
    at WARNING on every call.

This is the brief's second option, taken deliberately. A visibility-graph
geodesic between two pad *polygons* (not two points) has to minimise over all
candidate endpoint pairs to stay a sound lower bound; getting that subtly
wrong yields a metric that over-reports margin, which is the exact failure
mode being fixed here. A loudly-conservative correct-direction metric is worth
more on a mains-connected board than a complex possibly-unsound one. The
machinery a real implementation would consume already exists
(`io/isolation_slot_geometry.py`, `temper-drc-rs/src/rules/routing/isolation_slot.rs`).

**`pcb/temper.kicad_pcb` has exactly one `Edge.Cuts` item** -- a rectangular
`gr_poly` -- **and no slot, groove or cutout anywhere**, so on today's board the
two metrics coincide numerically. That is now a *measured* fact, re-derived
every run from the real outline and printed by the test, not an assumption in
a comment. It is also the reason the 8.0mm creepage requirement is strictly
harder than the 6.0mm clearance requirement here: there is no slot to relieve
it. Cutting one is the standard way to make 8.0mm of creepage in less lateral
space, and the only route that rescues U3 and U7 below without changing parts.

`test_clearance_copper.py::TestCreepageVsClearance` proves the distinction is
structural: a board with a cutout flips the recorded model and fires the
warning; clearance is unaffected by the same cutout; and `creepage >=
clearance` holds in both configurations.

## Intra-footprint crossings: what was done

**Extended, not deferred.** `_domain_boundary_pairs` pairs only *distinct*
components, so a part whose own pads straddle the HV<->SELV barrier was
invisible at every possible placement.

They are enumerated by a separate function,
`_intra_component_boundary_components`, rather than by relaxing
`_domain_boundary_pairs`. That is deliberate:
`placer.cp_sat.domain_clearance.generate_domain_clearance_constraints` builds
one `SeparatedConstraint` per pair from the same function, and a self-pair
there becomes a nonsensical `SeparatedConstraint(a=X, b=X)`. The separation is
pinned by a test.

Every part on this board whose own pads cross the barrier:

| part | HV pad | SELV pad | gap (mm) | verdict at 6.0/8.0 |
|---|---|---|---:|---|
| C6 | `PWR_RTN` (1) | `gnd` (2) | **3.200** | FAILS clearance, FAILS creepage |
| K2 | `PWR_RTN` (1) | `discharge.k_dis1-coil1` (2) | **3.559** | FAILS clearance, FAILS creepage |
| K3 | `DC_BUS_RTN` (1) | `discharge.k_dis2-coil1` (2) | **3.559** | FAILS clearance, FAILS creepage |
| U3 | `PWR_RTN` (2) | `gnd` (5) | **6.020** | passes clearance by 0.020mm, **FAILS creepage** |
| U7 | `DC_BUS_RTN` (9) | `+3V3` (8) | **7.250** | passes clearance, **FAILS creepage** |
| K1 | `power_in.ntc-no` (13) | `power_in.bypass_relay-coil1` (A1) | 8.000 | passes both, **zero margin** |
| T1 | `tank-out` (1) | `gnd` (4) | 9.100 | passes both |
| PS1 | `PWR_RTN` (2) | `+15V` (3) | 35.500 | passes both |

No placement change alters any of these. The remedy is a different part, a
different footprint, a milled isolation slot, or a documented deviation.

**Same-domain rows are deliberately excluded** from intra-component pairing.
The one same-domain matrix row is LV_CONTROL<->LV_CONTROL FUNCTIONAL
(0.5/1.0mm); applying it inside a footprint flags the manufacturer's own fixed
pad pitch. Measured, not assumed: **41 further violation records across 33
parts**, closest pairs being a 0.35mm QFN/SOT pitch and a 0.65mm 0402 pad gap.
None is a barrier crossing, none is actionable (you cannot re-pitch a 0402),
and functional insulation between two SELV nets of one part is governed by
that part's datasheet ratings, not by PCB layout. Pinned by
`test_intra_pairs_are_not_generated_for_same_domain_boundaries`.

## Why the numbers move so far: copper reach

The distance from a component's origin to the furthest point of its own
copper, for every part involved:

| ref | copper reach (mm) | | ref | copper reach (mm) |
|---|---:|---|---|---:|
| K2, K3 | 10.546 | | R1 | 5.880 |
| L2 | 8.233 | | C6 | 3.400 |
| U7 | 7.471 | | C12, C17 | 2.872 |
| R30 | 6.500 | | U13, U15 | 2.166 |
| U3 | 5.607 | | R26/R32/R46/R54/R73/R77 | 1.365 |
| | | | C16/C22/C30/C37 | 1.336 |

R30 alone generates 8 of the 19 inter pairs: it is a `lib:LitzPad_15A` with
two 8mm-diameter through-hole pads at +/-2.5mm from its origin, so its copper
reaches **6.500mm** from the point the old checker measured from. Any SELV part
must sit >=14.5mm from R30's *origin* to make 8.0mm of creepage. The placer
solved against a constraint that thought 8.0mm from R30's origin was enough.

Four HV parts -- R30 (8 pairs), C22 (6), C17 (5), plus R1/L2 as counterparties
-- generate all 19 inter pairs.

## Secondary finding: the HV-proximity check had the same defect

`_real_board_fixture.py`'s fail-closed check ("no unclassified component may
sit within the largest IEC margin of a declared-HV part") also ranked by
origin distance. Fixed the same way, through the same `_CopperModel`. It still
passes, but the margins are much thinner than the old model implied:

| unclassified ref | nearest HV | copper (mm) | origins (mm) |
|---|---|---:|---:|
| R42 | R5 | **8.570** | 11.846 |
| R34 | R5 | **8.645** | 12.340 |
| R40 | R5 | **8.705** | 11.495 |
| R45 | R5 | **9.681** | 14.379 |
| R64 | U2 | **10.661** | 13.541 |

The closest had 3.8mm of apparent margin against the 8.0mm bar; it actually
has **0.57mm**.

## Open questions, flagged not concluded

- **Rotation convention.** World pad centres require rotating the local pad
  offset by the footprint angle. This implementation uses `R(+theta)`, matching
  this repo's own parser (`io/_parse_modules.py`, which builds
  `initial_position` that way) and writer -- picking the opposite sign for pads
  only would make the pad set inconsistent with the origin it is reported
  against. KiCad's internal `RotatePoint` is `R(-theta)`. Every footprint on
  this board is at a multiple of 90 degrees, and PR #389 measured that both
  conventions yield 19 violating inter pairs with 17 identical; all 8
  originally-reported pairs are convention-independent. No conclusion in this
  document depends on it, but it should be settled.
- **Routed copper is not included.** Everything here is pads-only, the
  like-for-like comparison against a component-pair checker. PR #389 measured
  minimum same-layer HV<->SELV separation including tracks at **0.000mm on
  F.Cu**, caveated because only 68.6% of pads on routed nets touch their own
  net's copper. If that is real, no re-placement fixes it.
- **Layers are collapsed to 2D.** A cross-layer pair is separated in 3D by at
  least the dielectric thickness as well, so the 2D figure is a lower bound --
  the safe direction. Not special-cased.

## Constraints honoured

- `pcb/temper.kicad_pcb` **not modified**: no placement change, no keepout, no
  slot. Verified with `git diff origin/main -- pcb/`.
- No test weakened, skipped, xfailed, marked or allowlisted. Two vacuous
  assertions were strengthened.
- 6.0mm clearance / 8.0mm creepage / REINFORCED classification unchanged.
- No `git stash` used.

## Reproducing

```
make netlist                       # elec/build/ is gitignored; without it the
                                   # fixture skips silently rather than running
cd packages/temper-placer
uv run --no-sync python -m pytest tests/requirements/safety/ -q
```
