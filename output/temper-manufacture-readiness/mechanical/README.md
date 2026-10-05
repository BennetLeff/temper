# R4 / native-18 packaging envelope study

**SPACE STUDY ONLY — NOT AN INTEGRATED PCB ASSEMBLY, CUT FILE OR MANUFACTURING RELEASE.**

The valid STEP files show retained R4 geometry with clearly named orange boxes. These boxes are body allocations, not purchased component geometry. The historical PCB and old sink/fan/duct allocations are removed explicitly; the old PCB chamber, controls, sensor, feet, support and shell remain. The board box is bare and unpopulated. The rear-bay sink has **no thermal connection to that board**. The EMI box is a historical space request, not a selected module; fan supply/controller/harness/guards/new ducts are absent.

| File | Digital result |
| --- | --- |
| `rear_bay_shifted_disconnected_candidate.step` | Zero envelope/context volume intersections; nominal space candidate only. |
| `rear_bay_disconnected_study.step` | Rejected: four rear-foot fastener collisions. |
| `rear_edge_direct_sink_conflict_study.step` | Rejected: twenty chamber/sensor/hatch collisions. |
| `front_edge_direct_sink_conflict_study.step` | Rejected: ninety-three front-structure/control collisions. |

`envelopes.json` is the reviewable study input. `checks.json` records source hashes, omissions, exact intersections and STEP reimport checks. `build_envelopes.py` is only a CadQuery/OCC adapter over these boxes and the saved R4 parts, not a new product CAD engine. STEP files are intentionally gitignored generated outputs. Full context has 252 named parts; the valid exports contain 282 or 285 solids depending on the study.

To reproduce from the repository root, use an existing environment containing CadQuery2.6.1:

```sh
python output/temper-manufacture-readiness/mechanical/build_envelopes.py
```

Requires the saved R4 `STEP/parts/` outputs and matching `STEP/assembly.step`, plus sibling `pcb/native18-geometry.json`. The script refuses changed assembly or board identity and a mismatched saved stack thickness. No environment installation is performed. The measured run used `/private/tmp/temper-center-sensor-env/bin/python` (CadQuery2.6.1).

Design implications and next drawing inputs are in `docs/research/mit-product-design/readiness/mechanical/`. Keep this README with any forwarded STEP. The original R4 complete assembly remains the original prototype reference; these are separate engineering studies, not its replacement.
