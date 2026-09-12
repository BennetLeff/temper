# P3 switching, thermal, and shutdown validation

This batch adds two callable Rust contracts. They are intentionally separate
from the coordinator and from the thermal-sense circuit checker:

* `zapote_drc::switching::validate(&SwitchingBoard, &SwitchingContract)`
  evaluates explicit commutation paths, a labeled bounding-box loop-area
  screen, explicit return traces and required stitching vias, and declared
  aggressor/victim parallel-run screens. A missing path, missing native
  geometry, or missing noise population is `Indeterminate`; a missing return
  trace or required stitching via is `Fail`.
* `zapote_erc::operating_limits::validate(Option<DeviceOperatingPoint>,
  Option<ShutdownTimingBound>)` evaluates modeled junction temperature and a
  sum of worst-case detection, actuation, and switch-off delays. The result is
  a model-bound screen. Missing case-to-sink/sink-to-ambient data or a missing
  guaranteed response limit is `Indeterminate`.

The loop-area and parallel-run values are placement/noise heuristics. They do
not claim inductance, EMI compliance, or a guaranteed transient response. Via
count is only evidence for the authored return-path obligation; it is not a
temperature prediction. Device losses and thermal resistance values must be
bound by the caller to reviewed device/operating evidence.

## Current saved-board result

The P3 contracts were tested with discriminating synthetic fixtures and the
workspace's saved-board files were inspected for a P3-specific source contract.
The current PFC, gate-drive, and current-sense/interlock saved-board inputs do
not yet provide the typed commutation path, return pairing, device-loss,
heatsink, and guaranteed shutdown-delay populations required by these APIs.
Accordingly their P3 result is **INDETERMINATE**, with no physical thermal or
shutdown guarantee asserted. The coordinator should call these APIs only after
extracting those fields from the native evidence and recording their hashes.

## Integration evidence

The unit runner should preserve the returned `CheckReport` unchanged, merge
`checked_rules` and `coverage_gaps`, and retain each finding's rule/object.
Applicability is represented by whether the caller supplies a path/device
contract; an absent required contract must remain an indeterminate obligation.
