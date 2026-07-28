# Forced-segment-disallowed analysis: mechanism, falsifier, and why no fix was committed

<!-- provenance: base commit=6b421099 (docs/methodology-loop-discipline canonical
tip), worktree agent-ac9040ce7a4ff852b -->

**Date:** 2026-07-27

**Task:** 45 nets on the committed board (`pcb/temper.kicad_pcb`, 51/96 =
53.1%) fail with `no legal path found (forced segment disallowed)`. Find
out why, and fix what can be fixed.

## Falsifier, stated before diagnosing

**"The 45 failures share a cause in name only, and the underlying
geometry differs per net."**

**Result: fired — confirmed.** Per-net instrumentation (below) found at
least two mechanistically distinct failure shapes hiding behind the one
error string, and neither responds to the same fix.

## Part 0 — Reproducibility note (read this before the numbers below)

The committed board's 45-failure / 51-96 (53.1%) figure comes from
`docs/evidence/2026-07-27-committed-route.md`, written **before**
`docs/evidence/2026-07-27-router-determinism.md` fixed a `uuid4()`
non-determinism bug and settled the reproducible rate at 36/96 (37.5%) on
that day's netlist. On today's HEAD (6b421099), re-running the documented
production entry point (`route_pcb(parsed_stub, {}, design_rules=...)`,
empty placements → routes the board's existing positions, matching every
prior measurement's call site) gives **37/96 = 38.5% (59 unrouted)**,
byte-identical across every run in this task (4 independent runs, see Part
4). This is one net better than the determinism doc's 36/96, plausibly
from an intervening commit (netlist resync changed footprint count
170→168) — not traced further, **UNVERIFIED**.

**All analysis below is against this task's own reproducible 59-net
failure set**, not the stale 45-net committed-board set — the mechanism
findings apply equally to both (same code, same error string, same
router), but the committed board is a fixed historical artifact this task
did not re-produce or supersede (no board write occurred — see Part 5).
The committed board's own 45-net subsystem breakdown from the prior doc is
reproduced in Part 1 for continuity with the task brief; Part 1 also gives
the fresh 59-net breakdown measured in this task.

## Part 1 — Subsystem breakdown

**Committed board (51/96, 45 failures — from `2026-07-27-committed-route.md`, not reproduced here):**

| Subsystem | Failed nets |
|---|---:|
| `safety.*` | 12 |
| Misc signals | 15 |
| `discharge.*` | 6 |
| `RTD_*`/`rtd_pan.*` | 6 |
| Gate-drive/PWM | 3 |
| `tank*` | 2 |
| `power_in.*` | 1 |
| **Total** | **45** |

**This task's reproducible run (37/96, 59 failures):**

| Subsystem | Failed nets |
|---|---:|
| Misc signals | 20 |
| `safety.*` | 16 |
| `RTD_*`/`rtd_pan.*` | 7 |
| Gate-drive/PWM | 6 |
| `discharge.*` | 6 |
| `power_in.*` | 2 |
| `tank*` | 2 |
| **Total** | **59** |

Same shape (safety/misc/RTD/gate-drive/discharge dominate both), consistent
with one underlying mechanism family, not 45 (or 59) unrelated bugs.

## Part 2 — What the mechanism actually rejects

Traced the full call chain for a two-terminal net's segment search
(`packages/temper-placer/src/temper_placer/router_v6/_astar_reconstruct.py`):

1. `attempt_route()` computes a per-net A* iteration cap from a
   straight-line ellipse between the net's first and last waypoint
   (`span_cells → π×(span/2)²`, floored at 1000, ceiled at `grid_area`,
   then capped again by the pipeline's global `max_iter`).
2. `_astar_route_multilayer()` tries, per waypoint pair, in order:
   **(a)** coarse-to-fine A* on the primary grid (a 4x-downsampled coarse
   pass, then either a corridor-constrained fine pass or an unconstrained
   fine-grid fallback — both via the Numba kernel, `astar_core_numba.py`),
   **(b)** the same coarse-to-fine sequence on the alternate-layer grid if
   one exists and the board has any THT pads anywhere, **(c)** a bounded
   3D via-aware fallback (`_route_segment_3d`, 200,000-iteration cap).
3. If **all** tiers fail for **any** waypoint pair, `_astar_route_multilayer`
   returns a path with `forced_segment_count=1` instead of splicing in an
   unchecked direct line.
4. `attempt_route()` sees `forced_segment_count > 0` and reports the net as
   failed with the string in question — **it never fabricates the illegal
   segment.** `_allow_forced_segments()` is hard-coded `False` for every
   net class (this branch's whole subject); this is not a bug, it is the
   fail-closed gate doing exactly its documented job.

**So "forced segment disallowed" means: "A* (2D primary + 2D alternate +
3D via fallback, each coarse-to-fine) could not prove a legal,
clearance-respecting path exists for at least one waypoint pair, within
its search budget."** That sentence bundles at least two different
underlying situations, which is exactly what the falsifier predicted.

## Part 3 — Per-net diagnostic: cap-limited vs. genuinely exhausted

Instrumented (read-only monkeypatches, no source changes) the Numba
kernel wrapper to record, per call: the iteration cap passed in, the
actual iterations consumed, and whether a path was found. This
distinguishes "the search was cut off before it could decide" (`iters ==
cap`) from "the search proved no path exists" (`iters < cap`, frontier
genuinely emptied).

**At the production cap (500,000):**

| | Count | % |
|---|---:|---:|
| Hit the cap exactly on every failing tier call | 43 | 73% |
| Exhausted the frontier immediately (`iters == 1` on every tier) | 16 | 27% |

The 73% figure looked, at first, like the smoking gun for "over-restrictive
cap" — see Part 4 for why that reading did not survive a direct test.

## Part 4 — Is the cap over-restrictive? Tested directly, not inferred

**Swept the production `max_iter` from 500k (current) up to 4,000,000 (8x)
on the actual board**, re-measuring completion at each value:

| `max_iter` | Completion | Unrouted | Wall (s) | Output hash (16 hex) |
|---:|---:|---:|---:|---|
| 500,000 (current) | 37/96 = 38.5% | 59 | 56.1 | `87a10b057aa8c279` |
| 1,000,000 | 37/96 = 38.5% | 59 | 61.1 | `392919572c5bbada` |
| 2,000,000 | 37/96 = 38.5% | 59 | 61.2 | `3f3e28a43343e15f` |
| 4,000,000 | 37/96 = 38.5% | 59 | 62.6 | `3f3e28a43343e15f` |

**The failure count never moved across an 8x budget range.** 2M and 4M
produced byte-identical output. 500k→1M *churned* the specific failing set
(`RELAY_CTRL` and `safety.thermal-line` started succeeding; `sdi` and
`safety.ovp.r_adc_top2-p2` started failing) without changing the total —
a tie-break/path-choice effect, not a capacity effect. This exactly
matches a documented finding on a much smaller 24-net smoke subset
(`docs/solutions/architecture-patterns/router-v6-closure-rate-100pct-2026-06-24.md`:
*"a higher cap leads to different tie-breaks... path quality, not iter
count, is the ceiling"*) — now confirmed to also hold at full-board scale.

**Re-ran the per-net cap-hit diagnostic at the 4,000,000 ceiling** (a
ceiling close enough to the fine grid's own cell count — 3,712,800 cells —
that it is close to "search everything reachable"):

| | Count at 500k | Count at 4M |
|---|---:|---:|
| Hit the cap exactly | 43 | **3** |
| Genuinely exhausted (`iters < cap`) | 16 | **56** |

**Verdict: the cap is not the binding constraint.** At 4M, 56 of 59
failing nets provably exhaust their reachable search space without finding
a path — several (e.g. `RTD_DRDY`: 3,410,300 of 3,712,800 cells, 92%)
came close to exploring the entire connected grid. Only 3 nets
(`hb.gate_hs.driver-p1`, `i2c_scl_ui`, `power_in.bypass_relay-coil1`)
still hit a cap at 4M, and that cap is itself already at (or very near)
the grid's total cell count, so raising it further is not meaningful —
there is nothing left to search.

**Conclusion for this axis: the fail-closed gate is correct, and for the
large majority of these 59 nets, so is the "no legal path found" verdict —
this is a finding about the board (placement density/congestion at this
net order), not a router bug or a mistunable parameter.**

## Part 5 — The 27% "immediate exhaustion" bucket, and why it wasn't a quick fix either

The 16 nets with `iters == 1` on every tier looked like a different,
possibly more fixable bug: the start (or goal) cell has *zero* free
8-neighbors, meaning the pad is completely boxed in. Dumped the primary
grid's 5×5 neighborhood around `RELAY_CTRL`'s start waypoint at the
4,000,000-cap configuration: **every one of the 25 cells was occupied by a
single other net's ID** — a real, complete box-in by already-routed copper
at the point in the fixed net order when `RELAY_CTRL` is attempted (not a
grid-rounding or off-by-one artifact; the same neighborhood was free in a
different-cap run, confirming this is order/tie-break-dependent, not a
fixed placement defect).

This looked promising because the router already computes exactly this
information: `_astar_route_with_ripup()` calls `_identify_blocking_nets()`
for every forced-segment failure and returns the blocker net IDs. **But
the actual rip-up code (`_mark_route_blocked`/`reroute_queue.append`) is
only reached on the `forced_segment_count == 0` success branch — for a
forced-segment failure, `attempt_route()` returns early with "no legal
path found" before ever reaching it.** The blockers are recorded into
`blocker_history` for the failure report only; nothing acts on them. This
is a genuine, identifiable dead code path.

**Checked how many of the 59 failures have a small, single-blocker
signature that this dead path could safely resolve:** patched
`_identify_blocking_nets` to log its result for every failing net.

| Blocker-set size | Net count |
|---:|---:|
| 0 (no straight-line blocker found) | 2 |
| 1 | 2 |
| 2 | 4 |
| 3 | 6 |
| 4 | 4 |
| 5 | 6 |
| 6–13 | 35 |

**57/59 failing nets have an identifiable straight-line blocker, but the
median is 7–9 distinct blocking nets, not one.** Most of these lines cross
a dense thicket of already-routed copper, not a single net in the way.
Wiring up rip-up-and-reroute for this case would mean ripping up 6–13
other successful nets per failure with no guarantee of net improvement,
and a real risk of thrashing or regressing currently-successful routes —
not something to land inside this task's time/verification budget on a
gate that already went through a nine-reviewer review. **Only 2/59 nets
have a clean single-blocker signature** — too small a yield to justify the
engineering and regression risk. Reported as a scoped follow-up (Ranked
follow-ups, below), not attempted.

## Part 6 — Constraint verdict

**Correct and the board is too tight, not over-restrictive**, for the
substantial majority (56+/59) of current failures:

- The fail-closed gate itself: **correct, untouched, should stay exactly
  as strict.** It never fabricates unchecked copper; every failure it
  reports is either a proven unreachable path or (a small remainder) a
  search the router chose not to fund further because funding it further
  demonstrably does not help (Part 4).
- The iteration-cap heuristic: **not the lever.** Empirically tested
  across an 8x range with a fully-instrumented before/after; total
  completion never moved. Comment updated in place
  (`_pipeline_core.py`, `_adapter_convert.py`) to record this so a future
  agent does not re-derive the same 8x sweep from scratch.
- The rip-up-and-reroute dead code path: **a real gap, but not a safe,
  well-scoped fix for this board today** — the blocker-count distribution
  shows most failures are genuine multi-net congestion, not a single
  net's copper in the way.

## Part 7 — Fix applied

**None that improved completion.** Two candidate changes were built,
measured, and reverted or scoped down:

1. An 8x multiplier on the ellipse-derived per-net iteration budget
   (`_ELLIPSE_DETOUR_SAFETY_FACTOR`) — reverted after measurement showed
   it produced **byte-identical output** to no change at all, because the
   pipeline's hardcoded `max_iter=500_000` ceiling
   (`_adapter_convert.py:258`) was already the binding constraint for
   every net the multiplier would have affected. Superseded by the direct
   500k→4M sweep in Part 4, which tested the real binding parameter
   directly instead.
2. Wiring up the rip-up-and-reroute dead path for forced-segment
   blockers — scoped down to a measurement (Part 5) after the blocker-set-
   size distribution showed the yield (2/59 clean single-blocker nets)
   did not justify the regression risk within this task.

**What was actually committed: two documentation-only comment updates**
(`_pipeline_core.py`, `_adapter_convert.py`) recording that the 500k
"sweet spot" claim, previously validated only on a 24-net smoke subset,
has now been re-validated on the full 96-net production board and holds
(500k is no worse than spending 8x more compute) — closing the
documented-precondition gap the task asked to watch for, in the direction
of "still holds," this time.

## Completion rate before and after

| | Completion | Unrouted | Notes |
|---|---:|---:|---|
| Before (HEAD, unmodified) | 37/96 = 38.5% | 59 | `sha256=87a10b05...` |
| After (comment-only changes) | 37/96 = 38.5% | 59 | `sha256=87a10b05...` — **identical**, as expected for a documentation-only diff |

No `pcb/temper.kicad_pcb` write was made — the task permits committing a
re-routed board only if completion improves, and it did not.
`check_copper_net_consistency.py` was re-run anyway (Part 8) and stays
green against the existing committed board.

## Part 8 — Determinism re-proof and gate states

**4 independent process launches** of the production `route_pcb()` call
against today's board, both before and after the comment-only edits, all
byte-identical:

```
87a10b057aa8c279a87a57172f7e32cac990aafd334fb562e0cbcf74a9d0ca4d  (baseline run 1)
87a10b057aa8c279a87a57172f7e32cac990aafd334fb562e0cbcf74a9d0ca4d  (sweep, max_iter=500_000, matches production default)
87a10b057aa8c279a87a57172f7e32cac990aafd334fb562e0cbcf74a9d0ca4d  (final, post-edit, run 1)
87a10b057aa8c279a87a57172f7e32cac990aafd334fb562e0cbcf74a9d0ca4d  (final, post-edit, run 2)
```

**Determinism holds.**

| Check | Result |
|---|---|
| `make netlist` | 76 assertions, 76 passed, 0 failed |
| `scripts/check_domain_partition.py` | exit 0 — 0 domain crossings, 0 isolator-barrier breaches, 0 protective-impedance chain defects |
| `scripts/capacity_budget_gate.py` | exit 0 — 0 defects |
| `scripts/mpn_fabrication_gate.py` | exit 0 — 0 new violations |
| `scripts/check_derived_doc_drift.py` | exit 0 — 3 documents, 45 tables, 52 gate rows matched, 132 fields checked |
| `scripts/check_vacuous_gates.py` | exit 0 — 533 files scanned, 0 violations |
| `scripts/check_copper_net_consistency.py` | exit 0 — 2482/2482 copper items checked, 510 pads checked, 0 violations |
| `tests/requirements/safety/` | 54 passed |
| `cargo test --release` (temper-rust-router-core) | 101 passed (90+1+1+8+1+0 across 6 binaries), 0 failed |

## Ranked follow-ups (reported, not attempted)

1. **Wire up rip-up-and-reroute for the 2 clean single-blocker
   forced-segment failures**, conservatively (only when exactly one
   already-routed net is identified as the straight-line blocker, to
   avoid the thrashing risk the 6–13-blocker majority would carry).
   Smallest possible version of Part 5's finding; would need its own
   before/after measurement and a bound on total rip-up attempts to avoid
   interacting badly with `_MAX_REROUTE_ATTEMPTS_PER_NET`.
2. **Net-ordering or placement-density work**, not iteration-cap tuning,
   is the correct lever for the remaining ~56 genuinely-congested
   failures — per Part 4's finding that search budget is not binding.
   Out of scope for a router-mechanism task; this is a placement/board
   finding, consistent with the task's own explicit alternative branch.
3. **Investigate why 500k→1M churns the specific failing set** (Part 4) —
   the underlying tie-break sensitivity (which net wins a contested cell
   first) was described but not traced into the Numba kernel's priority
   comparison; doing so might explain *why* some orderings are
   systematically better without brute-force sweeping.

## UNVERIFIED

- Root cause of the 1-net difference between this task's 37/96 baseline
  and `docs/evidence/2026-07-27-router-determinism.md`'s 36/96 — plausibly
  the intervening 170→168 footprint netlist resync, not traced to a
  specific commit.
- Exact failing-net-set diff between `max_iter=1,000,000` and
  `max_iter=2,000,000` in the Part 4 sweep (the byte-identical 2M/4M
  result and the invariant total count across the whole range make this a
  minor supplementary detail, not re-derived after the raw sweep JSON was
  cleaned up).
- Whether the 3 nets that still hit their cap at 4,000,000
  (`hb.gate_hs.driver-p1`, `i2c_scl_ui`, `power_in.bypass_relay-coil1`)
  would resolve with a literally uncapped search — not tested, since their
  4M cap is already at or near the fine grid's total cell count, making an
  even larger cap search-space-meaningless rather than budget-limited.
- Whether the 2 clean single-blocker nets identified in Part 5 would
  actually succeed if their blocker were ripped up (only the blocker-count
  was measured, not a live rip-up trial).
- Why exactly 2/59 failing nets return an empty blocker set from
  `_identify_blocking_nets` (no straight-line obstruction identified at
  all, yet still forced-segment-failed) — not traced; plausibly a
  different waypoint-pair failure within a multi-segment net, or an
  off-grid/bounds edge case distinct from both buckets above.
