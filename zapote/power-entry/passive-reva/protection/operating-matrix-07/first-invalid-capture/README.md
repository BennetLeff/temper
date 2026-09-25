# First-invalid-time diagnostic harness

This folder is a bounded diagnostic copy of `normal-tracked`. It does not
change the electrical equations, models, tolerances, initial conditions or
the tracked harness. The only deck change is an expanded `.save` line that
retains the original vectors plus:

```text
v(xu.raw) v(xu.pwm_hold) v(pwm) v(pwm_input) v(drv_req) v(drv)
v(xu.phase) v(xu.blank) v(isense) v(xu.ov) v(xu.fault)
v(xu.pcl_hold) v(xu.pcl_request) v(disable) v(xu.m1) v(xu.m2)
```

The copied model/include hashes match `normal-tracked` byte-for-byte:

| input | SHA-256 |
| --- | --- |
| `clamp.inc` | `96cd8d6bfd3870b22403c39437ef2625f0a930f9e06632adcebbc45b61b9dcde` |
| `standby.inc` | `94d995d17a85ef932fe511bb2adbee02a1cd3fd1c88604b16d6b6929b31a50eb` |
| `protection.inc` | `b57b854883ee992dad036fd49c5a249b457e200873a3408652186de59122ea1c` |
| `ucc28180-pwm-latch.inc` | `2e885755aad4d03fb9c06d7c556faf23ad0ae7922f581d56752db78933b97251` |

## Callback behavior

`progress.rs` scans only the scale/time vector on ordinary accepted points,
so the 16 named analog diagnostics add no per-point string allocation or
name-mapping work. Once the callback sees the first non-increasing accepted
time (including a non-finite time), it performs one bounded scan of the named
diagnostics, copies their scalar values into an owned snapshot, publishes the
flag, and returns. It never retains ngspice pointers and never sends a
command from the callback. The main thread then issues `bg_halt`, waits for
ngspice to become idle, writes `first-invalid.tsv`, metadata and `stop.txt`,
and exports the retained full trace.

The Rust unit tests cover the time predicate, name mapping, and a synthetic
two-callback `Values` sequence. The synthetic sequence verifies exact
previous/current callback indices and times and all 16 copied diagnostics.

## Verification performed

```text
rustc --edition=2021 --test progress.rs -o progress-tests
./progress-tests                         # 3 passed
rustc --edition=2021 -O progress.rs \
  -L /opt/homebrew/lib -l ngspice -o first-invalid-progress
```

The vector-slicing smoke test was deliberately run before choosing an export
strategy. `v(out)[lo,hi]` through `wrdata` produced a full-length, malformed
scale/value output rather than a bounded window, so it is rejected. The
harness uses the existing safe full-trace path. For a real run, feed that
path through a FIFO and gzip while ngspice writes:

```text
mkfifo trace.tsv
gzip -c < trace.tsv > trace.tsv.gz &
DYLD_LIBRARY_PATH=/opt/homebrew/opt/libngspice/lib \
SPICE_SCRIPTS=/opt/homebrew/share/ngspice/scripts \
./first-invalid-progress cold.cir 1200 0.5 trace.tsv first-invalid.tsv
wait
```

The full cold run has **not** been launched from this folder. The smoke deck
(`slice-smoke.cir`) completed to exactly 20 µs with 213 callback points and
214 exported rows, `first_invalid=false`, and a clean solver-stop result.
This is transport verification only; it is not evidence about the PFC
operating point.

`names-smoke.cir` adds a short behavioral subcircuit that exposes every
requested diagnostic node. Its callback metadata reports
`seen_names_mask=65535` and `expected_names_mask=65535`; the ngspice initial
solution and export header contain names such as `xu.raw`, `xu.pwm_hold`,
`xu.phase`, `xu.m1`, `xu.m2`, `pwm`, `pwm_input`, `drv_req`, `drv`, `isense`,
`disable`, `xu.ov`, `xu.fault`, `xu.pcl_hold`, and `xu.pcl_request`. This
confirms the callback name shape before any long replay. The callback's
synthetic duplicate-time test also captures all 16 values with
`missing_mask=0`.
