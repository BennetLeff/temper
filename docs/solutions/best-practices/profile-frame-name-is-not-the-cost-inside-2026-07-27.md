---
title: "A name on a profile frame is not the cost inside it — four performance misattributions in one day"
date: "2026-07-27"
category: best-practices
module: router_v6
problem_type: best_practice
component: performance
severity: high
applies_when:
  - "a profiler reports time inside an opaque native/FFI frame that cProfile or py-spy cannot see into"
  - "a stage-level timer attributes cost to 'the stage' when the stage calls multiple sub-phases internally"
  - "an O(n^2) hypothesis has arithmetic that roughly matches an observed symptom"
  - "comparing a per-stage micro-benchmark against a full end-to-end wall-clock delta"
tags:
  - profiling
  - misattribution
  - opaque-native-frame
  - stage-level-timing
  - instrumentation-over-arithmetic
  - sat-solver
  - manufacturing-drc
---

# A name on a profile frame is not the cost inside it — four performance misattributions in one day

## Context

Four separate performance figures were reported, believed, and acted on
this project before being corrected by direct instrumentation on
2026-07-27. Each misattribution had a plausible name attached to it; none
of the names were the actual cost:

1. **"27 minutes / 9.2 GB" was Stage 5 (manufacturing DRC) entire, not
   `verify_clearance`.** A historical figure attributed a multi-GB memory
   spike to the clearance-check function specifically. Direct
   re-measurement with manufacturing DRC turned **off** still hit **6.93 GB**
   peak RSS at full-board scale — the figure was in the right order of
   magnitude but attributed to the wrong stage entirely: **Stage 3's SAT
   model construction** (a 3.9M-variable, then 42M-CNF-variable class of
   problem) is the dominant memory consumer, not Stage 5, and not
   `verify_clearance` within it.
2. **"Stage 3 SAT = 95.5%" of full-board wall time was real, but the
   opaque native frame it came from conflated three sub-phases — rewrite,
   CNF encoding, and the solve itself — under one name,
   `temper_rust_router.solve_topology_rust`, because cProfile cannot see
   inside a Rust/FFI call.** At the time that number was reported, it was
   read as "the SAT solve dominates." Direct instrumentation
   (`TEMPER_REWRITE_TRACE`, per-phase timers added inside the Rust code)
   found otherwise: at full-board pre-fix scale, essentially none of that
   time was the solve — the actual CDCL search needed 0 conflicts and
   finished in seconds once it started. The overwhelming majority was an
   O(n²) bug inside `rewrite()`, one phase *before* `solve()` is ever
   called. Separately, two independent full-board attempts had `rewrite()`
   still running past 250 seconds before `solve()` was reached at all —
   the frame's name said "solve," the clock inside it was overwhelmingly
   a different phase with a different fix.
3. **"Manufacturing DRC ~0.7s" (an isolated stage-level timer on an
   11-net partial route) became roughly 6–7× the routing-only wall time
   end-to-end**, once measured at matched completion rate on a real,
   170-component board (~278–333s of manufacturing DRC on top of a ~56s
   route). The isolated per-call timer was not wrong about what it
   measured; it was measuring a scale two orders of magnitude smaller than
   the board the figure was later quoted against.
4. **A supplied O(n²) hypothesis had arithmetic that matched the symptom,
   and was refuted by instrumentation anyway.** The named loop —
   `subsume_capacity`'s pairwise comparison, `39,544² / 2 ≈ 782M` pairs at
   a few hundred nanoseconds each, arithmetically close to an observed
   ~250-second-plus hang — measured **113–159 microseconds** when
   instrumented directly, because every one of the 20,734
   `CapacityConstraint`s on the board turned out to have a **unique**
   `channel_id` (`size_histogram = {1: 20734}`), so the "pairwise" loop did
   `n` trivial `i==j`-skip iterations, not `n²/2`. The real cost was **90
   lines further into the same function**: a "rebuild capacity
   constraints" step doing an O(N) linear scan with an O(m·log m)
   `BTreeSet` rebuild-and-compare *for every candidate*, measured directly
   at **144.34 seconds for a single call, at just 15 nets** — because a
   pre-existing, already-known index (`orig_idx`, sitting unused in the
   very tuple being destructured — the leading underscore was the tell)
   made the search unnecessary. `cap_infos[i].orig_idx == i` held
   unconditionally, so the O(N²·m log m) search collapsed to an O(1)
   lookup: **144.34s → 62.4ms**, a ≈2,313× reduction, with the same test
   suite passing and the same final constraint counts before and after.

Full detail: `docs/evidence/2026-07-27-first-route-and-profile.md`,
`docs/evidence/2026-07-27-stage3-model-and-rewrite.md`,
`docs/evidence/2026-07-27-committed-route.md`,
`docs/evidence/2026-07-27-sat-bound-tradeoff.md`.

## Guidance

1. **An opaque FFI/native frame's name in a profiler is a label for
   everything that happens inside the call, not a description of what
   dominates it.** cProfile cannot see past a single native call boundary
   — if that call internally does phase A, then B, then C, the profiler
   attributes 100% of the wall time to "the function," and a reader fills
   in the blank with whatever the function's name suggests. Instrument
   *inside* the native code (a cheap env-var-gated trace, timing each
   internal phase) before believing which phase is expensive.
