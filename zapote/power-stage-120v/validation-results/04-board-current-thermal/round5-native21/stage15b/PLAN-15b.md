# Native-21 stage 15b: FET-row copper for a 28 A tank ceiling

> **Planning only, model-based.** Nothing under the unit or the repo was changed.
> - **Basis:** stage-15 board `5b9dbd61…` (scratchpad `s15/section.kicad_pcb`), copper `native21s15-all-copper.json.gz`, B3 / A4 as committed in `round5-native21` (unit at `5191b3263`).
> - **Copies:** every script runs on copies in this folder (`model/` = the round-5 scripts and A4 outputs; `kicad/base/` = the routed board).
> - **Reproduce:** `sh run_all.sh`. Outputs go to `out/`, `runs/`, `png/`, `kicad/<candidate>/`.
> - **Gate (DECISIONS 13):** at c28 (29.4 A = 1.05 × 28 A), h 25, p 1.0, no new hot spot above the nominal board peak. The nominal peak is 133.3 °C; the 26 A sweep peak is 133.9 °C. Both are U26's pad cell.

## 0. Summary

| | Stage 15 as built | **Recommended: c2h** |
|---|---|---|
| Board peak, c28 h 25, committed thermal.py | **142.0 °C** at (76.5, 9.5) | **134.1 °C** at U26, the same part and cell as nominal (133.3) and 26 A (133.9) |
| FET-row max (x 0–80, y 0–12.5), committed model | 142.0 | **132.2** |
| FET-row max with stray heat moved onto copper (`thermal_snap.py`) | 136.6 | **132.9** |
| FET-row max, finer meshes p 0.5 / p 0.25 (snap) | 126.9 / 128.6 | 124.6 / 126.1 |
| Lanes (x 0–110, y 12.5–35), committed / snap | 132.3 / 123.6 | 132.3 / 123.9 |
| DRC errors / unconnected / parity | 0 / 0 / 0 | 0 / 0 / 0 |
| Parts moved; In1 / In2 changed; R5, C38 / C40 moved | — | **none** |

- **c2h is two outline edits:**
  - an SW_A F.Cu fill into the free corner between Q2.3 and BR1.1;
  - SW_A's B.Cu leg-A link raised 1 mm (y 12.5 → 13.5) over x 50.5–70, with SW_B's B.Cu lane bottom raised the same 1 mm (15.7 → 16.7).
- **Task 01 / F6 are not re-opened:** nothing changes on In1 or In2, no part moves, and the F6 tie via at (73.1, 15.2) and its stub are outside the edit.
- **One caveat:** the widened link is the HS-source → LS-drain conductor of the leg-A commutation loop on B.Cu. It widens on the side away from the pads, which can only lower its partial inductance. A task-01 confirmation is optional (§4).
- **The as-built 142.0 °C is mostly a meshing artefact.**
  - The peak cell is bare FR-4 on all four layers. It receives 0.021 W of A4 copper heat from the 0.5 mm of SW_A F.Cu that lies inside it.
  - With that heat moved onto the nearest copper cell, the real FET-row hot spot is **136.6 °C at Q3.2**: SW_A's low-side path, In1 pad ring cell at (50.5, 4.5).
  - On finer meshes the FET row is 126.9 (p 0.5) and 128.6 (p 0.25), which would pass even without a change.
  - c2h passes on every model and mesh tried.

## 1. Cause

### 1.1 Where the heat is (`diag_decompose.py` → `out/decompose_base.json`)

B3 is linear in its sources. The c28 field is exactly the sum of 15 single-source runs (14 A4 cases at their c28 scale, plus the A6 parts); the superposition error is 7e-8 K.

