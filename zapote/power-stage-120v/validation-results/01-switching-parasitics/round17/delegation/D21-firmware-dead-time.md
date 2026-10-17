# D-21: firmware MCPWM dead-time handling fix (proposal PR with tests)

**Read [README.md](README.md) first (ground rules, board facts).**
This brief **does** change firmware source, as a reviewed proposal PR.
It must not be merged by the agent.

## Why it matters

D-5 (`out-D5/README.md`, "P1: dead-time hardware is configured incompatibly
with ESP-IDF") found that `firmware/components/hal/esp32/hal_pwm_esp32.c`
requests both edge delays on the high generator (`:180–186`) and again on the
low generator (`:192–193`); ESP-IDF v5.3 rejects the second use of an
edge-delay block, the errors are only logged, and init still returns
`HAL_OK` (`:187–214`) and caches the requested value, which `pwm_guard`
then trusts (`pwm_guard.c:93–100`). The low request also sets
`invert_output=true` on an already complementary generator. MCPWM init is
commented out in `firmware/main/main.c:153–154`. So nothing guarantees any
dead time in the shipped firmware.

## Task

1. **HAL:** implement complementary PWM with dead time the way ESP-IDF v5.3
   documents it for the target (ESP32-S3; cite the MCPWM "Dead Time" section
   and the `mcpwm_gen.c` behaviour D-5 cites): one generator source with
   rising-edge delay on one output and falling-edge delay (with inversion) on
   the other, or the documented equivalent. Exactly one owner per
   edge-delay block.
2. **Errors:** every MCPWM configuration call's error propagates; init
   returns an error and leaves outputs in the safe (both off) state on any
   failure. No cached "configured" state unless configuration succeeded.
3. **Readback:** `get_state`/the guard must report what was configured
   (ticks actually programmed, rounding stated: 12.5 ns/tick at 80 MHz),
   not the requested value; the guard checks the programmed value.
4. **Value:** make the controller dead time a configuration parameter with a
   validated range. Do **not** pick the deployed value yourself: cite D-20's
   dead-time-ownership requirement if it exists; otherwise leave the default
   unchanged and flag it as an owner decision. Do not uncomment/enable MCPWM
   init in `main.c` (that is an integration decision).
5. **Tests:** extend the existing host tests (`firmware/test/`, e.g.
   `test_pwm_guard.c`, the mock PWM) to cover: successful configuration
   reports programmed ticks; any failing MCPWM call makes init fail and
   leaves outputs off; the guard rejects out-of-range programmed values;
   no double ownership of an edge-delay block. Run the host test suite and
   commit its output.

## Rules specific to this brief

- Change only the PWM HAL, its header/types, `pwm_guard`, the mock, and
  tests. No board, netlist, `elec/`, `pcb/` changes.
- Do not build the Rust workspace or the native bridge. Build and run only
  the firmware host tests (and, if available, an ESP-IDF compile of the
  touched component; say if not available).
- Open the PR as **draft**; it is reviewed before merge.

## Deliverable

Draft PR against `codex/power-stage-120v-build` with the change, tests,
test output, and `round17/delegation/out-D21/README.md`: what was wrong
(cite D-5), what changed, how each D-5 point is addressed, what remains
unverified on hardware (both transitions on all four outputs must still be
measured, D-8).

## Acceptance

Host tests pass, including the new failure-path tests; every D-5 firmware
point is addressed or explicitly deferred with a reason; no behaviour change
outside the PWM path.
