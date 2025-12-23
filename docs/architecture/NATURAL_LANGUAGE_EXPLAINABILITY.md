# Natural Language Explainability for Placer and Router

## Overview

Extend the existing `DecisionTrace` system to provide natural language explanations for every placement and routing decision, connecting PCL constraints (`because` field) to optimizer and router actions.

## Current State

### ✅ Already Exists

**Explainability Infrastructure:**
- `Decision` - Single auditable decision with reason
- `DecisionTrace` - Complete audit trail
- `DecisionType` - Types of decisions (placement, rotation, routing)
- `DecisionPhase` - Pipeline phases (semantic, topological, geometric, routing)
- Markdown and HTML report generation
- JSON serialization

**PCL `because` Field:**
- Every constraint has mandatory `because` field (≥10 chars)
- Examples:
  - `"Minimize commutation loop for half-bridge"`
  - `"IEC 60335-1 reinforced isolation requirement"`
  - `"Thermal edge constraint requires IGBT within 5mm of top edge"`

### ❌ Not Connected

- Optimizer doesn't emit `Decision` objects
- Router doesn't emit `Decision` objects
- No link between PCL `because` and optimizer/router decisions
- No natural language generation for complex decisions

## Proposed Extensions

### 1. Optimizer Decision Logging

**What:** Emit `Decision` objects during optimization to explain placement choices.

**Implementation:**

```python
# In optimizer/train.py
def train(..., decision_trace: DecisionTrace | None = None):
    for epoch in range(num_epochs):
        # ... optimization step ...
        
        if decision_trace and epoch % log_interval == 0:
            # Log significant position changes
            for i, comp in enumerate(components):
                if position_changed_significantly(i):
                    # Find which constraints influenced this move
                    active_constraints = find_active_constraints(i, constraints)
                    
                    decision_trace.add(Decision(
                        phase=DecisionPhase.GEOMETRIC,
                        decision_type=DecisionType.POSITION_UPDATE,
                        subject=comp.ref,
                        value=(positions[i, 0], positions[i, 1]),
                        previous_value=(prev_positions[i, 0], prev_positions[i, 1]),
                        reason=generate_position_reason(comp, active_constraints),
                        constraint_refs=[c.id for c in active_constraints],
                        loss_contribution=loss_delta[i],
                        epoch=epoch,
                    ))
```

**Natural Language Generation:**

```python
def generate_position_reason(comp, constraints):
    """Generate human-readable reason for position update."""
    if not constraints:
        return f"Moved {comp.ref} to reduce wirelength"
    
    # Primary constraint (highest tier or largest loss contribution)
    primary = max(constraints, key=lambda c: (c.tier, c.loss_contribution))
    
    # Use the constraint's 'because' field
    return f"{comp.ref} moved to satisfy: {primary.because}"

# Examples:
# "Q1 moved to satisfy: Minimize commutation loop for half-bridge"
# "C1 moved to satisfy: Decoupling cap must be within 5mm of U1"
# "J1 moved to satisfy: Connectors must be on left edge for external access"
```

### 2. Router Decision Logging

**What:** Emit `Decision` objects during routing to explain path choices.

**Implementation:**

```python
# In routing/maze_router.py
class MazeRouter:
    def __init__(self, ..., decision_trace: DecisionTrace | None = None):
        self.decision_trace = decision_trace
    
    def route_net(self, net_name, pins, net_class='Signal'):
        # Determine layer assignment
        allowed_layers = self.layer_stackup.routable_layers(net_class)
        
        if self.decision_trace:
            self.decision_trace.add(Decision(
                phase=DecisionPhase.ROUTING,
                decision_type=DecisionType.LAYER_ASSIGNMENT,
                subject=net_name,
                value=allowed_layers,
                reason=generate_layer_reason(net_class, allowed_layers),
            ))
        
        # Route path
        path = self.find_path(...)
        
        if self.decision_trace and path:
            # Log via placements
            for i, cell in enumerate(path):
                if i > 0 and cell.layer != path[i-1].layer:
                    self.decision_trace.add(Decision(
                        phase=DecisionPhase.ROUTING,
                        decision_type=DecisionType.VIA_PLACEMENT,
                        subject=net_name,
                        value=(cell.x, cell.y, cell.layer),
                        reason=generate_via_reason(path, i),
                    ))
```

**Natural Language Generation:**

```python
def generate_layer_reason(net_class, allowed_layers):
    """Explain layer assignment."""
    if net_class == "HighVoltage":
        return "HV net restricted to L1 (2oz copper for current capacity)"
    elif net_class == "Power":
        return "Power net can route on signal layers L1, L4"
    else:
        return f"Signal net can route on {len(allowed_layers)} routable layers"

def generate_via_reason(path, via_index):
    """Explain why a via was placed."""
    cell = path[via_index]
    prev_layer = path[via_index - 1].layer
    
    # Check if via was necessary (obstacle avoidance)
    if was_blocked_on_same_layer(cell, prev_layer):
        return f"Via to L{cell.layer} to avoid obstacle on L{prev_layer}"
    else:
        return f"Via to L{cell.layer} for shorter path (via cost: {via_cost})"
```

