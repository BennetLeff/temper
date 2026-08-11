// footprint_parser: FootprintBounds, parse_footprint_courtyard, parse_footprint_directory.
//
// The parser itself (`parse_footprint_courtyard_str`) is pure regex over a
// `&str` and has no filesystem or pyo3 dependency — it is exported
// unconditionally, including on wasm32. Reading the `.kicad_mod` file from
// disk is a separate step gated on `not(target_arch = "wasm32")` (wasm32
// has no filesystem), and the pyo3-facing `#[pyfunction]`s that combine the
// two are additionally gated on the `python` feature.

use regex::Regex;
use std::sync::OnceLock;

#[derive(Clone, Debug, PartialEq)]
pub struct FootprintBounds {
    pub width: f64,
    pub height: f64,
    pub center_offset: (f64, f64),
}

impl FootprintBounds {
    pub fn repr(&self) -> String {
        format!(
            "FootprintBounds(width={}, height={}, center_offset={:?})",
            self.width, self.height, self.center_offset
        )
    }
}

fn fp_line_pattern() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    #[expect(
        clippy::unwrap_used,
        reason = "literal pattern compiled from a source constant; cannot fail"
    )]
    RE.get_or_init(|| {
        Regex::new(concat!(
            r"(?m)\(fp_line\s+",
            r"\(start\s+([-\d.]+)\s+([-\d.]+)\)\s+",
            r"\(end\s+([-\d.]+)\s+([-\d.]+)\)\s+",
            r#"\(layer\s+"([FB]\.CrtYd)"\)"#
        ))
        .unwrap()
    })
}

fn fp_rect_pattern() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    #[expect(
        clippy::unwrap_used,
        reason = "literal pattern compiled from a source constant; cannot fail"
    )]
    RE.get_or_init(|| {
        Regex::new(concat!(
            r"(?m)\(fp_rect\s+",
            r"\(start\s+([-\d.]+)\s+([-\d.]+)\)\s+",
            r"\(end\s+([-\d.]+)\s+([-\d.]+)\)\s+",
            r#"\(layer\s+"([FB]\.CrtYd)"\)"#
        ))
        .unwrap()
    })
}

/// Parse the courtyard bounds out of the raw text content of a
/// `.kicad_mod` footprint file. Pure — no filesystem, no Python.
///
/// `source_label` is used only to build the "no courtyard found in {}"
/// error message (callers with a real path pass its display string;
/// callers without one, e.g. wasm32 embedders parsing an in-memory
/// string, can pass any label such as `"<input>"`).
pub fn parse_footprint_courtyard_str(
    content: &str,
    source_label: &str,
) -> Result<FootprintBounds, String> {
    let mut x_coords: Vec<f64> = Vec::new();
    let mut y_coords: Vec<f64> = Vec::new();

    for caps in fp_line_pattern().captures_iter(content) {
        let x1: f64 = caps[1].parse().unwrap_or(0.0);
        let y1: f64 = caps[2].parse().unwrap_or(0.0);
        let x2: f64 = caps[3].parse().unwrap_or(0.0);
        let y2: f64 = caps[4].parse().unwrap_or(0.0);
        x_coords.push(x1);
        y_coords.push(y1);
        x_coords.push(x2);
        y_coords.push(y2);
    }

    for caps in fp_rect_pattern().captures_iter(content) {
        let x1: f64 = caps[1].parse().unwrap_or(0.0);
        let y1: f64 = caps[2].parse().unwrap_or(0.0);
        let x2: f64 = caps[3].parse().unwrap_or(0.0);
        let y2: f64 = caps[4].parse().unwrap_or(0.0);
        x_coords.push(x1);
        y_coords.push(y1);
        x_coords.push(x2);
        y_coords.push(y1);
        x_coords.push(x2);
        y_coords.push(y2);
        x_coords.push(x1);
        y_coords.push(y2);
    }

    if x_coords.is_empty() {
        return Err(format!(
            "No courtyard (F.CrtYd or B.CrtYd) found in {}. \
             Footprint must have courtyard lines to extract bounds.",
            source_label
        ));
    }

    let min_x = x_coords.iter().cloned().fold(f64::INFINITY, f64::min);
    let max_x = x_coords.iter().cloned().fold(f64::NEG_INFINITY, f64::max);
    let min_y = y_coords.iter().cloned().fold(f64::INFINITY, f64::min);
    let max_y = y_coords.iter().cloned().fold(f64::NEG_INFINITY, f64::max);

    let width = max_x - min_x;
    let height = max_y - min_y;
    let center_x = (min_x + max_x) / 2.0;
    let center_y = (min_y + max_y) / 2.0;

    Ok(FootprintBounds {
        width,
        height,
        center_offset: (center_x, center_y),
    })
}

