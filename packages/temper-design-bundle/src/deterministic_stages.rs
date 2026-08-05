//! Deterministic leaf-stage compute — Wave 4 **Phase 5, first slice**
//! (deterministic stages).
//!
//! Ports the pure compute of three deterministic leaf stages to Rust:
//!
//! | Python module | Rust function(s) |
//! |---|---|
//! | `deterministic/stages/slot_generation.py` | [`generate_slots_for_zone`] |
//! | `deterministic/stages/zone_geometry.py` | [`define_zone_layout`], [`scale_zone_bounds`] |
//! | `deterministic/stages/zone_assignment.py` | [`assign_component_zones`] |
//!
//! The pre-migration implementations are pinned VERBATIM as the differential
//! oracles in `packages/temper-placer/tests/deterministic/stages/`
//! (`_slot_generation_py_oracle.py`, `_zone_geometry_py_oracle.py`,
//! `_zone_assignment_py_oracle.py`); the Python stages become delegation
//! shims that keep their `run()` orchestration (the `state.*` guards and
//! the `frozenset` wraps) in Python. Bit-exactness is asserted by
//! `test_{slot_generation,zone_geometry,zone_assignment}_rust_differential.py`
//! and the PBT suites; the structural proof lives in `VERIFICATION.md`.
//!
//! # Numerical-traps pinned here (see `docs/MIGRATION_PHASE_GUIDE.md`)
//!
//! - **Naive `+=` accumulation** (NOT compensated): `generate_slots_for_zone`
//!   walks `x`/`y` with `x += spacing`, so the generated coordinates drift
//!   from `min + k*spacing` by the accumulated rounding error. Rust `f64`
//!   `+=` accumulates identically to CPython; the differential pins the drift
//!   with `spacing = 0.1` (not exactly representable).
//! - **Strict `<` upper bounds**: a slot exactly at `x_max`/`y_max` is NOT
//!   emitted, and `spacing >= zone extent` yields an EMPTY slot list.
//! - **`int`-vs-`float` leaves**: the oracle's 4-zone layout uses integer `0`
//!   for `HV.x_min` and every `y_min` (`((0, 0), ...)`). The type-carrying
//!   differential canon discriminates `int` from `float`, so
//!   [`define_zone_layout`] emits Python `int` `0` in exactly those positions
//!   (a Rust `0.0_f64` would fail the differential).
//! - **Expression order**: every boundary is `board_width * 0.3 / * 0.6 /
//!   * 0.9`, and each subsequent zone reuses the *previous* product
//!   (`power_x_min = hv_x_max`, ...) rather than a fresh multiply.
//! - **Dict insertion order**: `assign_component_zones` emits `(ref, zone)`
//!   pairs in `netlist.components` order (the shim rebuilds the dict, so
//!   insertion order is pinned); `comp_nets` appends net names in netlist
//!   order.
//! - **Empty-input semantics**: a zone with zero extent or `spacing >=
//!   extent` yields `[]`; a netlist with no components yields `[]`; a
//!   component with no nets defaults to `Signal` (unless `U_MCU`-prefixed).

use std::collections::HashMap;
use std::panic::AssertUnwindSafe;

use pyo3::prelude::*;
use pyo3::types::PyTuple;

use crate::netlist_contracts::unpack2;

/// Wrap a pyo3 boundary body so a Rust panic surfaces as a Python
/// `RuntimeError` instead of aborting the interpreter (G7 / R1g
/// `catch_unwind` at every pyo3 boundary).
fn guard<R>(body: impl FnOnce() -> PyResult<R>) -> PyResult<R> {
    match temper_py_bridge::catch_unwind(AssertUnwindSafe(body)) {
        Ok(result) => result,
        Err(payload) => Err(temper_py_bridge::panic_to_err(payload)),
    }
}

