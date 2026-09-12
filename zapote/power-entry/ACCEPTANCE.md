# Acceptance scope

Source-build-22 is the current 54-component active-PFC circuit. The routed
230 × 210 mm native candidate passes the recorded construction checks:

| Check | Actual result |
|---|---|
| Atopile compile/export | PASS |
| Native ERC, all severities | 0 findings |
| Native DRC, all track errors and schematic parity | 0 violations / 0 unconnected / 0 parity |
| Rust exact source/component/pad graph | PASS |
| Rust saved-byte binding and physical stackup | PASS |
| Rust native copper connectivity | PASS, all 33 source nets |
| Rust voltage-domain copper spacing | PASS, 2 mm HV / 6 mm PE / 0.2 mm other pairs |
| Overall qualification | INDETERMINATE |

See [routed-checkpoint.json](evidence/routed-checkpoint.json) for exact hashes
and [routing-review.md](evidence/routing-review.md) for the geometry and limits.

The spacing profile is a prototype construction screen, not an insulation
coordination or product certification. Ampacity calculations do not replace
thermal measurements. External isolated bias, default-off HOT permit, precharge
and relay sequencing, low-line RMS foldback, switching/loop stability, inrush,
capacitor ripple, thermal, EMC, insulation, active discharge and mains
qualification remain open. Physical tests are **NOT RUN**. This is not a
fabrication release or an authorization to energize the board.
