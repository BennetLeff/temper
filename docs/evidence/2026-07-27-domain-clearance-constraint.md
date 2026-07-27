# Domain-Aware Clearance Constraint — CP-SAT Placer Teaches Voltage Domains (R24)

<!-- provenance: commit=e67b8a6e074457a77090f095d452b935561533e1 dirty=UNKNOWN -->

**Date:** 2026-07-27
**Scope:** `packages/temper-placer/src/temper_placer/placer/cp_sat/domain_clearance.py`
(new), `packages/temper-placer/tests/placer/cp_sat/test_domain_clearance.py` (new),
`packages/temper-placer/tests/requirements/safety/test_clearance.py` (xfail → pass),
`pcb/temper.kicad_pcb` (re-solved placement).

**Note on numbers in this document:** an earlier draft of this evidence
(committed briefly, then superseded — see §0) reported a "16/18 violations"
baseline computed on a since-corrected reference-designator join. Every
number below is re-derived against the corrected board (§0, §5) and is not
carried forward from that draft.

---

## 0. Base verification, and a mid-session correction

Started mid-session on branch `worktree-agent-ac6e5eb7a36f42c4a`, initially
179 commits behind `docs/methodology-loop-discipline`; rebased clean.
The base branch moved **five more times** while this work was in progress
(new prior-art evidence, a LOC-cap paydown record, an RTD-net fix, a
PCB↔netlist resync, and an OVP-01/BusDischarge electrical retune). Each
time: `git fetch . docs/methodology-loop-discipline` + `git rebase`,
confirmed via `git rev-list --count HEAD..docs/methodology-loop-discipline`
== 0 immediately before any measurement or write (`assert-base.sh` itself
reports FAIL once this worktree carries its own commits ahead of the base
— expected; the invariant that matters is 0 *behind*, checked directly).

**A concurrent PCB resync landed mid-session** (commit `1461d944`,
`fix(pcb): resync temper.kicad_pcb net/designator/footprint assignments
against current netlist`, plus its own evidence doc
`docs/evidence/2026-07-27-pcb-netlist-resync.md`) — exactly the scenario
the dispatch warned about. That resync:

- Rewrote nets, designators, and footprints (149 → 169 footprints: 148
  kept, 1 removed, 21 added) **without moving any of the 148 persisting
  components** (verified independently in that document, and re-confirmed
  here: re-parsing both the pre-resync and post-resync files and comparing
  `(X, Y, angle)` per `Sheetpath` match shows 0 movement).
- Proved that **78 of the 149 previously-shared reference designators now
  point at a physically different component** (e.g. old `U3` was a
  SOT-23-6 buck converter; the current netlist's `U3` is a DIP-6 H11L1
  optocoupler) — a real, independent finding, not something this task
  introduced.

Because `_real_board_fixture.py` (the safety-validator test fixture) joins
PCB positions to netlist-derived voltage domains **by reference
designator**, this means the violation count this session first measured
(16, and the previously-documented 18 from 2026-07-26) was **computed on a
broken join** for those 78 components. This was caught before the fix was
finalized, not after: this document's numbers are re-derived against the
resynced board, and an earlier commit on this branch that re-solved the
*pre-resync* board was dropped (`git rebase --skip`) rather than kept or
silently amended, once the resync's implications were clear.

**Board revision solved against (final):** `pcb/temper.kicad_pcb` blob
`60cb5077d40fd8c47299fa8f3ec0bbe0a2e52c13`, written by resync commit
`1461d944ec5131039b78d1319e9d0d34b8611812`. Re-confirmed 0 commits behind
`docs/methodology-loop-discipline` immediately before the final solve and
again immediately before the final write.

---

## 1. Did the placer have prior domain awareness? Confirmed: no.

Surveyed `placer/cp_sat/_encoder_core.py`, `model.py`, `encoder.py`,
`_encoder_solve.py` directly (not assumed from the task brief):

```
grep -n "clearance\|domain\|isolation\|voltage" _encoder_core.py model.py encoder.py _encoder_solve.py
```

