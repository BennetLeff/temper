# B3 jet case and HF film-cap body-to-air path (2026-10-15)

OPEN-ITEMS S2, board side (a) and (b). Board s42 (9e075b4b), I_line 13.5 A, task-04 fields checked by `a4_fields.py`.

- **(a)** The temper-8d airflow-r1 jet case (`sensor-c1-impulse-mining:output/temper-airflow-r1/board_h_sweep.py`) is
  now a supported B3 case. Before, it was a monkeypatch of `tb.assemble` / `tb.build_network_parts`.
- **(b)** C38–C41 get a body-to-air path.

Both are in the model since eabef510a. This folder holds the jet sweep run on that model.

```
python3 scripts/jet_sweep.py solve --workers 3     # ~110 min on a shared machine; 56 solves -> ../runs/jet-2026-10-15/ (gitignored)
python3 scripts/jet_sweep.py solve-air15 --workers 3   # 28 A, bay 55 / 61, on the bay + 15 K cap-air default (16 solves)
python3 scripts/jet_sweep.py summary               # -> jet-sweep.json (committed)
```

## Current basis: cap air at bay + 15 K (supersedes the bay-air numbers further down)

**Why.** The cap-air addendum (end of this file, `cap-air.json`) showed the release gain rests partly on the caps seeing
bay air. They do not: they stand in the board's warm air layer, an estimated +8 to +12 K. So the film_hf default is now
`thermal_body.FILM_HF_AIR_RISE_K` = 15 K over the bay: that estimate's upper end plus 3 K of headroom.
- A cap credited by a TopRegion keeps the region's air, because the jet sweeps the board's warm layer away. No cap is
  inside `JET_REGION`, so under the jet the caps also see bay + 15 K.
- The sens key `film_air_rise` overrides the default, as does `run_basis --film-air-rise K`.
- `top_bound_c` and the air / energy bookkeeping use the cap's `t_air`. The BASIS balance closes to ≤ 7e-11.

**Controls.**
- `--film-lead-only` still reproduces the pre-2026-10-15 `margins.json` byte for byte (re-run).
- `margins.json` c18_h10 matches the cap-air +15 K sensitivity row for row, within 0.05 K. `test_b3_airflow.py` pins
  both this and the 15 K default.
- `air15` `c28_h10_jet10@55` matches `margins.json` c28_h10: 44 rows, 0.0 K.

**BASIS (s42), margin in K: lead-only → bay air → bay + 15 K (current `margins.json`)**

| Row | c18 bay 61 (release) | c22 bay 55 | c28 bay 55 |
|---|---|---|---|
| R10 2512 terminal derating | +0.7 → +5.2 → **+3.6** | −6.2 → −0.5 → −2.1 | −28.1 → −20.2 → −21.7 |
| R20 / R18 derating | +1.1 / +1.8 → +6.8 / +7.3 → +4.9 / +5.5 | −5.1 / −3.4 → +1.8 / +3.4 → −0.1 / +1.6 | −24.1 / −19.4 → −15.3 / −11.4 → −17.0 / −13.0 |
| R12 derating | +5.7 → +11.6 → +9.6 | −5.1 → +2.4 → +0.4 | −33.4 → −23.2 → −25.2 |
| Laminate block / FET row | +4.1 / +7.0 → +10.0 / +11.8 → +8.1 / +10.2 | −6.8 / −3.6 → +0.8 / +2.5 → −1.2 / +0.9 | −30.6 / −30.7 → −20.6 / −22.5 → −22.5 / −24.1 |
| C40 | +1.1 → +14.2 → +10.4 | −6.0 → +9.6 → +5.9 | −27.8 → −8.1 → −11.8 |
| C41 / C38 / C39 | +3.7 / +5.1 / +10.6 → … → +13.3 / +13.1 / +17.1 | −1.3 / −2.0 / +4.5 → … → +11.0 / +8.9 / +13.4 | −18.8 / −24.1 / −16.3 → … → −2.3 / −8.4 / −3.0 |
| U26 | +5.9 → +6.2 → +6.1 | +9.4 → +9.7 → +9.6 | +4.7 → +5.2 → +5.1 |
| R58 1206 derating | +11.1 → +16.9 → +15.0 | +1.8 → +9.3 → +7.3 | −25.4 → −15.2 → −17.2 |
| R5 terminal / element | +42.4 / +46.9 → … → +46.3 / +50.3 | +25.4 / +31.7 → … → +30.9 / +36.5 | −14.6 / −4.8 → … → −6.5 / +2.3 |

