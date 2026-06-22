---
date: 2026-06-21
topic: net-class-rules-fields
depends_on: 2026-06-21-source-of-truth-validation-requirements (R4 / U4)
---

# NetClassRules Field Extension: dru_priority + required_layer + safety_category

## Summary

A focused model extension that adds three fields to `NetClassRules` — `dru_priority: int`, `required_layer: str | None`, and `safety_category: Literal["HV","LV","AC","iso"] | None` — and collapses five hand-maintained registries that currently duplicate information already derivable from the net class definitions. One change to the model in `packages/temper-placer/temper_placer/core/design_rules.py:94` retires: the `class_order` list and its drift-catching `assert` at `scripts/generate_kicad_dru.py:229-243`; the `_REQUIRED_LAYERS` dict at `packages/temper-drc/temper_drc/checks/drc/layer_assignment.py:13`; the `HV_KEYWORDS`/`LV_KEYWORDS` substring scan at `packages/temper-drc/temper_drc/checks/safety/hv_lv_separation.py:34-35`; and the two divergent `ISO_KEYWORDS` lists at `packages/temper-drc/temper_drc/checks/safety/creepage.py:31` and `packages/temper-drc/temper_drc/checks/safety/isolation.py:30`.

This brainstorm is **Standard scope**, builds on idea #1 (Pydantic migration of `NetClassRules`, R4/U4 in the source-of-truth-validation plan), and assumes that migration has landed. The keyword scanners become a loud-warning fallback rather than the primary classifier; `TEMPER_NET_ASSIGNMENTS` remains the authoritative net→class map and is not subsumed.

---

## Problem Frame

Today, four pieces of information about each net class live outside `NetClassRules` in hand-maintained registries that must be kept in sync by the developer:

1. **DRU emission order.** `scripts/generate_kicad_dru.py:229-239` hardcodes a 9-element `class_order` list. A drift `assert` at line 240 catches additions/removals but not reordering, and the list must be edited by hand whenever a class is added. The `assert` exists precisely because this list drifted silently during the June 2026 sprint.
2. **Layer constraints.** `packages/temper-drc/temper_drc/checks/drc/layer_assignment.py:13` defines `_REQUIRED_LAYERS = {"HighVoltage": "B.Cu", "GateDrive": "F.Cu"}`. The only consumer is 30 lines below in the same file. There is no structural link from `NetClassRules("HighVoltage")` to the fact that it must route on `B.Cu`.
3. **HV/LV safety classification.** `packages/temper-drc/temper_drc/checks/safety/hv_lv_separation.py:34-35` scans `comp.net_class.lower()` for the substrings `["hv","line","ac","neutral","mains"]` and `["lv","signal","3v3","5v","gnd","analog"]`. This duplicates `TEMPER_NET_ASSIGNMENTS` (`design_rules.py:563-575`): a net assigned to `ACMains` is HV by declaration, not by substring. The substring scan also mis-classifies — e.g. `HighVoltage` contains `"hv"` but `ACMains` contains neither `"hv"` nor `"line"` yet is HV. `"ac"` matches `ACMains` but also matches any future `DAC` class.
4. **Isolation classification.** `ISO_KEYWORDS` is duplicated in two checks with **divergent lists**: `creepage.py:31` uses `["iso","opto","coupler","isolator","transformer","adum","dcdc","mev1"]` while `isolation.py:30` uses `["iso","opto","coupler","transformer","gutter","slot"]`. The first list classifies components; the second classifies both components and zone names (hence `gutter`,`slot`). The worktree copy at `.claude/worktrees/agent-ac3b6b1a386e1bf71/packages/temper-drc/src/temper_drc/checks/safety/creepage.py:41` even contains a typo (`"isoloator"`) — the exact class of silent rot this initiative exists to prevent.

Each registry is small and each looks harmless in isolation. The failure mode is the same as the broader source-of-truth problem: a constraint exists in `NetClassRules` (or in `TEMPER_NET_ASSIGNMENTS`) and is re-derived by substring heuristics elsewhere, with no machine-enforced link. Adding a new safety-relevant net class today requires editing `NetClassRules`, `TEMPER_NET_ASSIGNMENTS`, `_REQUIRED_LAYERS`, possibly `class_order`, and hoping the keyword scanners happen to match the new name.

