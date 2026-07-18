---
title: "Board Capacity vs. BOM — Decision Memo with Per-Option Numbers"
date: "2026-07-18"
category: architecture-patterns
module: temper_placer
problem_type: decision_support
component: board-design
severity: critical
applies_when:
  - "Deciding how to close the board-capacity gap (option A: resize, B: BOM substitution, C: reviewed-overlap, D: blended)"
tags:
  - temper-placer
  - courtyard
  - board-size
  - bom
  - decision
---

# Board Capacity vs. BOM — Decision Memo with Per-Option Numbers

## Context

This memo re-derives the board-capacity math from [`production-board-courtyard-area-exceeds-usable-board-area.md`](production-board-courtyard-area-exceeds-usable-board-area.md)
into concrete, per-option candidate numbers a human decision-maker
(mechanical/enclosure, circuit-design, PCB-layout, or project-lead authority)
can act on.  It does **not** recommend or select an option — per
[the requirements document](../../brainstorms/2026-07-18-board-capacity-bom-decision-requirements.md):
"No option is pre-selected."

All raw numbers below were independently verified by the U4
area-sufficiency tool:
```bash
uv run python packages/temper-placer/scripts/analysis/area_sufficiency_check.py --pcb pcb/temper.kicad_pcb
```
Output: total courtyard area = 13,670.8 mm^2, usable area = 12,600.0 mm^2,
raw ratio = 108.5%.

## Current State

| Metric | Value |
|--------|-------|
| Board dimensions | 100 x 150 mm (15,000 mm^2) |
| Usable area (5mm margin) | 12,600 mm^2 |
| Total courtyard area | 13,670.8 mm^2 |
| Raw ratio | 108.5% |
| Components | 149 |
| Top-8 share (L1, PS1, C2–C5, K1, U22) | 7,860.1 mm^2 (57.5%) |

**Important caveat:** All "ratio" and "gap" numbers in this memo are
computed at **raw, 100% packing efficiency**.  Real-world packing of
mixed rectangle/circle components never achieves 100% area efficiency.
The original investigation uses 50–80% "generously" as a placeholder
packing-efficiency range (which implies the board might need to be
1.4×–2.2× larger).  A mechanical/PCB-layout expert should refine this
assumption before committing to exact dimensions.  Every table below
reports both the raw ratio and the effective ratio at example packing
efficiencies to avoid overstating precision.

---

## Option A: Enlarge the Board

Preserving the current 2:3 aspect ratio (100:150 mm).

| Scale | Dimensions (mm) | Usable Area (mm^2) | Raw Ratio | @70% Packing Eff. | @60% Packing Eff. | @50% Packing Eff. |
|-------|-----------------|-------------------|-----------|-------------------|-------------------|-------------------|
| 1.10× | 110 × 165 | 15,500 | 88.2% | 126.0% | 147.0% | 176.4% |
| 1.15× | 115 × 172.5 | 17,062 | 80.1% | 114.5% | 133.5% | 160.2% |
| **1.20×** | **120 × 180** | **18,700** | **73.1%** | **104.4%** | **121.8%** | **146.2%** |
| 1.30× | 130 × 195 | 22,200 | 61.6% | 88.0% | 102.6% | 123.2% |
| 1.40× | 140 × 210 | 26,000 | 52.6% | 75.1% | 87.6% | 105.2% |

- 1.20× (120×180 mm, +30 mm in height, +20 mm in width) is the
  smallest scale that gets the **raw** ratio comfortably under 100%.
  It is still at-risk under pessimistic packing efficiency assumptions
  (104.4% @70% PE).
- 1.30× (130×195 mm) clears even at 70% PE (88.0%), and at 60% PE is
  only 2.6% over (102.6%).  This is likely the minimum "safe" size if
  the 50–80% placeholder range holds.
- 1.40× (140×210 mm) comfortably clears at all reasonable PEs.

**Formula (usable area):** `(board_width - 10) * (board_height - 10)` mm^2 (5mm margin each side).
**Formula (raw ratio):** `(13,670.8 / usable_area) * 100`%.

### Option A Gate: MCH-03 (Glass Load 20kg)

