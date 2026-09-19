# TEA2209T/1 package insulation disposition request — draft, not sent

Purpose: obtain a build/no-build construction decision for the existing SO16
footprint, not general permission to relax a DRC rule.

Recipients: NXP TEA2209 applications engineering for package information;
the product safety reviewer/lab for applicable standard and acceptance route.
No response or approval has been obtained.

## Exact construction and application

- Part U1: TEA2209T/1, SOT109-1 / SO16. NXP datasheet Rev 1.1,
  14 April 2021, pp.4,8–9,12–13. HVS pins 4,11,15 are unconnected.
- Candidate PCB SHA-256:
  `a725929a65e1756b0ad36c39373b6ab993335818344a19721cdc4b7c07ef7ab7`.
  It is a construction candidate, not qualified hardware.
- This unit: 120 V AC nominal, 108–132 V design range, at or below 2000 m.
  No 230 V qualification is requested. Broader product-market scope is separate.
- Present package/PCB microenvironment is unqualified. Production target is
  PD2 only if the documented isolated PCB compartment is verified; otherwise
  the repo requires PD3. No coating, CTI or solder-mask insulation credit is
  asserted. FR4 and molding compound CTI are not established.
- Board pitch 1.27 mm, pad width along pin row 0.60 mm. Endpoint span across
  each HVS pad is 1.94 mm; two adjacent bare geometric gaps sum to 1.34 mm.
  Projected lead-gap sum from the retained package drawing is 1.56 mm before
  solder/position tolerance. None is a measured assembled creepage distance.
- Pairs: 3–5 (GATEHL/GATELL), 10–12 (GATELR/R), 14–16 (GATEHR/VR).
  VR is the **pre-boost rectified mains** node, never the 390 V bulk bank.
  See the companion review for ideal node equations; actual worst-case pair
  waveforms and impulse stresses are not yet qualified.
- Adopted system surge target: 1 kV differential / 2 kV common mode. Those
  generator settings are not the voltage across each pin gap. The actual
  clamped pin differential must be established; no guaranteed 400 V clamp is
  assumed.

## Four questions requiring a concrete answer

1. **NXP package construction:** Are HVS leads electrically floating and
   internally unbonded in this exact package? Provide dimensioned recommended
   lands and relevant molding/material/path data or the package qualification
   basis that applies to these external pin pairs. Does UM11493 use any
   insulation construction or assembly condition beyond what its figure shows?
2. **Governing requirement:** Identify the applicable product standard, edition,
   market deviations and clauses for this induction cooking appliance. Confirm
   the insulation classification of these functional HOT-to-HOT pin pairs and
   the PD/material/working-voltage/impulse inputs required for assessment.
3. **Path measurement:** Determine whether the floating-conductor rule shown
   in IEC 60664-1:2007 Example 11 applies here, including its individual-gap X
   condition and any edition/product-specific modifications. Mark the actual
   limiting PCB, solder, lead and molded-body paths. Do not count floating
   metal as insulation or assume its potential is halfway between neighbors.
4. **Disposition:** For each pair, return required and available clearance and
   creepage (with tolerances), or the precise alternative functional-fault test
   route and acceptance criteria. Answer whether the present construction is
   supportable with the specified enclosure, needs a concrete construction
   change, or is unsuitable. Identify evidence still required to release it.

## Requested returned record

| Pair | Standard / clause | Working / impulse basis | Environment / materials | Limiting physical path | Required vs available | Disposition / condition |
|---|---|---|---|---|---|---|
| 3–5 | reviewer input | reviewer input | reviewer input | reviewer input | reviewer input | reviewer input |
| 10–12 | reviewer input | reviewer input | reviewer input | reviewer input | reviewer input | reviewer input |
| 14–16 | reviewer input | reviewer input | reviewer input | reviewer input | reviewer input | reviewer input |

A statement that the IC is rated for high voltage, an unreferenced “PD2 is fine,”
or an evaluation-board photo does not close this request. Conversely, the
generic 2 mm checker failure does not by itself prove the component unsuitable.

## Prepared references

- Current candidate PCB, schematic, native pin/net record and `FREEZE.md`.
- NXP TEA2209T datasheet and retained UM11493; manifest in `sources/`.
- Bourns manufacturer interpretation, p.2 Figure 2 (lead to the rule, not an
  appliance approval).
- `docs/ENVIRONMENTAL_SPEC.md`, `docs/specs/SURGE_CONTRACT.md`.
- Current review `README.md`. Older dossier's full-line-RMS and 408 V claims
  must not be used as stress inputs.

For a limited NXP inquiry, use [the package-only message](../tea-resolution/NXP-MESSAGE.txt)
without attaching the PCB or source files. External transmission still needs
the user's approval. The wider safety-review packet remains local.
