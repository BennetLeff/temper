// footprint_spec: FootprintSpec.
//
// Pure data holder — no logic beyond derived width()/height() accessors,
// so it is not on any golden-file byte-identity path. Kept working and
// exported on wasm32 (not currently imported from `temper_io_types` by any
// Python module, but part of the public pymodule surface).

#[derive(Clone, Debug, PartialEq)]
pub struct FootprintSpec {
    pub name: String,
    pub bounds: (f64, f64),
    pub courtyard_margin: f64,
    pub thermal_pad: bool,
    pub pin_1_offset: Option<(f64, f64)>,
}

impl FootprintSpec {
    pub fn width(&self) -> f64 {
        self.bounds.0
    }

    pub fn height(&self) -> f64 {
        self.bounds.1
    }

    pub fn repr(&self) -> String {
        format!(
            "FootprintSpec({:?}, bounds={:?}, thermal_pad={})",
            self.name, self.bounds, self.thermal_pad
        )
    }
}

#[cfg(feature = "python")]
mod py_bridge {
    use pyo3::prelude::*;
    use pyo3::types::PyTuple;
    use pyo3::IntoPyObjectExt;

    /// CPython-style repr of a Python string: single-quoted with backslash and
    /// single-quote escaping (matches ``repr("0805") == "'0805'"``). Rust's
    /// `{:?}` renders double quotes, which would diverge in the dataclass repr.
    fn py_str_repr(s: &str) -> String {
        let escaped = s.replace('\\', "\\\\").replace('\'', "\\'");
        format!("'{escaped}'")
    }

    /// `TypeError` CPython raises for a class whose `__hash__` is `None` —
    /// which is every `eq=True, frozen=False` dataclass. pyo3's default
    /// message would interpolate the dotted `tp_name`; raising explicitly
    /// keeps the text byte-identical to the oracle's `unhashable type:
    /// 'FootprintSpec'`.
    fn unhashable(class: &str) -> PyErr {
        pyo3::exceptions::PyTypeError::new_err(format!("unhashable type: '{class}'"))
    }

    /// Wave 4 Phase 3 candidate 5: the `io/footprint_library.py` dataclass
    /// coerces NOTHING — `FootprintSpec("0805", (2, 1))` stores `int` bounds
    /// and `.width` returns `int` `2`. The pyclass therefore stores every
    /// field as the caller's own object (`Py<PyAny>`), exactly the
    /// type-preservation-by-construction pattern board_contracts.rs uses;
    /// widening `int`→`float` is not merely untested but unrepresentable.
    #[pyclass(name = "FootprintSpec", from_py_object)]
    pub struct PyFootprintSpec {
        #[pyo3(get, set)]
        pub name: Py<PyAny>,
        #[pyo3(get, set)]
        pub bounds: Py<PyAny>,
        #[pyo3(get, set)]
        pub courtyard_margin: Py<PyAny>,
        #[pyo3(get, set)]
        pub thermal_pad: Py<PyAny>,
        #[pyo3(get, set)]
        pub pin_1_offset: Py<PyAny>,
    }

    // `#[pyclass(from_py_object)]` requires `Clone`; the manual impl borrows
    // (pyo3 0.29 renamed `Python::with_gil` to `Python::attach`).
    impl Clone for PyFootprintSpec {
        fn clone(&self) -> Self {
            Python::attach(|py| PyFootprintSpec {
                name: self.name.clone_ref(py),
                bounds: self.bounds.clone_ref(py),
                courtyard_margin: self.courtyard_margin.clone_ref(py),
                thermal_pad: self.thermal_pad.clone_ref(py),
                pin_1_offset: self.pin_1_offset.clone_ref(py),
            })
        }
    }

    impl PyFootprintSpec {
        fn field_list(&self, py: Python<'_>) -> Vec<Py<PyAny>> {
            vec![
                self.name.clone_ref(py),
                self.bounds.clone_ref(py),
                self.courtyard_margin.clone_ref(py),
                self.thermal_pad.clone_ref(py),
                self.pin_1_offset.clone_ref(py),
            ]
        }
    }

