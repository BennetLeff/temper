# F2 shutdown Rev B final review

Scope reviewed: `elec/src/power_entry_f2_shutdown_revb.ato` (source-06),
`fault-tests/{controller.inc,fault_template.cir,run_cases.sh,extract.rs,traces/summary.csv}`,
`vendor/driver-final-interface.cir`, and the official
`vendor/UCC27511A_TINA_TRANS/UCC27511A.lib`. The frozen Rust ERC test binary
passes its five tests; the frozen fault summary has 13 expected PASS cases and
two negative cases that fail from measured assertions.

## Findings

1. **Dead `LATE_FAULT` control parameter makes the named negative case
   misleading (P2).**

   `run_cases.sh` substitutes `@LATE_FAULT@` (line 26) and
   `late_fault_negative` supplies `1` (line 56). `fault_template.cir` declares
   `.param LATE_FAULT` (line 9), and `controller.inc` declares it (line 4), but
   no expression in `controller.inc` references it. The negative verdict is
   instead caused by positional argument 26 setting `FAULT_TAU=10u`; the
   summary records 8.407105 us and fails the >2 us assertion. This is a real
   delayed-filter negative control, but it is not a test of `LATE_FAULT` and the
   unused parameter can silently invalidate future edits to that case.

2. **Absent-rail cases can pass with a truncated, event-free trace (P2).**

   `parse_trace` accepts any finite trace with at least three rows (lines
   111–114) and does not require the expected simulation time span. In the
   `logic_absent`/`aux_absent` branch (lines 267–278), a case passes when no
   `q`, `en`, or `gate` sample exceeds its OFF threshold; all rail/ARM/PWM
   coverage checks are skipped for `absent_rail`. Therefore a three-row,
   all-zero, 25-column trace named `logic_absent.tsv` or `aux_absent.tsv` would
   be accepted as PASS. The existing traces are real and nonempty, but the
   extractor's stated no-empty guarantee is not true for these two scenarios.
   Require time-range/control-event coverage for absent-rail cases.

3. **Fresh-ARM proof leaves a transition window unasserted (P2).**

   For fault cases, the extractor requires OFF only through 549 us (lines
   244–255), then searches for the first `q > 2.5` at or after 560 us (line
   200) and a high gate in 562–580 us (line 256). The fixture drives ARM low
   from 550 to 560 us and raises it at 560.1 us (`fault_template.cir` line 29;
   common arguments in `run_cases.sh` line 42). Thus the 549–560 us interval is
   not checked, and the q transition is not causally tied to the ARM rising
   edge. A stale automatic re-enable in that interval, or q already high before
   the fresh edge, is not distinguished from a valid fresh re-arm. Extend the
   OFF window to the edge and assert the transition follows ARM's rise.

## Claims supported by the reviewed artifacts

The fault latency calculation starts from the direct bus threshold/mismatch
event (`voltage_event` in `extract.rs`, lines 166–186), not from filtered
`ch_*`; current summaries show 0.748899–1.535580 us for positive cases. The
negative controls are classified from the actual extracted metrics, not a
hardcoded expected output. The parser rejects missing/short (<3 rows) and
non-finite values, but finding 2 qualifies that guarantee.

The compiled graph checks bind source SHA and 79 physical components. Driver
pin order is consistent: the vendor fixture instantiates
`Xdriver disable pwm aux 0 outh outl`, matching the official model's
`INM INP VDD GND OUTH OUTL` subcircuit order. The source's health D1 and D2
connections are distinct and correctly exercised. The final vendor fixture's
1 kohm IN- pullup is the reviewed revision; its 12 nF gate and small-FET
capacitances are explicitly authored surrogate assumptions, not device
qualification. Supervisor timing is an authored nominal model (132 us release
timer and 8 us fall delay), and the LVC buffer's below-1.65 V behavior is
explicitly modeled OFF rather than presented as a guaranteed hardware transfer
function.
