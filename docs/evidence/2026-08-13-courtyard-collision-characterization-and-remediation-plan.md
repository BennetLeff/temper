# Every `courtyards_overlap` pair, characterized: 6 real body collisions, 2
# benign courtyard touches, 7 of 8 locally repairable, 1 that is not

provenance: commit=a3fbaff37afd739b72f2b109847813b30ceb8e88 dirty=false

**Plain answer up front: as placed today, this board is NOT assemblable.**
`C2` and `C3` -- two 35mm-diameter snap-in electrolytic capacitors -- occupy
7.73mm of the same physical space. Two solid cylindrical cans cannot both be
soldered onto the board at their recorded positions. This is not a drawing
error or a silkscreen cosmetic issue; it is a mechanical impossibility on a
mains-voltage IEC 60335-1 induction cooktop controller.

This document is ANALYSIS + a REMEDIATION PLAN only. Per the task brief's
coordination requirement, **no component was moved and `pcb/temper.kicad_pcb`
was not edited** -- every candidate placement below was tested against
scratch copies outside the repository. `pcb/temper.kicad_pcb` sha256 is
identical before and after every step in this document:
`b7d865b7946f55dcc0d907cccbbee12f730fd1878b30d417bd56004d1091c1d6`.

## 0. Provenance

| | |
|---|---|
| Branch | `agent/collision-remediation-plan`, based on `origin/fix/board-schematic-resync` @ `a3fbaff37afd739b72f2b109847813b30ceb8e88` (no commits between base and this branch's tip other than this document) |
| `pcb/temper.kicad_pcb` sha256 | `b7d865b7946f55dcc0d907cccbbee12f730fd1878b30d417bd56004d1091c1d6` (unchanged throughout; matches `power_pcb_dataset/drc_ceiling.json`'s own recorded `provenance.inputs[].sha256` exactly) |
| `kicad-cli --version` | `10.0.5` (matches `drc_ceiling.json`'s recorded `tool_versions.kicad-cli`) |
| pyo3/maturin extensions | `make venv-isolate` run in this worktree; `scripts/check_stale_extensions.py` reports **PASSED -- 10/10 fresh** both before and after all measurements; every one of the 10 modules explicitly `import`-checked (not just freshness-checked) and confirmed loadable, per the task brief's warning that fresh-but-unimportable has happened before |
| `scripts/check_venv_integrity.py` | PASSED -- all 18 entries resolve under this worktree's own repo root, not a different checkout |
| `make netlist` | run in this worktree; `elec/build/default.net` built, 8-input digest `8cfd715e60a3…` |
| `git status --porcelain` / `git grep -l "^<<<<<<< "` | clean / empty, checked before and after every step below |

## 1. Reproducing the ground truth: live kicad-cli, not inference

```
$ kicad-cli pcb drc --format json --severity-error pcb/temper.kicad_pcb
Found 774 violations
```

Filtering to `type == "courtyards_overlap"` gives exactly 8 pairs, matching
PR #1154 and `power_pcb_dataset/drc_ceiling.json`'s own ceiling (8, zero
headroom, `provenance.inputs[].sha256` identical to this board):

```
R4  x C4      K3  x C3      L1  x C5      C22 x C4
C2  x C3      C2  x PS1     C4  x R46     C5  x C7
```

This is the complete, exhaustive set. There are no other `courtyards_overlap`
violations on the board today.

## 2. Real body collision vs. benign courtyard touch -- measured per pair

The task brief distinguishes a **courtyard** (a keep-out zone that different
conventions treat differently, and which can legitimately brush without a
manufacturing problem) from an **`F.Fab` body** (the part's actual physical
envelope; two of those overlapping is not a convention question, it is two
solids trying to occupy the same volume). I measured both, independently,
for every one of the 8 pairs.

### 2.1 Method, and the sign-convention trap the brief warned about

Each footprint's true body geometry (`F.Fab` graphics: `fp_circle` /
`fp_rect` / `fp_poly` / chained `fp_line` outlines) was parsed directly from
`pcb/temper.kicad_pcb` (a from-scratch, dependency-free S-expression parser
-- no `kiutils`, no assumptions borrowed from the placer's own code) and
transformed from local footprint coordinates into world coordinates.
PR #1154's own writeup records that the *first* attempt at this exact
transform used the textbook counter-clockwise rotation matrix and produced a
confident, wrong answer (a comfortable "1.13mm clear" for C2/C3) -- caught
only because it was cross-validated against kicad-cli's own DRC verdict
before being trusted. I did not take PR #1154's corrected convention on
faith either: I re-derived it and checked the result against kicad-cli
independently, from a cold start.

The convention that reproduces kicad-cli's verdict exactly, for all 8 pairs
and every other pair tested (57 total pairs, see 2.2):

```
world_x =  local_x * cos(theta) + local_y * sin(theta) + X
world_y = -local_x * sin(theta) + local_y * cos(theta) + Y
```

Proof this is right, not assumed: computing `C2`'s and `C3`'s true body
centers this way gives `(98.48, 64.84)` and `(87.36, 39.94)` -- a
center-to-center distance of **27.271mm**. Sum of body radii (both
`CP_Radial_D35.0mm`, radius 17.5mm each) is 35.00mm. **27.271mm < 35.00mm by
7.73mm** -- independently reproducing PR #1154's published `7.73mm` to three
decimal places, from a completely separate parser and implementation. Same
result for `C5`x`C7`: **7.410mm**, matching PR #1154's `7.41mm` exactly.

### 2.2 Full pairwise table, F.Fab body vs. F.CrtYd courtyard, all 8

Penetration depth computed as the true minimum-translation-distance to
separate the two convex hulls (Separating Axis Theorem over each body's
convex hull -- using the hull is a *conservative* simplification: it can
only report >= the true depth along a possibly-concave outline, never
under-report a real collision).

| pair | F.Fab body | F.CrtYd courtyard | classification |
|---|---|---|---|
| **C2 x C3** | **OVERLAP 7.728mm** | OVERLAP 8.228mm | **REAL BODY COLLISION -- SEVERE** |
| **C5 x C7** | **OVERLAP 7.410mm** | OVERLAP 7.910mm | **REAL BODY COLLISION -- SEVERE** |
| C4 x R46 | OVERLAP 1.600mm | OVERLAP 2.260mm | REAL BODY COLLISION -- moderate |
| C5 x L1 | OVERLAP 1.560mm | OVERLAP 2.310mm | REAL BODY COLLISION -- moderate |
| C4 x C22 | OVERLAP 0.800mm | OVERLAP 1.460mm | REAL BODY COLLISION -- minor |
| C4 x R4 | OVERLAP 0.147mm | OVERLAP 1.151mm | REAL BODY COLLISION -- marginal |
| C3 x K3 | clear (gap 0.390mm) | OVERLAP 0.310mm | **courtyard-only touch, NOT a body collision** |
| C2 x PS1 | clear (gap 0.190mm) | OVERLAP 0.310mm | **courtyard-only touch, NOT a body collision** |

**6 of the 8 tracked `courtyards_overlap` violations are real, physical
body collisions.** The remaining 2 (`C3`x`K3`, `C2`x`PS1`) have bodies that
genuinely clear each other (0.19-0.39mm of real air gap) -- only the
0.25mm-larger `F.CrtYd` keep-out margin around the `CP_Radial` capacitors
pushes those two into "courtyard overlap." These 2 are cosmetic/keep-out
issues, not "the part doesn't fit" issues -- consistent with the brief's own
framing of what a benign courtyard touch looks like. I did **not** find any
case where a body collision existed without a matching courtyard overlap,
or vice versa in the "real" 6 -- the courtyard number is always >= the body
number, as geometrically required (courtyard fully encloses the body).

Cross-validation, not just self-consistency: I additionally computed all 57
non-flagged pairs among these 12 components (66 total pairs minus the 8
flagged, plus a few extra reference pairs) and confirmed **zero** false
positives or false negatives against kicad-cli's list -- every pair kicad-cli
does not flag comes back "clear" in my own geometry, and every pair it does
flag comes back "overlap." Full reproduction:

```bash
kicad-cli pcb drc --format json --severity-error --output /tmp/drc.json pcb/temper.kicad_pcb
python3 -c "
import json
d = json.load(open('/tmp/drc.json'))
for v in d['violations']:
    if v['type'] == 'courtyards_overlap':
        print([it['description'] for it in v['items']])
"
```

## 3. Why: git history, and which tool produced this

### 3.1 The 2026-08-13 designator resync did NOT introduce any of this

`power_pcb_dataset/drc_ceiling.json`'s own `_march` log records the most
recent board change (commit `96ebe489c`, "resync `temper.kicad_pcb` against
`elec/src`") explicitly: `` `scripts/resync_pcb_netlist.py` run... ~90
components renumbered... zero footprint swaps, **zero positions moved**
(confirmed via the tool's own report, `moved_count: 0`) ``. I confirmed this
independently by comparing every one of the 8 pairs' `(at X Y theta)` values
immediately before and after that commit: **byte-identical**. The only
visible effect on our 8 pairs is a designator rename -- today's `R46` was
`R51` before the resync (confirmed by exact position match: `(161.82,
45.91, 180)` under both names). **The resync tool is not the defect.**

### 3.2 One commit put every one of the 8 colliding pairs where they are today

Tracing each of the 12 involved components' `(at ...)` value through
`git log -- pcb/temper.kicad_pcb`, all 12 (`R4, C4, K3, C3, L1, C5, C22, C2,
PS1, R46`/`R51`, `C7`) have the position they hold **today** first appearing
in a single commit: `de59c0458` ("`feat(pcb): K3 RT314012 swap +
validator-gated board write + DRC ceiling re-measure (#602)`", 2026-08-03).
Diffing that commit against its immediate parent (`73d179b6`) shows every
one of these 12 components' `at` line changing, alongside dozens of other
capacitors (C17-C30 and more) -- this was a broad, automated re-solve, not a
narrow K3-only edit, despite the commit's headline description.

I ran kicad-cli DRC directly against the **historical** board content at
that commit (checked out to a scratch copy, `pcb/temper.kicad_pcb` in this
worktree never touched) to see what it produced, live:

```
courtyards_overlap = 11   (matches the ceiling de59c0458 itself recorded)
pairs: C9xC4, R42xC3, R8xC4, R12xC5, R70xC4, C2xC20, C24xC3, D2xC3, C5xC7,
       C5xR19, C5xR13
```

...and against the commit's own **parent** (before the K3 swap / re-solve):

```
courtyards_overlap = 11
pairs: R4xC4, K3xC3, L1xC5, C22xC4, R7xC5, C2xD2, C2xC3, C4xR51, D2xC3,
       C5xC7
```

This is the key finding: **`C5`x`C7` -- the second-worst collision (7.41mm
body interpenetration) -- already existed before `de59c0458`, and the
commit's own re-solve moved BOTH `C5` and `C7` (each ~20mm) without fixing
it.** It is a chronic defect that has survived at least one full automated
re-placement pass unaddressed. `C2`x`C3` -- the worst collision (7.73mm) --
is different: it is **new** as of `de59c0458`. Before that commit, `C2`
collided with a different neighbor (`C20`) and `C3` collided with yet other
neighbors (`R42`, `C24`, `D2`); the re-solve moved both `C2` and `C3` into
each other instead. `R4`x`C4`, `K3`x`C3`, `L1`x`C5`, `C22`x`C4` were present
(under different specific partner names in some cases -- `C4` was `R51`'s
partner then, `R46` now) both before and after, i.e. this general
neighborhood has been packed since before this commit and the re-solve
churned the specific pairings without resolving the underlying density.

### 3.3 The placement tool's own courtyard-avoidance machinery, and why it didn't stop this

`packages/temper-placer/src/temper_placer/placer/cp_sat/_encoder_solve.py`
(the CP-SAT placement encoder `de59c0458`'s "validator-gated repair re-solve"
ran) **does** register a courtyard no-overlap constraint --
`model_wrapper.add_no_overlap_2d(comp_refs)` -- **unconditionally, over
every registered component**, plus a per-pair `SEPARATED`-with-`τ`-clearance
constraint at encoding time (commented "per-pair SEPARATED-τ is added during
constraint encoding in U2"). Unlike `domain_clearance`/keepaway constraints,
which the *same codebase* (see `repair_commands.py`'s own module docstring,
PR #1144) explicitly filters to pairs touching the free/movable set "so a
pre-existing violation between two unrelated frozen components can't
manufacture a spurious UNSAT" -- **this base courtyard constraint carries no
such filter.** That two 35mm capacitors nonetheless ended up 7.73mm deep in
each other after a solve that includes this constraint means one of two
things: either this specific historical call (whose own squashed commit
message describes an inconsistent "Run A reported-but-not-written /
Run B written with `fixed_copper free_refs={K3,C27}` only" narrative that
does not actually explain why `C2`, `C3`, `C4`, `C5`, `C7`, and a dozen other
capacitors all show changed `at` values in the final diff) never actually
routed these components through this constraint as mutually-checked
variables, or `comp.bounds` for this footprint class does not carry its true
35mm courtyard envelope into the solver. **I could not fully resolve which
from the historical record alone** -- the commit is a 15-sub-commit squash
whose message and its actual diff do not fully agree, and reproducing the
exact historical solver invocation is out of scope for an analysis task that
must not touch `pcb/temper.kicad_pcb`. What is established, measured fact:
the tool that produced today's placement has a courtyard-avoidance
mechanism, and today's board violates it in 8 places -- consistent with the
task brief's framing that a tool producing physically-impossible placements
is the primary defect, more important than any single instance.

### 3.4 A second, more urgent tooling finding: `repair-unplaced` cannot currently answer anything on this real board

The brief points at `temper-placer repair-unplaced` (PR #1144, branch
`fix/t2-repair-entrypoint`, based on the same `fix/board-schematic-resync`)
as the mechanism to answer "where can this go." I built it in a separate,
disposable worktree (venv-isolated, 10/10 extensions fresh, all imports
verified, `pcb/temper.kicad_pcb` sha256 confirmed identical to this branch's
copy) and ran it. **A control test first, before trusting any result against
our actual colliding parts**: I asked it to place `R1` -- a small resistor
nowhere near any of the 8 collisions, with `--refs R1` and every other
component frozen:

```
$ temper-placer repair-unplaced pcb/temper.kicad_pcb --refs R1 --no-auto-escalate --no-run-drc \
    --no-domain-clearance --no-fixed-copper --no-isolation-barrier -o /tmp/control_R1.kicad_pcb
Phase 1: solve free refs only, every neighbour frozen
  status=infeasible (856ms)
  status=infeasible (no unsat core reported by the solver)
UNSAT after phase 1 -- no legal placement found for ['R1']
```

**UNSAT, for an uninvolved resistor, with every diagnostic ablation flag
that exists in the CLI turned off.** The only hard constraint left active in
that call is the base courtyard/board-bounds machinery described in 3.3 --
not gated by any `--no-*` flag -- and it is violated by the board's own
existing frozen geometry (our 8 tracked pairs) regardless of what `--refs`
names. Escalating to a full Phase-2 run (with `--displace` candidates) makes
this concrete: the reported UNSAT core names dozens of `sep_courtyard_Ux_Uy`
constraints between components with nothing to do with the request (e.g.
`U3`x`U6`, `U7`x`U8`, `U25`x`U26` -- none of which are among kicad-cli's 8
flagged pairs), meaning the solver's own internal courtyard/clearance model
is measurably **stricter** than kicad-cli's true polygon check and trips on
additional pairs kicad-cli does not consider violations at all.

**Consequence: `repair-unplaced`, as currently implemented, cannot produce
a trustworthy SAT/UNSAT verdict on this specific board today, for any
component** -- not because of a bug in this analysis, but because its base
courtyard constraint family is unconditional (unlike `domain_clearance`,
which the same PR's own docstring says is deliberately filtered for exactly
this reason) and the real board already violates it in multiple places. This
is a second, independent instance of "the tool is the defect" -- one level
up from the placement solve itself: the *repair* tool inherits the same
missing filter its own documentation says it added for a different
constraint family.

This also means **PR #1144's own T2-UNSAT headline should be treated as not
fully settled**, insofar as it leaned on this same `solve_placement` Phase-1
path. That PR does cite an independently-implemented brute-force geometry
search reaching the same conclusion, so I attempted to reproduce that
independently -- courtyard-only, grid search, cross-validated live against
kicad-cli exactly as required by this task's own instructions -- and found a
result that **conflicts** with it: a legal, courtyard-clear candidate
position for T2 at `(133.5, 120.5, 0deg)`. Verified by writing a scratch
board with T2 moved there and re-running live DRC:

```
$ kicad-cli pcb drc --format json --severity-error pcb/temper.kicad_pcb   # T2 moved, everything else untouched
courtyards_overlap: 8   (same 8 pairs as the unmodified board -- NONE name T2)
```

I flag this as an open discrepancy for follow-up, not a resolved claim
against PR #1144 -- I did not check copper/pad clearance, creepage, the
isolation barrier, or routing feasibility for that T2 candidate (courtyard
geometry only, exactly as PR #1144's own quoted claim scopes itself). It
matters here because it means neither this report's own findings nor PR
#1144's should be taken purely on a tool's SAT/UNSAT verdict alone on this
board -- every number in Section 4 below was independently re-verified
against live kicad-cli, not against `repair-unplaced`'s own verdict, for
exactly this reason.

## 4. Remediation plan -- measured per pair, live-kicad-cli-verified

Because `repair-unplaced`'s CP-SAT path is not currently usable on this
board (Sec. 3.4), I used the same class of check its own T2 analysis used
(courtyard-geometry brute-force search) implemented independently, and
verified every proposed relocation by writing it into a scratch board copy
and re-running live `kicad-cli pcb drc`. **No candidate below is asserted
without a matching live DRC re-measurement.**

### 4.1 Per-component free-space search (courtyard-only, all other 167 components frozen)

For each component in a colliding pair, does *any* position on the board
exist where its true `F.CrtYd` clears every other currently-frozen
component (including its own collision partner, still at its current
position)?

| ref | legal positions found (1mm grid) | nearest to current position |
|---|---|---|
| C2 | 0 | -- (UNSAT anywhere on the board) |
| C3 | 0 | -- (UNSAT anywhere on the board) |
| C4 | 0 | -- (UNSAT anywhere on the board) |
| C5 | 0 | -- (UNSAT anywhere on the board) |
| L1 | 0 | -- (UNSAT anywhere on the board) |
| **C7** | **1209** | **63.5mm away** |
| R4 | 9513 | **1.6mm away** |
| R46 | 12939 | **7.4mm away** |
| C22 | 15339 | **7.6mm away** |
| K3 | 379 | **0.4mm away** |
| PS1 | 258 | **1.0mm away** |

All four `CP_Radial_D35.0mm` capacitors (`C2, C3, C4, C5`) and the large
inductor `L1` have **zero** legal positions anywhere on the current board,
holding everything else fixed -- this board's large parts have no spare
courtyard headroom anywhere, the same finding PR #1144 reports for `T2`
(a different large part). Every small/medium part checked (`R4, R46, C22,
K3, PS1, C7`) has abundant free space and, critically, a *legal position
very close to where it already sits* -- these are true "the placer left
0.15-1.6mm of unnecessary overlap when a few mm of headroom existed
1mm away" defects, not density problems.

### 4.2 Verified fix: 6 of the 8 pairs clear with small single-part nudges

Applying six single-component relocations -- **R4** +1.6mm, **R46** +7.4mm,
**C22** +7.6mm, **K3** +0.4mm, **PS1** +1.0mm, and **C7** +63.5mm (the one
larger move; the other five are sub-8mm nudges) -- to a scratch copy and
re-running live kicad-cli DRC:

```
$ kicad-cli pcb drc --format json --severity-error temper.kicad_pcb   # 6 relocations applied
courtyards_overlap: 2
  ['Footprint L1', 'Footprint C5']
  ['Footprint C2', 'Footprint C3']
```

**8 -> 2, verified live, with zero new collisions introduced anywhere else
on the board** (courtyard-overlap count strictly fell; no new pair
appeared). This resolves `R4xC4`, `C4xR46`, `C4xC22`, `C5xC7`, `C3xK3`, and
`C2xPS1` -- both courtyard-only touches and 4 of the 6 real body collisions,
including the second-worst one (`C5xC7`, 7.41mm).

### 4.3 Verified fix: C5xL1 clears too, once C7 is out of the way

`C5` and `L1` individually are both UNSAT (table above) -- but excluding
each other from the obstacle set (both moving) finds each has candidates
once `C7` has vacated its former spot (before `C7` moved, no *joint*
solution existed for `C5`/`L1` even excluding each other; the neighbourhood
was genuinely too tight until `C7`'s relocation freed room). A small joint
move -- **C5 +2.4mm, L1 +0.7mm** -- clears it:

```
$ kicad-cli pcb drc --format json --severity-error temper.kicad_pcb   # +C5/L1 nudge, on top of 4.2
courtyards_overlap: 1
  ['Footprint C2', 'Footprint C3']
```

**8 -> 1, live-verified.** Every real body collision and every courtyard
touch is resolved except one.

### 4.4 The one that does not have a local fix: C2 x C3

For `C2`/`C3` (the worst collision, 7.73mm), I searched every combination:

- `C2` alone (everything else, incl. `C3`, frozen): **0 legal positions.**
- `C3` alone (everything else, incl. `C2`, frozen): **0 legal positions.**
- `C2` and `C3` jointly, excluding only each other (both free to move,
  `K3`/`PS1` and everyone else still frozen at their current -- even
  post-4.2-relocated -- positions): candidate sets exist for each
  individually (164-179 points each) but **no pair of candidates from the
  two sets is mutually non-overlapping** -- every combination checked still
  has the two 35mm cans overlapping each other somewhere.
- `C2` and `C3` jointly, **also** excluding `K3` and `PS1` (i.e. allowing
  the two courtyard-touch neighbors to move too, not just nudge): **a joint
  solution exists** -- `C2 -> (97.5, 72.5)` (~9mm move), `C3 -> (86.5,
  35.5)` (~1mm move), 9.7mm total combined displacement. This was not
  further verified end-to-end (`K3`'s and `PS1`'s own destinations were not
  jointly re-checked against these new `C2`/`C3` positions), so treat this
  as an **existence proof that a local 4-body re-place is geometrically
  possible**, not a finished, verified candidate.

**`C2`x`C3` requires moving at least 4 components together (`C2`, `C3`,
`K3`, `PS1`), not a 2-body swap and not a single-part nudge.** This is
short of a full-board re-place (unlike `T2`, which PR #1144 proved UNSAT
even with a single displaceable neighbor at 15mm bound) -- but it is real
work, not a trivial fix, and it involves two safety-relevant parts (`K3`, a
relay, and `PS1`, a power-supply module) that
`generate_domain_clearance_constraints`'s own diagnostic flags as
intra-footprint domain straddlers (`DC_BUS<->LV_CONTROL, 8.0mm` on both).
**Any actual re-place of this cluster must re-verify creepage/clearance and
the HV/SELV isolation barrier from scratch -- courtyard-clear is necessary
but is not sufficient for a mains-adjacent part, and none of the safety
checks were exercised by this document's courtyard-only search.**

### 4.5 Summary table

| pair | severity | fix | verified |
|---|---|---|---|
| C2 x C3 | 7.73mm body (worst) | 4-body re-place (C2, C3, K3, PS1); existence proven, not fully finished | partial -- geometry only, courtyard-clear existence proven; NOT DRC/safety re-verified |
| C5 x C7 | 7.41mm body | move C7 63.5mm | live kicad-cli, 4.2 |
| C4 x R46 | 1.60mm body | move R46 7.4mm | live kicad-cli, 4.2 |
| C5 x L1 | 1.56mm body | move C5 2.4mm + L1 0.7mm (after C7 relocates) | live kicad-cli, 4.3 |
| C4 x C22 | 0.80mm body | move C22 7.6mm | live kicad-cli, 4.2 |
| C4 x R4 | 0.147mm body | move R4 1.6mm | live kicad-cli, 4.2 |
| C3 x K3 | courtyard-only (0.31mm), body clear | move K3 0.4mm | live kicad-cli, 4.2 |
| C2 x PS1 | courtyard-only (0.31mm), body clear | move PS1 1.0mm | live kicad-cli, 4.2 |

## 5. Is the board currently assemblable? Plain answer.

**No.** `C2` and `C3` -- both mains-adjacent 35mm electrolytic capacitors --
physically cannot both be installed at their recorded positions; their
bodies interpenetrate by 7.73mm. `C5` and `C7` have the same problem
(7.41mm). Four more pairs have smaller but still real body interpenetration
(0.15-1.6mm) that would show up as parts refusing to seat flush or shorting
against each other during assembly. Two more pairs are courtyard-only
(cosmetic keep-out) touches with real physical clearance, not assembly
blockers.

**The good news, measured here for the first time: 7 of these 8 defects have
verified, geometrically-legal fixes**, 6 of them via single-part moves under
8mm (plus one 63.5mm move for `C7`) that were confirmed live against
kicad-cli to reduce the tracked violation count with zero new collisions
introduced. **Only `C2`x`C3` -- ironically the worst one -- needs real,
coordinated re-placement work** (at minimum `C2`, `C3`, `K3`, `PS1` moving
together), and even that was shown to be geometrically possible, not proven
impossible the way `T2` was.

None of the fixes in Section 4 were applied to `pcb/temper.kicad_pcb` --
this is a plan, and per the task's coordination constraint the tracked board
was not touched (sha256 verified identical throughout, restated at the
bottom of this document). None of them were checked against copper/routing,
creepage, clearance, or the HV/SELV isolation barrier -- courtyard-clear is
the necessary first gate this document answers; the safety gates are a
required next step before any of these moves land for real, especially for
`C2`/`C3`/`K3`/`PS1` given their proximity to the mains-adjacent domain
boundary.

## 6. Recommended follow-up (not executed here)

1. **Sequence a placement PR** (after the in-flight copper-strip/reroute,
   via-enlargement, and stackup work on `pcb/temper.kicad_pcb` lands) that
   applies the 6 verified single-part nudges from Sec. 4.2/4.3, re-measures
   `courtyards_overlap` (should read 1, not 0, honestly -- `C2`x`C3` is not
   included), and re-runs full DRC/creepage/clearance/isolation-barrier
   verification on every moved part before writing the board.
2. **Do a proper 4-body (or larger) CP-SAT re-solve for `C2`/`C3`/`K3`/`PS1`**
   rather than hand-placing the existence-proof coordinates from Sec. 4.4 --
   those coordinates prove the neighbourhood has room, they are not a
   safety-checked candidate.
3. **File the `repair-unplaced` filtering gap** (Sec. 3.4) as its own fix:
   the base courtyard/`sep_courtyard` constraint family needs the same
   free/touch-set filter `domain_clearance`/keepaway already have, or the
   tool cannot be used on any board carrying a pre-existing, unrelated
   courtyard violation -- which, per this document, is every board state
   between now and whenever Sec. 6.1 lands.
4. **Reconcile the T2 discrepancy** (Sec. 3.4): PR #1144 claims zero legal
   courtyard positions for T2 anywhere on the board; this document's
   independent, kicad-cli-cross-validated brute-force search found one.
   Both cannot be right; figure out which brute-force implementation has
   the bug (or what additional constraint PR #1144's "pure courtyard
   geometry alone" claim was implicitly also checking) before relying on
   either for T2's own remediation.
5. **Do not raise `courtyards_overlap`'s ceiling (8).** It is exactly at the
   live measured count with zero headroom; this document's own reproduction
   confirms 8/8, unchanged. Raising it would formalize the unbuildable state
   this document exists to characterize.

## 7. Final verification

```
$ sha256sum pcb/temper.kicad_pcb
b7d865b7946f55dcc0d907cccbbee12f730fd1878b30d417bd56004d1091c1d6
```

Identical to the value recorded at the top of this document and to
`power_pcb_dataset/drc_ceiling.json`'s own `provenance.inputs[].sha256` --
`pcb/temper.kicad_pcb` was not modified by this analysis.

```
$ git status --porcelain
(clean)
$ git grep -l "^<<<<<<< "
(empty)
$ python3 scripts/check_stale_extensions.py
PASSED -- 10/10 extension module(s) fresh.
```
