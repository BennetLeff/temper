---
title: Netclass-aware clearance SSOT — YAML authority consumed by placer, router, and output PCB
date: "2026-07-07"
category: architecture-patterns
module: temper_placer
problem_type: architecture_pattern
component: tooling
severity: high
applies_when:
  - "Adding a new constraint authority that multiple subsystems must consume consistently"
  - "Deriving PCB design rules from a config file into placement, routing, and DRC enforcement"
  - "Closing a 121→29 DRC-violation gap caused by missing per-netclass clearance rules"
tags: ["netclass", "clearance", "ssot", "designrules", "cp-sat", "router-v6", "drc", "iec-60335-1"]
---

# Netclass-aware clearance SSOT — YAML authority consumed by placer, router, and output PCB

## Context

The Temper induction cooker PCB had **zero `(net_class ...)` definitions** in it. kicad-cli DRC ran at KiCad's ~0.15mm default clearance, producing 121 DRC errors against the 29-violation human baseline. The board *should* have a 6mm ACMains-to-signal rule per IEC 60335-1, but neither the placer nor the PCB carried it.

Three infrastructure pieces already existed that could be wired together:

- `core/design_rules.py` — `DesignRules` dataclass with `net_classes: dict[str, NetClassRules]` and `get_rules_for_net()`. The canonical in-memory representation of per-netclass routing rules.
- `core/net_classification.py` — `classify_net_type()` returning `"ground"`, `"power"`, `"hv"`, or `"signal"` via name-pattern frozensets.
- `router_v6/constraint_model.py:401` — existing consumer: `rule = design_rules.get_rules_for_net(net.name)` → `net_width = rule.trace_width_mm + rule.clearance_mm`.

What was missing: the *mapping* between netclass pairs and clearance values, a single source of truth so the placer, router, and truth gate all enforced the same rules, and the derived `(net_class ...)` s-expression forms in the output PCB.

## Guidance

### Architecture: single YAML authority → DesignRules instance → three consumers

```
netclass_rules.yaml
        │
        ▼
io/netclass_loader.py ──► DesignRules (populates net_classes + class_pairs)
        │
        ├──► CP-SAT encoder ──► auto-generated SeparatedConstraint per cross-class pair
        │
        ├──► router_v6 ──► constraint_model.py:401 consumes net_width = trace + clearance
        │
        └──► adapter.py:_apply_placements_to_pcb ──► injects (net_class ...) s-exprs
                │
                ▼
        kicad-cli pcb drc ──► truth gate checks against same rules
```

### YAML schema

```yaml
default_clearance_mm: 0.2

classes:
  HighVoltage:
    clearance: 6.0          # field names match NetClassRules Pydantic model
    trace_width: 3.0
    via_diameter: 1.2
    via_drill: 0.6
    safety_category: "HV"
    because: "IEC 60335-1 Table 16 working isolation at 400V"
  Signal:
    clearance: 0.15
    trace_width: 0.2
    via_diameter: 0.6
    via_drill: 0.3
    safety_category: "LV"
  # ... 7 more classes

class_pairs:
  HighVoltage-Signal: {clearance: 6.0, because: "IEC 60335-1 Table 16 — 6mm between HV and signal"}
  HighVoltage-GND: {clearance: 6.0, because: "IEC 60335-1 Table 16 — 6mm between HV and ground"}
  # Safety-critical pairs only. Routine pairs use max(self-clearance-a, self-clearance-b).
```

### Loader: populate DesignRules, not replace it

```python
# io/netclass_loader.py
@dataclass
class NetClassRulesDict:
    design_rules: DesignRules
    class_pairs: dict[tuple[str, str], dict]

def load_netclass_rules(path: Path) -> NetClassRulesDict:
    data = yaml.safe_load(path.read_text())
    dr = DesignRules()
    dr.default_clearance = data["default_clearance_mm"]

    for name, spec in data["classes"].items():
        dr.net_classes[name] = NetClassRules(
            name=name,
            clearance=spec["clearance"],
            trace_width=spec["trace_width"],
            via_diameter=spec["via_diameter"],
            via_drill=spec["via_drill"],
            safety_category=spec.get("safety_category"),
        )

    class_pairs = {}
    for key, val in data["class_pairs"].items():
        a, b = key.split("-")
        class_pairs[tuple(sorted([a, b]))] = {"clearance": val["clearance"], "because": val.get("because")}
    dr.class_pairs = class_pairs

    return NetClassRulesDict(design_rules=dr, class_pairs=class_pairs)
```

### Consumer 1: CP-SAT placement — auto-generated SEPARATED constraints

