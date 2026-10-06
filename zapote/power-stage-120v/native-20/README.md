# Native20 engineering candidate

**Value-only revision of [native-19](../native-19/README.md): R34 and R8/R16.
Copper is unchanged. Native DRC/ERC match native-19. Product qualification is open.**

| Ref | Source instance | native-19 | native-20 | Why |
| --- | --- | --- | --- | --- |
| R34 | `r_th_top` | RT0603BRD0710K5L (10.5 kΩ) | **RT0603BRD0710K6L (10.6 kΩ, ±0.1 %, 25 ppm/°C)** | Task 02 decision B. The shunt-OCP band moves from 38.44–85.55 A to **49.73–97.98 A**, which meets the ≥ 44 A nuisance-trip minimum |
| R8, R16 | `leg_a/leg_b.r_dis_pu` | RC0603FR-071KL (1 kΩ) | **RC0603FR-07330RL (330 Ω)** | The allocated DIS rise drops from 360.8 ns to 119.1 ns, putting the chain at ≤ 546/573 ns (CT/shunt) |

Decided in [DECISIONS.md](../DECISIONS.md) 2026-10-05 (protection closure). The
evidence is in [D-31](../validation-results/01-switching-parasitics/round17/delegation/out-D31/README.md):
`retune.py` gives the band and `ledger.py` gives the timing. Both parts use the same
0603 footprint and the same nets.

## Evidence

- **Source:** `elec/src` was edited and compiled with atopile 0.2.69. The netlist is
  identical to native-19 apart from absolute build paths: ato 0.2.69 aliases
  netlist MPNs, so values travel in the CSV and `resolved-components.json`. Those
  two files change only in these three parts. The source audit passes 66/66
  tests and the full connectivity audit (142 components, 89 nets). `audit.rs`
  IDENTITY now pins the new MPNs.
- **Board:** built by `prototype-closure/pcb/build_native20.py`. It refuses any
  native-19 board or schematic that differs from native-19's final manifest,
  then rewrites only the Value/MPN text in the three parts' footprint, symbol
  and instance blocks, with an exact count per block. After the zone refill and
  save, the board differs from native-19 in exactly six lines, all Value/MPN, so
  the copper is byte-identical.
- **DRC:** three runs (all-track-errors, schematic parity, zone refill). Each
  has **zero errors, zero unconnected items and zero parity findings**, with the
  same 36 library-mismatch and 3 silk warnings as native-19. **ERC:** zero errors;
  the same 13 + 3 warnings as native-19.
- **FEM:** [leg-region diff](verification/leg-region-diff.txt) gives leg A **UNCHANGED** and
  leg B **UNCHANGED**, with no stackup or FET-geometry flags. All native-19 switching
  evidence (leg A best matrix, leg B extraction) carries over unchanged.
- [final-manifest.json](verification/final-manifest.json) holds the hashes.

## Not covered

- **V3V3 load:** each 330 Ω pull-up draws up to 10.6 mA from the controller-side
  V3V3 (J4.3) while PERMIT holds DIS low. That is about 21 mA for both legs,
  versus about 7 mA before. The controller rail budget must include it (D-20
  requirements). Dissipation is 36 mW per 0.1 W 0603 resistor.
- **Bench confirmation:** the DIS and PERMIT edge timings are still allocations;
  a bench capture must confirm them. The threshold band must be confirmed on the
  bench as well.
- Library naming: this revision keeps native-19's `Native19:` symbol library
  nickname so that no unrelated text churns.
- The STEP and schematic PDF exports were not regenerated (no geometry change).
