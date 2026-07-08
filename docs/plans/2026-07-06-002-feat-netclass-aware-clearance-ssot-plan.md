---
title: "feat: Netclass-aware clearance SSOT — placement + routing + derived output PCB"
type: feat
status: active
date: 2026-07-06
origin: docs/brainstorms/2026-07-06-netclass-aware-clearance-ssot-requirements.md
---

# feat: Netclass-Aware Clearance — Single Source of Truth + Place/Route Enforcement + Per-Layer Experiment

## Summary

Add `netclass_rules.yaml` as the sole editable surface for per-class-pair clearance values; consume it through the existing `DesignRules` / `NetClassRules` infrastructure in both CP-SAT (auto-generated SEPARATED constraints) and router_v6 (per-net channel-width rules); write the same values as `(net_class ...)` forms into the output `.kicad_pcb` via the existing `_apply_placements_to_pcb` text-transformation path; verify the F3 feedback handler uses YAML-derived `required_mm` instead of hardcoded default; measure the 121→≤29 baseline gap closure per layer (placement-only / +routing / +feedback) as the decisive experiment.

---

## Problem Frame

The umbrella-final-report's headline open item: CP-SAT placement produces 121 DRC errors vs the 29-violation human baseline. Verified root cause: the temper PCB has **zero `(net_class ...)` definitions** in it (no matches in `power_pcb_dataset/corpus/temper/temper.kicad_pcb`); kicad-cli DRC runs at KiCad's default ~0.1524mm clearance, not at the 6mm ACMains-to-signal rule the board *should* have. The manufacturing-relevant rules are missing from the board — and per the brainstorm's SSOT decision, the fix is for the placer to *derive* those rules from a YAML authority and write them into the generated output PCB as `(net_class ...)` forms, so the truth gate checks at the same values the preventive layers enforced.

Three pieces of infrastructure verified to already exist in the codebase (resolved Deferred-to-Planning technical questions during planning):

1. **`core/design_rules.py:96` defines `NetClassRules` and `DesignRules` with `net_classes: dict[str, NetClassRules]` and `get_rules_for_net(net_name, net_class=None)`** — the per-netclass rules infrastructure is built. Router_v6's `constraint_model.py:401` already consumes `rule.trace_width_mm + rule.clearance_mm` from `design_rules.get_rules_for_net(net.name)`. The workstream loads `netclass_rules.yaml` into a `DesignRules` instance and feeds it through this existing path; no new router_v6 architecture per the brainstorm's Scope Boundaries.
2. **KiCad `(net_class ...)` syntax verified** against `packages/temper-validation/data/reference_layouts/complex/ESP32-POE_ESP32-PoE_Rev_K.kicad_pcb`: `(net_class Default "..." (clearance 0.1524) (trace_width 0.1524) (via_dia 0.7) (via_drill 0.4) ...)`. The output-PCB write step emits these forms by string interpolation after `_apply_placements_to_pcb`.
3. **`router_v6/adapter.py:402` `_apply_placements_to_pcb(raw_content, placements)` is the output-PCB write step** — reads input PCB text, applies placements, writes a temp file. Netclass form injection slots as a second text transformation pass before the temp-file write. Same pattern, adjacent code path.

One genuine gap the scan confirmed: **`feedback.py:242` reads `required_mm` from the DRC violation object with a hardcoded default of `6.0`** (`getattr(violation, 'required_mm', 6.0)`). The handler doesn't look up the YAML's physics-cited value today; if a DRC violation lacks `required_mm` or carries a different value, the handler injects an arbitrary 6.0mm constraint. The fix is for the handler to consult the YAML authority (via `DesignRules`) for the violating pair's class-pair clearance.

---

## Requirements

