---
title: Check for duplicate plans before implementing — prefer the plan that extends existing types
date: "2026-07-07"
category: best-practices
module: temper_placer
problem_type: best_practice
component: development_workflow
severity: medium
applies_when:
  - "Starting implementation from a feature plan"
  - "Multiple plans reference the same brainstorms or requirements"
  - "A plan proposes creating new types/modules that duplicate existing infrastructure"
tags: ["plan-discovery", "duplicate-plans", "type-drift", "ssot", "designrules"]
---

# Check for duplicate plans before implementing — prefer the plan that extends existing types

## Context

Implementing the netclass-aware clearance SSOT for the Temper placer, plan 001 (`docs/plans/2026-07-07-001`) was read and implemented first. Only after completing all 9 implementation units was a second plan discovered: plan 002 (`docs/plans/2026-07-06-002`). Despite the earlier filing date, plan 002 was finalized after deeper codebase research and specified a different architecture — one that extended existing `DesignRules`/`NetClassRules` types instead of creating parallel modules.

Plan 001 created a standalone `core/netclass_rules.py` with new `NetClassRulesDict`, `get_pair_clearance()`, and `resolve_net_class()` — duplicating semantics already present in `DesignRules.get_rules_for_net()`. It also created router architecture changes (`netclass_inflation.py`) that violated the plan's own scope boundary, and output PCB writing in the wrong module. The refactor to align with plan 002 required deleting 5 files, restoring 3 files to their `origin/main` state, rewriting 6 files, and recreating 4 test files — a 1400-line net reduction.

## Guidance

**Before implementing from a plan, scan for other plans targeting the same problem domain.** The timestamp or plan number is not a reliable ordering signal. A plan filed earlier may have been finalized after deeper research than one filed later.

```bash
# 1. List plans touching the same subsystem
ls docs/plans/ | grep -i "netclass\|clearance\|ssot"

# 2. Grep for concept overlap across plan bodies
rg -l "DesignRules\|NetClassRules\|class_pairs\|clearance" docs/plans/

# 3. Check the origin document's Outstanding Questions — if plan 002 resolved
# questions that plan 001 deferred, prefer plan 002
rg "Resolve Before Planning\|Deferred to Planning" docs/plans/<candidate>.md
```

When two plans exist, prefer the one that **extends existing types** over creating parallel ones:

### Wrong (plan 001) — parallel types and schemas

```python
# NEW standalone module competing with existing DesignRules
class NetClassRulesDict(TypedDict):
    net_classes: dict[str, NetClassRulesFromYaml]
    pair_clearances: dict[tuple[str, str], float]
    ...

def get_pair_clearance(class_a, class_b, *, rules):
    """Duplicates DesignRules.get_rules_for_net() semantics"""

def resolve_net_class(net_name):
    """Duplicates DesignRules net_class_assignments"""
```

```yaml
# YAML schema creates a net_classes LIST — parallel format
net_classes:
  - name: "Power"
    clearance: 0.25
cross_class_clearances:
  - class_a: "Power"
    class_b: "Signal"
    clearance_mm: 0.3
```

```python
# NEW router module — scope boundary violation
class NetClassInflation:
    def inflate_obstacles(self, grid, clearance, net_class):
        # Modifies A* pathfinder binary grid
```

### Correct (plan 002) — extend existing types

```python
# Existing DesignRules dataclass from core/design_rules.py
@dataclass
class DesignRules:
    net_classes: dict[str, NetClassRules] = field(default_factory=dict)
    net_class_assignments: dict[str, str] = field(default_factory=dict)

    def get_rules_for_net(self, net_name, net_class=None) -> NetClassRules:
        """Single method — no new get_pair_clearance() needed"""
```

