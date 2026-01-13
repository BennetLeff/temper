Baseline sweep of 12 DSN files completed.

**Results Summary:**
- **Best performance:** 13 unrouted nets.
- **Top DSNs:**
  - pcb/temper_fixed.dsn
  - pcb/temper_ordered.dsn
  - pcb/temper_no_layer_restrict.dsn (This one was previously reported as having 29 unrouted, but achieved 13 in this run).
- **Worst performance:** 74 unrouted nets (temper_agent_test.dsn, temper_boundary_fixed.dsn).

**Common Patterns:**
- The 13 unrouted floor seems consistent across several 'good' DSNs.
- temper_ordered.dsn and temper_fixed.dsn are strong candidates for further optimization.
- The discrepancy in temper_no_layer_restrict.dsn suggests either non-determinism in FreeRouter or that the current floorplan is actually better than previously thought even without restrictions.
