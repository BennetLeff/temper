# Domain-clearance constraint vs. copper-to-copper validator: closing the model gap

<!-- provenance: commit=0c0c21c4a1abcb392212e063da0cf69e20ecda8b dirty=UNKNOWN -->

**Date:** 2026-07-30
**Scope:** `pcb/**` and `elec/src/**` are read-only throughout. No placement was written to
`pcb/temper.kicad_pcb`. All re-solves are candidate placements measured in memory / scratch and
reported here, never committed to the tracked board.

**Base:** `git fetch origin && git checkout -b fix/domain-clearance-copper-aware origin/main`,
`uv sync --all-packages`, `make netlist` (`elec/build/default.net` digest `1b1d641f6647…`).
`origin/main` moved twice under this session (a concurrent board-resync agent is active, per this
task's own brief); the branch was rebased onto the current tip (`0c0c21c4`) before any measurement
below, and `scripts/assert-base.sh origin/main` confirmed `HEAD == origin/main` immediately before
starting.

---

## 0. Baseline reproduction

```
uv run pytest packages/temper-placer/tests/requirements/safety/test_clearance.py::TestClearanceIntegration::test_temper_board_clearance_compliance -rA -s
```

**98 REQ-SAFE-01 violations across 52 pairs** (13 of the records intra-footprint), 158/168
components classified. Matches the task brief's stated current baseline exactly (post PR #442's
corrected 10.0mm reinforced creepage bar — the earlier 76/33 figure this repo also carries in
older evidence docs is stale relative to that correction).

---

## 1. The gap, confirmed by code trail

