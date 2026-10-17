# 01 R5-D1 native-17 commutation and gate-loop extraction — blocked result

- Board: `native-17/section.kicad_pcb`, SHA-256 `16e8b70bb7f2bc9020ea574022c13661cd09640ca3a52db1ff43f9f6db976162`
- Date: 2026-09-28; checkout HEAD `91888bb29e318eef09c0a292245de88b9016d250`; KiCad 10.0.4; Miniforge Python 3; FastHenry2 source `363e43ed57ad3b9affa11cba5a86624fad0edaa9`, binary SHA-256 `79c7faac90f8aeb2ac5d805b66f2e4dd70baf3988af0fe3444e3d1fcf83184a4`; agent operator
- Evidence class: exact structural native-copper export and port identity; model-based analytic solver fixtures; **unqualified** raster-mesh feasibility diagnostics
- Verdict: **BLOCKED — extraction software and port contract**. No board R+jωL matrix, `spice_coupled.inc`, or converged loop-total fallback is accepted.

## Summary

The native-17 FlashLayer export passed its PTH outer-land check and contains the power and gate nets needed for both legs. The corrected-conductivity FastHenry wire and plane fixtures pass. A 0.25 mm candidate raster at the smallest required crop still has 341 leg-A and 550 leg-B centerline-valid links whose 20 µm-wide elements would leave native copper; simply removing them fragments connected native polygons. At 0.125 mm those counts rise to 1,351 and 1,673. These are **meshing artifacts, not evidence of missing physical copper or a board defect**. No deck was solved because its geometry would violate the no-omitted-link acceptance rule. The same geometry gap blocks the planned commutation/gate loop-total fallback.

## Method and assumptions

- `export_native17.py` imports the unchanged `tools/export_power_copper.py` (SHA-256 `b9d8543c37aaa218ab068a82f089a36bc69311d24f162201596b4947b8f29c61`), extends its net list with the eight explicit high/low gate drive nets, then calls its `export()` function. It adds the native PTH/via barrel catalogue and reads every named endpoint from pcbnew. The generated ignored export is `extraction/native17-power-and-gates.json.gz`, SHA-256 `d7d9783859bf20932c4e2355e96924e408f4b3ebc427506b8b4f9f2558fb2a8a`. It has 803 planar primitives, 147 physical barrels, and 134 suppressed pad/layer combinations. `export-summary.json` and `port-map.json` pin the identities.
- This native-17 export enforces both outer lands on every exported PTH pad. `check_missing_land_negative.py` independently runs the approved exporter on native-15 and confirms its expected rejection at `PS2.1` (`native15-negative-control.json`). The earlier native-15 D1 export admitted suppressed outer rings; its Q3.1/In1 nominal overlap was not a physical short. Neither historical shape nor a raw `IsOnLayer()` ring is substituted for this board's flashed copper.
- `run_physical_fixtures.py` pins the FastHenry binary and source and corrects `.units mm` to `sigma=5.8e4` S/mm, corresponding to an **assumed** copper conductivity of 5.8×10⁷ S/m. The plane fixture uses 61 µm copper. These calibrate dimensions; they do not qualify a native-board matrix. No board copper thickness or 18 µm barrel-plating estimate entered a solved board deck.
- `characterize_geometry.py` unions the actual exported shapes by net/layer and subtracts every physical drill bore from the final planar union. It tests all four specified port-pad bounding-box margins (5, 10, 20, 40 mm). Counts beyond M=5 are area-based allocation estimates, not emitted node counts or convergence solves.
- `audit_candidate_links.py` samples an orthogonal grid and tests every adjacent candidate's centerline, 20 µm-wide rectangle and pitch-wide rectangle against the native union. It compares connected components before and after the 20 µm filter. The diagnostic grid is not a contained no-drop mesh: a different node placement or native-conforming route may connect the same copper without the failing candidate edge. Narrowing an element alone also does **not** prove an upper bound on coupled self/mutual inductance or on the derived switching behavior.
- The board has two local capacitors and both high/low gate loops per leg. `port-map.json` preserves 12 signed *copper branches* per leg, each mapped to actual pad refs, XY, net, and flashed layers. For leg A: BUS_P C38.1/C39.1→Q2.2; switch Q2.3→Q3.2; source Q3.3→R5.1; return R5.4→C38.2/C39.2; high gate U1.15→R10.1, R10.2→Q2.1, Q2.3→U1.14; low gate U1.10→R12.1, R12.2→Q3.1, Q3.3→U1.9. Leg B uses C40/C41, Q5/Q6, U2, R18/R20, and the same R5. The gate resistor is an external component between two different nets; the MOSFET package and drivers are also external. No copper-only `.external` may silently short these devices.
- A six-port matrix with only one gate-drive/return pair per leg omits the other gate loop. Combining each capacitor pair into one port also requires a stated excitation/current-sharing convention. The coordinator has requested the owner's port choice; an eight-port per-leg interpretation (four power plus high and low gate-drive/return pairs) is a possible contract, but **not yet approved or implemented**. This independent port-definition gap remains even if meshing is repaired.

