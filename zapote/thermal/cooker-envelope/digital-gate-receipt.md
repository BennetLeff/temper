# Cooker cooling digital gate receipt

2026-09-23, P4 implementation. The typed gate is `zapote/packages/zapote-thermal/src/cooker_envelope.rs`; `tests/cooker_envelope.rs` supplies nine adverse and replay cases. The source manifest and four protection interface files, including the executable discharge gate and its selection receipt, are checked by SHA-256 before a retained result can be reused. Source-manifest verification passed for all 13 listed files at this checkout. The active Rev38 working copy is separate and remains provisional.

## Conditional results and failure boundary

| Case | Digital result | Scope limit |
| --- | --- | --- |
| GBU-395, 40 °C, 40 W, 500 LFM catalog face condition | 120.0 °C conditional whole-bridge junction screen. Fan-off retained sensitivity is 150.0 °C and fails the 125 °C engineering ceiling. | GBU package and retained board only. Neither an installed 500 LFM path nor stop time is established. |
| GBU-392, 40 °C, 40 W bridge + 65 W other PFC, 100 CFM catalog point | 118.645 °C conditional GBU junction screen. | The shared sink load and fan curve are provisional; it cannot inherit the GBU-395 PCB neck result. |
| GBJ-392, 40 °C, 110.6 W combined heat, 100 CFM catalog point | 59.639 °C conditional sink screen, 0.361 K below the retained four-diode FEM's prescribed 60 °C boundary. +5 K inlet or +10 W shared heat fails that boundary. | No GBJ diode/joint pass follows without a new FEM solve. Installed airflow and Rev38 simultaneous loss remain unknown. |
| Free-air endpoint, missing pressure, unknown support, omitted whole-cooker heat, unknown heat destination or package/sink/fan mismatch | Invalid or indeterminate; no assembly pass. | Even a future installed pressure/flow pair still needs a validated thermal mapping. |
| AUX lost, NC discharge engaged, 400/450 V, F2 closed, mains attached, fan off | Nominal 7.5 kΩ: intact 21.333/27.0 W, one resistor short 32.0/40.5 W. At 450 V and 1% low resistance: intact 27.273 W, one short 40.909 W. | Sustained heat requires F2 closed or another **verified** mains feed to VB. With F2 open and VB isolated, the listed voltage yields initial instantaneous power from finite stored energy; VD can remain separately replenished. Chassis and air path remain indeterminate. |

The RH50 40 W at 70 °C mounted rating is conditional on its 536 cm² specified fixture; the unknown cooker mount cannot use it. The 9.6 W unmounted rating at 70 °C also does not solve the actual transient or chassis temperature. The gate carries both figures as conditions and never emits a thermal pass for this fault.

## Paired producer and logical stop matrix

The cooling producer sinks interlock J1-4 only in `Ready`; every other state releases it for active-high Heatsink fault. It drives J2-5 `SENSOR_LIVE` high only with cooling and sensing rails present and valid sensing. Startup grace keeps J1 fault high and PERMIT low. Tach/airflow loss after ready latches fault; motor self-recovery does not restart heat. A deliberate local reset only returns the producer to `Starting`. Complete power loss clears its volatile reason, but a fresh fan qualification and separate deliberate interlock reset are still required. An open J1 fault wire reads high; an open J2 sensing wire reads low. With an unpowered interlock, J1 voltage is unobservable and the receiving PERMIT must default low.

The downstream truth table is logical only: healthy J1-low, J2-high, all other faults clear and a **fresh deliberate reset** establish interlock permit. `PFC_RUN_ALLOWED = PERMIT && REV38_AUTHORIZED`; `INVERTER_GATE_PERMIT = PERMIT && INVERTER_REQUESTED`. An interlock fault removes both permissions. Rev38 authorization applies to PFC only; a separate product-level decision is still needed on which Rev38 trips must inhibit the inverter. The model treats the reset edge as an input already meeting the standalone interlock's ≥1 ms healthy interval; it does not generate or validate the electrical pulse.

The J1 electrical requirements remain ≤0.3 V at roughly 350 µA when healthy, ≥2.7 V fault, and ≤20 µA combined off-state/cable leakage. These, J2 validity levels, cooling rail behavior, actual PFC/inverter stop latency and power-off clamps need circuit and physical verification. No fan circuit, timer, tach window or thermal trip has been selected.

## Checks

- Focused `rustc` module compile against the cached `sha2` release rlib: pass.
- Focused `rustc --test` integration suite: **9 passed, 0 failed**.
- Focused source-lock mutation unit test: **1 passed, 0 failed**.
- `rustfmt --edition 2021 --check` for source and test: pass.
- `shasum -a 256 -c zapote/thermal/cooker-envelope/sources.sha256`: **13 OK**.
- `git diff --check`: pass.
- `cargo test -p zapote-thermal --test cooker_envelope` could not complete because the restricted network could not resolve the registry while fetching `zlib-rs 0.6.7`; `--offline` reported uncached `adler2 2.0.1`. The direct `rustc` route compiled the new module and exercised its test file, but it does not prove the full Cargo dependency graph.

To promote a cooling choice, obtain actual fin-path pressure and flow with the selected fan voltage and closed enclosure, simultaneous PFC/inverter/auxiliary losses and heat locations, mounted sink/clamp geometry, and fan-off discharge resistor/chassis temperatures under the F2/feed states. Protection timing additionally needs loaded fan start/stall and sensor-lag measurements plus a joined PFC/inverter disable capture.
