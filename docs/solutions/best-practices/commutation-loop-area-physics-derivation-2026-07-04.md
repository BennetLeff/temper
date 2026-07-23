---
title: "Physics derivation: commutation loop-area budget for half-bridge IGBT power stage"
date: 2026-07-04
category: best-practices
module: temper-placer
problem_type: best_practice
component: tooling
severity: medium
applies_when:
  - "Validating a numeric constraint in a PCB or EDA config against the underlying physics"
  - "Deciding whether a constraint enters a solver as a hard ceiling or soft lexicographic tier"
  - "Reverse-engineering a 'because' comment into a first-principles derivation"
tags:
  - physics-derivation
  - loop-inductance
  - igbt
  - half-bridge
  - commutation-loop
  - overshoot
  - di-dt
---

# Physics derivation: commutation loop-area budget for half-bridge IGBT power stage

## Context

The temper-placer constraint config (`configs/templates/loops/commutation.yaml`)
sets `max_area_mm2: 500` for the commutation loop with the comment "Commutation
loop EMI scales with area.  500mm² max for acceptable EMI at 25kHz switching
frequency."  The calendar-gate retirement requirements doc flagged this as a
blocking Resolve-Before-Planning question — loop_area needed to be classified as
a hard ceiling (feasibility) or soft lexicographic tier (tiebreaker) before the
constraint-completion workstream could proceed.  The physics derivation settles
the question: it's a hard ceiling.

## Derivation

### Source parameters

From `configs/templates/loops/commutation.yaml`:

| Parameter | Value | Field |
|-----------|-------|-------|
| `di/dt` | 1.0 × 10⁹ A/s (1 A/ns) | `events.di_dt` |
| `dV/dt` | 5.0 × 10⁹ V/s (5 V/ns) | `events.dv_dt` |
| Switching frequency | 25 kHz | `events.frequency_hz` |
| Peak current | 50 A | `events.peak_current_a` |
| RMS current | 25 A | `events.rms_current_a` |
| Max loop area | 500 mm² | `max_area_mm2` |

From `configs/constraints/temper_induction_cooker.yaml` and `configs/pcb_spec.yaml`:

| Parameter | Value |
|-----------|-------|
| IGBT | IKW40N120H3 (V_CE rated = 1200V) |
| DC bus voltage | 230V × √2 ≈ 325V |
| Derated ceiling | 1200V × 0.8 = 960V |

### Overshoot budget

The voltage overshoot across the IGBT at turn-off is determined by the
commutation loop inductance and the di/dt of the switching current:

```
V_os = L_loop × (di/dt)
```

Rearranging for maximum allowable loop inductance:

```
L_max = V_os_budget / (di/dt)
```

The overshoot budget is the difference between the derated IGBT voltage rating
and the DC bus voltage:

```
V_os_budget = (V_CE_rated × 0.8) − V_DC_bus
            = (1200V × 0.8) − 325V
            = 960V − 325V
            = 635V
```

Maximum allowable loop inductance:

```
L_max = 635V / (1.0 × 10⁹ A/s) = 635 × 10⁻⁹ H = 635 nH
```

### Loop area to inductance

For a compact, single-turn rectangular PCB loop with power-plane return
(1oz copper, 2mm trace width, 1.6mm PCB thickness), the loop inductance
scales approximately linearly with loop area for well-designed layouts:

```
L_loop ≈ 1 nH/mm² × area_mm²
```

This is a conservative engineering approximation accepted in power electronics
PCB design.  At 500mm²:

```
L_loop(500mm²) ≈ 500 nH
```

The overshoot at 500mm²:

```
V_os(500mm²) = 500 nH × 1 A/ns = 500V
```

### Margin check

```
Margin = L_max − L(500mm²) = 635 nH − 500 nH = 135 nH
Margin = V_os_budget − V_os(500mm²) = 635V − 500V = 135V
```

The 500mm² constraint leaves 135V / 135nH of headroom for:
- Parasitic trace inductance outside the core commutation loop
- Via inductance in the power path
- ESL of the DC bus capacitors
- Package inductance of the IGBTs (TO-247 package: ~5-10 nH per lead)

### Inflection point

Setting L_loop ≈ 1 nH/mm² and solving for the area where overshoot equals the
derated ceiling:

```
A_critical × 1 nH/mm² × 1 A/ns = 635V
A_critical = 635 mm²
```

Above 635mm², the overshoot exceeds the IGBT's 80% derated voltage rating
**regardless of snubber or gate drive tuning**.  This is a genuine infeasibility
— not a solver artifact, not a preference — because the IGBT would be destroyed
by overvoltage during hard switching.

The 500mm² constraint places the design at 500/635 ≈ **79% of the physical ceiling**,
leaving a 21% safety margin for parasitic inductances and component tolerances.

## Result

The 500mm² constraint is a **hard ceiling**.  It enters the CP-SAT constraint
encoder as a feasibility constraint (must satisfy), not a soft lexicographic
tier.  The tolerance is strict: the physics gate is `area ≤ 500mm²`, and UNSAT
above this threshold is a genuine infeasibility.  No tolerance slack — there
is no "close enough" when the IGBT voltage rating is at stake.

This validates the existing `max_area_mm2: 500` in `commutation.yaml` as a
physics-grounded value, not an arbitrary engineering guess.  The "because"
comment's "acceptable EMI" framing understates the constraint — the primary
failure mode is IGBT overvoltage destruction, not EMI compliance.

## When to Apply

Use this derivation pattern when:
- A numeric constraint in a YAML config needs to be classified as hard ceiling
  vs soft preference for solver encoding
- The constraint's "because" field provides a qualitative rationale but no
  quantitative derivation
- The constraint involves a physical failure mode (overvoltage, overcurrent,
  thermal runaway) rather than a quality preference (wirelength, spread)
- You need to determine whether UNSAT above the constraint is genuine or a
  solver artifact

Do NOT apply when:
- The constraint is a quality preference without a physical failure mode
- The relevant device datasheet is unavailable and the parameter cannot be
  derived from the codebase alone
- The constraint is already accompanied by a verifiable physical derivation
  in the config or adjacent documentation

## Related

- `packages/temper-placer/configs/templates/loops/commutation.yaml` — loop
  template with di/dt, dV/dt, and frequency parameters
- `packages/temper-placer/configs/constraints/half_bridge_base.yaml` — 500mm²
  constraint with because field
- `docs/brainstorms/2026-07-03-calendar-gate-jax-retirement-requirements.md` —
  requirements doc that flagged this as a Resolve-Before-Planning blocker
