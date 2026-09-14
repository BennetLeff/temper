# Power-entry bridge neck thermal assessment

This experiment answers how the four existing bridge necks respond to specified
terminal temperatures and cooling conditions. It does **not** establish those
conditions in an assembled cooker. Numerical validity and board acceptance are
separate harness rules; a valid experiment cannot waive an ampacity finding.

Follow-up: [selected cooling design and contract-bound run](bridge-cooling.md).
This page and its original 40-case bundle remain the initial experiment;
the common runner now uses the subsequent 20-case cooling-design bundle.

## Results and board disposition

[Retained run](evidence/bridge-necks-2026-09-14/assessment.json): 40 cases on
board `84f4b325b25e4be71fcf990d9420ddb4346687ca1c28be63fb44a0d661fa2317`.
Gmsh 4.15.2-git and Elmer 26.2.1 source revision `a19504a` ran on the M2 Pro.
These are calculated steady-state peaks, not measured temperatures:

| Neck | Baseline, fine mesh | Hot reservoirs | Hot/weak cooling, fine mesh |
|---|---:|---:|---:|
| minus | 83.90 °C | 127.88 °C | 243.62 °C |
| ac1 | 84.96 °C | 128.98 °C | 258.66 °C |
| ac2 | 80.93 °C | 124.97 °C | 200.02 °C |
| plus | 82.12 °C | 126.12 °C | 217.99 °C |

[Harness and native-board verification receipts](verification-2026-09-14/README.md)
retain the seven-unit rerun and review disposition.

All numerical checks passed. Maximum heat-balance residual was 6.64×10⁻¹⁰ W;
maximum electrical-power residual was 2.86×10⁻¹¹ W. Coupling required at most
17 iterations. Medium/fine peak differences stayed below 0.02 K in the
baseline and 0.18 K in the hot/weak corner.

**Disposition: retain all four current-capacity findings.** The baseline shows
that the simple width screen alone does not prove overheating. The stress cases
show that the design also cannot be cleared without bounding its heat paths.
The high-temperature cases extrapolate constant thermal properties and omit
radiation, so their exact peaks are not reliable predictions of a physical board.
They identify a sensitivity requiring a better assembly model or measurements.

The separate, already-checked 4→6 mm trace repair remains in the PCB. It improves
that segment's nominal current screen from 14.65 A to 19.66 A at the unchanged
15 A requirement. It does not repair these four 2.5 mm bridge necks or certify
their pad contacts.

The remaining design input is a bridge/board cooling contract: selected bridge
heatsink and mounting, exposed lead length/material, solder/barrel construction,
local airflow, and permitted package/PCB temperatures. The baseline reservoir
values are candidate design targets, not evidence that an assembly meets them.
Once that contract is bounded, rerun the required corner. If it fails, revise the
escape routing or package/copper arrangement. Simply widening the centered
connections is constrained by adjacent pads and electrical clearance.

Work status: geometry, numerical validation and harness replay are implemented;
the 4→6 mm repair is retained; thermal acceptance of the four bridge connections
is blocked on the assembly inputs above. No fabrication or powered test is
authorized by this numerical result.

## Geometry and physics

The source is the saved power-entry PCB, `native-copper-12.json`, and the
manufacturing extraction retained with the 4→6 mm repair. Rust checks native
identities against the KiCad document, the shared board digest, pad/drill data,
and the four specific trace UUIDs. The local models retain the 3×3.2 mm pads,
1.6 mm drill, 2.5 mm traces and native pad-to-cut distances:

| Net | Layer | Distance |
|---|---|---:|
| minus | B.Cu | 8.5 mm |
| ac1 | F.Cu | 9 mm |
| ac2 | B.Cu | 6 mm |
| plus | F.Cu | 7 mm |

Gmsh creates one copper solid and a conforming 1.44 mm FR-4 substrate per neck.
The substrate patch is 5 mm wide and extends from 2 mm behind the pad to the
trace cut. The drill passes through both solids. Elmer solves electrical
conduction, Joule heating and steady heat conduction. Copper conductivity is
58 MS/m at **20 °C**, with temperature coefficient 0.00393/K; changing ambient
does not change that reference temperature. Heat conductivity is initially
400 W/(m·K) for copper and 0.3 W/(m·K) for FR-4.

Physical groups have fixed meanings: volume 1 copper, volume 2 FR-4; boundary
11 copper drill wall, boundary 12 copper cut face, boundary 13 remaining exterior.
Internal copper/FR-4 faces exchange heat and have no convection boundary.
Current is distributed uniformly over the independently measured mesh area of
boundary 11, and boundary 12 is the electrical zero-potential reference.