| Point (c28, p 1.0) | h 25 | h 10 | Top contributions at h 25 (K of rise) |
|---|---|---|---|
| (76.5, 9.5) F.Cu, the reported peak | 142.0 | 198.8 | sw_a_low 39.3, sw_a 26.5, bus_mixed_q2 6.1, sw_b_low 5.5 |
| Q3.2 (50.5, 4.5) In1, the h 10 peak | 135.4 | 202.7 | sw_a_low 44.0, leg_a_18p7 10.5, parts 6.8, sw_b_low 6.5 |
| Link neck over Q3.3 (55.5, 9.5) | 131.6 | 198.1 | sw_a_low 30.0, leg_a_18p7 19.7 |
| Link neck over Q2.2 (68.0, 9.5) | 124.7 | 185.1 | sw_a_low 28.8, bus_mixed_q2 14.9 |
| Q6.2 (sw_b) | 120.0 | 183.2 | sw_b_low 33.1 |

- **Heat in the strip** (x 0–80, y 0–12.5) totals 4.56 W at c28:
  - sw_a_low 1.47 W;
  - leg_a 0.75 W;
  - parts 0.50 W;
  - sw_b_high 0.38 W, bus_mixed_q2 0.38 W, sw_b_low 0.38 W;
  - sw_a (high side) 0.23 W.