Found exactly one clearance mechanism: `EncoderContext.courtyard_clearance_mm`
— a single scalar (`τ = default_clearance_mm + 2×mask_expansion_mm`, ≈
0.3–0.6mm) applied **uniformly to every component pair** via
`_generate_courtyard_separated_constraints`. Nothing classifies a component
by voltage domain (`VoltageDomain`, `hv_clearance`, `domain_clearance`,
`isolation_gap` — zero matches in these four files). The placer was
structurally incapable of a domain-compliant placement: any hand-fix of the
violations would have been silently reintroduced by the next solve, exactly
as the task predicted.

(`hv_clearance`/`isolation_gap` strings *do* appear elsewhere in the
codebase — `metrics/quality_score.py`, `_constraint_types/config.py`,
`deterministic/stages/placement_validation.py`, `router_v6/power_plane.py` —
but none of these are in the CP-SAT encode path; they're a separate
deterministic-pipeline validator and a routed-copper-plane generator,
neither of which gates the CP-SAT placer's own search.)

---

## 2. Falsifiers, stated before implementing, and whether they fired

| # | Falsifier | Fired? |
|---|---|---|
| 1 | `generate_domain_clearance_constraints()` returns 0 constraints against the real board's classified domains → the generator inspects nothing. | **Did not fire.** 7715 constraints generated from the resynced board (§5). |
| 2 | The BMC-exhaustive sweep of the encoder's Chebyshev disjunction against the validator's own Euclidean-distance oracle (`_distance`) finds *any* (size, margin, offset) combination where the encoding claims separation but the oracle distance is below the margin → the soundness proof is false. | **Did not fire.** 9375 combinations swept (3 courtyard-size pairs × 5 margins × 25×25 integer-mm offsets), 0 counterexamples (`test_domain_clearance.py::TestChebyshevSoundnessBMC::test_exhaustive_offsets_bounded_grid`). |
| 3 | `audit_domain_clearance()` — recomputing real center-to-center distance from the *actual solved* coordinates — finds any mismatch against the encoded bound → the proof held on paper but not on the real solve. | **Did not fire.** 0 mismatches across all 7715 constraints, checked against the real solve's output coordinates. |
| 4 | `verify_iec60335_compliance()` re-run against the re-solved, **re-parsed** `pcb/temper.kicad_pcb` (not the in-memory placement dict from the solve itself) reports >0 violations → the fix didn't survive the round trip through the file. | **Did not fire.** 0 violations (§5); confirmed via `test_temper_board_clearance_compliance`, now a normal passing assertion (§6). |
| 5 | `solve_placement()` with the domain constraints added returns `infeasible` or exhausts a generous bounded foreground timeout at `unknown` → the constraint (combined with the existing courtyard/NoOverlap encoding) cannot be satisfied in 152×234mm; report as a board-size finding, do not relax the constraint. | **Did not fire.** `status=optimal`, solve time 27.6s (well under the 120s budget given), 169/169 components placed. |
| 6 (added mid-session, on discovering the resync) | The re-derived (post-resync) violation count could plausibly differ from the pre-resync count in either direction — if it dropped to near-zero *before any placement change*, the original "18 violations" finding would have been an artifact of the broken join, not a real defect, and this whole fix would be solving a phantom problem. | **Did not fire in that direction.** Re-derived count is **22** (higher than the original 18, not lower) — the real defect is at least as bad as originally reported, and F1↔J1 at 0.836mm (the worst original finding) is independently reconfirmed under the corrected identity mapping (F1 and J1 did not renumber in the resync's 78-designator table). |

---

## 3. R24 three-part evidence

### 3.1 Chebyshev-style soundness proof (item 1)

Full proof is in `domain_clearance.py`'s module docstring; summary:

The validator (`clearance.py::_check_distance`) measures **Euclidean
center-to-center distance** between component `position` fields. The CP-SAT
`SeparatedConstraint` handler (`handlers/separated.py::encode_separated`,
pre-existing, unmodified) bounds the **Chebyshev edge-to-edge gap** between
courtyard bounding boxes. These are different metrics on the same pair; the
proof shows the encoded (edge) bound is conservative for the validator's
(center) metric.

For the "left" branch (others symmetric): `a.x_end + margin <= b.x_start`,
where `a.x_end = a.x_center + hw_a` and `b.x_start = b.x_center - hw_b`.
Algebra: `b.x_center - a.x_center >= margin + hw_a + hw_b >= margin` (since
half-extents `hw ⩾ 0`). So `|Δx| >= margin`, and Euclidean distance `>=
|Δx| >= margin`. **SAT of the encoding at margin M ⇒ Euclidean center
distance >= M**, for any nonnegative courtyard half-extents — never
overestimates the true separation the validator will measure; if anything
it under-claims (`realized >= M + hw_a + hw_b > M`).

Both `min_clearance_mm` and `min_creepage_mm` are checked against the same
Euclidean quantity (creepage is documented in `clearance.py` as a
conservative lower bound via the triangle inequality), so encoding at
`margin = max(min_clearance_mm, min_creepage_mm)` per matrix row satisfies
both checks with one constraint. In the current `IEC60335_REQUIREMENTS`
matrix, creepage ⩾ clearance in every row, so this reduces to
`min_creepage_mm`; `max()` is kept explicit rather than assumed, so a future
matrix edit that broke this wouldn't silently invert the margin (see
`test_every_matrix_row_creepage_dominates_today`, a canary, not a load-
bearing assumption).

### 3.2 BMC-exhaustive validation on small N (item 2)

`test_domain_clearance.py::TestChebyshevSoundnessBMC`:

- Reimplements the encoder's own 4-branch Chebyshev disjunction as a pure
  Python predicate on rectangles (line-for-line match to
  `encode_separated`, not re-derived), so it can be swept without invoking
  OR-Tools per point.
- Sweeps 3 courtyard half-size pairs (including a degenerate 0×0 point
  case) × 5 margins spanning the actual matrix values (1.0, 3.0, 4.0, 6.0,
  8.0mm) × every integer-mm offset in a ±12mm window (25×25) = 9375 bounded
  cases.
- Oracle: `tests/requirements/validators/_geometry.py::_distance` — the
  exact function the safety validator itself calls (`math.dist`), imported
  not reimplemented.
- Assertion: zero cases where the encoding claims separation but the
  oracle distance is below the margin. **Passed, 0 counterexamples.**
- A companion test (`test_sweep_is_not_trivially_all_true_or_all_false`)
  confirms the sweep isn't vacuous — both `True` and `False` outcomes occur
  across the offset range, so the implication being checked is non-trivial.

13/13 tests pass in `test_domain_clearance.py` (generator-not-vacuous,
margin selection, self-pair exclusion, ref filtering, BMC sweep, audit
function — clean and broken placements, missing positions, non-domain
constraints correctly ignored). This part of the work is unaffected by the
mid-session resync — the constraint generator and its tests operate on
whatever `elec/build/default.net` and PCB positions are current at call
time; they were only ever *re-run*, never edited, after the resync landed.

### 3.3 Post-solve audit (item 3 — "the one that matters most")

`audit_domain_clearance(constraints, resolved_positions_mm)`: for every
generated constraint, recomputes `math.dist` between the two refs' *actual
solved* center coordinates and compares against `min_distance_mm`,
independent of what the solver's own status claims. Run against the real
solve's output (§5): **0 mismatches across all 7715 constraints.** This is
the check that would have caught a units bug, a half-extent sign error, or
a component silently dropped from the model — it does not trust the
solver's "optimal" status, it recomputes from coordinates.

A second, stronger form of the same audit was also run: re-parsing the
*written* `pcb/temper.kicad_pcb` file from scratch (fresh
`parse_kicad_pcb` + fresh `elec/build/default.net`, an independent process,
not the in-memory objects from the solve) and re-running
`verify_iec60335_compliance` against it. This is what
`test_temper_board_clearance_compliance` now asserts (§6) — it caught
nothing wrong on the final run, but an equivalent check *did* catch a real
bug earlier in this session: `solve_placement()` returns positions in the
CP-SAT model's local `(0,0)`-based frame, and a first draft of the write
script did not apply the board's `(20, 20)` origin offset before writing —
caught by checking the *raw* absolute footprint coordinates against the
real board outline before considering the write final (§7.2).

---

## 4. Encoding approach: reuse, not a new CP-SAT handler

`domain_clearance.py` generates ordinary `SeparatedConstraint` objects (one
per domain-crossing pair) and lets the pre-existing, already-registered
`encode_separated` handler encode them — no new CP-SAT machinery. Component
classification reuses `IEC60335_REQUIREMENTS`, `VoltageDomain`, and the
pairing functions `_nets_domain_map`/`_domain_boundary_pairs` **imported
directly from** `tests/requirements/validators/clearance.py` — the same
module the safety validator itself uses — rather than writing a second
classifier that could drift from it, per the task's explicit instruction.

**A real architectural tradeoff, stated plainly rather than hidden:** this
makes `src/temper_placer/placer/cp_sat/domain_clearance.py` import from
`tests/`, which is backwards from normal layering (`tests` is not an
installed runtime dependency). A `sys.path` shim in the module makes the
import work outside pytest's own path insertion. This is a real wart. The
alternative — promoting `VoltageDomain`/`IEC60335_REQUIREMENTS` into `src/`
and having the validator import *from* there — was not done, because the
task named the specific file to reuse *from* and did not ask for that file
to move; moving it would also touch a file this task was told to leave as
the reuse target, not the refactor target. Flagged as a follow-up (§7).

Domain identity is joined by reference designator against
`elec/build/default.net` (rebuilt via `make netlist`, exit 0, 76/76
assertions passed) — the same approach `_real_board_fixture.py` already
uses. Critically, this join is **always re-derived from whatever
`elec/build/default.net` and `pcb/temper.kicad_pcb` are current** at call
time, never cached or hand-authored — which is exactly why this constraint
generator did not need any changes at all when the mid-session PCB resync
corrected 78 stale designators; only the *inputs* to the same code changed.

---

## 5. Before / after violation counts

Real-board fixture: `tests/requirements/safety/_real_board_fixture.py`,
`load_real_board_placement()`, against the **resynced** board (169
footprints). **126 of 126** netlist components on a classified
voltage-domain net now resolve to a placed position (up from 109/126
pre-resync — the 17-component gap was exactly the broken-join effect: those
components' *old* designators pointed at parts with no classified net, or
at the wrong part entirely).

**Domain-clearance constraints generated: 7715** (up from 5679 pre-resync,
tracking the 126/126 vs 109/126 classifiable-component increase) — split
roughly between MAINS/DC_BUS ↔ LV_CONTROL reinforced-tier pairs (8.0mm
margin) and LV_CONTROL ↔ LV_CONTROL functional-tier pairs (1.0mm margin).
Every applicable `IEC60335_REQUIREMENTS` row is walked; the `(MAINS,
ISOLATED, REINFORCED)` row again finds 0 candidates (pre-existing,
documented gap: no component resolves to `VoltageDomain.ISOLATED` in this
design — carried forward from the 2026-07-26 evidence doc, unaffected by
this pass or the resync).

**BEFORE (resynced board, corrected join):** `passed=False`, **22**
REQ-SAFE-01 violations, all severity `error` — re-measured directly, not
assumed from the resync's own evidence doc (independently reproduced here:
`matched_components_in_placement: 126/126`, `error_count: 22`). This is
higher than the originally-documented 18 (not lower), because the broken
join had been *hiding* some real violations along with distorting others —
see §0. The worst finding, **F1 (MAINS) ↔ J1 (LV_CONTROL) at 0.836mm**
(clearance and creepage, both basic and reinforced tiers), is unchanged and
independently reconfirmed: F1 and J1 are not among the 78 designators that
changed meaning in the resync.

