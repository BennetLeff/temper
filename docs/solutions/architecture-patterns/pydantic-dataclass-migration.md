---
title: "Pydantic Migration: @dataclass to BaseModel for NetClassRules (N4)"
date: 2026-06-22
category: architecture-patterns
module: temper-placer/core
problem_type: architecture_pattern
component: data-model
severity: medium
applies_when:
  - Adding a new required field to a widely-instantiated data class
  - Migrating from stdlib dataclass to Pydantic for validation or type constraints
  - Fixing test assertions that encode stale field values after a field refactoring
tags:
  - pydantic
  - dataclass
  - migration
  - frozen-model
  - safety-category
  - literal-types
  - test-maintenance
  - sprint-N4
---

# Pydantic Migration: @dataclass to BaseModel for NetClassRules (N4)

## Context

During the June sprint refactoring (N4), `NetClassRules` needed three new
fields—`dru_priority` (required), `required_layer` (optional), and
`safety_category` (typed `Literal["HV", "LV", "AC", "iso"] | None`)—to enable
the HV/LV separation and creepage safety checks in `temper-drc`.

The class was originally a stdlib `@dataclass`. Adding a required field to a
dataclass that is instantiated across 9 entries in `TEMPER_NET_CLASSES`, test
factories, and the fallback path in `DesignRules.get_rules_for_net()` meant that
every call site would silently break at runtime unless the developer found every
one. Stdlib dataclasses offer no validation at construction time beyond
`__post_init__` (if written).

The decision was to migrate to Pydantic `BaseModel(frozen=True)` in a single
commit, adding all three new fields and fixing every call site simultaneously.

## Guidance

### Why Pydantic over dataclasses for this case

1. **Required-field enforcement at construction time.** A Pydantic `BaseModel`
   raises `ValidationError` immediately on `NetClassRules(name="Foo",
   trace_width=0.5)` if `dru_priority` is missing. An `@dataclass` with a
   required field without a default would also fail, but only with a less
   specific `TypeError`. More importantly, Pydantic catches type mismatches
   (e.g., passing `"10"` for `dru_priority`) that a dataclass silently accepts.

2. **`Literal` type for `safety_category`.** The four valid safety categories
   (`"HV"`, `"LV"`, `"AC"`, `"iso"`) and `None` are enforced by the type
   system at runtime. A typo like `safety_category="Hv"` is rejected at
   construction rather than propagating to downstream checks. Stdlib
   dataclasses cannot enforce this without a custom `__post_init__`.

3. **Immutability via `frozen=True`.** `ConfigDict(frozen=True)` replaces the
   `frozen=True` kwarg (Pydantic v1) and prevents accidental mutation.
   `@dataclass(frozen=True)` also provides immutability, but combined with
   the validation advantage, Pydantic's `frozen` is the better fit.

4. **Explicit `model_config` as a canonical location.** Future model-level
   configuration (e.g., `extra="forbid"` to reject unknown kwargs) has an
   obvious place to land without ad-hoc decorator arguments.

### Migration steps

```
@dataclass                     →   class NetClassRules(BaseModel):
class NetClassRules:               model_config = ConfigDict(frozen=True)
    name: str                          name: str
    trace_width: float                 trace_width: float
    ...                                ...
    target_impedance: float|None       target_impedance: float | None = None
                                       dru_priority: int                     # required
                                       required_layer: str | None = None
                                       safety_category: Literal["HV", ...] | None = None
```

The key steps in `67349784`:

1. Replace `@dataclass` decorator with `BaseModel` inheritance.
2. Add `model_config = ConfigDict(frozen=True)`.
3. Add the three new fields with appropriate types and defaults.
4. Add `from pydantic import BaseModel, ConfigDict` and `from typing import
   Literal` to imports.
5. Populate `dru_priority`, `required_layer`, and `safety_category` on all 9
   entries in `TEMPER_NET_CLASSES`.
6. Add `dru_priority=999` to the fallback `NetClassRules(...)` call in
   `get_rules_for_net()`.
7. Update all test-helper `NetClassRules(...)` calls to include `dru_priority=`.
8. Fix stale test assertions.

### The stale-test-assertions problem

The June sprint refactoring had already changed the field values for `Power`
and `HighCurrent` net classes (e.g., `Power.trace_width` 1.0→0.5,
`Power.clearance` 0.5→0.25, `HighCurrent.trace_width` 2.0→0.5). However,
several test assertions still tested against the **old** values. Because the
tests construct `DesignRules` via the factory and then read `.trace_width`,
the assertions appeared to pass against the pre-sprint defaults that no
longer matched the actual production values in `TEMPER_NET_CLASSES`.

The migration commit surfaced these stale assertions because adding
`dru_priority` forced touching every `NetClassRules(...)` instantiation in
the test file. The commit author fixed them in the same change:

| Test assertion | Old (stale) | New (actual) |
|---|---|---|
| `Power.trace_width` | `1.0` | `0.5` |
| `Power.clearance` | `0.5` | `0.25` |
| `Power.via_diameter` | `1.0` | `0.8` |
| `Power.via_drill` | `0.5` | `0.4` |
| `HighCurrent.trace_width` | `2.0` | `0.5` |
| `HighCurrent.via_diameter` | `1.2` | `0.8` |

