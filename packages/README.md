# packages

The design-bundle crate chain. `temper-design-bundle` builds the
`temper_design_bundle_python` module (strict bridge, pin-map validation, net
admission, freshness checks) that zapote's unit tools import; the other crates
are its path dependencies.

| Crate | Role |
|---|---|
| `temper-design-bundle` | Validated, provenance-carrying Atopile design boundary (pyo3 module) |
| `temper-pcl-ir` | Shared typed PCL intermediate representation |
| `temper-geometry` | 2D geometry kernels |
| `temper-io-types` | Shared IO types |
| `temper-rust-router-core` | Pure-Rust core types used by the bundle |
| `temper-py-bridge`, `temper-py-bridge-derive` | pyo3 bridge helpers |

CI: `.github/workflows/crates.yml`. Build the Python module with `uv sync`.
