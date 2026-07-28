<!-- provenance: commit=c0109b1c49c5714809b062ce9a86b932745982fd dirty=false -->

# Physical mains<->SELV isolation barrier: feasibility, gate, and honest result

Base commit: `60d441f2` (`fix(placer): revert the outer-layer half of the
stackup fix, keep the phantom-layer half`), branch
`docs/methodology-loop-discipline`. Work done in worktree
`agent-a19a2f5a6e7f6fd91`, branch `fix/mains-selv-isolation-keepout`,
checked out directly at that commit.

All numbers below were produced by actually running the commands/scripts
shown, on this machine (macOS arm64, Python 3.12.13, `uv`), against the
real `elec/domain_manifest.yaml` and `pcb/temper.kicad_pcb` as of this
worktree's base commit, unless explicitly marked UNVERIFIED.

## Summary (read this first)

**Task 1 finding: a contiguous mains<->SELV keepout CANNOT be drawn on the
current placement without carving through existing HV or SELV components.**
The current layout interleaves the two domains across virtually the
entire 152mm x 234mm board -- every 10mm-wide vertical strip across the
full board width contains components from both domains, and the two
domains' pad bounding boxes are both within ~1.5mm of all four board
edges. This is the honest deliverable the plan asked for: report it and
stop, rather than draw a barrier that would immediately violate itself.

**Task 2 (add the keepout) was correctly skipped** as a direct consequence
-- no keepout geometry was added to `pcb/temper.kicad_pcb`. Zero bytes of
that file were touched by this change.

**Task 3 (the gate) was completed in full.** `scripts/check_isolation_keepout.py`
exists, is unit-tested (27 tests, synthetic fixtures, all passing), is
wired into `scripts/manifest.yaml` and `.github/workflows/python-tests.yml`
with no `continue-on-error`, and when run against the real board **fails
closed with exit code 3**, reporting precisely that the barrier is
missing and what a human must do about it. This is the expected, correct
outcome given Task 1's finding -- not a bug.

**Falsifier stated and reported (see "Falsifier" section below): FALSIFIED.**
The barrier cannot be drawn on the current placement without cutting
through existing copper/components. This is reported as a placement
finding, not papered over by shrinking the required separation.

## Task 1 -- can a barrier even be drawn?

### Method

Wrote a one-off analysis script (not committed -- scratch analysis only,
matching this plan's instruction that only the gate itself is the durable
deliverable) that:

1. Loads `elec/domain_manifest.yaml`'s `domains.HV.nets` (21 nets) and
   `domains.SELV.nets` (33 nets) -- counted directly from the manifest,
   both by script and by manual line count as a cross-check.
2. Parses `pcb/temper.kicad_pcb` via `kiutils.board.Board` (the same
   library `resync_pcb_netlist.py` and `check_copper_net_consistency.py`
   already use for this file).
3. For every footprint, transforms each pad's local position by the
   footprint's absolute position and rotation (no footprints on this board
   are flipped to the back layer, verified: `grep -c '(footprint .*
   (layer "B.Cu")' pcb/temper.kicad_pcb` returns 0) to get absolute board
   coordinates.
4. Classifies each pad by its net name against the manifest's exact HV/SELV
   net-name sets (never substring matching -- this project's own
   documented defect class, `docs/evidence/2026-07-27-net-classification-gate.md`).

### Component/pad counts (denominators)

| | Count |
|---|---|
| Total footprints on board | 168 (`grep -c "^  (footprint " pcb/temper.kicad_pcb`) |
| HV-domain pads | 97, across 52 unique components |
| SELV-domain pads | 221, across 114 unique components |
| Components with pads in BOTH domains | 8 -- exactly the declared isolators: `C6` (y_cap_pe), `K1`/`K2`/`K3` (bypass relay + 2 discharge relays), `PS1` (aux_supply.psu), `T1` (ct_sense.ct), `U3` (zcd_opto), `U7` (gate driver) |
| HV-only components | 44 |
| SELV-only components | 106 |
| Components touching only unclassified nets | 10 (168 - 44 - 106 - 8) |

