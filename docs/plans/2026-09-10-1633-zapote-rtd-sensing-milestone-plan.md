# Milestone 2: standalone RTD unit and hardware fault interface
Created: 2026-09-10

Status: standalone design/layout milestone accepted. See the [coordinator acceptance](../../zapote/rtd/unit/ACCEPTANCE.md) for exact evidence and deferred physical, timing and procurement obligations. Full-cooker integration remains a later goal.

Updated by user direction, 2026-09-10: build and accept each unit separately
first; integrate units afterward under a separate goal. This plan now targets
the standalone RTD unit. Preserve prior full-cooker candidates and receipts as
historical work; do not continue their placement/routing under this goal.

Build the cooker's pan-temperature sensing unit as a standalone source-derived,
placed and routed KiCad artifact. Deliver the digital measurement interface
and local hardware fault output through explicit unit boundaries, using the
same Atopile → KiCad → agent edits → Rust validation flow.

This expands milestone 2 of the [overall roadmap](2026-09-10-1627-zapote-cooker-roadmap-plan.md).
It is a hardware delivery plan with validation work, not a claim that the
circuit, harness or hardware has already passed. Buck/MCU interface contracts
and lessons are inputs; their integration into this board is not a prerequisite.

## Replacement goal text

Complete the standalone RTD pan-temperature sensing unit first. GPT-6 Astra/high
owns placement/routing through the existing KiCad adapter; delegate circuit,
models, Rust validation and evidence tasks to Luna. Check the circuit and
interfaces, generate the unit from Atopile with exact source/pin/pad/net identity,
place and route its own board, use actual Rust feedback to correct it, and verify
the saved unit with Rust and native KiCad checks plus meaningful deliberate
defects. Deliver the exact BOM, bounded fault/reference/power/SPI contracts,
reproducible evidence and reviewed reusable lessons. Preserve prior integration
work but defer buck/MCU/full-cooker composition and cross-unit routing to a later
integration goal. Physical testing remains explicitly NOT RUN unless performed.

## What is in the section

The source04 standalone checkpoint contains 36 components and 119 electrical
pads, including the unit interface connector, separate supply bypasses and
protected comparator branch. Its complete source-to-native identity comparison
is retained under `zapote/rtd/unit/evidence/root-source04-identity/`. Reconcile
the final inventory from the accepted source manifest; this checkpoint is not
the final frozen BOM.

| Circuit group | Role and current starting point |
|---|---|
| Four-wire PT100 interface | JST XH four-pin header, separate force and sense conductors, MAX31865AAP+ and 430 Ω precision reference resistor. Include the mating harness pinout and probe requirements. |
| Measurement and MCU interface | Local supply filtering/bypassing; SPI clock/data/chip-select series resistors; DRDY connection. Reuse the existing MAX31865 firmware/service. |
| Hardware fault detection | REF2025 reference, two TLV3201 window comparators, TPS389001DSER rail supervisor, AND/open-drain NAND logic and pull resistors. Source04 uses the TPS389001 replacement after the original TPS3700 divider failed the upstream-voltage contract. The supervisor and fault NAND use upstream power; the window comparators use the filtered rail. Final acceptance must establish active-high `RTD_HW_FAULT` behavior under the declared power-loss conditions. |
| Shared reference interface | REF2025's 1.25 V output serves the local window; its 2.5 V output also feeds the later OVP and OCP2 circuits. Account for both consumers and the physical route reservation. |

The revised hardware window observes local `RTDIN_P` through a shared 100 kΩ
resistor, with the LOW threshold's bottom leg returned to `RTDIN_N`. Paired
diagnostic pulls and the differential capacitor terminate at the ADC sense
pins. The earlier `REFIN−`/`ISENSOR` window missed isolated sense-wire opens;
retain that failure as a counterexample, not as the current circuit definition.
Final acceptance must cover each conductor separately with the actual revised
network. The digital path provides conversion and device/cable diagnostics.
Neither path alone establishes complete cooker protection.

## Interfaces and boundaries

