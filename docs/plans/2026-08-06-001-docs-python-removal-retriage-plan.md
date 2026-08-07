# Re-triage: what actually blocks deleting Python

**Date:** 2026-08-06
**Supersedes (in scope, not in fact):** `docs/evidence/2026-08-06-never-port-triage.md`

## Why this exists

The never-port triage answered **"should this compute move to Rust?"** and
produced 45,470 LOC of `NEVER-PORT`. Those verdicts are not wrong — they are
answers to a different question, asked when the assumption was that Python
remains the orchestrator.

The stated goal is now to **remove Python entirely**. Under that goal
`NEVER-PORT` mostly means *"not yet triaged for this question."* A re-export
shim is not "never port" — it disappears. A click CLI is not "never port" —
it becomes `clap`. And `ortools` is not a porting problem at all.

This document re-scores the 42 `NEVER-PORT` rows (44,856 LOC) against a
different question: **what has to happen to this code before the interpreter
can go away?**

## The four answers that are not "port it"

| verdict | meaning |
|---|---|
| **BLOCKER** | Bound to a third-party Python library with no in-process Rust path. Needs a *decision*, not a port. |
| **REPLACE** | Reimplemented natively rather than translated line-by-line (`clap` for CLI, direct HTML emission for plots). |
| **PORT** | Must move. Mechanical orchestration/glue — no third-party blocker, no design question. |
| **DELETE** | Disappears with the interpreter: re-export shims, dict-marshalling at the Rust boundary, dead code. |
| **OUT-OF-RUNTIME** | Dev/CI tooling, not shipped runtime. In scope only under "no Python in the repo," not "no Python at runtime." |

## Result

| category | LOC | % |
|---|---:|---:|
| BLOCKER — OR-Tools | 3,599 | 8.0% |
| BLOCKER — scipy EDT | 673 | 1.5% |
| PORT | 23,684 | 52.8% |
| REPLACE | 9,764 | 21.8% |
| OUT-OF-RUNTIME | 5,572 | 12.4% |
| DELETE | 1,564 | 3.5% |
| **total re-scored** | **44,856** | |

**Only 4,272 LOC — 9.5% — are genuine blockers.** Everything else is work
whose difficulty is known: mechanical (PORT), a rewrite with a clear target
(REPLACE), or nothing at all (DELETE).

### Total scope for "no Python at runtime"

```
36,269   existing PORT queue (real compute)
39,284   re-scored NEVER-PORT, excluding OUT-OF-RUNTIME
-------
75,553   LOC
+ an OR-Tools FFI, which is not measured in LOC
```

Add **5,572** if the goal is "no Python in the repo at all" rather than "no
Python at runtime." **That distinction is the one open question in this
document** — see below.

## The critical path is OR-Tools, and it is not a porting task

| row | LOC |
|---|---:|
| CP-SAT solve entry (`_encoder_solve.py`) | 717 |
| Constraint handlers (`handlers/*.py`, 8 files) | 590 |
| Encoder dispatch + validation (`cp_sat/__init__.py`) | 584 |
| CpModel wrapper (`model.py`) | 518 |
| UNSAT extraction (`unsat.py`) | 433 |
| Clearance repair solve wrapper | 757 |
| **total** | **3,599** |

This is the smallest blocker by LOC and the largest by risk. Every other item
on the list is answered by writing Rust. This one is not: there is no mature
Rust CP-SAT solver, and the code is bound to the OR-Tools Python API
(`CpModel`, `AddConstraint`, `NewIntervalVar`, the infeasible-assumption API).

Three options, in rough order of preference:

1. **FFI to OR-Tools' C++ library.** OR-Tools *is* C++; the Python package is a
   binding. Rust can bind it directly, so nothing here needs an interpreter.
   This is an FFI project, not a migration, and nothing in the current plan
   touches it.
2. **Out-of-process solver.** Serialize the model, invoke a solver binary,
   read the result. Removes Python from the runtime *if* the binary is not the
   Python one. Weaker coupling, easier to stage, extra IO.
