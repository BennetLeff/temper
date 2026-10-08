# D-5: the dead time that actually reaches the gates

**Read [README.md](README.md) first (ground rules, board facts).**

## Why it matters

The D2 grid v2 (`round17/d2/README.md`, "Grid v2", `results/grid-h0-lin12-v2/`)
now brackets the off-gate margin: at **307 ns** every nominal S1 case fails
(off-gate 3.45–4.01 V, limit 3.0 V); at **348 ns** all pass. D-1
(`out-D1/`) estimated the UCC21550 DT-pin dead time at 348.4 ns nominal,
307–391 ns over tolerance, and left the controller's own timing open. The
firmware inserts its own dead time too: `firmware/components/hal/esp32/hal_pwm_esp32.c`
configures ESP32 MCPWM hardware dead time (its header comment says
"500ns minimum", written for an earlier IGBT design). If the controller's
dead time exceeds the driver's, the 307 ns corner may be unreachable; if the
driver adds to it, or the paths have mismatched delays, it may not be.

## Task

1. **Firmware:** find every place the PWM dead time for the power stage is
   set (config structs, defaults, `pwm_guard`, the board-specific HAL, any
   Kconfig/sdkconfig). Report the value(s) that ship, the MCPWM tick
   resolution and rounding, and whether the dead time is applied to both
   edges of both channels. Cite file:line at a specific commit.
2. **Driver interaction:** from the UCC21550 datasheet (cite revision and
   page), state exactly how the programmed DT combines with dead time
   already present at INA/INB (max of the two? sum? only on overlap?), and
   the input-to-output propagation delay and channel-to-channel mismatch
   (min/max over temperature).
3. **Board path:** from `frozen/default.net`, list anything between the
   ESP32 pins and INA/INB (isolators, buffers, RC filters, level shifters)
   with their propagation-delay min/max and any skew between the two paths.
   `validation-plan/06-controller-interface.md` describes the interface.
4. Compute the **minimum and maximum dead time at the two gate-driver
   outputs** for each edge (HS-off→LS-on and LS-off→HS-on), stacking the
   firmware value, path skew, driver DT tolerance (D-1) and driver channel
   mismatch. Committed script + output.

## Deliverable

`round17/delegation/out-D5/README.md`: a one-line answer (worst-case
minimum dead time at the gates, per edge, and whether it can fall below
348 ns), then the sources. Script `gate_dead_time.py` and its output.

## Acceptance

Every number traces to a file:line at a cited commit, the netlist/BOM, or a
datasheet page. Min/max are real stacked worst cases or explicitly labelled
typical. If the firmware value is not determinable (e.g. set at runtime from
an unknown source), say so and give the range of values the code permits.
Do not change firmware.
