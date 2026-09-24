# Cooling/fan U3 readiness gate

**Decision:** `INDETERMINATE` for all three retained alternatives. No fan rail, fault circuit or thermal trip may be selected from this gate. The executable is [`readiness.rs`](readiness.rs); its inputs are [`candidate-inputs.tsv`](candidate-inputs.tsv), [`timed-cases.tsv`](timed-cases.tsv) and [`source-lock.sha256`](source-lock.sha256). The saved deterministic result is [`readiness-output.csv`](readiness-output.csv). This work is based on `afb8b9e31`, the reviewed R4 plan, and the retained cooling contract. The active Rev38 checkout is separate.

## What the gate decides

The three rows keep the GBU-395/two-Sunon, GBU-392/one-Sanyo and GBJ-392/one-Sanyo concepts distinct. Each row names the exact fan MPN, quantity and catalog 12 V rating. All **17** required operating/evidence fields are `UNKNOWN`: fan terminal range under load, startup/stall current and start time, selected tach window, installed fin flow and pressure, blocked-inlet detection, sensor error and lag, thermal trip window, J1 low/high/leakage, joined stop time, and reviewed evidence identity. Unknown is never treated as zero. A numeric entry outside a known fan voltage, retained catalog flow, J1 electrical or conservative trip-window bound is rejected. Numeric entries alone still cannot produce readiness because independent adoption and assembly qualification are absent.

The source check hashes four contract artifacts: the existing 13-file cooling source manifest, the fan/fault contract, standalone interlock interfaces and prior typed thermal/fault gate. It then checks the 13 files named by the retained manifest. A changed or absent source returns `INVALID_INPUT` before any verdict. The two TSV files are compiled into the executable by `include_str!`, so the result is bound to their bytes and the executable revision. The snapshot SHA-256 values are:

| Artifact | SHA-256 |
| --- | --- |
| `candidate-inputs.tsv` | `13b020f4b4fc3534ab3d43f5efd33fd76622ceedf70ce90b031c25c8616e85b2` |
| `timed-cases.tsv` | `d98c6566c06fbac0ff2b0fc8d9be19ae0b13d542afbee1be6e73d5ff15f66052` |
| `source-lock.sha256` | `4b2fad3e75d296ca2661b3b03e011c3f2178df9ec23d267e85bb51074926671b` |
| `readiness-output.csv` | `a8f9f6c05caef977222acdd89c9132ba4cf2768f340579726219a6650b9ff15c` |

## Timed adverse matrix

The timestamps in `timed-cases.tsv` order synthetic events; they are **not measured reaction times**. Each case begins from an explicitly healthy, authorized baseline. The second event introduces one intended adverse input. The gate requires J1-4 Heatsink fault high and both PFC and inverter permits low after a latched cooling fault. J2-5 is required low for invalid sensing, but cooling contributes only its own validity; integration must combine every sensing producer before claiming global `SENSOR_LIVE` high.

| Case | Digital result | Reason |
| --- | --- | --- |
| One of two Sunon tach signals missing | `INDETERMINATE` | Logical stop shown; no measured detection or stop bound. |
| Blocked flow with plausible tach | `INDETERMINATE` | Independent flow input prevents tach-only credit; no measured detection bound. |
| Fan rail brownout | `INDETERMINATE` | Fault and both permits follow the safe logical state; power-off voltages remain unproved. |
| J1 line stuck healthy | `REJECTED` | Fault is present while J1 reads healthy and both permits survive. |
| Reset held through fault/recovery | `REJECTED` | A held level cannot be a fresh deliberate reset edge; automatic restart is unsafe. |
| Fan tach auto-recovers | `REJECTED` | Recovery without reset cannot clear the fault latch. |
| One sensor invalid among valid peers | `REJECTED` | J2 incorrectly remains high and heating survives. |

The gate does not credit free-air CFM as installed flow. The 43.4 CFM GBU-395 gross-face conversion and 100 CFM 392 catalog point are **minimum conditions for reusing those particular catalog arithmetic screens**, not accepted fan operating points. Pressure, flow distribution, inlet heating, support and total concurrent heat still require physical evidence. The synthetic trace gate is an independent adverse check of the prior logical contract, not a substitute for a native circuit, latency capture or installed test.

## Interface and trip evidence still needed

- Select a protected fan rail and one fan variant. Capture terminal voltage at each fan through cold/hot startup, stall, running and brownout; measure startup/stall current and time. Two Sunon maximum running current is 0.276 A combined, and Sanyo 0.47 A is a rated free-air value; neither bounds startup or stall.
- Capture separate tach channels for the two-Sunon case, a justified speed window for the selected MPN, and an independent blocked-inlet or thermal-flow detector. A spinning rotor alone cannot establish fin flow.
- Measure each relevant sensor's error, placement and lag, then establish a positive thermal trip window using worst-case detection, lag, output and joined PFC/inverter stop delays plus temperature overshoot. No numeric trip setting follows from the current 2.14 K retained PCB margin or the 0.361 K GBJ sink-boundary margin.
- Build and test the J1-4 healthy sink and J2-5 validity contributor. J1 requires ≤0.3 V healthy at about 350 µA, ≥2.7 V fault and ≤20 µA combined power-off/cable leakage. Prove rail-loss, controller reset, open wire and unpowered clamp behavior. J2 global `SENSOR_LIVE` belongs to integration.
- Trace physical J1/J2 through interlock PERMIT and the separately joined PFC RUN and inverter gate enables. Rev38 authorization and inverter permit remain distinct. Capture stop timing and no automatic restart after fault, power cycle and fan self-recovery.

## Reproduce

From the repository root:

```sh
shasum -a 256 -c zapote/thermal/cooker-envelope/sources.sha256
rustfmt --edition 2021 --check zapote/thermal/cooker-envelope/readiness.rs
rustc --edition=2021 --test zapote/thermal/cooker-envelope/readiness.rs -o /private/tmp/zapote-cooling-readiness-test
/private/tmp/zapote-cooling-readiness-test
rustc --edition=2021 zapote/thermal/cooker-envelope/readiness.rs -o /private/tmp/zapote-cooling-readiness
/private/tmp/zapote-cooling-readiness . > /private/tmp/zapote-cooling-readiness-output.csv
cmp /private/tmp/zapote-cooling-readiness-output.csv zapote/thermal/cooker-envelope/readiness-output.csv
```

Focused Rust tests: **6 passed** with `rustc 1.92.0 (ded5c06cf 2025-12-08)`. All 13 retained hashes and the four contract hashes passed. Saved output replay is byte-identical. No full Cargo, native-circuit, physical fan, flow, trip or joined-stop qualification was performed.
