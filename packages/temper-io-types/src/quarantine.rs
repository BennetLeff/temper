//! quarantine: dead-letter quarantine compute for the pipeline-failure
//! taxonomy (`temper_placer/testing/quarantine.py` migration).
//!
//! The pre-migration module's deterministic kernels move here:
//!
//! - `classify`          — the `classify_error` taxonomy decision table
//!   (stage + lowercased message + exception class name → taxonomy class);
//! - `sha256_hex_prefix` — the stack-hash reduction
//!   `hashlib.sha256(...).hexdigest()[:12]`;
//! - `count_lines` / `has_kicad_header` — the board-fingerprint content
//!   kernels (`content.count("\n") + 1` and
//!   `"(kicad_pcb" in content.lower()[:200]`).
//!
//! The exported pyfunctions (all under `#[cfg(feature = "python")]`) are
//! thin `Bound`-to-kernel adapters; the shim
//! (`src/temper_placer/testing/quarantine.py`) wires them. What stays
//! Python (the shim, kept as evidence — it is the dead-letter manifest
//! management, not portable compute): `QuarantineEntry` (+ its
//! `to_dict`/`to_json` dataclass serialization), `quarantine_error` (the
//! date-directory + entry-file write orchestration), `_update_manifest`,
//! `load_manifest`, `quarantine_summary` (the presentation) and the
//! `TAXONOMY_CLASSES` label table. The pre-migration module is pinned
//! VERBATIM as `tests/testing/_quarantine_py_oracle.py` (content-hash
//! registered in `scripts/oracle_hashes.json`); bit-identical parity is
//! pinned by `tests/testing/test_quarantine_rust_differential.py`.
//!
//! Bit-exactness traps pinned here:
//! - `classify_error` reads `str(error)` and `type(error).__name__`
//!   through CPython (`PyObject_Str` / `__name__`), so exception `__str__`
//!   overrides and exception-class hierarchies behave identically; the
//!   kernel receives the already-extracted message + class name and applies
//!   the decision table. The `.lower()` substring checks run on Rust
//!   `str::to_lowercase` — identical to CPython `str.lower()` for the
//!   ASCII exception messages this pipeline produces (the differential
//!   suite pins that domain; exotic-Unicode lowercasing divergences are
//!   out of scope and documented below).
//! - `compute_stack_hash` renders the traceback through CPython's
//!   `traceback.format_exception(type, exc, exc.__traceback__)`: the
//!   pre-migration hash covers the *formatted* traceback text, whose
//!   rendering is CPython semantics (frame iteration, source-line lookup,
//!   exception chaining, per-version syntax-error carets) that no Rust
//!   reimplementation can be bit-identical to across Python versions. The
//!   genuinely portable compute — the SHA-256 prefix — is Rust
//!   (`sha256_hex_prefix`, sha2, byte-identical to `hashlib.sha256`).
//! - `compute_fingerprint` reads the file with Rust `std::fs`; the
//!   `errors="replace"` UTF-8 decode is `String::from_utf8_lossy` (both
//!   replace each invalid sequence with U+FFFD). `has_kicad_header` slices
//!   the first 200 *code points* like Python's `[:200]`. The
//!   `except Exception` unreadable fallback (`readable: False`) is a
//!   match arm on the read result.
//!
//! Ascii-boundary note: `str::to_lowercase` vs CPython `str.lower()` agree
//! for ASCII; the classifier's keywords and realistic exception messages
//! are ASCII by construction, and the differential/PBT suites constrain
//! their inputs accordingly. kicad_pcb content is ASCII by the format's
//! spec, so `has_kicad_header` is exact on any real board file.

use std::path::Path;

/// `hashlib.sha256(data).hexdigest()[:prefix_len]` — the stack-hash prefix.
pub fn sha256_hex_prefix(data: &[u8], prefix_len: usize) -> String {
    crate::provenance::sha256_hex(data)
        .chars()
        .take(prefix_len)
        .collect()
}

