# Contact detection: firmware interlock and hardware qualification boundary

Status: **SIMULATION AND TEST PREPARATION ONLY. Hardware NOT VALIDATED.**

The production state-machine path now inhibits every cooking excitation unless
fresh independent contact evidence has passed release and acquisition checks.
There is **no physical detector backend**, no assigned GPIO, and no bypass that
assumes contact. On this board definition a cooking attempt fails closed.

**The proposed lower spring-seat force sensor plus plunger displacement is not a
qualified detector. A plunger jam after acquisition can preserve both readings
while the pan no longer touches the cap.** Startup release proof detects a
pre-existing stuck plunger; it cannot detect every later jam. Sensor agreement
is not proof of thermal coupling. Insulating debris can also transmit force
without useful thermal contact.

## Mechanical interface and candidate decision

The coordinated cartridge candidate uses 0.6 mm nominal protrusion, 1.2 mm
travel, a 0.2 N/mm spring and 0.15 N gross installed preload. Its tolerance case
with a recessed pan can leave only 0.10 mm depression. A sensor beneath the
spring seat would see a nominal load change of only 0.020 N in that case
(`0.2 N/mm × 0.10 mm`), before seal, friction and mounting errors.

| Candidate | Primary-source properties | Engineering disposition |
|---|---|---|
| Honeywell FSS005WNSX | 0–5 N uncompensated bridge; typical sensitivity 7.2 mV/V/N, repeatability 0.2% span, linearity 0.5% span; typical full-scale deflection 26 µm. | Bench force-characterization candidate only. Typical repeatability corresponds to 0.010 N and linearity to 0.025 N, comparable to the worst-case 0.020 N signal. These typical values are not guaranteed error bounds. Its datasheet exposure/temperature caveat does not qualify powered operation near a hot cap. Requires supplier clarification, calibration and thermal isolation. |
| Vishay TCST1103 | Transmissive phototransistor sensor, 3.1 mm gap, 1 mm aperture, typical 10–90% shutter path 0.6 mm; ambient rating −55 to +85°C. | Candidate for a dry, cool-zone return/travel flag. Custom vane edges need measured trip/release distributions; the aperture does not establish a 0.10 mm guaranteed motion threshold. LED modulation with off/on diagnostics can detect some wiring/optical faults, not a mechanically stuck vane. |
| TE FX29K0-100A-0010-L | 10 lbf range, 14-bit I²C output, ±1% full-scale accuracy, 0–50°C operating range. | Reject for this low-force in-product interface: ±0.445 N nominal full-scale accuracy is larger than the cartridge's expected force change. Suitable range matters more than ADC bit count. |

