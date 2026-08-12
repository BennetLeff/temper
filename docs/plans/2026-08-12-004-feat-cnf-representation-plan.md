---
title: CNF-Layer Representation — Plan
type: feat
date: 2026-08-12
topic: cnf-representation
artifact_contract: ce-unified-plan/v1
artifact_readiness: design-and-prototype
execution: code
product_contract_source: measurement
status: draft
swept: null
swept_basis: null
---

# CNF-Layer Representation — Plan

## Goal Capsule

**Objective:** Design (not implement) fixes to the SAT pipeline's CNF-layer
memory representation — `CnfFormula.clauses: Vec<Vec<i32>>` and the
`var_names: Vec<String>` `encode_to_cnf` returns alongside it
(`packages/temper-rust-router-core/src/encoding.rs:11-15,79-227`) — the
layer plan `2026-08-12-002` flagged, honestly and explicitly, as an open
question after fixing the model layer (U1 there): *"the downstream CNF is
real Rust memory... `Vec<Vec<i32>>` for ~450M clauses is the same class of
representation bug, one layer down."* This plan measures that layer,
verifies whether packing it (plus the already-scoped model-layer fix) makes
the unbatched monolithic SAT solve fit in memory, and states what CaDiCaL
itself costs — because the task and the honest reading of `2026-08-12-002`
both flag that solver-internal memory could make the whole representation
question moot.

**Verdict, stated first, per this task's own instruction to lead with a
dominant-cost finding.** **It is moot, mostly.** MEASURED (full methodology
and all four numbers below in
`docs/brainstorms/2026-08-12-cnf-representation-options.md`, reproduced
from real code — real `encode_to_cnf`, real `rustsat-cadical` 0.7.5, real
`/proc/self/status` `VmRSS`, never `sys.getsizeof` or a guess):

- Our own clause list, `CnfFormula.clauses: Vec<Vec<i32>>`, costs
  **56.00 bytes/clause** today; a flat `Vec<i32>` literal pool + `Vec<u32>`
  clause-offset index costs **13.81 bytes/clause** — a real **4.06×**
  reduction, exact and reproducible at two scales 10× apart.
- A second, unnamed-by-the-task finding: `var_names: Vec<String>`
  (`encoding.rs:217`) allocates a heap `String` per SAT variable —
  including every Sinz sequential-counter auxiliary variable
  (`"sc_r{i}_{j}"`, `encoding.rs:44-46`) — that **nothing downstream reads**
  (`solve_with_cadical`'s `_var_names` parameter is unused,
  `solver.rs:60`; `extract_topology` only matches a `"uses_"` prefix no aux
  name has, `extraction.rs:44`). MEASURED **56.00 bytes/aux-var** for the
  waste, **0.00** to carry no name.
- **CaDiCaL itself, loading the same real clauses via the exact production
  `add_clause` path (`solver.rs:70-88`), costs 152–175 bytes/clause** — 2.7×
  our *unpacked* representation and 11–13× the *packed* one, and this
  ratio, not our packing choices, decides whether the monolith fits.

At the current 204,490-edge skeleton (9.9× the 2026-07-27 baseline plan
`2026-08-12-002` measured, same scaling factor reused, DERIVED not
independently re-measured — see Confidence in the brainstorm): **best case,
everything packed and the model-layer fix (U1 of `2026-08-12-002`) landed,
is ≈128–146 GB — 91.5–92.6% of it CaDiCaL's own clause storage.** Today
(model layer fixed, CNF layer not) it is ≈182–200 GB. **Packing moves the
number but not the verdict: the monolith does not fit, on any realistic
machine, either way.** The net-batching loop is not being kept because our
representation is inefficient — it was already fixed enough on our side
that CaDiCaL's own floor is now the binding constraint — it is being kept
because CaDiCaL cannot hold ~770M clauses in bounded memory, and no
representation change on our side of the `rustsat` FFI boundary touches
that number.

**This does not mean "do nothing."** Fixing the dead aux-variable-name
allocation (§2 of the brainstorm) is free — a deletion of proven-dead work,
not a tradeoff — and worth **21.1 GB** at full scale, applicable at *any*
batch size the moment `AtMostK` is encoded at all, including a future
raised-batch-size world (see "Interaction with the capacity finding,"
below). Packing the clause list is a real, mechanical, low-risk **32.5 GB**
win with an existing property-test harness
(`encoding.rs`'s `prop_output_sizes_consistent`,
`prop_clause_indices_in_bounds`, `prop_no_empty_clauses`,
`prop_no_tautological_clause`, `prop_empty_constraints_no_clauses`) to lean
on for regression coverage. Both are scoped here as independently landable
units; neither is scoped as "the fix that makes the monolith fit," because
neither does.

