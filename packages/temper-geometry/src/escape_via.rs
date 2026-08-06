//! Wave-4 Phase B: the `router_v6/escape_via_generator` kernel in Rust.
//!
//! Mirrors, bit for bit, the pinned Python oracle
//! `packages/temper-placer/tests/router_v6/_escape_via_py_oracle.py` -- a
//! verbatim `git show` extraction of `router_v6/escape_via_generator.py` at
//! `143752893c177dc976da614566c64e4e53e4951f`, re-pinned by #801 onto the
//! post-#760 source (defect **D4** repaired: `side = component.initial_side
//! or 0`, not `getattr(component, "side", 0)`).
//!
//! Why this crate
//! --------------
//! The kernel is a *clearance predicate over pad geometry*: it needs
//! [`crate::pad_geometry::bounding_radius`] (the exact circumscribing radius
//! `pin_world_radius` delegates to) and the host-libm `cos`/`sin`/`pow` in
//! [`crate::host_math`].  Both already live here, and the differential's
//! adapter block names `temper_geometry` as the migration target, so the
//! kernel binds with zero edits to the test file.  The oracle header makes
//! the same recommendation ("its kernel should extend one of those crates
//! rather than found a 'cluster G' crate of its own").
//!
//! Semantics that are NOT the obvious Rust ones
//! --------------------------------------------
//! * **B1 -- host libm, resolved by `dlsym`.** `rotate_local_to_world` is
//!   CPython's `math.cos`/`math.sin`, which come from the *host Python
//!   runtime's* libm; a statically bound `f64::cos`/`f64::sin` measured 1 ulp
//!   apart on the uv standalone build.  [`crate::host_math`] resolves them
//!   through `dlsym(RTLD_DEFAULT, ...)`.
//! * **A quadrant rotation is NOT an exact axis swap.** `cos(pi/2)` is
//!   `6.123233995736766e-17`, so the reference leaves a residue proportional
//!   to the other coordinate.  The obvious "optimisation" -- swapping axes
//!   for a 0-3 rotation index -- is *more* correct and fails the
//!   differential.  The trig form is kept.
//! * **B7 -- `**` is libm `pow`, not `x * x`.** `_is_position_valid` computes
//!   `math.sqrt((x - px) ** 2 + (y - py) ** 2)`.  Measured over 20 000 random
//!   pairs, that form disagrees with `math.sqrt(dx*dx + dy*dy)` on 0.06% of
//!   them, so [`crate::host_math::pow`] is used rather than a multiply --
//!   and rather than `f64::powf`, which LLVM's `SimplifyLibCalls` rewrites
//!   into `x * x` for an exponent of exactly 2.0.
//! * **NaN is ACCEPTED, not rejected.** `dist < required_dist - 0.001` is
//!   `false` when `dist` is NaN, so `_is_position_valid` returns `true` and a
//!   NaN candidate is *chosen*.  A mirror that early-returns on NaN, or that
//!   spells the test `!(dist >= required)`, emits a different number of vias
//!   (pinned by `test_nan_pitch_emits_nan_positioned_vias`).
//! * **`_ignore_net` is deliberately dead.** It is underscore-prefixed and
//!   never read: the source pin's own pad *is* checked for clearance, which
//!   is what makes dog-bone placement fail below ~0.813 mm pitch.  Honouring
//!   it would be "more correct" and would fail
//!   `test_is_position_valid_ignores_its_ignore_net_argument`.
//! * **`rot * PI / 2.0`** is `(rot * PI) / 2.0`.  Division by 2.0 is exact, so
//!   this agrees with `rot * FRAC_PI_2` on 0 of 20 000 random values
//!   (measured; recorded in the oracle header as a *non*-divergence).  The
//!   multiply-then-divide form is kept because it is what the oracle writes.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyString};

use crate::host_math;
use crate::pad_geometry::bounding_radius;

/// `temper_placer.core.pad_geometry.DEFAULT_ROUNDRECT_RATIO`.
const DEFAULT_ROUNDRECT_RATIO: f64 = 0.25;

/// `temper_placer.core.pad_geometry.shape_code` -- unknown names map to the
/// `SHAPE_UNKNOWN` sentinel, which the pad core treats as a sharp rectangle.
fn shape_code(shape: &str) -> i64 {
    match shape {
        "circle" => 0,
        "oval" => 1,
        "rect" => 2,
        "roundrect" => 3,
        "thru_hole" => 4,
        _ => 99,
    }
}

