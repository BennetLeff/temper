# Rev38 shared-ESP monitor progress contract

Status: **OPEN; no monitor epoch is credited in the target service**. The
source runtime requires both a new control epoch and a new monitor epoch
before crediting local progress. `PE_LOCAL_PROGRESS_QUALIFIED` remains zero,
so the current image cannot authorize Rev38 WDI or START.

The existing `main.c::monitor_task` contains no safety work. Calling
`pe_esp32_source_service_monitor_progress()` on every loop would credit a
running scheduler, not a completed check. Calling `run_safety_check()` before
the epoch also fails normal startup: that function unconditionally requires
PLL lock, while `pll_reset()` clears lock and the cooker starts in idle.
`state_machine.c::check_safety_interlocks()` is not a monitor substitute:
it mutates the state machine, whose owner is the control task.

The monitor implementation must publish a fresh, bounded, read-only result
before advancing its epoch. It needs a state-specific check set:

| Cooker state | Progress requirement |
| --- | --- |
| INIT, IDLE, PAN_DET, NO_PAN, COOLDOWN | Check the applicable current, temperature, RTD, fan, interlock, reset and fault conditions without demanding an inactive PLL/ZVS measurement. Define each state's safe output condition and maximum sample age. |
| PREHEAT, HEATING | Check those inputs plus PLL lock, frequency and ZVS where the measurements are valid and required. Any missing or stale active measurement suppresses progress. |
| FAULT, RUNAWAY_FAULT or safe mode | No Rev38 progress credit; assert the owned fail-low STOP/fault path. |

The `control_task` now increments its epoch only when
`state_machine_update()` reports that a nonfault state handler completed.
The update reports false while a display message defers the handler, when
the tick starts in or enters a fault state, or when a fault remains latched.
This narrows control progress but does not prove sensor freshness, monitor
health, or the target execution bound. The existing TPS3823 feed at the start
of `state_machine_update()` is independent of this return value.
`read_rtd_resistance()` can return a
cached conversion while ready; valid-looking ohms alone are not freshness
evidence. `rtd_service_sample_status()` now publishes readiness, a generation
that advances only after a healthy completed conversion and status read, and
elapsed `age_ms` from the monotonic HAL timer. The generation and timestamp
are read under one atomic sequence. `age_ms` is `UINT32_MAX` when the sample
or clock is unavailable. A stalled control task cannot keep a cached sample
young. Readiness clears on a stalled or faulted conversion and does not
advance for either. The nonzero generation wraps after `0x7fffffff`, so the
monitor must compare it only within a bounded sample-age window, rather than
treat it as a lifetime-unique identifier. Host tests cover repeated
conversions, a silent DRDY and a faulted conversion after a valid sample, a
transport failure, generation wrap, elapsed age, timer wrap and invalidation.
This is only one input to the future monitor: the allowable RTD age, ages of
every other input, state snapshot and result publication still need an
explicit contract. A timestamp does not establish a safe age limit.

Tests before enabling progress: idle-to-first-start, PREHEAT/HEATING and
return-to-idle; each task stalled independently; frozen/replayed sensor
values; fault entry during a sample; late result after cancellation; and
CPU-only reset while the expander retains outputs. A failed check must
initiate the physical fail-low path within U1's independently accepted
deadline, rather than relying solely on eventual watchdog expiration.
Target captures must establish scheduling, sample age and reset feed-tail
bounds. No such capture exists yet.