---

## Actors

- A1. **Developer** — adds or reclassifies a net class (e.g. a new `SELV` class for user-accessible low-voltage). Today must coordinate 5 registries; after this change, edits one model field.
- A2. **CI pipeline** — runs the existing assert at `generate_kicad_dru.py:240` (retained as a backstop), the new field validators, and the safety-check tests. Enforcement layer.
- A3. **Safety checks** (`HVLVSeparationCheck`, `CreepageCheck`, `IsolationCheck`, `LayerAssignmentCheck`) — consumers that today read the four registries; after migration, read typed attributes off `NetClassRules`.

---

## Key Flows

- F1. **Developer adds a new HV net class**
  - **Trigger:** A1 adds a `SELV` class to `TEMPER_NET_CLASSES` that must be separated from `HighVoltage`.
  - **Actors:** A1, A2
  - **Steps:** (1) A1 adds `NetClassRules(name="SELV", ..., safety_category="LV", required_layer=None, dru_priority=40)`. (2) Pydantic validates the `safety_category` literal at construction — a typo like `"LowV"` raises `ValidationError` at import. (3) `HVLVSeparationCheck` reads `safety_category` from the rule and applies HV↔LV separation automatically — no keyword list edit. (4) `generate_kicad_dru.py` emits the trace-width rule in `dru_priority` order — no `class_order` edit. (5) The existing `assert set(class_order) == set(TEMPER_NET_CLASSES.keys())` either passes (if `class_order` is regenerated from `dru_priority`) or is removed.
  - **Outcome:** One model edit produces correct DRU ordering, correct layer enforcement (if `required_layer` set), and correct HV/LV safety classification. No second registry to forget.
  - **Covered by:** R1, R2, R3

- F2. **Developer classifies an isolation component**
  - **Trigger:** A1 adds an `ADUM1250` I2C isolator whose footprint `Package_SO:SOIC-8_3.9x4.9mm_P1.27mm` matches no `ISO_KEYWORD` (a known gap documented in the Phase 5 plan).
  - **Actors:** A1, A3
  - **Steps:** (1) The isolator's net is assigned to a class with `safety_category="iso"` via `TEMPER_NET_ASSIGNMENTS`. (2) `CreepageCheck` reads `safety_category` off the resolved `NetClassRules` for the component's net and classifies it as isolation — no footprint substring match needed. (3) `IsolationCheck` does the same for the component-classification branch; its zone-name classification branch continues to use a (now shared) keyword list, because zones are not net classes. (4) The component's footprint no longer matters for classification.
  - **Outcome:** The ADUM1250 is correctly identified as an isolation device without footprint keyword matching. The known Phase 5 gap (footprint-based miss) is closed for any component whose net is explicitly assigned.
  - **Covered by:** R3, R4

- F3. **Keyword fallback fires for an undeclared net**
  - **Trigger:** A net appears on the board that is not in `TEMPER_NET_ASSIGNMENTS` and whose class has `safety_category=None`.
  - **Actors:** A3, A1
  - **Steps:** (1) A safety check falls back to the keyword scanner. (2) The scanner emits a **loud warning to stderr** naming the net, the guessed category, and the instruction to declare it. (3) The check proceeds with the guessed category (fail-open for routing) but the warning is visible in CI logs. (4) A1 adds the net to `TEMPER_NET_ASSIGNMENTS` or sets `safety_category` on its class; the warning goes silent.
  - **Outcome:** Undeclared nets are visible, not silent. The fallback exists to preserve routing throughput during development; it never silently mis-classifies a declared net.
  - **Covered by:** R4

---

## Requirements

**Phase A — Model extension (assumes R4/U4 Pydantic migration has landed)**

