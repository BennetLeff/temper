# GBJ2510-F thermal evaluation

This study evaluates the routed GBJ alternative without promoting it into the
maintained power-entry candidate. The board is
[`alternate-gbj/section.kicad_pcb`](../../power-entry/bridge-redesign/variants/alternate-gbj/section.kicad_pcb),
SHA-256 `fd624e37be053e5140256fcbcb8ab84e330b42d1fbff3a01f92fa8d8a205447b`.
No PCB bytes, fabrication orders or powered hardware were changed by this study.

## Model and source contract

The Diodes Incorporated GBJ25005–GBJ2510 sheet, DS21221 Rev.11-2, May 2025,
is retained in the candidate's `sources/Diodes-GBJ2510.pdf`. Its SHA-256 is
`c7d9657711588ecf8d9adf4e1438435d488b21b7733e99caaead3c2490728a02`.
Page 2 gives **1 K/W typical junction-to-case per element**, under its specified
250 × 250 × 20 mm aluminum plate condition. The model has four diode nodes
and one case node; it never multiplies that per-element rating by the entire
40 W bridge allowance. Page 4 gives external lead dimensions I=0.9–1.1 mm
and R=0.6–0.8 mm. Lead material is not established by that drawing.

The electrical topology selects the two conducting diodes in each half-cycle.
Production PFC waveform weights allocate the **one 40 W allowance** between
the four elements. The sheet's 1.05 V maximum at 12.5 A and 25 °C is used only
for a separate fixed-VF point estimate. The actual waveform exceeds that test
current; the estimate is not a guaranteed hot-loss bound.

Each diode connects thermally to the case through the typical 1 K/W datum and
to its two electrical endpoint leads through an **assumed** 0.1 W/K path.
Using electrical adjacency as thermal adjacency is a model hypothesis, not
manufacturer internal-construction evidence. The case connects to the sink
through an assumed 0.25 K/W clamp/spreader interface. Each of the four local
FEM domains contains copper, FR4, solder and an external lead. FEM reaction
flows couple the domains to the package network. Every lead, diode, case and
global heat balance must close; current × measured voltage independently
checks conductor Joule heating.

## Native geometry and current scope

The translator binds the actual saved board, manufacturing capture, pin map,
pad and trace UUIDs. The four pads are 4 × 4 mm (pin 1 rectangular, the others
circular), with 1.6 mm drills and 4.2 mm traces. AC2 is on B.Cu. The model
preserves that side while the lead and solder remain on the component side.
An independently calculated union area handles traces wider than their pads;
round pads are not approximated as rectangles or elongated ovals.

Three neck traces have determined 15 A RMS cuts in the production graph.
**AC2 has an unresolved pad-contact split.** Its FEM case assumes the full
terminal RMS, checked against the production waveform and trace envelopes.
This does not resolve the current field in the pad/contact area. The ordinary
PFC current-distribution finding remains INDETERMINATE. No thermal result
silently replaces that finding with PASS.

## Cooling and sensitivity contract

The nominal FEM imposes 80 °C at external board cut faces and 60 °C at the
sink. Side walls are adiabatic. The retained Wakefield 392-120AB catalog gives
0.16 K/W at 100 CFM; the Sanyo 9RA1212E1001 fan has 120 CFM free-air and
100 Pa shutoff endpoints. Those endpoints do not establish installed airflow.

The Rust cooling calculation includes 40 W bridge, 65 W other-PFC allowance
and the fan's full 5.6 W electrical rating in one 110.6 W shared heat budget.
At the imposed 100 CFM, it adds the bulk air rise to the catalog sink rise as
an inlet-warming allowance. This leaves little margin against the prescribed
60 °C reservoir; actual duct pressure, local spreading and recirculation are
not solved by this calculation.

The predeclared cases are three nominal meshes (0.6/0.3/0.15 mm), a 1.5×
wider local domain, weaker assembly, and a 100 °C sink fan-loss sensitivity.
The weak case uses minimum sourced lead section, 6 mm instead of 3 mm
standoff, half lead electrical/thermal conductivities, half solder/plating,
90% copper thickness, 1.5 K/W per diode, 0.5 K/W case interface and half
diode-to-lead conductance. These are sensitivities, not a proven worst-case
envelope. The fan-loss case is steady-state; shutdown timing remains unmodeled.

Whole-joint peaks include lead and solder. A peak below the 110 °C PCB ceiling
is a conservative check on these modeled PCB solids. A peak above that value
does not identify which material overheated. The hottest lumped diode node
is checked against the 125 °C engineering target; it is not a resolved silicon
temperature or hardware measurement.

## Harness and learning

`zapote-joint-model` builds or replays this model through the production PFC
adapter. The common runner dispatches the GBJ model under the same ten
mandatory thermal rule IDs as the GBU study, using GBJ-specific physics and
source bytes. Missing, stale or contradictory evidence fails closed.
Applicability stays INDETERMINATE independently of numerical checks.

