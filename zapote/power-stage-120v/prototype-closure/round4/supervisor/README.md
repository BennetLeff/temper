# Joined independent supervisor — implemented source review

**An implemented, compiled circuit capture; not a fabrication or powered-test release.** This replaces the round3 block-only supervisor with component pins, nets, a typed native KiCad schematic, a compiler export, and executable fault-path checks. It does not claim that the full remaining digital design is finished.

The circuit authority is `circuit.rs`. It emits `generated/supervisor.ato`, `pins.tsv`, and a review BOM. `render.py` renders the pin table into the multi-sheet native KiCad project and checks the exported connectivity. Do not edit generated files. Native19 remains byte-identical, SHA-256 `3557aa444873fa8b45eb7e0ae8ec3a4bc2b5cd526826b338b58d50e57747430b`.

## What is now connected

- Upstream HDR-60-24 auxiliary supply, dedicated fused branch, 5 V converter and 3.3 V regulator. The MCU, ADC, analog reference and all six AMC3330 low-side supplies share 3.3 V. This removes a still-powered 5 V sensor-output path into an unpowered 3.3 V ADC. The independent 24 V supply remains upstream of both source contactors.
- Distinct K1 and K2 high-side TPS1H100 drivers and low-side MOSFET commands; separate switched mirror-contact excitation and readback. KB bypass and an actual G5Q proof-load relay have explicit coil and contact terminals. PE is unswitched. Contact opening and removal of stored energy remain different functions.
- Six independent voltage channels: upstream line, precharge branch drop, downstream line, bus, catch and resonant-capacitor voltage. Catch sensing is powered by AUX, references HV_RET, and has no connection to bleed midpoints, LEG_RET or the OCP Kelvin return. Tank sensing connects to native RES_A and SW_B.
- Talema AC1005 proof-load and AC1020 whole-inlet current channels with permanent dual burdens. Their signals are centered at buffered 1.25 V. Each secondary has a bidirectional SMCJ5.0CA clamp across its burden, and each inlet-current comparator input has its own 20 kΩ series limit. This removes the unprotected direct CT-to-comparator path. The ≤12 V raw-voltage bound gives <0.607 mA through a -1% series resistor, but that bound is conditional on the TVS/CT/reference system remaining within its qualified waveform and temperature. The TVS 1500 W rating is for a specified short pulse; it is not a 500 ms fault-energy rating. ADC/reference-rail injection, TVS dissipation, CT saturation and low-current calibration remain unqualified.
- Independent analog bus/catch/tank/current/24 V and resistor-temperature comparator chains, joined to STOP, watchdog, supply monitors, isolation diagnostics and the MCU health input. Missing controller power cannot grant PERMIT.
- Hardware fault, attempt, precharge-complete, bypass-proven and run-armed latches; three one-shot windows; once-per-attempt proof trigger; independently RC-delayed total-timer arm; separate START and RESET; normally closed STOP. Restoring health does not automatically restore the fault latch or restart.
- ADS131M08 and exact STM32G071RBT6 package pins; SPI, ADC clock/reset, UART, watchdog, coil commands and feedback all have source bindings. There is **no guessed ESP32 GPIO mapping**.
- Dedicated isolated JCTRL, plus a separately isolated output intercept for existing native J4.9 PERMIT. The AUX rail is never tied to native J4.1. ISO7710F channels default low; the native fault channel uses ISO7710 without F, which defaults high.

## Controller interface

All JCTRL signals are 3.3 V logic referred to CTRL_GND on the controller side. CTRL_3V3 is supplied by the controller. It powers only the controller side of the isolators. There is no AUX supply pin on this connector. Physical connector footprints, mating cable, keying and pin-one inspection remain release work; the table is the electrical contract.

| JCTRL pin | Net | Direction relative to supervisor | Meaning |
| --- | --- | --- | --- |
| 1 | CTRL_3V3 | power input | Controller-owned isolated-interface supply |
| 2 | CTRL_GND | reference | Controller local ground |
| 3 | SUP_RUN_OK | output | High only after supervisor admission; does not itself request PWM |
| 4 | CTRL_PWM_REQUEST | input | High requests permission; low/disconnected removes it |
| 5 | CTRL_HEARTBEAT | input | Edge stream; MCU must qualify freshness, not merely high level |
| 6 | CTRL_FAULT_HIGH | input | High is fault; disconnected or unpowered transmitter fails high |
| 7 | CTRL_TX | input | Framed request stream to supervisor UART RX |
| 8 | CTRL_RX | output | Supervisor UART TX; invalid/truncated packets convey no permission |
| 9 | CTRL_RAIL_OK | input | Explicit controller/native rail qualification |
| 10 | CTRL_INTERLOCK_OK | input | Independent high-healthy interlock observation |

J_PERMIT.1 is NATIVE_PERMIT; J_PERMIT.2 is CTRL_GND. Route it to the existing J4.9 input through a reviewed inline harness, disconnecting the former direct drive. There must not be two push-pull drivers. The public firmware `energy_link` framing and portable energy sequencer live under `firmware/components/power/`; this capture does not flash or implement their STM32 target port.