- **No gated row is below its lead-only value.**
- **Metrics:** release **+3.6 K** (R10, PASS); laminate ratchet −30.7 → −24.1 K; rated parts −33.4 → −25.2 K; advisory
  −7.7 → −7.3 K. The s42 card was re-scored and only these three card metrics move.
- **Still-air ceiling at bay 55** (`c39-gate-network/scripts/ceilings.py` on the new c22 / c28 pair): all gated rows
  **21.3 A** (R10), laminate 21.6 A, gate R_off 23.9 A. Before this change it was 20.0 A.

**Required h_top at 28 A (bay + 15 K cap air, `jet-sweep.json` → `air15`):**

| | bay + 15 K (current) | bay air (superseded) | airflow-r1 |
|---|---|---|---|
| 28 A, bay 55 | **45.1** | 42.5 | 73.2 |
| 28 A, bay 61 | **59.2** | 59.1 | 97.2 |

- Per-row zeros at 28 A, bay 61: laminate block 54.4, C40 54.1, laminate FET row 53.8, R12 52.1.
- The 59.2 is the chord to U26's +0.3 K at h 60. U26 is outside the jet and the jet does not move it.
- At bay 55: laminate block 43.6, R12 42.6.
- Not re-solved on this basis: the 26 A rows and the ceiling-vs-h table. A full re-sweep would take more than 45 min at
  3 workers on the shared machine. Below they are marked as the bay-air basis.
- `capjet` is unaffected: it credits all four caps to the jet region, whose air is the bay.

## (a) The airflow case

- **Code:** `thermal_body.TopRegion`, `body_runs.run_case(region=)`, `run_basis.py --cases c<ceil>_h<h>_jet<h_top>[a<air C>]@<bay>`.
- **Region:** `run_basis.JET_REGION`, x 0–90, y 7.0–23.5 mm, inclusive.
  - It is defined once. It is airflow-r1's `REGIONS["channel"]`, the strip under its jet box.
  - The test checks that `gates/jet_strip_height.py` REGION contains it. Today the two are equal.
- **What the region changes:**
  - Top-face (F.Cu) cells with centres in the region convect at h_top. The air is at `a<air C>`, or at the bay if that is
    not given.
  - Package networks whose heat-row centre is in the region take body-to-air at h_top, to the same air. On s42 these
    are R5, R10/R12/R18/R20 and R53/R54/R57/R58.
  - Every other cell, and the whole bottom face, stays at h 10.
- **Run files** record `region`: xy, h_top, air °C, the credited bodies, the region area and the region convection.
- **Gate:** `b3_ratings_gate` labels these cases role `airflow`.
  - It refuses them as release cases.
  - It keeps them out of the ratchet metrics.
  - It checks that each run file's region matches the case name.
  - It refuses one case at two bays, because the run files would collide.
- **BASIS is unchanged:** c18 at bay 61, c22 / c28 at bay 55, still air.
- **Controls:**
  - With no region and `--film-lead-only`, the re-solved BASIS reproduces the old `margins.json` byte for byte.
  - A region at h_top 10 equals still air: `c28_h10_jet10@55` against the new `margins.json` c28_h10 gives 44 rows,
    0.0 K.
  - `test_b3_airflow.py` checks that the solution is bit-identical with h_top = h, and that energy balance is 1e-11 with
    a region.

## (b) C38–C41 body-to-air (`thermal_body.film_hf`, `film_body_g_air`, `FILM_HF_STRONG`)

**Physics.**
- The body is TDK's plastic box with epoxy fill, 9.0 × 17.5 × 18.0 mm. Sources, all TDK B3265*A/G/J/T, June 2026
  (sha256 c32e3754787fa19b…):
  - p.14 ordering table, B32652A0104, maximum dimensions w × h × l;
  - p.2 construction;
  - p.3 drawing A1: leads d1 0.8 mm, e 15 mm.
- Its surface loses heat to the bay air. TDK's own self-heating terms are the heat transfer coefficient and the
  "capacitor surface area" (p.77).
- Heat that comes up the leads enters at the sprayed end contacts (the l-ends). It must then run along the winding to
  reach the sides.