2. **A stage-level timer measures the stage, not the function whose name
   happens to match the historical bug report.** "27 min / 9.2 GB" was
   real and was Stage 5's memory footprint; it was not, on remeasurement,
   attributable to the one function inside Stage 5 that everyone assumed.
   Re-attribute by isolating the specific function with its own timer
   before naming it as the cost driver in a fix's justification.
3. **Arithmetic that matches a symptom is a hypothesis, not a finding.**
   `39,544² / 2 ≈ 782M` comparisons landing close to an observed ~250s hang
   is a good reason to *instrument* that loop — it is not evidence the loop
   is the cost until the instrumentation says so. Here it was refuted at
   113 microseconds, and the real O(n²) bug was 90 lines away in a
   completely different step of the same function.
4. **A micro-benchmark and a full-scale measurement answer different
   questions; do not quote one as if it were the other.** A 0.7s figure
   on an 11-net partial route and a 6–7× full-board wall-time multiplier
   are both correct measurements — of different things. State the scale a
   number was measured at every time it is repeated.
5. **When a "tell" is sitting in the code (an unused variable, a leading
   underscore, a value already computed and discarded) — that is often the
   fix, not a hypothesis to test.** `_orig_idx` was already the correct
   index; the search that replaced an O(1) lookup with an O(N) scan
   existed only because that field was ignored.

## Why This Matters

All four instances shared the same shape: a plausible number, correctly
measured at the scale and in the way it was measured, generalized past
what it could support. None involved a measurement error — the 27-minute
figure was real, the 95.5% figure was real, the 0.7s figure was real, and
the O(n²) arithmetic genuinely matched the symptom's order of magnitude.
The failure was entirely in attribution: which function, which phase,
which scale a real number actually describes. Each of these cost real
engineering time before direct instrumentation corrected it — roughly a
month of prior profiling attention aimed at the wrong kernel (A* search)
before Stage 3's SAT phase was even identified as the dominant cost, and
then a further round of attention aimed at "the SAT solve" before the
rewrite-phase bug inside the same opaque frame was found. The fix, once
correctly attributed, was small in every case (a config flag, an O(1)
lookup) — the expensive part was always the diagnosis, not the repair.

## When to Apply

- Before repeating any profiling figure that crossed a native/FFI call
  boundary — confirm what's inside that call was actually decomposed, not
  assumed from the call's name.
- Before accepting a stage-level timer's implicit attribution to "the
  function that stage is named after" — isolate that specific function
  with its own timer.
- Before implementing a fix for a named O(n²) loop whose arithmetic merely
  matches an observed symptom — instrument the actual loop directly before
  writing the fix.
- Before quoting a micro-benchmark figure (small input, isolated call) in
  a discussion about full-scale, end-to-end behavior — restate the scale
  every time, and re-measure at the scale that matters before trusting the
  multiplier.

## Examples

```
# The opaque frame that hid the real cost:
ncalls  tottime  cumtime  function
     1   100.002  100.002  {built-in method
                            temper_rust_router.temper_rust_router.solve_topology_rust}
# Read as: "96.5% of Stage 3 is the CaDiCaL SAT solve."
# Actual, once instrumented per-phase inside the Rust code:
#   rewrite() (pre-fix, full-board scale): ~1,000-1,800s (the O(n^2) bug)
#   solve()   (post-fix, full-board scale): 27.78s of a 52.67s total
# The name on the frame was "solve"; the cost inside it was "rewrite."
```

```rust
// The tell that was already sitting in the code:
for (var_sorted, (_orig_idx, tight_k)) in dedup_map {
//                ^^^^^^^^^ unused -- the leading underscore is the signal
    let info = cap_infos.iter().find(|info| { /* O(N) rebuild + compare */ });
    // ...
}
// cap_infos[i].orig_idx == i holds unconditionally (cap_infos is built by
// .map() over caps, preserving order) -- the search was never necessary.
for (_var_sorted, (orig_idx, tight_k)) in dedup_map {
    let info = cap_infos.get(orig_idx).ok_or_else(...)?;   // O(1)
}
// 144.34s -> 62.4ms at 15 nets; same test suite, same final constraint counts.
```

## Related

- `docs/solutions/best-practices/profiling-cascade-algorithms-sampling-insufficient-2026-06-30.md`
  — a sibling profiling failure with a different mechanism: sampling on an
  "easy" subset misses a cascade that only appears under full load, rather
  than an opaque frame hiding which internal phase dominates.
- `docs/solutions/best-practices/benchmark-before-optimizing-state-the-falsifier-2026-07-26.md`
  — the falsifier-first discipline this incident's "arithmetic matched the
  symptom" step should have applied before writing any fix.
- `docs/evidence/2026-07-27-first-route-and-profile.md` — the Stage 3
  dominance finding, the 6.93 GB peak-RSS re-attribution, and the isolated
  0.7s manufacturing-DRC timer.
- `docs/evidence/2026-07-27-committed-route.md` — the full-board,
  matched-completion 6-7x manufacturing-DRC wall-time multiplier.
- `docs/evidence/2026-07-27-stage3-model-and-rewrite.md` — the refuted
  O(n²) hypothesis, the real rebuild-loop bug, and the 144.34s -> 62.4ms fix.
- `docs/evidence/2026-07-27-sat-bound-tradeoff.md` — the two independent
  full-board runs where `rewrite()` ran past 250s before `solve()` was ever
  reached.