| Interface | Milestone 2 obligation |
|---|---|
| Upstream 3.3 V and ground | Provide an explicit standalone supply interface; honor the declared voltage/current envelope and local filtered rail. Preserve upstream versus post-ferrite ownership. Actual buck connection is deferred. |
| `RTD_SCK`, `RTD_SDI`, `RTD_SDO`, `RTD_CS_N`, `RTD_DRDY` | Route to the unit interface connector; reconcile its pinout with the source, schematic, PCB and host firmware contract. Actual MCU-board copper is deferred. |
| External probe | Header pins 1–4 are FORCE+, SENSE+, SENSE−, FORCE− in current source. Verify physical pin numbering, cable mating orientation, separate conductors and probe/cable assumptions. |
| `RTD_HW_FAULT` | Validate the local output's polarity, pull-up rail, loading and fault behavior at the unit boundary. Name the future safety input without claiming a routed connection to it. |
| Shared 2.5 V reference | Provide one named reference output and a load budget accounting for future OVP/OCP2 consumers. Their physical connection is deferred. |

Use a real, explicitly identified low-voltage unit/test connector alongside the
four-wire probe connector. Record its exact part, pinout and harness assumptions;
distinguish this standalone carrier interface from final product interfaces.
Preserve stable source identities to support later composition. Deferred external
loads are contract inputs, not fake connected components or suppressed opens.

Source04 uses the unshrouded Samtec FTSH-105-01-F-D as `unit_io`. Pins 1–10 are
`+3V3`, `gnd`, `gnd`, `RTD_SCK`, `RTD_SDI`, `RTD_SDO`, `RTD_CS_N`,
`RTD_DRDY`, `RTD_HW_FAULT`, `SHARED_REF_2V5`. The two ground contacts are one
electrical net. The interface is not mechanically keyed; the harness drawing
must identify pin 1 and mating orientation explicitly.

The later safety unit owns latch/reset/shutdown behavior; the separate integration
goal owns cross-unit composition. This unit checks its RTD contributor. Full-chain
simulation remains supporting evidence and does not establish physical timing.

## Work sequence

### 1. Reconcile the existing design and freeze its contract

Use current source, generated identities, firmware configuration, datasheets and
retained evidence. Preserve working circuitry; resolve discrepancies before
freezing placement inputs.

- Define the required temperature range, measurement-error allocation, probe
  tolerance, cable conditions and update/settling timing. Allocate sensing error
  against the product's control-accuracy requirement; do not equate IC accuracy
  with pan-temperature accuracy.
- Separate normal operation, transition/guard regions and fault conditions.
  Firmware currently declares inclusive short/open boundaries of 10 Ω and 300 Ω.
  Derive actual hardware trip corners separately; document which faults each
  path covers and the response budget allocated to this section.
- Check reference topology, pin/package identities, supply operating ranges,
  local bypassing, input filtering, digital I/O during partial power loss, and
  probe-connector protection requirements. Every adopted numerical bound needs
  a source or an explicit engineering assumption.
- Check hardware-window behavior during normal MAX31865 bias/fault-detection
  cycles as well as startup. A local active-high fault level is only meaningful
  while its upstream pull-up supply is valid. Upstream supply loss needs an
  explicit downstream disable obligation, not a claim that an unpowered output
  stays high; milestone 3 owns that system-level response.
- Resolve the specific source/document gaps below. Select real orderable parts
  for any necessary corrections, preferring standard DigiKey/Mouser options;
  exact procurement snapshots belong with the resulting BOM.

**Output:** one circuit/interface contract, reconciled component inventory and
an explicit acceptance table. Missing information needed for a verdict remains
indeterminate until resolved; it is not filled with a convenient nominal value.

### 2. Produce the source-derived section and its validation inputs

Make necessary corrections in Atopile and component definitions, then generate
the section through the milestone 1 flow. Verify part → symbol pin → footprint
pad → net identity, including intended NC pins and physical connector numbering.
Carry the contract's supplies, net roles, sensitive regions and component
properties into the validator input. Generate RTDSensing and the explicit unit
interfaces into a standalone board, retaining stable identities for later reuse.

