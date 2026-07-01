---
title: "Pattern: PCL Constraint System Extension with PBT-Verified Semantic Bridge"
date: 2026-07-01
category: architecture-patterns
module: temper-placer
problem_type: architecture_pattern
component: tooling
severity: high
applies_when:
  - "Extending a physical constraint language (PCL) with new constraint types that must coexist with existing loss functions, YAML parsers, DRC checks, and CLI pipelines"
  - "Adding semantic tag dispatch where tags form a hierarchy and constraints express membership queries over that hierarchy"
  - "Auto-detecting component roles (e.g., decoupling capacitors) from netlist topology where manual annotation doesn't scale"
  - "Bridging geometry-level constraints (keepout zones) into gradient-based optimization via signed-distance fields with tiered penalty weights"
tags:
  - pcl-constraints
  - semantic-tag-dispatch
  - decoupling-detection
  - keepout-zone
  - property-based-testing
  - bounded-model-checking
  - induction-ladder
---
# Pattern: PCL Constraint System Extension with PBT-Verified Semantic Bridge

## Context

The Temper placer's Physical Constraint Language (PCL) needed three new
constraint families that operate at different semantic levels — component roles
(decoupling capacitors), net-class membership (tag dispatch), and geometric
exclusion (keepout zones). Each family required:

1. A **loss function** that produces differentiable penalties fed into the
   gradient-based optimizer
2. A **YAML parser** so users can declare constraints declaratively
3. A **pipeline bridge** so constraints are auto-detected or parsed into the
   optimizer's `WeightedLoss → CompositeLoss` compilation chain
4. A **verification suite** proving correctness at both the unit (PBT) and
   integration (BMC, induction) levels

The risk: adding constraints without structural patterns leads to ad-hoc wiring,
silent semantic mismatches between YAML tags and internal enums, and
unverifiable correctness.

## Guidance

### 1. Canonical SSOT Enums for Component Roles

Define a single enum as the canonical source of truth for every classification
dimension. Avoid scattering classification constants across helper functions.

```python
# losses/decoupling_types.py — canonical classification
class DecouplingClass(Enum):
    BYPASS = ("bypass", 3.0, "HARD")    # 3mm distance, hard enforcement
    BULK = ("bulk", 20.0, "STRONG")     # 20mm distance, strong enforcement

    def __init__(self, label: str, max_distance_mm: float, tier: str):
        self.label = label
        self.max_distance_mm = max_distance_mm
        self.tier = tier
```

Every consumer — the detection algorithm, the loss function, the tier-weight
mapper — imports from this single enum. No consumer defines its own notion of
"bypass" vs "bulk."

### 2. Net-Class Detection with Priority Merge

When auto-detecting decoupling capacitors from the netlist, multiple net
classes may be assigned to the same net. Resolve conflicts with a deterministic
priority merge rather than first-match or last-match.

```python
# losses/decoupling.py — priority-ordered merge
_NET_CLASS_PRIORITY: dict[str, int] = {
    "Power": 0, "HighVoltage": 1, "Ground": 2, "Signal": 3,
}

def _build_net_class_map(netlist) -> dict[str, str]:
    """Assign each net to its highest-priority class. Lower number wins."""
    ...
```

This guarantees idempotence: re-running detection on the same netlist always
produces the same classification, regardless of net iteration order.

### 3. Component Topology Heuristics

Define ground-truth predicates that encode the physical design intent. These
predicates serve dual roles: they drive detection, and they serve as the oracle
for BMC/ESL verification.

```python
def _is_capacitor(part) -> bool:
    """Reference designator prefix or footprint pattern match."""

def _is_ic(part) -> bool:
    """IC if pin count >= 4."""

def _shared_vital_net(part_a, part_b) -> str | None:
    """Returns the net name if both parts share a Power/Ground net."""

def _esl_is_decoupling(part, ic, net) -> bool:
    """Ground-truth predicate: capacitor, shares vital net with IC, within
    class max-distance. Used as BMC oracle."""
```

The ESL (executable specification language) predicate enables bounded model
checking across all ≤N-component layouts to prove the detector never classifies
a non-decoupling component as decoupling.

### 4. Hierarchical Tag Dispatch with Floyd-Warshall Closure

Tags form a hierarchy. Clients express queries as boolean expressions over
tags. The dispatcher resolves tag membership through transitive closure.

```python
# pcl/tag_dispatch.py — tag hierarchy and expression algebra
class ComponentTag(Enum):
    POWER = "power"
    SIGNAL = "signal"
    MECHANICAL = "mechanical"
    # ... 14 tags total

# Parent → child relationships
_TAG_HIERARCHY_UP: dict[ComponentTag, frozenset[ComponentTag]] = { ... }

# Floyd-Warshall transitive closure computed at module load
_TAG_CLOSURE = _transitive_closure()
```