- **Solver side:** `placer/cp_sat/domain_clearance.py:155-234`
  (`generate_domain_clearance_constraints`) emits one whole-component `SeparatedConstraint` per
  domain-crossing pair. `handlers/separated.py:20-94` (`encode_separated`) encodes each as a
  Chebyshev (L∞) disjunction over `model.py`'s `x_start`/`x_end`/`y_start`/`y_end` — **bounding-box
  edges**, populated from `comp.bounds` (`io/_parse_modules.py::_calculate_footprint_bounds`, union
  of courtyard/fab graphics and every pad's copper extent).
- **Validator side:** `requirements/validators/clearance.py:7-53` measures **copper-to-copper on
  exact, rotation-aware pad geometry** (`core/pad_geometry.py`), restricted to pads whose own net
  is classified into the relevant domain, per domain-crossing pair *and* per intra-footprint
  straddle.
- **The stale proof:** `domain_clearance.py:42-97` (pre-fix) proved "SAT of the encoding ⇒
  Euclidean **center-to-center** distance ≥ margin" — a true statement about a quantity the
  validator stopped measuring on 2026-07-28. The proof's own premise ("the validator measures
  center-to-center distance") was already false when written.

---

## 2. Measuring the gap and its direction (not assumed)

### 2.1 The mathematical result: box-vs-box implies copper-vs-copper, given one precondition

The Chebyshev disjunction's per-axis inequality (e.g. `a.x_end + margin <= b.x_start`) is a
statement about **every point** in box A vs. **every point** in box B, not just their centers: if
`p_a.x <= a.x_end` and `p_b.x >= b.x_start`, then `p_b.x - p_a.x >= margin` for *any* `p_a` in box A
and `p_b` in box B — including every pad-copper point on each side. So **SAT of the encoding at
margin M ⇒ every point of box A is ≥ M from every point of box B**, which is strictly stronger than
the old center-only conclusion (recovered as the special case `p_a = a.center`, `p_b = b.center`)
and is exactly the copper-to-copper quantity the validator measures — **provided box A actually
contains component A's real pad copper at the point the solver places it.**

### 2.2 The precondition was not reliably true: a real, provable frame mismatch

`_calculate_footprint_bounds` computed its symmetric half-extents around the footprint's **raw
KiCad anchor** (`fp.position`). But `Component.initial_position` — the point CP-SAT actually
centers the box at — and `Pin.position` — what the validator's pad geometry is expressed relative
to — are **both** shifted by `center_offset`, the pad centroid computed in
`_extract_components_from_pcb` (`(min_pad_center + max_pad_center) / 2`, added originally so
placement position tracks a component's electrical centroid, not its arbitrary library-reference
point). The box was therefore being drawn symmetric around one point while being *placed* at a
different one.

**Synthetic counter-example (real code, not hand-derived), before the fix:**

```
Pad 1: local x=-5, half-width 6   (extent [-11, 1])
Pad 2: local x=+8, half-width 0.5 (extent [7.5, 8.5])
center_offset_x = (-5 + 8) / 2 = 1.5
```

```
>>> _calculate_footprint_bounds(fp)              # pre-fix: no offset argument existed
(22.0, 2.0)   # half-width 11.0
>>> true pad extent, in the frame Pin.position/initial_position actually use: [-12.5, 7]
>>> box relative to that shifted centre: [-11, 11]  -- does NOT contain -12.5
```

1.5mm of pad 1's real copper sits **outside** the box the `SeparatedConstraint` handler protects.
This is pinned as a regression test:
`tests/placer/cp_sat/test_geometry_constraints_pbt.py::test_bounds_computed_in_placement_frame_not_raw_anchor`
(P10). Confirmed to fail on the pre-fix code by temporarily restoring the pre-fix file content
(via `git show HEAD:<path>`, never `git stash`) and re-running:

```
FAILED test_bounds_computed_in_placement_frame_not_raw_anchor
AssertionError: comp.bounds=(22.0, 2.0) does not enclose real pad copper in the placement frame --
  pad 1 at (-6.500,0.000) size (12.000x2.000) extends to x=[-12.500,-0.500]
  outside bounds half-width ±11.000
```

### 2.3 Direction on THIS board's real 168 components: conservative, but not by proof — by luck

Measured directly (script against `pcb/temper.kicad_pcb`, read-only, reimplementing nothing —
calls the real `_calculate_footprint_bounds`):

- **0 of 168 real components exhibit an actual overhang** under the pre-fix (unshifted) bounds
  calculation — the frame-mismatch bug above is real and provable, but this board's specific
  footprints happen not to trigger it (their courtyard graphics are generous enough, or their pad
  layouts symmetric enough, to still cover the shifted extent by coincidence).
- **Over-conservatism, quantified:** comparing the pre-fix box to the minimal box that *would* be
  needed at the correctly-shifted centre, median excess half-width **0.255mm**, mean **1.63mm**,
  max **21.6mm** (`PS1`). Total footprint-box area across all 168 components: **19,771.3mm²**
  pre-fix.

So on this board, direction was **conservative (safe, pessimistic)** — matching the general
expectation that a courtyard/fab-derived box encloses its own pads — but this was an empirical
fact about this board's footprints, not a property the code guaranteed. A future board resync (one
is running concurrently, per this task's brief) could introduce a footprint whose asymmetric pad
sizes trigger the failure mode in Sec 2.2 for real.

---

## 3. The fix implemented, and why

**Chosen fix:** thread `center_offset` through `_calculate_footprint_bounds` so the box is computed
symmetric around the *same* point (`initial_position`) the solver centers it at and the validator's
pad geometry is expressed relative to — not the footprint's raw anchor.

```python
def _calculate_footprint_bounds(
    fp: Footprint, center_offset_x: float = 0.0, center_offset_y: float = 0.0
) -> tuple[float, float]:
    ...
    hw = max(abs(x_min - center_offset_x), abs(x_max - center_offset_x))
    hh = max(abs(y_min - center_offset_y), abs(y_max - center_offset_y))
```

`_extract_components_from_pcb` now computes `center_offset_x/y` from `fp.pads` **before** calling
bounds (previously computed only afterward, from `raw_pins`, for the pin-recentering step) and
threads the identical values into both the bounds call and the pin-recentering — one source of
truth instead of two independent derivations that could silently diverge.

**Why this fix, not per-pad-group constraints or a bbox-from-per-domain-pads model:**

Per the proof in Sec 2.1, once box ⊇ real pad copper *at the placement frame* is restored, the
**existing whole-component `SeparatedConstraint` mechanism already gives the exact guarantee the
validator needs** — for every pad, not just domain-classified ones, which is a strictly *stronger*
guarantee than a per-domain box would give at a fraction of the engineering cost (no new CP-SAT
machinery, no per-pad offset modeling under 4-way rotation, no change to the constraint count or
the handler). A per-pad-group re-encoding was the higher-cost option in the task's own ordering; it
is not warranted once the actual defect (a coordinate-frame bug, not an inherent limitation of
whole-component boxes) is fixed directly.

**Evidence this is not a needless-infeasibility trade (measured, not asserted):**

- **0 of 168 components regress into unsafe (overhang) territory** — verified identically
  post-fix (by construction now, not observation: the containment invariant is proven, see Sec 2.1).
- **Box area shrinks net-wide:** 168-component total area 19,771.3mm² → **14,120.2mm²** (−28.6%).
  133 components unchanged, 29 shrink, only **6 grow** (`C2/C3/C4/C5` +115.7mm² each on the same
  footprint, `K1` +99.1mm², `T1` +2.5mm² — all safety-restoring corrections, not regressions: their
  old boxes were the ones at risk of the Sec 2.2 failure mode, just not badly enough to overhang on
  this specific layout).
- **The re-solve (Sec 4) is faster than the prior evidence doc's pre-fix run** (25.5s wall vs.
  40–82s in `docs/evidence/2026-07-30-copper-aware-domain-resolve.md`, same 11,856-constraint full
  classified-domain set, same methodology) — consistent with a net-smaller, not larger, encoded
  search space; the fix did not make the problem harder to solve.

