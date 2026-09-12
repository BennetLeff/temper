# Copper-bar reference receipt

The native M2 Pro run passed the three-mesh electrical-conduction and Joule-heating
reference. This establishes the reference execution path; it does not qualify a PCB.
See [model and acceptance definitions](../../README.md) and the
[native installation receipt](../native-2026-09-12/README.md).

| Mesh size | Nodes | Resistance | Power | Peak rise |
|---|---:|---:|---:|---:|
| 0.5 mm | 356 | 86.20689655 µΩ | 4.64 W | 7.25006733 K |
| 0.25 mm | 1,794 | 86.20689655 µΩ | 4.64 W | 7.25098279 K |
| 0.125 mm | 10,392 | 86.20689655 µΩ | 4.64 W | 7.25072237 K |

Analytic expectations are 86.20689655 µΩ, 4.64 W and 7.25 K. All configured
tolerances pass. The per-case mesh/conversion/solve times were 354, 487 and
1,698 ms with one OpenMP thread; these are observations, not a performance study.

## Retained evidence

- `report.json` contains measurements, node counts, tool versions, source identity,
  execution times and SHA-256 identities. All 247 recorded artifact and solver-module
  hashes were checked immediately after the final run: `hash-verification.log`.
- `run.tar.gz` retains the complete run directory, including meshes, VTU fields,
  raw stdout/stderr, inputs and per-command execution records. Archive SHA-256:
  `dd68905243c19baa16341b4fb2271c0d3d4ad50fd0d03ca3bd11fade52e79182`.
  Its root is `zapote-thermal-canonical-final-b7e41-20260912/`.
- `workspace-tests.log`: **335 passed, zero failed**. Of these, 15 are thermal
  reference, parser, tamper, execution-failure and timeout regressions.
- `index-checkout-tests.log`: all 15 thermal tests compile and pass in a separate
  Git checkout assembled only from staged manifests and package files. In
  particular, all three required raw solver logs are tracked.
- `clippy.log`: the thermal crate and all its test targets pass with warnings denied.
- `parser-before-fix.log`: four strict-evidence regressions failed against the
  earlier permissive parser. `thermal-tests.log` records the corrected suite.
- `review.json`: completed code review with no actionable findings after fixes.
  Its final-native-run limitation reflects review timing; the canonical run and
  hash verification recorded above completed afterward. Live execution remains
  an explicit Make target rather than a dependency of ordinary Cargo tests.

The final run identifies parent commit
`cb80a1df1246cd9227431baa57d9f42381489fd9` and honestly records `dirty: true`:
the new backend and this receipt had not yet been committed. The runtime binary,
model and retained outputs are identified by their content hashes.

## Verification lessons

Checking a second checkout with a shared Cargo target can leave the executable
compiled with that checkout's `CARGO_MANIFEST_DIR`. A subsequent run reused that
binary and correctly reported the temporary checkout's identity. A forced rebuild
from the canonical checkout restored the intended identity before the final run.
Always inspect the recorded source identity, not only the invoking shell's directory.
Likewise, hash verification must precede another build that replaces the runner
binary. These are execution-evidence checks, not numerical discrepancies.

The runner now rejects altered reference templates, malformed or ambiguous scalar
columns, raw-log/scalar disagreement, non-finite results and stale output directories.
Failures retain a structured report; subprocess timeouts kill descendant processes.
These behaviors are regression-tested. Real-board material properties, cooling,
terminal temperatures and geometry transfer remain future model work.