- **Model:** each half-body is a fin from its end face: length l/2, k 0.2 W/mK (ASSUMED, the low end for PP / epoxy / PBT),
  exposed perimeter top + two sides. The end face itself is added at full h. The bottom faces the board and gets nothing.
  - g_air at h 10 is 0.0090 W/K, 81 % of h·A (A = 1107 mm²).
  - At h 100 it is 50 % of h·A.
- h is the local h:
  - 10 in still air;
  - the region's h_top only for a body centred in the region.

  C38–C41 are centred at y 28.2, outside it, so under the jet their bodies stay at h 10. The `capjet` sensitivity below
  credits them at h_top.

**Why lead-only was an upper bound.** With the body reached only through its leads, the body node has no other exit.
It settles at the lead-weighted pad temperature plus P × 50 K/W. That is the hottest a body heated from its leads can be.

Two caveats:
- It bounded the lumped node, not the hotter end. It averaged the two pads, which differ by up to 2 K at c28.
- It also bounded the board badly: it gave the board no credit for the heat the four caps carry away. In the new solve
  that is 0.85 W at c18 and 1.46 W at c28, through the 50 K/W leads.

**Why the new path is still conservative.** The tie between body and board decides both results, and the two row kinds
need opposite ends of it:
- **Board rows (laminate, gate R, R5) need a weak tie.** The solve keeps the assumed 50 K/W lead path: 3 mm of
  copper-clad steel at k 60, a value carried over from film_radial. The board's own 3D model seats the body 0.62 mm above
  the board, and copper leads would be stiffer still. Either way, a stronger tie only takes more heat off the board.
- **The cap's own Top row needs a strong tie.** It is gated on `top_bound_c`: the body tied to its **hotter** pad through
  copper leads (k 390) over the 0.62 mm seat, plus air conduction across the gap under the bottom face. That tie is
  0.64 W/K, 71 × g_air. So the row sits within about 0.5 K of the hotter pad, and the pads come from the weak-tie solve,
  which leaves them hotter.

  Where the weak-tie body node is a bigger number than this bound, the row uses the node. The weak node alone would read
  +23.6 K at c18 C40. The bound reads +14.2 K.
- **h 10 is still-air natural convection.**
  - Vertical 17.5 mm sides at ΔT 30–40 K: about 9–10 W/m²K.
  - Top face: about 13–14 W/m²K.
  - End faces in the 3.8 mm gaps between neighbouring caps: about 6 W/m²K (Elenbaas).
  - Applied per face, this gives g_air about 16 % below the uniform h-10 value for C38 / C40, which have both ends in
    gaps. That would take back roughly 0.5 K of the release-row gain.
  - Radiation is not credited at all. ε ≈ 0.9 at ~85 °C is about 9 W/m²K on the outward faces, roughly as large as the
    convection.
- **TDK's own rating implies more conductance.** The p.14 rating (5.4 A, ESR typ 14.0 mΩ, self-heating ≤ 20 K) implies
  ≥ 0.020 W/K from body to ambient. The model uses 0.009.
- **No credit is taken for the bottom face, the leads' own surface, or air cooler than the bay.**
- **Board-heated air, now covered:** the air at the lower part of the body is warmer than the bay. Since
  `FILM_HF_AIR_RISE_K` the caps convect to bay + 15 K (see "Current basis" above).

## Results

### Still-air BASIS, lead-only → with (b) at bay air (superseded by the bay + 15 K table above)

| Row | c18 bay 61 (release) | c22 bay 55 | c28 bay 55 |
|---|---|---|---|
| R10 2512 terminal derating | +0.7 → **+5.2** | −6.2 → −0.5 | −28.1 → −20.2 |
| R12 2512 terminal derating | +5.7 → +11.6 | −5.1 → +2.4 | −33.4 → −23.2 |
| R18 / R20 terminal derating | +1.8 / +1.1 → +7.3 / +6.8 | −3.4 / −5.1 → +3.4 / +1.8 | −19.4 / −24.1 → −11.4 / −15.3 |
| Laminate 1 mm block | +4.1 → +10.0 | −6.8 → +0.8 | −30.6 → −20.6 |
| Laminate FET row | +7.0 → +11.8 | −3.6 → +2.5 | −30.7 → −22.5 |
| C40 | +1.1 → +14.2 | −6.0 → +9.6 | −27.8 → −8.1 |
| C41 / C38 / C39 | +3.7 / +5.1 / +10.6 → +16.6 / +15.9 / +19.8 | −1.3 / −2.0 / +4.5 → +14.7 / +12.4 / +16.7 | −18.8 / −24.1 / −16.3 → +1.4 / −4.8 / +0.2 |
| U26 | +5.9 → +6.2 | +9.4 → +9.7 | +4.7 → +5.2 |
| R58 1206 terminal derating | +11.1 → +16.9 | +1.8 → +9.3 | −25.4 → −15.2 |
| R5 terminal / element | +42.4 / +46.9 → +48.2 / +52.0 | +25.4 / +31.7 → +32.8 / +38.2 | −14.6 / −4.8 → −4.6 / +4.0 |

