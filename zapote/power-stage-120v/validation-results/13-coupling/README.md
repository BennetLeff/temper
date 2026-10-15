# 13 Coupling audit: how far can native-21 work be parallelised?

Board: native-21 stage 32 (tag `native21s32`, board `2fb346dc…`, frozen netlist `f23302546e74…`, 349 parts).
Question: which of the ten functional groups (`../11-candidates/GROUPS.md`) can be changed at the same time by
separate agents or stages, which changes spill into other groups, and what interface contracts would let them run apart.

Rerun everything (about 60 s; it runs twice and checks the outputs are byte-identical):

    sh validation-results/13-coupling/scripts/run_all.sh

All scripts are `python3 -I` with numpy, scipy, shapely and networkx, and read their inputs without changing them. Each
one writes `results/*.json` and exits 1 if a control fails. The last run passed 126 controls, and all 15 result files
matched over two runs (`results/SHA256SUMS`, `results/run1.log`). Every number below comes from those files.

## Headline

- **Parts-only changes are already independent.** Four stages changed parts only (20, 26, 29, 31). None of them changed
  routed copper, and each moved only the metric it targeted. So any number of groups can run part swaps at once,
  provided each swap keeps the footprint and pin map.
- **Layout changes are not independent.** In 6 of the 7 copper stages, copper also changed in groups the stage did not
  target: 17 such cases in all.
- On layout, the board supports **five workstreams today, but only if one contract is kept.** That contract freezes the
  SELV spine: the PWM, permit, bias_good, bus_fault and vbus bundle into J4. Without it there are four, and six of the
  ten groups (G05-G10) must take turns.
- **The coupling model predicts the past ripple fairly well.** Its combined score separates rippled pairs from quiet
  ones with ROC AUC 0.81 (104 cases from history). The physical layer alone scores 0.85. The model predicted 13 of the
  14 scorecard metric moves directly, and all 14 once coupling is followed one step.
- **The current ten groups do not match the board's natural clusters.** Those clusters follow the isolation islands
  (HS-A, HS-B, low-side, SELV), not the circuit functions. The adjusted Rand index (ARI) between the two partitions is
  0.19. Re-cutting G05/G06/G07 by island and merging the SELV-side logic with G09 and G10 halves the electrical cut
  between groups (inter-group cut share 0.384 → 0.196). It also cuts the corridor tiles groups contend for by 55 %
  (133 → 60).

## 1. Stage-32 group assignment (`scripts/assign32.py`, `results/assignment.json`)

The stage-19c rule is reused unchanged and reproduces 19c for every surviving part. Four rules are added for parts from
stages 20-32:

- **R1:** `hb.*` is the stage-30 heartbeat, so it goes to **G07**.
- **R2:** U43 / U44, the rail-verdict isolators, and their caps go to **G07**. They do monitoring, although the 19c rule
  would have put them in G06.
- **R3:** R130, the F2 limiter, goes to **G10**.
- **R4:** R134 / C167, the BUS_FAULT RC at U13.A, goes to **G09**. This one is ambiguous: the electrical vote is a 1:1
  tie between G08 and G09.

Since 19c, 22 parts are new and 30 have been removed (J7-J10, Q1/Q4, R8/R16, the per-rail notice stages and U25/U33/U34).
Part counts per group: G01 12, G02 6, G03 12, G04 11, G05 92, G06 42, G07 90, G08 42, G09 32, G10 10.

16 parts sit electrically closer to another group than their own. This "vote" is the weight of each part's non-rail
nets, summed by the group on the other end. The parts are:

| Parts | Assigned to | Votes for |
|---|---|---|
| BR1, C5/C6 | G01 / G02 | G03 |
| Q2/Q3/Q5/Q6, C13/C20 | G03 | G05 |
| J2 | G04 | G09 (coil_feed) |
| J4 | G10 | G05 |
| PS1 | G10 | G01 |
| U4 | G08 | G10 |
| U9 | G08 | G08/G09 tie |
| R47, U24 | G09 | G09/G10 tie |

