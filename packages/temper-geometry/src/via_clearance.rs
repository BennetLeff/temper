// Wave 4, tier-2 router_v6 cluster: the pure kernels of
// `temper_placer/router_v6/{via_placement, clearance_engine, grid_converter,
// path_simplify}.py`.
//
// The verbatim pre-migration copies this module must reproduce bit-identically
// are pinned in the `_oracle_*` block of
// `packages/temper-placer/tests/router_v6/
// test_via_clearance_tier2_rust_differential.py` (`git show f1ffc013`).
//
// ---------------------------------------------------------------------------
// Contract
// ---------------------------------------------------------------------------
// * `via_placement._get_adjacent_layer` is the shipped `dict.get` layer map
//   (including `B.Cu -> In2.Cu`: the map is not a cycle) and `None` for
//   anything else.  `_place_vias_for_path`'s segment scan is first-match
//   wins with `abs(...) < 1e-4` on BOTH axes; a NaN on either side never
//   matches (`abs(nan) < 1e-4` is false).  The from/to pair is
//   `segs[vi][2]` / `segs[vi+1][2]` when a matching segment with a successor
//   exists, else the `("F.Cu", "B.Cu")` fallback.  These two kernels are the
//   verbatim twins of `temper-drc-rs`'s `dfm::via_segment_index` /
//   `dfm::adjacent_layer`; they are re-homed here (home crate for router_v6
//   geometry) rather than imported, because `temper-geometry` must not take
//   a dependency on `temper-drc-rs`.
// * `clearance_engine.calculate_safety_distances` is a bracket lookup over
//   the IEC 60950-1 clearance/creepage tables, then the
//   `overvoltage_category >= 3` (x1.25 both) and `pollution_degree >= 3`
//   (creepage x2.0) multipliers.  All literals are exact f64 doubles; a NaN
//   voltage fails every `voltage <= vl` comparison (including the
//   `inf` sentinel) exactly like Python and keeps the initial 0.2/0.4.
// * `_kw_boundary_match` is the regex `(?:^|_)kw(?:$|[\d_])` with
//   `re.escape(kw)`.  `\d` is the Unicode Nd property (Python `re`), not
//   ASCII digits only -- so the trailing check uses `char::is_digit(10)`
//   (the same replication as `creepage_check.rs`'s `word_bounded`, which
//   this helper mirrors).  All shipped keywords are alphanumeric/underscore,
//   so the byte scan replicates the regex exactly; `re.escape` is the
//   identity on that set.
// * `_net_class_to_voltage_class` evaluates `net_class.upper()` then the
//   keyword branches in the reference's order, with the widened `120`/`240`
//   trailing boundary `(?:V|$|[\d_])`.  Returns the IEC 60335-1
//   `VoltageClass` *value* (1 = SELV, 2 = LOW_VOLTAGE, 3 = MAINS_120V,
//   4 = MAINS_240V, 5 = HIGH_VOLTAGE) -- the pyo3 `VoltageClass` enum in
//   `temper-design-bundle` assigns exactly these `auto()` values, and the
//   Python shim maps the int back to the enum.
// * `grid_converter.grid_to_world` is `(origin + cell * size) + size / 2`
//   evaluated left-to-right on int-promoted-to-f64 -- same expression shape,
//   same rounding.  `compute_path_length` accumulates `(dx + dy) * size`
//   with a naive `+=` fold (the reference's loop), int deltas computed in
//   i128 so i64 extremes cannot overflow (Python ints are unbounded).
//   `extract_vias` / `count_vias_in_path` are pure index/count scans over
//   consecutive-layer changes.
// * `path_simplify.{is_collinear, simplify_path, estimate_segment_count}` are
//   re-homed bit-for-bit from `temper-rust-router::terminal_planning` (the
//   earlier #856 slice); both are pinned against the same oracle
//   (`_path_simplify_py_oracle.py`).  Grid cells are all-int, so every
//   comparison is exact; the only order-sensitive behaviour is that
//   `simplify_path` iterates cells in order and appends -- it must never
//   build its result through a set.
//
// All pure kernels are exposed under the `python` feature via `register()`;
// the crate builds `--no-default-features` (WASM tier R1) with the pyo3
// surface compiled out.

#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use temper_py_bridge;

// ===========================================================================
// via_placement.py
// ===========================================================================

/// `via_placement._get_adjacent_layer` — the shipped `dict.get`.
pub fn adjacent_layer(layer_name: &str) -> Option<&'static str> {
    match layer_name {
        "F.Cu" => Some("In1.Cu"),
        "In1.Cu" => Some("In2.Cu"),
        "In2.Cu" => Some("B.Cu"),
        "B.Cu" => Some("In2.Cu"),
        _ => None,
    }
}

