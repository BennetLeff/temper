# Rev38 implementation status

This file tracks the approved plan without changing its requirements.
The branch is an engineering candidate. **U4-U7 and the Definition of Done
are not yet complete.** No protected-operation or mains-build claim follows
from the current host tests or partial netlist.

`INSULATION-BASIS.md` records the new native-layout dependency: Rev38's
409.307 V maximum static bank regulation crosses the older cooker's 400 V
creepage-row boundary. The provisional PD3 reinforced screen is 16.0 mm
on Group IIIa board material and 12.6 mm on a qualified Group I package
surface. The current DWW pair specifies >14.5 mm external package paths,
but PD3 application and board land-to-land construction remain open. The
product-standard/voltage/construction decision remains open; no native
rule-file or DRC PASS is claimed.

| Unit | Current evidence | Remaining gate |
| --- | --- | --- |
| U1 | `response-contract.md`, `fault-response.tsv`, and `timing-analysis.md` establish the bounded-reset candidate and per-fault missing-input ledger. The event ledger identifies the Rev38 producers now joined and separates their connectivity from unproved capture. The timing companion maps every event to allowable/implementation input owners and evidence class; the AUX-source alternatives and startup-load decision gate are explicit. | Independently support allowable and worst-case implementation bounds, margin, and applicability using the joined circuit and real power-stage envelope. Numerical acceptance OPEN. |
| U2 | `receiver-selection.md` selects AVR64DA32-E/PT and assigns physical pins; journal format and exhaustion behavior are host-tested. The default locked target image builds with official avr-gcc. | Fuse image and device NVM/BOD/boot-pin verification; measured target timing and a nonzero-window programmed-device build. |
| U3 | `model.rs` and `protocol-tests.rs` cover the logical session, fault, deadline, and reset controls. | Recheck model against the eventual joined source and native circuit; logic tests do not prove physical pulse capture. |
| U4 | The joined Atopile candidate includes a 16-contact Rev38-side port for the existing cooker ESP, TCA6408A-Q1 expander, active-low START switch, source authority, both isolators, AVR receiver, watchdog, rail/fault detectors, driver, PFC, fused-board AC input, AUX branch loop, IRM-20-24 raw source, LMR36015BRNXT 15 V pre-cutoff converter, LTC4368/FDS3992 protected-AUX cutoff, and TPS54202 HOT logic5 converter. All three supply stage builds and `integrated` compile; `audit.rs` passes 147 exact-pin, BOM-identity, footprint and mutation tests. A separate `cooker-mate` derivative compiles the mating header joined to the existing cooker ESP and rail; its BOM has one ESP, and `build.sh` checks the exact pad map, power source/return chain, and supervised reset/interlock producer pins with the shared Rust audit. `SOURCE-RESET-INTERLOCK.md` records the new producer circuit and candidate GPIO14 open-drain owner; the Rev38 test-image target link passes, while programmed-pin and physical gates remain unresolved. `PIN-INTERFACE-CONTRACT.md` is the common map. The regulated 24 V route is the digital engineering candidate; direct IRM-20-15 remains a bench comparison. `SELV-SUPPLY-LOAD.md` inventories the added loads without crediting unproved cooker-rail headroom. | Qualify the candidate Rev38 3.3 V port supply/load/startup and fail-low behavior for the existing cooker ESP command source; measure GPIO14 open-drain ownership and reset/interlock behavior at physical pins after the source-task target link. Document F1/inrush/thermal qualification as open; establish the electrical corner inputs needed for native design, including AUX/logic5 load and startup, cutoff FET SOA and fast-fault peak, and expander retained-output and pulse timing. Physical acceptance remains separate. Physical captures are NOT RUN; U4 remains OPEN. |
| U5 | The receiver protocol, journal, core, runtime and host pin sequence tests pass. An AVR64DA32 fuse-readback guard rejects the default image before runtime; the internal watchdog is serviced only after completed receiver ticks. The adapter compiles and links with Microchip avr-gcc 15.1.0 for AVR64DA32; `receiver-firmware/README.md` records both the 16,050-byte locked-image build and a separately named 16,594-byte engineering-window image. `receiver-firmware/ENGINEERING-WINDOWS.md` records transport arithmetic, unmeasured timing hypotheses, exact profile and ELF hashes; the default remains locked. | Select and program exact WDTCFG/BODCFG/SYSCFG0/OSCCFG bytes, verify UPDI readback, pin/reset/rail behavior, clock accuracy and watchdog period on device; derive accepted nonzero timing windows. U5 remains OPEN. |
| U6 | Source core/runtime, ESP32 adapter and host tests pass. The source task owns the candidate direct STOP, heartbeat, permit, UART, START and I²C pads; zero target timing bounds retain lockout. RTD sample generation and cooker control epochs are exposed for progress checks. The board-backed cooker I/O module initializes ADC1 channels, checks calibration, converts the nominal heatsink NTC and requires a fresh MAX31865 POST; invalid temperature or non-finite bus current cuts hardware. The full host suite passes **18/18 CTest**. Earlier diagnostic and `TEMPER_REV38_TEST_IMAGE=ON` ESP-IDF images linked. With the user's Docker approval, the changed normal cooker image compiled through `cooker_board_io.c` and the state machine, then failed at target ELF link on **26 remaining genuine cooker functions** (`ESP-TARGET-COMPILE.md`). | Implement the remaining PWM/power, current, fan/UI, logging, low-power and POST hooks from the real board; then link and run the normal target. Qualify ADC transfer/3.3 V rail, independent idle/heating monitor progress, UART final bit, expander P1, WDI feed tail, reset and partial-power pins, and physical reset-to-off. No Rev38 WDI or START is enabled; U6 physical and production acceptance remains OPEN. |
| U7 | No accepted Rev38 native section exists. `source-build-06` freezes **296 references**, including separate Würth F2 studs, the off-board F2 declaration, the DWW isolator pair and the 16-contact port. Rust audit passes **147/147** tests; the cooker mate receipt audit passes. `placement-review/03/` saves a 295-footprint functional-region diagnostic with 275 moved poses relative to the earlier shelf board. Exact 1,052-edge source parity, zero ERC, zero non-routing DRC, zero schematic parity issues and zero library-footprint mismatches pass. Its provisional six-layer 1.8 mm stackup passes the Rust CAD consistency gate and is manifest-hashed; this is not a fabricator or insulation approval. KiCad caps the unrouted board at 499 unconnected items. No routes, zones or slots exist. The provisional 16 mm cross-domain screen still fails at the 15.2 mm DWW opposed pads. The prior seven-finding diagnostic remains in `NATIVE-DIAGNOSTIC-09.md`. Physical captures remain NOT RUN. | Review all poses and mechanical access, complete routing and a net-pair insulation rule coverage test, then run source/native parity, ERC/DRC, stackup and unit gates on the saved section board. Qualify SELV supply/connector, F2 studs, DWW barrier, current/thermal construction and physical captures separately. U7 remains OPEN. |
| Follow-on product power boundary | `POWER-ASSEMBLY-BOUNDARY.md` traces the two frozen sources: the cooker `Top` import retains an older fused AC doubler and half-bus-fed SELV source, while Rev38 has a separate inlet/PFC/bank. The 16-contact contract connects only SELV control and 3.3 V. | Keep the later one-front-end cooker product claim open until its SELV supply and inverter power joins are specified and audited. This does not gate the Rev38 native section. |

