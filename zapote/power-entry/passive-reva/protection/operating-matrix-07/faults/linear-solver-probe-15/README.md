# Linear-solver probe (bounded startup diagnostic)

This is a two-run diagnostic of `faults/startup-candidate-13/case.cir`.  It
does not change a campaign model or establish that KLU is a production repair.
The only deck changes in this owned probe are `TSTOP=8.900000000000e-2` to
`TSTOP=1.000000000000e-2` (to stay before the 75 ms fault) and, for the KLU
copy only, one `.options klu` line.  The original case hash is
`42d8e284cdef229e5e305fb49d2dea43c81d7fcb1dfe0fa01a2cb14ead9effda`;
probe deck hashes and all copied include hashes are in `input-sha256.txt`.

## Solver support

The installed executable is ngspice 45.2 and prints
`Compiled with KLU Direct Linear Solver`.  The installed release `NEWS` file
states that KLU is optional and selected with `option klu` (at
`/opt/homebrew/Cellar/ngspice/45.2/NEWS`, line 111).  This establishes that
the option is supported by this binary; it does not establish numerical
equivalence or production suitability for the XSPICE/controller model.

## Exact bounded commands and results

From this directory, the runs were:

```text
/usr/bin/time -p ngspice -b -r sparse.raw -o sparse.log sparse/case.cir > sparse.stdout 2> sparse.stderr
/usr/bin/time -p ngspice -b -r klu.raw    -o klu.log    klu/case.cir    > klu.stdout    2> klu.stderr
```

The SPARSE run exits 1 after 2.19 s wall (1.91917 s ngspice analysis), with
`doAnalyses: TRAN: Timestep too small; time = 0.00441687, timestep =
6.25e-19: trouble with node "vbody#branch"`.  Its raw file has 24,712 points
and the independent Rust raw-header/last-point check in `inspect_raw.rs`
reports finite endpoint `4.41687293081717298e-3 s`.

The KLU run exits 0 after 7.80 s wall (6.60446 s ngspice analysis), prints
`Using KLU as Direct Linear Solver`, and writes 142,428 points.  The same Rust
check reports finite endpoint `1.00000000000000002e-2 s`, matching the probe
TSTOP.  No electrical parameters, tolerances, source waveforms, fault time,
or device models were changed between the two copies.

The raw files and logs are evidence for this short startup experiment only;
their SHA-256 values, along with the Rust inspection source/binary hashes, are
retained in the directory.  KLU reaching 10 ms is a useful causal probe against the SPARSE
failure at 4.4169 ms, but is not evidence of stable 75/89 ms fault behavior,
full-trace event validity, or a safe solver substitution.  Any adoption needs
a separately source-bound comparison at the actual campaign horizon and the
existing event/energy/fault checks.