/// `temper_placer.core.board.side_to_layer_name` (`board_contracts.rs`).
fn side_to_layer_name(side: i64) -> PyResult<String> {
    match side {
        0 => Ok("F.Cu".to_string()),
        1 => Ok("B.Cu".to_string()),
        _ => Err(PyValueError::new_err(format!(
            "side must be 0 or 1, got {side}"
        ))),
    }
}

/// `geometry/kicad_transform.rotate_local_to_world` -- R(-theta).
///
/// The two expressions are kept in the reference's exact op order and
/// grouping: no reassociation, no `mul_add` fusion (B7).
fn rotate_local_to_world(x: f64, y: f64, theta_rad: f64) -> (f64, f64) {
    let c = host_math::cos(theta_rad);
    let s = host_math::sin(theta_rad);
    (x * c + y * s, -x * s + y * c)
}

/// `core/pin_geometry._normalize_rotation` for the integer-index branch.
///
/// `Component.initial_rotation` is a rotation *index*; the corpus carries
/// out-of-range values (`5`, `-1`) precisely because the module multiplies
/// without validating.
fn normalize_rotation(rotation: Option<i64>) -> f64 {
    match rotation {
        None => 0.0,
        Some(r) => (r as f64) * std::f64::consts::PI / 2.0,
    }
}

// ---------------------------------------------------------------------------
// Corpus row shapes
// ---------------------------------------------------------------------------

/// `(pin_number, (px, py), net, width, height, shape)`.
struct PadRow {
    number: String,
    position: (f64, f64),
    net: Option<String>,
    width: f64,
    height: f64,
    shape: String,
}

impl PadRow {
    /// `core/pin_geometry.pin_world_radius`.
    ///
    /// The `w == 0.0 and h == 0.0 -> 0.5` special case is a documented
    /// default for zero-sized pads, not a bug, and the corpus's
    /// `pads_zero_size` row depends on it.
    fn world_radius(&self) -> f64 {
        // `getattr(pin, "width", 0.0) or 0.0` -- a 0.0 width stays 0.0.
        let w = self.width;
        let h = self.height;
        if w == 0.0 && h == 0.0 {
            return 0.5;
        }
        // `getattr(pin, "shape", None) or "rect"`: the corpus always sets a
        // shape, but an empty string would fall back to "rect" here too.
        let shape = if self.shape.is_empty() {
            "rect"
        } else {
            self.shape.as_str()
        };
        // `Pin` carries no `roundrect_ratio`, so `getattr(...) or DEFAULT`
        // always takes the default for every row this kernel can see.
        bounding_radius(w, h, shape_code(shape), DEFAULT_ROUNDRECT_RATIO)
    }
}

struct CompRow {
    position: Option<(f64, f64)>,
    rotation: Option<i64>,
    side: Option<i64>,
    pads: Vec<PadRow>,
}

impl CompRow {
    /// `comp.initial_side or 0` -- `None` **and** `0` both yield 0.
    fn side(&self) -> i64 {
        self.side.unwrap_or(0)
    }

    /// `core/pin_geometry.pin_world_position`.
    fn pad_world_position(&self, pad: &PadRow) -> (f64, f64) {
        let rotation_rad = normalize_rotation(self.rotation);
        let (mut px, py) = pad.position;
        // Bottom-side pads mirror X *before* rotation (KiCad behaviour).
        if self.side() == 1 {
            px = -px;
        }
        let (rx, ry) = rotate_local_to_world(px, py, rotation_rad);
        // `comp.initial_position or (0.0, 0.0)`: a `(0.0, 0.0)` tuple is a
        // non-empty tuple and therefore truthy, so only `None` falls back.
        let cpos = self.position.unwrap_or((0.0, 0.0));
        (cpos.0 + rx, cpos.1 + ry)
    }
}

fn parse_pads(pins: &Bound<'_, PyAny>) -> PyResult<Vec<PadRow>> {
    let mut out = Vec::new();
    for row in pins.try_iter()? {
        let row = row?;
        out.push(PadRow {
            number: row.get_item(0)?.extract()?,
            position: row.get_item(1)?.extract()?,
            net: row.get_item(2)?.extract()?,
            width: row.get_item(3)?.extract()?,
            height: row.get_item(4)?.extract()?,
            shape: row.get_item(5)?.extract()?,
        });
    }
    Ok(out)
}