The 8-component mixed set matching the manifest's 7 declared `isolators:`
entries plus the Y-cap exactly, with no unexpected extra crossings, is a
strong internal cross-check that the classification (manifest exact-name
matching against real board pad nets) is correct.

### Bounding-box / interleaving analysis

Board outline (`Edge.Cuts`, a single `gr_poly`): **(20, 20) to (172, 254)**
-- a 152mm x 234mm rectangle. (Note: this does not match
`docs/hardware/POWER_PLANE_DESIGN.md`'s stated "100mm x 150mm" -- that
document is stale against the real board; not in scope to fix here, flagged
for the record.)

| Domain | Bounding box (xmin, ymin) - (xmax, ymax) |
|---|---|
| HV pads | (21.455, 21.23) - (170.175, 252.48) |
| SELV pads | (21.0, 21.25) - (170.6825, 252.75) |

Both domains' bounding boxes span **within ~1.5mm of all four board
edges** -- i.e. both domains occupy the entire board footprint, not
distinct halves.

Per-component (not per-pad) position grid, 10mm x 10mm bins across the
full board, HV-only components (H) vs SELV-only components (S) vs both (B)
vs empty (.) -- 24 rows (Y, top to bottom) x 15 columns (X, left to right):

```
...H.....H..SSH
.............S.
S....H..S.HH...
S.......S......
.....H.........
......H..SS....
......H...S....
.H.HH..........
H.H...........H
......H........
........HHS...S
S........SSS..S
SSS......SSSS.S
SSB..H....H....
H.S.HH...H.....
.SSS..S..S.H...
HSB...H.H.H.H.S
............H.S
.H..SS.........
...............
....H..........
.H.H...SS.....H
HSS..SSS.SS.H..
.SSSSSS.S.SH.HS
```

Per-X-column summary (ignoring Y -- does this 10mm-wide vertical strip,
spanning the FULL board height, contain HV-only components, SELV-only, or
both?):

| X range (mm) | HV count | SELV count | Marker |
|---|---|---|---|
| 20-30 | 4 | 19 | Both |
| 30-40 | 3 | 11 | Both |
| 40-50 | 4 | 12 | Both |
| 50-60 | 3 | 2 | Both |
| 60-70 | 3 | 3 | Both |
| 70-80 | 5 | 6 | Both |
| 80-90 | 4 | 4 | Both |
| 90-100 | 0 | 3 | SELV only |
| 100-110 | 2 | 6 | Both |
| 110-120 | 3 | 5 | Both |
| 120-130 | 3 | 10 | Both |
| 130-140 | 3 | 2 | Both |
| 140-150 | 3 | 6 | Both |
| 150-160 | 1 | 5 | Both |
| 160-170 | 3 | 12 | Both |

