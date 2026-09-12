# Standalone thermal sensing and protection

Build the next separate unit in the cooker roadmap: heatsink THM-01 and coil THM-02 temperature detectors. Preserve the existing TLV3201/resistive positive-feedback circuit and intended nominal trip/release points (85/70 °C and 120/100 °C), but expose real connectors for external lug NTCs instead of drawing them as PCB axial resistors. Two channels form this one thermal-sensing unit; the safety latch/interlock remains the next unit.

Inputs: external Vishay NTCALUG01A104GA sensor assemblies (100 kΩ at 25 °C, published beta/tolerances to be independently checked), 3.3 V host supply. Outputs: separate active-high hot flags and analog sense nodes on a six-pin host connector. Per-channel input filtering and local comparator decoupling. No fan driver, firmware integration, switching power or latch.

The source must compile in pinned Atopile, preserve an exact component/pin map into the native schematic/PCB, and use explicit agent-authored placement and route vertices. Reuse native Python/KiCad transport and Rust validation kernels; no new placer/router algorithm. A two-layer 1.6 mm board with local libraries, accessible connectors, normal return copper and readable schematic is the deliverable.

Rust must enforce complete source/native identity, pin-net topology and physical connectivity, saved-document/stackup/clearance checks, bypass locality and actual source-derived threshold calculations. Sensor model parameters, trip/release corners, comparator nonideal applicability and open/short sensor outcomes must be explicit. Use independent numerical evidence and defect controls, not tests that merely reproduce source constants. Exact NTC identity is an off-board interface/model requirement, not a fictitious PCB population.

Digital construction requires no hard findings in Rust or native ERC/DRC/parity. Device applicability, NTC beta extrapolation near 120 °C, mounting/thermal coupling, self-heating, input acquisition, power-off and physical tests remain INDETERMINATE/NOT RUN where unsupported. Do not treat an open sensor's cold indication as fault-safe; record the observed topology and the integration obligation. Bench acceptance and cooker integration are separate goals.

Preserve selected memory and actual worker prompts/responses, rejected attempts, source/runtime hashes, final reports and review. New lessons must be portable procedures, never automatic transfer of thresholds or component facts. Commit only this unit and necessary shared harness changes. The voltage project's pre-existing KiCad settings change is excluded from thermal construction.

Execution bounds: each delegated task has a UTC deadline and explicit owned paths; source/native edits are coordinator-owned. Worker Rust work uses an isolated worktree. End each bounded attempt with retained pass/fail/indeterminate evidence before deciding a new attempt. Completion review and canonical commits remain coordinator-owned.
