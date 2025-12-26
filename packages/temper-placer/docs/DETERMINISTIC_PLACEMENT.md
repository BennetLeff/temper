# Deterministic Placement Architecture

This document consolidates the design for the template-based deterministic placement system,
replacing gradient-based optimization with a hierarchical, constraint-aware approach.

## The Core Question: What Makes a "Well-Designed PCB"?

The system's abstract goal is producing a "well-designed PCB." But we must ground this in
measurable physics, not geometric proxies.

### Physical Success Criteria

| Criterion | Physical Basis | What We Actually Measure |
|-----------|---------------|-------------------------|
| **EMI Compliance** | P_rad proportional to (loop_area * frequency * current)^2 | Post-routing trace loop areas |
| **Thermal Safety** | T_j = T_a + (Rth_jc + Rth_cs + Rth_sa) * P_diss | Junction temps from resistance network |
| **Signal Integrity** | Rise time, reflection coefficient, crosstalk coupling | Length matching, impedance, spacing |
| **Manufacturability** | Acid traps, silkscreen overlap, annular ring | DRC violations |

### The Measurement Gap

**Problem**: Current losses measure geometric proxies during placement, but physical properties
are only determinable after routing:

```
PLACEMENT PHASE                    ROUTING PHASE
     |                                  |
     v                                  v
[Component positions] -----> [Actual trace geometry]
     |                                  |
     v                                  v
Pin-to-pin shoelace       Actual current loop polygon
area (WRONG)              from routed traces (CORRECT)
```

**Solution**: The validation framework measures actual routed geometry, then feeds violations
back to constrain the next placement iteration.

---

## Architecture Overview

```
+------------------------------------------------------------------+
|  Step -1: Metrics & Baselines                                    |
|  (establish measurement capability FIRST)                        |
+------------------------------------------------------------------+
                              |
                              v
+------------------------------------------------------------------+
|  Step 0: Constraint Feasibility Check                            |
|  (catches impossible constraints before any placement)           |
+------------------------------------------------------------------+
                              |
                              v
+------------------------------------------------------------------+
|  Step 1: Parametric Template Placement                           |
|  (board-aware scaling, domain knowledge encoded)                 |
+------------------------------------------------------------------+
                              |
                              v
+------------------------------------------------------------------+
|  Step 2: Zone-Aware Legalization                                 |
|  (constraint hierarchy with backtracking)                        |
+------------------------------------------------------------------+
                              |
                              v
+------------------------------------------------------------------+
|  Step 2.5: Routability Validation                                |
|  (fast maze route, congestion detection, feedback loop)          |
+------------------------------------------------------------------+
                              |
                              v
+------------------------------------------------------------------+
|  Step 3: Local Refinement                                        |
|  (limited gradient optimization, max 2mm movement)               |
+------------------------------------------------------------------+
                              |
                              v
+------------------------------------------------------------------+
|  Step 4: Full Routing                                            |
|  (maze router + push-shove)                                      |
+------------------------------------------------------------------+
                              |
                              v
+------------------------------------------------------------------+
|  Step 5: Post-Routing Validation                                 |
|  (physics-based validation of actual traces)                     |
+------------------------------------------------------------------+
```

---

## Step -1: Metrics Infrastructure & Baselines

**Problem**: We can't improve what we can't measure. Without baselines, we can't prove
anything works.

**Solution**: Establish measurement capability BEFORE implementation.

### Measurable Sub-Problems

| Sub-Problem | Metric | When Measurable |
|-------------|--------|-----------------|
| Geometric Feasibility | overlap_count, zone_violations | Post-placement |
| Thermal Safety | max_Tj, thermal_margin | Post-routing |
| EMI/Loop Area | gate_loop_mm2, power_loop_mm2 | Post-routing |
| Routability | completion_pct, congestion_score | Post-routing |
| Signal Integrity | length_match_mm, impedance_pct | Post-routing |
| Manufacturability | drc_error_count | Post-export |

### Baseline Types

| Type | Purpose | Source |
|------|---------|--------|
| Internal | "How bad are we now?" | Current temper-placer output |
| External | "What does good look like?" | Scraped reference designs |

---

