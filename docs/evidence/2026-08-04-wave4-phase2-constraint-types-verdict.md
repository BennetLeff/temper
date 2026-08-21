<!-- provenance: commit=UNKNOWN dirty=UNKNOWN -- backfilled: predates the evidence-provenance gate and no self-declared commit exists in this file's own content. See .evidence-provenance-allowlist. -->

# Wave 4 Phase 2 — `_constraint_types` is not a pyo3-pyclass candidate

**Verdict: do not migrate. Re-scope Phase 2 to `core/**` and `pcl/**`.**

This records the survey and measurements behind that verdict. Nothing in
`_constraint_types/` was changed. `docs/wave4-verdicts.yaml` was not edited —
the `MIGRATE`/phase-2 entry for this pattern stands as written, and this
document is the measured input for revising it.

Reproduce the numbers with:

```
uv run python docs/evidence/scripts/2026-08-04-constraint-types-ffi-cost.py
```

## 1. Inventory: the surface is declarative schema, not compute

`packages/temper-placer/src/temper_placer/_constraint_types/` is 1027 LOC
across 9 files. It contains **34 `pydantic.BaseModel` subclasses and exactly 5
methods.**

| file | LOC | pydantic models | methods | genuine compute |
|---|---:|---:|---:|---|
| `__init__.py` | 81 | 0 | 0 | none — re-export list only |
| `clearance.py` | 84 | 4 | 0 | none — field declarations only |
| `config.py` | 464 | 8 | 4 | `get_active_losses`, `get_weights`, `get_zone_for_component`, `get_net_class` |
| `groups.py` | 109 | 6 | 1 | `compute_clearance` |
| `noise.py` | 29 | 2 | 0 | none |
| `routing.py` | 76 | 4 | 0 | none |
| `safety.py` | 45 | 4 | 0 | none |
| `thermal.py` | 77 | 2 | 0 | none — plus 2 module constants |
| `topology.py` | 62 | 4 | 0 | none |

The five method bodies total **~58 LOC**, a large share of which is comments.
The other ~969 LOC is `Field(...)` declarations.

