// export_types: TraceSegment, TraceVia, ExportResult.
//
// Pure data holders, always compiled (including on wasm32). The
// `#[cfg(feature = "python")]` submodule below wraps each one in a
// pyclass with the same Python-visible name and field set as before;
// the wrapper is a plain struct (not a newtype over the pure one) because
// pyo3's `#[pyo3(get, set)]` field shorthand must be resolved by the
// `#[pyclass]` macro itself, which only sees literal `#[pyo3(...)]`
// attributes — `#[cfg_attr(feature = "python", pyo3(get, set))]` does not
// work here (the inner `cfg_attr` is still unresolved token soup when
// `#[pyclass]` expands, so it can't recognise it as its own helper
// attribute). Keeping the wrapper's fields flat and delegating formatting
// to the pure struct's methods keeps the two from drifting.

use std::path::PathBuf;

#[derive(Clone, Debug, PartialEq)]
pub struct TraceSegment {
    pub net: String,
    pub start: (f64, f64),
    pub end: (f64, f64),
    pub width: f64,
    pub layer: String,
}

impl TraceSegment {
    pub fn repr(&self) -> String {
        format!(
            "TraceSegment(net={:?}, start={:?}, end={:?}, width={}, layer={:?})",
            self.net, self.start, self.end, self.width, self.layer
        )
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct TraceVia {
    pub net: String,
    pub position: (f64, f64),
    pub size: f64,
    pub drill: f64,
    pub layers: Vec<String>,
}

impl TraceVia {
    pub fn repr(&self) -> String {
        format!(
            "TraceVia(net={:?}, position={:?}, size={}, drill={}, layers={:?})",
            self.net, self.position, self.size, self.drill, self.layers
        )
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct ExportResult {
    pub output_path: PathBuf,
    pub segments_added: usize,
    pub vias_added: usize,
    pub nets_exported: usize,
    pub nets_failed: usize,
    pub warnings: Vec<String>,
}

impl ExportResult {
    pub fn display(&self) -> String {
        format!(
            "Export complete: {} nets, {} segments, {} vias -> {}",
            self.nets_exported,
            self.segments_added,
            self.vias_added,
            self.output_path.display(),
        )
    }
}

#[cfg(feature = "python")]
mod py_bridge {
    use super::*;
    use pyo3::prelude::*;

    #[pyclass(name = "TraceSegment", from_py_object)]
    #[derive(Clone)]
    pub struct PyTraceSegment {
        #[pyo3(get, set)]
        pub net: String,
        #[pyo3(get, set)]
        pub start: (f64, f64),
        #[pyo3(get, set)]
        pub end: (f64, f64),
        #[pyo3(get, set)]
        pub width: f64,
        #[pyo3(get, set)]
        pub layer: String,
    }

    impl PyTraceSegment {
        fn pure(&self) -> TraceSegment {
            TraceSegment {
                net: self.net.clone(),
                start: self.start,
                end: self.end,
                width: self.width,
                layer: self.layer.clone(),
            }
        }
    }

    #[pymethods]
    impl PyTraceSegment {
        #[new]
        fn new(net: String, start: (f64, f64), end: (f64, f64), width: f64, layer: String) -> Self {
            PyTraceSegment {
                net,
                start,
                end,
                width,
                layer,
            }
        }

        fn __repr__(&self) -> String {
            self.pure().repr()
        }
    }

    #[pyclass(name = "TraceVia", from_py_object)]
    #[derive(Clone)]
    pub struct PyTraceVia {
        #[pyo3(get, set)]
        pub net: String,
        #[pyo3(get, set)]
        pub position: (f64, f64),
        #[pyo3(get, set)]
        pub size: f64,
        #[pyo3(get, set)]
        pub drill: f64,
        #[pyo3(get, set)]
        pub layers: Vec<String>,
    }

    impl PyTraceVia {
        fn pure(&self) -> TraceVia {
            TraceVia {
                net: self.net.clone(),
                position: self.position,
                size: self.size,
                drill: self.drill,
                layers: self.layers.clone(),
            }
        }
    }

    #[pymethods]
    impl PyTraceVia {
        #[new]
        fn new(
            net: String,
            position: (f64, f64),
            size: f64,
            drill: f64,
            layers: Vec<String>,
        ) -> Self {
            PyTraceVia {
                net,
                position,
                size,
                drill,
                layers,
            }
        }

        fn __repr__(&self) -> String {
            self.pure().repr()
        }
    }

    #[pyclass(name = "ExportResult")]
    pub struct PyExportResult {
        #[pyo3(get, set)]
        pub output_path: PathBuf,
        #[pyo3(get, set)]
        pub segments_added: usize,
        #[pyo3(get, set)]
        pub vias_added: usize,
        #[pyo3(get, set)]
        pub nets_exported: usize,
        #[pyo3(get, set)]
        pub nets_failed: usize,
        #[pyo3(get, set)]
        pub warnings: Vec<String>,
    }

    impl PyExportResult {
        fn pure(&self) -> ExportResult {
            ExportResult {
                output_path: self.output_path.clone(),
                segments_added: self.segments_added,
                vias_added: self.vias_added,
                nets_exported: self.nets_exported,
                nets_failed: self.nets_failed,
                warnings: self.warnings.clone(),
            }
        }
    }

    #[pymethods]
    impl PyExportResult {
        #[new]
        fn new(
            output_path: PathBuf,
            segments_added: usize,
            vias_added: usize,
            nets_exported: usize,
            nets_failed: usize,
            warnings: Vec<String>,
        ) -> Self {
            PyExportResult {
                output_path,
                segments_added,
                vias_added,
                nets_exported,
                nets_failed,
                warnings,
            }
        }

        fn __str__(&self) -> String {
            self.pure().display()
        }

        fn __repr__(&self) -> String {
            self.pure().display()
        }
    }
}

#[cfg(feature = "python")]
pub use py_bridge::{PyExportResult, PyTraceSegment, PyTraceVia};

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    #[cfg_attr(test, test)]
    fn trace_segment_repr() {
        let seg = TraceSegment {
            net: "GND".into(),
            start: (0.0, 0.0),
            end: (1.0, 1.0),
            width: 0.25,
            layer: "F.Cu".into(),
        };
        assert_eq!(
            seg.repr(),
            "TraceSegment(net=\"GND\", start=(0.0, 0.0), end=(1.0, 1.0), width=0.25, layer=\"F.Cu\")"
        );
    }

    #[cfg_attr(test, test)]
    fn export_result_display() {
        let result = ExportResult {
            output_path: PathBuf::from("/tmp/out.dsn"),
            segments_added: 3,
            vias_added: 1,
            nets_exported: 2,
            nets_failed: 0,
            warnings: vec![],
        };
        assert_eq!(
            result.display(),
            "Export complete: 2 nets, 3 segments, 1 vias -> /tmp/out.dsn"
        );
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("export_types::tests::trace_segment_repr", trace_segment_repr),
        ("export_types::tests::export_result_display", export_result_display),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
