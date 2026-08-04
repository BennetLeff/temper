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
    use super::*;
    use pyo3::prelude::*;

    #[pyclass(name = "FootprintSpec", from_py_object)]
    #[derive(Clone)]
    pub struct PyFootprintSpec {
        #[pyo3(get, set)]
        pub name: String,
        #[pyo3(get, set)]
        pub bounds: (f64, f64),
        #[pyo3(get, set)]
        pub courtyard_margin: f64,
        #[pyo3(get, set)]
        pub thermal_pad: bool,
        #[pyo3(get, set)]
        pub pin_1_offset: Option<(f64, f64)>,
    }

    impl PyFootprintSpec {
        fn pure(&self) -> FootprintSpec {
            FootprintSpec {
                name: self.name.clone(),
                bounds: self.bounds,
                courtyard_margin: self.courtyard_margin,
                thermal_pad: self.thermal_pad,
                pin_1_offset: self.pin_1_offset,
            }
        }
    }

    #[pymethods]
    impl PyFootprintSpec {
        #[new]
        #[pyo3(signature = (name, bounds, courtyard_margin = 0.0, thermal_pad = false, pin_1_offset = None))]
        fn new(
            name: String,
            bounds: (f64, f64),
            courtyard_margin: f64,
            thermal_pad: bool,
            pin_1_offset: Option<(f64, f64)>,
        ) -> Self {
            PyFootprintSpec {
                name,
                bounds,
                courtyard_margin,
                thermal_pad,
                pin_1_offset,
            }
        }

        #[getter]
        fn width(&self) -> f64 {
            self.pure().width()
        }

        #[getter]
        fn height(&self) -> f64 {
            self.pure().height()
        }

        fn __repr__(&self) -> String {
            self.pure().repr()
        }
    }
}

#[cfg(feature = "python")]
pub use py_bridge::PyFootprintSpec;

#[cfg(test)]
#[allow(clippy::unwrap_used, clippy::expect_used)]
mod tests {
    use super::*;

    #[test]
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
}
