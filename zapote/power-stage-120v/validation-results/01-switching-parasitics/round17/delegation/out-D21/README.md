# D-21 — PWM dead-time handling proposal

**The draft fixes complementary delay ownership, propagates configuration errors, and makes the guard check successfully programmed ticks; no deployed gap is selected and application PWM remains disabled.**

Base: `b30b3ae35a4bd3ad5c22d8c300c4640986e1232a`. OpenAI GPT-6, 2026-10-02. This is a firmware proposal requiring controller/bench review, not a powered-operation release. No merge is authorized.

## Change and source

[D-5](../out-D5/README.md#p1-dead-time-hardware-is-configured-incompatibly-with-esp-idf) found both edge-delay blocks requested twice, ignored initialization errors, an inverted already-complementary low waveform, setter-only clamping and a guard that trusted requested nanoseconds. The official [ESP-IDF v5.3 Dead Time documentation](https://docs.espressif.com/projects/esp-idf/en/v5.3/esp32s3/api-reference/peripherals/mcpwm.html#dead-time) and `mcpwm_gen.c:318–395` define independent rising/falling paths and single-owner validation; the fetched source hash is in [sdk-source.json](sdk-source.json).

The implementation uses the documented independent-path equivalent: both raw generators have the same timer-HIGH/compare-LOW actions and the same comparator; high owns only rising-edge delay, low owns only falling-edge delay with inversion. No second complementary inversion or duplicate edge owner exists. Independent raw sources allow high=0 and low=1 forcing to produce **both final outputs low**. The documented single-source example cannot be shut down merely by forcing that one source to a constant: one inverted output would remain high. Espressif explicitly notes under `mcpwm_generator_set_force_level` that dead-time/GPIO inversion affects the final output.

Both GPIO pads are held low while the peripheral routes, actions, force levels and inversion are configured. On any configuration error, initialization fails, programmed state is invalid, pins are disconnected from the peripheral and driven low, and allocated resources are released in reverse order. Failed cleanup handles remain retained for `deinit` retry. This is tested API behavior, not proof against a failed GPIO controller or simultaneous hardware fault: shutdown errors propagate and the external interlock remains necessary.

The timer remains clocked during normal `stop`; independent force actions inhibit both outputs. `MCPWM_TIMER_STOP_FULL` is a future timer event, not an immediate-low guarantee. Deinitialization disconnects pins before stopping/disabling/deleting resources. Start, duty, frequency and emergency-stop API failures also invalidate the channel and use GPIO shutdown. Initialization/start/stop transitions still require scope measurement.

## Configuration and reported state

`hal_pwm_config_t.dead_time_ns` remains the explicit request; no new application default is added. The existing guard envelope **300–1000 ns** is shared by HAL and guard as a validation policy, not proof it is suitable for this power stage. The inconsistent setter-only 500 ns clamp is removed; invalid requests return an error. Complementary operation also requires enough on/off ticks for the gap, finite duty, valid pins and a realizable timer period. Single-output operation requires zero dead time.

At the configured 80 MHz, `ticks=floor(ns×2/25)`; each tick is nominally 12.5 ns. `get_state` reports `dead_time_ticks`, `timer_resolution_hz`, `configured`, and the legacy whole-nanosecond field truncated from the programmed ticks. Examples exercised in tests: 307 ns →24 ticks→300 ns; 313 ns →25 ticks→312.5 ns (legacy field312). The guard compares exact tick/clock products to its limits and rejects missing/failed reads, invalid state, and out-of-range ticks even if a cached ns field looks plausible. Integrity checking requires a successful self-test.

This state is a **successful API-programming receipt**, not register readback or measured waveform timing. The public v5.3 interface used here does not supply a dead-time-register getter. Clock tolerance, GPIO/harness skew, loaded driver timing and gate threshold crossings remain unverified. Firmware integrity comments no longer describe this software comparison as a register CRC.

Updates to dead time and frequency require stopped outputs because their paired SDK writes are not atomic. A partial update cannot leave a startable, apparently configured channel. This deliberately returns `HAL_ERROR_BUSY` to live frequency updates; continuous PLL retuning needs a separately reviewed atomic update/synchronization design. Duty updates keep the comparator's timer-zero update behavior and reject pulses too short for the configured gap.

[D-20 R24–R29 / PR1642](https://github.com/BennetLeff/temper/pull/1642), commit `1cc4acbbf`, records the same ownership gate. It was not merged into this baseline. The final controller gap remains an owner decision; native-18's estimated 396.6–488.0 ns DT-pin interval is neither added to the firmware gap nor selected as the firmware default. `main.c` is unchanged; MCPWM initialization remains commented out. Existing fan/channel aliases and the missing four-PWM allocation are not resolved here.

## D-5 coverage

| Finding | Disposition |
|---|---|
| SDK edge-block conflict and second inversion | Independent RED/FED owners, identical raw actions, only low FED inverted; actual HAL tested with SDK ownership rejection |
| Init logs errors then succeeds | Every configuration call checked; 29 initialization API failure positions exercised individually; failure never returns configured state |
| Initial comparator/action errors ignored | Included in failure loop; outputs low after every injected failure |
| Init and setter disagree about gap | Same 300–1000 ns policy, no clamp/default; timer/pulse validation |
| Requested ns cached as timing | Exact programmed ticks and resolution exposed; guard uses ticks |
| Partial setter update | Invalidates state and disconnects outputs; explicit reinitialization required |
| get-state failure ignored by runtime guard | Failure/null ops/invalid state rejected; no use of uninitialized state |
| 500 ns host constant mistaken for deployed setting | Existing host constant unchanged and labelled test-only; no main/config manifest change |
| MCPWM not initialized in application | Explicitly deferred by brief; `main.c` unchanged |
| Two root PWM pins vs four J4 inputs | Deferred to controller allocation / D20; no GPIO map invented |
| Actual gate timing unknown | D8 bench work still mandatory for both directions on both legs |

## Host verification and limits

- [PWM HAL tests](pwm-hal-tests.txt): 5 tests pass, including all 29 init API failure positions, separate rising/falling ownership, complete-period complementary waveform checks, stop inversion, partial dead-time/frequency failures, start failures, emergency-force failure and invalid inputs.
- [Guard tests](pwm-guard-tests.txt): 10 pass, including ticks below/above bounds, half-nanosecond representation, invalid programmed state and failed reads.
- [Host suite](host-tests.txt): **15/15 registered CTest targets pass**. The unchanged baseline passes 13/13 under the same build settings ([baseline](baseline-host-tests.txt)); the two additional registered targets are PWM HAL and the existing guard executable.
- The default AppleClang build first failed in unchanged `test_profiles.c` through the existing Unity pointer-to-int assertion macro ([log](initial-build-failure.txt)). Both baseline and changed builds use `-Wno-error=int-conversion` to retain this as a warning; no assertion is weakened or edited. This compatibility issue remains outside the PWM change.
- No installed `idf.py` was available; no target ESP-IDF compile or physical test is claimed. The stub deliberately models the SDK contracts being exercised, including final-output inversion and edge ownership; it is not an ESP32 peripheral emulator and cannot prove pad-hold timing, startup glitches, ISR latency or clock behavior.
- Main-context review checked failure paths, cleanup ownership, inversion, numerical conversion and scope. The independent GPIO fallback and stopped-only updates address the two main hazards. No independent model review is claimed.

Reproduce (from repository root):

```sh
cmake -B firmware/test/build firmware/test -DCMAKE_C_FLAGS=-Wno-error=int-conversion
cmake --build firmware/test/build -j 4
ctest --test-dir firmware/test/build --output-on-failure
./firmware/test/build/test_pwm_esp32
./firmware/test/build/test_pwm_guard_only
```

Owner/bench gates before merge or enabling PWM: select the controller gap and four-pin allocation; review the stopped-only frequency-update contract against PLL needs; compile with the pinned target SDK; verify independent raw paths and pad holds on silicon; measure startup/reset/brownout, both transitions on all four outputs, emergency shutdown and interlock timing. Hardware OVP/OCP and D8's S4 recovery questions remain independent.

Repository checks: import boundary gate passes (5 kept, 0 broken); `scripts/regen_derived.py --check` reports all derived artifacts consistent. No Rust build was run.
