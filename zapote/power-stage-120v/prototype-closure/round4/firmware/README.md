# Implemented energy-sequence and full-bridge firmware core

**Source implementation and host tests; target binding remains disabled.** This
round replaces the missing application power hooks with one guarded service,
implements an independently deployable AUX-supervisor state machine, and adds a
four-output bridge planner and capture validator. It does not claim an ESP32
waveform, a flashed STM32 supervisor, or a characterized heating map.

The native19 board is unchanged. Its electrical source maps J4.5/6/7/8 to
PWM_HA/PWM_LA/PWM_HB/PWM_LB, J4.9 to PERMIT, and J4.10 to BUS_FAULT. Controller
GPIOs 4/5 in the old header describe a provisional half bridge; this work does
not invent the other outputs or borrow fan/sensor pins.

## What is executable now

- `firmware/components/power/energy_supervisor.c` owns OFF, PRECHARGE,
  BYPASS_CLOSE, BYPASS_PROVE, RAIL_QUALIFY, READY, RUN, DISCHARGE and latched
  FAULT. Execute this portable C on the **upstream AUX-powered supervisor**;
  the downstream ESP32 cannot initiate precharge before its supply exists.
- Separate START and RESET require release then press. RESET only reaches OFF,
  cannot process START in that call, and cannot energize. STOP/wire break, AUX,
  hardware permission, sensor validity, line/energy limits, rail/fault/capture
  failures remove all requested outputs. A graceful `off_request` opens source
  requests and enters DISCHARGE. Neither path automatically recloses.
  The circuit's LATCH_OK starts low: START additionally requires the actual
  `hardware_latch_ok` input. `reset_ok` qualifies the hardware MCU_RESET_OK
  output only after cold eligibility and observed physical RESET release.
  RESET held at boot cannot create a latch clock when eligibility later rises.
  Hardware reset and a separate fresh START are both required; dropping
  LATCH_OK during an active attempt removes source and gate requests.
  For this guarded prototype pod, ordinary STOP_DONE also clears LATCH_OK.
  Latch loss in DISCHARGE is expected, not an active-attempt fault; after cold
  eligibility returns the next attempt still needs physical RESET, fresh POST
  and fresh START. This is the test-pod protocol, not a released cooker interaction.
  Bind `hardware_ok` to BASIC_HEALTHY and `hardware_latch_ok` to LATCH_OK;
  boot self-check must establish MCU_HEALTHY without waiting for its own latch.
- Boot and fault impose a 60 s retry lockout. Reset/start additionally require
  three independently valid storage channels below 30 V for 1 s, released
  contactors, cool resistor and receiver proof. START consumes a new nonzero
  manual resistance-POST record serial. This serial and POST validity must be
  cleared/qualified by the supervisor owner at boot, not restored as an assumed
  successful test from an old session.
- Millisecond firmware timeout ceilings are conservatively rounded down from
  the round3 allocations: 298 ms precharge, 50 ms bypass close, 96 ms proof,
  446 ms total attempt, 2 s rails. The proof completes immediately after 50 ms
  of continuously valid measured loaded current **within** the 96 ms timeout;
  relay pickup is excluded from that interval. It does not require current at
  the 96 ms boundary: the hardware one-shot is nominally 91.750 ms and its
  provisional low corner is 87.16 ms. A late single true sample cannot pass.
  Hardware timers remain independent of this software loop.
  A separate `catch_charge_proven` input defaults false and must correlate
  synchronized bus/catch charging before READY/RUN. Healthy sensor rails and
  catch voltage below its upper limit cannot substitute for this predicate.
  The target owner must establish the diode/divider/error-budget threshold;
  an open catch fuse/diode with charged bus and near-zero catch must not pass.
- `fullbridge_adapter.c` generates balanced, fixed-frequency, phase-shifted
  four-output cycles using one common period. Both polarities have equal pulse
  area; each leg has positive non-overlap. A/B phase spans 0..half a period.
  It rejects invalid frequency, phase, nonfinite requests, missing/stale captures,
  wrong common-clock edge phase, frequency, pulse widths, or any of four measured
  non-overlap intervals. Zero/missing capture is never a pass.
- The conductance loop executes once per complete line cycle: requested/pan/
  inlet budget divided by line RMS squared, 2 Hz exact first-order update,
  2000 W/s upward limit, immediate downward/current correction, 13.5 A target
  and 15 A hard whole-inlet limit. Measured inlet current includes AUX, so it
  is not subtracted twice. No instantaneous bus-valley constant-power law.
- `power_service.c` now provides the production `power_enable`,
  `power_set_level`, `pwm_set_duty_cycle`, `pwm_disable_all`, and PWM-test hooks.
  Main calls its bootstrap and tick. Legacy pan detection cannot start an
  MCPWM timer directly; the 20 us ping is explicitly rejected. ESP-platform
  low-temperature burst control is inhibited. PLL cannot write timer periods
  outside the fixed-frequency service, and the old half-bridge HAL cannot
  initialize the gate channel. Fan-channel behavior remains in its existing HAL.
- `energy_link.c` defines a 20-byte big-endian v1 command/status frame with CRC32,
  monotone wrap-safe sequence checking, bounded fields and 20 ms freshness.
  Corrupt/truncated/duplicate/backward frames are rejected. Dedicated hardware
  heartbeat, fault and RUN_OK wires remain independent; this is not an authenticated
  or safety-certified bus. A receiver must remove permission immediately when
  parsing fails; rejected packets do not refresh the last valid sample.

