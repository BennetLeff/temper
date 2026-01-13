# Router V6: Multilayer Board Analysis

## Current State in Plan

The plan mentions "layer assignment" 11 times but treats layers as a simple integer index. This is insufficient for real multilayer boards.

**What the plan says:**
```python
layer[n]: Layer  # Primary layer assignment (integer 0-3)
```

**What's missing:** Everything else about multilayer design.

---

## Gap Analysis: What Multilayer Boards Actually Need

### 1. Stackup Definition (NOT IN PLAN)

A 4-layer board isn't just "4 copper layers." It's a specific physical structure:

```
┌─────────────────────────────────────────────────────────────────┐
│                    TYPICAL 4-LAYER STACKUP                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   Layer 1 (F.Cu)    ───────────────────  Signal/Component       │
│   Prepreg           ≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈  0.2mm (dielectric)    │
│   Layer 2 (In1.Cu)  ───────────────────  GND Plane              │
│   Core              ████████████████████  1.0mm (FR4 core)      │
│   Layer 3 (In2.Cu)  ───────────────────  Power Plane (+15V)     │
│   Prepreg           ≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈  0.2mm (dielectric)    │
│   Layer 4 (B.Cu)    ───────────────────  Signal/Component       │
│                                                                 │
│   Total thickness: ≈1.6mm                                       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Why it matters:**
- Impedance depends on trace width + dielectric thickness + reference plane
- Signal integrity requires knowing which layer is the "reference" for a trace
- Crosstalk depends on layer spacing

### 2. Via Types (NOT IN PLAN)

The plan assumes all vias are the same. Real boards have:

| Via Type | Connects | Cost | Use Case |
|----------|----------|------|----------|
| **Through-hole** | All layers (L1→L4) | Low | Default, widely supported |
| **Blind** | Surface to inner (L1→L2) | Medium | BGA escape, HDI |
| **Buried** | Inner to inner (L2→L3) | High | Complex HDI only |
| **Microvia** | Adjacent layers only | Medium | Fine-pitch BGA |

```
THROUGH VIA:        BLIND VIA:         BURIED VIA:        MICROVIA:
    L1 ●───────        L1 ●───────        L1 ─────────        L1 ●─────
       │                  │                  │                   │
    L2 ●               L2 ●               L2 ●───────        L2 ●─────
       │                  ╳                  │                   ╳
    L3 ●               L3 ─               L3 ●               L3 ─────
       │                  ╳                  ╳                   ╳
    L4 ●───────        L4 ─────────        L4 ─────────        L4 ─────
```

**Impact on routing:**
- Through vias block ALL layers (waste inner layer routing space)
- Blind/buried vias cost more but preserve routing channels
- Microvia has aspect ratio limits (depth ≤ diameter)

### 3. Power/Ground Planes (PARTIALLY IN PLAN)

The plan mentions GND plane but doesn't architect it:

**Current:** "GND on In1.Cu, +15V on In2.Cu"

**Missing:**
- How do signals cross plane splits?
- Where are plane-to-plane vias (stitching)?
- How to handle multiple power domains?
- Anti-pad sizing for signal vias?

```
PLANE SPLIT PROBLEM:

    ┌────────────────┬────────────────┐
    │                │                │
    │    +3.3V       │     +5V        │  ← Power plane with split
    │                │                │
    └────────────────┴────────────────┘
              ↑
        Signal crossing here needs
        return path stitching vias
```

### 4. Layer Assignment Rules (IMPLICIT IN PLAN)

The plan says "topology assigns layers" but doesn't specify rules:

**Standard rules for 4-layer signal integrity:**

| Signal Type | Preferred Layer | Reference Plane | Why |
|-------------|-----------------|-----------------|-----|
| High-speed digital | L1 or L4 | Adjacent GND (L2) | Controlled impedance |
| Low-speed digital | Any | Any plane | Less critical |
| Analog/sensitive | L1 | L2 (GND) | Noise isolation |
| Power traces | L1/L4 or plane | N/A | Current capacity |
| High-voltage | L1/L4 only | N/A | Creepage on surface |

**Layer pairing for differential pairs:**
- Both P and N on same layer (always)
- Reference plane must be continuous under both traces
- No plane splits under diff pair

### 5. Reference Plane Continuity (NOT IN PLAN)

High-speed signals need a continuous reference plane:

```
GOOD:                              BAD:
Signal ════════════════════        Signal ════════════════════
       ↓ return current ↓                 ↓ return current ↓
Plane  ████████████████████        Plane  ████████╳╳╳█████████
                                                  ↑
                                            Slot in plane!
                                            Return current detours,
                                            causes EMI
