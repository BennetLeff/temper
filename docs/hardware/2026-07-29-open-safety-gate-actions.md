<!-- provenance: commit=a247227df78f7a324933c03446271e0356826434 (origin/main), dirty=false except this file -->

# Open safety-gate actions: the mains<->SELV isolation barrier

This is an analysis document. **It changes nothing.** No gate, threshold,
board file, or component was modified to produce it. Both gates below were
run locally, on a clean worktree branched from `origin/main` at
`a247227d` ("fix(gate): stop flagging copper-less pads, and wire the
pad-orientation gate (#427)"), to get their real current output rather than
relying on a summary. `elec/build/` was built once with `make netlist`
(required for the safety/EMC tests that read the compiled netlist); nothing
under `elec/src/`, `pcb/`, or `docs/evidence/` was written.

**Headline: both gates are still red, for the reasons already known, but the
REQ-SAFE-01 violation count is 76 across 33 pairs, not the ~56 quoted in the
task. The 56 figure is stale** — it is real and traceable (`docs/evidence/
2026-07-28-tank-cap-placement.md` records "56 over 24 pairs" as of that
commit) but a later change (the tank coil `R30`/`LitzPad_15A` being specified
as a real inductor, `docs/evidence/2026-07-29-tank-coil-specification.md`)
added 9 new violating pairs, taking it to 33 pairs / 76 records. Of those 33
pairs, **only 5 are component-level** (unfixable by moving anything); the
other 28 are ordinary layout/placement problems, all traceable to the one
thing Gate 1 already reports: no keepout has ever been imposed.

Also found in the course of this analysis, stated here because it changes
the layout-vs-purchasing split materially: **two of the five component-level
blockers (C6, U3) already have a corrected part + footprint decision
recorded in `elec/src/*.ato`, which was never propagated into
`pcb/temper.kicad_pcb`.** That is a regeneration/resync task, not a new
purchasing decision, for those two. See §3/§4.

---

## 1. Exact current failure output (verbatim)

### 1a. "Physical mains<->SELV isolation-barrier gate"

Command run (matches `.github/workflows/python-tests.yml:772`):

```
uv run python scripts/check_isolation_keepout.py
```

Exit code: **3** (verified separately from stdout capture; `MIN_BARRIER_WIDTH_MM = 8.0` at `scripts/check_isolation_keepout.py:173`).

```
DEBUG: Loading design_rules.py
Board: <repo>/pcb/temper.kicad_pcb
Manifest: <repo>/elec/domain_manifest.yaml
Copper layers: 4 (F.Cu, In1.Cu, In2.Cu, B.Cu). Footprints examined: 168. Pads examined: 519 (HV=97, SELV=221). Copper items examined (segments+arcs+vias+non-keepout zones): 2482. Keepout zones found on board (any name): 0.
Barrier zone NOT FOUND (name='MAINS_SELV_ISOLATION_BARRIER').
Required minimum barrier width: 8.0mm (REINFORCED creepage; see module docstring).

=== VIOLATIONS: 1 ===

  [missing] 1 violation(s):
    No keepout zone named 'MAINS_SELV_ISOLATION_BARRIER' found on the board (0 other keepout zone(s) present, if any). The mains<->SELV isolation barrier is not physically enforced -- it exists only as declarations (elec/domain_manifest.yaml) and after-the-fact clearance checks. A human must place a keepout region spanning all 4 copper layers (F.Cu, In1.Cu, In2.Cu, B.Cu), at least 8.0mm wide throughout, bisecting the board so every HV-domain component is on one side and every SELV-domain component is on the other, named exactly 'MAINS_SELV_ISOLATION_BARRIER'.

FAILED -- 1 violation(s)
```

This matches the run cited in the task (30390466165 / 30442762922); nothing
changed. **This is the entire failure**: one violation, a missing keepout
zone, no board copper analysis beyond confirming the zone doesn't exist.

### 1b. "Requirements tests (safety / EMC / review / DFM)"

Command run (matches `.github/workflows/python-tests.yml:1458-1463`, from
`packages/temper-placer/`):

```
uv run python ../../scripts/pytest_guard.py --min-tests 240 -- \
  tests/requirements/safety/ tests/requirements/emc/ \
  tests/requirements/review/ tests/requirements/dfm/ \
  -v --tb=short -p no:cacheprovider
```

Result: **299 collected, 293 passed, 1 failed, 5 skipped** (the 5 skips are
pre-existing missing-fixture gaps unrelated to this task — an
`accessible_components` fixture that doesn't exist — not netlist-related;
confirmed by rebuilding `elec/build/` first). Exit code **1** (pytest's own
code, propagated by `pytest_guard.py`). The one failure is the entirety of
this gate's red state:

```
=================================== FAILURES ===================================
_______ TestClearanceIntegration.test_temper_board_clearance_compliance ________
tests/requirements/safety/test_clearance.py:774: in test_temper_board_clearance_compliance
    assert not failures, "\n\n".join(
E   AssertionError: 1 REQ-SAFE-01 finding(s) on the real board:
E
E     76 REQ-SAFE-01 clearance/creepage violations on the real board across 33 pair(s) (11 of the records are intra-footprint, i.e. unfixable by moving anything). Components matched: 158.
E
E     76 REQ-SAFE-01 violation(s), worst first:
E     pair             boundary               insul       metric        meas     req    short  model
E     ----------------------------------------------------------------------------------------------
E     C17<->R32        DC_BUS<->LV_CONTROL    reinforced  creepage     0.905     8.0    7.095  copper; unbroken-surface (exact: geodesic == straight line)
E     C27<->D1         DC_BUS<->LV_CONTROL    reinforced  creepage     1.505     8.0    6.495  copper; unbroken-surface (exact: geodesic == straight line)
E     ... [74 more rows, full table reproduced and grouped in §2 below] ...
E     R30<->R1         DC_BUS<->LV_CONTROL    basic       clearance    2.953     3.0    0.047  copper
E
E     Closest copper, per violating pair: [33 pad-pair identities, reproduced in §2]
E
E     These are measured COPPER-TO-COPPER on exact pad geometry. The checker previously measured origin-to-origin, which is an upper bound on true separation and therefore hid violations; see docs/evidence/2026-07-28-clearance-copper-to-copper.md.
----------------------------- Captured stdout call -----------------------------

DOMAIN CLASSIFICATION COVERAGE: 158 of 168 components classified (94.0%), 54 of 162 compiled nets classified (boundary set ASSERTED by the hard check below: 158 components / 54 nets).
FULL-COVERAGE CROSS-CHECK: 76 REQ-SAFE-01 violation(s) over the full 54-net manifest declaration (158 components). As of 2026-07-27 the asserted set above IS the full declared set, so this figure should track it; a divergence between the two means the fixture has started filtering again.
CREEPAGE MODEL: board declares 0 Edge.Cuts cutout(s)/slot(s) (1 Edge.Cuts item(s), 0 uninterpretable). Surface is unbroken, so creepage == clearance EXACTLY.
MAX COMPONENT COPPER REACH: 23.909mm
============= 1 failed, 293 passed, 5 skipped, 5 warnings in 3.63s ==============
[pytest-guard] OK: 294 tests executed (5 skipped)
```

The full 76-row table and the 33 closest-copper pad identities are exact and
were captured; they are not reproduced a second time verbatim here for
length — they are parsed and grouped in full in §2.

**Every one of the 76 rows is the same boundary crossing: `DC_BUS<->LV_CONTROL`.**
No `MAINS<->LV_CONTROL`, `MAINS<->ISOLATED`, or other boundary type appears
in the failure at all. Every violation is a downstream, measured
consequence of the exact thing Gate 1 reports as missing.

---

## 2. Enumerated, deduplicated violation list, grouped by root cause

### Why 76 records is not 76 problems

Each *pair* of components is checked against up to 4 threshold cells
(`basic`/`reinforced` insulation class x `clearance`/`creepage` metric), and
every cell the measured gap fails to clear produces its own record. A single
physical gap therefore produces between 1 and 4 records. Deduplicating by
**pair** (the actual physical fact — "these two components are too close")
collapses the 76 records to **33 pairs**. The binding cell for every single
one of the 33 is the same: **reinforced creepage, required 8.0mm** — the
same figure Gate 1 is missing a keepout for. (`basic`/`clearance` failures
never occur without `reinforced`/`creepage` also failing, in this data set.)

Of the 33 pairs, **5 are intra-footprint** (a component's own two pads,
same reference designator, straddling the boundary — physically unfixable
by moving the part anywhere on the board) and **28 are inter-component**
(two different parts placed too close — fixable by moving one of them,
rerouting, or a keepout).

### Group A — component-level (intra-footprint, 5 pairs / 11 records)

These are exactly the 5 isolators already identified in
`docs/evidence/2026-07-28-isolator-sourcing-brief.md` and the CP-SAT
infeasibility proof in `docs/evidence/2026-07-28-barrier-constrained-placement.md`.
This run reproduces their numbers exactly (no drift since that analysis):

| Ref | Part (as built on the board) | Binding metric | Measured | Required | Shortfall |
|---|---|---|---:|---:|---:|
| C6 | Y-safety-cap, `Capacitor_THT:C_Disc_D10.0mm_W5.0mm_P5.00mm` | reinforced creepage | 3.200mm | 8.0mm | 4.800mm |
| K2 | Relay, `Relay_THT:Relay_SPDT_Omron-G5LE-1` | reinforced creepage | 3.559mm | 8.0mm | 4.441mm |
| K3 | Relay, `Relay_THT:Relay_SPDT_Omron-G5LE-1` (identical part) | reinforced creepage | 3.559mm | 8.0mm | 4.441mm |
| U3 | Optocoupler, `Package_DIP:DIP-6_W7.62mm` (board) | reinforced creepage | 6.020mm | 8.0mm | 1.980mm |
| U7 | Gate driver, `lib:SOIC16W_Isolated` | reinforced creepage | 7.250mm | 8.0mm | 0.750mm |

Two other manifest-declared isolators (`K1`, `T1`) and one (`PS1`) do **not**
appear here — their own intra-footprint gap already clears 8.0mm (K1 at
exactly 8.000mm, T1 at 9.100mm, per the pad-geometry-model fix,
`docs/evidence/2026-07-28-pad-geometry-model-fix.md`). `T1` does still
appear in Group B below, as an ordinary inter-component pair, not an
intra-footprint one — see the note in that group.

### Group B — layout-level (inter-component, 28 pairs / 65 records)

All 28 share the same boundary (`DC_BUS<->LV_CONTROL`) and the same missing
countermeasure (no keepout). They cluster tightly around four "hot"
DC_BUS-side components plus one near-miss pair, not 28 independent placement
decisions:

| Cluster | DC_BUS-side component | Pairs | Worst shortfall | Best (nearest-compliant) shortfall |
|---|---|---:|---:|---:|
| B1 | **R30** — tank resonant coil, `LitzPad_15A` | 8 (R1, R26, R32, R46, R54, R73, U13, C30) | 5.388mm (R30<->R32) | 0.047mm (R30<->R1) |
| B2 | **C27** — DC-bus link/snubber cap, THT axial `942C16P1K-F` | 7 (D1, R25, R66, C15, TP2, C34, C35) | 6.495mm (C27<->D1) | 0.105mm (C27<->TP2) |
| B3 | **C22** — 0.1uF bypass cap at the half-bridge gate driver | 6 (L2, U15, C16, R77, C12, C37) | 6.031mm (C22<->L2) | 0.401mm (C22<->C37) |
| B4 | **C17** — 10uF bulk bypass cap at the half-bridge gate driver | 5 (R32, R26, U13, R73, R54) | 7.095mm (C17<->R32) | 1.343mm (C17<->R54) |
| B5 | **T1** / **C23** near `U27` (ESP32) | 2 (T1<->U27, C23<->U27) | 0.150mm | 0.105mm |

8+7+6+5+2 = 28 pairs; every "LV_CONTROL-side" component named above is an
ordinary SELV passive (0603/1206 resistor or capacitor, a small logic
buffer, or a test point) that ended up a few mm from a DC_BUS-side part.
None of these 28 pairs involves a part whose own package geometry is the
limit — every one of them is "two ordinary components got placed too
close," which is exactly what happens when nothing on the board enforces
distance across this boundary during placement. **This is one root cause
(the missing keepout from Gate 1) expressed as 28 symptoms, not 28 root
causes.**

B5 needs one clarifying note: `T1` is one of the 8 manifest-declared
isolators (`ct_sense.ct`, a current-sense transformer, primary =
`DC_BUS`-side per `elec/domain_manifest.yaml`), but this specific pair is
**not** an intra-footprint finding — it's `T1`'s primary-side pad sitting
0.150mm short of 8mm from a nearby `U27` (ESP32) pin. `T1`'s own
intra-footprint gap (primary cluster to secondary cluster) already clears
at 9.100mm per Group A's note; this is an ordinary two-component placement
problem on top of that, coincidentally involving the same part.

### The 56-vs-76 discrepancy, resolved

`docs/evidence/2026-07-28-tank-cap-placement.md` records "56 over 24 pairs"
as the REQ-SAFE-01 count at that commit, with the same 5 intra-footprint
parts (11 records) already present then. The gap between 24 and 33 pairs is
almost entirely Group B1: `R30`'s footprint was `new Resistor` (a
placeholder) at that point; `docs/evidence/2026-07-29-tank-coil-specification.md`
replaced it with `new Inductor` on the real `LitzPad_15A` land, pinned to
keep the `R30` designator. That single BOM change is responsible for most of
the 9 new pairs (all of Group B1) and the jump from 56 to 76 records. **56
was accurate as of 2026-07-28; it is stale now.** The true current count is
**76 records / 33 pairs / 5 root-cause groups (A) + 5 clusters (B)**.

---

## 3. Layout-fixable vs. component-needed — and a wrinkle the task didn't anticipate

**Layout-fixable (no new part, no purchasing decision):**
- All of **Group B** (28 pairs). Once a `MAINS_SELV_ISOLATION_BARRIER`
  keepout exists (Gate 1's fix) and placement respects it, none of these 28
  should recur — they are the predictable result of placing SELV passives
  near HV-side bypass/snubber caps and the tank coil with no barrier
  constraint active during placement.
- **C6 and U3, but only partially** — see below. The part+footprint
  decision is *already made and recorded in `elec/src/*.ato`*; only the
  physical `pcb/temper.kicad_pcb` file was never regenerated to match. This
  is a **PCB regeneration/resync task**, not a purchasing task, for these
  two specifically. Concretely:
  - `elec/src/modules.ato:957-958` already declares `y_cap_pe.mpn =
    "VY1222M47Y5UQ6TV0"` and `y_cap_pe.footprint =
    "Capacitor_THT:C_Disc_D12.5mm_W5.0mm_P10.00mm"` (10.00mm pitch). The
    board's actual `C6` footprint is still `Capacitor_THT:
    C_Disc_D10.0mm_W5.0mm_P5.00mm` (5.00mm pitch) — confirmed by reading
    the `(footprint ...)` block for reference `C6` in `pcb/temper.kicad_pcb`
    directly. The 3.200mm measured gap is exactly `5.00 - 1.8` (the old
    pitch), not the 8.0-8.6mm the declared footprint would give.
  - `elec/src/components.ato:548-550` already declares `mpn = "H11L1TVM"`
    and `footprint = "Package_DIP:DIP-6_W10.16mm"` (400-mil DIP). The
    board's actual `U3` footprint is still `Package_DIP:DIP-6_W7.62mm`
    (300-mil DIP) — same direct-read confirmation. The 6.020mm measured gap
    is exactly `7.62 - 1.6` (the old pitch), not the 8.560mm the declared
    footprint would give.

  In both cases the schematic/BOM-level decision is done; what's missing is
  propagating it into the board (the same class of drift
  `docs/evidence/2026-07-29-board-regeneration-corrected-footprints.md`
  already fixed for `U27`/`R30`/`K1`, just not for `C6`/`U3`). This is
  cheap and high-confidence relative to a purchasing decision, but it is
  still a board edit — explicitly out of scope for this analysis document
  to perform.

**Needs a different component (genuine purchasing decision):**
- **K2, K3** — the Omron G5LE-1's own pin layout puts the coil terminals and
  the pole terminal within ~2mm of each other in the tightest axis,
  independent of rotation or land-pattern choice. No footprint edit on this
  part can produce 8mm; a different relay device is required. This matches
  the task's own framing exactly, and `elec/src/modules.ato:1118-1128`
  confirms `k_dis1`/`k_dis2` are still declared as `G5LE-1 DC12` in source
  — unlike C6/U3, no replacement has been decided anywhere yet.

**Needs a footprint-authoring decision, not new schematic silicon, but not a
simple resync either:**
- **U7** — TI's own UCC21550 datasheet publishes two land patterns for the
  same physical part (DWK0014A package): the board's current land ("IPC-7351
  NOMINAL", 9.30mm pad-centre span) measures 7.250mm; TI's own alternative
  ("HV / ISOLATION OPTION", 9.75mm span, narrower 1.65mm-long pads) measures
  8.100mm. Unlike C6/U3, `elec/src/components.ato:48` still declares
  `footprint = "SOIC16W_Isolated"` — the same custom footprint the board
  uses (`pcb/libs/lib.pretty/SOIC16W_Isolated.kicad_mod`) — with no HV/
  isolation-option variant defined anywhere in this repo yet. This is layout
  work (same part, no purchase), but it requires authoring a new footprint
  variant, not just re-running a resync script.

---

## 4. Component-fix binding parameters (no MPNs, no part selection)

Per the task's constraint, this section names the parameter that binds and
the value required — it does not select or recommend a replacement part.

| Ref | Binding parameter | Required value | Current value | Notes |
|---|---|---:|---:|---|
| C6 | **Creepage** (surface, HV pad cluster to SELV/PE pad, reinforced insulation) | >= 8.0mm | 3.200mm (as-built footprint) | Already-declared footprint (`elec/src`) would give ~8.0-8.6mm depending on pad diameter — a PCB-sync question, not a new spec. |
| K2 | **Creepage** (coil terminal to pole/contact terminal, reinforced insulation) | >= 8.0mm | 3.559mm | Also a **terminal-topology** constraint: the coil pins and contact pins must not be interleaved on the same package axis — this is what makes it component-only, not footprint-only. |
| K3 | Same as K2 (identical part) | >= 8.0mm | 3.559mm | Same terminal-topology constraint. |
| U3 | **Creepage** (LED-side pad to output-side pad, reinforced insulation) | >= 8.0mm | 6.020mm (as-built footprint) | Already-declared footprint (`elec/src`) would give 8.560mm — a PCB-sync question, not a new spec. |
| U7 | **Creepage** (primary-side pad cluster to secondary-side pad cluster, reinforced insulation) | >= 8.0mm | 7.250mm (current land pattern) | Same silicon; a manufacturer-published alternative land pattern for the same part number would give 8.100mm — 0.1mm of margin over the 8.0mm gate, effectively zero design margin. |

No clearance, current, or voltage parameter binds on any of these five —
in every case the model reports creepage == clearance exactly (the board
declares 0 usable Edge.Cuts slots, so the surface is unbroken and there is
no separate creepage path to model), and current/voltage ratings on these
parts are not the limiting spec here.

**On U7 specifically**: 0.1mm of margin over an 8.0mm regulatory-derived
figure is a real concern even if it technically passes the gate. Whether
that margin is acceptable is a judgment call for the person making the
purchasing/layout decision, not something this analysis resolves.

---

## 5. Recommended order of attack

Ordered cheapest / highest-confidence first, reasoning included:

1. **Place the `MAINS_SELV_ISOLATION_BARRIER` keepout (Gate 1).** This is
   the single highest-leverage action: it is the literal, direct fix for
   Gate 1, and by construction prevents Group B (28 of Gate 2's 33 pairs)
   from recurring once placement respects it. It requires no new part and
   no component decision — purely a board edit. Note from
   `docs/evidence/2026-07-28-barrier-constrained-placement.md`: a full
   CP-SAT re-solve with the barrier as a hard constraint was already
   attempted and returned INFEASIBLE — but that INFEASIBLE result was
   driven by the Group A isolators (7 of 8 at the time), not by the
   ordinary Group B passives. It is plausible a barrier-respecting re-solve
   restricted to the non-isolator components would succeed even before any
   isolator is fixed; this was **not re-verified** in this analysis (see §6).

2. **Resync `C6` and `U3`'s PCB footprints to what `elec/src` already
   declares.** Zero purchasing decision, zero new schematic work — the
   decision is already made and sitting unapplied. This closes 2 of the 5
   Group A blockers (and 2 of 11 intra-footprint records) for the cost of a
   footprint regeneration/resync pass, the same class of fix already done
   for `U27`/`R30`/`K1` in `docs/evidence/2026-07-29-board-regeneration-
   corrected-footprints.md`.

3. **Author the U7 HV/isolation-option footprint variant.** Same part,
   datasheet-published alternative land, no purchase — but it is a new
   footprint (not a resync) and it clears the gate by only 0.1mm, so this
   is more work and less comfortable margin than #2. Do it after #2, before
   #4, since it still needs no purchasing lead time.

4. **Make the K2/K3 purchasing decision last.** This is the only one of the
   five Group A blockers where the part itself (not just its footprint) has
   to change, meaning it is gated on procurement lead time, a fresh
   coil-driver/dropper compatibility check, and (per the task's framing) a
   decision this analysis does not make. Doing the cheap, no-purchase items
   first (##1-3) means that when this decision is made, it is the last
   open item rather than a blocker sitting in front of easier wins.

5. **Re-run both gates after each step**, not just at the end — Group B's
   28 pairs are placement-sensitive, and a keepout placed today could shift
   which pairs remain close without a full board re-route.

---

## 6. What could not be determined

- **Whether a keepout-respecting CP-SAT re-solve succeeds for the 28
  Group-B (non-isolator) pairs.** The only re-solve on record
  (`docs/evidence/2026-07-28-barrier-constrained-placement.md`) predates the
  pad-geometry-model fix and the tank-coil (`R30`) specification, and its
  INFEASIBLE result is attributed to the isolators, not the ordinary
  passives. No fresh re-solve was run for this analysis (the hard
  constraint against modifying board files/gates was interpreted to also
  cover not running a placement search that would want to write a new
  candidate board). **Could not determine** whether Group B is fully
  resolvable by placement alone, or whether some of the 28 pairs also have
  a genuine minimum-footprint-size floor (e.g. `TP2`, a 1.0mm test-point
  pad, or `L2`, a wound inductor) that limits how close the keepout edge
  can get.
- **Whether U7's 8.100mm HV/isolation-option land pattern is acceptable
  given it clears the 8.0mm gate by only 0.1mm** (and does not clear the
  CP-SAT module's separately-documented 8.5mm working-margin corridor at
  all, per `docs/evidence/2026-07-28-isolator-sourcing-brief.md`). This is
  a judgment call, not a fact to determine.
- **Whether the H11L1TVM part on U3, once its footprint is resynced, is
  certified for *reinforced* insulation at this working voltage** (as
  opposed to merely having a wider lead pitch). The datasheet gives a V_ISO
  rating and a VDE file number but no creepage/clearance figure for the
  package itself; the isolator-sourcing-brief flagged this as open and this
  analysis did not resolve it.
- **The task's `docs/plans/2026-07-28-002-fix-pad-geometry-model-plan.md`
  reference does not resolve to a file in this checkout** (searched by
  exact path and by `pad-geometry` glob under `docs/plans/`; not found).
  The corresponding evidence document,
  `docs/evidence/2026-07-28-pad-geometry-model-fix.md`, does exist and was
  used instead. **Could not determine** whether the plan file was renamed,
  never committed, or lives elsewhere.
- **IEC 60335-1's primary text for the 8.0mm reinforced-creepage figure
  itself.** Every source in this repo (the gate's own docstring, the
  isolator-sourcing-brief) already states this is UNVERIFIED at the primary
  standard and paywalled. This analysis did not attempt to verify it either
  — it is inherited, not re-derived, exactly as the existing evidence marks it.
- **Whether swapping C6's or U3's footprint to the wider-pitch part
  introduces a new local collision** with a neighboring component (larger
  footprint courtyard in the same board location). Not checked — this
  analysis did not run a full-board DRC against a hypothetical resynced
  board, per the hard constraint against modifying `pcb/temper.kicad_pcb`.
- **The two Requirements-gate DFM/EMC skips unrelated to this task**
  (`test_temper_board_bypass_cap_compliance`, `test_all_ics_checked`,
  `test_x_cap_trace_length`, `test_complete_filter_validation`,
  `test_all_requirement_types_checked` — all skipped for a missing
  `accessible_components` fixture or similar, not for netlist availability)
  were observed but not investigated; they do not affect this gate's
  pass/fail and are out of scope for an isolation-barrier analysis.

---

## Sources

- `scripts/check_isolation_keepout.py` (Gate 1, run directly)
- `packages/temper-placer/tests/requirements/safety/test_clearance.py` (Gate 2's failing test)
- `docs/evidence/2026-07-28-isolator-sourcing-brief.md` (Group A candidate research — cited, not repeated; no MPN in this document was written by this analysis)
- `docs/evidence/2026-07-28-barrier-constrained-placement.md` (CP-SAT INFEASIBLE proof)
- `docs/evidence/2026-07-28-pad-geometry-model-fix.md` (K1/T1 clearing the barrier)
- `docs/evidence/2026-07-28-tank-cap-placement.md` (the 56-over-24 baseline)
- `docs/evidence/2026-07-29-tank-coil-specification.md` (R30 becoming a real inductor -- source of the 56->76 growth)
- `docs/evidence/2026-07-29-board-regeneration-corrected-footprints.md` (the U27/R30/K1 precedent for the C6/U3 resync fix)
- `elec/src/modules.ato`, `elec/src/components.ato` (already-declared C6/U3/K2/K3/U7 parts and footprints, read directly)
- `pcb/temper.kicad_pcb` (read-only: footprint blocks for C6, U3, U7, K2, K3 confirmed directly, not inferred)
