# New Strategic Directions

This document tracks major architectural pivots, the reasoning behind them ("Why"), and the measurable impact ("How it helps").

## 3. Physics-Grounded Electrical Validity (Level 3) (December 2025)

### What we are doing
Integrating transient electrical analysis directly into the placement feedback loop. This includes:
1.  **PEEC Inductance Model:** Estimating parasitic loop inductance ($L_{gate}$) using calibrated Euclidean distances (~0.8 nH/mm).
2.  **Thermal Resistance Network:** Replacing distance-to-edge heuristics with a full $R_{\theta JC} + R_{\theta CH} + R_{\theta HA}$ model.
3.  **Automated SPICE Integration:** Dynamically generating and running `ngspice` transient simulations during local refinement.

### Why we are doing it
*   **The Switching Stability Gap:** Placements that are geometrically valid often fail electrically due to parasitic ringing or Miller-effect shoot-through.
*   **Safety Criticality:** High-power induction (1.8kW) requires accurate junction temperature ($T_j$) predictions to prevent IGBT thermal runaway.
*   **The "Stub" Problem:** Core electrical validation was previously a set of placeholders, leaving the optimizer blind to signal integrity and power integrity issues.

### How it is helping
1.  **Inductance Precision:** We can now quantify gate loop inductance (currently **34.4 nH** on Temper V1) and set hard engineering targets (≤10 nH).
2.  **Safety-Aware Refinement:** The orchestrator now automatically triggers additional placement iterations if $T_j > 150^\circ C$, reducing thermal violations by up to 14.5°C in test runs.
3. **Consistency:** The SPICE template system (using `common_options.spice`) ensures that all electrical verification uses stable, production-grade simulation parameters (METHOD=TRAP, RELTOL=0.001).

**See also:** [Electrical Validation Impact](ELECTRICAL_VALIDATION_IMPACT.md) for a detailed technical breakdown.


