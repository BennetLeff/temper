# Heat attribution on the B3 body model: which sources set the still-air ceiling (s43)

Board of record s43 (`61447816…`), repo snapshot cb48 (`cb48a12e6`), B3 body-level model as gated by
`b3-ratings/b3_ratings_gate.py`. The question: which heat sources set the board's still-air current ceiling? The answer
is used to rank the next candidates by ceiling amps per change. Every number below comes from `results.json` /
`tables.md`, which `analyze.py` writes. `tables.md` has the full tables: every gated row, every term, both cases.

## Headline

- **Superposition holds exactly.** The model is linear, and the unit-term solves rebuild the gate's own solves to
  ≤ 5.3e-6 K on every copper cell and ≤ 1.6e-6 K on every gated quantity. They reproduce every gate estimate to within
  0.049 K. That residual is the 0.1 K rounding in `margins.json`.
- **The release case c18_h10 / bay 61 °C has no dominant heat source.** C40 binds at +1.2 K. Of its 108.8 °C:
  - 61.0 K is bay air and 8.1 K the FET-case tie;
  - 38.3 K is board heat, spread over about ten terms of 1.5–5.2 K each;
  - 1.4 K is mesh correction.
- **By kind of change, at C40:**
  - tank-current copper loss: 18.1 K;
  - frequency/charge-set part heat (gate drive, RECOM, U26, PS2): 12.4 K;
  - fixed estimates (mostly C38–C41's own 0.05 W): 4.8 K;
  - tank-scaled parts (R5, bank, C5/C6): 2.9 K.
- **The gated rows are bunched.** Taken alone, each row would allow:
  - C40: 18.44 A;
  - R10 terminal: 19.14 A;
  - laminate 1 mm block: 19.39 A;
  - C41 / C38 / R12 / R20: 19.72–19.85 A;
  - FET-row copper: 20.24 A.

  So fixing one row buys at most 0.7 A before the next row binds. A gain of 1.5 A or more needs a lever that lowers all
  the rows together.
- **Ranked levers (exact re-solve of the gate case, bay 61 °C, from 18.44 A):**

  | Lever | Ceiling gain | Basis |
  |---|---|---|
  | All tank copper −20 % (≈ what 3 oz outer would do; not orderable) | +1.75 A | modelled cut |
  | HF-film self-heat to 0 | +1.03 A | an estimate, not a design change (see Surprises) |
  | Fan sink setpoint −10 K | +0.92 A | firmware |
  | sw_b copper −20 % | +0.70 A | modelled cut |
  | R5 at 0.5 mΩ | +0.63 A | rejected in DECISIONS 53 |
  | Fan sink setpoint −5 K | +0.47 A | firmware |
  | R_on 0.217 → 0.17 W | +0.45 A | the bench IR reading, DECISIONS 56 |
  | sw_b −10 % | +0.34 A | modelled cut |
  | hv_ret −20 % | +0.34 A | modelled cut |
  | RECOM −20 % | +0.29 A | modelled cut |
  | bus_p −20 % | +0.23 A | modelled cut |
  | sw_a −20 % | +0.19 A | modelled cut |

  Bay air is worth **0.27 A per K**: 18.44 A at bay 61 °C, 20.04 A at bay 55 °C.
- **Surprise 1: copper TCR is missing from B3.** The task-04 A4 fields are 20 °C DC copper (their `assumptions`), and
  nothing in B3 corrects them to hot copper. On the c18 field the tank copper runs at 83–112 °C (heat-weighted), which
  is ×1.25–1.36 loss. A first-order correction (one step, no feedback) adds:
  - +6.1 K at C40;
  - +6.5 K at R10 terminal;
  - +7.2 K at the laminate block.

  The ceiling at bay 61 °C drops **18.44 → 16.42 A (−2.0 A)**, so the c18 release case would fail C40 by about 5 K.
  This is a sensitivity outside the gate's model, not a gate result (see section 6).
- **Surprise 2: the binding row hinges on two of its own assumptions.**
  - C40's own 0.05 W (an unverified "edge-harmonic" estimate, bounded 0.2 W in make_heat_sources) reaches its body
    through the assumed lead-only 50 K/W path, with no body-to-air path (OPEN-ITEMS S2 b). That gives 23.5 K/W at C40.
  - At the 0.2 W bound C40 would be about 14 K hotter.
  - The lead-only path is the upper bound named in the gate docstring.

## 1. Linearity: confirmed by reading the code, then by numbers

Code read (snapshot):

- **Matrix, fixed.** `thermal_body.assemble`: cell conductance from k = K_FR4 + cfrac·(K_CU − K_FR4), where cfrac is the
  copper fill fraction, a geometry constant (`body_runs.run_case`), so nothing in it depends on T. Convection is
  `h * area` on the two outer sheets, with h fixed at 10. Barrels are fixed conductances (`barrel_links`).
- **Package networks, fixed.** `build_network_parts` / `solve_system`:
  - each part has fixed conductances: pad g = 1/r_pad split by pad area, and body-to-air 1/(r_top + 1/(h·A));
  - the right-hand side is the part watts.
- **FET drain leads: affine.** `LeadLink` / `solve_system` add g·w·wᵀ to M and g·t_rise·w to the RHS, with
  g = `drain_lead_conductance()`, a constant 0.0845 W/K.
- **Solve.** One SPD system solved by CG (rtol 1e-10).
- **No radiation term and no T-dependent property** anywhere in thermal_body.py, body_runs.py or thermal.py; a grep
  for radiat/emiss finds nothing.
- **Heat inputs are fixed.**
  - A4 copper heat is a precomputed field scaled by run_study.cases()' I² factors (`remap_a4`).
  - Part watts come from the heat file (run_basis.inputs).
  - Nothing feeds T back into a loss. That is also why copper TCR is absent (section 6).

So T = Σ coef_t · T_t exactly, where T_t solves the same matrix with only term t on the right-hand side. Every part
network and every lead tie stays in M for every solve: part watts are zeroed outside the term, never removed, because
`build_network_parts` drops zero-watt parts and that would change M. The non-linear steps all happen after the solve:
- max-type quantities (1 mm-block peak, FET-row max, hottest full pad cell);
- the mesh correction |Q(0.25) − Q(0.5)|.

They are handled by taking each quantity's locator from the synthesized 0.25 mm case field. Each term's value at that
point then sums exactly to the quantity, and 3·|ΔQ| is reported as its own term.

Numbers (`tables.md` "Checks"):

| check | c18_h10 | c22_h10 |
|---|---|---|
| field, 0.5 mm: max \|Σ terms − full solve\|, copper cells | 3.8e-6 K | 5.3e-6 K |
| field, 0.5 mm: max \|Σ − full\|, junction nodes | 3.2e-8 K | 3.5e-8 K |
| 0.25 mm: max \|synth − gate run\| (tj, pad max, block, FET row) | 1.3e-6 K | 1.3e-6 K |
| 0.5 mm: same | 1.6e-6 K | 1.6e-6 K |
| block peak at the gate run's location (both pitches) | yes | yes |
| Σ attribution terms − synthesized gate est (44 rows) | 1.0e-6 K | 1.2e-6 K |
| Σ terms − margins-repro.json / committed margins.json est_c | 0.049 K | 0.049 K |

The ≤ 0.049 K is margins.json's 0.1 K rounding of est_c. The reproduced run (`gate-runs/margins-repro.json`, the
snapshot's own run_basis.py) equals the committed margins.json on all 88 rows (0.0 K). Other controls:
- part watts from unit × coefficient equal run_basis.inputs at c22 and c28 to 5.6e-17 W;
- the worst energy balance over the unit solves is 2.8e-9 W.

## 2. Terms

Each term is solved at 0.25 and 0.5 mm (`solve_terms.py`). Unit bases:

- **A4 copper fields** (14) at scale 1. The case multiplies each by run_study.cases()' factor at I_trip = 1.05 × ceiling.
- **Part groups** (14) at their c18 watts. Tank rows (R5, R39, bank, C5/C6) scale with (I_trip / 18.9)²; the rest are
  fixed. The groups:
  - R5;
  - R_on R10/R12/R18/R20;
  - R_off R53/R54/R57/R58;
  - bank C21–23/C151/C152;
  - C5/C6;
  - HF film C38–C41;
  - RECOM U41/U42;
  - U26;
  - small LDOs U3/U37–U39;
  - PS2;
  - L1;
  - drivers U1/U2;
  - R39;
  - the rest (R22–R25, R67–R70).

  The PMEG turn-off diodes have no heat row in the c28 heat file, so they carry no term. The R_off branch's heat is
  in R_off.
- **FET-case tie:** tie_hs (Q2/Q5) and tie_ls (Q3/Q6) at t_rise = 1 K. The case coefficient is fet_case.t_case(ceiling)
  − bay. At c18, t_case is 92.86 / 92.91 °C (HS / LS); at c22 it is 94.68 / 94.72 °C. The sink sits at the fan's
  88.6 °C setpoint in both cases.
- **Bay air:** the bay temperature itself.
- **Mesh correction:** 3·|Q(0.25) − Q(0.5)|.

**How to read the tie term.** It is the board rise with the drain pads tied to a tab at t_case and no heat anywhere. The
heat terms are computed with that same lead conductance tied to bay temperature. In the full c18 case the drain pads
run 2.1–2.9 K above the tab (`gate-runs/c18_h10_p0p25.json` leads: 0.18–0.25 W per lead into the sink). So the leads
cool the board, but a hotter sink cools it less. The tie term is the price of the sink sitting at 92.9 °C rather than
at bay air.

Scaling class per term (from make_heat_sources.py / run_basis.py):
- **tank I²:** every A4 field except ac_l / ac_n, plus R5, R39, the bank and C5/C6;
- **line, fixed at 13.5 A:** ac_l_main, ac_n_main, L1;
- **frequency/charge-set:** R_on, R_off, drivers, RECOM, U26 and PS2. They sit at the 60 kHz window top on the deck
  gate charge and do not move with the ceiling;
- **fixed estimates:** HF film 0.05 W each, small LDOs, R22–R25 / R67–R70.

Groups: part groups follow `13-coupling/results/assignment.json`. Copper nets go to the group that owns a copper change
on that net; the full pad-group list is in `results.json`, from `11-candidates/GROUPS.md`.

| Net | Owner group | Groups with pads on it |
|---|---|---|
| sw_a | G03 | G03, G05, G06, G07, G09 |
| sw_b | G03 | G03, G04, G05, G06, G07 |
| leg_ret | G03 | G03, G05, G06, G07, G08 |
| bus_p | G03 | G02, G03, G08 |
| hv_ret | G08 | G02, G03, G08 (R5.4) |
| res_a / coil_feed | G04 | G04 (coil_feed also G09) |
| ac_l / ac_n | G01 | G01 |

## 3. Attribution, release case c18_h10, bay 61 °C (K at the row; rows by margin)

The "bay+tie" column includes the tie (shown in brackets). "Heat" is the sum of the heat terms. The share is the share
of the rise over bay.

| row | est °C | limit | margin | bay+tie (tie) | heat | mesh | top heat terms (K, share of rise over bay) |
|---|---|---|---|---|---|---|---|
| C40 body | 108.8 | 110.0 | +1.2 | 69.1 (+8.1) | 38.3 | 1.4 | R_on 5.2 (11 %); RECOM 4.9 (10 %); HF film 4.7 (10 %); sw_b_high 4.4 (9 %); sw_b_low 3.5 (7 %) |
| R10 terminal derating | 128.8 | 131.9 | +3.1 | 69.9 (+8.9) | 47.0 | 11.9 | R_on 19.3 (28 %); sw_a_low 5.3 (8 %); sw_b_high 3.8 (6 %); sw_b_low 3.6 (5 %); RECOM 1.9 (3 %) |
| C41 body | 106.2 | 110.0 | +3.8 | 69.9 (+8.9) | 35.3 | 1.0 | RECOM 5.9 (13 %); R_on 5.8 (13 %); HF film 4.8 (11 %); sw_b_high 4.2 (9 %); bus_mixed_q5 2.9 (6 %) |
| R20 terminal derating | 127.4 | 131.9 | +4.6 | 71.7 (+10.7) | 46.3 | 9.3 | R_on 19.6 (30 %); sw_b_high 4.9 (7 %); RECOM 3.6 (5 %); sw_b_low 3.3 (5 %); R5 2.8 (4 %) |
| C38 body | 105.0 | 110.0 | +5.0 | 68.0 (+7.0) | 36.2 | 0.9 | HF film 4.5 (10 %); sw_b_high 4.2 (10 %); R_on 4.0 (9 %); sw_b_low 3.8 (9 %); RECOM 3.4 (8 %) |
| laminate 1 mm block (45.5, 15.5 F.Cu, at R12) | 125.0 | 130.0 | +5.0 | 70.4 (+9.4) | 48.0 | 6.7 | R_on 13.7 (21 %); R5 5.8 (9 %); sw_b_high 4.5 (7 %); sw_b_low 3.9 (6 %); RECOM 3.1 (5 %) |
| U26 Tj | 119.1 | 125.0 | +5.9 | 61.4 (+0.4) | 46.3 | 11.4 | U26 37.7 (65 %); small LDOs 2.3 (4 %); sw_a_low 1.0 (2 %) |
| R12 terminal derating | 125.4 | 131.9 | +6.6 | 70.4 (+9.4) | 48.1 | 6.9 | R_on 14.0 (22 %); R5 5.8 (9 %); sw_b_high 4.5 (7 %); sw_b_low 3.9 (6 %) |
| laminate FET row | 122.1 | 130.0 | +7.9 | 70.6 (+9.6) | 47.0 | 4.4 | R_on 13.5 (22 %); R5 5.7 (9 %); sw_b_high 4.3 (7 %); sw_b_low 3.8 (6 %); leg_a 3.1 (5 %) |
| U42 Tj | 133.6 | 150.0 | +16.4 | 63.6 (+2.6) | 66.2 | 3.7 | RECOM 57.2 (79 %) |
| U41 Tj | 129.5 | 150.0 | +20.5 | 62.5 (+1.5) | 62.8 | 4.3 | RECOM 55.6 (81 %) |
| R10 element | 132.3 | 155.0 | +22.7 | 70.1 (+9.1) | 53.3 | 9.0 | R_on 25.8 (36 %); sw_a_low 5.4 (8 %) |
| R5 terminal derating | 118.3 | 161.1 | +42.7 | 70.5 (+9.5) | 45.1 | 2.7 | R5 7.7 (13 %); R_on 7.2 (13 %); sw_b_high 4.6 (8 %); sw_b_low 3.9; hv_mixed_a 3.5 |
| R5 element | 122.8 | 170.0 | +47.2 | 70.7 (+9.7) | 50.3 | 1.8 | R5 14.6 (24 %); R_on 7.2 (12 %); sw_b_high 4.4 (7 %) |

**By kind of change** (K at the row):

| | C40 | R10 term. | C41 | R20 term. | C38 | lam. block | U26 | R12 term. | FET row | U42 |
|---|---|---|---|---|---|---|---|---|---|---|
| bay air | 61.0 | 61.0 | 61.0 | 61.0 | 61.0 | 61.0 | 61.0 | 61.0 | 61.0 | 61.0 |
| copper loss, tank I² | 18.1 | 20.6 | 14.6 | 16.7 | 19.2 | 21.2 | 4.9 | 21.2 | 21.1 | 4.8 |
| part heat, frequency/charge-set | 12.4 | 23.6 | 13.8 | 25.5 | 10.0 | 19.5 | 38.5 | 19.7 | 19.0 | 59.7 |
| FET-case tie | 8.1 | 8.9 | 8.9 | 10.7 | 7.0 | 9.4 | 0.4 | 9.4 | 9.6 | 2.6 |
| part heat, fixed estimate | 4.8 | 1.1 | 4.9 | 1.2 | 4.7 | 1.2 | 2.4 | 1.2 | 1.2 | 1.1 |
| part heat, tank I² | 2.9 | 1.6 | 2.0 | 2.9 | 2.2 | 5.9 | 0.4 | 5.9 | 5.8 | 0.7 |
| mesh correction | 1.4 | 11.9 | 1.0 | 9.3 | 0.9 | 6.7 | 11.4 | 6.9 | 4.4 | 3.7 |

**By group:**

| | C40 | R10 term. | C41 | R20 term. | C38 | lam. block | U26 | R12 term. | FET row | U42 |
|---|---|---|---|---|---|---|---|---|---|---|
| G03 bridge (sw_a/sw_b/leg_ret/bus_p copper, HF film) | 19.1 | 19.4 | 17.1 | 15.0 | 20.6 | 18.0 | 3.7 | 18.0 | 18.3 | 4.5 |
| G05 gate drive (R_on, R_off, U1/U2) | 7.2 | 20.9 | 7.7 | 21.7 | 5.9 | 16.0 | 0.4 | 16.2 | 15.7 | 2.4 |
| G08 sense (R5, hv_ret copper) | 6.5 | 3.4 | 4.2 | 5.6 | 5.1 | 10.2 | 0.2 | 10.1 | 9.5 | 1.5 |
| G06 bias (RECOM, U26, PS2) | 5.2 | 2.7 | 6.1 | 3.8 | 4.1 | 3.5 | 38.1 | 3.5 | 3.3 | 57.2 |
| G03 sink tie | 8.1 | 8.9 | 8.9 | 10.7 | 7.0 | 9.4 | 0.4 | 9.4 | 9.6 | 2.6 |
| G01 / G02 / G04 / G07 / G09 (all together) | ≤ 0.3 | ≤ 0.4 | ≤ 0.2 | ≤ 0.2 | ≤ 0.4 | ≤ 0.3 | 3.6 | ≤ 0.3 | ≤ 0.3 | ≤ 0.6 |

The resonant bank, C5/C6, L1, PS2 and the ac copper are ≤ 0.35 K at every hot row (the bank 0.05–0.12 K). They sit
100–200 mm east, so bank ESR is not a lever for the ceiling.

## 4. Ratchet case c22_h10, bay 55 °C (the ranking at a raised ceiling)

| row | est °C | margin | bay+tie (tie) | heat | mesh | top heat terms |
|---|---|---|---|---|---|---|
| C40 body | 116.0 | −6.0 | 65.1 (+10.1) | 48.7 | 2.2 | sw_b_high 6.5; sw_b_low 5.2; R_on 5.2; RECOM 4.9; HF film 4.7 |
| laminate 1 mm block | 135.8 | −5.8 | 66.7 (+11.7) | 61.4 | 7.8 | R_on 13.7; R5 8.7; sw_b_high 6.7; sw_b_low 5.8; leg_a 3.9 |
| R12 terminal derating | 136.1 | −4.2 | 66.7 (+11.7) | 61.5 | 7.9 | R_on 14.0; R5 8.7; sw_b_high 6.7; sw_b_low 5.8; leg_a 4.0 |
| R10 terminal derating | 136.0 | −4.0 | 66.1 (+11.1) | 58.0 | 11.9 | R_on 19.3; sw_a_low 7.9; sw_b_high 5.7; sw_b_low 5.4 |
| laminate FET row | 132.6 | −2.6 | 67.0 (+12.0) | 60.3 | 5.3 | R_on 13.4; R5 8.6; sw_b_high 6.5; sw_b_low 5.7; leg_a 4.6 |
| C38 body | 112.2 | −2.2 | 63.7 (+8.7) | 46.8 | 1.7 | sw_b_high 6.3; sw_b_low 5.7; sw_a_low 4.7; HF film 4.5 |
| R20 terminal derating | 133.7 | −1.8 | 68.4 (+13.4) | 56.0 | 9.4 | R_on 19.6; sw_b_high 7.3; sw_b_low 4.9 |
| C41 body | 111.2 | −1.2 | 66.1 (+11.1) | 43.5 | 1.5 | sw_b_high 6.3; RECOM 5.9; R_on 5.8; HF film 4.8; bus_q5 4.3 |

At c22, tank copper is 27.0 K at C40 and 31.7 K at the laminate block, against 18.1 / 21.2 K at c18. So the ranking
moves toward copper as the ceiling rises:
- sw_b (both states) becomes C40's largest term, 11.7 K. Candidate 36 found 11.9 K on s38.
- R5 rises to 8.7 K at the block.

K gained per 10 % cut of one term at c22 / bay 55:

| term | W at c22 | C40 | lam. block | R12 term. | R10 term. | FET row | C38 |
|---|---|---|---|---|---|---|---|
| sw_b_high | 1.745 | 0.71 | 0.77 | 0.76 | 0.67 | 0.68 | 0.67 |
| R_on | 0.868 | 0.56 | 2.22 | 1.94 | 3.28 | 1.73 | 0.43 |
| sw_b_low | 1.704 | 0.56 | 0.65 | 0.65 | 0.63 | 0.59 | 0.62 |
| HF film | 0.200 | 0.50 | 0.14 | 0.14 | 0.11 | 0.11 | 0.47 |
| R5 | 0.534 | 0.46 | 1.04 | 1.00 | 0.23 | 0.96 | 0.33 |
| RECOM | 2.058 | 0.39 | 0.28 | 0.27 | 0.15 | 0.20 | 0.20 |
| hv_mixed_a | 0.413 | 0.38 | 0.50 | 0.49 | 0.22 | 0.33 | 0.32 |
| bus_mixed_q5 | 0.526 | 0.38 | 0.28 | 0.28 | 0.14 | 0.23 | 0.18 |
| sw_a_low | 1.698 | 0.26 | 0.33 | 0.34 | 0.63 | 0.41 | 0.51 |
| hv_mixed_b | 0.264 | 0.25 | 0.38 | 0.37 | 0.12 | 0.23 | 0.17 |
| leg_a | 0.372 | 0.20 | 0.26 | 0.27 | 0.23 | 0.52 | 0.26 |

## 5. Ranked levers, converted to ceiling amps

**Method.** The ceiling is found by bisection on the synthesized gate case:
- inputs at the ceiling: I_trip = 1.05 × ceiling, tank terms at I², t_case(ceiling), mesh term recomputed;
- each row's own derating limit recomputed (R5's terminal limit moves with its watts);
- the gate's own `evaluate()` run unrounded;
- the condition: every gated row ≥ 0.