**Solve:** `solve_placement()` with the 7715 domain constraints as
`extra_constraints` (no other PCL constraints loaded — see §7.1 for why),
timeout budget 120s. **Result: `status=optimal`, 169/169 components
placed, solve_time=27.6s, total wall time 27.9s.**

**AFTER:** re-ran `verify_iec60335_compliance` two independent ways:

1. **In-memory**, substituting the solver's own output positions into the
   placement dict used for the "before" measurement: `passed=True,
   error_count=0, total_violations=0`.
2. **End-to-end**, re-parsing the *written* `pcb/temper.kicad_pcb` from
   scratch via a fresh `parse_kicad_pcb` call and a fresh
   `elec/build/default.net`: `test_temper_board_clearance_compliance`
   **passes** (was `xfail(strict=True)`; is now a normal assertion, see §6).

**22 → 0.** Both measurements agree. The post-solve audit (§3.3) found 0
mismatches between the encoded bound and the real solved distances, so
there is no reason to expect these two counts to have diverged, and they
didn't.

**Unplanned corroborating evidence:**
`test_regression_drc.py::test_production_board_drc_regression` — a
pre-existing, unrelated KiCad-DRC-derived placement ratchet (threshold 800
violations) — was checked directly on three board states: the original
stale board (931), the resynced-but-not-repositioned board (954, checked by
temporarily restoring that backup and re-running the test), and this fix's
re-solved board. The first two both **already fail** this ratchet (it's a
pre-existing, out-of-scope failure, unrelated to this task); the re-solved
board **passes** it — fewer courtyard overlaps, shorting items, and
clearance violations than either prior state. This is not what this task
targeted (it's a KiCad-DRC-derived, not IEC-60335-derived, metric) but is
a real, unprompted improvement from teaching the placer domain-aware
separation.

---

## 6. Test suite: before / after

| Suite | Before (this session, corrected) | After |
|---|---|---|
| `test_clearance.py` + `test_isolation.py` (safety validators) | 53 passed, 1 xfailed (with the wrong 18-violation reason, later corrected in-flight) | **54 passed, 0 failed, 0 xfailed, 0 skipped** |
| `test_domain_clearance.py` (new) | n/a | **13 passed** |
| `test_regression_drc.py::test_production_board_drc_regression` (pre-existing, unrelated ratchet) | FAILED (931, then 954 post-resync) | **PASSED** (unplanned side-effect, §5) |

`test_temper_board_clearance_compliance` was `xfail(strict=True)`. Per the
task's own instruction ("if violations reach 0 it will fail because it
unexpectedly passes"), it XPASSed under the old marker at both intermediate
checkpoints in this session (confirmed directly each time — ran it before
each edit, saw `[XPASS(strict)] ... FAILED`) and has been converted to a
normal passing assertion, with the docstring rewritten twice in-session (see
§0) to end up stating the corrected 22→0 count and the resync context. This
is **not** leaving a strict-xfail masking a fixed state — the marker is
gone, and its replacement text matches the final, re-derived numbers, not
an intermediate draft.

---

## 7. What remains, ranked

### 7.1 `configs/pcl/temper_production.yaml` is stale (found, not fixed — out of scope)

That file's own header warns "re-verify every ref below against a fresh
`elec/build/default.net` before reusing this file after any BOM change."
Checked directly against a fresh `default.csv` (pre-resync): several of its
documented ref→function mappings no longer hold (e.g. `U22` was "MCU (ESP32
module)" as of 2026-07-17; at that point it resolved to
`SN74LVC1G38DBVR`, a logic inverter — and post-resync `U22` is the
`LogicUVLOComparator`'s inverter instead, a *third* meaning). **Deliberately
did not load this file's other PCL constraints (adjacent/anchored/on_side)
into the re-solve** — doing so would apply stale adjacency/anchor intent to
the wrong physical components, a different and unrelated bug this task did
not scope in. The re-solve used only the domain-clearance constraints plus
the encoder's own built-in courtyard-clearance/NoOverlap2D/netclass
machinery. Re-authoring that config against the current (resynced) netlist
is a real follow-up, separate from this fix.

### 7.2 Latent origin-offset bug in the CLI's `--no-loop` path (found, fixed only for this write)

`solve_placement()` returns positions in the CP-SAT model's local
`(0,0)`-based frame (`board_w`/`board_h` are dimensions, not absolute
extents). This board's real origin is `(20, 20)` (confirmed:
`parse_kicad_pcb(...).board.origin == (20, 20)`), and
`write_placements_to_pcb()` expects **absolute** KiCad coordinates (it
writes `fp.position.X/Y` directly with no offset). `io/_write_board.py`'s
`state_to_placements()` (a different call path) already adds
`origin[0]/origin[1]` before constructing `PlacementUpdate`s — but
`cli/__init__.py`'s `optimize --no-loop` branch does not; it builds
`PlacementUpdate(x=pos[0], y=pos[1], ...)` directly from
`cp_result.positions`. This looks like a **pre-existing, latent bug** in
that CLI path (any board whose Edge.Cuts origin isn't `(0,0)` would be
written into the wrong absolute location). This fix's own write script
applies `board.origin` before constructing `PlacementUpdate`s (verified:
raw `fp.position.X/Y` in the written file range `21.23–168.55 /
21.23–252.75`, fully inside the real `(20,20)-(172,254)` outline — checked
directly against the raw kiutils board object, not the round-tripped/
origin-subtracted `initial_position` field, which would misleadingly look
"out of bounds" against the absolute frame since it's origin-relative by
construction — this exact confusion happened once during development and
was caught before the final write). **The CLI's own `--no-loop` path was
not patched** — that's a separate fix, flagged here rather than silently
bundled into this change.