All of them are interface parts by nature. They are the pins the contracts below name.

## 2. Electrical layer (`scripts/electrical.py`, `results/electrical.json`)

This is a part-to-net graph. Each net is spread over its parts with weight 1/(k−1), where k is the number of parts on
it. That way every net adds 1 to each part's weight, and a 70-pin rail counts no more than a 2-pin signal. The graph is
built three ways: all nets; without the supply, ground and plane rails; and also without the poured power nets.

**The board's own clusters:**

| | All nets | Without rails |
|---|---|---|
| Q (how well a split matches the clusters) of the ten groups | 0.440 | 0.597 |
| Q of the Louvain communities | 0.682 (7 communities) | 0.775 (14 communities) |
| ARI against the ten groups | 0.19 | 0.34 |

With rails, the seven communities are the isolation islands:

- HS-A: leg A high side, bias_ha, its monitor.
- HS-B: leg B high side, bias_hb, its monitor, and the tank.
- Low side: both legs' low sides, bias_ls, monitor_ls and the heartbeat.
- SELV interface: J4, CT detect, driver inputs, PS1.
- The G08 HOT5 / Kelvin cluster.
- The power path: G02, G03, BR1 and the bus divider.
- Mains: G01, PS2, line-ZC and the blower tap.

182 of 349 parts sit in a community whose majority is another group.

**Conductance per group** is the share of a group's net weight that leaves the group; lower means more
self-contained. Without rails:

| Group | Conductance | |
|---|---|---|
| G07 | 0.063 | most self-contained |
| G08 | 0.133 | |
| G09 | 0.176 | |
| G06 | 0.222 | |
| G05 | 0.249 | |
| G01 | 0.274 | |
| G04 | 0.290 | |
| G02 | 0.479 | |
| G03 | 0.747 | an interface by nature |
| G10 | 0.759 | an interface by nature |

**Inside each group** (without rails), these are the candidate split points:

- **G06** falls apart into 7 pieces. The three bias supplies and PS2 share nothing but rails.
- **G07** is three 17-part monitors (LS, HS-A, HS-B) plus the heartbeat. Single "good" nets join them (monitor_ls-good,
  bias_ha.monitor-good, bias_hb.monitor-good). Its Fiedler value is 0.008, which means it splits almost cleanly.
- **G05** is leg A and leg B, joined only through leg_ret and the shared driver_dis / LS-bias blocks (Fiedler 0.020).
- **G08** is four blocks: OCP; OVP + AMC1311; HOT5-UV + NAND; and the bus divider. ocp_ok_hot, ovp_ok_hot and vsense_in
  join them.
- **G09** is CT detect (20 parts) and line ZC (7 parts), with no signal net between them.
- G01-G04 are each one tight cluster.

**Strongest electrical links between groups:**

| Pair | Score | Shared nets |
|---|---|---|
| G03-G05 | 1.00 | gate nets, sw_a, sw_b, leg_ret |
| G02-G03 | 0.87 | bus_p, hv_ret |
| G09-G10 | 0.61 | bus_fault, ct_mon, ct_zc, line_zc, l_filt, n_filt |
| G05-G10 | 0.61 | permit, pwm_ha, pwm_la, pwm_hb, pwm_lb |

Scores are scaled to the largest pair (`results/combined.json`, term matrices).

## 3. Physical layer (`scripts/physical.py`, `results/physical.json`)

Every 0.25 mm board cell is given to the group whose courtyard is nearest; that area is the group's "territory".
Copper of one group lying in another's territory counts as interleaving.

- **Courtyards within 2 mm:** 107 part pairs across groups. Most are G06-G07 (38), G03-G05 (18) and G07-G08 (13).
- **Routed copper in another group's territory:** 2,002 mm² in total. The largest shares are:

  | Pair | mm² |
  |---|---|
  | G06-G07 | 242 |
  | G05-G07 | 239 |
  | G05-G06 | 218 |
  | G09-G10 | 119 |
  | G07-G08 | 116 |
  | G03-G05 | 116 |
  | G05-G08 | 111 |

  Pours of shared planes add 28,010 mm². Most of that is G02-G03 (2,153), G01-G02 (2,017) and G02-G08 (1,722), which are
  the bus_p / hv_ret trunks.