## Step 0: Constraint Feasibility Checking

**Problem**: Constraints like "decoupling cap < 3mm from IC" are impossible when
IC is 8mm wide and cap is 3mm wide (min center-to-center = 5.5mm).

**Implementation**: `src/temper_placer/validation/preflight.py`

Checks:
1. **Proximity Feasibility** - Physical min distance vs requested max distance
2. **Zone Capacity** - Sum of component areas vs zone area
3. **Loop Area Feasibility** - Min polygon area given component sizes
4. **Clearance Chain** - HV/LV separation achievable given layout

---

## Step 1: Parametric Template Placement

**Problem**: Hardcoded offsets (e.g., `switch_spacing: 15.0`) don't adapt to board size.

**Solution**: Ratio-based scaling in config:

```yaml
zones:
  - name: "power_zone"
    bounds_ratio: [0.0, 0.73, 1.0, 1.0]  # Top 27% of board

groups:
  - name: "igbt_power_stage"
    max_spread_ratio: 0.25  # 25% of min(board_width, board_height)
```

Templates scale based on board geometry while respecting min/max spacing limits.

---

## Step 2: Zone-Aware Legalization with Backtracking

**Problem**: Current greedy legalization ignores zones during overlap resolution.

**Solution**: Priority-based resolution with state stack:

1. Fixed components (never move)
2. Zone-assigned components (must stay in zone)
3. Free components (most flexibility)

When a move would violate zone constraints, backtrack and try spiral search instead.

---

## Step 2.5: Routability Validation Loop

**Problem**: Waterfall pipeline with no feedback - placement might be unroutable.

**Solution**: Fast maze route of critical nets before committing:

```python
for iteration in range(max_routability_iterations):
    positions = legalize_zone_aware(positions, ...)
    routing_result = check_routability(positions, critical_nets)

    if routing_result.completion_rate >= 0.90:
        break

    # Feedback: adjust placement based on congestion
    positions = adjust_for_congestion(positions, routing_result.congestion_map)
```

---

## Step 3: Local Refinement Phase

**Problem**: Templates are rigid; need limited optimization for wirelength/loop area.

**Solution**: Projected gradient descent with hard constraints:

- Max 2mm component movement from template position
- Only optimize wirelength + loop area (soft losses)
- Overlap and zone constraints projected (hard constraints)
- Early stopping on convergence

---

## Step 5: Post-Routing Validation Framework

### Specification-Driven Validation

Instead of measuring proxies, we define physical specs and validate against actual routing:

```yaml
# pcb_spec.yaml
thermal:
  max_junction_temp_c: 125
  ambient_temp_c: 40
  power_dissipation:
    Q1: 15.0  # Watts
    Q2: 15.0

emi:
  max_loop_area_mm2:
    gate_drive_loop: 50
    power_loop: 100
  frequency_hz: 100000

signal_integrity:
  nets:
    - name: "CLK"
      max_length_mm: 50
      length_match_mm: 2.0
```

### Post-Routing Measurements

| What | How | Feedback |
|------|-----|----------|
| Loop Area | Trace actual polygon from routed net geometry | If > max, tighten proximity constraints |
| Thermal | Resistance network: trace width -> Rth, via count -> Rth | If T_j > max, increase spacing |
| Length Match | Sum routed segment lengths per net | If mismatch > tolerance, add length constraints |

### Validation Feedback Loop

```
Placement -> Routing -> Validation -> Root Cause Analysis -> Constraint Update
    ^                                                              |
    +--------------------------------------------------------------+
```

---

## Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Implementation order | Foundation -> Core -> Feedback -> Integration | Logical dependency order |
| Optimization approach | **Hybrid** | Templates + legalization + limited gradient (max 2mm) |
| Config format | **Predefined ratios** | `bounds_ratio: [0, 0.73, 1.0, 1.0]` - simple, secure |
| Loop area optimization | **Keep in placement** | Loop geometry is fundamentally a placement constraint |
| Validation | **Post-routing** | Physics can only be measured from actual traces |
| Exploration vs Templates | **Templates first** | See rationale below |

### Why Not More Exploration (PowerSynth-style)?

