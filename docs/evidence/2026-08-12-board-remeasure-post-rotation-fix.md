<!-- provenance: commit=756968706b4025b6910ec33c20a0c63fd7bb6b5b dirty=false -->
<!-- provenance: measured 2026-08-12, worktree /home/bennet/Desktop/temper-measure-rotfix,
branch measure/board-post-rotation-fix, base 756968706 (origin/main tip at task start,
includes #1060 engine pinning, #1061 netclass param reconciliation, #1070 shape-baseline
extraction, #1073/#1075 audit+CNF, #1074 rotation write-back fix). The worktree has its
own `.venv` (`make venv-isolate`); `scripts/check_venv_integrity.py` PASSED (16/16
editable entries under this repo root, 239 other registered worktrees excluded) and
`scripts/check_stale_extensions.py` PASSED (10/10 fresh) before any measurement.
pumpkin_engine identity VERIFIED via `scripts/verify_pumpkin_engine.py` (exit 0,
binary_sha256=7ff153f478f8022f8f8659a514ab7067220812ef82b002fd17955fe0f2083b5e,
source_commit=5bbf650d47d3a07fffd10a44e7c06c43a0a800bd) before every solve. kicad-cli 10.0.5 at
/home/bennet/.local/opt/kicad-10.0.5 (LD_LIBRARY_PATH covering root/usr/lib*,
KICAD_STOCK_DATA_HOME=root/usr/share/kicad). PYTHONHASHSEED left UNSET, matching the
recipe doc's own primary determinism protocol. Every board write went to
/tmp/.../scratchpad/remeasure/, never under pcb/** -- `git status --short pcb/` empty at
every checkpoint, including the DRU: this task regenerates the SSOT `.kicad_dru` NEXT TO
the scratch board rather than into `pcb/`, so unlike prior docs in this lineage it does
not write inside pcb/ at all. pcb/temper.kicad_pcb sha256
6928b7c8950a732f1991578f5ff7c080104c0847bf438ccd8bf2c75150544b64 unchanged throughout.
Machine: 24 cores, shared with 2-3 concurrent agent sessions (load average 9-75 over the
session). -->

# The raise list does NOT shrink: it shifts. `courtyards_overlap` and `copper_edge_clearance` shrink by ~70%, `silk_edge_clearance` does not move at all, three via/drill raises vanish, and the warning ceiling gets WORSE (+166 -> +206)

**Verdict up front.** With the three measurement-corrupting defects fixed (#1060
engine pin, #1074 rotation-index-0 write-back, #1070 void-baseline purge), the
recipe reproduces **byte-identically across two fully independent runs** at every
stage, and `check_board_containment.py` **PASSES** on both the placed and the routed
board. But the task's hypothesis -- "several of those were artifacts of components
written at stale angles, and the list shrinks materially" -- is **only partly
right, and it is wrong about which categories**. The honest answer, stated plainly
because it is the less convenient one:

| raise (candidate max vs. committed ceiling) | pre-#1074 | post-#1074 | hypothesis said | measured |
|---|---:|---:|---|---|
| `clearance` | +113 | **+113** | real | **real -- byte-identical 499/499, 130 samples each** |
| `courtyards_overlap` | +20 | **+6** | rotation artifact | **partly: -70%, but +6 survives** |
| `copper_edge_clearance` | +5 | **+2** | rotation artifact | **partly: -60%, but +2 survives** |
| `silk_edge_clearance` (warn) | +198 (1 -> 199) | **+198 (1 -> 199)** | rotation artifact | **NO -- does not move at all** |
| `annular_width` | +4 | **none (-2)** | real | **GONE** |
| `drill_out_of_range` | +4 | **none (-2)** | real | **GONE** |
| `via_diameter` | +4 | **none (-2)** | real | **GONE** |
| `pth_inside_courtyard` (warn) | +5 | **+5** | — | unchanged |
| `lib_footprint_issues` / `_mismatch` (warn) | +2 / +2 | **+2 / +2** | — | unchanged (environment artifact, §5c) |
| `silk_over_copper` (warn) | +1 | **+27** | — | **WORSE** |
| `holes_co_located` (warn, no ceiling entry -> implicit 0) | +2 (new class) | **+14 (new class)** | gone? | **still new, and 7x worse** |
| **aggregate warning ceiling** | +166 | **+206** | — | **WORSE** |
| **aggregate error ceiling** | none (-189) | **none (-211)** | — | better |

So: **6 error-severity raises become 3** (a genuine improvement, driven entirely by
the three via/drill categories vanishing), the **6 warning-severity raises stay at
6** with two of them growing, and
the single largest raise on the whole board -- `silk_edge_clearance` 1 -> 199,
saturated -- is completely untouched by the rotation fix. It is not a write-back
artifact.

**And the shrink is not all attributable to #1074.** §0 documents a fourth
measurement-affecting change (#1061) that landed 20 minutes after the last baseline
and moved the placement constraint model by 6,006 constraints. §6 isolates #1074
from it directly, by routing and DRC-ing the *same solve* written through the old
sparse filter: that experiment is the only thing in this document that attributes a
delta to the rotation fix specifically.

**The board is not landed and no ceiling paperwork was written.** This document
does not modify `power_pcb_dataset/drc_ceiling.json`, `pcb/temper.kicad_pcb`, or
anything else under `pcb/`.

## 0. A fourth measurement-affecting change the task did not list: #1061

`main` also carries **#1061** (`fix(netclass): reconcile 5 kicad_pro<->design_rules.py
param mismatches`, commit `4c9cbda14`, landed 2026-08-12 13:49) -- **20 minutes after
the last true baseline's placement solve ran (13:29)**. It changes
`packages/temper-placer/configs/netclass_rules.yaml`: `HighVoltage.clearance` 6.0 ->
2.0 and `Power.clearance` 0.25 -> 0.5 (plus trace_width/via_diameter/via_drill).

That moves the placement constraint model, measurably:

| | prior recipe (every doc through the 2,514 baseline) | this measurement |
|---|---:|---:|
| netclass SEPARATED constraints | 9,647 | **9,647** (unchanged) |
| courtyard-tau backfill | 12,301 | **6,295** |
| base total | 21,948 | **15,942** |
| barrier constraints | 170 | **170** (unchanged) |
| **total** | **22,118** | **16,112** |

Mechanism, not guesswork: the backfill skips any pair already carrying a netclass
constraint of at least `tau_mm` (= `courtyard_clearance_mm(default_clearance=0.2)` =
**0.4mm**). `Power.clearance` moving 0.25 -> 0.5 crosses that threshold, so every
Power-class pair that previously received *both* a 0.25mm netclass constraint and a
redundant 0.4mm backfill now receives only the 0.5mm netclass constraint. The model
is marginally **stronger** (those pairs go 0.4 -> 0.5mm) and 6,006 constraints
smaller. Nothing about this is a defect; it is stated here because any future
attempt to reproduce "21,948" against current `main` will fail, and would otherwise
look like the unpinned-engine class of bug all over again.

## 1. Engine pin, then two independent runs

`scripts/verify_pumpkin_engine.py` -> **exit 0**, VERIFIED, before every solve:

```
pumpkin_engine identity gate: VERIFIED -- pumpkin_engine
sha256=7ff153f478f8022f8f8659a514ab7067220812ef82b002fd17955fe0f2083b5e
source_commit=5bbf650d47d3a07fffd10a44e7c06c43a0a800bd
path=/home/bennet/Desktop/temper/target-shared/release/pumpkin_engine
```

Full recipe (reconcile -> Pumpkin placement with the PD2/8.0mm horizontal isolation
barrier, U6 relaxed -> `route_board.py --net-batching`), run twice from separate
process launches into separate scratch directories:

| stage | run A sha256 | run B sha256 | agree? |
|---|---|---|---|
| netlist (`make netlist`) | digest `8cfd715e60a3…` | same input | — |
| reconciled board | `f727fb1e4162…` | `f727fb1e4162…` | **byte-identical** |
| placed board | `2e64d507e201…` | `2e64d507e201…` | **byte-identical** |
| routed board | `e4a8e102e917…` | `e4a8e102e917…` | **byte-identical** |

`f727fb1e4162…` also matches the reconciled-board sha every prior doc in this
lineage recorded, so reconciliation is unchanged by anything that landed since.

Placement solved to `status=optimal` in 1.15s (run A) / 1.21s (run B) against a 30s
budget -- not a timeout truncation. Domain partition and per-isolator feasibility
reproduced the recipe **exactly**: `hv_only=40 selv_only=109 isolators=8
unclassified=11`, isolators `{C6,K1,K2,K3,PS1,T1,T2,U6}`, corridor `[113.0, 121.0]`
mm, and the eight `achievable_gap_mm`/`chosen_rotation` rows byte-identical to the
recipe (C6 8.000/3, K1 8.000/2, K2 12.760/1, K3 12.760/1, PS1 35.500/3, T1 9.100/0,
T2 9.100/0, U6 8.100/1). Routing reported `12 batch(es), 12 solved at batch level, 0
crashed (0 hit the subprocess wall-clock timeout)` in both runs.

**The two boards agree on every metric asked for.** Nothing is left unpinned.

## 2. The new true baseline

| metric | committed `pcb/temper.kicad_pcb` | **new candidate** | prior "true" baseline (VOID -- see §3) |
|---|---:|---:|---:|
| footprints | 169 | **168** | 168 |
| segments | 2,290 | **3,528** | 2,514 |
| vias | 48 | **36** | 22 |
| zones | 96 | **84** | 76 |
| nets routed (Stage-4 A\*) | — | **73 / 105 (69.5%)** | 63 / 105 (60.0%) |
| nets fully pad-connected (router's primary metric) | — | **49 / 139** | 48 / 139 |
| **nets fully connected (KiCad `unconnected_items`)** | **0 / 110 (0.0%)** | **23 / 112 (20.5%)** | 22 / 112 (19.6%) |
| `unconnected_items` entries | 428 | **343** | 351 |
| `SAF_HVL_001` | 94 | **38** | 74 |

Counted directly off the files (`(footprint `/`(segment`/`(via`/`(zone` blocks) and
cross-checked against `route_board.py`'s own summary line, which agrees:
`Result: 73/105 nets (69.5%)  segments=3528 vias=36 zones=84  wall=413.5s` (run A) /
`wall=451.3s` (run B).

Connectivity used KiCad's own `unconnected_items` as ground truth, with the
110-official-net denominator pulled from
`parse_kicad_pcb(...).netlist.nets` -- the identical method
`docs/evidence/2026-08-11-pad-connectivity-ground-truth.md` established. That
method **reproduces its published baseline exactly on the committed board**
(0/110 fully connected, 428 entries), which is what licenses trusting the
candidate's 23/112.

`SAF_HVL_001` **94 -> 38 (-56, -59.6%)**, measured through the Rust safety kernel
with the same `_run_rust_drc`-shaped board_dict construction the prior measurements
used. Component net-class populations: committed `{HighVoltage: 50, Signal: 119}`
(169 comp.), candidate `{HighVoltage: 45, Signal: 123}` (168 comp.), so the
normalised per-pair rate falls from 94/5,950 = 1.58% to 38/5,535 = **0.69%** --
better than halved, not an artifact of one fewer component. Every violation is
still `SAF_HVL_001`; no new safety class appears. **This is a further improvement on
the prior candidate's 74.**

It is **not** caused by the rotation fix, and this was checked rather than assumed:
the §6 counterfactual board -- the identical solve written through the pre-#1074
sparse filter, 34 footprints at different angles -- measures **`SAF_HVL_001` = 38 as
well**, byte-for-byte the same count. So the 74 -> 38 improvement is attributable to
the changed placement (§0's #1061 constraint-model move), not to #1074. The rotation
fix contributes exactly zero here, despite `Component::edge_distance_to` reading
rotation: none of the 34 re-angled components sits on an HV/LV pair close enough to
the 10.0mm requirement for the angle to change the verdict.

## 3. `check_board_containment.py`: PASS

```
$ python3 scripts/check_board_containment.py --board .../runA/board_placed.kicad_pcb
outline (Edge.Cuts) bounds: (20.00, 20.00) - (172.00, 254.00) mm
checked: 168 footprints, 527 pads
Board containment: PASS -- all copper inside the board outline        [exit 0]

$ python3 scripts/check_board_containment.py --board .../runA/board_routed.kicad_pcb
checked: 168 footprints, 527 pads
Board containment: PASS -- all copper inside the board outline        [exit 0]
```

Both the placed and the routed board pass. The pre-#1074 candidate failed with a
full pad off the outline; this one does not.

### 3a. The write path was correct, and the rotation blast radius is 34/168

`_apply_placements_to_pcb(..., board_origin=board.origin)` was passed explicitly
(logged: `[place] board_origin=(20, 20)`). The round-trip oracle
(`check_placement_roundtrip`, positions adjusted back into file coordinates by
`board.origin`) is **PASS, 168/168 components, zero mismatches**, on both runs.

The placement driver reused here is the same scratch driver that produced the prior
"true" baseline -- and **it carried the #1074 defect itself**:

```python
rotations = {ref: idx * 90.0 for ref, idx in outcome.get("rotations", {}).items() if idx}
```

That is the exact `if idx` filter `CpSatPlacementResult.to_rotations_dict()` shipped
before #1074. It was replaced with the dense form that `_encoder_solve.py` now
carries. This is why the prior 2,514/22/76 figure is void as a post-#1074 reference
even though it was measured on the pinned engine: **the 2,514 board was written
through the rotation bug.**

Measured on this solve: **42 of 168** components solved to rotation index 0 (25.0%),
and the pre-#1074 filter would have dropped all 42. Writing the *identical* solved
placement through the old sparse dict and diffing the two boards:

- **34 of 168 footprints (20.2%) receive a different written angle** -- exactly the
  defect shape (solved rot 0, non-zero pre-solve board angle, non-square footprint):
  `C9 C13 C19 C22 C35 C36 C38 C41 J2 R2 R10 R20 R26 R27 R32 R36 R42 R46 R52 R61 R63
  R70 R72 R73 T1 U3 U4 U5 U10 U11 U12 U18 U20 U23`
- positions differ for only 4 (a consequence of the angle change, not a move)
- the dense write reproduces `runA/board_placed.kicad_pcb` byte-for-byte
  (`2e64d507e201…`), confirming the reconstruction is exact

Honest caveat, stated because it cuts against the convenient story: on **this**
solve the sparse board also passes containment (0 violations). #1074's own
measurement found 4 and 2 containment violations on two other solves with 30 and 36
mismatched components. So a containment failure is a *stochastic* consequence of the
34 stale angles, not a deterministic one -- the pads-outside-outline symptom depends
on which components land near the edge. The 34 wrong angles are present either way,
and it is those, not the containment verdict, that drive the DRC deltas §6
attributes.

## 4. Component delta by Sheetpath identity

```
=== BY SHEETPATH IDENTITY (authoritative) ===
  kept    : 162        added   : 6        removed : 7
  designator renames among kept: 93
  added:   rtd_pan.j_rtd1 J1 | safety.ocp2.c_filter C37 | safety.ocp2.comp U19
           safety.ocp2.ct T2 | safety.ocp2.r_burden R65 | safety.tp_ocp2_fault TP3
  removed: power_in.d_zcd_clamp D2 | power_in.r_zcd_bot R8 | power_in.r_zcd_opto R9
           power_in.r_zcd_pullup R10 | power_in.r_zcd_top1 R6 | power_in.r_zcd_top2 R7
           power_in.zcd_opto U3
=== BY RAW Reference STRING (misleading -- shown for contrast) ===
  old_refs - new_refs = ['D5','R76','R77','R78','R79']  (5)
  new_refs - old_refs = ['C41','J2','T2','TP4']         (4)
```

**7 removed / 6 added / 162 kept / 0 moved**, three-way agreement (independent
derivation from the two boards' own embedded `Sheetpath` properties, the resync
report's self-report, and the recipe's documented delta). The raw-`Reference`
set-diff reproduces the documented misleading 5/4 exactly, caused by 93 designator
renames among kept components. Round-trip oracle: **PASS 168/168**.

## 5. The full R27 ceiling campaign

Protocol, per `AGENTS.md` § "Board Change -> DRC Ceiling Re-measurement":
`temper_placer.validation._drc_api`'s own `--all-track-errors` +
single-thread-`KICAD_CONFIG_HOME` invocation and its `_parse_drc_json` parser,
against a board with a resolvable KiCad project, after regenerating the `.kicad_dru`
from `scripts/generate_kicad_dru.py` (the SSOT). **130 samples** -- the contract
requires >=120 whenever **any** category is declared nondeterministic, and `creepage`
is, regardless of `clearance` being byte-stable.

Two protocol details worth stating because both would have silently corrupted the
result:

*   **The DRU and the project sidecars go next to the SCRATCH board, not into
    `pcb/`.** Prior docs in this lineage copied the candidate over
    `pcb/temper.kicad_pcb` (or wrote `pcb/temper.kicad_dru`) to get project
    context. This task instead copies `temper.kicad_pro`, the freshly generated
    `temper.kicad_dru`, `fp-lib-table`, `sym-lib-table` and a symlink to `libs/`
    beside the scratch board. `pcb/` is never written.
*   **`fp-lib-table` + `libs/` are load-bearing for the WARNING numbers.**
    `pcb/fp-lib-table` names project-local libraries via `${KIPRJMOD}`, resolved
    against the *scratch* directory. Without them every footprint fails to load:
    measured `lib_footprint_issues` **169** (one per footprint) and
    `lib_footprint_mismatch` **0**, total warnings 624 instead of 489. Errors are
    unaffected. A campaign run that way would have reported a fictitious
    warning-ceiling delta.

**Control first.** 15 samples of the *committed* board through this exact scratch
harness, before trusting anything about the candidate:

| | recorded ceiling / `violations_by_type` | this harness, 15 samples |
|---|---|---|
| every ERROR category | 4/386/10/11/186(182-184)/4/105/3/199/154/199/1/4 | **byte-identical**, `creepage` 182-184 |
| every WARNING category | 11/23/5/1/1/172/199/45/32 | **byte-identical** |
| total warnings | 489 (= `warning_ceiling`) | **489/489** |
| total errors | 1262-1264 (ceiling 1266) | **1262-1264** |

The harness reproduces the committed record exactly. That is what licenses reading
the candidate's numbers as a real delta rather than an environment difference.

### 5a. The full per-category table

Candidate board sha256 `e4a8e102e917902e6a27f92637d0e2471fe9b35b57e0572349cb50560c62bc4e`
(the byte-identical output of both runs), 130 samples, 0 timeout retries.
"OLD candidate" is the pre-#1074 130-sample record measured earlier the same day
(`clearance` 499, `creepage` 114-116, `shorting_items` 110, totals 1075-1077) --
the run whose raise list the task quotes.


### ERROR-severity
| category | ceiling (committed board) | OLD candidate (pre-#1074) | NEW candidate (post-#1074) | old raise | new raise | verdict |
|---|---:|---:|---:|---:|---:|---|
| `annular_width` | 4 | 8 | 2 | +4 | -2 | raise GONE |
| `clearance` | 386 | 499 | 499 | +113 | +113 | raise SURVIVES (same) |
| `copper_edge_clearance` | 10 | 15 | 12 | +5 | +2 | raise SURVIVES (smaller) |
| `courtyards_overlap` | 11 | 31 | 17 | +20 | +6 | raise SURVIVES (smaller) |
| `creepage` | 186 | 114-116 | 117-119 | -70 | -67 | no raise |
| `drill_out_of_range` | 4 | 8 | 2 | +4 | -2 | raise GONE |
| `hole_clearance` | 105 | 37 | 57 | -68 | -48 | no raise |
| `hole_to_hole` | 3 | 1 | 0 | -2 | -3 | no raise |
| `shorting_items` | 199 | 110 | 93 | -89 | -106 | no raise |
| `solder_mask_bridge` | 154 | 45 | 53 | -109 | -101 | no raise |
| `track_width` | 199 | 199 | 199 | +0 | +0 | no raise |
| `tracks_crossing` | 1 | 0 | 0 | -1 | -1 | no raise |
| `via_diameter` | 4 | 8 | 2 | +4 | -2 | raise GONE |

### WARNING-severity
| category | ceiling (committed board) | OLD candidate (pre-#1074) | NEW candidate (post-#1074) | old raise | new raise | verdict |
|---|---:|---:|---:|---:|---:|---|
| `holes_co_located` [no ceiling entry -> implicit 0] | 0 | 2 | 14 | +2 | +14 | raise SURVIVES (larger) |
| `lib_footprint_issues` | 11 | 13 | 13 | +2 | +2 | raise SURVIVES (same) |
| `lib_footprint_mismatch` | 23 | 25 | 25 | +2 | +2 | raise SURVIVES (same) |
| `missing_courtyard` | 5 | 5 | 5 | +0 | +0 | no raise |
| `pth_inside_courtyard` | 1 | 6 | 6 | +5 | +5 | raise SURVIVES (same) |
| `silk_edge_clearance` | 1 | 199 | 199 | +198 | +198 | raise SURVIVES (same) |
| `silk_over_copper` | 172 | 173 | 199 | +1 | +27 | raise SURVIVES (larger) |
| `silk_overlap` | 199 | 199 | 199 | +0 | +0 | no raise |
| `track_dangling` | 45 | 28 | 32 | -17 | -13 | no raise |
| `via_dangling` | 32 | 5 | 3 | -27 | -29 | no raise |

| aggregate | ceiling | OLD candidate | NEW candidate | old raise | new raise |
|---|---:|---:|---:|---:|---:|
| error_ceiling | 1266 | 1075-1077 | 1053-1055 | -189 | -211 |
| warning_ceiling | 489 | 655-655 | 695-695 | +166 | +206 |

### noise-headroom check on the NEW candidate (ceiling - max >= max - min)
  creepage: observed 117-119 spread=2 -> a ceiling would need >= 121 (max + spread), NOT max+1

### 5b. Noise, and what a ceiling would have to be

Exactly one category is nondeterministic on this board: **`creepage`, 117-119,
spread 2** (distribution `{117: 17, 118: 60, 119: 53}` over 130 samples) -- the same
3-value band width every prior record shows. `clearance` is **byte-stable at
499/499 across all 130 samples**, as it was on the pre-#1074 candidate and as it is
on the committed board (386/386). Every other category has spread 0.

Recorded here only so nobody has to re-derive it later, **not** as a proposed
ceiling: by `DrcRatchet.check_noise_headroom`'s invariant
(`ceiling - max(observed) >= max(observed) - min(observed)`), a `creepage` entry for
this board would need **>= 121** (`max 119 + spread 2`), *not* `max + 1` = 120.
`max + 1` is exactly the bug six consecutive records carried. No ceiling entry is
written by this PR.

### 5c. Two categories in the table are not board properties

*   `lib_footprint_issues` +2 / `lib_footprint_mismatch` +2 are the *same* +2 on
    both candidates and trace to the 6 added / 7 removed footprints, not to
    geometry. The recorded ceiling's own provenance already flags this family as
    environment-sensitive on this machine.
*   `silk_edge_clearance`, `silk_over_copper`, `silk_overlap`, `track_width` and
    (on the committed board) `shorting_items` all sit at **exactly 199**. Five
    unrelated rules landing on the same integer is a reporting artifact, not a
    coincidence -- but it is *not* a global cap, since `clearance` reaches 499 and
    `creepage` 186 in the same reports. The consequence for this document is
    narrow and stated rather than hand-waved: **a category reading 199 is a lower
    bound**, so `silk_edge_clearance` +198 and `silk_over_copper` +27 are floors on
    those raises, and a "no change" between two boards that both read 199 is not
    evidence of no change. Root-causing KiCad's per-rule reporting behaviour is out
    of scope here and is not needed for any conclusion below.

## 6. Isolating #1074 from #1061: the counterfactual route

Everything in §5 compares two boards that differ by **two** changes -- the rotation
write-back fix *and* #1061's constraint-model change. To attribute a delta to the
rotation fix specifically, the identical solved placement (same
`placement_outcome.json`, same positions, same rotation indices, same constraint
model, same pinned engine) was written **twice** -- once through the dense
post-#1074 dict, once through the pre-#1074 `if idx` filter -- then both were routed
with the same `route_board.py --net-batching` and DRC'd through the same harness.
**The only difference between these two boards is the write-back filter.**

| | pre-#1074 write (sparse) | post-#1074 write (dense) | Δ attributable to #1074 |
|---|---:|---:|---:|
| footprints with a different written angle | \- | \- | **34 / 168 (20.2%)** |
| segments / vias / zones | 3,542 / 48 / 84 | 3,528 / 36 / 84 | −14 / **−12** / 0 |
| nets routed | 74 / 105 | 73 / 105 | −1 |
| `check_board_containment.py` | PASS | PASS | — |
| **`copper_edge_clearance`** | **25** | **12** | **−13** |
| **`courtyards_overlap`** | **25** | **17** | **−8** |
| `annular_width` | 4 | 2 | −2 |
| `drill_out_of_range` | 4 | 2 | −2 |
| `via_diameter` | 4 | 2 | −2 |
| `holes_co_located` (warn) | 18 | 14 | −4 |
| `pth_inside_courtyard` (warn) | 8 | 6 | −2 |
| `via_dangling` (warn) | 4 | 3 | −1 |
| `SAF_HVL_001` (Rust safety kernel) | 38 | 38 | **0** |
| **`clearance`** | **499** | **499** | **0** |
| **`silk_edge_clearance`** (warn) | **199** | **199** | **0** |
| `silk_over_copper` / `silk_overlap` / `track_width` (warn/err) | 199 / 199 / 199 | 199 / 199 / 199 | 0 (all at the 199 floor) |
| `creepage` | 118-120 | 117-119 | −1 |
| `hole_clearance` | 49 | **57** | **+8** |
| `solder_mask_bridge` | 44 | **53** | **+9** |
| `shorting_items` | 86 | **93** | **+7** |
| `track_dangling` (warn) | 28 | **32** | **+4** |
| total errors | 1057-1059 | 1053-1055 | −4 |
| total warnings | 698 | 695 | −3 |

(20 samples for the sparse board -- enough to characterise the one nondeterministic
category, whose spread is 2, and every other category has spread 0 in both records.
This is an attribution probe, not a ceiling measurement, and is labelled as such.)

**Read this table carefully, because it is the answer to the question actually
asked.** The rotation fix is real and it is *large* for exactly two of the three
predicted categories -- `copper_edge_clearance` halves (25 -> 12) and
`courtyards_overlap` drops a third (25 -> 17). It is **exactly zero** for
`silk_edge_clearance`, the biggest raise on the board. It is zero for `clearance`,
the biggest *error* raise. And it makes three categories measurably **worse**
(`hole_clearance` +8, `solder_mask_bridge` +9, `shorting_items` +7) -- 34 components
turning to their solved orientation is not a monotone improvement, it is a different
board.

## 7. Which raises are real, and which were rotation artifacts

| raise | surviving size | rotation-attributable share (§6) | assessment |
|---|---:|---:|---|
| `clearance` +113 | +113 | **0 of 113** | **REAL.** 499 byte-identical on all three boards (old candidate, sparse, dense) and across 130+130+20 samples. Nothing about the rotation fix touches it. This is the one raise that has never moved and needs a real explanation, not a re-measurement. |
| `courtyards_overlap` +6 | +6 | −8 of the −14 total move | **REAL residual, artifact-inflated.** The rotation fix accounts for more than half the improvement; the remaining +6 is genuine courtyard overlap on the new placement. |
| `copper_edge_clearance` +2 | +2 | −13 | **REAL residual, heavily artifact-inflated.** Without #1074 this category would read 25 (+15, *worse* than the pre-#1074 candidate's +5). The fix is the only reason it is +2. |
| `silk_edge_clearance` +198 (>=) | +198 | **0** | **REAL, and unchanged.** The hypothesis is wrong here. Saturated at 199 on both writes, so the fix provably contributes nothing. Largest single raise on the board. |
| `annular_width` / `drill_out_of_range` / `via_diameter` +4 each | **none** | −2 each (of −6 each) | **GONE**, but only one third of that is #1074 -- the other 8 -> 4 happened between the two candidates for other reasons. The task expected these to be real; they are not raises any more. |
| `pth_inside_courtyard` +5 (warn) | +5 | −2 | **REAL.** |
| `lib_footprint_issues` / `_mismatch` +2 (warn) | +2 / +2 | 0 | **Not geometry** -- footprint-population delta / environment (§5c). |
| `silk_over_copper` +27 (>=, warn) | +27 | 0 | **REAL and worse** than the pre-#1074 candidate's +1. At the 199 floor, so +27 is a lower bound. |
| `holes_co_located` +14 (warn, new class, implicit ceiling 0) | +14 | −4 | **REAL, still a new violation class, and 7x worse** than the pre-#1074 candidate's 2. The rotation fix trims it (18 -> 14) but does not create or remove it. |
| aggregate **warning** ceiling +206 | +206 | −3 | **REAL and worse** than the pre-#1074 candidate's +166. |
| aggregate **error** ceiling | none (1053-1055 vs 1266) | −4 | No raise, and 211 below the ceiling. |

**Direct answer to the question.** The list shrinks on the error side (8 raises ->
3) but **not** for the reason hypothesised, and it grows on the warning side. Of the
three categories predicted to be rotation-driven, two really were -- substantially
-- and the third, `silk_edge_clearance`, provably was not: it is byte-identical
across the two write paths. Meanwhile the three categories the task expected to be
real (`annular_width`/`drill_out_of_range`/`via_diameter`) are the ones that
disappeared. **These are, in the main, real geometric problems rather than
write-back artifacts** -- `clearance` +113 and `silk_edge_clearance` +198 together
account for the overwhelming majority of the raise magnitude, and #1074 moves
neither by a single count.

## 8. What was NOT done, deliberately

*   **`pcb/temper.kicad_pcb` is not modified.** The candidate board is not landed.
*   **`power_pcb_dataset/drc_ceiling.json` is not modified.** No ceiling entry, no
    `_march` entry, no `Ceiling-Approval:` trailer. Writing ceiling paperwork for a
    board that is not being landed is the #1049 failure mode, and §5b's headroom
    figure is recorded as an input to a future decision, not as a decision.
*   **`scripts/board_shape_baseline.json` is not modified.** The 2,514/22/76 entry
    it carries is now known to have been written through the #1074 defect (§3a) --
    that is a real finding, but correcting a shared baseline belongs with the PR
    that lands a board, not with a measurement PR that does not.
