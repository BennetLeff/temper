<!-- provenance: measured 2026-08-12, worktree
/tmp/claude-1000/-home-bennet-Desktop-temper/c0bf43ed-bc14-4a43-9c79-57bf591cf8ab/scratchpad/wt-creepage,
branch fix/tank-creepage-geometry, base origin/main @ 900c79dd9, HEAD 1daba90e4 (clean:
`git status --porcelain` empty before every commit; `git grep -l '^<<<<<<< '` over
*.py/*.rs/*.yaml/*.kicad_mod empty). pcb/temper.kicad_pcb sha256
6928b7c8950a732f1991578f5ff7c080104c0847bf438ccd8bf2c75150544b64 -- UNCHANGED, identical to
the hash in docs/evidence/2026-08-11-pad-connectivity-ground-truth.md; every board written
here lives outside the repo tree. Artifacts: widened-R30 input
46ca942076c29ed446ae3ef486d326aa06ccb571541dbda9d212aefdb8f754ea, placed
3826db175501d12addf4cce06171cdaed57adcfd269c18279209dcda50538884, routed
8dbc332f8b4250244018d3c1613d5b043208cde4d889c4eac874466d561c6cfc, pcb/temper.kicad_dru
bad860a0d199e5b4fa35d0643ba68dae1ddecc50ae5f854c27832139b60e6ae4 (regenerated from
scripts/generate_kicad_dru.py before any DRC). pumpkin_engine sha256
7ff153f478f8022f8f8659a514ab7067220812ef82b002fd17955fe0f2083b5e source_commit
5bbf650d47d3a07fffd10a44e7c06c43a0a800bd; scripts/verify_pumpkin_engine.py --require exit 0
BEFORE any solve, engine NOT rebuilt. kicad-cli 10.0.5 via the ~/.local/bin shim. DRC N=130
per board on the canonical ruleset, N=10 on the PD3 probe, N=1 on the 40mm readout probe.
power_pcb_dataset/drc_ceiling.json and pcb/temper.kicad_pro NOT modified; no
Ceiling-Approval trailer written and none is owed -- no board is landed. -->

# Both HV↔HV creepage violations are closed, measured. The board is still not compliant at PD3, and the reason is the honest one: the router immediately re-created a 4.87mm approach on the *same* net pair, as pad-to-track, where no placement constraint can see it.

**Verdict up front.**

1. **Violation 1 — `R30` pad 1 ↔ pad 2 — CLOSED.** `5.0000mm → 10.0000mm`, measured by
   kicad-cli on the routed board. Exactly the requirement, to four decimals, because the
   pitch is derived as `8.0mm pad diameter + 10.0mm creepage` and both terms are exact.
   The pair is no longer reported at a 10.0mm rule minimum.
2. **Violation 2 — `C25` pad 2 ↔ `discharge.k_dis1-nc` — CLOSED, with room.**
   `2.2656mm → 31.3800mm`. The nearest tank-node ↔ `discharge.k_dis1-nc` copper pair
   anywhere on the new board is `C27` pad 2 ↔ `R12` pad 2 at 31.38mm, a 13.9× improvement,
   and it is now a pad-to-pad pair rather than the pad-to-track one that caused the
   violation. **This was the pair #1089 warned it could not promise** (component-box bound
   vs. pad-to-track violation); it cleared anyway, and the measurement — not the
   constraint — is what says so.
3. **Placement stayed feasible with everything composed.** Isolation barrier (all 8
   isolators `C6, K1, K2, K3, PS1, T1, U3, U7`, **none relaxed**) + tank creepage (180
   pairs @10.0mm) + #1082's heatsink co-location (U5/U6 common rotation) →
   `optimal`, on the board carrying the **widened** R30 (26.0×8.0mm, up from 21.0×8.0mm).
   0 tank-creepage post-check violations, heatsink requirement SATISFIED, containment PASS.
   The widened part cost solve time (1.3s → 37–46s) but not feasibility.
4. **The board is NOT compliant at PD3 afterwards, and this is the headline caveat.**
   Three *new* pairs sit under 10.0mm on the routed board, **all three pad-to-routed-copper,
   none of them pad-to-pad**. The worst, 4.8668mm, is a `tank.c_tank1-p2` **track** against
   `R30` pad 2 (`tank-out`) — electrically the *same two nets* as violation 1, 544.6 Vrms,
   re-created 3mm closer than the pad pair it replaced. Under the canonical PD2/6.3mm rule
   the tank-rule violation count is **unchanged at 2**; only the identities changed.
   Sec 3.
5. **`clearance` does not move, as expected — 499**, against 501 on the heatsink board and
   499 on the candidate before it. It is a placement-family property, not a regression of
   this work, and it is not presented as failure here. Sec 5.
6. **Pad connectivity (and that is the metric being reported): 50/139** nets fully
   pad-connected, fake-completion 44, honest-gap 45. The heatsink board's is 55/139.
   Slightly worse, on a board whose largest HV part just grew 5mm. Sec 6.
7. **A pre-existing condition found while baselining, unrelated to this work and not fixed
   here: the committed board no longer measures inside its own ceiling.** With today's
   regenerated ruleset it measures **1296 errors** (ceiling 1266), `clearance` 402 (ceiling
   386), `creepage` 200 (ceiling 186). Sec 5.1.

---

## 1. What changed

Two files, one fix each. Neither touches `pcb/temper.kicad_pcb`.

### 1.1 `pcb/libs/lib.pretty/LitzPad_15A.kicad_mod`: pad pitch 13.0mm → 18.0mm

That footprint's own `descr` had already predicted this failure and named its condition:

> "if the finalized L pushes working voltage above 400V, this 13.0mm/5.0mm figure is a
> floor, not sufficient, and must be re-derived at the higher voltage … a >400V case needs
> a fresh standard lookup, not extrapolation from this table"

The condition is met. The tank node is **measured** at 570.5 Vrms / 923.7 V peak; this pad
pair specifically carries `tank.c_tank1-p2` ↔ `tank-out`, essentially the tank↔`PWR_RTN`
voltage at **544.6 Vrms**. The fresh lookup is a different table *and* a different pollution
degree from the superseded one: **IEC 60335-1 Table 18** (functional insulation), band
**>500–800V**, material group **IIIa/IIIb**, **PD3** → **10.0mm**. PD3 governs as-built
(IEC 60335-2-6 cl. 29.2's Addition; the PD2 sealed compartment is unbuilt and thermally
counterproductive). Coating to PD1 is not available: IEC 60664-3 cl. 4.3 requires the
conductive part be *covered*, and these are bare litz-wire terminations that must stay
uncoated to be soldered.

New pitch **18.0mm = 8.0mm pad diameter + 10.0mm creepage**.

The `descr` records that derivation, records that the PD3/Table 18 lookup **supersedes** the
PD2/Table 16 400V one (the older figure is not "a floor that got raised" — it was read from
a table that does not apply to this node), and **preserves the author's still-open second
caveat verbatim in substance**: the 8.0mm pad *diameter* remains the original "generic …
low confidence, no part-specific datasheet" figure, unsourced, needing human sign-off. One
sentence is added to it, because the new derivation created a coupling that did not exist
before: the pitch is derived *as* `diameter + 10.0mm`, so if the diameter is ever sourced at
anything but 8.0mm, **the pitch must move with it or the 10.0mm is silently lost**. There is
zero margin here — Sec 2 measures the gap at exactly 10.0000mm.

### 1.2 `cli/__init__.py`: tank creepage enabled on the production CP-SAT solve

`solve_placement(tank_creepage={"margin_mm": DEFAULT_TANK_CREEPAGE_MM})` — 10.0mm, PD3 —
on the `optimize` CP-SAT path (the `--no-loop` direct solve; placement in this repo is a
deliberately human-gated CP-SAT solve, per `Makefile:35`'s note, not a `make build` step).
The constraint has existed since #1089 but was opt-in and passed by nothing, so no shipping
solve held the tank node off the other HV nets.

The report is printed too, including `self_pairs` — the intra-footprint pairs the constraint
provably *cannot* cover, because a component's pads move as one rigid body. Sec 1.1 is
exactly one of those, and a constraint that silently cannot see the violation next to it is
how this class of gap survives.

**Scope, stated rather than glossed:** the `--loop` place↔route repair path
(`_loop_core.py::_call_solver`) is **not** wired. It has a Python oracle mirror in
`tests/placer/cp_sat/_loop_core_py_oracle.py` and a large fixture surface that a new
always-on kwarg would move; that is a separate change with its own measurement, not a line
to slip in under this one.

---

## 2. The two violations, measured

### 2.1 Method: a readout probe, because a cleared violation reports no number

kicad-cli reports a creepage violation's `actual` distance only when it *fires*. A pair that
clears the rule vanishes from the report, which cannot distinguish "10.0mm" from "40mm" —
or from "the rule stopped matching this pair at all", which is the failure mode that would
make this whole document a lie.

So every distance below is read from a **readout probe**: the canonical, regenerated
`.kicad_dru` with the single `HighVoltageTank functional creepage` rule's `min` raised to
**40.0mm** and nothing else altered. Every matching pair inside 40mm then reports itself,
with its measured distance. The pass/fail question is answered separately by a **PD3 probe**
at `min 10.0mm` (N=10), and the ceiling table (Sec 5) uses the **canonical** ruleset at its
`main` value of 6.3mm.

Three DRU variants, one board each, differing in exactly one number. Every DRC directory
carries `fp-lib-table`, `libs/`, a matching-stem `.kicad_pro` **and** the regenerated
`.kicad_dru` (the 303-error silent undercount documented in
`2026-08-12-heatsink-board-drc.md` §1 is what that last one prevents).

### 2.2 Result

| | committed board | new board | |
|---|---:|---:|:--|
| **`R30` pad 1 (`tank.c_tank1-p2`) ↔ `R30` pad 2 (`tank-out`)** | | | |
| — measured gap | **5.0000mm** | **10.0000mm** | ✅ closed, exactly at the requirement |
| — reported at `min 10.0mm`? | yes (violation) | **no** | ✅ |
| **`C25` pad 2 (`tank.c_tank1-p2`) ↔ `discharge.k_dis1-nc`** | | | |
| — measured gap | **2.2656mm** (to a B.Cu track) | **31.3800mm** (`C27` pad 2 ↔ `R12` pad 2, the nearest such pair anywhere on the board) | ✅ closed, 13.9× |
| — reported at `min 10.0mm`? | yes (violation) | **no** | ✅ |

The committed-board figures reproduce `2026-08-12-hv-hv-creepage-enforcement.md` §5.1 to the
digit (2.2656 / 5.0000), on a different branch, a different ruleset regeneration and a
different day — the two named violations are real and stable, not measurement noise.

Full readout, committed board (13 pairs inside 40mm, 4 under 10.0mm, 2 under 6.3mm):

```
   2.2656  PTH pad 2 [tank.c_tank1-p2] of C25 | Track [discharge.k_dis1-nc] on B.Cu, length 7.6368 mm
   5.0000  PTH pad 1 [tank.c_tank1-p2] of R30 | PTH pad 2 [tank-out] of R30
   6.3992  PTH pad 2 [tank.c_tank1-p2] of C25 | Via [discharge.k_dis1-nc] on F.Cu - B.Cu
   8.2547  PTH pad 1 [tank.c_tank1-p2] of R30 | Pad 1 [tank-out] of T1 on F.Cu
  20.6595  PTH pad 2 [w1_1] of F1            | PTH pad 2 [tank.c_tank1-p2] of C26
  … 8 further pairs, all >23mm
```

Full readout, new board (25 pairs inside 40mm, 3 under 10.0mm, 2 under 6.3mm):

```
   4.8668  Track [tank.c_tank1-p2] on F.Cu, length 83.0124 mm | PTH pad 2 [tank-out] of R30      <-- NEW
   6.2350  Track [w1_1] on F.Cu, length 13.6000 mm            | PTH pad 2 [tank.c_tank1-p2] of C27  <-- NEW
   6.5525  Track [tank.c_tank1-p2] on F.Cu, length 0.1414 mm  | PTH pad 1 [SW_NODE] of C25         <-- NEW
  10.0000  PTH pad 1 [tank.c_tank1-p2] of R30 | PTH pad 2 [tank-out] of R30                        (was 5.0000)
  13.3767  PTH pad 4 [w1_2] of L1             | PTH pad 2 [tank.c_tank1-p2] of C27
  16.1391  PTH pad 2 [tank.c_tank1-p2] of C25 | Track [discharge.k_dis2-nc] on B.Cu, length 0.4000 mm
  … 19 further pairs, all >20mm, including 31.3800 to discharge.k_dis1-nc
```

The 25-vs-13 pair count is not a regression: it is the router emitting more tank-node copper
in more places, so more pairs fall inside the 40mm probe window at all.

---

## 3. What routing put back, and why the placement constraint could not stop it

**All three new sub-10mm pairs are pad-to-routed-copper. Not one is pad-to-pad.** That is
precisely the boundary `2026-08-12-tank-creepage-placement.md` §2 drew in advance: a
`separated` constraint bounds component *boxes*, which guarantees pad-to-pad separation
between two components' own footprints and says nothing about where a trace goes afterwards.
The constraint did its job — the post-solve check finds **0 violations across all 180
pairs**, and the pad-to-pad readout confirms it on real copper (the closest pad-to-pad pair
on the new board is 10.0000mm, the R30 self-pair, which placement cannot move either).

The worst new pair deserves naming rather than aggregating:

```
4.8668mm   Track [tank.c_tank1-p2] on F.Cu, length 83.0124mm  ↔  PTH pad 2 [tank-out] of R30
```

That is **the same electrical pair as violation 1** — the tank node against `tank-out`,
544.6 Vrms, Table 18 row vi, 10.0mm required. The geometry fix moved R30's two *pads* to
10.0mm apart, and the router then ran an 83mm `tank.c_tank1-p2` trace back to within 4.87mm
of the far pad. **The requirement is not met on the routed board.** What changed is where
the shortfall lives: it is no longer a footprint defect (which is fixed, permanently, in the
library) but a routing degree of freedom, and closing it needs a routing-aware creepage
keepout — the router honours netclass *clearance*, not the DRU's *creepage* rules.

The other two:

* `6.2350mm` — a `w1_1` track against `C27` pad 2. `w1_1` is mains-side; this pair is
  charged the tank rule's figure because `w1_1` classifies `HighVoltage`.
* `6.5525mm` — a **0.1414mm stub** of `tank.c_tank1-p2` against `C25` pad 1 (`SW_NODE`).
  This is the pair `generate_kicad_dru.py`'s own comment flags as *deliberately
  over-constrained by one table row*: tank↔`SW_NODE` is the voltage **across** the tank caps,
  411.5 Vrms, Table 18 band v, not band vi. Its 6.55mm clears band v's PD2 figure (4.0mm)
  comfortably; whether it clears band v at **PD3** is a table lookup this document does not
  have primary text for and will not extrapolate — flagged, not asserted.

**Net effect on the enforced rule as `main` has it configured (PD2/6.3mm): 2 tank-rule
violations before, 2 after.** Different pairs, same count. Under the requirement that
actually governs (PD3/10.0mm): **4 before, 3 after**. Both fixes are real and both are
measured; neither is sufficient on its own to make the routed board compliant, and this
document does not claim otherwise.

---

## 4. Composition: all three constraint sets, on the widened part

Engine gate first, per protocol:

```
$ .venv/bin/python scripts/verify_pumpkin_engine.py --require
pumpkin_engine identity gate: VERIFIED -- sha256=7ff153f4… source_commit=5bbf650d47…   (exit 0)
```

Model: board 152×234mm, 169 components, tau=0.4mm. Base 9,714 netclass + 6,282 courtyard =
15,996 `separated`. Barrier: PD2/8.0mm horizontal, corridor Y [113.0, 121.0], hv_only=43,
selv_only=106, isolators=8, unclassified=12, **`--relax ''` — no isolator relaxed**. Tank
creepage: **180 pairs** at 10.0mm (not #1089's 168 — the netclass full-sync widened the
`HighVoltage` population; see Sec 8.4). Heatsink: 4 constraints, common rotation 1.

| Run | status | solver | wall |
|---|---|---:|---:|
| barrier + tank creepage @10.0mm + heatsink rot 1, on the **widened** R30 board | **optimal** | 37.2s / 46.1s (two runs) | 37.5s / 46.3s |

Both runs returned **byte-identical positions and rotations**; only the solver's own wall
time varied. Post-solve, on the solved coordinates:

* `check_tank_creepage_separation`: **0 violations across all 180 pairs** at 10.0mm.
* `check_heatsink_colocation`: **shared-heatsink requirement SATISFIED** (U5 rot 1, U6 rot 1).
* Isolation barrier, re-derived independently from `elec/domain_manifest.yaml` and evaluated
  against the solved boxes: **0 violations** across 43 hv_only + 106 selv_only; all 8
  isolators straddle the corridor with their HV pads below it and SELV pads above it.
* Containment: **PASS**, 169 footprints / 527 pads inside the outline, write-back 169
  updated / 0 skipped / 0 warnings, with `board_origin=board.origin` = (20, 20).

Where the moved parts landed (normalized frame): `C25` (60.51, 75.64) rot 0, `C26` (129.94,
12.00) rot 0, `C27` (74.37, 52.14) rot 180°, `R30` (4.50, 75.25) rot 270°, `U5` (142.03,
44.90) rot 90°, `U6` (141.09, 62.00) rot 90°.

**The cost of the widened part is solve time, not feasibility.** #1089 measured this model at
1.29s with 168 pairs on the 21mm-wide R30; the same composition with 180 pairs on the 26mm
R30 takes 37–46s. Still `optimal`, still well inside the 120s budget, but a 30× jump worth
recording: R30 at 26.0×8.0mm is a large rigid obstacle that must clear 10.0mm from 45 other
HV components while staying HV-side of the barrier.

**Two isolators overshoot the corridor edge by ≤0.010mm** (`K1` hv_far 113.005, `K3` hv_far
113.010, against a bound of 113.000) — the engine serialises positions at 2 decimals
(0.01mm), and the write-back uses those rounded values. The encoded constraint is exact in
integer centi-mm; this is quantization at the write-back boundary, the same artifact #1089
recorded as `9.999999999999993mm`. Recorded because it is real geometry on the written
board, not because it is meaningful at 8.0mm of barrier.

---

## 5. Full per-category DRC table

**N=130 samples per board**, canonical regenerated ruleset (tank rule at its `main` value,
6.3mm), median with [min–max]. Ceiling column is `power_pcb_dataset/drc_ceiling.json`
`violations_by_type` for `pcb/temper.kicad_pcb`; **absent from that map ⇒ implicit ceiling 0**.

### Errors

| category | ceiling | committed, measured today (N=130) | **this board** (N=130) | Δ vs committed | vs ceiling |
|---|---:|---:|---:|---:|:--|
| `clearance` | 386 | 402 [402–402] | **499 [499–499]** | +97 | ❌ +113 over |
| `creepage` | 186 | 200 [198–200] | **121 [119–121]** | **−79** | ✅ 65 under |
| `shorting_items` | 199 | 199 | **142** | −57 | ✅ |
| `solder_mask_bridge` | 154 | 154 | **70** | −84 | ✅ |
| `hole_clearance` | 105 | 105 | **66** | −39 | ✅ |
| `track_width` | 199 | 199 | 199 | 0 | ⚠️ exactly at ceiling |
| `courtyards_overlap` | 11 | 11 | **13** | +2 | ❌ +2 over |
| `copper_edge_clearance` | 10 | 10 | **21** | +11 | ❌ +11 over |
| `tracks_crossing` | 1 | 1 | 1 | 0 | ⚠️ exactly at ceiling |
| `annular_width` | 4 | 4 | **absent (0)** | −4 | ✅ |
| `drill_out_of_range` | 4 | 4 | **absent (0)** | −4 | ✅ |
| `via_diameter` | 4 | 4 | **absent (0)** | −4 | ✅ |
| `hole_to_hole` | 3 | 3 | **absent (0)** | −3 | ✅ |
| **TOTAL errors** | **1266** | 1296 [1294–1296] | **1132 [1130–1132]** | **−164** | ✅ 134 under |

**No new error class:** every category present on this board already has a
`violations_by_type` entry. Two categories breach their per-type ceiling (`clearance` +113,
`copper_edge_clearance` +11, `courtyards_overlap` +2) — under R27 that is three
`Ceiling-Approval:` trailers, and **none is written here, because no board is landed here.**

### Warnings

| category | committed | this board | Δ |
|---|---:|---:|---:|
| `silk_edge_clearance` | 1 | **199** | **+198** |
| `holes_co_located` | absent (0) | **12** | **+12 — new class** |
| `silk_over_copper` | 172 | 199 | +27 |
| `pth_inside_courtyard` | 1 | 7 | +6 |
| `lib_footprint_mismatch` | 24 | 23 | −1 |
| `lib_footprint_issues` | 11 | 11 | 0 |
| `missing_courtyard` | 5 | 5 | 0 |
| `silk_overlap` | 199 | 199 | 0 |
| `track_dangling` | 45 | **21** | −24 |
| `via_dangling` | 32 | **absent (0)** | −32 |
| **TOTAL warnings** | 490 | **676** | **+186** |

`silk_edge_clearance` 1 → 199 is the standout and is almost certainly the 199-cap artifact
several categories here share (`silk_overlap`, `silk_over_copper`, `track_width` all sit at
exactly 199); a re-placed board pushes silkscreen toward the outline everywhere at once.
Warning-severity, not gating, but it is a real +198 and is not buried.

### 5.1 The committed board no longer measures inside its own ceiling — pre-existing

Measured this session, N=130, on **byte-identical** `pcb/temper.kicad_pcb` (sha256
`6928b7c8…`): **1296 errors** against a recorded `error_ceiling` of **1266**, `clearance`
**402** against 386, `creepage` **200** against 186.

`2026-08-12-heatsink-board-drc.md` measured the same board bytes at **1264 / 386 / 184**
this morning. The board did not change; the **ruleset** did — the `HighVoltageTank` netclass
carve-out and the new HV↔HV rule (#1084/#1089) landed on `main` after the ceiling record's
provenance commit (`f70296adc`), and `pcb/temper.kicad_pro`'s netclass assignments moved with
them. So:

* **Cross-document comparison to the heatsink board's 1143 / clearance 501 / creepage 112 is
  NOT matched-methodology** and is quoted here only as a family reference. The matched
  comparison in the table above is committed-today vs. this-board, both N=130, both on the
  same regenerated `.kicad_dru`.
* **The ratchet on `main` is currently red against its own board**, by +30 aggregate, before
  any candidate is considered. That is a pre-existing defect of the ceiling record, not of
  this work, and it is **not** repaired here: `drc_ceiling.json` is untouched, per
  instruction and per the #1049 failure mode.

### 5.2 `clearance` — 499, and that is not a failure

| board | `clearance` |
|---|---:|
| committed (today) | 402 |
| prior HV/LV candidate | 499 |
| heatsink board (#1082) | 501 |
| **this board** | **499** |

Every freshly re-solved, re-routed board in this family lands at 499–503. This one is at the
bottom of that band. It moved with the *placement family*, not with the tank constraint —
exactly the prediction, and reporting it as a regression of this change would be wrong. It
remains the single largest blocker to landing any re-solved board, and it is unaddressed
here by design.

---

## 6. Pad connectivity — and that is what is being reported

The router's PRIMARY metric, from the same run that produced the measured board:

```
Result: 66/103 nets (64.1%)  segments=3798 vias=38 zones=102  wall=459.9s
[net-batching] 11 batch(es), 11 solved at batch level, 0 crashed, 0 hit the timeout
Result (pad connectivity, PRIMARY metric): 50/139 nets fully pad-connected
    fake-completion=44  honest-gap=45
[copper-audit] 110 topology-solved nets: 74 carry copper, 2 legitimately need none,
    34 UNEXPLAINED (solved but emit no copper)
```

| | heatsink board (#1082) | **this board** |
|---|---:|---:|
| pad connectivity (PRIMARY) | 55/139 | **50/139** |
| fake-completion | 59 | **44** |
| honest-gap | 25 | **45** |
| topology-solved | 86/102 (84.3%) | 66/103 (64.1%) |
| copper-audit UNEXPLAINED | 14 | 34 |

**Down 5 nets on the primary metric**, and down harder on topology (−20 points). The
fake-completion count improves (−15) while honest-gap worsens (+20), which is the same total
told more honestly: fewer nets that *look* routed while leaving pads unjoined, more nets
that plainly failed. `unconnected_items` does not appear as a DRC category on either board
under this invocation, so there is no independent corroboration from KiCad's engine here —
stated rather than substituted for.

A 5mm-wider R30 with a hard 10.0mm keep-away from 45 HV neighbours is a plausible cause, but
this run does not isolate it (no ablation was solved for connectivity), so it is a
hypothesis, not a finding.

---

## 7. What did not fit

* **The R30 pad pair has exactly zero margin.** 10.0000mm against a 10.0mm requirement. Any
  future change to the 8.0mm pad diameter — still the unsourced figure the original author
  flagged and this change deliberately did not close — breaks compliance unless the pitch
  moves with it. The `descr` now says so explicitly; that is the only enforcement.
* **The routed board is not PD3-compliant.** Three pairs under 10.0mm, worst 4.8668mm, all
  pad-to-track (Sec 3). Closing them needs a routing-stage creepage keepout; the router
  honours netclass clearance, not DRU creepage rules. That is the next unit of work and it
  is not attempted here.
* **The DRU still enforces PD2/6.3mm.** `_TANK_POLLUTION_DEGREE = "PD2"` in
  `generate_kicad_dru.py` is deliberately left alone: flipping it to PD3 is a one-line change
  that raises the committed board's `creepage` from 200 to 202 and its total to 1298,
  **turning a red ratchet redder on `main`**, and it needs to be sequenced with a ceiling
  decision by someone who can approve one. Every PD3 number in this document therefore comes
  from a probe ruleset, never from a change to what CI enforces.
* **`clearance` +113 over ceiling.** Unaddressed, as expected, Sec 5.2.
* **The `--loop` repair path is still unwired** (Sec 1.2).

---

## 8. Environment and correctness notes worth carrying forward

### 8.1 Routing was broken repo-wide when this started

`scripts/route_board.py` died with
`AttributeError: module 'temper_orchestration' has no attribute 'RouterPipeline'`. The
installed `.venv/…/site-packages/temper_orchestration/*.so` (built today at 20:32) does not
export the `RouterPipeline` pyclass that `router_v6/_pipeline_core.py:358` calls
unconditionally — i.e. **no board in this checkout could be routed through the production
driver.** Consistent with the in-flight pyclass/PyAny removal spikes
(`docs/evidence/2026-08-12-pyclass-removal-spike.md`,
`…-rust-pyany-removal-spike.md`).

Worked around **without touching the shared venv**: `cargo build --release --locked
--features pyo3/extension-module` from this worktree's own pristine source (12.4s against
the shared cache), the resulting `libtemper_orchestration.so` dropped into a private
`PYTHONPATH` directory. The venv is left exactly as found. **Someone should re-run
`make extensions`** — this is an environment defect that will silently break the next
routing run too.

### 8.2 A pre-existing test failure on `main`, not caused by this change

`test_tank_creepage.py::TestGroupMembership::test_pair_count_matches_measured_board` fails on
`origin/main` (asserts 168 pairs, measures **180**), verified by `git stash` on an otherwise
clean tree. The netclass full-sync widened the `HighVoltage` net population after #1089 pinned
that number. Left alone: it is a real signal about a stale test, and repairing it inside a
board-measurement PR would hide the fact that the constraint's scope changed under it.

### 8.3 Provenance of every number

Every board written by this work lives in the session scratchpad. `git status --porcelain`
was empty (bar the intended source edits) before every commit, and
`git grep -l '^<<<<<<< ' -- '*.py' '*.rs' '*.yaml' '*.kicad_mod'` was empty before both.
`test_production_board_routing_drc_regression` was **not** run (it routes monolithically and
OOMs at 58.9 GB).

---

## 9. Reproduction

```bash
# 0. engine identity -- stop if this is not exit 0
.venv/bin/python scripts/verify_pumpkin_engine.py --require

# 1. widened-R30 input board (scratch copy; R30 pad 2 (at 13 0 180) -> (at 18 0 180),
#    mirroring pcb/libs/lib.pretty/LitzPad_15A.kicad_mod)

# 2. composed solve: barrier (no isolator relaxed) + tank creepage @10.0mm + heatsink rot 1
PYTHONPATH=packages/temper-placer/src .venv/bin/python \
  docs/evidence/2026-08-12-tank-creepage-geometry-run.py \
  --board <widened>.kicad_pcb --rot 1 --relax '' --margin-mm 10.0 \
  --timeout-ms 120000 --out solved.json

# 3. write-back WITH board_origin=board.origin (20,20), then containment
#    write_placements_to_pcb(..., components=netlist.components, board_origin=board.origin)
.venv/bin/python scripts/check_board_containment.py --board <placed>.kicad_pcb

# 4. route
PYTHONPATH=<private orchestration build>:packages/temper-placer/src .venv/bin/python \
  scripts/route_board.py --pcb <placed>.kicad_pcb \
  --rules packages/temper-placer/configs/netclass_rules.yaml \
  --output <routed>.kicad_pcb --net-batching --batch-size 10

# 5. DRC dirs: board + matching-stem .kicad_pro + REGENERATED .kicad_dru + fp-lib-table + libs/
.venv/bin/python scripts/generate_kicad_dru.py
#    canonical (6.3mm) for the ceiling table; min=10.0mm for pass/fail;
#    min=40.0mm for the readout probe. Nothing else in the ruleset is altered.

# 6. DRC campaign via the repo's own runner (--all-track-errors, single-threaded pin)
#    temper_placer.validation._drc_api.run_drc(board), N=130
```

## Files

* Footprint fix: `pcb/libs/lib.pretty/LitzPad_15A.kicad_mod`
* Production wiring: `packages/temper-placer/src/temper_placer/cli/__init__.py`
* Composition harness: `docs/evidence/2026-08-12-tank-creepage-geometry-run.py`
* This document: `docs/evidence/2026-08-12-tank-creepage-geometry.md`
* Carried forward, not re-derived: `docs/evidence/2026-08-12-hv-hv-creepage-determination.md`
  (Table 18), `…-hv-hv-creepage-enforcement.md` (the 2.2656/5.0000 measurements and the DRU
  rule), `…-tank-creepage-placement.md` (#1089's box-vs-copper boundary),
  `…-igbt-shared-heatsink-hard-constraint.md` (#1082), `…-heatsink-board-drc.md` (the DRC
  protocol and the 1143/501/55-of-139 reference figures)
* **Not modified:** `pcb/temper.kicad_pcb`, `pcb/temper.kicad_pro`,
  `power_pcb_dataset/drc_ceiling.json`, `scripts/generate_kicad_dru.py`, `elec/**`
