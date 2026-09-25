# SW-SHORT resource review 80

This review reads the explicit `resource-samples.txt` log and the regular
completion receipts from session 76829. It does not open the raw trace, read a
FIFO, rerun the solver, or modify the capture.

There are 499 samples at the logged five-second cadence, covering monitor
elapsed time 0 through 2510 s. Each sample sums only the runner PID 28932 and
its descendants, using the log's `owned_rss_sum_kib` field. The maximum owned
tree RSS was 4,534,496 KiB (4.3244 GiB) at elapsed 2228 s. The minimum sampled
filesystem availability was 41,808,908 1024-byte blocks (42,812,321,792 bytes,
39.8721 GiB), at the final sample.

The same samples report host-global swap, which is a separate scope from the
owned process tree. Swap used ranged from 13,533.12 MiB to 13,952.25 MiB, with
only 383.75 MiB free at the worst observed point. Low owned RSS therefore does
not prove that the host experienced no memory pressure.

The runner exited 1 and the monitor exited 0. Stage 1 host and pigz both
exited 0. The native export receipt reports 30,686,230 rows and 62.385 s
export time. Stage 2 decoder and decompressor exited 0, while adapter and
validator exited 1 because the trace endpoint differed from the configured
0.662 s end. The saved stop receipt records host wall time 2199.544551 s and
simulator time 0.6544026486296868 s; the separately reported 4398.88 transient
time and the monitor's 2510 s span are not interchangeable clocks.

This is a resource and timing review only. The run is incomplete and remains
`accepted: false`.