## Product Contract

### Summary

This plan does two things, both representation-only, and explicitly does
**not** attempt to change CaDiCaL's own memory footprint or the
batch-loop/monolith decision, which the measurement above shows is not a
representation question:

1. **Delete the dead auxiliary-variable-name allocation** (U1). Free,
   independent of every other decision in this document, and the highest
   value-per-line-of-code change identified in this investigation.
2. **Pack `CnfFormula.clauses` into a flat `Vec<i32>` + `Vec<u32>`
   clause-offset index** (U2). A real, bounded, mechanical 4.06× reduction
   on our side of the FFI boundary, worth doing on its own terms even
   though it does not change whether the monolith fits.

A third unit (U3) instruments both changes' actual effect on the *batched*
production path, which today encodes essentially zero `AtMostK` clauses
(`batch_size=10 < K≈17`, per the concurrent capacity-encoding finding —
see "Interaction with the capacity finding") — so U1/U2's measured wins
are real but currently *latent*: they matter today only for a monolithic or
future raised-batch-size solve, not for the batched path as it runs in
production right now. U3 makes that latency visible and re-checkable rather
than assumed.

**Explicitly out of scope, and named as a separate, harder project**:
anything that would change CaDiCaL's own per-clause cost — a different
cardinality encoding (totalizer, commander, or other AtMostK families with
a smaller aux-var/clause footprint than Sinz's sequential counter for this
K≈17, n≈108-110 regime), or restructuring the monolithic solve into
CaDiCaL-scale chunks (which is, functionally, a form of net-batching, not a
data-representation change). This is a solver/encoding-algorithm question,
Option 4 in the brainstorm, and is not scoped here.

### The measurement (full detail in the brainstorm; summarized for the plan)