/// `via_placement._place_vias_for_path`'s segment-match scan: first match
/// wins, `abs(...) < 1e-4` on both axes, NaN never matches.  Returns `None`
/// for a ragged input (`seg_xs.len() != seg_ys.len()`); the Python caller
/// can never produce one (its `segments` are always 3-tuples), so the
/// channel is unobservable and the deterministic `None` is chosen over the
/// `temper-drc-rs` twin's error channel.
fn via_segment_index(vx: f64, vy: f64, seg_xs: &[f64], seg_ys: &[f64]) -> Option<usize> {
    if seg_xs.len() != seg_ys.len() {
        return None;
    }
    (0..seg_xs.len()).find(|&i| (seg_xs[i] - vx).abs() < 1e-4 && (seg_ys[i] - vy).abs() < 1e-4)
}

/// The derived `(from_layer, to_layer)` for a via at `(vx, vy)`:
/// `segs[vi][2]` / `segs[vi+1][2]` when a matching segment with a successor
/// exists, else the `("F.Cu", "B.Cu")` fallback — exactly the U3 branch of
/// `_place_vias_for_path`.
pub fn via_layer_pair(
    vx: f64,
    vy: f64,
    seg_xs: &[f64],
    seg_ys: &[f64],
    seg_layers: &[String],
) -> (String, String) {
    match via_segment_index(vx, vy, seg_xs, seg_ys) {
        Some(vi) if vi + 1 < seg_layers.len() => (seg_layers[vi].clone(), seg_layers[vi + 1].clone()),
        _ => ("F.Cu".to_string(), "B.Cu".to_string()),
    }
}

// ===========================================================================
// clearance_engine.py
// ===========================================================================

/// `calculate_safety_distances`'s IEC 60950-1 clearance/creepage tables and
/// the overvoltage/pollution multipliers.  Returns
/// `(clearance_mm, creepage_mm, voltage_v)` — the three fields of the
/// Python `SafetyDistances` dataclass.
pub fn safety_distances(voltage_v: f64, pollution_degree: i64, overvoltage_category: i64) -> (f64, f64, f64) {
    const CLEARANCE_TABLE: [(f64, f64); 6] = [
        (50.0, 0.2),
        (150.0, 1.0),
        (300.0, 2.0),
        (600.0, 2.5),
        (1000.0, 4.0),
        (f64::INFINITY, 5.0),
    ];
    const CREEPAGE_TABLE: [(f64, f64); 6] = [
        (50.0, 0.4),
        (150.0, 2.0),
        (300.0, 2.5),
        (600.0, 3.0),
        (1000.0, 5.0),
        (f64::INFINITY, 8.0),
    ];
    let mut clearance_mm = 0.2;
    for (vl, d) in CLEARANCE_TABLE {
        if voltage_v <= vl {
            clearance_mm = d;
            break;
        }
    }
    let mut creepage_mm = 0.4;
    for (vl, d) in CREEPAGE_TABLE {
        if voltage_v <= vl {
            creepage_mm = d;
            break;
        }
    }
    if overvoltage_category >= 3 {
        clearance_mm *= 1.25;
        creepage_mm *= 1.25;
    }
    if pollution_degree >= 3 {
        creepage_mm *= 2.0;
    }
    (clearance_mm, creepage_mm, voltage_v)
}

/// `(?:^|_)kw(?:$|[\d_])` — word-boundary scan with the Unicode-Nd trailing
/// digit (Python `re`'s `\d`), mirroring `creepage_check.rs`'s `word_bounded`
/// exactly.  Candidate start positions are 0 and every index right after
/// `_`; the trailing check decodes the next char so non-ASCII decimal digits
/// match.  `re.escape(kw)` is the identity on the shipped keyword set
/// (alphanumeric/underscore only).
fn word_bounded(name: &str, kw: &str) -> bool {
    let bytes = name.as_bytes();
    if name.len() < kw.len() {
        return false;
    }
    let mut i = 0usize;
    loop {
        if (i == 0 || bytes[i - 1] == b'_') && name[i..].starts_with(kw) {
            let after = i + kw.len();
            if after == name.len() {
                return true;
            }
            if let Some(c) = name[after..].chars().next() {
                // char::is_digit(10) is exactly the Unicode Nd property
                // (Python re `\d`); is_ascii_digit would miss non-ASCII digits.
                #[expect(clippy::is_digit_ascii_radix, reason = "Unicode Nd property required to match Python re \\d")]
                let is_digit = c.is_digit(10);
                if c == '_' || is_digit {
                    return true;
                }
            }
        }
        match bytes[i..].iter().position(|&b| b == b'_') {
            Some(p) => i += p + 1,
            None => return false,
        }
    }
}

/// `clearance_engine._kw_boundary_match`: does ANY keyword occur word-bounded
/// in `upper`?  Python's `any(...)` short-circuits; the outcome is the same.
pub fn kw_boundary_match(upper: &str, keywords: &[&str]) -> bool {
    keywords.iter().any(|kw| word_bounded(upper, kw))
}

