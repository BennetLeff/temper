<!-- provenance: commit=4455284848b08253b2a81a0c8a3bdc7a0e1da75a dirty=false -- code commits b5b4b124/44552848 (this task, full SHA of the latter cited above); board pcb/temper.kicad_pcb sha256 1cce4a0872051675b0339de3378ff7ec2c16bb4b035c999dfa408dec5ecbc3f6 unchanged from the prior evidence doc; measured live this task -->

# Subprocess-per-batch net-batching on the production board: all 11 Stage 3 batches complete for the first time, 0 crashes, RSS creep eliminated -- Stage 4 (unmodified) leaves 44/110 nets unrouted

**Date:** 2026-08-08

**Headline, stated plainly up front:** `docs/evidence/2026-08-07-net-batching-prototype.md`
died at batch 5 of 11 to an uncatchable Rust allocator `abort()`, having
completed 50/110 nets (45.5%). Running each batch in a fresh
`multiprocessing` (spawn) subprocess instead of in-process, **all 11
batches now complete: every one of the 110 nets receives a real
SAT-derived Stage 3 topology, 0 lost to a crash, 0 falling back to Stage
4's no-topology path.** Peak RSS across batches ranges 5.01-5.51GB with no
monotonic trend (contrast: the prior run crept 5.21GB -> 5.78GB batch over
batch before dying) -- the RSS-creep hypothesis is confirmed **and
eliminated**. This is the first time Stage 3 has ever completed for every
net on this board.

**The board still does not route end-to-end at the copper level.** Stage 4
(geometric A* realization -- unmodified by this task, exactly as it ran
before) leaves 44/110 nets unrouted ("no legal path found (forced segment
disallowed)"), a pre-existing Stage 4 limitation this task's change does
not touch and does not claim to fix. Net-batching's job -- get every net a
Stage 3 topology instead of dying during model construction or a mid-run
crash -- is now fully done; Stage 4 completion is a separate, downstream
problem.

---

## 1. Per-batch measurements (MEASURED, live run)

Board: `pcb/temper.kicad_pcb`, 110 nets, sha256
`1cce4a0872051675b0339de3378ff7ec2c16bb4b035c999dfa408dec5ecbc3f6`
(**unchanged** by this task). `batch_size=10` (11 batches, subprocess-per-batch,
`subprocess_timeout_s=900`). Guarded with `ulimit -v 8388608` (8GB),
`PYTHONHASHSEED=0`, `TEMPER_BATCH_TRACE=1`, `timeout 7200`, `/usr/bin/time -v`,
backgrounded and polled in-turn (bounded `until`-style poll loop, not a
blind wait).