Method: a scratch Cargo project path-depending on
`packages/temper-rust-router-core` as a library (pure Rust, no `pyo3`;
`sat` is its only non-default-off feature, pulling `rustsat`/
`rustsat-cadical` 0.7.5 exactly as pinned in that crate's `Cargo.lock`).
Nothing under `packages/**` was edited; the probe only reads the crate as a
dependency. Real `InternalConstraintModel`, real `encode_to_cnf`, real
`CaDiCaL::default()` + `add_clause` (verbatim copy of
`solver.rs:70-88`'s loop), real `/proc/self/status` `VmRSS`. All five probe
source files are committed at
`docs/evidence/2026-08-12-cnf-repr-probe-{common,lumped,isolated}.rs`,
`docs/evidence/2026-08-12-cadical-memory-probe.rs`,
`docs/evidence/2026-08-12-varnames-waste-probe.rs`, reproducible the same
way plan `2026-08-12-002`'s probe scripts are.

| layer | today | packed/fixed | ratio | full-scale (≈770.3M clauses) today → packed |
|---|---:|---:|---:|---|
| clause list (`Vec<Vec<i32>>` → flat+offsets) | 56.00 B/clause | 13.81 B/clause | 4.06× | 43.1 GB → 10.6 GB |
| aux var names (`Vec<String>` → none) | 56.00 B/aux-var | 0.00 B/aux-var | ∞ | 21.1 GB → 0 GB |
| CaDiCaL clause storage (measured, not changed by this plan) | 152–175 B/clause | *(unchanged)* | — | 117.2–135.0 GB either way |
| model layer (CITED, `2026-08-12-002` U1, not this plan) | 326.7 B/var | 8.9 B/var | 38× | 7.35 GB → 0.2 GB |

**Total: ≈182–200 GB today (model layer already fixed) → ≈128–146 GB after
this plan, CaDiCaL holding 91.5–92.6% of the packed total either way.**
Confidence is **high** on the qualitative verdict (CaDiCaL dominates,
packing does not make the monolith fit) because that share is large enough
to absorb a ±20–30% error in the edge-count extrapolation without changing
which side of "fits" the total lands on; **medium** on the exact GB
figures, since the 204,490-edge current-skeleton figure and the 9.9×
linear-scaling assumption are both inherited/DERIVED rather than
independently re-measured this task (same caveat plan `2026-08-12-002`
itself raised and left to a future re-measurement); **medium-low**
specifically on the full-scale CaDiCaL number, since it is extrapolated
from two measured points spanning one order of magnitude (152.12 B/clause
at 7.56M clauses, 175.25 B/clause at 22.7M clauses, a real ~15%
super-linear trend) to a target two orders of magnitude beyond the smaller
point.

### Interaction with the capacity finding

`docs/plans/2026-08-12-003-fix-sat-capacity-encoding-plan.md` has not
landed on any branch (`git fetch origin && git log --all --oneline --
docs/plans/2026-08-12-003-fix-sat-capacity-encoding-plan.md` returns
nothing as of this writing; checked per this task's instruction before
concluding absence). The task's own description of it — production
`batch_size=10 < K≈17` means `encoding.rs:148`'s
`max_nets < var_indices.len()` guard never fires, so the batched path
encodes **zero** `AtMostK` clauses and reports 0 conflicts/0 decisions — is
corroborated by this plan's own measurements: every number above is for
the *monolithic* shape (`n=110` nets per capacity constraint), which is
precisely the shape the production batched path never constructs.

**If `2026-08-12-003` raises `DEFAULT_BATCH_SIZE` above K:** per-batch
clause count jumps from today's ~0 to a **bounded-by-batch-size** (not
bounded-by-board-size) quantity, using the same Sinz shape with `n ≤ B`
(the new batch size) instead of `n = 110`. Both U1 and U2 in this plan
apply identically per-batch, at the same measured bytes-per-item ratios —
but the *absolute* GB at stake per batch is unmeasured here, because it
depends on a batch size this plan does not know. **R5 below requires
re-running the committed probes against whatever batch size
`2026-08-12-003` lands on**, rather than assuming today's near-zero SAT
footprint, or this plan's, continues to hold.

### What would change the board — flagged deliberately

Both U1 and U2 are stated, and must remain, **representation-only**: same
literal content, same clause order, same variable assignment semantics —
only the container changes. The correctness bar is the same one
`2026-08-12-002` uses: a byte-identical `temper_routed.kicad_pcb` against
the baseline in `docs/evidence/2026-08-12-board-recipe-reproducibility.md`
(not yet on `origin/main` — commit `0659ef39b`; **168 footprints, 3,349
segments, 56 vias, 70 zones, 80/105 nets routed**), run with
`--net-batching` per that plan's R3/R7 (byte-equality is asserted only
batched-vs-batched, never monolith-vs-batched — the two are different
algorithms at today's batch size, per the capacity finding, and this plan
does not change that).

- **U1 (dead-name deletion) is representation-only** in the strongest
  sense: the task explicitly proves the removed data is never read, so
  there is no behavior to preserve beyond "still compiles and still
  indexes correctly for primary variables."
- **U2 (clause-list packing) is representation-only** by construction (same
  literals, same order) but touches more call sites (§ Units, below), so
  its risk is in *missing* a consumer, not in *changing* semantics at a
  consumer it does reach.
- **Neither unit changes `DEFAULT_BATCH_SIZE`, `encoding.rs:148`'s guard,
  or any encoding algorithm.** `2026-08-12-003` owns that; this plan is
  strictly upstream/orthogonal to it and must not be read as taking a
  position on raising the batch size.

### Requirements

Requirement IDs are stable and become `@req(2026-08-12-004, Rn)`.

- **R1.** `encode_to_cnf` does not allocate a `String` name for any
  auxiliary variable it creates (Sinz sequential-counter variables,
  `encoding.rs:41-48`, `sc_r{i}_{j}`). Primary-variable names (those
  registered via `add_var_with_net`, `encoding.rs:91-106`) are unaffected.
  **Check:** a repeat of `docs/evidence/2026-08-12-varnames-waste-probe.rs`
  reports **0.00 bytes/aux-var** against the fixed code path (today: 56.00);
  `rg 'SatVariable::new\(format!\("sc_r' packages/temper-rust-router-core/src/encoding.rs`
  still finds the aux-var construction site but the resulting `var_names`
  entry for that index is empty/absent rather than a formatted string.
