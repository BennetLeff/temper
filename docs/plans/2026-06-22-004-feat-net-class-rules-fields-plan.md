---
title: "feat: NetClassRules Field Extension — dru_priority + required_layer + safety_category"
type: feat
status: active
date: 2026-06-22
origin: docs/brainstorms/2026-06-21-net-class-rules-fields-requirements.md
---

# feat: NetClassRules Field Extension — dru_priority + required_layer + safety_category

## Summary

A coordinated single-changeset model extension that adds three fields to `NetClassRules` at `packages/temper-placer/temper_placer/core/design_rules.py:95` — `dru_priority: int`, `required_layer: str | None`, `safety_category: Literal["HV","LV","AC","iso"] | None` — and collapses the five hand-maintained registries that today duplicate information already derivable from the net class definitions. One model edit retires: the `class_order` list and its drift `assert` at `scripts/generate_kicad_dru.py:229-243`; the `_REQUIRED_LAYERS` dict at `packages/temper-drc/temper_drc/checks/drc/layer_assignment.py:13-16`; the `HV_KEYWORDS`/`LV_KEYWORDS` substring scan at `packages/temper-drc/temper_drc/checks/safety/hv_lv_separation.py:34-35`; and the two divergent `ISO_KEYWORDS` lists at `packages/temper-drc/temper_drc/checks/safety/creepage.py:31-34` and `packages/temper-drc/temper_drc/checks/safety/isolation.py:30`.

N4 builds on the parent initiative `docs/plans/2026-06-21-002-feat-source-of-truth-validation-plan.md` U4 (Pydantic migration of `NetClassRules`). It assumes that migration has landed — the `Literal` field validation that makes a typo like `"Iso"` a `ValidationError` at import requires `BaseModel`. If U4 has not landed, N4 must wait: applying `Literal` validation to a stdlib `@dataclass` requires a manual `__post_init__` and loses the parent plan's `model_dump()` consumer story. The keyword scanners survive as a loud-warning fallback, never as the primary classifier; `TEMPER_NET_ASSIGNMENTS` (`design_rules.py:563-575`) remains the authoritative net→class map and is not subsumed.

---

## Problem Frame

Four pieces of information about each net class live outside `NetClassRules` in hand-maintained registries that must be kept in sync by the developer:

1. **DRU emission order.** `scripts/generate_kicad_dru.py:229-239` hardcodes a 9-element `class_order` list. The drift `assert` at line 240 catches additions/removals but not reordering, and the list must be edited by hand whenever a class is added. The `assert` exists precisely because this list drifted silently during the June 2026 sprint.
2. **Layer constraints.** `packages/temper-drc/temper_drc/checks/drc/layer_assignment.py:13-16` defines `_REQUIRED_LAYERS = {"HighVoltage": "B.Cu", "GateDrive": "F.Cu"}`. The only consumer is 30 lines below at `layer_assignment.py:118`. There is no structural link from `NetClassRules("HighVoltage")` to the fact that it must route on `B.Cu`.
3. **HV/LV safety classification.** `packages/temper-drc/temper_drc/checks/safety/hv_lv_separation.py:34-35` scans `comp.net_class.lower()` for the substrings `["hv","line","ac","neutral","mains"]` and `["lv","signal","3v3","5v","gnd","analog"]`. This duplicates `TEMPER_NET_ASSIGNMENTS` (`design_rules.py:563-575`): a net assigned to `ACMains` is HV by declaration, not by substring. The substring scan also mis-classifies — `ACMains` contains `"ac"` but not `"hv"` or `"line"`; `"ac"` matches `ACMains` but also any future `DAC` class. `HighCurrent` contains none of `HV_KEYWORDS` and is silently treated as neither HV nor LV today — a latent safety bug.
4. **Isolation classification.** `ISO_KEYWORDS` is duplicated in two checks with **divergent lists**: `creepage.py:31-34` uses `["iso","opto","coupler","isolator","transformer","adum","dcdc","mev1"]` while `isolation.py:30` uses `["iso","opto","coupler","transformer","gutter","slot"]`. The first list classifies components; the second classifies both components and zone names (hence `gutter`,`slot`).

A critical architectural fact the plan must address: the three safety checks today read `comp.net_class` (a free-form string on `ComponentPlacement` at `packages/temper-drc/temper_drc/input/placement.py:39`), not a resolved `NetClassRules`. Test fixtures at `packages/temper-drc/tests/checks/safety/test_hv_lv_separation.py:14-15` use placeholder strings `"HV"`, `"LV"`, `"ISO"` that are **not** keys in `TEMPER_NET_CLASSES`. The migration must therefore resolve `comp.net_class` against `TEMPER_NET_CLASSES` and fall back to the keyword scan when the string is not a registered class name (preserving test behaviour and tolerating undeclared nets).

Each registry is small and each looks harmless in isolation. The failure mode is the same as the broader source-of-truth problem: a constraint exists in `NetClassRules` (or in `TEMPER_NET_ASSIGNMENTS`) and is re-derived by substring heuristics elsewhere, with no machine-enforced link. Adding a new safety-relevant net class today requires editing `NetClassRules`, `TEMPER_NET_ASSIGNMENTS`, `_REQUIRED_LAYERS`, possibly `class_order`, and hoping the keyword scanners happen to match the new name.

---

## Scope Boundaries

### In scope

- R1–R7 from the origin requirements document: the three new fields on `NetClassRules`, the `dru_priority`-derived emission order in `generate_kicad_dru.py`, the `required_layer` repointing in `layer_assignment.py`, the `safety_category`-driven classification with keyword fallback in the three safety checks, the consolidated `ISO_ZONE_KEYWORDS` constant, the deletion of the four legacy registries, and the test updates.
- The `HighCurrent.safety_category` latent-bug fix (origin Open Question [Affects R4/A4]) is in scope as a called-out behaviour change: `HighCurrent` is declared `"HV"`, and the changeset description names the reclassification.

### Deferred to companion plan

- `docs/plans/2026-06-21-002-feat-source-of-truth-validation-plan.md` U4: Pydantic migration of `NetClassRules` (`@dataclass` → `BaseModel` with `ConfigDict(frozen=True)`). N4 adds three fields to that model; U4 must land first.
- Same plan U2: module-scope `assert` that every value in `TEMPER_NET_ASSIGNMENTS` is a key in `TEMPER_NET_CLASSES`. N4 depends on this invariant (so `safety_category` resolution via `TEMPER_NET_CLASSES[cls]` never KeyErrors) but does not add the assert.
- Same plan U5: IEC 60664-1 `iec_reference` field and normative-minimum validator. Orthogonal to N4's three fields.
- Same plan U6/U7: golden-file DRU diffing and `kiutils` round-trip parse. N4's R7 behaviour-preservation relies on manual diff of `pcb/temper.kicad_dru` for this changeset; the automated golden-file guard is the companion plan's deliverable.

