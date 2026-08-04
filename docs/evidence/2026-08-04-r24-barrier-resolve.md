<!-- provenance: commit=f2b09d84673b3a18d8fabe454230f1b240148f3d dirty=true -->

# Moving `R24` so the mains↔SELV barrier becomes geometrically admissible

**Date:** 2026-08-04
**Board measured:** `pcb/temper.kicad_pcb` at `f2b09d846` (byte-identical through
`aece7c372`, the `origin/main` this branch is cut from — verified with
`git diff f2b09d846..origin/main -- pcb/ power_pcb_dataset/drc_ceiling.json
elec/domain_manifest.yaml scripts/check_isolation_keepout.py packages/temper-placer/`,
which touches only one router test file).
**`dirty=true`** above is literal: every "written board" number below was measured
against a working tree carrying this PR's own one-line board edit. The written
board's `sha256` is recorded in §4 so the numbers are pinned to exact bytes.

**Acting on:** PR #690,
`docs/evidence/2026-08-04-isolation-barrier-freeform-corridor.md` — which proved,
shape-independently, that the committed placement admits no conforming
`MAINS_SELV_ISOLATION_BARRIER`, and that **`R24` alone is why**.

**Scripts** (all `uv run --no-sync python …`):
`2026-08-04-r24-barrier-admissibility.py` (scores one board against #690's two
necessary conditions), `…-frontier.py` (the admissible-position search),
`…-resolve.py` (the scoped CP-SAT solves), `…-apply.py` (the board write).

---

## Verdict

**A conforming barrier becomes geometrically admissible.** `R24` moves from
(31.480, 21.240) to **(81.000, 21.500)**, rotation unchanged; nothing else moves;
DRC does not move in any category.

| | committed | written |
|---|---|---|
| #690 Test 1 (pairwise separability) | PASS (103 regions, 0 mixed) | PASS (103 regions, 0 mixed) |
| #690 Test 2 (HV connectivity) @0.40 mm | **SPLIT — `R24.1`,`R24.2` stranded** | **CONNECTED** |
| #690 Test 2 (HV connectivity) @0.25 mm | **SPLIT — `R24.1`,`R24.2` stranded** | **CONNECTED** |
| widest channel to the other 99 HV pads | **5.727 mm** (shortfall **2.273 mm**) | **≥ 8.000 mm — no shortfall** |
| REQ-SAFE-01 (`verify_iec60335_compliance`) | 0 inter / 0 intra | 0 inter / 0 intra |
| DRC total errors, N=11 | 1262 [1261–1263] | 1262 [1261–1263] |
| DRC total warnings, N=11 | 472 [472–472] | 472 [472–472] |

This is a **necessary** condition, not a sufficient one — #690's own UNVERIFIED
section applies unchanged: that a single connected polygon exists leaving exactly
two regions is *not* established here. And the barrier still cannot be added,
because of the re-route in §6.

The committed-board baseline reproduces #690 exactly (5.727 vs its 5.728 mm,
1283.74 vs its 1284 mm² pad copper, same 101/221 pad split, same two stranded
pads), which is what licenses reusing its method on candidates.

---

## 1. Why a plain re-solve returns `R24` unmoved

`R24` passes every *pairwise* bar on the committed board — #690 measured its
nearest neighbour at 8.510 mm — and fails only **connectivity**. The CP-SAT model
has no constraint expressing connectivity, so a min-displacement repair solve is
already at its optimum with `R24` where it is. Something has to *tell* the solver
where to go, which is why this is a two-stage search: geometry proposes, CP-SAT
disposes.

## 2. The admissible set, and the displacement frontier

`…-frontier.py` scans candidate `R24` origins, removing `R24`'s two pads from the
copper model and re-adding them at each candidate, keeping positions that clear
**both** bars:

- **Bar 1 — admissibility.** #690's Part-C HV reachability must read CONNECTED at
  **0.40 mm and 0.25 mm** (verdicts must agree, as #690 requires).
- **Bar 2 — clearance.** `R24` carries HV copper: ≥ **8.0 mm** from all non-HV
  copper (the REQ-SAFE-01 `DC_BUS`↔`LV_CONTROL` figure, and also what
  `generate_unclassified_hv_keepaway_constraints` holds unclassified copper to),
  and ≥ 0.5 mm from other HV copper.

Evaluating bar 1 with `R24`'s own copper **present** is load-bearing. `R24`'s pads
are what close the 5.727 mm channel they sit in; a map computed with `R24` removed
reports its current position as admissible and is answering a different question.
This cost a wrong first answer here before it was caught.

**Bar 2 is not a refinement — it moves the frontier by 11.5 mm:**

| bars enforced | nearest admissible position | Manhattan |
|---|---|---|
| bar 1 only | (57.00, 21.50) | **25.78 mm** — but measures REQ-SAFE-01 `R24`↔`C36` creepage **7.71 mm < 8.0 mm** |
| bar 1 + bar 2 | (55.50, 34.50) | **37.28 mm** |

A second apparent basin at ≈(31.5, 48.0) — "straight down the left edge" — is a
**0.40 mm rasterisation artifact**: it reads CONNECTED at 0.40 mm and SPLIT at
0.25 mm. The dual-resolution requirement is what rejected it, and it is recorded
here because a single-resolution search would have shipped it.

## 3. The scoped CP-SAT re-solve — reported, not written

Run through `de59c0458`'s Run-B recipe (`solve_placement`, `fixed_copper`
`free_refs={R24}` margin 0.05, fixed rotations, min-displacement,
`max_displacement_mm=60`, seed 0, 180 s, full 11,571 domain-clearance + 530
keepaway), with `R24`'s displacement reference retargeted.