U6 now has a separate `TEMPER_REV38_TEST_IMAGE=ON` source entry that starts
the actual ESP Rev38 service under zero timing lockout. Its full ESP-IDF
target link passed after Docker became available; see `ESP-TARGET-COMPILE.md`.
The default diagnostic image still does not run that service. Programmed-pin,
reset, UART, watchdog and fault timing acceptance remains OPEN.

The refreshed U1 ledger records an independent overcurrent decision: the
joined UCC28180 peak-current limit ends an active PWM cycle but has no
retained HOT-clear output. If the derated switch, inductor and interconnect
energy envelope requires latched overcurrent shutdown, U4 must add a physical
producer and the audit must trace it. F2 opening also needs a separate bound
from opening to its first observable threshold; comparator speed after that
threshold cannot establish detection coverage when VD and VB begin equal.

For follow-on product work, the direct-bank join audit in `POWER-ASSEMBLY-BOUNDARY.md` identifies the
legacy cooker's doubler midpoint as a separate tank-current return, active
discharge node and auxiliary-source input. The Rev38 single bank has no such
node. A wire-only bank join or PFC setpoint change cannot preserve that
inverter topology. The existing `cooker-mate` remains a pin-contract fixture,
not the one-front-end product source. The Rev38 section-board gate proceeds independently with a defined SELV command and supply port.

The diagnostic ESP-IDF image was rebuilt after Docker became available and
now links the current RTD freshness-status and control changes. The Rev38
source-task test image also links current target code. Exact hashes are in
`ESP-TARGET-COMPILE.md`. Neither image has a device boot or pin capture; the
cooker production image still fails at final link on missing production hooks.

