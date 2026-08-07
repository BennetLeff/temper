<!-- provenance: commit=UNKNOWN dirty=UNKNOWN -- backfilled: predates the evidence-provenance gate and no self-declared commit exists in this file's own content. See .evidence-provenance-allowlist. -->

# OR-Tools FFI spike: can Rust drive CP-SAT without Python?

**Date:** 2026-08-06
**Question from:** `docs/plans/2026-08-06-001-docs-python-removal-retriage-plan.md`
— OR-Tools is the critical path (3,599 LOC), the smallest blocker by LOC and the
largest by risk, and the only item on the removal list that is not answered by
writing more Rust.
**Reproduce:** `uv run --no-sync python tools/measurements/ortools_ffi_spike.py`

## Verdict

**Feasible.** The CP-SAT interface is **bytes in, bytes out**. A Rust
implementation needs generated protobuf structs plus a thin C++ shim, and **no
Python modelling logic at all**.

The 1,605 LOC bound to `ortools` is bound to a *protobuf schema*, not to
Python. That is a much weaker coupling than the triage assumed.

What this spike did **not** do: run an end-to-end Rust→solver solve. That needs
OR-Tools C++ headers, which the Python wheel does not ship. That is a
packaging prerequisite, not a viability question — see *Remaining unknown*.

## Evidence

### 1. The shipped dylib already exports the C++ entry points

`libortools.9.dylib` (23 MB) ships **inside the Python wheel** at
`ortools/.libs/`, and exports:

```
operations_research::sat::Solve(CpModelProto const&)
operations_research::sat::SolveWithParameters(CpModelProto const&, SatParameters const&)
```

The Python package is a binding over this library. The solver is already
native code; Python is a client of it, not a participant.

### 2. The interface type is a protobuf, which is language-neutral

Both entry points take `CpModelProto` and return `CpSolverResponse`. Neither
has any Python in it. A hand-built `CpModelProto` for a two-variable model
serialises to **58 bytes** — that is the entire request.

### 3. The schema is obtainable with no OR-Tools source checkout

The wheel ships no `.proto` files, but the generated `cp_model_pb2` module
embeds the `FileDescriptorProto`. Dumping it yields a **`FileDescriptorSet`
(6,937 bytes, 29 messages)**, which `prost_build::Config::compile_fds()`
consumes directly.

So the Rust structs are generatable today, from the wheel already installed,
without building OR-Tools from source.

### 4. Every risky production API is a proto field

The API surface actually used across the 5 files is small — `NewIntVar`,
`NewBoolVar`, `NewConstant`, `NewIntervalVar`, `AddBoolOr`, `AddElement`,
`AddMultiplicationEquality`, `AddAbsEquality`, `AddAssumption(s)`, `AddHint`,
`Solve`, `Value`, `ObjectiveValue`, `WallTime`,
`SufficientAssumptionsForInfeasibility` — and all of it maps onto proto
fields:

| API | proto field | present |
|---|---|:--:|
| UNSAT extraction | `CpSolverResponse.sufficient_assumptions_for_infeasibility` | OK |
| `AddAssumption(s)` | `CpModelProto.assumptions` | OK |
| `AddHint` | `CpModelProto.solution_hint` | OK |
| `Solve` status | `CpSolverResponse.status` | OK |
| `Value(v)` | `CpSolverResponse.solution` | OK |
| `ObjectiveValue` | `CpSolverResponse.objective_value` | OK |
| `WallTime` | `CpSolverResponse.wall_time` | OK |

`SufficientAssumptionsForInfeasibility` is the one that mattered. It drives
UNSAT surfacing at three call sites, and had it been Python-side logic it
would have sunk the whole approach. It is a response field.

## The design this implies

```
Rust                            C++ shim (~50 lines)        OR-Tools
────                            ────────────────────        ────────
build CpModelProto  ──bytes──►  ParseFromString
  (prost structs                SolveWithParameters  ─────►  libortools
   from the FDS)                SerializeAsString
parse CpSolverResponse ◄─bytes──
```

The shim is the only C++ in the design, it is stateless, and its entire
surface is `(const uint8_t*, size_t) -> (uint8_t*, size_t)`. Everything above
it is Rust; everything below is the solver that is already native.

## Remaining unknown — and it is packaging, not viability

The shim must `#include` OR-Tools headers to name `CpModelProto` and
`SolveWithParameters`. The wheel ships the dylib but not the headers, so
finishing the proof needs OR-Tools' C++ distribution (`brew install or-tools`,
vcpkg, or a CMake build).

Consequences worth pricing before committing:

* **Build dependency.** OR-Tools becomes a native build input, not a
  `uv` dependency. CI images must carry it.
* **Distribution size.** `libortools` is 23 MB and pulls a large set of absl
  dylibs alongside it.
* **Linking against the wheel's dylib works locally**, but shipping should
  link a library built for the target rather than one extracted from a Python
  wheel.

None of these are unknowns about whether it works. They are costs.

## Recommendation

**Proceed, and sequence it early** — it gates the whole `placer/cp_sat/` tree
(3,599 LOC) and nothing downstream can be planned until the packaging choice
is made.

Suggested order:

1. `brew install or-tools` (or a pinned CMake build) to get headers.
2. Generate prost structs from the `FileDescriptorSet` this spike already
   produces.
3. Write the shim, and prove it on the two-variable model used here.
4. **Then** port the encoder: it becomes a proto-building exercise with a
   pinned oracle, exactly like every other migration in this program — build
   the same model in Python and Rust, compare the serialised `CpModelProto`
   byte-for-byte. That differential is stronger than the usual one, because
   proto equality is exact.

Point 4 is the part worth noticing: once the boundary is a proto, the encoder
port gets the *best* differential in the program. Two implementations either
emit identical bytes or they do not.
