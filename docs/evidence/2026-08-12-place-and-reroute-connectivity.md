<!-- provenance: measured 2026-08-12, feat/board-place-and-reroute session, against a reconciled+placed+routed pcb/temper.kicad_pcb that is NOT the version committed by this PR (see verdict below). kicad-cli 10.0.5, same LD_LIBRARY_PATH/KICAD_STOCK_DATA_HOME environment as docs/evidence/2026-08-11-pad-connectivity-ground-truth.md. -->

# Place + re-route experiment on the reconciled board: real connectivity gains, a real clearance regression, and why this PR does not land the board

> **CORRECTION (2026-08-12), added by the void-board-baseline purge task, not by this
> document's original author.** §3's copper table below (**4,228 track segments / 74
> vias / 66 zones**, cited elsewhere as "PR #1050's figure") and §4's connectivity table
> (**0/110 -> 34/112 nets fully connected**, §6's headline) do not reproduce and are
> **VOID**. The cause, found afterward: this PR's recipe ran its placement stage through
> `target-shared/release/pumpkin_engine`, an untracked, `.gitignore`d binary with no
> identity check -- nothing pinned which source it was built from, so a later session
> regenerating "the same" board with a different build of that binary got a materially
> different placement and a downstream route differing by hundreds to thousands of
> segments (`docs/evidence/2026-08-12-candidate-board-not-landed-engine-provenance.md`
> §3, `docs/evidence/2026-08-12-engine-binary-pinning.md` §1-2). This document's write
> path is not the problem -- it applies `board_origin` correctly (§2 above, "the
> categorically different from #1049's un-fixed write path" note is accurate) -- only the
> unpinned engine is.
>
> **True baseline** -- pinned engine (`docs/evidence/2026-08-07-pumpkin-engine/engine_pin.json`,
> landed #1060) plus a corrected write path (a *different* PR's driver, #1058's, separately
> dropped `board_origin`; not this one) -- **2,514 segments / 22 vias / 76 zones / 168
> footprints**; nets connected 22/112 (19.6%); `unconnected_items` 428 -> 351; kicad-cli
> `clearance`=499 across 130 samples, `creepage` 114-116, `shorting_items` 110, total
> errors 1075-1077. `SAF_HVL_001` 94 -> 74 (-21%) -- not the 94 -> 44 §5's cross-reference
> table cites from `docs/evidence/2026-08-12-hvlv-candidate-board-measurement.md`, which
> carries its own correction notice for the same reason. Current source of truth:
> `scripts/board_shape_baseline.json`. **Nothing below this notice has been edited** --
> the reconciliation, placement-model, and DRC-category findings in §1-7 stand as
> originally recorded; only the specific copper/connectivity counts in §3-4/§6 (and
> anything computed from them) are void.

**Verdict up front: this PR does NOT change `pcb/temper.kicad_pcb`.** The
experiment below is real, reproducible, and shows genuine progress on
connectivity — but the `clearance` DRC category regresses by a real,
deterministic margin, which fails this task's own landing bar ("better on
connectivity AND not worse on safety"). Per that bar, the correct action is
to report honestly and not land, which is what this document and the PR do.
The source-level fixes (coordinate-normalization bug, Pumpkin engine
constraint primitives) are landed regardless — see the PR description.

## 1. Reconciliation (this part *was* verified to work correctly)

`scripts/resync_pcb_netlist.py` against a fresh `make netlist` (digest
`8cfd715e60a3…`, matching #1049's own independently-reported digest) on a
copper-stripped copy of `origin/main`'s board:

```
netlist_components: 168   old_board_footprints: 169   new_board_footprints: 168
kept_count: 162  added_count: 6  removed_count: 7  moved_count: 0
added:   [C37, J1, R65, T2, TP3, U19]   (safety.ocp2.*, rtd_pan.j_rtd1)
removed: [D2, R6, R7, R8, R9, R10, U3]  (power_in.*zcd*)
```

**This is the exact 7-removed/6-added delta the task named**, verified by
stable `Sheetpath` identity (not raw `Reference` strings — see §1a for why
a raw Reference-set diff is the wrong check here), with `moved_count: 0`
proving no already-placed footprint's position/orientation/layer changed
during reconciliation itself (only the subsequent Pumpkin re-solve, §2,
moved anything).

**#1049's failure mode, independently re-checked and NOT repeated**: that
PR reported this exact reconciliation claim on a board whose `Reference`
sets were byte-identical to `origin/main` (`removed: []`, `added: []` —
no reconciliation occurred at all). Diffing my board's `pcb/temper.kicad_pcb`
Reference set directly against `origin/main`'s confirms this board is
genuinely different: 168 footprints vs. 169, with real content changes
(see §1a for the exact set-diff and why it looks smaller than 13 at first
glance).

### 1a. Why a raw `Reference` string-set diff shows 4 removed / 4 added, not 7 / 6

```
old_refs - new_refs = {D5, R76, R77, R78, R79}   (5, not 7)
new_refs - old_refs = {C41, J2, T2, TP4}          (4, not 6)
```

This is **not** a discrepancy in the reconciliation — it is designator
renumbering, a normal, expected side effect of matching by `Sheetpath`
identity (KiCad's own "update PCB from schematic" convention) rather than
by `Reference` string. Removing/adding components anywhere in atopile's
sequential per-class numbering shifts every subsequent designator of that
class: `resync_pcb_netlist.py`'s own report lists **93** such
`designator_changes` (e.g. `discharge.d_fly1` renamed `D3`→`D2`,
`thermal.j_fan` renamed `J1`→`J2` to make room for the newly-added
`rtd_pan.j_rtd1` claiming `J1`). A `Reference`-string set-diff conflates
"same designator, different physical component" (e.g. old `R10` =
`power_in.r_zcd_pullup`, being removed; new `R10` = `discharge.r_coil1`,
renamed from `R15`) with "same component, same designator" — the two
cancel out in a naive set diff, undercounting both sides. The authoritative
check is `Sheetpath` identity (§1's table), which is what
`resync_pcb_netlist.py` actually matches on and reports.

## 2. Placement (Pumpkin, isolation-barrier-constrained)

Full detail, including the reproduced U6-jointly-UNSAT finding, in
`docs/evidence/2026-08-12-isolation-barrier-pumpkin-placement.md`. Summary:
netclass+courtyard constraints (21,948) + PD2/8.0mm horizontal isolation
barrier over all 40 HV-only / 109 SELV-only / 8 isolator components,
solved with all 8 isolators hard-constrained: **infeasible, proven in
3.17s**. Relaxing isolator **U6** alone: **optimal in 2.6s** — reproducing
#1049's central finding independently, on the reconciled component set and
a from-scratch constraint build (the isolator set itself differs from
#1049's board: `T2` — the new OCP-02 current transformer — enters the
isolator set; `U3` — removed by reconciliation — leaves it).

Round-trip oracle: PASS, 168/168 components, 521/521 pads. Containment
(`scripts/check_board_containment.py`): 2 minor violations (near-edge pad
overhang on `L1`, `R60`) out of 527 checked pads — real but small, and
categorically different from #1049's un-fixed write path, which would have
put every component ~20mm off (see
`docs/evidence/2026-08-11-board-origin-write-path-fix.md`).

## 3. Copper preservation/regeneration (the hard precondition this PR's own process enforces)

| | `origin/main` | after placement (pre-route) | after `route_board.py --net-batching` |
|---|---:|---:|---:|
| footprints | 169 | 168 | 168 |
| track segments | **2,290** | 0 (stripped before placing — same primitive `route_pcb` uses) | **4,228** |
| copper zones | **96** | 0 | **66** |
| vias | 48 | 0 | **74** |

**Copper is regenerated, not discarded** — the opposite of #1049's board
(0 segments, 0 zones, final). `segments > 0 and zones > 0` holds on the
final routed output.

## 4. Pad connectivity: real, substantial, cross-validated improvement

Same methodology as
`docs/evidence/2026-08-11-pad-connectivity-ground-truth.md` (KiCad's own
`unconnected_items`, cross-checked against
`pad_connectivity_audit.audit_pcb_file`, both restricted to the *official*
schematic net list — 112 nets on this reconciled board, vs. 110 on
`origin/main`, since reconciliation changed the net table by removing the
`zcd` net and adding OCP-02 nets).

| | `origin/main` (baseline) | this board, routed |
|---|---:|---:|
| Official nets | 110 | 112 |
| **Nets fully connected — KiCad `unconnected_items`** | **0 / 110 (0.0%)** | **34 / 112 (30.4%)** |
| Nets fully connected — `pad_connectivity_audit` (zone-blind) | 0 / 110 | 33 / 112 |
| `unconnected_items` entries | 428 | **319** |
| Pads reached (audit tool, official nets) | 110 / 487 | **181 / 496** |

The 1-net gap between KiCad's oracle (34) and the audit tool (33) is the
same documented zone-connectivity blind spot §5 of the ground-truth doc
already characterizes (the audit tool has no code path for `(zone ...)`
blocks) — not a new disagreement.

**This is real, mechanistically-explained progress**: routing 168
components with `route_pcb` after a fresh, non-overlapping placement
actually connects roughly a third of the board's nets end-to-end, where
`origin/main`'s existing (but fragmented) copper connects none.

## 5. DRC per category — the mixed result that decides the verdict

Single-run values below are exactly reproducible: 10 repeated `run_drc()`
calls against the identical routed board file returned **byte-identical**
`clearance` (499/499/499/499/499/499/499/499/499/499) and `shorting_items`
(81 every time); only `creepage` showed its already-documented ±1 run-to-run
scatter (73 or 74), consistent with `creepage` being the one category
`drc_ceiling.json` already declares nondeterministic. `clearance` is
declared fully deterministic on `origin/main` too (386/386 across 130
samples) — so a single `clearance` sample on this board is already
decisive, not noise.

| Category (error severity) | `origin/main` ceiling | this board, routed | Delta | Verdict |
|---|---:|---:|---:|---|
| **error_ceiling (total)** | 1266 | 1046–1047 | **−219 to −220** | better |
| **clearance** | 386 | **499** | **+113** | **worse** |
| **creepage** | 186 (182–184 observed) | 73–74 | **−112** | much better |
| **shorting_items** | 199 | 81 | **−118** | much better |
| solder_mask_bridge | 154 | 11 | −143 | much better |
| track_width | 199 | 199 | 0 | unchanged |
| copper_edge_clearance | 10 | 10 | 0 | unchanged |
| hole_to_hole | 3 | 2 | −1 | better |
| tracks_crossing | 1 | 0 | −1 | better |
| courtyards_overlap | 11 | 24 | +13 | worse |
| hole_clearance | 105 | 111 | +6 | worse |
| annular_width | 4 | 12 | +8 | worse |
| drill_out_of_range | 4 | 12 | +8 | worse |
| via_diameter | 4 | 12 | +8 | worse |

(Warning-severity categories, e.g. `lib_footprint_issues`/`silk_edge_clearance`,
moved by large amounts in both directions but are **not** used to decide
this verdict — `drc_ceiling.json`'s own provenance already documents that
this environment's missing `kicad-footprints` package makes several warning
categories environment artifacts rather than measured deltas on this exact
board, and this experiment's environment has the identical gap.)

**`clearance` is the deciding category.** Of this task's four explicitly
named comparison categories (`error_ceiling`, `clearance`, `creepage`,
`shorting_items`), three improve substantially and one — `clearance` —
regresses by a real, deterministic, non-trivial margin (+29%). The
regression is concentrated, not diffuse: `487` of `499` violations trace to
15 net pairs, dominated by the `rtd_pan`/`SHUTDOWN`/`vcc`/`safety.ovp-line`
cluster around `U27` (25 violations) and `U26` (12) — a locally congested
region, not a board-wide degradation. A second re-route was attempted
without `--net-batching` (the Makefile's actual `make route` default) to
check whether batching itself was the cause; per
`docs/evidence/2026-08-07-net-batching-prototype.md`'s own architecture
argument, `clearance`/`creepage` enforcement lives entirely in Stage 4
(`occupancy_grid.py`'s path/via dilation), which is **not** batched either
way, so this was not expected to change the picture much. [Result, if it
completed before this document was finalized, is appended below; if not,
the monolithic run was still in progress and this PR's verdict rests on
the `--net-batching` measurement alone, which is itself a complete,
reproducible result.]

## 6. Verdict

**Connectivity: substantially better** (0/110 → 34/112 nets fully
connected; 428 → 319 unconnected items; real copper regenerated, not
discarded). **Safety: not uniformly better** — `clearance` regresses by a
real, deterministic +113 (+29%), concentrated around one congested region,
even though `creepage` (the category most directly targeted by the PD2/8mm
isolation-barrier constraint) and `shorting_items` both improve
substantially.

Per this task's explicit landing rule — **"land only if the board is
better on connectivity AND not worse on safety"** — this does not clear the
bar. Landing it would ratchet `clearance`'s ceiling up by a real amount to
match a board with a real, if concentrated, safety-relevant regression,
which is exactly what `AGENTS.md`'s ceiling-approval contract exists to
prevent doing casually. **`pcb/temper.kicad_pcb` is therefore left
unchanged by this PR.** The reconciliation, placement, and routing
pipeline described above is real, reproducible, and a genuine improvement
over #1049 on every axis that PR failed on (copper preservation,
reconciliation, and rotation-aware isolation-barrier feasibility) — it
simply surfaces a real, previously-invisible clearance problem that a
mostly-unrouted board could not have shown, and that is exactly the kind
of finding this task's "prove it is not better by subtraction" framing
asks for: a board with real copper and real connectivity gains can still
lose on an individual safety axis, and the honest answer is to say so and
not land, not to manufacture an improvement.

## 7. What a follow-up would need to do

1. Investigate the concentrated `clearance` cluster (`U27`/`U26`/`rtd_pan`/
   `SHUTDOWN`/`vcc` region) directly — likely a local placement-density or
   routing-order issue rather than a systemic one, given how few net pairs
   account for the bulk of the regression (§5).
2. If a re-route configuration is found that keeps the connectivity and
   creepage/shorting_items gains while not regressing `clearance`, re-run
   this same measurement pipeline and, if it clears the bar, land the board
   with a full ≥120-sample `drc_ceiling.json` re-measurement and
   `Ceiling-Approval` trailer for any category whose ceiling would need to
   rise (none should, if `clearance` no longer regresses).
3. `pcb/libs/Connector_JST.pretty/JST_XH_B4B-XH-A_1x04_P2.50mm_Vertical.kicad_mod`
   and its `pcb/fp-lib-table` entry (both recovered unmodified from #1049,
   needed because this environment has no `kicad-footprints` checkout to
   resolve `J1`'s real footprint from) are **not** committed by this PR,
   since they only matter in service of a board change this PR does not
   land — a future placement attempt will need to re-add both (trivial;
   shown in full in #1049's diff).