- **R2.** `CnfFormula.clauses: Vec<Vec<i32>>` is replaced by a flat
  `literals: Vec<i32>` + `clause_offsets: Vec<u32>` pair (or equivalent
  CSR-style representation). **Check:** a repeat of
  `docs/evidence/2026-08-12-cnf-repr-probe-isolated.rs`'s arm-C
  methodology against the real (not synthetic) post-change `CnfFormula`
  reports **≤ 15 bytes/clause** (against 56.00 today); `rg 'Vec<Vec<i32>>'
  packages/temper-rust-router-core/src/encoding.rs` returns no hit in the
  `CnfFormula` struct definition.
- **R3.** Every consumer of `CnfFormula.clauses` is converted to the new
  representation, not left silently reading a stale field: `solver.rs`'s
  `solve_with_cadical` clause-loading loop (`:73-88`), `bmc.rs`'s CaDiCaL
  construction (`:131,163`), `equivalence.rs`'s differential-solve call
  sites, `property_campaigns.rs`'s CNF-shape property tests
  (`:1099-1190`), and `encoding.rs`'s own `#[cfg(test)]` exhaustive DPLL
  solver (`:254-327`, used by `exhaustive_at_most_k_n1_to_n8`) and
  proptest module (`:396-517`). **Check:** `cargo build --manifest-path
  packages/temper-rust-router-core/Cargo.toml` and `cargo build
  --manifest-path packages/temper-rust-router/Cargo.toml` succeed with no
  remaining reference to `Vec<Vec<i32>>`-shaped clause iteration; `cargo
  test --manifest-path packages/temper-rust-router-core/Cargo.toml`
  passes unchanged, including the five `prop_*` proptests in
  `encoding.rs`.
- **R4.** The board is unchanged. **Check:** `diff` empty and sha256 equal
  against the `2026-08-12-board-recipe-reproducibility.md` baseline, for
  the full recipe run with `--net-batching` (same verification protocol
  `2026-08-12-002` §"Verification protocol" defines — reused, not
  reinvented).
- **R5.** Once `2026-08-12-003` lands (or its batch-size decision is
  otherwise made), the probes committed by this plan
  (`2026-08-12-cnf-repr-probe-isolated.rs`, `2026-08-12-cadical-memory-probe.rs`)
  are re-run with `NETS` set to the landed batch size and `K` to whatever
  capacity bound applies at that size, and the resulting per-batch GB
  figure is recorded. **Check:** a follow-up evidence doc (or an
  addendum to this plan) reports the re-measured number; this plan's own
  §"Interaction with the capacity finding" is not treated as satisfied
  until that re-measurement exists.
- **R6.** No requirement in this plan changes `DEFAULT_BATCH_SIZE`,
  `encoding.rs:148`'s guard, or any cardinality-encoding algorithm.
  **Check:** `git diff` for any unit in this plan touches only
  `CnfFormula`'s definition, its constructors inside `encode_to_cnf`, and
  its consumers' iteration code — never `encode_at_most_k`'s clause-*count*
  logic (`:21-76`) or the `max_nets < var_indices.len()` guard (`:148`).
- **R7.** Peak RSS of a full batched route is measured and reported before
  and after U1+U2 land, by the same `/proc/<pid>/status` `VmHWM` mechanism
  `2026-08-12-002`'s R4 uses. Given the capacity finding (today's batched
  path encodes ~0 `AtMostK` clauses), this number is expected to show
  little or no change at today's `batch_size=10` — **that null result is
  itself the correct, honestly-reported outcome**, not a failure of the
  plan, and confirms the "latent until batch size crosses K" framing
  above rather than contradicting it.

### Verification protocol (applies to every unit)

Reused verbatim from `2026-08-12-002`, not reinvented:

```
# full recipe, twice, concurrently, then:
diff  route_a/temper_routed.kicad_pcb route_b/temper_routed.kicad_pcb   # must be empty
sha256sum route_a/... route_b/...                                       # must match
diff  route_a/temper_routed.kicad_pcb baseline/temper_routed.kicad_pcb  # must be empty
```

with `python3 scripts/route_board.py --runs N --net-batching`. Baseline: 168
footprints / 3,349 segments / 56 vias / 70 zones / 80 of 105 nets. This
plan's units all run under `--net-batching` (R6: no batch-size change), so
the byte-identity bar is meaningful and achievable — unlike a
monolith-vs-batched comparison, which `2026-08-12-002` correctly forbids
(its R7).

## Units

### U0 — Pin the baseline (shared with `2026-08-12-002`; do not re-regenerate if already pinned)

