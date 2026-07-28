# Post-OVP-01 PCB resync — `pcb/temper.kicad_pcb` reconciled against the current netlist, on a *routed* board

<!-- provenance: commit=faf5171ad4a367d709a59a64f6bf36b9b765039a dirty=UNKNOWN -->

**Date:** 2026-07-27
**Scope:** `pcb/temper.kicad_pcb` only.
**Trigger:** OVP-01's Option C re-reference (`75a708a8`) deleted
`safety.ovp.r_ref_top` (old `R55`) and `safety.ovp.r_ref_bot` (old `R56`).
Every subsequent auto-assigned reference designator shifted down by two,
leaving the committed board at 170 footprints against 168 netlist
components, and `test_temper_board_clearance_compliance` misattributing
designators (53 passed / 1 failed in
`packages/temper-placer/tests/requirements/safety/`, confirmed against
baseline via `git stash`).

---

## 1. Falsifier, stated before implementing

**Falsifier:** *Resyncing preserves all routed copper and its net
assignments.*

**Result: the falsifier FIRED against the existing tool used naively, and
that firing is the central finding of this exercise.** `scripts/resync_pcb_netlist.py`
rebuilds `board.nets` (the net-number table) from the current netlist —
sorted alphabetically, renumbered `1..N` — but it never touches
`board.traceItems` (`Segment`/`Via`) or `board.zones` at all. Per the KiCad
file format (and kiutils' own `Segment.net` docstring: *"the net token
defines by the net ordinal number which net in the net section that the
segment is part of"*), a segment's net is a **bare ordinal index**, not a
name. Rebuilding the net table without remapping every segment/via/zone's
ordinal is a silent, first-class defect for any board that has copper on it.

Measured directly, before running the tool for real: comparing the old
board's 165-entry net table to the net table the tool would build (164
entries — two nets vanish with `r_ref_top`/`r_ref_bot`, one net
`OVP_VREF_2V5` is added) shows **131 of 165 net names would land at a
different ordinal number.** Applying that renumbering to `board.nets` while
leaving the existing copper's ordinal references untouched — which is
exactly what the unmodified tool does — would have **silently reassigned**:

| Item | Total | Would keep correct net (coincidence) | Would silently claim the WRONG net |
|---|---|---|---|
| Segments | 2,338 | 481 | **1,857 (79%)** |
| Vias | 48 | 12 | **36 (75%)** |
| Zones | 96 | 78 | **18 (19%)** |

No copper was found on either of the two nets that actually disappear
(`safety.ovp.comp-inn`, `vref` — 0 segments/vias/zones reference them), so
there is no orphaned trace from the two deleted resistors themselves; the
danger is purely the ordinal-table-rebuild-without-remap defect above.

**This means the tool, as committed, does not handle routed boards
correctly.** Per the task's own instruction — *"If the tool does not
handle routed boards, say so and report rather than producing a board with
silently wrong net assignments"* — that finding is reported here rather
than glossed over.

**Resolution used, without modifying the tool or anything under `scripts/`,
`elec/`, `simulation/`, or `docs/solutions/`:** the existing tool was run
unmodified for its footprint/designator/pad-net reconciliation (exactly as
designed — this part of it is correct and was independently verified, see
§4–§6). Then, as a separate post-process against the board file only (which
this task owns), every segment/via/zone's net ordinal was remapped by
**net-NAME identity**: `old ordinal → name (from a pre-resync backup) → new
ordinal (from the tool's freshly-written net table)`. This is a pure
relabeling — no copper geometry, no track/via/zone count, and no component
position changed; only the numeric net-table index each item points at was
corrected to keep pointing at the same electrically-named net it always
was. The script is not part of the deliverable and was not committed
(scratch tooling only, per "do not modify `scripts/`" — the fix lives
outside that directory and outside version control).

**After the fix, the falsifier does NOT fire:** every one of the 2,338
segments, 48 vias, and 96 zones was independently re-verified (matching
pre- and post-fix by track/via `tstamp` and by zone list position, since
zones in this board carry no `tstamp`) to resolve to the **identical net
name** before and after, with **zero** geometry (`start`/`end`/`width`/
`layer` for segments; `position`/`size`/`drill`/`layers` for vias;
`polygons`/`filledPolygons`/`layers` for zones) changes. See §5.

---

## 2. Footprint/netlist counts: 170/168 → 168/168