**Control.** The I_trip² method (`c39-gate-network/scripts/ceilings.py`) applied to c22 / c28 synthesized at bay 61 °C
gives the same 18.44 A. DECISIONS 56 had 18.3 A on s42; s43's +0.5 K at the binding row accounts for the difference.
The direct solve and I_trip² agree because the binding row's margin is near-linear in I_trip² over 18–28 A.

**Which terms scale with the ceiling.** Tank-scaled terms shrink as the ceiling falls. Frequency-set terms (R_on, R_off,
drivers, RECOM, U26, PS2) and the fixed HF-film estimate do not. A watt removed from them is worth the same at any
ceiling, and is relatively more valuable at a low one: R10's terminal row is 23.6 K frequency-set against 20.6 K tank
copper at c18.

### 5a. One term cut 10 % (c18, bay 61 °C, base 18.44 A; exact, includes the mesh term)

| term | kind / group / scaling | W at c18 | ΔK C40 | ΔK R10 term. | ΔK lam. block | K/W at C40 | K/W at R10 | ceiling (gain) |
|---|---|---|---|---|---|---|---|---|
| R_on (R10/R12/R18/R20) | part heat / G05 / frequency-set | 0.868 | 0.56 | 3.18 | 1.86 | 5.9 | 22.2 | 18.65 (+0.21) |
| sw_b_high | copper sw_b / G03 / tank I² | 1.168 | 0.47 | 0.41 | 0.51 | 3.7 | 3.3 | 18.63 (+0.19) |
| HF film (C38–C41) | part heat / G03 / fixed estimate | 0.200 | 0.50 | 0.09 | 0.14 | 23.5 | 4.3 | 18.63 (+0.19) |
| sw_b_low | copper sw_b / G03 / tank I² | 1.140 | 0.37 | 0.38 | 0.44 | 3.1 | 3.2 | 18.59 (+0.15) |
| RECOM (U41/U42) | part heat / G06 / frequency-set | 2.058 | 0.39 | 0.12 | 0.28 | 2.4 | 0.9 | 18.58 (+0.14) |
| R5 | part heat / G08 / tank I² | 0.357 | 0.31 | 0.15 | 0.70 | 7.9 | 4.1 | 18.56 (+0.12) |
| sw_a_low | copper sw_a / G03 / tank I² | 1.137 | 0.17 | 0.50 | 0.22 | 1.5 | 4.7 | 18.51 (+0.07) |
| leg_a | copper leg_ret / G03 / tank I² | 0.249 | 0.13 | 0.19 | 0.17 | 5.4 | 7.0 | 18.49 (+0.05) |
| sw_a | copper sw_a / G03 / tank I² | 0.670 | 0.06 | 0.18 | 0.08 | 0.9 | 2.7 | 18.46 (+0.02) |

