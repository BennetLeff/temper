// Build script for temper-quality-oracle.
//
// This is a PyO3 extension module that shares the Python interpreter's
// existing libpython.  Unlike an embedded-Python binary, we do NOT
// link against a separate libpython — the `pyo3/extension-module`
// feature handles this automatically.
//
// Origin: U1 of docs/plans/2026-07-01-009-feat-quality-oracle-typed-pipeline-plan.md
fn main() {
    // No extra linking needed.  The `pyo3` crate and the
    // `extension-module` feature set up the correct ABI.
}
