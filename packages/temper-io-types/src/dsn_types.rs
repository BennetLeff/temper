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

#[cfg(test)]
#[allow(clippy::unwrap_used, clippy::expect_used)]
mod tests {
    use super::*;

    #[test]
    fn float_arg_trims_trailing_zeros() {
        assert_eq!(format_dsn_arg(&DsnArg::Float(10.0)), "10");
        assert_eq!(format_dsn_arg(&DsnArg::Float(10.5)), "10.5");
        assert_eq!(format_dsn_arg(&DsnArg::Float(10.54321)), "10.54321");
        assert_eq!(format_dsn_arg(&DsnArg::Float(0.0)), "0");
    }

    #[test]
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

    #[test]
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

    #[test]
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

    #[test]
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

    #[test]
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

    #[test]
    fn format_dsn_arg_negative_zero() {
        // -0.0 has a signed representation; document the current behaviour.
        let s = format_dsn_arg(&DsnArg::Float(-0.0));
        // `format!("{:.6}", -0.0)` → "-0.000000" → trimmed → "-0"
        // DSN accepts signed coordinates, so this is valid.
        assert!(s == "0" || s == "-0", "-0.0 formatted as '{s}'");
    }

    #[test]
    fn format_dsn_arg_inf_and_nan() {
        // Infinity and NaN are not expected in DSN coordinates, but the
        // formatter should produce something parseable rather than panic.
        let s_inf = format_dsn_arg(&DsnArg::Float(f64::INFINITY));
        let s_nan = format_dsn_arg(&DsnArg::Float(f64::NAN));
        assert!(!s_inf.is_empty());
        assert!(!s_nan.is_empty());
    }
}