C40 stays the binding row after every single 10 % cut. R_on's ΔK at R10 (3.18 K) exceeds 10 % of its 19.3 K
contribution because R_on also drives most of R10's 11.9 K mesh term.

### 5b. Stated changes (ceilings at bay 61 / 55 °C; base 18.44 / 20.04 A)

| change | bay 61 (gain) | binding after | bay 55 (gain) |
|---|---|---|---|
| all tank copper −20 % (every tank-scaled A4 field) | 20.19 (+1.75) | C40 | 21.94 (+1.90) |
| R_on 0.17 W and sw_b −20 % | 19.61 (+1.17) | C40 | 21.24 (+1.20) |
| HF film self-heat 0 | 19.47 (+1.03) | R10 terminal | 20.90 (+0.86) |
| fan sink setpoint 88.6 → 78.6 °C | 19.36 (+0.92) | C40 | 20.90 (+0.86) |
| HF film self-heat halved | 19.31 (+0.87) | R10 terminal | 20.73 (+0.69) |
| sw_b copper −20 % | 19.14 (+0.70) | C40 | 20.81 (+0.77) |
| R5 0.5 mΩ (row × 0.5) | 19.07 (+0.63) | C40 | 20.73 (+0.69) |
| fan sink setpoint 88.6 → 83.6 °C | 18.91 (+0.47) | C40 | 20.48 (+0.44) |
| R_on 0.217 → 0.17 W | 18.89 (+0.45) | C40 | 20.46 (+0.42) |
| sw_b copper −10 % | 18.78 (+0.34) | C40 | 20.42 (+0.38) |
| hv_ret copper −20 % | 18.78 (+0.34) | C40 | 20.41 (+0.37) |
| RECOM −20 % | 18.73 (+0.29) | C40 | 20.31 (+0.27) |
| bus_p copper −20 % | 18.67 (+0.23) | C40 | 20.30 (+0.26) |
| sw_a copper −20 % | 18.63 (+0.19) | C40 | 20.25 (+0.21) |
| leg_ret −20 % / R_off −20 % | 18.56 (+0.12) | C40 | 20.18 / 20.16 |
| drivers −20 % / U26 −20 % / bank ESR −20 % | 18.48 / 18.45 / 18.45 (≤ +0.04) | C40 | ≤ +0.05 |