The source watchdog feed uses the spare SN74LV221A-Q1 rising-trigger channel
and the receiver relay gate requires both AVR PA2 and retained HOT RUN Q.
Those default-off joins pass digital audit. A boot/other-core rising WDI edge,
expander-retained relay request, one-shot rail collapse, and the last possible
post-reset WDI edge remain unmeasured. Their reset-to-off timing is OPEN.

The cooker-mate derivative now has digital reset/interlock producers on
pins 14/15. Their supervisor, LVC gates and existing NAND latch have no
power-ramp or transient-fault capture. The source adapter releases GPIO14
as an input during boot. Its new candidate operation sinks GPIO14 only in
open-drain mode for one pulse per deliberate restart, with a bounded fresh
disarm sample before the edge and healthy physical readback afterward. A slow
UART drain, stale sample, failed pulse or second request fails closed in host
tests. The current restart-disarm API also requires
`safety_ok`, which contains the interlock itself, so it cannot acknowledge
disarm while the cooker fault latch is set. The source core and runtime now
expose a separately sampled, host-tested latch-reset eligibility predicate
that requires physical local/HOT PERMIT and HOT session low with rail good.
The source task now accepts one queued deliberate restart request, waits for
physical disarm, uses the one-shot latch reset only when required, and calls
`esp_restart()` after healthy disarm. No UI/operator caller exists. The changed
ESP32-S3 source-task image now links, but has no boot or pin capture; the 1 ms candidate
pulse has no measured maximum. Physical reset behavior remains OPEN.

The 2026-09-24 `make -C zapote check-units` rerun used KiCad 10.0.4's
`pcbnew` interpreter and reported six units INDETERMINATE and the maintained
`power-entry` unit FAIL. The runner now classifies the current `GBU2510A`
bridge's GBJ-bound loss/candidate obligations as INDETERMINATE while retaining
their required rule IDs; an unknown bridge identity still fails closed. The
remaining maintained power-entry FAIL is substantive: `WSL2726R0100FEA` is
an unsupported 10 mΩ/two-pad shunt identity, and four branch-copper findings
screen 15.0000 A nominal RMS against 10.4205 A at the saved 2.5 mm/70 µm
geometry and assumed 20 °C rise. These are findings on the separate
maintained GBU board, not a Rev38 native-board result. The plan preserves
the passive reference and does not authorize changing that board to make the
gate green. U7 digital acceptance remains OPEN.

`ESP-MONITOR-CONTRACT.md` records why an idle cooker cannot credit the
existing unconditional `run_safety_check()`. The control task now credits
only a completed nonfault state-machine handler; message-deferred and fault
ticks cannot advance its epoch. Cached RTD values still need an accepted
freshness bound, and the absent monitor result still prevents Rev38 progress.
The RTD service now exposes an atomic conversion generation and elapsed
monotonic `age_ms`, with invalid samples returning `UINT32_MAX`. Host tests
cover age growth, refresh, wrap and invalidation. The state-specific monitor
and its accepted age bounds remain absent, so no monitor epoch is credited.
The production cooker pan-temperature hook now converts the fresh PT100
sample and rejects missing or over-100-ms control samples. INIT waits for
the first conversion without crediting control progress; missing DRDY still
faults through the RTD service. The cooker clock hook uses ESP-IDF's monotonic
timer, and the diagnostic image's state-machine link anchor matches the new
return type. These changed target bytes have Rev38 test and diagnostic image
target-link receipts, but no cooker production image link or device capture.
`SELV-CONTROLLER-CONNECTOR.md` screens one 16-contact harness and pinout for
the selected shared cooker ESP. It is not a joined conductor or a measured
rail-budget claim.

`F1-SCREEN.md` nominates Eaton `LP-CC-20` with `BCM603-1P` and `CVR-CCM`
for a proposed dedicated-20 A, 10 kA prospective-fault-current residential
review envelope. The compiled board has a fused-L input and a separate AUX
branch loop, but neither off-board fuse assembly nor harness is built.
`F1-COORDINATION.md` maps each fault location to the actual exposed inlet
parts and the required maximum-clearing versus transient-withstand comparison.
The 20 A fuse remains intact for at least 12 seconds at 40 A, while the
selected CMC, bypass contact and NTC have 15–16 A continuous ratings. Their
transient withstand or an independent clearing path is unproved.
Whole-assembly fault, inrush, thermal, F2/MOV coordination and access remain
OPEN; the F1 matrix's physical rows are NOT RUN.