- **Every gated row moves up; none gets worse.**
- **Metrics:** release 0.7 → 5.2 K (R10), laminate ratchet −30.7 → −22.5 K, rated parts −33.4 → −23.2 K, advisory
  −7.7 → −7.2 K (C21).
- **Still-air ceiling at bay 55** (c36 `ceilings.py`, c22 / c28): all gated rows 20.0 → 21.8 A (R10). Laminate
  20.0 → 22.3 A.
- **Bay 61 from this sweep's c26 / c28 pair:** 20.1 A. The pair is 27.3 / 29.4 A trips, so 20 A is an extrapolation; it
  is not a direct solve. The release ceiling stays 18.0 A (DECISIONS 55 / 56) until the owner decides otherwise.

### Required h_top (smallest h with every gated row ≥ 0, W/m²K): bay-air basis, superseded at 28 A by `air15` (above)

| | This study (b, caps at h 10) | capjet (caps at h_top) | airflow-r1 (lead-only caps, 11.1 A) |
|---|---|---|---|
| 26 A, bay 55 | 29.0 | 26.2 | 52.9 |
| 26 A, bay 61 | 41.2 | 33.0 | 82.1 |
| 28 A, bay 55 | 42.5 | 34.2 | 73.2 |
| 28 A, bay 61 | **59.1** | 57.4 | 97.2 |

- **Method:** a chord between grid points (10 / 35 / 60 / 100). Margin is concave in h, so the chord over-estimates the
  required h.
- **The limiting rows move.** In airflow-r1, C40 then C38 set every point. Here the R12 2512 terminal derating and the
  laminate set it.
  - At 28 A, bay 61, the per-row zeros are: laminate block 52.3, laminate FET row 50.9, R12 49.5, C40 41.8.
  - The 59.1 is the chord from R12 −7.7 K at h 35 to **U26 +0.3 K** at h 60.
- **U26 is outside the region and airflow does not reach it:** +0.3 K at h 60 and +0.8 K at h 100 (28 A, bay 61). At
  bay 61, U26 is the next limiter above about h 55 (OPEN-ITEMS S2 (d)).

### Ceiling vs h_top (c36 I_trip² method on the c26 / c28 pair, A, all gated rows): bay-air basis, superseded at 28 A by `air15`

| h_top | 10 | 35 | 60 | 100 |
|---|---|---|---|---|
| Bay 55 °C | 21.8 (R10) | 27.3 (R12) | 29.8 (laminate FET row) | 32.1 (laminate FET row) |
| Bay 61 °C | 20.1 (R10) | 25.8 (R12) | 28.4 (U26) | 29.0 (U26) |
| airflow-r1, bay 55 | 19.9 | 23.9 | 26.9 | 30.5 |
| airflow-r1, bay 61 | 18.2 | 22.2 | 25.0 | 28.5 |

- Above 28 A the table is extrapolated, and the 28 A Kconfig cap applies.
- Below 26 A it is extrapolated along the same line. At h 10 it reproduces the c22 / c28 interpolation at bay 55
  (21.8 A).
- capjet adds 0.2–1.0 A (`jet-sweep.json` → `capjet`).

## Open and not done

- **The cap rows depend on the seat and lead metal.** The bound uses the board's own 3D model, and the TDK drawing A1
  dimensions were not readable as text. A thermocouple on C40 in the S2 soak settles it.
- **Jet h is still airflow-r1's correlation estimate.** No ceiling raise until the bench measures it (S2).
- **The datasheet ledger cites `margins.json` by line and value** (34 citations: C40 108.9 / 116.0 / 137.8 °C, R10 /
  R12, U42, L1, C5, C21, R22, R5). The rows moved and were re-sorted. The values live in `seed_ledger.py`; they need
  that owner's refresh. Its gate still passes, because it checks only that the cited line numbers exist.