**[Single source of truth]**
- R1. `packages/temper-placer/configs/netclass_rules.yaml` is the sole editable surface for netclass → clearance (and track-width, via-size) rules. Two-tier: safety-critical class-pairs (HV↔SIGNAL at 6.0mm, HV↔GROUND per IEC 60335-1 derating at the board's working voltage) with `because` fields citing IEC table IDs; routine pairs (POWER↔SIGNAL, POWER↔GROUND, intra-HV) at manufacturer defaults. `default_clearance_mm` covers any pair not explicitly listed. Schema mirrors `NetClassRules` field names (`clearance_mm`, `trace_width_mm`, `via_dia_mm`, `via_drill_mm`) per `core/design_rules.py:96`.

**[Preventive placement (CP-SAT)]**
- R2. The CP-SAT encoder auto-generates SEPARATED constraints for every cross-class component-net-pair from `netclass_rules.yaml` (loaded as `DesignRules`). Per-pair clearance value comes from `design_rules.get_rules_for_net(net_name)` by resolving both nets' classes via `core/net_classification.classify_net()` and looking up the class-pair clearance. Safety-critical pair values are hard constraints (tol=0); routine pairs are hard by default with the hybrid backtracking policy governing relax/escalate (flex-arm for tunable pairs, escalate operator on physics-grounded pairs).

**[Preventive routing (router_v6)]**
- R3. router_v6 routes with per-netclass spacing from the same `DesignRules` loaded from the YAML. The existing `constraint_model.py:401` consumption path already does `rule.trace_width_mm + rule.clearance_mm` per net; this workstream ensures the `DesignRules` it consumes is the YAML-loaded one (not a hardcoded default).

**[Output PCB as derived artifact]**
- R4. `temper optimize`'s output-PCB write step (in `router_v6/adapter.py:_apply_placements_to_pcb`) gains a second transformation pass that injects `(net_class ...)` forms into the output PCB from the loaded `DesignRules`. The output PCB is a derived artifact — never hand-edited for netclass rules. Pre-existing input PCB forms are preserved (the temper input has none; merge is append-only in practice).

**[Reactive feedback backstop (existing, verified)]**
- R5. The existing `_handle_clearance_violation` at `feedback.py:239-282` is the backstop. Verified: handler reads `required_mm` from `violation.required_mm` with hardcoded fallback `6.0`. Modify the handler to look up the YAML-derived clearance value via `design_rules.get_rules_for_net(net_a)` and `get_rules_for_net(net_b)`, taking the max of the two nets' class-pair clearances. The injected `SeparatedConstraint` then carries the YAML's physics-cited value on safety-critical pairs, not a default.

**[Per-layer experiment (decisive measurement)]**
- R6. Three-row experiment measuring DRC error count vs the 29-violation human baseline:
  - Row A: placement-only netclass-aware constraints (CP-SAT with F2 active, routing without F3 active — swap F3 from "default" to "default-routing")
  - Row B: placement + routing (both preventive layers, feedback loop off)
  - Row C: placement + routing + feedback (full pipeline)
  Reports the per-row DRC count and a one-sentence "load-bearing layer" finding. Per the brainstorm: doesn't gate the merge, gates follow-up tuning investment.

---

**Origin flows:** F1 (Authority definition), F2 (Preventive placement), F3 (Preventive routing), F4 (Output-PCB write), F5 (Reactive feedback backstop), F6 (Per-layer experiment)

**Origin actors:** A1 (`netclass_rules.yaml`), A2 (CP-SAT encoder), A3 (router_v6), A4 (output-PCB write step), A5 (kicad-cli DRC), A6 (F3 feedback loop)

**Origin acceptance examples:** AE1 (YAML authority on placement/router/output PCB match), AE2 (placement + output-PCB forms traceable), AE3 (router spacing ≥ clearance), AE4 (feedback handler uses YAML value), AE5 (per-layer experiment table)

---

## Scope Boundaries

- **Full IEC 60335-1 Table 16 encoding** — out of scope. Only the rows for the temper board's voltage classes: mains AC at 230Vrms/325Vpk, DC bus at 325V, IGBT power stage.
- **router_v6 internal architecture changes** — out of scope. The router consumes the YAML-derived `DesignRules` through the existing `constraint_model.py:401` path; no channel-model or topology-solver restructure.
- **Per-pin or per-route-segment clearance rules** — out of scope. Rules are class-pair rules (HV-net to SIGNAL-net), not per-pin.
- **Schematic-editor-integrated netclass declaration** — out of scope. PCB's `(net_class ...)` forms are generated by `temper optimize`, not synchronized from a schematic.
- **Modifying the input KiCad PCB** — out of scope. Only the generated output PCB carries the derived `(net_class ...)` forms.

---

## Context & Research

### Relevant Code (consumed infrastructure — already built)

| Component | File | Key detail |
|-----------|------|------------|
| `DesignRules` / `NetClassRules` | `packages/temper-placer/src/temper_placer/core/design_rules.py:96,148` | Pydantic-ish model with `net_classes: dict[str, NetClassRules]` and `get_rules_for_net(net_name, net_class=None)`. Per-net rules infrastructure exists. |
| Net classification | `packages/temper-placer/src/temper_placer/core/net_classification.py` | `classify_net(name)` returns GROUND/POWER/HV/SIGNAL via name-pattern frozensets. Consumed by R2's auto-generation. |
| Router consumption of `DesignRules` | `packages/temper-placer/src/temper_placer/router_v6/constraint_model.py:401` | `rule = design_rules.get_rules_for_net(net.name); net_width = rule.trace_width_mm + rule.clearance_mm`. The R3 mechanism is mostly "make sure the YAML-loaded DesignRules reaches this call site." |
| Existing feedback handler | `packages/temper-placer/src/temper_placer/placer/cp_sat/feedback.py:239-282` | `_handle_clearance_violation` reads `getattr(violation, 'required_mm', 6.0)`. R5 modifies this to look up `DesignRules` by net pair. |
| Input PCB write step | `packages/temper-placer/src/temper_placer/router_v6/adapter.py:402-440` | `_apply_placements_to_pcb(raw_content, placements)` runs a text transformation on the input PCB and writes a temp file. R4 injects netclass writing as an adjacent transformation. |
| Existing IEC-cited constraint | `packages/temper-placer/configs/constraints/safety_isolation.yaml` | Cites IEC 60335-1 Table 16 at 10mm/400V reinforced isolation. Pattern: `because:` field cites physics derivation; this workstream extends to `netclass_rules.yaml`. |
| KiCad net_class syntax reference | `packages/temper-validation/data/reference_layouts/complex/ESP32-POE_ESP32-PoE_Rev_K.kicad_pcb` | `(net_class Default "..." (clearance 0.1524) (trace_width 0.1524) (via_dia 0.7) ...)`. The R4 emits forms this shape. |
| Existing SEPARATED handler | `packages/temper-placer/src/temper_placer/placer/cp_sat/encoder.py:97` | `_encode_separated` auto-generates inflated-interval NoOverlap2D constraints from `min_distance_mm`. R2 wires YAML-derived `min_distance_mm` into the existing pipeline. |

### Institutional Learnings

- **`docs/solutions/logic-errors/cp-sat-midpoint-constraint-parity-bug-2026-07-06.md`**: `mm_to_units` produces even integers for parity compatibility. Any new clearance values from `netclass_rules.yaml` flow through `mm_to_units` and inherit this protection.
- **`docs/solutions/performance-issues/cp-sat-pairwise-wirelength-solver-timeout-2026-07-06.md`**: O(n²) variable expansion kills the solver. R2 auto-generates cross-class SEPARATED constraints selectively — only for cross-class pairs, not all-pairs — keeping the variable count manageable.
- **`docs/solutions/best-practices/commutation-loop-area-physics-derivation-2026-07-04.md`**: Pattern for `because`-cited physics-grounded constraint values. R1 extends the pattern to `netclass_rules.yaml`.

---

## Key Technical Decisions

- **SSOT = `netclass_rules.yaml`**, not `DesignRules` extension or the KiCad PCB itself. The Pydantic `DesignRules` class instance is *constructed* from the YAML; the PCB is *derived* from it; both are read-only artifacts of the YAML's authority.
- **Two-tier YAML**, mirroring the existing PCL `tier` discipline. Safety-critical pairs cite IEC tables and physics derivations; routine pairs cite manufacturer defaults. The two-tier pattern is the project's established `because` discipline extended to a new artifact.
- **R2 uses selective cross-class auto-generation**, not all-pairs. The O(n²) expansion risk (per the pairwise-wirelength learning) is avoided by generating constraints only for cross-class pairs (HV↔SIGNAL, HV↔POWER, etc.), leveraging `net_classification.classify_net()` to skip intra-class pairs (where existing NoOverlap2D suffices).
- **R4 netclass forms written as text in `_apply_placements_to_pcb`**, not by parsing the PCB into a structured-modify-then-serialize pipeline. Reinforcing the existing pattern (placement writing is also text-transformation). Keeps the parsing surface out of scope.
- **R5 handler consulting `DesignRules`**, not reading the YAML directly. The YAML is the authority; `DesignRules` is its in-memory representation. The handler shouldn't re-parse the YAML for each violation.
- **R6 per-layer measurement doesn't gate merge** — per the brainstorm's Key Decision "experiment gates follow-up tuning, not merge."

---

## Implementation Units

### U1. `netclass_rules.yaml` authority + `DesignRules` loader

**Goal:** Define the YAML schema and the loader that constructs a `DesignRules` instance from it.

**Requirements:** R1

**Dependencies:** None

**Files:**
- Create: `packages/temper-placer/configs/netclass_rules.yaml`
- Create: `packages/temper-placer/src/temper_placer/io/netclass_loader.py` (or extend an existing io module)
- Test: `packages/temper-placer/tests/io/test_netclass_loader.py`

**Approach:**
- YAML schema (v1):
  ```yaml
  default_clearance_mm: 0.2
  classes:
    HV:
      clearance_mm: 6.0
      trace_width_mm: 0.5
      via_dia_mm: 1.0
      via_drill_mm: 0.6
      because: "IEC 60335-1 Table 16: reinforced isolation creepage/clearance at 400V working voltage"
    POWER:
      clearance_mm: 0.3
      trace_width_mm: 0.4
      via_dia_mm: 0.8
      via_drill_mm: 0.4
      because: "Manufacturer default for power rails"
    SIGNAL:
      clearance_mm: 0.2
      trace_width_mm: 0.2
      via_dia_mm: 0.6
      via_drill_mm: 0.3
      because: "Manufacturer default for signals"
  # Class-pair overrides: when present, take precedence over single-class values
  class_pairs:
    HV-SIGNAL:
      clearance_mm: 6.0
      because: "IEC 60335-1 Table 16 reinforced isolation at 400V working voltage"
    HV-POWER:
      clearance_mm: 3.0
      because: "50% derating per IEC 60335-1 between HV and user-touchable power domain"
  ```
  The `because` field is optional for routine classes; required for safety-critical class-pairs. `class_pairs` overrides take precedence.
- Loader returns a `DesignRules` instance with `net_classes` populated from `classes` (each becomes a `NetClassRules`). Per-class-pair clearance computed as `max(clearance_a, clearance_b)` *unless* `class_pairs` has an explicit entry. The `default_clearance_mm` is the fallback for unknown classes.
- Loader is a function `load_netclass_rules(path: Path) -> DesignRules`. Consumed by the CP-SAT pipeline and router_v6.

**Test scenarios:**
- Happy path: load a fixture YAML and assert HV's `clearance_mm` is 6.0, SIGNAL's is 0.2
- Happy path: load a fixture YAML with `class_pairs` overrides and assert HV-SIGNAL pair clearance is 6.0 from the override, not `max(6.0, 0.2)`
- Edge case: empty `classes` dict → returns `DesignRules` with `default_clearance_mm` only
- Edge case: class pair not in `class_pairs` → `max(clearance_a, clearance_b)` is used
- Edge case: unknown class in `class_pairs` (e.g. `FOO-BAR`) but `FOO` not in `classes` → logs warning, skips the override
- Integration: load `netclass_rules.yaml` and verify the result populates `DesignRules.get_rules_for_net("AC_L")` returning HV's 6.0mm clearance (AC_L is an HV-class per `net_classification.py`'s `HV_NET_PATTERNS`)

