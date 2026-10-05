# R5 thermal verification

`./run.sh` completed against final CAD scalar SHA256 `420fdbe70bef0dbaf73cb7b03821721cec9e9065e2e85f774eff2d2a9d0219e3`.

- 25 tests pass (14 inherited,11 added).
- rustfmt check, rustc with warnings denied, and direct clippy-driver with warnings denied pass.
- 8 CSVs,784 data rows.
- Frozen kernel SHA256 is pinned in inputs.sha256; no copied kernel is maintained.
- Post-run receipt pins CAD, source, kernel and comparison output. Output validation must check the receipt before interpreting these results.
- Physical validation: NOT_RUN.

The whole-wire axial-path regression test was mutation-checked: restoring the prior omitted anchor resistance fails with exit101.