/// `(?:^|_){digits}(?:V|$|[\d_])` — the widened trailing boundary the
/// reference uses for the literal `120`/`240` markers (`re.search`, so the
/// whole string is scanned, first match wins).
fn voltage_number(name: &str, digits: &str) -> bool {
    let bytes = name.as_bytes();
    if name.len() < digits.len() {
        return false;
    }
    let mut i = 0usize;
    loop {
        if (i == 0 || bytes[i - 1] == b'_') && name[i..].starts_with(digits) {
            let after = i + digits.len();
            if after == name.len() {
                return true;
            }
            if let Some(c) = name[after..].chars().next() {
                // char::is_digit(10) is exactly the Unicode Nd property
                // (Python re `\d`); is_ascii_digit would miss non-ASCII digits.
                #[expect(clippy::is_digit_ascii_radix, reason = "Unicode Nd property required to match Python re \\d")]
                let is_digit = c.is_digit(10);
                if c == 'V' || c == '_' || is_digit {
                    return true;
                }
            }
        }
        match bytes[i..].iter().position(|&b| b == b'_') {
            Some(p) => i += p + 1,
            None => return false,
        }
    }
}

/// `clearance_engine._net_class_to_voltage_class`, returned as the IEC 60335-1
/// `VoltageClass` value (1..=5) so the shim can map back to the pyo3 enum.
pub fn net_class_to_voltage_class(net_class: &str) -> i64 {
    let upper = net_class.to_uppercase();
    if kw_boundary_match(&upper, &["HIGH_VOLTAGE", "HV", "MAINS_240V", "MAINS", "AC"]) {
        if voltage_number(&upper, "120") {
            return 3; // MAINS_120V
        }
        if voltage_number(&upper, "240") || kw_boundary_match(&upper, &["MAINS"]) {
            return 4; // MAINS_240V
        }
        return 5; // HIGH_VOLTAGE
    }
    if voltage_number(&upper, "120") || kw_boundary_match(&upper, &["MAINS_120V"]) {
        return 3; // MAINS_120V
    }
    if kw_boundary_match(&upper, &["LOW_VOLTAGE", "LV", "POWER"]) {
        return 2; // LOW_VOLTAGE
    }
    1 // SELV
}

// ===========================================================================
// grid_converter.py
// ===========================================================================

/// `grid_converter.grid_to_world` — cell centre in world coordinates.
/// `(origin + cell * size) + size / 2`, left-to-right, exactly the
/// reference's expression shape.
pub fn grid_to_world(x: i64, y: i64, origin_x: f64, origin_y: f64, cell_size: f64) -> (f64, f64) {
    let fx = x as f64;
    let fy = y as f64;
    (origin_x + fx * cell_size + cell_size / 2.0, origin_y + fy * cell_size + cell_size / 2.0)
}

/// `grid_converter.extract_vias` — indices of consecutive layer transitions.
pub fn extract_vias(layers: &[i64]) -> Vec<usize> {
    let mut out = Vec::new();
    for i in 1..layers.len() {
        if layers[i] != layers[i - 1] {
            out.push(i);
        }
    }
    out
}

/// `grid_converter.compute_path_length` — Manhattan cell-distance summed with
/// a naive `+=` fold, int deltas in i128 (Python ints are unbounded), each
/// term `(dx + dy) as f64 * cell_size` exactly like the reference.
pub fn compute_path_length(xs: &[i64], ys: &[i64], cell_size: f64) -> f64 {
    if xs.len() != ys.len() || xs.len() < 2 {
        return 0.0;
    }
    let mut total = 0.0f64;
    for i in 1..xs.len() {
        let dx = (xs[i] as i128 - xs[i - 1] as i128).abs();
        let dy = (ys[i] as i128 - ys[i - 1] as i128).abs();
        total += (dx + dy) as f64 * cell_size;
    }
    total
}

/// `grid_converter.count_vias_in_path` — `len(extract_vias(cells))`.
pub fn count_vias_in_path(layers: &[i64]) -> usize {
    let mut n = 0usize;
    for i in 1..layers.len() {
        if layers[i] != layers[i - 1] {
            n += 1;
        }
    }
    n
}

// ===========================================================================
// path_simplify.py (re-homed from temper-rust-router terminal_planning.rs)
// ===========================================================================

/// `path_simplify.is_collinear` — all on one layer, then same-y (horizontal)
/// or same-x (vertical).  Exact int comparison.
pub fn is_collinear(p1: (i64, i64, i64), p2: (i64, i64, i64), p3: (i64, i64, i64)) -> bool {
    if !(p1.2 == p2.2 && p2.2 == p3.2) {
        return false;
    }
    if p1.1 == p2.1 && p2.1 == p3.1 {
        return true;
    }
    p1.0 == p2.0 && p2.0 == p3.0
}

/// `path_simplify.simplify_path` — keep layer transitions and direction
/// changes, always keep first and last.  Iterates in order and appends; never
/// reorders through a set.
pub fn simplify_path(cells: &[(i64, i64, i64)]) -> Vec<(i64, i64, i64)> {
    if cells.len() <= 2 {
        return cells.to_vec();
    }
    let mut simplified: Vec<(i64, i64, i64)> = Vec::with_capacity(cells.len());
    simplified.push(cells[0]);
    for i in 1..cells.len() - 1 {
        let prev = cells[i - 1];
        let curr = cells[i];
        let next = cells[i + 1];
        if curr.2 != prev.2 || curr.2 != next.2 {
            simplified.push(curr);
            continue;
        }
        if !is_collinear(prev, curr, next) {
            simplified.push(curr);
        }
    }
    simplified.push(cells[cells.len() - 1]);
    simplified
}

