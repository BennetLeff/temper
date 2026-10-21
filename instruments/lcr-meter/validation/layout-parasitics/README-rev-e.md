# PCB parasitics — Rev E (relay range switching)

Two Rev E boards are extracted. `run_reve.sh` takes each one from git, so the inputs are pinned. The CAD was only read.

| Variant | Board SHA-256 | Commit | What it is |
|---|---|---|---|
| `reve` | `2f6486c4…4bd8` | 1438ecbc9 | First relay layout |
| `reve_r104` | `cf379f85…95dc` | a04880a87 | As built: R104 (47 Ω) between U6A, net SRC_DRV, and SOURCE_BUF; SOURCE_BUF moved to In2 x 185.5, off DUT_HI. See [the R104 section](#r104-board-reve_r104) |

`sh run_reve.sh [reve|reve_r104|all]` regenerates every number below. For each variant `<v>` it writes:

- `geometry_<v>.json`
- `inductance_<v>.json`
- `fd_results/*_<v>.json`
- `extracted_<v>.json`
- `../stability-full-chain/<v>_extracted.rs` (the harness include)

`STAB=1 sh run_reve.sh` also reruns the stability modes. The Rev C and Rev D files are unchanged. Method and conventions are the same as in `README.md`. Every value is **low / nominal / high**, in pF and nH. No range is a bound unless the text says so.

## Findings

### Capacitance

The selected relay closes Kx.8–Kx.7 and Kx.3–Kx.4. Per range, the selected RF net is therefore merged into TIA_OUT and the selected RG net into SOURCE_BUF. Values are worst over the three ranges, and part terms are included.

| Quantity | Harness before (`fixedrelaycng100`) | Rev E extracted (low / nom / high) |
|---|---|---|
| **TIA_OUT node → GND** (TIA_OUT copper, relay pads, In2 bus, selected RF net, R67 codec tap) | Rev D board 10.53 + relay-pad estimate dC 3 / 10 = **13.53 / 20.53** | **8.17 / 10.07 / 14.62** |
| …TIA_OUT net alone | — | 6.57 / 7.39 / 10.99 |
| **SOURCE_BUF node → GND** (net + selected RG net) | **not modelled (0)** | **8.66 / 9.82 / 13.23** |
| **SOURCE_BUF ↔ DUT_HI** (broadside: In2 x 188.8 over B.Cu x 188.9, 31 mm) | not modelled | **2.03 / 2.42 / 2.99** |
| TIA_SUM → GND | 1.274 | 0.78 / 0.90 / 1.06 |
| TIA_SUM ↔ TIA_OUT (parallel to C104) | 0.399 | 0.12 / 0.21 / 0.32 |
| TIA_SUM ↔ DUT_LO (across R94) | 0.118 | 0.03 / 0.06 / 0.12 |
| DUT_LO (J3 side) → GND | 5.666 | 3.12 / 3.85 / 6.33 |
| DUT_HI → GND | 5.232 | 6.28 / 7.40 / 10.23 |
| DUT_HI ↔ DUT_LO | 0.158 | 0.11 / 0.14 / 0.16 |
| DUT_LO ↔ LOW_BUF | 0.15 | 0.06 / 0.09 / 0.14 |
| SOURCE_BUF ↔ TIA_SUM | — | ≤ 0.0001 (all corners) |
| SOURCE_BUF ↔ unselected RF nets (sum) | relay Cpp 0.5 / 2 per branch | 0.003 / 0.013 / 0.016 (board only) |
| SOURCE_BUF ↔ TIA_OUT | relay Cppsel 0.5 / 2 | 0.04 / 0.05 / 0.07 (board only) |
| TIA_OUT ↔ unselected RF nets (sum) | relay Coc 0.3 / 2 per branch | 0.33 / 0.77 / 0.94 (board only) |

The relay-internal terms are not in the board model and stay estimates: contact-to-coil Ccc, open contact Coc and pole-to-pole Cpp.

The **high** TIA_OUT and SOURCE_BUF values come from the thin-prepreg JLC04161H-1080 solve. On the default 7628 stackup they are about 10–11 pF.

The full per-range matrices are in `extracted_reve.json` under `ranges` and `spice`.

### Loop inductance

Values include the OPA2810 package closure, as in Rev C/D.

| Loop | Harness before | Rev E low (solid plane) | nom | **high (free space)** | Nominal geometry, solid / free |
|---|---|---|---|---|---|
| C104 branch | 4.87 (Rev D), 10 stress | 2.36 | not computed | **5.04** | 3.69 / 4.34 |
| RF branch, 100 Ω (K1, R43) | 21.65 + L_rel 10 / 20 | 50.39 | not computed | **64.93** | 54.10 / 63.87 |
| RF branch, 5 kΩ (K2, R44) | 50.46 + L_rel | 39.49 | not computed | **64.41** | 45.55 / 63.42 |
| RF branch, 100 kΩ (K3, R45) | 33.14 + L_rel | 73.92 | not computed | **92.44** | 77.02 / 91.35 |

The stability harness uses the free-space value plus the unchanged L_rel (10 / 20 nH).

Board paths found by the multi-layer walk:

- **TIA_OUT, from U7.1:** F.Cu to the via at (165.1, 102.0), then B.Cu along x 158.6, then a via to the In2 bus at y 126.2, then a via up to the pad. Lengths are 48.0 mm to K1.8, 45.2 mm to K2.8 and 62.8 mm to K3.8.
- **RF100:** In2 along y 124.2 and x 159.4, 28.7 mm.
- **RF5K:** F.Cu, 12.2 mm.
- **RF100K:** In2 along y 123.5 and x 160.0, 40.4 mm.

The Rev D RF loops ran 17–48 mm on F.Cu through the jumper headers. The Rev E C104 loop rose from 4.87 to 5.04 nH because the U7.1 → C104.2 trace narrowed from 0.4 mm to 0.2 mm.

### What the extraction changes in the stability result

See `../stability-full-chain/README.md`, mode `reverelaycng100`.

- **TIA loop: improves.** It goes from 55.97° to 58.10° at stress parasitics and the high board corner. The measured TIA_OUT copper (≤ 14.6 pF) is below the previous 10.53 + 10 pF stress allowance. Swapping the extracted RF lead for the shorter Rev D lead changes the margin by under 0.5°.
- **Source-driver (`drive`) loop: FAILS at the stress corner.** It falls from 48.29° to **38.46°**.
  - The cause is SOURCE_BUF board copper. This load was never modelled before: 13.2 pF to GND plus 3.0 pF to DUT_HI at the high corner. It sits on a unity-gain OPA2810 together with the estimated relay contact capacitances.
  - The details, and the proposed 47 Ω fix, are in the stability README.

## Method (differences from README.md)

### Geometry

- `export_geometry.py` (unchanged), run with `LP_GEOMETRY=geometry_reve.json` and `LP_SUM=TIA_SUM`.
- The stored In1 GND fill matches an in-memory refill (relative difference 0).

### FD capacitance

`fd3d.py` has three new windows.

**`reve` (150.5–190.5 × 86.7–139.5 mm)**

- This window covers the copper of all 13 conductors, whose bounding box is x 152.00–189.03, y 88.18–138.05.
- `check_window()` refuses any whole-board window whose margin is under 1.4 mm.
- 13 conductors: TIA_SUM, DUT_LO, TIA_OUT, DUT_HI, RF100/5K/100K, LOW_BUF, HIGH_BUF, SOURCE_BUF and RG100/5K/100K. None was dropped.
- Solved at dx 0.2 and 0.14 mm on 7628, and at 0.2 mm on 1080.
- A 0.1 mm solve (8.5 M unknowns, about 10 GB) did not fit beside the other jobs on the 32 GB Mac. The 0.14 mm solve used 4.1 M unknowns and 5.2 GB peak.

**Two-dx whole-board check, raw values at 0.2 → 0.14 mm**

| Quantity | 0.2 mm | 0.14 mm | Change |
|---|---|---|---|
| TIA_OUT ground | 6.61 | 6.73 | +1.8 % |
| SOURCE_BUF ground | 7.29 | 7.97 | +9 % |
| TIA_SUM ground | 0.818 | 0.782 | −4 % |
| SOURCE_BUF–DUT_HI | 1.47 | 1.82 | +24 % |

**Zoom windows, used for grid convergence**

- **`reve_relay`** covers K1 pins 3/4/7/8 and the In2 TIA_OUT, RF100, RF100K and SOURCE_BUF buses. Solved at 0.2, 0.14, 0.1, 0.07 and 0.05 mm.
- **`zoom`** is the existing U7/C104/R43–45 window. Solved at 0.2, 0.14, 0.1 and 0.07 mm.
- **`reve_hiside`** covers the SOURCE_BUF/DUT_HI broadside pair. Solved at 0.2 down to 0.03 mm.

Converged values:

- TIA_OUT ground in `reve_relay`: 2.057 at 0.07 mm, 2.077 at 0.05 mm.
- SOURCE_BUF–DUT_HI mutual: 0.81–0.84 pF from 0.05 to 0.03 mm. At coarse grids it moves −20 % to +4 %, because the 0.1 mm offset between the traces quantizes badly.

**How the nominal is built (`assemble_reve.py`)**

- Start from the whole-board 0.14 mm solve.
- Apply a ground factor of ×1.098: TIA_OUT ground, finest zoom over 0.14 mm.
- Apply a mutual factor of ×1.045: TIA_SUM–TIA_OUT, same ratio.
- Correct SOURCE_BUF–DUT_HI by its own ratio, ×1.243.
- The grid uncertainty is U = max(10 %, spread of all zoom ratios) = **11.1 %**. The spread is set by the SOURCE_BUF ground in `reve_hiside`, ratio 1.22.
- Low and high are ±U. High also takes the larger 1080-stackup ground terms and the +15 % mask uplift.
- Part terms: U7 pin pairs, the R40–R45 and R94 bodies, and the J3 posts, as in `assemble.py`.

### Inductance

`inductance_reve.py` reuses the parts, package and kernel of `inductance.py`.

**`board_path_ml()`** builds a graph over the net's copper:

- Tracks on all four layers, split at junctions and via positions.
- Vias as vertical segments between the copper z of each layer they reach. The radius is the drill radius.
- SMD land edges, as before.

On the Rev D board it reproduces the F.Cu-only `board_path()` lengths exactly (C104 loop and the JP4/5/6 paths), and the C104 loop L to 1e-15.

**RF loop:** U7.1 → TIA_OUT → Kx.8 → pad-to-pad hop → Kx.7 → RFx → R4x body → TIA_SUM → U7.2, closed through the package.

- The hop goes up at pin 8 to z = 0.3 / 0.6 / 1.0 mm, across 2.54 mm, then down at pin 7. It uses a 0.5 × 0.2 mm lead.
- **This hop is an assumption.** No TQ2SA terminal drawing is in `sources/`.
- Everything inside the relay base stays in L_rel.

**Plane treatment.** The loops have conductors on both sides of In1, so the single-sided image method is not valid. Two treatments are used instead:

- **free**: no plane. This is the upper value for the modelled geometry, because induced currents can only lower L.
- **solid**: In1 treated as a perfect, unbroken plane. Each half-space sees only its own currents and their images about its plane surface. Opposite sides do not couple, and the part of a via inside the plane copper is dropped. The real voids can only raise L above this, so it is the lower value for the modelled geometry with a perfect plane.

**A nominal for the perforated real plane is not computed.** It would need a field solve.

Validation:

- Circular loop to 6e-5 and microstrip +9–10 %, as in Rev C.
- The two-sided method on a strip under In1 matches the single-sided mirror exactly. This is a sign and regression check only.

## Limits

- **The capacitance ranges are engineering ranges, not bounds.**
  - The high corner is driven by the 1080 stackup, solved only at 0.2 mm. Its grid correction is borrowed from the 7628 zoom series.
  - The FD model has zero-thickness copper, no solder mask (covered by the uplift) and **no relay body**. The TQ2SA plastic (εr ≈ 3–4) over the pads and the internal contact metal are not modelled. Ccc, Coc and Cpp still carry that.
- **Inductance is the low-frequency, uniform-current value.**
  - Free space is the upper value only for the modelled path. Current spreading in the In2 bus and relay internals are not represented.
  - The VSSOP package closure and the relay hop are assumed geometry.
- **Relay-internal parameters are unchanged estimates** and are UNVERIFIED (range-switching §6): Ccc, Coc, Cpp, L_rel and Rc. The `drive` loop failure depends on them; see the stability README.
- **The `reve` numbers are for board `2f6486c4…`, which is superseded.** The as-built board is `reve_r104`; see the next section.

## R104 board (`reve_r104`)

Board `cf379f85…95dc`, commit a04880a87.

- **SRC_DRV.** U6 pins 1/2 (unity follower, feedback at the pin) are now net SRC_DRV. It runs on F.Cu to the via at (169.66, 88.96), then about 8 mm on In2, then to R104.1 at (176.5, 85.8).
- **SOURCE_BUF.** It leaves R104.2 through In2 down x 185.5, no longer stacked over DUT_HI at B.Cu x 188.9, then joins the y 129.6 bus as before.
- **Conductors.** SRC_DRV is a 14th conductor. It maps to the harness X6A node (`srcdrv`); SOURCE_BUF sits behind R104.
- **Window.** `reve_r104` is 150.5–190.5 × 83.9–139.5 mm. The conductor bounding box is x 152.00–189.03, y 85.33–138.05.

**Shorter schedule**

| Solve | Status |
|---|---|
| Whole board, 7628 at 0.2 and 0.14 mm | re-solved |
| Whole board, 1080 at 0.2 mm (high corner) | re-solved; cheap |
| New window `reve_hiside_r104` (183.5–191 × 105–120), 0.14 to 0.05 mm | solved |
| K1-relay and U7 zoom series | **reused from `reve`**: inside those windows (+3 mm) every conductor's copper and the In1 fill are identical on the two boards |
| Finest whole-board grid | not re-solved |
| Loop inductances | recomputed; unchanged (TIA_OUT, RF and TIA_SUM copper did not move) |

Grid uncertainty is 12.3 %. It is set by the SOURCE_BUF ground ratio in the new zoom window, 0.96.

All values in pF:

| Quantity | `reve` (stacked) | **`reve_r104`** (low / nom / high) |
|---|---|---|
| SOURCE_BUF node (+ selected RG) → GND | 8.66 / 9.82 / 13.23 | **7.86 / 9.04 / 13.11** |
| SOURCE_BUF ↔ DUT_HI | 2.03 / 2.42 / 2.99 | **0.107 / 0.155 / 0.229** |
| SRC_DRV → GND (driver side of R104) | — | **1.20 / 1.36 / 1.61** |
| SRC_DRV ↔ SOURCE_BUF / DUT_HI / HIGH_BUF | — | 0.005 / 0.015 / 0.005 (high) |
| SOURCE_BUF ↔ selected RF / TIA_OUT | 0.04 / 0.05 / 0.07 | 0.04 / 0.14 / 0.17 |
| SOURCE_BUF ↔ unselected RF nets | ≤ 0.016 | ≤ 0.11 |
| TIA_OUT node → GND | 8.17 / 10.07 / 14.62 | 8.06 / 10.01 / 14.72 |
| DUT_HI → GND | 6.28 / 7.40 / 10.23 | 6.87 / 8.17 / 11.22 |
| TIA_SUM → GND / ↔ TIA_OUT | 0.78 / 0.90 / 1.06; 0.12 / 0.21 / 0.32 | 0.77 / 0.90 / 1.07; 0.12 / 0.21 / 0.32 |

On the two SOURCE_BUF coupling rows:

- At x 185.5, SOURCE_BUF passes 0.66 mm from the In2 stub and via of RF100K at x 184.84, y 123.5–125.3. That coupling joins TIA_OUT on the 100 kΩ range and an unselected RF node on the others. It is still at most 0.17 pF, about 10× below the relay pole-to-pole estimate (Cpp 0.5 / 2 pF).
- SOURCE_BUF ↔ TIA_SUM stays ≤ 0.0001 pF.

Stability: `../stability-full-chain/README.md`, mode `reverelaycng100_r104`. The source driver recovers to **46.77°** at stress parasitics on the high board corner.

## Four-terminal BNC board (`reve_bnc`)

Board `cad/temper-lcr.kicad_pcb`, SHA-256 `80d44838c74637ec36cfbfc698f97a873b6be7c94604f3b49706651995aeddd5`. **The board was uncommitted when it was extracted.** `run_reve.sh reve_bnc` refuses any other file. Pass `BNC_COMMIT=<sha>` once it lands, and `BNC_SHA=` if the board changes.

**Layout.**

| Item | Detail |
|---|---|
| J3 HCUR | DUT_HI, at (108, 51) |
| J7 HPOT | at (130, 51) |
| J8 LPOT | at (152, 51) |
| J9 LCUR | DUT_LO, at (174, 51) |
| R105 | 1 k, DUT_HI–HPOT |
| R106 | 1 k, DUT_LO–LPOT |
| K4 reference relay | TQ2SA at (182, 70). Pin 8 = DUT_HI, pin 7 = REF_A |
| R107 | 1 k, REF_A–DUT_LO |
| Followers | HPOT drives U6.5 (HIGH follower +IN); LPOT drives U7.5 (LOW follower +IN) |

**Method changes from `reve_r104`.**

- **L-shaped domain.** The window `reve_bnc` (102.5–190.5 × 45.5–139.5) is solved as the union of 102.5–190.5 × 45.5–66.0 and 150.5–190.5 × 45.5–139.5 (`DOMAINS` in `fd3d.py`). Nodes outside the L are dropped, with zero flux. At 0.4 mm the L matches the full box (`reve_bnc_box`) to 0.04 % max relative difference.
- **Zoom windows.** New windows `bnc_band`, `bnc_corner` and `bnc_vert`, each solved from 0.14 to 0.05 mm. Factors applied per net:

  | Net | Window | Factor |
  |---|---|---|
  | HPOT | `bnc_band` | 1.169 |
  | DUT_HI | `bnc_band` | 1.024 |
  | LPOT | `bnc_vert` | 1.120 |
  | DUT_LO | `bnc_vert` | 0.925 |
  | REF_A | `bnc_corner` | 1.040 |
  | SOURCE_BUF | `reve_hiside_r104` | 1.171 |

  Pair factors are applied only where the zoom value is at least 0.01 pF: DUT_HI–HPOT 0.984, DUT_LO–LPOT 1.045, DUT_HI–DUT_LO 1.046.
- **Grid uncertainty is 11.8 %.** The DUT_LO `bnc_vert` series oscillates (0.50 / 0.35 / 0.48 / 0.43 / 0.47 pF), which widens U.
- **No two-dx whole-board check.** The whole board is solved at 0.2 mm on 7628 (4.6 M unknowns) and on 1080. The 0.4 mm run drops traces (SOURCE_BUF 2.7 pF against 7.2 pF), so it is used only to validate the L-domain. Convergence rests on the zooms.
- **BNC jacks are an ESTIMATE.** Each jack is 1.5 / 2.5 / 3.5 pF (`BNC_JACK_PF`), modelled as a 50 Ω line 15 / 22 / 30 mm long. There is no jack datasheet in `sources/`.
- **Kelvin extras.** Added analytically:
  - U6 pins 5–6: HPOT–HIGH_BUF and HPOT–GND.
  - U7 pins 5–6: LPOT–LOW_BUF and LPOT–GND.
  - R105, R106 and R107 bodies.
  - The J3 header posts are gone.
- **Relay body and internals are not modelled**, as on the earlier boards. K4 Coc (HCUR–REF_A) and Ccc are the harness estimates: Coc 0.3 / 2 pF and Ccc 1 / 5 pF per side (nominal / stress).
- **Inductance.** Unchanged: RF branch 64.93 / 64.41 / 92.44 nH; C104 branch 5.04 nH.

**Capacitances.** Values are low / nom / high in pF, worst over ranges, jack estimate included:

| Quantity | low / nom / high (pF) |
|---|---|
| DUT_HI (HCUR) → GND | **10.70 / 12.93 / 16.49** |
| DUT_LO (LCUR) → GND | **5.87 / 7.45 / 10.89** |
| HPOT → GND | **7.10 / 8.87 / 10.70** |
| LPOT → GND | **8.86 / 10.86 / 16.94** |
| REF_A → GND (board only) | 0.80 / 0.91 / 2.10 |
| HCUR ↔ LCUR | 0.014 / 0.017 / 0.020 |
| HPOT ↔ LPOT | 0.010 / 0.012 / 0.014 |
| HPOT ↔ HCUR | 0.18 / 0.24 / 0.33 |
| LPOT ↔ LCUR | 0.093 / 0.137 / 0.207 |
| HPOT ↔ LCUR | ≤ 0.002 |
| LPOT ↔ HCUR | ≤ 0.004 |
| SOURCE_BUF ↔ HCUR | 0.045 / 0.080 / 0.136 |
| SOURCE_BUF ↔ LCUR | 0.083 / 0.099 / 0.121 |
| SOURCE_BUF ↔ HPOT | ≈ 0 |
| SOURCE_BUF ↔ LPOT | 0.010 / 0.012 / 0.015 |
| SRC_DRV ↔ the four (sum) | 0.09 / 0.11 / 0.14 |
| TIA_SUM ↔ LCUR (incl. R94 body) | 0.030 / 0.062 / 0.115 |
| HCUR ↔ REF_A (board; K4 Coc separate) | 0.002–0.003 |
| REF_A ↔ LCUR (incl. R107 body) | 0.021 / 0.051 / 0.102 |
| HPOT ↔ HIGH_BUF | 0.07 / 0.10 / 0.15 |
| LPOT ↔ LOW_BUF | 0.06 / 0.09 / 0.14 |
| TIA_OUT ↔ any Kelvin net | ≤ 0.019 |
| SOURCE_BUF → GND | 8.27 / 9.38 / 13.72 |
| SRC_DRV → GND | 1.13 / 1.28 / 1.55 |
| TIA_OUT → GND | 7.97 / 10.21 / 14.70 |
| TIA_SUM → GND / ↔ TIA_OUT | 0.81 / 0.94 / 1.09; 0.13 / 0.23 / 0.35 |

The ground loads are larger than on `reve_r104`. DUT_HI was 8.17 pF nominal, and the long routes out to the jack row add to it, as does the jack. Every cross-coupling between the four terminals stays below 0.35 pF. The jack and cable ground loads are far larger than any of them.

**Outputs.**

- `geometry_reve_bnc.json`
- `inductance_reve_bnc.json`
- `fd_results/*_reve_bnc.json`
- `extracted_reve_bnc.json`
- `../stability-full-chain/reve_bnc_extracted.rs`

**Reproduce** with `sh run_reve.sh reve_bnc`. Add `STAB=1` to also run the `kelvincng100` loop matrix and `kelvin_summary.py`.

Stability: `../stability-full-chain/README.md`, mode `kelvincng100`.
