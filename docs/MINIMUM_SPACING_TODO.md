# Minimum Component Spacing Implementation TODO

## Context
Based on analysis in temper-2edy.10, we found critical component overlaps and clearance violations in the power section. We've added `minimum_spacing` rules to the config, but they're not yet enforced by the optimizer.

## Current State
- ✅ Added `minimum_spacing` section to `temper_constraints.yaml`
- ✅ Defined 7 HV component spacing rules (D2, C_BUS1/2, Q1/2)
- ❌ No code to parse and enforce these rules

## Implementation Needed

### 1. Extend Config Loader
**File**: `packages/temper-placer/src/temper_placer/config/config_loader.py`

Add parsing for `minimum_spacing` section:
```python
def load_minimum_spacing_rules(config: dict) -> list[ComponentSpacingRule]:
    """Parse minimum_spacing from YAML config."""
    rules = []
    for rule_dict in config.get('minimum_spacing', []):
        rules.append(ComponentSpacingRule(
            components=tuple(rule_dict['components']),
            min_separation_mm=rule_dict['min_separation_mm'],
            description=rule_dict.get('description', ''),
        ))
    return rules
```

### 2. Add ComponentSpacingRule Dataclass
**File**: `packages/temper-placer/src/temper_placer/losses/base.py`

```python
@dataclass
class ComponentSpacingRule:
    """Minimum spacing requirement between specific components."""
    components: tuple[str, str]  # Component references (e.g., ("D2", "C_BUS1"))
    min_separation_mm: float
    description: str = ""
    weight: float = 1.0
```

### 3. Extend LossContext
**File**: `packages/temper-placer/src/temper_placer/losses/base.py`

Add to `LossContext`:
```python
@dataclass
class LossContext:
    # ... existing fields ...
    component_spacing_rules: list[ComponentSpacingRule] = field(default_factory=list)
    component_name_to_index: dict[str, int] = field(default_factory=dict)  # For lookups
```

### 4. Add ComponentSpacingLoss
**File**: `packages/temper-placer/src/temper_placer/losses/component_spacing.py` (NEW)

```python
class ComponentSpacingLoss(LossFunction):
    """Enforce minimum edge-to-edge spacing between specific component pairs."""
    
    def __call__(self, positions, rotations, context, epoch=0, total_epochs=1):
        total_penalty = 0.0
        
        for rule in context.component_spacing_rules:
            comp_a, comp_b = rule.components
            idx_a = context.component_name_to_index.get(comp_a)
            idx_b = context.component_name_to_index.get(comp_b)
            
            if idx_a is None or idx_b is None:
                continue
            
            # Get component bounds and positions
            pos_a = positions[idx_a]
            pos_b = positions[idx_b]
            bounds_a = context.bounds[idx_a]
            bounds_b = context.bounds[idx_b]
            
            # Compute edge-to-edge distance (reuse logic from ClearanceLoss)
            edge_dist = compute_box_box_distance(pos_a, bounds_a, pos_b, bounds_b)
            
            # Penalize if too close
            violation = jax.nn.relu(rule.min_separation_mm - edge_dist)
            total_penalty += rule.weight * violation**2
        
        return LossResult(value=total_penalty, breakdown={"component_spacing": total_penalty})
```

### 5. Register Loss in Pipeline
**File**: `packages/temper-placer/src/temper_placer/losses/__init__.py`

Add to loss registry and ensure it's instantiated in the optimization pipeline.

## Testing
1. Run placement with updated config
2. Verify D2-C_BUS2 spacing > 3.0mm
3. Verify all HV pairs meet 2.0mm minimum
4. Check that violations produce non-zero loss

## Priority
**P1** - This prevents the exact issue found in temper-2edy.10 from recurring.

## Estimated Effort
~2-3 hours for implementation + testing