Sources accessed 2026-10-04: [Honeywell FSS datasheet](https://prod-edam.honeywell.com/content/dam/honeywell-edam/sps/siot/en-us/products/sensors/force-sensors/fss-series/documents/sps-siot-force-sensors-fss-product-sheet-080809-2-en-ciid-50137.pdf?download=false),
[Vishay TCST1103 datasheet](https://www.vishay.com/docs/83764/tcst1103.pdf),
[TE exact FX29 part](https://www.te.com/en/product-20009605-20.html).
These are evaluation candidates, not purchased, assembled or qualified parts.

A force detector intended to establish actual cap load must intercept the cap's
reaction **above all guide, seal, hard-stop and spring reaction paths**, while
maintaining electrical and thermal isolation. This requires a mechanical design
change and a qualified sensor temperature envelope; none is represented as
finished CAD or a fitted sensor. The optical channel can remain a travel and
return diagnostic. A force/position pair below the guide cannot meet that
requirement, regardless of debounce quality.

No force threshold is programmed from these nominal numbers. A later driver
must define conservative valid intervals from measured clean-contact,
no-contact/jammed and contaminated distributions. If those distributions overlap,
it must report unavailable rather than selecting a convenient threshold.

## Firmware contract

`firmware/main/contact_guard.c` accepts control-task-only, timestamped samples:

- `UNAVAILABLE` (including no backend), `FAULT`, invalid enum, stale, future or
  reversed samples invalidate evidence immediately.
- `RELEASED` must be a diagnostically valid, unloaded/returned observation. It
  must remain continuously sampled for 100 ms before a later loaded acquisition
  can qualify. Maximum accepted inter-sample gap is strictly less than 50 ms.
- `LOADED` means a future *qualified* detector's independent contact criteria
  passed. It must remain continuously sampled for 100 ms after release proof.
  RTD continuity, temperature and inductive pan presence are not accepted inputs.
- Age of 50 ms or more invalidates contact. An identical timestamp replay cannot
  refresh freshness; a contradictory sample at the same timestamp revokes it.
  Normal 32-bit millisecond rollover is supported within the bounded interval.
- Any release drops permission on that same update; there is no loss debounce.
  Acquisition delay is deliberately asymmetric. A transport or diagnostic fault
  requires new release proof, not merely another loaded sample.

The hardware driver is deliberately absent. Its eventual owner must preserve
acquisition timestamps, report sensor diagnostics and publish only from the
100 Hz control task before `state_machine_update()`. Calling the API from an ISR
or another task is outside the contract. A cached value with a renewed timestamp
would violate it. No pin or electrical interface is silently assigned.

## Control policy and recovery

The current firmware has temperature-controlled PREHEAT and HEATING states.
Intensity is a power ceiling within temperature control; no independent user
power-mode implementation exists. All such cooking and profile paths require
contact. There is no automatic fallback to power mode or to the liquid probe.

PAN_DET itself commands 5% excitation, so its **entry** is also gated. Contact
acquisition must be passive and possible in IDLE, independently of inductive
presence. Boot with a pan already depressing the probe requires unloading and
replacing it to establish release proof. An attempted start before qualification
latches the contact fault; no low-power excitation bypass is allowed.

`transition_to()` checks before active-state entry. `state_machine_update()`
checks before every active-state handler and before pending UI-message returns.
Thus PREHEAT, HEATING (including its <50°C PID branch), profile start and NO_PAN
resume cannot bypass the gate. The runaway boundary retains first priority.
Contact faults use the existing hardware-cut function, set power to zero,
disable PWM and PLL, log `FAULT_PROBE_CONTACT`, and cancel queued UI transitions.
Existing fault numeric IDs 0–13 are preserved; the new ID is 14, in an append-only
generator registry with a C regression.

Recovery of a contact reading never automatically resumes cooking. BUTTON_RESET
cannot clear this fault under the existing default fault-reset policy; hardware
reset/power-cycle, fresh release/acquisition and an explicit new START are
required. This is conservative simulation behavior, not a released interaction
design. Firmware does not claim a software reset can clear the external latch.

The separate low-temperature burst-controller component exists, but its calls
in production state handlers remain commented out. The tests cover the actual
low-temperature HEATING/PID branch and do not claim a connected burst-control
system. Similarly, output functions and several board services are unresolved
integration stubs in the wider repository; host tests verify the production
state-machine commands, not real gate-driver waveforms.

## Timing budget: specified, not physically measured

| Event | Firmware behavior with the scheduled 10 ms loop |
|---|---|
| Driver reports lost/faulty contact | Cut on the next `state_machine_update`, before any positive output command |
| Driver stops publishing | Cut at first update with sample age ≥50 ms (less than 60 ms after last sample with an on-time 10 ms loop) |
| New contact | ≥100 ms release proof followed by ≥100 ms loaded proof |
| Control task stalls | The 50 ms software deadline no longer holds; existing watchdog/hardware protection is a separate layer |

The sensor sample/diagnostic latency, scheduler jitter and physical cut latency
must be added. Neither a 10 ms physical cutoff nor a 60 ms real-system bound is
claimed. Acceptance before deployment requires timestamped acquisition and gate
observations under maximum CPU load and induction EMI.

## Prepared hardware tests, not results

Use the cartridge-validation and induction-validation workstreams for test
fixtures and safe procedures. Contact qualification must add these discriminating
cases to their logged input matrix:

1. Establish release and load, then jam the stem while removing the pan but
   leaving inductive pan presence true. A lower-seat sensor is expected to fail
   this discriminator. Record cap reaction independently above the jam location.
2. Repeat with seal drag, guide debris, side loads, hard-stop loading, thermal
   expansion and slow return at hot and cold conditions. Attack each reaction
   path separately; testing only a free-moving room-temperature plunger is weak.
3. Put thin insulating contamination between pan and cap. Record sensor evidence
   against reference temperature error/response. Establish whether mechanically
   loaded but thermally invalid cases can be distinguished. If not, that remains
   an explicit limitation and blocks claiming qualified thermal contact.
4. Disconnect/short each channel; freeze samples; replay timestamps; stick the
   optical emitter on/off; saturate the force frontend; expose optical paths to
   contamination and ambient light. Lost diagnostics must yield no permission.
5. During future induction testing, record force raw values, optical off/on
   samples, timestamps, pan-presence result, RTD value and commanded/observed gate
   state. Sweep power/frequency/pan alignment. Magnetic or electrical interference
   must not create believable fresh loaded evidence when actual cap force is zero.
6. Measure end-to-end latency with qualified acquisition timestamps and physical
   gate observation, including an intentionally stalled control task. Software
   tests do not qualify EMC, thermal drift, contact conductance or the hardware latch.

## Verification and reproduction

Base: `767f2fbae7a842e58afb288c5966453f10ab3d7a`. Native Astra subagent execution.
No baseline study simulation files, pinned PID/cascade sources, PCB, schematic,
or cartridge CAD were changed by this workstream.

```sh
uv run --no-project --with pyyaml --with jinja2 python firmware/tools/gen_fault_list.py
cmake -S firmware/test -B /tmp/temper-contact-build
uv run --no-project --with pyyaml --with jinja2 cmake --build /tmp/temper-contact-build --target test_contact_interlock test_fault_list_only test_state_machine_only test_max31865_only test_integration_only test_sil_fault_injection
/tmp/temper-contact-build/test_contact_interlock
/tmp/temper-contact-build/test_fault_list_only
uv run --no-project --with pyyaml --with jinja2 python firmware/test/test_sil_coverage.py --gate
```

Observed results, preserved in `evidence/`:

- 18 focused tests pass. One test iterates **300 state/timing combinations**:
  3 active states × 50 phases × reported-loss/missing-sample cases. Assertions
  include no new positive output command before shutdown, zero power, disabled
  PLL/PWM, hardware-cut invocation and logged contact fault.
- All **14 registered CTest suites pass**, including state machine, MAX31865,
  integration, contact, SIL, PID, cascade, low-temperature and hardware mocks.
  These binaries were built locally. Legacy state-machine suites mock contact
  valid as an explicit dependency; the dedicated contact target links the real
  guard and has an unavailable default. A legacy pass is not detector validation.
- SIL coverage: **23/23 designed fault×state pairs**, including new PAN_DET,
  PREHEAT and HEATING contact-loss scenarios. These exercise the fault path with
  a mocked contact input; acquisition/freshness are verified by the real-guard target.
- Six fault-list tests pass, including every pre-existing numeric ID and ID14.
- Initial proof-first test compile failed for the missing guard header. A later
  temporary copy of `state_machine.c` with both contact checks replaced by false
  produced **13 failing tests**. This mutation touched no production file and
  demonstrates the suite detects absence of inhibition, not just API availability.
- The complete all-target build is **not green**: unchanged
  `firmware/test/test_profiles.c:24` passes pointers to `TEST_ASSERT_EQUAL`, which
  AppleClang rejects. Byte-identical source extracted from the base commit
  reproduces the same two errors using `cc -fsyntax-only -Ifirmware/test/unity
  -Ifirmware/components/control /tmp/temper-baseline-test-profiles.c`.
  The unchanged source SHA-256 is `c7b552e5291be54ff5b0ce264963a5623fee6c3b3cc7334dd248d5eccee56c29`. The profile target is not one of the registered CTest suites. This unrelated
  baseline compile problem was preserved rather than silently hidden.

The known PAN_DET fan-interlock gap from the earlier SIL documentation is not
fixed by contact qualification and is not claimed fixed here. No ESP-IDF target
build, physical cartridge, detector, induction run or hardware qualification was
performed.
