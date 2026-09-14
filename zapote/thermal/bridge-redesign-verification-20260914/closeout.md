# Bridge redesign integration closeout

The source-bound candidate study, resolved Gmsh/Elmer joint model, Rust replay
integration and conditional cooling comparison are retained together. The
maintained power-entry board is not promoted or qualified by this work.

## Decision

Keep the current board as the reference. The 3 mm candidate reduces nominal
whole-joint peak by 1.28 K, while the weak-assembly sensitivity still reaches
159.56 °C. More mesh refinement is unlikely to change that decision. Develop
the wider-pitch GBJ assembly with its own thermal inputs, or resolve the missing
package/lead/assembly/cooling evidence before choosing a final repair.

- [Physical comparison](../physical-model/comparison.md): baseline and 3 mm,
  identical source/load/material assumptions, mesh and domain checks.
- [Connection study](../../power-entry/bridge-redesign/comparison.md): reviewed
  pin semantics, compiler receipts, native-clean GBJ, rejected 6 mm experiment.
- [Cooling options](../cooling-options/README.md): retained component sources and
  airflow/contact limitations; enclosure/system-curve fit remains unresolved.
- [Candidate review](candidate-review/resolution.json): three source/provenance
  findings resolved, including all referenced compiler outputs.

## Harness changes that persist

The common runner requires and records physical-model, source-loss and resolved
joint checks. Its input identity includes the full joint evidence tree. Replays
check raw meshes, logs, scalars and solver commands, regenerate model geometry
and physics, and reject source/board/waveform drift. Gzip stores large artifacts
losslessly while preserving the hashes of the original bytes.

Regression cases cover missing/incorrect material domains and ports, changed
voltage, inconsistent heat, edited summaries, disabled Joule heating, rehashed
geometry, ambiguous compressed evidence, altered native drill/stackup, changing
trace split ordinals, and contradictory duplicate source pin maps.

Four existing DRC.PFC.BRANCH_COPPER failures remain on the maintained board.
Numerical validity cannot clear those findings or establish physical applicability.
No purchase, fabrication, powered test or mains qualification was performed.

## Learning and memory

The durable explanation is
[independent FEM domains and ports](../../../docs/solutions/best-practices/fem-balance-needs-independent-domains-and-ports.md).
The new bridge-fem-lessons-v1 memory revision contains portable procedure only.
Its preparation receipt selects the new note and excludes unmatched RTD-specific
facts; delivery to a future agent is not claimed.

Documentation was captured in lightweight mode. Frontmatter and mechanical
claims checks passed. Vocabulary scan found no new project-specific term;
existing instructions already surface docs/solutions, so no discovery gap was found.

## Final verification

The [common run](common-run/summary.json) has seven units, no source changes
during execution and exactly the four retained branch-current failures. The
[power-entry report](common-run/power-entry.json) exposes the passing physical,
source-loss and joint numerical results alongside indeterminate applicability.
The thermal suite passed 79 tests; the final harness library passed 35, runner
integration passed 5 and remaining harness integration passed 50. The real
pretty-printed contract round-trip and native-dimension mutation regression pass.
Import boundaries and generated-artifact checks pass. All-target Clippy completes
with only the previously recorded warnings in unchanged ERC/DRC files.

Frozen CAD, compiler CSV and solver outputs retain their original whitespace
and line endings to preserve evidence hashes. They are not reformatted to
satisfy source-code whitespace lint.
