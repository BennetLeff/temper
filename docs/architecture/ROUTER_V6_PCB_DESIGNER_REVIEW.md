# Router V6: Professional PCB Designer Review

**Reviewer Background:** This review applies the perspective of a professional PCB designer with experience in power electronics, high-speed digital, and mixed-signal designs.

**Overall Assessment:** The plan is technically sophisticated from a computer science perspective but shows gaps in practical PCB design knowledge. Several fundamental aspects of real-world PCB design are missing or underweighted.

---

## Critical Gap 1: Pin Escape is THE Problem (Not Channel Routing)

### What the Plan Says
Pin escape is mentioned briefly in Phase 4 of Solution B: "Escape routing for dense pins (~300 lines)."

### Reality
**Pin escape is 50-70% of routing difficulty** on modern boards. Channel routing between component clusters is comparatively easy.

The hard part isn't routing from cluster A to cluster B. It's getting signals OUT of:
- **QFN/DFN packages**: Exposed pad underneath, pins on all 4 edges
- **BGA packages**: Array of balls, inner balls are trapped
- **Fine-pitch SOIC**: 0.5mm pitch, traces can't fit between pads

### Industry Patterns the Plan Ignores

```
DOG-BONE FANOUT (for SMD):
    ┌─────┐
    │ PAD │──via──→ escape to inner layer
    └─────┘

VIA-IN-PAD (for BGA):
    ┌─────┐
    │VIA│ ← via directly in pad (filled + plated over)
    └─────┘

NECK-DOWN (for fine-pitch):
    ════════╲
             ╲───────  ← trace narrows to fit between pads
    ════════╱
```

### Required Plan Changes
1. **Elevate escape routing to Phase 0** (before channel routing)
2. **Define escape patterns** for each footprint type (QFN, BGA, fine-pitch)
3. **Pre-compute escape vias** during placement, not routing

---

## Critical Gap 2: Placement is (X, Y, Rotation, Side) Not Just (X, Y)

### What the Plan Says
Placement feedback suggests "Move C12 south 2mm."

### Reality
Placement has **4 degrees of freedom** per component:
- **X, Y**: Position on board
- **Rotation**: 0°, 90°, 180°, 270° (or continuous for some)
- **Side**: Top or bottom layer

Rotation is **critical** for routing:
```
BAD ROTATION:              GOOD ROTATION:
  ┌───────┐                  ┌───────┐
  │ 1 2 3 │                  │ 3 │
  │ IC    │  pins face       │ 2 │ IC    pins face
  │ 4 5 6 │  congested       │ 1 │       escape route
  └───────┘  area            └───────┘
```

### Placement Constraints from Real Design

| Constraint Type | Example | Impact |
|-----------------|---------|--------|
| **Fixed** | Connectors, switches, LEDs | Set by mechanical/user interface |
| **Constrained** | Decoupling caps | Must be within 3mm of IC power pin |
| **Thermal** | IGBTs, FETs | Need thermal pad connection, via array |
| **Grouped** | Diff pair resistors | Must be adjacent for matching |
| **Flexible** | Generic passives | Can go almost anywhere |

### Required Plan Changes
1. **Placement model must include rotation and side**
2. **Placement feedback must suggest rotation changes**, not just position
3. **Define component constraint categories** in test suite

---

## Critical Gap 3: Differential Pairs are More Than "Route Together"

### What the Plan Says
References `CoupledDiffPairRouter` from V5. Mentions "topology assigns them to same channel."

### Reality
Differential pair routing has **5 simultaneous constraints**:

1. **Intra-pair spacing**: P and N traces must be parallel, fixed distance (e.g., 0.15mm)
2. **Intra-pair length matching**: P and N within ~0.1mm of each other
3. **Inter-pair spacing**: Different diff pairs must be separated (crosstalk)
4. **Impedance control**: Trace width + spacing determines differential impedance
5. **Reference plane continuity**: Must have solid ground under entire run