| Batch | Nets | Status | Primary vars | net_channel | via | Constraints | Wall (s) | Peak RSS (this batch's own subprocess) | Retried | Crashed nets |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 10 | **sat** | 2,992,330 | 2,044,900 | 947,430 | 109,124 | 44.58 | 5,147,060 KB (5.15 GB) | 0 | 0 |
| 1 | 10 | **sat** | 2,992,330 | 2,044,900 | 947,430 | 109,145 | 48.28 | 5,513,080 KB (5.51 GB) | 0 | 0 |
| 2 | 10 | **sat** | 2,992,330 | 2,044,900 | 947,430 | 109,154 | 48.43 | 5,082,180 KB (5.08 GB) | 0 | 0 |
| 3 | 10 | **sat** | 2,992,330 | 2,044,900 | 947,430 | 109,181 | 50.90 | 5,500,572 KB (5.50 GB) | 0 | 0 |
| 4 | 10 | **sat** | 2,992,330 | 2,044,900 | 947,430 | 109,154 | 46.03 | 5,009,928 KB (5.01 GB) | 0 | 0 |
| 5 | 10 | **sat** | 2,992,330 | 2,044,900 | 947,430 | 109,235 | 59.55 | 5,178,412 KB (5.18 GB) | 0 | 0 |
| 6 | 10 | **sat** | 2,992,330 | 2,044,900 | 947,430 | 109,142 | 47.63 | 5,504,740 KB (5.50 GB) | 0 | 0 |
| 7 | 10 | **sat** | 2,992,330 | 2,044,900 | 947,430 | 109,160 | 48.90 | 5,470,176 KB (5.47 GB) | 0 | 0 |
| 8 | 10 | **sat** | 2,992,330 | 2,044,900 | 947,430 | 109,169 | 48.99 | 5,312,296 KB (5.31 GB) | 0 | 0 |
| 9 | 10 | **sat** | 2,992,330 | 2,044,900 | 947,430 | 109,196 | 55.91 | 5,207,452 KB (5.21 GB) | 0 | 0 |
| 10 | 10 | **sat** | 2,992,330 | 2,044,900 | 947,430 | 109,595 | 130.46 | 5,375,748 KB (5.38 GB) | 0 | 0 |

**Batch 5 in this run is not the batch 5 that crashed in the prior run in
any meaningful sense beyond the index** -- this run's batch 5 completed SAT
cleanly at 59.55s / 5.18GB, well inside budget. Batch 10 (the last batch,
containing the `mcu`/`safety` hub-block nets deferred to the end by
`order_nets_for_batching`) took noticeably longer (130.46s vs. ~45-60s for
every other batch) and has the highest constraint count (109,595 vs.
~109.1-109.2K elsewhere), consistent with the ordering design putting the
most cross-cutting congestion last -- but it still completed SAT at batch
granularity, no retry needed.

- **Total Stage 3 wall time**: 631.10s (MEASURED, `[batch-trace] done` line).
- **Total run wall time** (Stage 0-2 setup + Stage 3 batching + Stage 4
  A*): 768.7s per `route_once()`'s own timer; 769.75s (12:49.75) per
  `/usr/bin/time -v`'s independent wall-clock measurement -- the two agree
  to within a second.
- **Whole-run peak RSS** (`/usr/bin/time -v` "Maximum resident set size",
  covering the orchestrator process's own footprint plus everything
  `wait()`-reaped from its child subprocesses over the entire run, not
  just Stage 3): 5,513,080 KB (5.51 GB) -- numerically identical to batch
  1's own self-reported peak, i.e. the single largest moment of memory use
  in this entire 769s run was one batch's own subprocess, not an
  accumulation across batches. **Comfortably under the 8GB cap**, with
  ~2.5GB of headroom to spare, where the prior run had none left by batch 5.
- **Nets that reached a Stage 3 topology**: **110/110 (100%)** -- 0 fell
  back to Stage 4's no-topology fallback path (`[batch-trace] done` line:
  "0/110 nets fell back"). This is new: the prototype run reached 50/110
  (45.5%) before crashing; the monolith reaches 0/110 (OOMs during
  variable construction).
- **Batch-level crashes**: **0**. No singleton retries were needed at any
  batch (every `retried`/`crashed_nets` column above is 0) -- unlike the
  prototype run, which needed singleton retry twice (batches 1 and 3, both
  genuine UNSAT). This run's batches were all SAT at full batch
  granularity on the first attempt.

---

## 2. Does RSS creep still happen? **No -- eliminated, not just survived.**

The prototype run's own diagnosis (§4 of the prior evidence doc): peak RSS
crept monotonically batch-over-batch -- 5.21 -> 5.73 -> 5.73 -> 5.78 ->
5.78 GB -- even though each batch's model was discarded after use, and
that shrinking headroom was named as the proximate cause of the batch-5
crash (a same-sized batch failing only because less room was left for it).

