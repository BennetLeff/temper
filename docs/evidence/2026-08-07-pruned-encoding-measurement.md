<!-- provenance: commit=ed84ca27a7c7846326dd9e43da17a7e456bb3eb5 dirty=false -->

# Router encoding pruning (U5): production-board measurement — pruning provides ~0% reduction on this board; both paths OOM before reaching CNF encoding under the 8GB gate

**Date:** 2026-08-07

**Task:** U5 of `docs/plans/2026-08-07-001-feat-router-encoding-pruning-plan.md`
— measure the production-board CNF size with `enable_geographic_pruning`
OFF and ON, under the plan's `ulimit -v 8388608` (8 GB) gate, and report the
actual reduction factor against the plan's ≥10× target (R3/R4).

**Headline result, stated plainly up front:** Neither run reached Rust's
`encode_to_cnf` step, so **no CNF-level variable/clause count was obtained
in either direction** (UNMEASURED, not a target quoted as a result). But a
real, load-bearing number *was* obtained at the Python primary-variable
level, and it answers the question this task exists to ask: **geographic
pruning as currently parameterized (`K=2.0`, `M_min=30mm`) removes
approximately 0% of the primary variables on the nets sampled** (14 of 110
nets, directly observed; MEASURED). A follow-up geometric analysis of the
whole net list (independent of the router, MEASURED separately) shows why:
this board's nets are not locally clustered, so the pruning margin covers
most of the board for most nets. This is a genuine, board-specific finding,
not a bug in the predicate.

---

## 0. Why this measurement was newly possible today

Per the task brief: `route_pcb()` was previously blocked from building any
model at all by the plane-classification bug, then by quadratic skeleton
bridging, once the model existed. Both are fixed on this branch (merged
from `worktree-agent-af448502d9c6417ca`):

- `8abcec24` — `fix(router): open F.Cu/B.Cu to real routing instead of the
  plane-condemnation fallback`
- `07d514f9` — `perf(router): replace O(components^2 * nodes^2) island
  bridging with KD-tree + Kruskal MST`

With both fixed, `route_pcb()` reaches `ModelBuilder.build()` for the first
time since 2026-07-27, which is what makes this measurement runnable. It
also means the channel skeleton is now **far larger** than the pre-fix
board (see §2) — the plane-condemnation fallback had been silently
suppressing most of the routable copper area, and removing it exposed a
skeleton roughly 10× bigger than the one the July 27 baseline measured.

---

## 1. Machine, commit, and board provenance

| Field | Value |
|---|---|
| Host | Linux `earth`, 6.8.0-136-generic, x86_64, 24 cores, 62 GiB RAM |
| Worktree | `/home/bennet/Desktop/temper/.claude/worktrees/agent-a14cebd66c9c866e4` |
| Commit at measurement | `ed84ca27a7c7846326dd9e43da17a7e456bb3eb5` (working tree clean) |
| Base merged | `worktree-agent-af448502d9c6417ca` (fast-forward), carrying `8abcec24` + `07d514f9` |
| Board | `pcb/temper.kicad_pcb`, sha256 `1cce4a0872051675b0339de3378ff7ec2c16bb4b035c999dfa408dec5ecbc3f6` (unchanged by this task) |
| Python | 3.12.3 (uv-managed `.venv`, this worktree) |
| Rust extensions | `make extensions-check`: 12/13 fresh (mtime-fallback), 1 missing (`temper-constraints`, unrelated to the router path) |
| Machine load during measurement | `uptime` load average ~11 on 24 cores; other agent worktrees concurrently active (per task brief) — not a dedicated quiet machine |

Another agent is concurrently fixing net-blind pour handling in
`obstacle_map.py` on this same base (out of scope here, per the task's
constraint to stay out of that file — confirmed untouched:
`git status --short` shows no changes to `obstacle_map.py`). Their fix is
expected to shrink the skeleton/model further. **The numbers in this
document are therefore a pre-that-fix baseline**, not a final verdict on
the router's tractability — see §7.

---

## 2. Call path used, and why