---

## 4. Corrected soundness proof (R24 item 1)

Rewritten in `domain_clearance.py`'s module docstring in full; summary:

> SAT of the Chebyshev box encoding at margin M implies the distance between **every point** of
> component A's box and **every point** of component B's box is ≥ M — not just their centers. Given
> `comp.bounds` now provably encloses every real pad on each component *at the placement position*
> (the precondition this fix restores, tested by P8/P9/P10), this directly implies copper-to-copper
> separation ≥ M for every pad pair between the two components — the exact quantity
> `clearance.py::_check_distance` measures, for *every* pad (a strict superset of the
> domain-restricted subset the validator actually requires, hence still conservative). This proof
> explicitly does **not** cover intra-footprint (self) pairs — see Sec 5 — and the post-solve audit
> (R24 item 3) still checks the cheaper center-distance quantity, which is implied by but weaker
> than the box's full guarantee; it catches encoder/units bugs, and is not a substitute for
> re-running the validator itself (which Sec 4 below does).

---

## 5. Self-pair (intra-footprint) blindness

**Categorically not fixable by any placement constraint**, confirmed and now stated plainly at
every point a reader can hit it: placing a component only translates/rotates its box as a rigid
whole. It cannot change the distance between two of that same component's own pads. No
`SeparatedConstraint`, and no other placement-time mechanism, can ever make an intra-footprint
domain crossing (e.g. an isolator relay with primary- and secondary-side pads on one part)
compliant — the remedy is a different part, a different footprint, or a milled isolation slot,
never a placement.

**What changed:** this exclusion previously produced **zero signal** — `_domain_boundary_pairs`
(imported, shared with the validator) silently excludes same-ref pairs, and
`handlers/separated.py`'s own `if ra == rb: continue` was undocumented defense-in-depth. Now:

- **`find_intra_footprint_domain_conflicts`** (new, exported) enumerates every ref classified into
  both sides of a matrix-covered domain boundary — a coarser, **component-level** superset check of
  the validator's pad-level `clearance.py::_intra_component_boundary_components`.
- **`generate_domain_clearance_constraints` now logs a `WARNING`** naming every such ref on every
  call that finds one — so "the solve reported optimal" is never silently mistaken for "the board
  is compliant" when an unfixable isolator is the actual remaining violation.
- **`handlers/separated.py`'s `if ra == rb: continue`** now carries a comment explaining it is
  generic defense-in-depth (legitimately hit by unrelated tag-expanded-group callers too, so a
  warning there would be noise) and pointing to where the domain-clearance-specific signal actually
  lives.

**Real board result:** `find_intra_footprint_domain_conflicts` flags **8** refs (`C6, K1, K2, K3,
PS1, T1, U3, U7`) — a proper superset of the validator's own **7** confirmed pad-level
intra-footprint violators (`C6, K1, K2, K3, T1, U3, U7`; 13 violation records across basic/
reinforced/clearance/creepage). `PS1` is flagged at the coarser component level (it carries nets in
both domains somewhere) but its specific straddling pads do not actually violate the requirement —
exactly the documented, expected false-positive direction (superset, never a miss). Pinned by
`TestIntraFootprintDomainConflicts::test_real_board_finds_known_isolators`.