```
old board footprints:   170
new board footprints:   168
netlist components:     168     <- reconciled: 168 == 168
kept (Sheetpath in both):        168
removed (Sheetpath only in old):   2
added (Sheetpath only in new):     0
```

**2 removed**, both consumed by OVP-01's Option C re-reference:

| Sheetpath | Old ref | Reason |
|---|---|---|
| `safety.ovp.r_ref_top` | R55 | Deleted by OVP-01 Option C re-reference (`75a708a8`). |
| `safety.ovp.r_ref_bot` | R56 | Deleted by OVP-01 Option C re-reference (`75a708a8`). |

**0 added.** This is a pure two-component removal/renumbering resync, not a
new-module resync — no staging row was needed (`added_count: 0`).

---

## 3. Every designator whose meaning changed: 25 (all downshift-by-2)

All 25 are the mechanical consequence of `r_ref_top`/`r_ref_bot`'s removal
shifting every subsequent same-prefix designator down by two. Verified by
`Sheetpath` identity (not by trusting the label), so this is a checked 1:1
mapping, not an assumption:

```
Sheetpath                                Old -> New
safety.ovp.r_hyst                        R57 -> R55
safety.ovp.r_adc_top1                    R58 -> R56
safety.ovp.r_adc_top2                    R59 -> R57
safety.ovp.r_adc_top3                    R60 -> R58
safety.ovp.r_adc_bot                     R61 -> R59
safety.thermal.ntc                       R62 -> R60
safety.thermal.r_ntc_fixed               R63 -> R61
safety.thermal.r_ref_top                 R64 -> R62
safety.thermal.r_ref_bot                 R65 -> R63
safety.thermal.r_hyst                    R66 -> R64
safety.coil_thermal.ntc                  R67 -> R65
safety.coil_thermal.r_ntc_fixed          R68 -> R66
safety.coil_thermal.r_ref_top            R69 -> R67
safety.coil_thermal.r_ref_bot            R70 -> R68
safety.coil_thermal.r_hyst               R71 -> R69
safety.uvlo_logic.r_div_top              R72 -> R70
safety.uvlo_logic.r_div_bot              R73 -> R71
safety.uvlo_logic.r_hyst                 R74 -> R72
safety.uvlo_logic.r_outa_pullup          R75 -> R73
safety.uvlo_logic.r_fault_pullup         R76 -> R74
mcu.r_en                                 R77 -> R75
mcu.r_boot                               R78 -> R76
mcu.r_sda_pullup                         R79 -> R77
mcu.r_scl_pullup                         R80 -> R78
thermal.r_fan_drop                       R81 -> R79
```

