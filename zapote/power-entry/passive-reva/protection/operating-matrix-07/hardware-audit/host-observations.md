# Live hardware utilization, 2026-09-20

The final finite-edge-safe cold run (PID 93754, launched 10:23:44 -0600)
was preserved throughout this audit. At 14:24 elapsed it had used 14:19.77
CPU time and was consuming 100% of one core. That ratio indicates CPU-bound
execution during the observed interval, not a long I/O wait. It does not
establish forward progress in simulated time; the batch log does not expose
that until the analysis returns.

`sysctl` reports Mac14,10, 12 physical/logical cores, 8 performance and
4 efficiency cores, and 34,359,738,368 bytes RAM. `pmset -g therm` reported
no recorded thermal, performance, or CPU-power warning.

The retained one-second ARM64 process sample has 813 main-thread samples.
442 leaf samples are in `PTeval` (about 54%); 49 are in `spFactor` and
33 in `spSolve`. This identifies behavioral expression evaluation as the
largest observed cost. It is a short profile, not a whole-run attribution.
The process footprint was 710 MiB at 10:33, despite `ps` reporting a much
smaller resident set; compressed memory makes RSS alone misleading.
At 10:39:38 a second sample showed 1.3 GiB footprint and 419 of 760 leaf
samples in `PTeval` (about 55%). Growing stored state is consistent with
continued work, but does not reveal the simulated time or guarantee arrival
at the requested endpoint. The 20-minute duration remains an estimate.

The machine already had about 3.49 GiB of swap allocated and substantial
compressed memory. Two successive two-second `vm_stat` intervals showed
zero new swap-ins and swap-outs. The pressure sysctl returned 2; this audit
does not use that undocumented numeric reading as a capacity guarantee.
Current one-core CPU utilization is healthy, but free core count alone is
not enough to authorize twelve simultaneous waveform-heavy processes.

An obsolete intermediate-candidate review run was still consuming another
core: PID 92902, cwd `/private/tmp/temper07-pwm-edge-review`, argv
`ngspice -b -o continuous-cold-352-fg.log ucc28180-pwm-continuous.cir`.
Its identity was verified immediately before SIGTERM; a later process
inspection confirmed it gone and PID 93754 still running. The old run used
the superseded undefined-state mapping and was not an acceptance run.
Its interruption is resource cleanup, not an electrical-model failure.

## Execution decision

Keep the current canonical run. There is no supported thread-count setting
that parallelizes this model mix, and the prior KLU timing was not faster.
Do not restart a substantial run for an unmeasured optimization.

For the later independent matrix, begin with two concurrent processes and
measure completed cases per minute, peak combined footprint, swap activity,
and output size. Increase toward four only if throughput improves without
memory or disk pressure; reassess before going higher. This is a proposed
measurement policy, not an established optimal worker count. Keep distinct
input hashes, output files, exit statuses, and unchanged acceptance limits.
No matrix cases were started by this audit.

## Short-fixture concurrency measurement

The existing final-candidate integrated fixture was copied without changing
its deck or includes. The canonical cold run stayed active throughout.
Each benchmark trace was SHA256-identical to the already checked reference
(`f46bd3d7d78663155a1fd9f4efb97f36d3ab0a6c516bac8afb2366e56f5ad968`).
Identical duplicate traces were removed after hashing; inputs, run logs and
individual timing/hash receipts are retained under `benchmark/`.

| Concurrent workers | Completed cases | Batch elapsed | Relative throughput |
|---|---:|---:|---:|
| 1 | 2 | 16.401 s | 1.00x |
| 2 | 2 | 8.475 s | 1.94x |
| 4 | 4 | 8.662 s | 3.79x |

This single short benchmark demonstrates useful process-level parallelism
on this host under the current load. It does not establish peak memory or
an optimal worker count for full cold-start traces. Apply the two-worker
initial cold-run policy above, then increase after checking live memory,
disk and throughput. The current single cold run cannot inherit this
throughput gain because its successive timesteps depend on prior state.