### 7.3 Feasibility in 152×234mm: confirmed feasible, and faster than expected

The board (169 components) solved to `optimal` in 27.6s with 7715 extra
HARD SEPARATED constraints on top of the existing courtyard/NoOverlap2D
encoding. This is notable against `docs/solutions/architecture-patterns/
cp-sat-feasibility-first-paradigm-2026-07-03.md`'s documented CP-SAT scale
wall (persistent `unknown` status on this same board with a different
constraint mix — `ADJACENT`/`ANCHORED`/`ON_SIDE` constraints from
`temper_production.yaml`). A plausible reason, not fully verified: `SEPARATED`
constraints and `NoOverlap2D` both push components apart — the same
direction — so they compose without the back-and-forth tension that
`ADJACENT` (pull together) creates against `NoOverlap2D`/courtyard
(push apart), which may make this particular constraint mix much easier
for CP-SAT to propagate toward a feasible point. **This is not a formal
claim about CP-SAT's general scalability on this board** — it's an
observation about this specific constraint combination, reported honestly
rather than generalized. The falsifier (§2, item 5) did not fire: no
board-size finding is warranted here, because feasibility was reached, not
because it's guaranteed to remain feasible under every future constraint
addition.

### 7.4 Scope gaps carried forward from 2026-07-26, unchanged by this pass