- **Contested corridor:** 15 tiles of 10 × 10 mm each hold copper from four or more groups at over 50 % fill. All 15
  lie in one strip, x 30-110 / y 130-180: the SELV spine from J4 to the drivers and detectors. The pairs that share it
  most are G09-G10 (14 tiles), G05-G10 (12), G01-G10 (12), G08-G10 (11) and G05-G09 (11).
- **The y 47-60 band** (x 0-26; DECISIONS 33) is checked as clearance-legal free space for a 0.2 mm track under rules21:

  | Net type | Where it can cross | Free space | Via-legal cells |
  |---|---|---|---|
  | SELV | nowhere | 0 % on F / In2 / B, 0.2 % on In1 | 0 |
  | HS-B (SW_B) | In2 only | 14 % | 1 |
  | Low-side (LOW) | F and B | 34 % and 11 % | — |

  So any HS-B route that needs a layer change is closed. That is the geometric reason 30a / 30b wait.
- **Routing room is tightest in G03, G05 and G07.** Their mean low-side-legal free fraction is 0.099, 0.100 and 0.144.
  It is largest in G04 (0.41), G06 (0.41) and G01 (0.39).
- **The barrier is a real decoupler for the HOT-only groups.** There are 260 net pairs at 8.0-9 mm across the HOT/SELV
  barrier. G05 touches 168 of them, G07 200, G08 137, G10 128, G09 115 and G06 100. G01 touches 17, G03 11, G02 5 and
  G04 4, and those few come from the shared bus_p / hv_ret planes (minimum 8.162 mm, bus_p / selv_gnd on In2). The
  floor itself is 8.047 mm: n_ha against leg_a-permit_gate, which spans G05, G06 and G07. It matches the D5 audit.

## 4. Physics layer: coupling that is on no net (`scripts/physics.py`, `results/physics.json`)

This layer reads existing model outputs only; it runs no new physics.

- **Thermal.** B3's own deposited-heat map for the c28 run (25.24 W) is split by group:

  | Group | W |
  |---|---|
  | G06 | 5.00 |
  | G03 | 3.40 |
  | G04 | 3.28 |
  | G01 | 2.83 |
  | G08 | 2.73 |
  | G02 | 2.37 |
  | G05 | 2.25 |
  | G07 | 1.39 |
  | G09 | 1.23 |
  | G10 | 0.76 |

  The hottest spots belong to G08 (R5, 135.0 °C) and G06 (U42, 132.9 °C). R5 sits in G08's own territory, but G08's heat
  lands next to G05's parts (1.85 W within 5 mm) and G03's (1.34 W). Within 15 mm, G06 puts 3.01 W next to G07 and G03
  puts 2.78 W next to G05. This is a proximity screen on B3's heat, not a separate solve.
- **Coil field.** The coil current (driven through G04) couples into G08's OCP loops at 4.17 A against a 6.5 A gate,
  which is 64 % of the gate. CT and line-ZC pickup is negligible (`coil-pickup/PICKUP.md`).
- **Return-path references.** 11 of the 18 open reference changes have no transfer capacitor in reach. They are mostly
  G07 / G08 HOT-side nets: mon_good_ha, bus_fault_hot, ovp_ok_hot, ocp_ok_hot. The other 7 lean on capacitors in other
  groups:

  | Capacitor | Group | Open changes |
  |---|---|---|
  | C144 | G07 | 3 |
  | C47 | G09 | 2 |
  | C61 | G05 | 1 |
  | C156 | G10 | 1 |

  So a SELV signal's return path depends on another group's parts and plane pair. The signal-to-capacitor pairs are
  G05→G10, G10→G09, G05→G07 and similar.
