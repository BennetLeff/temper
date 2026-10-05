# D-29 — inhibited prototype PWM conformance

The prototype target now restores REQUEST and all four PWM pads to push-pull low, pull-up off, pull-down on after every failure and after generator deletion. It accepts only canonical phase separations from 0 through 180 degrees for **disabled setup**. No phase range is released for heating and no output-enable path was added.

Base: `6717013f7ffcd7f880dc750a0579ef89059c480f`. Implements [D-27 decision](../../../../../DECISIONS.md) (2026-10-05 prototype reconciliation, C1/C2) and [D-29 brief](../D29-prototype-firmware-conformance.md). The source and host tests are under `prototype-closure/round5/firmware/`:

- `esp32/mcpwm_target.c`, `restore_pads`: REQUEST is handled first, independently of MCPWM. Every GPIO operation is checked without short-circuiting the other pads. `cleanup` disconnects first, stops/disables the timer, deletes child resources before parents, then restores pads last. Failed handles remain owned for a later cleanup attempt. A transient final-restoration failure is retried once, retaining failure status.
- `fail` routes early initialization, invalid/update, timeout and request failures through cleanup. Initialization publishes a backend only after success. The shared `inhibit` callback is void, so a GPIO error latches a fault and subsequent boolean operations fail until explicit successful reinitialization. A persistent hardware/SDK failure is reported, not claimed to have been repaired.
- `PHASE_LIMIT_PERIOD_DIVISOR` is the single named separation bound. Canonical pulse validation rejects one tick beyond 180 degrees and out-of-period aliases. At 180 degrees the B fall compare wraps to zero with the same low EMPTY action. This is disabled configuration only; real zero-event ordering is a target-validation item.
- The controller gap is 200 ns (16 ticks at 80 MHz), matching the retained 2026-10-03 decision. Frequency remains the existing 50 kHz bench setting. Both legs share one timer. All writes remain stopped-timer setup; live shadow updates are still absent. Generator creation's matrix connection is removed before dead-time inversion is configured, and no force-low is released.

## Evidence

[Red run](red.txt): the host pad oracle fails on the original target at `!up[p]`. [Green run](green.txt): 244 initialization, 38 update, 73 cleanup, 30 request-low and 30 inhibit failure positions pass (415 injected single-call positions). Cleanup failures are followed by explicit reinitialization to check retained resource ownership. Tests also cover 180 degrees, above-limit/aliased phases, NULL, stop-callback timeout, request-high rejection and persistent GPIO failures through both boolean and void callbacks. Compiler: C11, `-Wall -Wextra -Werror`, AddressSanitizer and UndefinedBehaviorSanitizer. The final tests use the required 200 ns gap; the recorded red run reached the same pull-up assertion with the original 125 ns configuration before the target change.

The stub models reset as output disabled, pull-up on, pull-down off, and generator deletion resets its pin. Primary source: ESP-IDF v5.3 commit `e0991facf5ecb362af6aac1fae972139eb38d2e4`, [gpio.c:436–448](https://github.com/espressif/esp-idf/blob/e0991facf5ecb362af6aac1fae972139eb38d2e4/components/esp_driver_gpio/src/gpio.c#L436-L448), [mcpwm_gen.c:114–124](https://github.com/espressif/esp-idf/blob/e0991facf5ecb362af6aac1fae972139eb38d2e4/components/esp_driver_mcpwm/src/mcpwm_gen.c#L114-L124); see also [D-25](../out-D25/README.md). GPIO direction alone does not disconnect the matrix in the stub. Internal deletion reset is modeled as deletion's effect, not as a separately injectable public call. This host stub tests state/error/resource ownership, not analog transients or MCPWM event arbitration.

Run from repository root:

```sh
sh zapote/power-stage-120v/prototype-closure/round5/firmware/tests/run_pwm_target.sh
```

The repository-wide host build failed in unchanged `firmware/test/test_profiles.c` (pointer-to-integer arguments to Unity): [full build log](host-tests.txt). Building/running `test_state_machine_only` separately passed: [log](state-machine.txt). These results do not label the full firmware suite passing. Import and report-only regeneration results are in [repo-gates.json](repo-gates.json); the initial missing-tool attempt is retained in [import-gate.txt](import-gate.txt). The existing gate was rerun with the available isolated lint-imports executable, `--no-cache`, and this checkout's package source. No dependency synchronization or Rust/native build occurred. Write-mode regeneration was omitted to respect the edit boundary.

## Review and remaining target work

Sequential in-context simplification and correctness/resource/API/fault-path review covered only the changed target and its host harness, per the repository's sequential-agent instruction. No shared adapter interface was changed. Review corrected an over-generous stub assumption about direction disconnecting the matrix, added error-latch tests for the void callback, and added cleanup-failure reinitialization checks. Reverification passed after those changes. No independent peer or physical hardware review is claimed.

Keep this PR **draft**. Scope captures on all four pads, reset/startup transients, persistent GPIO/SDK failure behavior, zero-event ordering at 180 degrees, target compilation and live timer-zero shadow updates remain unverified. The external <=10 kohm pull-downs and independent supervisor PERMIT contract remain hardware requirements; driving REQUEST low is not proof that downstream PERMIT is low. D-28 must establish any lower-phase operating envelope. This image grants no heat permission.
