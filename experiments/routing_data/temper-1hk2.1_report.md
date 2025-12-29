# Experiment Result: temper-1hk2.1
## Router Ceiling Test (50 RRR Iterations)

**Date:** 2025-12-29
**Command:** `uv run python scripts/internal_route.py pcb/temper_ready_for_route.kicad_pcb --exclude-power-nets --rrr-iters 50 --soft-blocking --cell-size 0.25`

### Metrics
- **Nets Attempted:** 14 (Power nets excluded)
- **Nets Completed:** 6
- **Completion Rate:** 42.86%
- **Total Runtime:** 539.59s
- **Conflict Locations:** 2
- **Severe Conflicts:** `GATE_H` and `SW_NODE` are fundamentally blocked.

### Failed Nets
- `GATE_H`
- `GATE_L`
- `SW_NODE`
- (and others not explicitly listed in terminal but inferred from completion rate)

### Conflict Details
- `(52.5, 104.5, L1): GATE_H, SW_NODE`
- `(22.0, 66.2, L1): GATE_H, SW_NODE`

### Conclusion
The router is unable to resolve conflicts even with 50 iterations of Rip-up and Reroute. The bottleneck is the **router's inability to find paths** in the current placement or the grid resolution/strategy is insufficient.
Completion is < 100% (6/14), therefore **Router is the bottleneck**.

**Recommendation:** Prioritize Phase 1 (Router fixes/enhancements).
