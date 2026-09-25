# Matrix 07 fault unit

Status: **UNEXECUTED**. The host has not accepted a contiguous normal
cold-start prefix, so no fault deck or campaign run is evidence. The matrix,
checker, and all negative fixtures are preparation artifacts only.

Files:

* `fault-matrix.md` — bounded F2-open, switch-short, diode-short, both-short,
  and protection-bypass cases plus evidence contract.
* `fault-matrix.json` — machine-readable case list and graph boundary.
* `fault_checks.rs` — independent Rust fail-closed parser and fault checks.

Run the checker unit tests from this directory:

```text
rustc --edition=2021 --test fault_checks.rs -o /tmp/temper07_fault_checks_tests
/tmp/temper07_fault_checks_tests
```

Once the host supplies an accepted trace and timing receipt, a campaign run
must provide every bound explicitly:

```text
rustc --edition=2021 fault_checks.rs -o /tmp/temper07_fault_checks
/tmp/temper07_fault_checks TRACE.tsv TSTOP KIND EXPECTED_FAULT DETECTOR_WINDOW TURN_OFF_BUDGET OBSERVATION [MAX_GAP]
```

`KIND` is `f2-open`, `switch-short`, `diode-short`, `both-short`, or
`bypass`. Python/shell may launch ngspice and hash artifacts; Rust owns all
trace and verdict logic. Retain every failed, timed-out, or indeterminate
attempt alongside its deck and source hashes.