```python
# io/netclass_loader.py loads YAML INTO existing DesignRules instance
def load_netclass_rules(path: Path) -> NetClassRulesDict:
    dr = DesignRules()
    for class_name, class_data in data["classes"].items():
        dr.net_classes[class_name] = NetClassRules(
            name=class_name,
            clearance=class_data["clearance"],  # matches existing field name
            trace_width=class_data["trace_width"],
        )
    dr.class_pairs = {tuple(sorted(k.split("-"))): v for k, v in class_pairs.items()}
    return NetClassRulesDict(design_rules=dr, class_pairs=class_pairs)
```

```yaml
# YAML schema mirrors NetClassRules field names exactly
classes:
  Power:
    clearance: 0.25       # matches NetClassRules.clearance
    trace_width: 0.5       # matches NetClassRules.trace_width
class_pairs:
  Power-Signal: {clearance: 0.3, because: "..."}
  ACMains-Signal: {clearance: 6.0, because: "IEC 60335-1 Table 16"}
```

```python
# No new router module — just thread DesignRules through existing path
# constraint_model.py:400 (unchanged)
rule = self.design_rules.get_rules_for_net(net.name)
net_width = rule.trace_width_mm + rule.clearance_mm
```

## Why This Matters

**Type drift is the most expensive silent failure.** Creating a parallel `NetClassRulesDict` alongside the existing `NetClassRules` means bug fixes, field additions, or validation rules applied to one type won't propagate to the other. The `splr→rustsat-cadical` migration (2026-06-29) documented the exact same anti-pattern: two `NetClassRules` types in different packages diverged, requiring `getattr(x, "safety_category", None)` defensive workarounds.

**Scope creep from wrong plan.** Plan 001's `netclass_inflation.py` modified the A* pathfinder — explicitly ruled out by the brainstorm's Scope Boundaries of "no router_v6 internal architecture changes." Implementing the wrong plan wastes time on work that should not be done.

**Pattern already documented.** Both the `pydantic-dataclass-migration` (2026-06-28) and `layer-index-ssot-placer` (2026-06-23) learnings document the SSOT consolidation pattern: co-locate with the existing concept, big-bang migrate in a single PR. Plan 001 broke this pattern by creating parallel infrastructure.

## When to Apply

- Whenever you find a plan document and are about to implement it
- When the plan references a subsystem that has an existing type or data model (`DesignRules`, `NetClassRules`, `ParsedPCB`, etc.)
- When a plan creates a new file/module that appears to solve the same problem an existing module already handles
- When a plan proposes a new YAML schema format covering the same domain
- When plan numbers and filing dates seem inconsistent (002 filed before 001 but finalized after)

## Examples

| Symptom | What to check |
|---------|---------------|
| Plan creates a new `TypedDict`/Pydantic model for a concept that already has one | Search for the existing model; a sibling plan likely extends it |
| Plan adds files to `router_v6/` | Confirm router architecture changes are in scope |
| Plan uses `kiutils` for PCB output | Check if `adapter.py:_apply_placements_to_pcb` is the canonical path |
| Plan mentions `DesignRules` only as context, not as target | The plan may be unaware of the existing infrastructure |

## Related

- `docs/solutions/architecture-patterns/pydantic-dataclass-migration.md` — canonical `NetClassRules` Pydantic model and `TEMPER_NET_CLASSES`
- `docs/solutions/tooling-decisions/splr-to-rustsat-cadical-solver-migration-2026-06-29.md` — type drift across packages (same anti-pattern, different context)
- `docs/solutions/architecture-patterns/layer-index-ssot-placer-2026-06-23.md` — SSOT consolidation pattern ("co-locate, big-bang migrate")
- `docs/plans/2026-07-06-002-feat-netclass-aware-clearance-ssot-plan.md` — the correct plan
- `packages/temper-placer/src/temper_placer/core/design_rules.py:148` — existing `DesignRules` dataclass
- `packages/temper-placer/src/temper_placer/router_v6/adapter.py:402` — `_apply_placements_to_pcb` text-transformation path
