<!-- provenance: commit=88320cb0 (code), measured live this task; board pcb/temper.kicad_pcb sha256 unchanged -->

# Net-batching prototype for `#871`: 5/11 Stage 3 batches complete (50/110 nets get a SAT topology), then a Rust allocator abort under the 8GB cap — the board does NOT route end-to-end at B=10

**Date:** 2026-08-07

**Headline, stated plainly up front:** This run does **not** route the board
end-to-end. Batches 0–4 (50/110 nets, 45.5%) each produced a valid SAT
topology — either directly (batch-level SAT) or via the singleton-retry
fallback after a batch-level UNSAT — under the 8GB `ulimit -v` cap, with 0
nets lost to Stage 4's fallback path. Batch 5 then crashed the whole process
with a **Rust allocator abort** (`memory allocation of 35651600 bytes
failed`, exit 134/SIGABRT) — not a catchable Python `MemoryError` like the
monolith's own failure mode. No output board was written (Stage 4 never
runs until every Stage 3 batch — or its documented fallback — has
contributed). This is still new information: **50 nets got a real SAT-solved
topology, which is 50 more than the 22.5M-variable monolith ever achieves —
that model OOMs during raw variable *construction*, before a single SAT
call is ever made.** But "some batches complete" is not "the board routes,"
and this report does not claim the latter.

---

## 1. Per-batch measurements (MEASURED, live run)

Board: `pcb/temper.kicad_pcb`, 110 nets. `batch_size=10` (11 batches).
Guarded with `ulimit -v 8388608` (8GB), `PYTHONHASHSEED=0`,
`TEMPER_BATCH_TRACE=1`, `timeout 3000`, backgrounded and polled in-turn.

