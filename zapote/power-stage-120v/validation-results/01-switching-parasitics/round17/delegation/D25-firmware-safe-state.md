# D-25: does the forced safe state drive both gates low? (D-21's blocker)

**Read [README.md](README.md) first (ground rules, board facts).**

## Why it matters

Draft PR #1643 (D-21) fixes the MCPWM dead-time configuration. Its review
(comment on #1643) raised one **blocking** question: the safe/shutdown state
forces `gen_high = 0` and `gen_low = 1` (`firmware/components/hal/esp32/hal_pwm_esp32.c`
in that PR, around lines 99–100, 132, 140), relying on the force acting
**before** the inverting dead-time stage so the low output reads 0. If the
ESP32-S3 applies the force **after** the dead-time inversion, the safe state
turns the low-side gates **on**. This must be settled before any powered test,
and the owner wants it settled in software where possible.

## Task

1. **Documentation and source:** from the ESP32-S3 Technical Reference Manual
   (MCPWM chapter: generator, dead-time and fault/force submodules, their
   signal order) and ESP-IDF v5.3 (`components/esp_driver_mcpwm/src/mcpwm_gen.c`,
   the HAL/LL layers, `mcpwm_generator_set_force_level`), establish the exact
   order of force, dead time and inversion on the output path. Cite TRM
   section/figure and file:line at a pinned ESP-IDF commit.
2. **Emulation, if possible:** check whether Espressif's QEMU fork models the
   ESP32-S3 MCPWM peripheral well enough to observe the outputs; if so, run
   D-21's firmware image (or a minimal test image using the same HAL) and
   record both GPIO levels in: forced safe state, after init, after a failed
   init, after stop. If QEMU does not model MCPWM, say so with evidence.
3. **Register-level check:** independently, compute from the TRM what the
   MCPWM registers D-21 writes produce for each output in each state, and
   cross-check against (1).
4. **Verdict and fix:** state whether the safe state is correct. If not,
   propose the minimal change to D-21 (e.g. force on the dead-time output, a
   GPIO-matrix/fault-action safe state, or an independent GPIO path), as a
   patch file in `out-D25/`, with host tests updated. Do not push to #1643.

## Deliverable

`round17/delegation/out-D25/README.md` (one-line answer first: safe state
correct / incorrect / undetermined, and why), with citations, any emulation
logs, and a proposed patch if needed. Read-only on firmware except the patch
file in `out-D25/`; no board, netlist, `elec/` or `pcb/` edits.

## Acceptance

Every claim about signal order cites the TRM or ESP-IDF source at a pinned
revision; emulation results, if any, are reproducible from committed
scripts; "correct" is claimed only with documentation and (if available)
emulation agreeing.
