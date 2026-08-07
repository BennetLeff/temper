<!-- provenance: commit=UNKNOWN dirty=UNKNOWN -- backfilled: predates the evidence-provenance gate and no self-declared commit exists in this file's own content. See .evidence-provenance-allowlist. -->

# PR #751 Phase A: three adapter/oracle projection inconsistencies

**Date:** 2026-08-06
**Branch:** `test/router-v6-congestion-oracle-and-differential` (#751)
**Found while:** writing the Phase-B Rust kernels for cluster E (congestion &
placement feedback) and cluster G-split (`escape_via_generator`).

## Summary

`packages/temper-placer/tests/router_v6/test_congestion_rust_differential.py`
asks **three** of its Rust symbols for **two different return projections** from
two different call sites each. `_assert_same` compares by
`tests/router_v6/_signature.sig`, which is type- and arity-carrying:
`sig(('a', 1.0))` and `sig(('a', 1.0, True))` are different values, and no
single Rust function can satisfy both sides.

This is a defect in the **Phase-A differential**, not in the pinned oracle
(`_congestion_py_oracle.py`) and not in the shipped module. The oracle is a
verbatim `git show` extraction and is not implicated in any of the three; what
differs is which fields each *test* projects out of the oracle's result before
handing it to `sig()`.

**Consequence for Phase B:** 4 of the 564 congestion differential tests cannot
go green without making the kernel's return type a function of the test file's
inconsistency. I did not do that. The four are listed under "Net effect".

None of the three can be repaired from the Rust side, and none may be repaired
by editing the oracle — the oracle is the specification and is correct in all
three cases. The fix belongs in the test file, in a follow-up, and is a
one-line projection change in each place.

---

## 1. `placement_suggestions_generate_py` — 5-tuple vs 4-tuple

**What the adapter does.** Two call sites, two projections:

| test | rust arm | oracle projects |
|---|---|---|
| `test_generate_placement_suggestions_bit_exact` (20 params) | `fn(case, dict(SUGGESTION_POSITIONS))` | `(component_id, current_position, suggested_position, reason, priority)` |
| `test_generate_placement_suggestions_over_many_regions` (1 test) | `fn(list(SUGGESTION_REGIONS), dict(SUGGESTION_POSITIONS))` | `(component_id, suggested_position, reason, priority)` |

The second omits `current_position`. A third test,
`test_generate_placement_suggestions_with_no_positions`, compares
`.suggestions` directly, but that call
(`SUGGESTION_REGIONS[4]` with `component_positions=None`) yields the empty
list, so `sig([])` is satisfied by either projection and it does not
discriminate.

**What the oracle does.** `generate_placement_suggestions` returns
`PlacementSuggestions(suggestions=[PlacementSuggestion(...)])`, and
`PlacementSuggestion` carries all five fields. Both projections are lossy
views of the same correct object.

**Which is correct.** The **5-tuple**. `current_position` is a compared field
everywhere else in the cluster (it is `original_position` in
`AppliedAdjustment`), and dropping it in the many-regions case removes the only
check that the suggestion carries the position it was computed *from* when more
than one region contributes. The 4-tuple looks like a copy/paste slip.

**Distinguishable by input?** Yes — `case[0]` is a `float` for a single region
row and a `tuple` for a list of rows, so a shape-dispatch *could* satisfy both.
I rejected that: it would make the kernel return a different record shape
depending on how many regions it was handed, which is not a contract anyone
would write down, and it would bake a test defect into the Rust API.

---

## 2. `apply_suggestions_damped_py` — 3-tuple vs bare list of ids

**What the adapter does.**

| test | rust arm | oracle projects |
|---|---|---|
| `test_apply_suggestions_with_damping_bit_exact` (11 params, `DAMPING_CASES`) | `fn(list(SUGGESTION_REGIONS), dict(SUGGESTION_POSITIONS), damping, threshold)` | `([(component_id, original_position, suggested_position, applied_position, damping_factor)], adjustment_count, total_movement)` |
| `test_apply_suggestions_with_missing_component` (1 test) | `fn(list(SUGGESTION_REGIONS), partial, 0.5, 0.5)` | `[a.component_id for a in ...adjustments]` — a plain `list[str]` |

**This one is not distinguishable by input at all.** `(0.5, 0.5)` is itself a
`DAMPING_CASES` row, and both calls pass the same region list and a `dict` in
the same argument position. The *only* difference is the number of entries in
that dict (12 vs 1). Dispatching a return type on the size of a dictionary is
not an API; it is pattern-matching the test suite.

**What the oracle does.** `apply_suggestions_with_damping` returns an
`AdjustmentResult`, whose `adjustments`, `adjustment_count` and
`total_movement` are all part of the contract.

**Which is correct.** The **3-tuple**. `total_movement` is where the
`(dx**2 + dy**2) ** 0.5` libm-`pow` trap (B7) actually bites, and the
id-only projection cannot see it. `test_apply_suggestions_with_missing_component`
should project the same 3-tuple; its point is the
`if current_pos is None: continue` guard, which is fully visible in the
adjustment list.

**Secondary, and benign.** In `missing_component` the oracle arm *generates*
suggestions from the full `SUGGESTION_POSITIONS` and only *applies* them
against `partial`, while the Rust arm is handed `partial` alone and must do
both from it. Those coincide: `generate_placement_suggestions` with the
restricted dict emits exactly the subset whose component is in `partial`, in
the same region-major order, and `apply_suggestions_with_damping` then filters
the full list down to that same subset. So the id list matches either way.
Worth recording so a future reader does not "fix" the wrong half.

---

## 3. `congestion_estimate_net_demand_py` — `(array, bool)` vs bare array

**What the adapter does.**

| test | rust arm | oracle projects |
|---|---|---|
| `test_estimate_net_demand_bit_exact` (22 params, `NET_BBOXES`) | `fn(w, h, cell, origin, pins, layer, per_cell, layers)` | `(out.demand, out is grid)` |
| `test_estimate_net_demand_random_sweep` (2 tests, seeds 11/12) | `fn(10.0, 10.0, 1.0, (0.0, 0.0), p, 0, 1.0, 1)` | `out.demand` |

**Also not distinguishable.** The sweep's fixed arguments
`(10.0, 10.0, 1.0, (0.0, 0.0), ..., 0, 1.0, 1)` occur verbatim as `NET_BBOXES`
rows (e.g. `(10.0, 10.0, 1.0, (0.0, 0.0), [(1.0, 1.0), (5.0, 4.0)], 0, 1.0)`),
so the same 8 arguments must produce a 2-tuple in one test and a bare array in
the other.

**What the oracle does.** `estimate_net_demand` returns a `CongestionGrid` —
either a fresh one or, on the two early-return paths (`len(pin_positions) < 2`,
and the D3 off-board guard), **the input object by identity**.

**Which is correct.** The **`(demand, out is grid)` pair**. The identity return
*is* the D3 repair's contract: `test_repaired_d3_offboard_net_contributes_nothing`
asserts `near is grid` and `far is grid` explicitly, and the far edge used to
be right only by accident, via an empty slice on a fresh copy. A projection
that drops the identity bit cannot tell the repaired guard from a copy carrying
an empty write — which is exactly the regression D3 exists to catch. The random
sweep should sign the same pair.

---

## Net effect on Phase B

Four differential tests cannot be made green by any honest kernel:

- `test_generate_placement_suggestions_over_many_regions`
- `test_apply_suggestions_with_missing_component`
- `test_estimate_net_demand_random_sweep[11]`
- `test_estimate_net_demand_random_sweep[12]`

The Phase-B kernels implement the projection named "correct" above in each
case, so the other 27 tests across those three symbols (20 + 1 + 11 + 22, minus
the four) compare real Rust against the pinned oracle bit-for-bit.

**Recommended fix (test file only, one line each):**

1. `test_generate_placement_suggestions_over_many_regions` — add
   `s.current_position` back into the projected tuple.
2. `test_apply_suggestions_with_missing_component` — project the same
   `(adjustments, adjustment_count, total_movement)` triple its sibling does.
3. `test_estimate_net_demand_random_sweep` — return `(out.demand, out is grid)`.

None of these weakens an assertion; all three *strengthen* the comparison,
because each currently signs strictly less than its sibling does.