`docs/STRATEGY.md`'s MCH-03 gate constrains glass-top sizing — the
glass must support 20kg load.  A larger board implies a larger glass
top.  A mechanical engineer must confirm the chosen dimensions fit
within the enclosure and glass-top design before any resizing
execution.  **This section presents candidate numbers only; it does
not verify or violate MCH-03.**

---

## Option B: BOM Substitution (Shrink Footprints)

Per-component leveragene at the current board size (100×150mm, usable
12,600 mm^2).  The gap to close at raw 100% PE is 1,070.8 mm^2.

### Single-Component Leverage

| Ref | Courtyard Area (mm^2) | 25% Reduction (mm^2 freed) | 50% Reduction (mm^2 freed) | 75% Reduction (mm^2 freed) | % of Gap at 50% |
|-----|----------------------|---------------------------|---------------------------|---------------------------|-----------------|
| L1  | 1,428.0 | 357.0 | 714.0 | 1,071.0 | 67% |
| PS1 | 1,196.6 | 299.2 | 598.3 | 897.4 | 56% |
| C2  | 989.4 | 247.4 | 494.7 | 742.1 | 46% |
| C3  | 989.4 | 247.4 | 494.7 | 742.1 | 46% |
| C4  | 989.4 | 247.4 | 494.7 | 742.1 | 46% |
| C5  | 989.4 | 247.4 | 494.7 | 742.1 | 46% |
| K1  | 716.8 | 179.2 | 358.4 | 537.6 | 33% |
| U22 | 561.2 | 140.3 | 280.6 | 420.9 | 26% |

**Formula (area freed):** `courtyard_area * (reduction_pct)`.
**Formula (% of gap):** `area_freed / 1,070.8 * 100`.

### Cumulative Leverage (50% reduction per component)

| Top N | Cumulative Freed (mm^2) | % of Gap |
|-------|------------------------|----------|
| L1 alone | 714.0 | 67% |
| L1 + PS1 | 1,312.3 | 123% |
| L1 + PS1 + C2 | 1,807.0 | 169% |
| L1 + PS1 + C2 + C3 | 2,301.7 | 215% |
| All 8 | 3,930.1 | 367% |

- A 50% footprint reduction on L1 alone closes 67% of the raw gap
  (from 108.5% raw ratio to ~102.8% — still over 100%, the board
  remains technically undersized).
- L1 + PS1 at 50% closes the raw gap completely (raw ratio drops to
  ~98.1%).
- A 25% reduction on all four bulk capacitors (C2–C5) frees 989.4 mm^2
  (92% of the gap).
- Any single capacitor (C2–C5) at 75% reduction closes ~69% of the gap.

**Important note:** These are leverage numbers, not replacement-part
recommendations.  Each substituted component must be re-verified
against its original electrical requirement by someone with
circuit-design authority — see Option B gates below.

### Option B Gates: EFF-01/EFF-02, PWR-01/PWR-02

`docs/STRATEGY.md`'s EFF-01/EFF-02 (efficiency, temp-rise) and
PWR-01/PWR-02 (electrical input, output, and isolation) gates constrain
the circuit design.  Undersizing any of these components risks:

- **L1 (inductor):** inductance drop, ESR increase, core saturation at
  peak current → EFF-01/EFF-02 efficiency/thermal risk.
- **C2–C5 (bulk capacitors):** reduced capacitance, ripple-current
  derating, voltage margin loss → PWR-01/PWR-02 ripple/stability risk.
- **PS1 (power supply module):** thermal dissipation, switching
  frequency, isolation requirements → PWR-01/PWR-02, EFF-01/EFF-02 risk.
- **K1 (relay/contactor):** contact rating, dielectric withstand →
  safety/isolation risk.
- **U22 (large IC/module):** depends on function — may affect any of
  the above gates.

A circuit designer must re-verify each substituted component against
these gates.  **This section identifies leverage only; it does not
assert that any specific substitution is electrically safe.**

---

## Option C: Reviewed-Overlap Acceptance

This option accepts some courtyard overlaps as reviewed-safe (e.g., a
courtyard margin that is deliberately conservative where the real
mechanical body does not reach).  The U1 violation report at
[`/tmp/courtyard_violation_report.md`][u1-report] (or regenerated via
the U1 tool) provides the exact 43 pairs (27 courtyards_overlap + 16
pth_inside_courtyard) a human PCB-layout reviewer needs to evaluate.