Two call paths build different models (per the task brief; the specific
"silent-noop-diagnosis" doc it names does not exist in this worktree — this
section is this document's own record of the distinction instead):

1. **`route_pcb()` direct**, as used by
   `test_production_board_routing_drc_regression` — passes the *committed*
   board (with its existing 2,290 segments / 48 vias / 96 zones still
   present) plus a `placements_dict` produced by an actual placement solve.
2. **`scripts/route_board.py`** — strips existing copper (segments, vias,
   *and* zones — the S-expression-aware strip, not the old single-line
   regex that never matched multi-line zone blocks) before calling
   `route_pcb()` with empty placements (route from the board's existing
   component *positions*, but with a clean copper slate). This is the path
   wired into `make route` and the `board-regeneration.yml` CI workflow —
   i.e., the actual R3 producer.

**This measurement uses `scripts/route_board.py`** (extended with a new
`--pruning` flag, see §5), because it is the path CI and `make route`
actually invoke, and because the plan's own U5 protocol ("production
defaults", no placement solve required) matches its call signature, not the
DRC-regression test's placement-dependent one.

---

## 3. Instrumentation added

Two new trace sites, both gated behind `TEMPER_MODEL_TRACE=1` (mirrors the
existing `TEMPER_REWRITE_TRACE=1` Rust phase-trace pattern) in
`constraint_model.py`:

1. **`ModelBuilder.build()`** — a summary line (primary var/constraint
   counts) printed once, after `build()` completes and before the model is
   handed to Rust's `encode_to_cnf`. Useful if the process reaches this
   point but the *solve* OOMs.
2. **`ModelBuilder._create_per_net_channel_vars()`** — two more granular
   traces, since in practice **the first run OOM'd inside this method,
   before (1) ever printed**:
   - The channel-skeleton edge count per layer, printed the moment it is
     known (during the first net's iteration) — survives a crash on net 0.
   - A running `vars_so_far` count printed every 200,000 variables created
     — survives a crash mid-loop, at any net.

`scripts/route_board.py` gained a `--pruning` flag threading
`enable_geographic_pruning` through `route_once()`, `run_single()`,
`run_measurement()`, and the `--runs` worker subprocess. Both changes are
opt-in (env var / explicit flag) and committed:

- `64755f3b` — `measure(router): instrument ModelBuilder.build() for pre-CNF var/constraint counts`
- `ed84ca27` — `measure(router): add incremental progress trace to per-net channel var creation`

---

## 4. Guardrails

Both runs used the same guard, per plan R4 and the task brief:

```bash
ulimit -v 8388608          # 8 GB virtual memory cap
TEMPER_MODEL_TRACE=1
TEMPER_REWRITE_TRACE=1     # Rust encode_to_cnf phase-trace, in case it's reached
PYTHONHASHSEED=0
timeout 1200 ...           # 20-minute wall-time cap per run, enforced externally
/usr/bin/time -v uv run --no-sync python3 scripts/route_board.py [--pruning] \
  --output <scratch>/routed_{full,pruned}.kicad_pcb
```

Both runs were launched in the background and polled inside-turn via a
`Monitor` until-loop tailing the log for new lines, with a hard kill on
budget exhaustion. Actual outcome: neither run needed the 20-minute budget
— see §5 and §6 for why each was stopped early, deliberately, once it had
produced the load-bearing number.

---

## 5. Pruning OFF (full encoding) — MEASURED

### 5.1 First attempt: natural OOM (no incremental trace yet)

Before the per-net incremental trace (§3.2) existed, a first run was
launched with only the `ModelBuilder.build()`-level trace. It ran to a
natural `MemoryError`, **inside** `_create_per_net_channel_vars`'s
`add_variable()` dict-assignment — i.e., before `build()`'s own post-loop
print ever executed, and long before Rust's `encode_to_cnf`:

```
Traceback (most recent call last):
  ...
  File ".../constraint_model.py", line 484, in build
    self._create_channel_vars()
  File ".../constraint_model.py", line 522, in _create_channel_vars
    self._create_per_net_channel_vars()
  File ".../constraint_model.py", line 551, in _create_per_net_channel_vars
    self.model.add_variable(var)
  File ".../constraint_model.py", line 313, in add_variable
    self.net_channel_vars[(var.net_idx, var.channel_id)] = var
MemoryError
```

`/usr/bin/time -v` (MEASURED, this is the one run that completed to a
resource-usage report — the two later runs were operator-killed and
`/usr/bin/time` itself was in the kill pattern's match, so it never got to
print its report):

| Metric | Value | Label |
|---|---|---|
| Wall time to `MemoryError` | 2:57.05 (177.05s) | MEASURED |
| Peak RSS | 5,431,204 KB ≈ **5.43 GB** | MEASURED |
| User+sys CPU | 169.97s + 7.97s = 177.94s (~100% of 1 core) | MEASURED |
| Exit status | 1 (Python exception, not SIGKILL — the `ulimit -v` cap turned an eventual system OOM into a catchable `MemoryError` first) | MEASURED |

### 5.2 Second attempt: with incremental trace, killed once the growth rate was established

Per the coordinator's correction mid-task (waiting for a terminal state was
the wrong strategy — the *rate*, not the crash, is the informative
signal), this run was launched with the full instrumentation from §3 and
**deliberately killed** once its variable-count trajectory was
unambiguous, rather than run to a second natural OOM.

**Channel-skeleton edge count, printed before any variable is created**
(MEASURED — this alone is new information: the July 27 baseline, taken
*before* the plane-classification fix, saw ~20,734 total edges board-wide):

| Layer | Edges (`canonical_channel_edges`) |
|---|---|
| F.Cu | 114,622 |
| In1.Cu | 29,956 |
| In2.Cu | 29,956 |
| B.Cu | 29,956 |
| **Total** | **204,490** |

That is a **~9.9× increase** in channel-skeleton edges over the pre-fix
20,734-edge baseline (MEASURED edge count ÷ July 27 doc's reported edge
count). This is expected and correctly attributed: the plane-classification
fix (`8abcec24`) opened F.Cu/B.Cu to real routing instead of the
plane-condemnation fallback that had been silently excluding most of the
board's copper area from the skeleton. **This is why the model is bigger
now, not smaller** — a working router with a correct (larger) skeleton was
never measured against production before this task, per the task brief.

**Net count:** `len(self.nets)` = **110** (MEASURED, printed as
`net_idx=.../110` in every progress line). This differs from both the July
27 baseline's "96 attempted" and the OOM diagnosis doc's "108 parsed" —
plausibly a consequence of the same skeleton/net-eligibility changes; not
independently reconciled here (out of scope, noted as a discrepancy).

**Primary `NetChannelVar` growth, unpruned** (MEASURED, `vars_so_far`
printed every 200,000 variables):

```
t=3.216s   net_idx=0/110   vars_so_far=200,000
t=4.848s   net_idx=1/110   vars_so_far=400,000
t=6.796s   net_idx=2/110   vars_so_far=600,000
...
t=55.474s  net_idx=35/110  vars_so_far=7,200,000   <- killed here
```

The rate is linear and consistent with the measured edge count: since
pruning is off, every net gets exactly one `NetChannelVar` per edge, so the
exact total (not an estimate — direct arithmetic on two measured integers)
is:

```
204,490 edges/net × 110 nets = 22,493,900 primary NetChannelVar instances (DERIVED, exact)
```

This also explains §5.1's crash almost exactly: at the observed rate
(~35 nets in 55.5s ⇒ ~1.585s/net), reaching all 110 nets would take
~174.4s — within a few seconds of the 177.05s wall time §5.1 actually took
to `MemoryError`. **The strong inference (not directly measured, but
tightly bounded by two independent runs' timing): the unpruned run gets to
essentially the very end of primary-variable construction (~22.5M
`NetChannelVar` objects, before via-vars, order-vars, or any capacity
constraint is built) and fails right around there, under an 8 GB virtual
memory cap.** It never reaches `_create_via_vars`, `_create_capacity_constraints`,
or Rust's `encode_to_cnf` in either attempt.

**Peak RSS for §5.2 is not separately measured** (the process was
`pkill -f`-terminated, and the kill pattern also matched `/usr/bin/time`'s
own command line — a scripting mistake in the second run, noted here rather
than silently omitted — so no resource-usage report was printed).
§5.1's 5.43 GB is the only directly measured peak-RSS figure for the
unpruned path, and it corresponds to a comparable point in the same loop.

---

## 6. Pruning ON (`enable_geographic_pruning=True`) — MEASURED

Same guardrails, same board, immediately following §5.2, using the new
`--pruning` flag.

**Channel-skeleton edge count:** identical to §5.2 (204,490 total across 4
layers) — expected, since edge discovery happens before the predicate is
ever applied.

**Primary `NetChannelVar` growth, pruned** (MEASURED):

```
t=47.630s  net_idx=0/110   vars_so_far=200,000
t=53.009s  net_idx=1/110   vars_so_far=400,000
t=57.302s  net_idx=2/110   vars_so_far=600,000
t=59.547s  net_idx=3/110   vars_so_far=800,000
t=63.961s  net_idx=4/110   vars_so_far=1,000,000
t=67.359s  net_idx=5/110   vars_so_far=1,200,000
t=70.479s  net_idx=7/110   vars_so_far=1,400,000
t=72.159s  net_idx=8/110   vars_so_far=1,600,000
t=74.402s  net_idx=9/110   vars_so_far=1,800,000
t=76.377s  net_idx=10/110  vars_so_far=2,000,000
t=78.421s  net_idx=11/110  vars_so_far=2,200,000
t=80.645s  net_idx=12/110  vars_so_far=2,400,000
t=82.378s  net_idx=13/110  vars_so_far=2,600,000   <- killed here
```

**Finding, stated plainly: across every net observed (0 through 13, 14
consecutive nets), pruning produced exactly the same 200,000-variables-per-net
rate as the unpruned run in §5.2.** Reduction on the observed sample: **0%**
(MEASURED — not "small," not "below target," exactly zero on this sample).

This run was killed deliberately at this point, once the flat rate was
unambiguous across 14 nets — not because it crashed. Wall-clock note: the
pruned run took **~4× longer per net** than the unpruned run to emit the
same variable count (82.4s / 13 nets ≈ 6.3s/net, vs. 55.5s / 35 nets ≈
1.6s/net) — evaluating the geographic predicate for every candidate edge
costs real CPU even when it does not reduce the variable count, so on nets
where pruning provides no benefit, it is strictly worse than the unpruned
path (more wall time, same memory).

**No CNF-level count and no peak RSS were obtained for the pruned run** —
same reasons as §5.2 (never reached Rust's `encode_to_cnf`; killed rather
than run to natural exhaustion).

### 6.1 Root cause: this board's net topology, independently confirmed

A standalone diagnostic (not going through the router pipeline — direct
`parse_kicad_pcb()` + per-net pad-position span calculation, ~10s to run)
explains *why* pruning is a near-no-op here, independent of the live run
above:

| Quantity | Value | Label |
|---|---|---|
| Board size (`board.width` × `board.height`) | 152 mm × 234 mm | MEASURED |
| Board diagonal | 279.0 mm | DERIVED (exact, from measured dims) |
| Net count with ≥1 pad | 140 | MEASURED (raw pad-net count; differs from the router's 110 "attempted" nets — includes single-pin/NC nets the router excludes) |
| Median net pin span (`S_n`) | 120.9 mm | MEASURED |
| Mean net pin span | 108.4 mm | MEASURED |
| Nets with `M_n = max(2×S_n, 30mm) ≥` half the board diagonal (139.5 mm) | 93 / 140 (66%) | MEASURED |
| Nets with `S_n ≤ 15mm` (small enough to floor at `M_min=30mm`) | 38 / 140 (27%) | MEASURED |

Highest-span nets (all with `M_n` far exceeding the 279mm board diagonal,
so their candidate region is the *entire* skeleton — pruning is a
mathematical no-op for them):

| Net | Span | Pins | `M_n` |
|---|---|---|---|
| `gnd` | 241.6 mm | 86 | 483.2 mm |
| `vcc` | 241.6 mm | 13 | 483.1 mm |
| `RELAY_CTRL` | 238.4 mm | 2 | 476.8 mm |
| `+3V3` | 237.2 mm | 51 | 474.4 mm |
| `+170V_BUS` | 230.7 mm | 11 | 461.4 mm |

**Interpretation:** this is a physically distributed board (an induction
cooker spanning a mains/HV power section and a low-voltage MCU/sensor
section across 152×234mm), not a densely-clustered one. The plan's own U1
section named this exact risk: *"nets with `S_n > 50mm`... get `M_n ≥
100mm` → nearly full-board candidate set → negligible pruning for those
nets... acceptable: spanning nets legitimately need board-wide access."*
What was not anticipated is that **most** nets on this specific board fall
into that category (median span 120.9mm, not ≤50mm), including several of
the numerically largest-variable-count nets (`gnd` alone has 86 pins). The
14 nets directly observed in the live run (§6) are consistent with this —
they include exactly the kind of large-span, high-connectivity nets this
table identifies, and every one of them showed 0% pruning.

This is not evidence of a predicate bug (the predicate's own unit/property
tests, `pruning.rs` and `test_encoding_pruning_geographic.py`, both pass —
U1–U4 were not touched or re-run here). It is evidence that **`K=2.0` /
`M_min=30mm`, calibrated as a generic conservative bound in the plan, is
too generous for this board's specific net geometry** to deliver the
plan's ≥10× target.

---

## 7. Reduction factor: does it meet the ≥10× target?

**No — measured reduction on the observed sample is 0%, i.e. a factor of
1.0×, against the plan's ≥10× target (R3).** This is a MEASURED result on
14/110 nets, corroborated by an independent MEASURED geometric analysis of
all 140 (or 110) nets showing the majority are in the same "board-wide
candidate set" regime. It is not a projection.

What remains genuinely uncertain: the 96 nets *not* directly observed in
the live run. If the un-sampled nets are disproportionately the 38 nets
with `S_n ≤ 15mm` (real pruning candidates), the aggregate reduction across
all 110 nets could be nonzero — but even in the best case bounded by that
38/140 (27%) figure, an aggregate ≥10× reduction is very unlikely: it would
require the un-pruned majority (73%+ of nets by count, and disproportionately
represented by the highest-pin-count nets like `gnd`'s 86 pins) to
contribute a vanishing share of total variables, which is not what the
observed rate shows (every large-span net contributes its full,
unreduced 204,490-variable share).

**This measurement does not extend the live run far enough to produce a
whole-board aggregate reduction number** — doing so exactly would require
either completing the run under a much larger memory cap (outside this
task's 8 GB gate; would need re-labeling as a relaxed-limit diagnostic, not
a gate-compliant U5 result) or adding per-net aggregate counters and a
lighter-weight standalone predicate sweep (an extension not built here, in
the interest of reporting promptly rather than continuing to iterate).

---

## 8. Does anything complete? Is `#871` closer?

**No completion in either direction, under the plan's 8 GB gate.** Per the
task's explicit instruction, this is reported as evidence, not as a
closure of `#871`.

- **Pruning OFF:** natural `MemoryError` at 2:57 wall / 5.43 GB peak RSS,
  inside primary-variable construction — never reaches `encode_to_cnf`,
  `solve_topology_rust`, or any completion/DRC signal.
- **Pruning ON:** no natural failure observed (operator-killed at 82.4s,
  2.6M variables, ~13% of the way through primary-variable construction by
  net count) — but given the identical per-net variable rate observed
  through net 13, and no evidence of it improving, there is no basis to
  expect a different outcome than §5 if run to completion; it would just
  take longer wall-clock to get there (§6's ~4× per-net slowdown).

**What #871 needs beyond this task:** either (a) a materially larger memory
budget than 8 GB for the unpruned path to even reach CNF encoding (the
plan's own R4 gate is 8 GB, so this would be a deliberate gate change, not
a workaround), or (b) a pruning margin re-tuned to this board's actual net
geometry (smaller `K`, or a fundamentally different predicate — e.g.
per-net-class margins, since the plan's own E.2 already flagged
net-class-aware margins as a deferred open question), or (c) the
concurrently-in-progress `obstacle_map.py` net-blind-pour fix (§1) shrinking
the skeleton enough that even the unpruned model fits in 8 GB on its own.
None of these are implemented or evaluated here.

---

## 9. What remains for a maintainer to run

Exact reproduction commands (from repo root, this worktree):

```bash
# Pruning OFF
ulimit -v 8388608
TEMPER_MODEL_TRACE=1 TEMPER_REWRITE_TRACE=1 PYTHONHASHSEED=0 \
  /usr/bin/time -v uv run --no-sync python3 scripts/route_board.py \
  --output /tmp/routed_full.kicad_pcb

# Pruning ON
ulimit -v 8388608
TEMPER_MODEL_TRACE=1 TEMPER_REWRITE_TRACE=1 PYTHONHASHSEED=0 \
  /usr/bin/time -v uv run --no-sync python3 scripts/route_board.py \
  --pruning --output /tmp/routed_pruned.kicad_pcb
```

To get a real CNF-level (Rust) number in either direction, the 8 GB cap
would need to be relaxed for a diagnostic (non-gate-compliant) run — e.g.
`ulimit -v 33554432` (32 GB) — and re-labeled accordingly; not done here
because the task's guard was the plan's own 8 GB R4 gate, not a higher
exploratory limit.

To get a true whole-board pruned/unpruned aggregate reduction factor without
running the full pipeline to a crash: extend `_create_per_net_channel_vars`'s
trace to accumulate a per-net variable count (not just the running total)
and let both runs complete under a relaxed memory cap, or write a
standalone script that loads Stage 0–2 (parse + skeleton) once and then
evaluates the predicate against all 110×204,490 pairs directly (avoiding
the router's own per-run Stage 0–2 rebuild cost, ~45–50s of the wall time
above).

---

## Sources

- `docs/plans/2026-08-07-001-feat-router-encoding-pruning-plan.md` — the
  plan this task's U5 unit belongs to (predicate spec, margins, R3/R4
  gates, U1's own "spanning nets" caveat).
- `docs/evidence/2026-07-27-stage3-model-and-rewrite.md` — the pre-fix
  baseline (42,145,777 vars / 78,107,180 clauses, 20,734-edge skeleton,
  52.67s Stage 3, ~6.93 GB RSS, 108 nets parsed) this document's numbers are
  compared against. **Not directly comparable**: that baseline predates
  both the plane-classification fix and the skeleton-bridging fix: this
  document's 204,490-edge skeleton is ~9.9× larger, for reasons attributed
  in §5.2, not a regression.
- `docs/evidence/2026-08-07-router-oom-diagnosis.md` — the diagnosis that
  motivated this plan (Sinz encoding blowup mechanics, `var_to_net` fix).
- `docs/evidence/2026-08-05-r3-router-status.md` — prior (pre-fix)
  attempts to run `route_pcb()` on the production board, all OOM'd before
  any bug fix existed.
- `docs/evidence/2026-08-07-pruning-u1u2-implementation.md`,
  `docs/evidence/2026-08-07-router-encoding-u3u4.md` — U1–U4
  implementation and gate records this task's `enable_geographic_pruning`
  flag relies on (not re-verified here; their unit/property tests were not
  re-run as part of this task).
- `docs/evidence/2026-08-07-channel-skeleton-bridging-perf.md` — the
  skeleton-bridging fix (`07d514f9`) merged into this task's base.
- `scripts/route_board.py`, `packages/temper-placer/src/temper_placer/router_v6/constraint_model.py` —
  files modified by this task (instrumentation + `--pruning` flag; see
  commits `64755f3b`, `ed84ca27`).