`energy_study_config()` has `commissioned=false`, and the bridge also requires
an explicitly commissioned configuration. **Nothing in this tree binds those
functions to live outputs by default.** Study thresholds include a 2 kV tank
monitor range; that is not a released tank-capacitor operating limit. The 125 ns
MCU input deadtime and 50 kHz used in host stimuli are test parameters. They are
not the separate UCC21550 physical output-deadtime allocation or a release choice.

## JCTRL boundary with the supervisor circuit

The circuit owner's 2x5 JCTRL carries CTRL_3V3, CTRL_GND, SUP_RUN_OK,
CTRL_PWM_REQUEST, CTRL_HEARTBEAT, CTRL_FAULT_HIGH, CTRL_TX, CTRL_RX,
CTRL_RAIL_OK and CTRL_INTERLOCK_OK on pins 1..10 respectively. Connector pin
numbers are not ESP32 GPIO numbers. Fail-low isolated permissives and fail-high
fault receivers must prevent backfeed when CTRL_3V3 is absent. J4.1 remains the
native power-board output; no AUX supply is paralleled onto it.

`power_binding_t` is the explicit target integration boundary. A board owner must
supply all-or-nothing **atomic common-period** four-channel updates, request
inhibit, independent capture snapshots, qualified RMS/sensor data and a validated
conductance-to-phase map. `inhibit` must drop PWM_REQUEST first and then force
all four outputs low. Any failed operation latches the adapter until rebootstrap;
a software rebootstrap still cannot clear the independent supervisor/hardware
latches or start a new power attempt. Sequential raw comparator writes across
an active timer boundary do not satisfy `apply_cycle`.

## Verification

Fresh host CMake build and CTest passed all five selected executables:

| Check | Result |
|---|---|
| New adapter/supervisor/protocol suite | 10 assertion groups; 606 complete-cycle waveform sweeps |
| ESP-platform low-temperature burst path | Compiled with ESP_PLATFORM=1; always requests zero |
| Existing cooking state machine | 60 tests passed |
| Existing PLL | 24 tests passed |
| Existing state-machine integration | 30 tests passed |

The new adapter suite also passed AddressSanitizer and UndefinedBehaviorSanitizer.
It tests held START at boot, RESET/START collision, consumed POST, timeouts,
late proof, invalid/stale sensing, twelve RUN permission faults, every missing
non-overlap interval, a wrong leg phase, missing fourth capture, stale/duplicate
line estimates, NaN, backend error and 20 independently corrupted frame bytes.
All tests compile the production C core, not a duplicate model. The 114 existing
legacy tests still use their existing hardware stubs; they are regression checks,
not proof of the new target wiring. Existing config/transition manifests were
unchanged; their generated headers remain unchanged.

The supervisor circuit integration test additionally exercises cold LATCH_OK=0,
held RESET at boot, a physical-reset-to-fresh-START sequence, 20 ms relay pickup
plus 50 ms loaded proof completing before the one-shot's low corner, and an
open receiver signature (bus 170 V/catch 0 V) that times out with gates inhibited.
An additional stop/restart regression verifies ordinary OFF, intentional latch
clear during DISCHARGE, rejection of START before reset and of a consumed POST,
then acceptance only after a new physical reset/POST/START sequence.

Reproduce from repository root:

```sh
cmake -S firmware/test -B /private/tmp/temper-round4-firmware-build -DCMAKE_BUILD_TYPE=Debug
cmake --build /private/tmp/temper-round4-firmware-build --target test_power_adapter_only test_power_no_burst_only test_state_machine_only test_pll_only test_integration_only -j 4
ctest --test-dir /private/tmp/temper-round4-firmware-build -R '^(power_adapter_tests|power_no_burst_tests|state_machine_tests|pll_tests|integration_tests)$' --output-on-failure
```

`export-control.c` calls the real adapter to produce `conductance-study.csv`:
453 rows at 100/120/140 V, 1500 W requested/characterized study budget, 25 W AUX,
60 Hz line updates from 90 ms, with **assumed inlet feedback zero/below target**.
It supplies exact open-loop firmware command stimulus to the joined circuit
model. PWL injection alone does not implement simulated-current feedback or
validate its RLC-to-phase inversion. CSV regeneration was byte-identical.

## Remaining digital work, distinct from physical measurements

1. Assign and review the actual controller GPIO/connector map; implement and
   build the ESP-IDF shared-timer atomic commit/capture/transport binding.
   No ESP-IDF toolchain was available for a target build here. This deliverable
   is a tested portable four-output adapter, **not a deployed MCPWM peripheral**.
2. Integrate the portable supervisor on the circuit owner's STM32G071RBT6,
   with actual ADC qualification, manual POST record lifetime, watchdog,
   output drivers and framed-link task. Hardware capture does not flash this code.
3. Provide the characterized current/phase map and explicit pan-detection
   strategy that works without the prohibited burst. Until then both heat and
   legacy pan ping remain inhibited. Bound any adaptive map correction to the
   design's 20 Hz bandwidth; the current callback deliberately makes no claim
   to implement an unprovided pan estimator.
4. Correlate the exact control implementation, actual sensor sampling/latency,
   target scheduling and hardware permission paths in the coupled model.

Physical target captures, device limits, real pans, loss/thermal behavior and
fault interruption remain additional requirements. A host test does not close
any of those gates.