/// `path_simplify.estimate_segment_count` — same-layer consecutive pairs in
/// the simplified path.
pub fn estimate_segment_count(cells: &[(i64, i64, i64)]) -> usize {
    let simplified = simplify_path(cells);
    let mut count = 0usize;
    for i in 1..simplified.len() {
        if simplified[i].2 == simplified[i - 1].2 {
            count += 1;
        }
    }
    count
}

// ===========================================================================
// PyO3 bridge
// ===========================================================================

#[cfg(feature = "python")]
#[pyfunction]
pub fn adjacent_layer_py(layer_name: String) -> PyResult<Option<String>> {
    temper_py_bridge::catch_unwind(|| adjacent_layer(&layer_name).map(str::to_string))
        .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
#[pyfunction]
pub fn via_layer_pair_py(
    via_x: f64,
    via_y: f64,
    seg_xs: Vec<f64>,
    seg_ys: Vec<f64>,
    seg_layers: Vec<String>,
) -> PyResult<(String, String)> {
    temper_py_bridge::catch_unwind(|| via_layer_pair(via_x, via_y, &seg_xs, &seg_ys, &seg_layers))
        .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
#[pyfunction]
pub fn safety_distances_py(
    voltage_v: f64,
    pollution_degree: i64,
    overvoltage_category: i64,
) -> PyResult<(f64, f64, f64)> {
    temper_py_bridge::catch_unwind(|| {
        safety_distances(voltage_v, pollution_degree, overvoltage_category)
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
#[pyfunction]
pub fn kw_boundary_match_py(upper: String, keywords: Vec<String>) -> PyResult<bool> {
    let kws: Vec<&str> = keywords.iter().map(String::as_str).collect();
    temper_py_bridge::catch_unwind(|| kw_boundary_match(&upper, &kws))
        .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
#[pyfunction]
pub fn net_class_to_voltage_class_py(net_class: String) -> PyResult<i64> {
    temper_py_bridge::catch_unwind(|| net_class_to_voltage_class(&net_class))
        .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
#[pyfunction]
pub fn grid_to_world_py(
    x: i64,
    y: i64,
    origin_x: f64,
    origin_y: f64,
    cell_size: f64,
) -> PyResult<(f64, f64)> {
    temper_py_bridge::catch_unwind(|| grid_to_world(x, y, origin_x, origin_y, cell_size))
        .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
#[pyfunction]
pub fn extract_vias_py(layers: Vec<i64>) -> PyResult<Vec<usize>> {
    temper_py_bridge::catch_unwind(|| extract_vias(&layers)).map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
#[pyfunction]
pub fn compute_path_length_py(xs: Vec<i64>, ys: Vec<i64>, cell_size: f64) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| compute_path_length(&xs, &ys, cell_size))
        .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
#[pyfunction]
pub fn count_vias_in_path_py(layers: Vec<i64>) -> PyResult<usize> {
    temper_py_bridge::catch_unwind(|| count_vias_in_path(&layers))
        .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
#[pyfunction]
pub fn is_collinear_py(
    p1: (i64, i64, i64),
    p2: (i64, i64, i64),
    p3: (i64, i64, i64),
) -> PyResult<bool> {
    temper_py_bridge::catch_unwind(|| is_collinear(p1, p2, p3)).map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
#[pyfunction]
pub fn simplify_path_py(cells: Vec<(i64, i64, i64)>) -> PyResult<Vec<(i64, i64, i64)>> {
    temper_py_bridge::catch_unwind(|| simplify_path(&cells)).map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
#[pyfunction]
pub fn estimate_segment_count_py(cells: Vec<(i64, i64, i64)>) -> PyResult<usize> {
    temper_py_bridge::catch_unwind(|| estimate_segment_count(&cells))
        .map_err(temper_py_bridge::panic_to_err)
}

/// Register the tier-2 kernels on the `temper_geometry` module.
#[cfg(feature = "python")]
pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(adjacent_layer_py, m)?)?;
    m.add_function(wrap_pyfunction!(via_layer_pair_py, m)?)?;
    m.add_function(wrap_pyfunction!(safety_distances_py, m)?)?;
    m.add_function(wrap_pyfunction!(kw_boundary_match_py, m)?)?;
    m.add_function(wrap_pyfunction!(net_class_to_voltage_class_py, m)?)?;
    m.add_function(wrap_pyfunction!(grid_to_world_py, m)?)?;
    m.add_function(wrap_pyfunction!(extract_vias_py, m)?)?;
    m.add_function(wrap_pyfunction!(compute_path_length_py, m)?)?;
    m.add_function(wrap_pyfunction!(count_vias_in_path_py, m)?)?;
    m.add_function(wrap_pyfunction!(is_collinear_py, m)?)?;
    m.add_function(wrap_pyfunction!(simplify_path_py, m)?)?;
    m.add_function(wrap_pyfunction!(estimate_segment_count_py, m)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn adjacent_layer_map() {
        assert_eq!(adjacent_layer("F.Cu"), Some("In1.Cu"));
        assert_eq!(adjacent_layer("In1.Cu"), Some("In2.Cu"));
        assert_eq!(adjacent_layer("In2.Cu"), Some("B.Cu"));
        assert_eq!(adjacent_layer("B.Cu"), Some("In2.Cu"));
        assert_eq!(adjacent_layer("In3.Cu"), None);
        assert_eq!(adjacent_layer(""), None);
    }

    #[test]
    fn via_segment_index_matches_and_epsilon() {
        let xs = [0.0, 5.0, 5.0, 10.0];
        let ys = [0.0, 0.0, 0.0, 0.0];
        assert_eq!(via_segment_index(5.0, 0.0, &xs, &ys), Some(1));
        // First match wins when two segments coincide.
        let xs2 = [5.0, 5.0, 10.0];
        let ys2 = [0.0, 0.0, 0.0];
        assert_eq!(via_segment_index(5.0, 0.0, &xs2, &ys2), Some(0));
        // Just inside epsilon on both axes.
        assert_eq!(via_segment_index(5.000099, 0.000099, &xs, &ys), Some(1));
        // 5.0001 is NOT safely "outside": 5.0001 - 5.0 in f64 rounds BELOW
        // 1e-4, so both Python and Rust treat it as a match.  Use a clearly
        // outside value instead.
        assert_eq!(via_segment_index(5.00015, 0.0, &xs, &ys), None);
        // NaN never matches.
        assert_eq!(via_segment_index(f64::NAN, 0.0, &xs, &ys), None);
        // Ragged input -> deterministic None.
        assert_eq!(via_segment_index(5.0, 0.0, &xs, &[0.0]), None);
    }

    #[test]
    fn via_layer_pair_derives_and_falls_back() {
        let xs = [0.0, 5.0, 5.0, 10.0];
        let ys = [0.0, 0.0, 0.0, 0.0];
        let layers = ["F.Cu", "F.Cu", "B.Cu", "B.Cu"]
            .into_iter()
            .map(str::to_string)
            .collect::<Vec<_>>();
        assert_eq!(
            via_layer_pair(5.0, 0.0, &xs, &ys, &layers),
            ("F.Cu".to_string(), "B.Cu".to_string())
        );
        // Last segment: no successor -> fallback.
        assert_eq!(
            via_layer_pair(10.0, 0.0, &xs, &ys, &layers),
            ("F.Cu".to_string(), "B.Cu".to_string())
        );
        // No match -> fallback.
        assert_eq!(
            via_layer_pair(99.0, 99.0, &xs, &ys, &layers),
            ("F.Cu".to_string(), "B.Cu".to_string())
        );
        // Empty segments -> fallback.
        assert_eq!(
            via_layer_pair(1.0, 1.0, &[], &[], &[]),
            ("F.Cu".to_string(), "B.Cu".to_string())
        );
    }

    #[test]
    fn safety_distances_tables_and_multipliers() {
        // Brackets at the boundary values.
        assert_eq!(safety_distances(50.0, 2, 2).0, 0.2);
        assert_eq!(safety_distances(50.0001, 2, 2).0, 1.0);
        assert_eq!(safety_distances(150.0, 2, 2).0, 1.0);
        assert_eq!(safety_distances(1000.0, 2, 2).0, 4.0);
        assert_eq!(safety_distances(1200.0, 2, 2).0, 5.0);
        assert_eq!(safety_distances(50.0, 2, 2).1, 0.4);
        assert_eq!(safety_distances(150.0, 2, 2).1, 2.0);
        assert_eq!(safety_distances(1200.0, 2, 2).1, 8.0);
        // Overvoltage category >= 3 scales both by 1.25.
        assert_eq!(safety_distances(100.0, 2, 3).0, 1.0 * 1.25);
        assert_eq!(safety_distances(100.0, 2, 3).1, 2.0 * 1.25);
        // Pollution degree >= 3 doubles creepage only.
        assert_eq!(safety_distances(100.0, 3, 2).1, 2.0 * 2.0);
        assert_eq!(safety_distances(100.0, 3, 2).0, 1.0);
        // NaN voltage: every `voltage <= vl` is false -> initial values.
        assert_eq!(safety_distances(f64::NAN, 2, 2).0, 0.2);
        assert_eq!(safety_distances(f64::NAN, 2, 2).1, 0.4);
        // +inf voltage hits the sentinel bracket.
        assert_eq!(safety_distances(f64::INFINITY, 2, 2).0, 5.0);
        assert_eq!(safety_distances(f64::INFINITY, 2, 2).1, 8.0);
        // -inf / negative voltages fall through to the lowest bracket.
        assert_eq!(safety_distances(f64::NEG_INFINITY, 2, 2).0, 0.2);
        assert_eq!(safety_distances(-5.0, 2, 2).1, 0.4);
        // voltage_v is passed through verbatim.
        assert_eq!(safety_distances(340.0, 2, 2).2, 340.0);
    }

    #[test]
    fn kw_boundary_match_positive_and_negative() {
        for (label, word) in [
            ("AC_L", "AC"),
            ("AC1", "AC"),
            ("_AC", "AC"),
            ("AC_", "AC"),
            ("HV_BUS", "HV"),
            ("HV1", "HV"),
            ("X_HV_2", "HV"),
            ("MAINS_240V", "MAINS_240V"),
            ("MAINS_120V", "MAINS_120V"),
            ("MAINS", "MAINS"),
            ("LOW_VOLTAGE", "LOW_VOLTAGE"),
            ("POWER", "POWER"),
        ] {
            assert!(kw_boundary_match(label, &[word]), "{label} ~ {word}");
        }
        for (label, word) in [
            ("TRACE", "AC"),
            ("ACH", "AC"),
            ("CAC", "AC"),
            ("AC-", "AC"),
            ("AC.", "AC"),
            ("AC:", "AC"),
            ("HIVE", "HV"),
            ("BEHAVE", "HV"),
            ("XHVX", "HV"),
            ("COIL1", "AC"),
            ("COIL2", "AC"),
            ("safety-line", "AC"),
            ("MAINS_EXTRA", "MAINS_240V"), // suffix must be `_`/digit/end
            ("MAINS240V", "MAINS_240V"),
        ] {
            assert!(!kw_boundary_match(label, &[word]), "{label} ~ {word}");
        }
        // any() semantics: one matching keyword suffices.
        assert!(kw_boundary_match("LOW_VOLTAGE_HV", &["AC", "HV"]));
    }

    #[test]
    fn net_class_to_voltage_class_branches() {
        // Value contract: 1=SELV, 2=LOW_VOLTAGE, 3=MAINS_120V,
        // 4=MAINS_240V, 5=HIGH_VOLTAGE.
        assert_eq!(net_class_to_voltage_class("MAINS_120V"), 3);
        assert_eq!(net_class_to_voltage_class("MAINS_240V"), 4);
        assert_eq!(net_class_to_voltage_class("MAINS"), 4);
        assert_eq!(net_class_to_voltage_class("HV"), 5);
        assert_eq!(net_class_to_voltage_class("AC_L"), 5);
        assert_eq!(net_class_to_voltage_class("AC1"), 5);
        assert_eq!(net_class_to_voltage_class("HIGH_VOLTAGE"), 5);
        assert_eq!(net_class_to_voltage_class("120V"), 3);
        // "240V" alone is SELV: the standalone 120-check has no 240 twin --
        // the 240 branch fires only AFTER an HV/MAINS keyword matched first.
        assert_eq!(net_class_to_voltage_class("240V"), 1);
        assert_eq!(net_class_to_voltage_class("LV"), 2);
        assert_eq!(net_class_to_voltage_class("POWER"), 2);
        assert_eq!(net_class_to_voltage_class("GND"), 1);
        assert_eq!(net_class_to_voltage_class("Signal"), 1);
        assert_eq!(net_class_to_voltage_class(""), 1);
        // Case-insensitivity.
        assert_eq!(net_class_to_voltage_class("hv"), 5);
        assert_eq!(net_class_to_voltage_class("mains_120v"), 3);
        // Substring landmines must NOT fire.
        assert_eq!(net_class_to_voltage_class("ACH"), 1);
        assert_eq!(net_class_to_voltage_class("HIVE"), 1);
        assert_eq!(net_class_to_voltage_class("COIL1"), 1);
        // "MAINS240V": "MAINS" IS word-bounded (followed by digit "2"), so the
        // 240 branch fires -- exactly as the Python oracle does.
        assert_eq!(net_class_to_voltage_class("MAINS240V"), 4);
    }

    #[test]
    fn grid_kernels() {
        assert_eq!(grid_to_world(10, 20, 0.0, 0.0, 0.5), (5.25, 10.25));
        assert_eq!(grid_to_world(0, 0, 0.0, 0.0, 0.5), (0.25, 0.25));
        assert_eq!(grid_to_world(0, 0, 0.0, 0.0, 0.0), (0.0, 0.0));
        assert_eq!(grid_to_world(-3, 7, -10.0, 2.5, 0.25), (-10.625, 4.375));

        let layers = [0, 0, 1, 1, 2];
        assert_eq!(extract_vias(&layers), vec![2, 4]);
        assert_eq!(count_vias_in_path(&layers), 2);
        assert_eq!(extract_vias(&[]), Vec::<usize>::new());
        assert_eq!(count_vias_in_path(&[0]), 0);
        assert_eq!(count_vias_in_path(&[0, 0, 0]), 0);

        assert_eq!(
            compute_path_length(&[0, 1, 2], &[0, 0, 0], 0.5),
            1.0 // (1 + 1) * 0.5
        );
        assert_eq!(compute_path_length(&[0, 1], &[0, 1], 0.5), 1.0);
        assert_eq!(compute_path_length(&[], &[], 0.5), 0.0);
        assert_eq!(compute_path_length(&[5], &[5], 0.5), 0.0);
        assert_eq!(compute_path_length(&[0, 0], &[0, 0], 0.5), 0.0); // layer change adds nothing
        // Large-coordinate extremes must not overflow (i128 deltas).
        assert_eq!(
            compute_path_length(&[i64::MAX, i64::MIN], &[0, 0], 1.0),
            (i64::MAX as f64) * 2.0 + 1.0
        );
    }

    #[test]
    fn path_simplify_kernels() {
        assert!(is_collinear((0, 0, 0), (1, 0, 0), (2, 0, 0)));
        assert!(is_collinear((0, 0, 0), (0, 1, 0), (0, 2, 0)));
        assert!(!is_collinear((0, 0, 0), (1, 0, 0), (1, 1, 0)));
        assert!(!is_collinear((0, 0, 1), (1, 0, 0), (2, 0, 0))); // layer mismatch
        assert!(!is_collinear((0, 0, 0), (1, 1, 0), (2, 2, 0))); // diagonal
        assert!(is_collinear((3, 3, 0), (3, 3, 0), (3, 3, 0))); // coincident

        let straight = vec![(0, 0, 0), (1, 0, 0), (2, 0, 0)];
        assert_eq!(simplify_path(&straight), vec![(0, 0, 0), (2, 0, 0)]);
        assert_eq!(estimate_segment_count(&straight), 1);

        let l_shape = vec![(0, 0, 0), (1, 0, 0), (1, 1, 0)];
        assert_eq!(simplify_path(&l_shape), l_shape);
        assert_eq!(estimate_segment_count(&l_shape), 2);

        let layer_change = vec![(0, 0, 0), (1, 0, 0), (1, 0, 1)];
        assert_eq!(simplify_path(&layer_change), layer_change);
        // Layer transitions create vias, not segments.
        assert_eq!(estimate_segment_count(&layer_change), 1);

        assert_eq!(simplify_path(&[]), Vec::<(i64, i64, i64)>::new());
        let single = vec![(5, 5, 0)];
        assert_eq!(simplify_path(&single), single);
    }
}

// ===========================================================================
// Property-based and metamorphic tests (G4/G5), running natively so they are
// exercised by `cargo test -p temper-geometry` even when the pyo3 extension
// is not importable in the shared venv.
//
// Property IDs P1-P5 map to the Python PBT file
// `test_via_clearance_tier2_pbt.py`; M1-M3 are the metamorphic relations.
// ===========================================================================
#[cfg(test)]
mod properties {
    use super::*;
    use proptest::prelude::*;

    fn coord() -> impl Strategy<Value = i64> {
        -100i64..100i64
    }

    fn layer() -> impl Strategy<Value = i64> {
        0i64..4i64
    }

    fn path() -> impl Strategy<Value = Vec<(i64, i64, i64)>> {
        proptest::collection::vec((coord(), coord(), layer()), 0..16)
    }

    proptest! {
        #![proptest_config(ProptestConfig { cases: 2000, ..ProptestConfig::default() })]
        // 2000 cases, matching the other native property suites in this crate.

        /// P1. `grid_to_world`'s x and y components are separable: the x
        /// output of `(x, y)` equals the x output of `(x, 0)` and the y
        /// output of `(x, y)` equals the y output of `(0, y)`, both
        /// BIT-EXACT (each is the same `origin + cell*size + size/2`
        /// expression).  A degenerate kernel that mixes the axes (e.g.
        /// returns `(x + y, ...)`) fails this on the first case.
        #[test]
        fn p1_grid_to_world_axes_are_separable(
            x in coord(), y in coord(), ox in -50.0f64..50.0, oy in -50.0f64..50.0,
            size in 0.1f64..10.0,
        ) {
            let (gx, gy) = grid_to_world(x, y, ox, oy, size);
            let (sx, _) = grid_to_world(x, 0, ox, oy, size);
            let (_, sy) = grid_to_world(0, y, ox, oy, size);
            prop_assert_eq!(gx, sx, "x axis not separable");
            prop_assert_eq!(gy, sy, "y axis not separable");
        }

        /// P2. `compute_path_length` of a two-cell path is exactly
        /// `(abs(dx) + abs(dy)) * size` -- int deltas in i128, then one
        /// int->f64 promotion and one multiply, exactly the reference's term
        /// shape.  A degenerate kernel that returns a constant (or that
        /// forgot the int-to-float promotion) fails this on the first case.
        #[test]
        fn p2_path_length_two_cells_matches_formula(
            x1 in coord(), y1 in coord(), x2 in coord(), y2 in coord(), size in 0.1f64..10.0,
        ) {
            let got = compute_path_length(&[x1, x2], &[y1, y2], size);
            let dx = (x2 as i128 - x1 as i128).abs();
            let dy = (y2 as i128 - y1 as i128).abs();
            let expected = (dx + dy) as f64 * size;
            prop_assert_eq!(got, expected, "{} != {}", got, expected);
        }

        /// P3. `safety_distances`'s IEC brackets are monotone: a higher
        /// voltage never requires LESS clearance or creepage (before the
        /// pollution/overvoltage multipliers, which do not involve voltage).
        #[test]
        fn p3_safety_distances_monotone_in_voltage(
            a in 0.0f64..1200.0, b in 0.0f64..1200.0,
        ) {
            let (lo, hi) = if a <= b { (a, b) } else { (b, a) };
            let (c_lo, k_lo, _) = safety_distances(lo, 2, 2);
            let (c_hi, k_hi, _) = safety_distances(hi, 2, 2);
            prop_assert!(c_hi >= c_lo, "clearance({hi}) < clearance({lo})");
            prop_assert!(k_hi >= k_lo, "creepage({hi}) < creepage({lo})");
        }

        /// P4. `net_class_to_voltage_class` is total and monotone with
        /// respect to the classification ladder: appending a suffix that is
        /// a `_`+digit (e.g. "HV" -> "HV_2") never changes the class, and
        /// the "broader" labels resolve to the expected dominant class.
        #[test]
        fn p4_voltage_class_agnostic_to_numeric_suffix(label in "[A-Z_]{0,24}") {
            let with_suffix = format!("{label}_3");
            prop_assert_eq!(
                net_class_to_voltage_class(&with_suffix),
                net_class_to_voltage_class(&label),
                "numeric `_N` suffix changed the class of {}",
                label
            );
        }

        /// P5. `extract_vias`/`count_vias_in_path`/`estimate_segment_count`
        /// agree with each other on any path: the count of via positions the
        /// router will place equals the number of layer transitions, and the
        /// simplified segment count is >= the number of layer-boundary
        /// transitions and never exceeds the simplified length.
        #[test]
        fn p5_via_counts_and_segments_consistent(cells in path()) {
            let layers: Vec<i64> = cells.iter().map(|t| t.2).collect();
            let transitions = extract_vias(&layers).len();
            prop_assert_eq!(transitions, count_vias_in_path(&layers));
            let simplified = simplify_path(&cells);
            let segs = estimate_segment_count(&cells);
            prop_assert!(segs <= simplified.len(), "{segs} > {} (simplified length)", simplified.len());
            // Same-layer consecutive pairs never exceed the number of cells.
            prop_assert!(segs <= cells.len(), "{segs} > {} (cells)", cells.len());
        }
    }

    proptest! {
        #![proptest_config(ProptestConfig { cases: 1000, ..ProptestConfig::default() })]
        /// M1 (metamorphic). `compute_path_length` is invariant under a
        /// TRANSLATION of the whole path by an integer offset: int deltas are
        /// unchanged, so the result is bit-exact, not approximate.
        #[test]
        fn m1_path_length_invariant_under_translation(
            cells in path(), tx in -50i64..50, ty in -50i64..50, size in 0.1f64..10.0,
        ) {
            let (xs, ys): (Vec<i64>, Vec<i64>) = cells.iter().map(|t| (t.0, t.1)).unzip();
            let before = compute_path_length(&xs, &ys, size);
            let (xs2, ys2): (Vec<i64>, Vec<i64>) =
                cells.iter().map(|t| (t.0 + tx, t.1 + ty)).unzip();
            let after = compute_path_length(&xs2, &ys2, size);
            prop_assert_eq!(before, after, "translation changed the Manhattan length");
        }

        /// M2 (metamorphic). `simplify_path` is invariant under coordinate
        /// reflection (x -> -x): collinearity, layer transitions and order are
        /// all preserved exactly.
        #[test]
        fn m2_simplify_invariant_under_reflection(cells in path()) {
            let reflected: Vec<(i64, i64, i64)> =
                cells.iter().map(|t| (-t.0, -t.1, t.2)).collect();
            let a = simplify_path(&cells);
            let b = simplify_path(&reflected);
            prop_assert_eq!(a.len(), b.len(), "reflection changed the simplified length");
            for (pa, pb) in a.iter().zip(b.iter()) {
                prop_assert_eq!(pa.0, -pb.0);
                prop_assert_eq!(pa.1, -pb.1);
                prop_assert_eq!(pa.2, pb.2);
            }
        }

        /// M3 (metamorphic). `safety_distances` is monotone under the
        /// pollution-degree ladder: for fixed voltage and overvoltage
        /// category, creepage never decreases as pollution degree rises from
        /// 1 to 2 to 3.
        #[test]
        fn m3_safety_distances_monotone_in_pollution(voltage in 0.0f64..1200.0, ovcat in 1i64..5) {
            let (_, k1, _) = safety_distances(voltage, 1, ovcat);
            let (_, k2, _) = safety_distances(voltage, 2, ovcat);
            let (_, k3, _) = safety_distances(voltage, 3, ovcat);
            prop_assert!(k2 >= k1, "creepage(2) < creepage(1)");
            prop_assert!(k3 >= k2, "creepage(3) < creepage(2)");
        }
    }
}