/// Build one `(name, xmin, ymin, xmax, ymax)` layout row as a Python tuple.
///
/// `xmin`/`ymin` arrive as `Bound<PyAny>` so the caller controls the
/// concrete Python type (the oracle stores `int` `0` for HV's `x_min` and
/// every `y_min`; the type-carrying differential canon must see those as
/// `int`, not `float`).
fn layout_row<'py>(
    py: Python<'py>,
    name: &str,
    xmin: Bound<'py, PyAny>,
    ymin: Bound<'py, PyAny>,
    xmax: f64,
    ymax: f64,
) -> PyResult<Bound<'py, PyTuple>> {
    let items: Vec<Bound<'py, PyAny>> = vec![
        name.into_pyobject(py)?.into_any(),
        xmin,
        ymin,
        xmax.into_pyobject(py)?.into_any(),
        ymax.into_pyobject(py)?.into_any(),
    ];
    PyTuple::new(py, items)
}

/// `SlotGenerationStage._generate_slots_for_zone` — the slot-grid walk.
///
/// Mirrors the oracle exactly: start at `min + spacing / 2` (the half-cell
/// anchor is computed once per row), accumulate with naive `+=`, and use
/// strict `<` upper bounds. `spacing >= extent` (or a zero-extent zone)
/// produces an empty list.
fn generate_slots(x_min: f64, y_min: f64, x_max: f64, y_max: f64, spacing: f64) -> Vec<(f64, f64)> {
    let mut slots: Vec<(f64, f64)> = Vec::new();
    let mut x = x_min + spacing / 2.0;
    while x < x_max {
        let mut y = y_min + spacing / 2.0;
        while y < y_max {
            slots.push((x, y));
            y += spacing;
        }
        x += spacing;
    }
    slots
}

/// The boundary products of the 4-zone layout: `w * 0.3 / * 0.6 / * 0.9`,
/// each subsequent zone REUSING the previous product (not a fresh multiply).
struct LayoutBoundaries {
    hv_x_max: f64,
    power_x_max: f64,
    signal_x_max: f64,
}

fn layout_boundaries(board_width: f64) -> LayoutBoundaries {
    LayoutBoundaries {
        hv_x_max: board_width * 0.3,
        power_x_max: board_width * 0.6,
        signal_x_max: board_width * 0.9,
    }
}

/// The dict-branch scale: `ratio[i] * board_dim`, in the oracle's order.
fn scale_bounds(r0: f64, r1: f64, r2: f64, r3: f64, w: f64, h: f64) -> (f64, f64, f64, f64) {
    (r0 * w, r1 * h, r2 * w, r3 * h)
}

#[pyfunction]
fn generate_slots_for_zone(
    _py: Python<'_>,
    x_min: f64,
    y_min: f64,
    x_max: f64,
    y_max: f64,
    spacing: f64,
) -> PyResult<Vec<(f64, f64)>> {
    guard(|| Ok(generate_slots(x_min, y_min, x_max, y_max, spacing)))
}

/// `ZoneGeometryStage._define_zone_layout` — the 4-zone MVP-3 layout.
///
/// Returns `(name, xmin, ymin, xmax, ymax)` rows in zone order
/// (`HV, Power, Signal, MCU`). Every boundary is `board_width * 0.3 / 0.6 /
/// 0.9` with each subsequent zone REUSING the previous product (not a fresh
/// multiply); `HV.x_min` and every `y_min` are Python `int` `0` (oracle
/// `((0, 0), ...)` — the type-carrying canon pins int-vs-float).
#[pyfunction]
fn define_zone_layout<'py>(
    py: Python<'py>,
    board_width: f64,
    board_height: f64,
) -> PyResult<Vec<Bound<'py, PyTuple>>> {
    guard(|| {
        let b = layout_boundaries(board_width);
        let zero = 0i64.into_pyobject(py)?.into_any();
        let rows = vec![
            layout_row(
                py,
                "HV",
                zero.clone(),
                zero.clone(),
                b.hv_x_max,
                board_height,
            )?,
            layout_row(
                py,
                "Power",
                b.hv_x_max.into_pyobject(py)?.into_any(),
                zero.clone(),
                b.power_x_max,
                board_height,
            )?,
            layout_row(
                py,
                "Signal",
                b.power_x_max.into_pyobject(py)?.into_any(),
                zero.clone(),
                b.signal_x_max,
                board_height,
            )?,
            layout_row(
                py,
                "MCU",
                b.signal_x_max.into_pyobject(py)?.into_any(),
                zero.clone(),
                board_width,
                board_height,
            )?,
        ];
        Ok(rows)
    })
}