### What This Means for Channel Model

Differential pairs **don't fit the channel model**:
- A diff pair is ONE logical net but TWO physical traces
- The "capacity" consumed is 2× trace width + spacing
- They can't cross other traces on same layer (unlike single-ended)
- Length matching may require serpentine (uses more space)

### Required Plan Changes
1. **Model diff pairs as special net type** in topology
2. **Channel capacity for diff pairs = 2*trace + 3*spacing** (P, gap, N, gap to next)
3. **Length matching serpentine must be planned** during topology

---

## Critical Gap 4: Creepage ≠ Clearance (Power Electronics)

### What the Plan Says
"Clearance" mentioned throughout. HV nets need "3mm+ clearance."

### Reality
**Clearance** and **creepage** are different:

| Term | Definition | Measurement |
|------|------------|-------------|
| **Clearance** | Shortest distance through AIR | Straight line |
| **Creepage** | Shortest distance along SURFACE | Following PCB surface |

```
CROSS-SECTION VIEW:

  Trace A          Trace B
    │                │
    │   clearance    │    ← through air: 3mm
    │   ════════     │
────┴────────────────┴────  PCB surface
    ←─── creepage ───→      ← along surface: 5mm (goes around)
```

### Why This Matters for Temper

Induction cookers have **MAINS VOLTAGE** (120-240VAC). Safety standards require:
- **Creepage**: 4-8mm between mains and SELV (safe extra-low voltage)
- **Clearance**: 3-4mm minimum

**Slots and cutouts INCREASE creepage** by forcing current to go around:
```
  Trace A    ╔════╗    Trace B
    │        ║SLOT║       │
    │        ║    ║       │
────┴────────╚════╝───────┴────
    ←──── creepage increased ────→
```

### Required Plan Changes
1. **Distinguish clearance and creepage** in design rules
2. **Model slots/cutouts** as creepage increasers
3. **Safety-critical nets** (AC_L, AC_N) need creepage checking, not just clearance

---

## Critical Gap 5: Length Matching Groups

### What the Plan Says
Not mentioned.

### Reality
High-speed interfaces require **matched-length** trace groups:

| Interface | Matching Requirement | Typical Tolerance |
|-----------|---------------------|-------------------|
| USB 2.0 | D+/D- within pair | ±0.15mm |
| DDR3/4 | Data bits to strobe | ±25ps (~3mm) |
| RGMII | TX group, RX group | ±50ps |
| HDMI | Each pair + inter-pair | ±0.5mm |

### Impact on Router Architecture

Length matching **fundamentally changes topology**:
- Can't just find shortest path
- May need serpentine/meander to ADD length
- Group members must be routed similarly (same layer changes, same via count)

```
WITHOUT MATCHING:         WITH MATCHING:
  A ─────────────────→     A ─────────────────→
  B ────────→              B ─────╱╲╱╲╱╲──────→  (serpentine adds length)
  C ──────────────→        C ─────────╱╲╱╲───→
```

### Required Plan Changes
1. **Length matching groups as first-class concept** in topology
2. **Report length mismatch** in diagnostics
3. **Reserve space for serpentine** in channel capacity

---

## Critical Gap 6: Current Capacity (Not Just Clearance)

### What the Plan Says
Trace width determined by `design_rules.default_trace_width`.

### Reality
Trace width is determined by **THREE factors**:

1. **Impedance** (high-speed signals): Width + stackup → target impedance
2. **Current capacity** (power traces): Width × copper weight → amps
3. **Manufacturing minimum** (all traces): Fab capability

### Current Capacity Formula (IPC-2152)

```
I = k × ΔT^0.44 × A^0.725

Where:
  I = Current (amps)
  k = 0.024 for internal, 0.048 for external
  ΔT = Temperature rise (°C)
  A = Cross-sectional area (mils²) = width × thickness
```

**Example for Temper (40A traces):**
- External layer, 2oz copper, 20°C rise
- Required width: ~15mm (0.6 inches)

