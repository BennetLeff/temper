---
title: Verified monotonicity bounds close the sensitivity-sweep soundness gap
date: "2026-07-09"
category: best-practices
module: temper_placer
problem_type: best_practice
component: testing_framework
severity: high
applies_when:
  - "a sensitivity sweep over uncertain parameters gates a safety or performance verdict"
  - "random sampled perturbations could miss an interior resonance or worst case"
  - "a parameter box has provably monotone response — and you want a mathematical guarantee, not a sample"
tags:
  - soundness
  - monotonicity
  - interval-bounds
  - sensitivity-sweep
  - gate
  - worst-case
---

# Verified monotonicity bounds close the sensitivity-sweep soundness gap

## Context
A helps-battery sensitivity sweep over uncertain thermal parameters (power, conductivity, ambient, through-plane sink) used random N-point sampling to test whether the verdict held across the uncertainty range. Sampling avoids the elementary endpoint-only trap but cannot guarantee it captured the true worst case — a resonance or non-monotone response in an interior parameter value could be missed. Each additional "good" perturbation made a false-KEEP more likely, and no test could distinguish "sampled enough" from "actually worst."

## Guidance
If the model response to each uncertain parameter is **provably monotone** over the uncertainty box, the worst-case configuration is a corner of the box (the combination of parameter extremes in the monotone-ward direction). Determine monotonicity from the model structure:

- For an M-matrix system `A T = b` (thermal FDM, many elliptic PDEs), the inverse is nonnegative (A⁻¹ ≥ 0). Then T is monotone **increasing** in sources (Q, T_amb) and monotone **decreasing** in conductances (k_eff, h_sink).
- For parameters where monotonicity is proven, the corner-bound is a **mathematical guarantee** — not a sample, not a heuristic. If the verdict holds at the worst-case corner, it holds for *every* configuration in the box.
- Gate truthfully: tag the verdict as `"sound"` when the corner passes, `"sampled-only"` when it doesn't. The gate reports truth — it never pretends soundness where the corner violates the ceiling. A realistic worst-case corner (e.g., pure FR4, max power, max ambient, zero through-plane sink) is deliberately brutal, and most real configurations will be `"sampled-only"`. This is correct — it forces the model owner to either harden the corner input (the copper/power/heatsink ladder) or acknowledge the honesty gap.

## Why This Matters
A sampled sweep that misses a worst case produces a false-KEEP — the exact map-vs-territory failure the verification discipline was built to prevent. Converting to a verified bound is the difference between "looked at N points" and "mathematically guaranteed." It closes the last prose-ahead-of-gate delta in the L2 column and makes the soundness claim genuinely sound.

## When to Apply
- Any sensitivity sweep over uncertain parameters where the system matrix has provable monotonicity properties.
- Any gating decision (safety, performance) that must hold across an entire uncertainty range, not just at sampled points.
- The monotonicity argument is cheap when the system is an M-matrix; for non-M-matrix systems, monotonicity must be proven per-parameter or the corner-bound cannot be trusted.

## Examples
For the thermal FDM helps-battery, all four parameters are provably monotone via the M-matrix property:
- Power (P): increasing. `T ∈ A⁻¹b`, A unchanged, `A⁻¹ ≥ 0` → T increases with Q.
- Conductivity (k_eff): decreasing. `k' ≥ k ⇒ A(k') ≥ A(k) ⇒ A(k')⁻¹ ≤ A(k)⁻¹` → T decreases.
- Ambient (T_amb): increasing. `A⁻¹ ≥ 0` → T increases with `b`.
- Through-plane sink (h_sink): decreasing. `∂T/∂h_i = A⁻¹e_i (T_amb − T_i) ≤ 0` since `T_i ≥ T_amb`.

The worst-case corner is (max power, min k_eff, max T_amb, min h_sink, zero copper) — the pure-FR4 envelope. If the verdict holds at this corner, it is mathematically sound across the entire parameter box.

## Related
- `docs/solutions/logic-errors/endpoint-bounding-unsound-without-monotonicity-2026-07-09.md` (the endpoint-only trap that motivated this)
- `docs/solutions/best-practices/termination-is-not-convergence-2026-07-09.md` (halting ≠ convergence — the same "claim what you've actually proven" discipline)
- `docs/physics-verification-methodology.md` (four-layer verification pattern — verified bounds are layer 2: domain-invariant, cross-validated by MMS in layer 3)
