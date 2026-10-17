# Standalone interlock interfaces

This board accepts seven active-high faults and emits active-high PERMIT. PERMIT is the authoritative downstream enable: the receiver must require a driven high and have its own pulldown. LATCHED_FAULT is complementary telemetry while powered, not an independently fail-safe shutdown output.

| J1 pin | Signal | Healthy condition |
|---|---|---|
| 1 | GND | Common logic return |
| 2 | OCP | Low |
| 3 | OVP | Low |
| 4 | Heatsink fault | Low |
| 5 | Coil fault | Low |
| 6 | RTD fault | Low |
| 7 | Runaway fault | Low |
| 8 | AUX fault | Low; reserved for additional protection |

| J2 pin | Signal | Direction / behavior |
|---|---|---|
| 1 | +3V3 | Supply input, 3.135–3.465 V |
| 2 | GND | Common logic return |
| 3 | WDI | Host watchdog transitions; 1 kΩ pulldown |
| 4 | RESET_N | Host input; fresh falling edge requests permission |
| 5 | SENSOR_LIVE | High only when all relevant sensing is powered and valid; 10 kΩ pulldown |
| 6 | PERMIT | High permits operation; low disables |
| 7 | LATCHED_FAULT | Q complement, diagnostic output |
| 8 | WDT_RESET_N | Supervisor reset diagnostic output |

Each fault has a local 10 kΩ ±1% pullup. Remote healthy outputs must sink the pullup current and hold ≤0.3 V. An asserted fault must reach ≥2.7 V. At maximum supply and minimum resistance, pullup current is approximately 350 µA per fault. The aggregate leakage budget on each disconnected fault input is 20 µA. These conditions are explicit interface assumptions, including cable loading; they are not a qualification of every remote board.

A broken individual fault conductor rises to fault under the stated leakage budget. A whole fault connector disconnected also opens its fault conductors. A broken common return, shorts between channels, a stuck-low fault driver, or an unpowered remote output clamping the pullup are different failure modes and are not covered by that assertion. In particular, do not assume the SN74LVC14A inputs or remote outputs provide power-off isolation.

SENSOR_LIVE has no qualified producer in the existing standalone units yet. Its future producer must verify sensing-rail availability and valid outputs. It must go low on lost power or validity. AUX likewise requires an explicit producer (for example secondary OCP or dedicated logic UVLO). Neither may be silently tied healthy in an integrated cooker. Controlled bench stimuli may drive these inputs during unpowered-load testing.

RESET_N must first be high, then fall only after all inputs have been healthy for at least 1 ms. Hold low for at least 1 µs; return high before another request. Holding RESET_N low across a fault and recovery must not restart. The host must not generate repeated reset pulses as an automatic recovery policy. External reset pulse integrity and recovery/removal timing remain physical qualification work.

WDI must be actively toggled while the host is healthy. A suggested integration budget is ≤400 ms between falling edges, leaving margin to the supervisor's 900 ms minimum timeout; qualify host behavior separately. The 1 kΩ pulldown adds about 3.5 mA at maximum supply when WDI is high, which the host driver must support. TI specifies this resistor to prevent a high-impedance WDI from disabling the watchdog. Supervisor reset is asynchronous to the host.

No mains, load current, gate drive or heater connection is present on this unit. All physical and whole-chain tests remain NOT RUN.
