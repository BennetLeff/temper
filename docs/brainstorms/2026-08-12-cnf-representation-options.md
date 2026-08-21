<!-- provenance: branch spike/cnf-representation, from origin/main at 66a277d94, worktree
/home/bennet/Desktop/temper-worktrees/cnf-representation. Companion to
docs/plans/2026-08-12-004-feat-cnf-representation-plan.md on the same branch. No pcb/**
touched or modified at any point (verified via `git status --short pcb/` before/after).
Measurement probes ran as a standalone scratch Cargo project outside this repo
(path-dependency onto packages/temper-rust-router-core as a library only -- nothing in
that crate or anywhere under packages/** was edited), committed here for reproducibility
as docs/evidence/2026-08-12-cnf-repr-probe-*.rs, 2026-08-12-cadical-memory-probe.rs,
2026-08-12-varnames-waste-probe.rs. Builds directly on
docs/plans/2026-08-12-002-feat-router-orchestration-rust-plan.md (branch
spike/router-orchestration-rust, unlanded, commit 6b669db2a) -- its model-layer numbers
are CITED, not re-derived. -->

# The CNF layer, one layer down from the model: options, with the dominant cost named first

**Status:** research/decision only. No `pcb/**`, no `packages/**` edited. All measurements
below ran in a scratch Cargo project that path-depends on
`packages/temper-rust-router-core` as a library (real `encode_to_cnf`, real
`InternalConstraintModel`, real `rustsat`/`rustsat-cadical` 0.7.5 — the exact versions
pinned in `packages/temper-rust-router-core/Cargo.lock`) and reads `/proc/self/status`
`VmRSS`, never `sys.getsizeof` or a manual estimate.

## Verdict, stated first

**CaDiCaL's own internal memory dominates, and packing our side of the CNF is real but
cosmetic relative to the "does the monolith fit" question.** MEASURED, loading the real
production clause shapes into a real `CaDiCaL::default()` via the exact `add_clause` path
`solver.rs:70-88` uses: **152–175 bytes per clause**, growing slightly *faster* than
linear as scale increases (152.12 B/clause at 7.56M clauses, 175.25 B/clause at 22.7M
clauses — a real, measured, mildly super-linear trend, not noise: both are exact repeat
values across independent runs). Our own clause representation, `CnfFormula.clauses:
Vec<Vec<i32>>` (`encoding.rs:11-15`), costs a MEASURED **56.00 bytes/clause**
(cold-start, verified byte-for-byte reproducible at two scales 10× apart). A packed flat
`Vec<i32>` literal pool + `Vec<u32>` clause-offset index costs a MEASURED **13.81
bytes/clause** — a real **4.06×** reduction, nowhere near the model layer's 38×, and
smaller than CaDiCaL's own per-clause cost even *before* packing.

Extrapolated to the current 204,490-edge skeleton (scaling the 2026-07-27 measured
78,107,180-clause baseline by the same 9.9× edge-count ratio plan
2026-08-12-002 used, DERIVED not independently re-measured — see Confidence, below):

| what | bytes/item | full-scale (≈770.3M clauses) | share of best-case total |
|---|---:|---:|---:|
| CaDiCaL clause storage (measured, add_clause loop only) | 152–175 B/clause | **117.2–135.0 GB** | **91.5–92.6%** |
| our clauses, packed (flat + offsets) | 13.81 B/clause | 10.6 GB | 7.4–8.5% |
| our clauses, today (`Vec<Vec<i32>>`) | 56.00 B/clause | 43.1 GB | — |
| aux SAT-variable names, today (`Vec<String>`, dead weight — see below) | 56.00 B/var | 21.1 GB | — |
| aux SAT-variable names, fixed (no name stored) | 0 B/var | 0 GB | 0% |
| model layer, packed (U1, CITED not re-derived) | 8.9 B/var | 0.2 GB | 0.1–0.2% |

**Best case — everything packed on our side, U1 landed — is ≈128–146 GB.** Today, with
U1 landed but the CNF layer untouched, it is ≈182–199 GB. **Neither fits on any
realistic machine, and packing does not change that answer.** The batch loop is not
being kept because our representation is inefficient; it is being kept because CaDiCaL
itself cannot ingest ~770M clauses in bounded memory, full stop, and there is no
representation trick on our side of the FFI boundary that touches that number.

**A second, independent finding, found while measuring the first: `var_names:
Vec<String>` (`encoding.rs:217`, `var_map.iter().map(|v| v.name.clone())`) materializes
one heap `String` per SAT variable, including every Sinz auxiliary variable
(`"sc_r{i}_{j}"`, `encoding.rs:44-46`) — and `solve_with_cadical` never reads them
(`solver.rs:60`: `_var_names: &[String]`, underscore-prefixed, unused parameter).
`extract_topology` (`extraction.rs:18-44`) only ever matches names against a `"uses_"`
prefix, which no Sinz auxiliary name has.** This is a proven-dead allocation, not a
tradeoff: 21.1 GB (at full scale) spent naming variables that are read for nothing.
Unlike the clause-packing question, this one is unambiguous and should be fixed
regardless of what happens to net-batching.

---

## Read this first: what "CNF layer" turned out to mean

The task frames this as "does `Vec<Vec<i32>>` for ~450M clauses fit once packed" — a
single representation question. Measuring it surfaced **three** separate, independently
addressable findings, only one of which is the one named in the task:

1. **The clause list itself** (`CnfFormula.clauses: Vec<Vec<i32>>`) — the thing the task
   asked about. Real, measurable, worth ~4× — see §1.
2. **The auxiliary-variable name strings** (`var_names: Vec<String>`, returned
   *alongside* `CnfFormula` by `encode_to_cnf`) — not named in the task, found by
   instrumenting the same call, and larger in absolute terms (21.1 GB vs. the clause
   list's 32.5 GB saved by packing) because it is pure waste rather than a packing
   tradeoff. See §2.
3. **CaDiCaL's own clause storage** — the thing the task explicitly warned might
   dominate. It does. See §3.

None of the three, alone or combined, closes the gap between "packed" and "fits."

---

## §1. The clause list: `Vec<Vec<i32>>` vs. flat `Vec<i32>` + `Vec<u32>` offsets

### Method

`encode_to_cnf` is pure Rust with no `pyo3` dependency
(`packages/temper-rust-router-core/Cargo.toml` — `sat` is the only non-default-off
feature and pulls only `rustsat`/`rustsat-cadical`). It is safe and correct to
path-depend on it directly from a throwaway probe crate without touching the crate
itself. I built a real `InternalConstraintModel` with `NETS=110` competing nets per
channel and a `Capacity` constraint per channel with `capacity`/`slack_factor`/`width`
chosen so `floor(capacity*slack/width) == 17` — the same K the concurrent capacity plan
derived from the real 2026-07-27 measurement (two independent equations, K ≈ 17.2–17.5;
`docs/plans/2026-08-12-002-...`, "The capacity finding"). This is the **monolithic**
shape: every channel's capacity term set spans all NETS nets, so
`encoding.rs:148`'s `max_nets < var_indices.len()` guard *does* fire (unlike the
`batch_size=10` production path, where it never does — see §4).

Calling the real `encode_to_cnf` at `num_channels=2000` produced **exactly** 7,564,000
clauses / 18,552,000 literals / 3,926,000 CNF vars — matching a hand-derived closed form
for Sinz's sequential counter (`encoding.rs:21-76`) exactly: per constraint, 16
length-1 clauses + 2,038 length-2 + 1,728 length-3 (verified against the real encoder's
output at two scales, 2,000 and 20,000 channels, both times exact). That closed form was
then used to build clean, cold-start, single-purpose probe processes — one per
arm — so the representation comparison is not contaminated by allocator-arena slack left
over from constructing the real model first (see the "confound found and corrected"
callout below).

### Result

| representation | bytes/clause | measured at | note |
|---|---:|---:|---|
| **A** `Vec<Vec<i32>>` (today, `encoding.rs:13`) | **56.00** | N=2,000 and N=20,000, exact both times | one heap allocation per clause (glibc's minimum ~32-byte chunk for a 2–3-`i32` payload) + 24 bytes of outer-`Vec<Vec<i32>>`-buffer overhead per clause |
| **C** flat `Vec<i32>` + `Vec<u32>` clause-offset index | **13.81** | N=2,000 and N=20,000, exact both times | one allocation total for the literal pool, one for the offset index; no per-clause allocation at all |

**Ratio: 4.06×.** Exactly reproducible at a 10× scale difference — this is a clean,
confident, structural number, not an extrapolation artifact.

**Confound found and corrected, reported because it nearly produced a wrong number.**
The first version of this probe measured arm A by *cloning* the real `cnf.clauses`
in-process after building the real model (mirroring how one might naively reuse a live
object). That gave **24.00 bytes/clause** — implausibly low, and it turned out to be an
artifact: the process's glibc arena already had slack from the model-construction and
`encode_to_cnf`-internal `Vec` reallocation churn (doubling-growth waste), and the clone's
small per-clause allocations were satisfied from that slack without touching new pages,
so RSS barely moved. Rebuilding the same clause shapes from a **cold process per arm**
(zero prior allocation) recovered the analytically-sane number (56.00 = 24-byte outer
struct + 32-byte minimum heap chunk) and it held at 10× scale. Any future probe in this
family should measure representation cost from a cold start, not by cloning inside a
process that already built the object under test — plan 2026-08-12-002's own
`2026-08-12-router-model-memory-counterfactual.rs` already does this correctly (one arm
per process invocation); this spike's first draft did not, and the second draft was
brought in line with it.

### At scale

77,107,180 → 770.3M clauses (9.9× the 2026-07-27 baseline, same scaling plan
2026-08-12-002 used): **43.1 GB today, 10.6 GB packed.** A real 32.5 GB saved. Real, and
worth doing — see the plan's R2 — but 32.5 GB against a ≥128 GB floor (§3) does not move
the "does it fit" verdict.

---

## §2. The dead weight: `var_names: Vec<String>` for auxiliary variables

`encode_to_cnf`'s second return value clones every `SatVariable.name` into a fresh
`String` (`encoding.rs:217`), including the ~1,853 Sinz auxiliary variables generated
*per capacity constraint* (`(n-1)·k = 109·17`, `encoding.rs:41-48`, named
`"sc_r{i}_{j}"`). Two facts, both structural, make these names pure waste:

- `solve_with_cadical`'s `_var_names: &[String]` parameter (`solver.rs:60`) is
  underscore-prefixed and **never read** inside the function — grep confirms no other
  reference to `_var_names` in `solver.rs`.
- `extract_topology` (`extraction.rs:18-44`) only extracts variables whose name starts
  with `"uses_"` (`NetChannelVar`s). No Sinz auxiliary name matches — the check is a
  `strip_prefix("uses_")` that fails for every `"sc_r{i}_{j}"` and falls through to
  nothing.

So every auxiliary-variable name is allocated, indexed at most once during topology
extraction (a `var_names[*idx]` lookup that immediately fails a prefix check), and then
carried at full cost until the whole CNF/topology structure is dropped.

### Measurement

Cold-start probe building only `Vec<String>` of `"sc_r{i}_{j}"`-shaped strings at the
same per-constraint count (1,853 × num_channels): **56.00 bytes/aux-var** — the same
per-item cost as §1's arm A, for the same reason (small heap `String`, minimum glibc
chunk). Carrying no name at all (an index-only or `Option<String>` tag defaulting to
`None` for aux vars): **0.00 bytes/aux-var**, exactly, both scales.

### At scale

Aux vars at the current skeleton scale ≈ 377.4M (415.7M total CNF vars − 38.2M primary,
both DERIVED by the same 9.9× scaling as §1). **21.1 GB today, ~0 GB fixed.** This is
larger in absolute terms than the clause-packing saving in §1 (32.5 GB) is *not* — it's
smaller (21.1 < 32.5) — but it is a **strictly free** fix: nothing downstream reads it,
so there is no representation tradeoff to weigh, only a deletion. It should be the first
thing landed in this family, independent of every other decision in this document.

---

## §3. CaDiCaL's own memory: measured, not assumed

The task asks this directly because it is the question that decides whether everything
else in this document matters. It does not, mostly.

### Method

Same real model, same real `encode_to_cnf` output, fed into a real
`rustsat_cadical::CaDiCaL::default()` via the *exact* clause-loading loop production
uses (`solver.rs:70-88`, reproduced verbatim in the probe): build a `rustsat::types::Lit`
per literal, collect into a `Clause`, call `solver.add_clause(...)`. RSS measured
immediately before the loop (with our own `Vec<Vec<i32>>` CNF *already resident* — the
delta isolates CaDiCaL's own allocation cleanly regardless of what else is resident,
since nothing else changes across the loop) and immediately after.

Also inspected CaDiCaL's actual C++ source (vendored at
`~/.cargo/registry/src/.../rustsat-cadical-0.7.5/cppsrc/src/clause.{hpp,cpp}`, the exact
0.7.5 pinned in `packages/temper-rust-router-core/Cargo.lock`) to understand *why*:
`Internal::new_clause` (`clause.cpp:78`) does `new char[bytes]` — **one heap allocation
per clause**, same allocation-per-clause class as our own `Vec<Vec<i32>>`, not an arena
(CaDiCaL's `Arena` class exists only for the garbage collector's clause *compaction*
pass, not for original problem clauses — `arena.hpp:1-30`). The header
(`clause.hpp:31-100`) is a `union { int64_t id; Clause *copy; }` (8B) plus ~18 packed
boolean bitfields, `int glue`, `int size`, `int pos` (12B) — roughly 24 bytes of
housekeeping *before* the flexible-array-member literals (4 bytes each). So CaDiCaL pays
a comparable *fixed* per-clause tax to our own unpacked representation, on top of which
it carries watch-list entries (two per clause, for the first two literals) and other
solver-internal bookkeeping — which is almost certainly what accounts for the measured
cost being ~3× our own unpacked number rather than roughly equal to it.

### Result

| scale | clauses | CaDiCaL delta | bytes/clause |
|---:|---:|---:|---:|
| N=2,000 channels | 7,564,000 | 1.072 GB | **152.12** |
| N=6,000 channels | 22,692,000 | 3.704 GB | **175.25** |

Not perfectly linear — a real ~15% increase in per-clause cost across a 3× scale
increase, most plausibly internal array resizing/preprocessing bookkeeping that scales
with variable count rather than clause count alone (both grow together in this shape, so
the two are not separable by this experiment alone). Conservatively extrapolating with
the *larger*, larger-scale-measured ratio (175.25 B/clause, the worse case) rather than
the smaller one is the right choice for a capacity ceiling.

A bounded solve (`limit_conflicts(20_000)`, the production default at
`_pipeline_core.py:67`) on the N=2,000 case added only **0.09 GB** beyond clause
loading and returned SAT — for this shape, clause *ingestion* dominates over search, so
the loading-only number is a fair proxy for peak memory at a bounded conflict limit; an
unbounded or much-higher-limit solve on a genuinely hard instance could add
learned-clause growth on top, which this probe does not characterize and which is a
separate, dynamic (not representation) cost.

### At scale

770.3M clauses × 152–175 B/clause = **117.2–135.0 GB**, for clause storage alone, before
any search-time learned-clause growth. This is the number that matters:

**Total, best case (U1 landed, §1's packed clauses, §2's aux-names fix, CaDiCaL as
measured):**

```
packed clauses (§1, arm C)         10.6 GB
aux var names, fixed (§2)           0.0 GB
model layer, packed (U1, CITED)     0.2 GB
CaDiCaL clause storage (§3)   117.2–135.0 GB
─────────────────────────────────────────────
TOTAL                        128.0–145.8 GB   (CaDiCaL = 91.5–92.6% of the total)
```

**Total, today (U1 landed but this plan's fixes not):**

```
unpacked clauses (§1, arm A)       43.1 GB
aux var names, unfixed (§2)        21.1 GB
model layer, packed (U1, CITED)     0.2 GB
CaDiCaL clause storage (§3)   117.2–135.0 GB
─────────────────────────────────────────────
TOTAL                        181.7–199.5 GB
```

Packing moves the total from ~182–200 GB to ~128–146 GB — genuinely worth doing, and the
plan should do it — but it does not move the verdict. Neither number fits an ordinary
machine, and the 91.5–92.6% CaDiCaL share means no amount of further cleverness on our
side of the FFI boundary gets there. **Leading with this, per the task's own instruction:
solver-internal memory dominates, and packing our side is real but cosmetic against the
"does the monolith fit" question.**

---

## §4. Interaction with the concurrent capacity-encoding finding

`docs/plans/2026-08-12-003-fix-sat-capacity-encoding-plan.md` has not landed on any
branch as of this writing (`git log --all -- <path>` returns nothing; checked before
concluding this). What the task states about it — production `batch_size=10 < K≈17`
means `encoding.rs:148`'s guard never fires, so the batched path encodes **zero**
capacity constraints and reports 0 conflicts/0 decisions — is corroborated exactly by
this spike's own measurements: every number in §1–§3 above is for the *monolithic*
shape (`n=110` nets, full-width capacity terms), and it is precisely that shape that the
production batched path never constructs, because `var_indices.len() ≤ 10 < 17`.

**If that plan raises `DEFAULT_BATCH_SIZE` above K:** each batch would begin encoding
AtMostK for any channel whose in-batch net count exceeds the (monotonically shrinking,
per `_shrink_channel_widths`) local K. Per-batch clause count would jump from
**today's ~0** to a **bounded-by-batch-size**, not bounded-by-board-size, quantity — the
same §1 Sinz shape applies (`(n-1)·k` aux vars, `~(n-1)(2k-1)+ (n-k)` clauses) with
`n ≤ B` (the new batch size) rather than `n = 110`. This is structurally much smaller
than the monolithic case per batch, but it would be the *first* time the batched path's
CaDiCaL solves carry any real memory cost at all, and both this spike's packed-clause
representation (§1) and the dead-aux-name fix (§2) apply identically per-batch, at the
same measured bytes/clause and bytes/aux-var ratios. **This plan's requirements (R1–R2 in
particular) should therefore be verified once more, cheaply, against whatever batch size
that plan lands on** — reusing the same probes (`docs/evidence/scripts/2026-08-12-cnf-repr-probe-isolated.rs`,
`docs/evidence/scripts/2026-08-12-cadical-memory-probe.rs`), swapping `NETS=110`/`K=17` for
`NETS=B`/the new K, rather than re-deriving from scratch. No number in this document
should be read as "safe at any batch size" — it is scoped to the monolithic (`n=110`)
shape as stated.

---

## Options, ranked

### Option 1 — Fix the dead aux-name allocation (§2). **Recommended, do first, independent of everything else.**

Stop cloning names for Sinz auxiliary variables in `encode_to_cnf`
(`encoding.rs:217`) — carry `Option<String>` (or, more precisely, don't allocate a
`SatVariable` name at all for aux vars, since `SatVariable::new(name, "")` already wastes
a formatted `String` per aux var that nothing reads even at today's tiny batch=10 scale).

- **Representation-only or semantic?** Representation-only. `var_names[idx]` for a
  primary variable is unchanged; for an auxiliary variable, the only currently-observed
  behavior is "index into a slice and fail a prefix check" — replacing the entry with an
  empty string or sentinel changes nothing observable.
- **Cost:** near-zero (a few lines in `encoding.rs`; the `var_names: Vec<String>`
  return type may need to become `Vec<Option<String>>` or similar, which is a signature
  change with a small number of call sites — `lib.rs:199`, `bmc.rs:58`,
  `equivalence.rs` test call sites, `property_campaigns.rs`).
- **Win:** 21.1 GB at full scale, 100% of it currently pure waste. Applies at *any* batch
  size the moment `AtMostK` is encoded at all — including a future batch size raised
  above K (§4).
- **Risk:** low. The "never read" claim is directly checkable (`rg '_var_names'`,
  `rg 'strip_prefix\("uses_"\)'`) and the acceptance test (byte-identical board) would
  catch any case this analysis missed.

### Option 2 — Pack the clause list: flat `Vec<i32>` + `Vec<u32>` offsets (§1). **Recommended, second.**

Replace `CnfFormula.clauses: Vec<Vec<i32>>` with a CSR-style `literals: Vec<i32>`,
`clause_offsets: Vec<u32>` pair. `solve_with_cadical`'s consumption loop
(`solver.rs:73-88`) becomes an iteration over `offsets.windows(2)` instead of
`&cnf.clauses`; every other consumer (`bmc.rs`, `equivalence.rs`,
`property_campaigns.rs`, the `#[cfg(test)]` DPLL solver in `encoding.rs`) needs the same
mechanical rewrite from `&[Vec<i32>]`-shaped iteration to CSR-window iteration.

- **Representation-only or semantic?** Representation-only. The literal *content* and
  *order* are unchanged; only the container changes. A byte-identical-board test is the
  correct and sufficient acceptance bar.
- **Cost:** medium. `CnfFormula` is a small, contained type but has several consumers
  (`solver.rs`, `bmc.rs`, `equivalence.rs`, the exhaustive DPLL test harness in
  `encoding.rs`'s own test module) that all iterate clauses; each needs the CSR-window
  rewrite. `Clause` (a growable `Vec<i32>` per in-progress clause during construction,
  e.g. inside `encode_at_most_k`) can stay as-is during *construction* and be flattened
  once at the end, or `encode_at_most_k` can be rewritten to push directly into the flat
  pool + offsets — the latter is more invasive but avoids a double-allocation
  (build-then-flatten) at construction time; worth measuring both, not assuming.
- **Win:** 32.5 GB at full scale (43.1 → 10.6 GB). Real, and — unlike Option 1 — this one
  *is* a genuine representation tradeoff (a small amount of extra indexing complexity for
  a real memory win), not a pure deletion.
- **Risk:** low-medium. Every consumer must be found and converted; missing one either
  fails to compile (safe) or silently keeps the old representation for that call site
  (a correctness risk if that path diverges from tested behavior — the property-test
  invariants already in `encoding.rs` (`prop_output_sizes_consistent`,
  `prop_clause_indices_in_bounds`, `prop_no_empty_clauses`, `prop_no_tautological_clause`,
  `prop_empty_constraints_no_clauses`) should be re-run against the packed type as a
  cheap, already-written regression net.

### Option 3 — Do nothing to the CNF layer; land only U1 (model layer) and rely on net-batching indefinitely. **Not recommended, but not unreasonable — stated honestly.**

Given CaDiCaL's 91.5–92.6% share of the best-case total, one could argue the CNF-layer
packing in Options 1–2 is not worth the engineering cost, since it does not change
whether the monolith fits. This is a legitimate position and the task explicitly invites
it ("the CNF layer is already efficient and this is not worth doing" is a fully
legitimate conclusion) — but it is not the conclusion this measurement supports, for two
reasons specific to *this* codebase rather than to CNF representation in the abstract:

- Option 1 is free (a deletion of proven-dead work, not a tradeoff) and its 21.1 GB
  matters **before** the "does the monolith fit" question is even asked — it is memory
  wasted at *any* scale where `AtMostK` is encoded, including a future raised-batch-size
  world (§4) where per-batch memory, not full-board memory, is the relevant budget and
  every gigabyte counts differently.
- Option 2's 4.06× is smaller than the model layer's 38× but is not small in absolute
  terms (32.5 GB) and is a mechanical, low-risk, well-scoped change with an existing
  property-test harness to lean on. Declining to do a real, cheap, low-risk 4× reduction
  solely because a *different* component (CaDiCaL) dominates the *total* is optimizing
  the wrong variable — the right comparison is cost-to-implement vs. GB-saved, not
  share-of-total.

**Ranking: Option 1, then Option 2, and Option 3 only as "not now" rather than "never" —
see the plan's phasing.**

### Option 4 — Replace or bound CaDiCaL's own memory (e.g., a different cardinality encoding, or splitting the monolithic solve into CaDiCaL-scale chunks). **Out of scope for this plan; named because it is the one option that would actually change the "does it fit" verdict.**

Since §3 shows CaDiCaL dominates, the only way to make the monolith fit is to change what
CaDiCaL is asked to hold — either a cardinality encoding with a smaller aux-var/clause
footprint than Sinz's sequential counter (e.g., a totalizer or commander encoding trades
aux-var count for clause count differently; whether either is meaningfully smaller *for
this K≈17, n≈108-110 regime specifically* is an open, measurable question this spike did
not answer), or restructuring the monolithic solve into CaDiCaL-scale chunks (which is,
functionally, net-batching by another name — the two are not as separate as the task's
framing implies). This is a solver/encoding-algorithm question, not a data-representation
question, and is explicitly out of scope here — named so the plan's "monolith does not
fit" verdict is not mistaken for "and nothing can be done," which would be a different,
stronger, unsupported claim.

---

## Confidence

- **High** on the qualitative verdict: CaDiCaL dominates, packing is real but cosmetic
  against "does it fit," Option 1 is free money. These conclusions are robust to the
  exact scaling factor because CaDiCaL's share (91.5–92.6%) is large enough that plausible
  errors in the edge-count extrapolation (±20–30%) would not change which side of "fits"
  the total lands on.
- **Medium** on the exact GB figures. Two DERIVED (not independently re-measured)
  inputs carry uncertainty: (1) the current skeleton is still 204,490 edges — inherited
  from `2026-08-07-sat-model-reduction-options.md`, itself flagged by plan
  2026-08-12-002 as predating the T2 footprint change and needing re-measurement; (2) the
  9.9× linear scaling of the 2026-07-27 baseline assumes clause/aux-var count per
  constraint (K, n) stays constant as edge count grows, which is a reasonable but
  unverified assumption — K is a property of physical channel width vs. track width, not
  of skeleton density, so this should hold, but was not independently checked.
- **Medium-low** on the exact CaDiCaL bytes/clause figure at *full* scale specifically,
  since the two measured points (152.12 at 7.56M clauses, 175.25 at 22.7M clauses) show
  real super-linear growth and 770M clauses is another ~34× beyond the larger measured
  point — extrapolating a trend measured over one order of magnitude to a second order of
  magnitude is the weakest link in this chain. The plan should re-measure at a third,
  larger scale before treating 117–135 GB as precise rather than "the right order of
  magnitude and clearly >100GB."

## Sources / Research

- MEASURED this task: `docs/evidence/scripts/2026-08-12-cnf-repr-probe-common.rs`,
  `docs/evidence/scripts/2026-08-12-cnf-repr-probe-lumped.rs` (whole-`encode_to_cnf`-call
  context number, and the confound writeup above),
  `docs/evidence/scripts/2026-08-12-cnf-repr-probe-isolated.rs` (§1's clean cold-start A/C
  comparison), `docs/evidence/scripts/2026-08-12-cadical-memory-probe.rs` (§3),
  `docs/evidence/scripts/2026-08-12-varnames-waste-probe.rs` (§2),
  `docs/evidence/2026-08-12-cnf-probe-Cargo.toml.txt` (exact dependency pins:
  `rustsat`/`rustsat-cadical` 0.7.5, matching `packages/temper-rust-router-core/Cargo.lock`).
- CITED, not re-derived: `docs/plans/2026-08-12-002-feat-router-orchestration-rust-plan.md`
  (branch `spike/router-orchestration-rust`, unlanded, commit `6b669db2a`) — the model-layer
  326.7/8.9 B/var numbers, the 2026-07-27 baseline (42,145,777 vars / 78,107,180 clauses /
  20,734 constraints), the K≈17 derivation, the 204,490-edge current-skeleton figure, and
  the 9.9× scaling factor this spike reuses rather than re-deriving.
- `docs/evidence/2026-08-07-sat-model-reduction-options.md`,
  `docs/evidence/2026-08-07-router-oom-diagnosis.md` — origin of the 204,490-edge and
  42,145,777-var/78,107,180-clause figures respectively (both already on `main`).
- `docs/evidence/2026-08-12-board-recipe-reproducibility.md` (branch
  `diagnose/clearance-regression`, unlanded, commit `0659ef39b`) — the verification
  baseline: 168 footprints, 3,349 segments, 56 vias, 70 zones, 80/105 nets routed.
- CaDiCaL 0.7.5 C++ source, vendored at
  `~/.cargo/registry/src/index.crates.io-1949cf8c6b5b557f/rustsat-cadical-0.7.5/cppsrc/src/`
  — `clause.hpp` (struct layout), `clause.cpp:78-131` (`Internal::new_clause`,
  the per-clause `new char[bytes]` allocation), `arena.hpp` (confirms the arena is
  GC-compaction-only, not used for original problem clauses).
- Code: `packages/temper-rust-router-core/src/encoding.rs:11-15,21-76,79-227` ·
  `packages/temper-rust-router-core/src/solver.rs:58-88` ·
  `packages/temper-rust-router-core/src/extraction.rs:18-58` ·
  `packages/temper-rust-router-core/src/types.rs:17-92` ·
  `packages/temper-placer/src/temper_placer/router_v6/_pipeline_core.py:67`
  (`sat_conflict_limit=20_000` default).
- Checked and found absent (per this task's instruction to verify before concluding
  absence): `git fetch origin && git log origin/main --oneline -5`,
  `git log --all --oneline -- docs/plans/2026-08-12-003-fix-sat-capacity-encoding-plan.md`
  — no commit on any branch as of this writing.
