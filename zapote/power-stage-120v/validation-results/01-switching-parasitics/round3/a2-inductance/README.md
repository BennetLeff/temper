# A2 — connected-copper inductance scenarios

**Verdict:** Complete *geometry-based heuristic scenarios* are available for a ROUND-3 B1 exploratory sweep. No FastHenry field result, 5% analytic solver validation, 10 MHz current-distribution result, or physical low/high bound is claimed. The qualified deck parameters remain `null` in [`outputs/loop_inductance_fallback_heuristic.json`](outputs/loop_inductance_fallback_heuristic.json). The B1 grid can use the explicitly named scenario values for sensitivity, but a stress pass against them cannot qualify the board.

- Board: `native-15/section.kicad_pcb`, SHA-256 `a3ac1249f5052afe52944804cdc3f6ef0e8f895668360e79c1fa7b6fb7322155`.
- Source revision: `44417ae1489fd00e2d652fd3b2c1582b76d17630`; 2026-09-27. Inputs are copied, byte-for-byte, from the prior native-15 Task 01 and Task 04 captures; their hashes are in the result JSON. Native board hash was rechecked against every input before calculation.
- Solver source: [official ediloren/FastHenry2](https://github.com/ediloren/FastHenry2), commit `363e43ed57ad3b9affa11cba5a86624fad0edaa9`, Git tree `86c4f4c441dcf600fb5f4a19e16dea8f3b764fc8`, `src/fasthenry/induct.c` SHA-256 `94eb918fd62c4c6e5db022608282ac32ba495952744a8f12c1888d1a967f75e6`. The source is unmodified.
- Runtime: Apple clang 21.0.0; KiCad 10.0.4 native exports; Miniforge Python 3.12, Shapely 2.1.2, SciPy 1.18.0.
- Evidence classes: exact native port/net/layer identity and hole-aware copper geometry; approximate connected-route geometry; heuristic magnetic scenarios; assumed C38–C41 ESL.

## Solver and analytic fixtures

Official source was fetched successfully with an escalated clone. `make fasthenry` failed on Apple's modern C compiler's rejection of implicit `int` and undeclared functions; [attempt-1 excerpt](outputs/fasthenry-build1.txt) preserves the reported failure. A second build using `-std=gnu89` and legacy warning flags still failed on non-void `return;` in `induct.c`; [attempt-2 full compiler log](outputs/fasthenry-build2.txt) is preserved. ROUND-3 A2 explicitly directs the fallback after two failed builds. No third build or local source patch was attempted.

[`scripts/test_fasthenry.py`](scripts/test_fasthenry.py) writes a 10 × 50 mm, 0.5 mm-spaced plane-pair deck and a 50 × 1 mm straight-wire deck at two subdivisions each. Its independent analytic references are **3.1416 nH loop** for the ideal plane pair and **42.9832 nH external partial self inductance** for a 50 mm, 0.5 mm-radius round wire. The wire's DC internal contribution is 2.5 nH; at 10 MHz, skin effect reduces that term, but no computed high-frequency internal value is claimed. The generated square-wire deck differs from the round analytic shape. [`outputs/analytic-fixtures.json`](outputs/analytic-fixtures.json) correctly records `UNRUN_NO_EXECUTABLE`, with both the 5% analytic comparison and electromagnetic mesh convergence `null`. No board value was tuned to match an analytic answer.

## Actual copper and route topology

[`scripts/trace_connected_copper.py`](scripts/trace_connected_copper.py) rasterizes KiCad-exported hole-aware copper, tracks, pads and vias. It traces each named same-net port pair through connected copper with plated through-hole/via layer transitions. Native KiCad exports give pad positions and pad polygons, so no independent `R(+theta)` calculation can invert KiCad's required `R(-theta)` placement. [`outputs/annotated_ports.json`](outputs/annotated_ports.json) identifies all 42 used ports; the full 0.25 mm and 0.5 mm route polylines and transitions are in [`outputs/connected_routes_0p25.json`](outputs/connected_routes_0p25.json) and [`outputs/connected_routes_0p5.json`](outputs/connected_routes_0p5.json). These paths witness connectivity and geometric length; the shortest path is not a 10 MHz current streamline.

| Route | Direct pad chord | Connected 0.25 mm route | Important topology |
| --- | ---: | ---: | --- |
| A Q2 source → Q3 drain | 23.45 mm | 30.53 mm | Through-hole barrels to B.Cu switch-node pour and back |
| B Q5 source → Q6 drain | 12.55 mm | 29.71 mm | Through-hole barrels to B.Cu switch-node pour and back |
| A Q3 source → R5.1 | 17.19 mm | 24.14 mm | In1/outer-layer transition |
| B Q6 source → R5.1 | 7.84 mm | 11.56 mm | In1/outer-layer transition |

The return routes from MOSFET sources to driver returns are Q2 47.42 mm, Q3 79.37 mm, Q5 42.57 mm and Q6 46.80 mm at 0.25 mm pitch. Q3's return did not connect at 0.5 mm but did at 0.25 mm, so its raster convergence is **unresolved**. Every other route's 0.5/0.25 mm length changed by less than 5% (largest 3.47%). This is **raster path convergence, not electromagnetic mesh convergence**. Plated-barrel vertical spans and their drill diameters are explicitly recorded in the scenario JSON. [`inputs/gate_vias.json`](inputs/gate_vias.json) adds KiCad-probed gate-output vias (two on Q3, 0.3 mm drill); parallel via current division and mutual inductance are not solved.

## Heuristic magnetic scenarios and B1 interface

[`scripts/summarize_routes.py`](scripts/summarize_routes.py) compares two magnetic *scenarios* on the connected routes. The reference-plane case applies `μ₀ h ℓ/(w+2h)` with adjacent-layer height derived from [`stackup.json`](../../../../stackup.json). The separated-pair case uses `μ₀ ℓ/π ln(D/r)`, with the nearest distance between two *selected connected route polylines* in three dimensions and `r = track-width/2`. It adds the runbook's cylindrical via term for each actual vertical transition. Gate scenarios include both exact outgoing track length and the connected source-to-driver-return route; their effective paired length is the longer route. Internal copper inductance, skin/proximity effects, via-bank sharing, current spreading in pours, component-lead geometry, and mutual coupling among consecutive path sections remain unresolved. The selected path is a shortest connected route, not a field-solved current distribution.

The two scenarios are sorted into `min`/`max` for a reproducible sensitivity sweep; those labels **do not mean physical lower/upper bounds**. Q3's raw reference-plane and separated-pair cases even reverse their nominal order. `LS_HS` and `LD_LS` each get half the same switch-node route for deck bookkeeping, not separately extracted partial inductances. `LCS` maps Q3/Q6 source → R5.1, and `LS_LS` maps R5.4 → the selected local-cap return. Each scenario keeps BUS_P and HV_RET on the *same* C38/C39 or C40/C41 capacitor branch. The Infineon L1 MOSFET model already includes package L; it is not added here.

| Leg | Board-copper min/max **scenario**, excluding capacitor ESL | Selected local cap (min/max) | Per-device gate `LG` min/max scenario |
| --- | ---: | --- | --- |
| A | 34.7 / 140.2 nH | C38 / C39 | Q2 16.9 / 23.1 nH; Q3 33.8 / 33.9 nH |
| B | 28.0 / 128.0 nH | C40 / C41 | Q5 15.7 / 38.4 nH; Q6 19.6 / 29.2 nH |

The upper board-copper scenarios exceed the runbook's 100 nH sanity trigger. Successive separated-pair terms share returns and may double-count inductance; they are deliberate stress inputs, **not measured loop inductance or a validated maximum**. The exact [TDK B32652A0104K000 product page](https://product.tdk.com/en/search/capacitor/film/snubbering_pfc/info?part_no=B32652A0104K000) lists electrical ratings and datasheet, but no exact-part SPICE/S-parameter model or numeric ESL. ROUND-3 authorizes C38–C41 `LCAP = 5–20 nH`, explicitly **ASSUMED**. `LBULK_copper_only` is routed C5/C6-to-local-cap copper (A 21.5–85.7 nH; B 61.1–257.1 nH); **bulk capacitor internal ESL is unresolved**. The exploratory `LBULK` field equals this copper-only value with the omitted capacitor ESL flagged in each case; it is not a complete physical `LBULK`. The starter deck has one `LG` knob; the JSON provides the two device-specific values to sweep separately.

B1 can read `deck_parameters_heuristic_scenario_nH` directly for a complete exploratory deck and must state that `LBULK` omits unknown bulk-capacitor internal ESL. Any peaks are model sensitivity. `qualified_deck_parameters_nH` remains all `null`. No physical stress acceptance follows from a favorable exploratory run.

## Reproduce and verify

From the repository root, using `/Users/bennet/Miniforge3/bin/python3` as `PY` and this directory as `R`:

```sh
P=zapote/power-stage-120v
R=$P/validation-results/01-switching-parasitics/round3/a2-inductance
PY=/Users/bennet/Miniforge3/bin/python3
KP=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3
$KP "$R/scripts/gate_via_probe.py" "$P/native-15/section.kicad_pcb" "$R/inputs/gate_vias.json"
$PY "$R/scripts/test_fasthenry.py" --out "$R/fixtures" --report "$R/outputs/analytic-fixtures.json"
$PY "$R/scripts/trace_connected_copper.py" --unit "$P" --inputs "$R/inputs" --output "$R/outputs/connected_routes_0p5.json" --pitch 0.5 > "$R/outputs/connected_routes_0p5.txt" 2>&1
$PY "$R/scripts/trace_connected_copper.py" --unit "$P" --inputs "$R/inputs" --output "$R/outputs/connected_routes_0p25.json" --pitch 0.25 > "$R/outputs/connected_routes_0p25.txt" 2>&1
$PY "$R/scripts/summarize_routes.py" --unit "$P" --inputs "$R/inputs" --outputs "$R/outputs"
$PY "$R/scripts/verify_inductance.py" --unit "$P" --inputs "$R/inputs" --outputs "$R/outputs"
```

[`outputs/verification.json`](outputs/verification.json) passes source, analytic-unit, route, port, scenario-order and explicit-uncertainty checks. It does not convert the unrun field-solver fixtures into a pass.
