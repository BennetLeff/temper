# Deterministic, Physics‑Aware PCB Placement & Routing

This document summarizes the core ideas, critiques, and synthesized architecture from prior discussion. It is intended as a **handoff artifact** for planning and implementation with another chatbot or team.

---

## 1. Core Thesis

- **Placement is the dominant optimization problem** in power electronics PCB design.
- **Routing is the proof**, not the source of correctness.
- Deterministic routing is valuable **only** when combined with:
  - loop‑centric modeling
  - physics‑aware constraints
  - explainability
  - manufacturing variability awareness

The target domain is a **4‑layer induction cooker PCB**, starting from a **validated atopile schematic**.

---

## 2. Fundamental Architectural Principles

### 2.1 Determinism
- Same inputs → same outputs
- Fixed ordering, tie‑breaks, and cost functions
- No stochastic search in the core solver

### 2.2 Loop‑First Modeling

Routing and placement operate on **current loops**, not just nets.

Examples:
- Fast commutation loop (DC+ → switch → coil → DC− → DC link cap)
- Gate drive loop
- Current sense loop

Each loop carries:
- direction
- return ownership
- event tags (dv/dt, di/dt, switching frequency)

---

## 3. What a Naïve Deterministic Router Misses (Critical Gaps)

The following were identified as **non‑optional** for induction/power electronics:

1. **Time‑domain awareness**
   - dv/dt, di/dt, edge timing
2. **Magnetic coupling modeling**
   - mutual inductance, loop‑to‑loop coupling, plane shorted turns
3. **Via‑as‑component modeling**
   - inductance, resistance, thermal impedance, fatigue risk
4. **Risk‑weighted constraints**
   - not all violations are equal; severity & probability matter
5. **Manufacturing variability**
   - etch tolerance, copper thickness, stackup variance
6. **Explainability / decision trace**
   - every placement & route must have a reason
7. **Assembly & mechanical constraints**
   - heatsinks, connectors, screws, creepage after contamination
8. **Post‑layout schematic feedback**
   - tool must say “no routing can save this topology”

---

## 4. Correct Mental Model: Placement ↔ Routing Loop

Placement and routing are **co‑equal, coupled systems**.

Correct loop:

```
Schematic (validated)
→ Initial placement hypothesis
→ Topological feasibility check
→ Routing attempt
→ Physics + constraint evaluation
→ Placement feedback / adjustment
↺ iterate until feasible
```

Routing failures are assumed to be **placement failures** unless proven otherwise.

---

## 5. Placement Phases

### Phase 0 — Semantic Grouping (No Geometry)
- Extract loops, clusters, regions from atopile
- Assign ownership (which components belong to which loop)

### Phase 1 — Topological Placement
- Decide adjacency, separation, enclosure relationships
- No coordinates yet

### Phase 2 — Coarse Geometry
- Bounding boxes, halos, field influence zones
- Early rejection of impossible layouts

### Phase 3 — Routing‑Informed Refinement
- Deterministic placement adjustments driven by routing diagnostics

### Phase 4 — Placement Freeze
- Once loops are feasible and metrics are satisfied

---

## 6. Constraint System

### 6.1 Constraint Tiers

- **Tier 1 (Hard):** never violate
  - clearance, creepage, fast edge over plane splits
- **Tier 2 (Strong):** cost‑guided, can escalate
  - loop area targets, coupling limits
- **Tier 3 (Soft):** aesthetics / convenience

### 6.2 Constraint Scope

Constraints apply to:
- components
- clusters
- loops
- regions

---

## 7. Placement Constraint Language (PCL)

The PCL is designed to be:
- readable
- deterministic
- auditable
- loop‑native

### 7.1 Core Relations

#### Adjacent
> Put A near B, with explicit metric

#### Separated
> Keep A away from B, optionally allowing shielding

#### Enclosing
> One object or loop must geometrically or topologically enclose another

### 7.2 Required Extensions

- oriented / aligned
- on_layer / side
- between / blocking
- anchored_to_region

Each constraint must include:
- scope (what objects)
- metric (edge‑to‑edge, loop area, etc.)
- threshold + units
- tier
- human‑readable reason (`because`)

---

## 8. Deterministic Routing Role

Routing is responsible for:
- topology‑first → geometry‑second realization
- DRC + physics pruning *in the loop*
- acting as verifier and diagnostic tool

Routing is **not** responsible for fixing bad placement.

---

## 9. Physics Integration Strategy

### Early (Fast Proxies)
- loop area metrics
- switch‑node proximity cost fields
- mutual coupling heuristics

### Later (Optional)
- batch EM / thermal simulation for verification & calibration

Physics is conservative and pruning‑oriented, not perfectly accurate.

---

## 10. Via Modeling

Vias are treated as components:
- inductance
- resistance
- thermal impedance
- reliability limits

Power vias synthesized as arrays with explicit budgets.

---

## 11. Manufacturing Variability

- worst‑case geometry inflation
- tolerance envelopes
- margin reporting (not just pass/fail)

Goal: manufacturable, not just routable.

---

## 12. Explainability

Every decision produces a trace:
- which constraint forced it
- which alternatives were rejected
- which physics metric dominated

This is mandatory for trust, debugging, and adoption.

---

## 13. Project Goal Statement

> Build a **deterministic, loop‑centric, physics‑aware placement + routing system** where:
>
> - placement is primary
> - routing is proof
> - physics prunes the search
> - failures are explainable
> - bad schematics are rejected early

---

## 14. Next Planning Step

Use this document to:
- break the system into epics (placement engine, router, physics, explainability)
- sequence milestones (baseline → loop‑aware → physics‑aware)
- define acceptance tests using known good / bad induction layouts

This document intentionally avoids implementation detail so planning can proceed cleanly.