The terminal and rest-board connections use Robin boundaries: conductance in
W/K multiplied by the difference between surface and reservoir temperature.
This represents combined lead/solder/package and surrounding-board effects;
it does not resolve their solids. Plated barrel, solder fillets, opposite-side
copper, bridge package and neighboring board features are omitted. The bottom
trace cases are reflected into the same local orientation; this assumes equal
top/bottom convection. This abstraction must be revisited for a real enclosure.
Radiative exchange is omitted. At high temperatures its omission and the
constant FR-4 heat conductivity limit the interpretation of absolute peaks.

## Assumptions and sensitivity

These are chosen sensitivity inputs, not measured assembly properties or a
certified worst-case envelope. All full-load cases use 15 A RMS; the harness
also checks that this agrees with the source-derived PFC bridge branch current.

| Input | Baseline | Sensitivities |
|---|---:|---:|
| Air temperature | 40 °C | 60 °C |
| Terminal reservoir | 80 °C | 125 °C |
| Rest-board reservoir | 60 °C | 100 °C |
| Air convection | 8 W/(m²·K) | 2, 25 |
| Terminal conductance | 0.02 W/K | 0.002 |
| Rest-board conductance | 0.007 W/K | 0.001 |
| Copper thickness | 70 µm | 63, 77 |
| Current | 15 A | 5 A |

The hot/weak-cooling corner also uses copper conductivity 55 MS/m, copper heat
conductivity 350 W/(m·K), and FR-4 heat conductivity 0.25 W/(m·K). Ten scenarios
per neck include mesh refinement at 0.4/0.2/0.15 mm, plus a fine-mesh check of
the hot/weak corner. This is a sampled sensitivity study, not proof that every
combination between or outside these inputs is covered.

For scale, assuming a sinusoidal 15 A RMS input and a constant 1 V drop per
conducting diode gives about **27 W in the bridge**, not 13.5 W:
`2 × 1 V × (2√2/π) × 15 A`. The factor `2√2/π` is the mean of the absolute
sine divided by its RMS. This is illustrative, not an upper loss bound: the
[Yangjie GBU2510A datasheet](https://www.21yangjie.com/pdf/zlqj/zhengliuqiao/GBU25005A%20THRU%20GBU2510A.pdf)
specifies the 1 V point at 12.5 A, below the 21.2 A peak of that assumed waveform.
Bridge heat cannot simply be deposited wholly in the four PCB necks; its split
between package, heatsink and leads requires an assembly model or measurement.

## Numerical checks

- Mesh nodes, tetrahedral volumes, boundary membership, drilled-wall area and
  trace cross-section are checked independently of Elmer. Exterior faces must
  have exactly one boundary tag; internal faces must have none. A conforming
  copper/FR-4 interface must exist.
- Electrical power must match current times mean terminal potential. Integrated
  Robin heat leaving all boundaries must balance Joule power to 0.1 mW.
- The sum of Elmer's nodal reaction fluxes must also balance power to 0.25 mW.
  Individual `RES ... flux over bc` numbers are **not** per-face heat flows at
  shared boundary nodes: Elmer assigns a node's reaction to the first BC it
  encounters. We retain these diagnostics but use Robin integrals for physical
  heat partition. See `SolverUtils.F90`, `CalculateLoads`, in the pinned
  [Elmer source](https://github.com/ElmerCSC/elmerfem/tree/a19504ac53ec222e3355e182b08f2ff280c2203a).
- The final thermal relative change must be finite and ≤10⁻⁸, with fewer than
  30 outer coupling iterations. Completion alone is insufficient.
- Nominal medium/fine peaks must differ by ≤0.5 K and power by ≤1%; coarse/
  medium and hot/weak medium/fine allow ≤1 K and ≤1%. Node counts must increase.
  These numerical tolerances are not temperature ratings.
- A separate constant-conductivity bar with Robin boundaries is checked against
  a closed-form heat-equation solution, including retained raw Elmer output.

Replay checks the saved board, full artifact hashes, native binding, regenerated
geometry and SIF, mesh topology, raw log/scalar agreement, convergence and case
population. Edited summary values or a changed scenario with refreshed hashes
must fail. The numerical harness rule can pass; thermal applicability remains
INDETERMINATE until assembly cooling and temperature limits are established.

Replay validates historical evidence without requiring the original backend
installation. It verifies recorded command arguments, environment, retained
stdout/stderr and backend hash identities; it does not qualify today's installed
solver. A new live run hashes its executable and solver libraries before and
after execution. Updating an installed backend does not invalidate an earlier
source-bound result. These records provide reproducibility and detect accidental
drift; they are not cryptographic attestations against fabricated evidence.

## Run and replay

Build `zapote-thermal-necks` from the Zapote workspace. Its `run` command takes
absolute paths in this order:

```text
zapote-thermal-necks run BOARD NATIVE MANUFACTURING NEW_OUTPUT GMSH ELMERGRID ELMERSOLVER
zapote-thermal-necks replay EVIDENCE_DIRECTORY BOARD
```

Every invocation uses a new output directory. The bundle retains geometry,
mesh, SIF, scalar output, solver logs, backend hashes and per-command records.
No hardware was powered or measured for this assessment.
