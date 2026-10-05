# Independent review disposition

Independent Astra review by the reused cooling-closure agent, 2026-10-04; read-only review of the source, emitted pins and primary device data. No release approval is implied.

| Finding | Correction | Evidence / remaining qualification |
| --- | --- | --- |
| P1: TPS3825 pin3/4 copied from the wrong family member, tying actual RESET output to5V | Pin3 RESET is explicitly NC; pin4 MR_N is tied to5V. TPS3820 watchdog remains pin3MR/pin4WDI. | Exact-part regression checks both family members; fresh typed exports required by replay. |
| P2: normal STOP_DONE could clear LATCH_OK through the timer RC tail after the start windows expire | Made completed-attempt latch clear an explicit requirement of the guarded prototype pod. Dedicated U_SESSION_END combines STOP_DONE_N with the fault-chain health. Every attempt, including ordinary OFF, requires a fresh physical RESET/START/POST. | Source-connected logic test covers mature RUN with expired timers, STOP_DONE, release and attempted START without RESET. The firmware owner confirmed the corresponding OFF/DISCHARGE/reset/fresh-POST sequence in a host regression; ten assertion groups pass there. No claim of glitch-free latch retention is made or required. |
| Current comparator inputs directly on CT_RAW without current limiting | Separate20kΩ input resistors feed the two comparator inputs. Bidirectional SMCJ5.0CA clamps are directly across both CT burdens. | Structural and conditional clamp-current tests added. CT/TVS pulse-energy survival, temperature, ADC/reference backfeed and burden-failure behavior remain digital fault-analysis work; not closed by the resistor calculation. |

Earlier implementation review also corrected the actual RES_A/SW_B sensing connection, isolated-amplifier power-rail backfeed path, watchdog floating-input disable possibility, proof-pulse retriggering, missing controller-input defaults, and missing remote DIAG low default. Cold latch admission, proof observation interval and catch-charge admission were coordinated with the firmware owner and have host tests there. Target deployment remains outstanding.