**14 of 15 columns across the full 150mm board width contain BOTH HV-only
and SELV-only components.** Only x=[90,100) has zero HV components in that
column (a single 10mm-wide gap, not a usable full-height corridor even if
it were -- the row grid above shows SELV/mixed activity fills most of that
column's height too). No single vertical line, and by the row-grid
evidence above no single horizontal line either, separates the two
domains -- this is checkerboard-level interleaving, not "mostly separated
with a few outliers."

### Nearest-neighbor proximity (context, not the primary Task-1 finding)

For completeness: computed the closest HV pad <-> SELV pad distance across
different components (97 x 221 = 21,437 pairs, brute force):

- **Nearest cross-domain pad pair (different components): 2.115mm**
  (`C17` pad 2, net `hb.gate_hs.driver-p2`, HV -- vs `R32` pad 1, net
  `+3V3`, SELV).
- Of 21,392 cross-domain, cross-component pad pairs, **21 pairs are
  already within 8.0mm** today.
- Of 5,920 distinct (HV component, SELV component) combinations, **11
  distinct pairs** have a closest approach under 8.0mm.

This confirms the interleaving is not merely a coarse-grid artifact: real
pad-to-pad proximity violations of the derived 8.0mm figure already exist
on the board today, in addition to (and independent of) the
topological/checkerboard argument above.

### Which clearance figure applies: 8.0mm (top of the stated 3.0-8.0mm range)

The DC bus is +-170V about a grounded midpoint (340V differential --
`elec/domain_manifest.yaml`'s `+170V_BUS`/`PWR_RTN`/`DC_BUS_RTN`
declarations; `packages/temper-placer/configs/netclass_rules.yaml`'s
`HighVoltage` class independently declares `voltage_v: 400.0` for the same
crossing).

The SELV domain is **user-accessible in normal operation**: the RTD probe
reads the pan surface directly, and the UI (buttons, USB) is touched
during normal use. This is not a barrier between two internal functional
circuits (BASIC/working insulation territory, ~2-3mm class) -- it is a
barrier between a mains-derived circuit and a part a user's hand can
reach, which IEC 60335-1 requires REINFORCED insulation across (equivalent
to two independent basic-insulation layers), absent a separate
double-insulated enclosure doing that job at the board level for this
specific crossing.

`packages/temper-placer/configs/netclass_rules.yaml` already declares
**6.0mm** for `ACMains`/`HighVoltage` class pairs, citing "IEC 60335-1
Table 16 working isolation at 400V" -- note "**working** isolation": that
is the BASIC/functional clearance between two HV-class nets of similar
domain, not the reinforced mains<->user-accessible-SELV figure this
barrier needs. Reusing 6.0mm here would repeat the exact class of error
this plan explicitly warned against ("do NOT assume 3-6mm; that error was
made earlier on this project").

At <=400V working voltage, pollution degree 2, material group IIIb (the
conservative assumption for generic FR4 -- CTI not independently verified
against a laminate datasheet for this board, see UNVERIFIED below), the
commonly-cited figures for **reinforced** insulation in this voltage class
(widely used in industry application notes for the closely analogous
IEC 60950-1/62368-1 "reinforced insulation, <=250Vac mains,
post-doubler/PFC DC bus" case) are approximately **6.4mm CLEARANCE** and
**8.0mm CREEPAGE**. Creepage (surface distance) is always >= clearance
(through-air distance) for the same voltage/pollution class, and a PCB
keepout enforces surface distance directly (both sides of the gap are
literally board surface), so creepage is the binding figure for sizing a
physical keepout. `MIN_BARRIER_WIDTH_MM` in the gate is therefore set to
the **top** of the plan's stated 3.0-8.0mm range: **8.0mm**, not the
middle and not the existing (looser, wrong-provision) 6.0mm netclass
figure.

**UNVERIFIED-at-primary** (same epistemic status this project's own
`elec/domain_manifest.yaml` already carries for its OVP-01
protective-impedance writeup): IEC 60335-1's Table 16 / IEC 60664-1's
creepage tables are paywalled primary text; the 8.0mm/6.4mm figures above
are reconstructed from secondary/industry sources, not read from the
standard directly in this pass. Never shrunk to match this repo's existing
6.0mm figure regardless.

### Conclusion (Task 1)

**No contiguous, axis-aligned (or any reasonably simple) copper-free
barrier separates the HV and SELV domains on the current placement.** This
is a placement finding: the components themselves would need to be
re-clustered (HV components grouped on one side of the board, SELV on the
other, isolator components straddling a single dedicated barrier strip --
which is what `docs/hardware/POWER_PLANE_DESIGN.md` Sec 3.4's "Isolation
slot zone: 2mm x board width" entry suggests was the ORIGINAL intent, now
drifted away from) before a physical keepout can be drawn at all. Per the
plan's own instruction, this is reported and Task 2 is skipped rather than
forcing a barrier that would carve through dozens of components of one
domain or the other.

## Task 2 -- add the keepout

**Skipped**, as a direct, correct consequence of Task 1's finding. No
keepout geometry was added to `pcb/temper.kicad_pcb`; the file was not
touched by this change (`git diff 60d441f2 -- pcb/temper.kicad_pcb` is
empty). This also eliminates any merge-conflict risk with the concurrent
sibling agent auditing the copper-pour strategy on the same file -- my
change makes zero edits to `pcb/temper.kicad_pcb`.

## Task 3 -- the gate

### What it does

`scripts/check_isolation_keepout.py` (full derivation and design rationale
in its own module docstring, not repeated in full here):

- Looks for a KiCad keepout zone (a "rule area" with `keepoutSettings` set,
  not an ordinary copper-pour zone) named exactly
  `MAINS_SELV_ISOLATION_BARRIER` -- a documented naming convention so an
  unrelated keepout elsewhere on the board is never mistaken for this
  specific safety barrier.
- If found, verifies: (1) it spans all 4 copper layers the board's own
  stackup declares (`F.Cu`, `In1.Cu`, `In2.Cu`, `B.Cu` -- read from the
  board's own `(layers ...)` block, `type=signal` entries, never
  hardcoded); (2) its keepout settings (`tracks`/`vias`/`pads`/
  `copperpour`/`footprints`) are all `not_allowed`; (3) it is
  >=8.0mm wide EVERYWHERE along its length (via a Shapely negative-buffer
  erosion test, not just an average/bounding-box width); (4) subtracting it
  from the board outline (`Edge.Cuts`) yields EXACTLY two disjoint regions
  -- a barrier that does not span the full board edge-to-edge does not
  separate anything, since copper could route around its ends; (5) no
  copper item (segment, arc, via -- expanded to every copper layer
  physically between its two named endpoint layers, since a through via's
  drill breaches every inner layer regardless of what its `layers` field
  names -- pad, or non-keepout pour zone) overlaps it on a shared layer;
  (6) no domain has copper on both sides of the partition.
- If the named barrier zone is missing entirely: **VIOLATION** (exit 3),
  not a gate error -- this is a real, substantive, correctly-reasoned
  finding against real data (168 footprints, 519 pads, 2482 copper items
  all genuinely examined), not a vacuous no-op.

### Anti-vacuous-truth contract (verified both directions)

Fails closed (`GateError`, exit 5) on: missing/empty board or manifest;
malformed manifest (`schema_version`/domains structure); HV/SELV nets
overlapping; zero copper (type=signal) layers declared; zero footprints;
zero pads; zero copper items (segments+arcs+vias+non-keepout zones); zero
HV-classified pads found on the board; zero SELV-classified pads found on
the board; the board outline (`Edge.Cuts`) missing or invalid. Every one of
these is covered by a dedicated unit test in
`TestAntiVacuity`/`TestLoaders` (see below) -- confirmed by actually
running `pytest.raises(GateError, match=...)` against each, not merely
asserted.

### Unit tests

`scripts/tests/test_check_isolation_keepout.py`: 27 tests, all passing,
built entirely from synthetic boards constructed via the `kiutils` Python
API and round-tripped through `Board.to_file`/`Board.from_file` (matching
`scripts/tests/test_resync_pcb_netlist.py`'s established convention for
this exact library) -- never depends on or mutates the real
`pcb/temper.kicad_pcb`.

```
$ uv run --no-sync python3 -m pytest scripts/tests/test_check_isolation_keepout.py -q
27 passed in 0.32s
```

Coverage by group: `TestMissingBarrier` (2), `TestLayerSpan` (2, including
the `*.Cu` wildcard-acceptance case), `TestKeepoutSettings` (1, asserts all
5 sub-settings independently), `TestWidth` (2, narrow-fails /
minimum-plus-margin-passes), `TestPartition` (1, barrier that stops short
of the board edge), `TestIntrusion` (6 -- segment, via, via-breaches-
inner-layer-though-not-named, pad-center-inside, pad-body-overlaps-while-
center-is-outside, copper-pour-zone), `TestFarSideCrossing` (1),
`TestPass` (1, fully correct barrier), `TestAntiVacuity` (7), and
`TestFailBeforePassAfter` (2 -- explicit before/after pair, built as two
synthetic fixtures, **without `git stash`** per this plan's hard rule; the
stash ref is shared across worktrees on this project and has already
corrupted another session's entry).

One real correctness bug was found and fixed during this same pass (not a
separate incident, folded into this evidence doc): the pad-intrusion check
initially tested only each pad's CENTER point against the keepout polygon,
which would silently miss a pad whose physical body straddles the barrier
boundary while its center sits just outside it -- an under-approximation
in exactly the wrong direction for a safety-critical check (segments and
vias were already correctly buffered by their trace width / drill radius;
pads were not). Fixed by giving each pad a conservative bounding-circle
radius (`max(pad.size.X, pad.size.Y)/2`) and buffering its point by that
radius before the intersection test, matching the segment/via treatment.
`test_pad_body_overlaps_barrier_even_when_center_is_outside` (a 6mm-wide
pad centered 2mm outside the barrier edge, so its body reaches 1mm past
it) exercises this specifically.

### Run against the real board

```
$ uv run --no-sync python3 scripts/check_isolation_keepout.py
Board: pcb/temper.kicad_pcb
Manifest: elec/domain_manifest.yaml
Copper layers: 4 (F.Cu, In1.Cu, In2.Cu, B.Cu). Footprints examined: 168.
Pads examined: 519 (HV=97, SELV=221). Copper items examined
(segments+arcs+vias+non-keepout zones): 2482. Keepout zones found on
board (any name): 0.
Barrier zone NOT FOUND (name='MAINS_SELV_ISOLATION_BARRIER').
Required minimum barrier width: 8.0mm (REINFORCED creepage; see module
docstring).

=== VIOLATIONS: 1 ===

  [missing] 1 violation(s):
    No keepout zone named 'MAINS_SELV_ISOLATION_BARRIER' found on the
    board (0 other keepout zone(s) present, if any). The mains<->SELV
    isolation barrier is not physically enforced -- it exists only as
    declarations (elec/domain_manifest.yaml) and after-the-fact clearance
    checks. A human must place a keepout region spanning all 4 copper
    layers (F.Cu, In1.Cu, In2.Cu, B.Cu), at least 8.0mm wide throughout,
    bisecting the board so every HV-domain component is on one side and
    every SELV-domain component is on the other, named exactly
    'MAINS_SELV_ISOLATION_BARRIER'.

FAILED -- 1 violation(s)
$ echo $?
3
```

**This is the correct, expected, honest result** given Task 1's finding.
The gate genuinely examined real data (168 footprints, 519 pads, 2482
copper items -- all denominators reported, none zero) and correctly
concluded the safety artifact is absent, rather than passing vacuously.

### Falsifier -- stated and reported

> "A contiguous mains<->SELV keepout can be defined on the current
> placement, and once defined the board respects it. If the barrier
> cannot be drawn without cutting through existing copper, or the board
> violates it immediately, that is a placement/layout finding and the
> honest deliverable -- not a reason to shrink the barrier until it fits."

**FALSIFIED.** The barrier cannot be drawn on the current placement
without cutting through existing HV or SELV components (Task 1's
checkerboard-interleaving finding: 14 of 15 10mm-wide board-spanning
columns contain both domains; both domains' bounding boxes span within
~1.5mm of every board edge; 11 distinct HV/SELV component pairs are
already closer than 8.0mm today). This is reported as a placement/layout
finding, and the required 8.0mm separation was never shrunk to make
either Task 1 or the gate report success.

### CI wiring

Added to `scripts/manifest.yaml` (script inventory) and
`.github/workflows/python-tests.yml`: a unit-test step
(`uv run pytest scripts/tests/test_check_isolation_keepout.py`) and a gate
step (`uv run python scripts/check_isolation_keepout.py`), both in the
`test` job immediately after the existing domain-partition gate step, and
both without `continue-on-error` -- consistent with this plan's hard rule
and with the four `continue-on-error` steps already retired elsewhere in
this repo for the same reason. Also added the two new file paths (plus
`pcb/temper.kicad_pcb` itself) to both the `push` and `pull_request`
trigger path lists. Verified `scripts/check_workflow_pr_triggers.py`
(checks every push-triggered workflow also declares `pull_request`) still
passes after this edit (`23 file(s) checked, all compliant`, exit 0).

**Consequence, stated plainly:** merging this change as-is will turn the
new "Physical mains<->SELV isolation-barrier gate" CI step red, by design,
because Task 1 found the barrier cannot honestly be added yet. This is not
a masked or `continue-on-error`'d failure -- it is the gate doing its job
and reporting a genuine, pre-existing safety gap that was previously
invisible (no check on this project examined "does a physical barrier
exist" before this change; the closest existing checks,
`check_domain_partition.py` and `check_net_classification.py`, both
verify *declared/connectivity* properties over the netlist, not the
board's physical copper-free-region geometry).

## Verification (all commands run, all output shown or summarized above)

| Check | Result |
|---|---|
| `check_domain_partition.py` | exit 0 |
| `capacity_budget_gate.py` | exit 0 |
| `mpn_fabrication_gate.py` | exit 0 |
| `check_derived_doc_drift.py` | exit 0 |
| `check_copper_net_consistency.py` | exit 0 (2482 copper items, 519 pads checked -- unchanged from baseline; confirms `pcb/temper.kicad_pcb` was not touched) |
| `check_rust_drc_presence.py` (`TEMPER_REQUIRE_RUST_DRC=1`) | exit 0 |
| `check_undeclared_imports.py` | exit 0 |
| `check_stale_extensions.py` | exit 0 |
| `check_net_classification.py` | exit 0 |
| `check_pll_range_consistency.py` | exit 0 |
| **`check_isolation_keepout.py` (new)** | **exit 3** -- honest failure, reason stated above |
| `make netlist` | passes (build complete) |
| `uv run --no-sync python -m pytest elec/validation -q` | 30 passed |
| `uv run --no-sync python -m pytest scripts/tests/test_check_isolation_keepout.py -q` | 27 passed |
| `scripts/check_workflow_pr_triggers.py` | exit 0 (23 files checked, all compliant) |
| `scripts/check_manifest_gate.py` | 1 pre-existing violation remains (`check_copper_net_consistency.py` has no manifest entry -- a documented, pre-existing gap from a prior change, NOT introduced by this one; my own new script's entry is present and resolves the OTHER previously-reported gap). Not one of the 10 required gates for this plan. |

All ten gates named in the plan exit 0; the eleventh (new) gate exits 3
for the clearly-stated reason above -- exactly the alternate branch the
plan's "Verify before finishing" section anticipates.

## UNVERIFIED

- IEC 60335-1 Table 16 / IEC 60664-1's creepage/clearance tables are
  paywalled primary text; the 8.0mm creepage / 6.4mm clearance
  reinforced-insulation figures are reconstructed from secondary/industry
  sources (widely cited in offline-SMPS application notes for the
  analogous IEC 60950-1/62368-1 reinforced-insulation, <=250Vac-mains,
  post-doubler/PFC-bus case), not read from the standard's own primary
  text in this pass.
- The board's actual copper-clad laminate's CTI (comparative tracking
  index, which determines material group I/II/IIIa/IIIb) was not checked
  against a datasheet; material group IIIb (the more conservative,
  larger-creepage-requiring assumption) was used rather than assuming a
  more favorable IIIa/generic-FR4 figure.
- Whether IEC 60335-1 requires any additional certified/tested
  construction for the barrier region itself (beyond plain substrate
  spacing) was not checked.
- The bounding-box / 10mm-grid / nearest-neighbor analysis in Task 1 is
  strong, multiply-cross-checked evidence of interleaving, but is not an
  exhaustive geometric search over every conceivable (non-rectangular,
  non-axis-aligned) barrier polygon -- it operates at the level of detail
  the plan itself requested ("report the domains' bounding geometry"). A
  sufficiently exotic serpentine keepout threading between all 158
  domain-classified components was not constructed or ruled out by
  exhaustive search; given the density of interleaving found (14/15
  board-spanning columns mixed, checkerboard pattern down to <10mm
  resolution in both axes), this is treated as practically infeasible
  rather than formally impossible.
- The via-layer-span expansion (a through via's `layers` field names only
  its two outer endpoints; this gate expands to every board layer between
  them by ordinal) is correct for standard through vias and is exercised
  by a unit test, but this board currently has zero blind/buried vias to
  validate the narrower-span case against directly.
- `docs/hardware/POWER_PLANE_DESIGN.md`'s stated board size ("100mm x
  150mm") does not match the real board's `Edge.Cuts` outline (152mm x
  234mm) -- noted for the record; not investigated further as it is
  outside this plan's scope.
