# Native copper meshing and current integration review

Scope: changes after `2b2f4f4ad6b3a2f397bce719c80c5b47ab42b58e` on
`codex/zapote-layout-quality`. Intent: reconstruct the remaining saved-copper
paths and make a declared current experiment execute on real native geometry,
with useful comparisons and explicit physical/model limits.

The implementing agent reviewed correctness, adversarial failure cases, tests,
API changes, maintainability, performance and project instructions sequentially,
as required by the user's AGENTS tool mapping. This is not an independent or
cross-model review. No independent reviewer was run; numerical and native
oracles provide the separate evidence described below.

## Findings addressed

- The initial iterative solver passed small closed-form tests but exhausted its
  budget on most real-board nets. Replaced it with the maintained Rust `faer`
  sparse Cholesky backend, diagonal equilibration and iterative refinement.
- Absolute nodal sums cancelled on highly conductive short edges. Compute KCL
  and voltage gradients from differences; check KCL after scaling to actual
  current, and independently integrate sheet/barrel energy. No tolerance was
  relaxed to absorb the failures.
- Two of seven paths exceeded the 3% R-refinement criterion at 2/0.5 mm².
  Tightened both meshes to 0.5/0.125 mm²; retained the unsuccessful run.
- Separate centreline limitations from full-copper connectivity gaps. Retain
  abstract barrel-link semantics and mesh-dependent witness lengths explicitly.
- Do not publish a failed or insufficiently refined solve as zero R/loss.
  Omit its metrics and preserve null before/after deltas plus case diagnostics.
- Propagate unsupported native geometry into current status; verify board and
  ordered stack identities. Baseline tool/profile mismatches remain rejected.
- The scratch thickness test first failed the existing total-stack guard.
  Corrected the scratch board's general thickness to match its modified layers.
- Add barrel coordinates and physical pad labels so current results can be
  located on the PCB without reverse-engineering UUIDs.

## Correctness and limits examined

Planar triangulation preserves native union boundaries, holes and separate
islands. Contacts use actual native copper; net labels alone do not connect
islands. Plated round/slot cross-sections use declared plating and nominal hole
sizes. Source/sink terminal electrodes and pad/via annuli are explicitly ideal;
this excludes radial crowding and package/lead/contact resistance. Terminal
contacts may span layers; that is the declared boundary condition, not a claim
about how current enters a physical solder joint.

Sheet conductance uses thickness in metres; gradients and areas use consistent
millimetre units. Independent strip and annular formulas verify R, current
density, I²R and discretization convergence. Series barrels and parallel layers
verify topology and sharing. Current/model assumptions require finite positive
values. Solver/mesh budgets fail closed. The total triangle count includes
unused islands; active and unused node counts are separate.

The new public native snapshot/report schemas are v3. The live envelope remains
v1 with an additive optional current report; enabling the current profile changes
the comparison profile identity. Python transports native facts only. No donor
Python implementation, pinned oracle, production PCB or firmware file changed.
The original `power_branches` tree kernel remains test-only; this FEM handles
parallel sharing directly and is not presented as complete P1 integration.

Simplification kept one mesh builder shared by path and current consumers,
reused existing report comparison and resistance code, and replaced custom
iterative numerical code with a tested sparse factorization library. The sparse
backend adds locked dependencies, with default threading/random features off.

## Verification and delivery boundary

See `zapote/layout-quality/mesh-evidence/README.md` for final commands, counts,
source hashes, native snapshots, scratch mutations and performance receipts.
Full workspace/property tests, focused final tests, native mutation checks,
Clippy, formatting, import boundaries and regeneration were exercised. The
common five-unit runner was rerun; missing acceptance inputs remain explicit.

No unresolved implementation defect was identified in this bounded feature.
This does not establish local-peak convergence, full operating current moments,
AC/inductive behavior, temperature, ampacity or full 120 V board acceptance.
Those remaining software and physical inputs are documented in CURRENT.md and
the integration audit, and remain tracked under issue #1628.