```

**Router must check:**
- Is there a continuous plane under this trace?
- If plane has split, is there a stitching via nearby?
- Does the via anti-pad break the return path?

### 6. Via Aspect Ratio (NOT IN PLAN)

Drill depth / diameter must be ≤ fab capability:

| Via Type | Typical Aspect Ratio | Example |
|----------|---------------------|---------|
| Through (standard) | 10:1 | 1.6mm deep, 0.2mm drill |
| Through (HDI) | 12:1 | 1.6mm deep, 0.15mm drill |
| Microvia | 1:1 max | 0.15mm deep, 0.15mm drill |
| Blind | 1:1 typical | 0.2mm deep, 0.2mm drill |

**Impact:** Can't use 0.1mm microvia to connect L1→L3 (too deep).

### 7. Impedance Control (NOT IN PLAN)

Trace width for impedance depends on stackup:

```python
def microstrip_impedance(
    width_mm: float,
    height_mm: float,  # Distance to reference plane
    er: float = 4.3,   # FR4 dielectric constant
    thickness_mm: float = 0.035  # 1oz copper
) -> float:
    """Calculate microstrip impedance (outer layer trace over plane)."""
    # Simplified formula - real calc is more complex
    w = width_mm
    h = height_mm
    t = thickness_mm

    # Effective dielectric
    er_eff = (er + 1) / 2 + (er - 1) / 2 * (1 + 12 * h / w) ** -0.5

    # Impedance
    z0 = (87 / (er_eff ** 0.5)) * math.log(5.98 * h / (0.8 * w + t))
    return z0  # Ohms

# Example: 50Ω trace on standard 4-layer
# width_mm=0.2, height_mm=0.2 (prepreg thickness) → Z0 ≈ 50Ω
```

**For differential pairs:**
- Impedance depends on spacing AND width AND stackup
- USB 2.0: 90Ω differential
- HDMI: 100Ω differential
- PCIe: 85Ω differential

### 8. Layer-Specific Routing Rules (NOT IN PLAN)

Different layers have different rules:

| Layer | Routing Direction | Via Access | Net Classes Allowed |
|-------|-------------------|------------|---------------------|
| L1 (F.Cu) | Any (component side) | Yes | All |
| L2 (GND) | None (plane) | Via anti-pad only | GND only |
| L3 (PWR) | Limited traces in splits | Via anti-pad only | Power nets |
| L4 (B.Cu) | Any | Yes | All |

**Plane layers with routing:**
Some designs route signals on "plane" layers in the gaps between power domains. This requires:
- Knowing where the plane splits are
- Keeping signals away from plane edges
- Ensuring return path continuity

---

## Required Plan Updates

### Update 1: Add Stackup Model

```python
@dataclass
class LayerStackup:
    """Physical stackup definition."""

    layers: list[CopperLayer]
    dielectrics: list[DielectricLayer]

    total_thickness_mm: float

    def get_reference_plane(self, signal_layer: int) -> int | None:
        """Return the reference plane for a signal layer."""
        # Usually the adjacent plane layer
        ...

    def get_dielectric_height(self, signal_layer: int, ref_layer: int) -> float:
        """Distance from signal layer to reference plane."""
        ...

@dataclass
class CopperLayer:
    index: int
    name: str  # "F.Cu", "In1.Cu", etc.
    layer_type: Literal["signal", "plane", "mixed"]
    copper_weight_oz: float

    # For plane layers
    plane_net: str | None  # "GND", "+15V", etc.
    plane_splits: list[Polygon] | None  # Split regions

@dataclass
class DielectricLayer:
    material: Literal["prepreg", "core"]
    thickness_mm: float
    dielectric_constant: float  # Er, typically 4.3 for FR4
```

### Update 2: Add Via Types

```python
@dataclass
class ViaDefinition:
    """Via type with manufacturing constraints."""

    via_type: Literal["through", "blind", "buried", "microvia"]
    start_layer: int
    end_layer: int
    drill_mm: float
    pad_mm: float

    # Manufacturing constraints
    aspect_ratio: float  # depth / drill

    def is_manufacturable(self, stackup: LayerStackup) -> bool:
        depth = stackup.layer_distance(self.start_layer, self.end_layer)
        return depth / self.drill_mm <= self.aspect_ratio

# Via cost model for topology
VIA_COSTS = {
    "through": 1.0,      # Baseline
    "blind": 2.0,        # More expensive fab
    "buried": 4.0,       # Requires sequential lamination
    "microvia": 1.5,     # Common in HDI
}
```

### Update 3: Enhance Layer Assignment

```python
@dataclass
class LayerAssignmentRules:
    """Rules for which nets can use which layers."""

    # Layer capabilities
    signal_layers: list[int]        # Layers that can have traces
    plane_layers: dict[int, str]    # Layer → net name (GND, +15V)

    # Net class to layer mapping
    hv_nets: frozenset[str]         # Must be on outer layers (creepage)
    sensitive_nets: frozenset[str]  # Should be on L1 with GND reference

    # Differential pair rules
    diff_pairs: dict[str, DiffPairRules]

    def allowed_layers(self, net: Net) -> list[int]:
        """Return layers this net can be routed on."""
        if net.name in self.hv_nets:
            return [0, 3]  # Outer only for creepage
        if net.net_class == "Power" and net.current > 5:
            return [0, 3]  # High current on outer (wider traces)
        return self.signal_layers

@dataclass
class DiffPairRules:
    """Rules for differential pair routing."""

    target_impedance_ohm: float     # 90Ω for USB, 100Ω for HDMI
    required_spacing_mm: float      # Intra-pair spacing
    length_tolerance_mm: float      # Max length mismatch
    reference_plane: int            # Must have continuous plane on this layer
