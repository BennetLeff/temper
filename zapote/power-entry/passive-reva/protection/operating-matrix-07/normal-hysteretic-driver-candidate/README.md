# Hysteretic authored-driver candidate (prepared, unexecuted)

This candidate starts from `first-invalid-capture/run/cold.cir` and the
`normal-tracked` include set. It replaces the original threshold driver block
with the reviewed `authored_logic_hysteretic.inc` subcircuit. The retained
`Rgate=10` and `Rgs=10k` paths are unchanged. The `Ben` monitor now reports the
driver qualification states (`inm_logic` and `aux_logic`) rather than the old
single threshold expression. The `.save` line and callback diagnostics use
`xdriver.driver_req` and `xdriver.drv_delay` so the first-invalid snapshot
continues to name the actual driver nodes.

`inputs.json` records the source, include, authored-logic and compiled-host
hashes. `verify.rs` proves the inverse cold/progress changes and reconstructs
the exact protection block replacement; it also compares every unchanged
include byte-for-byte. Build and run it from this directory:

```sh
rustc --edition=2021 -D warnings -O verify.rs -o /tmp/matrix07-hysteretic-verify
/tmp/matrix07-hysteretic-verify
```

The unique host is `/private/tmp/matrix07-hysteretic-driver-host`, built from
the copied first-invalid callback with ngspice 45.2. Its exact five-argument
protocol is:

```text
./matrix07-hysteretic-driver-host cold.cir WALL_SECONDS TARGET_SECONDS trace.fifo first-invalid.tsv
```

The isolated `smoke/` directory ran this host for a two-second wall limit,
stopped at 7.9033847801 ms simulated time with `first_invalid=false`, and
contained all sixteen diagnostic names with finite first 1000 rows. The full
candidate has not been launched and has no root FIFO or full-run output.