// ---------------------------------------------------------------------------
// Filesystem-backed entry points (native only — wasm32 has no filesystem).
// ---------------------------------------------------------------------------

#[cfg(not(target_arch = "wasm32"))]
pub fn read_footprint_file(path: &std::path::Path) -> std::io::Result<String> {
    std::fs::read_to_string(path)
}

#[cfg(feature = "python")]
mod py_fs {
    use super::*;
    use pyo3::prelude::*;
    use std::collections::HashMap;
    use std::path::PathBuf;

    pyo3::create_exception!(
        temper_io_types,
        FootprintParseError,
        pyo3::exceptions::PyException
    );

    #[pyclass(name = "FootprintBounds", from_py_object)]
    #[derive(Clone)]
    pub struct PyFootprintBounds {
        #[pyo3(get, set)]
        pub width: f64,
        #[pyo3(get, set)]
        pub height: f64,
        #[pyo3(get, set)]
        pub center_offset: (f64, f64),
    }

    impl From<FootprintBounds> for PyFootprintBounds {
        fn from(b: FootprintBounds) -> Self {
            PyFootprintBounds {
                width: b.width,
                height: b.height,
                center_offset: b.center_offset,
            }
        }
    }

    impl PyFootprintBounds {
        fn pure(&self) -> FootprintBounds {
            FootprintBounds {
                width: self.width,
                height: self.height,
                center_offset: self.center_offset,
            }
        }
    }

    #[pymethods]
    impl PyFootprintBounds {
        #[new]
        #[pyo3(signature = (width, height, center_offset = (0.0, 0.0)))]
        fn new(width: f64, height: f64, center_offset: (f64, f64)) -> Self {
            PyFootprintBounds {
                width,
                height,
                center_offset,
            }
        }

        fn __repr__(&self) -> String {
            self.pure().repr()
        }
    }

    #[pyfunction]
    pub fn parse_footprint_courtyard(path: PathBuf) -> PyResult<PyFootprintBounds> {
        if !path.exists() {
            return Err(pyo3::exceptions::PyFileNotFoundError::new_err(format!(
                "Footprint file not found: {}",
                path.display()
            )));
        }

        let content = read_footprint_file(&path).map_err(|e| {
            FootprintParseError::new_err(format!("Error reading {}: {}", path.display(), e))
        })?;

        parse_footprint_courtyard_str(&content, &path.display().to_string())
            .map(PyFootprintBounds::from)
            .map_err(FootprintParseError::new_err)
    }

    #[pyfunction]
    pub fn parse_footprint_directory(
        directory: PathBuf,
    ) -> PyResult<HashMap<String, PyFootprintBounds>> {
        let mut results: HashMap<String, PyFootprintBounds> = HashMap::new();

        let entries = match std::fs::read_dir(&directory) {
            Ok(e) => e,
            Err(e) => {
                return Err(pyo3::exceptions::PyOSError::new_err(format!(
                    "Error reading directory {}: {}",
                    directory.display(),
                    e
                )));
            }
        };

        for entry in entries.flatten() {
            let path = entry.path();
            if path.extension().and_then(|e| e.to_str()) != Some("kicad_mod") {
                continue;
            }
            let Some(stem) = path.file_stem().and_then(|s| s.to_str()) else {
                continue;
            };
            if let Ok(bounds) = parse_footprint_courtyard(path.clone()) {
                results.insert(stem.to_string(), bounds);
            }
        }

        Ok(results)
    }
}

