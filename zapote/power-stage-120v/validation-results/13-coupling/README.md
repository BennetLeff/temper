# 13 Coupling audit: how far can native-21 work be parallelised?

Board: native-21 stage 43, the board of record (commit `719084486`, board `61447816…`, 351 parts). The audit was first
run on stage 32 (`2fb346dc…`, 349 parts, commit `f7e98c0ec`). This refresh re-runs every layer on s43 and re-tests the
model on the six stages adopted since. Changes since the s32 run are marked **(s32: …)** or "Changed since s32".

Question: which of the ten functional groups (`../11-candidates/GROUPS.md`) can be changed at the same time by
separate agents or stages? Which changes spill into other groups, and what interface contracts would let them run
apart?

## Running it

The scripts now take the stage as input (`scripts/stages.py` is the registry; the options are in `scripts/common.py`):

    sh validation-results/13-coupling/scripts/run_all.sh                         # s43, the board of record -> results/
    sh validation-results/13-coupling/scripts/export_stage.sh f7e98c0ec /tmp/s32 "" \
         .../runs-native21/s32/b2/section.kicad_pcb                               # stage-32 inputs as committed
    sh validation-results/13-coupling/scripts/run_all.sh --stage native21s32 \
         --root /tmp/s32/zapote/power-stage-120v                                  # -> results-s32/

Options: `--stage TAG --root DIR --out DIR --repo DIR --build DIR --b3-dir DIR`, plus `--b3-primary RUN` for the heat
sensitivity. Every script is `python3 -I` with numpy, scipy, shapely and networkx, and reads its inputs without
changing them. Each writes JSON into the results directory and exits 1 if a control fails. `run_all.sh` runs the whole
audit twice and checks that every JSON is byte-identical.

| Run | Controls passed | Result files identical over two runs | Notes |
|---|---|---|---|
| s43, `results/` | 164 | 17 | about 3 min; adds `spine.json` and `oos.json` |
| s32, `results-s32/` | 131 (the original 126, plus 5 input checks) | 15 | all 15 files byte-identical to the stage-32 audit's committed `SHA256SUMS` |

Inputs outside git:

- **The chain BUILDDIR** (`runs-native21/sNN/…`): return-path, creepage, bypass, PI and pads files.
- **s43's legacy B3 heat maps.** `b3_maps.py` re-solves them into `cache/` (gitignored) from the root's committed
  `b3/thermal.py`, the stage's copper dump and the task-04 A4 fields, which are also gitignored. The c28 map
  reproduces the stage's committed B3 output (peak 147.18 °C, 25.044 W), and its npz is byte-identical to the s43
  chain's.
- **s32's heat map.** It cannot be re-solved, because its A4 fields are gone. `inputs/native21s32/c28_h25_p1p0.npz` is
  a copy of the stage-32 chain's file, checked by sha256 (`e5222d6c…`). It is gitignored (no `.npz` in git); the durable
  copy is `runs-native21/s32/coupling-inputs/c28_h25_p1p0.npz`. Copy it into `inputs/native21s32/` before the s32 rerun.

## Headline

- **Parts-only changes are still independent.** No stage since s32 was parts-only, so the evidence is still the four
  parts-only stages (20, 26, 29, 31). Two later part swaps rode with copper stages:
  - s42: R10 / R12 / R18 / R20 and C55 / C56 / C62 / C63;
  - s43: the snubber MPN on C12 / C13 / C19 / C20.
- **Layout changes are still not independent.** Of the 5 targeted copper stages after s32, 3 put copper into groups
  they did not target: s38, s40 and s42. s35 and s41 did not. Over the whole history, 9 of 12 targeted copper stages
  rippled, 23 cases in all **(s32: 6 of 7, 17 cases)**. s43, the cleanup pass, is global by design and has no outside
  group.
- **Out of sample, the stage-32 model kept part of its predictive power.** It was frozen before stages 35-43 existed.
  - On their 81 cases (16 rippled) its combined ROC AUC is **0.70** (bootstrap 95 % 0.54-0.84). In sample it was 0.81.
  - The physical layer held best: 0.85 → 0.78.
  - The physics layer fell to near chance: 0.70 → 0.55.
  - The miss is concentrated in one stage. s38 re-laid the mains pair L_FILT / N_FILT, which left 2 items in each of
    three other groups' territories, and the model scored those pairs low. Without s38 the AUC is 0.86.
  - The 8 moved metrics that the s32 card carried were all in the intended groups' s32 read lists.
- **The SELV-spine lock worked, like the OCP lock.**
  - Before it, 4 of 7 copper stages changed spine copper, 484 locked items in all.
  - After it, none of the 5 lanes that did not own the spine changed a single locked item: s35, s40, s41, s42, and
    s43's board-wide cleanup.
  - The one change came from s38, the SELV lane that owns the spine. It came from deleting PS1 / V15_SELV, and the lane
    re-issued the lock.
  - The contract values held: D5 8.047 / 8.507 mm, worst asserted return path 2.72 mm, and return-path open changes
    improved 18 → 15.
