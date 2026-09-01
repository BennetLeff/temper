<!-- provenance: commit=f4907a25c7167fb87ace24afd9ac2e717820a1e6 dirty=UNKNOWN -->
# JUSTIFIED-KEEP Verdict — `validation/drc_result.py`

**Date**: 2026-08-10
**Branch**: `fanout4/fix-2` (ce-work, marshalling-boundary fan-out unit)
**Base commit**: `57c083c0389f5f35222d61f3d0273ef43e60f0ba` (origin/main)
**Module**: `packages/temper-placer/src/temper_placer/validation/drc_result.py`
**Classification**: product runtime
**Decision**: JUSTIFIED-KEEP — no marshalers to migrate; entirely the Check protocol + pyclass re-exports
**Wave-4 plan status**: Explicitly classified REQUIRED-PYTHON in `docs/evidence/2026-08-09-python-over-rust-interrogation.md` §1.4

---

## 1. What the file actually is — marshaler-vs-protocol split

The task dispatched against `drc_result.py` (780 LOC) with the hypothesis that it
might contain dict-marshalling functions — the `_placement_to_board_dict`-style
converters that the strategy doc §1.3 classifies as "pure FFI-tax — no value beyond
bridge compat." A line-by-line audit of all 780 LOC yields the following split:

### 1.1 Result contract type re-exports (lines 79–127) — SHIM, not marshaler

```python
Severity: TypeAlias = _tdrc.Severity
Location: TypeAlias = _tdrc.Location
Issue: TypeAlias = _tdrc.Issue
CheckResult: TypeAlias = _tdrc.CheckResult
RunResult: TypeAlias = _tdrc.RunResult
```

These are pure TypeAlias re-exports of Rust pyclasses, with dataclass protocol
compat installed via `install_dataclass_fields`. They are part of the PURE-DELEGATION
SHIM surface (6,397 LOC, 9.2% — interrogation doc §1.1), not MARSHALLING. They
convert nothing; they re-export already-typed Rust objects.

### 1.2 Check ABC + CompositeCheck (lines 135–243) — REQUIRED-PYTHON

Duck-typed protocol base class with `@abstractmethod` properties (`name`, `category`,
`run`) and a `CompositeCheck` orchestrator. This is the protocol layer that the
strategy §1.4 classifies as REQUIRED-PYTHON. Contains no marshalling logic.

### 1.3 `_run_check_via_rust()` (lines 257–309) — ORCHESTRATION, not marshaler

This function:
1. Imports marshalers FROM `drc_runner.py` (`_placement_to_board_dict`,
   `_constraints_to_dict`, `_violations_to_run_result`)
2. Calls `_tdrc_mod.run_drc(board_dict, constraints_dict, check_names=[check_name])`
3. Extracts the per-check `CheckResult` from the returned `RunResult`

It is orchestration glue (ORCHESTRATION GLUE class, 68.5% of the 69k surface) —
it calls marshalers but does NOT contain marshaler logic itself. The actual
`_placement_to_board_dict` (210 LOC of pyclass→K1-dict field-level conversion),
`_constraints_to_dict` (93 LOC), and `_violations_to_run_result` (58 LOC) live
in `drc_runner.py`, which already carries a documented JUSTIFIED-KEEP verdict
(its own module docstring, lines 10–112).

### 1.4 15 Check stub classes (lines 312–780) — REQUIRED-PYTHON

Each class (`ClearanceCheck`, `ComponentOverlapCheck`, … `GroundPlaneCheck`)
implements the `Check` ABC and delegates its `run()` to `_run_check_via_rust()`.
These are the "17 ABC Check protocol classes" the strategy doc references.
(`PowerDomainCheck` is the one exception that does NOT delegate — it reports
not-run because the Rust schema has no `voltage_domain` field.)

### 1.5 Summary — zero marshalers in this file

| Section | Lines | Class | Has marshalers? |
|---------|-------|-------|-----------------|
| Result contract re-exports | 79–127 | PURE-DELEGATION SHIM | No — TypeAlias re-exports |
| Check ABC + CompositeCheck | 135–243 | REQUIRED-PYTHON | No — duck-typed protocol |
| `_run_check_via_rust()` | 257–309 | ORCHESTRATION GLUE | No — calls marshalers from `drc_runner.py` |
| 15 Check stub classes | 312–780 | REQUIRED-PYTHON | No — delegates to Rust via `_run_check_via_rust()` |
| **Total** | **780** | | **0 marshaler LOC** |

---

## 2. Where the actual marshalers are

The marshalers that `_run_check_via_rust()` imports are:

| Marshaler | Location | LOC | Verdict |
|-----------|----------|-----|---------|
| `_placement_to_board_dict` | `drc_runner.py`, lines 176–289 | 114 | JUSTIFIED-KEEP (module docstring lines 10–112) |
| `_constraints_to_dict` | `drc_runner.py`, lines 292–384 | 93 | JUSTIFIED-KEEP (same docstring) |
| `_violations_to_run_result` | `drc_runner.py`, lines 387–444 | 58 | Partial migration — `group_violations` kernel already Rust; wrapper only |