---

## 6. Standard of proof: re-solve, full classified-domain constraint set

Methodology matches `docs/evidence/2026-07-30-copper-aware-domain-resolve.md` Sec 3 (full
11,856-constraint set, not just the violating pairs — scoping to violators alone regressed the rest
of the board there): `load_real_board_placement()` for the validator-shape placement,
`parse_kicad_pcb(pcb/temper.kicad_pcb)` for the CP-SAT netlist/board, current positions as
`AddHint` (not pinned), `seed=0`, `timeout_ms=180_000`.

| Metric | Value |
|---|---|
| Constraints generated | 11,856 |
| CP-SAT status | **optimal** |
| Solve time | **25,515.3ms (25.5s wall)** |
| Positions returned | 168 / 168 |
| Post-solve audit (center-distance, R24 item 3) | **0 mismatches** |
| REQ-SAFE-01 violations, validator, **before** | 98 (52 pairs, 13 intra records) |
| REQ-SAFE-01 violations, validator, **after** | **28 (17 pairs, 13 intra records)** |

**The 7 intra-footprint self-pairs (13 records: `C6`×3, `K1`×1, `K2`×3, `K3`×3, `T1`×1, `U3`×1,
`U7`×1) are UNCHANGED before and after** — exactly as predicted by Sec 5: no placement can touch
them, and none did.

**10 new inter-component pairs appear post-resolve** that were not in the 98-violation baseline
(`U5<->R49`, `F1<->R62`, `U3<->R65`, `RT1<->U27`, `RT1<->R58`, `C19<->R37`, `R48<->R60`, `L2<->R31`,
`R21<->R35`, `C16<->R38`), all marginal (shortfalls 0.010mm–4.178mm). This is the same "full-board
reshuffle" side effect the prior evidence doc already documented for this re-solve methodology
(warm-started `AddHint`, not a binding pin, against ~12,000 hard constraints lets CP-SAT move every
component) — reported plainly, not hidden: **the net effect is a large, real improvement (98→28,
−71%; 52→17 pairs, −67%), not a clean zero**, and this candidate placement was never written to
`pcb/temper.kicad_pcb` (read-only per this task's constraints; a production fix would still need a
routing pass afterward, as the prior evidence doc's DRC section already established for this same
methodology).

---

## 7. Regression checks

```
uv run pytest packages/temper-placer/tests/placer/cp_sat/test_domain_clearance.py -v   # 21 passed
uv run pytest packages/temper-placer/tests/placer/cp_sat/test_geometry_constraints_pbt.py -v  # 10 passed
uv run pytest packages/temper-placer/tests/io/ -q     # 275 passed, 8 skipped, 1 xfailed
uv run pytest packages/temper-placer/tests/requirements/ -q   # 293 passed, 5 skipped,
                                                                # 1 pre-existing failure (see below)
```

The one failure in `tests/requirements/` is `test_temper_board_clearance_compliance` itself — the
98-violation baseline this task's hard constraints explicitly forbid modifying to pass. Not touched.

`ruff check` clean on every changed file. `ty check` on the three touched `src/` modules reports
only 10 pre-existing `possibly-missing-attribute` warnings in `handlers/separated.py` on
`model.model_ref.Add(...)`/`AddBoolOr(...)` calls unrelated to and unchanged by this fix (present on
lines this diff did not touch).

---

## 8. Reproduction

```bash
git fetch origin && git checkout -b fix/domain-clearance-copper-aware origin/main
uv sync --all-packages
make netlist
uv run pytest packages/temper-placer/tests/requirements/safety/test_clearance.py::TestClearanceIntegration::test_temper_board_clearance_compliance -rA -s   # 98/52 baseline, unchanged by this PR
uv run pytest packages/temper-placer/tests/placer/cp_sat/test_domain_clearance.py packages/temper-placer/tests/placer/cp_sat/test_geometry_constraints_pbt.py -v
```

The re-solve driver (`dcca_resolve_2026-07-30.py`) is scratch-only per this task's instructions
(not committed); its full invocation and output are reproduced verbatim in Sec 6 above.