- **dv/dt.** The switching domains overlap other domains' copper by only a few mm² on adjacent layers. The largest
  victim is n_ls, at 27 mm². The static bus, return and leg planes screen the bridge by design. This is a small term.
- **Creepage.** RES_A (G04) keeps 12.6 mm on the outer layers. Its closest neighbours are line_zc_raw (G09) at 13.375 mm,
  0.775 mm of margin, and v15_selv (G10) at 14.4 mm. So G04 and G09 are coupled through a keep-out, not a net.

## 5. Verification layer (`scripts/verification.py`, `results/verification.json`)

Each gate and metric is mapped to the parts and nets it reads, from its own stage-32 files.

- **11 are global.** DRC, DFM, enclosure fit, audit.rs, the ledger, cost, the via count and the CPL audit run on any
  change.
- **The rest re-trigger per group.** Non-global checks per group: G01 14, G02 9, G03 9, G04 12, G05 17, G06 13, G07 16,
  G08 18, G09 16, G10 17.

The pairs that share the most re-checks are:

| Pair | Shared reads |
|---|---|
| G09-G10 | 3.39 |
| G05-G08 | 3.37 |
| G05-G07 | 3.37 |
| G07-G08 | 3.08 |
| G07-G09 | 2.42 |
| G01-G10 | 2.32 |

The cross-cutting metrics are B3 peaks, barrier / D5, the return path and task 04. Single-owner metrics are those whose
inputs belong to one group: Kelvin band (G08), CMTI gate ratio (G05), bank ratio (G04), and OCP pickup (G08, plus the
coil current from G04).

## 6. Combined ranking (`scripts/combine.py`, `results/combined.json`)

Each layer is scaled to [0, 1], and the combined score is the plain mean of the four.

| Rank | Pair | Combined | Electrical | Physical | Physics | Verification | What binds them |
|---|---|---|---|---|---|---|---|
| 1 | G09-G10 | 0.571 | 0.61 | 0.56 | 0.11 | 1.00 | J4 signals, SELV spine, transfer caps |
| 2 | G05-G07 | 0.510 | 0.27 | 0.50 | 0.28 | 0.99 | same islands, barrier floor, bias_good |
| 3 | G05-G10 | 0.475 | 0.61 | 0.45 | 0.24 | 0.60 | PWM / permit bundle to J4 |
| 4 | G05-G08 | 0.433 | 0.07 | 0.43 | 0.23 | 1.00 | low-side area, R5 heat, Kelvin plane |
| 5 | G03-G05 | 0.414 | 1.00 | 0.21 | 0.28 | 0.17 | gate nets, switch nodes, gate loop |
| 6 | G06-G07 | 0.405 | 0.26 | 0.65 | 0.30 | 0.42 | 38 courtyard contacts, island pockets |
| 7 | G07-G08 | 0.378 | 0.04 | 0.50 | 0.07 | 0.91 | low-side area, In1 n_ls vs ocp_kelvin_p pour |
| 8 | G05-G06 | 0.337 | 0.40 | 0.30 | 0.23 | 0.42 | driver rails |
| 9 | G01-G10 | 0.326 | 0.30 | 0.32 | 0.01 | 0.68 | l_filt / n_filt / pe, leakage |
| 10 | G05-G09 | 0.319 | 0.14 | 0.36 | 0.15 | 0.63 | SELV spine |
| 11 | G07-G09 | 0.318 | 0.10 | 0.35 | 0.11 | 0.71 | SELV spine |
| 12 | G02-G03 | 0.304 | 0.87 | 0.02 | 0.06 | 0.26 | bus_p / hv_ret |
| 13 | G08-G10 | 0.298 | | | | | |
| 14 | G08-G09 | 0.278 | | | | | |
| 15 | G07-G10 | 0.243 | | | | | |
| 16 | G04-G09 | 0.204 | | | | | coil_feed, RES_A keep-out |

The other 29 pairs score below 0.20. G02-G07 is lowest, at 0.029.

