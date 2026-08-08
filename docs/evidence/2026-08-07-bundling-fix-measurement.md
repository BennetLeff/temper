<!-- provenance: commit=b36e7b37cecbabafa99e1a3338439242e41c1c4a dirty=false -->

# Bundled-encoding fix-order execution for `#871`: grouping widened, `BundleAnalyzer` vectorized, capacity-constraint collision fixed — construction still does not complete under the 8GB gate

**Date:** 2026-08-07

**Task:** `docs/evidence/2026-08-07-sat-model-reduction-options.md` (§3.4,
§8) found the bundled encoding's real blocker was not (only) the missing
PyO3 binding: `BundleAnalyzer`'s `TypeSignature` grouping was too strict
(8 bundle classes / 21 of 110 nets), `_compute_covered_edges` was an
unvectorized `O(n_nets × E)` loop (~391s wall), and
`_create_capacity_constraints` had a real net-index/bundle-id key
collision. Its recommendation was to fix those three things, in that
order, before spending more effort on the binding. This task executes
that fix order and re-measures.

**Headline, stated up front:**

1. **Grouping widened, capacity-collision fixed, `BundleAnalyzer`
   vectorized ~33.5×, all three MEASURED — but the resulting channel-var
   reduction is still far short of what's needed.** Bundle coverage moved
   from 21/110 to 28/110 nets (8 bundle classes both before and after — the
   same geometric clusters simply absorbed a few more type-compatible
   nets), a **channel-var-creating-unit** reduction of 110 → 90 (18.2%,
   up from the prior 11.8%). Applied to the 204,490-edge skeleton:
   `22,493,900 → 18,404,100` primary channel variables, DERIVED exact.
2. **Construction still `MemoryError`s under the 8GB gate** — MEASURED,
   same order of magnitude as before the fix (peak RSS 5.66GB here vs.
   5.43GB unbundled / ~5.78GB pre-fix-bundled). It crashes partway through
   `_create_bundle_channel_vars`'s per-net loop, at ~12.4M of the ~18.4M
   channel variables needed, **before ever reaching `_create_via_vars`** —
   and via variables are completely unreduced by bundling (`_create_via_vars`
   ignores `enable_bundling` entirely), at roughly `153,432 nodes × 110
   nets ≈ 16.9M` more variables on top. Via variables, not channel
   variables, are now the dominant unaddressed cost.
3. **The missing PyO3 binding (`solve_topology_rust_bundled`) is still
   masked, not the binding constraint.** Construction itself does not
   reach the solve call on the production board, so restoring the binding
   would not currently help. Not attempted this task, consistent with the
   prior evidence doc's own conditional recommendation ("only if steps 1–3
   make the numbers worth it").
4. **A full-pipeline regression test was added** (not just a
   `ModelBuilder`-level one) that drives `RouterV6Pipeline._run_stage3`
   with `enable_bundling=True` and asserts control actually reaches the
   Rust solve-call boundary — the exact wiring gap that let the binding
   go missing for three weeks undetected in the first place.

---

## 0. Why the grouping was narrow, and the soundness argument for widening it

`TypeSignature` (`bundle_analyzer.py`) required an **exact** match on
`(net_class, trace_width, clearance, has_diff_pair, pin_layer_set)`.
`net_class` itself is coarse (`net_classification.classify_net_type`'s
four name-pattern buckets: ground/power/hv/signal — 98/110 nets fall into
"signal"), but `trace_width`/`clearance` are continuous, per-design-rule
values, and this board has **11 distinct design-rule netclasses**
(`netclass_rules.yaml`: `ACMains`, `HighVoltage`, `HighVoltageIsolated`,
`FinePitch`, `Power`, `GND`, `GateDriveHV`, `GateDriveSELV`, `HighSpeed`,
`Signal`, `HighCurrent`), each with its own width/clearance. "Same coarse
net_class" almost never meant "same exact width/clearance" — the extra
precision in the old signature was, in the prior evidence doc's words,
"smuggling locality back in through a side door."

**The fix**: `TypeSignature` now keys on `(safety_category, net_class,
has_diff_pair)` — dropping the exact `trace_width`/`clearance` match
entirely, and dropping `pin_layer_set`, while *adding* `safety_category`
(read directly from `design_rules.get_rules_for_net(name).safety_category`
— previously never consulted by the bundle analyzer at all).

**Soundness argument** (also recorded as a docstring on `BundleAnalyzer`
and `TypeSignature` in the source, so it stays next to the code it
justifies):

