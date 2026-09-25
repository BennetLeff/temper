# Interface active clamp 15 — concrete prototype

The candidate is documented in `design.md`; all arithmetic is reproduced by
`clamp_calc.rs` and `results.csv`. Run:

```text
rustc --edition=2021 --test clamp_calc.rs -o clamp_calc_tests
./clamp_calc_tests
```

This directory is an isolated handoff artifact. It does not modify the
revision-11/136-component circuit, PCB, firmware, or production BOM.
