# Review resolution

The Luna circuit review is retained verbatim in `circuit-review.md`. It sampled
the tree while host integration was replacing `source-01` with `source-02`.
The final authoritative build is **source-02**; source-01 is historical.

| Finding | Disposition and evidence |
|---|---|
| F1: gate resistor downsized to0603 | Fixed: baseline RC1206FR-0710RL and1206 footprint restored. `gate-package-red.txt` shows the new check failing on the old export; current compiled tests pass. |
| F2: unpowered Q/ENA interface | Unresolved for rail-off qualification. This experiment requires externally valid rails and aggregate rails_ok startup/reset sequencing. Direct Q→ENA remains; the2.2k pulldown's nominal margin is not a bound on the unspecified internal pullup or back-power path. No power-off safety claim. |
| F3: stale build/test evidence | Rebuilt source-02 after package correction, regenerated compiled bridge, and reran the source-hash and physical-pin checks. The old receipt was not promoted. |
| F4: PRE1 not tested | Added exact PRE1-to-VCC assertion and unused-half input assertions. |
| F5: return paths not tested | Added reference anode, divider bottoms/filters and all local bypass rail/ground checks. |
| F6: substring net tests | Replaced them with exact external-net identities; also require all four push-pull outputs to occupy distinct nets. |

The device audit is advisory. Its recommended default-off isolation/POR work
remains necessary before qualification across unpowered states; the current
isolated experiment does not implement a power supply or a reset supervisor.
`rails_ok` means valid logic5, aux15 and sensing, including required startup
clear sequencing. A tied-high fourth AND input does not generate that evidence.

The host rejected early full-path simulation results because a capacitive
behavioral latch did not implement true edge-triggering, a gate-voltage proxy
was being substituted for the saved switch-current branch, and control cases
were preempted by earlier F2 faults. The accepted simulation must use the real
edge-triggered XSPICE flip-flop and measured branch current, with dedicated
state-case assertions and a negative control. Early all-PASS summaries are not
acceptance evidence. The final simulation record identifies the accepted run.

## Frozen simulation review and host corrections

`simulation-review.md` reviews the worker's frozen tree, identified by its
hashes. `simulation/worker-attempt/summary.csv` retains that attempt's summary;
the canonical run was regenerated after the following host corrections:

- Removed the second, unrelated input dropout from each qualification-input
  test. Required switching before the event, a real low-input interval, both
  inputs recovered afterward, and Q/EN/gate/current remaining off.
- Required Q/EN/gate/current off before the fresh ARM edge, then an actual
  high ARM/Q observation and switching afterward. Added a regression that
  rejects an early restart and one that rejects absent post-edge switching.
- Held ARM high across actual F2 recovery; removed an unrelated permit event
  that had obscured the fault-clear test. Checked recovered health explicitly.
- Made the healthy-run scenario keep F2 closed for its observation window.
  Kept F2 open in ordinary fault runs through the end; removed unrelated
  late permit/rails events and artificial reclosure from their voltage peaks.
- Preserved exact22-column/header/finite/time-order validation and measured
  current across the1mΩ sense element. Removed dead latch-model elements.
- Initialized each divider filter from its own bus. Startup fault cases still
  do not provide a valid isolated running-fault latency test; all three are
  INDETERMINATE with timing fields null, rather than accepting a0µs result.
- Measured gate voltage and switch current at Q clear. The initial F2 cases
  happened during PWM off time, so added four phases and a refinement of the
  overlapping gate-pulse case. This observes loaded turn-off at about53A.
- Added doubled gate charge as a separate sensitivity. Retained the slow-EN
  negative control, which still fails. Corrected maximum/typical fixture labels.

The reviewed weak state assertions are fixed, not carried forward as accepted
evidence. The startup stimulus coverage gap and implausible short switch-model
current impulses remain explicit limitations. The19 final cases, their raw
traces, final extractor and runner are bound by the final receipt. No third
party or hardware validation is implied by the independent agent reviews.