#[cfg(feature = "python")]
pub use py_fs::{
    FootprintParseError, PyFootprintBounds, parse_footprint_courtyard, parse_footprint_directory,
};

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    const TO247: &str = r#"
(footprint "Package_TO_SOT_THT:TO-247-3_Horizontal_TabDown"
  (layer "F.Cu")
  (fp_line (start -8.0 -10.5) (end 8.0 -10.5) (layer "F.CrtYd") (width 0.05))
  (fp_line (start 8.0 -10.5) (end 8.0 10.5) (layer "F.CrtYd") (width 0.05))
  (fp_line (start 8.0 10.5) (end -8.0 10.5) (layer "F.CrtYd") (width 0.05))
  (fp_line (start -8.0 10.5) (end -8.0 -10.5) (layer "F.CrtYd") (width 0.05))
)
"#;

    #[cfg_attr(test, test)]
    fn parses_to247_courtyard() {
        let bounds = parse_footprint_courtyard_str(TO247, "<test>").expect("should parse");
        assert!((bounds.width - 16.0).abs() < 0.5);
        assert!((bounds.height - 21.0).abs() < 0.5);
    }

    #[cfg_attr(test, test)]
    fn parses_fp_rect_courtyard() {
        let content = r#"
(footprint "Test:RectCourt"
  (layer "F.Cu")
  (fp_rect (start -2.0 -1.0) (end 2.0 1.0) (layer "F.CrtYd") (width 0.05))
)
"#;
        let bounds = parse_footprint_courtyard_str(content, "<test>").expect("should parse");
        assert!((bounds.width - 4.0).abs() < 0.1);
        assert!((bounds.height - 2.0).abs() < 0.1);
    }

    #[cfg_attr(test, test)]
    fn parses_back_courtyard() {
        let content = r#"
(footprint "Test:BackSide"
  (layer "B.Cu")
  (fp_line (start -3.0 -2.0) (end 3.0 -2.0) (layer "B.CrtYd") (width 0.05))
  (fp_line (start 3.0 -2.0) (end 3.0 2.0) (layer "B.CrtYd") (width 0.05))
  (fp_line (start 3.0 2.0) (end -3.0 2.0) (layer "B.CrtYd") (width 0.05))
  (fp_line (start -3.0 2.0) (end -3.0 -2.0) (layer "B.CrtYd") (width 0.05))
)
"#;
        let bounds = parse_footprint_courtyard_str(content, "<test>").expect("should parse");
        assert!((bounds.width - 6.0).abs() < 0.1);
        assert!((bounds.height - 4.0).abs() < 0.1);
    }

    #[cfg_attr(test, test)]
    fn no_courtyard_is_an_error() {
        let content = r#"
(footprint "Test:NoCourt"
  (layer "F.Cu")
  (pad "1" smd rect (at 0 0) (size 1.0 1.0))
)
"#;
        let err = parse_footprint_courtyard_str(content, "NoCourt.kicad_mod").unwrap_err();
        assert!(err.to_lowercase().contains("courtyard"));
        assert!(err.contains("NoCourt.kicad_mod"));
    }

    #[cfg_attr(test, test)]
    fn invalid_content_is_an_error() {
        let err =
            parse_footprint_courtyard_str("not valid s-expression content", "<test>").unwrap_err();
        assert!(err.to_lowercase().contains("courtyard"));
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("footprint::tests::parses_to247_courtyard", parses_to247_courtyard),
        ("footprint::tests::parses_fp_rect_courtyard", parses_fp_rect_courtyard),
        ("footprint::tests::parses_back_courtyard", parses_back_courtyard),
        ("footprint::tests::no_courtyard_is_an_error", no_courtyard_is_an_error),
        ("footprint::tests::invalid_content_is_an_error", invalid_content_is_an_error),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