If `2026-08-12-002`'s U0 has already produced a pinned baseline artifact and
sha256 for the current commit, reuse it — do not regenerate. If not,
regenerate per that plan's U0 exactly (two concurrent runs, `diff` empty,
counts match 168/3,349/56/70/80). **Effort:** 0 (reuse) or 0.5 day
(regenerate), mostly wall-clock.

### U1 — Delete the dead auxiliary-variable-name allocation (R1)

In `encode_to_cnf` (`encoding.rs:79-227`), stop formatting and cloning a
`String` for each Sinz auxiliary variable `encode_at_most_k` creates
(`:41-48`). The cleanest form: give `SatVariable` (or the `var_map` entries
`encode_at_most_k` pushes) an `Option<String>` name, `None` for auxiliary
variables, and have the final `var_names: Vec<String>` construction
(`:217`) emit an empty string (or, if a signature change to
`Vec<Option<String>>` is acceptable to every consumer, `None`) for those
indices rather than a formatted `"sc_r{i}_{j}"`. Prefer **not** changing
`encode_to_cnf`'s public return signature (`Vec<String>`, not
`Vec<Option<String>>`) unless a consumer genuinely needs to distinguish
"no name" from "empty name" — `extract_topology`'s `strip_prefix("uses_")`
check already treats both identically, so the minimal, lowest-risk version
of this unit keeps the signature and just stops paying for content nothing
reads.

Independently landable, touches only `encoding.rs`, and is the highest
value-per-line-of-code change in this plan. **Verified by:** R1's probe
re-run; R4 board byte-identity; existing `encoding.rs` unit/proptest suite
unchanged. **Effort: 1–2 days.** Risk: low — the "never read" claim is
mechanically checkable (`rg '_var_names'`,
`rg 'strip_prefix\("uses_"\)'`) and R4's byte-identity test is a strong,
cheap backstop if this analysis missed a consumer.

### U2 — Pack `CnfFormula.clauses` into flat `Vec<i32>` + `Vec<u32>` offsets (R2, R3)

