# Refined Explainability Architecture

## Critique of Original Design

### Issues Identified

**1. Too Much Boilerplate**
```python
# Original: 10+ fields to populate every time
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

**2. Coupling Business Logic with Logging**
- `if decision_trace:` checks scattered throughout code
- Router and optimizer must know about tracing internals
- Violates single responsibility

**3. Mutable State**
- `trace.add()` mutates a list
- Hard to parallelize or test
- State threading through functions

**4. Repeated Patterns**
- Same `if trace: trace.add(...)` pattern everywhere
- NL generation functions duplicated for each decision type
- Not composable

**5. YAGNI Violations**
- HTML viewer, conflict detection, timeline - all complex features
- Build before knowing if simpler approach works

---

## Refined Architecture

### Core Insight: Decisions are Just Annotated Values

Instead of a complex `Decision` class with many fields, use a simple wrapper:

```python
# A decision is just: value + why
Traced = tuple[T, str]  # (value, reason)

# Or as a simple dataclass
@dataclass(frozen=True)
class Traced(Generic[T]):
    value: T
    because: str
    constraint: str | None = None
```

### Design Principles

1. **Pure Functions** - No mutation, return traced values
2. **Context Propagation** - Use context managers, not explicit passing
3. **Lazy Explanation** - Generate NL only when queried
4. **Composable Traces** - Combine traces like monoids

---

## Simplified Implementation

### 1. The `@traced` Decorator (Zero Boilerplate)

```python
from contextvars import ContextVar
from functools import wraps

# Global context for trace collection
_trace_context: ContextVar[list] = ContextVar("trace", default=[])

def traced(reason_fn=None):
    """Decorator to automatically trace function outputs."""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            result = fn(*args, **kwargs)
            
            # Generate reason lazily
            reason = reason_fn(args, kwargs, result) if reason_fn else fn.__doc__
            
            # Add to context trace
            ctx = _trace_context.get()
            ctx.append({
                "fn": fn.__name__,
                "result": result,
                "reason": reason,
            })
            
            return result
        return wrapper
    return decorator

# Usage: Zero changes to function signature!
@traced(lambda args, kw, r: f"Moved to {r} for proximity constraint")
def compute_position(component, constraints):
    """Position based on constraints."""
    # ... compute position ...
    return (x, y)
```

### 2. Context Manager for Scoped Tracing

```python
from contextlib import contextmanager

@contextmanager
def tracing():
    """Context manager for collecting traces."""
    trace = []
    token = _trace_context.set(trace)
    try:
        yield trace
    finally:
        _trace_context.reset(token)

# Usage
with tracing() as trace:
    optimize(components, constraints)
    route(nets)

print(trace.why("Q1"))  # Explains all decisions for Q1
```

### 3. Composable Trace (Monoid)

```python
@dataclass(frozen=True)
class Trace:
    """Immutable, composable trace."""
    entries: tuple[Entry, ...] = ()
    
    def __add__(self, other: "Trace") -> "Trace":
        return Trace(self.entries + other.entries)
    
    @staticmethod  
    def empty() -> "Trace":
        return Trace(())
    
    def add(self, subject: str, value: Any, because: str) -> "Trace":
        """Return NEW trace with entry added (immutable)."""
        return Trace(self.entries + (Entry(subject, value, because),))
    
    def for_subject(self, subject: str) -> "Trace":
        """Filter to specific subject."""
        return Trace(tuple(e for e in self.entries if e.subject == subject))
    
    def why(self, subject: str) -> str:
        """Generate natural language explanation."""
        entries = self.for_subject(subject).entries
        if not entries:
            return f"No decisions for {subject}"
        
        final = entries[-1]
        reasons = [e.because for e in entries]
        
        return f"{subject} is at {final.value} because:\n" + \
               "\n".join(f"  - {r}" for r in reasons[:3])
```

### 4. The `because` Propagates Naturally

Instead of generating NL reasons, let constraints carry their `because`:

```python
# PCL constraint already has 'because'
@dataclass
class Adjacent:
    a: str
    b: str
    max_distance_mm: float
    because: str  # Already exists!
    
    def compute_loss(self, positions) -> Traced[float]:
        distance = compute_distance(self.a, self.b, positions)
        loss = max(0, distance - self.max_distance_mm) ** 2
        # Return traced loss with constraint's 'because'
        return (loss, self.because)

# Loss aggregation preserves reasons
def total_loss(constraints, positions) -> Traced[float]:
    losses = [c.compute_loss(positions) for c in constraints]
    # Combine: (total, top reasons)
    total = sum(l[0] for l in losses)
    top_reasons = sorted(losses, key=lambda x: -x[0])[:3]
    return (total, [l[1] for l in top_reasons])
```

### 5. Router: Return Traced Paths

```python
def find_path(start, end, layer_stackup) -> Traced[Path]:
    """Find path, returning reason for layer choices."""
    allowed = layer_stackup.routable_layers("Signal")
    path = a_star(start, end, allowed)
    
    # Build reason from path characteristics
    via_count = count_vias(path)
    if via_count > 0:
        reason = f"Used {via_count} vias to navigate obstacles"
    else:
        reason = f"Direct path on L{path[0].layer}"
    
    return (path, reason)