- **Workstreams: five, with the spine lock; four without it** (as at s32).
  - A fifth contract is now needed, WS1 ↔ WS4 (G01-G06, 0.212). It is a shared re-check: the leakage budget (PS2 and
    the Y caps) and the release-case heat. It is not shared layout.
  - The model's own count at the history-calibrated threshold (τ 0.263) is 3 connected workstreams, with 5 groups
    concurrent.
- **The ten groups still do not match the board's natural clusters.** These are the same seven isolation-island
  communities as at s32, with PS1 gone from the SELV one. ARI 0.198 **(s32: 0.19)**.
  - Re-cutting by island, with the SELV side merged, halves the inter-group cut (0.381 → 0.194).
  - It cuts contested corridor tile-pairs 133 → 30 **(s32: 133 → 60)**.

## 1. Stage-43 group assignment (`scripts/assign.py`, `results/assignment.json`)

Changed since s32: `assign32.py` is now `assign.py`, and the rules carry the stage that introduced them. A stage run
applies only the rules up to its own stage, so the s32 run is unchanged. The stage-19c rule (R0) still reproduces 19c
for every surviving part.

| Rule | Introduced | Parts | Group | Why |
|---|---|---|---|---|
| R1 | s32 | `hb.*` (now also D20, R135, added at s40) | G07 | stage-30 heartbeat |
| R2 | s32 | U43 and its caps (`bias_ha.link`) | G07 | rail-verdict isolator: monitoring |
| R3 | s32 | R130 | G10 | F2 limiter |
| R4 | s32 | R134 / C167 | G09 | BUS_FAULT RC (an electrical 1:1 tie) |
| **R5** | **s40** | **U44, C159, C160 (`bias_hb.link` / `clink1` / `clink2`)** | **G07** | U44 became the ISO6721FB HS-B → LS verdict link, like U43 (DECISIONS 52). Its path was renamed from `bias_hb.verdict` / `cver*`, so without R5 the 19c rule would put it in G06 |

The full parts diff from s32 to s43 (`history.py` checks each row against its DECISIONS item):

| Stage | Change | Group |
|---|---|---|
| s35 | J2 / J5 MPN → 7466004R | G04 |
| s38 | PS1 deleted | was G10 |
| s38 | PS2 → MPM-20-24 | G06 |
| s40 | C168 added (`c_ref_xfer_5`, transfer cap) | G10 by R0, like C153-C156 |
| s40 | D20, R135 added | G07 by R1 |
| s40 | U44 → ISO6721FBDR, with the path rename | G07 by R5 |
| s41 | no part change; the netlist is identical | — |
| s42 | R10 / R12 / R18 / R20 → 25121WF680JT4E; C55 / C56 / C62 / C63 → GRM1885C1H472JA01D | G05 |
| s43 | C12 / C13 / C19 / C20 → CC1206JKNPOCBN102; the nets are identical | G03 |

Since 19c, 25 parts are new and 31 have been removed. Part counts per group: G01 12, G02 6, G03 12, G04 11, G05 92,
G06 42, G07 92, G08 42, G09 32, G10 10 **(s32: G07 90; G10 10, with PS1 out and C168 in)**.

15 parts sit electrically closer to another group than their own **(s32: 16; PS1 is gone)**. They are the same
interface parts as at s32:

- BR1, C5 / C6 vote G03;
- Q2 / Q3 / Q5 / Q6, C13 / C20 vote G05;
- J2 votes G09;
- J4 votes G05;
- U4 votes G10;
- U9 is a G08 / G09 tie;
- R47 and U24 are G09 / G10 ties.

None of the new parts votes elsewhere.

## 2. Electrical layer (`scripts/electrical.py`, `results/electrical.json`)

The method is unchanged.

| | All nets | Without rails |
|---|---|---|
| Q of the ten groups | 0.441 (s32 0.440) | 0.600 (0.597) |
| Q of the Louvain communities | 0.691, 7 communities (0.682) | 0.778, 14 communities (0.775) |
| ARI against the ten groups | 0.198 (0.19) | 0.337 (0.34) |

With rails, the seven communities are still the isolation islands. 183 of 351 parts sit in a community whose majority
is another group.

| Community | Parts | What it is |
|---|---|---|
| Low side | 93 | both legs' low sides, bias_ls, the heartbeat |
| SELV interface | 65 | J4, CT detect, driver inputs. **PS1 is gone** |
| HS-B | 60 | its bias and monitor, and the tank |
| HS-A | 53 | |
| G08 | 35 | HOT5 / Kelvin / OCP |
| Power path | 23 | |
| Mains | 22 | G01, PS2, line ZC, the blower tap |