## Results

| Check | Leg A | Leg B | Trace |
| --- | ---: | ---: | --- |
| Corrected 50 mm × 1 mm² wire resistance | 0.000862069 Ω; analytic 0.00086206897 Ω | same fixture | `fixture-results.json` and ignored `extraction/fixtures/` |
| Corrected 50 × 10 mm two-plate fixture at 10 MHz | 20/40/80 subdivisions: 2.750707/2.947884/3.080333 nH; 40→80 change 4.493%; fine-grid R 0.00356669 Ω exceeds 0.00282646 Ω DC floor | same fixture | `fixture-results.json` |
| M=5, 0.5 mm candidate grid | 16,231 occupied nodes; 64 centerline-valid links fail 20 µm containment | not run | `link-audit-a-m5-p0p5.json` |
| M=5, 0.25 mm candidate grid | 64,261 occupied nodes, 123,666 adjacent candidates; 341 centerline-valid links fail 20 µm containment | 54,301 nodes, 102,776 candidates; 550 fail | `link-audit-*-m5-p0p25.json` |
| M=5, 0.125 mm candidate grid | 256,560 nodes, 503,353 candidates; 1,351 fail | 216,421 nodes, 421,070 candidates; 1,673 fail | `link-audit-*-m5-p0p125.json` |
| Exact native shape versus 0.25 mm/20 µm grid topology | BUS_P/In2.Cu: 1 polygon versus 18 grid components; SW_A/F.Cu: 1 versus 17 | BUS_P/In2.Cu: 1 versus 8; SW_B/B.Cu: 1 versus 14 | same link audits |
| Pad-bbox crop | (125.865, 4.215, 164.6, 41.125) mm | (88.4, 4.215, 127.135, 41.125) mm | `geometry-characterization.json` |
| Estimated occupied nodes at M=40, 0.125 / 0.0625 mm | 488,072 / 1,952,288 | 554,940 / 2,219,759 | `geometry-characterization.json` |

At M=5, the native ROI boundary cuts 6 leg-A and 10 leg-B net/layers. At M=40 it still cuts 9 and 8, including BUS_P/In2.Cu and HV_RET/In1.Cu on both legs. `geometry-characterization.json` names every cut side and length. An open, port-free boundary has **not** been generated or checked, and these counts are not crop convergence evidence.

`branch-connectivity.json` compares each signed branch's two pads only within a single raster layer. Several power and gate-return branches have no such planar connection, because a valid route may cross a plated barrel; this partial check cannot establish or reject full 3-D connectivity. A native-contained barrel, spoke and terminal landing audit remains required. The fixture raw inputs, logs and `Zc.mat` outputs are retained under ignored `extraction/` and pinned by `raw-manifest.json`.

There are **no** 1/10/30 MHz native-board solves, crop or two-pitch/`nhinc` convergence tables, reciprocal/PSD/passive R/L matrix, or SPICE L/K include. Package inductance and the separate 5–20 nH local-capacitor ESL assumption must remain outside any later copper matrix.

## Sensitivity

The link failures increase with a finer grid because more boundary-adjacent candidate edges are sampled; that trend cannot be interpreted as a physical inductance trend. Coarsening to 0.5 mm reduces the leg-A candidate count, but still creates extra grid components and misses a same-layer high-side return connection. A native-conforming, locally adaptive mesh must place or route elements within the actual copper, keep every physically connected pathway, prove every finite-width element and barrel spoke contained, and then pass the specified four-margin and two-pitch/`nhinc=1,3` matrix convergence checks. The 0.25 mm candidate allocation is tractable enough to prototype that mesher before any expensive solver run; repeating the 0.125/0.0625 mm full raster without this repair would repeat the known failure.

## Open items and the physical test that confirms this result