```

---

## Functional Pipeline

The optimizer/router become pure pipelines that accumulate traces:

```python
def optimize(components, constraints) -> tuple[Positions, Trace]:
    """Pure optimization returning positions and trace."""
    trace = Trace.empty()
    positions = initial_positions(components)
    
    for epoch in range(epochs):
        # Compute traced losses
        losses = [(c.compute_loss(positions), c) for c in constraints]
        
        # Gradient step
        new_positions = gradient_step(positions, losses)
        
        # Immutable trace accumulation
        for i, comp in enumerate(components):
            if moved_significantly(positions[i], new_positions[i]):
                active = [c for l, c in losses if affects(c, comp)]
                trace = trace.add(
                    subject=comp.ref,
                    value=tuple(new_positions[i]),
                    because=active[0].because if active else "wirelength",
                )
        
        positions = new_positions
    
    return positions, trace

def route(nets, positions, layer_stackup) -> tuple[Routes, Trace]:
    """Pure routing returning routes and trace."""
    trace = Trace.empty()
    routes = {}
    
    for net in nets:
        path, reason = find_path(net.pins, layer_stackup)
        routes[net.name] = path
        trace = trace.add(net.name, path, reason)
    
    return routes, trace
```

---

## Full Pipeline (Composable)

```python
# Run entire pipeline
def run_pipeline(pcb, pcl) -> tuple[Result, Trace]:
    # Each phase returns (result, trace)
    positions, trace1 = optimize(pcb.components, pcl.constraints)
    routes, trace2 = route(pcb.nets, positions, pcl.layer_stackup)
    
    # Compose traces (monoid!)
    trace = trace1 + trace2
    
    return Result(positions, routes), trace

# Usage
result, trace = run_pipeline(pcb, pcl)

# Query
print(trace.why("Q1"))
print(trace.why("VCC"))

# Export
save_report(trace.to_markdown())
```

---

## Benefits of Refined Design

### DRY
- No repeated `if trace: trace.add(...)` patterns
- Constraints carry their `because` - no regeneration
- One `Trace` class for all phases

### YAGNI
- Start with simple `Trace.why()` - no HTML/timeline
- Add features only when needed
- Simpler = easier to maintain

### Functional
- Pure functions return `(result, trace)` tuples
- Immutable `Trace` via `trace = trace.add(...)`
- No global mutable state

### Composable  
- `trace1 + trace2` combines phases
- `trace.for_subject("Q1")` filters
- Traces are monoids: `empty + x = x`, `(a + b) + c = a + (b + c)`

### Easy to Reason About
- Function signature tells you it traces: `-> (T, Trace)`
- No hidden state mutations
- Test traces in isolation

### Zero Boilerplate (with decorator)
```python
@traced
def optimize(...):
    # No explicit trace handling
    # Decorator captures inputs/outputs
```

---

## Migration Path

1. **Start Simple**: Just `Trace` class with `add()` and `why()`
2. **Add Decorator**: Reduce boilerplate in hot paths
3. **Compose Phases**: Connect optimizer → router traces
4. **Query Interface**: `trace.why(subject)` with NL
5. **Reports**: Markdown/HTML only if needed

---

## Comparison

| Aspect | Original | Refined |
|--------|----------|---------|
| Lines per decision | ~15 | ~3 |
| Mutation | `trace.add()` | `trace = trace.add()` |
| Coupling | High (if/else everywhere) | Low (return values) |
| NL Generation | Eager (per decision) | Lazy (on query) |
| Composability | None | Monoid operations |
| Testing | Hard (mock trace) | Easy (compare traces) |
| YAGNI | HTML viewer, timeline | Just `why()` |

---

## Example: Before vs After

### Before (Original)
```python
def train(..., decision_trace: DecisionTrace | None = None):
    for epoch in range(num_epochs):
        # ... optimization ...
        
        if decision_trace and epoch % log_interval == 0:
            for i, comp in enumerate(components):
                if position_changed_significantly(i):
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

### After (Refined)
```python
def train(components, constraints) -> tuple[Positions, Trace]:
    trace = Trace.empty()
    
    for epoch in range(num_epochs):
        positions, epoch_trace = train_epoch(components, constraints, positions)
        trace = trace + epoch_trace
    
    return positions, trace

def train_epoch(components, constraints, positions) -> tuple[Positions, Trace]:
    # Pure function, returns traced result
    new_positions = gradient_step(...)
    
    movements = [
        (comp.ref, new_positions[i], constraint.because)
        for i, comp in enumerate(components)
        if moved(positions[i], new_positions[i])
        for constraint in active_constraints(comp, constraints)
    ]
    
    return new_positions, Trace.from_entries(movements)
```

**80% less boilerplate, 100% more composable.**
