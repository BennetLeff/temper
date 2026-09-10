# Milestone 2: pan-temperature sensing and hardware fault interface
Created: 2026-09-10

Build the cooker's pan-temperature sensing section into the accepted buck/MCU
board candidate. Deliver both the digital measurement connection and the local
hardware fault output, using the same Atopile → KiCad → agent edits → Rust
validation flow established in milestone 1.

This expands milestone 2 of the [overall roadmap](2026-09-10-1627-zapote-cooker-roadmap-plan.md).
It is a hardware delivery plan with validation work, not a claim that the
circuit, harness or hardware has already passed. Construction follows acceptance
of milestone 1; source review and preparation can happen earlier.

## What is in the section

The current `RTDSensing` source contains 30 component instances, excluding
interface objects. Reconcile that inventory during source review; it is not a
frozen BOM or a reason to retain a missing/incorrect component.

| Circuit group | Role and current starting point |
|---|---|
| Four-wire PT100 interface | JST XH four-pin header, separate force and sense conductors, MAX31865AAP+ and 430 Ω precision reference resistor. Include the mating harness pinout and probe requirements. |
| Measurement and MCU interface | Local supply filtering/bypassing; SPI clock/data/chip-select series resistors; DRDY connection. Reuse the existing MAX31865 firmware/service. |
| Hardware fault detection | REF2025 reference, two TLV3201 window comparators, TPS3700 rail monitor, AND/open-drain NAND logic and pull resistors. Produce active-high `RTD_HW_FAULT` with defined local supply-loss behavior. |
| Shared reference interface | REF2025's 1.25 V output serves the local window; its 2.5 V output also feeds the later OVP and OCP2 circuits. Account for both consumers and the physical route reservation. |

The hardware path observes the local `REFIN−`/`ISENSOR` node. It does not
independently diagnose every possible four-wire cable fault. The digital path
provides conversion and device/cable diagnostics. Neither path alone establishes
complete cooker protection.

## Interfaces and boundaries

| Interface | Milestone 2 obligation |
|---|---|
| Upstream 3.3 V and ground | Connect to the accepted control section; account for sensor/reference load and local filtered rail. Preserve upstream versus post-ferrite ownership. |
| `RTD_SCK`, `RTD_SDI`, `RTD_SDO`, `RTD_CS_N`, `RTD_DRDY` | Route to the actual MCU pads and reconcile Atopile, generated schematic, PCB and firmware pin definitions. Promote these from future obligations to checked connections. |
| External probe | Header pins 1–4 are FORCE+, SENSE+, SENSE−, FORCE− in current source. Verify physical pin numbering, cable mating orientation, separate conductors and probe/cable assumptions. |
| `RTD_HW_FAULT` | Validate the local output's polarity, pull-up rail, loading and fault behavior. Preserve its connection to the named safety input. |
| Shared 2.5 V reference | Publish one electrical net identity with both OVP/OCP2 consumers; resolve the source's two override-name assignments without inventing separate references. |

For downstream safety/reference endpoints already present in the accepted
candidate, verify and preserve their real connections. If those endpoints are
not yet admitted, record exact destinations, load assumptions and routing access
for milestone 3. Do not create dummy product connectors, fictional connections
or suppress unexplained opens to make a section look complete.

Milestone 3 owns the integrated latch/reset/shutdown chain. Milestone 2 defines
and checks its RTD contributor. Full-chain simulation can remain supporting
evidence; it does not advance milestone 3 or establish physical shutdown timing.

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
properties into the validator input. Map the section into the existing full-board
context with stable identities and an explicit replacement boundary.

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

### 4. Let the agent place, route and integrate the section

Supply the accepted source/board context, applicable buck/MCU lessons and RTD
constraints. The agent makes explicit placement/routing decisions through the
working KiCad adapter and receives actionable Rust findings during correction.
Keep the probe/analog section away from declared aggressors and preserve access
for the safety/reference interfaces. Fix violations in the circuit, layout or
checker as evidence warrants; never relax a rule simply to finish a run.

Run the complete adopted section suite and integrated regressions on the saved
candidate, plus independent native KiCad ERC/DRC and schematic parity checks in
the correct library/rule environment. Preserve all attempts and their outcomes.

**Output:** the combined buck + MCU + RTD candidate, checks tied to its exact
source/board/suite identities, and a reviewable integration delta.

### 5. Close the milestone and hand off safety integration

Deliver an indexed bundle containing the accepted contract/BOM, source-derived
artifacts, integrated board, validation and model evidence, remaining downstream
obligations, and a low-voltage bench-test outline. Keep all unperformed physical
tests marked NOT RUN. Promote reviewed lessons and relevant counterexamples into
memory and tests for the milestone 3 agent.

Use bounded Luna owners for circuit/source work, validators/models, and
placement/integration. Circuit and validation preparation can run in parallel
after agreeing interfaces. Placement uses their accepted outputs. One coordinator
owns the shared input contract and the final combined acceptance; owners must
not concurrently edit the same files.

## Specific reconciliation work found during planning

- **Shared reference:** `components/REF2025/REF2025_Documentation.md` says VREF
  is unused; `elec/src/main.ato` connects it to OVP and OCP2. The documentation
  must follow the reconciled generated connectivity and loading contract.
- **Filter and open sense lead:** current `RTDSensing` does not declare a
  capacitor across RTDIN+/RTDIN− or the optional RTDIN+-to-BIAS diagnostic
  resistor. The manufacturer describes input filtering/settling and warns that
  an open RTDIN+ lead can escape detection; it describes a 10 MΩ bias option.
  Resolve these against noise, leakage/error and individual-wire fault coverage
  before source freeze. Do not assume an RTD-element-open test covers every
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
  HV/SELV-crossing warnings against the accepted full-board source.

## Acceptance and next handoff

Milestone 2 is complete when the RTD section is integrated, all mandatory
section checks pass on that exact candidate, required source/model ambiguities
are resolved, and integrated regressions introduce no unexplained failures.
Explicitly inherited full-board debt and future endpoints remain named for their
owners. A required section check that is missing or indeterminate blocks acceptance.

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