**Verification:**
- `python -c "from temper_placer.io.netclass_loader import load_netclass_rules; dr = load_netclass_rules(Path('packages/temper-placer/configs/netclass_rules.yaml')); assert dr.get_rules_for_net('AC_L').clearance_mm == 6.0"`

---

### U2. CP-SAT encoder: auto-generate SEPARATED constraints from netclass rules

**Goal:** When `DesignRules` is loaded from YAML at solve time, the CP-SAT encoder automatically generates SEPARATED constraints for cross-class component-net-pairs using the per-pair clearance value.

**Requirements:** R2

**Dependencies:** U1

**Files:**
- Modify: `packages/temper-placer/src/temper_placer/placer/cp_sat/encoder.py` (new auto-generation pass in `compile_pcl_to_cp_sat`)
- Modify: `packages/temper-placer/src/temper_placer/placer/cp_sat/model.py` (pass `design_rules` into the model context)
- Test: `packages/temper-placer/tests/placer/cp_sat/test_encoder.py` (extend existing suite)

**Approach:**
- New step in `compile_pcl_to_cp_sat`: after user-declared constraints are encoded, iterate the cross-class component-net-pairs and auto-generate `SeparatedConstraint` for each, with `min_distance_mm` from `design_rules.get_rules_for_net(net_a).clearance_mm` and `get_rules_for_net(net_b).clearance_mm` (taking the max), or look up `class_pairs` overrides.
- **Selective generation** (per the learning about O(n²) explosion): only cross-class pairs (where `classify_net(net_a) != classify_net(net_b)`). Intra-class pairs already get NoOverlap2D from the model; no auto-SEPARATED needed.
- Generated constraints carry `because` text from the YAML when present (inherits the safety-critical pair's physics citation), branded `id="netclass_autogen_HV_SIGNAL_*"` to distinguish from user-declared constraints.
- Generated constraints insert into the same assumption-variable pipeline so they participate in UNSAT-core extraction.
- Design choice — the brainstorm's two-tier: safety-critical class-pairs (HV-SIGNAL at 6mm) are encoded as `ConstraintTier.HARD`; routine class-pairs are also `ConstraintTier.HARD` (the hybrid backtracking policy handles relax, per the brainstorm — no relax baked into the encoder).

**Test scenarios:**
- Happy path: load temper netlist with `netclass_rules.yaml` and verify `HV-tagged` ↔ `SIGNAL-tagged` cross-pairs produce auto-generated SEPARATED with `min_distance_mm == 6.0`
- Happy path: any intra-SIGNAL pair produces *no* auto-generated SEPARATED (covered by NoOverlap2D)
- Happy path: `class_pairs` override `HV-POWER: 3.0mm` overrides the `max(6.0, 0.3)` computation
- Edge case: empty `DesignRules` (no YAML loaded) → no auto-generated constraints (backward-compat with existing single-board usage)
- Edge case: net in netlist has no classifiable name → skipped with a warning
- Integration: full encode+solve on temper with corrected `temper_induction.yaml` from the ref-resolution fix — placements satisfy the union of user-declared and auto-generated SEPARATED
- Property-based: for N≤8 random component classifications, every cross-class pair has an auto-generated constraint with the correct clearance value (BMC-style exhaustive over small N)

**Verification:**
- `python -m pytest packages/temper-placer/tests/placer/cp_sat/test_encoder.py::test_netclass_autogen_separated -xvs` passes
- Encoder log shows "auto-generated separated constraint for HV↔SIGNAL pair (6.0mm)" entries

---

### U3. router_v6: pass YAML-loaded `DesignRules` through existing channel-width path

**Goal:** Ensure router_v6 consumes the YAML-derived `DesignRules` instance (rather than any hardcoded fallback) when computing per-net channel widths via `constraint_model.py:401`.

**Requirements:** R3

**Dependencies:** U1

**Files:**
- Modify: `packages/temper-placer/src/temper_placer/router_v6/adapter.py` (accept `DesignRules` parameter in `route_pcb`)
- Modify: `packages/temper-placer/src/temper_placer/router_v6/pipeline.py` (thread `DesignRules` to `ConstraintModel`)
- Test: `packages/temper-placer/tests/router_v6/test_constraint_model.py` (extend)

**Approach:**
- `route_pcb(...)` gains an optional `design_rules: DesignRules | None = None` parameter. If `None`, router keeps existing default (backward-compat for callers without YAML). If provided, it threads to `RouterV6Pipeline` → `ConstraintModel` and the existing `constraint_model.py:401` consumption path (`rule.trace_width_mm + rule.clearance_mm`) uses YAML-derived values.
- No new architecture per Scope Boundaries. The change is wiring + plumbing + parameter threading.
- The `DesignRules` is passed through `route_pcb` -> `RouterV6Pipeline.__init__` -> `Stage2Orchestrator`/`Stage4Orchestrator` -> `ConstraintModel.build_constraints`. Existing construction path is preserved.

**Test scenarios:**
- Happy path: router_v6 routes a netlist with YAML-loaded `DesignRules` calling `route_pcb(..., design_rules=dr)`. The `constraint_model.py:401` line consumes `rule.clearance_mm` matching the YAML's `HV: 6.0mm` value.
- Happy path: with default `design_rules=None`, router uses existing behavior (backward-compat: parametrized tests that don't supply the YAML)
- Edge case: `DesignRules` has `HV` class but netlist has no HV-tagged nets → no HV constraints fire, no spurious spacing injected
- Integration: routes a 33-component temper netlist with `netclass_rules.yaml` without throwing; channel-width computation reports wide channels where HV/SIGNAL proximity exists

**Verification:**
- All existing router_v6 tests pass without `design_rules` (backward-compat preserved)
- Test that `route_pcb(design_rules=dr)` propagates: assert `ConstraintModel.design_rules == dr`

---

### U4. Output-PCB `(net_class ...)` form injection

**Goal:** Write `(net_class ...)` forms derived from YAML-loaded `DesignRules` into the output PCB during `_apply_placements_to_pcb`.

**Requirements:** R4

**Dependencies:** U1, U3

**Files:**
- Modify: `packages/temper-placer/src/temper_placer/router_v6/adapter.py:_apply_placements_to_pcb` (extend to inject netclass forms)
- Test: `packages/temper-placer/tests/router_v6/test_adapter.py`

**Approach:**
- `_apply_placements_to_pcb(raw_content, placements, design_rules=None)` — extend signature; when `design_rules` is provided, run a second text transformation after placements are applied.
- The transformer finds the `  (net 0 "")` declarations block (or the end of `(nets ...)` section — exact pattern to verify in planning — and inserts `(net_class ...)` forms before or after the existing `(net ...)` declarations per KiCad format conventions.
- One form per `net_class` in `design_rules.net_classes`:
  ```
    (net_class HV "High voltage class - IEC 60335-1 Table 16"
      (clearance 0.6)
      (trace_width 0.5)
      (via_dia 1.0)
      (via_drill 0.6)
    )
  ```
  (Clearance in mm, scaled directly from the YAML — KiCad expects millimeters.)
- **Pre-existing forms preservation**: if the input PCB already contains `(net_class ...)` forms, the YAML-derived forms are *merged* — for any class name already present, the YAML's values override the existing values. (For the temper board today, no pre-existing forms, so this is append-only.)
- Default KiCad class (`Default`) is preserved if present; the YAML's `default_clearance_mm` overrides its `clearance` value if the YAML specifies one.

**Test scenarios:**
- Happy path: input PCB with no `(net_class ...)` forms; after transformation, output contains `(net_class HV ...)`, `(net_class POWER ...)`, `(net_class SIGNAL ...)` with YAML's clearance values
- Happy path: input PCB with `(net_class Default ...)`; output preserves Default and adds the YAML's classes
- Edge case: input PCB's `(clearance 0.1524)` in `Default` overridden by YAML's `default_clearance_mm: 0.2` produces `(clearance 0.2)`
- Edge case: input PCB has `(net_class HV ...)` pre-existing; YAML's `HV` overrides the existing values (-clearance, trace_width, via_dia, via_drill all updated)
- Integration: `temper optimize --placer cp-sat temper.kicad_pcb --config pcl/temper_induction.yaml --netclass-rules configs/netclass_rules.yaml` produces an output PCB that, when DRC'd by `kicad-cli drc`, reports DRC errors against the YAML's clearances (not KiCad's default 0.1524mm)

**Verification:**
- `python -m pytest packages/temper-placer/tests/router_v6/test_adapter.py::test_netclass_form_injection -xvs` passes
- `grep "net_class" <output-pcb>` returns HV/POWER/SIGNAL forms with YAML's values

---

### U5. Feedback handler: read YAML-derived clearance via `DesignRules`

**Goal:** Modify `_handle_clearance_violation` to use the YAML-loaded `DesignRules` for `required_mm` instead of the hardcoded `6.0` default.

**Requirements:** R5

**Dependencies:** U1

**Files:**
- Modify: `packages/temper-placer/src/temper_placer/placer/cp_sat/feedback.py:239-282` (`_handle_clearance_violation`)
- Test: `packages/temper-placer/tests/placer/cp_sat/test_feedback.py` (extend)

**Approach:**
- `PlaceRouteLoop.__init__` already has `design_rules` threaded through (per U3). Pass it to the feedback handler's context.
- In `_handle_clearance_violation`: after resolving `comp_a`, `comp_b` from `violation`, look up the nets connected to `comp_a` and `comp_b` (via the netlist — needs to be available on the loop's context).
  - Get `class_a = classify_net(net_a)`, `class_b = classify_net(net_b)`
  - Get `clearance = design_rules.get_rules_for_net(net_a).clearance_mm` and `get_rules_for_net(net_b).clearance_mm`; take the max.
  - Override via `design_rules.class_pairs.get(f"{class_a}-{class_b}")` if present (matching U1's override semantics).
- Fallback path (when `design_rules` is None or nets can't be resolved): preserve the existing `getattr(violation, 'required_mm', 6.0)` for backward-compat.
- The injected constraint's `because` text: when YAML-derived value is used, the `because` field cites the YAML's `because` for the class-pair; when fallback is used, the existing "Post-route DRC clearance violation at {required_mm}mm" text stays.

**Test scenarios:**
- Happy path: `_handle_clearance_violation` called with `comp_a` on `AC_L` net (HV) and `comp_b` on `SPI_CLK` net (SIGNAL), `DesignRules` loaded from YAML → injected `SeparatedConstraint.min_distance_mm == 6.0` and `because` contains "IEC 60335-1"
- Happy path: same pair with `class_pairs` override `HV-SIGNAL: 3.0mm` (hypothetical) → injected `min_distance_mm == 3.0`
- Edge case: `design_rules=None` → existing behavior preserved (comp_a=comp_b=None short-circuit iff, fallback to `getattr` default `6.0`)
- Edge case: violation has `required_mm` explicitly set on the object → the YAML-derived value still takes precedence (it's the authoritative rules source, not the violation-reporter's default)
- Edge case: net can't be classified (no `GND`, `POWER`, `HV`, or `SIGNAL` pattern match) → logs warning, uses `default_clearance_mm` from YAML
- Integration: feed a DRC violation into the loop → next-round's CP-SAT model includes a `SeparatedConstraint` with the YAML's clearance value (not 6.0 hardcoded)

**Verification:**
- `python -m pytest packages/temper-placer/tests/placer/cp_sat/test_feedback.py::test_handle_clearance_violation_uses_yaml -xvs` passes
- Feedback loop test asserting no `6.0` hardcoded default survives in the handler's path

---

### U6. Per-layer decisive experiment + report

**Goal:** Run the three-row experiment measuring DRC error count at each checkpoint and record the load-bearing layer.

**Requirements:** R6

**Dependencies:** U1, U2, U3, U4, U5 (all preventive + reactive layers in place)

**Files:**
- Create: `packages/temper-placer/tests/regression/test_netclass_layers_experiment.py` (or a script-style harness)
- Create: `docs/reports/2026-07-06-netclass-layers-experiment.md`

**Approach:**
- Three runs of `temper optimize` (or programmatic equivalent via the existing pipeline test harness) on `power_pcb_dataset/corpus/temper/temper.kicad_pcb` with `netclass_rules.yaml` loaded:

  **Row A — placement-only:**
  - Load `netclass_rules.yaml` → CP-SAT with auto-generated SEPARATED (U2 active).
  - Run router_v6 with `design_rules=None` (U3 *not* active — router uses existing defaults).
  - Skip U4 PCB netclass forms (or write them anyway for parity, doesn't affect count).
  - Run kicad-cli DRC. Record error count.

  **Row B — placement + routing:**
  - Load `netclass_rules.yaml` → CP-SAT with U2.
  - Run router_v6 with `design_rules=dr` (U3 active).
  - Write U4 netclass forms to output PCB.
  - Run kicad-cli DRC. Record error count.

  **Row C — full pipeline + feedback:**
  - Same as Row B, but enable the F3 place→route loop with U5's updated feedback handler.
  - Run kicad-cli DRC on the final output PCB. Record error count.

- Each row runs against the 29-violation human baseline (from `docs/reports/2026-07-06-umbrella-status.md`).

- **If `kicad-cli` is unavailable** (the worktree subagent reported it was; main checkout may have it), use the oracle-proxy DRC as fallback for Row A (where netclass forms aren't in the output PCB anyway) and flag Rows B/C as deferred-pending-pipeline-availability. Same discipline as the earlier decisive-result report — surface the dependency status, never silently downgrade.

- Report at `docs/reports/2026-07-06-netclass-layers-experiment.md` with:
  - Three-row table (Row, Layer active, DRC error count, vs baseline)
  - One-sentence "load-bearing layer" finding (which layer is responsible for the largest delta)
  - Per-row sample of common error types if available (was the largest class "clearance between HV and SIGNAL tracks"? or track-to-board-edge? etc.) — informs where the next round of investment goes.

**Test scenarios:**
- Smoke test: harness runs without crashing; produces three numbers (or three "deferred" entries)
- Sanity: Row A error count ≤ 121 (the no-constraints baseline) — the placement constraints alone should reduce errors
- Deterministic: same input → same output across runs (CP-SAT deterministic; router_v6 mostly deterministic; the F3 feedback loop may have variance — record if so)

**Verification:**
- `docs/reports/2026-07-06-netclass-layers-experiment.md` exists with the three-row table
- The workstream's decisive result (R6) is the table itself

---

## System-Wide Impact

- **Interaction graph:** the YAML authority flows into three consumers: the CP-SAT encoder (new auto-generation pass in `compile_pcl_to_cp_sat`), router_v6 (existing `constraint_model.py:401` path, parameter threading through `route_pcb`), and the output PCB write step (new pass in `_apply_placements_to_pcb`). The F3 feedback handler gets the `DesignRules` reference via the loop's context. Single source, three consumers (two preventive, one output-PCB-derivation), one reactive ref.
- **Error propagation:** if `netclass_rules.yaml` is missing or malformed, all three consumers fall back to existing defaults (no `DesignRules` = no auto-generated SEPARATED in CP-SAT, no netclass routing rules in router_v6, no netclass forms in output PCB). No hard failure for backward-compat; warnings logged.
- **State lifecycle:** `DesignRules` instances are loaded fresh per `temper optimize` invocation. No module-level state.
- **Unchanged invariants:** the existing `_encode_separated` handler behavior for user-declared SEPARATED is preserved; auto-generated SEPARATED (R2) is an additional pass, not a replacement. The output PCB write preserves pre-existing `(net_class ...)` and `Default` class.

---

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| KiCad `(net_class ...)` form placement in the PCB syntax may have ordering requirements (must come after `(net ...)` declarations, before `(footprint ...)`) | Verify placement by parsing a known-good reference PCB and grep the lines around `net_class` for ordering requirements. Adjust U4's insertion point accordingly. |
| kicad-cli DRC may use **per-class** clearance (not per-class-pair) — KiCad's native model may be "clear X class-to-Default, Y class-to-Default" not "X class to Y class." | Verify against KiCad 9 format spec. If per-class, the YAML's per-pair overrides compile down to a derived per-class clearance that satisfies the pair requirement; this is a planning-time decision affecting U1's schema and U4's emission. |
| O(n²) auto-generated SEPARATED constraints bloat solver time | Already mitigated by U2's selective cross-class generation (`intra-class` pairs are skipped). Validate on temper N=33 the auto-generated count stays ≤ ~50 constraints (4-8 cross-class pairs in practice). Per-parameter explainability if exceeded. |
| `kicad-cli` not available in CI | Row A experiment can still run via oracle-proxy DRC; Rows B/C defer as in the prior decisive-result measurement. Flag dependency status, never silent downgrade. |
| Class pair override semantics: `HV-SIGNAL` matching direction (a-b vs b-a) | Loader normalizes to alphabetical-order keys (`HV-SIGNAL` not `SIGNAL-HV`) and lookups check both orders. Unit-tested. |
| Feedback handler's looking up by *net name* may miss the case where the DRC violation reports only `comp_a`/`comp_b` components, not the specific nets | Handle this via the netlist: the components' connected nets come from the loop's `netlist` reference. Fall back to `default_clearance_mm` if neither component's net can be resolved. |

---

## Deferred to Follow-Up Work

- **Full IEC 60335-1 Table 16 encoding** — out of scope per the brainstorm. Only the rows for the temper board's voltages.
- **router_v6 architecture changes** — out of scope per the brainstorm. Only parameter threading.
- **Per-pin or per-route-segment clearance rules** — out of scope. Class-pair rules only.
- **Track-width and via-size fields beyond safety-critical pairs** — the YAML schema reserves the fields; v1 fills them with manufacturer defaults for routine classes and IEC-cited values for safety-critical pairs. A follow-up encoding pass for IEC-aware widths is out of scope.
- **Strict-zero DRC bar** — the workstream's success criterion is ≤ the 29-violation human baseline. Strict-zero is a follow-up if Row C closes most of the gap.

---

## Sources & References

- **Origin document:** `docs/brainstorms/2026-07-06-netclass-aware-clearance-ssot-requirements.md`
- **Umbrella final report:** `docs/reports/2026-07-06-umbrella-final-report.md` — identified the 121-vs-29 gap as headline open item
- **Prior ref-resolution plan:** `docs/plans/2026-07-06-001-fix-pcl-constraint-ref-resolution-plan.md` — sibling work on the same board; ref-resolution must land for the encoder to fully exercise netclass auto-generation
- **Physics derivation pattern:** `docs/solutions/best-practices/commutation-loop-area-physics-derivation-2026-07-04.md`
- **Existing IEC-cited constraint:** `packages/temper-placer/configs/constraints/safety_isolation.yaml`
- **Compound learnings (constraint-modeling):**
  - `docs/solutions/logic-errors/cp-sat-midpoint-constraint-parity-bug-2026-07-06.md`
  - `docs/solutions/performance-issues/cp-sat-pairwise-wirelength-solver-timeout-2026-07-06.md`
- **Consumed infrastructure:**
  - `packages/temper-placer/src/temper_placer/core/design_rules.py:96,148`
  - `packages/temper-placer/src/temper_placer/core/net_classification.py`
  - `packages/temper-placer/src/temper_placer/router_v6/constraint_model.py:401`
  - `packages/temper-placer/src/temper_placer/placer/cp_sat/encoder.py:97`
  - `packages/temper-placer/src/temper_placer/placer/cp_sat/feedback.py:239`
  - `packages/temper-placer/src/temper_placer/router_v6/adapter.py:402`
- **KiCad net_class syntax reference:** `packages/temper-validation/data/reference_layouts/complex/ESP32-POE_ESP32-PoE_Rev_K.kicad_pcb`