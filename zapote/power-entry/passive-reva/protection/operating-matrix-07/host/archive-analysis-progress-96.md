# Observing archive-pass progress without changing frozen tools

The macOS archive reader exposes its current regular-file offset through
`lsof`. This is a read-only progress observation, not waveform validation.
Identify the current `pigz` child of the known analysis wrapper using `ps`
and then inspect only that process's open-file metadata:

```sh
ps -axo pid=,ppid=,etime=,pcpu=,rss=,comm=
/usr/sbin/lsof -a -p READER_PID -o -Fnfot
```

Find the descriptor whose `tREG` record names the exact retained raw archive.
The `o` field is an offset: `o0x...` is hexadecimal, while `o0t...` is
decimal. A descriptor may be inspected directly with `-d DESCRIPTOR` after
its identity is observed. Never assume a PID or descriptor is reusable across
stages. Never open a FIFO to inspect progress.

Observed during DIODE-SHORT phase43 analysis on 2026-09-22: reader87195,
descriptor3, exact archive `faults/settled-diode-short-64/full-DIODE-SHORT/raw.trace.raw.gz`
(5,340,687,952 bytes). Its offset advanced from `0x6de18000` to `0x134040000`;
the latter was recorded at00:56:59UTC. Thus the reader was advancing through
the compressed archive. A previous reader85647 had already exited because the
metrics pass completed; `lsof` exit1 alone was not evidence of a stalled job.

Offset divided by archive size estimates bytes read in the **current pass**.
It is not a row percentage or whole-analysis completion percentage. Read-ahead,
varying compression density, downstream buffering, post-EOF calculations and
remaining passes prevent an exact ETA. Completion still requires the parent
session and stage exit records, final receipts, hash checks and result review.
No solver, checker, acceptance criterion or analysis wrapper was modified.
