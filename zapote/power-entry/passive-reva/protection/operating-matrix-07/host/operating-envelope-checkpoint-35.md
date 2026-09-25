# Operating-envelope checkpoint 35

Status: **interim consolidation of seven accepted modeled normal points**. This document and its JSON companion summarize existing acceptance receipts; they do not replace per-case acceptance authority or add LL08/LL09 results.

## Scope and declared grid

The accepted points are LL01 through LL07 under `event-aware-normal-v1`. The original planning manifest is retained separately with its historical `planned_unexecuted` status; its source identity fields are still `PENDING`, so the accepted baseline receipt is the source authority for these completed cases.

Declared manifest points:

- LL01: 108 V RMS, Rload 416.460488957 ohm, load fraction 0.25, target 364.500 W.
- LL02: 108 V RMS, Rload 208.230244479 ohm, load fraction 0.50, target 729.000 W.
- LL03: 108 V RMS, Rload 115.683469155 ohm, load fraction 0.90, target 1312.200 W.
- LL04: 120 V RMS, Rload 374.814440062 ohm, load fraction 0.25, target 405.000 W.
- LL05: 120 V RMS, Rload 187.407220031 ohm, load fraction 0.50, target 810.000 W.
- LL06: 120 V RMS, Rload 104.115122239 ohm, load fraction 0.90, target 1458.000 W.
- LL07: 132 V RMS, Rload 374.814440062 ohm, load fraction 0.25, target 405.000 W.
- LL08: 132 V RMS, Rload 187.407220031 ohm, load fraction 0.50, target 810.000 W.
- LL09: 132 V RMS, Rload 104.115122239 ohm, load fraction 0.90, target 1458.000 W.

LL08 was live when this checkpoint was made and is excluded. LL09 was unrun and is excluded. No fault result is included beyond the separately scoped startup/fault work.

The nominal baseline is separately recorded at 120 V RMS and 190 ohm. Its acceptance receipt is `accepted-baseline-11/acceptance.json` with SHA-256 `18ce2902682b4cedb2880e260c15e731e599df4224dc842a70c85e9cadb6cf22`; it is a reference baseline, not one of the seven grid points.

## Accepted-point comparison

### LL01 — 108 V RMS, Rload 416.460488957 ohm

Acceptance receipt: `line-load-native-runner-12/full-LL01-initialized/LL01/acceptance.json`; SHA-256 `a4e09215acac4b80920257ceebfa96e4a9f7f618732cd24c778cca34f24105c7`.
Raw receipt: 29,955,738 rows, 2,151,465,343 bytes, endpoint 0.65 s; the raw SHA remains in the JSON receipt.

- Current and power: Irms 3.869202 A; Pin 405.389658 W; Pload 359.070534 W; PF 0.970125.
- Bus and drift: mean 386.715892 V; settled range 385.675669–387.716140 V; final-three drift 0.001498523.
- Whole-prefix stress: IL peak 25.067335 A (reported only); VD 387.776829 V; VB 387.716140 V; VDS 389.022540 V; VGS magnitude 14.982205 V.

### LL02 — 108 V RMS, Rload 208.230244479 ohm

Acceptance receipt: `line-load-native-runner-12/full-LL02-initialized/LL02/acceptance.json`; SHA-256 `542318b9fa0a061fa05af1616844320441f1ba59ac4a70275b14266c69c82eb2`.
Raw receipt: 29,682,485 rows, 2,132,735,226 bytes, endpoint 0.65 s; the raw SHA remains in the JSON receipt.

- Current and power: Irms 7.509729 A; Pin 802.223598 W; Pload 705.399729 W; PF 0.989116.
- Bus and drift: mean 383.282760 V; settled range 381.307658–385.188525 V; final-three drift 0.002726078.
- Whole-prefix stress: IL peak 25.777695 A (reported only); VD 385.299212 V; VB 385.188525 V; VDS 386.595233 V; VGS magnitude 14.982208 V.

### LL03 — 108 V RMS, Rload 115.683469155 ohm

Acceptance receipt: `line-load-native-runner-12/full-LL03-initialized/LL03/acceptance.json`; SHA-256 `224ac1a30d64b05b9b06d3319bb2a6dfaa3ce45330277fb97f8f50e82385041d`.
Raw receipt: 29,479,028 rows, 2,114,596,110 bytes, endpoint 0.65 s; the raw SHA remains in the JSON receipt.

- Current and power: Irms 13.412054 A; Pin 1438.880040 W; Pload 1242.516057 W; PF 0.993357.
- Bus and drift: mean 379.173791 V; settled range 375.857870–382.392349 V; final-three drift 0.004155817.
- Whole-prefix stress: IL peak 30.039218 A (reported only); VD 382.584396 V; VB 382.392349 V; VDS 383.958912 V; VGS magnitude 14.982208 V.

### LL04 — 120 V RMS, Rload 374.814440062 ohm

Acceptance receipt: `line-load-native-runner-12/full-LL04-initialized/LL04/acceptance.json`; SHA-256 `f4a6ba5435add8b2946712b957d6f222cbc0384e28ccdd32980863249acdddfc`.
Raw receipt: 30,400,545 rows, 2,189,160,539 bytes, endpoint 0.65 s; the raw SHA remains in the JSON receipt.

