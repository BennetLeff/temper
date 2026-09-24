# HOT rail-order laboratory fixture

**LAB ONLY — no energized Rev38 board, mains, AC, VD, VB or PFC power.** Use only with a standalone, mains-disconnected driver-stage coupon and two isolated, current-limited low-voltage supplies. `HOT0` becomes hazardous if a later assembly ties it to energized mains. Any live-board hookup requires a separate pad-map, isolation, instrumentation and operator-protection review. The generic J3 pinout below is a *fixture harness assignment*, not a claim that a Rev38 connector exists or that the fixture can physically mate with Rev38.

This is a passive rail-order harness. It creates neither a protected AUX producer nor a new permission signal. The two supply inputs are independently sequenced and share HOT0 only. DUT signal pins are probes; the fixture does not drive PWM, permission, RUN, ENA or gate. Use a reviewed DUT coupon and probe loading/instrument grounding setup before any powered capture. No powered capture has been made.

| Connector | Pin mapping |
| --- | --- |
| J1 AUX input | 1 `AUX_PROTECTED`, 2 `HOT0` |
| J2 logic input | 1 `HOT_LOGIC5`, 2 `HOT0` |
| J3 DUT harness | 1 `AUX_PROTECTED`, 2 `HOT_LOGIC5`, 3 `HOT0`, 4 `DRIVER_PERMISSION`, 5 `ENA_NODE`, 6 `EN_SHUNT_BASE`, 7 `PFC_PWM`, 8 `STW_GATE`, 9 `HOT_RUN_Q`, 10 `HOT_SESSION_Q` |

TP1–TP10 mirror the J3 signals in that order. Probe points are passive one-pin taps. J1/J2 are test inputs at the named protected rail of a disconnected coupon. The fixture contains no cutoff element; never use it to bypass an installed LTC4368 or other cutoff. Generic 2.54 mm header footprints are digital fixture candidates only; no native board or mating connector is accepted.

## Pinned interface and build

The source net names and driver paths come from committed Rev38 `elec/src/driver_stage.ato` at worktree commit `8b26664fec4d5acf00e56b8125b01bcb0bc18795`, SHA-256 `a5896531ef006dfa390b9fdee7ad6a681f87a8105c15f627911d24c39c5b741c`. The provisional `gate-enable-corners.md` saved bytes at that checkout hash to `ed5981a83a24bc1d468c6402dd1fb05a74eccc160fd6c7dcc1effe058c5b8305`. Recheck both on interface changes. The nominal gate-drive circuit is **not** a physical default-off proof.

Build from this directory with Atopile 0.2.69: `ato build`. Then run the independent Rust netlist audit in `../evidence/rail-order-audit.rs` against `build/default.net`. The audit must inspect the generated netlist; source-only checking is not a substitute. The deterministic event and fault matrix is `../evidence/rail-order-cases.tsv`. Its voltage and gate columns are capture requirements, not measured results. See `../evidence/rail-order-receipt.md` for the pinned source-copy build and result.
