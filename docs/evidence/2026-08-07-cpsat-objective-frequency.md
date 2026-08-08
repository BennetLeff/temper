<!-- provenance: commit=4f0e138b2cc6cf42f94d1321ed1eb19bbe5db954 dirty=true -->

# CP-SAT objective-posting frequency, the 5s budget's origin, and Pumpkin's real time-to-optimum (2026-08-07)

**Scope.** BLOCKER-ORTOOLS (`docs/wave4-verdicts.yaml`,
`packages/temper-placer/src/temper_placer/placer/cp_sat/**`) is down to one
open question after the 2026-08-07 equivalence harness and Pumpkin
differential (`docs/evidence/2026-08-07-cpsat-equivalence-harness.md`,
`docs/evidence/2026-08-07-pumpkin-engine-differential.md`): Pumpkin clears
Tiers 1 (feasibility) and 3 (independent verification) unconditionally, and
FAILS Tier 2 (objective parity) at a 5s budget on the one corpus with a real
objective, though it reaches the exact same proven optimum given 60s. This
doc answers the four questions that determine whether that failure matters:
how often production actually posts an objective, what the 5s budget
protects, how long Pumpkin actually needs, and what the R2 verdict is. **No
call site was migrated, no solver behavior changed.** Companion code:
`docs/evidence/2026-08-07-cpsat-objective-frequency-instrument.py` (dynamic
call-site instrumentation) +
`docs/evidence/2026-08-07-cpsat-objective-frequency-instrument-summary.json`
(its raw output), `docs/evidence/2026-08-07-pumpkin-time-to-optimum.py`
(timeout sweep) + `docs/evidence/2026-08-07-pumpkin-time-to-optimum-summary.json`
(its raw output).