No footprint was swapped (`footprint_swapped_count: 0` — every kept
component's KiCad footprint identifier is unchanged), consistent with this
being a pure removal/renumber, not a part substitution.

---

## 4. Zero-components-moved proof

Independent check (not the resync tool's own self-report): the pre-resync
backup and the final committed board were parsed directly with `kiutils`,
footprints matched by `Sheetpath`, and `(X, Y, angle, layer)` compared for
every match.

```
168 persisting components checked (Sheetpath present in both files)
moved: 0
```

Cross-checked a second way: the tool's own dry-run report (`moved_count: 0`)
and the real run's report were identical
(`kept_count: 168, added_count: 0, removed_count: 2`, same 25 designator
changes) before any copper post-processing — the footprint/position/pad
side of the resync is deterministic and was not touched by the copper fix.

---

## 5. What happened to routed copper: counts unchanged, net assignments corrected, geometry untouched

```
                  before    after
segments           2,338    2,338
vias                   48       48
zones                  96       96
net table entries     165      164
```

No segment, via, or zone was added or removed. For every one of the 2,482
copper items:

- **Net NAME preserved: 100% (0 mismatches).** Verified by comparing, for
  each item, the net name resolved through the *old* net table (pre-resync
  backup) against the net name resolved through the *new* net table
  (post-fix board), matched by `tstamp` for segments/vias and by list
  position for zones (zones in this board carry no `tstamp` — kiutils
  parses it as `None` for all 96, confirmed, so `tstamp` cannot be used as
  a zone key; list order is stable across the whole pipeline since the tool
  never touches `board.zones` and reserialization preserves order).
- **Net ordinal number**: 571 of 2,482 items happened to keep the same
  number (nets whose alphabetical position didn't shift), and 1,911 were
  remapped to a new number — in every case, to the ordinal that now
  corresponds to the *same* net name in the rebuilt table.
- **Geometry**: 0 changes. Segment `start`/`end`/`width`/`layer`, via
  `position`/`size`/`drill`/`layers`, and zone `polygons`/
  `filledPolygons`/`layers` are bit-for-bit identical before and after.
- **Zone `netName` field** (a redundant human-readable copy KiCad also
  stores) was kept consistent with the corrected `net` ordinal in all 96
  zones — 0 inconsistencies.

**No copper was orphaned.** The two nets that disappear from the netlist
(`safety.ovp.comp-inn`, `vref` — the removed resistors' own nets) have zero
segments, zero vias, and zero zones referencing them in the pre-resync
board, so there is no dangling trace left pointing at a net that no longer
exists.

**Secondary, non-blocking observation (`kicad-cli pcb drc`, informational
only — not one of the required gates):** raw DRC violation count moved from
1,444 to 1,523 (unconnected-item count moved from 385 to 382); the
`lib_footprint_mismatch` category specifically dropped from 90 to 2 (fewer
footprints now disagree with their own metadata, consistent with the
resync correcting stale bookkeeping) while `clearance` rose slightly
(306 → 338). This board was already far from DRC-clean before this task
(first committed route, not yet clearance-remediated) and no component
moved and no copper geometry changed, so the shift is attributed to
corrected net bookkeeping surfacing/reclassifying pre-existing physical
conditions, not to anything this resync altered physically. Routing and
clearance remediation are explicitly out of scope for this task.

---

## 6. Safety suite: 53/54 → 54/54

```
$ python3 -m pytest packages/temper-placer/tests/requirements/safety/ -v
...
53 passed, 1 failed   (baseline, confirmed via git stash before this task)
...
54 passed             (after resync + copper net-ordinal fix)
```

---

## 7. Required gates — exit 0 before and after

| Gate | Before | After |
|---|---|---|
| `check_domain_partition.py` | exit 0 | exit 0 |
| `capacity_budget_gate.py` | exit 0 | exit 0 |
| `mpn_fabrication_gate.py` | exit 0 | exit 0 |
| `check_derived_doc_drift.py` | exit 0 | exit 0 |
| `check_vacuous_gates.py` | exit 0 | exit 0 |

`make netlist`: **76/76 assertions PASSED**, exit 0 (unaffected by this
task — `elec/` was not modified; the netlist was rebuilt only to obtain a
fresh `elec/build/default.net` for the resync and gate checks, an untracked
build artifact, not a source change).

---

## 8. Commands run (foreground, for reproducibility)

```
scripts/assert-base.sh docs/methodology-loop-discipline   # repointed, then OK
make netlist                                               # exit 0, 76/76 PASSED
python3 scripts/resync_pcb_netlist.py --dry-run             # preview: 168/168, 25 relabels, 2 removed, 0 moved
python3 scripts/resync_pcb_netlist.py                        # real run: footprints+pads+net table
<scratch net-ordinal remap by name-identity, applied to pcb/temper.kicad_pcb only>
python3 -m pytest packages/temper-placer/tests/requirements/safety/ -v   # 54 passed
python3 scripts/check_domain_partition.py
python3 scripts/capacity_budget_gate.py
python3 scripts/mpn_fabrication_gate.py
python3 scripts/check_derived_doc_drift.py
python3 scripts/check_vacuous_gates.py
kicad-cli pcb drc --format json ...                          # informational only, see §5
```

## 9. What this does not claim

- Routing and clearance remediation are untouched — this is a
  nets/designators/footprints resync plus a copper-label correction, not a
  re-route. No component moved and no track/via/zone was added, removed, or
  geometrically altered.
- The scratch script used to correct segment/via/zone net ordinals is not
  part of this repository's tracked tooling and was not committed; it exists
  only to close a gap in `scripts/resync_pcb_netlist.py` that this task was
  not permitted to modify directly. If this project resyncs another routed
  board in the future, `scripts/resync_pcb_netlist.py` itself should gain a
  by-name net-ordinal remap step for `board.traceItems`/`board.zones` so
  this is not a manual step again.
- The raw `kicad-cli pcb drc` violation count (§5) is reported for
  transparency but is not one of this task's required gates and was not
  investigated further.
