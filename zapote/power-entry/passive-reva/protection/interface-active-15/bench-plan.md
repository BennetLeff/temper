# Physical qualification worksheet — not executed

First construct isolated low-voltage fixtures from the parent-corrected pin
tables in clamp/design.md and reset/design.md. No mains or charged PFC bus is
needed to establish these interface waveforms. Validate exact symbols, pinout,
capacitors and load connections before fixture construction. This document
does not declare either circuit ready for a production PCB.

Use a programmable isolated fault source, current measurement and differential
voltage probes. Record calibration, bandwidth, probe delay matching, fixture
wiring, full capacitance/ESR, source current limit/impedance, ramp waveform,
actual case temperature and exact part identities. A current-limited source
that never produces the intended fault is an invalid test, not a pass.

| Test | Stimulus and observation | Acceptance / open prerequisite |
| --- | --- | --- |
| A1 normal/load | 14.625 and15.75 V; idle, relay, PWM and simultaneous loads; measure at driver VDD pins | ≥14.25 V; no clamp timer trip; replace provisional load allocations with measured bounded envelope |
| A2 cold startup | Fully discharge output; include actual buck startup and all downstream caps; repeat slow/fast input ramps | Complete startup without current-limit/timer latch-off; verify current below foldback allowance at low VOUT; RUN stays low |
| A3 supply fault | Start at15.75 V; step/ramp to24.6 and35 V under documented source impedances; no-load and maximum load | Driver VDD peak plus measurement uncertainty <18 V; capture from fault onset through off, including gate/SNS/OUT and input current |
| A4 pass-device stress | Record VDS, ID and case temperature throughout A2/A3, short circuit and repetitive events | Full trajectory within applicable derated SOA; actual assembly temperature within limits; room-temperature graph alone is insufficient |
| A5 persistent/repeated fault | Hold fault after latch-off, then several short faults separated by partial timer recovery | No automatic AUX retry for -1; cumulative heating/timer behavior accounted for |
| A6 service reset | Low /SHDN ≥120 ms for stated timer tolerance, release with verified slew | AUX may recover; RUN and authorization stay reset until a fresh valid protocol exchange |
| R1 fault capture | Individually drop reset-good, source WD-good and interlock PERMIT during RUN; include pulses shorter than isolator propagation | Recognized pulse clears source latch, HOT authorization and RUN; low duration remains captured after input recovers |
| R2 power/open | Source supply removal, HOT supply removal, open health/permit inputs, both boot orders and slow brownouts | No output enable during boot/recovery; qualify minimum captured pulse and power-ramp limits rather than assuming default-low covers undefined rails |
| R3 frozen decoder | Hold SESSION_ARM and START high; assert each hardware trip and HOT watchdog | Hardware disable and both latches clear without firmware execution; restoring health creates no new RUN |
| R4 stale/fresh sequence | START before authorization; START after fault without new session; then fresh session edge followed by START | First two remain OFF; last may set RUN only after actual clear recovery/setup times are met |
| R5 stop measurement | Source health edge→captureQ→isolationOUTB→clear_ok_hw→BSS138 gate/driverIN−→power-gate/current cessation | Measure every term at actual rails/load/temp; set allowable PFC stop time/energy from power-stage analysis before marking qualified |
| R6 race | Sweep START relative to fault edge and clear release, including setup/recovery windows | Record any pulse and energy; finite START-before-inhibit interval is not automatically acceptable |
| R7 failed high | Force shared PERMIT path high while source fault occurs | Expected uncovered single-path fault; no blanket fault-tolerance pass |
| A7 pass FET short | Assess drain-source short using a non-destructive representative bypass fixture | Expected uncovered clamp failure; retain as architectural limitation |

For first arithmetic comparison, use25°C. Extend to the actual approved
assembly temperature envelope once supplied; do not silently assume all the
future components support the same temperature grade. Sweep capacitor/error
corners with either characterized substitutions or component worst-case data.

No bench samples have been collected. Overall Tstop allowance, full load
envelope, producer fault waveform, exact capacitors, HOT decoder, level
translation and watchdog/supervisor producers remain unresolved engineering
inputs. Those are distinct from the executable arithmetic and functional
SPICE checks included in this directory.