**Bottom line.** Every automatically-triggered production solve path —
`temper optimize` (the CLI), the full 10-round `PlaceRouteLoop`, and the
CI-gating golden-board/production-board regression tests — is unconditionally
objective-free by static construction: `minimize_displacement_to` is never
passed on any of them. The **only** code path that can ever post an
objective is the opt-in `run_clearance_repair_solve` clearance-repair loop
(issue #504), which is wired into nothing automatic — no CLI command, no CI
gate, no `PlaceRouteLoop` round — and has been invoked, by grep across this
repo's history, in exactly 5 real one-off incident scripts (`docs/evidence/
k3_*`, `gap1_runc_compound_probe.py`, `2026-08-04_domain_first_resolve_solve.py`)
against 482 commits touching this surface. The harness's 5s budget is not
derived from any CI gate, R2 margin, or production timeout: production's own
default for the one objective-bearing path is **180,000 ms**, 36x the
harness's number, and the test suite that exercises it never uses anything
tighter than 1,000 ms for a single artificial-timeout edge case. Pumpkin's
measured time-to-optimum on the objective corpus is
**[FILLED IN BELOW, Sec 3]**. **Verdict: R2 does not yet formally apply to
this surface (it is JUSTIFIED-KEEP, not MIGRATE), but the underlying
performance question resolves in Pumpkin's favor with a recorded exception:
KEEP the 5s number as a Tier-2 diagnostic, not a decision gate, and measure
against the 180s production budget instead.**

---

## 1. How often does production actually post an objective?

### 1.1 Static call-site census: only one path can ever post an objective

Traced every producer of a CP-SAT objective term
(`packages/temper-placer/src/temper_placer/placer/cp_sat/model.py`):

- `CpSatModel.add_objective_term()` (model.py:275) is the only thing that
  appends to `_objective_terms`.
- `CpSatModel.apply_objective()` (model.py:288) is the only thing that ever
  calls `Minimize()`, and it is a documented no-op when `_objective_terms`
  is empty ("the phase-1 feasibility solve stays objective-free unless a
  caller explicitly requested an objective").
- `add_objective_term()` has exactly one caller in the entire module:
  `CpSatModel.add_displacement_objective()` (model.py:337), which in turn
  has exactly one caller: `_encoder_solve.py:343`, gated behind `if
  minimize_displacement_to:` — the one and only keyword parameter of
  `solve_placement()` that can cause an objective to exist.

So "does this solve post an objective" reduces exactly to "was
`minimize_displacement_to` passed to `solve_placement()`." Every real
caller in the codebase, traced:

| Caller | Passes `minimize_displacement_to`? | Automatically triggered? |
|---|---|---|
| `cli/__init__.py`'s `optimize` command (the `temper optimize` CLI, line 749) | **No** | Yes — the routine placement command |
| `PlaceRouteLoop._call_solver` (`_loop_core.py:46-85`, the full place→route feedback loop, `MAX_ROUNDS=10`) | **No** — `solver_kwargs` never includes it, by inspection of every key it builds | Yes — every round of every loop run |
| `tests/placer/cp_sat/test_regression_drc.py::test_golden_board_drc_regression` / `test_production_board_drc_regression` (the CI-gating golden-board and ship-target regression tests) | **No** | Yes — CI, on every PR touching the placer or the PCB |
| `benchmarks/cp_sat_bench.py` (the R2-adjacent, opt-in `ci-advisory` perf corpus) | **No** | Opt-in via PR label, but never objective-bearing when it does run |
| `clearance_repair.py::run_clearance_repair_solve` (issue #504's repair loop) | **Yes**, unconditionally — this is its entire purpose | **No** — not called by the CLI, not called by `PlaceRouteLoop`, not called by any CI-gating test. `grep -rn "run_clearance_repair_solve" --include="*.py"` across the whole repo returns exactly 7 files: its own definition, its own unit-test suite, and **5 real invocations**, all one-off `docs/evidence/` incident scripts (`k3_fixed_copper_repair_solve.py`, `k3_resolve_gated_solve.py`, `k3_swap_board_write_solve.py`, `gap1_runc_compound_probe.py`, `2026-08-04_domain_first_resolve_solve.py`), spanning issue #504's introduction through the K3 copper-swap board write. |

Every automatically-triggered production path is objective-free by
construction; the one path that can post an objective requires a human (or
agent) to explicitly invoke a repair script by hand for a named clearance
incident. `git log --oneline --all -- packages/temper-placer/src/temper_placer/placer/cp_sat/ pcb/temper.kicad_pcb power_pcb_dataset/`
returns **482 commits** touching this surface (each PR's CI runs the
objective-free regression gate) against those **5** manual repair
invocations — call-site reachability alone puts the real-world ratio at
roughly 1%, not the near-50/50 split a test-suite grep would suggest (see
1.3).

### 1.2 Dynamic confirmation: one real golden-board placement, instrumented

Ran the exact same 4 steps `test_golden_board_drc_regression` runs (parse →
load PCL config → `solve_placement`) on the real golden-board corpus
(`power_pcb_dataset/corpus/temper/temper.kicad_pcb`, 33 components, the same
board the harness's own `full-board` corpus and the Pumpkin differential's
"14-35ms" figure are built from), with `solve_placement` monkeypatched to
record every call's `minimize_displacement_to` truthiness — the same
observation-only hook pattern the equivalence harness already uses for
`_forced_worker_count`:

```
components=33
pcl_constraints=21 zones=['MCU_ZONE', 'ISOLATION_BARRIER', 'HV_ZONE']
status=optimal wall_s=5.52 solve_placement_calls=1 objective_calls=0
```

**One real full placement = exactly one `solve_placement` call, zero
objective terms.** This is the production shape: a placement run is not a
multi-round objective-bearing search, it is a single feasibility solve (the
`PlaceRouteLoop` can iterate up to 10 rounds when DRC/routing gates fail and
re-place, but every round goes through the same objective-free
`_call_solver` path traced in 1.1).

### 1.3 Whole-CI-suite instrumentation: why it shows a different number, and why that number is the wrong lens

`docs/evidence/2026-08-07-cpsat-objective-frequency-instrument.py`
monkeypatches all three name-bindings a caller can resolve `solve_placement`
through (`_encoder_solve.solve_placement`, `encoder.solve_placement`, and
the `cp_sat` package's own re-export — all three needed because `encoder.py`
and `cp_sat/__init__.py` each did `from ..._encoder_solve import
solve_placement` at their own import time, which captures the pre-patch
function object into their own namespace) plus `CpSolver.Solve` globally,
then runs the full `tests/placer/cp_sat/` + `tests/cli/` +
`tests/router_v6/test_phase1_anti_false_zero.py` suite — every test file
that calls `solve_placement`, i.e. "whatever CI exercises" for this module
(737 tests executed, 13 pre-existing environment failures unrelated to this
instrumentation — missing `kicad-cli`/`KICAD7_FOOTPRINT_DIR` in this
sandbox, the same gate `test_golden_board_drc_regression` itself skips on
when absent):

| Solve path | Total calls | With objective | Without | % with objective |
|---|---|---|---|---|
| `solve_placement` (the production entry point) | 44 | 24 | 20 | 54.5% |
| `CpSatModel.solve()` (direct low-level model path — **zero non-test callers exist**; see 1.1's model.py trace, only encoder-unit tests like `test_encoder.py`/`test_courtyard_edge.py` call it) | 210 | 31 | 179 | 14.8% |
| `unsat.py` UNSAT-core re-solve (always objective-free by construction) | 15 | 0 | 15 | 0% |

**This 54.5% figure for `solve_placement` is real but is not a production
frequency — it is test density**, and conflating the two would be a
mistake. `tests/placer/cp_sat/test_clearance_repair.py` alone contributes
10 of the 44 `solve_placement` calls and most of the 24 objective-bearing
ones: it is the unit-test suite for the repair primitive itself, and
correctly drills the harder, riskier, opt-in path hard — that is what good
test coverage of an opt-in feature looks like, not evidence that production
traffic is half repair solves. Sec 1.1's call-site census (what production
code can *reach* automatically) and Sec 1.2's direct measurement (what one
real placement *does*) are the ones that answer "how often does production
post an objective"; Sec 1.3 answers a different, also-useful question
("how well-tested is the objective path relative to the feasibility path")
and the honest answer there is "proportionally, quite well" — which is a
good sign for Pumpkin's own coverage obligations if it were ever adopted on
this path, not a contradiction of Sec 1.1/1.2.

**Conclusion for Q1: production posts an objective on a small, single-digit
percentage of real solves at most, and on zero automatically-triggered
solves at all** — the objective-bearing path exists solely as an opt-in
tool invoked by hand for specific clearance-repair incidents (5 of them, on
record, ever).

---

## 2. What is the 5s budget actually protecting?

**Nothing traceable.** The 5s figure appears in exactly two places in this
repository, both written by the same 2026-08-07 evidence work: `docs/evidence/
2026-08-07-cpsat-equivalence-harness.py:883` and
`docs/evidence/2026-08-07-pumpkin-equivalence-run.py:177`, both as the
literal `timeout_ms = 30_000 if model.name == "full-board" else 5_000` with
no comment tying it to any production constant, CI budget, or R2 margin —
it is the harness author's own choice of a "fast enough to sweep 3 seeds x 3
worker-counts x 2 repeats in a few minutes" convenience number for the
`small`/`medium` synthetic corpora, reused unchanged for the Pumpkin
differential for apples-to-apples comparison. It was never meant to model a
real deadline, and tracing every actual timeout constant in the codebase
confirms it does not correspond to one:

| Constant | Value | Where | Applies to an objective-bearing solve? |
|---|---|---|---|
| `solve_placement(timeout_ms=...)` default | **1,000 ms** | `_encoder_solve.py:100` | Only if the caller opts in — the default itself is objective-free |
| `PlaceRouteLoop.INITIAL_SOLVE_TIMEOUT_MS` | 30,000 ms | `loop.py:44` | No — this loop never posts an objective (Sec 1.1) |
| `PlaceRouteLoop.RE_SOLVE_TIMEOUT_MS` | 1,000 ms | `loop.py:43` | No — same loop |
| `test_golden_board_drc_regression` / `test_production_board_drc_regression` (CI-gating) | 30,000 ms | `test_regression_drc.py:166,445` | No |
| `benchmarks/cp_sat_bench.py` default scenario timeout | 2,000 ms | `ScenarioConfig.timeout_ms` | No — this benchmark never passes `minimize_displacement_to` either |
| `run_clearance_repair_solve(timeout_ms=...)` default — **the one objective-bearing path's own production default** | **180,000 ms** | `clearance_repair.py:298` | **Yes — this is what actually gates the objective path in production** |
| `test_clearance_repair.py`'s own per-round timeouts (the suite exercising the objective path) | 10,000 – 180,000 ms, most commonly 20,000 ms; the only `1,000` ms entries are two validation tests (`test_unknown_ref_in_objective_raises`, `test_displacement_bound_without_reference_raises`) that assert a `KeyError`/`ValueError` is raised *before* the solver ever runs, so the timeout value is inert there | grep across the file | Yes (except the two inert entries) |
| The 5 real repair incident scripts (`k3_swap_board_write_solve.py` etc.) | 180,000 ms/round, up to 4 rounds | e.g. `k3_swap_board_write_solve.py:18-19,84` | Yes — the actual historical production usage |

**R2 (the migration program's Performance-A/B gate) does not use an
absolute wall-clock figure at all.** `docs/wave4-discipline-contract.md`
G3: margins come from `scripts/pr_perf_compare.py` — `TIMING_MARGIN = 0.20`
(a 20% regression against a *rolling median baseline*, not a fixed second
count), `COMPLETION_MARGIN = 0.10`, a `DEFAULT_WINDOW = 5`-run rolling
window, and a documented carve-out for pure-delegation modules
("no regression beyond noise", the CI noise floor stated in the PR body).
So the 5s number is not an R2 artifact either — R2 has never been run
against this surface, because `packages/temper-placer/src/temper_placer/
placer/cp_sat/**` is currently `JUSTIFIED-KEEP` in `docs/wave4-verdicts.yaml`,
not `MIGRATE`; G3 only fires on a landing migration PR. There is also no
interactive-latency requirement on record anywhere in this repo's docs —
`grep`s for "5 second"/"5s budget"/"interactive latency" near the placer
return nothing.

**Conclusion for Q2: the 5s budget is an artifact of the harness's own test
convenience, not a real requirement anyone's PR, CI gate, or user-facing
latency SLA depends on.** The number that actually protects something in
production is 180,000 ms (per round, up to 4 rounds) — 36x looser — and
even the harness doc's own §4.3 already flagged that OR-Tools itself shows
13-14x seed-dependent variance on the golden board's plain feasibility
search, so a tight budget was already known to be fragile for the
incumbent before Pumpkin was even in the picture.

---

## 3. Pumpkin's real time-to-optimum on the objective corpus

**[SWEEP RESULTS PLACEHOLDER — filled in from
`docs/evidence/2026-08-07-pumpkin-time-to-optimum-summary.json` after the
background run completes; see the script's own header for methodology.]**

---

## 4. R2 verdict and BLOCKER-ORTOOLS recommendation

**[FILLED IN AFTER SEC 3]**

---

## 5. Reproduction

```
# Objective-frequency census (Sec 1.2/1.3):
cd packages/temper-placer
uv run --no-sync python ../../docs/evidence/2026-08-07-cpsat-objective-frequency-instrument.py

# Time-to-optimum sweep (Sec 3):
(cd docs/evidence/2026-08-07-pumpkin-engine && cargo build --release)
cd packages/temper-placer
uv run --no-sync python ../../docs/evidence/2026-08-07-pumpkin-time-to-optimum.py
```

Both need the built Rust pyo3 extensions (`make extensions` from the repo
root; note this worktree's cargo config routes all crate build output to a
shared `target-shared/` directory at the repo root rather than each crate's
own `target/`, which the time-to-optimum script accounts for explicitly).
The instrumentation script writes
`docs/evidence/2026-08-07-cpsat-objective-frequency-instrument-summary.json`;
the sweep writes
`docs/evidence/2026-08-07-pumpkin-time-to-optimum-summary.json`.
