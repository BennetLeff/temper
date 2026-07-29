<!-- provenance: commit=ed5ee134282083 dirty=true -->

# Resyncing `pcb/temper.kicad_pcb` against `elec/src` / `pcb/libs`: 6 stale embedded footprints, 13 drifted designators, `tank.c_tank3` staged

Base commit `ed5ee134` (`fix(evidence): repair provenance stamps on two docs
failing the gate`), branch `fix/resync-board-against-source`, isolated
worktree at `.../scratchpad/wt-resync`. Environment: macOS arm64 (Darwin
25.5.0), `kicad-cli` 10.0.4, Python 3.12.13, `uv`.

Mid-task, `origin/main` advanced 4 commits, one of which
(`0c0c21c4`, "footprint-drift gate") added exactly the CI gate this task's
defect class needed, and another (`12179f94`) fixed a 4th stale footprint
(`c_x2`/C1) whose own new comment named this task's precedent
(`C6/U3 resync`) as the place to propagate it. Both were merged in before
finishing (`git merge origin/main`, no conflicts — the new commits touch
`elec/src/modules.ato` and add new scripts, none of which overlap
`pcb/temper.kicad_pcb` or the DRC regression test).

## Summary (read this first)

Six footprints were corrected in `elec/src`/`pcb/libs` days ago and never
propagated into the board's embedded copies. Three were named in this
task's brief (U3, C6, U7); a fourth (C1/`power_in.c_x2`) landed in source
mid-task with an explicit note pointing at this exact resync; two more
(C25/C26, `tank.c_tank1`/`tank.c_tank2`) were found independently by
verifying every footprint identity against source rather than trusting the
brief's table, per its own instruction to do so.

Separately, commit `3ae26dfe` added a third tank capacitor
(`tank.c_tank3`) to `elec/src`, which shifted every subsequent `C`
designator down by one across 13 sheetpaths, and left `tank.c_tank3`
itself with no footprint on the board at all. Both are fixed here:
13 designators resynced, `tank.c_tank3` added in the resync's staging
row — **not given a real placement**, which remains a human PCB-design
decision for a resonant-tank HV component.

**`tank.c_tank3` is staged, not placed, and needs a human to give it a real
position.**

## 1. Verification against source (not taken on faith)

