<!-- provenance: commit=3e639ffd37a25df1d8086f38a701a04a7bcfa4c0 dirty=true -->

# Pumpkin vs OR-Tools at the real production budgets, and at real board scale (2026-08-11)

**Scope.** Spike only — no line under
`packages/temper-placer/src/temper_placer/placer/cp_sat/**` was touched, no
call site migrated. Companion code: this doc's own driver scripts
(`docs/evidence/scripts/2026-08-11-pumpkin-hpwl-realboard-run.py`,
`docs/evidence/scripts/2026-08-11-pumpkin-hpwl-realboard-clean-run.py`), the HPWL
extension to the standalone Rust binary
(`docs/evidence/2026-08-07-pumpkin-engine/src/main.rs`, +HPWL support only,
reusing the crate's existing `pumpkin_solver::minimum`/`maximum`), and raw
data (`docs/evidence/2026-08-11-pumpkin-hpwl-realboard-summary.json`,
`docs/evidence/2026-08-11-pumpkin-hpwl-realboard-clean-summary.json`).

## Verdict, first

**MIGRATE-WITH-CONDITIONS.** At true production scale (169 components, the
real `pcb/temper.kicad_pcb`, not the 33-component fixture three prior spikes
mistakenly called "the real golden board" — see §5), single-threaded
OR-Tools CP-SAT does not complete even a bare feasibility solve within the
real 30s `INITIAL_SOLVE_TIMEOUT_MS` budget, and does not find a single
feasible HPWL-augmented solution within the real 5s polish budget either.
Pumpkin, single-threaded (its only mode), proves feasibility in 0.9–2.0s
(independently re-verified from scratch, PASS) and returns a real,
self-consistent HPWL solution within the 5s polish budget on every seed
tested. **This is the opposite of the earlier (33-component, now-retracted)
finding that motivated caution about Pumpkin's objective-search speed** —
at true scale the objective gap runs the other way. The conditions: (1) one
run exceeded a 50s safety margin against a 30s requested budget and did not
reproduce on retry (30.17s, essentially on-budget) — not confirmed as a
real defect, but not stress-tested enough to rule one out either, and
separately, Pumpkin's HPWL objective barely improved between the 5s and 30s
budgets on the seed retested (17,601mm to 17,601mm) — "give it more time"
is not obviously a lever that works here (§4.2); (2) the production PCL
config is currently unusable against the real board at all (§4.0) — a
separate, pre-existing defect this spike found and did not cause, that
blocks any "real," fully-constrained full-board CP-SAT solve (OR-Tools or
Pumpkin) until fixed, independent of which engine is chosen.

## The budget table this verdict rests on

| Budget | Value | Where | Live today? |
|---|---:|---|---|
| `RE_SOLVE_TIMEOUT_MS` (most rounds) | 1,000 ms | `packages/temper-placer/src/temper_placer/placer/cp_sat/loop.py:43` | Yes, every non-round-1 solve |
| `INITIAL_SOLVE_TIMEOUT_MS` (round 1) | 30,000 ms | `loop.py:44` | Yes, every round-1 solve |
| Phase-2 "polish" | 5,000 ms | `_loop_core.py:925` | Yes, but objective-free (§2) |
| `run_clearance_repair_solve` default (the only path that ever posted an objective) | 180,000 ms | historical — **the function was deleted 2026-08-09** (`9985bae48`, "retire dormant clearance_repair module"); see §2 | **No — dead code today** |

Verified directly, not trusted: `sed -n '42,44p' loop.py`, `sed -n '920,930p'
_loop_core.py`, and `git log --oneline -- '**/clearance_repair.py'` (one
commit: `9985bae48 refactor(placer): retire dormant clearance_repair
module`, on `main`, 2026-08-09).

## 1. The task's premises, checked

**"Does Pumpkin meet 5s with an HPWL objective on a real-board-scale
instance" assumed the HPWL objective would land on the existing 5s polish
path.** It will not, per the actual wirelength/HV-separation plan
(`docs/plans/2026-08-11-002-feat-placer-wirelength-and-hv-separation-plan.md`,
Key Decision D6): the HPWL objective is designed as a **new, separate,
opt-in entry point**, explicitly *not* inserted into today's Phase 1 or the
vestigial Phase-2 "polish" call — "not silently reusing the vestigial
`Phase 2` name" is D6's own wording. That plan sizes its own budget
recommendation at 30–60s to start, citing the (as it turns out, dead-code)
180s figure. This spike measures against **both** the existing 5s/30s
literals (since they are real, live numbers in the codebase even though no
objective runs on them today) and reports what an HPWL pass would need,
without assuming which budget a not-yet-built entry point will actually
get.

## 2. Objective-posting frequency: verified at 0% live, and the 180s citation traced to dead code

Read `_loop_core.py`'s `_call_solver` (lines 46–88) directly:
`solver_kwargs` is built from `netlist`, `board`, `extra_constraints`,
`timeout_ms`, `seed`, `zones`, `zone_components`, `loop_components`, plus
conditionally `reference_aliases`/`loop_aliases`/`validator_input` — **never
`minimize_displacement_to`**, on any of the four call sites
(`_loop_core.py:226,484,885,921`). `cli/__init__.py`'s `optimize` command
(line 749) does not pass it either. `grep -rn minimize_displacement_to`
across `packages/temper-placer/{src,tests}` turns up exactly one production
kwarg definition (`_encoder_solve.py:106`) and one test call
(`test_validator_audit.py:910`) — no automatic caller anywhere.

The 2026-08-07 doc this task's brief called "a later assessment" —
`docs/evidence/2026-08-07-cpsat-objective-frequency.md` — is real, and its
own reasoning holds up: it correctly traced objective-posting to exactly one
function, `run_clearance_repair_solve` (issue #504's repair loop), whose own
default timeout was 180,000 ms
(`clearance_repair.py:298`, at the time), used unconditionally by 5 one-off
incident scripts and nothing automatic. **What that doc could not have
known: `git log --oneline -- '**/clearance_repair.py'` shows the module was
deleted two days after that doc was written** —
`9985bae48 refactor(placer): retire dormant clearance_repair module`
(2026-08-09, on `main`), justified in its own commit message as "zero
production src importers." The 5 incident scripts
(`docs/evidence/k3_*.py`, `gap1_runc_compound_probe.py`,
`2026-08-04_domain_first_resolve_solve.py`) now raise `ImportError` if run.
So both the task brief's skepticism ("I could not confirm that and believe
it is wrong") and the 2026-08-07 doc's own math were right for their
respective moments — the 180s number was real production history, and it
is now attached to nothing live. **Objective-posting frequency today is
0%, not "<1%"**: every automatically-triggered path is objective-free by
construction, and the one path that was ever objective-bearing no longer
exists.

`docs/plans/2026-08-11-002-...` (dated today) inherits the 180s figure from
that same 2026-08-07 doc as its own budget anchor (§ Dependencies:
"Production's real objective-bearing solve budget is 180,000ms/round").
That inheritance is now stale for the reason above — worth the plan's
owner knowing, though fixing it is outside this spike's scope.

## 3. Single-threaded, apples-to-apples: the parallelism theory, and why it was dropped

The coordinator's first hypothesis — that Pumpkin's `medium`-corpus loss to
OR-Tools was a single-thread-vs-multi-thread artifact — is refuted by data
already in `docs/evidence/2026-08-07-pumpkin-equivalence-summary.json`
(no re-run needed: `num_workers` was already swept 1/4/8 for OR-Tools in
the original 108-run harness, and is a documented no-op for Pumpkin, so
every one of those rows is already single-thread-equivalent for Pumpkin):

| corpus (component count) | OR-Tools, `num_search_workers=1` | Pumpkin (always single-threaded) |
|---|---|---|
| `small` (5 comp, synthetic corpus, not board-derived) | optimal, 19–30 ms, obj 0 | optimal, 1–2 ms, obj 0 |
| `medium` (12 comp, has a real `minimize_displacement_to` objective) | **optimal, 915–1942 ms, obj 2220** (true proven optimum) | **feasible only, hits the 5s timeout every time, obj 3113–26146** (up to 11x worse, never converges) |
| `full-board` (**33-component fixture, not the real board — see §5**) | optimal *or* **unknown** (12/18 runs hit the 30s ceiling), 2593–30045 ms | **optimal, 14–21 ms**, obj 0 (trivial — no real objective on this corpus) |

Single-threaded OR-Tools proves `medium` optimal in under 2s and gains
almost nothing from more workers (867–1942ms across 1/4/8 workers) — so
Pumpkin's `medium` loss is real and algorithmic, not a parallelism gap.
**But `full-board`'s 0.0 objective for both engines makes that row's
"inversion" trivial** (the min-displacement objective at a point requiring
no repair) — it was never evidence Pumpkin wins on a *real*, non-trivial
objective at scale. That is what §4 below measures directly, on the real
169-component board, with a real (HPWL) objective.

## 4. HPWL at real scale: 169 components, 97 router-eligible nets, `pcb/temper.kicad_pcb`

### 4.0 Getting a working real-board corpus was itself two bugs deep

`build_full_board_corpus()` — the mechanism all three prior CP-SAT spikes
used — loads `power_pcb_dataset/corpus/temper/temper.kicad_pcb`. Verified
directly:

| | components | bytes | last touched |
|---|---:|---:|---|
| `power_pcb_dataset/corpus/temper/temper.kicad_pcb` (the harness's "full-board") | 33 | 33,927 | 2026-07-08 |
| `pcb/temper.kicad_pcb` (the real ship target) | **169** | 1,025,477 | 2026-08-08 |

`test_regression_drc.py` itself already distinguishes these
(`BOARD_PATH` vs `_REAL_PRODUCTION_BOARD`, lines 60/70) and documents, in
`test_production_board_drc_regression`'s own docstring (line 1052), that
CP-SAT is **not** run against the real board because it is "infeasible at
168 components / 30s timeout." This spike re-pointed the harness's own
corpus-building mechanism at `pcb/temper.kicad_pcb` and confirmed that
comment directly (§4.1) rather than trusting it.

Doing so hit a second, independent, live bug: `load_constraints()`
(`temper-design-bundle`'s Rust `config_loader.rs`,
`reject_unknown_raw_keys`) currently raises `ValueError` on
`configs/constraints/temper_induction_cooker.yaml` — the production PCL
config — because the file's own top-level keys (`version`, `metadata`,
`netclasses`) are not in the guard's `RAW_CONFIG_KEYS` /
`KNOWN_UNCONSUMED_*` allowlists. This is not cosmetic:
`test_golden_board_drc_regression`/`test_production_board_drc_regression`'s
own `_load_pcl_constraints`/`_load_zones` helpers wrap the call in a bare
`except Exception: return []`/`{}` — **so both CI-gating regression tests
currently run with zero PCL constraints active**, silently, despite their
own comments claiming "solve placement with all constraints active." The
CLI's `optimize` command (`cli/__init__.py:456,689`) hits the same
exception unguarded. This spike worked around it with a read-only,
temp-only copy of the config with just those 3 keys stripped (never
touching the committed file) to get the real 21 PCL constraints + 3 zones
loading, matching the counts the 2026-08-07 objective-frequency doc's own
(33-component-fixture) run reported. **This is a live defect independent
of anything else in this doc; it is not fixed here (out of scope, and
`temper-design-bundle`/`config_loader.rs` is not under this spike's
touched-files list).**

A third, independent finding, also verified directly: even with the config
loading, most of its 21 constraints reference component names
(`C_BUS1`, `Q1`, `U_MCU`, `J_AC_IN`, `J_COIL`, `J_DEBUG`, `MAX31865`,
`U_GATE`, `C_BOOT`, `C_BUS2`) absent from the real board's netlist, or
present under those names but not where the config's zone assumptions
expect — confirmed by running the harness's own `IndependentVerifier`
against the **real, committed board's own as-placed positions**: it FAILS
(10 violations, e.g. `adj_Q1_Q2` requires ≤10mm, actual measured distance
101.85mm; `enc_HV_ZONE` requires components inside a `(0,80)-(100,150)`
zone on a board the config apparently assumes is smaller than the real
234mm-tall board). **The real, physically-shipped board violates its own
nominal PCL config.** This is config/board drift, not a solver artifact —
it affects OR-Tools and Pumpkin identically and is why §4.1's "full,
as-configured" run below returns `infeasible` for both engines.

### 4.1 Full config (with the drift from §4.0): both engines agree — infeasible

Single-threaded, real board, real (stripped-only-for-schema) PCL config +
courtyard SEPARATED pairs (14,217 constraints total), 97 HPWL nets:

| mode | engine | seeds 0/1/7 | status | time |
|---|---|---|---|---|
| feasibility (no objective) | OR-Tools, 1 worker | all 3 | `unknown` | 22.9–25.4s (hits 30s wall) |
| feasibility (no objective) | Pumpkin | all 3 | `infeasible` | 235–362 ms |
| HPWL, 5s budget | OR-Tools, 1 worker | all 3 | `infeasible` | 1.1–1.4s |
| HPWL, 5s budget | Pumpkin | all 3 | `infeasible` | 216–240 ms |
| HPWL, 30s budget | OR-Tools, 1 worker | all 3 | `infeasible` | 1.2–1.4s |
| HPWL, 30s budget | Pumpkin | all 3 | `infeasible` | 233–248 ms |

Both engines agree on UNSAT here, fast, on every seed — consistent with
§4.0's finding that the constraint set itself (not either solver) is
over-constrained relative to the real board's actual geometry. This row is
reported for completeness but is **not** a meaningful engine comparison —
it is confirmation that the *config* is broken, independently corroborated
by the real board's own positions failing the same check (§4.0). Raw data:
`docs/evidence/2026-08-11-pumpkin-hpwl-realboard-summary.json`.

### 4.2 Clean model (courtyard-only, no drifted zone/adjacency constraints): the real comparison

To isolate the packing/objective question from §4.0's config drift, this
run drops the 21 drifted PCL constraints and keeps only board bounds +
courtyard-clearance SEPARATED pairs (14,196 constraints, O(n²) over 169
real components at real footprint sizes) — a legitimate, real geometric
placement problem on the real board (152mm × 234mm, confirmed from the
parsed board — matching the dimensions the wirelength plan's own §3
synthetic test independently assumed for its 150-component mock, a useful
cross-check). Single-threaded throughout.

**Feasibility (no objective), 30s budget:**

| engine | seed 0 | seed 1 | seed 7 |
|---|---|---|---|
| OR-Tools, 1 worker | `unknown`, 25.8s | `unknown`, 26.1s | `unknown`, 26.7s |
| Pumpkin | **`optimal`, 2.0s** | **`optimal`, 0.9s** | **`optimal`, 1.0s** |

Pumpkin's `optimal` claim was independently re-verified from scratch
against the harness's own `IndependentVerifier` (not accepted on the
engine's own say-so): **PASS**. Single-threaded OR-Tools does not complete
even bare feasibility on the real board within the real 30s budget; Pumpkin
proves it in ~1–2 seconds every time.

**HPWL objective, 5s budget (the real "polish" literal):**

| engine | seed 0 | seed 1 | seed 7 |
|---|---|---|---|
| OR-Tools, 1 worker | `unknown` (no feasible solution found at all), 6.1–6.2s | same | same |
| Pumpkin | `feasible`, obj 1,864,185 units = **18,641.85mm HPWL**, 5.3s | `feasible`, 17,601.49mm, 5.3s | `feasible`, 17,870.43mm, 5.3s |

OR-Tools produces **nothing** within 5s at real scale with the HPWL
objective — not a worse solution, no solution. Pumpkin returns a real,
non-trivial, internally-consistent HPWL solution every time (the reported
`objective_value` and an independent from-scratch recomputation of HPWL
from the returned positions agree to the unit, e.g. 1,864,185 raw units
== 18,641.85mm × 100 units/mm exactly — the encoding is self-consistent,
not just plausible-looking).

**HPWL objective, 30s budget:** OR-Tools remains `unknown` on seed 0 (the
only seed reached at this budget before the run below crashed; 25.95s
wall — still no feasible point found, consistent with the 5s-budget row).
Pumpkin seed=0 first run crashed the driver — a
`subprocess.TimeoutExpired` after 50s against a 30s requested budget (a
20s safety margin the rest of this spike's runs never came close to
needing). A same-configuration retry with a 180s outer margin completed
cleanly: **`feasible`, 30.17s wall (1.7% over the requested 30,000ms — the
usual solve/report overhead, not a runaway), objective 1,760,066 units =
17,600.66mm.** That is essentially identical to the *same seed's 5s-budget*
result (17,601.49mm, §4.2 table above) — 6x more time bought a 0.005%
objective improvement. Two readings are both worth recording rather than
picking one: (a) the one >50s run did not reproduce and may have been
system contention from this spike's own concurrent processes rather than a
Pumpkin defect — not confirmed either way with a single data point; (b)
independent of that anomaly, Pumpkin's HPWL search on this real-scale model
appears to plateau almost immediately — it is fast to a usable feasible
point but does not obviously keep improving with more budget, which matters
for anyone planning to rely on "give it more time" as a lever.

## 5. The other three CP-SAT spikes: which conclusions rest on the 33-component fixture

Checked directly, not inferred:

- **`docs/evidence/2026-08-07-cpsat-equivalence-harness.md`** — its `full-board`
  row (line 261) explicitly states "the real golden-board corpus
  (`power_pcb_dataset/corpus/temper/temper.kicad_pcb`)." **33 components,
  not 169.** Its Tier-1 "full-board" finding (OR-Tools `{optimal,unknown}`,
  12/18 unknown at 30s) is real but describes a 5x-smaller problem than
  production.
- **`docs/evidence/2026-08-07-pumpkin-engine-differential.md`** — its `full-board`
  row (Sec 3) explicitly labels it "33 comp, 543 constr, **real golden
  board**." The headline "Pumpkin: 18/18 optimal, in 14-35ms every time"
  and "dramatically faster than OR-Tools on the real golden board's plain
  feasibility search" claims are about the 33-component fixture. **Withdraw
  the word "real" from that claim; substitute this spike's §4.2 result**
  (still a Pumpkin win, now at true scale: ~1–2s vs OR-Tools' non-completion
  at 30s — the qualitative conclusion survives, the specific numbers do
  not).
- **`docs/evidence/2026-08-07-cpsat-objective-frequency.md`** — Sec 1.2's
  dynamic measurement ("Ran the exact same 4 steps... on the real
  golden-board corpus... 33 components... wall_s=5.52") is the same
  fixture. This does **not** affect that doc's core Sec-1.1 finding (the
  call-site census showing zero automatic callers ever pass
  `minimize_displacement_to`) — that is a static-code argument, independent
  of board size — but its one dynamic data point describes a 33-component
  solve, not the 169-component board production actually places.

All three docs' corpus-size conflation traces to one place: the harness's
own `build_full_board_corpus()` docstring
(`docs/evidence/scripts/2026-08-07-cpsat-equivalence-harness.py:697`) calling its
fixture "The real golden-board corpus" and "the same board
`test_golden_board_drc_regression` uses" — true of `BOARD_PATH`
specifically, but `test_golden_board_drc_regression` is itself the *fast*
regression gate, explicitly distinct in its own module docstring
(lines 22–26) from the *slow*, real-ship-target
`test_production_board_drc_regression`. Nothing was dishonest here — the
harness's own naming is locally accurate — but three independent spikes
each reused "full-board" as a stand-in for "the real board" without
re-deriving that it wasn't.

## 6. Answering the task's five questions

1. **Budgets verified**: 30s/1s/5s are real, current, unconditional
   literals (§ budget table). The 180s figure is real history, now
   attached to deleted code (§2).
2. **Objective-path frequency**: 0% today (§2) — not "<1%," genuinely zero,
   because the one function that ever exercised it no longer exists.
3. **Re-ran the existing harness at real budgets**: done at the medium
   corpus's native 5s (already the harness's own literal, matching the
   "polish" budget by coincidence) via the already-existing dataset (§3);
   extended it to true real-board scale for the HPWL question (§4), which
   the existing harness's corpus builder could not reach without the
   `pcb/temper.kicad_pcb` re-point.
4. **HPWL at real-board scale**: measured (§4.2) — Pumpkin produces a
   real, verified feasible solution within the 5s polish budget; OR-Tools
   produces nothing within 5s or 30s, single-threaded, at true scale. The
   budget an HPWL pass would need for Pumpkin to *prove* optimality (as
   opposed to return a usable feasible point) was not established — no run
   in this spike reached `optimal` on the HPWL-augmented model at real
   scale — that remains open, but "usable within budget" (this plan's own
   D4 target, not proven-optimal) is answered.
5. **Verdict**: MIGRATE-WITH-CONDITIONS, stated above.

## 7. `docs/wave4-verdicts.yaml` is stale, not edited here

The `BLOCKER-ORTOOLS` entries (lines 887 onward) and the `placer/cp_sat/**`
`JUSTIFIED-KEEP` entry (line 438) predate this measurement and the
2026-08-07 doc's. The `JUSTIFIED-KEEP` entry's own text names its unmet
acceptance criteria as "(b) search quality on this board class is
unmeasured for every candidate ... (d) what 'good enough' means here is a
human judgment ... under a wall-clock budget." (b) is now measured, at true
scale, with a real objective (§4.2) — the record no longer supports
"unmeasured." Per this task's instruction, the ledger is not edited here;
three sibling agents are active on it.

## 8. Reproduction

```
# HPWL extension to the Pumpkin binary (already applied in this branch):
cd docs/evidence/2026-08-07-pumpkin-engine && cargo build --release
# binary lands at $REPO_ROOT/target-shared/release/pumpkin_engine in this
# worktree's shared-target cargo config.

# Real-board (169-comp) corpus + full config-drift run:
uv run --no-sync python docs/evidence/scripts/2026-08-11-pumpkin-hpwl-realboard-run.py

# Clean (courtyard-only) real-board run — the comparison in §4.2:
uv run --no-sync python docs/evidence/scripts/2026-08-11-pumpkin-hpwl-realboard-clean-run.py
```

Needs the built Rust pyo3 extensions (`make extensions`) and a working
`load_constraints()` — see §4.0 for the schema-validation workaround this
spike used (a temp stripped copy of `temper_induction_cooker.yaml`, built
inline by the driver script, never touching the committed file).
