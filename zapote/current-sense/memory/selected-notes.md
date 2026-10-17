## rtd-mem-001: Qualify model meaning before accepting model output

# Qualify model meaning before accepting model output

This is portable engineering guidance, not an acceptance rule or a source of component limits.

Before accepting analytical or SPICE results:
1. Inspect the actual post-fault circuit graph. Account for every remaining current path, including threshold dividers. Verify that an injected open opens rather than reconnects the wire.
2. Match datasheet limits to their columns, test conditions, operating envelope and stated guarantees. Keep typical values separate from guaranteed bounds.
3. Check model and circuit identities, then check meaning: runtime fault rows must agree with the independently justified certificate. Rehashing contradictory output must still fail the normal validator.
4. Use an independent derivation or simulator as an oracle. Sampled agreement helps find defects but does not prove coverage of a continuous parameter range.
5. Preserve device applicability and hardware characterization gaps as INDETERMINATE or NOT RUN. Mathematical qualification does not qualify omitted physical behavior.
6. Retain counterexamples through the normal Rust validation entry point: stale sources, missing or duplicate faults, changed parameter ranges, and rehashed contradictory claims.

For another unit, derive its own equations, fault cases and limits. Current source, constraints and Rust validators govern acceptance. Record which lesson affected a decision; propose new lessons with evidence for review between attempts. A statement that a helper ran is not execution evidence.


