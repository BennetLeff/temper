# Bridge cooling design requirements

This is the selected cooling concept for the saved power-entry board, not an
assembly qualification or a fabrication release. The [machine contract](bridge-cooling-contract.json)
feeds the Rust thermal runner and common unit harness. Its values are design
requirements to achieve and verify. Hardware tests remain **NOT RUN**.

## Result and disposition

[The retained 20-case run](evidence/bridge-cooling-2026-09-14/assessment.json)
completed on the M2 Pro using Gmsh 4.15.2-git and Elmer 26.2.1. Temperatures
below are calculated steady-state local copper/FR-4 peaks, not measurements:

| Neck | Design targets, fine mesh | Quarter conductance, fine mesh |
|---|---:|---:|
| minus | 106.04 °C | 142.18 °C |
| ac1 | 107.86 °C | 147.77 °C |
| ac2 | 100.48 °C | 125.09 °C |
| plus | 102.72 °C | 132.18 °C |

All geometry-transfer, energy and convergence checks passed. Maximum heat-
balance residual was 8.18×10⁻¹⁰ W; electrical-power residual 4.05×10⁻¹¹ W.
Coupling took at most 11 iterations. The largest medium/fine difference was
0.0152 K for the design cases and 0.0585 K for the reduced-contact cases.

**Retain all four current-capacity findings.** The normal local margin is only
2.14 K, while weaker heat paths change the result by tens of kelvin.
The result supports the selected cooling concept as a candidate; it does not
justify accepting the existing neck geometry. Prioritize improving the bridge
connections or resolving their actual lead/barrel/solder heat paths over further
mesh refinement. Increasing fan flow alone cannot be credited with fixing an
unresolved package-to-PCB heat path. No PCB geometry changed in this follow-up.

The original [40-case study](bridge-necks.md) remains unchanged. The common
runner now selects this new contract-bound evidence and separately reports
numerical validity, the junction budget, PCB target compliance, contact
sensitivity and assembly applicability. Source/input mutations, edited summary
numbers and missing process evidence must fail replay even if hashes are refreshed.
The v1 profile requires the exact selected heatsink and two-fan assembly;
substitutions require review rather than relabeling this result. Passive
reservoirs below inlet air temperature and non-finite heat budgets are rejected.

## Selected assembly

| Item | Selection | Basis / limitation |
|---|---|---|
| Bridge | Existing Yangjie GBU2510A | Saved PCB unchanged; use the exact A-suffix datasheet |
| Heatsink | Wakefield **395-1AB**, DigiKey **345-1177-ND** | 127 × 76.2 × 63.5 mm; central device mounting area 50 × 76 mm |
| Fans | **2 × Sunon MF80251V1-1000U-G99**, DigiKey **259-1859-ND** | Each 80 × 80 × 25 mm, regulated 12 V, tach output |
| Spreader | Custom flat aluminum plate, **75 × 45 × 5.5 mm** | Fits the nominal central mounting area; edge tolerances and fastener access still need a mechanical drawing |
| Bridge contact | Thin thermal grease film and a separate broad spring clamp | Clamp the bridge's broad case face to the spreader; do not drill its plastic body or load its leads with the heatsink weight |
| Spreader isolation | **Bergquist SIL PAD TSP 1800**, 0.229 mm sheet, cut to plate outline | Between spreader and heatsink; insulated fasteners required if this interface is used as electrical isolation |
| Support / duct | Chassis-supported bracket and two-fan plenum, sealed to fin passages | Support the heatsink independently of PCB and bridge solder joints |

The [Wakefield manufacturer catalog, printed page 93](cooling-sources/wakefield-catalog-page-74.pdf)
gives 0.50 K/W at **500 LFM (2.54 m/s)** and 1.10 K/W natural convection for
this part. These are typical catalog conditions, not a guarantee in our duct.
The contract requires installed sink-to-inlet-air resistance ≤0.50 K/W.
Measure at the spreader contact region: an average fin temperature would miss
the spreading resistance from the small bridge footprint.

The [exact fan datasheet](cooling-sources/sunon-mf80251v1.pdf), pages 2 and 5,
specifies 41 CFM free-air flow and 44.8 Pa shutoff pressure **per fan**.
Those are opposite endpoints of the curve, not simultaneous performance.
Two fans in parallel provide flow coverage across the sink width; their
pressures do not add. The gross 127 × 63.5 mm face at 500 LFM corresponds to
about 43.4 CFM before subtracting solid fins. One 41 CFM free-air fan cannot
establish that condition. Two fans are a candidate pending the duct/system
pressure curve, flow distribution and thermal test.

Arrange the fans side by side, feeding a 30 mm transition plenum along the
76.2 mm fin length, with at least 20 mm unobstructed exhaust allowance. Reserve
approximately **170 × 160 × 95 mm** for this cooling module in its own axes,
including fan frames, duct and support allowances. This is a packaging allowance,
not a collision-checked placement in the 230 × 210 mm PCB or cooker enclosure.
The upright bridge case fixes the mounting-plane orientation; do not overlay
a horizontal heatsink on the existing board and assume that it fits. Final
bracket/duct orientation and neighboring-component clearance remain mechanical
integration work.

The plate and pad provide a practical large-area interface. The
[Henkel pad data](cooling-sources/henkel-tsp1800.pdf) give typical area-normalized
impedance 0.62 K·in²/W at 25 psi. Over an ideal 75 × 45 mm contact this is
about 0.119 K/W; bolt holes, flatness and spreading increase it. The **0.25 K/W
total case-to-sink requirement** includes grease, spreader, pad and both contact
interfaces. It is not established by dividing pad thickness by conductivity.
Do not apply the pad's assembly pressure through the bridge package: plate
fasteners and the bridge spring clamp have separate load paths. Clamp force,
fastener torque and machining details need vendor/mechanical validation.