- R1. `NetClassRules` gains three fields with these exact names and semantics:
  - `dru_priority: int` — non-negative integer; lower emits earlier in the DRU trace-width section. Replaces the hand-maintained `class_order` list at `scripts/generate_kicad_dru.py:229-239`. Distinct values are not required (ties broken by class name lexicographic order, documented in the generator).
  - `required_layer: str | None = None` — a KiCad layer name (`"F.Cu"`, `"B.Cu"`, `"In1.Cu"`, ...) or `None` for "no constraint". Replaces `_REQUIRED_LAYERS` at `packages/temper-drc/temper_drc/checks/drc/layer_assignment.py:13`.
  - `safety_category: Literal["HV","LV","AC","iso"] | None = None` — the safety domain the class belongs to, or `None` for "not safety-classified". `Literal` is chosen over a free string so a typo (`"Iso"`, `"hv"`) is a `ValidationError` at construction; chosen over an `enum.Enum` to keep `NetClassRules` serialization plain (the source-of-truth plan uses Pydantic v2 with `model_dump()` consumers). Replaces the `HV_KEYWORDS`/`LV_KEYWORDS` substring classification at `hv_lv_separation.py:34-50` for declared classes.
- R2. The `assert set(class_order) == set(TEMPER_NET_CLASSES.keys())` at `scripts/generate_kicad_dru.py:240` is replaced by `class_order = sorted(TEMPER_NET_CLASSES.keys(), key=lambda k: (TEMPER_NET_CLASSES[k].dru_priority, k))`. A module-scope assertion that all `dru_priority` values are unique-or-tied (no `None`) is retained as a backstop; the drift assert on key set is retired because the list is now derived. The DRU golden-file diff (R6 of the parent initiative) catches any emission-order regression.
- R3. `LayerAssignmentCheck` at `packages/temper-drc/temper_drc/checks/drc/layer_assignment.py:118` reads `required_layer` from the resolved `NetClassRules` instead of `_REQUIRED_LAYERS.get(cls)`. The module-level `_REQUIRED_LAYERS` dict is deleted. The `cls = TEMPER_NET_ASSIGNMENTS.get(net)` lookup at line 110 is unchanged — `TEMPER_NET_ASSIGNMENTS` remains the authoritative net→class map; only the class→layer step is repointed at the model.
- R4. The three safety checks are updated to read `safety_category` from the resolved `NetClassRules` for each component's net class, **with a keyword fallback**:
  - `HVLVSeparationCheck` (`hv_lv_separation.py`): a class with `safety_category="HV"` or `"AC"` is HV; `"LV"` is LV. The `HV_KEYWORDS`/`LV_KEYWORDS` lists become a fallback used **only** when a component's net class has `safety_category=None`. When the fallback fires, the check writes a **loud warning to stderr** naming the net, the guessed category, and the message `"declare safety_category on net class '<name>' or add net to TEMPER_NET_ASSIGNMENTS"`. The warning is not a CI failure (fail-open for routing) but is grep-visible.
  - `CreepageCheck` (`creepage.py`): a component is isolation if its resolved `NetClassRules.safety_category == "iso"`. Fallback to `ISO_KEYWORDS` on `comp.net_class` and `comp.footprint` with the same loud-warning behaviour.
  - `IsolationCheck` (`isolation.py`): the **component-classification branch** uses `safety_category == "iso"` with keyword fallback. The **zone-name classification branch** (identifying isolation zones by `zone.name`) is **not collapsed** — zones are not net classes and do not carry a `safety_category`. `IsolationCheck` retains a single `ISO_ZONE_KEYWORDS` list for zone names; this list is shared with `CreepageCheck`'s fallback to retire the divergence.
