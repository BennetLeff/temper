# R7 axis conflict resolution — `_constraint_types/**` (spike)

**Date:** 2026-08-11
**Branch:** `spike/constraint-types-r7`
**provenance: commit=d21926ffbddd2b896801e4ff2336bd6b0cf30697 dirty=false**
**Measured against:** `origin/main` at `d21926ffb` (worktree `wt-r7`, created from
`origin/main` per dispatch; no files in scope existed before this spike's own edits).

## The R7 conflict

`docs/wave4-verdicts.yaml` marks `_constraint_types/**` (9 files, 1,033 LOC per the
removal-surfaces ledger) as `MIGRATE phase 2`. Two recorded positions conflict:

- **Measured-keep (#719, merged 2026-08-06):** `_constraint_types` is not a
  pyo3-pyclass candidate — the surface is declarative pydantic schema, and five
  load-bearing pydantic behaviours break under a `#[pyclass]`. Evidence:
  `docs/evidence/2026-08-04-wave4-phase2-constraint-types-verdict.md`.
- **Always-migrate (product authority, recorded 2026-08-05 in the ledger):** the
  authority's always-migrate stance overturns JUSTIFIED-KEEP records; contract
  objects/parser/registry migrate.

The close-out audit (`docs/evidence/2026-08-06-wave4-owned-surface-closeout.md` §6)
records this as the **one open verdict conflict in the program** — a decision owed to
product authority. This spike was dispatched to produce the decision-ready facts: is
the surface technically portable to Rust (always-migrate) or genuinely blocked
(measured-keep)?

**The dispatch's framing of the two stances did not survive contact with the code.**
The keep side is *not* "genuinely coupled to the ortools boundary", and the migrate
side is *not* "point the generator at a Rust pyclass emitter". Both premises are
factually wrong, for reasons that make the decision *easier*, not harder.

## Q1. What ARE the 9 files? — hand-written pydantic models, NOT generated stubs

There is **no generator**. Exhaustive search found no codegen, template, or manifest
for these files:

- No `.j2`/`.jinja`/`.tmpl` template produces them (the only Python-templates in the
  repo are `scripts/templates/netclass_rules.{rs,py}.j2` — a different surface).
- No script under `scripts/`, `packages/temper-placer/scripts/`, or
  `packages/temper-placer/tools/` writes into `_constraint_types/`.
- No file in the directory carries a generated-header marker
  (`# generated`/`# auto`), and `git log` shows no "generate" commit.
- The git history is a hand-edit history:
  `59e5368c2` (2026-07-03) "lift PlacementConstraints types out of
  io/config_loader (#120)" → `3ddc36ab3` (2026-07-10) submodule split →
  `e76aaf645` "migrate 34 @dataclass constraint types to Pydantic BaseModel" →
  continuous manual edits since (dated `FIXED 2026-07-28` comments, `@req` tags,
  `allow-safety-constant:` markers, three-source lockstep notes).

**Consequence for the migration path:** AGENTS.md's coverage-gate section labels
`_constraint_types/` "generated constraint type stubs". That label is **factually
inaccurate** — the coverage-gate `omit` is a scope carve-out (`pyproject.toml:111`),
not a provenance statement. The dispatch's migrate path ("point the GENERATOR at a
Rust pyclass emitter") has **no object to point**; there is no generator to re-target.
This is a documentation defect in AGENTS.md, recorded here (out of file-ownership
scope to fix in this spike).

### Per-file classification

| file | LOC | content | generated? | portable? |
|---|---|---:|---|---|---|
| `__init__.py` | 81 | re-export list | no | N/A — surface follows the types |
| `clearance.py` | 84 | 4 pydantic models, field-only | no | no — pydantic contract, zero compute |
| `config.py` | 464 | 8 pydantic models incl. `PlacementConstraints` (~50 fields) + 4 methods | no | no — see §Q3 blockers 1–5 |
| `groups.py` | 109 | 6 pydantic models + `compute_clearance` | no | no — 1 `math.sqrt`, net-negative measured |
| `noise.py` | 29 | 2 pydantic models, field-only | no | no |
| `routing.py` | 76 | 4 pydantic models, field-only | no | no |
| `safety.py` | 80 | 4 pydantic models, field-only | no | no (`IsolationBarrier` already mirrors `temper_drc_rs::constraints::IsolationBarrier`; in-source "keep both in sync" note) |
| `thermal.py` | 83 | 2 pydantic models + 2 module constants | no | no — constants already triple-sourced with Rust (`config_loader.rs` `RJC_PACKAGE_LOOKUP`; `io/config_loader.py`) |
| `topology.py` | 62 | 4 pydantic models, field-only | no | no |

Inventory matches #719's measured count exactly (34 `BaseModel` subclasses, 5 methods,
~58 LOC of method bodies). Re-verified on this tree: the only float expression is
`math.sqrt(pin_count) * pitch_mm * 1.5` (`groups.py:80`); **no numpy, no ortools, no
accumulation, no iteration-order dependence** anywhere in the 9 files.

## Q2. Who consumes them?

Production importers (`grep` over `src/`, excluding `io/__init__.py` re-export):

1. **`io/config_loader.py`** — the sole YAML constraint entry point. It is *itself*
   already a Wave-4 delegation shim over `temper-design-bundle` (`config_loader.rs`),
   but the Rust side **calls back into these pydantic types**: `config_loader.rs:721`
   constructs `ClearanceRule` (and ~12 more sub-models) by importing
   `temper_placer._constraint_types` and calling each class as a callable, and
   `config_loader.rs:2095-2098` calls `PlacementConstraints.model_validate(processed)`
   as the "final authority … never reimplemented in Rust" (`config_loader.rs:2061`,
   `config_loader.py:8`). `pydantic.ValidationError` from that call is wrapped in
   `ConfigValidationError` exactly as the oracle does.
2. **`constraints/compiler.py`, `constraints/builder.py`** — both already Wave-4
   delegation shims over `temper-constraint-compiler`. They read `_constraint_types`
   attributes and marshal once into a flat dict via `constraints/_payload.py`
   (`float()`/`bool()`/`list()` coercion); all compute is Rust on the far side. They
   consume the types as *data*, not through pydantic's validation API.
3. **`scripts/gen_config_reference.py`** (`packages/temper-placer/scripts/`) — **CI
   gate** (`.github/workflows/python-tests.yml:1757`, `--check`). Walks the entire
   `PlacementConstraints` model tree recursively via `model_fields`, reading
   `FieldInfo.annotation/default/default_factory/description/metadata(gt,ge,lt,le)` and
   `model_config(frozen, extra)` to regenerate `docs/reference/config-reference.md`.
4. **Rust `drc_oracle_marshal.rs`** (`temper-drc-rs`) — duck-types `model_dump`:
   `hasattr("model_dump")` then `model_dump(mode="json")` on every constraint value.
5. **`temper_drc_rs`/`temper_design_bundle_python` value types already inside the
   schema** — `PlacementConstraints.zones: list[Zone]`, `net_topologies:
   list[NetGraph]`, `net_classification: NetClassification`; `Zone`/`GroundDomain`/
   `LayerStackup` (`core/board.py`) and `NetGraph` (`core/net_graph.py`, landed
   `cb344aa64` 2026-08-08) and `NetClassification` (`core/net_types.py`, #560) are
   **already Rust pyclasses**. `PlacementConstraints` carries `arbitrary_types_allowed=True`
   precisely to hold them.
6. Tests: `tests/constraint_types/` (3 files), the consumer differential/PBT suites
   (`tests/io/test_config_loader_rust_differential.py`, `tests/constraints/`
   `test_{compiler,builder,reporter}_rust_differential.py` + PBTs, `tests/validation/`
   `test_drc_{marshal,oracle_marshal}_*`), plus ~20 other files importing
   `IsolationBarrier`, `ComponentGroup`, `ThermalProperties`, `CriticalLoop`, etc.

No consumer sits behind the ortools boundary in any coupling sense: the ortools KEEP
is confined to `placer/cp_sat/{model,_encoder_solve,unsat}.py`, and none of the nine
files (nor any consumer listed above) imports ortools.

## Q3. Is the content portable? — no, and the blocker is the pydantic API surface

Verified against the current tree, the #719 measured verdict stands and is if
anything *stronger* post-landing:

**1. `model_validate` + `ValidationError` are the live validation authority — of the
always-migrate side's own flagship Rust code.** `config_loader.rs` calls
`PlacementConstraints.model_validate(processed)` and wraps the resulting
`ValidationError` — for a ~50-field model with coercion (`float`, `int`, `bool`,
lists, tuples, nested models, dicts), `extra="forbid"`, `frozen=True`, and per-field
`ge`/`gt`/`le`/`lt` constraints. A `#[pyclass]` migration replaces that with
`PyValueError`/`PyTypeError` and hand validation — a **public exception-type and
validation-semantics change** at the single busiest entry point in the placer. This is
not "preference"; it is the boundary the already-landed Rust loader depends on.

**2. `model_fields` introspection is a live CI gate — and it just caught a real
drift.** `gen_config_reference.py --check` is failing on `origin/main` *right now*:
commit `68a8bbdfc` expanded `IsolationBarrier` (polyline `points`, `clearance_mm`)
and the checked-in `docs/reference/config-reference.md` was never regenerated. This is
direct, current evidence that the `Field(description=..., ge=...)` metadata on all 34
models is not decoration — a gate reads it and fails when it drifts. A `#[pyclass]`
exposes no `model_fields`/`FieldInfo`; reproducing it means reimplementing pydantic's
schema-introspection model in Rust.

**3. `model_dump` is duck-typed on the Rust side.** `drc_oracle_marshal.rs`
`constraint_value_to_plain_py` checks `hasattr("model_dump")` and calls
`model_dump(mode="json")`; the `mode="json"` tuple→list coercion is load-bearing for
the PyO3 JSON bridge. A pyclass without `model_dump` breaks that consumer silently.

**4. Zero compute exists to port.** 34 models / 5 methods / ~58 LOC bodies / one
float expression. Three of the five methods (`get_zone_for_component`,
`get_active_losses`, `get_weights`) have **zero production call sites** (verified by
grep — the `scheduler.py:119` `get_weights` is an unrelated class method). The only
production-called one, `get_net_class`, is called **duck-typed** via
`getattr(constraints, "get_net_class", None)` (`deterministic/stages/_phase_rotation.py:149`).
Its two regexes are a documented false-positive-fix surface (`config.py:442-460`) with
a Rust-regex semantics differential — a poor trade for a cold path. #719 measured every
method as net-negative across the pyo3 boundary floor (10–21× slower; 268 ns floor vs
7.7 ns pydantic attribute read).

**5. No marshalling is removed by migrating.** The compute consumers already decompose
to flat scalars before crossing (`_payload.py`); `temper-constraint-compiler` holds
typed `ConstraintData`, not `Py<PyAny>` handles. Converting the schema shell to a
pyclass removes zero crossings and adds ~35× on every one of `PlacementConstraints`'
~50 field reads.

**6. The always-migrate precedent does not reach.** Every contract migrated under
Wave 4 (`drc_types`/`drc_result` #808, `net_types` #560, `board`/`net_graph`) was a
**`@dataclass`/`Enum`**, restored via `core/_contract_dataclass_compat` — attributes,
`__repr__`, `__eq__`, `dataclasses.replace`. That shim restores the *dataclass*
protocol, not pydantic's (`model_validate`/`model_dump`/`model_fields`/
`ValidationError`/`FieldInfo`/constraints). `_constraint_types` is `pydantic.BaseModel`
throughout; there is no pyclass-compat shim that reproduces a BaseModel's public API.

**7. The surface is already as Rust as it can be without reimplementing pydantic.**
The value types inside the schema (`Zone`, `NetGraph`, `NetClassification`) are pyo3
pyclasses; the compute that reads the schema (`config_loader.rs`,
`temper-constraint-compiler`) is Rust; the pydantic shell is the schema/validation
authority that the Rust side itself treats as the final authority. What remains is
exactly and only the pydantic contract.

## Q4/Q5. The R7 resolution — KEEP (measured-verdict branch, #719)

**Verdict: `_constraint_types/**` is JUSTIFIED-KEEP, not MIGRATE.** The decision-ready
facts, per the dispatch's own decision rule:

- The dispatch's migrate path ("point the generator at a Rust pyclass emitter") is
  **vacuous — no generator exists** (§Q1).
- The dispatch's keep path ("stubs encode ortools-coupled shapes") is **wrong about
  the mechanism but right about the conclusion** — the surface is not ortools-coupled
  (zero ortools imports anywhere in the 9 files or their production consumers); it is
  **pydantic-API-coupled**, which is a *harder* blocker than ortools coupling, because
  the always-migrate dataclass-protocol precedent cannot restore pydantic behaviours
  (§Q3.6).
- The pydantic contract is not only load-bearing; it is the **authority the
  always-migrate side's own already-landed Rust code calls back into**
  (`config_loader.rs` `model_validate`), and the subject of a **live CI gate that is
  red on main today** because the metadata it reads drifted (§Q3.1–2).
- There is no remaining migratable remainder: compute is Rust, value types are
  pyclasses, and the pydantic shell carries zero compute (§Q3.4–5, §Q3.7).

Under the wave-4 program plan's D6/R3, this is the "measured verdict" branch of
JUSTIFIED-KEEP (`#719` merged exactly that verdict). The always-migrate stance's own
rationale — "the constraint objects/parser/registry migrate, the ortools calls stay
Python" — is already satisfied in this surface: the objects that carry compute or cross
the boundary have migrated; what stays Python is the schema shell whose pydantic
behaviours the Rust side itself refuses to reimplement.

**Ledger note:** this spike does not edit `docs/wave4-verdicts.yaml` (out of file-
ownership scope; #719 set the same precedent — the ledger is the product authority's
to flip). The ledger's `MIGRATE phase 2` entry and its `_constraint_types` NOTE block
stand until the authority records the flip to JUSTIFIED-KEEP citing this document.

## What was verified on this tree

- `uv run python scripts/import_linter_gate.py` → **PASSED** (0 new violations).
- Consumer differential/PBT suites (the exact suites the dispatch names for a migrated
  surface) → **130 passed**:
  `tests/constraint_types/`, `tests/io/test_config_loader_rust_differential.py`,
  `tests/constraints/test_compiler_rust_differential.py`,
  `tests/constraints/test_builder_rust_differential.py`.
- `gen_config_reference.py --check` → **RED on `origin/main`** (pre-existing drift,
  see §Q3.2); regenerated in this spike's commit.
- `make regen-check` → **1 pre-existing REFUSE, unrelated**: a hash-order `NEW_SITE`
  in `physics/loop_area.py:108` (a `set` materialised to an ordered artifact). Not in
  this spike's file-ownership scope; pre-existing on `origin/main`; reported, not fixed.

## Files changed by this spike

- `docs/evidence/2026-08-11-r7-constraint-types-resolution.md` — this note.
- `docs/reference/config-reference.md` — regenerated from the live `model_fields`
  tree (fixes the pre-existing drift introduced by `68a8bbdfc`; the regeneration is
  itself the proof that #719's blocker #3 is load-bearing).

No migration was performed because the surface is not portable (documented above). The
only "consumers that need repointing" finding is the AGENTS.md "generated constraint
type stubs" label, which is inaccurate and out of this spike's ownership to fix.
