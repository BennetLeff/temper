# Bridge redesign continuation checks

The coordinator ran the actual `zapote-pfc-power` CLI from source at `cf2b907ae` against the three frozen candidate bundles from `0fe34b68`.
The [receipt](receipt.json) identifies the executable and exact source/native/PCB/manufacturing bytes.
These checks do not rerun native DRC or establish thermal suitability.

| Candidate | Required branch RMS | Copper-screen capacity | Current result | Separate clearance result from candidate evidence |
|---|---:|---:|---|---|
| Baseline, 2.5 mm | 15 A | 10.4205 A | Four failures | Pass |
| Same package, 3 mm | 15 A | 11.8931 A | Four failures | Pass |
| Same package, 6 mm | 15 A | Above 15 A | No branch-copper failures; overall indeterminate | Fail |

The previous `rust-power-entry.json` artifacts exercise seven construction rules and omit `DRC.PFC.BRANCH_COPPER`.
Their construction result cannot establish branch-current capacity.
The common maintained-unit runner already includes that current check; candidate work must use it or the dedicated PFC CLI before making a capacity claim.

## Thermal-network review counterexample

The first uncommitted physical-model handback computed package temperature by treating all package-to-lead conductances as additional direct paths to the sink.
It then added conductor temperature rise without solving lead-to-package and lead-to-board balances.
Its total-power residual reused the temperature-setting formula and did not test the physical network.
That implementation is not accepted evidence.

An independently eliminated linear network gives a concrete regression reference:

- One package node, four identical lead nodes.
- Sink 60 °C; board reservoir 80 °C.
- Package-to-sink conductance 1 W/K.
- Each package-to-lead conductance 0.2 W/K.
- Each lead-to-board conductance 0.02 W/K.
- Package source 40 W; each lead source 0.5 W.

Eliminating the lead nodes gives package temperature `5920/59 = 100.33898305084746 °C` and each lead temperature `5945/59 = 100.76271186440678 °C`.
Sink heat is 40.33898305084746 W and total board heat is 1.6610169491525424 W, summing to 42 W.
The rejected implementation instead predicts 83.3333 °C at the package and 108.3333 °C at the leads.
This is a mathematical reference, not a claim about the real bridge.
The corrected code must enforce nodal balances and include an asymmetric independent case as well.

## Completion boundary

The revised FEM comparison, package/connection alternative and installed cooling requirements are still being completed.
No candidate is promoted by these receipts.

## Exact bridge substitution

The coordinator visually checked Diodes DS21221 Rev.11-2, pages 1 and 4,
against the retained `Diodes-GBJ2510.pdf` in the alternate candidate bundle.
`GBJ2510-F` uses positive/AC/AC/negative left to right in the front view,
with nominal spacings 10.0, 7.5 and 7.5 mm. This reverses the DC pin mapping
of the original `GBU2510A` footprint.

The ERC part contract now selects DC endpoints and the required footprint
by exact MPN. PFC current injection uses that same reviewed mapping.
Regressions reject an MPN-only swap, the old footprint, and similar unreviewed
part numbers; branch-current tests exercise both pin orders.
This protects source interpretation; native geometry and footprint evidence
are still required for the actual candidate.

Thermal resistance needs its measurement scope too. The Diodes sheet's
1.0 K/W junction-to-case value is explicitly **per element**, measured with a
250 × 250 × 20 mm aluminum plate. It is not a reviewed whole-bridge multiplier
for the total 40 W allowance. Its 1.05 V maximum forward drop applies at
12.5 A and 25 °C; extrapolating it across the PFC waveform does not establish
a guaranteed hot-loss bound.