Expression algebra uses frozen dataclasses for hashability (needed for PBT
shrink strategies):

```python
@dataclass(frozen=True)
class TagRef:
    tag: ComponentTag
@dataclass(frozen=True)
class TagAnd:
    operands: tuple[TagExpr, ...]
@dataclass(frozen=True)
class TagOr:
    operands: tuple[TagExpr, ...]
@dataclass(frozen=True)
class TagNot:
    operand: TagExpr

TagExpr = TagRef | TagAnd | TagOr | TagNot | ComponentRef
```

The `E()` expansion function resolves a `TagExpr` into a concrete set of
component references, with a `max_expansion=500` guard to prevent
combinatorial explosion. YAML syntax: `{tag: power}`, `{and: [{tag: power}, {not: {tag: mechanical}}]}`, `{or: [{tag: decoupling}, {tag: ferrite}]}`.

### 5. Signed-Distance Keepout Loss with Smooth ReLU

Keepout zones define rectangular AABBs that components must stay outside.
Convert the geometric constraint into a differentiable penalty using a smooth
ReLU over the signed distance field:

```python
# pcl/loss_bridge.py — keepout loss
def keepout_to_loss(constraint, netlist, board):
    """Signed-distance penalty: zero if outside, positive if inside.
    Uses smooth_relu_penalty from geometry/smooth.py for gradient continuity."""
    # AABB signed-distance computation per-axis
    gap_x = max(zone.x_min - comp.x_max, comp.x_min - zone.x_max)
    gap_y = max(zone.y_min - comp.y_max, comp.y_min - zone.y_max)
    d = max(gap_x, gap_y) if separated else min(gap_x, gap_y)
    return smooth_relu_penalty(margin - d)
```

`smooth_relu_penalty` from `geometry/smooth.py` provides a continuous gradient
at the boundary, critical for gradient-based optimizers that would otherwise
see a zero-gradient cliff at the keepout edge.

### 6. Per-Tier Weight Mapping

Every constraint is classified into a tier with a corresponding loss weight.
Centralize the tier→weight mapping so all constraint types use consistent
penalty scaling:

```python
TIER_WEIGHTS = {ConstraintTier.HARD: 1e6, ConstraintTier.STRONG: 1e3, ConstraintTier.SOFT: 1e1}
```

Both decoupling constraints (`BYPASS=HARD, BULK=STRONG`) and keepout zones
(tier from YAML) pass through this same mapping during `constraint_to_loss()`
compilation in the `make_loss()` closure.

### 7. PBT-Verified Semantic Bridge

Each constraint family is verified with a property-based test suite following
the same structure:

| Layer | What it proves | Technique |
|-------|---------------|-----------|
| Unit PBT | Idempotence, hash stability, De Morgan, resolution soundness, tier monotonicity, expansion correctness | Hypothesis `@given` with custom strategies |
| BMC | Detector never produces false positives (exhaustive enumeration over ≤N component layouts) | `_esl_is_decoupling()` oracle |
| Induction Ladder | Invariants hold under add/remove/modify operations | Hypothesis state-machine testing |
| Integration | End-to-end regression on the Temper board | Golden-fixture comparison |

### 8. Pipeline Wiring Through Bridge Objects

Each constraint family plugs into the pipeline through a dedicated bridge
module, not through direct `import` chains:

```python
# pcl/loss_bridge.py — constraint-to-loss compilation
def constraint_to_loss(constraint, netlist, board=None) -> LossFunction:
    """Dispatch a PCL constraint to its loss function."""

# pcl/drc_bridge.py — constraint-to-DRC-check mapping  
TYPE_HANDLERS[ConstraintType.KEEPOUT] = _keepout_to_drc
```

The YAML parser (`load_constraints()`) auto-emits constraints from zone
definitions. Decoupling detection runs automatically during `optimize` CLI and
pipeline stages — no manual annotation required.

### 9. Formal Design Before Implementation

The design process follows a mathematical-formalization-first order:

1. **Mathematical formalization**: Write constraints, loss functions, and
   invariants as mathematical propositions before any code
2. **Adversarial document review**: Subject the formalization to peer review
   focused on edge cases and counterexamples
3. **P0/P1 fix rounds**: Address critical and important issues before implementation
4. **Implementation**: Code follows the formalization exactly
5. **Verification**: PBT, BMC, induction ladders, and integration tests prove
   correctness against the formal spec

## Consequences

- **43 new tests** across PBT, BMC, induction, and integration suites
- BMC exhaustiveness guarantee: no false positives for any layout ≤3 components
- Induction ladder guarantee: invariants preserved under add/remove/modify
- 5 design documents with formal theorems in `docs/plans/`