- Current and power: Irms 3.843647 A; Pin 445.943798 W; Pload 398.199053 W; PF 0.966842.
- Bus and drift: mean 386.344874 V; settled range 385.201839–387.442138 V; final-three drift 0.001652792.
- Whole-prefix stress: IL peak 29.777999 A (reported only); VD 387.506047 V; VB 387.442138 V; VDS 388.751460 V; VGS magnitude 14.982215 V.

### LL05 — 120 V RMS, Rload 187.407220031 ohm

Acceptance receipt: `line-load-native-runner-27/full-LL05-retry/LL05/acceptance.json`; SHA-256 `44859f112de35192015ace76a4c1d0619c4689533eaceea62b8834b04c8f4206`.
Raw receipt: 30,103,973 rows, 2,167,895,869 bytes, endpoint 0.65 s; the raw SHA remains in the JSON receipt.

- Current and power: Irms 7.420222 A; Pin 880.539980 W; Pload 783.847484 W; PF 0.988897.
- Bus and drift: mean 383.302734 V; settled range 381.211753–385.347086 V; final-three drift 0.002748746.
- Whole-prefix stress: IL peak 30.704239 A (reported only); VD 385.458665 V; VB 385.347086 V; VDS 386.758245 V; VGS magnitude 14.982213 V.

### LL06 — 120 V RMS, Rload 104.115122239 ohm

Acceptance receipt: `line-load-native-runner-27/full-LL06/LL06/acceptance.json`; SHA-256 `6eb356547ab348e16353cc9ec86cc3c520835f45ace8b5c8b6f1fddc921221a9`.
Raw receipt: 29,845,886 rows, 2,145,942,203 bytes, endpoint 0.65 s; the raw SHA remains in the JSON receipt.

- Current and power: Irms 13.198676 A; Pin 1574.420283 W; Pload 1383.936186 W; PF 0.994052.
- Bus and drift: mean 379.640270 V; settled range 376.244081–382.998346 V; final-three drift 0.003872727.
- Whole-prefix stress: IL peak 32.104756 A (reported only); VD 383.190576 V; VB 382.998346 V; VDS 384.563792 V; VGS magnitude 14.982199 V.

### LL07 — 132 V RMS, Rload 374.814440062 ohm

Acceptance receipt: `line-load-native-runner-27/full-LL07/LL07/acceptance.json`; SHA-256 `b87c23441b4e55a5e46ec4ec19bfba3bd8fa02a456a9bbdb4aed0c41a0cc7b69`.
Raw receipt: 30,812,694 rows, 2,220,002,011 bytes, endpoint 0.65 s; the raw SHA remains in the JSON receipt.

- Current and power: Irms 3.505044 A; Pin 442.290077 W; Pload 398.384114 W; PF 0.955960.
- Bus and drift: mean 386.434659 V; settled range 385.328039–387.506868 V; final-three drift 0.001562650.
- Whole-prefix stress: IL peak 34.364070 A (reported only); VD 387.566527 V; VB 387.506868 V; VDS 388.809757 V; VGS magnitude 14.982226 V.

## Narrowest observed margins

These are minima across the seven accepted points, against the unchanged normal-screen limits:

- `mains_lower_v`: 0.001000000, tied at LL01, LL02 and LL03.
- `mains_upper_v`: 0.001000000, at LL07.
- `bus_lower_v`: 5.723620000, at LL03.
- `bus_upper_v`: 21.379610000, at LL01.
- `cycle_drift`: 0.000844183, at LL03.
- `rms_current_a`: 1.587946000, at LL03.
- `vd_peak_v`: 112.223171000, at LL01.
- `vb_peak_v`: 62.283860000, at LL01.
- `vds_peak_v`: 260.977460000, at LL01.
- `vgs_abs_peak_v`: 10.017774000, at LL07.
- `energy_residual_above_lower_screen_w`: 30.259155083, at LL07.

The corresponding limits are: source 107.999–132.001 V RMS; bus 370.134250–409.095750 V; cycle drift below 0.005; input Irms at most 15 A; VD at most 500 V; VB at most 450 V; VDS at most 650 V; VGS magnitude at most 25 V; armed and on fractions at least 0.99; and energy balance Pin−Pload−dE/dt no lower than −max(1 W, 0.005 Pin).

## Limits of the checkpoint

- Seven discrete points do not establish a continuous operating envelope or justify interpolation between line/load values.
- IL peak is reported modeled stress only; there is no automatic inductor-current-rating screen.
- Energy residual is a modeled accounting screen, not measured loss, thermal qualification, or total-energy closure.
- The unchanged strict checker rejects repeated timestamps. Each accepted receipt preserves that rejection and its upstream broken-pipe branch; complete event audit and metrics are the independent normal-screen evidence.
- This checkpoint covers modeled normal operation only. It does not accept hardware behavior, faults, protection, fuse clearing, SOA, or thermal performance.

Acceptance authority remains each per-case `acceptance.json` and its parent evidence. The JSON companion records the manifest, receipt paths and hashes, complete metrics, raw receipt identities, and margin minima without mutating any authoritative acceptance artifact.