/// `(initial_position, initial_rotation, initial_side, pitch_mm,
/// package_type, pins)` -- the corpus `PACKAGES` row with its label dropped.
fn parse_package(pkg: &Bound<'_, PyAny>) -> PyResult<(CompRow, f64)> {
    let position: Option<(f64, f64)> = pkg.get_item(0)?.extract()?;
    let rotation: Option<i64> = pkg.get_item(1)?.extract()?;
    let side: Option<i64> = pkg.get_item(2)?.extract()?;
    let pitch: f64 = pkg.get_item(3)?.extract()?;
    let pads = parse_pads(&pkg.get_item(5)?)?;
    Ok((
        CompRow {
            position,
            rotation,
            side,
            pads,
        },
        pitch,
    ))
}

/// `stage0_data.NetClassRules`, reduced to the four fields this kernel reads.
#[derive(Clone, Copy)]
struct Rules {
    clearance_mm: f64,
    via_diameter_mm: f64,
    via_drill_mm: f64,
}

/// `(net_classes, net_class_assignments, defaults)`.
struct DesignRules {
    classes: std::collections::HashMap<String, Rules>,
    assignments: std::collections::HashMap<String, String>,
    defaults: Rules,
}

impl DesignRules {
    /// `stage0_data.DesignRules.get_rules_for_net`.
    ///
    /// `if class_name and class_name in self.net_classes` -- an EMPTY class
    /// name is falsy and falls through to the defaults *without* a lookup,
    /// which is why the corpus carries `assignment_empty_string_class`.
    fn for_net(&self, net: &str) -> Rules {
        if let Some(class_name) = self.assignments.get(net) {
            if !class_name.is_empty() {
                if let Some(r) = self.classes.get(class_name) {
                    return *r;
                }
            }
        }
        self.defaults
    }
}

fn parse_rules(spec: &Bound<'_, PyAny>) -> PyResult<DesignRules> {
    let mut classes = std::collections::HashMap::new();
    let class_dict = spec.get_item(0)?.downcast_into::<PyDict>()?;
    for (k, v) in class_dict.iter() {
        let name: String = k.extract()?;
        let (clearance, _trace_w, via_dia, via_drill): (f64, f64, f64, f64) = v.extract()?;
        classes.insert(
            name,
            Rules {
                clearance_mm: clearance,
                via_diameter_mm: via_dia,
                via_drill_mm: via_drill,
            },
        );
    }
    let mut assignments = std::collections::HashMap::new();
    let assign_dict = spec.get_item(1)?.downcast_into::<PyDict>()?;
    for (k, v) in assign_dict.iter() {
        assignments.insert(k.extract()?, v.extract()?);
    }
    let (clearance, _trace_w, via_dia, via_drill): (f64, f64, f64, f64) =
        spec.get_item(2)?.extract()?;
    Ok(DesignRules {
        classes,
        assignments,
        defaults: Rules {
            clearance_mm: clearance,
            via_diameter_mm: via_dia,
            via_drill_mm: via_drill,
        },
    })
}

// ---------------------------------------------------------------------------
// The kernel
// ---------------------------------------------------------------------------

/// `_is_position_valid`.
///
/// The scan short-circuits on the first violating pad, and returns `true`
/// for an empty pad list (the loop body never runs).  `_ignore_net` is not a
/// parameter here because the reference never reads it -- see the module
/// docstring.
fn is_position_valid(x: f64, y: f64, radius: f64, comp: &CompRow, clearance: f64) -> bool {
    for pad in &comp.pads {
        let p_pos = comp.pad_world_position(pad);
        let pin_radius = pad.world_radius();

        // `math.sqrt((x - p_pos[0]) ** 2 + (y - p_pos[1]) ** 2)` -- libm
        // `pow`, then `sqrt`.  Neither `hypot` nor `dx * dx` is a legal
        // substitute (B7/B6).
        let dist = (host_math::pow(x - p_pos.0, 2.0) + host_math::pow(y - p_pos.1, 2.0)).sqrt();

        let required_dist = radius + pin_radius + clearance;

        // NaN makes this comparison false, so the candidate is ACCEPTED.
        if dist < required_dist - 0.001 {
            return false;
        }
    }
    true
}