This is **not a clearance problem, it's a trace width problem**.

### Required Plan Changes
1. **Net class includes current rating**, not just clearance
2. **Trace width computed from current requirement**
3. **High-current nets may need copper pours**, not traces

---

## Critical Gap 7: Manufacturing Realities

### Not Mentioned in Plan

| Issue | Why It Matters |
|-------|----------------|
| **Copper balancing** | Unbalanced copper causes board warping. Each layer should be 40-60% copper. |
| **Acid traps** | Acute angles (<90°) trap etchant, cause opens |
| **Annular ring** | Via pad must extend beyond drill hole |
| **Solder mask slivers** | Thin mask strips peel off |
| **Thermal relief** | Pads connected to planes need spoke pattern for soldering |
| **Teardrops** | Gradual transitions at pad-trace junctions prevent cracks |

### Most Critical: Copper Balancing

```
BAD (will warp):           GOOD (balanced):
Layer 1: ████████ 80%      Layer 1: █████ 50%
Layer 2: ██ 10%            Layer 2: █████ 50%

→ Add copper thieving to empty areas
```

### Required Plan Changes
1. **Add copper pour/thieving** as post-routing step
2. **DRC must check acid traps, annular ring**
3. **Thermal relief for plane-connected pads**

---

## Critical Gap 8: 100% Automation is Wrong Goal

### What the Plan Says
"100% automatic schematic → PCB pipeline"

### Industry Reality
**No production autorouter achieves 100%.** The industry standard is:

| Phase | Method | Typical Coverage |
|-------|--------|------------------|
| Critical nets | Manual routing | 10-20% of nets |
| Escape/fanout | Semi-auto wizard | 30-40% of nets |
| Fill routing | Autorouter | 40-50% of nets |
| Cleanup | Manual touch-up | All nets |

### Why 100% Auto Fails

1. **Design intent isn't in netlist**: "These traces should be symmetric" isn't captured
2. **Aesthetics matter**: Customers judge quality by visual appearance
3. **Edge cases**: Every board has 5-10 nets that need human judgment
4. **Verification**: Human must review DRC, not just pass/fail

### Revised Goal

**Target: 80% auto + 20% guided**

- Auto-route 80% of nets (the boring ones)
- Identify the 20% that need human guidance
- Provide interactive tools for the 20%
- Total time savings: 60-70% vs full manual

### Required Plan Changes
1. **Reframe success metric**: 80% auto-routed with identified exceptions
2. **Add "needs attention" flag** in diagnostics
3. **Don't fail on hard nets** - flag them and continue

---

## Critical Gap 9: Schematic Design Intent

### What the Plan Assumes
Clean netlist with nets and pins.

### What Schematics Actually Contain

| Information | How It's Expressed | Router Impact |
|-------------|-------------------|---------------|
| Net classes | Net attributes or naming convention | Clearance, width |
| Diff pairs | Special symbols or naming (D+/D-) | Coupled routing |
| Length groups | Net attributes | Must match lengths |
| No-connects | NC symbol on pin | Don't flag as unrouted |
| Power symbols | Global power nets | Special routing rules |
| Hierarchy | Sheet structure | Net naming, grouping |

### Example: Design Intent Lost

Schematic says:
```
USB_D+ ──────┤ differential_pair="USB"
USB_D- ──────┤ length_group="USB_DATA"
```

Netlist says:
```
Net "USB_D+": pin U1.3, pin J1.2
Net "USB_D-": pin U1.4, pin J1.3
```

**The diff pair and length group information is LOST** unless explicitly preserved.

### Required Plan Changes
1. **Parse schematic, not just netlist** (or preserve attributes in netlist)
2. **Extract diff pairs, length groups, net classes** from source
3. **Preserve design intent** through topology stage

---

## Summary: What the Plan is Missing

### Must Fix (Plan Will Fail Without These)