    #[pymethods]
    impl PyFootprintSpec {
        #[new]
        #[pyo3(signature = (name, bounds, courtyard_margin = None, thermal_pad = None, pin_1_offset = None))]
        fn new(
            name: &Bound<'_, PyAny>,
            bounds: &Bound<'_, PyAny>,
            courtyard_margin: Option<&Bound<'_, PyAny>>,
            thermal_pad: Option<&Bound<'_, PyAny>>,
            pin_1_offset: Option<&Bound<'_, PyAny>>,
        ) -> PyResult<Self> {
            let py = name.py();
            let courtyard_margin = match courtyard_margin {
                Some(v) => v.clone().unbind(),
                None => py.get_type::<pyo3::types::PyFloat>().call1((0.0,))?.unbind(),
            };
            let thermal_pad = match thermal_pad {
                Some(v) => v.clone().unbind(),
                None => py.get_type::<pyo3::types::PyBool>().call1((false,))?.unbind(),
            };
            Ok(PyFootprintSpec {
                name: name.clone().unbind(),
                bounds: bounds.clone().unbind(),
                courtyard_margin,
                thermal_pad,
                pin_1_offset: match pin_1_offset {
                    Some(v) => v.clone().unbind(),
                    None => py.None(),
                },
            })
        }

        /// `.width` returns `self.bounds[0]` as the oracle's property does —
        /// through Python's own `__getitem__`, so an `int` stays `int`.
        #[getter]
        fn width<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
            self.bounds.bind(py).get_item(0)
        }

        #[getter]
        fn height<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
            self.bounds.bind(py).get_item(1)
        }

        /// The oracle's dataclass repr: `FootprintSpec('0805', bounds=(2.0,
        /// 1.25), thermal_pad=False)` — `name` via `repr`, `bounds` via `str`,
        /// `thermal_pad` via `str` (`True`/`False`).
        fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
            let name = if let Ok(s) = self.name.extract::<String>(py) {
                py_str_repr(&s)
            } else {
                self.name.bind(py).repr()?.extract::<String>()?
            };
            let bounds = self.bounds.bind(py).str()?.extract::<String>()?;
            let thermal_pad = self.thermal_pad.bind(py).str()?.extract::<String>()?;
            Ok(format!(
                "FootprintSpec({name}, bounds={bounds}, thermal_pad={thermal_pad})"
            ))
        }

        /// Generated-dataclass `__eq__`: compare the field tuples when
        /// `other.__class__ is self.__class__`, else `NotImplemented`.
        fn __eq__(slf: &Bound<'_, Self>, other: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
            let py = slf.py();
            let this_type = slf.get_type();
            if !other.get_type().is(&this_type) {
                return Ok(py.NotImplemented());
            }
            let lhs = slf.borrow().field_list(py);
            let rhs = other.cast::<Self>()?.borrow().field_list(py);
            let lhs_tuple = PyTuple::new(py, lhs.iter().map(|v| v.bind(py)))?;
            let rhs_tuple = PyTuple::new(py, rhs.iter().map(|v| v.bind(py)))?;
            lhs_tuple.eq(&rhs_tuple)?.into_py_any(py)
        }

        /// `eq=True, frozen=False` -> the dataclass sets `__hash__ = None`.
        fn __hash__(&self) -> PyResult<isize> {
            Err(unhashable("FootprintSpec"))
        }
    }
}

#[cfg(feature = "python")]
pub use py_bridge::PyFootprintSpec;

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    #[cfg_attr(test, test)]
    fn width_height_are_bounds_components() {
        let spec = FootprintSpec {
            name: "SOIC-8".into(),
            bounds: (5.0, 4.0),
            courtyard_margin: 0.0,
            thermal_pad: false,
            pin_1_offset: None,
        };
        assert_eq!(spec.width(), 5.0);
        assert_eq!(spec.height(), 4.0);
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("footprint_spec::tests::width_height_are_bounds_components", width_height_are_bounds_components),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