Replace `CnfFormula { clauses: Vec<Vec<i32>>, .. }`
(`encoding.rs:11-15`) with a CSR-style pair (`literals: Vec<i32>`,
`clause_offsets: Vec<u32>`, `clause_offsets.len() == clauses.len() + 1`).
Two implementation strategies, both to be measured rather than assumed
before choosing:

  (a) **Build-then-flatten.** Keep `encode_at_most_k` and the constraint
      loop pushing into a temporary `Vec<Vec<i32>>` exactly as today, then
      flatten once at the end of `encode_to_cnf` into the packed form.
      Simpler, smaller diff, but pays a transient double-allocation
      (both representations briefly resident) during construction — worth
      quantifying with the same probe methodology before assuming it is
      negligible.
  (b) **Direct packed construction.** Rewrite `encode_at_most_k` and the
      constraint-encoding loop to push literals directly into the flat pool
      and record offsets as clauses complete, never materializing the
      intermediate `Vec<Vec<i32>>` at all. More invasive (touches
      `encode_at_most_k`'s internals, not just the type it writes into),
      but avoids the transient double-allocation entirely — likely the
      right choice given this plan's own measured concern about
      construction-time allocator behavior (the "confound found and
      corrected" callout in the brainstorm), but pick with a real
      measurement, not a preference.

Then convert every consumer (R3's list: `solver.rs`, `bmc.rs`,
`equivalence.rs`, `property_campaigns.rs`, `encoding.rs`'s own test DPLL
solver and proptest module) from `&[Vec<i32>]`-shaped iteration to
CSR-window iteration (`offsets.windows(2)` or equivalent).

**Verified by:** R2's probe re-run against the *real* post-change
`CnfFormula` (not the synthetic isolated probe — R2's check explicitly
calls for measuring the real type); R3's build/test-suite check across
both dependent crates; R4 board byte-identity. **Effort: 5–9 days**
(materially more than U1 — this touches five files' worth of clause
iteration, and choosing between strategies (a)/(b) above needs its own
small measurement pass before the main implementation starts). Risk:
low-medium — mechanical but wide; the existing five `prop_*` proptests in
`encoding.rs` are the cheapest available regression net and should be the
first thing re-run against the new type, before the board-level R4 check.

### U3 — Instrument U1+U2's actual effect on the batched production path, and re-scope against the capacity finding (R5, R7)

Run the existing peak-RSS measurement (`_watch_peak_rss_kb` or its Rust
successor from `2026-08-12-002`'s U3/U4, whichever has landed by the time
this unit runs) before and after U1+U2, on the real batched board recipe
at today's `batch_size=10`. Report the delta honestly, including if it is
near-zero (R7 — expected, given the capacity finding that `AtMostK` is not
encoded at this batch size today). Then, once `2026-08-12-003` lands or its
batch-size decision is otherwise settled, re-run
`2026-08-12-cnf-repr-probe-isolated.rs` and `2026-08-12-cadical-memory-probe.rs`
with `NETS`/`K` set to that decision's actual numbers (R5), and record the
result as a follow-up evidence document.

**Verified by:** R7's before/after RSS report exists and is honest about a
null result if that is what is measured; R5's post-`2026-08-12-003`
re-measurement exists once that plan lands (this unit may need to be
revisited/re-run rather than closed at the time this plan is written, since
`2026-08-12-003` has not landed — see Outstanding Questions).
**Effort: 1–2 days** for the immediate before/after measurement;
**0.5–1 day** for the follow-up re-measurement once `2026-08-12-003` lands
(separate, later work, not blocking this plan's own completion).

### Sequencing

```
U0 ──> U1 ──> U2 ──> U3 (immediate half: R7)
                       └──> U3 (deferred half: R5, blocked on 2026-08-12-003 landing)
```

U1 and U2 are independently landable and do not depend on each other's
completion (both touch `encoding.rs` but in disjoint regions — U1 the
`var_names` construction, U2 the `clauses` field and its consumers — so
land in either order, or in parallel on separate branches, with R4's
byte-identity check gating each). **Total for U0–U3's immediate work:
7.5–13.5 days.** U3's deferred half is explicitly not counted in that
total, since it is gated on a different, unlanded plan's decision.

## Scope Boundaries

**Explicitly not in this plan**, each a real, separate project:

- **CaDiCaL's own memory** — Option 4 in the brainstorm. A different
  cardinality encoding or a CaDiCaL-scale-chunking restructure would be the
  only changes that move the "does the monolith fit" verdict, per this
  plan's own measurement (§ "The measurement," CaDiCaL = 91.5–92.6% of the
  packed total). Not attempted here; flagged so this plan's "packed but
  does not fit" conclusion is not mistaken for "and nothing further can be
  done."
- **`DEFAULT_BATCH_SIZE` or any capacity-encoding change** — owned by
  `2026-08-12-003`. This plan is strictly orthogonal (R6) and its units
  apply unchanged regardless of what that plan decides, modulo U3's
  deferred re-measurement (R5).
- **The model layer (`ConstraintModel`, `Vec<Py<PyAny>>`)** — owned by
  `2026-08-12-002`'s U1/U2, CITED here, not re-scoped or re-implemented.
- **Net-batching's subprocess-vs-in-process-loop question** —
  `2026-08-12-002`'s U3/U4. This plan's measurement (monolith does not fit
  either way) is an input to that decision but does not make it; the batch
  *loop* staying is a conclusion this plan's measurement supports, but
  whether it stays a Python `multiprocessing` subprocess or becomes a Rust
  `for` loop is that plan's question, not this one's.

## Dependencies / Assumptions

- **Assumes** the 204,490-edge current-skeleton figure still holds — same
  assumption `2026-08-12-002` flagged and left open (it predates the T2
  footprint change per that plan's own "Dependencies / Assumptions"). If
  a future re-measurement of the model layer (that plan's U2) finds a
  different edge count, this plan's full-scale GB figures scale with it
  linearly and should be recomputed, not assumed unchanged.
- **Assumes** K (the capacity bound, ≈17) is a property of physical channel
  width vs. track width and stays roughly constant as skeleton edge count
  grows — reasonable given how it is derived (capacity/slack/min-track-width
  per channel, not a function of how many channels exist) but not
  independently verified this task.
- **Depends on** `2026-08-12-002`'s U1 (model-layer fix) having landed, or
  landing before/alongside this plan's units — this plan's "best case" GB
  figures assume the model layer is already packed (8.9 B/var, not
  326.7 B/var). If U1 has not landed, add the model layer's own 7.15 GB
  delta back into every full-scale total in this plan.
- **Depends on** the recipe staying deterministic — every acceptance test
  in this plan is a `diff`, same as `2026-08-12-002`; if determinism
  regresses, this plan is blocked, not degraded.
- **Depends on** `2026-08-12-003` for R5/U3's deferred half specifically —
  not for U1/U2, which are self-contained and independently verifiable
  today.

## Outstanding Questions

1. **Does packing choice (a) vs (b) in U2 matter measurably?** Deferred to
   U2's own implementation-time measurement rather than decided here — see
   U2's description.
2. **Should `SatVariable`'s `description: String` field
   (`types.rs:74-77`, always `""` for CNF-layer variables per
   `SatVariable::new(name, "")` at `encoding.rs:101`) be removed or
   `Option`-ized too?** Not measured this task — it costs a `String`
   struct's worth of stack space per variable (24 bytes) but, being always
   empty, allocates no heap for it (`""`.into()` does not allocate); the
   win would be smaller than either U1 or U2 and was not prioritized for
   measurement here. Worth a follow-up probe if U1/U2's actual landed
   savings are smaller than projected and further reduction is wanted.
3. **What is CaDiCaL's memory cost *during* an unbounded or high-conflict-limit
   search**, as opposed to clause loading? This plan's §3 measurement
   (both here and in the brainstorm) deliberately isolates clause-loading
   cost and notes only that a bounded (`conflict_limit=20_000`, production
   default) solve added little beyond it for the one shape tested. A
   harder, more contested instance could grow the learned-clause database
   materially — this is a dynamic, not representation, cost, and is not
   measured or scoped here.
4. **Re: R5/U3's deferred half** — this plan cannot close R5 today because
   `2026-08-12-003` has not landed. Whoever executes this plan should treat
   U3's deferred half as a standing follow-up item, not silently drop it
   once U1/U2/U3's immediate half are done.

## Sources / Research

- MEASURED this task:
  `docs/evidence/2026-08-12-cnf-repr-probe-common.rs`,
  `docs/evidence/2026-08-12-cnf-repr-probe-lumped.rs`,
  `docs/evidence/2026-08-12-cnf-repr-probe-isolated.rs`,
  `docs/evidence/2026-08-12-cadical-memory-probe.rs`,
  `docs/evidence/2026-08-12-varnames-waste-probe.rs`,
  `docs/evidence/2026-08-12-cnf-probe-Cargo.toml.txt`
- `docs/brainstorms/2026-08-12-cnf-representation-options.md` — full
  measurement methodology, the confound-found-and-corrected writeup, the
  four ranked options, and the confidence breakdown this plan's numbers
  are drawn from.
- CITED, not re-derived:
  `docs/plans/2026-08-12-002-feat-router-orchestration-rust-plan.md`
  (branch `spike/router-orchestration-rust`, unlanded, commit `6b669db2a`)
  — model-layer 326.7/8.9 B/var figures, the 2026-07-27 baseline
  (42,145,777 vars / 78,107,180 clauses / 20,734 constraints), the K≈17
  capacity derivation, the 204,490-edge current-skeleton figure, the 9.9×
  scaling factor, and the verification-protocol/byte-identity methodology
  this plan reuses.
- `docs/evidence/2026-08-07-sat-model-reduction-options.md`,
  `docs/evidence/2026-08-07-router-oom-diagnosis.md` — origin of the
  204,490-edge and 42,145,777-var/78,107,180-clause figures (both already
  on `main`).
- `docs/evidence/2026-08-12-board-recipe-reproducibility.md` (branch
  `diagnose/clearance-regression`, unlanded, commit `0659ef39b`) — the
  verification baseline.
- Code: `packages/temper-rust-router-core/src/encoding.rs:11-15,21-76,79-227` ·
  `packages/temper-rust-router-core/src/solver.rs:58-88` ·
  `packages/temper-rust-router-core/src/extraction.rs:18-58` ·
  `packages/temper-rust-router-core/src/types.rs:17-92` ·
  `packages/temper-rust-router-core/src/bmc.rs:17,58,131,163` ·
  `packages/temper-rust-router-core/src/equivalence.rs:288-452` ·
  `packages/temper-rust-router-core/src/property_campaigns.rs:1056-1190` ·
  `packages/temper-placer/src/temper_placer/router_v6/_pipeline_core.py:67`
- Checked and found absent (per this task's instruction to verify before
  concluding absence): `git fetch origin && git log origin/main --oneline -5`,
  `git log --all --oneline -- docs/plans/2026-08-12-003-fix-sat-capacity-encoding-plan.md`
  — no commit on any branch as of this writing.