| ref | sheetpath | source declares (`elec/src`) | board had (pre-fix) |
|---|---|---|---|
| U3 | `power_in.zcd_opto` | `Package_DIP:DIP-6_W10.16mm` (`components.ato:549`) | `Package_DIP:DIP-6_W7.62mm` |
| C6 | `power_in.y_cap_pe` | `Capacitor_THT:C_Disc_D12.5mm_W5.0mm_P10.00mm` (`modules.ato:958`) | `Capacitor_THT:C_Disc_D10.0mm_W5.0mm_P5.00mm` (a hand-written "stub… created to resolve netlist reference", no real geometry) |
| U7 | `hb.gate_hs.driver` | `SOIC16W_Isolated` -> `pcb/libs/lib.pretty/SOIC16W_Isolated.kicad_mod`, corrected 2026-07-28 (pad 1.65×0.6 @ ±4.875, courtyard ±5.95) | same library nickname, but the board's embedded copy still had the pre-correction geometry (pad 2.05×0.6 @ ±4.65, courtyard ±5.93) |
| C1 | `power_in.c_x2` | `Capacitor_THT:C_Rect_L18.0mm_W7.0mm_P15.00mm_FKS3_FKP3` (`modules.ato`, PR #452, landed mid-task) | `Capacitor_THT:C_Disc_D10.0mm_W5.0mm_P5.00mm` (same disc-stub pattern as C6 had) |
| C25 | `tank.c_tank1` | `temper:C_Axial_L34.0mm_D22.5mm_P40.00mm_Horizontal` (`modules.ato:518`, part of `3ae26dfe`'s WIMA->CDE re-source) | `Capacitor_THT:C_Rect_L41.5mm_W20.0mm_P37.50mm_MKS4` (old WIMA FKP1 rect land) |
| C26 | `tank.c_tank2` | same as C25 | same stale WIMA rect land as C25 |
| — | `tank.c_tank3` | `temper:C_Axial_L34.0mm_D22.5mm_P40.00mm_Horizontal`, `mpn=942C16P1K-F` | **no footprint anywhere on the board** |

C25/C26 were not in this task's original 3-footprint brief. `3ae26dfe`'s
own title ("re-source the tank capacitors on AC current — 2 × WIMA FKP1 →
3 × CDE 942C16P1K-F") already says all three tank caps changed part number
and footprint, not just that a third was added; `scripts/resync_pcb_
netlist.py --dry-run` surfaced this directly as two `footprint_swapped`
entries the moment it ran. `scripts/check_footprint_drift.py` (new,
`0c0c21c4`, wired into CI in the same commit) independently confirms this
is the complete list: it FAILED on `C1` alone before that fix went in
(all other 5 already resolved by this point in the session), and reports
`PASSED -- 0 violations across 169 matched component(s)` on the final
board.

## 2. The 13-designator drift and the missing `tank.c_tank3`

`3ae26dfe` inserted `tank.c_tank3` immediately after `tank.c_tank2` in
`elec/src`; atopile's sequential `C` numbering shifted every subsequent
same-prefix designator up by one. The board was never resynced after that
commit. `scripts/check_copper_net_consistency.py` reported this directly:

```
=== VIOLATIONS: 10 ===
  [pad-mismatch] 10 violation(s):
    C27 pad 1: board has net 'I_SENSE', compiled netlist declares 'SW_NODE' ...
    C27 pad 2: board has net 'gnd', compiled netlist declares 'tank.c_tank1-p2' ...
    C28 pad 1: board has net 'vcc', compiled netlist declares 'I_SENSE' ...
    ... (C29..C39, one violation each)
FAILED -- 10 violation(s)
```

Board `C27` carried `Sheetpath ct_sense.c_filter` — SELV copper
(`I_SENSE`/`gnd`, downstream of the CT isolator) — while the netlist's
current `C27` is `tank.c_tank3`, the real HV resonant-tank capacitor. That
mislabeling made 10 real REQ-SAFE-01 pairs (see §5) look like mains/SELV
boundary violations when they were, physically, SELV-to-SELV.

## 3. Method: `scripts/resync_pcb_netlist.py`, plus 5 hand-edited footprints

Per `docs/evidence/2026-07-29-board-regeneration-corrected-footprints.md`'s
precedent (PR #426), U3/C6/C1's corrected footprints are standard KiCad
libraries this box cannot resolve through `pcb/fp-lib-table`'s
`${KICAD10_FOOTPRINT_DIR}` placeholder (the resync script's `_parse_
fp_lib_table` does not env-expand it), so `resolve_footprint()` would
raise. U7's identity string (`lib:SOIC16W_Isolated`) never changed — only
the library file's own geometry did — so the resync tool's
same-libId-means-"kept" fast path would have silently carried the STALE
embedded copy forward. All four were therefore **hand-edited in-place
first** (line-oriented, preserving `tstamp`/`tedit`/position/rotation/layer
and every pad's `(net ...)` binding by pad number), using the real
`.kicad_mod` content of the corrected footprint as source of truth (found
on-disk in this machine's installed KiCad 10 footprint set — same
`version 20260206` / `generator kicad-footprint-generator` stamp already
used throughout this board's other embedded standard-library copies, so
these are the same upstream files this board was originally built
against).

With those 4 footprints already matching their new libId strings, running
`scripts/resync_pcb_netlist.py` (real run, not dry-run) then:
- matched all 168 existing components by `Sheetpath` (stable across
  designator renumbering) and kept every one's position/rotation/layer/
  UUID unchanged;
- took the cheap "kept, same libId" path for U3/C6/C1/U7 (already fixed,
  see above) and the genuine "footprint swap, transplant old position"
  path for C25/C26 (`temper:C_Axial_L34.0mm_D22.5mm_P40.00mm_Horizontal`
  resolves locally via `pcb/libs/temper.pretty/`, no network needed);
- relabeled the 13 drifted `C` designators (`ct_sense.c_filter` C27->C28
  through `mcu.c_en` C39->C40);
- staged `tank.c_tank3` (new `Reference C27`, sheetpath `tank.c_tank3`) in
  the script's `STAGING_GAP_MM` row below the board outline, at
  `(20, 272.75)`, rotation 0 — **not a real placement**;
- rebuilt `board.nets` (164 -> 162 entries; the net set itself changed —
  fewer WIMA-specific nets, the tank bank's rewiring — not merely
  reordered) and remapped **every** existing copper item's net ordinal by
  NAME identity as part of that rebuild (this codepath now lives in
  `resync_pcb_netlist.py` itself, closing the manual-post-process gap the
  2026-07-27 post-OVP resync flagged as follow-up work).

`comp.tstamp` (the netlist's own per-instance stamp, stable across
designator renumbering since it is derived from the `.ato`
module-instantiation path, not the positional designator) was independently
verified to reproduce the SAME `_uuid_from_seed(f"fp:{comp.tstamp}")` value
for all 168 pre-existing sheetpaths before running the real resync — the
tool's own UUID-preservation mechanism, checked rather than assumed.

## 4. The landmine, and the proof it did not fire

Every segment/via/arc/zone stores its net as a bare ordinal index into
`board.nets`, not a name (`docs/evidence/2026-07-27-post-ovp-resync.md`
§1: 79% of segments / 75% of vias would silently repoint at the wrong net
on this exact board if the table were rebuilt without a by-name remap).
Adding a component and renumbering 13 designators is exactly the operation
that perturbs the table — this was a live risk here, not theoretical.

Both boards were parsed independently with `kiutils` and compared field by
field (script in this evidence's companion scratch tooling, not committed
— pure verification, no board mutation):

```
counts:              before  {footprints:168, segments:2338, vias:48, arcs:0, zones:96, nets:164}
                     after   {footprints:169, segments:2338, vias:48, arcs:0, zones:96, nets:162}

footprint position/rotation/layer:  moved 0   (0 of 168 matched sheetpaths)
footprint UUID (tstamp) on matched sheetpaths:  changed 0
added sheetpaths:    1  -> tank.c_tank3
removed sheetpaths:  0
reference (designator) changes:  13  (exactly the ct_sense.c_filter..mcu.c_en chain)
libId changes:  5
  power_in.c_x2   Capacitor_THT:C_Disc_D10.0mm_W5.0mm_P5.00mm -> C_Rect_L18.0mm_W7.0mm_P15.00mm_FKS3_FKP3
  tank.c_tank1    Capacitor_THT:C_Rect_L41.5mm_W20.0mm_P37.50mm_MKS4 -> temper:C_Axial_L34.0mm_D22.5mm_P40.00mm_Horizontal
  tank.c_tank2    (same swap as tank.c_tank1)
  power_in.y_cap_pe  Capacitor_THT:C_Disc_D10.0mm_W5.0mm_P5.00mm -> C_Disc_D12.5mm_W5.0mm_P10.00mm
  power_in.zcd_opto Package_DIP:DIP-6_W7.62mm -> DIP-6_W10.16mm
  (U7's libId string is unchanged -- lib:SOIC16W_Isolated -- only its internal pad/silk/courtyard geometry moved, hand-edited to match the corrected .kicad_mod)

copper net identity BY NAME:
  segment/via matched by tstamp:  2386 before, 2386 after, 0 missing, 0 new, 0 NAME mismatches
  zones matched by list order:    96 before, 96 after, 0 NAME mismatches

RESULT: PASS -- 0 net-identity mismatches
```

This is the anti-corruption proof: every one of the 2,482 copper items
(2338 segments + 48 vias + 96 zones) resolves to the **same net name**
before and after, despite ~49% of them (1,210 of 2,482, per the resync
tool's own report) having their numeric ordinal reassigned by the net-table
rebuild. Zero footprints moved, rotated, or changed layer; zero UUIDs
changed on any of the 168 pre-existing sheetpaths.

## 5. Gate results

### `scripts/check_footprint_drift.py` (new, `0c0c21c4`)

```
Components: 169 in netlist, 169 matched by sheetpath against the board.
PASSED -- 0 violations across 169 matched component(s).
```

(FAILED with exactly 1 `[mismatch]` violation on `C1` immediately before
that footprint's fix was applied — confirms the gate is exercising the
real defect class, not vacuously passing.)

### `scripts/check_copper_net_consistency.py`

```
before: FAILED -- 10 violation(s)   (all 10 pad-mismatch, C27..C39)
after:  PASSED -- 0 violations across 2482 copper item(s) and 512 pad(s) checked.
```

### `scripts/check_domain_partition.py` / `scripts/ci_identity_check.py`

Both PASS before and after, unchanged in kind
(`0 domain crossings, 0 isolator-barrier breaches, 0 protective-impedance
chain defects`; `production board ... passes the identity gate`).

### `kicad-cli pcb drc`, median of N=5

| metric | before | after | Δ |
|---|---|---|---|
| total | median 1254 `[1232,1250,1254,1257,1258]` | median 1255 `[1249,1254,1255,1261,1262]` | ~flat |
| `shorting_items` | median 86 `[68,86,86,87,87]` | median 82 `[77,81,82,86,89]` | improved |
| `unconnected_items` | 388 (all 5 runs, 0 scatter) | 390 (all 5 runs, 0 scatter) | **+2** |

The `unconnected_items` rise is fully explained and verified pair-by-pair:
of 70 raw new/removed unconnected-pair entries between the two boards, 68
are ordinary designator-relabeling churn (KiCad re-picking the nearest
ratsnest item for the SAME physical pair — e.g. `Pad 1 [+3V3] of C12` /
`Pad 1 [+3V3] of C37` becomes `.../C38` after the renumber — 0 cross-net,
same mechanism `docs/evidence/2026-07-29-board-regeneration-corrected-
footprints.md` §4 already documents for this board). The only 2 genuinely
NEW pairs are `tank.c_tank3`'s own two pads, reported unconnected to their
real-copper neighbours because the part is staged, unrouted, by design:

```
PTH pad 1 [SW_NODE] of C27           <-> PTH pad 3 [SW_NODE] of U5
PTH pad 1 [tank.c_tank1-p2] of R30   <-> PTH pad 2 [tank.c_tank1-p2] of C27
```

Both same-net. This is the expected, designed-for state of a staged,
not-yet-placed HV component — not a defect.

`total`/`shorting_items` are re-verified within the existing
`PRODUCTION_COMMITTED_BOARD_*` ratchets (1260 / 90) unchanged;
`PRODUCTION_COMMITTED_BOARD_UNCONNECTED` was raised 388 -> 390 with the
same pair-by-pair proof recorded directly in
`packages/temper-placer/tests/placer/cp_sat/test_regression_drc.py`'s
comment block. The router-output category
(`PRODUCTION_ROUTER_OUTPUT_UNCONNECTED`) needed the same treatment: running
`route_pcb()` against both the pre-resync board (via `git show`) and the
final board and DRC'ing each gave 404 -> 407 unconnected, 0 cross-net over
all differing pairs (same `tank.c_tank3` mechanism plus router-noise
relabeling) — raised 405 -> 407.
`PRODUCTION_BOARD_BASELINE_SHAPE`'s `footprints` field moved 168 -> 169
(segments/vias/zones unchanged), which is the change the shape guard exists
to catch and re-verify against, not silently absorb.

### REQ-SAFE-01 (`test_temper_board_clearance_compliance`)

This test is a pre-existing, documented FAIL (copper-to-copper clearance
violations that require a placement re-solve out of this task's scope —
see the test's own 2026-07-28 docstring update). It is **not** expected to
turn green here; what matters is the C27/`ct_sense.c_filter` phantom
mislabeling clearing out of it.

| | before | after |
|---|---|---|
| total violations | 98 | 75 |
| violating pairs | 52 | 44 |
| C27-involving pairs | 10 (all phantom — see below) | **0** |

All 10 pairs naming "C27" in the before-state (`C27<->D1`, `C27<->R25`,
`C27<->R66`, `C27<->C15`, `C27<->TP2`, `C27<->C35`, `C27<->C34`,
`C27<->U22`, `C27<->R29`, `C27<->C18` — 23 individual violation rows across
those 10 pairs, since each pair can fail up to 4 metric/insulation
combinations) are **gone** and do not reappear under any label. These were
phantom: the test's own HV/SELV classification looked up "the component
labeled C27" via the compiled netlist's current designator map (which says
C27 = `tank.c_tank3`, HV) while the physical copper occupying that board
location was actually `ct_sense.c_filter` (SELV) — exactly the mislabeling
`docs/evidence/2026-07-30-copper-net-consistency-drift.md` diagnosed
without fixing. Now that `ct_sense.c_filter` correctly carries designator
C28, its clearance is evaluated as SELV, and the real `tank.c_tank3` (now
correctly C27) is staged far from every neighbour named above, so none of
those 10 pairs can recur.

Two new pairs appear (`C25<->R36`, `C25<->C37`), both directly explained by
the C25 (`tank.c_tank1`) footprint correction: swapping the WIMA rect land
for the real CDE axial land changes C25's courtyard/pad extent, moving it
fractionally closer to two nearby SELV components (8.569mm and 9.010mm
measured — both still short of the 10.0mm reinforced margin, same failure
class as the pre-existing violations, not a new hazard class). This is an
honest, measured, source-explained consequence of correcting C25's
geometry, not something this task's placement-preserving scope can or
should paper over. `U3 (intra)` and `U7 (intra)` creepage figures moved
6.020mm -> 8.560mm and 7.250mm -> 8.100mm respectively — matching, to the
millimetre, the numbers `elec/src/components.ato` and `pcb/libs/lib.pretty/
SOIC16W_Isolated.kicad_mod`'s own descr text already claim for the
corrected geometry (independent confirmation the fix is geometrically
correct, not merely "a different footprint string").

The remaining 33 unclassified-proximity findings and 44 REQ-SAFE-01 pairs
are unaudited, pre-existing, and out of this task's scope (placement is
frozen; only the geometry/designators listed, plus the staged addition,
were changed).

## 6. Re-baselined constants

`packages/temper-placer/tests/placer/cp_sat/test_regression_drc.py`:

| constant | old | new | why |
|---|---|---|---|
| `PRODUCTION_BOARD_BASELINE_SHAPE.footprints` | 168 | **169** | the staged `tank.c_tank3`; segments/vias/zones unchanged |
| `PRODUCTION_COMMITTED_BOARD_TOTAL_DVIOLATIONS` | 1260 | **1260 (unchanged)** | measured median 1255 still clears it |
| `PRODUCTION_COMMITTED_BOARD_SHORTING_ITEMS` | 90 | **90 (unchanged)** | measured median 82 still clears it |
| `PRODUCTION_COMMITTED_BOARD_UNCONNECTED` | 388 | **390** | +2, both same-net, both `tank.c_tank3`'s own staged pads (proved pair-by-pair, §5) |
| `PRODUCTION_ROUTER_OUTPUT_TOTAL_DVIOLATIONS` | 1560 | **1560 (unchanged)** | measured median 1449 still clears it |
| `PRODUCTION_ROUTER_OUTPUT_SHORTING_ITEMS` | 125 | **125 (unchanged)** | measured median 95 still clears it |
| `PRODUCTION_ROUTER_OUTPUT_UNCONNECTED` | 405 | **407** | +2 net (404->407 measured directly on both pre/post-resync boards routed identically; 0 cross-net) |

Nothing was raised to make a test pass by fiat — every change above is a
measured value with a same-net pair-by-pair proof, following the
convention already established in this file.

## 7. What is explicitly not done here

- `tank.c_tank3` is staged only, at `(20, 272.75)`, rotation 0, in the
  resync's clear staging row below the board outline. **It has not been
  given a real position.** Placing a resonant-tank HV component is a PCB
  design decision (proximity to the other two tank caps, HV creepage to
  neighbouring SELV copper, thermal/mechanical clearance) that belongs to
  a human, not this resync.
- The pre-existing REQ-SAFE-01 clearance failures (44 pairs, minus the 10
  phantom C27 pairs and plus 2 new C25-adjacent ones, both explained above)
  are not fixed — placement is out of scope and frozen by this task's own
  constraints.
- `scripts/check_isolation_keepout.py` (FAIL, 0 keepout zones — unrelated,
  pre-existing) and `scripts/check_measurement_provenance.py` (ERROR, the
  `drc_ceiling.json#boards.temper` record is stale against this board's new
  content hash — expected any time the board file is legitimately
  rewritten; re-measuring the ceiling needs a `Ceiling-Approval:` trailer
  and is a separate deliverable) were reproduced and are unaffected in kind
  by this change.
- `tests/analysis/test_area_sufficiency_check.py::test_real_board_reports_approximately_108_5_pct`
  remains a pre-existing FAIL (now 52.4% vs the ~108.5% target, up from the
  47.9%/48.2% already on record) — six real, larger footprints (DIP-6 wider
  lead form, both Y-caps, the tank axial bodies, the X2 MKP box) grow the
  pad-derived courtyard sum; this is the correct, honest direction for
  fixing footprints toward their real physical size, not a regression this
  task introduced in the sense of "making something wrong."

## Reproduction

```bash
make netlist
uv run python scripts/check_footprint_drift.py             # exit 0
uv run python scripts/check_copper_net_consistency.py       # exit 0
uv run python scripts/ci_identity_check.py                  # exit 0
uv run python scripts/check_domain_partition.py             # exit 0

kicad-cli pcb drc --format json -o /tmp/drc.json pcb/temper.kicad_pcb   # x5, median
uv run --no-sync python -m pytest \
  packages/temper-placer/tests/placer/cp_sat/test_regression_drc.py -k production

uv run --no-sync python -m pytest \
  packages/temper-placer/tests/requirements/safety/test_clearance.py::TestClearanceIntegration::test_temper_board_clearance_compliance
```