- `VoltageDomain.ISOLATED` still has 0 real-board candidates (no component
  in this design resolves to "the floating side of a declared isolator" by
  net name) — the `(MAINS, ISOLATED, REINFORCED)` matrix row is walked but
  structurally finds nothing to constrain. Same honest gap as before, not
  fixed here, and unaffected by the resync (it's a net-name/topology gap,
  not a designator-join gap).
- `isolation.py`'s barrier/trace/ground-plane checks (REQ-SAFE-02) are
  still not run against real board geometry (no real
  trace/ground-plane/barrier extraction pipeline exists yet) — untouched by
  this pass, which only addresses REQ-SAFE-01 (clearance/creepage).
- 7 other pre-existing, unrelated test failures were surveyed while
  checking for regressions in the wider `cp_sat` test directory
  (`test_all_constraint_types_covered`/`test_e2e_temper_board_feasible` —
  a missing `ON_SIDE` CP-SAT handler; `test_solve_time_trend_warning` — a
  stale `mock.patch` target; `test_golden_board_drc_regression` — a stale
  `monkeypatch.setattr` target that no longer exists on that module
  post-refactor; 3 `ModuleNotFoundError: temper_rust_router` failures — a
  native extension not built in this environment). None of these touch
  `pcb/temper.kicad_pcb` content or this change's code; all reproduce
  identically regardless of which board revision is checked out. Not fixed
  here — genuinely out of scope.

### 7.5 IEC60335_REQUIREMENTS matrix provenance — inherited, unchanged

As already flagged in the 2026-07-26 evidence doc: the clearance/creepage
figures in the matrix were not independently re-derived from a cited IEC
60664-1 table cell in this pass either. This pass consumes the matrix as-is
(per the task's explicit instruction to reuse it verbatim), so this
provenance gap is inherited, not introduced or resolved here.

---

## 8. Commits

- `feat(placer): add voltage-domain clearance constraint generator (R24)` —
  `domain_clearance.py` (generator + soundness proof + post-solve audit)
  and `test_domain_clearance.py` (13 tests: generator-not-vacuous, BMC-
  exhaustive soundness sweep, audit correctness). Unaffected by the
  mid-session resync — re-run, not re-authored, against the corrected
  board.
- `fix(pcb): re-solve resynced temper board with domain-clearance
  constraints` — the re-solved `pcb/temper.kicad_pcb` (against the
  resynced, 169-footprint board) and the
  `test_temper_board_clearance_compliance` xfail→pass conversion with the
  corrected 22→0 count. A prior commit on this branch that re-solved the
  pre-resync board was dropped (`git rebase --skip`) rather than kept.
