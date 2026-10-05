# R6 seal architecture force envelope

**Analytical budget screen only. No diaphragm geometry, stiffness, fatigue, temperature qualification or liquid seal has been established.** Positive rows are budget-feasible under their assumptions, never approved designs.

The model calculates F=Δpπd²/4 for assumed effective diameters6/8/10/12mm. Effective area is not necessarily the physical cap area and can vary with membrane stroke. The inherited proposed pressure allocation is3mN, seal hysteresis3mN and harness/witness4mN within a10mN total parasitic budget. These are R5 development allocations, not measured limits.

Two motion envelopes are screened: a local island boundary moving0.25mm, and a single boundary accommodating1.2mm common plus0.25mm local motion. The latter1.45mm is an endpoint envelope, not proof those motions co-occur under a pan. The0.20mm retention lift and upward capture remain separate abuse/service conditions for an eventual seal. `local_island_only` does not account for the common carrier seal and is NOT a complete two-seal architecture score.

For an assumed linear elastic seal, worst-case force is |ΔpA|+hysteresis+harness+k×stroke. Unlike forces cannot be cancelled to create an optimistic screen. The stiffness limit uses the remaining total budget after pressure,3mN hysteresis and4mN harness. At zero pressure that leaves3mN for elastic force; consuming the full separate pressure allocation leaves no elastic margin. This intentionally exposes competition between allocations rather than allocating the same10mN twice.

No elasticity is inferred from Shore hardness or a datasheet's100% modulus. Thermal growth, compression set, viscoelastic hysteresis, reassembly, preload, membrane buckling, drain blockage and force transmitted by the other stage remain unresolved. Water head assumes998kg/m³; it is an illustrative pressure conversion, not a spill simulation.

## Architecture decision

Develop a replaceable cartridge with defined compression datums, a connected dry pressure reference and a separate gravity drainage route away from the induction electronics. Preserve positive cap retention independently of the seal. Compare the complete single-boundary and two-boundary load paths before picking a compound or thickness.

Breville's patent supplies useful service, clamping and drainage precedents. Conventional pneumatic rolling diaphragms can need pressure to maintain convolution shape; low and reversing pressure must be specified to a supplier. Bellofram's high temperature table states stationary rather than cycling limits. Neither publication qualifies our250°C millinewton application.

- [Breville US10582573B2](https://patents.google.com/patent/US10582573B2/en)
- [Bellofram design manual](https://damapi.marshbellofram.com/uploads/design_manual_3e8071e17a.pdf), stationary temperature limits and pressure-reversal guidance.
- [Kalrez6375](https://www.dupont.com/content/dam/dupont/amer/us/en/kalrez/public/documents/en/KZE-H82112-00-F0719_Kalrez_Spectrum_6375.pdf): R5 compound control, no installed membrane qualification.
- [Kalrez7375](https://www.qnityelectronics.com/products/kalrez-7375.html): wet/hot candidate;300°C rating does not establish force or flex life.

`pressure_envelope.csv`:4 rows; `force_budget.csv`:90 hypothetical combinations; `stiffness_limits.csv`:30 bounds. Run `./run.sh`. Required physical evidence is hot/cold installed force-displacement loops, effective area through travel, blocked/condensed pressure path, leak/drain behavior and aged/reassembled performance. All physical results are NOT_RUN.