**Conductance without rails** (lower means more self-contained): G07 0.061, G08 0.133, G09 0.176, G06 0.222,
G05 0.249, G01 0.250, G04 0.290, G02 0.479, G03 0.747, G10 0.765. The order is as at s32. G03 and G10 are still
interfaces by nature.

**Split points inside groups** are as at s32:

- G06 falls into 7 pieces.
- G07 has a Fiedler value of 0.013: three monitors plus the heartbeat.
- G05 has a Fiedler value of 0.020: leg A and leg B.
- G08 splits into 4 blocks.
- G09 is two components, CT and line ZC.

**Strongest electrical links:**

| Pair | Score | Shared nets |
|---|---|---|
| G03-G05 | 1.00 | gate nets, sw_a, sw_b, leg_ret |
| G02-G03 | 0.87 | bus_p, hv_ret |
| G05-G10 | 0.69 (s32 0.61) | permit, pwm_ha, pwm_la, pwm_hb, pwm_lb |
| G09-G10 | 0.67 (s32 0.61) | bus_fault, ct_mon, ct_zc, line_zc, l_filt, n_filt |

G10 is smaller in volume without PS1, so its normalised links rose.

Changed since s32, the "random relabelling modularity ~ 0" control: one seeded draw on the no_rails_no_planes variant
read 0.0517, just past the old fixed 0.05. That draw is now judged against the null of 200 seeded relabellings: mean
−0.006, sd 0.022, z 2.63, against Q_groups 0.698. The fallback runs only when the single draw exceeds 0.05, so s32's
output is unchanged.

## 3. Physical layer (`scripts/physical.py`, `results/physical.json`)

- **Courtyards within 2 mm:** 115 part pairs across groups **(s32: 107)**. The largest are G06-G07 (42), G03-G05 (22)
  and G07-G08 (13). The s42 2512 gate resistors are bigger.
- **Routed copper in another group's territory:** 1,957 mm² **(s32: 2,002)**.

  | Pair | mm² | s32 |
  |---|---|---|
  | G06-G07 | 273 | 242 |
  | G05-G07 | 247 | 239 |
  | G05-G06 | 207 | 218 |
  | G07-G08 | 114 | |
  | G05-G08 | 112 | |
  | G03-G05 | 106 | |
  | G09-G10 | 87 | 119 |

  Shared-plane pours add 27,705 mm². The largest are G02-G03 (2,173), G01-G02 (2,045) and G02-G08 (1,750).
- **Contested corridor:** the same 15 tiles in the same strip (x 30-110, y 130-180), with the same pair counts. The
  pairs that share it most are G09-G10 (14), G05-G10 (12) and G01-G10 (12). The lock kept the spine still (section 7b).
- **The y 47-60 band, changed since s32:** stage 40 used U42's pocket (U44 sits in it), which moved the band's
  routing room.

  | Net type | s43 | s32 |
  |---|---|---|
  | SELV | 0 % on every layer | 0 % / 0.2 % on In1 |
  | HS-B (SW_B) | crosses on B.Cu (16 %) and In2 (17 %); 0 via-legal cells | In2 only; 1 cell |
  | Low-side (LOW) | crosses on In2 only (21 %) | F and B |

  An HS-B route that needs a layer change is still closed.
- **Routing room is tightest in G03, G05 and G07** (LOW-legal free fraction 0.081, 0.085 and 0.155). It is largest in
  G04 (0.41), G06 (0.41) and G01 (0.39). G10's room fell 0.32 → 0.19: without PS1 its territory is mostly the SELV
  spine.
- **Barrier:** 221 net pairs at 8.0-9 mm across the barrier **(s32: 260)**.
  - Pairs touched per group: G05 153, G07 161, G08 126, G10 118, G09 104, G06 96.
  - The HOT-only groups touch few: G01 17, G03 11, G02 5, G04 4.
  - The floor is unchanged at 8.047 mm (n_ha / leg_a-permit_gate), with HOT-PE at 8.507 mm. The control now reads both
    values from the stage's scorecard.

## 4. Physics layer (`scripts/physics.py`, `results/physics.json`)

**Thermal.** Changed since s32, two B3 heat maps are used (`b3_maps.py`):

- **c18_h10, the primary.** This is the release case (DECISIONS 56): an 18.9 A trip, I_line 13.5 A. It is built
  exactly as `b3-ratings/run_basis.inputs` builds it: tank rows × 0.413, L1 × 1.479.
- **c28_h25, kept for continuity** with the s32 audit (`thermal_other_runs`).

Both are legacy `thermal.py` deposit maps, and only their heat is used.

| Group | c18 release, 15.32 W | c28_h25, 25.04 W | s32 c28_h25, 25.24 W |
|---|---|---|---|
| G06 | 4.13 | 4.83 | 5.00 |
| G01 | 2.84 | 2.96 | 2.83 |
| G05 | 2.03 | 3.02 | 2.25 |
| G03 | 1.49 | 3.32 | 3.40 |
| G04 | 1.38 | 3.32 | 3.28 |
| G08 | 1.17 | 2.70 | 2.73 |
| G02 | 0.97 | 2.34 | 2.37 |
| G09 | 0.68 | 1.22 | 1.23 |
| G07 | 0.64 | 1.34 | 1.39 |
| G10 | 0.00 | 0.00 | 0.76 (PS1) |