```python
# placer/cp_sat/netclass_constraints.py
def generate_netclass_separated_constraints(netlist, components, design_rules):
    """For every cross-class component pair, generate a SeparatedConstraint."""
    for comp_a, comp_b in cross_class_pairs(components, netlist):
        class_a = resolve_net_class_from_components(comp_a, netlist)
        class_b = resolve_net_class_from_components(comp_b, netlist)
        if class_a == class_b:
            continue  # same-class handled by global NoOverlap2D

        max_self = max(
            design_rules.net_classes[class_a].clearance,
            design_rules.net_classes[class_b].clearance,
        )
        cp_key = tuple(sorted([class_a, class_b]))
        clearance = design_rules.class_pairs.get(cp_key, {}).get("clearance", max_self)
        because = design_rules.class_pairs.get(cp_key, {}).get("because", "")

        yield SeparatedConstraint(
            a=comp_a.ref, b=comp_b.ref,
            min_distance_mm=clearance,
            tier=ConstraintTier.HARD,
            because=because or f"Netclass {class_a}↔{class_b} at {clearance}mm",
        )
```

The constraints enter the existing `TYPE_HANDLERS` dispatch (`_encode_separated` → `NoOverlap2D` + `OnlyEnforceIf`). Safety-critical pairs are `HARD`; the hybrid backtracking policy governs relax behavior.

### Consumer 2: Router — thread through existing constraint_model path

No new router module. The `DesignRules` is passed through `route_pcb(design_rules=dr)` → `RouterV6Pipeline` → `ConstraintModel`. The existing line at `constraint_model.py:401`:

```python
rule = design_rules.get_rules_for_net(net.name)
net_width = rule.trace_width_mm + rule.clearance_mm
```

now receives YAML-derived values instead of hardcoded defaults.

### Consumer 3: Output PCB — inject (net_class ...) s-expressions

```python
# adapter.py:_apply_placements_to_pcb (text transformation)
def _apply_placements_to_pcb(raw_content, placements, design_rules=None):
    # ... existing footprint position rewriting ...
    if design_rules and design_rules.net_classes:
        nc_forms = []
        for nc_name, nc in sorted(design_rules.net_classes.items()):
            nc_forms.append(
                f"  (net_class \"{nc_name}\""
                f" (clearance {nc.clearance})"
                f" (trace_width {nc.trace_width})"
                f" (via_dia {nc.via_diameter})"
                f" (via_drill {nc.via_drill}))"
            )
        # Inject after (setup ...) block, before (net ...) declarations
        raw_content = _inject_after_setup(raw_content, "\n".join(nc_forms))
    return raw_content
```

This is a text transformation — same pattern as the existing placement rewriting. No `kiutils` dependency.

### Backstop: Feedback handler

`feedback.py:_handle_clearance_violation` reads the YAML's authoritative clearance via `DesignRules.get_rules_for_net()` instead of trusting the DRC violation's `required_mm` (which reflects the output PCB's potentially default rules on the first round):

```python
if self.design_rules:
    class_a = _map_class(classify_net_type(violation.net_a))
    class_b = _map_class(classify_net_type(violation.net_b))
    rules_a = self.design_rules.get_rules_for_net("", net_class=class_a)
    rules_b = self.design_rules.get_rules_for_net("", net_class=class_b)
    authoritative_mm = max(rules_a.clearance, rules_b.clearance)
    # Check class_pairs override
    cp_key = tuple(sorted([class_a, class_b]))
    if cp_key in self.design_rules.class_pairs:
        authoritative_mm = self.design_rules.class_pairs[cp_key]["clearance"]
```

## Why This Matters

**Single source of truth prevents constraint drift.** The 6mm ACMains→Signal clearance is defined once (in the YAML) and consumed identically by the placer, router, and output PCB. kicad-cli DRC checks against the same value the placer enforced — the two-tier gate is meaningful.

**Extends, doesn't replace.** `DesignRules` and `NetClassRules` already existed as the canonical in-memory representation. The YAML populates these types rather than creating parallel ones. This avoids the type-drift documented in the `splr→rustsat-cadical` migration.

**No router architecture changes.** The plan's Scope Boundaries explicitly ruled out router internal changes. The existing `constraint_model.py:401` path already consumed `DesignRules` — the work was wiring the YAML-loaded instance through.

**Text transformation for output PCB.** KiCad's `(net_class ...)` syntax supports per-class self-clearance (verified against `ESP32-POE_ESP32-PoE_Rev_K.kicad_pcb`). The existing `_apply_placements_to_pcb` text-transformation path co-locates the injection with the existing footprint position rewriting.

## When to Apply

- Adding a constraint authority that must be consumed identically by multiple subsystems
- Deriving KiCad PCB rules from a YAML config that placement and routing already enforce
- Closing DRC violation gaps caused by missing per-netclass definitions in the board file
- When `DesignRules` / `NetClassRules` infrastructure already exists — populate it, don't replace it

## Related

- `docs/brainstorms/2026-07-06-netclass-aware-clearance-ssot-requirements.md` — requirements origin
- `docs/plans/2026-07-06-002-feat-netclass-aware-clearance-ssot-plan.md` — implementation plan
- `docs/solutions/architecture-patterns/pydantic-dataclass-migration.md` — NetClassRules Pydantic model
- `docs/solutions/architecture-patterns/layer-index-ssot-placer-2026-06-23.md` — SSOT consolidation pattern
- `docs/solutions/best-practices/commutation-loop-area-physics-derivation-2026-07-04.md` — `because`-cited physics derivation pattern
- `packages/temper-placer/configs/constraints/safety_isolation.yaml` — IEC 60335-1 citation precedent