**Output:** generated schematic/PCB inputs, source manifest, exact parts and
interface mapping. Hand-edited CAD must not become an unrecorded source fork.

### 3. Extend the Rust checks before accepting layout

Reuse the working Zapote packages and actual Temper donor implementations.
Add the RTD-specific rules and missing input fields; retain copied tests and
provenance. Existing Python launchers and KiCad adapters may remain. New
engineering verdict logic belongs in Rust.

| Check family | Concrete proof or deliberate failure to include |
|---|---|
| Source and four-wire topology | Detect a swapped connector pad, an on-board force/sense short, a missing RREF connection, or an unintended ground on a sense node. |
| Power and component semantics | Distinguish upstream/post-ferrite rails; check operating limits and pull-up ownership. Treat the ferrite's impedance specification separately from DC resistance. |
| Firmware correspondence | Detect incorrect CS/DRDY GPIOs, incompatible device setup, or threshold words that use the wrong RREF/bit shift/rounding. Test inclusive boundaries and adjacent ADC codes. |
| Locality and return paths | Check actual bypass-to-supply/ground paths, reference/comparator placement, sensor routing and SPI resistor placement using documented constraints. |
| Noise and isolation | Apply authored sensitive-net/aggressor roles and domain boundaries to real copper. Test a sensor route through a switching region or a prohibited domain connection; do not rely on component names alone. |
| Fault behavior and corners | Cover valid resistance, short/open, each conductor open separately, local rail loss/brownout, upstream loss, startup and bias enable/disable. Classify which path detects each case and which remain uncovered. |
| Reference loading and error | Include both future reference consumers, RREF/divider tolerances, offset/drift, bias behavior, probe/cable assumptions and filtering effects in bounded calculations/models. |
| Evidence validity | Missing required inputs, an unregistered rule, stale model/source identity or a failed external tool must not become a zero-findings pass. |

Use positive, boundary and intentional-fault cases. Give each fault case an
expected detector/verdict; a known blind spot must remain an explicit coverage
gap. Reuse existing SPICE decks after checking their topology, values and model
scope against the revised source. Luna can build or extend a datasheet-based
model when needed. Record assumptions and validity limits; a behavioral model
is not a measured device or a substitute for unavailable physical evidence.

**Output:** executable RTD validation coverage and a defect corpus, connected to
the existing agent feedback loop. Do not expand this into a new validation
framework, editor, placer or router.

### 4. Let the agent place and route the standalone unit

Supply the accepted unit source/board context, applicable buck/MCU lessons and RTD
constraints. The agent makes explicit placement/routing decisions through the
working KiCad adapter and receives actionable Rust findings during correction.
Keep the probe/analog section away from declared aggressors and preserve access
for the safety/reference interfaces. Fix violations in the circuit, layout or
checker as evidence warrants; never relax a rule simply to finish a run.

Run the complete adopted unit suite on the saved standalone candidate, plus
independent native KiCad ERC/DRC and schematic parity checks in the correct
library/rule environment. Rerun affected shared validator/adapter regressions;
full-board buck/MCU routing regressions belong to integration. Keep future
aggressor/interface constraints explicit without claiming those absent sections
have been physically validated. Preserve attempts and outcomes.

**Output:** a routed standalone RTD unit, checks tied to its exact source,
board and suite identities, and a reviewable source-to-board record.

### 5. Close the unit goal and hand off its interfaces

Deliver an indexed bundle containing the accepted contract/BOM, source-derived
artifacts, standalone board, validation and model evidence, remaining downstream
obligations, and a low-voltage bench-test outline. Keep all unperformed physical
tests marked NOT RUN. Promote reviewed lessons and relevant counterexamples into
memory and tests for the milestone 3 agent.

Use bounded Luna owners for circuit/source work, validators/models and evidence.
GPT-6 Astra/high owns placement/routing. Circuit and validation preparation can
run in parallel after agreeing interfaces. Placement uses their accepted outputs. One coordinator
owns the shared input contract and the final combined acceptance; owners must
not concurrently edit the same files.