- **Capacity soundness.** A bundle's shared SAT variable stands in for
  every member net using an edge *together* — so the capacity term a
  bundle contributes must reflect the summed physical width of all its
  members, not one representative member's width.
  `ModelBuilder._create_capacity_constraints` (fixed alongside this
  change, §2 below) now sums each member's own
  `trace_width_mm + clearance_mm` from `design_rules` when building a
  bundle's capacity term. Because that sum is now exact per-member
  regardless of whether members share a width, dropping the old exact
  width/clearance match does not create an under-counted capacity term —
  it was never load-bearing for correctness, only for (accidentally)
  narrowing the grouping.
- **Safety-domain soundness.** Bundling can never cross an AC/HV/LV
  boundary, because `safety_category` — the design-rule-authoritative
  physical isolation tier — is part of the required match.  This is
  *stricter* than the old signature in one respect: `net_class` alone
  (the name-pattern heuristic) can misclassify a design-rule-HV net whose
  *name* doesn't match an HV pattern (e.g. `GATE_HS`/`GATE_LS`, netclass
  `GateDriveHV`, `safety_category="HV"`, but not matched by
  `HV_NET_PATTERNS`) as plain "signal". Requiring `safety_category` too
  closes that gap — a case the old signature would have gotten wrong in
  the *unsafe* direction if such a net had ever geometrically clustered
  with an LV signal net.
- **Geometric soundness is untouched.** The Jaccard > 0.5 footprint-overlap
  requirement — the primary defense against bundling unrelated,
  board-spanning nets — is unchanged. Only the "type" half of "type AND
  geometry" was loosened; "geometry" still does the real discriminating
  work, which is precisely what the underlying measurement shows (§1).
- **Known, unaffected gap, stated explicitly rather than silently
  inherited**: SMD pin-layer restrictions
  (`ModelBuilder._create_layer_constraints`) are not enforced for bundled
  member nets today, independent of this change — that function only
  ever looks up per-net `(net_idx, edge_id)` keys, which bundled members
  never populate (only unbundled/singleton nets do). Dropping
  `pin_layer_set` does not remove enforcement that existed, since none
  existed for bundled nets before this change either. This is a real,
  separately-scoped follow-on item, not silently fixed or worsened here.

---

## 1. Vectorizing `BundleAnalyzer` — MEASURED ~33.5× wall-time reduction