## Addendum: cap air warmer than the bay (`cap-air.json`)

**Question.** How much of the release gain rests on C38–C41 seeing bay air?

**Setup.** A `TopRegion` of zero board area: xy −1000..−999, h_top 10, `credit_refs` C38–C41, air at bay + ΔT.
- Only the four cap bodies see the warmer air; no board cell moves (asserted: `region_cells_top` 0).
- Solved as `run_basis.one`, at 0.25 / 0.5 mm.
- The driver is embedded in the json (`script`). Runs are in `../runs/cap-air/`, not committed.

**Results** (margins in K; "lead-only" is the floor from `--film-lead-only`):

| Case | Verdict | R10 / R20 / R12 derating | C40 / C38 top_bound | Laminate block / FET row | Heat out via caps |
|---|---|---|---|---|---|
| c18 @ 61, lead-only (floor) | PASS +0.7 | +0.7 / +1.1 / +5.7 | +1.1 / +5.1 (node) | +4.1 / +7.0 | 0 |
| c18 @ 61, cap air +0 K (`margins.json`) | PASS +5.2 | +5.2 / +6.8 / +11.6 | +14.2 / +15.9 | +10.0 / +11.8 | 0.85 W |
| c18 @ 61, +5 K | PASS +4.7 | +4.7 / +6.1 / +10.9 | +12.9 / +15.0 | +9.4 / +11.2 | 0.75 W |
| c18 @ 61, +10 K | PASS +4.1 | +4.1 / +5.5 / +10.3 | +11.7 / +14.0 | +8.7 / +10.7 | 0.65 W |
| c18 @ 61, +15 K | PASS +3.6 | +3.6 / +4.9 / +9.6 | +10.4 / +13.1 | +8.1 / +10.2 | 0.55 W |
| c22 @ 55, lead-only (floor) | FAIL −6.8 | −6.2 / −5.1 / −5.1 | −6.0 / −2.0 (node) | −6.8 / −3.6 | 0 |
| c22 @ 55, +0 K | FAIL −0.5 | −0.5 / +1.8 / +2.4 | +9.6 / +12.4 | +0.8 / +2.5 | 1.07 W |
| c22 @ 55, +10 K | FAIL −1.5 | −1.5 / +0.5 / +1.1 | +7.1 / +10.1 | −0.5 / +1.5 | 0.88 W |

**What the sweep shows.**
- The release margin is linear in the cap-air rise: about −0.11 K per K.
- The heat the caps carry falls about 0.02 W per K, reaching 0 near +42 K.
- At about +42 K the cap air is at the pad temperature. There the margin is back at the lead-only +0.7 K, and the caps
  carry no heat.

**Estimate of the real rise: about +8 to +12 K.**
- **Board-side air layer.** The board is a large, heated, upward-facing plate.
  - Incropera & DeWitt, *Fundamentals of Heat and Mass Transfer* §9.6: upper surface of a heated horizontal plate,
    Nu = 0.54 Ra_L^1/4 with L = A/P.
  - For the 290 × 190 mm board (L ≈ 57 mm) at ΔT ≈ 40 K: Ra ≈ 3.5e5, so h ≈ 6.5 W/m²K.
  - That gives a conduction-equivalent thermal-layer thickness δ = k/h ≈ 4.3 mm.
- **Averaging over the cap.** Take an exponential profile, T − T_bay = ΔT_b·exp(−z/δ), over the 17.5 mm side and end
  faces. Their mean air excess is 0.24 ΔT_b. The top face is at 17.5 mm and sees about bay air.
- **At the release case.** The board under the caps is at about 98 °C. That is C40's hotter pad, 87.1 °C in the
  model's 50 °C frame plus the 11 K bay shift. With the bay at 61 °C, ΔT_b ≈ 37 K, so the cap air is about +9 K.
- **Upper end.** Air rising from the 110–120 °C channel next to the caps' inner faces pushes the estimate toward +12 K.
- **For a 110 °C board top at bay 61:** 0.24 × 49 ≈ +12 K.
- **Not credited, and it works the other way:** the same rising air speeds up the flow past the faces, which raises h.

**Answers.**
- At +10 K the release margin is +4.1 K and the gate PASSes.
- The margin falls back to the old +0.7 K only when the cap air is about +42 K over the bay, that is, at pad temperature.
- c22 @ 55 stays a FAIL: −0.5 → −1.5 K at +10 K (R10).