- **`heatmap_cases.py`** (`png/heat_base.png`, `out/heat_bins_base.json`):
  - sw_a and sw_a_low put the **same 0.18 W into the F.Cu neck right of Q2.3** (x 72–76). Both states leave the board through Q2.3 → F.Cu → T1, so that 3.4 mm F.Cu neck (x 73.1–76.5, y 6.5–9.8) carries the full 29.4 A all the time.
  - sw_a_low adds 0.82 W in the B.Cu link: 0.21 W at x 48–52 (Q3.2's column), and 0.13–0.14 W in each of the Q3.3 and Q2.2 necks (2.83 mm).
- **Cause, by data:** SW_A's low-side state is the dominant driver. Its B.Cu link (2.83 mm over Q3.3 and Q2.2, 2.8 mm column at Q3.2) reaches the T1 pour only through Q2.3, so it adds to the F.Cu neck as well. The A4 `sw_a_low` case was new in stage 15. Its 6.69 mΩ (against 3.82 mΩ for the high side) is what tipped 26 → 28 A.

### 1.2 The 142.0 °C cell is a rasterisation artefact (`thermal_snap.py`, `snap_screen.py`, `mesh_study.py`)

- **What happens at that cell:**
  - At p 1.0 the thermal cell centred at (76.5, 9.5) is FR-4 on all four layers. The F.Cu pour edge is at x 76.5, so the cell centre is not inside copper.
  - thermal.py's `remap_a4` floors A4 heat into thermal cells, so this cell still receives 0.0209 W of F.Cu Joule heat.
  - That heat warms bare FR-4 (k 0.3) and produces the 142.0 °C peak. The next cell in, (75.5, 9.5) on copper, is 114.2 °C.
  - Round 5 fixed the same class of error for sub-cell SMD pads (thermal.py `add_part_heat`), but not for A4 heat.
- **The fix (`model/b3/thermal_snap.py`):** a copy of thermal.py whose only change moves A4 heat that lands in a non-copper cell to the nearest copper cell of the same layer. It conserves energy; the balance stays at 1e-8 W.
  - At p 1.0 it moves 0.75 W from about 4,400 cells: F.Cu 0.15 W, In1 0.09 W, In2 0.16 W, B.Cu 0.36 W.
  - **Result:** the c28 board peak becomes **136.6 °C at Q3.2 In1 (50.5, 4.5)**. The lane cell at (44.5, 20.5), 132.3 °C in the committed model and the "C56 neck" hot spot, drops to 123.6 °C. It was the same artefact.

**Mesh study** (snap model; `out/mesh_study.json`). FET-row max is over x 0–80, y 0–12.5.

| Operating point | p 1.0, h 25 | p 0.5, h 25 | p 0.25, h 25 | p 1.0, h 10 | p 0.5, h 10 |
|---|---|---|---|---|---|
| nominal (21.47 A), stage 15 | 97.3 | 92.3 | 93.1 | 135.8 | 129.2 |
| 26 A ceiling (27.3 A), stage 15 | 125.6 | 117.3 | 118.8 | 185.3 | 174.0 |
| **c28, stage 15** | **136.6** | 126.9 | 128.6 | 204.0 | 190.9 |
| **c28, c2h** | **132.9** | 124.6 | 126.1 | 198.9 | 187.6 |
| board peak, nominal (U26 / U41 / U42) | 133.3 | 180.8 | 139.8 | 163.1 | 214.8 |

- **What the mesh study shows:**
  - The FET-row result is mesh-sensitive: 1.0 mm cells cannot resolve the 2.8 mm necks.
  - p 1.0 is the conservative end (finer meshes are 8–10 K cooler), and it is the mesh the DECISIONS-13 gate uses.
  - c2h lowers the FET row by 2.3–3.7 K at every mesh.
- **A finer-mesh flag outside the FET row:** at p 0.25, c28, R5's pad cell (39.9, 16.4) is the board peak at 149.2 °C, above that mesh's nominal peak of 139.8 °C (U42). At p 0.5 it is 144.6 °C, against 180.8.
  - R5 is a part (0.86 W at 29.4 A), not tank copper, and c2h does not change it (149.1).
  - It depends on R5's own rating: its terminal-temperature derating against 0.86 W (`thermal_scale.py`).
  - The same holds at the **26 A ceiling already accepted:** R5 is 143.2 °C at p 0.25, also above 139.8. So this is a pre-existing mesh-dependent finding, not a 28 A regression.
  - This is recorded as open item O2. It is not part of the FET-row fix.

### 1.3 Model treatment of the FET leads and the sink (`lead_bias.py`, `lead_core.py`)

- **How thermal.py treats them:**
  - It gives Q2/Q3/Q5/Q6 `board_fraction` 0 ("modeled as heatsink power; lead heat unknown") and **no conductance from the pads to the package**.
  - The outline is insulated (`dirichlet_x_ends` False), so the model has no sink edge at all.
  - Board copper can neither receive die heat through the leads nor shed heat into the heatsinked package.
- **Bound used for the lead path:** G ≤ k·A/L = 390 × 1.125 mm² / 3.85 mm = **0.114 W/K per lead**.
  - A is the largest rectangle through the 1.5 mm drill.
  - L is the body-bottom height L1 min (m11 RECOMMENDATION §1, Infineon PG-TO247-3 p.12).
  - Solder joints and the in-body path only lower it.
- **Case temperature at 28 A** (round 6 `board-side-fets.csv`, 45 kHz; R_thJC 0.28 °C/W):
  - basis B (ZVS): T_c = 81.6 − 11.86 × 0.28 = 78.3 °C;
  - basis A: T_c ≤ 134.5 − 14.47 × 0.28 = 130.4 °C.

| c28, p 1.0, committed copper | FET-row max h 25 | h 10 | Lead heat to the package (h 25) |
|---|---|---|---|
| No lead path (as committed) | 142.0 | 202.7 | — |
| Basis B, drain lead only | 136.4 (−5.6) | 176.9 | +1.38 W |
| Basis B, all three leads | 124.0 | 145.3 | +2.71 W |
| Basis A, drain only | 142.5 (+0.5) | 187.2 | −0.28 W |
| Basis A, all leads (over-states: pins 1 and 3 go through bond wires) | 144.9 (+2.9) | 172.0 | −1.17 W |

- **Bias:** the missing lead path biases the FET row by **−5.6 to +0.5 K at h 25** for the realistic drain-lead case, with the sign set by the unmeasured switching loss.
  - It is not the cause of the 28 A result.
  - Bench switching loss decides the sign. With ZVS (basis B) the board is cooler than B3 says; with basis A it is up to 0.5 K warmer (2.9 K if all three leads are counted).
- **On c2h:**
  - basis A, drain lead: FET row 131.0 °C;
  - basis A, all leads: 133.6 °C. Lead heat then raises the lane cell at (44.5, 20.5) to 136.0 °C: the over-stated corner.
- **Barrel conduction:** adding the lead's copper core to the FET barrels' thermal links (`lead_core.py`) moves the FET row by only −0.4 K (136.2 / 132.4 °C). The Q3.2 hot spot is the whole column, not an isolated ring.

## 2. Candidates (least intrusive first)

All candidates are outline edits applied to a copy of the routed board with pcbnew (`kedit.py`). KiCad's own refill and DRC under `section.kicad_dru` (8.0 / 5.0 / 3.2 / 1.8-escape rules) are the clearance authority, which is stronger than the shapely check in proposals.py.

Each candidate then goes through `tools/export_power_copper.py` + `extract_geometry.py`, all 14 A4 cases, and B3 c28 (`run_candidate.sh`).

- **Control `c0_refill`** (refill only) reproduces 142.0 / 202.7 °C and every A4 resistance exactly.

| ID | Edit (board mm; add = union into the net's pour, trim = difference) | Re-opens task 01 / F6? | sw_a / sw_a_low / sw_b_high (mΩ) | FET row h 25, committed / snap | Lanes h 25, committed / snap | Board peak h 25, committed | Verdict |
|---|---|---|---|---|---|---|---|
| c0 | none | — | 3.819 / 6.686 / 6.556 | 142.0 / 136.6 | 132.3 / 123.6 | 142.0 | fails |
| **c1** | sw_a F.Cu add (76.5, 0.6, 81.7, 9.8): BR1.1 corner (+2.6 mm²) | no | 3.751 / 6.618 / 6.556 | 135.1 / 136.3 | 132.0 / 123.5 | 135.1 | fails; removes the artefact only (−0.3 K physical) |
| c1b | c1 + sw_a B.Cu add (76.5, 0.6, 81.7, 12.5) | no | 3.751 / 6.616 / — | 135.0 / — | 132.0 / — | 135.0 | no gain over c1 |
| c2a | c1 + link add (50.5, 12.4, 60.5, 14.5); sw_b trim (50.5, 12.5, 60.5, 17.7) | no | 3.751 / 6.490 / — | 132.7 / 133.3 | 133.4 / 125.6 | 134.1 (U26) | marginal (snap = 133.33) |
| c2b | c1 + link add (46.5, 12.4, 76.5, 14.5); sw_b trim (46.5, 12.5, 79.7, 17.7) | no | 3.751 / 6.129 / — | 129.9 / — | **136.5** | 136.5 | **fails**: new lane hot spot at (44.5, 20.5), the C56 neck |
| c2c | c1 + link add (46.5, 12.4, 76.5, 13.5); sw_b trim (46.5, 12.5, 79.7, 16.7) | no | 3.751 / 6.313 / — | 131.2 / 131.8 | 133.3 / 125.4 | 134.1 | passes; trims the C56 neck |
| c2f | c1 + link add (50.5, 12.4, 76.5, 13.5); sw_b trim (50.5, 12.5, 79.7, 16.7) | no; touches the tie-via stub area | 3.751 / 6.329 / 6.644 | 132.1 / 132.7 | 132.2 / 123.8 | 134.1 | passes |
| c2g | c1 + link add (50.5, 12.4, 60.5, 14.0); sw_b trim (50.5, 12.5, 60.5, 17.2) | no | 3.751 / 6.500 / 6.654 | 132.6 / 133.2 | 132.8 / 124.5 | 134.1 | passes; 0.1 K snap margin |
| **c2h** | c1 + link add (50.5, 12.4, 70.0, 13.5); sw_b trim (50.5, 12.5, 70.0, 16.7) | **no** | 3.751 / **6.374** / 6.635 | **132.2 / 132.9** | **132.3 / 123.9** | **134.1 (U26)** | **passes on both models, all meshes** |

Widths for c2h (`cut_widths.py`, vertical cuts):
- **SW_A link:** 2.83 → **3.83 mm** at x 55.5 and x 68.05.
- **SW_B lane:**
  - 11.3 → 10.3 mm at x 52–55.5;
  - 8.1 → 7.1 mm at x 61 and x 68.05 (the C38.1 / C39.2 antipad necks);
  - 7.17 mm unchanged at x 70.
  - SW_B's resistance rises 6.556 → 6.635 mΩ (sw_b_high), +1.2 %.
- **SW_A F.Cu right of Q2.3** (pad edge to pour edge): 1.75 → 3.59 mm at y 9.5.

Copper area change in x 0–110, y 0–35 (`area_delta.py`): sw_a B.Cu +18.0 mm², sw_a F.Cu +2.6 mm², sw_b B.Cu −19.1 mm². No other net changes.

Plot: `png/fetrow_c2h.png` (against `png/fetrow_base.png`).

**Considered and not taken:**

| Option | Why not | Re-opens |
|---|---|---|
| sw_a F↔B stitching vias at x 72.5–76.5, y 9.6–12.5 (parallel the Q2.3 neck) | Every spot is inside In1 hv_ret / In2 bus_p plane copper. A 3.2 mm antipad per via severs the plane sliver at x 72–76.5. Not needed once c2h passes. | task 01 (planes) |
| C56 gate-return via out of the SW_B lane (PLAN §5 fallback 1) | Its "hot spot" at (44.5, 20.5) is the stray-heat artefact: 123.6 °C with snap. c2h leaves it at baseline. | F6 (leg-A LS gate loop) |
| Pad / thermal-relief changes on the FET THT pads | sw_a / sw_b / leg_ret / bus_p pours already connect FULL (zone pad_connection 2; FET power pins inherit). Nothing is left to gain. The pads' own copper is fixed by the 1.5 mm drill and the 1.965 mm edge distance (M11). | — |
| SW_A F.Cu widening left of Q2.3 | Bounded by Q2.2 bus_p and C12.1 at 3.2 mm. | — |
| BR1 +x move (frees x 76.5–79.7 on F.Cu and B.Cu) | Not needed. It is a part move on AlN tile B, the enclosure fit and the BR1 gap pad. | enclosure / M11 |
| R5 north, C38/C40 south | Not needed. | task 01, F6, Kelvin chain |

## 3. Thermal result at 28 A (c2h)

`out/b3_c2h_link_e1_notie.json`, `out/region_check.json`, `out/snap_screen.json`, `out/mesh_study.json`.

- **Gate, h 25, p 1.0, committed thermal.py:**
  - Board peak 134.14 °C at (109.5, 77.5) F.Cu. That is U26's pad cell, the nominal peak part: 133.3 nominal, 133.9 at 26 A, 134.2 at c28 on the unchanged board. It rises with total board heat and is not a new hot spot.
  - FET row 132.2 °C, lanes 132.3 °C.
  - `region_check.py` finds **0 cells** above 133.9 °C that got hotter than the stage-15 baseline.
  - **PASS.**
- **With the stray-heat fix (snap), p 1.0:** FET row 132.9 °C, below 133.3 °C. **PASS.**
- **p 0.5 / p 0.25 (snap):** FET row 124.6 / 126.1 °C. The board peaks are parts: U41 182.2 / R5 149.1, the same as stage 15 without c2h (R5: open item O2).
- **h 10** (still air, report only; DECISIONS 13 gates at h 25):
  - FET row c28: 198.2 °C committed, 198.9 snap. The stage-15 board is 202.7 / 204.0.
  - At 26 A the stage-15 FET row at h 10 is already 184.1 °C (committed; `region_check.py` 26 A reference), and the nominal-point board peak at h 10 is 163.0 °C (U42).
  - No copper edit in the FET row brings h 10 near the nominal peak. Fan loss is a derating case at any ceiling above 22 A, which the coil-NTC derating loop and the bench gates must own (DECISIONS 10 / R32 item 8).
- **Attribution after c2h** (`out/decompose_c2h.json`, h 25):
  - Q3.2: 132.2 °C, of which sw_a_low 40.6 K and leg_a 10.3 K.
  - (76.5, 9.5): 108.4 °C, from 142.0.
  - Link neck over Q3.3: 125.3 °C, from 131.6.
  - Link neck over Q2.2: 120.1 °C, from 124.7.

## 4. Recommendation and the writer's ordered steps

**Call: take c2h.** It is the least change that passes at 28 A on the committed model with margin (FET row 132.2 °C, 1.1 K under nominal 133.3) and on the corrected model (132.9 °C). It moves no part, touches no inner layer, and keeps clear of the F6 tie via.

c2g (a 1.5 mm raise over x 50.5–60.5 only) also passes, but with only 0.1 K of margin on the snap model, so it is not taken.

1. **`native-21/layout/patches21.py`:** append to the stage-15 lists. edit_zones' S15 block already handles both nets: trims first, keep the largest piece, then union.
   ```python
   # Stage 15b (28 A FET row, scratchpad stage15b/PLAN-15b.md): SW_A's low-side path was the B3 28 A hot spot.
   S15_ADD += [(("sw_a", "F.Cu"), (76.5, 0.6, 81.7, 9.8)),     # Q2.3-BR1.1 corner; refill clips 3.2 mm round BR1.1
               (("sw_a", "B.Cu"), (50.5, 12.4, 70.0, 13.5))]   # leg-A link top 12.5 -> 13.5 (2.83 -> 3.83 mm over Q3.3 / Q2.2)
   S15_TRIM += [(("sw_b", "B.Cu"), (50.5, 12.5, 70.0, 16.7))]  # SW_B lane bottom 15.7 -> 16.7 over the same span (3.2 mm HOT gap kept)
   ```
   - The B.Cu add starts at y 12.4 so that it intersects the trimmed link (SWA_TRIM leaves the top at 12.5).
   - It stops at x 70.0, short of the C55 tie via (73.1, 15.2) and its B.Cu stub. SWA_TRIM, SWB_RAISE and TIE_KEEPOUT are untouched.
   - No vias, no tracks, no place.py change.
2. **`incr21.py`** on the stage-15 board, then the gates: DRC 0 / 0 / parity 0 (this folder's KiCad refill of the same edit is 0 / 0 / 0); barrier21 + the Rust barrier gate; D5 audit (`d5-audit.json`, expect 8.047 / 8.507 unchanged); JLC DFM; Gerber review; enclosure fit (no part moves).
   - **M11 / sink paths:** the new F.Cu copper reaches the y 0.6 edge rule between Q2 and BR1, the same edge distance as the existing pours. Rerun `owner-items/m11/sink_paths.py` for the record.
3. **Exports:** a new `native21s15b-all-copper.json.gz` (extract_geometry.py) and the round-5 `inputs/power_copper.json.gz` (export_power_copper.py).
4. **Task 04:**
   - rerun `run_cases.py`. Expected R (this folder): sw_a 3.751, sw_a_low 6.374, sw_b_high 6.635, sw_b_low 6.563 mΩ; leg_ret / hv_ret / bus_p cases unchanged;
   - then `b3/run_study.py` and `b3/ceiling_sweep.py` with GEOM → the s15b export.
   - **Expect:** the 28 A point at 134.1 °C on U26 (FET row 132.2 °C), and the 22–26 A points unchanged on U26.
   - **Also commit the stray-heat fix** (`thermal_snap.py`'s A4 snap, about 15 lines in `run()`) as a model correction. Report both and gate on the committed form until DECISIONS adopts the fix. Rerun `sw_widths.py` / `neck_fin.py` from stage15-28A for the record.
5. **Task 01 / F6:**
   - **No re-open:** In1 / In2, R5, C38 / C40 and every gate-loop part and via are unchanged.
   - **Record in DECISIONS:** the SW_A B.Cu link (Q2 source → Q3 drain) is a commutation-loop conductor and gains 1 mm of width on its far edge.
   - **Optional confirmation:** task 01's partial-inductance extraction on the s15b copper. Expect equal or lower loop L. Not a release gate.
   - **Task 07:** the sw_a switch-node copper grows by 20.6 mm² (+2.6 F.Cu at the board edge, +18.0 B.Cu); the sw_b node shrinks by 19.1 mm². Note it in the CM budget record. No new copper approaches PE beyond the existing y 0.6 edge rule.
6. **DECISIONS 13 follow-up:** "28 A thermally supported at h 25 (B3 c28 134.1 °C on U26, FET row 132.2 °C); the stage-15 142.0 °C was a stray-heat cell at (76.5, 9.5)". The commissioned ceiling still rises only after the bench items in DECISIONS 10 / 13. Add FET-row IR at 28 A (Q3.2 drain lead, the leg-A link) to the bench list, because the model's lead path is unbounded in sign until switching loss is measured.

## Open items

- **O1: h 10.** FET row 198 °C at c28 and 184 °C at 26 A. This is a fan-failure case and needs the derating loop; copper cannot close it.
- **O2: R5 at fine mesh.** Its pad cell is 149.2 °C at c28, p 0.25 (144.6 at p 0.5), and is the p 0.25 board peak. It is 143.2 °C at 26 A, so the finding pre-dates stage 15b. Check R5's terminal-temperature derating at 0.86 W. This is independent of c2h.
- **O3: lead-path sign.** −5.6 K (ZVS) to +0.5 K (basis A, drain lead) at the FET row. It closes with the bench switching-loss measurement.

## Files

| Script | Purpose → output |
|---|---|
| `model/` | Copies: round-5 `b3/thermal.py` (paths only), `run_study.py`, `ceiling_sweep.py`, `make_heat_sources.py`, inputs; `run_board.py` (paths only), `run_cases.py`, the 14 A4 cases. Also `b3/thermal_lead.py` (+LEAD_SINK) and `b3/thermal_snap.py` (+A4 snap, +LEAD_CORE). |
| `diag_decompose.py [geom A4 tag]` | per-source superposition, FET-row profile, points → `out/decompose_<tag>.json` |
| `heatmap_cases.py` | per-case A4 heat maps and bins → `png/heat_base.png`, `out/heat_bins_base.json` |
| `lead_bias.py [tag geom A4 copper]` | lead-to-package bias → `out/lead_bias*.json` |
| `lead_core.py` | barrel lead-core sensitivity → `out/lead_core.json` |
| `kedit.py` (KiCad Python), `run_candidate.sh`, `candidates/*.json` | edit + refill + DRC + export + A4 + B3 → `kicad/<c>/`, `a4/<c>/`, `out/b3_<c>.json` |
| `extract_geometry.py` | round-4 extractor copy (unit's exporter path) |
| `a4_cases.py`, `b3_eval.py` | the 14 A4 cases; B3 c28 h 25 / h 10 |
| `region_check.py` | gate check by region and new-hot-spot cells; 26 A reference → `out/region_check.json` |
| `snap_screen.py`, `mesh_study.py` | stray-heat-fixed screen; p 1.0 / 0.5 / 0.25 study → `out/snap_screen.json`, `out/mesh_study.json` |
| `cut_widths.py`, `area_delta.py`, `plot_fetrow.py` | widths, copper area deltas, layer plots |
| `run_all.sh` | everything above, in order |
