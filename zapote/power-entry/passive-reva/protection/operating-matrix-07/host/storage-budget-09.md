# Matrix 07 storage budget and retention plan (read-only)

Status: **PLANNING ONLY / NO RUNS STARTED BY THIS NOTE**.

## Measured update (2026-09-21T01:11:43Z)

The completed 650 ms native-switch diagnostic now measures 5,356,097,124
bytes (`4.988 GiB`) for
`numerical-repair/nonstopping-first-invalid/run/trace.tsv.gz`. It reached the
0.65 s endpoint with 30,108,912 finite 31-column rows, 66 equal-time repeats
in 45 groups, and is rejected by the unchanged strict checker; it is
diagnostic evidence, not an accepted baseline. The recorded gzip hash is in
that run's `trace.sha256`, and the run receipt binds its deck and include
hashes.

At this timestamp, `df -k /private/tmp` reports filesystem `/dev/disk3s5`
with 482,797,652 KiB total, 415,879,832 KiB used, 33,828,192 KiB available,
and 93% capacity (about 32.26 GiB available). `du -sh` for the
operating-matrix-07 tree is 21 GiB. No files were deleted, recompressed, or
moved for this measurement. The planning estimates below remain projections;
this measured artifact should replace the old “pending” estimate in any launch
decision.

The earlier parent measurement, after the strict native candidate completed,
recorded a retained gzip of **1,962,876,932 bytes (1.828 GiB)** and **41.30
GiB** free. That snapshot is retained as historical planning context; the
dated measurement below supersedes its free-space and pending-export values.
Using the same rough projections, future demand is now approximately
4.87 +29.10 +40.47 = **74.44 GiB**, about **33.14 GiB** above measured free
space before reserve, or about **48.03 GiB** above it with a20% reserve.
These updated values supersede the initial two-pending-export ledger below.
Available space also changes with other work on this shared filesystem.

This is a capacity plan for the nine-grid normal follow-ups and seven fault
cases after the 650 ms source is accepted. It does not delete, recompress, or
archive any existing artifact. The current 650 ms extension reached its
endpoint as a duplicate-continuing diagnostic and is not accepted. A separate
strict-native candidate also reached its guard near 0.259748 s; its completed
size remains a separate diagnostic artifact.

## Measured anchors

The completed 500 ms hysteretic-driver trace is the strongest full-size
measurement:

| artifact | measured bytes | note |
|---|---:|---|
| `normal-hysteretic-driver-candidate/trace.tsv.gz` | 4,024,370,873 (3.75 GiB) | complete 500 ms, 31 columns including `time` |
| current partial settling-extension gzip | 4,037,304,639 (3.76 GiB) | stopped around 501.55 ms; not acceptance evidence |
| `numerical-repair/nonstopping-first-invalid/run/trace.tsv.gz` | 5,356,097,124 (4.988 GiB) | complete 650 ms diagnostic; 66 repeats; strict checker rejected |
| 30 MB all-column sample, default gzip | 5,855,432 | measured compression preflight |
| same sample projected to `time` + 14 normal vectors | 3,885,885 | measured projection, 66.35% of all-column gzip |
| 20 us fault export smoke traces | 2.0–3.8 MB each | measured 42-column schema smoke only; not a 650 ms forecast |

The compression preflight is in `host/compression-preflight/README.md`. Its
projection and compression results were byte-compared after decompression. The
20 us fault traces prove header/export behavior, but their startup/adaptive
sampling regime is too short to extrapolate their byte count to a 650 ms run.

At this planning point the local data filesystem reports about 46 GiB free.
The small alternate volumes are not useful for this campaign (`/Volumes/KiCad`
has about 2.2 GiB and `/Volumes/Granola` about 33 MiB). These are read-only
observations; this note makes no filesystem changes.

## Estimates and uncertainty

The estimates below deliberately separate measured values from extrapolations.
The 650/500 time multiplier is 1.3. The 15-column normal ratio is the measured
sample ratio `3,885,885 / 5,855,432 = 0.6635`. A 42-column fault ratio based
only on column count is a rough planning proxy, not an upper bound and not a
measured fault compression ratio; branch currents may compress better or worse.

| workload | calculation | estimated compressed bytes | estimated GiB |
|---|---|---:|---:|
| one 650 ms, 31-column full export | `4,024,370,873 × 1.3` | 5.23 GB | 4.87 GiB |
| one 650 ms normal export (`time` + 14 vectors) | prior row × 0.6635 | 3.47 GB | 3.23 GiB |
| nine-grid normal exports | 9 × 3.47 GB | 31.25 GB | 29.10 GiB |
| one 650 ms, 42-column fault export | rough `4,024,370,873 × 1.3 × 42/31` | 7.09 GB | 6.60 GiB |
| six 650 ms fault exports | 6 × 7.09 GB | 42.53 GB | 39.61 GiB |
| one startup fault ending near 85 ms | 7.09 GB × 0.085/0.65 | 0.93 GB | 0.86 GiB |

