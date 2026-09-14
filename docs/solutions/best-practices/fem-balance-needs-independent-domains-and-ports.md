---
title: "FEM power balance needs independently checked domains and ports"
date: "2026-09-14"
module: zapote
problem_type: best_practice
component: testing_framework
severity: high
applies_when:
  - "promoting Gmsh and Elmer output into PCB engineering evidence"
  - "coupling local conductor models to an uncertain shared package"
tags:
  - "thermal-model"
  - "energy-balance"
  - "independent-oracle"
  - "evidence-binding"
---

# FEM power balance needs independently checked domains and ports

A converged solver can solve the wrong physical problem exactly. During the
bridge model extension, failed prototypes merged distinct materials, lost
boundary ports, or clamped internal interfaces to a reservoir. A successful
process exit and a balanced heat total could not distinguish those problems
from valid engineering evidence.

Check geometry before interpreting temperatures. The new Rust joint model
independently calculates expected copper, substrate, solder and lead volumes,
counts shared tetrahedron faces, and requires reservoir ports to lie on actual
exterior cut faces with the expected material and area. Its rectangle and
obround references include unequal dimensions; the volume formulas do not
reuse the mesher's volume output as their own expected answer.

Electrical and thermal balances need different observations. The electrical
check uses imposed current times the measured port potential. The heat check
uses the integrated Joule source and the sum of boundary heat reactions.
Assigning the Joule total to a variable called electrical input power would
produce a tautological check. The regression changes voltage while retaining
Joule power and requires rejection.

Elmer boundary reactions also need a carefully chosen interpretation. The two
board ports meet at edge nodes, so their separate reported heat contributions
are not reliable partitions between copper and substrate. Their sum is used.
The isolated lead port provides the package coupling reaction. A shared package
receives its loss allowance once; each local conductor contributes its own
Joule heat. Per-contact residuals and the global residual must both close.

The retained native reference and mutation tests are under
`zapote/thermal/physical-model/joint-fem/` and
`zapote/packages/zapote-thermal/tests/joint_fem.rs`. The pending branch change
also binds the joint evidence tree in the common runner and regenerates solver
physics during replay. Changed summaries, missing ports and disabled Joule
heating reject even if producer hashes are refreshed. Gzip archival preserves
the hashes of the original bytes; dual raw/compressed copies reject as ambiguous.

A separate lesson from this comparison is that graph segment numbers are not
stable trace identities: widening the same native trace changed its split
ordinal. The new physical adapter requires the exact trace UUID, net and a
unique determined cut current. Uniform current through short pad-overlap
segments remains a stated distribution assumption. It is not a resolved
full-board current field.

Use this procedure to establish numerical validity, then assess applicability
separately. Unknown package paths, lead material, wetting and cooling conditions
remain unknown after convergence. The package node is not a resolved die
junction, and a whole-joint peak is not a separately measured PCB temperature.
The existing branch-current findings therefore remain independent of the FEM
verdict. See also [semantic binding](model-certificates-need-semantic-binding.md).