None of the 9 files imports a `temper_*` Rust module. `config.py` reaches one
transitively: it annotates a field with `NetClassification` from
`temper_placer.core.net_types`, which is itself already a pure-delegation shim
over `temper_design_bundle_python` (PR #560).

### None of the program's numerical traps are reachable here

`grep -nE "np\.|numpy|sum\(|min\(|max\(|linspace|clip|\*\*2|radians|norm\("`
over all 9 files returns **no matches**. There is no numpy, no accumulation, no
NaN-propagating comparison, no iteration-order dependence. The only float
expression in the entire surface is:

```python
math.sqrt(pin_count) * pitch_mm * 1.5
```

The R1a bit-parity apparatus, the compensated-summation traps, and the
libm-divergence risk that sank PR #714 have no purchase on this surface. A
differential harness here would compare one `sqrt` and two regexes.

## 2. The contract is pydantic, and five public pydantic behaviours are load-bearing

The Phase 2 precedent — `net_types`, PR #560 — converted **`@dataclass` and
`Enum`** types to pyclasses. That is API-preserving: a frozen dataclass's public
surface (attributes, `__repr__`, `__eq__`) maps onto a `#[pyclass]` almost
exactly.

`_constraint_types` is `pydantic.BaseModel` throughout, which is a different
contract. A `#[pyclass]` is not a `BaseModel` and cannot be one without
reimplementing pydantic in Rust. These five usages would break:

| # | pydantic behaviour | consumer | consequence |
|---|---|---|---|
| 1 | `PlacementConstraints.model_validate(dict)` | `io/config_loader.py:862` | sole entry point for all YAML config loading |
| 2 | `pydantic.ValidationError` | `io/config_loader.py:863-864` | caught and re-wrapped; stored as the public `ConfigValidationError.validation_error` attribute |
| 3 | `model_fields` recursive introspection | `scripts/gen_config_reference.py` | **CI gate** (`--check`, `.github/workflows/python-tests.yml:1259`) that walks the whole model tree reading `annotation`, default, `description`, and `ge`/`gt`/`le` metadata to regenerate a checked-in doc |
| 4 | `model_dump()` | `tests/deterministic/stages/test_hv_lv_partition.py:64` | exact-dict assertion |
| 5 | field constraints + `extra="forbid"` + `frozen=True` | every model | `ge=0`/`gt=0`/`le=1000` raise `ValidationError`; `extra="forbid"` rejects unknown YAML keys |

Item 3 is the hard blocker: the `Field(description=...)` metadata on all 34
models is not decoration, it is the input to a gate. A `#[pyclass]` exposes no
`model_fields` and no `FieldInfo`.

The task's own constraint — *"the public Python API must not change: attributes,
method signatures, `__repr__`, `__eq__`, exception types"* — and the instruction
to deliver `#[pyclass]` contract types are, for this specific surface, mutually
unsatisfiable. `__repr__` alone differs: pydantic emits
`LossConfig(weight=1.0, enabled=True, margin=None)`; a pyclass emits whatever
`#[pyo3(get)]` and a hand-written `__repr__` produce, and exception types change
from `ValidationError` to `PyValueError`/`PyTypeError`.

## 3. The pivot's stated benefit is already realised here

The premise for the pivot is that downstream *"stops marshalling Python objects
across the boundary on every call."* For this surface that marshalling does not
happen. The Rust constraint engine already takes flat primitives:

```rust
// packages/temper-placer/temper-constraints/src/lib.rs
#[pyo3(signature = (positions, idx_a, idx_b, max_distance_mm, weight,
                    metric = 1, pin_a_x = None, pin_a_y = None, ...))]
fn compute_adjacent_loss_py(...)
```

Constraint objects are decomposed to scalars on the Python side before
crossing. No `PlacementConstraints` instance is marshalled per call, so
converting it to a pyclass removes zero crossings.

It *adds* them. `PlacementConstraints` has ~50 fields read throughout the
placer. Measured on this machine:

- pydantic frozen attribute read: **7.7 ns**
- pyo3 boundary floor: **268 ns**

Every config field read would get ~35x more expensive.

## 4. Measured: 4 of 5 compute sites are net-negative in Rust

Machine: arm64 macOS (Darwin 25.5.0), CPython 3.12.13, pydantic 2.13.4.
Boundary floor obtained by fitting `sha256_hex` at 1 B and 1024 B
(275.9 ns and 3148.5 ns, 2.81 ns/byte) and extrapolating to zero payload,
which isolates crossing + argument conversion + return allocation from the
hashing work.

| compute site | Python | vs boundary floor | verdict |
|---|---:|---:|---|
| `get_zone_for_component` | 12.9 ns | 0.05x | **21x slower** in Rust |
| `compute_clearance` | 26.9 ns | 0.10x | **10x slower** in Rust |
| `get_active_losses` | 459.2 ns | 1.71x | no material win |
| `get_weights` | 656.0 ns | 2.44x | no material win |
| `get_net_class` | 1010.3 ns | 3.76x | only candidate |

`get_active_losses` is worse than the ratio suggests: it returns a dict of up to
11 `LossConfig` **Python objects**. Implementing it in Rust would *increase*
Python-object marshalling — the precise cost the pivot exists to remove.

`get_net_class` is the only site with headroom, and it is a poor trade:

- It takes and returns Python `str`, so ~268 ns of the 1010 ns is unavoidable;
  the realistic ceiling is well under the nominal 3.8x.
- Rust's `regex` crate and Python's `re` differ in edge semantics, so this is
  the one site where a differential would be doing real work — for a method
  whose only production call site is **duck-typed**:
  `getattr(constraints, "get_net_class", None)` at
  `deterministic/stages/_phase_rotation.py:235`.
- Its two patterns were deliberately anchored to fix substring false-positives
  (`config.py:442-460`, referencing
  `docs/evidence/2026-07-28-zone-layer-classification-fix.md`). That history is
  a reason to leave the implementation alone absent a real payoff.

Three of the five methods — `compute_clearance`, `get_active_losses`,
`get_weights` — have **no production call sites at all**. They are exercised
only by tests.

## 5. Recommendation

Move this pattern out of Phase 2. Phase 2's thesis holds for the surfaces that
are dataclass-shaped and genuinely on the boundary — `core/**` and `pcl/**`,
already listed separately in `wave4-verdicts.yaml` — and it does not hold here.

This is not a pre-exclusion under R7. R7 forbids excluding a surface *before*
surveying it; the surface was surveyed in full, and the exclusion is the survey's
result, with the measurements above as evidence.

If Phase 2 is nonetheless required to claim this directory, the only
API-preserving option is to keep every `BaseModel` exactly as-is and move
`get_net_class`'s two regexes behind an FFI call — roughly 10 statements, a
sub-2x win on a cold path, in exchange for a new dependency edge from the
otherwise dependency-free contract layer into a Rust crate. That is a net loss
and is not recommended.

## What was not verified

- **Linux.** All timings are arm64 macOS. The boundary floor and the pydantic
  read cost will differ on x86-64 Linux CI. The *ordering* (boundary floor
  greatly exceeding a dict lookup or a `sqrt`) is architecture-independent, but
  the specific ratios are not, and I did not measure them there.
- The 268 ns floor is an estimate from a two-point linear fit on one probe
  function, not a direct measurement of an empty pyo3 call — no zero-work pyo3
  entry point is exported by the built extensions. It is accurate enough for a
  20x margin and should not be quoted as a precise constant.
- `temper_design_bundle_python` in the shared venv is a stale build (it exports
  only the hashing helpers, not `NetClassification`). That does not affect the
  boundary-floor measurement, which needs only one linear pyo3 function, but it
  means I did not exercise the `net_types` pyclasses themselves.