A useful uncertainty reserve is at least 20%. The nine-grid estimate alone
would consume about 35 GiB with that reserve. These are six long faults plus
one shorter startup fault, about 40.5 GiB combined, not seven long faults.
These figures are planning estimates, not claims about an unmeasured fault
compressor ratio.

The capacity ledger is a pre-completion planning snapshot. Its
“two currently live 31-column exports” line predates the completed diagnostic
reported above; do not add that +9.74 GiB again when planning the next launch.
Re-measure `df` immediately before any new run.

The capacity ledger is:

| ledger item | GiB | treatment |
|---|---:|---|
| current free space at inspection | 46.0 | measured available capacity |
| two currently live 31-column exports | +9.74 | pending staging demand; no extra staging copies |
| nine direct 15-column normal grid outputs | +29.10 | projected retained evidence |
| six long + one startup raw fault gzip | +40.47 | projected retained evidence for all seven cases |
| cumulative planned demand | **79.31** | before safety reserve |
| gap against current free space | **33.31** | additional capacity needed before reserve |
| 20% reserve on cumulative demand | +15.86 | working-space and compression uncertainty |
| conservative capacity target | **95.17** | about 49.17 GiB above current free space |

## Minimal retention strategy

The two currently live 31-column exports are the only staging slots planned.
Do not start additional duplicate staging exports. Each slot should be backed
by a FIFO-to-`pigz` stream, so a simulator never creates a second uncompressed
copy. Retain both full diagnostic source traces after inspection, including a
rejected or partial trace. Reproducible derived tables need not be retained;
the canonical source trace is retained regardless of checker outcome.

For the nine normal follow-ups, the reviewed grid host should export only the
needed `time` + 14-vector checker input directly. Retain that compressed
15-column artifact per grid point, its source/deck/simulator hashes, the
checker report, and a small command/metadata receipt. Do not export a full
31-column trace and project it afterward. Use a full export only as an explicit
diagnostic fallback for a nonfinite/schema investigation, and mark it outside
the normal grid budget. The measured projection gives about 3.23 GiB per 650
ms point, or 29.1 GiB for all nine. Preserve the frozen 04/05/06 artifacts
unchanged.

For faults, retain one canonical compressed raw 42-column gzip for **every**
case, plus the adapter report, checker stdout/stderr and exit, host logs,
first-invalid snapshot, deck closure hashes, and command receipt. Serializing
the six long faults and one startup fault reduces transient peak use but does
not reduce cumulative retained storage. The normalized `TRACE.tsv` and
supplemental table are reproducible from each raw gzip and may be discarded
after that case's report and raw hash are recorded; they must never be silently
discarded before that point. A startup fault is expected to be shorter, but the
0.86 GiB value is unmeasured until its actual trace completes.

With nine normal reduced artifacts and all seven raw fault gzip files retained,
the projected cumulative demand is about 69.6 GiB before the two currently
live staging exports, or about 79.3 GiB including them. Serial execution only
reduces transient use; it cannot justify deleting any reviewed raw fault
evidence. The complete campaign needs additional capacity under these
estimates. The first two grid cases can proceed after baseline acceptance if
their forecast leaves the 10 GiB free-space floor. Review their measured sizes
before committing to the remaining cases.

The two diagnostic exports are separate from future grid cases and remain
retained in their original form. Future grid cases directly export their own
15-column raw trace; they do not replace either diagnostic artifact. Never use
compression failure, disk pressure, or a partial simulator stop as a reason to
call a case accepted.

## Operational guardrails

1. Check free space before each new staging slot and after each compressed
   output closes. Keep a safety floor of at least 10 GiB; stop before crossing
   it rather than starting the next case.
2. Stream simulator output through FIFO readers and `pigz`, then `wait` for
   producer, tee, compressor, adapter, and checker statuses. A failed reader
   or compressor invalidates the case receipt even if ngspice exits zero.
3. Keep exactly one retained raw fault gzip for every reviewed fault case.
   Derived normalized tables can be regenerated for review from that gzip, but
   the raw hash, command, source closure, and simulator identity must remain.
4. Do not recompress the frozen 500 ms baseline or any frozen 04/05/06
   artifact in place. The measured gzip and projection ratios here are
   planning evidence only.
5. If the corrected 650 ms normal run again stops before its exact endpoint,
   retain its partial trace and failure logs as a diagnostic artifact, mark
   the source unaccepted, and do not begin the nine-grid or fault sequence.

The user reports no separate storage location and may free local space.
Re-measure capacity before each launch and update estimates from completed
files. Under this initial estimate the entire campaign needs roughly 49 GiB
of additional capacity including reserve. Running cases serially reduces transient use, but every raw
fault gzip remains retained. Neither choice changes the frozen checker, event
windows, current classification, or acceptance criteria.
