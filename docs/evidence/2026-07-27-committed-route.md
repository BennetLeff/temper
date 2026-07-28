# Committed route of `pcb/temper.kicad_pcb`

<!-- provenance: commit=afaf9000960f0ff141b849447c0d106c2fca26eb (repointed to
docs/methodology-loop-discipline @ 220fd89ac45b5e5efa8b3be365af3e1653ed2967)
dirty=UNKNOWN -->

**Date:** 2026-07-27

**Board going in:** `pcb/temper.kicad_pcb`, 170 footprints, placed
(170/170 `optimal`, R24 audit clean), **0 segments / 0 vias / 0 zones**.
No committed route had ever existed for this board — a route was measured
earlier today at 48/96 = 50.0% (`docs/evidence/2026-07-27-first-route-and-
profile.md`) but that board was clobbered and never reached disk.

**This task fixes that: the routed board below is now committed, with
copper in it.**

## Falsifier, stated before routing

**"Stage 3 being 30x faster does not change completion rate."** Given that
`docs/evidence/2026-07-27-stage3-model-and-rewrite.md` cut Stage 3 from
1,573.8s to 52.67s via an O(n²) bugfix (not an algorithm change — same CNF,
same SAT result, "0 conflicts both before-conceptually and after"), the a
priori expectation was that this is a pure speed win with no effect on
which nets route.

**Result: neither cleanly confirmed nor rejected — the falsifier is
confounded by a larger effect discovered during this task.** Completion
rate on this board turned out to vary **run-to-run**, on identical code and
identical input, independent of the manufacturing-DRC flag:

| Run | Config | Wall time | Completion |
|---|---|---:|---:|
| 1 (**committed**) | DRC off | 214.628s | **51/96 = 53.1%** |
| 2 | DRC off (repeat, same code/input) | 55.637s | 36/96 = 37.5% |
| 3 | DRC on | 388.404s | 36/96 = 37.5% |
| 4 | DRC on (repeat) | 333.763s | 36/96 = 37.5% |

Three of four runs landed on the same 36/96, and the DRC-off repeat (run 2)
reproduced the DRC-on runs' completion rate exactly — the divergence is not
attributable to `enable_manufacturing_drc` (which only runs *after* Stage 4
routing and cannot feed back into it per `_pipeline_core.py`'s stage
ordering). It is real process-to-process variance in the routing outcome
itself, spanning **37.5% to 53.1%** (nearly 16 points) on the same board
with the same call. The pre-fix historical baseline (48/96 = 50.0%,
measured once, no error bars) sits inside that range.

**Conclusion: the falsifier cannot be honestly called either way.** Our
best run (committed, 53.1%) beats the baseline; our worst (37.5%) would
read as a regression if it had been the only sample taken. Given the
spread is larger than any plausible effect size from a pure speed change,
the correct statement is "not enough signal to distinguish a completion-
rate effect from noise," not "confirmed unchanged." **This run-to-run
non-determinism is itself the most important new finding of this task** —
see Ranked follow-ups below. Root cause is **UNVERIFIED**: candidates are
Python hash-seed randomization affecting dict/set iteration order in
Stage 3/4 tie-breaking, or CaCiCaL/rustsat's `sat_conflict_limit=20_000`
solve being sensitive to wall-clock/thread-scheduling jitter despite the
single measured instance in the prior doc reporting "0 conflicts,
0 decisions." Not investigated further — diagnosing or fixing router
internals is explicitly out of scope for this task.

## Part 0 — Environment setup required before anything ran

None of the Rust extension wheels were importable in this fresh worktree's
`.venv`, beyond the two the prior evidence doc already flagged
(`temper_drc_rs`, `temper_rust_router`). Discovered by working through a
chain of `ModuleNotFoundError`s while trying to run the safety suite:
`temper_ipc`, `temper_geometry`, `temper_dsn`, `temper_design_bundle`,
`temper_constraint_compiler`, `temper_io_types`, `temper_quality_oracle`
also had to be built via `uv run maturin develop --release` in their
respective `packages/temper-*` directories before `import temper_placer`
worked at all (the import chain pulls in `temper_ipc` via
`core/ipc2221.py`, `temper_geometry` via `geometry/__init__.py`,
`temper_dsn` via `io/dsn_normalizer.py`, and so on). **Every one of these
had to be rebuilt in this worktree; none were cached from a prior build.**
Worth folding into a single setup script for future worktrees rather than
re-discovering the dependency chain by import-error archaeology each time.

## Part 1 — Route completion and failure modes (committed board)

