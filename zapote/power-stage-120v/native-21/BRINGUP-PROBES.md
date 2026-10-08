# Native-21 bring-up probe map

Board-only test pads (TestPoint_Pad_D1.0mm: bare 1 mm copper, no part, not in BOM/CPL), each
paired with a ground-reference pad on its own domain for a short probe ground (D-8: ≤ 10 mm loop).
Chosen by `layout/plan_board_only21.py` from the routed copper; added on every build by
`layout/board_only21.py`. Pads sit on an existing via or track of their net (no routing change).
Bottom-side pads are probed with the board on standoffs; their designators are on F.Fab.

**Safety:** HOT domains float at bus / switch-node potential. Probe them only with rated
differential or isolated probes (D-8 equipment table), never a grounded scope ground.

| Signal pad | Net | Side | At (mm) | Ground pad | Ground net | Purpose |
| --- | --- | --- | --- | --- | --- | --- |
| TP1 | leg_a-out_l | B | 82.0, 37.0 | TP23 | n_ls | leg A low-side driver output vs VSSB |
| TP2 | leg_b-out_l | F | 36.0, 42.5 | TP24 | n_ls | leg B low-side driver output vs VSSB |
| TP3 | n_ls | B | 113.5, 82.6 | TP25 | leg_ret | LS -2 V rail vs low-side sources (F6 rail at the edge) |
| TP4 | v15_ls | B | 116.3, 62.4 | TP26 | leg_ret | LS +15 V rail |
| TP5 | v24_raw | F | 54.6, 48.0 | TP27 | n_ls | 24 V HOT supply |
| TP6 | ocp_node | B | 116.8, 71.0 | TP28 | ocp_kelvin_p | OCP comparator input (D4 condition 2) |
| TP7 | hot5 | B | 114.9, 116.1 | TP29 | ocp_kelvin_p | HOT5 protection rail |
| TP8 | bus_fault_hot | F | 122.8, 60.3 | TP30 | ocp_kelvin_p | OCP fault, HOT side |
| TP9 | n_ha | B | 58.7, 74.0 | TP31 | sw_a | HS-A -2 V rail vs switch node (F6 rail at the edge) |
| TP10 | p_ha | F | 67.1, 51.7 | TP32 | sw_a | HS-A +15 V rail |
| TP11 | leg_b-out_h | F | 29.8, 41.9 | TP33 | n_hb | leg B high-side driver output vs VSSA |
| TP12 | n_hb | F | 18.6, 52.0 | TP34 | sw_b | HS-B -2 V rail vs switch node |
| TP13 | p_hb | F | 24.7, 47.0 | TP34 | sw_b | HS-B +15 V rail |
| TP14 | v15_selv | B | 134.0, 131.7 | TP35 | selv_gnd | SELV 15 V |
| TP15 | v3v3 | B | 77.2, 107.4 | TP36 | selv_gnd | SELV 3.3 V |
| TP16 | pwm_ha | B | 78.3, 102.4 | TP36 | selv_gnd | PWM A high |
| TP17 | pwm_la | B | 79.8, 60.8 | TP37 | selv_gnd | PWM A low |
| TP18 | pwm_hb | B | 56.2, 131.2 | TP38 | selv_gnd | PWM B high |
| TP19 | permit | B | 44.3, 132.9 | TP39 | selv_gnd | PERMIT |
| TP20 | bias_bad | B | 33.2, 72.0 | TP40 | selv_gnd | BIAS_BAD (rail monitors) |
| TP21 | bus_fault | B | 35.2, 133.6 | TP39 | selv_gnd | OCP fault, SELV side |
| TP22 | ct_mon | B | 23.8, 134.6 | TP41 | selv_gnd | tank CT monitor |

## Probed elsewhere (no legal test-pad spot)

| Net | Probe at |
| --- | --- |
| leg_a-out_h | component pad R53.2 / U1.15 / R10.1 (no legal test-pad spot) |
| pwm_lb | J4.8 (bottom), ground J4.2 / J4.4 / J4.15 |
| leg_a-dis | component pad R8.1 / U22.1 / Q1.3 (no legal test-pad spot) |
| leg_b-dis | component pad U23.1 / Q4.3 / R16.1 (no legal test-pad spot) |
| line_zc | J4.16 (bottom), ground J4.2 / J4.4 / J4.15 |
| ct_zc | J4.13 (bottom), ground J4.2 / J4.4 / J4.15 |

FET gate/drain/source (VGS, VDS): at the TO-247 package leads with rigid insulated adapters, per
D-8 (`validation-results/01-switching-parasitics/round17/delegation/out-D8/README.md`).

## Fiducials and fixings

Fiducials: FID1 (4, 36), FID2 (280, 130), FID3 (4, 184) (1 mm copper, 3 mm mask opening, F side).

| Hole | At (mm) | Hardware |
| --- | --- | --- |
| H1 | 285.0, 135.0 | M3 metal allowed: chassis/PE, ≥ 8 mm from HOT (D5) |
| H2 | 42, 62 | **M3 nylon only** (UL94 V-0); within 8 mm of HOT or on SELV copper |
| H3 | 20, 122 | **M3 nylon only** (UL94 V-0); within 8 mm of HOT or on SELV copper |
| H4 | 84, 120 | **M3 nylon only** (UL94 V-0); within 8 mm of HOT or on SELV copper |
| H5 | 134, 54 | **M3 nylon only** (UL94 V-0); within 8 mm of HOT or on SELV copper |
| H6 | 218, 18 | **M3 nylon only** (UL94 V-0); within 8 mm of HOT or on SELV copper |
| H7 | 200, 128 | **M3 nylon only** (UL94 V-0); within 8 mm of HOT or on SELV copper |
| H8 | 164, 126 | **M3 nylon only** (UL94 V-0); within 8 mm of HOT or on SELV copper |

Positions must match the enclosure's bosses before release (D5-AUDIT.md). The enclosure
design adopts them, or the holes move with it.