`drc_runner.py`'s own JUSTIFIED-KEEP verdict records four concrete blockers
(cross-consumer coordination, two distinct Rust type layers, WASM tier dependency,
the dict as schema contract) and an overturn trigger. That verdict is the
authentic marshaler-status record; this file is a consumer, not a container.

---

## 3. Decision (Step 2 of the residual procedure)

**JUSTIFIED-KEEP** — the file contains zero marshaler functions to migrate.
Migrating the Check protocol would violate the strategy's own classification
(§1.4 explicitly lists this file as REQUIRED-PYTHON: "duck-typed `Check`/`Stage`
protocols"). The `_run_check_via_rust()` orchestration function is the consumer
side of marshalers already documented as kept elsewhere; migrating it would move
the marshaler-import statement from one Python file to another without removing
any marshalling logic, which is a net-zero-value reshuffle, not a migration.

**Re-decidable trigger**: When `drc_runner.py`'s marshalers are migrated (per
their own overturn trigger: `drc_result._run_check_via_rust()` is migrated away
from the dict path, `serialize_board_state()` gains a pyclass path, and
`build_board_state()`/`build_constraint_set()` gain pyclass-constructor
equivalents), `_run_check_via_rust()` becomes a thin `return
_tdrc.run_drc_typed(placement, constraints, check_names=[check_name]).for_name(check_name)`
— a one-liner that can then be collapsed into each Check stub's `run()` or left
as a shared helper. That is when this file gets re-examined, not before.

---

## 4. Evidence (Step 3)

### LOC

- `drc_result.py`: **780 LOC** total (matching the interrogation doc's count)
  - Result contract re-exports + dataclass compat: ~49 LOC
  - Check ABC + CompositeCheck: ~109 LOC
  - `_run_check_via_rust()`: ~53 LOC
  - 15 Check stub classes: ~469 LOC

### Consumers of the Check protocol

| Consumer | How it uses the Check classes |
|----------|------------------------------|
| `validation/drc_runner.py` | Imports `Check`, `CheckResult`, `Issue`, `Location`, `RunResult`, `Severity` |
| `validation/drc_fence.py` | Imports result types from `drc_result` |
| `validation/drc_oracle.py` | Imports `RunResult`, `CheckResult`, `Issue`, `Location`, `Severity` |
| `validation/drc.py` | Constructs Check subclasses for kicad-cli wrapper |
| `validation/preflight.py` | Instantiates Check subclasses |
| `tests/validation/test_drc_result_coverage.py` | Exercises all 15 stubs + ABC defaults |

### Dependency surface

| Dependency | Bound to | Migration impact |
|-----------|----------|------------------|
| `abc.ABC`, `abc.abstractmethod` | Check protocol | REQUIRED-PYTHON — duck-typing is intrinsic to the design |
| `dataclasses` (via `_contract_dataclass_compat`) | Result contract re-exports | Already shimmed — fields installed on Rust pyclasses |
| `temper_drc_rs` | Re-exports + `_run_check_via_rust()` | Already migrated — Rust extension is the source of truth |
| `drc_runner._placement_to_board_dict` et al | Marshalling in `_run_check_via_rust()` | Consumed, not contained — see `drc_runner.py`'s own verdict |

### Churn rate

```
57c083c0 merge: migrate/thermal-spsolve — replace the last scipy with faer sparse LU
17553437d fix(drc): per-check Rust delegation — 14 stubs now genuinely delegate
5d8c8e7bc fix(drc): K1-schema key mismatch in _placement_to_board_dict
3c2faf4ba feat(drc): migrate result contracts to Rust pyclasses
```

**Signal: LOW-MEDIUM**. The file was substantively edited in the last 3 commits
(Phase 2 pyclass migration, K1-schema fixes, per-check Rust delegation). All three
edits were migration-internal — moving from Python native to Rust-backed contracts.
The protocol layer itself (Check ABC, stub classes) is structurally stable; the
changes were wiring, not algorithmic.

---

## 5. Verification

- **Tests**: `tests/validation/test_drc_result_coverage.py` — 20 passed (0.57s)
- **Cargo clippy**: `temper-drc-rs --all-features --all-targets -- -D warnings` — clean (0 errors)
- **Import linter**: `import_linter_gate.py` — 0 violations ("3 kept, 0 broken")
- **No source files modified** — this is an evidence-only verdict, no migration attempted
- **Strategy alignment**: `docs/evidence/2026-08-09-python-over-rust-interrogation.md` §1.4
  already classifies this file as REQUIRED-PYTHON — this verdict confirms rather than revises

---

## 6. Follow-ups

None from this file. The marshaler-migration action is on `drc_runner.py` (see its
own JUSTIFIED-KEEP docstring for the overturn trigger). When those marshalers are
migrated, `_run_check_via_rust()` in this file will be re-examined for collapse —
that is a separate fan-out unit, not a follow-up from this one.

---

*This verdict follows the R3 recording template from `docs/wave4-discipline-contract.md` §3:
classify → decide → record evidence. The pipeline hard rule ("a candidate whose parity
cannot be pinned bit-exactly is reported and recorded, not faked") extends here to
"a candidate with nothing to migrate is recorded as such, not invented."*