### 5c. What each lever means physically, and what a candidate would have to show

The cut sizes are this study's assumptions. The amps that follow from them are model outputs.

1. **Tank copper: sw_b first, then hv_ret, bus_p and sw_a (G03 / G08).**
   - sw_b (1.17 + 1.14 W at c18) gives 3.1–3.7 K/W at C40, R10 and the block. Each 10 % of sw_b is worth +0.34 A.
   - sw_b's influence on C40 is not local. Only 0.014 W of sw_b heat lands within 5 mm of C40 (all on B.Cu); at the
     laminate block it is 0.14 W, also all B.Cu. sw_b reaches C40 through general warming of the FET-row area.
   - So "move C40 off the sw_b lane" is not supported by the model as a large gain. What matters is sw_b's total
     B.Cu lane loss, and C40's pad copper temperature (pads on bus_p 24.2, 28.2 and hv_ret 39.2, 28.2).
   - On 2 oz outer copper, candidate 36 cut sw_b loss only 1.2 % and leg_a 15 %. Its 3 oz-outer what-if (×1.5 outer
     thickness) moved C40 by +6.7 K at c22. That is the order of the "all tank copper −20 %" line here (0.2 × 27.0 K
     = 5.4 K at C40 at c22; +1.75 A at bay 61), and it cannot be ordered (DECISIONS 53).
   - So 5–10 % of sw_b (+0.17–0.34 A) is the plausible 2 oz range, unless a second layer can carry sw_b in parallel.
   - A candidate must show the task-04 sw_b_high / sw_b_low loss_w drop and the C40 / R10 / block rows moving by
     about 0.84 / 0.79 / 0.95 K per 10 %.
