# Native-20 capture verdicts

Run `python3 zapote/power-stage-120v/validation-plan/bench_verdict.py shot.csv shot.json` from the repository root. JSON goes to stdout; exit codes are PASS=0, FAIL=1, INVALID=2. A verdict applies to one test, leg, direction and acquisition window. Repeat the required shots on both legs; this tool does not sequence or authorize them.

CSV begins with `time_s`; all remaining columns contain calibrated volts or amperes as named below. Values must be finite, timestamps strictly increasing, and headers unique. Use lossless export; no decimation, clipping, min/max envelopes or unit suffixes. Deskew is applied **once** as `corrected_time = time_s - deskew_s[channel]`: a probe that reports an edge late has positive delay. Values between samples use linear interpolation. All channels must cover the entire requested corrected-time window.

| Test | Required columns after time_s |
|---|---|
| B0 | r35_kelvin_v, u5_kelvin_v: signed differential offsets against R5.2 |
| B1 | permit_v, permit_gate_v (Q1 or Q4), dis_v, out_a_v, out_b_v (one driver per capture) |
| B2 | incoming_cmd_v, outgoing_vgs_v (the partner, referenced to its source) |
| B3 | incoming_cmd_v, outgoing_cmd_v, incoming_out_v, outgoing_out_v, incoming_vgs_v, outgoing_vgs_v, incoming_vds_v, outgoing_vds_v, diode_id_a |
| B4 | bus_fault_v, load_current_a, comparator_v (U6 healthy-high output), conducting_vgs_v, die_vds_v |

Retain both VDS and bus-current channels for B2's raw shot record even though its numerical screen uses only partner VGS. B3's role names must match direction: DIR=0 outgoing low-side, DIR=1 outgoing high-side. Diode terminal current is negative during forward conduction and positive during recovery; load current cannot substitute for it.

Example metadata (B2):

```json
{
  "test": "B2", "leg": "A", "bus_v": 50,
  "board_manifest_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
  "capture_ok": true,
  "deskew_s": {"incoming_cmd_v": 0, "outgoing_vgs_v": 2e-9},
  "window_s": [0, 2e-6], "logic_threshold_v": 1.65,
  "uncertainty": {"gate_v": 0.1, "vds_v": 5, "current_a": 1,
                  "offset_v": 0.00001, "timing_s": 2e-9}
}
```

Replace the example identity with the SHA-256 of the actual board manifest, and replace every illustrative uncertainty/deskew value with the acquisition's evidence. `capture_ok=true` asserts that the D-8 null, overrange, unwanted activity and fixture checks passed; software cannot infer these from CSV. `timing_s` is the combined uncertainty of a measured interval, not a per-probe delay. B1/B3 also require `driver_high_v` (measured high relative to VSS). B4 requires `vds_reference="die"`; use only a die-domain simulation or documented, validated package-to-die de-embedding. Merely renaming a package waveform is invalid.

The default edge persistence is 2 ns, configurable by `edge_hold_s`. Threshold crossings are interpolated and must stay across the threshold for this duration. Analog peaks are never filtered. Choose a window containing exactly the intended event and its guard; the first qualifying edge is used. The CSV cannot resolve excursions between samples; scope bandwidth, sampling and residual deskew remain acquisition requirements. Inspect later ringing in the retained raw shot.

## Criteria and definitions

Each numerical screen reports value, worst-direction uncertainty, operator, limit and source path. B0 conservatively uses maximum absolute offset, including negative offsets. B1 uses the addendum's 0.65 V gate, 2.3 V DIS and 10% OUT thresholds. B2 examines the full 0.75 µs after the incoming command. Missing events or guard time produce INVALID.

B3 reports input gap, output 90%-fall to 10%-rise gap, package-gate 3.0 V and exploratory 1.9 V gaps, and all gate crossings. It screens VDS against 520 V, partner VGS against strictly 3.0 V in both command- and output-aligned windows, and single-shot |VGS| against strictly 20 V. Qrr integrates positive terminal current from its forward-to-reverse zero crossing through the first descending 10% Irrm endpoint. It reports trr, ta, tb10, softness and fitted di/dt over ±20 ns and ±40 ns. Missing terminal current is INVALID for this complete B3 tool; retain a voltage-only shot separately. Recovery numbers are measurements without invented acceptance limits: the native S4 fixture is not Infineon's matched coupon, and typical values are not limits.

B4 samples current at BUS_FAULT's configured logic threshold, uses U6 falling to VGS below 3.0 V for the gate-off screen, and screens die VDS. The addendum rounds the chain budget to 573 ns; D-31's ledger is 573.2 ns to driver DIS-response completion, with gate discharge separate. This tool deliberately applies the addendum's stricter 573 ns endpoint to gate VGS and labels it explicitly. It does not claim that the ledger proves that added gate-discharge time.

No aggregate PASS means hardware qualification, hot-threshold qualification, recovery-model fidelity or a power-up release. INVALID can retain earlier completed criteria for diagnosis but never returns a successful aggregate verdict.
