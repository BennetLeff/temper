# Draft: DECISIONS 39 update, adoption checks 1–3 (2026-10-14; not yet in DECISIONS.md)

Evidence: `validation-results/11-candidates/c33-six-layer/adoption/README.md`.

- **Item 1 (FEM commutation loops): DEFERRED.** Six layers is not adopted, on price. The pinned JLC061622-1080A
  quotes $19.11 per board at 500 (stackup fee $1,466.39, $2.93 per board) against $17.28 for the pinned four-layer
  JLC041622-7628, which trips this item's reversal clause. FEM is needed only if a stack-envelope route (JLC "No
  requirement" stack) is reopened.
  - **Reference.** Round 17's 37.6 / 24.5 nH come from native-21's first routed copper (board 76ec8cca), not s32.
    A re-run needs s32 and s33 on the same set-up.
  - **Ready to run.** The mesher takes the stack (`MESH_STACKUP`). It now refuses copper on an unknown layer instead
    of dropping In3 / In4. The closures are re-anchored (only R5 moved). The coarse reference meshes pass every gate
    on both boards and both legs. `fem/chain_c33.sh` runs it.
  - **Screen only:** the plane-pair term falls 1.28 / 0.74 nH.
- **Item 2 (sw-node capacitance vs ZVS dead-time margin): PASS.** The as-built D2 deck (F6, 2EDR, Rg 8.2 Ω) plus the
  screen's board sw-node capacitance. Worst corner: 2EDR weak output, 150 °C, 280 V, 37 A. S1 ZVS 42 / 42 per leg
  on both boards.
  - **Margin at the 340 ns audit edge.** Leg A: s32 151.1 ns, s33 150.6 ns. Leg B: s32 149.6 ns, s33 150.0 ns.
  - **ZVS current threshold.** Leg A: 11.65 → 11.73 A. Leg B: 11.73 → 11.65 A.
  - **Board worst leg:** 149.6 → 150.0 ns, not worse.
  - The leg-A loss (0.5 ns, 0.3 %) is the only literal "worse". It is well inside the screen's own uncertainty, and
    the board's worst-case margin improves.
- **Item 3 (EMI): PASS, unchanged.** The unmodified s19b model on each board's copper gives
  `emi_min_margin_dB` 10.479 on s32 (B.Cu 1.633 mm) and on s33 (1.658 mm).
  - The outer switch-node pours are identical (frozen base).
  - The depth change is below the model's 0.5 mm grid. On a 0.1 mm grid it moves the margin 0.0001 dB.
- **Against adoption:** nothing in items 2–3. Item 1 is open and moot while six layers is out on price.
- **Reverses if:** a stack-envelope quote brings six layers at or below four-layer POFV. Then item 1 runs first
  (`chain_c33.sh`), then F6 if either loop rises.