PowerSynth generates 10,000-30,000 random solutions to find Pareto-optimal trade-offs.
We considered this but decided **no** for now.

**The problem we're solving**: "Gradient conflicts make placement fail" - zones fight overlap,
grouping fights loop area, thermal fights electrical. The optimizer can't navigate the space.

**What exploration solves**: "We don't know the optimal trade-off point" - finding the best
balance between competing objectives in a space we can already navigate.

**Why exploration doesn't help yet**: More exploration of a broken optimizer just finds more
broken solutions. Random search won't resolve the fundamental conflict between soft losses.

**The path forward**:
1. Get deterministic pipeline working (templates + legalization)
2. If templates produce good-enough placements reliably, exploration becomes optional polish
3. If templates fail, we'll have concrete failure modes to explore around - not random search

**When to revisit**: Once the deterministic pipeline reliably produces DRC-clean, routable
placements, NSGA-II exploration could find better thermal-electrical trade-offs. But that's
optimization of a working system, not a fix for a broken one.

---

## Implementation Tracking

All implementation is tracked in Beads epics. **Metrics epic blocks all implementation.**

```
temper-biv9: Metrics & Baselines (Step -1)  <- MUST COMPLETE FIRST
     |
     +-- blocks --> temper-l0nd: Constraint Feasibility (Step 0)
     +-- blocks --> temper-rbr9: Parametric Templates (Step 1)
     +-- blocks --> temper-zsd1: Zone-Aware Legalization (Step 2)
     +-- blocks --> temper-c4vf: Routability Feedback (Step 2.5)
     +-- blocks --> temper-iquo: Local Refinement (Step 3)
     +-- blocks --> temper-n5rr: MCU Template (Step 4)
                         |
                         +--> temper-xh5l: CLI Integration
                                   |
                                   +--> temper-oe49: Validation Framework
```

| Epic | Description | Priority | Children |
|------|-------------|----------|----------|
| `temper-biv9` | **Metrics & Baselines (Step -1)** | P0 | 5 |
| `temper-l0nd` | Constraint Feasibility Checking (Step 0) | P0 | 3 |
| `temper-rbr9` | Parametric Template System (Step 1) | P0 | 2 |
| `temper-zsd1` | Zone-Aware Legalization (Step 2) | P0 | 3 |
| `temper-c4vf` | Routability Feedback Loop (Step 2.5) | P0 | 2 |
| `temper-iquo` | Local Gradient Refinement (Step 3) | P0 | 2 |
| `temper-n5rr` | MCU Subsystem Template (Step 4) | P1 | 2 |
| `temper-xh5l` | CLI Integration | P1 | 2 |
| `temper-oe49` | Specification-Driven Validation Framework | P0 | 6 |

Use `bd show <epic-id>` to see child tickets for each epic.

### Scientific Method Structure

Each epic should follow this pattern:

```yaml
epic: temper-zsd1
hypothesis: "Zone-aware legalization reduces zone_violations from X to 0"
baseline: temper-biv9.3  # Internal baseline measurement
metrics:
  - zone_violation_count (must_achieve: 0)
  - overlap_count (must_achieve: 0)
ablation: "Compare with/without backtracking"
```

---

## Success Criteria

1. **Feasibility Check**: Catches 100% of impossible proximity constraints before placement
2. **Zone-Aware Legalization**: Zero zone violations after legalization
3. **Routability Feedback**: <10% unroutable nets triggers adjustment
4. **Local Refinement**: <=2mm max movement, measurable wirelength improvement
5. **Validation Framework**: Physics-based pass/fail with actionable feedback
6. **End-to-End**: Deterministic placement + routing succeeds on Temper board in <30 seconds

---

## Failure Modes

### Metrics Infrastructure Failures

| Failure Mode | Likelihood | Impact | Detection |
|--------------|------------|--------|-----------|
| Metrics don't correlate with real success | Medium | Fatal | PCB fails in practice despite good metrics |
| External baselines aren't comparable | High | Medium | Different topologies make comparison meaningless |
| Can't parse reference designs | Medium | Low | Format conversion hell |
| Metrics too slow to compute | Low | Medium | Iteration grinds to halt |