/// The `classify_error` decision table, as a pure function over the
/// already-extracted message and exception class name.
///
/// Returns the `PARSE_*` / `STAGE_*` / `UNKNOWN` taxonomy class string
/// exactly as the pre-migration table does (branch order preserved).
pub fn classify(stage: &str, message: &str, cls_name: &str) -> &'static str {
    let msg = message.to_lowercase();
    match stage {
        "parse" => {
            if msg.contains("version") || msg.contains("format_version") {
                "PARSE_KICAD_VERSION_MISMATCH"
            } else if msg.contains("footprint") || msg.contains("lib") {
                "PARSE_MISSING_FOOTPRINT_LIB"
            } else if msg.contains("decode") || msg.contains("utf") || msg.contains("encoding")
            {
                "PARSE_DECODE_ERROR"
            } else if msg.contains("zero") && (msg.contains("component") || msg.contains("net")) {
                "PARSE_EMPTY_BOARD"
            } else if matches!(cls_name, "SyntaxError" | "ValueError" | "KeyError") {
                "PARSE_UNSUPPORTED_SYNTAX"
            } else {
                "PARSE_UNKNOWN"
            }
        }
        "preflight" => "STAGE_PREFLIGHT_FAILED",
        "geometric" => "STAGE_GEOMETRIC_DIVERGED",
        "routing" => "STAGE_ROUTING_FAILED",
        "output" => "STAGE_OUTPUT_FAILED",
        _ => "UNKNOWN",
    }
}

/// `content.count("\n") + 1` — the fingerprint's line count.
pub fn count_lines(content: &str) -> usize {
    content.matches('\n').count() + 1
}

/// `"(kicad_pcb" in content.lower()[:200]` — the fingerprint's header probe.
pub fn has_kicad_header(content: &str) -> bool {
    let head: String = content.chars().take(200).collect();
    head.to_lowercase().contains("(kicad_pcb")
}

#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use pyo3::types::PyDict;

/// The pre-migration `classify_error`: extract `str(error)` and
/// `type(error).__name__` through CPython, then apply the pure decision
/// table.
#[cfg(feature = "python")]
#[pyfunction]
pub fn classify_error(stage: &str, exc: &Bound<'_, PyAny>) -> PyResult<String> {
    let msg_py = exc.str()?;
    let msg = msg_py.to_string_lossy();
    let cls_name: String = exc.get_type().getattr("__name__")?.extract()?;
    Ok(classify(stage, &msg, &cls_name).to_string())
}

/// The pre-migration `compute_stack_hash`: format the traceback through
/// CPython (bit-identical rendering by construction — see the module doc's
/// trap note), then reduce it with the Rust SHA-256 prefix kernel.
#[cfg(feature = "python")]
#[pyfunction]
pub fn compute_stack_hash(py: Python<'_>, exc: &Bound<'_, PyAny>) -> PyResult<String> {
    let traceback_mod = py.import("traceback")?;
    let parts = traceback_mod.getattr("format_exception")?.call1((
        exc.get_type(),
        exc,
        exc.getattr("__traceback__")?,
    ))?;
    let mut joined = String::new();
    for part in parts.try_iter()? {
        joined.push_str(&part?.extract::<String>()?);
    }
    Ok(sha256_hex_prefix(joined.as_bytes(), 12))
}

/// The pre-migration `compute_fingerprint`: build the board fingerprint
/// dict from the filesystem (exists / size_bytes / lines /
/// has_kicad_header, or the `readable: False` fallback).
#[cfg(feature = "python")]
#[pyfunction]
pub fn compute_fingerprint(py: Python<'_>, path: &str) -> PyResult<Py<PyDict>> {
    let board_path = Path::new(path);
    let fp = PyDict::new(py);
    fp.set_item("path", path)?;
    let exists = board_path.exists();
    fp.set_item("exists", exists)?;
    if exists {
        let meta = board_path.metadata()?;
        fp.set_item("size_bytes", meta.len())?;
        match std::fs::read(board_path) {
            Ok(bytes) => {
                let content = String::from_utf8_lossy(&bytes);
                fp.set_item("lines", count_lines(&content))?;
                fp.set_item("has_kicad_header", has_kicad_header(&content))?;
            }
            Err(_) => {
                fp.set_item("readable", false)?;
            }
        }
    }
    Ok(fp.unbind())
}