At the release case, the fixed loads take most of the heat: the bias supplies and PS2 (G06), L1 / BR1 at 13.5 A (G01)
and the 2512 gate networks (G05).

Heat deposited within 5 mm of another group's parts:

| From → to | c18 W | c28 W | s32 c28 W |
|---|---|---|---|
| G06 → G07 | 1.35 | | |
| G05 → G03 | 0.93 | 1.46 | 0.96 |
| G01 → G02 | 0.84 | | |
| G08 → G05 | 0.78 | 1.89 | 1.85 |

The legacy single-cell hottest parts at c18 are U42 (G06) and R20 (G05). At c28 R10 (G05, 147.2 °C) has displaced R5,
and that is the s42 gate network's heat. These peaks are mesh artefacts (DECISIONS 46) and are not ratings. The
heat-sensitive terms barely move if c28 is the primary (`--b3-primary c28_h25_p1p0`); only G01-G06 falls, 0.212 →
0.179.

**Coil field.** The OCP pickup is 4.17 A against a 6.5 A gate (64 %), unchanged.

**Return-path references.** 15 open changes **(s32: 18; s40 closed MON_GOOD_HA's four and added one at the GOOD
node)**:

- 8 have no transfer capacitor in reach **(s32: 11)**.
- 7 lean on other groups' capacitors, as before: C144 (G07) 3, C47 (G09) 2, C61 (G05) 1, C156 (G10) 1.

**dv/dt.** Still a small term. The largest victim is n_ls, at 29.7 mm² **(s32: 27.1)**.

**Creepage.** RES_A keeps 12.6 mm, and its closest neighbour is still line_zc_raw (G09) at 13.375 mm, a 0.775 mm
margin. v15_selv, the s32 runner-up at 14.4 mm, was deleted with PS1. The next is pe at 19.2 mm.

## 5. Verification layer (`scripts/verification.py`, `results/verification.json`)

Changed since s32, the s43 card carries metrics the s32 card did not. They are read when present:

| Metric | How it is read |
|---|---|
| b3_ratings gate, b3_laminate / rated_part / release margins | on the B3 heat share; one body-level run set, so counted once in the coupling sum (`family`) |
| track_* geometry (4 metrics) | global |
| jet_strip_height | parts C12 / C13 / C19 / C20 / C55: G03, G05 |
| bank_ratio_tdk_28A_35k | the bank: G04 |

- **15 checks are global (s32: 11).**
- **Non-global checks per group:** G01 18, G02 13, G03 14, G04 17, G05 22, G06 17, G07 20, G08 22, G09 20, G10 14.

The pairs that share the most re-checks:

| Pair | Shared reads | s32 |
|---|---|---|
| G05-G08 | 1.86 | |
| G05-G07 | 1.76 | |
| G07-G08 | 1.70 | |
| G07-G09 | 1.30 | |
| G08-G09 | 1.23 | |
| G05-G09 | 1.15 | |
| G09-G10 | 1.12 | 1.69, the largest |

G09-G10 lost PS1's leakage and heat share.

## 6. Combined ranking (`scripts/combine.py`, `results/combined.json`)

The method is unchanged: each layer is scaled to [0, 1] and the combined score is the plain mean of the four.

| Rank | Pair | Combined | s32 (rank) | Electrical | Physical | Physics | Verification |
|---|---|---|---|---|---|---|---|
| 1 | G05-G07 | 0.483 | 0.510 (2) | 0.27 | 0.46 | 0.25 | 0.95 |
| 2 | G03-G05 | 0.451 | 0.414 (5) | 1.00 | 0.22 | 0.28 | 0.30 |
| 3 | G09-G10 | 0.448 | 0.571 (1) | 0.67 | 0.42 | 0.10 | 0.60 |
| 4 | G05-G10 | 0.431 | 0.475 (3) | 0.69 | 0.32 | 0.23 | 0.48 |
| 5 | G06-G07 | 0.428 | 0.405 (6) | 0.26 | 0.64 | 0.39 | 0.41 |
| 6 | G05-G08 | 0.404 | 0.433 (4) | 0.07 | 0.35 | 0.19 | 1.00 |
| 7 | G05-G06 | 0.354 | 0.337 (8) | 0.40 | 0.29 | 0.21 | 0.51 |
| 8 | G07-G08 | 0.347 | 0.378 (7) | 0.03 | 0.37 | 0.06 | 0.92 |
| 9 | G05-G09 | 0.294 | 0.319 (10) | 0.14 | 0.28 | 0.14 | 0.62 |
| 10 | G02-G03 | 0.291 | 0.304 (12) | 0.87 | 0.02 | 0.04 | 0.24 |
| 11 | G07-G09 | 0.287 | 0.318 (11) | 0.09 | 0.26 | 0.10 | 0.70 |
| 12 | G08-G09 | 0.269 | 0.278 (14) | 0.09 | 0.27 | 0.05 | 0.66 |
| 13 | G08-G10 | 0.263 | 0.298 (13) | 0.28 | 0.27 | 0.00 | 0.50 |
| 14 | G01-G10 | 0.242 | 0.326 (9) | 0.20 | 0.22 | 0.00 | 0.54 |
| 15 | G04-G09 | 0.213 | 0.204 (16) | 0.12 | 0.02 | 0.26 | 0.45 |
| 16 | G01-G06 | 0.212 | 0.166 (19) | 0.13 | 0.08 | 0.04 | 0.60 |

