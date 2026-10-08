# 01 Switching parasitics — round 3

Board native-15, SHA-256 `a3ac1249f5052afe52944804cdc3f6ef0e8f895668360e79c1fa7b6fb7322155`.
Source `44417ae1489fd00e2d652fd3b2c1582b76d17630`, 2026-09-27.
Evidence is simulation and heuristic geometry, not measured hardware.

**Verdict: model stress and independence checks FAIL; physical board
qualification remains BLOCKED.** No board or source circuit was edited.

- [A1: reference ZVS/edges](a1-zvs/README.md): 540 grid cases and 811 total
  transients including refinements. Bracketed threshold sensitivity is
  within 6.04%, but edge-time sensitivity reaches 68.92%, including a ZVS
  case. The required independence gate fails. The 250 ns dead-time cases
  have no qualifying sampled current through 100 A.
- [A2: board inductance scenarios](a2-inductance/README.md): two actual
  FastHenry build failures led to the authorized geometric fallback.
  Connected copper/gate-return routes support explicitly heuristic stress
  inputs. Field validation, Q3 return-route convergence and bulk capacitor
  internal ESL remain unresolved; no physical inductance bounds are claimed.
- [B1: switching stress](b1-board-grid/README.md): the first 170 V, 37 A
  A-leg scenario crossed the 520 V die-VDS and 3 V off-gate criteria. Its
  reference-L control reproduces A1, and halving timestep preserves the
  finding. The modeled 723.918 V peak exceeds device rating and is not a
  calibrated physical prediction. The gate repeatedly rises after its off
  command. The plan's stop rule left 1,511 of 1,512 selected rows unrun.

The child reports contain assumptions, exact inputs, commands, raw results,
numerical checks and physical confirmation steps. B2 cannot treat a first
gate-threshold crossing as sustained gate-off. B4/B5 cannot use this packet
as a qualified ZVS or EMI envelope. Resolve the loop/common-source mapping
and parasitics, then validate commutation waveforms before continuing those
dependent acceptance claims.