/// The `_define_zones_from_config` dict branch: `bounds_ratio` scaled by the
/// board dimensions, `ratio[i] * board_dim` in the oracle's order.
///
/// Returns the flat bounds `(xmin, ymin, xmax, ymax)` — all floats (the
/// products are always `float` in the oracle). `name` is accepted (the
/// caller passes it through) but is not part of the returned bounds.
// 8 args (7 Python + GIL token) is dictated by the differential's positional
// call surface `RS_SCALE(name, r0, r1, r2, r3, w, h)`; flattening would
// change the boundary contract the pinned oracle drives.
#[allow(clippy::too_many_arguments)]
#[pyfunction]
fn scale_zone_bounds(
    _py: Python<'_>,
    _name: &str,
    r0: f64,
    r1: f64,
    r2: f64,
    r3: f64,
    board_width: f64,
    board_height: f64,
) -> PyResult<(f64, f64, f64, f64)> {
    guard(|| Ok(scale_bounds(r0, r1, r2, r3, board_width, board_height)))
}

/// `ZoneAssignmentStage._assign_components_to_zones` — component-to-zone
/// assignment by ref prefix, protocol nets, and net class.
///
/// Reads the `Netlist`/`Net`/`Component` pyclass attribute surface
/// (`nets`, `components`, `net.name`, `net.net_class`, `net.pins`,
/// `component.ref`) dynamically — the exact attributes the oracle reads — so
/// both arms of the differential consume the identical input objects.
/// Returns `(ref, zone)` pairs in `netlist.components` order (the shim
/// rebuilds the dict, preserving insertion order).
#[pyfunction]
fn assign_component_zones<'py>(
    _py: Python<'py>,
    netlist: &Bound<'py, PyAny>,
) -> PyResult<Vec<(String, String)>> {
    guard(|| {
        let nets = netlist.getattr("nets")?;
        let components = netlist.getattr("components")?;

        // net_class_map: net.name -> net.net_class. The oracle's
        // `getattr(net, "net_class", "Signal")` fallback never fires on the
        // pyclass, which always carries `net_class` (default "Signal").
        let mut net_class_map: HashMap<String, String> = HashMap::new();
        for net in nets.try_iter()? {
            let net = net?;
            let name: String = net.getattr("name")?.extract()?;
            let net_class: String = net.getattr("net_class")?.extract()?;
            net_class_map.insert(name, net_class);
        }

        // comp_nets: comp_ref -> [net names], appended in netlist order
        // (outer loop over nets, inner loop over each net's pins).
        let mut comp_nets: HashMap<String, Vec<String>> = HashMap::new();
        for net in nets.try_iter()? {
            let net = net?;
            let name: String = net.getattr("name")?.extract()?;
            let pins = net.getattr("pins")?;
            for pin in pins.try_iter()? {
                let pin = pin?;
                // Oracle unpacks `for comp_ref, _ in net.pins` — unpack to
                // keep the ValueError-on-wrong-arity behaviour.
                let (comp_ref, _pin_name) = unpack2(&pin)?;
                let comp_ref: String = comp_ref.extract()?;
                comp_nets.entry(comp_ref).or_default().push(name.clone());
            }
        }

        let mut out: Vec<(String, String)> = Vec::new();
        for component in components.try_iter()? {
            let component = component?;
            let r#ref: String = component.getattr("ref")?.extract()?;
            let nets_of = comp_nets.get(&r#ref).map(Vec::as_slice).unwrap_or(&[]);
            let zone = infer_zone(&r#ref, nets_of, &net_class_map);
            out.push((r#ref, zone));
        }
        Ok(out)
    })
}

/// The five priority-ordered rules of `_infer_zone_for_component`.
fn infer_zone(
    r#ref: &str,
    nets: &[String],
    net_class_map: &HashMap<String, String>,
) -> String {
    // Rule 1: MCU zone by ref prefix.
    if r#ref.starts_with("U_MCU") {
        return "MCU".to_string();
    }
    // Rule 2: MCU zone by SPI/I2C/UART nets (substring on the uppercased
    // name). ASCII-identical to CPython `str.upper()` on the pinned surface.
    for net_name in nets {
        let upper = net_name.to_uppercase();
        if ["SPI", "I2C", "UART"].iter().any(|proto| upper.contains(proto)) {
            return "MCU".to_string();
        }
    }
    // Rule 3: HV zone by net class.
    for net_name in nets {
        if net_class_map.get(net_name).map(String::as_str) == Some("HighVoltage") {
            return "HV".to_string();
        }
    }
    // Rule 4: Power zone by net class.
    for net_name in nets {
        if net_class_map.get(net_name).map(String::as_str) == Some("Power") {
            return "Power".to_string();
        }
    }
    // Rule 5: Signal zone (default).
    "Signal".to_string()
}

// ---------------------------------------------------------------------------
// Registration
// ---------------------------------------------------------------------------

/// Registered as a submodule (`temper_design_bundle_python.deterministic_stages`)
/// so the delegation shims and the differential/PBT suites can address the
/// migrated kernels by name.
pub fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    let py = module.py();
    let sub = PyModule::new(py, "deterministic_stages")?;
    sub.add_function(wrap_pyfunction!(generate_slots_for_zone, &sub)?)?;
    sub.add_function(wrap_pyfunction!(define_zone_layout, &sub)?)?;
    sub.add_function(wrap_pyfunction!(scale_zone_bounds, &sub)?)?;
    sub.add_function(wrap_pyfunction!(assign_component_zones, &sub)?)?;
    module.add_submodule(&sub)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn slots_basic_grid() {
        let got = generate_slots(0.0, 0.0, 10.0, 10.0, 2.0);
        assert_eq!(got.len(), 25);
        assert_eq!(got[0], (1.0, 1.0));
        assert_eq!(got[24], (9.0, 9.0));
    }

    #[test]
    fn slots_empty_when_spacing_covers_zone() {
        assert!(generate_slots(0.0, 0.0, 1.0, 1.0, 5.0).is_empty());
        assert!(generate_slots(2.0, 2.0, 2.0, 2.0, 1.0).is_empty());
    }

    #[test]
    fn slots_strict_upper_bound_excludes_exact_max() {
        let got = generate_slots(0.0, 0.0, 10.0, 10.0, 2.0);
        for (x, y) in &got {
            assert!(*x < 10.0 && *y < 10.0);
        }
        assert!(!got.iter().any(|(x, _)| *x == 11.0));
    }

    #[test]
    fn slots_naive_accumulation_matches_expected_drift() {
        // spacing 0.1 is not exactly representable: the second y value is the
        // accumulated 0.05+0.1 sum, not 2*0.1.
        let got = generate_slots(0.0, 0.0, 1.0, 1.0, 0.1);
        let x_first = 0.05_f64;
        let y_first = 0.05_f64;
        assert_eq!(got[0], (x_first, y_first));
        assert_eq!(got[1], (x_first, y_first + 0.1));
        assert_eq!(got[2], (x_first, (y_first + 0.1) + 0.1));
    }

    #[test]
    fn layout_boundaries_reuse_products() {
        // w * 0.3 / * 0.6 / * 0.9, and each boundary REUSES the previous
        // product: power_x_min == hv_x_max, signal_x_min == power_x_max,
        // mcu_x_min == signal_x_max.
        let b = layout_boundaries(100.0);
        assert_eq!(b.hv_x_max, 30.0);
        assert_eq!(b.power_x_max, 60.0);
        assert_eq!(b.signal_x_max, 90.0);
        // Expression-order pin: 0.6*w is NOT 2*(0.3*w) in general; the oracle
        // computes each product independently from w. 100*0.3 == 30 exactly.
        let b2 = layout_boundaries(0.3);
        assert_eq!(b2.hv_x_max, 0.3 * 0.3);
        assert_eq!(b2.power_x_max, 0.3 * 0.6);
    }

    #[test]
    fn scale_bounds_matches_ratio_products() {
        assert_eq!(scale_bounds(0.1, 0.2, 0.7, 0.8, 200.0, 100.0), (20.0, 20.0, 140.0, 80.0));
        assert_eq!(scale_bounds(0.0, 0.0, 1.0, 1.0, 200.0, 100.0), (0.0, 0.0, 200.0, 100.0));
    }
}
