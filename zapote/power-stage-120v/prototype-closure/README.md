# Engineering prototype integration

This work continues the five prototype work orders in
[manufacturing readiness](../../../docs/research/mit-product-design/readiness/README.md).
The target is a few engineering prototypes, with the first unit inspected and
tested before completing its siblings. No assembled hardware or physical test
results have been supplied.

See the [integration verification record](verification.md) for independent
checks, corrected evidence-tool defects and the limits of each result.

## Design identity

- Integration checkout starts at `80e716110fb7ff05d5cc4011c1ac370f70498fad`.
- Routed electrical intake is native-18 from
  `fda5ab9ece24ef1ee6f2317604c5ca73367d5201`; board SHA-256 is
  `fb113d95819f1ea7cd8c27f929f7e88308eff44b663af85f71cd6f2bca5a0002`.
- HOT5 and Kelvin source correction has142 components and89 nets. Native-18 has 135
  components and 83 nets. Native-19 is the integration candidate; its own
  verification records determine which source and geometry it represents.
- D22 EMI intake is the separately published
  `7d1c97b92c0ed42be1c28a32d4ccaadd512d2238`, ahead of the canonical simulation
  branch for that work. Its finite-model results do not establish installed
  emissions performance.
- The R4 exterior remains the mechanical reference. Changing the internal
  board, sink, coil or chassis relationship requires a new integrated check.

## Work products

The domain directories contain authored design changes, reproducible studies,
and evidence. Their local reports distinguish completed digital checks from
conditional candidates and unavailable physical measurements.

- [Power experiment](power/README.md): 81 conditional commutation cases,
  historical-baseline reproduction, actual protection-path accounting,
  capacitor limits and an interlock component proposal. Full D17 remains open.
- [EMI intake](emi/README.md): verified existing D22 evidence, including 32
  recorded-waveform replays and 12 fresh AC simulations. The 16 diagnostic cases
  support 8.280 dB minimum modeled AV margin after the stated reserve;
  installed emissions, coupled stability and component qualification remain open.
- [Native19 PCB candidate](../native-19/README.md): HOT5 integration, corrected1mΩ four-terminal shunt, U8 routing, typed schematic pins, and probe/carrier checks. Three final DRC runs report zero errors, opens and schematic mismatches;39 inherited warnings remain. It is a digital candidate, not a fabrication release.
- [Cooling and cold fixture](../../../docs/research/mit-product-design/readiness/mechanical/cooling-closure/README.md):
  contact-bearing packaging, floating PCB carrier and control coupon. The local
  STEP has 539 valid solids and zero tested nominal collisions; it still uses
  the 135-part native18 population. Actual package contact bounds, clamp loads,
  custom-sink performance and the complete duct remain unresolved.
- [First-unit execution packet](manufacturing/first-unit.md): cold fixture,
  inventory, numbered inspection/test holds and intake manifest.

## Status against the five work orders

| Work order | Result available | Still required before powered prototypes |
| --- | --- | --- |
| Power range | Reproduced baseline,81 conditional cases, protection-path accounting and capacitor application questions | Actual coil/pan data, capacitor waveform limits, loaded Kelvin-reference error and complete protection/extinction evidence;45 A is not released |
| Cooling packaging | Contact-bearing cold study, connected sink, floating carrier and selected fan/clamp candidates | Integrate native19; establish real package contact/lead forming, clamp force and insulation; finish duct/chassis/harness and prove thermal performance |
| Native PCB | Routed142-part/89-net HOT5/Kelvin candidate, typed schematic, zero DRC errors/opens/parity and populated STEP | Re-extract changed copper, disposition warnings, qualify footprints/probes/retention and produce reviewed fabrication/assembly outputs |
| Mechanical details | Switch coupon, corrected drawing tolerance ranges and named material/process candidates | Measure travel/force, qualify bonds/seals/glass processes and integrate the actual button/controller interface |
| First unit | Serialized traveler, cold fixture,21-item picklist and nine explicit holds | Acquire specimens/instruments, build and inspect the first unit through staged tests; siblings follow its findings |

## Evidence boundaries

An unchanged-copper check can preserve the applicability of a board extraction;
it cannot prove that new nearby coil, heatsink or chassis geometry has unchanged
magnetic or capacitive coupling. Reconcile installed geometry with the EMI and
thermal assumptions before expanding the operating envelope.

The 45 A historical analysis is not an approved operating limit. Cold impedance
measurements, capacitor application limits, both detector paths and current at
actual shutdown still have to agree. An imposed-current commutation study is
not a closed-loop fault-survival test.

Physical records remain `NOT_RUN`. Fabrication, energization and completion of
additional units require the evidence specified in the first-unit packet;
creating this directory does not release any of those stages.