**Completion rate: 51/96 nets routed = 53.1%.** (108 nets total in the
netlist; 96 attempted by Stage 4 — 12 are GND/Power/GateDrive/HighVoltage/
ACMains-class nets that get zone-pour treatment instead of individual
routed segments, same accounting as the prior evidence doc; still
**UNVERIFIED** that this fully explains the 12-net gap, not traced
net-by-net.) **This beats the 48/96 = 50.0% baseline** the task set out to
match or beat — see the falsifier discussion above for why that comparison
carries a large asterisk.

**Failure mode: single category, no ambiguity — same as the prior run.**
All 45 failed nets on the committed board failed for the identical stated
reason, verbatim from the router's own per-net log:

```
✗ <net> FAILED: no legal path found (forced segment disallowed)
```

**0 of 45** failures were `congestion (blockers: ...)` or plain `no path
found` — the router's two other failure strings. Every failure is the
forced-segment fail-closed gate (this branch's own subject —
`fix/forced-segment-fail-closed`) declining to emit a segment it cannot
prove safe.

Secondary grouping by net/subsystem (informational only — the router's own
cause taxonomy is 100% one bucket; this is which parts of the board carry
the unrouted load):

| Subsystem | Failed nets | Examples |
|---|---:|---|
| `safety.*` / `safety-line*` | 12 | `safety.ocp-line`, `safety.ovp.comp-inn`, `safety.uvlo_logic.mon-ina_p`, `safety-line-1` |
| Misc single-purpose signals | 15 | `bias`, `boot`, `en`, `fb`, `I_SENSE`, `input`, `io0`, `refin_n`, `sdi`, `sdo`, `vbias`, `w1_1`, `ZCD_ISO`, `i2c_sda_ui`, `thermal.j_fan-p1` |
| `discharge.*` | 6 | `discharge.k_dis1-coil1`, `discharge.q_dis_drv-g`, `discharge.r_dis1a-p2` |
| `RTD_*` / `rtd_pan.*` | 6 | `RTD_DRDY`, `RTD_CS_N`, `RTD_HW_FAULT`, `rtd_pan.low_window-out` |
| Gate-drive / PWM | 3 | `GATE_HS`, `PWM_HS`, `PWM_LS` |
| `tank*` | 2 | `tank-out`, `tank.c_tank1-p2` |
| `power_in.*` | 1 | `power_in.bypass_relay-coil1` |
| **Total** | **45** | |

`safety.*` carries the largest single share (12/45, 27%), consistent with
those nets threading through the densest, most constraint-heavy part of
the board (HV/mains-adjacent isolation nets), but this is descriptive, not
diagnostic — no net-by-net root-cause tracing was done.

## Part 2 — Committed board contents

```
segments: 2,338
vias:     48
zones:    96
footprints: 170  (unchanged from input -- git diff on pcb/temper.kicad_pcb
                  is 2,483 insertions, 0 deletions: routing only appended
                  content, no footprint (at X Y) lines were touched)
```

All four counts confirmed directly with `grep -c` against the committed
file, not inferred from the router's self-report:

```
$ grep -c '(segment ' pcb/temper.kicad_pcb   # 2338
$ grep -c '(via ' pcb/temper.kicad_pcb       # 48
$ grep -c '(zone ' pcb/temper.kicad_pcb      # 96
$ grep -c '(footprint ' pcb/temper.kicad_pcb # 170
```

The committed board also parses cleanly through
`temper_placer.io.kicad_parser.parse_kicad_pcb` (108 nets recovered) —
checked directly rather than assumed from a clean write.

Peak RSS for the committed routing run (`resource.getrusage`, macOS units
are bytes not KB): **14.83 GB** (15,926,706,176 bytes). Same order of
magnitude as the prior evidence doc's 6.93 GB full-board figure; higher
here, plausibly because this run's 53.1% completion did more Stage 4 work
(more successful paths to realize) than the prior doc's own measurement.
Not independently isolated per-stage in this task.

## Part 3 — Manufacturing DRC on/off delta (end-to-end, on a board with copper)

This is the measurement flagged in the prior evidence doc as never having
been taken end-to-end (only an isolated `_run_manufacturing_drc` stage
timer existed, 0.0072s on an 11-net partial route). **That 0.7s-class
figure does not hold at full-board scale — it is off by roughly two orders
of magnitude.**

Because completion rate varies run-to-run (Part 0 falsifier finding), the
fairest DRC-cost comparison controls for completion rate rather than
comparing the (higher-completion, and therefore more Stage-4-work) committed
run directly against a DRC-on run:

| Comparison | Completion | Wall time |
|---|---:|---:|
| DRC off, run 2 | 36/96 | 55.637s |
| DRC on, run 3 | 36/96 | 388.404s |
| DRC on, run 4 | 36/96 | 333.763s |

**At matched completion (36/96), manufacturing DRC adds ~278–333s to a
~56s route — roughly 6–7x the routing-only wall time**, not the ~0.7s
figure. (The naive, completion-mismatched comparison against the committed
run's 214.628s would understate this further by attributing some of the
gap to the committed run's higher Stage-4 workload; the matched comparison
above is the correct one.)

**Why manufacturing DRC cannot be measured "on the exact committed board"
without re-routing:** `_run_manufacturing_drc(pcb, routing_results)` (called
from inside `RouterV6Pipeline.run()`, gated by `enable_manufacturing_drc`)
takes the in-memory `RoutingResults` object produced by that same Stage-4
call — there is no code path today that reconstructs a `RoutingResults`
from an already-written `.kicad_pcb` file's `(segment ...)`/`(via ...)`
elements to DRC-check it standalone. Measuring DRC-on therefore means
re-invoking the full pipeline (`route_pcb(..., enable_manufacturing_drc=
True)`), which is subject to the same run-to-run completion variance as
Part 1 — confirmed directly: both DRC-on runs in this task landed on
36/96, not the committed board's 51/96. **The violations-by-category
breakdown in Part 4 is therefore from a same-code/same-input but
different-outcome (36/96) run, not literally the 51/96 board that got
committed** — flagged again in UNVERIFIED below.

## Part 4 — DRC violations by category

Measured via a monkeypatch on `RouterV6Pipeline.run` that captures its
return value (which carries `.manufacturing_report`) while still going
through the documented `route_pcb()` call path unmodified — no router
source was changed, this only observes an existing return value that
`route_pcb()`'s own wrapper does not currently re-expose.

```
total_violations:       257,619
critical_violations:    257,617
is_manufacturability_ok: False
errored_checks:         ('acid_trap',)
```

| Category | Count | Denominator | Errored | Note |
|---|---:|---:|---|---|
| `acid_trap` | 0 (uncounted) | — | **True (crashed)** | `AttributeError: 'RoutePath3D' object has no attribute 'coordinates'` at `acid_trap_detection.py:117`. Pre-existing bug in the DFM checker, unrelated to this task's routing changes — reported, not fixed (out of scope: router/DFM source). |
| `annular_ring` | 0 violations | 0 vias checked | False | **Suspicious**: the committed board has 48 vias, yet this run's DRC-on route (36/96, presumably fewer vias than the committed 48) still reports checking exactly 0. The anti-vacuous-truth guard in `_pipeline_verify.py` (fail-closed on `total_checks == 0` with routed copper present) is implemented for `creepage` and `clearance` only — not `annular_ring` or `teardrop`/`thermal_relief` counts feeding this path. Possible real gap; not fixed (out of scope). |
| `teardrop` | 1 (by design: 0 generated) | — | False | `teardrop_count == 0` is itself scored as a violation per `ManufacturingReport.total_violations`'s definition — working as designed, not a bug. |
| `thermal_relief` | 1 (by design: 0 generated) | — | False | Same pattern as teardrop. |
| `copper_balance` | 4 unbalanced layers | — | — | `total_area_mm2` reported as 35,568 — an implausibly large figure for this board's physical size; **UNVERIFIED** whether this is a units/aggregation artifact in `copper_balance.py`, not investigated further. |
| `creepage` | 257,597 | 175 checks | False | Ran without crashing or vacuous-guard firing, but `violation_count` exceeds `total_checks` by ~1,470x. Plausible explanation: each of the 175 HV-net-pair checks enumerates many individual segment/point sub-pairs and records one violation per unsafe sub-pair rather than one per net-pair — **UNVERIFIED**, not traced into `creepage_check.py`'s violation-construction loop. |
| `clearance` (Rust backend) | 16 | 630 checks | False | Same order of magnitude as the 2026-07-26 evidence doc's 493-violation figure on a denser 64-route/149-footprint board revision; plausible given this run's lower (36/96) completion produced less routed copper overall. |

**Do not read this table as "the committed board has 257,619 DRC
violations."** It is measured on a 36/96-completion sibling run, not the
committed 51/96 board — see Part 3's explanation of why the two cannot
currently be decoupled. The committed board's true manufacturing-DRC
violation count is **UNVERIFIED**.

## Part 5 — Gate states (before and after routing)