| Batch | Nets | Batch-level SAT status | Primary vars | net_channel | via | Constraints | Wall (s) | Peak RSS (cumulative) | Retried (singleton) | Failed (no topology) |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 10 | **sat** | 2,992,330 | 2,044,900 | 947,430 | 109,124 | 77.07 | 5,207,660 KB (5.21 GB) | 0 | 0 |
| 1 | 10 | **unsat** → singleton retry | 2,992,330 | 2,044,900 | 947,430 | 109,145 | 184.62 | 5,730,072 KB (5.73 GB) | 10 | 0 |
| 2 | 10 | **sat** | 2,992,330 | 2,044,900 | 947,430 | 109,154 | 90.98 | 5,730,072 KB (5.73 GB) | 0 | 0 |
| 3 | 10 | **unsat** → singleton retry | 2,992,330 | 2,044,900 | 947,430 | 109,181 | 192.95 | 5,777,396 KB (5.78 GB) | 10 | 0 |
| 4 | 10 | **sat** | 2,992,330 | 2,044,900 | 947,430 | 109,154 | 49.59 | 5,777,396 KB (5.78 GB) | 0 | 0 |
| 5 | 10 | **CRASH** (Rust allocator abort, not SAT/UNSAT) | unknown (never printed — crashed inside the batch's build/solve) | — | — | — | included in the 878s total below | process killed; last-known 5.78 GB, cap 8 GB | — | — |
| 6–10 | 50 | **never attempted** — process aborted | — | — | — | — | — | — | — | — |

All figures MEASURED except batch 5's internals, which are UNMEASURED — the
crash is a hard process abort (SIGABRT), not a Python exception, so no
per-batch trace line was ever printed for it (my `except MemoryError` guard
in `net_batching.py` cannot catch this — see §4).

- **Total wall time for the run**: 878.63s (14:38.63, `/usr/bin/time`) from
  process start to the abort, covering Stage 0–2 setup + batches 0–4 +
  batch 5's partial attempt.
- **Peak RSS at the point of the crash**: `/usr/bin/time`'s own
  "Maximum resident set size" reads 5,777,396 KB (5.78 GB) — the same value
  already reached at the end of batch 4. The crash itself was a single
  ~35.65 MB allocation request that failed because total process virtual
  memory was already pinned at the 8 GB `ulimit -v` ceiling (not because RSS
  itself jumped past 8GB at that instant — see §4 for why this is a
  different failure mode than the monolith's).
- **Nets that reached a topology**: 50/110 (45.5%), all via Stage 3 (0 via
  Stage 4's fallback path, since Stage 3 never got far enough to leave any
  batch's nets unrecovered).
- **Segments/vias/zones emitted**: **0** — Stage 4 (the stage that actually
  writes routed copper) never runs; it is a single whole-board pass gated on
  every Stage 3 batch (or fallback) having contributed first, by design (see
  §3). No output `.kicad_pcb` was written (confirmed: the output path is
  empty).
- **Batch 5's nets** (recomputed offline from the same deterministic
  ordering, read-only, without touching the live run):
  `zcd`(4 pins), `discharge.k_dis1-coil2`(5), `refin_n`(5), `SW_NODE`(7),
  `+15V`(10), `DC_BUS_RTN`(12), `vcc`(13), `PWR_RTN`(18),
  `DISCHARGE_CTRL`(2), `OVP_VREF_2V5`(2) — the first batch containing
  several double-digit-pin-count nets, consistent with the ascending-pin-
  count ordering reaching that tier.

**Comparison to the monolith** (MEASURED, `docs/evidence/2026-08-07-pruned-encoding-measurement.md`, same board, same 8GB cap): the unbatched model needs
22,493,900 primary variables just for `NetChannelVar`s and `MemoryError`s
at 5.43GB **before completing variable construction for even one net's full
sweep of the model** — 0 nets ever reach a SAT call. This run's batches 0–4
completed 5 real SAT solves (some at batch granularity, some via singleton
retry) covering 50 nets, at a peak of 5.78GB. That is real, new progress —
just not completion.

---

## 2. Does the board route end-to-end? **No.**

Per the task's own framing: if it doesn't complete, report exactly where it
stopped and why. **It stopped at Stage 3, batch 5 of 11 (nets 51–60 in
batching order), crashing the whole process with a Rust allocator abort
under the 8GB `ulimit -v` cap**, after 5 batches (50/110 nets) had already
obtained a valid topology. No segments, vias, or zones were written. No DRC
counts exist for this run because there is no routed board to check.

---

## 3. How the non-batchable global constraints are enforced, and how that was verified

**Capacity** (the one cross-net constraint the Stage 3 SAT model actually
encodes — confirmed by reading `constraint_model.py`: the only
`Constraint` subclasses are `CapacityConstraint`, `DiffPairConstraint`,
`LayerConstraint`, and an unused, never-instantiated
`ChannelSeparationConstraint`) is carried across batch boundaries by
explicit bookkeeping in `net_batching.py`:
`_consume_capacity()` subtracts each successfully-routed net's
`trace_width_mm + clearance_mm` from every channel edge it used;
`_shrink_channel_widths()` rebuilds the next batch's `ChannelWidths` with
that consumption already subtracted (floored at 0, never negative).
Indirect verification from this run: constraint counts stay ~109.1–109.2K
across every batch (0: 109,124 / 1: 109,145 / 2: 109,154 / 3: 109,181 / 4:
109,154) — the same ~109K skeleton edges get a capacity constraint every
batch (capacity constraints are generated per-edge across the *whole*
skeleton regardless of which 10 nets are in a given batch), consistent with
the mechanism firing rather than being silently skipped. A sharper
verification (diffing the actual per-edge capacity RHS value between an
early and a late batch for a shared edge) was not done — this run never
reached a late-enough batch to make that comparison meaningful, and is
flagged as a follow-up.

**Creepage, HV/SELV separation, and geometric clearance are not encoded in
the Stage 3 SAT model at all — batched or monolithic.** This is the
load-bearing fact for the coordinator's question: batching Stage 3 cannot
weaken a constraint that was never inside Stage 3 to begin with. They are
enforced downstream, in **Stage 4**, which this change does not touch:
`occupancy_grid.py`'s `mark_path_blocked`/`mark_via_blocked` dilate every
routed path/via by its net's required clearance before the next net's A*
search runs — a **single whole-board pass over the complete net list**, run
once after Stage 3 (batched or not) hands off a topology graph, never
batched itself. `_run_stage4` is unmodified by this task; it still receives
`stage3.topology_graph` (here, the union of what the completed batches
produced) and runs exactly the call it always did. Post-hoc whole-board DRC
(this repo's `run_drc`/kicad-cli convention, `power_pcb_dataset/drc_ceiling.json`)
verifies the final assembled geometry the same way regardless of how Stage 3
produced its topology.

**Verification performed**: (a) code inspection — grep-confirmed no
`Clearance`/`Creepage` constraint class exists in `constraint_model.py`;
confirmed `occupancy_grid.py`'s blocking functions take a `clearance`
parameter and dilate by it; confirmed `_run_stage4`/`_run_stage5` are
byte-for-byte unmodified by this task's diff. (b) **Empirical DRC
verification was attempted and did not succeed in this environment**:
`kicad-cli` is not installed and is not installable without sudo in this
sandbox (this repo's own
`docs/solutions/workflow-issues/2026-07-18-plan-execution-and-ci-rot-excavation.md`
notes it requires a separate PPA, not plain `apt`); a `conda-forge` search
found no package either. Since Stage 3 never completed in this run, there is
also no routed board to check DRC against yet regardless. **This is stated
as an open gap, not glossed over**: the architectural argument (Stage 4 is
unbatched, always was, and this task didn't touch it) is verified by code
reading; the empirical "the resulting board actually has zero new
creepage/clearance violations" claim is UNVERIFIED in this environment and
would need either `kicad-cli` or a completed batched route to check against.

---

## 4. Failure-mode finding, corrected from the original design assumption

The design (see `net_batching.py`'s module docstring, written before this
run) assumed a batch that exhausts memory would surface as a **catchable
Python `MemoryError`**, matching the monolith's own observed failure mode
(`docs/evidence/2026-08-07-pruned-encoding-measurement.md`: `MemoryError`
inside `add_variable`'s dict assignment). This run shows that assumption is
**incomplete**: the crash that actually occurred was a **Rust allocator
abort** (`memory allocation of 35651600 bytes failed`, `SIGABRT`, exit 134)
— almost certainly inside `solve_topology_rust`'s CNF encoding or CaDiCaL
setup, not Python's own variable-dict construction (which had already
succeeded for every prior batch at a similar scale). A Rust `abort()` on
allocation failure terminates the whole process immediately; it is not a
Python exception, so `net_batching.py`'s `except MemoryError:` guards around
each batch and each singleton retry **cannot and did not catch it** — the
entire process died, discarding 5 batches' worth of already-successful,
already-in-memory topology results that were never written anywhere (they
existed only as in-process Python objects, not yet handed to Stage 4).

**This is a real, previously-unknown limitation of the current prototype**,
found by this run, not designed for: net-batching's memory profile is not
"peak per batch, released between batches" as hoped — cumulative RSS
climbed batch over batch (5.21 → 5.73 → 5.73 → 5.78 → 5.78 GB) even though
each batch's own model is discarded after use, meaning something (most
likely Rust-side CNF/solver buffers, or CPython arena fragmentation from
repeated large dict allocation/deallocation) is not being fully released
back to the OS between batches. With headroom shrinking batch by batch, a
later batch — batch 5 here — can fail even though its own model size is no
larger than earlier, successful batches.

**What this means for the "no rip-up of earlier batches" policy
(§ failure-handling in `net_batching.py`'s docstring)**: that policy already
correctly anticipated a *SAT-level* failure (batch UNSAT) and handled it
(batches 1 and 3, both recovered cleanly via singleton retry). It did not
anticipate a *process-level* failure, which by construction cannot be
recovered in-process at all — there is nothing left to retry once the
process is gone. A durable fix (not implemented here, flagged as follow-up
work, consistent with the task's "state what you chose and why" framing
rather than silently absorbing the gap): run each batch's build+solve in a
**fresh subprocess** rather than in-process, so a Rust abort in batch N
kills only that subprocess, not the accumulated results from batches
0..N-1 sitting in the parent process's memory. That subprocess boundary
would also reset any unreleased Rust/CPython allocator state between
batches, which is very likely the actual fix for the RSS-creep pattern
observed above, not just a fault-isolation improvement.

---

## 5. Optimality cost on a small, tractable board (MEASURED, with an honest caveat)

`pcb/benchmarks/temper_fixture_33.kicad_pcb` (24 routable nets after
placement, per this run's own output) was routed twice: once monolithic
(unbatched Stage 3), once with `--net-batching --batch-size 5` (5 batches,
all SAT at batch level, 0 retries, 0 fallback nets, total Stage 3 wall
59.27s).

| | Monolithic | Batched (B=5) |
|---|---|---|
| Segments | 674 | 674 |
| Vias | 4 | 4 |
| Zones | 10 | 10 |
| Total wirelength (summed segment length, mm) | 441.66 | 441.66 |

**Byte-identical.** MEASURED, not rounded coincidence — computed by summing
Euclidean segment lengths from both output `.kicad_pcb` files directly.

**Honest caveat, stated per the task's own instruction not to hand-wave**:
this is weak evidence for "batching has zero optimality cost" as a general
claim. Stage 4's A* pathfinding does the actual geometric realization from
scratch on the occupancy grid — Stage 3's SAT topology is *guidance*
(channel/terminal selection), not the literal emitted path — and this small
board's own pre-fix baseline needed "0 conflicts, 0 decisions" to solve
even in its monolithic form (per
`docs/evidence/2026-07-27-stage3-model-and-rewrite.md`), meaning the joint
SAT model had enormous solution freedom to begin with. A board with real
channel congestion (like the production board — where two batches in §1
went UNSAT at the joint level) is exactly the regime where batching's
sacrifice of joint optimality would show up in wirelength/via count, and
this small fixture never entered that regime. **This measurement shows 0%
cost on an uncongested board; it does not show 0% cost in general**, and
the production board — the one board on which this would actually matter —
never reached Stage 4 in this run, so no batched-vs-joint comparison exists
for it.

---

## 6. Batching design recap (unchanged from the code; restated here for the record)

- **Batch size**: 10 (`net_batching.DEFAULT_BATCH_SIZE`), matching the
  reduction survey's own worked estimate (~2.04M net_channel vars/batch,
  corroborated by both this run's own measurement — 2,044,900 net_channel
  vars/batch, exact — and the survey's independent prior data point of a
  2.6M-variable model surviving construction under the same 8GB cap).
- **Ordering**: low-fan-out-first (ascending pin count) with hub blocks
  (`mcu`, `safety`) deferred to the last batches. Hub-block membership
  MEASURED this task by extracting each footprint's atopile `Sheetpath`
  property directly from `pcb/temper.kicad_pcb` and cross-tabulating
  boundary-crossing nets per top-level block: `mcu` has 20 boundary nets,
  `safety` 13 — both far above the next-highest block (`rtd_pan`, 9). This
  corroborates (does not byte-for-byte reproduce — different counting
  method, not re-derived) the task brief's cited "18 and 11." Confirmed in
  this run's own batch dump: batches 9–10 are dominated by `safety.*` nets
  and end with `gnd` (86 pins) and `+3V3` (51 pins) — the two
  highest-arity nets on the board — exactly where the ordering was designed
  to put them.
- **Capacity carry-forward**: see §3.
- **Failure handling**: batch-level UNSAT → singleton retry against
  freshly-recomputed remaining capacity (not a rip-up of earlier batches);
  nets still failing get no topology and fall through to Stage 4's existing
  `fallback_channel_path`. This worked as designed twice in this run
  (batches 1 and 3). It does **not** cover a process-level abort (§4) —
  that is the gap this run surfaced.

---

## Sources

- `docs/evidence/2026-08-07-sat-model-reduction-options.md` — the survey
  that rated net-batching the best-evidenced non-bundling option and
  supplied the B=10 estimate this run corroborates almost exactly
  (2,044,900 measured net_channel vars vs. 2,044,900 estimated).
- `docs/evidence/2026-08-07-pruned-encoding-measurement.md` — the monolith
  baseline this run is compared against (22,493,900 vars, 5.43GB
  `MemoryError`, 0 nets ever reach a SAT call).
- `packages/temper-placer/src/temper_placer/router_v6/net_batching.py` —
  this task's implementation (ordering, capacity carry-forward, batch
  orchestration, failure handling).
- `packages/temper-placer/src/temper_placer/router_v6/constraint_model.py`,
  `occupancy_grid.py` — read for §3's constraint-enforcement verification.
- `docs/solutions/workflow-issues/2026-07-18-plan-execution-and-ci-rot-excavation.md`
  — confirms `kicad-cli` requires a PPA install, not plain `apt` (§3's DRC
  gap).
- Live run: `pcb/temper.kicad_pcb` sha256
  `1cce4a0872051675b0339de3378ff7ec2c16bb4b035c999dfa408dec5ecbc3f6`
  (unchanged by this task), `ulimit -v 8388608`, `PYTHONHASHSEED=0`,
  `TEMPER_BATCH_TRACE=1`, `timeout 3000`, `/usr/bin/time -v`, backgrounded
  and polled in-turn.