| run | status | terminated | refs moved | total displacement | `R24` → (abs) |
|---|---|---|---|---|---|
| `control-no-retarget` (recipe **verbatim**) | feasible | **timeout** | **167** | **7,068.8 mm** | (87.34, 21.24) |
| `candidate-1` target (57.50, 38.50) | feasible | **timeout** | 169 | 7,544.2 mm | (57.50, 38.50) |
| `candidate-2` target (81.00, 21.50) | feasible | **timeout** | 167 | 5,405.2 mm | (80.94, 48.93) |

`validator_audit` was clean for all three (`hard=0, intra=0, gaps=0,
covered_pair_count=11,571, geometry_trusted=True`).

**Determinism:** all three hit `max_time_in_seconds`. Per
`docs/evidence/2026-08-01-ortools-cpsat-spike.md`, CP-SAT is bit-identical only
for solves terminating *before* the timeout, so **all three are labelled NOT
reproducible across machines**. None is written.

**The control is the finding.** Asked to change as little as possible, the recipe
still moves 167 refs by 7.07 m. The churn is therefore intrinsic to the recipe on
today's board, not an artifact of retargeting `R24`. The cause is separable and was
measured: **the committed placement is not a feasible point of the encoder's own
base model** — pinning every ref at its current position via `fixed_positions`
with *no* extra constraints is reported `infeasible` (2.9 s). So CP-SAT must move
things, and 180 s does not converge a displacement objective over 169 components
and 12,101 constraints. `de59c0458` measured this exact failure mode for its Run A:
166 refs moved and the written board regressed to 1428–1437 total errors against a
1356 ceiling.

Writing any of these would be that regression again. The board write therefore
takes the single-component frontier candidate, and CP-SAT's role is confined to
confirming — via `validator_audit` — that the constraint set has no objection.

## 4. The two candidates, measured

Both move **only `R24`**, rotation unchanged, verified by re-parsing the written
board and asserting `R24` is the sole ref whose position changed.

| | **candidate 1** | **candidate 2 — RECOMMENDED** |
|---|---|---|
| `R24` → (absolute mm) | (57.500, 38.500) | **(81.000, 21.500)** |
| displacement (Manhattan / Euclid) | 43.28 / 31.22 mm | 49.78 / 49.52 mm |
| total displacement, all refs | **43.28 mm** | **49.78 mm** |
| per-component displacement | `R24` 43.28 mm; all others 0 | `R24` 49.78 mm; all others 0 |
| gap to nearest non-HV copper | 9.275 mm | **11.830 mm** |
| gap to nearest HV copper | 1.699 mm | 11.465 mm |
| **barrier admissible?** | **yes** (Test 1 PASS; Test 2 CONNECTED @0.40 and @0.25) | **yes** (Test 1 PASS; Test 2 CONNECTED @0.40 and @0.25) |
| REQ-SAFE-01 | 0 inter / 0 intra | 0 inter / 0 intra |
| DRC total errors (N=11) | 1265 [1265–1266] | **1262 [1261–1263]** |
| DRC total warnings (N=11) | 473 [473–473] | **472 [472–472]** |
| `courtyards_overlap` (ceiling 11) | **12 — RAISE** | 11 |
| `silk_over_copper` (ceiling 172) | **173 — RAISE** | 172 |
| warning total (ceiling 472) | **473 — RAISE** | 472 |
| `clearance` (ceiling 379) | 379 [378–379] — at ceiling | 378 [377–378] |
| `creepage` (ceiling 188) | 187 [187–188] — at ceiling | 186 [185–187] |

**Environment for every DRC number above:** `kicad-cli` **10.0.4**,
macOS-26.5.1-arm64 (Darwin 25.5.0, arm64), N=11 samples, `--all-track-errors`,
`pcb/temper.kicad_dru` regenerated from `scripts/generate_kicad_dru.py` before
measuring — the invocation `scripts/ci_check_drc.py` uses. **CI runs 10.0.5**,
which sits in a different version band (~+107 on `total`); none of these numbers
may be compared against a CI-recorded count.