STM32 pin bindings are exact and machine-readable in `generated/pins.tsv`: PA4/5/6/7 use SPI1 CS/SCLK/MISO/MOSI; PA0 receives DRDY; PA1 controls ADC reset; PA8 provides MCO; PA9/10 provide UART TX/RX; PA13/14 expose SWD. PA2/3 receive the two resistor NTC voltages through separate 1 kΩ/1 nF acquisition filters, and PA11 reads CTRL_INTERLOCK_OK_LOCAL. The NTCs are explicit external components, separate from their terminal blocks. The STM32 ADC sampling time, conversion/calibration and cold-restart temperature qualification still need the target port. Target startup, alternate-function setup, clock configuration, interrupt/DMA behavior and option bytes remain to implement and test. MCU pin typing is bidirectional for GPIO because direction is configured by that missing target program.

## Admission and timing

The target binding must map portable `hardware_ok` to BASIC_HEALTHY and `hardware_latch_ok` to LATCH_OK; these are different signals. Boot self-check and fresh ADC/watchdog acquisition must establish MCU_HEALTHY independently of the latch, otherwise the software creates a circular startup dependency.

The initial hardware latch is clear. A qualified physical RESET clocks the fault latch only after the MCU has checked discharge, operator release, valid fresh POST and health. Then a **separate fresh START** begins an attempt. In this guarded prototype pod, MCU_STOP_DONE deliberately clears the hardware latch after **every** completed attempt, including ordinary OFF. Every new attempt therefore requires another eligible physical RESET, fresh START and fresh POST. This is the external engineering-test protocol, not the intended finished-cooker interaction. A software OFF state alone does not arm the circuit. The portable firmware now requires hardware_latch_ok before START, drops active output on latch loss, and provides reset_ok only after an eligible physical RESET release. The actual STM32 binding must still observe LATCH_OK and ATTEMPT and map reset_ok to MCU_RESET_OK and fresh-start qualification to START_RELEASED; a restored stale POST is never valid.

The TPS3820 watchdog is the 112–300 ms family member, not the approximately 1.6 s TPS3823 variant. The WDI pulldown is 1 kΩ: the device's possible internal 190 µA source cannot float WDI high and disable the watchdog while the MCU resets. Startup must arrange a valid feed before the minimum interval; feeding from an unrelated free-running interrupt would defeat program-health supervision.

| Hardware window | LTC6993 RSET / DIV | Nominal duration | Upper allocation at +5% |
| --- | --- | --- | --- |
| Cold precharge | 54.2 kΩ / 6 | 284.164 ms | 298.372 ms |
| Entire start-through-proof | 81.1 kΩ / 6 | 425.198 ms | 446.458 ms |
| Proof-load energization | 140 kΩ / 5 | 91.750 ms | 96.338 ms |

These are component calculations and a provisional error allocation, not measured contact times or a completed worst-case timing proof. A maximum proof pulse near 96 ms cannot also promise a **minimum** 96 ms observation period. The portable energy core now distinguishes 50 ms of continuous measured proof from the 96 ms phase deadline. A host case includes 20 ms of relay pickup plus the proof interval; it does not measure the selected physical relay. Relay pickup/release, suppression, input filtering, comparator delay, one-shot limits, RC arm and flip-flop recovery/removal must be joined into the final timing budget. Normal stopping intentionally clears the latch through a dedicated STOP_DONE_N gate, rather than relying on retention during the RC disarm tail. The 2 s rail-qualification deadline is presently a firmware responsibility.

The capture retains the round3 two-parallel-HS200-22Ω / 11Ω branch. It does **not** authorize that resistor's unverified pulse duty. Round4 fault-model work is evaluating a different HS400 pair. Do not mix candidate resistor values, POST limits or mounting drawings. The 88Ω proposal was rejected by joined-filter behavior. Admission must use the joined model's crest-aware VPRE qualification: filter reactive current makes a whole-waveform 5 V peak-drop criterion inappropriate.

## Sensing and analog limits

The bus and catch input dividers are each 8 × 249 kΩ plus 2.49 kΩ (801:1), with a 1 nF lower-leg capacitor. At 600 V the entire divider draws approximately 300 µA and dissipates 180 mW. The ladder's eight resistors, creepage, transient distribution, high-side filtering and input protection need a routed design review. The current 60 × 35 mm catch-sensor reservation contains no completed PCB layout. The carrier owner places its 14 mm total thickness envelope at world X103–117, Y348–408, Z43–78 mm after clearing guard/fastener conflicts; these are allocated bounds, not a verified populated board. J_CATCH_REMOTE and J_CATCH_POD define both ends of a six-conductor SELV cable: pin1 POD_3V3, pin2 AUX_0V, pin3 VCATCH_P, pin4 VCATCH_N, pin5 VCATCH_DIAG_N, pin6 AUX_0V. Route supply/return, differential outputs and diagnostic/return as three pairs. This cable never carries the high-voltage catch feed. Its length, voltage drop, EMC/filter settling and exact mating assembly are still to qualify.