2. **R_on heat (G05, frequency-set; not reduced by a lower ceiling).**
   - 0.868 W gives 22.2 K/W at R10 terminal, 13.7 K at the block and 5.2 K at C40.
   - The cheapest move is the measurement: the bench IR reading of 0.17 W against the 0.217 W bound is +0.45 A
     (DECISIONS 56).
   - Real cuts: a lower Q·f (the 60 kHz window top or the 4.7 nF Cgs adds 61 nC; both set by S4 / control decisions),
     or splitting each R_on across two 2512s. Splitting halves the per-part watts and raises the derating line
     (155 − 85·P / 0.8 W), but C40 would still bind first.
   - A candidate must show the R10 / R20 terminal and block rows, and C40, which gets 5.9 K/W from R_on.
3. **FET-case tie: the fan sink setpoint (firmware, G03 sink).**
   - The tie adds 8–11 K at the hot rows: 0.25–0.32 K per K of t_case (1 − d est/d bay in `results.json`
     bay_sensitivity).
   - Holding the sink 10 K cooler (FAN_SINK_SETPOINT_C 88.6 → 78.6 °C) gives +0.92 A.
   - fet_case's own R_SA basis puts the sink at 63.8 °C at c18 (50 + 0.29 × 47.7 W, at 13 CFM and a 50 °C inlet), so
     78.6 °C is inside the fan's authority on that basis.
   - Before taking it: check the fan's noise and life budget, and that fet_case's 50 °C sink inlet holds when the bay
     is 61 °C.