1. Set the per-leg port contract, including both high and low gate loops, capacitor-pair excitation, gate-resistor placement, and signed current references. Preserve the twelve native branches as the copper truth until a documented circuit reduction is chosen.
2. Build and independently audit a native-conforming mesh with no lost physical connection, 20 µm minimum emitted width, flashed pad and plated-barrel landings, and explicit crop boundary treatment. Rerun the wire/plate fixtures first if the solver or deck method changes. Solve only after this gate passes. Then perform M=5/10/20/40 sensitivity, two in-plane pitches at least 2× apart, `nhinc=1,3`, and the 1/10/30 MHz matrix checks. If full matrices do not converge within a measured memory budget, try the permitted commutation and **both** gate loop totals plus mutuals on the same qualified geometry. That fallback was **not** attempted here because its geometry acceptance is the same blocker.
3. The model ultimately requires simultaneous VDS, VGS, device-current and local bus measurements on prototype hardware during controlled low-voltage double-pulse bring-up. No software result here approves a gate-drive or board change.

The cheapest immediate step is a small native-conforming link-and-barrel mesher for M=5 at 0.25 mm, with an exact containment/topology report and real pad endpoints. It should fail closed before running FastHenry; only after passing should it be extended to the specified crop and thickness studies. Downstream R5-D2/C1/C2 cannot use this packet as a board-inductance input.

## Verify the retained packet

The 18 raw files (including five pre-cleanup source/manifest/README snapshots) are **local and ignored**, as ROUND-5 requires. They are not in either the round-3 or round-4 release. A clean checkout cannot verify this historical manifest without that handback, and rerunning the diagnostics does not recreate the source snapshots or necessarily identical solver logs.

The authoritative local handback is in the coordinator checkout below. From a separate checkout on this host, copy without replacing any existing file, then verify all raw/source/report and binary hashes:

```sh
D1=zapote/power-stage-120v/validation-results/01-switching-parasitics/round5/d1-extraction
RAW_SOURCE=/Users/bennet/.codex/worktrees/ps-r4-integration/temper
FASTHENRY=/tmp/ps-r3-decision.5sy79t/fieldsolver/FastHenry2/bin/fasthenry
PY=/Users/bennet/Miniforge3/bin/python3
mkdir -p "$D1/extraction"
rsync -a --ignore-existing "$RAW_SOURCE/$D1/extraction/" "$D1/extraction/"
"$PY" "$D1/write_raw_manifest.py" --verify --solver "$FASTHENRY"
```

Existing mismatches are not overwritten by this copy; the verifier rejects them. On another host, obtain this exact `extraction/` tree from the coordinator before verifying. No publicly downloadable round-5 raw archive is claimed. The verifier accepts an explicit `--solver` path or `FASTHENRY` environment variable. Relocating the identical binary is allowed; a different binary still fails the recorded SHA-256 identity and requires a new, qualified run.

## Run new diagnostics

Use a separate checkout/output copy so the retained historical evidence remains untouched. These commands execute the measurements again; they do **not** promise byte-identical raw logs or verification against the historical manifest. Compare numerical results and classify the new evidence before recording its own manifest; never rewrite the historical manifest merely to make verification pass.

```sh
D1=zapote/power-stage-120v/validation-results/01-switching-parasitics/round5/d1-extraction
FASTHENRY=/path/to/qualified/fasthenry
KIPY=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3
PY=/Users/bennet/Miniforge3/bin/python3
"$PY" "$D1/run_physical_fixtures.py" --solver "$FASTHENRY"
"$KIPY" "$D1/export_native17.py"
"$KIPY" "$D1/check_missing_land_negative.py"
"$PY" "$D1/characterize_geometry.py"
"$PY" "$D1/audit_candidate_links.py" --leg A --pitch 0.5 --margin 5
for leg in A B; do for pitch in 0.25 0.125; do
  "$PY" "$D1/audit_candidate_links.py" --leg "$leg" --pitch "$pitch" --margin 5
done; done
"$PY" "$D1/analyze_branch_connectivity.py"
```

No command creates an accepted native-board matrix or include. The original manifest, verifier and README are preserved under ignored `extraction/source-before-review/`; the verifier-path fix did not rerun or alter the physical diagnostics. These are one-off diagnostics under master §2.7. Any future permanent mesh-acceptance rule must be implemented and independently verified in Rust rather than promoting this Python diagnostic into the permanent suite.
