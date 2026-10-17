# D-32 — firmware safe state, fixed phase, and crossing-only bursts

**Implemented and host-tested; native-20 remains continuous-only by default, and the new burst binding requires a commissioned controller backend.**

The product HAL and prototype MCPWM implementation both reassert push-pull low after resource deletion and GPIO reset. Fault injection uses a reset stub that really leaves a pad as an input with pull-up, so tests observe the D-25 failure rather than an idealized reset. A transient final grounding error is retried, but the API still reports the error. Persistent GPIO failure cannot establish a physical safe-state guarantee.

This consolidates the current D-21 draft (#1643, head d274b3e705c754268016771da13e6890e3951d78) and D-29 draft (#1653, head fa3e4dc02d4a70742f9ffc700d74064787715485), with additional cleanup and fixed-phase changes. Those PRs were neither merged nor rewritten. Product and prototype cycle validation reject every phase other than exactly 180 degrees. The waveform tests exercise rejected fractional phases and accepted fixed-phase timing; the original product implementation failed the new rejection assertion before the constraint was added.

## Burst contract

`firmware/components/power/burst_scheduler.c` owns half-cycle counts. Its zero-initialized `burst_enabled` configuration is false. Enabled operation uses measured burst power, line RMS voltage and power factor to evaluate the handoff's period formula, rounds upward to whole 60 Hz half-cycles, and uses 20 seconds when no explicit period is supplied. Tests pin the committed analytical screen's rounded results for 160/200/250/300 W, rather than deriving expected values with the implementation.

`hal_bus_crossing.h` is the controller-facing bus-sense contract: timestamped ADC1/AMC1311 receiver data and a one-shot crossing flag. It is deliberately distinct from the tank CT. Freshness, monotonic timestamps, low bus voltage, repeated samples, implausible crossing intervals and loss of crossings are checked. A normal zero demand stops at the next crossing; safety faults inhibit immediately. Duty is rounded down to whole half-cycles and a restart waits for the next period boundary.

The power-service binding requires `sample_bus` and `set_burst_gate` when enabled. The latter must atomically block/unblock all four PWM outputs while preserving internal timing and capture qualification; independent hardware PERMIT remains authoritative. Supervisor permission is established with outputs blocked, then the scheduler begins at a bus crossing. Tests exercise this binding over repeated burst periods and verify transitions occur only on crossing events. The obsolete phase-from-conductance callback is removed; the service always supplies fixed 180-degree timing. Frequency tuning remains outside this task.

## Reproduce

From the repository root:

```sh
cmake -S firmware/test -B /tmp/d32-host
cmake --build /tmp/d32-host
ctest --test-dir /tmp/d32-host --output-on-failure
sh zapote/power-stage-120v/prototype-closure/round5/firmware/tests/run_pwm_target.sh
```

See `host-tests.txt` and `prototype-sanitizers.txt`. The suite includes the real ESP32 HAL compiled against faithful host SDK stubs, prototype failure injection, phase invariants, analytical period vectors, scheduler faults and power-service integration.

## Open

No ESP32 hardware, scope or B2 qualification was performed. The bus receiver/zero-cross producer and atomic output-gating backend must be commissioned on the controller; an enabled configuration without either callback is rejected. Timing allocations in software do not prove physical ADC latency or GPIO drive during permanent hardware failure. Native-20 must keep `burst_enabled=false` until B2 passes. The analytical flicker rule remains the approved screen pending D-35 and measured-current validation.