## Specific reconciliation work found during planning

- **Shared reference:** `components/REF2025/REF2025_Documentation.md` says VREF
  is unused; `elec/src/main.ato` connects it to OVP and OCP2. The documentation
  must follow the reconciled generated connectivity and loading contract.
- **Filter and open sense lead:** the original `RTDSensing` did not declare a
  capacitor across RTDIN+/RTDIN− or the optional RTDIN+-to-BIAS diagnostic
  resistor. The manufacturer describes input filtering/settling and warns that
  an open RTDIN+ lead can escape detection; it describes a 10 MΩ bias option.
  Resolve these against noise, leakage/error and individual-wire fault coverage
  before source freeze. Source-02 added paired diagnostic pulls and a capacitor;
  their fault timing and accuracy still require acceptance. Do not assume an RTD-element-open test covers every
  cable open. [MAX31865 datasheet, pp. 19–21](https://www.analog.com/media/en/technical-documentation/data-sheets/MAX31865.pdf)
- **Stale acceptance evidence:** the RTD safety document references property-test
  files no longer present at those paths in this checkout. Existing selected-value
  SPICE tests cover a few nominal cases; they are not the missing corner proof.
  Recover usable evidence or implement the required checks in Rust. Reconcile
  the documented no-false-trip guard region with actual analog trip corners.
- **Donor gaps:** `temper-drc-rs` contains an unregistered power-domain placeholder;
  its isolation-zone and noise-distance rules cover narrower questions than
  end-to-end galvanic isolation or measured immunity. Adopt concrete rules with
  sufficient inputs; do not credit a filename as coverage. Recheck historical
  HV/SELV-crossing warnings during the later full-board integration goal.

## Acceptance and next handoff

Milestone 2 is complete when the standalone RTD unit is source-derived and
routed, all mandatory unit checks pass on that exact candidate, required circuit
and model ambiguities are resolved, and its interface contract/BOM/evidence and
reviewed lessons are delivered. A required unit check that is missing or
indeterminate blocks acceptance. Actual MCU/buck/full-cooker connections and
full-board inherited debt belong to the later integration goal, not this gate.

The next agent receives working measurement-interface circuitry, a checked local
fault output and shared reference contract, executable checks and reviewed
lessons. Actual temperature readings, noise performance and shutdown timing
still require the later physical verification milestone. An evidence requirement
explicitly mandated before fabrication remains a fabrication gate even if it is
not required to finish this layout milestone.

## Source map

- Circuit: `elec/src/modules.ato` (`RTDSensing`), `elec/src/components.ato`,
  `elec/src/main.ato`; existing control interfaces:
  `pcb/blocks/control-assembly/interfaces.json`.
- Requirements: `docs/FUNCTIONAL_TEST_CRITERIA.md`,
  `docs/hardware/RTD_SAFETY_DUAL_PATH.md`, `docs/CONNECTORS_AND_WIRING.md`.
- Firmware: `firmware/config.yaml`, `firmware/tools/board_derivations.yaml`,
  `firmware/components/sensors/`, `firmware/test/test_max31865.c` and
  `firmware/test/test_main_max31865.c`.
- Retained simulations: `elec/validation/rtd_window_selected_values.cir`,
  `rtd_window_ported_models.cir`, `rtd_fault_latch_transient.cir.in` in the same
  directory, their test launchers, and `simulation/models/`.
- Rust donor candidates: `packages/temper-drc-rs/src/rules/` and
  `packages/temper-design-bundle/src/`; adopt only verified applicable behavior.
- Memory: `docs/solutions/architecture-patterns/dual-path-rtd-fault-containment-2026-07-13.md`,
  `docs/solutions/best-practices/claimed-isolation-vs-actual-connectivity-2026-07-26.md`,
  and `docs/solutions/workflow-issues/firmware-hardware-pin-map-divergence-2026-07-14.md`.
