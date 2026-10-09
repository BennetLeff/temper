# Remaining prototype release work

This is the boundary after the round5 integration corrections. A passing
software or geometry receipt closes only its stated scope. The design has
not been released for fabrication or powered testing.

| Work | Required evidence to close | Category |
|---|---|---|
| Review the complete electrical revision | Review the joined power, sensor, supervisor and controller circuits with their actual interfaces and failure paths. The central export uses typed pin blocks; connectivity/parity checks and selected gate reviews do not replace a readable whole-circuit review. | Digital engineering review |
| Finish target provisioning and application inputs | Implement factory calibration/NTC and commissioning-record loaders, boot nonce and operator POST service; connect actual ESP32 rail/interlock providers and application power demand. Reject absent, corrupt, mismatched and expired records. Existing validators and inhibited defaults are not the complete service. | Digital |
| Bound target execution | Set and verify STM32 option bytes/BOR/flash configuration; establish stack and worst-case scheduling bounds, including mirror ISR entry and GPIO settling. Distinguish measured execution from allocated timing. | Digital plus physical correlation |
| Complete installed electrical model | Extract defensible installed catch, cross-leg and shared-return geometry; include the actual sensor/filter delays, gate-driver/guard delays and contact interruption behavior. The separate native19 local matrices cannot be combined by filling missing terms with zero. | Digital and supplier data |
| Close protection coordination | Obtain applicable DC fuse/contact interruption data and qualify resistor/proof-load pulse energy, peak power, temperature and repetition over the full source window. Prospective I²t with an assumed conducting fuse is not clearing evidence. | Supplier data and engineering analysis |
| Close manufacturing interfaces | Establish applicable insulation requirements, harness/feedthrough/connector details, assembly and drilling tolerances, approved materials, hot clearances and actual rail/clip stack. The closed-bore catch guide requires threading before termination and does not provide qualified axial strain relief. Complete terminal restraint and metal-frame bonding decisions; qualify the dedicated sink bond and its permanent cradle stud. Nominal no-overlap CAD does not establish tolerance yield. | Digital and supplier data plus physical qualification |
| Establish the operating envelope | Measure actual coil/pan impedance and capacitor limits; qualify rail startup/load/thermal behavior, ADC/NTC uncertainty, contactor timing and mirror wetting. Do not adopt the old45A assumption as an operating limit. | Physical |
| Commission one unit before its siblings | Inspect the cold assembly, then follow staged electrical/thermal testing with reviewed four-gate oscilloscope records, shutdown/fault injection and exact hardware/firmware identities. Correlate the model before extending the operating range. | Physical |

The FPGA experiment is outside this list. It has no product dependency and
is not required to close any item above. A demonstrated measurement need
unmet by an oscilloscope or suitable timer capture must justify any resumption.

Current board-routing, packaging-export and joined-model receipt status is
recorded in the linked [integration overview](README.md), rather than assumed
complete by this checklist.