### 3. Constraint Traceability

**What:** Link every optimizer/router decision back to the PCL constraint that caused it.

**Implementation:**

```python
@dataclass
class Constraint:
    id: str  # Auto-generated: "adj-Q1-U1"
    because: str  # User-provided rationale
    tier: int
    # ... other fields ...

# During optimization
def compute_loss(positions, constraints):
    for constraint in constraints:
        loss_value = constraint.compute_loss(positions)
        
        # Track which components are affected
        affected_components = constraint.get_affected_components()
        
        # Store for decision logging
        constraint.loss_contribution = loss_value
        constraint.affected_components = affected_components
    
    # Later, when logging decisions:
    active_constraints = [c for c in constraints 
                         if comp.ref in c.affected_components 
                         and c.loss_contribution > threshold]
```

**Trace Output:**

```markdown
## Decision: Q1 Position Update

**Epoch:** 150  
**Position:** (45.2, 12.3) → (43.8, 11.9)  
**Loss Improvement:** -2.3

**Reason:**  
Q1 moved to satisfy constraint `adj-Q1-U_GATE`:
> "Minimize gate drive loop inductance"

**Constraint Details:**
- Type: Adjacent
- Tier: 1 (Hard)
- Max Distance: 15mm
- Current Distance: 14.2mm (was 16.8mm)
```

### 4. Natural Language Query Interface

**What:** Allow users to ask "Why is Q1 here?" and get a natural language answer.

**Implementation:**

```python
class DecisionTrace:
    def why(self, subject: str, natural_language: bool = True) -> str:
        """Explain why a component is where it is."""
        decisions = self.get_decisions_for(subject)
        
        if not decisions:
            return f"No decisions recorded for {subject}"
        
        if natural_language:
            return self._generate_natural_language_explanation(subject, decisions)
        else:
            return self._generate_technical_explanation(subject, decisions)
    
    def _generate_natural_language_explanation(self, subject, decisions):
        """Generate human-friendly explanation."""
        # Get final position
        final_decision = decisions[-1]
        
        # Get primary constraints
        constraints = self._get_constraints_for_decisions(decisions)
        
        # Generate explanation
        lines = [
            f"{subject} is at ({final_decision.value[0]:.1f}, {final_decision.value[1]:.1f}).",
            "",
            "This placement was determined by:",
        ]
        
        for i, constraint in enumerate(constraints[:3], 1):  # Top 3
            lines.append(f"{i}. {constraint.because}")
        
        if len(decisions) > 1:
            lines.append("")
            lines.append(f"The optimizer made {len(decisions)} adjustments over {final_decision.epoch} epochs.")
        
        return "\n".join(lines)
```

**Example Queries:**

```python
>>> trace.why("Q1")
Q1 is at (45.2, 12.3).

This placement was determined by:
1. Minimize commutation loop for half-bridge (with Q2)
2. Thermal edge constraint requires IGBT within 5mm of top edge
3. HV isolation: maintain 10mm from MCU zone

The optimizer made 23 adjustments over 500 epochs.

>>> trace.why("VCC", net=True)
VCC net routes on layers L1, L4.

Routing decisions:
1. Layer assignment: Power net can route on signal layers L1, L4
2. Via at (23.4, 15.2): Via to L4 to avoid obstacle on L1
3. Path length: 45.3mm (estimated: 42.1mm, 7.6% longer due to obstacles)

>>> trace.why_via("VCC", (23.4, 15.2))
Via placed at (23.4, 15.2) on net VCC:
- From layer L1 to L4
- Reason: Via to L4 to avoid obstacle on L1 (component U1)
- Via cost: 5.0 (added to path cost)
```

### 5. Interactive HTML Viewer

**What:** Enhance existing HTML viewer with natural language explanations.

**Current:** HTML viewer shows decision table  
**Enhanced:** Add natural language summary cards

```html
<div class="explanation-card">
  <h3>Q1 Placement</h3>
  <p class="summary">
    Q1 is at (45.2, 12.3) to minimize the commutation loop with Q2.
  </p>
  
  <details>
    <summary>Why this location?</summary>
    <ul>
      <li><strong>Primary:</strong> Minimize commutation loop for half-bridge (Tier 1)</li>
      <li><strong>Secondary:</strong> Thermal edge constraint (Tier 1)</li>
      <li><strong>Tertiary:</strong> HV isolation from MCU (Tier 1)</li>
    </ul>
  </details>
  
  <details>
    <summary>Optimization history</summary>
    <p>23 position updates over 500 epochs</p>
    <ul>
      <li>Epoch 0: (50.0, 15.0) - Initial spectral placement</li>
      <li>Epoch 150: (45.2, 12.3) - Moved to satisfy adjacency constraint</li>
      <li>Epoch 500: (45.2, 12.3) - Converged</li>
    </ul>
  </details>
</div>
```

### 6. Conflict Resolution Explanations

**What:** Explain why constraints conflict and how they were resolved.

**Implementation:**