3. **Replace the solver.** Only if placement can be re-expressed for a solver
   that has a Rust implementation. This is a product decision, not a port.

**Spike this first.** It gates the entire `placer/cp_sat/` tree, it is the one
item that cannot be resolved by porting harder, and it is small enough to
answer in days. Discovering late that option 1 is intractable would invalidate
the sequencing of everything else.

`scipy.ndimage.distance_transform_edt` (673 LOC, two call sites) is the other
blocker and is much softer — EDT is a known algorithm with a clear Rust
implementation path. It is a real numeric port with an oracle, not glue, so it
belongs in the PORT stream with a differential rather than in a spike.

## Sequencing this implies

1. **OR-Tools FFI spike.** Days, not weeks. Answer option 1 before committing
   the rest of the plan.
2. **DELETE (1,564 LOC).** Free. Re-export shims and dead code that vanish with
   the interpreter; `io/net_class_manager.py` is already recorded RETIRE with
   zero consumers.
3. **Invert the boundary.** Move `main()` into Rust so the remaining Python is
   an explicit, shrinking list rather than the substrate. Without this the
   plan converges to "Python orchestrating Rust," not to no Python — see the
   next section.
4. **PORT (23,684 LOC).** Mechanical, parallelisable, and the bulk of the work.
5. **REPLACE (9,764 LOC).** `cli/` → `clap`; `visualization/` emits the same
   HTML/Plotly-JS from Rust. Independent of everything above.
6. **OUT-OF-RUNTIME (5,572 LOC).** Only if the goal is repo-wide.

## Why the current strategy does not converge to zero Python

Function-by-function migration with Python as the orchestrator converges to
**Python orchestrating Rust kernels**. That end state still has an
interpreter, and it is what produced the 117 pyclasses now on the boundary.

Those pyclasses are the visible cost. Because they replaced Python dataclasses
*in place*, Rust must emulate the Python data model on them: the dataclass
protocol, `pickle`, `deepcopy`, subclassing, `__eq__`/`__hash__`/`repr`,
`asdict` recursion shape. Four separate defects from that emulation were fixed
on 2026-08-06 alone (`__reduce__`, `subclass`, `is_dataclass`, and the wire
formats), and `router_v6/constraints_geometry.py` already declines to migrate
its types for exactly this reason — recording that keeping them in Python makes
the failure mode "structurally impossible."

**Under a full-removal goal, that protocol-emulation work is transitional cost
on an object model that is going to be deleted.** The 10 contract pyclasses
still lacking `__reduce__` (`board_contracts` Component/GroundDomain/
MountingHole/Pad/Trace/Via; `netlist_contracts` Component/Net/Netlist/Pin) are
therefore **ledgered, not fixed** — nothing reaches them from a `Board` today,
so the defect is latent, and paying it down buys compatibility with an
interpreter that is being removed.

The corollary is a rule worth adopting now: **stop adding pyclasses.** Each new
one is scaffolding that will be deleted, and each costs the full Python-semantics
surface on the way.

## Open question

**"No Python at runtime" or "no Python in the repo"?**

The answer moves 5,572 LOC of dev/CI tooling (`profiling/`, `regression/`,
`testing/`, `fixtures/`, the experiment harnesses) in or out of scope, and it
also decides whether the test suite itself is in scope — the pinned-oracle
differentials that the whole migration discipline rests on are Python, and they
are what makes each port verifiable.

Removing them is not free: it would remove the mechanism that has caught every
migration defect to date. A defensible end state is **no Python at runtime,
Python retained for verification**, which keeps the oracles and costs nothing
that ships.

This document does not decide it. Everything above is scoped to "no Python at
runtime"; the OUT-OF-RUNTIME row is the price of the other answer.

## Method

Each row was re-scored from the reason recorded in the original triage, not
from its name. The scoring is reproducible: `tools/measurements/retriage_python_removal.py`
holds the row-to-category assignment and prints the totals above.

The original triage's `PORT` rows (36,269 LOC) were not re-scored — they were
already "must move," and the goal change does not affect them.