`AUX-CUTOFF-CANDIDATE.md` records the joined LTC4368-2/FDS3992/50 mΩ
selection. Its independent-resistor static screen gives OV recovery no lower
than 15.95075 V and rising trip no higher than 17.84409 V under the stated
assumptions. This does not bound a fast-fault output peak. The protected rail
has 30.6 µF nominal direct capacitance; valid-start current, effective MLCC
values, FET linear SOA and latch reset are OPEN. `HOT-LOGIC5-CONVERTER.md`
records the joined TPS54202 output network and its 46.5 µF nominal 5 V bank.
`AUX-WINDOW.md` identifies about 41.50 mA of nominal-resistance direct AUX
paths before active switching loads, not a maximum. The old 75 mA allowances
cannot be inherited. With nominal direct-bank inrush, the cutoff's
lowest screened startup trip threshold leaves only 0.410 A for overlapping
active startup loads. This conditional subtraction is not a proven margin;
the joined-load and FET-stress worksheet remains NOT RUN.
`AUX-STARTUP-CORNER.md` adds an illustrative selected-shunt TCR and
gate-cap initial-tolerance screen, reducing that conditional residual to
0.386 A before any effective-capacitance, active-load, fixture, or SOA
qualification. It is not a load allowance.

The selected supply parts and pin/interface contract now need native
schematic/PCB realization, source/native parity, ERC/DRC, and physical tests.
U1's per-fault timing ledger must use those measured paths. Do not promote
Atopile connectivity or host tests into U4–U7 physical acceptance.

`SELV-PORT-CONTRACT.md` now sets a candidate **3.0–3.6 V at Rev38 pins**
input envelope and **100 mA Rev38-port design allocation** for the existing
cooker ESP command source. It names the parallel supply/return pads, direct
startup capacitance, retained-expander and partial-power cases, and the
measurements needed to qualify the rail. The allocation is not a measured
port maximum, and the cooker's existing 3.3 V regulator has no accepted
headroom or startup proof. The native Rev38 section may use this port
contract for interface design; supply and fail-low acceptance stay OPEN.

## Parallel verification refresh (2026-09-24)

- **U5:** Both AVR64DA32 target profiles link with the official Microchip
  toolchain. New host cases cover STOP in READY before PERMIT first rises and
  receiver-only reset in RUN while modeled HOT latches remain powered; the
  focused receiver/runtime binaries pass. Fuse bytes remain review-only and
  the physical reset-interval pull-down has not been measured.
- **U6:** A sticky monitor-fault request reaches the sole ESP source owner;
  host tests inject it before PERMIT, WDI and START. The later board-backed
  ADC/NTC/RTD hooks and invalid-temperature hardware cut bring the host suite
  to **18/18 CTest**. The earlier ESP-IDF source-task image linked; the
  changed normal cooker source compiled but its ELF link still has 26 genuine
  missing hooks. No qualified idle/heating monitor or measured target response
  exists. Zero timing qualifiers retain lockout.
- **U7:** Current `source-build-06` has 296 references. The native preflight
  passes source, footprint and pin-map conversion, then stops at missing
  reviewed `poses.json`; the user-approved planning `outline.json` is 360 ×
  250 mm, but no reviewed section schematic or PCB was emitted. The
  bridge checks selected-MPN/BOM identity against the compiler's possible
  footprint aliases. A historical temporary flat schematic of `source-build-05`
  preserves 1,054 numeric pin edges across 296 references and 246 nets;
  that result is not a native-board pass or a functional pin-name audit. The joined
  Würth studs and DWW isolators retain review-only footprints. Stud fault
  and thermal withstand, package/board PD3 construction, and ISO6742F
  1.2 V rail-decay timing remain OPEN. See `NATIVE-BUILD.md` and
  `INSULATION-BASIS.md`. The earlier shelf diagnostic had seven local
  placement/silkscreen findings (`NATIVE-DIAGNOSTIC-09.md`). The later saved
  `placement-review/02/` shelf diagnostic clears those findings. The later
  `placement-review/03/` functional-region candidate moves 275 poses and
  retains zero ERC, schematic-parity and non-routing DRC issues, exact
  1,052-edge parity and a passing provisional CAD stackup gate. It remains
  unrouted, capped at 499 unconnected items. The 15.2 mm DWW opposed-pad gap
  still fails the provisional 16 mm screen. Thermal, assembly and isolation
  qualification remain open.
