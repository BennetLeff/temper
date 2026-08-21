// dsn_types: DSNExpression, dsn_list, DSNRect, DSNCircle, DSNPath.
//
// Note: nothing in the Python codebase currently imports these from
// `temper_io_types` — `temper_placer/io/dsn.py` has its own pure-Python
// `DSNExpression` used by the real DSN exporter. These Rust types are kept
// working (they are still part of the public pymodule surface) but are not
// on the byte-identical-output hot path the way the JSON/SES serializers
// are.
//
// `DSNExpression.args` previously stored `Vec<Py<PyAny>>` — an
// arbitrary Python object per argument — which cannot exist without pyo3.
// The pure core instead models an argument as the closed set of shapes DSN
// expressions actually need: floats, ints, strings, nested expressions, or
// (for full fidelity with the old `bound.str()` fallback for anything
// else) a pre-formatted raw string.

#[cfg(feature = "python")]
use pyo3::prelude::*;

#[derive(Clone, Debug, PartialEq)]
pub enum DsnArg {
    Float(f64),
    Int(i64),
    Str(String),
    Nested(Box<DsnExpressionData>),
    /// Fallback for anything else — stored pre-formatted (unquoted),
    /// matching the old `bound.str()?.to_string()` catch-all branch.
    Raw(String),
}

#[derive(Clone, Debug, PartialEq)]
pub struct DsnExpressionData {
    pub name: String,
    pub args: Vec<DsnArg>,
    pub comment: Option<String>,
}

pub fn format_dsn_arg(arg: &DsnArg) -> String {
    match arg {
        DsnArg::Float(f) => {
            let s = format!("{:.6}", f);
            let trimmed = s.trim_end_matches('0').trim_end_matches('.');
            if trimmed.is_empty() {
                "0".to_string()
            } else {
                trimmed.to_string()
            }
        }
        DsnArg::Int(i) => i.to_string(),
        DsnArg::Str(s) => {
            if s.is_empty() {
                "\"\"".to_string()
            } else if s.contains(' ') || s.contains('(') || s.contains(')') || s.contains('"') {
                format!("\"{}\"", s.replace('"', "\\\""))
            } else {
                s.clone()
            }
        }
        DsnArg::Nested(expr) => dsn_expression_to_string(expr),
        DsnArg::Raw(s) => s.clone(),
    }
}