`_compute_covered_edges` previously re-derived every skeleton edge's `(id,
midpoint)` pair AND ran a raw, unprepared `Polygon.contains(Point(...))`
call against each one — **on every call**, i.e. once per net
(`O(n_nets × total_edges)`, MEASURED ~391s on the 204,490-edge production
skeleton per the prior evidence doc).

**Fix**: precompute the `(edge_id, midpoint)` table once per
`BundleAnalyzer` instance (cached), build a Shapely `STRtree` over the
midpoints once, and answer each net's edge-cover query with a single
`STRtree.query(footprint, predicate="contains")` call — a bounding-box-
pruned, vectorized, C-level query instead of a Python-level loop over
every edge. Same fix shape as `07d514f9`'s KD-tree rewrite of island
bridging elsewhere in this pipeline (named directly by the prior evidence
doc as the template to follow).

**MEASURED, this task, production board, clean/stripped copper (204,490
edges — see §3's methodology note on why stripping matters), two runs**:

| Run | `BundleAnalyzer.analyze()` wall |
|---|---:|
| Pre-vectorization (prior evidence doc) | ~391s |
| Post-vectorization, this task | **11.68s** |

`391 / 11.68 ≈ 33.5×` (DERIVED). A second run on the (confounded,
not-stripped, see §3) live board measured 3.53s for a smaller 149,900-edge
skeleton — consistent with the same mechanism, not a separate data point
for the headline ratio.

---

## 2. The net-index/bundle-id capacity-constraint collision — fixed, tested

`_create_bundle_channel_vars` stores one shared channel variable per
*bundle*, keyed by `bundle_id` (`0..bundle_count-1`) — a different,
smaller ID space than real net indices (`0..n_nets-1`), but
`ConstraintModel` stored both in the **same** `net_channel_vars` dict,
keyed `(net_idx_or_bundle_id, channel_id)`. A real net whose index
happened to numerically coincide with an unrelated bundle's id would
either silently drop out of every capacity constraint it should appear
in, or get misattributed to that unrelated bundle's variable.

**Fix**: `ConstraintModel` now has a separate `bundle_channel_vars` dict
(`(bundle_id, channel_id) → NetChannelVar`), so the two ID spaces can no
longer collide structurally. `_create_capacity_constraints` was rewritten
to build one term per bundle — summing every member net's own
`trace_width_mm + clearance_mm` (see §0's capacity-soundness argument) —
plus one term per net not covered by a bundle, with each net contributing
to exactly one term.

**Test**: `test_bundled_capacity_constraints.py` constructs a 4-net,
2-bundle scenario where a real net's index numerically coincides with an
*unrelated* bundle's id (net 1, a member of bundle 0, has the same index
as bundle 1's own id) and asserts each bundle's capacity term reflects
the sum of only its own members' widths — it fails against the pre-fix
code (verified by reasoning through the pre-fix dict-overwrite order; the
pre-fix single-dict scheme would have let bundle 1's term pick up net 1's
width, or dropped bundle 0/1's true member-width contributions entirely,
depending on `dict` insertion order). A second test checks the
mixed-bundled/unbundled case has no double-counting.

---

## 3. Live measurement: bundle coverage, variable count, peak RSS, completion

**Methodology note, load-bearing for comparability**: `pcb/temper.kicad_pcb`
currently carries 2290 committed `(segment ...)`, 48 `(via ...)`, and 96
`(zone ...)` blocks. An initial run against the board *as committed*
(not stripped) produced a smaller skeleton (149,900 edges vs. the
204,490-edge baseline) because Stage 2 treats existing copper as
additional routing obstacles — not a fair comparison against the
22,493,900-variable baseline, which was measured on a clean board. All
figures below are from a **second, corrected run** that strips existing
copper into an in-memory working copy first (mirroring
`scripts/route_board.py`'s own default behavior; `pcb/temper.kicad_pcb`
itself is never written), confirmed to reproduce the baseline's own
204,490-edge skeleton exactly.

**MEASURED, this task, `ulimit -v 8388608` (8GB), `TEMPER_MODEL_TRACE=1`,
background + polled in-turn, stripped working copy**:

| Quantity | Before this task (prior evidence doc) | After this task | Label |
|---|---:|---:|---|
| Bundle classes | 8 | 8 | MEASURED |
| Nets bundled | 21/110 | 28/110 | MEASURED |
| Nets unbundled | 89 | 82 | MEASURED |
| Channel-var-creating units (bundles + unbundled) | 97 | 90 | MEASURED |
| Reduction vs. 110 unbundled | 11.8% | **18.2%** | DERIVED, exact |
| Primary channel vars (× 204,490 edges) | 19,835,530 | **18,404,100** | DERIVED, exact |
| vs. 22,493,900 unbundled baseline | −11.8% | **−18.2%** | DERIVED, exact |
| `BundleAnalyzer.analyze()` wall | ~391s | 11.68s | MEASURED |
| Construction completes? | No (OOM) | **No (OOM)** | MEASURED |
| Peak RSS at crash | ~5.78GB (near-8GB ceiling, qualitative) | **5.66GB** | MEASURED |
| Wall to crash | ~491s | **187.3s** | MEASURED |

The 8 bundle classes did not grow in *count* — the same geometric
(Jaccard) clusters simply absorbed a few more type-compatible members
each, once the type match stopped over-splitting a "signal"-class cluster
by continuous width/clearance. This directly confirms §0's soundness
framing empirically: the geometry half of "type AND geometry" was already
doing most of the real discriminating work, and loosening only the type
half produced a real but bounded gain, not an order-of-magnitude one.

**Construction still does not complete.** `TEMPER_MODEL_TRACE` progress
instrumentation (added to `_create_bundle_channel_vars` this task — it had
none before, so a bundled-path OOM previously left zero partial data) shows
the crash lands **inside the per-net loop of `_create_bundle_channel_vars`
itself**, at `vars_so_far≈12,400,000` of the ≈18,404,100 channel variables
needed — i.e. it does not even finish creating channel variables, let
alone reach `_create_via_vars` or `_create_capacity_constraints`.

**Via variables are the newly-dominant, still-unaddressed cost.** The
stripped board's skeleton has 153,432 nodes across 4 layers.
`_create_via_vars` is completely bundle-unaware (`ModelBuilder.build()`
calls it unconditionally on every real net, regardless of
`enable_bundling`) — so even a hypothetically-successful bundled
channel-var phase would still need to create `153,432 × 110 ≈ 16.9M` via
variables on top, a term comparable in size to the reduced 18.4M
channel-var term and **larger** than the 4.09M variables this task's fix
actually removed. This confirms, with real numbers, the prior evidence
doc's own recommendation item 4 ("extend `_create_via_vars` to be
bundle-aware... would become the dominant term once channel vars shrink")
— it already is comparable in scale, whether or not channel-var creation
itself is ever fixed to complete.

---

## 4. Is the missing PyO3 binding now the binding constraint?

**No — still masked, exactly as before this task, and for the same
reason.** `ModelBuilder.build()` does not complete on the production
board (§3): the `MemoryError` fires inside `_create_bundle_channel_vars`,
well before `RouterV6Pipeline._run_stage3` would attempt
`from temper_rust_router import solve_topology_rust_bundled`. Restoring
that binding today would not change the production-board outcome at all
— the pipeline never reaches the call. Confirmed directly: `grep
solve_topology_rust_bundled packages/temper-rust-router/src/lib.rs` still
finds nothing (only `solve_topology_rust`, the unbundled entrypoint); the
binding was not restored this task, consistent with the prior evidence
doc's own conditional framing ("only if steps 1–3 make the numbers worth
it").

That said, the wiring *up to* the Rust call is now demonstrably intact
and exercised (§5) — a smaller board, or a future net-batching /
via-var-bundling fix that gets construction under budget, would reach a
real `ImportError` naming the missing symbol immediately, not a silent
fallback or an unrelated crash.

---

## 5. Full-pipeline regression test

The prior evidence doc's own root-cause finding: the bundled encoding's
PyO3 entrypoint was dropped by a 2026-07-08 crate split and went
undetected for three weeks because every test exercising
`enable_bundling=True` instantiated `ModelBuilder` directly — never
`RouterV6Pipeline` — so none of them ever executed the
`from temper_rust_router import solve_topology_rust_bundled` import line
that actually broke.

`test_bundled_full_pipeline.py::test_bundled_pipeline_reaches_rust_solve_boundary`
drives `RouterV6Pipeline._run_stage3` directly (`route_pcb()` still
doesn't expose `enable_bundling`) on a small synthetic 2-net board
constructed to actually bundle (identical footprints → guaranteed
Jaccard=1.0 overlap, matching `TypeSignature`), and asserts:

1. `BundleAnalyzer` really ran as part of the pipeline's own Stage 3
   wiring (its own "Bundle analysis: ..." print, captured via `capsys`,
   not a monkeypatched stand-in) and actually produced a bundle.
2. Control reaches the Rust solve-call boundary — today, that means the
   specific `ImportError` naming `solve_topology_rust_bundled`; this
   assertion should be updated to expect a successful solve if that
   binding is ever restored, but will keep failing loudly for the *right*
   reason (a different exception, or the bundle-analysis print going
   missing) if the wiring rots again in the meantime, which is the
   property that was absent for three weeks.

---

## 6. Recommendation for next steps (unchanged in shape from the prior doc)

Bundling's fix order is now: (1) grouping — done, this task; (2)
vectorization — done, this task; (3) capacity-collision — done, this
task; and the measurement this task adds is that **(1)-(3) alone are not
sufficient** — construction still does not complete, and via variables
(untouched by any of this task's fixes) are now comparable in size to the
reduced channel-var term. Before the PyO3 binding is worth restoring,
either:

- **Extend `_create_via_vars` to be bundle-aware** (prior doc's own item
  4) — the highest-leverage remaining item given via vars are now
  confirmed comparable in scale to channel vars, or
- **Pair with net-batching** (§2 of the prior evidence doc, still
  unimplemented) — corroborated by an existing measured data point (a
  2.6M-variable raw model already survived construction under this same
  8GB cap), and does not depend on further bundling work.

---

## Sources

- `docs/evidence/2026-08-07-sat-model-reduction-options.md` — this task's
  starting point: the narrow-grouping diagnosis, the unvectorized
  `_compute_covered_edges` finding, the capacity-collision bug, and the
  fix-order recommendation this task executes.
- `docs/evidence/2026-08-07-pruned-encoding-measurement.md` — the
  204,490-edge / 22,493,900-variable clean-board baseline this task
  reproduces exactly (§3's stripped-copper methodology note) and compares
  against.
- `packages/temper-placer/src/temper_placer/router_v6/bundle_analyzer.py`
  — `TypeSignature` (§0), `_build_edge_index`/`_compute_covered_edges`
  (§1), `BundleAnalyzer`'s own soundness docstring.
- `packages/temper-placer/src/temper_placer/router_v6/constraint_model.py`
  — `ConstraintModel.bundle_channel_vars` / `add_variable` / `_net_width`
  / `_create_capacity_constraints` (§2), `_create_bundle_channel_vars`'s
  new `TEMPER_MODEL_TRACE` instrumentation (§3).
- `packages/temper-placer/tests/router_v6/test_bundle_analyzer.py` —
  updated T-U1-3, new safety_category-isolation test.
- `packages/temper-placer/tests/router_v6/test_bundled_capacity_constraints.py`
  — collision regression tests (§2).
- `packages/temper-placer/tests/router_v6/test_bundled_full_pipeline.py`
  — full-pipeline wiring regression test (§5).
- `packages/temper-rust-router/src/lib.rs` — confirmed
  `solve_topology_rust_bundled` still absent (§4).