```

### Update 4: Reference Plane Checking

```python
def check_reference_plane_continuity(
    trace: Trace,
    stackup: LayerStackup,
) -> list[ReferencePlaneViolation]:
    """Check that trace has continuous reference plane underneath."""

    violations = []
    ref_layer = stackup.get_reference_plane(trace.layer)

    if ref_layer is None:
        violations.append(ReferencePlaneViolation(
            trace=trace,
            issue="No reference plane for this layer"
        ))
        return violations

    plane = stackup.layers[ref_layer]

    # Check if plane has splits under the trace
    for split in plane.plane_splits or []:
        if trace.geometry.intersects(split):
            violations.append(ReferencePlaneViolation(
                trace=trace,
                issue=f"Trace crosses plane split at {split}",
                suggestion="Add stitching vias or reroute"
            ))

    # Check via anti-pads
    for via in get_vias_near_trace(trace):
        if via.breaks_return_path(trace, ref_layer):
            violations.append(ReferencePlaneViolation(
                trace=trace,
                issue=f"Via anti-pad breaks return path at {via.position}",
                suggestion="Move via or add stitching via"
            ))

    return violations
```

### Update 5: Impedance-Aware Trace Width

```python
def calculate_trace_width_for_impedance(
    target_z0: float,
    stackup: LayerStackup,
    layer: int,
    is_differential: bool = False,
    diff_spacing_mm: float | None = None,
) -> float:
    """Calculate trace width to achieve target impedance."""

    ref_layer = stackup.get_reference_plane(layer)
    height = stackup.get_dielectric_height(layer, ref_layer)
    er = stackup.dielectrics[...].dielectric_constant

    if is_differential:
        # Differential pair - coupled microstrip
        return solve_coupled_microstrip(target_z0, height, er, diff_spacing_mm)
    else:
        # Single-ended microstrip
        return solve_microstrip(target_z0, height, er)
```

### Update 6: Channel Capacity Per Layer

The channel model needs per-layer capacity:

```python
@dataclass
class Channel:
    id: str
    region: Rectangle

    # Per-layer capacity (not all layers are equal!)
    layer_capacities: dict[int, int]  # layer_index → capacity

    # Some layers may be blocked (plane layers)
    blocked_layers: set[int]

    def capacity_for_net(self, net: Net, rules: LayerAssignmentRules) -> int:
        """Capacity available for this specific net."""
        allowed = rules.allowed_layers(net)
        return sum(
            self.layer_capacities.get(layer, 0)
            for layer in allowed
            if layer not in self.blocked_layers
        )
```

---

## Impact on Pipeline Stages

### Stage 0: Design Intent
- **Add:** Parse stackup from KiCad board file
- **Add:** Extract impedance requirements from net classes

### Stage 1: Pin Escape
- **Add:** Via type selection (through vs blind vs microvia)
- **Add:** Check via aspect ratio against stackup

### Stage 2: Channel Analysis
- **Add:** Per-layer capacity calculation
- **Add:** Plane layer blockage

### Stage 3: Topological Routing
- **Add:** Via type as variable in constraint model
- **Add:** Reference plane continuity constraint
- **Add:** Impedance-driven width assignment

### Stage 4: Geometric Realization
- **Add:** Return path checking during routing
- **Add:** Stitching via insertion

### Stage 5: Manufacturing DRC
- **Add:** Via aspect ratio check
- **Add:** Impedance verification (calculate actual vs target)
- **Add:** Plane split warnings

---

## Test Cases for Multilayer

```python
class TestMultilayer:
    def test_through_via_blocks_all_layers(self):
        """Through via consumes space on all 4 layers."""

    def test_blind_via_preserves_inner_capacity(self):
        """Blind L1→L2 via doesn't block L3, L4."""

    def test_hv_net_outer_layers_only(self):
        """High-voltage nets cannot route on inner layers."""

    def test_diff_pair_reference_plane(self):
        """Diff pair has continuous GND plane underneath."""

    def test_plane_split_crossing(self):
        """Signal crossing plane split has stitching via."""

    def test_impedance_width_calculation(self):
        """50Ω trace width correct for stackup."""

    def test_via_aspect_ratio(self):
        """0.15mm microvia can't connect L1→L3."""
```

---

## Summary: What Was Missing

| Concept | Status in Plan | Required For |
|---------|---------------|--------------|
| Stackup definition | Missing | Impedance, layer spacing |
| Via types (blind/buried) | Missing | BGA escape, HDI |
| Plane splits | Missing | Return path integrity |
| Reference plane checking | Missing | Signal integrity |
| Impedance control | Missing | High-speed signals |
| Per-layer capacity | Missing | Accurate channel model |
| Via aspect ratio | Missing | Manufacturability |
| Layer pairing rules | Missing | Diff pair routing |

**Severity:** High. Without these, the router will produce electrically incorrect boards for anything beyond simple 2-layer designs.

**Effort to add:** Medium. ~500 lines of model code + ~200 lines of checking code.
