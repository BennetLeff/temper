<!-- provenance: commit=23f4c8c3c37831cdc9addb96c911a67d88151b9a dirty=false -->
<!-- provenance: measured 2026-08-12, worktree /home/bennet/Desktop/temper-worktrees/land-candidate-board,
branch feat/land-candidate-board, base 66a277d94 (origin/main tip at task start). kicad-cli 10.0.5 at
/home/bennet/.local/opt/kicad-10.0.5 (LD_LIBRARY_PATH covering root/usr/lib*, KICAD_STOCK_DATA_HOME=
root/usr/share/kicad), the invocation docs/evidence/2026-08-11-pad-connectivity-ground-truth.md records.
PYTHONHASHSEED left UNSET throughout, matching the recipe doc's own primary determinism protocol.
All board regeneration under /tmp/.../scratchpad/run/, never under pcb/** (`git status --short pcb/`
empty at every checkpoint; the one write inside pcb/ -- pcb/temper.kicad_dru, needed to give scratch
DRC runs a resolvable ruleset -- is .gitignore'd and regenerated fresh, same convention as every prior
evidence doc in this lineage). Machine: 24 cores. -->

# The candidate board was NOT landed: the recipe's placement stage silently depends on an untracked `pumpkin_engine` binary, and no build of it reproduces the verified 3,349/56/70 baseline

**Verdict up front.** This PR does **not** change `pcb/temper.kicad_pcb`, and does
not touch `power_pcb_dataset/drc_ceiling.json`. The owner-authorised landing was
conditional on the produced board matching the verified baseline
(`docs/evidence/2026-08-12-board-recipe-reproducibility.md` §6:
**3,349 segments / 56 vias / 70 zones / 168 footprints / 80 of 105 nets**). It does
not, under either of the two `pumpkin_engine` builds that exist on this machine,
and the two builds disagree with **each other** as well. Per the task's own bar --
"if the board that comes out differs materially from the verified baseline, stop and
report rather than landing something plausible" -- the board is not landed.

The cause is identified, not guessed, and is proven by sha256 rather than inferred:
**the recipe's placement stage depends on a build artifact that no commit pins.**

## 1. What DID reproduce, exactly

Everything up to and including the placement *model* reproduces the recipe
bit-for-bit. This is worth stating plainly, because it localises the failure
precisely rather than leaving "the recipe didn't reproduce" as a vague claim.

**Netlist** — `make netlist` digest `8cfd715e60a3…`, matching the recipe doc and
#1049's independently-reported digest.

**Reconciliation** (`scripts/resync_pcb_netlist.py`) — byte-identical across three
independent runs (`sha256 f727fb1e4162…`), and every published figure matches:

```
netlist_components: 168   old_board_footprints: 169   new_board_footprints: 168
kept_count: 162  added_count: 6  removed_count: 7  moved_count: 0
added:   [C37, J1, R65, T2, TP3, U19]
removed: [D2, R6, R7, R8, R9, R10, U3]
designator_changes: 93
```

**Component delta by `Sheetpath` identity** — re-derived independently from the two
board files' own embedded `Sheetpath` properties, *not* taken from the resync's
self-report, then cross-checked against it: **162 kept / 6 added / 7 removed /
0 moved**, three-way agreement (independent derivation, resync report, recipe
doc). The misleading raw-`Reference` set-diff reproduces §1a of
`2026-08-12-place-and-reroute-connectivity.md` verbatim, including its exact sets:
`old−new = {D5, R76, R77, R78, R79}` (5), `new−old = {C41, J2, T2, TP4}` (4).

**Placement constraint model** — every published number matches exactly:

| quantity | recipe | measured here |
|---|---:|---:|
| netclass SEPARATED constraints | 9,647 | **9,647** |
| courtyard-tau backfill | 12,301 | **12,301** |
| base total | 21,948 | **21,948** |
| barrier constraints | 170 | **170** |
| **total** | **22,118** | **22,118** |
| partition hv_only / selv_only / isolators / unclassified | 40 / 109 / 8 / 11 | **40 / 109 / 8 / 11** |
| isolator set | C6,K1,K2,K3,PS1,T1,T2,U6 | **identical** |
| corridor (horizontal, PD2/8.0mm) | [113.0, 121.0] mm | **[113.0, 121.0] mm** |

The per-isolator feasibility table reproduces to the last digit (C6 8.000/rot3,
K1 8.000/rot2, K2 12.760/rot1, K3 12.760/rot1, PS1 35.500/rot3, T1 9.100/rot0,
T2 9.100/rot0, U6 8.100/rot1), and so does the **joint-infeasibility finding**:
all 8 isolators hard-constrained → `infeasible` in **3.1s** (recipe: 3.17s);
relaxing U6 alone → `optimal`. That agreement is what establishes the barrier was
re-expressed into the Pumpkin wire format faithfully — the barrier had to be
re-encoded by hand as `"bounded"`/`"fixed_rotation"` constraints, because
`isolation_barrier.add_isolation_barrier_to_model` is OR-Tools `CpModel`-coupled
and cannot drive the standalone binary.

**The isolation-barrier step was executed, not omitted** (the failure mode the task
flagged from a prior agent): 170 barrier constraints are present, and the U6
infeasibility proof above cannot be produced without them.

**Determinism of each stage, independently confirmed on this machine:**

- reconciliation: byte-identical ×3
- placement: **byte-identical across two independent process launches** (per binary)
- routing: **byte-identical across two independent process launches**
  (`sha256 850833906a9d…` both times, 86/105 nets, 4140/70/66 both times)

So the pipeline **is** deterministic, exactly as the recipe claims. That is precisely
what makes the next section a real finding rather than noise.

## 2. What did NOT reproduce, and by how much

| | segments | vias | zones | footprints | nets routed |
|---|---:|---:|---:|---:|---:|
| **verified baseline** (recipe §6) | **3,349** | **56** | **70** | 168 | **80/105** |
| this task, engine built from **`main`'s committed source** | 4,140 | 70 | 66 | 168 | 86/105 |
| this task, engine from **`target-shared/`** (the default pickup) | 3,505 | 26 | 76 | 168 | 75/105 |
| #1050's original figure (does not reproduce, per recipe §5) | 4,228 | 74 | 66 | — | — |

`scripts/check_landed_board_shape.py` (added by this PR) refuses both:

```
GATE 2 -- agreement with the verified recipe baseline (3,349 / 56 / 70)
  metric        measured  baseline    delta   delta%   verdict
  segments          4140      3349     +791  +23.62%   FAIL
  vias                70        56      +14  +25.00%   FAIL
  zones               66        70       -4   -5.71%   FAIL
```

`vias` 26 (−53.6%) under the other build is further still. These are not
tolerance-band disagreements; they are different boards.

## 3. Root cause, proven by sha256

`test_golden_board_pumpkin_real_board.py::_find_pumpkin_binary` resolves the
placement solver to `target-shared/release/pumpkin_engine` — falling back to the
**main checkout's** copy when run from a worktree. That path is `.gitignore`d
(`.gitignore:136`). Nothing pins which source it was built from, and the recipe
doc records no hash for it.

On this machine that artifact (built 2026-08-12 10:11, `sha256 7ff153f478f8…`) is
**not** a build of `main`. It is byte-for-byte a build of the **unmerged, in-flight**
branch `origin/fix/pumpkin-to-units-and-netclass-skip`:

```
7ff153f478f8022f8f8659a514ab7067220812ef82b002fd17955fe0f2083b5e  target-shared/release/pumpkin_engine
7ff153f478f8022f8f8659a514ab7067220812ef82b002fd17955fe0f2083b5e  <build of origin/fix/pumpkin-to-units-and-netclass-skip>
57fe087ecf6cfd3c611e23c78c32c1cde5bf50c8dbda7bae78b7eb7fd283cd02  <build of origin/main>
```

Fed the **identical** 22,118-constraint payload, the two builds return different
placements — both `optimal`, different decisions:

```
target-shared        optimal  decision_sha=4a6f1652f6465c42
build of fix-branch  optimal  decision_sha=4a6f1652f6465c42   <- identical
build of main        optimal  decision_sha=d2354778cdee5aa9   <- different
```

That branch's head commit for this file, `6ba28447e` *("fix(pumpkin-engine):
to_units ceil-to-even, not floor-to-even")*, changes `to_units` — the exact
function that scales **every** `value_mm` in the barrier constraints this recipe
posts, and every component's `w0`/`h0`. Its own commit message scopes the change
to 6 of 338 board dimensions. Six dimensions are evidently enough to move the CP
solve to a different optimum, which then moves the entire downstream route.

**Chain:** untracked binary → different placement → different routing. Each link is
individually deterministic (§1), which is why this produced three *stable*,
mutually-inconsistent boards rather than obvious flakiness.

This is the same class of defect the recipe doc's §4 already caught once, in
miniature: **silent input drift** (there, a footprint library file; here, a build
artifact) masquerading as "the recipe doesn't reproduce". The recipe's §4 pinned
the footprint; nothing pinned the solver binary.

## 4. What this says about the 3,349/56/70 baseline

The baseline is **not reproducible from `main`'s committed source today**. It was
almost certainly measured against a third `pumpkin_engine` build — one predating
the 10:11 rebuild — that no longer exists on this machine and that no commit
identifies. The recipe's determinism claim is sound *given a fixed binary*, which
is exactly the qualifier its §2–4 protocol tested and its method section omitted.

Recorded plainly, per the same instruction the recipe doc followed for #1050's
4,228/74: **3,349/56/70 should not be treated as a target reproducible from `main`
until the engine binary is pinned.** This document does not claim the baseline was
wrong when measured — only that it is not re-derivable from committed state.

## 5. DRC on the candidate board (context only — NOT a ceiling re-measurement)

6 samples via `temper_placer.validation._drc_api.run_drc` (`--all-track-errors`,
single-thread `KICAD_CONFIG_HOME` pin), DRU regenerated from
`scripts/generate_kicad_dru.py` first, `.kicad_pro` **and** `.kicad_dru` both
resolvable alongside the board:

| category | ceiling (`drc_ceiling.json`) | candidate (main-source build) |
|---|---:|---:|
| `clearance` | 386 | **499** (499 in all 6, deterministic) |
| `creepage` | 186 | **84–85** |
| `shorting_items` | 199 | **68** |
| `track_width` | 199 | 199 |

`clearance` = 499 lands on the same figure the recipe (499–501) and #1050 (≈499)
report **despite** this board's copper differing from both by >20% — corroborating
`2026-08-12-clearance-regression-independent-spike.md`'s finding that `clearance`
is driven by one congested region, not board-wide copper density.

**These 6 samples are deliberately not enough to move a ceiling** (R27 requires ≥120
for nondeterministic categories) and are recorded as characterisation only. No
ceiling was raised, lowered, or touched, because no board was landed.

## 6. What a follow-up needs

1. **Pin the solver binary.** Either build `pumpkin_engine` into a
   commit-identified location as an explicit recipe step, or have
   `_find_pumpkin_binary` record and assert the binary's sha256 alongside the
   board numbers. Until then any two runs of this recipe are only comparable by
   luck. This is the single highest-value fix and is a prerequisite for landing.
2. Re-run the recipe with a pinned binary, and re-establish the baseline from
   **that** run rather than from `3,349/56/70`.
3. Only then re-attempt the landing, with the full ≥120-sample R27 re-measurement.

## 7. Known-adjacent, deliberately untouched

Per the task's explicit scope bar: **no netclass clearance value was changed.**
`origin/fix/pumpkin-to-units-and-netclass-skip` (#1054/#1056 lineage — the
in-flight encoder/netclass work) is reported here purely as the **measured
provenance of a build artifact**; nothing on that branch was merged, cherry-picked,
or otherwise pulled in. `pcb/temper.kicad_pcb` is byte-unchanged
(`6928b7c8950a…`).

The one board-adjacent change this PR does make is restoring
`pcb/libs/Connector_JST.pretty/` and its single `pcb/fp-lib-table` line, recovered
byte-unmodified from #1049 (`d76bb27ed`) — the prerequisite
`2026-08-12-place-and-reroute-connectivity.md` §7.3 records as owed. Without it
`resync_pcb_netlist.py` hard-fails on J1 (`rtd_pan.j_rtd1`) and the recipe cannot
run at all from a clean checkout. It is landed here so the next attempt does not
re-discover it.

## 8. Latent gap found in passing (reported, not fixed)

`isolation_barrier.classify_domain_partition` marshals pin nets to Rust as
`list[str]` and raises `TypeError: 'None' is not an instance of 'str'` on any board
carrying an un-netted pad. Both the committed board (5 such pads) and the
reconciled board (4, all on `K1`) do. No production caller currently feeds it real
board data, which is why this has never fired. Worked around **at this task's call
site only** (`None` → `""`, semantically identical — domain membership is
exact-name, so an un-netted pad is in neither domain); production code is
untouched. Worth a real fix when something does wire that path up.
