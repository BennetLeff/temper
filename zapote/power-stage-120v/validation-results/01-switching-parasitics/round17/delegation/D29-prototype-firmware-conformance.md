# D-29: prototype ESP32 firmware — PWM safe state and phase cap (implementation PR)

**Read [README.md](README.md) first (ground rules, board facts).**
This brief **changes firmware** under recorded decisions; open it as a draft PR.

## Why it matters

D-27 (`out-D27/`, contradiction C2, row R27) found that the prototype target
`zapote/power-stage-120v/prototype-closure/round5/firmware/esp32/mcpwm_target.c`
(`inhibit()` around lines 21–34; initialisation around 82–120) calls
`gpio_reset_pin()` and then sets level/direction, but never disables the pull-up
or enables the pull-down, ignores GPIO errors, and returns from early init
failures without calling `inhibit()`. That misses `DECISIONS.md` 2026-10-05
(PWM safe state). D-27 C1 and the 2026-10-05 reconciliation entry also cap
phase separation at half a period (180°) until D-28 validates phase shift.

## Task

1. One final pad-restoration function: push-pull output, level low, pull-up
   disabled, pull-down enabled, for every PWM pad, after any MCPWM resource
   cleanup; propagate every GPIO error; route **every** partial-init and
   update failure through it. Mirror what D-21 (#1643) now does for the HAL.
2. Cap the commanded A/B phase separation at half a period (180°) with a
   single named limit and a test, pending D-28; do not remove the phase
   control structure.
3. Fault-injection host tests with a faithful model of ESP-IDF's
   `gpio_reset_pin()` (output disabled, pull-up enabled; cite `gpio.c` at the
   pinned ESP-IDF commit D-25 used): fail before, pass after, at every failure
   position.
4. Keep request/PERMIT low independently of the PWM path; do not enable
   outputs in the image.

## Rules specific to this brief

- Change only the prototype ESP32 PWM target, its tests and test stubs; no
  board, netlist, `elec/`, `pcb/` or `prototype-closure` hardware edits.
- Build and run only the firmware host tests and, if available, the target
  compile already used for the round-5 image; no Rust workspace or native
  bridge build.
- Draft PR; target/HIL validation follows separately.

## Deliverable

Draft PR against `codex/power-stage-120v-build` with the change, tests, test
output and `round17/delegation/out-D29/README.md` (what changed, how each D-27
C2 point is met, the phase cap, what remains for target validation).