The other 29 pairs score below 0.20. G03-G10 is lowest, at 0.025.

What moved:

- G09-G10 and G01-G10 fell with PS1. PS1 was G10's heat, its leakage row and its l_filt / n_filt link.
- G03-G05 rose. The 2512 gate network shares the FET-row heat and the jet strip.
- G01-G06 rose. The two largest release-case heat sources and the leakage budget (PS2 against the Y caps) are G01's and
  G06's.

**Total coupling per group:** G05 2.78, G07 2.01, G09 1.97, G08 1.89, G10 1.83, G06 1.65, G03 1.46, G01 1.45,
G04 1.05, G02 0.80.

## 7. Empirical check against stages 19c → 43 (`scripts/history.py`, `results/history.json`)

Changed since s32, the chain is extended with the adopted stages, read from their commits:

| Stage | Commit |
|---|---|
| s35 | `65c6bd08e` |
| s38 | `7f1fe9d3a` |
| s40 | `95e24e554` |
| s41 | `57fc55409` |
| s42 | `5ff4aded2` |
| s43 | `719084486` |

- **Stages skipped:** s33 (six layers, not adopted, DECISIONS 40) and s37 (cleanup on s35, board not merged,
  DECISIONS 48). s34, s36 and s39 were never built.
- **Commit check:** a control confirms that each commit's netlist parts are its copper dump's parts, and that the dump is
  the board its scorecard names.

Stages 19c-32 are as before. The new rows:

| Stage | DECISIONS | Intended | Copper changed in another group's territory | Metrics that moved |
|---|---|---|---|---|
| 35 | 44 | G04 (SMT coil terminals) | none (40 items, all in G04) | none |
| 38 | 50 | G01, G06, G10 (PS1 out, PS2, L_FILT / N_FILT re-laid) | G02 (2), G07 (2), G09 (2) | EMI, leakage; B3 margins (basis change, DECISIONS 51); track geometry (global) |
| 40 | 52 | G06, G07, G10 (U44 link, C161 / C168) | G05 (34), G08 (2) | return path; B3 margins; legacy B3 peaks (basis change: new c28 heat file); track geometry |
| 41 | 53 | G02, G03, G08 (tank copper) | none (4 items, in G08; pours on hv_ret / leg_ret) | B3 ×3 |
| 42 | 55 | G05 (gate network) | G03 (12) | B3 ×4, ledger, track geometry |
| 43 | 57 | all ten (global cleanup pass) | — (no outside group) | B3 ×4, track geometry ×4 |

DECISIONS records two new ripples in words, and they are added as positives:

- **s40, G07 → G05:** the HS-B verdict change removed the SELV decoupler that served pwm_hb's via. The return-path
  change failed the asserted 3 mm limit at 16.5 mm, so C168 was added.
- **s42, G05 → G03:** the first build's R11 sw_a via cut the leg-A In1 fuse neck to a 0.882 ratio. The network's own
  heat also cost the FET-row laminate 7.8 K at c28.

**How well the model separates rippled pairs from quiet ones.** This is the s43 model on all 185 cases (50 positive);
ROC AUC:

| Score | All 185 cases | s32 run, 104 cases |
|---|---|---|
| Combined | **0.768** | 0.808 |
| Physical | 0.823 | 0.848 |
| Verification | 0.728 | 0.804 |
| Electrical | 0.666 | 0.671 |
| Physics | 0.650 | 0.700 |

Over the 44 distinct pairs (23 positive), the combined AUC is 0.770 (s32: 0.78). Ripple still travels through shared
floor space and routing room more than through shared nets.

**Metric check:** 29 of 30 moved metrics were in the target groups' read lists. The one miss is still stage 22's OCP
pickup, and following coupling one step catches all 30. Counted apart:

- the global track-geometry moves;
- the two basis changes DECISIONS attributes to a model change: the s38 B3 margins (DECISIONS 51) and the s40 legacy B3
  peaks (the first chain on the corrected heat file).

**Thresholds** (recall = share of ripple pairs at or above τ; false alarm = share of quiet pairs):

