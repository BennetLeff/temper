//! Wave 4 Phase 4 — regression slice: fingerprint kernels.
//!
//! The hashing/decision compute of `temper_placer/regression/fingerprint.py`
//! (pinned verbatim as the oracle `_fingerprint_py_oracle.py`, commit
//! `0a29f15e3`) migrated into `temper-design-bundle`:
//!
//! | Kernel | Python origin |
//! |---|---|
//! | `input_fingerprint` | `compute_input_fingerprint`'s SHA-256 update sequence (existing-file bytes / missing-path strings, then `seed:`/`epochs:` suffixes) |
//! | `source_fingerprint` | `compute_source_fingerprint`'s `"\n"`-join + SHA-256 |
//! | `should_skip` | `should_skip` — the cache skip decision |
//!
//! Design boundaries (argued in-source; see
//! `packages/temper-design-bundle/VERIFICATION.md`):
//!
//! - File I/O stays Python-side: the delegation module reads the input
//!   files, walks `SOURCE_FINGERPRINT_DIRS` for `*.py`, and computes each
//!   file's hash with the crate's own `sha256_hex` (identical to
//!   `hashlib.sha256().hexdigest()` — SHA-256 is standardized; pinned anyway
//!   by the differential). The kernels operate on the marshalled parts.
//! - The input-parts ORDER is the oracle's `sorted([pcb, constraints,
//!   baseline])` path sort, performed in the delegation module and preserved
//!   by the kernel (a missing file contributes `str(path).encode()`, an
//!   existing one contributes its bytes — this is what makes path order
//!   observable).
//! - `should_skip` mirrors the oracle's falsy-board-cache semantics: `None`
//!   OR an empty dict → False; a dict lacking either fingerprint key →
//!   False (None never equals a hash string).

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyDictMethods, PyModule};
use sha2::{Digest, Sha256};

/// Input fingerprint over already-read parts (verbatim port of
/// `compute_input_fingerprint`'s update sequence). Each part is
/// `(Some(bytes) | None, path_string)`: existing files contribute their
/// bytes, missing files contribute `str(path).encode()`, then
/// `seed:{seed}` / `epochs:{epochs}` are appended. Returns the hex digest.
#[pyfunction]
fn input_fingerprint(
    parts: Vec<(Option<Vec<u8>>, String)>,
    seed: i64,
    epochs: i64,
) -> String {
    let mut hasher = Sha256::new();
    for (bytes, path_str) in &parts {
        match bytes {
            Some(b) => hasher.update(b),
            None => hasher.update(path_str.as_bytes()),
        }
    }
    hasher.update(format!("seed:{seed}").as_bytes());
    hasher.update(format!("epochs:{epochs}").as_bytes());
    format!("{:x}", hasher.finalize())
}

/// Source fingerprint over the pre-joined `path:hash` entry lines (verbatim
/// port of `compute_source_fingerprint`'s join+hash): the entries are joined
/// with `"\n"` and SHA-256'd.
#[pyfunction]
fn source_fingerprint(entries: Vec<String>) -> String {
    let joined = entries.join("\n");
    format!("{:x}", Sha256::digest(joined.as_bytes()))
}

/// Cache skip decision (verbatim port of `should_skip`): the board's cache
/// entry must exist (truthy) and carry BOTH fingerprints matching the given
/// ones. The delegation module performs the `cache["boards"][board_id]`
/// lookup and passes the resulting entry (or `None`).
#[pyfunction]
fn should_skip(
    input_fingerprint: String,
    source_fingerprint: String,
    board_cache: Option<&Bound<'_, PyDict>>,
) -> PyResult<bool> {
    let Some(cache) = board_cache else {
        return Ok(false);
    };
    // The oracle's `if not board_cache` — an empty dict is falsy.
    if cache.is_empty() {
        return Ok(false);
    }
    let cache_input: Option<String> = match cache.get_item("input_fingerprint")? {
        Some(v) => v.extract()?,
        None => None,
    };
    let cache_source: Option<String> = match cache.get_item("source_fingerprint")? {
        Some(v) => v.extract()?,
        None => None,
    };
    Ok(cache_input.as_deref() == Some(input_fingerprint.as_str())
        && cache_source.as_deref() == Some(source_fingerprint.as_str()))
}

/// Register the fingerprint kernels on the `temper_design_bundle_python` module.
pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(input_fingerprint, m)?)?;
    m.add_function(wrap_pyfunction!(source_fingerprint, m)?)?;
    m.add_function(wrap_pyfunction!(should_skip, m)?)?;
    Ok(())
}
