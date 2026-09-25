# Event-aware checked17 fault validation (candidate)

This folder contains a bounded outer validator for the canonical checked17
fault stream. It is diagnostic/evidence tooling only; it does not change the
frozen `fault_checks.rs` decision logic and it cannot qualify a fault case or
hardware.

`audit.rs` reads the stream from stdin and requires the exact 17-column header,
finite values, a timestamp starting at zero, nondecreasing time, and a global
maximum positive gap (the campaign default is 1 us). Every row contributes to
the frozen node screens (`vd`, `vb`, `sw`, `gate`, `Lboost`) before any suffix
is selected, so an early prefix excursion cannot be hidden by windowing. The
reported event artifact preserves each equal-time row and its left/right
context. Equal groups are capped at one million rows and fail closed if that
cap is exceeded. The retained checker suffix is separately capped at four
million rows; oversized checked17 lines (including the header) are rejected
at 16 KiB. These caps bound what the validator will retain; a producer still
must stream its input rather than materialize an unbounded line itself.

The retained checker suffix begins at `expected_fault - 2*window`, with one
preceding row when available, and ends at the declared trace endpoint. The
original checker is invoked only when its context is unambiguous: no equal-time
group crosses a protected predicate, no group lies exactly on either event
window boundary, and no F2 falling edge occurred before the retained suffix.
The outer report marks a terminal equal-time group as missing right context;
it never invents a positive delay or edits timestamps. This marker describes
event-artifact completeness; row-based node/event checks still see every
retained row, and it is never an acceptance waiver. Equal rows are never
deduplicated or nudged. A `--bypass` option is explicit and is passed to the
unchanged checker, which reports the existing protection-bypass failure.

The protected predicates use the same boundary semantics as the checker:
q/en/arm/permit are healthy only strictly above 2.5 V; fault/f2 detection
includes 2.5 V; gate and channel use their existing absolute limits.
`checker_verdict` is therefore only a retained-suffix diagnostic. A complete
raw-prefix screen and the event artifact remain required campaign evidence.

## CLI

```sh
rustc --edition=2021 -D warnings audit.rs -o /tmp/matrix07-event-aware-validation-13
/tmp/matrix07-event-aware-validation-13 \
  --end-s 0.65 --expected-fault-s 0.30 --window-s 0.002 \
  --observation-s 0.002 --turnoff-s 2e-6 --max-gap-s 1e-6 \
  --kind f2-open --events fault-events.tsv < checked17.tsv
```

`--kind` accepts `f2-open`, `switch-short`, `diode-short`, or `both-short`.
`--bypass` is intentionally opt-in and must not be used for acceptance.

## Verification

The owned regression suite compiles warning-clean and runs the imported frozen
checker tests as well as outer-validator tests:

```sh
rustc --edition=2021 -D warnings audit.rs -o /tmp/fault-event-audit
rustc --edition=2021 -D warnings --test tests.rs -o /tmp/fault-event-tests
/tmp/fault-event-tests   # 17 passed
```

The tests cover exact event-boundary groups, a pre-window F2 edge, one-left-row
retention, equal-time predicate crossings (including one count per group),
all-row node screening, terminal missing-right context, backward timestamps,
and the global gap rule.
