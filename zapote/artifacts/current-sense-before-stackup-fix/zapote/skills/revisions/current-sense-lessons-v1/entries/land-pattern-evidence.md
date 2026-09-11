# Verify the geometry before interpreting clearance

Before rejecting a component or moving copper to satisfy a corridor, inspect the official exact-package drawing. Identify each dimension's endpoints and view; distinguish body dimensions, lead centers and copper edges. Reconstruct one native pad census and compare it with that drawing. KiCad agreement with a supplied footprint proves implementation consistency, not correctness of the supplied shape.

The current-sense build exposed a CST3015 drawing dimension interpreted at the wrong endpoints. An independent drawing review and native readback corrected the standalone footprint. Do not transfer its numerical dimensions to a different package or assume PCB spacing qualifies device insulation. Read current sources for exact facts.

Evidence: docs/solutions/logic-errors/cst3015-land-pattern-edge-gap.md. This note is advisory and cannot relax any Rust rule or physical qualification requirement.