**Most likely**: External baselines turn out to be apples-to-oranges. A 5kW motor driver and
a 500W induction heater may not be comparable despite both being "half-bridge."

### Template Failures

| Failure Mode | Likelihood | Impact | Detection |
|--------------|------------|--------|-----------|
| Templates encode wrong knowledge | Medium | High | Consistently bad placements |
| Templates too rigid | High | Medium | Edge cases break (odd component counts) |
| Template scaling breaks | Medium | Medium | Works at 100x150mm, fails at 50x75mm |
| Missing templates for subsystems | High | Low | Some components placed randomly |

**Most likely**: Templates are too rigid. Real designs have variations (3 bus caps vs 2,
different gate driver pinouts) that templates don't handle.

### Legalization Failures

| Failure Mode | Likelihood | Impact | Detection |
|--------------|------------|--------|-----------|
| Backtracking infinite loops | Medium | High | Legalization never terminates |
| Zone-aware too slow | Low | Medium | Minutes instead of seconds |
| Priority ordering wrong | Medium | Medium | Important components pushed to bad locations |

**Most likely**: Priority ordering. Which component "wins" during overlap resolution is a
design decision, and we might get it wrong.

### Feedback Loop Failures

| Failure Mode | Likelihood | Impact | Detection |
|--------------|------------|--------|-----------|
| Fast routing != real routing | High | High | Passes check, fails real router |
| Congestion adjustment oscillates | Medium | High | Never converges |
| Feedback loop too slow | Medium | Medium | 3 iterations x routing time |

**Most likely**: Fast routing estimate is wrong. Maze router on 0.5mm grid misses via
placement constraints, layer transitions, differential pairs.

### Fundamental Assumption Failures

| Failure Mode | Likelihood | Impact | Fatal? |
|--------------|------------|--------|--------|
| Problem isn't gradient conflicts | Low | Fatal | Yes - whole approach wrong |
| Templates can't cover design space | Medium | High | Need exploration after all |
| Post-routing validation too late | Medium | High | Can't fix bad placement |
| Physics-based constraints wrong | Low | High | Derived constraints don't match reality |

**Most dangerous**: Post-routing validation is too late. If routing reveals placement is bad,
we have to re-place and re-route. The feedback loop may not converge.

### Meta Failures

| Failure Mode | Likelihood | Impact |
|--------------|------------|--------|
| Scope creep | High | Medium - never ship |
| Lost in metrics, never build system | Medium | High - analysis paralysis |
| Complexity makes debugging impossible | Medium | High - can't fix bugs |
| External baseline effort > value | High | Low - waste time |

### Most Likely Failure Scenario

```
1. We build metrics infrastructure (2 weeks)
2. We scrape 5 reference designs, discover they're not comparable (1 week wasted)
3. We build templates based on intuition, not data
4. Templates work for Temper board specifically
5. Templates break on next project (different topology)
6. We're back to square one, but with more code to maintain
```

**The bet we're making**: Domain knowledge is transferable across power electronics designs.
If each design is a special snowflake, templates provide no value over gradient optimization.

### Second Most Likely Failure

```
1. Placement looks good (metrics pass)
2. Routing fails (congestion, layer issues)
3. Feedback loop adjusts placement
4. Routing fails differently
5. Oscillation: placement -> routing -> placement -> routing
6. Never converges
```

**Why this happens**: Placement and routing are coupled, but we treat them as sequential
with limited feedback. The feedback may not have enough information.

### Abandon Criteria

We should abandon this approach if:

1. **External baselines show huge variance** - If "good" designs have loop areas from 30mm²
   to 300mm², our targets are arbitrary
2. **Templates fail on 3+ designs** - Can't generalize beyond Temper
3. **Feedback loop doesn't converge in 5 iterations** - Oscillation means abstraction is wrong
4. **Metrics don't predict fab success** - Board passes metrics, fails in practice

### Mitigations

| Risk | Mitigation |
|------|------------|
| External baselines incomparable | Start with internal baseline only, add external as validation |
| Templates too rigid | Build escape hatch: fall back to gradient if template fails |
| Feedback oscillation | Add damping (smaller adjustments each iteration), max iteration cap |
| Scope creep | Timebox metrics epic to 1 week, ship MVP |