- R5. `TEMPER_NET_ASSIGNMENTS` (`design_rules.py:563-575`) **remains authoritative** for net→class mapping. `safety_category` does **not** subsume it: `safety_category` is a property of a *class*, `TEMPER_NET_ASSIGNMENTS` is the map from *net* to *class`. The two compose. The existing assertion (planned in U2 of the parent initiative) that every value in `TEMPER_NET_ASSIGNMENTS` is a key in `TEMPER_NET_CLASSES` is retained.

**Phase B — Consumer migration (single coordinated changeset)**

- R6. All five registries are migrated in one changeset, not phased. The intermediate state (some consumers reading the field, others reading the legacy registry) is broken because the legacy registries are deleted in the same change. The migration order within the changeset is: (1) add fields with defaults to `NetClassRules`, (2) populate the 9 existing `TEMPER_NET_CLASSES` entries with `dru_priority`/`required_layer`/`safety_category` values that reproduce current behaviour exactly, (3) update `generate_kicad_dru.py`, (4) update `layer_assignment.py`, (5) update the three safety checks + share `ISO_ZONE_KEYWORDS`, (6) delete the four legacy registries, (7) update tests.
- R7. The migration is behaviour-preserving: the DRU output byte-for-byte identical (or, if ordering shifts because `dru_priority` ties break lexicographically and the old `class_order` was not lexicographic, the golden-file is regenerated once with a documented diff), `LayerAssignmentCheck` produces the same issues on the same board, and the safety checks produce the same HV/LV and iso classifications for all currently-declared nets. Any net currently classified by keyword that is **not** in `TEMPER_NET_ASSIGNMENTS` becomes a loud-warning case — these are enumerated in the changeset description.

---

## Success Criteria

- Adding a new net class to `TEMPER_NET_CLASSES` with `safety_category` and `required_layer` set produces correct DRU ordering, correct layer enforcement, and correct HV/LV/iso classification **with zero edits to any other file**.
- The `class_order` list and its drift `assert` no longer exist in `scripts/generate_kicad_dru.py`; the emission order is derivable from the model.
- `_REQUIRED_LAYERS` no longer exists in `layer_assignment.py`; the layer constraint is read off `NetClassRules.required_layer`.
- `HV_KEYWORDS` and `LV_KEYWORDS` no longer exist as primary classifiers in `hv_lv_separation.py`; they survive only as a named fallback constant with a stderr warning on use.
- The two divergent `ISO_KEYWORDS` lists in `creepage.py` and `isolation.py` are consolidated; `IsolationCheck`'s zone-name branch uses a single shared `ISO_ZONE_KEYWORDS` constant.
- A typo in `safety_category` (e.g. `"Iso"`, `"hv"`) is a `ValidationError` at `import temper_placer.core.design_rules`, not a silent mis-classification at DRC run time.
- The ADUM1250 isolator (footprint with no keyword match) is correctly classified as isolation when its net is assigned to a class with `safety_category="iso"` — the known Phase 5 footprint-miss gap is closed for declared nets.

---

## Scope Boundaries

- **Pydantic migration of `NetClassRules` itself** (dataclass → BaseModel) is **out of scope** — it is R4/U4 in the parent `2026-06-21-source-of-truth-validation-requirements.md` initiative. This brainstorm assumes it has landed. If it has not, the field extension can still be applied to the dataclass form (`Literal` validation via `typing.get_args` in a `__post_init__`), but that is a fallback path, not the recommended one.
- **`TEMPER_NET_ASSIGNMENTS` removal** is out of scope. The net→class map is orthogonal to class properties and remains the authoritative declaration of which net belongs to which class.
- **Zone classification** — `IsolationCheck`'s branch that identifies isolation *zones* by name continues to use keywords; zones are not net classes and do not carry `safety_category`. Only the component-classification branch is collapsed.
- **Failing CI on undeclared nets** — the keyword fallback is fail-open with a stderr warning, not a CI failure. Making undeclared nets a hard CI error is a separate decision (see Open Questions) and is deferred.
- **Component-level `isolation_barrier` attribute** (the Phase 5 plan's option (b) for the ADUM1250 gap) is not required here; `safety_category="iso"` on the net class is the chosen mechanism. The two are compatible if both are later adopted.
- **Reordering existing net classes** — `dru_priority` values are assigned to reproduce the current `class_order` (10, 20, 30, ...). Changing the order is a separate decision and out of scope.

---

## Assumptions

- **A1. R4/U4 has landed.** `NetClassRules` is already a Pydantic v2 `BaseModel` with `model_config = ConfigDict(frozen=True)` per the parent plan's U4. This brainstorm adds three fields to that model. If U4 has not landed, the field extension is still possible on the dataclass but loses the `Literal` validation (requires a manual `__post_init__` check); the recommended sequencing is U4 first, then this.
- **A2. `dru_priority` values reproduce current order.** The existing `class_order` is `["ACMains","HighVoltage","FinePitch","Power","GateDrive","GND","HighSpeed","Signal","HighCurrent"]`. Assigned priorities are `10,20,30,40,50,60,70,80,90` respectively. Ties (none currently) break by lexicographic class name. This reproduces the current DRU byte-for-byte.
- **A3. `required_layer` values reproduce current `_REQUIRED_LAYERS`.** `HighVoltage` → `"B.Cu"`, `GateDrive` → `"F.Cu"`, all others → `None`.
- **A4. `safety_category` assignments reproduce current keyword behaviour for declared classes.** `ACMains` → `"AC"` (currently matched by `"ac"` keyword), `HighVoltage` → `"HV"` (matched by `"hv"`), `Power`/`GateDrive`/`GND`/`Signal`/`HighSpeed`/`FinePitch` → `"LV"` (currently matched by `"signal"`/`"gnd"`/etc.), `HighCurrent` → `"HV"` (currently matched by... none of the HV keywords — this is a latent mis-classification; see Open Questions). No current class maps to `"iso"`; isolation is currently inferred per-component by footprint, not by class. After migration, any class that should classify as iso is declared so.
- **A5. The keyword fallback warns, does not fail.** A net not in `TEMPER_NET_ASSIGNMENTS` whose class has `safety_category=None` triggers a stderr warning from the safety check but does not fail CI. This preserves current routing throughput; making it a hard error is deferred (Open Questions).
- **A6. `IsolationCheck`'s zone branch keeps keywords.** Zones are named in the constraints input, not derived from net classes; no `safety_category` applies. The two `ISO_KEYWORDS` lists are consolidated into one `ISO_ZONE_KEYWORDS` shared constant.
- **A7. The golden-file DRU diff (R6 of parent) absorbs the one-time regeneration.** If `dru_priority` tie-breaking shifts any line, the committed `pcb/temper.kicad_dru` is regenerated and the diff is documented in the changeset. This is not a regression.

---

## Open Questions

### Resolve Before Planning

- **[Affects R4/A4]** `HighCurrent` is currently matched by **none** of `HV_KEYWORDS` (`["hv","line","ac","neutral","mains"]`) — `HVLVSeparationCheck` today treats it as neither HV nor LV. Should `HighCurrent.safety_category` be `"HV"` (it carries SW_NODE/DC_BUS currents at 400V) or `None` (preserving current behaviour)? **Recommendation:** `"HV"` — this is a latent safety bug and the migration is the right moment to fix it, but it changes behaviour and must be called out in the changeset.
- **[Affects R4]** Should the keyword fallback's stderr warning be promoted to a CI failure once a deprecation period has elapsed? **Recommendation:** keep it warn-only for now; revisit after one routing session to see how often it fires. A warn-only fallback that never fires is equivalent to a hard error with better ergonomics.
- **[Affects R1]** Is `Literal["HV","LV","AC","iso"]` the right vocabulary, or should `"AC"` be merged into `"HV"` (AC mains is high-voltage by any safety standard)? The current `HV_KEYWORDS` list treats `"ac"` as HV. **Recommendation:** keep `"AC"` distinct — it composes with the IEC 60335-1 mains-specific clearance (6.0mm in `ACMains`) versus the IEC 60664-1 DC clearance (2.0mm in `HighVoltage`), and the separation check may want to treat AC↔LV differently from HV↔LV. Confirm with an EE during planning.

### Deferred to Planning

- **[Affects R6]** Full consumer audit — the grep in this brainstorm identified `generate_kicad_dru.py`, `layer_assignment.py`, `trace_width.py`, `hv_lv_separation.py`, `creepage.py`, `isolation.py`, plus tests in `packages/temper-placer/tests/core/test_design_rules.py`, `packages/temper-drc/tests/checks/drc/test_layer_assignment.py`, `packages/temper-drc/tests/checks/drc/test_trace_width.py`, and `tests/deterministic/test_pipeline_integration.py`. Confirm no other consumer reads `class_order`, `_REQUIRED_LAYERS`, or the keyword lists before the coordinated changeset.
- **[Affects R1]** Should `dru_priority` be a required field (no default) or default to a large value (e.g. `1000`) so a new class without a priority lands at the end of the DRU rather than failing construction? **Recommendation:** required, no default — a new class without a priority is a developer error and the `ValidationError` is the desired signal. Confirm during planning.
- **[Affects R3]** `LayerAssignmentCheck`'s substring-heuristic fallback at `layer_assignment.py:113-116` (matching `r.name.lower() in net.lower()`) is separate from `_REQUIRED_LAYERS` and is not collapsed by this change. Should it be retired in favour of requiring every layer-constrained net to be in `TEMPER_NET_ASSIGNMENTS`? Deferred — it is a net-classification concern, not a layer-constraint concern.