| Gap | Current State | Required State |
|-----|--------------|----------------|
| Pin escape | Footnote | Primary phase |
| Rotation in placement | Not considered | 4-DOF placement model |
| Creepage vs clearance | Conflated | Separate checks |
| Current capacity | Not mentioned | Width from current |
| 100% auto goal | Stated goal | 80% auto + flagging |

### Should Fix (Significant Impact)

| Gap | Current State | Required State |
|-----|--------------|----------------|
| Diff pair constraints | "Same channel" | 5 constraints modeled |
| Length matching | Not mentioned | First-class concept |
| Schematic design intent | Assume clean netlist | Parse attributes |
| Manufacturing DRC | Not mentioned | Post-route checks |

### Nice to Have (Polish)

| Gap | Current State | Required State |
|-----|--------------|----------------|
| Copper balancing | Not mentioned | Auto-thieving |
| Teardrops | Not mentioned | Optional post-process |
| Glossing/optimization | Not mentioned | Trace cleanup phase |

---

## Recommended Plan Revisions

### 1. Restructure Pipeline Phases

**Current:**
```
Channel Analysis → Topological Routing → Geometric Realization
```

**Proposed:**
```
Design Intent Extraction → Pin Escape Planning → Channel Analysis →
Topological Routing → Geometric Realization → Manufacturing DRC
```

### 2. Redefine Success

**Current:** "100% completion rate"

**Proposed:**
- 80%+ auto-routed
- 100% of remaining nets flagged with specific guidance
- 0 manufacturing DRC violations
- 0 safety (creepage/clearance) violations

### 3. Add Rotation to Placement Model

```python
@dataclass
class PlacementSuggestion:
    component: str
    position: tuple[float, float]  # Current
    rotation: Literal[0, 90, 180, 270]  # ADD THIS
    side: Literal["top", "bottom"]  # ADD THIS
    reason: str
```

### 4. Add Current-Based Width Calculation

```python
def required_trace_width(net, copper_weight_oz, max_temp_rise_c):
    """Calculate minimum trace width for current capacity."""
    if net.current_rating is None:
        return design_rules.default_width

    # IPC-2152 formula
    area_mils2 = (net.current_rating / (0.048 * (max_temp_rise_c ** 0.44))) ** (1/0.725)
    thickness_mils = copper_weight_oz * 1.37  # 1oz = 1.37 mils
    width_mils = area_mils2 / thickness_mils
    return width_mils * 0.0254  # Convert to mm
```

### 5. Add Pin Escape Phase

New phase between placement and channel routing:

```python
class PinEscapeStage:
    """Plan escape routes for dense pin fields before channel routing."""

    def run(self, state: BoardState) -> BoardState:
        escape_vias = []

        for component in state.components:
            if component.package_type in ["QFN", "BGA", "TSSOP"]:
                # Plan dog-bone fanout
                for pad in component.pads:
                    if self.needs_escape_via(pad, state):
                        via_pos = self.compute_escape_position(pad, component)
                        escape_vias.append(EscapeVia(
                            pad=pad,
                            position=via_pos,
                            target_layer=self.select_escape_layer(pad)
                        ))

        return state.with_escape_plan(escape_vias)
```

### 6. Separate Creepage from Clearance

```python
@dataclass
class SafetyRules:
    """IEC 60950 / IEC 62368 safety requirements."""

    # Net pair → minimum distances
    clearance_mm: dict[tuple[str, str], float]  # Through air
    creepage_mm: dict[tuple[str, str], float]  # Along surface

    # Voltage-based defaults
    working_voltage: float  # e.g., 240V for mains
    pollution_degree: int   # 1, 2, or 3
    material_group: str     # I, II, IIIa, IIIb

    def get_creepage(self, net_a: str, net_b: str) -> float:
        """Look up creepage requirement, considering slots."""
        base = self.creepage_mm.get((net_a, net_b), 0)
        # Note: slots can reduce effective creepage requirement
        # because they increase the surface path
        return base
```