| τ | Recall | False alarm | Workstreams | Groups that can change concurrently |
|---|---|---|---|---|
| 0.20 | 0.52 (s32 0.67) | 0.14 (0.12) | 1 | 4: G03, G04, G07, G10 |
| 0.263 (median of ripple pairs; s32 0.308) | 0.52 | 0.00 | 3 | 5: G01, G03, G04, G07, G10 |
| 0.308 (s32's τ) | 0.35 | 0.00 | 4 | 7: G01, G02, G03, G04, G06, G08, G10 |

The pairs the model under-scores still ripple through router or region effects. New among them are the s38 mains
re-route pairs: G01 / G06 / G10 → G02 and G07.

### 7b. Did the SELV-spine lock work? (`scripts/spine.py`, `results/spine.json`)

The lock gate (`native-21/layout/gates/spine_lock.py`, `selv_spine_lock.json`) came after stage 32. Its own scope
function was applied, unchanged, to every consecutive pair of the chain. A control confirms that it reproduces the s43
chain's own SPINE_LOCK verdict and its 522 locked items.

| | Copper stages | Stages that changed locked spine items | Items changed |
|---|---|---|---|
| Before the lock (19c → 32) | 7 | 4: s22 6, s28 1, s30 440, s32 37 | 484 |
| After the lock, non-owner lanes (s35, s40, s41, s42, s43) | 5 | **0** | **0** |
| After the lock, the SELV owner lane (s38) | 1 | 1 (re-issued the lock) | 42 |

s38's 42 items break down as:

- the deleted V15_SELV copper (12 tracks, 12 vias, J4.1's 4 pad keys);
- the selv_gnd / v3v3 antipad fills;
- 4 test points renumbered on unchanged copper.

Its owner-scope change is 10 items, and every chain since passed against the s38 baseline.

The contract's "must not move" values held through s35-s43: D5 8.047 / 8.507 mm and worst asserted return path
2.72 mm. Open changes improved, 18 → 15.

So, as with the OCP lock, the spine stayed still while the lanes around it changed. s40 changed 167 routed items in G07's
territory and 34 in G05's, and the s43 cleanup touched 100 nets board-wide. The cleanup tool honours the spine region
(DECISIONS 48).

**Caveat.** The post-lock lanes were built as local patches on a frozen routed base (`patches21.edit_base*`). That by
itself limits router ripple, so the lock is shown to hold, not shown to be what held it. The G09 / G10 territory outside
the spine region still took edits: s40's C168 (11 items) and the s43 cleanup (169 items).

## 8. Parallelisation plan (`scripts/contracts.py`, `results/contracts.json`)

### Lane A: part and value changes. All ten groups in parallel.

The evidence is unchanged (4 of 4 parts-only stages). The value swaps since are consistent with it:

- s42's gate network changed only its own nets' copper and the FET-row heat it was meant to add;
- s43's snubber MPN was a pure re-key.

Each group still freezes:

- footprint, pad numbering and pin → net map;
- courtyard and height. The jet-strip height gate (C12 / C13 / C19 / C20 / C55) is now one of the checks;
- heat at or below its B3 input. The basis is now the c18 release case, with b3_release_margin_K at +1.2 K;
- a datasheet-ledger row.

### Lane B: layout changes. Five workstreams, now five contracts.

The workstreams are as at s32 (WS5 no longer has PS1). Contracts at combined ≥ 0.20:

| Contract | Max edge (s32) | Interface | Must not move (s43 values) |
|---|---|---|---|
| WS4 ↔ WS5 | 0.431 (0.475) | 13 nets: pwm_*, permit, vbus_*, bus_fault_iso, sw_a …; 15 spine tiles; 127 barrier pairs, closest 8.061 mm | return_path19 PASS, open changes 15, worst asserted 2.72 mm, D5 8.047 / 8.507, bypass, b3_ratings PASS (release +1.2 K). **Now enforced by the spine lock** |
| WS2 ↔ WS4 | 0.451 (0.414) | gate nets at Q2 / Q3 / Q5 / Q6 against the 2512 R_on and 4.7 nF Cgs, sw_a / sw_b, leg_ret, bus_p at R26, hv_ret at R5.4 | fusing ratio 0.993, which is the s41 / s42 neck margin; jet_strip_height; B3 laminate −30.2 K |
| WS1 ↔ WS5 | 0.242 (0.326) | l_filt, n_filt, pe | leakage 0.241 mA, against a 0.25 mA budget |
| WS3 ↔ WS5 | 0.213 (0.204) | coil_feed; the RES_A 12.6 mm keep-out, where line_zc_raw holds 0.775 mm | res_a_outer_min 13.375 mm |
| **WS1 ↔ WS4 (new)** | 0.212 (0.166) | l_filt / n_filt at PS2 and J3, bus_p / hv_ret at BR1 | leakage 0.241 mA (8.8 µA margin: PS2 against the Y caps C3 / C4); the release-case heat share (L1 / BR1 at 13.5 A against the bias supplies) |

The new contract is mostly a shared re-check (verification 0.60). The layout coupling between WS1 and WS4 is small
(electrical 0.13, physical 0.08). It drops below 0.20 if c28 is the heat basis (0.179).

## 9. Is the ten-group partition right? (`scripts/regroup.py`, `results/regroup.json`)

It is still not right for layout. The re-score on s43 (LS now 96 parts, with D20 and R135):

| | Current (10) | Islands (11) | Islands + SELV (9) |
|---|---|---|---|
| Q, all nets | 0.441 | 0.594 | **0.627** |
| Inter-group cut share | 0.381 | 0.255 | **0.194** |
| Mean conductance | 0.434 | 0.364 | **0.285** |
| Courtyard contacts ≤ 2 mm | 115 | 97 | **86** |
| Routed copper in another group's territory | 1,957 mm² | 1,815 | **1,636** |
| Contested corridor tile-pairs | 133 | 147 | **30** (s32: 60) |

The recommendation stands:

- Schedule layout by islands + SELV: HS-A, HS-B, LS, SELV side, G08, power path (G02 + G03), G01, G04.
- Keep the function groups as review units.
- The interfaces are the straddlers: U1 / U2, U41 / U42, U43 / U44, U32, PS2.

At the group level the combined graph's own clusters are unchanged from s32:

- {G01, G04, G09, G10}, {G05-G08}, {G02, G03} at resolution 1.0;
- {G02, G03}, {G06, G07}, {G09, G10} plus singletons at 2.0.

## 10. How many workstreams, and what raises the count

**Today, for layout (s43):**

- **History-calibrated threshold (τ 0.263):** 3 connected workstreams ({G01}, {G04}, the rest) and at most 5 groups
  concurrent.
- **s32's threshold (0.308):** 4 workstreams and 7 concurrent.
- **In practice:** five workstreams (WS1-WS5) with the contracts above. The SELV-spine contract is now enforced by the
  lock and is shown to hold. Without it, WS4 and WS5 merge into four.

**What would raise the count:**

1. **The spine lock:** done (section 7b).
2. **Six layers:** not adopted (DECISIONS 40). For the record, the s43 bound cuts:
   - G05-G10 0.431 → 0.318;
   - G09-G10 0.448 → 0.345;
   - G06-G07 0.428 → 0.328;
   - G05-G07 0.483 → 0.402.

   At τ 0.263 it removes the G05-G09, G07-G09, G08-G09 and G08-G10 edges. It does not change the component count (3),
   and it takes concurrent groups from 5 to 6.
3. **Regroup by island:** section 9.

## Out-of-sample check, stages 33-43 (`scripts/oos.py`, `results/oos.json`)

The stage-32 model (`results-s32/`, byte-identical to the committed stage-32 results) was frozen before stages 35-43
existed. It was scored, unchanged, on the cases those stages produced. The labelling rule is the same, applied on s43's
territories. s43 itself adds no case.

There are 81 new cases, 16 of them positive: s35 9 / 0, s38 21 / 9, s40 21 / 6, s41 21 / 0, s42 9 / 1. A control
confirms that the frozen model reproduces its own committed AUC on its own history (0.808).

| ROC AUC | Frozen s32 model, old stages (in sample, 104 cases) | Frozen s32 model, **new stages (out of sample, 81 cases)** | s43 model, new stages |
|---|---|---|---|
| Combined | 0.808 | **0.699** (bootstrap 95 % 0.54-0.84; 99 % of resamples > 0.5) | 0.703 |
| Physical | 0.848 | **0.783** | 0.782 |
| Electrical | 0.671 | 0.652 | 0.655 |
| Verification | 0.804 | 0.623 | 0.618 |
| Physics | 0.700 | 0.551 | 0.570 |
| Distinct pairs, combined | 0.78 | 0.733 (41 pairs, 16 positive) | 0.730 |

**Thresholds on the new distinct pairs** (frozen model):

| τ | Recall | False alarm | In sample, s32 |
|---|---|---|---|
| 0.308 (its own) | 0.44 | 0.16 | 0.50 / 0.08 |
| 0.20 | 0.56 | 0.24 | 0.67 / 0.12 |

Where the new positives ranked among their stage's cases (frozen scores):

- **s40:** G07 → G05 2nd of 21 (0.51; also the documented C168 return-path failure), G10 → G05 3rd, G07 → G08 4th,
  G06 → G05 5th.
- **s42:** G05 → G03 4th of 9 (0.41).
- **s38:** G10 → G09 1st of 21 (0.57), G06 → G07 3rd. The other seven s38 positives ranked 6th-20th. They are the
  2-item crossings of the re-laid L_FILT / N_FILT mains pair through G02 / G07 / G09 territory. Part of the low score is
  that G06 counts as intended only because PS2's MPN changed in the same stage.

**Sensitivity of the frozen model's new-case AUC:**

| Variant | AUC |
|---|---|
| without s38 | 0.86 |
| ripple threshold ≥ 5 items instead of ≥ 2 | 0.92 (4 positives) |

**Metric check with the frozen read lists:** all 8 moved metrics that the s32 card carried were in the intended groups'
s32 read lists. The track-geometry metrics and the B3 ratings margins were not on the s32 card, so they cannot be
tested.

**Verdict.** The model's ranking held up out of sample, but only in part.

- It still puts rippled pairs above quiet ones, and its strongest new predictions were right: s40 → G05, s42 → G03.
- Its combined AUC fell from 0.81 to 0.70, with a wide interval on 16 positives.
- The physical layer (floor space, routing room, corridors) carried the out-of-sample skill.
- The physics layer did not: its heat and return-path terms did not predict which territories took copper.
- The weakness is long shared nets re-laid across other groups' territory (s38). The model under-scores these,
  because the coupling sits on the net's path, not on the groups' parts.
- Use the model to schedule, not to waive the scorecard.

## Script changes since the stage-32 run

| Script | Change |
|---|---|
| `stages.py` (new) | Stage registry: board sha, root commit, BUILDDIR, B3 runs, rule cut-off. Adopted chain 19c → 43 with commit refs; s33 / s37 recorded as not adopted |
| `common.py` | `init()` parses `--stage / --root / --out / --repo / --build / --b3-dir / --b3-primary` and sets every path that was hard-coded to s32: board sha, dump, BUILDDIR (`S32_BUILD` → `BUILD`), courtyards, cards. `card()` and `method()`: method texts are templated per stage, and the s32 rendering reproduces the committed text. Rules R1-R5 carry the stage that introduced them (`assign_stage`, `rules_for`); `python3 common.py` prints the results directory |
| `assign32.py` → `assign.py` | Stage-aware rule set; new R5 (U44 / C159 / C160 at s40); control names follow the stage |
| `b3_maps.py` (new) | Checks the root's board file is the stage's board. Checks committed heat maps by sha256, or regenerates them with the root's own `thermal.py` (s43 c18 from `run_basis.inputs`, c28 as `run_study`), with controls against the committed B3 output |
| `electrical.py` | Stage options. The random-relabelling control falls back to a 200-draw seeded null when its single draw exceeds 0.05 |
| `physical.py` | Stage options; the barrier control reads D5 from the stage's card instead of the literals 8.047 / 8.507 |
| `physics.py` | Thermal is a function over the registry's B3 runs: primary, plus `thermal_other_runs`. Pickup / return path / creepage files are per stage |
| `verification.py` | Per-stage files (Kelvin budget, necks, BUILDDIR). Reads the later card metrics when present. A check run reporting several values (the B3 ratings gate and its margins) counts once (`family`). The B3 note names the run's own hottest parts |
| `history.py` | Chain from `stages.py` (tags, then commits). AUTHORED / DOCUMENTED_RIPPLE / GLOBAL_EVENTS for s35-s43 from DECISIONS 44-57. BASIS_CHANGES. Per-stage controls: commit = dump = card board, and the parts / BOM changes are the DECISIONS item's |
| `combine.py` | `eval_cases()` factored out for `oos.py`. The metric check sets global and basis-change moves apart |
| `contracts.py` | Card per stage; the "stageNN" value key; the WS5 name drops PS1 when PS1 is gone |
| `regroup.py` | Stage options |
| `spine.py`, `oos.py` (new) | Sections 7b and the out-of-sample check. Both skip the s32 run, which has no lock and no later history |
| `run_all.sh` | Takes stage options. Each step now returns on failure: `set -e` does not act inside a function called left of `\|\|`, so before this a crashed script went unnoticed |
| `export_stage.sh` (new) | Exports a stage's in-repo inputs at a commit, plus its chain board file |

## Limits

- **Weights and sample size.** The four layers are weighted equally. The AUC rests on 23 distinct rippled pairs from 12
  targeted copper stages. The out-of-sample test has 16 positives from 3 stages, and one of those stages (s38) supplies
  9 of them.
- **Intended groups.** Each stage's intended groups come from its parts / placement diff plus the DECISIONS item
  (`history.py` AUTHORED, with item numbers). A parts-only change in a copper stage, such as PS2 at s38, makes its group
  intended even though it moved no copper.
- **Ripple attribution.** Copper ripple is placed by the territory of the audited board, so router variance counts as
  ripple, as before.
- **Heat maps.** Thermal uses legacy `thermal.py` deposit maps. The c18 one is a re-solve of the release inputs, not
  the body-level ratings model that sets the margins. Its hottest-part temperatures, at a fixed 50 °C ambient, are not
  ratings.
- **Six-layer figures are a bound**, and six layers were not adopted.
- **What was left untouched.** GROUPS.md and groups.json were not changed; the per-stage assignment lives here.
