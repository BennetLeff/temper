# Scheduled observation-window timing probe

This is a timing-only ngspice fixture for planning future fault runs. It is
not a power-stage, normal-point, or fault result. The cold prefix uses a
5-us transient step through about 400 ms. An isolated scheduling source then
alternates at explicit 25-ns PWL corners from 25 ns before the observation
window through its 400.010 ms endpoint. Those corners are native ngspice
breakpoints, so the saved times are the solver's accepted points in raw
`wrdata` output.

The event marker is a separate sparse PWL source that rises at 400.005 ms.
The scheduling source is connected through 1 GΩ only to keep its node defined;
it is still an instrumentation load and must be revalidated before a
production deck uses this method. No `linearize`, interpolation, or XSPICE
resume is involved.

The strict Rust checker requires the exact six-column `wrdata` header, finite
values, equality of the repeated time columns, strict time ordering, a cold
first sample, the 400.010 ms endpoint, an event edge near 400.005 ms, and
every accepted-time interval that overlaps either observation boundary to be
no larger than 25 ns. It also requires many observed scheduling transitions,
which makes a sparse trace fail closed. The checker does not itself prove that
a file was never post-processed; raw `wrdata` provenance and the execution
receipt remain required for that claim.

Run from this directory:

```text
ngspice -b scheduled.cir > results/scheduled.log 2>&1
ngspice -b unscheduled.cir > results/unscheduled.log 2>&1
rustc --edition=2021 -D warnings --test check.rs -o /tmp/matrix07_event_sampling_tests
/tmp/matrix07_event_sampling_tests
rustc --edition=2021 -D warnings -O check.rs -o /tmp/matrix07_event_sampling_check
/tmp/matrix07_event_sampling_check results/scheduled.tsv > results/scheduled.check
/tmp/matrix07_event_sampling_check results/unscheduled.tsv > results/unscheduled.check  # expected rejection
```

The scheduled run produced 81,783 raw rows in 0.25 s. Across the inclusive
`[0.400000, 0.400010]` window, including boundary-straddling intervals, it
had 1,768 accepted intervals and a maximum gap of 13.2553 ns. The negative
control retained the same cold and endpoint setup but removed the interior
25-ns corners; the checker rejected it on a 42.5601-ns observation interval.
The checker unit suite is 5/5, and both test and non-test builds pass with
`-D warnings`.

This establishes that explicit PWL scheduling can create real accepted
solver times in a late window without forcing a 25-ns ceiling over the whole
cold run. It does not establish fault behavior, a valid normal operating
point, or that adding the scheduling source leaves the full model unchanged.
The first production use still needs a side-by-side trace without the
instrument and an accepted baseline before any fault verdict is considered.