Up to 27 of the 43 violations are courtyard overlap violations; a
reviewer would assess each pair individually, write a one-line
justification per accepted pair, and those pairs would be encoded in an
explicit allowlist (not a threshold fudge) — see U7 in the plan for the
allowlist mechanism, deferred pending a human decision.

This option produces no board/BOM change and no executable deliverable
in this plan.  The U1 report exists today; the allowlist mechanism is
scoped but deferred (U7).

---

## Option D: Blended Scenarios

Concrete blended data points (vs. the "not yet analyzed" state in the
origin document).

### Scenario D1: Small resize + capacitor substitution

- Board: 115 × 172.5 mm (1.15×), usable area 17,062 mm^2
- BOM: 25% footprint reduction on C2–C5 (four caps, frees 989.4 mm^2)
- Resulting courtyard area: 12,681.4 mm^2
- Raw ratio: 74.3% (comfortable even at 70% PE: 106.2%, close at 60% PE: 123.8%)

### Scenario D2: Small resize + biggest inductor substitution

- Board: 110 × 165 mm (1.10×), usable area 15,500 mm^2
- BOM: 50% footprint reduction on L1 alone (frees 714.0 mm^2)
- Resulting courtyard area: 12,956.8 mm^2
- Raw ratio: 83.6% (at-risk under realistic PE, but a significant improvement from 108.5%)

### Scenario D3: Minimal resize + moderate substitution

- Board: 110 × 165 mm (1.10×)
- BOM: 25% reduction on Top-4 components (L1, PS1, C2, C3, total freed: 1,151.0 mm^2)
- Resulting courtyard area: 12,519.8 mm^2
- Raw ratio: 80.8% (marginally acceptable even at 80% PE: 101.0%)

**Formula (new courtyard area):** `13,670.8 - cumulative_freed`.
**Formula (new raw ratio):** `(new_courtyard / new_usable_area) * 100`.

---

## Risk-Strategy Gate Cross-Reference

| Gate | Constrains | Affected Options |
|------|-----------|-----------------|
| MCH-03 (Glass Load 20kg) | Glass-top sizing / enclosure fit | A, D (any board resize) |
| EFF-01 (Power efficiency) | Inductor (L1) sizing, thermal | B, D (any BOM substitution) |
| EFF-02 (Temperature rise) | Component thermal dissipation | B, D (any BOM substitution) |
| PWR-01 (Electrical input) | Capacitor ripple, PSU rating | B, D (any BOM substitution) |
| PWR-02 (Output/Isolation) | Isolation, relay rating | B, D (any BOM substitution) |

No gate directly constrains option C (reviewed-overlap), which is a
PCB-layout-review judgment rather than a hardware change.

---

## What This Memo Does NOT Do

- **Does not recommend option A, B, C, or D.**  The numbers are
  presented neutrally to inform a decision; the decision itself
  requires mechanical, circuit-design, and/or PCB-layout authority this
  memo does not have.
- **Does not select replacement part numbers for option B.**  Only
  area friction is computed; electrical re-verification is explicitly
  deferred to circuit-design authority.
- **Does not pre-judge which violation pairs are safe for option C.**
  The U1 report lists them; a human reviewer evaluates them
  individually.
- **Does not assert precision of the 50–80% packing-efficiency
  placeholder.**  This is the same placeholder from the original
  investigation and should be refined by a mechanical/PCB-layout expert
  before option A's exact dimensions are committed.

---

## References

- Origin investigation: [`production-board-courtyard-area-exceeds-usable-board-area.md`](production-board-courtyard-area-exceeds-usable-board-area.md)
- Origin requirements: [`../../brainstorms/2026-07-18-board-capacity-bom-decision-requirements.md`](../../brainstorms/2026-07-18-board-capacity-bom-decision-requirements.md)
- U1 violation-pair report: regenerable via `courtyard_violation_report.py`
- U4 area-sufficiency tool: regenerable via `area_sufficiency_check.py`
- Strategy gates: [`../../STRATEGY.md`](../../STRATEGY.md)
- Plan: [`../../plans/2026-07-18-001-feat-board-capacity-bom-decision-plan.md`](../../plans/2026-07-18-001-feat-board-capacity-bom-decision-plan.md)

[u1-report]: /tmp/courtyard_violation_report.md
