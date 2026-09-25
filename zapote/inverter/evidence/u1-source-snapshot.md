# U1 source snapshot and arithmetic

Read 2026-09-23 from the `codex/zapote-parallel-units` worktree at parent base `cbfcc2ebcff9adfcab0f8d3adc1b6dde32005e02`. Rev38 is a concurrent candidate, so a later edit requires rechecking its bytes and the inverter interface claim. These hashes bind **read bytes**, not an approved physical design.

| Read source | SHA-256 |
| --- | --- |
| `elec/src/main.ato` | `492faf4b04351003c859512332b91d207e234274a4b7344f86c3674477626461` |
| `elec/src/modules.ato` | `1f9acff6493bad71bdb145ca6a42f7567d70f3c0b30f6bc6c22d082aec01ba0d` |
| `docs/hardware/TANK_COIL_SPECIFICATION.md` | `2018512d9a7f34aa7ebb114176974f4bbbb94a05ff87923a368591bcd657f579` |
| `zapote/gate-drive/source-build-09/elec/src/gate_drive_unit.ato` | `6e81398feb135f9a7382033173beda50f7a9cb8b7602ccab00a032f4fe40b2b1` |
| `zapote/power-entry/passive-reva/protection/interface-integration-38/elec/src/pfc_power.ato` | `e3daa14ea8b74344c307a86908c86cbf4d9b44447af367febeb4b581a84ba761` |
| `zapote/power-entry/passive-reva/protection/interface-integration-38/PFC-POWER.md` | `f776b6bfccf138cf5d5c3e81216374233182ebf36e67d0f27a2c64fb180a434d` |

Independent dimensional checks run with Python 3 `math` on these stated values:

| Calculation | Result | Use |
| --- | --- | --- |
| `4 × 560 µF` | `2.24 mF` nominal | VB bank inventory only |
| `0.5 × 2.24 mF × (390 V)²` | `170.352 J` nominal | Stored-energy inventory only |
| `150 µH × 0.399`; `88 µH × 0.68` | `59.850 µH`; `59.840 µH` | Exposes historical cancellation; not a new coil measurement |
| `79.2 µH × 0.60` | `47.52 µH` | Demonstrates ratio-only acceptance failure against 53.43 µH absolute floor |
| `1/(2π√(59.84 µH × 300 nF))` | `37,563.3 Hz` | Reproduces old nominal *loaded* resonance, not a Rev38 operating point |

The corresponding U1 interpretation and unresolved cross-unit inputs are in [../interface-contract.md](../interface-contract.md) and [../coil-evidence.md](../coil-evidence.md).
