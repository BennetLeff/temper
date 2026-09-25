# Stall trace analysis

`analyze.rs` is a standalone Rust/std reader for the canonical
`diagnostic-capture/before-stall.tsv`. It reads rows once, counts exact
minimum-step intervals, broad signal-change indicators, and 2.5 V crossings
of `xu.raw`/`xu.pwm_hold`; it also reports the post-hoc M2-weighted margin.
Signal changes are evidence for temporal correlation only; a minimum timestep
does not prove a root cause.

```sh
rustc --edition=2021 -O analyze.rs -o /tmp/matrix07-stall-analysis
/tmp/matrix07-stall-analysis /path/to/before-stall.tsv > report.txt
```