**Total coupling per group** (sum of its row): G05 2.83, G10 2.27, G09 2.14, G07 2.13, G08 2.03, G06 1.63, G03 1.50,
G01 1.47, G04 1.09, G02 0.86.

## 7. Empirical check against stages 19c → 32 (`scripts/history.py`, `results/history.json`)

Each stage was diffed against the one before it: BOM, netlist pins, placement, routed copper per net (each item placed
in a group's territory) and scorecard.

| Stage | Intended | Copper changed in another group's territory | Metrics that moved |
|---|---|---|---|
| 20 | G04, G09 (parts only) | none | bank_ratio |
| 21 | G01, G02, G03, G08 | none (42 items, all in G08) | B3 ×2, fusing ratio |
| 21b | G08 | G06 (50), G07 (70) | Kelvin band, OCP pickup |
| 22 | G05, G07 | G06, G08 (78), G09 (38), G10 | OCP pickup, return path |
| 26 | G05 (parts only) | none | none |
| 27 | G01 | G07 (21) | ledger only |
| 28 | G10 | G07, G08, G09 (64) | ledger only |
| 29 | G05 (parts only) | none | cmti ratio |
| 30 | G07, G09 | G05 (71), G06 (102), G08 (36), G10 (46) | B3 ×2, return path |
| 31 | G05-G08 (parts only) | none | none |
| 32 | G07, G08, G09 (+120 vias resized) | G05, G06, G10 | B3 c28, return path |

DECISIONS also records ripple in words, and those cases are added as positives:

- 22: pwm_hb's via spot, and ocp_thresh re-laid.
- 27: a dead permit branch trimmed.
- 28: the router re-laid ocp_node / ocp_thresh, and pickup went 4.17 → 4.78 A; that is why the OCP lock exists.
- 30: the HS-B link was blocked by U42's n_ls pocket, the In2 bus_p trunk and the PWM bundle.
- 32: 7 return-path fixes need the PWM bundle moved.

**How well the model separates rippled pairs from quiet ones** (104 cases, 34 positive; ROC AUC):

| Score | AUC |
|---|---|
| Combined | 0.808 |
| Physical | 0.848 |
| Verification | 0.804 |
| Physics | 0.700 |
| Electrical | 0.671 |

Over the 43 distinct pairs (18 positive), the combined AUC is 0.78. Ripple travels through shared floor space and
routing room more than through shared nets.

**Metric check:** 13 of 14 moved metrics were in the target groups' direct read lists. The miss was stage 22's OCP
pickup, where a G05/G07 change led the router to re-lay G08's nets. Adding the groups that are coupled ≥ 0.308 to the
targets catches all 14.

**Thresholds.** Recall is the share of past ripple pairs scoring at or above τ; false alarm is the same share of quiet
pairs.

| τ | Recall | False alarm | Groups that can change concurrently |
|---|---|---|---|
| 0.20 | 0.67 | 0.12 | 5: G01, G03, G04, G06, G08 |
| 0.308 (median of ripple pairs) | 0.50 | 0.08 | 7: G01, G02, G03, G04, G06, G08, G09 |

The pairs the model under-scores all rippled through router or region effects: G02-G07 and G03-G07 through the bus_p
trunk, G01-G07 (stage 27), G01-G05, G06-G09 and G06-G08.

**The lock precedent works.** After stage 28 locked the OCP nets, OCP pickup stayed at 4.17 A through stages 30 and 32,
although those stages changed 36 and 12 routed items in G08's territory.

## 8. Parallelisation plan

### Lane A: part and value changes. All ten groups in parallel, today.

Evidence: 4 of 4 parts-only stages changed no routed copper and moved only their target metric (stage 20 bank_ratio,
stage 29 cmti ratio).

Each group freezes:

- footprint, pad numbering and the pin → net map of every swapped part;
- courtyard and height inside the enclosure envelopes;
- heat at or below its B3 c28 input;
- a datasheet-ledger row.

Each group then re-runs only its own list (`contracts.json: bom_only_lane`). The global gates run once at merge.

### Lane B: layout changes. Five workstreams, four contracts.

These are computed in `scripts/contracts.py` / `results/contracts.json`.

| Workstream | Groups | Inside |
|---|---|---|
| WS1 mains / EMI | G01 | |
| WS2 power path | G02 + G03 | serialise G02 / G03; one commutation-loop region |
| WS3 resonant tank | G04 | |
| WS4 drive, bias, monitor, protect | G05 + G06 + G07 + G08 | serialise; the most tightly bound core |
| WS5 SELV side | G09 + G10 | serialise |

Every boundary with a group pair at ≥ 0.20 gets a contract. The "must not move" values are stage 32's.

**WS4 ↔ WS5 (G05-G10 0.475; G05-G09, G07-G09, G08-G10, G08-G09, G07-G10).** This is the binding one.

- **Freeze these nets and pins:**

  | Net | WS4 pin | J4 / WS5 pin |
  |---|---|---|
  | pwm_ha | U1.1 | J4.5 |
  | pwm_la | U1.2 | J4.6 |
  | pwm_hb | U2.1 | J4.7 |
  | pwm_lb | U2.2 | J4.8 |
  | permit | R6.1 / R14.1 | J4.9 |
  | vbus_p | U4.7 | J4.11 |
  | vbus_n | U4.6 | J4.12 |
  | bus_fault_iso | U9.13 | R134.1 |
  | sw_a | — | T1.1 |

  Also freeze the selv_gnd / v3v3 plane pair and the transfer capacitors C47, C144, C153-C156.
- **Geometry:** freeze the routed bundle through the SELV spine, x 30-110 / y 130-180. All 15 contested tiles are there.
  Each side has about 150 mm² of routed copper in the other's territory today (143 and 157). There are 137 barrier
  pairs within 9 mm across this boundary, the closest at 8.061 mm.
- **Must not move:** return_path19 PASS; open changes 18; worst asserted 2.72 mm; bypass PASS; D5 8.047 / 8.507; B3
  135.0 / 162.1 °C.

**WS2 ↔ WS4 (G03-G05 0.414).**

- **Nets and pins:** the gate nets at Q2.1 / Q3.1 / Q5.1 / Q6.1 against R10 / R12 / R18 / R20, D6-D9 and C55 / C56 / C62
  / C63; sw_a and sw_b at Q2.3 / Q3.2 / Q5.3 / Q6.2; leg_ret at Q3.3 / Q6.3; bus_p at R26.1 (bus divider); hv_ret at
  R5.4.
- **Geometry:** the TO-247 pin order and the gate-loop geometry stay as they are. 78 / 180 mm² of routed copper crosses
  the boundary.
- **Must not move:** fusing ratio 0.993; B3; task 04; D5 8.047.

**WS1 ↔ WS5 (G01-G10 0.326).**

- **Nets:** l_filt (BR1.2, C2, C3, L1.4 ↔ F2.1, PS1.1, R67.1); n_filt (BR1.3, C2, C4, L1.3 ↔ J11.2, PS1.2, R70.2); pe
  (C3.2, C4.2, J6 ↔ R38.1).
- **Must not move:** leakage 0.974 mA; HOT-PE 8.507 mm; RES_A outer 13.375 mm. The pe route crosses 12 of the
  contested tiles.

**WS3 ↔ WS5 (G04-G09 0.204).**

- **Net:** coil_feed (J2.1 ↔ T1.2).
- **Keep-out:** the 12.6 mm RES_A outer keep-out. line_zc_raw holds only 0.775 mm of margin, so WS5 must not route
  line_zc_raw nearer.
- **Must not move:** res_a_outer_min 13.375 mm.

**Also, below the 0.20 threshold:**

- WS3 → WS4 coil-field term: the coil terminal position and coil current spec, with OCP pickup 4.17 A against a 6.5 A
  gate.
- WS1 ↔ WS2: BR1.1 / BR1.4 landing on bus_p / hv_ret, with the fusing ratio 0.993.

## 9. Is the ten-group partition right? (`scripts/regroup.py`, `results/regroup.json`)

Not for layout. The electrical communities follow the isolation islands, and so does layout ripple. Two alternatives
were scored on the same data:

- **islands:** G05, G06 and G07 re-cut into HSA (52 parts), HSB (52), LS (94, including the U1 / U2 drivers, U32 and
  PS2) and SLOG (26).
- **islands_selv:** as islands, with SLOG, G09 and G10 merged into one 68-part SELV-side group.

| | Current (10) | Islands (11) | Islands + SELV (9) |
|---|---|---|---|
| Q, all nets | 0.440 | 0.595 | **0.626** |
| Inter-group cut share | 0.384 | 0.256 | **0.196** |
| Mean conductance | 0.432 | 0.363 | **0.288** |
| Courtyard contacts ≤ 2 mm | 107 | 92 | **82** |
| Routed copper in another group's territory | 2,002 mm² | 1,888 | **1,694** |
| Contested corridor tile-pairs | 133 | 180 | **60** |

Recommendation:

- **Schedule layout by islands + SELV:** HS-A, HS-B, LS, SELV side, G08, power path (G02 + G03), G01, G04.
- **Keep the function groups as review units.** They say what a change must re-check.
- **The straddlers are the interfaces:** U1/U2, U41/U42, U43/U44, U32, PS2. Their footprints and pinouts are part of
  every island contract.
- **Split points worth naming inside groups:** G06 per supply; G07 per monitor plus the heartbeat; G09 CT versus line
  ZC; G08 OCP / OVP / HOT5 / divider.

## 10. How many workstreams, and what raises the count

**Today, for layout:**

- At the history-calibrated threshold (τ 0.308), at most 7 groups can be laid out concurrently. At the 2/3-recall
  threshold (τ 0.20) the figure is 5.
- In practice the plan has five workstreams (WS1-WS5), and that count depends on the SELV-spine contract. Without it,
  WS4 and WS5 merge, leaving four.

**What would raise the count:**

1. **Lock the SELV spine,** the way stage 28 locked the OCP nets. That is the contract above, made deterministic, and it
   turns four workstreams into five. The OCP lock is evidence it works: pickup stayed at 4.17 A through two later layout
   stages that touched G08's territory.
2. **Six layers** (c33 `PLAN.md`). The upper bound sets the routing-room terms to zero (interleave, adjacency,
   corridors, return-path changes, the pickup plane term) and keeps barrier, creepage, electrical, thermal and
   verification.

   It cuts G05-G10 0.475 → 0.327, G09-G10 0.571 → 0.432, G06-G07 0.405 → 0.305, G05-G07 0.510 → 0.411 and G05-G09
   0.319 → 0.225. At τ 0.308 it removes the edges G01-G10, G05-G06, G05-G09, G06-G07, G07-G08 and G07-G09. That gives
   5 connected workstreams instead of 3, and 8 concurrent groups instead of 7.

   It cannot cut G03-G05 (still 0.39: gate nets), G05-G08 or the 8 mm / 12.6 mm keep-outs. It is aimed at the right
   place, since the y 47-60 band and the SELV spine are the binding corridors.
3. **Regroup by island** (section 9). This adds no capacity, but it makes each workstream's boundary follow the
   barrier and the islands, which halves the cut between groups.

## Limits

- **Weights and sample size.** The four layers are weighted equally. The AUC rests on 18 distinct rippled pairs from 7
  copper stages.
- **Intended groups.** Each stage's target groups come from its schematic and placement diff plus the DECISIONS item
  (`history.py` AUTHORED, with item numbers).
- **Ripple attribution.** Copper ripple is placed by territory, so router variance counts as ripple. That is
  deliberate: it is the coupling a parallel agent would meet.
- **Thermal and field inputs.** Thermal is a proximity screen on B3's heat map. The CT / line-ZC field verdict is the 13b
  study, which is not rerun per stage.
- **Six-layer figures are a bound,** not a re-route.
- **What was left untouched.** GROUPS.md and groups.json were not changed; the stage-32 assignment lives here.
