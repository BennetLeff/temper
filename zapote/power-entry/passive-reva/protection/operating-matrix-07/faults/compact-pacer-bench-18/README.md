# Compact repeated-PWL pacer benchmark

This is an isolated ngspice 45.2 parser/breakpoint benchmark for the delayed
repeat source used by the fault instrumentation.  It contains no power-stage
devices and makes no electrical-equivalence or fault-protection claim.

The deck uses the reviewed compact form:

```text
Vschedule_probe schedule_probe 0 PWL(0 0 25n 1 50n 0) r=0 td=64.999975m
Rschedule_probe schedule_probe 0 1G
```

It retains the plant's `STEP=500n`, trapezoidal tolerances, `uic`, and runs to
`TSTOP=89m`, covering the delayed waveform's 25 ns corners and repeated wraps.
The exact ngspice 45.2 source is retained outside this folder at
`/private/tmp/ngspice-45.2-src`; source hashes are in
`ngspice-vsrc-source-sha256.txt`.  `vsrcpar.c:124-158` documents `r=0` as
repeat forever and requires the repeat start to match a PWL time point;
`vsrcload.c:318-360` computes delayed phase and wraps it by the repeat period;
`vsrcacct.c:170-214` schedules the next PWL breakpoints.  This confirms the
syntax and the intended 0/25/50 ns corners without relying on a PULSE `PW=0`
form.

## Bounded run and checker

The one run was:

```text
/usr/bin/time -p ngspice -b -r pacer.raw -o ngspice.log pacer.cir \
  > ngspice.stdout 2> ngspice.stderr
```

It exited zero in 5.11 s wall (5.09402 s analysis), generated 4,365,703 rows,
and reached `8.90000000000000097e-2 s`.  The Rust `check_pacer.rs` checker
reads the raw binary vectors and checks finite/nondecreasing rows, the
actual delayed preamble, an analytic triangular waveform, unique corner
coverage, and the required 65--89 ms pacing window.  Its final report is:

```text
rows=4365703 first=5.00000000000000093e-9 endpoint=8.90000000000000097e-2 first_value=0.00000000000000000e0 pre_delay_range=0.00000000000000000e0..0.00000000000000000e0 active_range=-5.82054571573553431e-11..9.99999999999999556e-1 max_gap=5.00000000000500044e-7 first_corner_incoming_gap=4.94999945324647861e-7 active_max_gap=1.28590334769196346e-8 active_gaps=4235693 active_oversize=0 required_max_gap=1.28590334769196346e-8 required_gaps=4235689 required_oversize=0 pre_delay_bad=0 max_tri_error=2.08802641843419678e-10 expected_corners=960002 corner_hits=960002 missing_corners=0 near_zero=480001 near_one=480001
```

The 495 ns gap entering the first delayed corner is reported separately;
there are no oversized gaps within the 65--89 ms required window.  Every one
of the 960,002 expected 25 ns corners is present at least once within 1e-14 s, and the
maximum analytic triangle error is 2.09e-10 V.  Values before the actual delay
(`64.999975 ms`) remain zero.  The 5 ns first row is the isolated transient
run's normal initial step (the checker permits up to the configured 500 ns
maximum); it is not treated as the native host's separate 1 ns startup rule.

The raw file is retained together with a 43 MB `pacer.raw.gz`, logs, checker
receipt, superseded checker versions, exact deck/source hashes, and artifact
hashes.  This proves parser syntax and breakpoint pacing in isolation only;
the parent must still validate any use of this compact source in the full
fault deck.
