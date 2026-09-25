# Tracked cold-start replacement

The original `normal-finite-edge-safe` CLI run was terminated after 76:08
elapsed with no exported waveform or observable simulated time. That is a
host termination, not evidence of electrical pass/fail or a proven numerical
stall. Its initial 20-minute runtime estimate was unsupported by later
observations. The early one-minute probe cannot predict later solver cost.

This replacement retains byte-identical electrical inputs and tolerances.
Only the `.control` block moves into the shared-library host, using the
transport already exercised by `progress-probe`. The original run exited
143 and its waiting compressor was released; any resulting empty gzip is
cleanup output, not waveform evidence.

The Rust host records accepted-point simulation time every ten seconds in
`progress.tsv`. It requests a halt after 120 wall seconds with less than
1 us advancement, or at the 1800-second wall limit. These are diagnostic
resource limits, not circuit requirements. At solver stop or host halt it
exports every `.save` signal through a FIFO to gzip. `stop.txt` is written
before export so export time is distinguishable from solver time.

The callback lifecycle was rechecked on the short RC smoke circuit. Luna
independently reviewed the additions and found no material lifecycle blocker.
The process is single-run; normal or abnormal solver stop is not itself
acceptance. The strict endpoint, monotonicity and engineering checker remain
mandatory. No tolerance, regulation or sampling limit was relaxed.

Run from this directory (start the FIFO reader before the producer):

```sh
gzip -c < trace.fifo > trace.tsv.gz
SPICE_SCRIPTS=/opt/homebrew/Cellar/ngspice/45.2/share/ngspice/scripts \
  /private/tmp/matrix07-tracked cold.cir 1800 0.5 trace.fifo > run.log 2>&1
```

The two commands run in separate processes. On finished export:

```sh
set -o pipefail
gzip -cd trace.tsv.gz | /private/tmp/matrix07-normalize 190 | /private/tmp/matrix07-checker --end-s 0.5
```

Do not deduplicate a nonincreasing trace or accept a partial halted run.
The tracked process cannot recover the terminated CLI process's state.

## Captured result: rejected

The replacement stopped after the 120-second non-advancement screen fired.
Its simulated time was frozen at 0.348534537976268155 s; callbacks continued
arriving at that identical time. Solver wall time to controlled halt was
903.634 s; halt/export finished at 1041.271 s. Both the producer and gzip
exited zero, but the waveform is rejected by both maintained checkers.

The 14,951,468-row trace contains 1,126,438 nonincreasing intervals. The
first is one-based data row 9,736,224 at 0.256990362212805523 s, well before
the final freeze. Analog values differ between those equal-time rows.
`checker-report.txt` reports input line 9,736,225 because it counts the
header. `inspection.txt` and `tail.tsv` retain the detailed diagnostic.

The final exported VB is 366.544469 V, q/en are high and fault is low.
Those values are diagnostic state, not an accepted operating point. The
500 ms endpoint was not reached. The finite-edge repair's isolated tests
remain valid, but it did not resolve all full-plant numerical defects.
`execution.json` identifies the complete gzip by hash. No timestamps or
rows were removed, and no acceptance limit was relaxed.