pub fn dsn_expression_to_string(expr: &DsnExpressionData) -> String {
    let body = if expr.args.is_empty() {
        format!("({})", expr.name)
    } else {
        let formatted: Vec<String> = expr.args.iter().map(format_dsn_arg).collect();
        format!("({} {})", expr.name, formatted.join(" "))
    };
    // `if self.comment:` — Python tests TRUTHINESS, so an EMPTY comment string
    // emits no comment line at all. Matching on `Some(_)` alone would prefix a
    // bare ";\n", which is a different DSN file. (Found by the candidate-6 PBT
    // suite, property P5.)
    match &expr.comment {
        Some(c) if !c.is_empty() => format!(";{}\n{}", c, body),
        _ => body,
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct DsnRectData {
    pub layer: String,
    pub x1: f64,
    pub y1: f64,
    pub x2: f64,
    pub y2: f64,
}

impl DsnRectData {
    pub fn to_dsn(&self) -> DsnExpressionData {
        DsnExpressionData {
            name: "rect".into(),
            args: vec![
                DsnArg::Str(self.layer.clone()),
                DsnArg::Float(self.x1),
                DsnArg::Float(self.y1),
                DsnArg::Float(self.x2),
                DsnArg::Float(self.y2),
            ],
            comment: None,
        }
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct DsnCircleData {
    pub layer: String,
    pub diameter: f64,
    pub x: f64,
    pub y: f64,
}

impl DsnCircleData {
    pub fn to_dsn(&self) -> DsnExpressionData {
        DsnExpressionData {
            name: "circle".into(),
            args: vec![
                DsnArg::Str(self.layer.clone()),
                DsnArg::Float(self.diameter),
                DsnArg::Float(self.x),
                DsnArg::Float(self.y),
            ],
            comment: None,
        }
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct DsnPathData {
    pub layer: String,
    pub width: f64,
    pub points: Vec<(f64, f64)>,
}

impl DsnPathData {
    pub fn to_dsn(&self) -> DsnExpressionData {
        let mut args = Vec::with_capacity(2 + self.points.len() * 2);
        args.push(DsnArg::Str(self.layer.clone()));
        args.push(DsnArg::Float(self.width));
        for (x, y) in &self.points {
            args.push(DsnArg::Float(*x));
            args.push(DsnArg::Float(*y));
        }
        DsnExpressionData {
            name: "path".into(),
            args,
            comment: None,
        }
    }
}

// ---------------------------------------------------------------------------
// pyo3 boundary
// ---------------------------------------------------------------------------

#[cfg(feature = "python")]
mod py_bridge {
    use super::*;
    use pyo3::types::PyTuple;

    fn py_to_dsn_arg(bound: &Bound<'_, PyAny>) -> PyResult<DsnArg> {
        if let Ok(expr) = bound.extract::<PyRef<'_, DSNExpression>>() {
            return Ok(DsnArg::Nested(Box::new(expr.inner.clone())));
        }
        if bound.is_instance_of::<pyo3::types::PyFloat>() {
            return Ok(DsnArg::Float(bound.extract()?));
        }
        if bound.is_instance_of::<pyo3::types::PyBool>() {
            // MUST precede the `PyInt` arm: `bool` is a subclass of `int` in
            // CPython, so `is_instance_of::<PyInt>()` accepts it and would
            // format `True` as `1`. The Python `DSNExpression.__str__` tests
            // `float`, then `str`, then falls through to `str(v)` — and
            // `str(True)` is `"True"`, not `"1"`.
            let s: String = bound.str()?.to_string();
            return Ok(DsnArg::Raw(s));
        }
        if bound.is_instance_of::<pyo3::types::PyInt>() {
            // Match the pre-Rust-port behaviour for large ints (which
            // Python's arbitrary-precision `int` can represent but `i64`
            // cannot): fall back to Python's own `str()` rather than
            // erroring, formatted unquoted like every other catch-all.
            if let Ok(i) = bound.extract::<i64>() {
                return Ok(DsnArg::Int(i));
            }
            let s: String = bound.str()?.to_string();
            return Ok(DsnArg::Raw(s));
        }
        if bound.is_instance_of::<pyo3::types::PyString>() {
            return Ok(DsnArg::Str(bound.extract()?));
        }
        let s: String = bound.str()?.to_string();
        Ok(DsnArg::Raw(s))
    }

    fn dsn_arg_to_py(py: Python<'_>, arg: &DsnArg) -> PyResult<Py<PyAny>> {
        use pyo3::IntoPyObject;
        match arg {
            DsnArg::Float(f) => Ok((*f).into_pyobject(py)?.unbind().into()),
            DsnArg::Int(i) => Ok((*i).into_pyobject(py)?.unbind().into()),
            DsnArg::Str(s) => Ok(s.clone().into_pyobject(py)?.unbind().into()),
            DsnArg::Raw(s) => Ok(s.clone().into_pyobject(py)?.unbind().into()),
            DsnArg::Nested(expr) => {
                let obj = Py::new(
                    py,
                    DSNExpression {
                        inner: (**expr).clone(),
                    },
                )?;
                Ok(obj.into())
            }
        }
    }

    #[pyclass(name = "DSNExpression")]
    pub struct DSNExpression {
        pub(super) inner: DsnExpressionData,
    }

    impl DSNExpression {
        /// Wrap already-built pure-core data for return across the boundary.
        /// Used by `dsn_exporter`, which constructs whole `DsnExpressionData`
        /// trees in pure Rust and never round-trips them through Python.
        pub fn from_data(inner: DsnExpressionData) -> Self {
            DSNExpression { inner }
        }
    }

    #[pymethods]
    impl DSNExpression {
        #[new]
        #[pyo3(signature = (name, args = vec![], comment = None))]
        fn new(
            name: String,
            args: Vec<Bound<'_, PyAny>>,
            comment: Option<String>,
        ) -> PyResult<Self> {
            let args = args
                .iter()
                .map(py_to_dsn_arg)
                .collect::<PyResult<Vec<_>>>()?;
            Ok(DSNExpression {
                inner: DsnExpressionData {
                    name,
                    args,
                    comment,
                },
            })
        }

        #[getter]
        fn name(&self) -> String {
            self.inner.name.clone()
        }

        #[setter]
        fn set_name(&mut self, name: String) {
            self.inner.name = name;
        }

        #[getter]
        fn comment(&self) -> Option<String> {
            self.inner.comment.clone()
        }

        #[setter]
        fn set_comment(&mut self, comment: Option<String>) {
            self.inner.comment = comment;
        }

        #[getter]
        fn args(&self, py: Python<'_>) -> PyResult<Vec<Py<PyAny>>> {
            self.inner
                .args
                .iter()
                .map(|a| dsn_arg_to_py(py, a))
                .collect()
        }

        #[setter]
        fn set_args(&mut self, args: Vec<Bound<'_, PyAny>>) -> PyResult<()> {
            self.inner.args = args.iter().map(py_to_dsn_arg).collect::<PyResult<_>>()?;
            Ok(())
        }

        fn with_comment(&self, line: String) -> Self {
            DSNExpression {
                inner: DsnExpressionData {
                    name: self.inner.name.clone(),
                    args: self.inner.args.clone(),
                    comment: Some(line),
                },
            }
        }

        fn __str__(&self) -> String {
            dsn_expression_to_string(&self.inner)
        }

        fn __repr__(&self) -> String {
            format!(
                "DSNExpression(name={:?}, args.len()={}, comment={:?})",
                self.inner.name,
                self.inner.args.len(),
                self.inner.comment
            )
        }
    }

    #[pyfunction]
    #[pyo3(signature = (name, *args))]
    pub fn dsn_list(
        py: Python<'_>,
        name: String,
        args: &Bound<'_, PyTuple>,
    ) -> PyResult<Py<DSNExpression>> {
        let arg_vec = args
            .iter()
            .map(|a| py_to_dsn_arg(&a))
            .collect::<PyResult<Vec<_>>>()?;
        Py::new(
            py,
            DSNExpression {
                inner: DsnExpressionData {
                    name,
                    args: arg_vec,
                    comment: None,
                },
            },
        )
    }

    #[pyclass(name = "DSNRect", from_py_object)]
    #[derive(Clone)]
    pub struct PyDsnRect {
        #[pyo3(get, set)]
        pub layer: String,
        #[pyo3(get, set)]
        pub x1: f64,
        #[pyo3(get, set)]
        pub y1: f64,
        #[pyo3(get, set)]
        pub x2: f64,
        #[pyo3(get, set)]
        pub y2: f64,
    }

    impl PyDsnRect {
        fn data(&self) -> DsnRectData {
            DsnRectData {
                layer: self.layer.clone(),
                x1: self.x1,
                y1: self.y1,
                x2: self.x2,
                y2: self.y2,
            }
        }
    }

    #[pymethods]
    impl PyDsnRect {
        #[new]
        fn new(layer: String, x1: f64, y1: f64, x2: f64, y2: f64) -> Self {
            PyDsnRect {
                layer,
                x1,
                y1,
                x2,
                y2,
            }
        }

        fn to_dsn(&self, py: Python<'_>) -> PyResult<Py<DSNExpression>> {
            Py::new(
                py,
                DSNExpression {
                    inner: self.data().to_dsn(),
                },
            )
        }

        fn __repr__(&self) -> String {
            format!(
                "DSNRect(layer={:?}, x1={}, y1={}, x2={}, y2={})",
                self.layer, self.x1, self.y1, self.x2, self.y2
            )
        }
    }

    #[pyclass(name = "DSNCircle", from_py_object)]
    #[derive(Clone)]
    pub struct PyDsnCircle {
        #[pyo3(get, set)]
        pub layer: String,
        #[pyo3(get, set)]
        pub diameter: f64,
        #[pyo3(get, set)]
        pub x: f64,
        #[pyo3(get, set)]
        pub y: f64,
    }

    impl PyDsnCircle {
        fn data(&self) -> DsnCircleData {
            DsnCircleData {
                layer: self.layer.clone(),
                diameter: self.diameter,
                x: self.x,
                y: self.y,
            }
        }
    }

    #[pymethods]
    impl PyDsnCircle {
        #[new]
        #[pyo3(signature = (layer, diameter, x = 0.0, y = 0.0))]
        fn new(layer: String, diameter: f64, x: f64, y: f64) -> Self {
            PyDsnCircle {
                layer,
                diameter,
                x,
                y,
            }
        }

        fn to_dsn(&self, py: Python<'_>) -> PyResult<Py<DSNExpression>> {
            Py::new(
                py,
                DSNExpression {
                    inner: self.data().to_dsn(),
                },
            )
        }

        fn __repr__(&self) -> String {
            format!(
                "DSNCircle(layer={:?}, diameter={}, x={}, y={})",
                self.layer, self.diameter, self.x, self.y
            )
        }
    }

    #[pyclass(name = "DSNPath", from_py_object)]
    #[derive(Clone)]
    pub struct PyDsnPath {
        #[pyo3(get, set)]
        pub layer: String,
        #[pyo3(get, set)]
        pub width: f64,
        #[pyo3(get, set)]
        pub points: Vec<(f64, f64)>,
    }

    impl PyDsnPath {
        fn data(&self) -> DsnPathData {
            DsnPathData {
                layer: self.layer.clone(),
                width: self.width,
                points: self.points.clone(),
            }
        }
    }

    #[pymethods]
    impl PyDsnPath {
        #[new]
        fn new(layer: String, width: f64, points: Vec<(f64, f64)>) -> Self {
            PyDsnPath {
                layer,
                width,
                points,
            }
        }

        fn to_dsn(&self, py: Python<'_>) -> PyResult<Py<DSNExpression>> {
            Py::new(
                py,
                DSNExpression {
                    inner: self.data().to_dsn(),
                },
            )
        }

        fn __repr__(&self) -> String {
            format!(
                "DSNPath(layer={:?}, width={}, points={:?})",
                self.layer, self.width, self.points
            )
        }
    }
}

#[cfg(feature = "python")]
pub use py_bridge::{DSNExpression, PyDsnCircle, PyDsnPath, PyDsnRect, dsn_list};

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

// --- BEGIN generated by scripts/gen_oracle_freeze.py: dsn_primitives ---
    /// Frozen golden vectors for DSN S-expression formatting (FREEZE, U4/U5, batch 3).
    /// Regenerate: `python3 scripts/gen_oracle_freeze.py --spec dsn_primitives`
    /// (requires reviving the deleted oracle from git history first -- see
    /// scripts/oracle_freeze_specs/dsn_primitives.py's module docstring).
    #[cfg(test)]
    mod frozen_dsn_tests {
        use super::*;

        #[derive(Clone, Copy)]
        enum FrozenDsnArg {
            Float(f64),
            Int(i64),
            Str(&'static str),
            Nested(&'static FrozenDsnExpr),
            Raw(&'static str),
        }

        #[derive(Clone, Copy)]
        struct FrozenDsnExpr {
            name: &'static str,
            args: &'static [FrozenDsnArg],
            comment: Option<&'static str>,
        }

        struct FrozenDsnCase {
            expr: FrozenDsnExpr,
            expected: &'static str,
            tags: &'static [&'static str],
        }

        static NESTED_0: FrozenDsnExpr = FrozenDsnExpr {
            name: "unit",
            args: &[FrozenDsnArg::Str("mm")],
            comment: None,
        };

        static NESTED_1: FrozenDsnExpr = FrozenDsnExpr {
            name: "b",
            args: &[FrozenDsnArg::Nested(&NESTED_37)],
            comment: None,
        };

        static NESTED_2: FrozenDsnExpr = FrozenDsnExpr {
            name: "sub",
            args: &[FrozenDsnArg::Str("x"), FrozenDsnArg::Float(f64::from_bits(0x3FF0000000000000_u64))],
            comment: None,
        };

        static NESTED_3: FrozenDsnExpr = FrozenDsnExpr {
            name: "sub",
            args: &[FrozenDsnArg::Str("x"), FrozenDsnArg::Float(f64::from_bits(0x3FF0000000000000_u64))],
            comment: None,
        };

        static NESTED_4: FrozenDsnExpr = FrozenDsnExpr {
            name: "sub",
            args: &[FrozenDsnArg::Str("x"), FrozenDsnArg::Float(f64::from_bits(0x3FF0000000000000_u64))],
            comment: None,
        };

        static NESTED_5: FrozenDsnExpr = FrozenDsnExpr {
            name: "sub",
            args: &[FrozenDsnArg::Str("x"), FrozenDsnArg::Float(f64::from_bits(0x3FF0000000000000_u64))],
            comment: None,
        };

        static NESTED_6: FrozenDsnExpr = FrozenDsnExpr {
            name: "sub",
            args: &[FrozenDsnArg::Str("x"), FrozenDsnArg::Float(f64::from_bits(0x3FF0000000000000_u64))],
            comment: None,
        };

        static NESTED_7: FrozenDsnExpr = FrozenDsnExpr {
            name: "sub",
            args: &[FrozenDsnArg::Str("x"), FrozenDsnArg::Float(f64::from_bits(0x3FF0000000000000_u64))],
            comment: None,
        };

        static NESTED_8: FrozenDsnExpr = FrozenDsnExpr {
            name: "sub",
            args: &[FrozenDsnArg::Str("x"), FrozenDsnArg::Float(f64::from_bits(0x3FF0000000000000_u64))],
            comment: None,
        };

        static NESTED_9: FrozenDsnExpr = FrozenDsnExpr {
            name: "sub",
            args: &[FrozenDsnArg::Str("x"), FrozenDsnArg::Float(f64::from_bits(0x3FF0000000000000_u64))],
            comment: None,
        };

        static NESTED_10: FrozenDsnExpr = FrozenDsnExpr {
            name: "sub",
            args: &[FrozenDsnArg::Str("x"), FrozenDsnArg::Float(f64::from_bits(0x3FF0000000000000_u64))],
            comment: None,
        };

        static NESTED_11: FrozenDsnExpr = FrozenDsnExpr {
            name: "sub",
            args: &[FrozenDsnArg::Str("x"), FrozenDsnArg::Float(f64::from_bits(0x3FF0000000000000_u64))],
            comment: None,
        };

        static NESTED_12: FrozenDsnExpr = FrozenDsnExpr {
            name: "sub",
            args: &[FrozenDsnArg::Str("x"), FrozenDsnArg::Float(f64::from_bits(0x3FF0000000000000_u64))],
            comment: None,
        };

        static NESTED_13: FrozenDsnExpr = FrozenDsnExpr {
            name: "sub",
            args: &[FrozenDsnArg::Str("x"), FrozenDsnArg::Float(f64::from_bits(0x3FF0000000000000_u64))],
            comment: None,
        };

        static NESTED_14: FrozenDsnExpr = FrozenDsnExpr {
            name: "sub",
            args: &[FrozenDsnArg::Str("x"), FrozenDsnArg::Float(f64::from_bits(0x3FF0000000000000_u64))],
            comment: None,
        };

        static NESTED_15: FrozenDsnExpr = FrozenDsnExpr {
            name: "sub",
            args: &[FrozenDsnArg::Str("x"), FrozenDsnArg::Float(f64::from_bits(0x3FF0000000000000_u64))],
            comment: None,
        };

        static NESTED_16: FrozenDsnExpr = FrozenDsnExpr {
            name: "sub",
            args: &[FrozenDsnArg::Str("x"), FrozenDsnArg::Float(f64::from_bits(0x3FF0000000000000_u64))],
            comment: None,
        };

        static NESTED_17: FrozenDsnExpr = FrozenDsnExpr {
            name: "sub",
            args: &[FrozenDsnArg::Str("x"), FrozenDsnArg::Float(f64::from_bits(0x3FF0000000000000_u64))],
            comment: None,
        };

        static NESTED_18: FrozenDsnExpr = FrozenDsnExpr {
            name: "sub",
            args: &[FrozenDsnArg::Str("x"), FrozenDsnArg::Float(f64::from_bits(0x3FF0000000000000_u64))],
            comment: None,
        };

        static NESTED_19: FrozenDsnExpr = FrozenDsnExpr {
            name: "sub",
            args: &[FrozenDsnArg::Str("x"), FrozenDsnArg::Float(f64::from_bits(0x3FF0000000000000_u64))],
            comment: None,
        };

        static NESTED_20: FrozenDsnExpr = FrozenDsnExpr {
            name: "sub",
            args: &[FrozenDsnArg::Str("x"), FrozenDsnArg::Float(f64::from_bits(0x3FF0000000000000_u64))],
            comment: None,
        };

        static NESTED_21: FrozenDsnExpr = FrozenDsnExpr {
            name: "sub",
            args: &[FrozenDsnArg::Str("x"), FrozenDsnArg::Float(f64::from_bits(0x3FF0000000000000_u64))],
            comment: None,
        };

        static NESTED_22: FrozenDsnExpr = FrozenDsnExpr {
            name: "sub",
            args: &[FrozenDsnArg::Str("x"), FrozenDsnArg::Float(f64::from_bits(0x3FF0000000000000_u64))],
            comment: None,
        };

        static NESTED_23: FrozenDsnExpr = FrozenDsnExpr {
            name: "sub",
            args: &[FrozenDsnArg::Str("x"), FrozenDsnArg::Float(f64::from_bits(0x3FF0000000000000_u64))],
            comment: None,
        };

        static NESTED_24: FrozenDsnExpr = FrozenDsnExpr {
            name: "sub",
            args: &[FrozenDsnArg::Str("x"), FrozenDsnArg::Float(f64::from_bits(0x3FF0000000000000_u64))],
            comment: None,
        };

        static NESTED_25: FrozenDsnExpr = FrozenDsnExpr {
            name: "sub",
            args: &[FrozenDsnArg::Str("x"), FrozenDsnArg::Float(f64::from_bits(0x3FF0000000000000_u64))],
            comment: None,
        };

        static NESTED_26: FrozenDsnExpr = FrozenDsnExpr {
            name: "sub",
            args: &[FrozenDsnArg::Str("x"), FrozenDsnArg::Float(f64::from_bits(0x3FF0000000000000_u64))],
            comment: None,
        };

        static NESTED_27: FrozenDsnExpr = FrozenDsnExpr {
            name: "sub",
            args: &[FrozenDsnArg::Str("x"), FrozenDsnArg::Float(f64::from_bits(0x3FF0000000000000_u64))],
            comment: None,
        };

        static NESTED_28: FrozenDsnExpr = FrozenDsnExpr {
            name: "sub",
            args: &[FrozenDsnArg::Str("x"), FrozenDsnArg::Float(f64::from_bits(0x3FF0000000000000_u64))],
            comment: None,
        };

        static NESTED_29: FrozenDsnExpr = FrozenDsnExpr {
            name: "sub",
            args: &[FrozenDsnArg::Str("x"), FrozenDsnArg::Float(f64::from_bits(0x3FF0000000000000_u64))],
            comment: None,
        };

        static NESTED_30: FrozenDsnExpr = FrozenDsnExpr {
            name: "sub",
            args: &[FrozenDsnArg::Str("x"), FrozenDsnArg::Float(f64::from_bits(0x3FF0000000000000_u64))],
            comment: None,
        };

        static NESTED_31: FrozenDsnExpr = FrozenDsnExpr {
            name: "sub",
            args: &[FrozenDsnArg::Str("x"), FrozenDsnArg::Float(f64::from_bits(0x3FF0000000000000_u64))],
            comment: None,
        };

        static NESTED_32: FrozenDsnExpr = FrozenDsnExpr {
            name: "sub",
            args: &[FrozenDsnArg::Str("x"), FrozenDsnArg::Float(f64::from_bits(0x3FF0000000000000_u64))],
            comment: None,
        };

        static NESTED_33: FrozenDsnExpr = FrozenDsnExpr {
            name: "sub",
            args: &[FrozenDsnArg::Str("x"), FrozenDsnArg::Float(f64::from_bits(0x3FF0000000000000_u64))],
            comment: None,
        };

        static NESTED_34: FrozenDsnExpr = FrozenDsnExpr {
            name: "sub",
            args: &[FrozenDsnArg::Str("x"), FrozenDsnArg::Float(f64::from_bits(0x3FF0000000000000_u64))],
            comment: None,
        };

        static NESTED_35: FrozenDsnExpr = FrozenDsnExpr {
            name: "sub",
            args: &[FrozenDsnArg::Str("x"), FrozenDsnArg::Float(f64::from_bits(0x3FF0000000000000_u64))],
            comment: None,
        };

        static NESTED_36: FrozenDsnExpr = FrozenDsnExpr {
            name: "sub",
            args: &[FrozenDsnArg::Str("x"), FrozenDsnArg::Float(f64::from_bits(0x3FF0000000000000_u64))],
            comment: None,
        };

        static NESTED_37: FrozenDsnExpr = FrozenDsnExpr {
            name: "c",
            args: &[FrozenDsnArg::Str("deep")],
            comment: None,
        };

        const FROZEN_DSN_GOLDEN: &[FrozenDsnCase] = &[
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "pcb", args: &[], comment: None },
                expected: "(pcb)",
                tags: &["empty_args", "named:empty_expr"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "coord", args: &[FrozenDsnArg::Float(f64::from_bits(0x4024000000000000_u64)), FrozenDsnArg::Float(f64::from_bits(0x4025000000000000_u64)), FrozenDsnArg::Float(f64::from_bits(0x4025161F9F01B867_u64)), FrozenDsnArg::Float(f64::from_bits(0x0000000000000000_u64)), FrozenDsnArg::Float(f64::from_bits(0x8000000000000000_u64))], comment: None },
                expected: "(coord 10 10.5 10.54321 0 -0)",
                tags: &["arg:float", "float:fractional", "float:tiny", "float:zero", "named:simple_floats"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "pins", args: &[FrozenDsnArg::Int(1_i64), FrozenDsnArg::Int(2_i64), FrozenDsnArg::Int(100_i64)], comment: None },
                expected: "(pins 1 2 100)",
                tags: &["arg:int", "named:simple_ints"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "name", args: &[FrozenDsnArg::Str("GND"), FrozenDsnArg::Str("VCC (Power)"), FrozenDsnArg::Str("Quoted \"String\""), FrozenDsnArg::Str("")], comment: None },
                expected: "(name GND \"VCC (Power)\" \"Quoted \\\"String\\\"\" \"\")",
                tags: &["arg:str", "named:simple_strs", "str:empty", "str:special_chars"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "pcb", args: &[FrozenDsnArg::Str("sample"), FrozenDsnArg::Nested(&NESTED_0)], comment: None },
                expected: "(pcb sample (unit mm))",
                tags: &["arg:nested", "arg:str", "named:nested", "nested"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "pcb", args: &[FrozenDsnArg::Str("sample")], comment: Some("c: 1") },
                expected: ";c: 1\n(pcb sample)",
                tags: &["arg:str", "has_comment", "named:with_comment"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "pcb", args: &[FrozenDsnArg::Str("sample")], comment: Some("") },
                expected: "(pcb sample)",
                tags: &["arg:str", "named:empty_comment"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "mixed", args: &[FrozenDsnArg::Int(1_i64), FrozenDsnArg::Float(f64::from_bits(0x4000000000000000_u64)), FrozenDsnArg::Str("three"), FrozenDsnArg::Raw("1000000000000000000000000000000")], comment: None },
                expected: "(mixed 1 2 three 1000000000000000000000000000000)",
                tags: &["arg:float", "arg:int", "arg:str", "named:mixed"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "tiny", args: &[FrozenDsnArg::Float(f64::from_bits(0x3E7AD7F29ABCAF48_u64)), FrozenDsnArg::Float(f64::from_bits(0x3EB0C6F7A0B5ED8D_u64)), FrozenDsnArg::Float(f64::from_bits(0x3E112E0BE826D695_u64)), FrozenDsnArg::Float(f64::from_bits(0x419D6F34547E6B75_u64))], comment: None },
                expected: "(tiny 0 0.000001 0 123456789.123457)",
                tags: &["arg:float", "float:fractional", "float:tiny", "named:tiny_floats"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "inf", args: &[FrozenDsnArg::Float(f64::from_bits(0x7FF0000000000000_u64)), FrozenDsnArg::Float(f64::from_bits(0xFFF0000000000000_u64))], comment: None },
                expected: "(inf inf -inf)",
                tags: &["arg:float", "float:huge", "float:negative", "named:inf_floats"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "flags", args: &[FrozenDsnArg::Raw("True"), FrozenDsnArg::Raw("False")], comment: None },
                expected: "(flags True False)",
                tags: &["arg:bool", "bool_arg", "named:bool_args"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "neg", args: &[FrozenDsnArg::Float(f64::from_bits(0xBFE0000000000000_u64)), FrozenDsnArg::Float(f64::from_bits(0xBE112E0BE826D695_u64)), FrozenDsnArg::Float(f64::from_bits(0xC05EDD2F1A9FBE77_u64))], comment: None },
                expected: "(neg -0.5 -0 -123.456)",
                tags: &["arg:float", "float:fractional", "float:negative", "float:tiny", "named:negative_floats"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "frac", args: &[FrozenDsnArg::Float(f64::from_bits(0x3FD5555555555555_u64)), FrozenDsnArg::Float(f64::from_bits(0x3FE5555555555555_u64)), FrozenDsnArg::Float(f64::from_bits(0x3FD3333333333334_u64))], comment: None },
                expected: "(frac 0.333333 0.666667 0.3)",
                tags: &["arg:float", "float:fractional", "named:fractional_trim"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "big", args: &[FrozenDsnArg::Int(1000000000000000000_i64), FrozenDsnArg::Int(-1000000000000000000_i64)], comment: None },
                expected: "(big 1000000000000000000 -1000000000000000000)",
                tags: &["arg:int", "named:large_int"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "a", args: &[FrozenDsnArg::Nested(&NESTED_1)], comment: None },
                expected: "(a (b (c deep)))",
                tags: &["arg:nested", "named:deeply_nested", "nested"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "raw", args: &[FrozenDsnArg::Raw("None")], comment: None },
                expected: "(raw None)",
                tags: &["arg:raw", "named:raw_arg"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "u", args: &[FrozenDsnArg::Str("uni-Δ")], comment: None },
                expected: "(u uni-Δ)",
                tags: &["arg:str", "named:unicode_str"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "t", args: &[FrozenDsnArg::Str("tab	sep")], comment: None },
                expected: "(t tab\tsep)",
                tags: &["arg:str", "named:tab_str"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "c", args: &[FrozenDsnArg::Str("x")], comment: Some("multi word comment") },
                expected: ";multi word comment\n(c x)",
                tags: &["arg:str", "has_comment", "named:comment_with_newline_ref"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "ints", args: &[FrozenDsnArg::Int(0_i64), FrozenDsnArg::Int(-1_i64), FrozenDsnArg::Int(42_i64)], comment: None },
                expected: "(ints 0 -1 42)",
                tags: &["arg:int", "named:only_int_args"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "uni-Δ", args: &[], comment: Some("comment text") },
                expected: ";comment text\n(uni-Δ)",
                tags: &["empty_args", "has_comment"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "has space", args: &[FrozenDsnArg::Raw("False"), FrozenDsnArg::Raw("False"), FrozenDsnArg::Str("(paren)"), FrozenDsnArg::Raw("False")], comment: Some("comment text") },
                expected: ";comment text\n(has space False False \"(paren)\" False)",
                tags: &["arg:bool", "arg:str", "bool_arg", "has_comment", "str:special_chars"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "(paren)", args: &[], comment: None },
                expected: "((paren))",
                tags: &["empty_args"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "tab	sep", args: &[FrozenDsnArg::Int(7_i64), FrozenDsnArg::Float(f64::from_bits(0xBFF0000000000000_u64)), FrozenDsnArg::Str("GND"), FrozenDsnArg::Str(""), FrozenDsnArg::Nested(&NESTED_2)], comment: None },
                expected: "(tab\tsep 7 -1 GND \"\" (sub x 1))",
                tags: &["arg:float", "arg:int", "arg:nested", "arg:str", "float:negative", "nested", "str:empty"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "uni-Δ", args: &[], comment: None },
                expected: "(uni-Δ)",
                tags: &["empty_args"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "has\"quote\"", args: &[FrozenDsnArg::Float(f64::from_bits(0x3FF0000000000000_u64)), FrozenDsnArg::Nested(&NESTED_3)], comment: None },
                expected: "(has\"quote\" 1 (sub x 1))",
                tags: &["arg:float", "arg:nested", "nested"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "simple", args: &[FrozenDsnArg::Raw("False")], comment: Some("comment text") },
                expected: ";comment text\n(simple False)",
                tags: &["arg:bool", "bool_arg", "has_comment"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "has space", args: &[FrozenDsnArg::Int(-1_i64), FrozenDsnArg::Float(f64::from_bits(0x3FE0000000000000_u64)), FrozenDsnArg::Nested(&NESTED_4), FrozenDsnArg::Nested(&NESTED_5)], comment: None },
                expected: "(has space -1 0.5 (sub x 1) (sub x 1))",
                tags: &["arg:float", "arg:int", "arg:nested", "float:fractional", "nested"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "Net-(U1-Pad1)", args: &[FrozenDsnArg::Str("Net-(U1-Pad1)"), FrozenDsnArg::Int(100_i64), FrozenDsnArg::Raw("False"), FrozenDsnArg::Float(f64::from_bits(0x3FD3333333333334_u64))], comment: None },
                expected: "(Net-(U1-Pad1) \"Net-(U1-Pad1)\" 100 False 0.3)",
                tags: &["arg:bool", "arg:float", "arg:int", "arg:str", "bool_arg", "float:fractional", "str:special_chars"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "GND", args: &[FrozenDsnArg::Int(0_i64), FrozenDsnArg::Float(f64::from_bits(0x3FE0000000000000_u64)), FrozenDsnArg::Raw("False")], comment: Some("comment text") },
                expected: ";comment text\n(GND 0 0.5 False)",
                tags: &["arg:bool", "arg:float", "arg:int", "bool_arg", "float:fractional", "has_comment"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "", args: &[FrozenDsnArg::Int(0_i64)], comment: Some("comment text") },
                expected: ";comment text\n( 0)",
                tags: &["arg:int", "has_comment"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "", args: &[FrozenDsnArg::Float(f64::from_bits(0x0000000000000001_u64))], comment: None },
                expected: "( 0)",
                tags: &["arg:float", "float:fractional", "float:tiny"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "uni-Δ", args: &[FrozenDsnArg::Float(f64::from_bits(0xC08F3FFDF3B645A2_u64)), FrozenDsnArg::Raw("True")], comment: None },
                expected: "(uni-Δ -999.999 True)",
                tags: &["arg:bool", "arg:float", "bool_arg", "float:fractional", "float:negative"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "has space", args: &[FrozenDsnArg::Raw("True"), FrozenDsnArg::Raw("True"), FrozenDsnArg::Str(""), FrozenDsnArg::Nested(&NESTED_6)], comment: None },
                expected: "(has space True True \"\" (sub x 1))",
                tags: &["arg:bool", "arg:nested", "arg:str", "bool_arg", "nested", "str:empty"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "Net-(U1-Pad1)", args: &[FrozenDsnArg::Int(1000000000000000_i64), FrozenDsnArg::Float(f64::from_bits(0xBFF0000000000000_u64)), FrozenDsnArg::Raw("True"), FrozenDsnArg::Raw("False")], comment: None },
                expected: "(Net-(U1-Pad1) 1000000000000000 -1 True False)",
                tags: &["arg:bool", "arg:float", "arg:int", "bool_arg", "float:negative"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "Net-(U1-Pad1)", args: &[FrozenDsnArg::Nested(&NESTED_7)], comment: None },
                expected: "(Net-(U1-Pad1) (sub x 1))",
                tags: &["arg:nested", "nested"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "GND", args: &[FrozenDsnArg::Raw("True"), FrozenDsnArg::Raw("True"), FrozenDsnArg::Str("simple"), FrozenDsnArg::Int(1_i64)], comment: None },
                expected: "(GND True True simple 1)",
                tags: &["arg:bool", "arg:int", "arg:str", "bool_arg"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "", args: &[FrozenDsnArg::Int(1000000_i64), FrozenDsnArg::Raw("False"), FrozenDsnArg::Nested(&NESTED_8), FrozenDsnArg::Float(f64::from_bits(0xFFF0000000000000_u64))], comment: None },
                expected: "( 1000000 False (sub x 1) -inf)",
                tags: &["arg:bool", "arg:float", "arg:int", "arg:nested", "bool_arg", "float:huge", "float:negative", "nested"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "(paren)", args: &[FrozenDsnArg::Int(42_i64), FrozenDsnArg::Float(f64::from_bits(0xBFE0000000000000_u64))], comment: None },
                expected: "((paren) 42 -0.5)",
                tags: &["arg:float", "arg:int", "float:fractional", "float:negative"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "VCC", args: &[FrozenDsnArg::Float(f64::from_bits(0x3FE5555555555555_u64)), FrozenDsnArg::Raw("True"), FrozenDsnArg::Float(f64::from_bits(0x3FF0000000000000_u64)), FrozenDsnArg::Int(255_i64), FrozenDsnArg::Nested(&NESTED_9)], comment: Some("comment text") },
                expected: ";comment text\n(VCC 0.666667 True 1 255 (sub x 1))",
                tags: &["arg:bool", "arg:float", "arg:int", "arg:nested", "bool_arg", "float:fractional", "has_comment", "nested"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "has space", args: &[FrozenDsnArg::Int(42_i64)], comment: None },
                expected: "(has space 42)",
                tags: &["arg:int"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "uni-Δ", args: &[FrozenDsnArg::Str("Net-(U1-Pad1)"), FrozenDsnArg::Str("uni-Δ")], comment: Some("comment text") },
                expected: ";comment text\n(uni-Δ \"Net-(U1-Pad1)\" uni-Δ)",
                tags: &["arg:str", "has_comment", "str:special_chars"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "has\"quote\"", args: &[FrozenDsnArg::Float(f64::from_bits(0xFFF0000000000000_u64))], comment: Some("comment text") },
                expected: ";comment text\n(has\"quote\" -inf)",
                tags: &["arg:float", "float:huge", "float:negative", "has_comment"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "has space", args: &[FrozenDsnArg::Raw("True")], comment: None },
                expected: "(has space True)",
                tags: &["arg:bool", "bool_arg"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "simple", args: &[], comment: Some("comment text") },
                expected: ";comment text\n(simple)",
                tags: &["empty_args", "has_comment"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "Net-(U1-Pad1)", args: &[FrozenDsnArg::Int(1_i64), FrozenDsnArg::Str("VCC"), FrozenDsnArg::Str("tab	sep")], comment: Some("comment text") },
                expected: ";comment text\n(Net-(U1-Pad1) 1 VCC tab\tsep)",
                tags: &["arg:int", "arg:str", "has_comment"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "(paren)", args: &[FrozenDsnArg::Raw("True"), FrozenDsnArg::Str("VCC")], comment: None },
                expected: "((paren) True VCC)",
                tags: &["arg:bool", "arg:str", "bool_arg"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "Net-(U1-Pad1)", args: &[], comment: None },
                expected: "(Net-(U1-Pad1))",
                tags: &["empty_args"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "has\"quote\"", args: &[FrozenDsnArg::Float(f64::from_bits(0x7FF0000000000000_u64)), FrozenDsnArg::Str("uni-Δ")], comment: None },
                expected: "(has\"quote\" inf uni-Δ)",
                tags: &["arg:float", "arg:str", "float:huge"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "simple", args: &[FrozenDsnArg::Raw("True"), FrozenDsnArg::Str("has space"), FrozenDsnArg::Int(7_i64)], comment: None },
                expected: "(simple True \"has space\" 7)",
                tags: &["arg:bool", "arg:int", "arg:str", "bool_arg", "str:special_chars"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "(paren)", args: &[FrozenDsnArg::Int(0_i64)], comment: Some("comment text") },
                expected: ";comment text\n((paren) 0)",
                tags: &["arg:int", "has_comment"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "uni-Δ", args: &[FrozenDsnArg::Float(f64::from_bits(0x3E7AD7F29ABCAF48_u64)), FrozenDsnArg::Int(7_i64), FrozenDsnArg::Nested(&NESTED_10), FrozenDsnArg::Str("GND"), FrozenDsnArg::Raw("True")], comment: Some("comment text") },
                expected: ";comment text\n(uni-Δ 0 7 (sub x 1) GND True)",
                tags: &["arg:bool", "arg:float", "arg:int", "arg:nested", "arg:str", "bool_arg", "float:fractional", "float:tiny", "has_comment", "nested"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "", args: &[FrozenDsnArg::Raw("False"), FrozenDsnArg::Int(7_i64), FrozenDsnArg::Int(1000000_i64), FrozenDsnArg::Raw("False"), FrozenDsnArg::Float(f64::from_bits(0x4025161F9F01B867_u64))], comment: Some("comment text") },
                expected: ";comment text\n( False 7 1000000 False 10.54321)",
                tags: &["arg:bool", "arg:float", "arg:int", "bool_arg", "float:fractional", "has_comment"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "tab	sep", args: &[FrozenDsnArg::Raw("False")], comment: Some("comment text") },
                expected: ";comment text\n(tab\tsep False)",
                tags: &["arg:bool", "bool_arg", "has_comment"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "simple", args: &[], comment: None },
                expected: "(simple)",
                tags: &["empty_args"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "simple", args: &[FrozenDsnArg::Float(f64::from_bits(0x0000000000000000_u64)), FrozenDsnArg::Nested(&NESTED_11), FrozenDsnArg::Str("tab	sep"), FrozenDsnArg::Nested(&NESTED_12)], comment: None },
                expected: "(simple 0 (sub x 1) tab\tsep (sub x 1))",
                tags: &["arg:float", "arg:nested", "arg:str", "float:tiny", "float:zero", "nested"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "simple", args: &[FrozenDsnArg::Float(f64::from_bits(0x3FD3333333333334_u64)), FrozenDsnArg::Raw("True"), FrozenDsnArg::Raw("True"), FrozenDsnArg::Str("(paren)"), FrozenDsnArg::Float(f64::from_bits(0xC08F3FFDF3B645A2_u64))], comment: Some("comment text") },
                expected: ";comment text\n(simple 0.3 True True \"(paren)\" -999.999)",
                tags: &["arg:bool", "arg:float", "arg:str", "bool_arg", "float:fractional", "float:negative", "has_comment", "str:special_chars"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "Net-(U1-Pad1)", args: &[FrozenDsnArg::Raw("True")], comment: None },
                expected: "(Net-(U1-Pad1) True)",
                tags: &["arg:bool", "bool_arg"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "has space", args: &[], comment: None },
                expected: "(has space)",
                tags: &["empty_args"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "simple", args: &[FrozenDsnArg::Raw("False"), FrozenDsnArg::Raw("True")], comment: Some("comment text") },
                expected: ";comment text\n(simple False True)",
                tags: &["arg:bool", "bool_arg", "has_comment"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "VCC", args: &[], comment: None },
                expected: "(VCC)",
                tags: &["empty_args"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "has\"quote\"", args: &[FrozenDsnArg::Float(f64::from_bits(0x00000000000007E8_u64)), FrozenDsnArg::Float(f64::from_bits(0x405EDD2F1A9FBE77_u64)), FrozenDsnArg::Raw("False"), FrozenDsnArg::Nested(&NESTED_13), FrozenDsnArg::Float(f64::from_bits(0xBFF0000000000000_u64))], comment: None },
                expected: "(has\"quote\" 0 123.456 False (sub x 1) -1)",
                tags: &["arg:bool", "arg:float", "arg:nested", "bool_arg", "float:fractional", "float:negative", "float:tiny", "nested"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "Net-(U1-Pad1)", args: &[FrozenDsnArg::Raw("True"), FrozenDsnArg::Float(f64::from_bits(0x3FD5555555555555_u64)), FrozenDsnArg::Int(1000000_i64)], comment: None },
                expected: "(Net-(U1-Pad1) True 0.333333 1000000)",
                tags: &["arg:bool", "arg:float", "arg:int", "bool_arg", "float:fractional"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "", args: &[FrozenDsnArg::Raw("True"), FrozenDsnArg::Float(f64::from_bits(0x3FF0000000000000_u64))], comment: None },
                expected: "( True 1)",
                tags: &["arg:bool", "arg:float", "bool_arg"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "Net-(U1-Pad1)", args: &[], comment: Some("comment text") },
                expected: ";comment text\n(Net-(U1-Pad1))",
                tags: &["empty_args", "has_comment"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "Net-(U1-Pad1)", args: &[FrozenDsnArg::Nested(&NESTED_14), FrozenDsnArg::Nested(&NESTED_15), FrozenDsnArg::Raw("False")], comment: Some("comment text") },
                expected: ";comment text\n(Net-(U1-Pad1) (sub x 1) (sub x 1) False)",
                tags: &["arg:bool", "arg:nested", "bool_arg", "has_comment", "nested"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "GND", args: &[], comment: None },
                expected: "(GND)",
                tags: &["empty_args"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "(paren)", args: &[FrozenDsnArg::Raw("False"), FrozenDsnArg::Str("GND"), FrozenDsnArg::Nested(&NESTED_16)], comment: None },
                expected: "((paren) False GND (sub x 1))",
                tags: &["arg:bool", "arg:nested", "arg:str", "bool_arg", "nested"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "GND", args: &[FrozenDsnArg::Raw("True"), FrozenDsnArg::Raw("False"), FrozenDsnArg::Raw("True"), FrozenDsnArg::Float(f64::from_bits(0x3F747AE147AE147B_u64))], comment: Some("comment text") },
                expected: ";comment text\n(GND True False True 0.005)",
                tags: &["arg:bool", "arg:float", "bool_arg", "float:fractional", "has_comment"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "tab	sep", args: &[FrozenDsnArg::Float(f64::from_bits(0x405EDD2F1A9FBE77_u64)), FrozenDsnArg::Nested(&NESTED_17), FrozenDsnArg::Str("tab	sep"), FrozenDsnArg::Nested(&NESTED_18), FrozenDsnArg::Int(1000000000000000_i64)], comment: Some("comment text") },
                expected: ";comment text\n(tab\tsep 123.456 (sub x 1) tab\tsep (sub x 1) 1000000000000000)",
                tags: &["arg:float", "arg:int", "arg:nested", "arg:str", "float:fractional", "has_comment", "nested"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "VCC", args: &[FrozenDsnArg::Int(1_i64), FrozenDsnArg::Str("GND"), FrozenDsnArg::Int(255_i64), FrozenDsnArg::Str("Net-(U1-Pad1)"), FrozenDsnArg::Nested(&NESTED_19)], comment: None },
                expected: "(VCC 1 GND 255 \"Net-(U1-Pad1)\" (sub x 1))",
                tags: &["arg:int", "arg:nested", "arg:str", "nested", "str:special_chars"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "has space", args: &[FrozenDsnArg::Nested(&NESTED_20), FrozenDsnArg::Str("(paren)"), FrozenDsnArg::Str("Net-(U1-Pad1)"), FrozenDsnArg::Float(f64::from_bits(0x412E848000000000_u64)), FrozenDsnArg::Float(f64::from_bits(0x0000000000000001_u64))], comment: Some("comment text") },
                expected: ";comment text\n(has space (sub x 1) \"(paren)\" \"Net-(U1-Pad1)\" 1000000 0)",
                tags: &["arg:float", "arg:nested", "arg:str", "float:fractional", "float:tiny", "has_comment", "nested", "str:special_chars"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "", args: &[FrozenDsnArg::Str(""), FrozenDsnArg::Nested(&NESTED_21), FrozenDsnArg::Str("uni-Δ"), FrozenDsnArg::Raw("True"), FrozenDsnArg::Str("has\"quote\"")], comment: None },
                expected: "( \"\" (sub x 1) uni-Δ True \"has\\\"quote\\\"\")",
                tags: &["arg:bool", "arg:nested", "arg:str", "bool_arg", "nested", "str:empty", "str:special_chars"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "simple", args: &[FrozenDsnArg::Nested(&NESTED_22)], comment: Some("comment text") },
                expected: ";comment text\n(simple (sub x 1))",
                tags: &["arg:nested", "has_comment", "nested"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "GND", args: &[], comment: None },
                expected: "(GND)",
                tags: &["empty_args"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "VCC", args: &[FrozenDsnArg::Nested(&NESTED_23), FrozenDsnArg::Raw("True"), FrozenDsnArg::Float(f64::from_bits(0x405EDD2F1A9FBE77_u64)), FrozenDsnArg::Nested(&NESTED_24), FrozenDsnArg::Raw("False")], comment: None },
                expected: "(VCC (sub x 1) True 123.456 (sub x 1) False)",
                tags: &["arg:bool", "arg:float", "arg:nested", "bool_arg", "float:fractional", "nested"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "has space", args: &[FrozenDsnArg::Int(0_i64), FrozenDsnArg::Str("uni-Δ"), FrozenDsnArg::Str(""), FrozenDsnArg::Float(f64::from_bits(0x412E848000000000_u64))], comment: None },
                expected: "(has space 0 uni-Δ \"\" 1000000)",
                tags: &["arg:float", "arg:int", "arg:str", "str:empty"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "has space", args: &[FrozenDsnArg::Float(f64::from_bits(0x3F9999999999999A_u64)), FrozenDsnArg::Float(f64::from_bits(0x00000000000007E8_u64)), FrozenDsnArg::Float(f64::from_bits(0x3FF0000000000000_u64)), FrozenDsnArg::Nested(&NESTED_25)], comment: Some("comment text") },
                expected: ";comment text\n(has space 0.025 0 1 (sub x 1))",
                tags: &["arg:float", "arg:nested", "float:fractional", "float:tiny", "has_comment", "nested"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "", args: &[FrozenDsnArg::Float(f64::from_bits(0x0000000000000000_u64)), FrozenDsnArg::Int(1_i64), FrozenDsnArg::Float(f64::from_bits(0x3FD3333333333334_u64)), FrozenDsnArg::Str("GND"), FrozenDsnArg::Float(f64::from_bits(0x405EDD2F1A9FBE77_u64))], comment: None },
                expected: "( 0 1 0.3 GND 123.456)",
                tags: &["arg:float", "arg:int", "arg:str", "float:fractional", "float:tiny", "float:zero"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "Net-(U1-Pad1)", args: &[FrozenDsnArg::Int(1000000_i64), FrozenDsnArg::Str("")], comment: Some("comment text") },
                expected: ";comment text\n(Net-(U1-Pad1) 1000000 \"\")",
                tags: &["arg:int", "arg:str", "has_comment", "str:empty"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "", args: &[FrozenDsnArg::Str(""), FrozenDsnArg::Float(f64::from_bits(0xBFE0000000000000_u64)), FrozenDsnArg::Float(f64::from_bits(0xBFF0000000000000_u64)), FrozenDsnArg::Float(f64::from_bits(0x405EDD2F1A9FBE77_u64))], comment: Some("comment text") },
                expected: ";comment text\n( \"\" -0.5 -1 123.456)",
                tags: &["arg:float", "arg:str", "float:fractional", "float:negative", "has_comment", "str:empty"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "", args: &[FrozenDsnArg::Raw("False"), FrozenDsnArg::Float(f64::from_bits(0x3FD3333333333334_u64)), FrozenDsnArg::Raw("False"), FrozenDsnArg::Int(255_i64)], comment: Some("comment text") },
                expected: ";comment text\n( False 0.3 False 255)",
                tags: &["arg:bool", "arg:float", "arg:int", "bool_arg", "float:fractional", "has_comment"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "VCC", args: &[FrozenDsnArg::Str("has space")], comment: Some("comment text") },
                expected: ";comment text\n(VCC \"has space\")",
                tags: &["arg:str", "has_comment", "str:special_chars"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "(paren)", args: &[FrozenDsnArg::Float(f64::from_bits(0x3F747AE147AE147B_u64)), FrozenDsnArg::Int(0_i64), FrozenDsnArg::Nested(&NESTED_26), FrozenDsnArg::Int(1000000_i64), FrozenDsnArg::Float(f64::from_bits(0x3E7AD7F29ABCAF48_u64))], comment: None },
                expected: "((paren) 0.005 0 (sub x 1) 1000000 0)",
                tags: &["arg:float", "arg:int", "arg:nested", "float:fractional", "float:tiny", "nested"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "has\"quote\"", args: &[FrozenDsnArg::Float(f64::from_bits(0x3FD3333333333334_u64)), FrozenDsnArg::Nested(&NESTED_27), FrozenDsnArg::Float(f64::from_bits(0x3FE5555555555555_u64)), FrozenDsnArg::Float(f64::from_bits(0x0000000000000001_u64))], comment: Some("comment text") },
                expected: ";comment text\n(has\"quote\" 0.3 (sub x 1) 0.666667 0)",
                tags: &["arg:float", "arg:nested", "float:fractional", "float:tiny", "has_comment", "nested"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "uni-Δ", args: &[FrozenDsnArg::Float(f64::from_bits(0x419D6F3457F35BA8_u64)), FrozenDsnArg::Str("tab	sep"), FrozenDsnArg::Raw("False")], comment: None },
                expected: "(uni-Δ 123456789.987654 tab\tsep False)",
                tags: &["arg:bool", "arg:float", "arg:str", "bool_arg", "float:fractional"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "has space", args: &[], comment: None },
                expected: "(has space)",
                tags: &["empty_args"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "uni-Δ", args: &[FrozenDsnArg::Float(f64::from_bits(0x3FD3333333333334_u64)), FrozenDsnArg::Float(f64::from_bits(0x0000000000000001_u64)), FrozenDsnArg::Int(0_i64), FrozenDsnArg::Int(0_i64)], comment: Some("comment text") },
                expected: ";comment text\n(uni-Δ 0.3 0 0 0)",
                tags: &["arg:float", "arg:int", "float:fractional", "float:tiny", "has_comment"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "GND", args: &[FrozenDsnArg::Raw("False")], comment: Some("comment text") },
                expected: ";comment text\n(GND False)",
                tags: &["arg:bool", "bool_arg", "has_comment"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "Net-(U1-Pad1)", args: &[], comment: None },
                expected: "(Net-(U1-Pad1))",
                tags: &["empty_args"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "has\"quote\"", args: &[FrozenDsnArg::Str("GND")], comment: Some("comment text") },
                expected: ";comment text\n(has\"quote\" GND)",
                tags: &["arg:str", "has_comment"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "(paren)", args: &[FrozenDsnArg::Str("tab	sep"), FrozenDsnArg::Nested(&NESTED_28), FrozenDsnArg::Int(1000000000000000_i64), FrozenDsnArg::Int(1000000_i64)], comment: Some("comment text") },
                expected: ";comment text\n((paren) tab\tsep (sub x 1) 1000000000000000 1000000)",
                tags: &["arg:int", "arg:nested", "arg:str", "has_comment", "nested"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "GND", args: &[FrozenDsnArg::Raw("True"), FrozenDsnArg::Int(100_i64)], comment: Some("comment text") },
                expected: ";comment text\n(GND True 100)",
                tags: &["arg:bool", "arg:int", "bool_arg", "has_comment"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "simple", args: &[], comment: Some("comment text") },
                expected: ";comment text\n(simple)",
                tags: &["empty_args", "has_comment"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "uni-Δ", args: &[FrozenDsnArg::Int(1000000_i64)], comment: Some("comment text") },
                expected: ";comment text\n(uni-Δ 1000000)",
                tags: &["arg:int", "has_comment"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "GND", args: &[FrozenDsnArg::Str("tab	sep"), FrozenDsnArg::Nested(&NESTED_29)], comment: Some("comment text") },
                expected: ";comment text\n(GND tab\tsep (sub x 1))",
                tags: &["arg:nested", "arg:str", "has_comment", "nested"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "has\"quote\"", args: &[], comment: Some("comment text") },
                expected: ";comment text\n(has\"quote\")",
                tags: &["empty_args", "has_comment"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "(paren)", args: &[FrozenDsnArg::Nested(&NESTED_30), FrozenDsnArg::Nested(&NESTED_31), FrozenDsnArg::Nested(&NESTED_32), FrozenDsnArg::Nested(&NESTED_33)], comment: None },
                expected: "((paren) (sub x 1) (sub x 1) (sub x 1) (sub x 1))",
                tags: &["arg:nested", "nested"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "GND", args: &[FrozenDsnArg::Int(1000000000000000_i64), FrozenDsnArg::Raw("True"), FrozenDsnArg::Int(0_i64), FrozenDsnArg::Nested(&NESTED_34), FrozenDsnArg::Nested(&NESTED_35)], comment: Some("comment text") },
                expected: ";comment text\n(GND 1000000000000000 True 0 (sub x 1) (sub x 1))",
                tags: &["arg:bool", "arg:int", "arg:nested", "bool_arg", "has_comment", "nested"],
            },
            FrozenDsnCase {
                expr: FrozenDsnExpr { name: "has space", args: &[FrozenDsnArg::Str("VCC"), FrozenDsnArg::Nested(&NESTED_36), FrozenDsnArg::Float(f64::from_bits(0x3F747AE147AE147B_u64))], comment: None },
                expected: "(has space VCC (sub x 1) 0.005)",
                tags: &["arg:float", "arg:nested", "arg:str", "float:fractional", "nested"],
            },
        ];

        fn frozen_arg_to_dsn(arg: &FrozenDsnArg) -> DsnArg {
            match arg {
                FrozenDsnArg::Float(f) => DsnArg::Float(*f),
                FrozenDsnArg::Int(i) => DsnArg::Int(*i),
                FrozenDsnArg::Str(s) => DsnArg::Str(s.to_string()),
                FrozenDsnArg::Nested(e) => DsnArg::Nested(Box::new(frozen_expr_to_dsn(e))),
                FrozenDsnArg::Raw(s) => DsnArg::Raw(s.to_string()),
            }
        }

        fn frozen_expr_to_dsn(e: &FrozenDsnExpr) -> DsnExpressionData {
            DsnExpressionData {
                name: e.name.to_string(),
                args: e.args.iter().map(frozen_arg_to_dsn).collect(),
                comment: e.comment.map(|c| c.to_string()),
            }
        }

        #[test]
        fn frozen_dsn_matches_golden_corpus() {
            for case in FROZEN_DSN_GOLDEN {
                let expr = frozen_expr_to_dsn(&case.expr);
                let got = dsn_expression_to_string(&expr);
                assert_eq!(got, case.expected, "tags={:?}", case.tags);
            }
        }

        /// Q2 non-vacuity guard.
        #[test]
        fn frozen_dsn_corpus_is_non_vacuous() {
            let n = FROZEN_DSN_GOLDEN.len() as u32;
            let count = |tag: &str| FROZEN_DSN_GOLDEN.iter()
                .filter(|c| c.tags.contains(&tag)).count() as u32;
            assert!(count("arg:float") >= 20, "arg:float: only {}/{} (need >= 20) -- float args must be exercised", count("arg:float"), n);
            assert!(count("arg:int") >= 10, "arg:int: only {}/{} (need >= 10) -- int args must be exercised", count("arg:int"), n);
            assert!(count("arg:str") >= 20, "arg:str: only {}/{} (need >= 20) -- str args must be exercised", count("arg:str"), n);
            assert!(count("arg:bool") >= 3, "arg:bool: only {}/{} (need >= 3) -- bool args (str(v) fallback) must be exercised", count("arg:bool"), n);
            assert!(count("arg:nested") >= 5, "arg:nested: only {}/{} (need >= 5) -- nested expressions must be exercised", count("arg:nested"), n);
            assert!(count("empty_args") >= 2, "empty_args: only {}/{} (need >= 2) -- empty-args expression must be exercised", count("empty_args"), n);
            assert!(count("has_comment") >= 5, "has_comment: only {}/{} (need >= 5) -- comment prefix must be exercised", count("has_comment"), n);
            assert!(count("str:special_chars") >= 5, "str:special_chars: only {}/{} (need >= 5) -- strings needing quoting/escaping must be exercised", count("str:special_chars"), n);
            assert!(count("str:empty") >= 3, "str:empty: only {}/{} (need >= 3) -- empty string (-> \"\") must be exercised", count("str:empty"), n);
            assert!(count("float:zero") >= 3, "float:zero: only {}/{} (need >= 3) -- zero floats must be exercised", count("float:zero"), n);
            assert!(count("float:fractional") >= 10, "float:fractional: only {}/{} (need >= 10) -- fractional floats must be exercised", count("float:fractional"), n);
            assert!(count("float:negative") >= 5, "float:negative: only {}/{} (need >= 5) -- negative floats must be exercised", count("float:negative"), n);
            assert!(count("float:tiny") >= 2, "float:tiny: only {}/{} (need >= 2) -- tiny (subnormal) floats must be exercised", count("float:tiny"), n);
            assert!(count("bool_arg") >= 3, "bool_arg: only {}/{} (need >= 3) -- bool args must be exercised", count("bool_arg"), n);
            assert!(count("nested") >= 5, "nested: only {}/{} (need >= 5) -- nested expressions must be exercised", count("nested"), n);
        }
    }
// --- END generated by scripts/gen_oracle_freeze.py: dsn_primitives ---

    #[cfg_attr(test, test)]
    fn float_arg_trims_trailing_zeros() {
        assert_eq!(format_dsn_arg(&DsnArg::Float(10.0)), "10");
        assert_eq!(format_dsn_arg(&DsnArg::Float(10.5)), "10.5");
        assert_eq!(format_dsn_arg(&DsnArg::Float(10.54321)), "10.54321");
        assert_eq!(format_dsn_arg(&DsnArg::Float(0.0)), "0");
    }

    #[cfg_attr(test, test)]
    fn string_arg_quotes_when_needed() {
        assert_eq!(format_dsn_arg(&DsnArg::Str("GND".into())), "GND");
        assert_eq!(
            format_dsn_arg(&DsnArg::Str("VCC (Power)".into())),
            "\"VCC (Power)\""
        );
        assert_eq!(
            format_dsn_arg(&DsnArg::Str("Quoted \"String\"".into())),
            "\"Quoted \\\"String\\\"\""
        );
        assert_eq!(format_dsn_arg(&DsnArg::Str(String::new())), "\"\"");
    }

    #[cfg_attr(test, test)]
    fn empty_comment_is_falsy_and_emits_no_comment_line() {
        let e = DsnExpressionData {
            name: "pcb".into(),
            args: vec![],
            comment: Some(String::new()),
        };
        assert_eq!(dsn_expression_to_string(&e), "(pcb)");
        let e = DsnExpressionData {
            name: "pcb".into(),
            args: vec![],
            comment: Some("v: 1".into()),
        };
        assert_eq!(dsn_expression_to_string(&e), ";v: 1\n(pcb)");
    }

    #[cfg_attr(test, test)]
    fn nested_expression_round_trips() {
        let inner = DsnExpressionData {
            name: "unit".into(),
            args: vec![DsnArg::Str("mm".into())],
            comment: None,
        };
        let outer = DsnExpressionData {
            name: "pcb".into(),
            args: vec![
                DsnArg::Str("sample".into()),
                DsnArg::Nested(Box::new(inner)),
            ],
            comment: None,
        };
        assert_eq!(dsn_expression_to_string(&outer), "(pcb sample (unit mm))");
    }

    #[cfg_attr(test, test)]
    fn rect_shape_formats_as_dsn() {
        let rect = DsnRectData {
            layer: "pcb".into(),
            x1: 0.0,
            y1: 0.0,
            x2: 100.0,
            y2: 100.0,
        };
        assert_eq!(
            dsn_expression_to_string(&rect.to_dsn()),
            "(rect pcb 0 0 100 100)"
        );
    }

    #[cfg_attr(test, test)]
    fn dsn_expression_comment_truthiness() {
        // An empty string comment is falsy in Python and must not emit a
        // comment line.
        let expr = DsnExpressionData {
            name: "x".into(),
            args: vec![],
            comment: Some(String::new()),
        };
        let s = dsn_expression_to_string(&expr);
        assert!(!s.contains(';'), "empty comment emitted semicolon: '{s}'");
        // None comment emits no semicolon.
        let expr = DsnExpressionData {
            name: "x".into(),
            args: vec![],
            comment: None,
        };
        let s = dsn_expression_to_string(&expr);
        assert!(!s.contains(';'), "None comment emitted semicolon: '{s}'");
    }

    #[cfg_attr(test, test)]
    fn format_dsn_arg_negative_zero() {
        // -0.0 has a signed representation; document the current behaviour.
        let s = format_dsn_arg(&DsnArg::Float(-0.0));
        // `format!("{:.6}", -0.0)` → "-0.000000" → trimmed → "-0"
        // DSN accepts signed coordinates, so this is valid.
        assert!(s == "0" || s == "-0", "-0.0 formatted as '{s}'");
    }

    #[cfg_attr(test, test)]
    fn format_dsn_arg_inf_and_nan() {
        // Infinity and NaN are not expected in DSN coordinates, but the
        // formatter should produce something parseable rather than panic.
        let s_inf = format_dsn_arg(&DsnArg::Float(f64::INFINITY));
        let s_nan = format_dsn_arg(&DsnArg::Float(f64::NAN));
        assert!(!s_inf.is_empty());
        assert!(!s_nan.is_empty());
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("dsn_types::tests::float_arg_trims_trailing_zeros", float_arg_trims_trailing_zeros),
        ("dsn_types::tests::string_arg_quotes_when_needed", string_arg_quotes_when_needed),
        ("dsn_types::tests::empty_comment_is_falsy_and_emits_no_comment_line", empty_comment_is_falsy_and_emits_no_comment_line),
        ("dsn_types::tests::nested_expression_round_trips", nested_expression_round_trips),
        ("dsn_types::tests::rect_shape_formats_as_dsn", rect_shape_formats_as_dsn),
        ("dsn_types::tests::dsn_expression_comment_truthiness", dsn_expression_comment_truthiness),
        ("dsn_types::tests::format_dsn_arg_negative_zero", format_dsn_arg_negative_zero),
        ("dsn_types::tests::format_dsn_arg_inf_and_nan", format_dsn_arg_inf_and_nan),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}

// ---------------------------------------------------------------------------
// Property-based tests (proptest)
// ---------------------------------------------------------------------------
// A sibling module rather than `#[test] fn`s mixed into `tests` above, matching
// `pyfmt.rs`, `stackup_validator.rs`, `placer_core/units.rs` and
// `placer_core/placer_compute.rs`.  `proptest` is a dev-dependency, so it is
// absent from the ordinary (non-test) build the `wasm32` registry compiles
// into; keeping these apart is what lets the deterministic tests above join
// the tier instead of being excluded alongside them.
#[cfg(test)]
mod proptests {
    use super::*;

    // ---------- proptest: format_dsn_arg -----------------------------------

    #[test]
    fn format_dsn_arg_float_round_trips_visually() {
        use proptest::prelude::*;
        proptest!(|(x in -1e6f64..1e6f64)| {
            let s = format_dsn_arg(&DsnArg::Float(x));
            // The output must not contain spaces, parentheses, or quotes
            // (it's an unquoted DSN atom).
            prop_assert!(!s.contains(' '), "float {x} -> '{s}' contains space");
            prop_assert!(!s.contains('('), "float {x} -> '{s}' contains '('");
            prop_assert!(!s.contains(')'), "float {x} -> '{s}' contains ')'");
        });
    }

    #[test]
    fn format_dsn_arg_str_is_properly_quoted() {
        use proptest::prelude::*;
        let special = "[a-zA-Z0-9 _(){}\"\\\\]{0,20}";
        proptest!(|(s in special)| {
            let result = format_dsn_arg(&DsnArg::Str(s.clone()));
            // If the string is empty or contains special chars, it MUST be
            // quoted (otherwise the DSN parser would choke).
            let needs_quote = s.is_empty() || s.contains(' ') || s.contains('(') || s.contains(')') || s.contains('"');
            if needs_quote {
                prop_assert!(result.starts_with('"') && result.ends_with('"'),
                    "string '{s}' must be quoted but got '{result}'");
                // The quoted content must not contain an unescaped double quote.
                let inner = &result[1..result.len()-1];
                let bytes = inner.as_bytes();
                let mut has_unescaped = false;
                for (i, &b) in bytes.iter().enumerate() {
                    if b == b'"' && (i == 0 || bytes[i-1] != b'\\') {
                        has_unescaped = true;
                        break;
                    }
                }
                prop_assert!(!has_unescaped,
                    "string '{s}' -> '{result}' has unescaped quote");
            } else {
                prop_assert!(!result.starts_with('"'),
                    "string '{s}' should not be quoted but got '{result}'");
            }
        });
    }

    // ---------- proptest: dsn_expression_to_string --------------------------

    #[test]
    fn dsn_expression_has_balanced_parens() {
        use proptest::prelude::*;
        let ident = "[a-zA-Z][a-zA-Z0-9_]{0,10}";
        proptest!(|(name in ident)| {
            let expr = DsnExpressionData { name, args: vec![], comment: None };
            let s = dsn_expression_to_string(&expr);
            // Every '(' must have a matching ')'.
            let mut depth = 0i32;
            for ch in s.chars() {
                match ch {
                    '(' => depth += 1,
                    ')' => depth -= 1,
                    _ => {}
                }
                prop_assert!(depth >= 0, "unbalanced ')' in: {}", s);
            }
            prop_assert_eq!(depth, 0, "unbalanced '(' in: {}", s);
        });
    }
}
