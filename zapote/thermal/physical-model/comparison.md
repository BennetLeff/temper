# Physical bridge-joint comparison — 2026-09-14

The validated model extension runs on the maintained 2.5 mm necks and the frozen
3 mm candidate. Widening helps modestly. Neither result establishes an acceptable
assembly across the tested sensitivities; no candidate is promoted.

| Same physical assumptions | Baseline 2.5 mm | Candidate 3 mm |
|---|---:|---:|
| Nominal finest-mesh hottest joint | 102.207 °C | 100.924 °C |
| Nominal shared package node | 100.188 °C | 100.071 °C |
| Sum of conductor Joule heating | 1.32880 W | 1.19503 W |
| Last mesh peak-temperature change | 0.04919 K | 0.03445 K |
| Wider-domain peak-temperature change | 0.07722 K | 0.04408 K |
| Weak-assembly hottest joint | 164.349 °C | 159.562 °C |
| Weak-assembly shared package node | 142.060 °C | 141.835 °C |
| Native board SHA-256 | `84f4b325b25e4be71fcf990d9420ddb4346687ca1c28be63fb44a0d661fa2317` | `8a464486017deb4fdbc027fa05c2f8cdd66533569ccd10727137f8b6c12a99d8` |

Temperatures are calculated, not measured. A joint peak includes the copper,
lead and solder; it is an upper bound on the copper/FR4 peak, not a separately
resolved PCB result. The lumped package node is not the die-junction temperature.
Do not compare that node directly to a junction rating and call it qualified.

## Inputs and uncertainty

Both runs use production PFC branch RMS at 15 A, one 40 W package allowance,
80 °C board cut faces and a 60 °C sink reservoir. The cooling comparison's inlet
is 40 °C: the sink boundary presupposes an assembly that can achieve the resulting
20 K rise, rather than proving its airflow. Nominal package-to-sink conductance
is 1 W/K and each package-to-lead conductance is 0.2 W/K. These are assumptions.
The exact Yangjie source supplies external lead-section dimensions; internal
paths, lead material and installed standoff are not guaranteed by that drawing.

The predeclared weak corner halves package conductances, plating thickness,
solder thickness and lead conductivities, uses minimum sourced lead dimensions,
6 mm rather than 3 mm standoff, and 90% nominal copper thickness. It is a
sensitivity case, not an established worst-case bound. It changes the answer
much more than mesh resolution or 0.5 mm trace widening.

The 40 W allowance is counted once. The fixed 1 V at 12.5 A datasheet point and
production waveform do not establish a guaranteed hot-current loss bound.
The field solution computes conductor heating independently; it does not use
the reduced model's all-series resistance approximation.

## What is established

Four conforming material domains, native pad/drill/trace geometry, true exterior
ports, electrical input versus Joule power, thermal reactions, nonlinear solver
convergence, per-contact package coupling and global balance are checked. Each
mesh refinement must increase actual node and tetrahedron counts; heating must
converge within 2%, in addition to the peak-temperature thresholds. Retained raw
replay regenerates geometry and solver settings and rejects stale summaries.

The [baseline evidence](../evidence/bridge-joints-2026-09-14/baseline/) and
[3 mm evidence](../evidence/bridge-joints-2026-09-14/same-package-3mm/) preserve
inputs, backend hashes/versions, meshes, commands and scalar/log outputs. Large
mesh files are losslessly compressed; their report hashes describe decompressed
bytes. Full untrimmed solver directories remain in the local dated `/private/tmp`
runs; all acceptance-required artifacts are retained here.

The standard unit manifest consumes the baseline through mandatory numerical,
source-loss and applicability rules. Applicability stays INDETERMINATE. The four
DRC.PFC.BRANCH_COPPER findings remain FAIL; FEM cannot silently waive them.

## Engineering disposition

The 3 mm option saves about 0.134 W of conductor heat and 1.28 K nominal peak.
That is insufficient evidence to choose it as the final repair. The wider-pitch
GBJ2510-F board is a source-bound, native-clean next candidate, but its lead,
pad and package thermal model is unsupported by this GBU-specific importer and
must receive separate evidence. The shaped 3→4.2 mm draft remains limited by
its 3 mm entry. The rejected 6 mm GBU experiment violates the Rust clearance
profile. These historical experiments are not additional production options.

The next decision should reduce uncertainty in the actual package-to-sink and
lead/assembly paths, or evaluate the GBJ assembly with its own model. More mesh
refinement on the existing GBU model is unlikely to change this ranking.
Hardware procurement, fabrication, thermal measurements and mains qualification
remain NOT RUN.