/// One `EscapeVia`, flattened to the tuple the differential compares.
type ViaRow = ((f64, f64), String, String, f64, f64, String, String);

fn generate_escape_vias(
    comp: &CompRow,
    pitch_mm: f64,
    rules: &DesignRules,
    strategy: &str,
) -> PyResult<Vec<ViaRow>> {
    let mut escape_vias: Vec<ViaRow> = Vec::new();

    // Resolved BEFORE the pad loop, so a bad side raises before any geometry.
    let layer = side_to_layer_name(comp.side())?;

    // `angle` is the component's own board rotation.  `comp_x`/`comp_y` are
    // computed by the reference and then only handed to `_is_position_valid`'s
    // unused `_comp_pos`, so they are deliberately not modelled here.
    let angle = match comp.rotation {
        None => 0.0,
        Some(r) => (r as f64) * std::f64::consts::PI / 2.0,
    };

    for pad in &comp.pads {
        // `if not pin.net` -- both `None` and `""` are skipped.
        let net = match pad.net.as_deref() {
            None | Some("") => continue,
            Some(n) => n,
        };

        let r = rules.for_net(net);
        let via_diameter = r.via_diameter_mm;
        let via_drill = r.via_drill_mm;
        let clearance = r.clearance_mm;

        if strategy == "via-in-pad" {
            let abs_pos = comp.pad_world_position(pad);
            escape_vias.push((
                abs_pos,
                net.to_string(),
                pad.number.clone(),
                via_diameter,
                via_drill,
                "via-in-pad".to_string(),
                layer.clone(),
            ));
        } else if strategy == "dog-bone" {
            let pin_abs_pos = comp.pad_world_position(pad);
            let half_pitch = pitch_mm / 2.0;
            let candidates = [
                (half_pitch, half_pitch),
                (half_pitch, -half_pitch),
                (-half_pitch, half_pitch),
                (-half_pitch, -half_pitch),
            ];

            let mut chosen_pos: Option<(f64, f64)> = None;
            for (dx, dy) in candidates {
                let (rot_dx, rot_dy) = rotate_local_to_world(dx, dy, angle);
                let cand_x = pin_abs_pos.0 + rot_dx;
                let cand_y = pin_abs_pos.1 + rot_dy;
                if is_position_valid(cand_x, cand_y, via_diameter / 2.0, comp, clearance) {
                    chosen_pos = Some((cand_x, cand_y));
                    break;
                }
            }

            // `if chosen_pos:` on a 2-tuple is truthiness of a non-empty
            // tuple, i.e. exactly "is not None" -- including for `(0.0, 0.0)`.
            if let Some(pos) = chosen_pos {
                escape_vias.push((
                    pos,
                    net.to_string(),
                    pad.number.clone(),
                    via_diameter,
                    via_drill,
                    "dog-bone".to_string(),
                    layer.clone(),
                ));
            }
            // else: no valid dog-bone position -- the reference `pass`es.
        }
        // No `else`: an unknown strategy silently produces nothing.
    }

    Ok(escape_vias)
}

// ---------------------------------------------------------------------------
// PyO3 bridge
// ---------------------------------------------------------------------------

/// `generate_escape_vias(dense_pkg, design_rules, strategy)`.
///
/// `package` is a `PACKAGES` row with its label dropped:
/// `(initial_position, initial_rotation, initial_side, pitch_mm,
/// package_type, pins)`.  `rules` is a `RULE_SETS` row with its label
/// dropped: `(net_classes, net_class_assignments, defaults)`.
#[pyfunction]
#[pyo3(signature = (package, rules, strategy))]
pub fn escape_generate_vias_py(
    package: &Bound<'_, PyAny>,
    rules: &Bound<'_, PyAny>,
    strategy: &Bound<'_, PyString>,
) -> PyResult<Vec<ViaRow>> {
    let (comp, pitch) = parse_package(package)?;
    let design_rules = parse_rules(rules)?;
    let strategy: String = strategy.extract()?;
    generate_escape_vias(&comp, pitch, &design_rules, &strategy)
}