### Out of scope

- **`TEMPER_NET_ASSIGNMENTS` removal.** The net→class map is orthogonal to class properties and remains the authoritative declaration of which net belongs to which class (R5).
- **Zone classification.** `IsolationCheck`'s branch that identifies isolation *zones* by name continues to use keywords; zones are not net classes and do not carry a `safety_category`. Only the component-classification branch is collapsed (R4, origin Assumption A6).
- **Failing CI on undeclared nets.** The keyword fallback is fail-open with a stderr warning, not a CI failure. Promoting it to a hard error is a separate decision (origin Open Question [Affects R4], deferred).
- **Component-level `isolation_barrier` attribute** (Phase 5 plan's option (b) for the ADUM1250 gap). `safety_category="iso"` on the net class is the chosen mechanism; the two are compatible if both are later adopted.
- **Reordering existing net classes.** `dru_priority` values reproduce the current `class_order` (10, 20, 30, …, 90). Changing the order is a separate decision (origin Assumption A2).
- **`LayerAssignmentCheck`'s substring-heuristic fallback** at `layer_assignment.py:113-116` (matching `r.name.lower() in net.lower()`) is not collapsed by this change (origin Open Question [Affects R3], deferred).

---

## Key Technical Decisions

**Three fields added to `NetClassRules` with exact names and semantics per R1.** `dru_priority: int` (required, no default — a new class without a priority is a developer error and the `ValidationError` is the desired signal; resolves origin Open Question [Affects R1] "required, no default"); `required_layer: str | None = None`; `safety_category: Literal["HV","LV","AC","iso"] | None = None`. `Literal` is chosen over `enum.Enum` to keep `NetClassRules` serialization plain (the parent plan's U4 uses Pydantic v2 with `model_dump()` consumers; a `Literal` serializes as a bare string, an `Enum` requires custom json encoders). A typo like `"Iso"` or `"hv"` is a `ValidationError` at construction — the success criterion "fail at import, not at DRC run time" is met.

**`"AC"` kept distinct from `"HV"` in the `safety_category` vocabulary.** Resolves origin Open Question [Affects R1]: AC mains composes with the IEC 60335-1 mains-specific clearance (6.0mm in `ACMains.clearance`) versus the IEC 60664-1 DC clearance (2.0mm in `HighVoltage.clearance`), and `HVLVSeparationCheck` may want to treat AC↔LV differently from HV↔LV in a future changeset. The current `HV_KEYWORDS` list treats `"ac"` as HV; merging would lose the distinction. The plan treats `"HV"` and `"AC"` as both triggering the HV side of the HV↔LV separation check (R4), so behaviour is preserved for `ACMains` while keeping the vocabulary distinct for future use. Confirm with an EE during implementation review (carried forward as a Deferred item, not a plan blocker).

**`dru_priority` values reproduce the current `class_order` exactly.** Per Assumption A2: `ACMains=10, HighVoltage=20, FinePitch=30, Power=40, GateDrive=50, GND=60, HighSpeed=70, Signal=80, HighCurrent=90`. Ties (none currently) break by lexicographic class name. This reproduces the current DRU byte-for-byte; the golden `pcb/temper.kicad_dru` diff is empty. The `assert set(class_order) == set(TEMPER_NET_CLASSES.keys())` at `generate_kicad_dru.py:240-243` is replaced by `class_order = sorted(TEMPER_NET_CLASSES.keys(), key=lambda k: (TEMPER_NET_CLASSES[k].dru_priority, k))`. A module-scope assertion that no `dru_priority` is `None` (impossible after U4 since the field is required, but retained as a backstop) is kept; the drift assert on key set is retired because the list is now derived (R2).

**`required_layer` values reproduce current `_REQUIRED_LAYERS`.** Per Assumption A3: `HighVoltage → "B.Cu"`, `GateDrive → "F.Cu"`, all others → `None`. `LayerAssignmentCheck` at `layer_assignment.py:118` reads `required_layer` from the resolved `NetClassRules` instead of `_REQUIRED_LAYERS.get(cls)`. The `cls = TEMPER_NET_ASSIGNMENTS.get(net)` lookup at `layer_assignment.py:110` is unchanged (R3). The module-level `_REQUIRED_LAYERS` dict is deleted.

**`HighCurrent.safety_category = "HV"` — the latent-bug fix.** Resolves origin Open Question [Affects R4/A4]: `HighCurrent` today matches none of `HV_KEYWORDS` and is silently treated as neither HV nor LV. `HighCurrent` carries `SW_NODE`/`DC_BUS` currents at 400V per `TEMPER_NET_ASSIGNMENTS` (`design_rules.py:571` maps `SW_NODE` to `HighVoltage`, but `HighCurrent` itself is a separate class for 20A+ nets). The migration is the right moment to declare it `"HV"`; this changes behaviour (a `HighCurrent`-classed component will now trigger HV↔LV separation) and must be called out in the changeset description. If EE review disagrees, the fallback is `None` (preserving current behaviour); the plan default is `"HV"`.

**Safety-check resolution path: model first, keyword fallback with stderr warning.** The three safety checks today read `comp.net_class` (a free-form string at `placement.py:39`), not a resolved `NetClassRules`. Test fixtures use `"HV"`, `"LV"`, `"ISO"` which are not keys in `TEMPER_NET_CLASSES`. The migration introduces a shared resolver used by all three checks:

```python
def resolve_safety_category(net_class_str: str) -> str | None:
    """Return 'HV'|'LV'|'AC'|'iso'|None for a net-class string."""
    rules = TEMPER_NET_CLASSES.get(net_class_str)
    if rules is not None and rules.safety_category is not None:
        return rules.safety_category
    # Fallback: keyword scan with loud warning
    ...
```

When `comp.net_class` resolves to a registered class with a non-`None` `safety_category`, the check uses it directly — no keyword scan. When it does not (test fixture, undeclared net, or a registered class with `safety_category=None`), the check falls back to the keyword scan and writes a **loud warning to stderr** naming the net/class string, the guessed category, and the message `"declare safety_category on net class '<name>' or add net to TEMPER_NET_ASSIGNMENTS"` (R4, F3). The warning is `sys.stderr.write(...)` — grep-visible in CI logs, not a CI failure. The fallback preserves routing throughput during development; it never silently mis-classifies a declared net.

**`ISO_KEYWORDS` consolidation.** The two divergent lists at `creepage.py:31-34` and `isolation.py:30` are replaced by a single shared module `packages/temper-drc/temper_drc/checks/safety/_safety_keywords.py` (new) exporting:
- `ISO_COMPONENT_KEYWORDS = ("iso","opto","coupler","isolator","transformer","adum","dcdc","mev1")` — used by `CreepageCheck`'s fallback and `IsolationCheck`'s component-classification fallback (the union of the two lists minus the zone-only `gutter`/`slot`).
- `ISO_ZONE_KEYWORDS = ("iso","opto","coupler","transformer","gutter","slot")` — used by `IsolationCheck`'s zone-name classification branch only (R4, Assumption A6).

`IsolationCheck`'s zone-name branch is **not collapsed** — zones are named in the constraints input (`constraints.zones` at `isolation.py:34`), not derived from net classes, and do not carry a `safety_category`. The two fallback constants are kept distinct because their vocabularies legitimately differ (zone names include `gutter`/`slot`; component footprints include `adum`/`dcdc`/`mev1`).

**Single coordinated changeset (R6).** The intermediate state (some consumers reading the field, others reading the deleted legacy registry) is broken. The migration order within the changeset is: (1) add fields with defaults to `NetClassRules` (U4 already migrated it to Pydantic), (2) populate the 9 existing `TEMPER_NET_CLASSES` entries with `dru_priority`/`required_layer`/`safety_category` values that reproduce current behaviour (plus the `HighCurrent` fix), (3) update `generate_kicad_dru.py`, (4) update `layer_assignment.py`, (5) update the three safety checks + share `ISO_COMPONENT_KEYWORDS`/`ISO_ZONE_KEYWORDS`, (6) delete the four legacy registries, (7) update tests. All in one commit.

**Behaviour-preservation verification (R7).** The DRU output is regenerated and diffed against `pcb/temper.kicad_dru` — the diff must be empty (Assumption A2 guarantees byte-identical ordering). `LayerAssignmentCheck` produces the same issues on the same board (the `required_layer` values are identical). The safety checks produce the same HV/LV and iso classifications for all currently-declared nets. Any net currently classified by keyword that is **not** in `TEMPER_NET_ASSIGNMENTS` becomes a loud-warning case — these are enumerated in the changeset description (the test fixtures' `"HV"`/`"LV"`/`"ISO"` strings fall here, and the updated tests assert the warning is emitted).

**Test fixtures must be updated to exercise both paths.** The existing tests at `test_hv_lv_separation.py:14-15`, `test_isolation.py:18-20`, `test_creepage.py:14` use placeholder strings `"HV"`/`"LV"`/`"ISO"`. After migration these trigger the keyword fallback and emit stderr warnings. The updated tests: (a) keep the placeholder-string cases and assert the fallback warning is emitted (covering F3), and (b) add new cases using the real class names `"HighVoltage"`/`"ACMains"`/`"Signal"` that resolve via `TEMPER_NET_CLASSES` with no warning (covering F1/F2). The `_FakeNetClassRules` stubs at `test_layer_assignment.py:17-20` and `test_trace_width.py:21-24` must be extended with `dru_priority`, `required_layer`, `safety_category` attributes so the fakes stay structurally compatible with the migrated check code paths.

---

## Implementation Units

### U1. Add three fields to `NetClassRules` and populate `TEMPER_NET_CLASSES`

**Goal:** Extend the Pydantic `NetClassRules` model (post-U4) with `dru_priority: int`, `required_layer: str | None`, `safety_category: Literal["HV","LV","AC","iso"] | None`, and populate the 9 existing `TEMPER_NET_CLASSES` entries with values that reproduce current behaviour plus the `HighCurrent` fix.

**Requirements:** R1, R5

**Dependencies:** Parent plan U4 (`NetClassRules` must already be a Pydantic v2 `BaseModel` with `model_config = ConfigDict(frozen=True)`). Parent plan U2 (module-scope assert that `TEMPER_NET_ASSIGNMENTS` values are keys in `TEMPER_NET_CLASSES`).

**Files:**
- `packages/temper-placer/temper_placer/core/design_rules.py` (add three fields to `NetClassRules` at line 95-127; populate the 9 `TEMPER_NET_CLASSES` entries at lines 480-560)
- `packages/temper-placer/tests/core/test_design_rules.py` (add field-population assertions; extend the `name in TEMPER_NET_CLASSES` loop at line 154)

**Approach:**

Add to `NetClassRules` after the existing `layer_costs` field at `design_rules.py:125-127`:

```python
dru_priority: int                       # lower emits earlier in DRU trace-width section
required_layer: str | None = None       # KiCad layer name or None for no constraint
safety_category: Literal["HV","LV","AC","iso"] | None = None
```

`dru_priority` has no default — a new class without a priority is a `ValidationError` at construction (resolves origin Open Question [Affects R1]). `from typing import Literal` is added to the module imports. After U4 the model is a Pydantic `BaseModel`, so `Literal` validation is automatic; no `__post_init__` is needed.

Populate the 9 `TEMPER_NET_CLASSES` entries (R1, Assumptions A2/A3/A4):

| Class | `dru_priority` | `required_layer` | `safety_category` |
|-------|----------------|------------------|-------------------|
| `ACMains` (`design_rules.py:481`) | 10 | `None` | `"AC"` |
| `HighVoltage` (`design_rules.py:492`) | 20 | `"B.Cu"` | `"HV"` |
| `FinePitch` (`design_rules.py:503`) | 30 | `None` | `"LV"` |
| `Power` (`design_rules.py:511`) | 40 | `None` | `"LV"` |
| `GateDrive` (`design_rules.py:519`) | 50 | `"F.Cu"` | `"LV"` |
| `GND` (`design_rules.py:527`) | 60 | `None` | `"LV"` |
| `HighSpeed` (`design_rules.py:535`) | 70 | `None` | `"LV"` |
| `Signal` (`design_rules.py:544`) | 80 | `None` | `"LV"` |
| `HighCurrent` (`design_rules.py:552`) | 90 | `None` | `"HV"` (latent-bug fix) |

No current class maps to `"iso"`; isolation is currently inferred per-component by footprint, not by class. After migration, any class that should classify as iso is declared so (none today).

**Patterns to follow:** Existing `TEMPER_NET_CLASSES` literal style at `design_rules.py:480-560`. Pydantic v2 `BaseModel` field syntax (post-U4).

**Test scenarios:**
- `from temper_placer.core.design_rules import TEMPER_NET_CLASSES; TEMPER_NET_CLASSES["ACMains"].dru_priority == 10`.
- All 9 entries have non-`None` `dru_priority` (required-field violation caught by Pydantic at import if a new class omits it).
- `TEMPER_NET_CLASSES["HighVoltage"].required_layer == "B.Cu"`; `TEMPER_NET_CLASSES["GateDrive"].required_layer == "F.Cu"`; all others `None`.
- `TEMPER_NET_CLASSES["ACMains"].safety_category == "AC"`; `HighVoltage`/`HighCurrent` == `"HV"`; `FinePitch`/`Power`/`GateDrive`/`GND`/`HighSpeed`/`Signal` == `"LV"`.
- Constructing `NetClassRules(name="X", trace_width=0.2, clearance=0.1, dru_priority=10, safety_category="Iso")` raises `pydantic.ValidationError` (typo caught at construction).
- Constructing `NetClassRules(name="X", trace_width=0.2, clearance=0.1, dru_priority=10)` succeeds (all optionals default).
- Constructing `NetClassRules(name="X", trace_width=0.2, clearance=0.1)` raises `ValidationError` (missing required `dru_priority`).
- The existing `TEMPER_NET_ASSIGNMENTS`-keys-in-`TEMPER_NET_CLASSES` assert (parent U2) still passes — no assignment was changed.

**Verification:** `uv run pytest packages/temper-placer/tests/core/test_design_rules.py` passes. `python -c "from temper_placer.core.design_rules import TEMPER_NET_CLASSES; print({k: v.safety_category for k,v in TEMPER_NET_CLASSES.items()})"` prints the expected mapping.

> **Pre-existing bug — prerequisite fix before N4 lands.** `test_design_rules.py:159-162` (`test_power_class_parameters`) contains stale assertions that do not match the current `Power` class definition at `design_rules.py:357-364`. The test asserts `trace_width==1.0`, `clearance==0.5`, `via_diameter==1.0`, `via_drill==0.5`, but the actual `Power` class defines `trace_width=0.5`, `clearance=0.25`, `via_diameter=0.8`, `via_drill=0.4` (values were reduced in a prior changeset without updating the test). These assertions **must** be corrected to match the live class before N4 touches this test file, otherwise CI will fail on unrelated stale assertions when the test is extended with field-population checks. Fix: update the four asserts to `0.5`/`0.25`/`0.8`/`0.4` respectively.

---

### U2. Derive `class_order` from `dru_priority` in `generate_kicad_dru.py`

**Goal:** Replace the hardcoded `class_order` list and its drift `assert` with a derived sort, retiring the hand-maintained registry.

**Requirements:** R2

**Dependencies:** U1 (`dru_priority` must exist on `NetClassRules`)

**Files:**
- `scripts/generate_kicad_dru.py` (replace lines 229-243 with the derived sort; add a module-scope backstop assert)

**Approach:**

At `scripts/generate_kicad_dru.py:229-243`, replace:

```python
class_order = [
    "ACMains", "HighVoltage", "FinePitch", "Power", "GateDrive",
    "GND", "HighSpeed", "Signal", "HighCurrent",
]
assert set(class_order) == set(TEMPER_NET_CLASSES.keys()), (
    f"class_order out of sync with TEMPER_NET_CLASSES: "
    f"{set(class_order) ^ set(TEMPER_NET_CLASSES.keys())}"
)
```

with:

```python
class_order = sorted(
    TEMPER_NET_CLASSES.keys(),
    key=lambda k: (TEMPER_NET_CLASSES[k].dru_priority, k),
)
```

The drift assert on the key set is retired — the list is now derived, so it cannot drift. A module-scope (or function-scope) backstop `assert all(TEMPER_NET_CLASSES[k].dru_priority is not None for k in TEMPER_NET_CLASSES), "dru_priority must be set on every NetClassRules"` is retained as a defensive check (redundant after U1 since the field is required, but cheap and documents the invariant). Ties break by lexicographic class name (the `k` second sort key), documented in an inline comment.

Because the `dru_priority` values (10, 20, …, 90) are distinct and assigned to reproduce the current `class_order`, the derived sort produces the identical 9-element sequence. The generated `pcb/temper.kicad_dru` is byte-for-byte identical — verify with a diff.

**Patterns to follow:** The existing `assert set(class_order) == ...` pattern at `generate_kicad_dru.py:240` (now retired). Python `sorted` with tuple key.

**Test scenarios:**
- `generate_dru()` produces output byte-for-byte identical to the pre-change output (diff `pcb/temper.kicad_dru` before and after — empty diff).
- Adding a new `NetClassRules("Z_class", ..., dru_priority=15)` to `TEMPER_NET_CLASSES` causes it to emit between `ACMains` (10) and `HighVoltage` (20) with no `class_order` edit.
- Removing `dru_priority` from a class causes `ValidationError` at import (U1) — the generator never sees a `None` priority.

**Verification:** `python scripts/generate_kicad_dru.py` runs; `git diff pcb/temper.kicad_dru` is empty. `uv run pytest tests/deterministic/test_pipeline_integration.py` passes (per origin Open Question [Affects R6] consumer audit — this test reads `generate_kicad_dru.py` output).

---

### U3. Repoint `LayerAssignmentCheck` to `required_layer`

**Goal:** Replace the module-level `_REQUIRED_LAYERS` dict lookup with a read off the resolved `NetClassRules.required_layer`; delete the dict.

**Requirements:** R3

**Dependencies:** U1 (`required_layer` must exist on `NetClassRules`)

**Files:**
- `packages/temper-drc/temper_drc/checks/drc/layer_assignment.py` (delete lines 13-16; rewrite line 118)
- `packages/temper-drc/tests/checks/drc/test_layer_assignment.py` (extend `_FakeNetClassRules` at lines 17-20 with `required_layer`)

**Approach:**

Delete the `_REQUIRED_LAYERS` dict at `layer_assignment.py:13-16`. At `layer_assignment.py:118`, replace:

```python
required_layer = _REQUIRED_LAYERS.get(cls)
```

with:

```python
net_class_rules = TEMPER_NET_CLASSES.get(cls)
required_layer = net_class_rules.required_layer if net_class_rules is not None else None
```

The `cls = TEMPER_NET_ASSIGNMENTS.get(net)` lookup at `layer_assignment.py:110` is unchanged — `TEMPER_NET_ASSIGNMENTS` remains the authoritative net→class map (R3, R5). The substring-heuristic fallback at `layer_assignment.py:113-116` is unchanged (origin Open Question [Affects R3], deferred). When `cls` is the `"Signal"` default from the heuristic, `TEMPER_NET_CLASSES["Signal"].required_layer` is `None`, so the check continues to skip — behaviour preserved.

The test fake `_FakeNetClassRules` at `test_layer_assignment.py:17-20` must gain a `required_layer` attribute (default `None`) so the patched module's `net_class_rules.required_layer` access works. Add `required_layer: str | None = None` to `_FakeNetClassRules.__init__` and populate `_FAKE_NET_CLASSES["HighVoltage"].required_layer = "B.Cu"`, `_FAKE_NET_CLASSES["GateDrive"].required_layer = "F.Cu"`.

**Patterns to follow:** The existing `TEMPER_NET_CLASSES.get(cls)` pattern at `trace_width.py:110-112`.

**Test scenarios:**
- Existing `test_layer_assignment.py` tests pass unchanged after the fake extension (the `required_layer` values match the deleted `_REQUIRED_LAYERS` dict).
- A `HighVoltage` track on `F.Cu` still raises `DRC002` with `required_layer="B.Cu"`.
- A `GateDrive` track on `B.Cu` still raises `DRC002` with `required_layer="F.Cu"`.
- A `Signal` track on any layer produces no issue (`required_layer=None`).
- `_REQUIRED_LAYERS` no longer exists in `layer_assignment.py` (grep confirms).

**Verification:** `uv run pytest packages/temper-drc/tests/checks/drc/test_layer_assignment.py` passes. `grep _REQUIRED_LAYERS packages/temper-drc/temper_drc/checks/drc/layer_assignment.py` returns no matches.

---

### U4. Migrate the three safety checks to `safety_category` with keyword fallback

**Goal:** `HVLVSeparationCheck`, `CreepageCheck`, and `IsolationCheck` read `safety_category` from the resolved `NetClassRules` for each component's net class, with a keyword fallback that emits a loud stderr warning when the fallback fires. The two divergent `ISO_KEYWORDS` lists are consolidated into shared constants.

**Requirements:** R4, R5

**Dependencies:** U1 (`safety_category` must exist on `NetClassRules`)

**Files:**
- `packages/temper-drc/temper_drc/checks/safety/_safety_keywords.py` (new — shared constants + `resolve_safety_category` helper)
- `packages/temper-drc/temper_drc/checks/safety/hv_lv_separation.py` (rewrite lines 34-50)
- `packages/temper-drc/temper_drc/checks/safety/creepage.py` (rewrite lines 31-43)
- `packages/temper-drc/temper_drc/checks/safety/isolation.py` (rewrite lines 30, 43-44)
- `packages/temper-drc/tests/checks/safety/test_hv_lv_separation.py` (extend with real-class cases; assert fallback warning)
- `packages/temper-drc/tests/checks/safety/test_isolation.py` (extend; assert fallback warning)
- `packages/temper-drc/tests/checks/safety/test_creepage.py` (extend; assert fallback warning)

**Approach:**

**Step 1 — shared module `_safety_keywords.py`:**

```python
from __future__ import annotations
import sys
from typing import Literal

ISO_COMPONENT_KEYWORDS: tuple[str, ...] = (
    "iso", "opto", "coupler", "isolator", "transformer", "adum", "dcdc", "mev1",
)
ISO_ZONE_KEYWORDS: tuple[str, ...] = (
    "iso", "opto", "coupler", "transformer", "gutter", "slot",
)
HV_KEYWORDS: tuple[str, ...] = ("hv", "line", "ac", "neutral", "mains")
LV_KEYWORDS: tuple[str, ...] = ("lv", "signal", "3v3", "5v", "gnd", "analog")

SafetyCategory = Literal["HV", "LV", "AC", "iso"]

def _warn_fallback(net_class_str: str, guessed: str) -> None:
    sys.stderr.write(
        f"[temper-drc] safety_category fallback: net_class='{net_class_str}' "
        f"guessed='{guessed}'. Declare safety_category on net class '{net_class_str}' "
        f"or add net to TEMPER_NET_ASSIGNMENTS.\n"
    )

def resolve_safety_category(net_class_str: str) -> str | None:
    """Resolve a net-class string to a safety category, with keyword fallback."""
    from temper_placer.core.design_rules import TEMPER_NET_CLASSES
    rules = TEMPER_NET_CLASSES.get(net_class_str)
    if rules is not None and getattr(rules, "safety_category", None) is not None:
        return rules.safety_category
    # Fallback: keyword scan
    lc = net_class_str.lower()
    if any(k in lc for k in HV_KEYWORDS):
        guessed: str | None = "HV"
    elif any(k in lc for k in LV_KEYWORDS):
        guessed = "LV"
    elif any(k in lc for k in ISO_COMPONENT_KEYWORDS):
        guessed = "iso"
    else:
        return None
    _warn_fallback(net_class_str, guessed)
    return guessed
```

The import of `TEMPER_NET_CLASSES` is local to the function to avoid a circular import at module load (the safety checks are imported by `temper_drc.checks.__init__` which already imports `design_rules` at line 60). `getattr(rules, "safety_category", None)` is defensive so the resolver works even if a test stub omits the field.

**Step 2 — `HVLVSeparationCheck`:**

At `hv_lv_separation.py:34-50`, replace the inline `HV_KEYWORDS`/`LV_KEYWORDS` and substring scan with calls to `resolve_safety_category`:

```python
from temper_drc.checks.safety._safety_keywords import resolve_safety_category

# inside the loop:
a_cat = resolve_safety_category(comp_a.net_class)
b_cat = resolve_safety_category(comp_b.net_class)
is_a_hv = a_cat in ("HV", "AC")
is_b_hv = b_cat in ("HV", "AC")
is_a_lv = a_cat == "LV"
is_b_lv = b_cat == "LV"
if (is_a_hv and is_b_lv) or (is_b_hv and is_a_lv):
    ...
```

`"AC"` is treated as HV-side for separation (preserves current behaviour where `ACMains` matches the `"ac"` keyword and is treated as HV). The `HV_KEYWORDS`/`LV_KEYWORDS` module constants are deleted from this file — they live in `_safety_keywords.py` now.

**Step 3 — `CreepageCheck`:**

At `creepage.py:31-43`, replace the inline `ISO_KEYWORDS` and substring scan:

```python
from temper_drc.checks.safety._safety_keywords import resolve_safety_category, ISO_COMPONENT_KEYWORDS

# inside the loop:
cat = resolve_safety_category(comp.net_class)
is_iso = (cat == "iso") or (
    any(k in comp.net_class.lower() for k in ISO_COMPONENT_KEYWORDS)
    or any(k in comp.footprint.lower() for k in ISO_COMPONENT_KEYWORDS)
)
```

The `resolve_safety_category` call handles the class-name path; the explicit `ISO_COMPONENT_KEYWORDS` footprint scan remains because `safety_category` is a property of the *class*, and the footprint fallback covers components whose net class is not registered (the ADUM1250 case from F2 — footprint `Package_SO:SOIC-8_3.9x4.9mm_P1.27mm` matches no keyword today, so this remains a documented gap closed only when the net is explicitly assigned to an `"iso"` class). The fallback warning fires when `resolve_safety_category` falls back (i.e. when the class string is not registered or has `safety_category=None`).

**Step 4 — `IsolationCheck`:**

At `isolation.py:30, 43-44`, split the keyword usage:
- Zone-name branch (lines 33-36): use `ISO_ZONE_KEYWORDS` from `_safety_keywords.py` (unchanged behaviour, consolidated constant).
- Component-classification branch (lines 43-44): use `resolve_safety_category(comp.net_class) == "iso"` with `ISO_COMPONENT_KEYWORDS` fallback on `comp.net_class` and `comp.footprint`.

```python
from temper_drc.checks.safety._safety_keywords import (
    ISO_ZONE_KEYWORDS, ISO_COMPONENT_KEYWORDS, resolve_safety_category,
)

# 1. Identify Isolation Zones — uses ISO_ZONE_KEYWORDS
iso_zones = [z for z in constraints.zones if any(k in z.name.lower() for k in ISO_ZONE_KEYWORDS)]

# 2. Check each component
for ref, comp in placement.components.items():
    cat = resolve_safety_category(comp.net_class)
    is_iso_device = (cat == "iso") or (
        any(k in comp.net_class.lower() for k in ISO_COMPONENT_KEYWORDS)
        or any(k in comp.footprint.lower() for k in ISO_COMPONENT_KEYWORDS)
    )
    ...
```

**Step 5 — test updates:**

The existing tests use placeholder strings `"HV"`, `"LV"`, `"ISO"` which are not in `TEMPER_NET_CLASSES` and therefore trigger the fallback. Update the tests to:
- Keep the placeholder-string cases and assert the fallback warning is emitted (use `capsys` pytest fixture to capture stderr; assert the warning text contains the net class name and "declare safety_category").
- Add new cases using real class names `"HighVoltage"`, `"ACMains"`, `"Signal"` that resolve via `TEMPER_NET_CLASSES` with no stderr warning (covering F1/F2).

The `_FakeNetClassRules` stubs in `test_layer_assignment.py:17-20` and `test_trace_width.py:21-24` are not in scope for U4 (those tests do not touch the safety checks), but the fake classes used by safety tests are the real `ComponentPlacement` objects with arbitrary `net_class` strings — no fake `NetClassRules` is needed because the resolver reads the real `TEMPER_NET_CLASSES`.

**Patterns to follow:** `packages/temper-drc/temper_drc/checks/safety/` module style. `sys.stderr.write` for warnings (no logging framework in this package — confirmed by grep). `capsys` pytest fixture for stderr assertion.

**Test scenarios:**
- `test_hv_lv_separation_pass`: with `net_class="HighVoltage"` and `net_class="Signal"` (real classes), no stderr warning, separation check uses `safety_category="HV"`/`"LV"` from the model.
- `test_hv_lv_separation_pass_ac_mains`: with `net_class="ACMains"` (`safety_category="AC"`) and `net_class="Signal"` (`safety_category="LV"`) — both real classes, no stderr warning, separation enforced because `"AC"` is treated as HV-side. This covers the `"HV"`/`"AC"` vocabulary-distinction path in `HVLVSeparationCheck` (`is_a_hv = a_cat in ("HV","AC")`).
- `test_hv_lv_separation_pass` (legacy): with `net_class="HV"` and `net_class="LV"` (placeholders), the fallback fires, stderr contains `"declare safety_category"`, and the check still classifies correctly via keyword scan.
- `test_hv_lv_separation_fail`: same assertions on classification; warning emitted for placeholder strings.
- `test_isolation_pass`: `ISO1` with `net_class="ISO"` triggers fallback; `ISO1` with a real `"iso"`-classed net (none today, so use a hypothetical test class added to a test-only `TEMPER_NET_CLASSES` patch, or assert the fallback path) is classified as iso without warning.
- `test_isolation_fail_component_in_slot`: `R_BAD` with `net_class="LV"` triggers fallback warning; non-iso component correctly flagged.
- `test_creepage_fail`: `net_class="ISO"` triggers fallback; component classified as iso via keyword; warning emitted.
- New test: a component with `net_class="HighVoltage"` (real class, `safety_category="HV"`) is NOT classified as iso (no false positive from `ISO_COMPONENT_KEYWORDS`).
- `ISO_KEYWORDS` no longer exists in `creepage.py` or `isolation.py` (grep confirms); `ISO_COMPONENT_KEYWORDS` and `ISO_ZONE_KEYWORDS` exist in `_safety_keywords.py`.
- `HV_KEYWORDS`/`LV_KEYWORDS` no longer exist in `hv_lv_separation.py` (grep confirms).

**Verification:** `uv run pytest packages/temper-drc/tests/checks/safety/` passes. `grep -r "HV_KEYWORDS\|LV_KEYWORDS\|ISO_KEYWORDS" packages/temper-drc/temper_drc/checks/safety/` returns no matches (only the new shared constants in `_safety_keywords.py`).

---

### U5. Update integration tests and documentation

**Goal:** Update the cross-package integration test and the developer documentation to reflect the new field requirements and the fallback warning convention.

**Requirements:** R6, R7

**Dependencies:** U1, U2, U3, U4

**Files:**
- `tests/deterministic/test_pipeline_integration.py` (update if it asserts on DRU output or safety-check classification counts)
- `CLAUDE.md` or `AGENT_INSTRUCTIONS.md` (document the three new fields, the `dru_priority` ordering rule, the keyword-fallback warning convention, and the `HighCurrent` reclassification)

**Approach:**

Audit `tests/deterministic/test_pipeline_integration.py` per origin Open Question [Affects R6] for any assertion that reads `class_order`, `_REQUIRED_LAYERS`, or the keyword lists directly. Update those assertions to read from `TEMPER_NET_CLASSES[k].dru_priority` / `.required_layer` / `.safety_category`. If the test only consumes the generated DRU text or `CheckResult` objects, no change is needed — the behaviour is preserved.

Document in `CLAUDE.md` (preferred per the companion N2 plan's convention) or `AGENT_INSTRUCTIONS.md`:
- Every `NetClassRules` instance in `TEMPER_NET_CLASSES` must set `dru_priority` (required) and should set `safety_category` if the class is safety-relevant.
- DRU emission order is `sorted(keys, key=lambda k: (dru_priority, k))` — do not edit `generate_kicad_dru.py` to add a new class.
- Layer constraints are set via `required_layer` on the model — do not add to a separate dict.
- The keyword fallback in safety checks emits a stderr warning; a silent CI log means all nets are declared. Promoting the warning to a hard error is a future decision.
- `HighCurrent` was reclassified from "neither HV nor LV" to `"HV"` in this changeset — a behaviour change called out for regression review.

**Patterns to follow:** The N2 plan's `CLAUDE.md` documentation convention (origin Key Technical Decisions "Documentation sync").

**Test scenarios:**
- `uv run pytest tests/deterministic/test_pipeline_integration.py` passes.
- `CLAUDE.md` (or `AGENT_INSTRUCTIONS.md`) contains a section naming the three fields and the fallback warning convention.

**Verification:** Full CI run (`uv run pytest tests/ -v` in each package) passes. `grep dru_priority CLAUDE.md` returns a match.

---

## System-Wide Impact

- **`packages/temper-placer/temper_placer/core/design_rules.py`:** `NetClassRules` gains three fields (after U4 made it a Pydantic `BaseModel`). The 9 `TEMPER_NET_CLASSES` entries gain three constructor arguments each. No other change in this module. The `TEMPER_NET_ASSIGNMENTS` dict at lines 563-575 is unchanged.
- **`scripts/generate_kicad_dru.py`:** The `class_order` list (lines 229-239) and its drift `assert` (lines 240-243) are deleted and replaced with a 3-line derived sort. The `pcb/temper.kicad_dru` output is byte-for-byte identical (Assumption A2).
- **`packages/temper-drc/temper_drc/checks/drc/layer_assignment.py`:** The `_REQUIRED_LAYERS` dict (lines 13-16) is deleted. Line 118 reads `required_layer` off the resolved `NetClassRules`. The substring-heuristic fallback at lines 113-116 is unchanged (deferred).
- **`packages/temper-drc/temper_drc/checks/safety/hv_lv_separation.py`:** The inline `HV_KEYWORDS`/`LV_KEYWORDS` (lines 34-35) are deleted; the substring scan (lines 44-50) is replaced with `resolve_safety_category` calls.
- **`packages/temper-drc/temper_drc/checks/safety/creepage.py`:** The inline `ISO_KEYWORDS` (lines 31-34) is deleted; the scan (lines 40-43) is replaced with `resolve_safety_category` + `ISO_COMPONENT_KEYWORDS` footprint fallback.
- **`packages/temper-drc/temper_drc/checks/safety/isolation.py`:** The inline `ISO_KEYWORDS` (line 30) is deleted; the zone branch uses `ISO_ZONE_KEYWORDS`, the component branch uses `resolve_safety_category` + `ISO_COMPONENT_KEYWORDS` footprint fallback.
- **`packages/temper-drc/temper_drc/checks/safety/_safety_keywords.py`:** New file with the four keyword constants and the `resolve_safety_category` helper.
- **Tests:** `test_design_rules.py`, `test_layer_assignment.py`, `test_hv_lv_separation.py`, `test_isolation.py`, `test_creepage.py`, and possibly `test_pipeline_integration.py` are updated. The `_FakeNetClassRules` stubs in `test_layer_assignment.py:17-20` and `test_trace_width.py:21-24` gain a `required_layer` attribute (the `test_trace_width.py` fake is not strictly required to change since `TraceWidthCheck` does not read `required_layer`, but adding the attribute keeps the fake structurally compatible with the migrated model — implementation-time decision).
- **CI pipeline:** No new CI job. `.github/workflows/python-tests.yml` `paths:` filter (lines 6-9, 12-15) already includes `packages/**`; `scripts/**` is NOT included, so editing `generate_kicad_dru.py` alone does not trigger CI — but this changeset edits `packages/**` files too, so CI runs. Consider adding `'scripts/**'` to the `paths:` filter as a follow-up (the N2 plan already recommends this for its reconciliation test).
- **`CLAUDE.md` / `AGENT_INSTRUCTIONS.md`:** Documents the three new fields, the `dru_priority` ordering rule, the keyword-fallback warning convention, and the `HighCurrent` reclassification.
- **Developer workflow:** A developer adding a new net class edits `TEMPER_NET_CLASSES` with `dru_priority`, `required_layer`, and `safety_category` set — and gets correct DRU ordering, layer enforcement, and safety classification with zero edits to any other file (the success criterion). A developer who typos `safety_category="Iso"` sees a `ValidationError` at `import temper_placer.core.design_rules`, not a silent mis-classification at DRC run time.

---

## Risk Analysis & Mitigation

| Risk | Severity | Likelihood | Mitigation |
|------|----------|------------|------------|
| Parent plan U4 (Pydantic migration) has not landed; N4 cannot apply `Literal` validation | High | Medium | N4 is gated on U4. If U4 is delayed, N4 is blocked — do not fall back to the `@dataclass` + `__post_init__` path (loses the `model_dump()` consumer story and the parent plan's `iec_reference` validator). Confirm U4 has landed before starting N4. |
| `HighCurrent.safety_category="HV"` reclassification changes safety-check output on existing boards | Medium | High | The reclassification is called out in the changeset description and the `CLAUDE.md` entry. Run the full `temper-drc` test suite and the `test_pipeline_integration.py` against the current board; any new HV/LV separation issues from `HighCurrent`-classed components are the intended signal (a latent bug surfacing). If EE review disagrees, set `safety_category=None` instead — the plan default is `"HV"`. |
| Safety-check test fixtures use placeholder strings (`"HV"`, `"LV"`, `"ISO"`) that trigger the fallback; tests may fail on stderr-warning assertions if `capsys` is not wired | Low | High | U4 Step 5 explicitly adds `capsys`-based stderr assertions and keeps the placeholder-string cases. The fallback warning is not a failure — the test asserts the warning is *emitted*, not that the check fails. |
| `resolve_safety_category` import of `TEMPER_NET_CLASSES` inside the function creates a circular import or performance hit | Low | Low | The import is local to the function body, executed only on check runs (not at module load). `design_rules` is already imported by `temper_drc.checks.__init__` at line 60, so the module is cached in `sys.modules` — the local import is a dict lookup, effectively free. |
| The footprint-based `ISO_COMPONENT_KEYWORDS` fallback in `CreepageCheck`/`IsolationCheck` still misses the ADUM1250 (footprint `Package_SO:SOIC-8_3.9x4.9mm_P1.27mm` matches no keyword) | Low | Medium | This is the known Phase 5 gap documented in the origin (F2). N4 closes the gap *for declared nets* (a net assigned to an `"iso"` class classifies correctly via `resolve_safety_category`); the footprint fallback remains for undeclared components. Closing the footprint gap fully is the Phase 5 plan's `isolation_barrier` attribute work, out of N4 scope. |
| A new net class added to `TEMPER_NET_CLASSES` without `safety_category` silently bypasses safety classification | Low | Medium | `safety_category` defaults to `None` (a class that is not safety-classified is the common case). A developer who intends a class to be safety-classified and forgets the field gets no error — but the keyword fallback fires with a stderr warning when a component on that class is checked, making the omission visible. Document in `CLAUDE.md` that safety-relevant classes must set `safety_category`. |
| `dru_priority` tie-breaking by lexicographic class name shifts DRU output if two classes are assigned the same priority | Low | Low | No ties exist in the initial population (10, 20, …, 90 are distinct). If a future addition creates a tie, the lexicographic break is deterministic and documented; the N2 reconciliation test / companion plan U6 golden-file diff catches any unexpected shift. |
| `pcb/temper.kicad_dru` golden-file diff is non-empty despite Assumption A2 | Low | Low | Verify with `git diff pcb/temper.kicad_dru` after U2. If non-empty, the `dru_priority` assignments are wrong — fix before landing. The diff must be empty; a non-empty diff is a U1/U2 bug, not an Assumption A2 failure. |
| `tests/deterministic/test_pipeline_integration.py` reads `class_order` or `_REQUIRED_LAYERS` directly and breaks | Medium | Medium | U5 audits the test per origin Open Question [Affects R6]. The consumer-audit grep identified this test as a candidate; confirm at implementation time and update assertions. |

---

## Test Strategy

- **U1 (model fields):** Unit tests in `packages/temper-placer/tests/core/test_design_rules.py` asserting the 9-entry population, the `Literal` validation (typo raises `ValidationError`), the required-`dru_priority` validation (missing field raises `ValidationError`), and the unchanged `TEMPER_NET_ASSIGNMENTS` invariant.
- **U2 (DRU ordering):** Byte-for-byte diff of `pcb/temper.kicad_dru` before and after. `test_pipeline_integration.py` passes. A new test asserting `class_order` is derived (add a `dru_priority=15` class, confirm it emits in the right position) is optional but recommended.
- **U3 (layer assignment):** Existing `test_layer_assignment.py` passes after the `_FakeNetClassRules` extension. No new test file — the existing cases cover the behaviour, and the `required_layer` values are identical to the deleted `_REQUIRED_LAYERS` dict.
- **U4 (safety checks):** Existing `test_hv_lv_separation.py`, `test_isolation.py`, `test_creepage.py` extended with: (a) `capsys`-based stderr-warning assertions for the placeholder-string fallback cases, (b) new cases using real class names (`"HighVoltage"`, `"ACMains"`, `"Signal"`) that resolve via `TEMPER_NET_CLASSES` with no warning. The `_safety_keywords.py` helper is exercised through the check tests — no separate unit test file (it is a pure function with three branches, covered by the check tests).
- **U5 (integration + docs):** `test_pipeline_integration.py` passes. `CLAUDE.md` grep confirms documentation.
- **CI integration:** No new CI job. All changes run in the existing `Run temper-placer tests (core only)` and `Run temper-drc tests` steps (`.github/workflows/python-tests.yml:36-50`). The `paths:` filter already includes `packages/**`; the `scripts/**` edit in U2 is covered by the `packages/**` edits in U1/U3/U4.
- **Regression:** The existing `packages/temper-placer/tests/core/` and `packages/temper-drc/tests/` suites continue to pass. The only modified existing tests are the safety-check tests (U4) and `test_layer_assignment.py` (U3 fake extension); both preserve their original assertions and add new ones.

---

## Deferred to Implementation

- **Parent plan U4 landing status.** Confirm U4 (`NetClassRules` Pydantic migration) and U2 (module-scope `TEMPER_NET_ASSIGNMENTS`-keys-in-`TEMPER_NET_CLASSES` assert) have landed on `main` before starting N4. N4 is blocked without U4.
- **`HighCurrent.safety_category` EE sign-off.** The plan default is `"HV"` (latent-bug fix). Confirm with an EE during implementation review; if disputed, fall back to `None` (preserving current behaviour) and record the decision in the changeset description.
- **`"AC"` vs `"HV"` vocabulary EE confirmation.** The plan keeps `"AC"` distinct (origin Open Question [Affects R1]). Confirm with an EE that the distinction is useful for future AC↔LV-specific separation rules; if not, merge `"AC"` into `"HV"` and simplify the `HVLVSeparationCheck` `is_a_hv = a_cat in ("HV","AC")` to `is_a_hv = a_cat == "HV"`.
- **`_FakeNetClassRules` in `test_trace_width.py`.** The fake at `test_trace_width.py:21-24` does not strictly need `required_layer`/`safety_category`/`dru_priority` (the `TraceWidthCheck` does not read them), but adding the attributes keeps the fake structurally compatible with the migrated model. Implementation-time decision — prefer adding them for symmetry.
- **`test_pipeline_integration.py` audit.** Per origin Open Question [Affects R6]: confirm at implementation time whether this test reads `class_order`, `_REQUIRED_LAYERS`, or the keyword lists directly. The consumer-audit grep in the origin identified it as a candidate; the actual assertion shape determines whether U5 needs to touch it.
- **`CLAUDE.md` vs `AGENT_INSTRUCTIONS.md`.** Confirm which file exists and is the project convention. The N2 companion plan references `CLAUDE.md`; prefer it if present.
- **`sys.stderr` vs `logging` for the fallback warning.** The `temper-drc` package has no logging framework (confirmed by grep — no `import logging` in `checks/safety/`). `sys.stderr.write` is the chosen mechanism for grep-visibility. If a logging framework is introduced later, the warning is migrated in that changeset.
- **`scripts/**` CI `paths:` filter.** The N2 plan already recommends adding `'scripts/**'` to `.github/workflows/python-tests.yml` `paths:` so `generate_kicad_dru.py` edits trigger CI. N4 does not duplicate this; coordinate with N2's landing.
- **Warn-to-error promotion.** Per origin Open Question [Affects R4]: keep the fallback warn-only for now; revisit after one routing session to see how often it fires. A warn-only fallback that never fires is equivalent to a hard error with better ergonomics. Promoting to a hard CI failure is a separate changeset.