```python
def detect_constraint_conflicts(constraints):
    """Find contradictory constraints."""
    conflicts = []
    
    for c1, c2 in combinations(constraints, 2):
        if are_contradictory(c1, c2):
            conflicts.append(ConstraintConflict(
                constraint1=c1,
                constraint2=c2,
                reason=explain_conflict(c1, c2),
                resolution=suggest_resolution(c1, c2),
            ))
    
    return conflicts

def explain_conflict(c1, c2):
    """Generate natural language conflict explanation."""
    if isinstance(c1, Adjacent) and isinstance(c2, Separated):
        if c1.a == c2.a and c1.b == c2.b:
            return (
                f"Constraint '{c1.id}' requires {c1.a} and {c1.b} to be "
                f"within {c1.max_distance_mm}mm, but constraint '{c2.id}' "
                f"requires them to be at least {c2.min_distance_mm}mm apart."
            )
```

**Example Output:**

```markdown
## ⚠️ Constraint Conflict Detected

**Conflict:** `adj-Q1-Q2` vs `sep-Q1-Q2`

**Explanation:**
Constraint 'adj-Q1-Q2' requires Q1 and Q2 to be within 15mm 
(because: "Minimize commutation loop for half-bridge"), 
but constraint 'sep-Q1-Q2' requires them to be at least 20mm apart 
(because: "Thermal isolation between IGBTs").

**Resolution:**
These constraints are contradictory. Please either:
1. Relax the adjacency constraint to >20mm, or
2. Reduce the separation constraint to <15mm, or
3. Remove one of the constraints

**Current Behavior:**
Optimizer will prioritize the higher-tier constraint (both are Tier 1).
```

## Implementation Plan

### Phase 1: Optimizer Integration (P2)

1. Add `decision_trace` parameter to `train()`
2. Emit `Decision` for significant position updates
3. Link decisions to active constraints
4. Generate natural language reasons using constraint `because` fields

### Phase 2: Router Integration (P2)

1. Add `decision_trace` parameter to `MazeRouter`
2. Emit `Decision` for layer assignments
3. Emit `Decision` for via placements
4. Generate natural language routing explanations

### Phase 3: Natural Language Query (P3)

1. Implement `DecisionTrace.why(subject)`
2. Implement `DecisionTrace.why_via(net, position)`
3. Add natural language generation helpers
4. Add constraint conflict detection

### Phase 4: Enhanced Visualization (P3)

1. Add explanation cards to HTML viewer
2. Add optimization history timeline
3. Add constraint dependency graph
4. Add "What if?" scenario explorer

## Benefits

### For Engineers

**Debugging:**
```
Q: "Why did the optimizer put Q1 so far from Q2?"
A: "Q1 moved away from Q2 to satisfy thermal isolation constraint: 
    'Thermal isolation between IGBTs requires 20mm spacing'"
```

**Validation:**
```
Q: "Is the HV isolation requirement being met?"
A: "Yes. All HV components (Q1, Q2, D1) maintain 10mm from MCU zone 
    as required by constraint 'hv-isolation': 
    'IEC 60335-1 reinforced isolation requirement'"
```

**Learning:**
```
Q: "Why did the router use a via here?"
A: "Via placed to avoid component U1 on L1. 
    Routing on L4 was 3.2mm shorter despite via cost of 5.0."
```

### For Auditing

**Traceability:**
- Every placement decision traces back to PCL constraint
- Every constraint has engineer-provided rationale
- Complete audit trail from requirement → constraint → decision

**Compliance:**
- Safety requirements (IEC 60335-1) explicitly documented
- Design decisions justified with engineering rationale
- Automated compliance report generation

## Example: Complete Explanation Chain

**PCL Constraint:**
```yaml
- type: adjacent
  a: Q1
  b: Q2
  max_distance_mm: 15
  tier: 1
  because: "Minimize commutation loop for half-bridge to reduce radiated EMI"
```

**Optimizer Decision:**
```python
Decision(
    phase=DecisionPhase.GEOMETRIC,
    decision_type=DecisionType.POSITION_UPDATE,
    subject="Q1",
    value=(45.2, 12.3),
    previous_value=(50.0, 15.0),
    reason="Q1 moved to satisfy: Minimize commutation loop for half-bridge to reduce radiated EMI",
    constraint_refs=["adj-Q1-Q2"],
    loss_contribution=-2.3,
    epoch=150,
)
```

**Natural Language Query:**
```python
>>> trace.why("Q1")
Q1 is at (45.2, 12.3).

This placement was determined by:
1. Minimize commutation loop for half-bridge to reduce radiated EMI (with Q2)
2. Thermal edge constraint requires IGBT within 5mm of top edge
3. HV isolation: IEC 60335-1 reinforced isolation requirement

The optimizer made 23 adjustments over 500 epochs to satisfy these constraints.
```

**HTML Report:**
![Q1 Explanation Card showing position, constraints, and optimization history]

## Next Steps

1. Create tasks for each phase
2. Start with Phase 1 (optimizer integration)
3. Add tests for natural language generation
4. Iterate on explanation quality with user feedback