The historical GBU evidence remains immutable. It uses a front-side local
trace normalization; it is not evidence for the newly modeled asymmetric
B.Cu lead/trace configuration. Comparison with GBJ therefore changes both
package geometry and the model's package/trace-side treatment, and cannot
attribute all improvement to trace width alone.

The existing reviewed memory notes were read during implementation. The Rust
memory selection under [`memory-review/`](memory-review/) was prepared for
the subsequent review. It is not retroactive proof of delivery before the
implementation agents started. Agent prompts, acknowledgements and final
review receipts are distinguished from the generic process transport.

See the retained assessment, validation receipt and review for numerical results
and the candidate decision. Hardware qualification remains NOT RUN.

## Results and decision — 2026-09-14

The retained [assessment](evidence-01/assessment.json) contains six scenarios,
96 local Gmsh/Elmer solves including coupling bases and iterations:

| Scenario | Whole-joint peak °C | Hottest diode node °C | Conductor loss W |
|---|---:|---:|---:|
| nominal-coarse | 84.28 | 80.22 | 0.858 |
| nominal-medium | 84.33 | 80.22 | 0.863 |
| nominal-fine | 84.35 | 80.22 | 0.866 |
| wider-domain | 84.31 | 80.22 | 0.863 |
| weak-assembly | 117.82 | 95.95 | 2.567 |
| fan-loss | 118.64 | 119.53 | 0.878 |

Nominal peak changes are 0.044 K then 0.025 K over mesh refinement;
the wider-domain change is 0.017 K. Global heat-balance residuals are below
0.000001 W. These establish numerical consistency within the specified model.
They do not establish the thermal assumptions or a bounded hot diode loss.

**Keep GBJ as the preferred alternative for further assembly development;
do not promote it to a qualified power-entry board.** Nominal temperatures
have useful margin. The weak-assembly whole-joint peak exceeds the conservative
110 °C screening ceiling, and the fan-loss diode node reaches 119.53 °C against
the 125 °C engineering target. Neither case is a demonstrated worst case.
The catalog cooling budget predicts 59.64 °C at the imposed 100 CFM, leaving
only 0.36 K against the nominal sink boundary.

Next engineering work is to define a reproducible bridge mounting/contact
assembly, establish its thermal paths and installed fan operating point, and
resolve pad/contact current distribution. A transient shutdown model is needed
before claiming fan-loss protection. Additional nominal mesh refinement is not
the next useful step. No powered hardware tests have been run.

## Regressions and retained evidence

- `zapote-thermal/tests/gbj_geometry.rs`: native pin order, pin/net forgery,
  actual back-layer mesh versus an incorrect front-layer interpretation.
- `zapote-harness/tests/gbj_model.rs`: actual production trace IDs, missing or
  changed AC2 envelopes, forged native geometry, missing mandatory evidence,
  asymmetric diode conduction and full retained-evidence replay.
- Package unit tests check a closed-form symmetric case and an asymmetric
  manufactured case, every node's energy balance, and Kelvin-shift invariance.
- Existing GBU replay remains a regression against accidental model migration.

The diode-pair review concern was rejected after tracing the production sign
convention: positive injection means current enters **PCB copper**. Negative
AC1 injection therefore means current entering the device at AC1. Positive
half-cycles use diode pairs 0/3; negative half-cycles use 1/2. A balanced sine
alone cannot distinguish that mapping; the asymmetric test can.

Large bound meshes are stored as gzip with hashes over their original bytes.
Replay rechecks those bytes and reconstructs geometry, physics and scalar
measurements. Unbound full-field visualization output is preserved locally,
listed with hashes in [full-field-archive.json](evidence-01/full-field-archive.json);
it is not required for acceptance replay. It is not bundled in Git.


## Common-suite comparison

The initial native run (`common-maintained-01`) could not access the macOS
display service. Its seven extraction failures are preserved as a failed
instrument setup, not board findings. With the required runtime access:

- [Maintained GBU run](common-maintained-final/summary.json): six units
  INDETERMINATE; power entry FAIL, with exactly four `DRC.PFC.BRANCH_COPPER`
  failures at the existing 2.5 mm bridge necks.
- [GBJ comparison run](common-gbj-final/summary.json): all seven units
  INDETERMINATE, no FAIL findings. The comparison changes only power-entry
  inputs in [units-gbj.json](units-gbj.json); the maintained registry is unchanged.

These statuses preserve outstanding engineering applicability; INDETERMINATE
is not hardware acceptance. Buck and MCU remain outside this seven-unit registry.


Final verification: 273 thermal/harness tests pass; the one normally ignored
live Gmsh test was run separately and passed. Clippy reports no warnings in the
changed crates (13 existing DRC/ERC warnings remain). Import-boundary and derived
artifact gates pass. See [validation receipt](validation.json),
[logs](validation-logs/), and [review resolutions](review-resolution.md).
The final common run reports weak-assembly and fan-loss separately; neither can
silently displace the other.
