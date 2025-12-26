# New Strategic Directions

This document tracks major architectural pivots, the reasoning behind them ("Why"), and the measurable impact ("How it helps").

## 2. Hierarchical Deterministic Placement Pipeline (December 2025)

### What we are doing
Implementing a multi-phase engineering pipeline that replaces the "one-shot" gradient descent search with a **Hierarchical Deterministic** approach:
1.  **Topological Phase:** Parametric templates (MCU, Power Stage) place critical macro-blocks.
2.  **Preflight Phase:** Fast feasibility checking catches impossible constraints (e.g., physical size limits).
3.  **Local Refinement Phase:** Gradient-based optimization limited to a 2mm trust-region for fine-tuning.
4.  **Routing Feedback Loop:** Iterative adjustment based on actual routing congestion.

### Why we are doing it
*   **The "Hallucination" Problem:** Unconstrained gradient descent would often "hallucinate" unmanufacturable positions (e.g., placing a decoupling capacitor inside the MCU die).
*   **The Engineering Gap:** Power electronics require specific topologies (e.g., Vertical Half-Bridge) that are difficult to discover through search but easy to define through rules.
*   **Verification Latency:** We previously waited for 8000 epochs to find out a design was infeasible. Preflight checks catch this in 0.1ms.

### How it is helping
1.  **Speed:** Placement is **65% faster** (7.1s vs 20.7s) by reducing the search space through deterministic macro-placement.
2.  **Physical Validity:** Overlap area reduced by **99.9%** (near-zero artifacts vs 8.8mm² massive collisions).
3.  **Routability:** organized layouts reduced overflow cells by **62%**, significantly easing the burden on the auto-router.
4.  **Reliability:** Eliminated board boundary violations and ensured perfect compliance with isolation zones (6.5mm reinforced isolation).