This run's 11 peak-RSS figures, in batch order (GB): **5.15, 5.51, 5.08,
5.50, 5.01, 5.18, 5.50, 5.47, 5.31, 5.21, 5.38**. Min 5.01GB (batch 4), max
5.51GB (batch 1), range 0.50GB, **no monotonic trend** -- the values
oscillate within a ~0.5GB band around a ~5.3GB mean with the same net
count and constraint count every batch, which is exactly what "each
batch's subprocess starts from a genuinely fresh interpreter heap, uses
what it needs, and hands back a small result" predicts. This is the
mechanism working as designed, not merely "the crash stopped happening
for some other reason": each subprocess is a brand-new `spawn`-context
Python interpreter (not a `fork` of the orchestrator's current heap), so
there is no *possible* channel for one batch's Rust/CPython allocator
arena state to carry into the next -- the two processes never share
address space to begin with.

---

## 3. Does it get past batch 5? **Yes -- all the way through batch 10.**

Every batch from 0 through 10 (the last one) completed. This is new
ground: no attempt on this board -- monolithic or the first net-batching
prototype -- has ever gotten Stage 3 past batch 5 (50/110 nets) before
this run.

---

## 4. Does the board route end-to-end? **Stage 3: yes, for the first time. Stage 4 (unmodified): no, 44/110 nets unrouted.**

Two different questions, deliberately not conflated:

- **Stage 3 (what this task's change touches): complete.** All 110 nets
  got a real SAT-derived topology from a batch that solved SAT at full
  batch granularity (no batch needed singleton retry or fallback). This
  is the first time this has ever happened on this board -- the
  headline claim of this document.
- **Stage 4 (geometric A* realization on the occupancy grid, byte-for-byte
  unmodified by this task -- see the module docstring's "what this does
  and does not preserve" section): 44/110 nets unrouted**, all with the
  reported reason "no legal path found (forced segment disallowed)".
  Segments/vias/zones actually written: **3,058 segments, 50 vias, 32
  zones** (MEASURED both from `route_once()`'s own counters and by direct
  `grep -c` against the output `.kicad_pcb` file -- the two agree
  exactly). `route_once()`'s own completion-rate arithmetic reports
  "54/98 nets (55.1%)" -- that denominator (98, not 110) is a
  reconstruction artifact of that script's own pre-existing
  `attempted = round(unrouted / (1 - completion_rate))` formula (see
  `scripts/route_board.py`'s own comment on that line), not a directly
  measured net count; the directly measured figures are completion_rate
  (0.551) and the 44-net unrouted list below, both taken as-is from
  `RoutingResult`.
  Unrouted (44, MEASURED, names from the run's own output): `GATE_LS`,
  `RELAY_CTRL`, `RTD_DRDY`, `RTD_SCK`, `WDT_KICK`, `WDT_RESET_N`, `bias`,
  `boot`, `cs_n`, `discharge.k_dis1-coil1`, `discharge.k_dis2-coil1`,
  `discharge.r_dis1a-p2`, `discharge.r_dis2a-p2`, `discharge.r_snub1-p2`,
  `discharge.r_snub2-p2`, `fb`, `hb.power_loop.q_high-g`, `i2c_sda_ui`,
  `power_in.bypass_relay-coil2`, `power_in.ntc-no`,
  `power_in.q_relay_drv-g`, `refin_n`, `rtd_pan.low_window-out`,
  `rtd_pan.rail_monitor-ina_p`, `rtd_pan.rail_monitor-outa`,
  `safety-line`, `safety-line-2`, `safety-line-3`,
  `safety.coil_thermal-line`, `safety.fault_any_or-y2`,
  `safety.fault_or-a2`, `safety.fault_or-b2`, `safety.fault_or-y2`,
  `safety.ovp-line`, `safety.ovp.r_div_top2-p2`, `sdi`, `sdo`, `sw`,
  `tank-out`, `tank.c_tank1-p2`, `thermal.j_fan-p1`, `vbias`, `w1_1`,
  `w1_2`.

  Because Stage 3 gave every one of these 44 nets a real topology (0 nets
  fell back to Stage 4's no-topology fallback path, per §1), their Stage 4
  failure is **not** a net-batching artifact -- it happens downstream, in
  the same unmodified A*-on-occupancy-grid pass that has always run once
  over the complete net list regardless of how Stage 3 produced its
  topology (see the module docstring's Stage 4 section, and
  `_adapter_convert.py`'s own prior note that this board's forced-segment
  failures are "congestion/placement-limited, not search-budget-limited").
  Diagnosing *why* Stage 4 fails these specific 44 nets is out of scope
  for this task (Stage 4 is explicitly not to be modified here) and is
  flagged as a separate follow-up.

- **Output was never written to `pcb/temper.kicad_pcb`**: `--output`
  pointed at a scratch path
  (`temper_routed_subprocess_batched.kicad_pcb`); the production board
  file's content hash was re-verified unchanged after the run.

---

## 5. DRC: still UNVERIFIED in this environment (unchanged gap)

Same finding as the prior evidence doc: `kicad-cli` is not installed in
this sandbox (`which kicad-cli` -> not found) and is not installable
without sudo (see `docs/solutions/workflow-issues/2026-07-18-plan-execution-and-ci-rot-excavation.md`).
This run does have a routed board to check DRC against (unlike the
prototype run, which never reached Stage 4 at all) -- so unlike before,
this is now a checkable gap, just not checked in this environment. Flagged
as an open follow-up rather than glossed over.

---

## 6. Crash-vs-UNSAT isolation: proven at the unit level, not exercised live this run

No batch crashed in this run (§1) -- 0/11 batches needed the crash-recovery
path, so there is no live production data point demonstrating "one batch
lost, prior batches' results retained, run continues" on this board. That
mechanism is instead verified directly by
`packages/temper-placer/tests/router_v6/test_net_batching_subprocess.py`
(10 tests, all passing): a child that dies to `SIGABRT` is reported
`crashed=True` with a distinct reason string, never conflated with a
`"unsat"`/`"unknown"` result; a child that hits a *catchable* `MemoryError`
still sends a clean result and is *not* reported as crashed; a result
that is received is trusted regardless of the child's subsequent exit
path; and a hung child past the timeout budget is correctly reported as
crashed rather than silently waited on indefinitely (this last case is a
real bug this test suite caught and fixed during development -- the
initial implementation's 30s post-timeout join grace period let a
merely-slow child finish normally just after its result had already been
given up on, producing a misleading "exit 0" crash reason).

---

## 7. Capacity carry-forward across the subprocess boundary (MEASURED + tested)

`_consume_capacity`/`_shrink_channel_widths` bookkeeping stays in the
*parent* process (unchanged from the prototype); only the *result*
(`shrunk_widths`, a `dict[str, ChannelWidths]`) crosses into each batch's
fresh subprocess, as a pickled `multiprocessing.Process` argument.
Indirect verification from this run: constraint counts stay in a tight
~109.1-109.6K band across all 11 batches (109,124 / 109,145 / 109,154 /
109,181 / 109,154 / 109,235 / 109,142 / 109,160 / 109,169 / 109,196 /
109,595 -- the same ~109K skeleton edges get a capacity constraint every
batch regardless of which 10 nets are in it), consistent with the
mechanism firing identically to the prototype run (which showed the same
~109.1-109.2K band across its 5 completed batches) rather than being
silently skipped or corrupted by the extra serialization round trip.
Direct verification: `test_net_batching_subprocess.py::TestCapacityRoundTrip`
pickles a `ChannelWidths` after `_shrink_channel_widths` has already
subtracted a simulated net's consumption, unpickles it (the same
serialization `multiprocessing` applies to every `Process` arg), and
asserts the reduced edge width survives exactly, floors at 0 rather than
going negative when consumption exceeds capacity, and that
`_DesignRulesStub` (the picklable stand-in for the Rust `DesignRules`
pyclass discovered not to support pickling at all -- see §8) reproduces
the same `trace_width_mm + clearance_mm` arithmetic `_consume_capacity`
itself uses.

---

## 8. A design surprise found while building this: `ParsedPCB`/`DesignRules` don't pickle

The subprocess boundary was originally going to be "pickle the whole
`ParsedPCB` once, let every child re-read it." That failed immediately:
`ParsedPCB.components`/`.nets` and `ParsedPCB.design_rules` are all
`temper_design_bundle_python` pyo3 pyclasses (the Rust-migrated
netlist/design-rules model), none of which implement
`__reduce__`/`__getstate__` -- `pickle.dump` raised
`TypeError: cannot pickle '...Component'/'...DesignRules' object`, not a
hypothetical failure mode, hit twice while building this feature (see
`net_batching.py`'s `_write_shared_context` docstring for the full design
rationale). The shipped design instead crosses the boundary as a source
file path (each child cheaply re-parses it -- ~40ms measured on this
production board, via the same `parse_kicad_pcb_v6` call Stage 0 itself
uses) plus a precomputed `net_name -> NetClassRules` snapshot (the one
`design_rules` fact `_solve_subset`'s codepath actually reads, per
`constraint_model.py`'s single `get_rules_for_net(...).{trace_width_mm,
clearance_mm}` call site), wrapped by a small local `_DesignRulesStub`
class in the child.

---

## 9. Caveat named by the coordinator: `ViaVar` over-count, not fixed here

A separate, concurrent line of work (different branch, not present in
this tree) found `ViaVar` to be an unread, unconstrained boolean --
never referenced by any SAT constraint, never read back by topology
extraction, and not used by Stage 4's real via placement -- and is
making it default-off, which would remove ~16.9M variables from the
*monolithic* model once it got far enough to build them (it currently
doesn't). This run's own numbers -- 947,430 `ViaVar`s per batch, unchanged
from the prototype run -- are **pre-fix**: that change is not in this
worktree. If a future re-measurement on this board shows meaningfully
lower per-batch variable counts than the 2,992,330 reported here, that is
the expected, and separate, effect of that fix landing -- not a
regression or inconsistency in this task's own subprocess-isolation work.

---

## Sources

- `docs/evidence/2026-08-07-net-batching-prototype.md` -- the specification
  this task worked from; named subprocess-per-batch as the unimplemented
  fix for the batch-5 crash it measured.
- `packages/temper-placer/src/temper_placer/router_v6/net_batching.py` --
  this task's implementation (subprocess boundary, crash detection,
  extended singleton-retry recovery).
- `packages/temper-placer/tests/router_v6/test_net_batching_subprocess.py`
  -- crash-vs-clean detection and capacity round-trip tests.
- Live run: `pcb/temper.kicad_pcb` sha256
  `1cce4a0872051675b0339de3378ff7ec2c16bb4b035c999dfa408dec5ecbc3f6`
  (unchanged by this task), `ulimit -v 8388608`, `PYTHONHASHSEED=0`,
  `TEMPER_BATCH_TRACE=1`, `timeout 7200`, `/usr/bin/time -v`, backgrounded
  and polled in-turn via a bounded `until`-style loop.
