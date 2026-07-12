// Build script for temper-geometry.
//
// This is a PyO3 extension module that shares the Python interpreter's
// existing libpython.  Unlike an embedded-Python binary, we do NOT
// link against a separate libpython — the pyo3/extension-module
// feature handles this automatically.
fn main() {
    // No extra linking needed.  The pyo3 crate and the
    // extension-module feature set up the correct ABI.
}