All five gates plus `make netlist`'s 76 assertions and the safety suite
were run twice: once pre-route (board still at 0 segments/vias/zones,
confirming the placed-but-unrouted board doesn't already fail anything) and
once post-route (against the committed 2,338-segment/48-via/96-zone board).

| Check | Pre-route | Post-route |
|---|---|---|
| `make netlist` (76 assertions) | 76 passed, 0 failed | 76 passed, 0 failed |
| `scripts/check_domain_partition.py` | exit 0 | exit 0 |
| `scripts/capacity_budget_gate.py` | exit 0 | exit 0 |
| `scripts/mpn_fabrication_gate.py` | exit 0 | exit 0 |
| `scripts/check_derived_doc_drift.py` | exit 0 | exit 0 |
| `scripts/check_vacuous_gates.py` | exit 0 | exit 0 |
| Safety suite (`tests/requirements/safety/`) | 54 passed | 54 passed |
| `test_clearance.py` domain-classification coverage | 92.4% (157/170 components, 48/165 nets) | 92.4% (unchanged) |

**No regressions.** The safety suite's coverage guard
(`coverage_ratio >= 0.85`) remains satisfied at 92.4%, well above the
0.85 floor, unchanged pre/post-route (expected: domain classification
operates on component placement, not copper, and routing did not move any
footprint). The five gates and `make netlist` all operate on the
netlist/BOM/schematic/documentation domain, not on `pcb/temper.kicad_pcb`'s
copper layer, so this is a mechanical confirmation rather than a targeted
check — consistent with the prior evidence doc's framing.

## Ranked follow-ups (reported, not attempted — out of scope for this task)

1. **Diagnose the run-to-run completion-rate non-determinism** (Part 0/1).
   A 37.5%–53.1% spread on identical code and input is a bigger open
   question than anything else in this document and makes any single
   completion-rate measurement on this board hard to trust without
   several repeats. Likely culprits: `PYTHONHASHSEED`-dependent iteration
   order in Stage 3/4, or `sat_conflict_limit=20_000` CaDiCaL solve
   sensitivity to timing despite the "0 conflicts" single-instance
   measurement in the prior doc. Would need controlled reruns with a
   pinned hash seed to isolate — not attempted here (would mean touching
   or wrapping router invocation semantics beyond a passive measurement).
2. **Fix the `acid_trap_detection.py:117` crash** (`RoutePath3D` has no
   `.coordinates` — likely needs the 3D path's actual coordinate accessor,
   whatever it's now called after a prior refactor). Currently silently
   folds to `errored=True` and contributes 0 to violation counts, meaning
   acid-trap defects are invisible in every report generated by the
   current Rust-clearance-port era of this codebase.
3. **Extend the anti-vacuous-truth guard** (`_pipeline_verify.py`) to
   `annular_ring` (and arguably `teardrop`/`thermal_relief`), which
   reported "0 checked, 0 violations" on a board with 48 committed vias —
   currently only `creepage` and `clearance` fail closed on a zero-check
   result.
4. **Investigate `creepage.violation_count` vs `total_checks` semantics**
   (257,597 vs 175) — either document the intentional per-sub-pair
   counting convention, or fix a genuine over-count bug; not distinguished
   in this task.
5. **Provide a standalone "DRC an already-routed file" entry point** so
   manufacturing DRC can be measured (and used) without re-invoking the
   full Stage 2–4 pipeline — would also remove the Part 3/4 confound
   between DRC cost and routing-outcome variance.

## UNVERIFIED

- Root cause of the 37.5%–53.1% run-to-run completion-rate variance
  (Part 0/1) — not diagnosed, flagged as the primary open question.
- Whether the 12-net gap between 108 parsed nets and 96 nets attempted by
  Stage 4 is fully explained by zone-pour-treated net classes — carried
  over unverified from the prior evidence doc, not re-traced here.
- The committed (51/96) board's own manufacturing-DRC violation count and
  category breakdown — Part 4's numbers are from a same-code/input,
  different-outcome (36/96) sibling run; see Part 3 for why the two could
  not be decoupled with the tooling as it exists today.
- Whether `copper_balance.total_area_mm2 == 35,568` (Part 4) is a genuine
  measurement or a units/aggregation defect in `copper_balance.py` — not
  investigated.
- Exact multiplicity semantics of `CreepageReport.violation_count` vs
  `total_checks` (257,597 vs 175) — plausible per-sub-pair explanation
  offered, not confirmed by reading `creepage_check.py`'s violation
  construction loop in detail.
- Whether `annular_ring`'s "0 vias checked" on a board with 48 committed
  vias is a genuine defect (most likely) or an artifact of running against
  the 36/96 sibling run rather than the 51/96 committed board (less
  likely, since both runs have vias present).