#[cfg(test)]
#[cfg(feature = "python")]
#[allow(clippy::unwrap_used)]
mod tests {
    use super::*;

    #[test]
    fn sha256_hex_prefix_truncates_sha256() {
        let full = crate::provenance::sha256_hex(b"x");
        assert_eq!(full.len(), 64);
        let pref = sha256_hex_prefix(b"x", 12);
        assert_eq!(pref, &full[..12]);
        assert_eq!(pref.len(), 12);
    }

    #[test]
    fn classify_parse_branch_precedence_matches_python() {
        // Precedence: version > footprint/lib > decode/utf > empty-board >
        // syntax classes > UNKNOWN — an earlier match wins.
        assert_eq!(classify("parse", "version mismatch", "ValueError"), "PARSE_KICAD_VERSION_MISMATCH");
        assert_eq!(classify("parse", "footprint library missing", "RuntimeError"), "PARSE_MISSING_FOOTPRINT_LIB");
        assert_eq!(classify("parse", "decode failed", "UnicodeDecodeError"), "PARSE_DECODE_ERROR");
        assert_eq!(classify("parse", "zero nets found", "ValueError"), "PARSE_EMPTY_BOARD");
        assert_eq!(classify("parse", "unexpected token", "SyntaxError"), "PARSE_UNSUPPORTED_SYNTAX");
        assert_eq!(classify("parse", "weird thing", "RuntimeError"), "PARSE_UNKNOWN");
    }

    #[test]
    fn classify_non_parse_stages_and_unknown() {
        assert_eq!(classify("preflight", "x", "E"), "STAGE_PREFLIGHT_FAILED");
        assert_eq!(classify("geometric", "x", "E"), "STAGE_GEOMETRIC_DIVERGED");
        assert_eq!(classify("routing", "x", "E"), "STAGE_ROUTING_FAILED");
        assert_eq!(classify("output", "x", "E"), "STAGE_OUTPUT_FAILED");
        assert_eq!(classify("nope", "x", "E"), "UNKNOWN");
        assert_eq!(classify("", "x", "E"), "UNKNOWN");
    }

    #[test]
    fn classify_is_case_insensitive_on_ascii() {
        assert_eq!(classify("parse", "VERSION MISMATCH", "ValueError"), "PARSE_KICAD_VERSION_MISMATCH");
        assert_eq!(classify("parse", "UTF-8", "UnicodeDecodeError"), "PARSE_DECODE_ERROR");
        assert_eq!(classify("parse", "Zero Components", "ValueError"), "PARSE_EMPTY_BOARD");
    }

    #[test]
    fn classify_keywords_take_precedence_over_class_name() {
        // "valueerror" class name but a version keyword in the message:
        // the message keyword wins (checked before the class-name arm).
        assert_eq!(classify("parse", "format_version", "ValueError"), "PARSE_KICAD_VERSION_MISMATCH");
        // class name alone (no keyword) routes to UNSUPPORTED_SYNTAX.
        assert_eq!(classify("parse", "oops", "KeyError"), "PARSE_UNSUPPORTED_SYNTAX");
        // a non-listed class name falls through to PARSE_UNKNOWN.
        assert_eq!(classify("parse", "oops", "RuntimeError"), "PARSE_UNKNOWN");
    }

    #[test]
    fn count_lines_matches_python_count_plus_one() {
        assert_eq!(count_lines(""), 1);
        assert_eq!(count_lines("a"), 1);
        assert_eq!(count_lines("a\nb"), 2);
        assert_eq!(count_lines("a\n"), 2);
        assert_eq!(count_lines("\n\n\n"), 4);
    }

    #[test]
    fn has_kicad_header_probes_first_200_chars_lowercased() {
        assert!(has_kicad_header("(kicad_pcb (version 20240108)\n)"));
        assert!(has_kicad_header("  (KiCad_PCB (version 1)\n)"));
        assert!(!has_kicad_header("(other_format\n)"));
        // Probe stops at 200 code points, like Python's [:200].
        let late = format!("{}x", "a".repeat(200));
        assert!(!has_kicad_header(&late));
        let at_200 = format!("{}(kicad_pcb", "a".repeat(190));
        assert!(has_kicad_header(&at_200));
    }
}