4. **HF film C38–C41 self-heat (G03): settle it before designing for it.**
   - 0.05 W per cap at an assumed 50 K/W lead path, with no body-to-air path, gives 4.5–4.8 K on each cap's own row.
   - The OPEN-ITEMS S2 (b) body-to-air path, or a measured ripple / ESR value, moves the binding row more than any
     2 oz layout change (up to +1.03 A, after which R10 binds).
   - The worst-case allocation (0.2 W) would cost about 14 K.
5. **RECOM U41/U42 (G06, frequency-set).**
   - 2.06 W, 33–45 mm away, still gives 4.9 K at C40 and 5.9 K at C41 (2.4 K/W at C40), through the inner planes.
   - −20 % (a measured efficiency above the 45 % allocation) is +0.29 A.
   - A layout candidate would have to cut the plane path between the HS-bias block and the film-cap row.
6. **R5 (G08, tank I²).**
   - 5.8 K at the block, 2.8 K at C40.
   - The 0.5 mΩ shunt is +0.63 A, but DECISIONS 53 rejected it (OCP pickup).
7. **Not levers here:**
   - the resonant bank, C5/C6, L1, PS2, U26 and the ac copper: each ≤ 0.04 A for a 20 % cut;
   - U26 (37.7 K of its own heat) and U41/U42 (about 80 % their own) are local problems with ceilings of 26.6 A and
     36.6 A / ≥ 40 A at bay 61 (40 A is the search cap). U26 moves almost only with the bay (0.99 K/K) and its own
     watts.