Neither the pad's breakdown test nor the bridge's molded body alone establishes
the cooker's required mains insulation. Creepage around the plate, screw
insulation and chassis bonding must be resolved in the assembly safety design.

## Thermal requirements and model boundary

| Quantity | Required design value | Meaning |
|---|---:|---|
| Bridge branch RMS current | 15 A | Bound to the actual PFC branch report |
| Cooling inlet air | 40 °C maximum | Ambient at fan inlet, not room air remote from cooker |
| Bridge dissipation allowance | 40 W | Design allowance; not a proven upper loss bound |
| Junction-to-case allowance | 1.25 K/W | Sensitivity above published 1 K/W; not a guaranteed production maximum |
| Case-to-sink allowance | 0.25 K/W | Entire installed interface/spreader budget |
| Sink-to-air allowance | 0.50 K/W | Must be achieved in the installed duct |
| Junction design ceiling | 125 °C | Engineering derating ceiling, below the part's absolute limit |
| Local PCB design ceiling | 110 °C | Assembly requirement; actual laminate, solder and nearby part ratings must support it |
| Terminal reservoir target | 95 °C | Independent boundary target, **not derived from case temperature** |
| Rest-board reservoir target | 80 °C | Independent target at the four model cut faces |
| Terminal / rest-board conductance | 0.020 / 0.007 W/K | Effective model connections, not measured lead/barrel properties |

The series budget is `Tj = Ta + P × (Rjc + Rcs + Rsa)`. At these values the
sink, case and junction are **60, 70 and 120 °C**. The available junction margin
is 5 K. The no-fan stress allowance Rsa=1.25 K/W produces **150 °C**, so
continued full power without cooling is outside the design. This is a steady
heat-budget failure, not a validated time-to-trip calculation.

The bridge loss allowance must be checked using actual current waveform,
temperature-dependent diode behavior and tolerances. The illustrative 27 W
calculation in [the initial study](bridge-necks.md) is not an upper bound.
The reduced series network conservatively sends all 40 W through the sink
branch; it does not solve the competing heat path into the leads. Consequently
it cannot establish the 95 °C terminal reservoir or the conductances. Those
require a package/lead/barrel model or controlled measurements. Reservoir
temperatures are not directly the modeled boundary-surface temperatures when
the Robin connection carries heat.

The new local FEM profile uses 63 µm copper, 55 MS/m electrical conductivity
at 20 °C, 350 W/(m·K) copper and 0.25 W/(m·K) FR-4 thermal conductivity,
and only 2 W/(m²·K) convection. It gives no direct fan-cooling credit to the
PCB. Each neck gets three design meshes (0.4, 0.2, 0.15 mm) and two meshes
with both connection conductances reduced to one quarter. This tests contact
sensitivity; it is not a proof over all possible assemblies.

## Cooling fault response and qualification

Provide a regulated 12 V supply for both fans, sized for startup as well as
the combined 0.276 A datasheet maximum running current. Do not attach these
fans directly to 15 V. Qualify the tach interface against its electrical
specification before connecting it to a 3.3 V controller. Each fan needs its
own monitored tach signal; loss of either inhibits heating and latches a fault.

Tach alone cannot detect a blocked duct with spinning fans. Add independent
bridge thermal supervision to the hardware permit path. At the 40 W / 1.25 K/W
junction-to-case allowance, the case trip must be **below 75 °C**, with sensor
error and shutdown overshoot subtracted from that bound. The PCB trip must
likewise be below **110 °C minus error and overshoot**. Its modeled normal
107.86 °C peak leaves only 2.14 K for operating margin, sensing error and
response. A usable full-power protection window is therefore not established.
Do not choose a higher trip merely to avoid nuisance shutdowns.

These are **integration requirements**, not implemented protection. Determine
the actual trip/restart values from sensor placement, uncertainty, lag and
fault tests; latch a cooling fault until inspection. Existing coil/inverter
sensors cannot be claimed to cover this separate bridge unless their placement
and response prove it.

Before thermal acceptance, record actual assembly identity, bridge losses at
full current, inlet temperature, sink/case/pad temperatures, duct airflow,
laminate/assembly ratings and steady-state drift. Exercise stalled fan,
disconnected tach and blocked inlet separately. Model sensor lag and shutdown
transients before interpreting the fault trip targets as protective limits.

The common harness must continue reporting cooling applicability as
INDETERMINATE, and retain the four current-capacity findings, until those
requirements are established. A numerical design result is not an IPC-screen
waiver. No heatsink, fan or PCB has been purchased or powered in this work.

## Reproduce

From the repository root, replay without Gmsh or Elmer installed:

```sh
CARGO_TARGET_DIR=/private/tmp/zapote-rtd-target cargo run --release \
  --manifest-path zapote/Cargo.toml -p zapote-thermal --bin zapote-bridge-cooling -- \
  replay zapote/thermal/evidence/bridge-cooling-2026-09-14 \
  zapote/power-entry/candidate/section.kicad_pcb \
  zapote/thermal/bridge-cooling-contract.json
```

For a fresh solve, the same binary accepts absolute paths in this order:

```text
zapote-bridge-cooling run BOARD NATIVE MANUFACTURING CONTRACT NEW_OUTPUT GMSH ELMERGRID ELMERSOLVER
```

Use `power-entry/evidence/native-copper-12.json` and
`power-entry/evidence/copper-repair-2026-09-12/parent-manufacturing.json`
with the saved candidate. Every attempt requires a new output directory.
`make -C zapote check-units` consumes the contract and evidence automatically;
the five thermal rule IDs are mandatory for power-entry, even if its thermal
hook fails to return a report. Assembly qualification remains separate.