Also, the `test_all_expected_classes_defined` only checked 5 classes
(`["Power", "GND", "HighSpeed", "Signal", "HighCurrent"]`) but the actual
`TEMPER_NET_CLASSES` dict had grown to 9. Updated to include `ACMains`,
`HighVoltage`, `FinePitch`, and `GateDrive`.

## Why This Matters

Pydantic `BaseModel` turns a silent-misconfiguration risk into an
immediate `ValidationError`. Without it, adding a required field to a
dataclass forces the developer to grep for every call site manually — miss
one, and it fails only when that code path is exercised (potentially in
production).

The `Literal` type on `safety_category` is particularly important for safety
checks. The HV/LV separation check in `hv_lv_separation.py:44-47` and the
creepage check in `creepage.py:46` both call `resolve_safety_category()`,
which reads `safety_category` from `TEMPER_NET_CLASSES` and falls back to
keyword scanning. A typo in a net class's `safety_category` string (e.g.,
`"hv"` instead of `"HV"`) would silently fail the keyword fallback and
produce incorrect results. Pydantic catches this at module-import time.

## When to Apply

- When a data class has required fields whose absence should be caught at
  construction, not at downstream use.
- When field values have a constrained set of valid options (enums,
  `Literal`, regex-validated strings).
- When the data class is instantiated at many call sites (here: 9 dictionary
  entries, test factories, a fallback path) and adding a required field
  would otherwise require manual grep-and-fix.
- When runtime type-checking provides value beyond static mypy/pyright
  analysis (e.g., data loaded from YAML or JSON at runtime that Pydantic
  validates before the rest of the application sees it).

Do NOT apply when:
- The data class is a pure internal intermediary with a single construction
  site and no external data ingestion.
- The performance cost of Pydantic's validation (attribute access overhead
  on frozen models) matters in a hot loop. (For `NetClassRules`, attribute
  reads are infrequent — the model is constructed once at startup and read
  many times during routing.)
- The codebase has no existing Pydantic dependency and adding one requires
  nontrivial infrastructure work. (Here, Pydantic was already available in
  the dependency tree via `temper-drc`.)

## Examples

### Before: stdlib @dataclass

```python
from dataclasses import dataclass

@dataclass
class NetClassRules:
    name: str
    trace_width: float
    clearance: float
    via_diameter: float = 0.6
    via_drill: float = 0.3
    via_template: str | None = None
    creepage_mm: float = 0.0
    target_impedance: float | None = None
    voltage_v: float = 0.0
    routing_strategy: str | None = None
    via_cost_multiplier: float = 1.0
    layer_costs: dict[str, float] | None = None

# No field-level validation. A typo in safety_category is silently
# accepted. Adding a required field means every call site breaks
# at runtime with a non-obvious TypeError.
```

### After: Pydantic BaseModel

```python
from typing import Literal
from pydantic import BaseModel, ConfigDict

class NetClassRules(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    trace_width: float
    clearance: float
    via_diameter: float = 0.6
    via_drill: float = 0.3
    via_template: str | None = None
    creepage_mm: float = 0.0
    target_impedance: float | None = None
    voltage_v: float = 0.0
    routing_strategy: str | None = None
    via_cost_multiplier: float = 1.0
    layer_costs: dict[str, float] | None = None
    dru_priority: int                                 # required
    required_layer: str | None = None
    safety_category: Literal["HV", "LV", "AC", "iso"] | None = None
```

### Consumer: safety category resolution

In `_safety_keywords.py:25-31`, Pydantic's type enforcement guarantees that
`safety_category` is either one of the four valid strings or `None`. The
fallback keyword scan only fires when `safety_category` is `None` or the
net class is not in `TEMPER_NET_CLASSES`:

```python
def resolve_safety_category(net_class_str: str) -> str | None:
    from temper_placer.core.design_rules import TEMPER_NET_CLASSES
    rules = TEMPER_NET_CLASSES.get(net_class_str)
    if rules is not None and getattr(rules, "safety_category", None) is not None:
        return rules.safety_category  # Guaranteed valid by Pydantic
    # Fallback: keyword scan (only fires for unregistered net classes)
    ...
```

### Consumer: HV/LV separation check

In `hv_lv_separation.py:42-47`, the resolved category is used to classify
nets as HV/AC or LV. Pydantic prevents a malformed `safety_category` from
ever reaching this code:

```python
a_cat = resolve_safety_category(comp_a.net_class)
b_cat = resolve_safety_category(comp_b.net_class)
is_a_hv = a_cat in ("HV", "AC")
is_b_hv = b_cat in ("HV", "AC")
is_a_lv = a_cat == "LV"
is_b_lv = b_cat == "LV"
```

## Related

- `packages/temper-placer/src/temper_placer/core/design_rules.py:93-133` — NetClassRules Pydantic model
- `packages/temper-placer/src/temper_placer/core/design_rules.py:337-444` — TEMPER_NET_CLASSES with all 9 populated entries
- `packages/temper-drc/src/temper_drc/checks/safety/_safety_keywords.py` — resolve_safety_category consumer
- `packages/temper-drc/src/temper_drc/checks/safety/hv_lv_separation.py` — HVLVSeparationCheck consumer
- `packages/temper-drc/src/temper_drc/checks/safety/creepage.py` — CreepageCheck consumer
- `packages/temper-placer/tests/core/test_design_rules.py` — updated test assertions
- `docs/solutions/architecture-patterns/ci-gate-quality-enforcement.md` — sibling pattern (safety SSOT N2)
