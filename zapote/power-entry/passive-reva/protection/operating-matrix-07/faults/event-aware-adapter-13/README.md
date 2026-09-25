# Event-aware fault adapter candidate (matrix-07)

This is a versioned candidate cloned from `faults/adapter-09`; the frozen
adapter remains unchanged. It accepts the same raw `wrdata` schema and emits
the exact 17-column checker stream plus the nine-column supplemental stream.
All raw fields are finite-checked, including fields that are not selected for
the checker.

Time is now nondecreasing: a backwards timestamp fails, an exact equal-time
group is retained and contributes zero elapsed time, and a positive gap above
the invocation bound fails. The campaign invocation should pass the global
1 us bound (`1e-6`); the local 25 ns pacing requirement belongs to the
prepared fault deck/checker and is not substituted for this global bound.
Every equal-time group is retained in the report as `left`, all group members,
and `right`, with all raw fields, zero-based source row indices, and exact
decimal values. `left` is the row immediately before the group when one
exists; a group at the beginning reports `left=none`, and an unfinished tail
group reports `right=none`. Storage is bounded by explicit caps: 1024 groups,
4096 raw rows per group, and 100,000 retained equal-group context rows
(including left, group members, and right rows). The left clone is charged
against the total cap at group creation. Exceeding a cap fails closed rather
than silently dropping events.

Equal-time transitions crossing any protected predicate (fault injection,
F2 control, or fault at inclusive `>=2.5 V`; q/en/arm/permit health at strict
`>2.5 V`; gate-off at inclusive `<=0.20 V`; or channel retention at strict
`>0.10 A`) produce. Thus an injection edge `0 -> 2.5 V`, a health edge
`2.5 -> 5 V`, and exact gate/current boundary transitions are classified using
the same predicates as the edge, prefault, latch, and retention logic. This produces
`INDETERMINATE_EQUAL_TIME_THRESHOLD_CROSSING`. Benign equal-time groups retain
all rows and can remain `SCHEMA_AND_EVIDENCE_OK`. No deduplication, timestamp
editing, or threshold relaxation occurs. Reports include original row count,
equal-group count, and logic-change count.

The adapter remains transport/evidence tooling. Its status is never a hardware,
protection, thermal, or product qualification result.

## Build and tests

```sh
rustc --edition=2021 -D warnings --test fault_normalize.rs \
  -o /tmp/matrix07-fault-adapter13-tests
/tmp/matrix07-fault-adapter13-tests
rustc --edition=2021 -D warnings -O fault_normalize.rs \
  -o /tmp/matrix07-fault-adapter13
```

The production CLI is unchanged:

```text
fault_normalize RAW CHECKED SUPPLEMENT REPORT TSTOP KIND MUTATION_S EVENT_WINDOW MAX_GAP
```

For campaign use, `MAX_GAP=1e-6` is the declared global bound. The report is
written only after both output streams flush successfully. The 22 tests cover
benign and threshold-crossing duplicate groups (including exact injection,
health, gate, and channel boundaries), strict prefault health, inclusive
latch-off, left-context cap accounting, backward/nonfinite/gap/incomplete
traces, extra-field validation, mutation-edge checks, output preservation, and
a synthetic flush failure.
