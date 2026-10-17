# D25 GPIO cleanup regression

The 2026-10-05 PWM safe-state decision in
`zapote/power-stage-120v/DECISIONS.md` requires the final cleanup action to restore
configured PWM pins to push-pull output low, pull-up disabled and pull-down
enabled, after MCPWM generator deletion.

ESP-IDF commit `e0991facf5ecb362af6aac1fae972139eb38d2e4` supplies the external
behavioral premise:

- [gpio.c, lines 436–448](https://github.com/espressif/esp-idf/blob/e0991facf5ecb362af6aac1fae972139eb38d2e4/components/esp_driver_gpio/src/gpio.c#L436-L448):
  reset disables output, enables pull-up and disables pull-down.
- [mcpwm_gen.c, lines 114–124](https://github.com/espressif/esp-idf/blob/e0991facf5ecb362af6aac1fae972139eb38d2e4/components/esp_driver_mcpwm/src/mcpwm_gen.c#L114-L124):
  successful generator deletion resets its GPIO.

D25's original `cleanup_probe.c`, `cleanup_probe.txt` and source hashes remain
unchanged under `zapote/power-stage-120v/validation-results/01-switching-parasitics/round17/delegation/out-D25/`.
The stub now models both reset effects, exposes mode/pulls/route/hold, and reports
an undriven pin as `-1`, independently of its stored level. The internal reset
on generator deletion is not counted as another public failure-injection call.
This preserves the original failure-position comparison.

## Recorded RED and GREEN

`d25-red.txt` was recorded before the HAL cleanup fix, after resolving the merge
of draft HEAD `9cddf149a1500896a7cf8fbca78ee2cc901f04ba` with required base
`27b23b5ea01ee983d651c9461b648cf2d123f575`. That resolution retains the native19
gate-channel rejection and both sets of CMake targets. The faithful stub and
stronger assertions produced **7 tests, 2 failures**: successful deinit fails,
and all 29 initialization fault positions have wrong pulls. Exactly 11 positions
(19–29) leave at least one output disabled, matching D25's original probe.

`d25-green.txt` records **11 tests, 0 failures** after the fix. All 33 init fault
positions restore both pins. Four new public calls configure the two pulls on
each pin; the original fault positions map as follows:

| Original positions | Current positions | Calls |
| --- | --- | --- |
| 1–3 | 1–3 | High-pin level/reset/level |
| 4–6 | 6–8 | High-pin direction/hold-disable/hold-enable |
| 7–9 | 9–11 | Low-pin level/reset/level |
| 10–12 | 14–16 | Low-pin direction/hold-disable/hold-enable |
| 13–29 | 17–33 | MCPWM allocation/configuration and final hold release |
| Added | 4–5, 12–13 | Pull-up disable, pull-down enable |

The suite also injects each of 35 running-deinit calls, all four start calls,
both calls of frequency/dead-time updates, the running duty call, and both
force calls for stop/emergency-stop. Assertions check push-pull output mode,
pulls, disconnected routing, released hold and low level. Deinit faults before
the last 14 GPIO calls must still restore both pins; a fault within that final
GPIO sequence must return `HAL_ERROR`, restore the other pin, and permit a
successful retry. Persistent GPIO-direction failures exercise both failed init
and deinit after all resources have been deleted. Retaining the configuration
prevents a false successful no-op deinit and allows the pins to be restored on
retry. Fully successful cleanup after an operation fault still allows fresh init.

The legacy HAL's gate channel remains rejected. Complementary legacy-HAL tests
use the FAN channel as a host test vehicle; they do not enable or qualify the
native19 synchronized four-output power service. Its incoming tests remain in
CMake and pass. Timing constants and allocation policies are unchanged.

## Reproduction

From the repository root:

```sh
cmake -S firmware/test -B firmware/test/build-d25 -DCMAKE_C_FLAGS=-Wno-error=int-conversion
cmake --build firmware/test/build-d25 -j 4
firmware/test/build-d25/test_pwm_esp32
ctest --test-dir firmware/test/build-d25 --output-on-failure
```

`d25-host-tests.txt` records all **17 registered CTest suites passing**. The
compatibility flag is the existing draft workaround for the unrelated
`test_profiles.c:24` pointer-to-integer Unity assertion. The initial default-flags
build failed there; `firmware/test/build-d25/build.log` preserves that diagnostic
locally, and `build-compat.log` records the successful full host build. The build
directory has a local ignore file and is not part of the patch.

These checks execute the real HAL C against a source-informed host SDK model.
They are not ESP-IDF target builds, register/pin measurements, timing evidence,
or hardware qualification. GPIO API failures can prevent the requested physical
state; error propagation and retries cannot replace the external pull-downs and
independent PERMIT/DIS hardware interlock required by the decision.