Line, VPRE and VOUT use 4 × 249 kΩ plus 4.02 kΩ. Tank sensing uses 12 × 249 kΩ plus 1 kΩ, directly across RES_A/SW_B; its approximately 2989:1 scale is a sensing allocation, not permission to operate at 2 kV. The AMC gain is two; paired output dividers halve both outputs for the ADC. All AMC isolated supply outputs have the manufacturer's local decoupling; their internal low-side LDO does not supply external circuitry.

Provisional comparator set points are approximately 230 V bus, 250 V catch, ±1000 V tank, ±22 A instantaneous inlet current, 20–30 V AUX, and a resistor NTC window. They are guard candidates, not operating limits. Peak current comparison does not enforce 15 A RMS. The full tolerance stack, reference drift, ADC calibration, phase/frequency response, common-mode behavior and diagnostic coverage remain digital engineering work.

Each DIAG channel has its 10 kΩ pull-up on the sensor and a 47 kΩ pull-down at the pod input, so an open diagnostic conductor has a local low default. The source test includes resistor and input-leakage corners; it does not prove arbitrary multi-wire fault coverage.

**DIAG does not prove the divider or measured voltage is correct.** It monitors AMC supply behavior. An open top resistor or frozen in-range output can evade it. The portable energy core now requires explicit catch_charge_proven before READY and trips on its loss in READY/RUN. The predicate must come from synchronized bus/catch charge correlation to detect an open catch fuse/diode; a catch voltage near zero is not healthy merely because it is below 250 V. Numerical discrepancy limits must include diode drop, measurement error and line phase. Divider injection tests, stuck-channel detection and a deployed freshness/CRC-aware ADC driver are not implemented here.

ADS131M08 is limited to 32 kSPS. This design cannot use it to claim validated 20–60 kHz tank waveforms or ZVS timing. The separate full-bridge capture contract needs a suitable fast acquisition path and actual target binding. The analog tank comparator is an independent guard, not a substitute for that measurement.

## Replay and evidence

Use Rust, Python 3, KiCad 10.0.4 and the repository-compatible Atopile 0.2.69 environment:

```sh
ATO_BIN=/path/to/ato ATO_PYTHON=/path/to/atopile/python ./replay.sh
```

`ATO_PYTHON` must have Atopile installed; it is used by the existing `tools/circuit_export.py`. No package install or physical board modification occurs. Output is under `output/temper-prototype-closure/round4/supervisor/`.

- Rust structural checks reject duplicate pins, incompatible output shorts, wrong source enables, fault-clear bypass and forbidden catch/control supply nets.
- Rust logic tests traverse the actual source-connected gates and asynchronous latch clears. Positive healthy-running tests prevent an all-off fixture from making every fault test pass. Mutation tests deliberately bypass a guard and verify that the oracle detects it. The tests do not simulate latch clock edges, analog transients or vendor propagation delays.
- Atopile is compiled independently, then every connected pin and every resolved per-instance MPN/footprint is compared with the Rust output. Atopile 0.2.69 can alias `libsource` identities for components with the same footprint: use `resolved-components.json` and the review BOM for identity, never a `libsource` label.
- Native KiCad exports every connected pin for an independent exact comparison. Typed ERC warnings remain recorded, including external/missing footprints and isolated-domain ground naming. No unconnected-label warning is accepted by the replay report. A zero ERC error count is not a layout, part, timing or safety approval.
- Some descriptive references do not end in numbers, so KiCad emits an annotation warning. They are stable review identifiers, not placement-ready refdes. Renumbering requires a source-level mapping and replay, not manual auto-annotation of generated sheets.
- `evidence.json` records counts, warning dispositions and full SHA-256 hashes. `replay-status.txt` starts as INCOMPLETE and becomes PASS only after every command succeeds. Inspect the final evidence rather than copying an earlier count.

## Remaining work, separated by evidence type

**Digital work still required:** complete independent analog/fault-design review beyond the initial pinout and sequencing review recorded in `review-disposition.md`; STM32 startup and driver port; deployment of the portable sequencer and packet protocol; cold-reset/post ownership; sensor injection/ADC validity/catch-charge qualification; fast bridge capture and controller pin binding; final component tolerance, rail budget and analog timing analysis; power-up/power-down/backfeed SPICE or equivalent analysis; source-contact suppression and weld/fuse/protection coordination; finalize the inlet resistor/POST choice with the joined model; exact cable connectors and HV terminations; routed supervisor/sensor boards with clearance, creepage, thermal and EMC review; and fabrication/assembly exports. These are not blocked solely by unavailable hardware.

**Physical evidence still required:** purchased-part drawing/marking checks, cold harness/mockup fit, contact timing, watchdog/power-ramp/fault injection, divider calibration and insulation, actual coil/pan characterization, installed thermal/EMI measurements and staged first-unit testing. No unassembled sibling unit should be treated as qualified by these digital checks.

The LD1117 3.3 V stage is sized for approximately 0.65 W at a 350 mA design load and therefore needs deliberate copper/thermal analysis. Its actual load includes six isolated converters, ADC, MCU and logic; the 5 V converter is rated 0.5 A. Load totals, derating and regulator stability are not yet released. Neither a nominal part-current sum nor a zero ERC error count closes this.