Written board `sha256`: `c4c2b59ac11bdff42506498db97e6520c82feb66afd4226e295a94ad4678b445`.

Two measurement traps were hit and are recorded so the next reader does not repeat
them:

- **Measure the candidate in place, at `pcb/temper.kicad_pcb`.** `kicad-cli`
  resolves `temper.kicad_dru` *and* `pcb/fp-lib-table` relative to the board's own
  directory. A candidate measured in a scratch directory silently loses every
  custom rule: it read **842** total errors with `creepage` 186→0, `track_width`
  199→0 and `annular_width` 4→0 — for a one-resistor move. Self-consistent, and
  entirely an artifact.
- **The writer reformats the whole file.** `write_placements_to_pcb` rewrites every
  footprint's rotation (`180.0`→`180`), producing a 338-line diff for a
  one-component move. The committed change is instead a **one-line** edit to
  `R24`'s `(at …)`, and every number in this document was re-measured on those
  exact bytes.

## 5. Why candidate 2 over candidate 1

Candidate 1 is 6.5 mm closer and sits nearer `R24`'s net-mates — on displacement
alone it wins. It is rejected because **it moves DRC counts that are already at
their ceiling**: `courtyards_overlap` 11→12 and `silk_over_copper` 172→173 are
each a ceiling *raise*, which `scripts/check_drc_ceiling_approval.py` requires a
`Ceiling-Approval:` trailer for. A raise is legitimate only for measured noise or
an attributed, deliberate change; "the resistor I moved now overlaps a courtyard"
is a real regression, not either of those. Candidate 1 also lands 6.4 mm from `K3`
and leaves `clearance` sitting exactly on its 379 ceiling with no headroom.

Candidate 2 moves **no count at all** — every category identical to baseline,
same observed ranges, across 11 samples. For a safety-critical board that is the
right trade for 6.5 mm of extra displacement.

Two facts that make the move cheaper than it looks:

- **`R24` is entirely unrouted.** Zero track segments exist on `hb.power_loop.q_high-g`
  or `SW_NODE`, and no trace endpoint lies within 1.0 mm of either pad. Moving it
  orphans no copper, which is why DRC does not move.
- Nothing else moves, so no other component's routing is disturbed.

**Stated against the recommendation, because it is a real cost:** candidate 2 moves
`R24` *further* from its net-mates — `R23` 95.2→100.1 mm, `U5` 217.6→224.6 mm —
whereas candidate 1 improves both (77.7 mm, 203.0 mm). A high-side gate resistor
224 mm from its IGBT is not a finished layout. #690 already flagged this net as
scattered across the full 234 mm board height; **this change does not fix that and
is not trying to.** It buys barrier admissibility at minimum DRC cost, and the
gate-loop question belongs to the re-route in §6, where `R24`, `R23` and `U5` should
be considered together.

## 6. What remains before the barrier can actually be added

1. **Re-route, including re-pouring.** #690 §4.1 is unconditional and
   placement-independent: as routed, copper covers 31,087 of 35,568 mm² (87.4 %),
   and *all 101* HV copper pads have no admissible HV-side space at all. No
   placement change can fix that, this one included. **A keepout must be placed
   before the pour, not carved out after.** Not attempted here.
2. **Then add the `MAINS_SELV_ISOLATION_BARRIER` keepout zone** — deliberately not
   done here; it is a separate change after the re-route.
3. **Sufficiency is still open.** §Verdict's tests are necessary conditions. #690's
   min-cut probe found a separating curve but none reaching exactly two regions.
4. **Consider `R24`/`R23`/`U5` together during the re-route** (§5).

## 7. `drc_ceiling.json` — action required, deliberately not taken

`AGENTS.md` requires a board change to land with its DRC re-measurement in the same
PR. The measurement is §4; **`power_pcb_dataset/drc_ceiling.json` is deliberately
not edited in this PR**, per the explicit instruction under which this work was done.

- **No ceiling would rise.** Every per-type count and both aggregates are unchanged
  from baseline, within the same observed ranges. **No `Ceiling-Approval:` trailer
  is warranted and none is authored.**
- **But the provenance block is now stale.** It records
  `inputs[0].sha256 = 51e39844…` for `pcb/temper.kicad_pcb`; the written board is
  `c4c2b59a…`. `scripts/check_measurement_provenance.py` fails closed on that
  mismatch, so **this PR will show that gate red until the maintainer refreshes the
  block** — a hash/commit/branch update only, no number changes, plus a `_march`
  entry noting "R24 moved for barrier admissibility; no per-type delta".

Recorded rather than done, so the omission is visible instead of silent.