## 6. Surprises and cautions

- **Copper TCR is not in B3, and it is worth about −2 A.**
  - The A4 fields are DC at 20 °C (`outputs/*.json` "assumptions": "20 C copper; DC resistive spreading only").
    run_basis / thermal_body use them unscaled. The only TCR in the round-5 tree is in `stage15b/ref/neck_fin.py`
    and `r5-derating` (R5's alloy).
  - Heat-weighted copper temperatures on the c18 field: sw_b 96–98 °C, hv_ret 104–106 °C, leg 109–112 °C, sw_a
    90–96 °C, bus_p 99–102 °C, res_a / coil_feed 83–86 °C. With α = 0.00393 /K that is ×1.25–1.36 loss.
  - First order (one Picard step, no feedback, `analyze.py` "copper_tcr_first_order"): C40 +6.1 K, R10 terminal
    +6.5 K, laminate block +7.2 K, C41 +4.9 K, R20 +5.4 K. The bay-61 ceiling goes 18.44 → 16.42 A.
  - With feedback it is somewhat more. Current redistribution toward cooler copper makes it slightly less.
  - This is a new class of model gap. It wants a systemic fix: a hot-copper option in run_basis, iterating A4 loss ×
    (1 + α(T − 20)) to convergence, gated on the same rows. Until then, treat the +1.2 K release margin as not
    covering it.
- **No row is dominated by one heat source.** Bay air plus the tie is 68–72 K of the 105–129 °C binding rows. The heat
  part of C40 is spread over about ten terms. Layout levers are therefore worth tenths of an amp each.
- **What moves every row at once:**
  - bay air: 0.75 K/K at the hot rows, 0.27 A per K. A measured bay ≤ 55 °C is worth 1.6 A. DECISIONS 55's
    bay-sensor option is the biggest non-airflow lever;
  - the sink setpoint (the tie): ~0.09 A per K;
  - board-face airflow (h), which this linear fixed-h model cannot rank. The R10/R20/block rows carry 19.5–25.5 K of
    frequency-set heat that does not fall with the ceiling, so only h or the R_on watts move it.
- **The mesh correction is large on the gate-resistor and U26 rows.**
  - It is 11.9 K at R10's terminal, 9.3 K at R20 and 11.4 K at U26: bigger than any single heat term on those rows
    except their own.
  - It is not a design lever, but a refined-window solve (`b3-convergence` windows) that bounds |ΔQ| more tightly
    could free several K there. It is not the binding row today (C40's mesh term is 1.4 K).
- **The FET-case tie term is positive (+8–11 K) even though the leads remove heat** (0.18–0.25 W each in the c18 run).
  It measures the sink at 92.9 °C rather than at bay air.

## Rerun

```
sh run_all.sh          # SNAP=<snapshot root> to override; default ../snap-cb48
```
It runs three steps, each with at most 3 workers:
1. The snapshot's own `run_basis.py --cases c18_h10@61,c22_h10@55`, into `gate-runs/` (4 solves).
2. `solve_terms.py`: 30 terms × 2 pitches plus 2 full-case 0.5 mm field controls, cached per term in `cache/`. At
   0.25 mm each term took 9–13 min on the shared machine; the whole set took about 2 h.
3. `analyze.py`: synthesis, checks, attribution, ceilings, levers, about 5 min. It writes `results.json` and
   `tables.md`.

Imports come only from the snapshot (`solve_terms.env` asserts each module's path). The B3 fine-mask cache is written
under the snapshot's `b3-ratings/runs/cache`, as run_basis.py does. `cache/` (378 MB of float32 copper-sheet fields)
is gitignored; commit the scripts, `README.md`, `results.json`, `tables.md` and `gate-runs/*.json`.

## Limits

- **Fixed-h still-air model:** h 10 everywhere. Airflow levers cannot be ranked with these unit solves, because
  changing h changes the matrix.
- **Heat inputs are the gate's own:** c28 heat file rescaled, the HF film estimate and RECOM's 45 % allocation. Lever
  sizes in 5b and 5c are stated assumptions; the amps follow from them.
- **Locators are frozen per case.** Under a lever the max-type rows are re-located on the new synthesized field, but
  the per-term attribution tables use the base case's locator.
- **The copper TCR estimate is first order and outside the gate model**; it needs the coupled re-solve named above.