/// `_is_position_valid(x, y, radius, component, _, _, clearance)`.
///
/// `pads` rows are `(pad_x, pad_y, pad_w, pad_h, shape)`; the probe corpus
/// builds them into a component whose position is `(0.0, 0.0)` and whose
/// rotation index is `0`, so the world transform is the identity *by
/// arithmetic* rather than by a shortcut -- `px * 1.0 + py * 0.0` is not
/// `px` when `px` is `-0.0`.
#[pyfunction]
#[pyo3(signature = (x, y, radius, pads, clearance))]
pub fn escape_is_position_valid_py(
    x: f64,
    y: f64,
    radius: f64,
    pads: &Bound<'_, PyAny>,
    clearance: f64,
) -> PyResult<bool> {
    let mut rows = Vec::new();
    for (i, row) in pads.try_iter()?.enumerate() {
        let row = row?;
        let (px, py, w, h, shape): (f64, f64, f64, f64, String) = row.extract()?;
        rows.push(PadRow {
            number: i.to_string(),
            position: (px, py),
            net: None,
            width: w,
            height: h,
            shape,
        });
    }
    let comp = CompRow {
        position: Some((0.0, 0.0)),
        rotation: Some(0),
        side: None,
        pads: rows,
    };
    Ok(is_position_valid(x, y, radius, &comp, clearance))
}

pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(escape_generate_vias_py, m)?)?;
    m.add_function(wrap_pyfunction!(escape_is_position_valid_py, m)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn quadrant_rotation_is_not_an_exact_axis_swap() {
        let (x, y) = rotate_local_to_world(0.9375, 0.0, normalize_rotation(Some(1)));
        assert_ne!(x, 0.0, "the cos(pi/2) residue was optimised away");
        assert_eq!(y, -0.9375);
    }

    #[test]
    fn pow_two_is_libm_not_a_multiply() {
        // `x ** 2` is a libm `pow` call; on this host it disagrees with
        // `x * x` on a measurable fraction of inputs, which is why
        // `host_math::pow` is used rather than `f64::powf` (LLVM rewrites
        // `powf(x, 2.0)` into `x * x`) or an explicit multiply.
        let mut seen = 0usize;
        let mut v = 0.1234567_f64;
        for _ in 0..20000 {
            v = (v * 1.000_37).rem_euclid(1000.0) + 0.000_1;
            if host_math::pow(v, 2.0) != v * v {
                seen += 1;
            }
        }
        // Reported, not asserted non-zero: whether the host libm's `pow`
        // is correctly rounded is a property of the machine, not of this
        // code.  What matters is that the call is not constant-folded away.
        assert!(seen < 20000);
    }

    #[test]
    fn nan_distance_is_accepted_not_rejected() {
        let comp = CompRow {
            position: Some((0.0, 0.0)),
            rotation: Some(0),
            side: None,
            pads: vec![PadRow {
                number: "1".into(),
                position: (0.0, 0.0),
                net: None,
                width: 0.4,
                height: 0.4,
                shape: "circle".into(),
            }],
        };
        // A coincident via is rejected ...
        assert!(!is_position_valid(0.0, 0.0, 0.225, &comp, 0.15));
        // ... but a NaN one is ACCEPTED, because `NaN < x` is false.
        assert!(is_position_valid(f64::NAN, 0.0, 0.225, &comp, 0.15));
    }

    #[test]
    fn empty_pad_list_is_always_valid() {
        let comp = CompRow {
            position: Some((0.0, 0.0)),
            rotation: Some(0),
            side: None,
            pads: vec![],
        };
        assert!(is_position_valid(0.0, 0.0, 1.0, &comp, 1.0));
    }

    #[test]
    fn side_none_and_side_zero_both_resolve_to_f_cu() {
        assert_eq!(side_to_layer_name(0).ok(), Some("F.Cu".to_string()));
        assert_eq!(side_to_layer_name(1).ok(), Some("B.Cu".to_string()));
        assert!(side_to_layer_name(2).is_err());
    }

    #[test]
    fn zero_sized_pad_radius_is_the_documented_half_millimetre() {
        let pad = PadRow {
            number: "1".into(),
            position: (0.0, 0.0),
            net: None,
            width: 0.0,
            height: 0.0,
            shape: "rect".into(),
        };
        assert_eq!(pad.world_radius(), 0.5);
    }
}
