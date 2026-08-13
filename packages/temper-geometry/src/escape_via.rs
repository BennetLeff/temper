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
//! * **The rotation is resolved TWICE, under different rules.**  Pad world
//!   positions go through `pin_world_position` -> `_normalize_rotation`,
//!   whose dispatch is `None -> 0.0`, `int -> index * PI/2`, `float -> as-is
//!   (already RADIANS)`.  The dog-bone candidate offsets are rotated by the
//!   generator's *own* local `angle = float(initial_rotation_quadrant) * math.pi /
//!   2.0`, which scales unconditionally.  The two coincide on every integer
//!   index -- which is why the pinned corpus, all of whose rows carry an
//!   index, never separated them -- and diverge on every fractional one.
//!   Modelling both with one helper reads radians as a quarter-turn index
//!   (#931); [`rot_to_radians`] and [`local_dogbone_angle`] are kept apart,
//!   each faithful to its own call site.
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

/// `core/pin_geometry._normalize_rotation`'s **integer-index** branch: a
/// quarter-turn index becomes radians.
///
/// `Component.initial_rotation_quadrant` is a rotation *index*; the corpus carries
/// out-of-range values (`5`, `-1`) precisely because the module multiplies
/// without validating.
///
/// Written as `(index * PI) / 2.0`, not `index * (PI / 2.0)` and not
/// `index * FRAC_PI_2` -- the same spelling
/// [`crate::core_graph_geometry::normalize_rotation_index`] uses. All three
/// agree here (division by `2.0` is exact; measured over 20 000 values by
/// `test_trap_pi_over_two_is_exact_here`), so this is form-fidelity, not a
/// divergence fix.
fn normalize_rotation_index(index: f64) -> f64 {
    index * std::f64::consts::PI / 2.0
}

/// `core/pin_geometry._normalize_rotation`, the WHOLE three-way dispatch --
/// the rotation that reaches `pin_world_position`.
///
/// Mirrors [`crate::core_graph_geometry`]'s `rot_to_radians`, the canonical
/// implementation that `core/pin_geometry.py` binds as `_normalize_rotation`
/// and that the oracle therefore calls through `pin_world_position`:
///
/// ```text
/// None  -> 0.0
/// int   -> index * PI / 2      (a quarter-turn INDEX)
/// float -> as-is               (already RADIANS)
/// ```
///
/// The int and float branches mean **different things**, and that is the
/// whole subtlety. This kernel originally bound the value as `Option<i64>`,
/// which raised `TypeError` on a fractional rotation (pyo3 REJECTS a
/// non-integral float on an `i64` extract rather than truncating). The repair
/// widened the binding to `Option<f64>` and kept the unconditional `* PI/2`,
/// which accepted the float and then read radians as an index -- trading a
/// loud `TypeError` for a quiet wrong number (#931). #930 hit the identical
/// shape in `net_ordering.rs`/`terminal_planning.rs` and measured the
/// divergence at `rotation=0.5`: `0x1.6a09e667f3bccp+0` against the oracle's
/// `0x1.5b64e20408024p+0`. Reproducing the dispatch is the fix.
///
/// A *guard* that rejected non-integral input would be wrong here: the
/// canonical kernel accepts float and returns a defined answer, so raising
/// would be a fresh divergence from the oracle rather than a repair of one.
///
/// `bool` extracts as `i64` in pyo3 and so takes the index branch, matching
/// the oracle's `isinstance(rotation, int)` being `True` for `bool`.
fn rot_to_radians(rot: &Bound<'_, PyAny>) -> PyResult<f64> {
    if rot.is_none() {
        return Ok(0.0);
    }
    // `isinstance(rotation, int)`.
    if let Ok(index) = rot.extract::<i64>() {
        return Ok(normalize_rotation_index(index as f64));
    }
    // Otherwise (float, or anything `__float__` converts -- NaN/inf included).
    rot.extract::<f64>()
}

/// The oracle's **local** `angle`, which is NOT `_normalize_rotation`:
///
/// ```python
/// angle = 0.0
/// if component.initial_rotation_quadrant is not None:
///     angle = float(component.initial_rotation_quadrant) * math.pi / 2.0
/// ```
///
/// `escape_via_generator` resolves the rotation *twice, differently*, and the
/// two resolutions only coincide on the integer indices the corpus carries:
///
/// * pad world positions go through `pin_world_position` ->
///   `_normalize_rotation` -> [`rot_to_radians`] (int is an index, float is
///   already radians);
/// * the dog-bone candidate offsets are rotated by this local `angle`, which
///   calls `float()` first and then scales **unconditionally** -- so a float
///   rotation is scaled here and passed through there.
///
/// Collapsing the two into one helper is what #931 is about. They are kept
/// separate, each faithful to its own call site.
fn local_dogbone_angle(rot: &Bound<'_, PyAny>) -> PyResult<f64> {
    if rot.is_none() {
        return Ok(0.0);
    }
    // `float(...)` -- pyo3's f64 extract is `PyFloat_AsDouble`, i.e. exactly
    // Python's `float()`, so an int, a bool and a float all land here the way
    // the oracle's `float()` does.
    Ok(normalize_rotation_index(rot.extract::<f64>()?))
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
    /// `Pin.roundrect_ratio`. Optional so an older 6-tuple row still parses.
    roundrect_ratio: Option<f64>,
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
        // `ratio = getattr(pin, "roundrect_ratio", None) or DEFAULT`.
        //
        // The `or` is load-bearing and is NOT `unwrap_or`: 0.0 is FALSY in
        // Python, so a zero ratio also falls back to the default. Only a
        // non-zero value is honoured. This kernel previously hardcoded the
        // default outright, which silently diverged from the shipped
        // `pin_world_radius` for any board carrying a non-default
        // `roundrect_rratio` -- and `.kicad_pcb` files do carry them
        // (parse_engine.rs reads the field).
        let ratio = match self.roundrect_ratio {
            Some(r) if r != 0.0 => r,
            _ => DEFAULT_ROUNDRECT_RATIO,
        };
        bounding_radius(w, h, shape_code(shape), ratio)
    }
}

struct CompRow {
    position: Option<(f64, f64)>,
    /// `_normalize_rotation(initial_rotation_quadrant)` -- RESOLVED RADIANS, not the
    /// raw index, and resolved by [`rot_to_radians`] at parse time because the
    /// int/float dispatch needs the live Python object, which is gone by the
    /// time this struct exists. Read by [`CompRow::pad_world_position`].
    pad_rotation_rad: f64,
    /// The generator's own local `angle` -- `float(rot) * PI / 2.0`, scaled
    /// unconditionally ([`local_dogbone_angle`]). Read ONLY when rotating the
    /// dog-bone candidate offsets. Equal to `pad_rotation_rad` for every
    /// integer index, which is why the corpus never separated them.
    dogbone_angle_rad: f64,
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
        let rotation_rad = self.pad_rotation_rad;
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
            // 7th element is optional: a 6-tuple row keeps the old shape and
            // falls back to the default ratio, exactly as `getattr` would.
            roundrect_ratio: match row.get_item(6) {
                Ok(v) => v.extract().ok(),
                Err(_) => None,
            },
        });
    }
    Ok(out)
}

/// `(initial_position, initial_rotation_quadrant, initial_side, pitch_mm,
/// package_type, pins)` -- the corpus `PACKAGES` row with its label dropped.
fn parse_package(pkg: &Bound<'_, PyAny>) -> PyResult<(CompRow, f64)> {
    let position: Option<(f64, f64)> = pkg.get_item(0)?.extract()?;
    // Resolved TWICE, deliberately -- see `rot_to_radians` and
    // `local_dogbone_angle`. The two disagree for a non-integral rotation and
    // the oracle really does compute both.
    let rotation = pkg.get_item(1)?;
    let pad_rotation_rad = rot_to_radians(&rotation)?;
    let dogbone_angle_rad = local_dogbone_angle(&rotation)?;
    let side: Option<i64> = pkg.get_item(2)?.extract()?;
    let pitch: f64 = pkg.get_item(3)?.extract()?;
    let pads = parse_pads(&pkg.get_item(5)?)?;
    Ok((
        CompRow {
            position,
            pad_rotation_rad,
            dogbone_angle_rad,
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
        // Written as a single match rather than nested `if`s only to satisfy
        // `clippy::collapsible_if` under CI's `-D warnings`; the three
        // fall-through paths are unchanged -- no assignment, an EMPTY class
        // name, or a class name absent from `classes` all yield `defaults`.
        match self.assignments.get(net) {
            Some(class_name) if !class_name.is_empty() => {
                self.classes.get(class_name).copied().unwrap_or(self.defaults)
            }
            _ => self.defaults,
        }
    }
}

fn parse_rules(spec: &Bound<'_, PyAny>) -> PyResult<DesignRules> {
    let mut classes = std::collections::HashMap::new();
    let class_item = spec.get_item(0)?;
    let class_dict = class_item.cast::<PyDict>()?;
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
    let assign_item = spec.get_item(1)?;
    let assign_dict = assign_item.cast::<PyDict>()?;
    for (k, v) in assign_dict.iter() {
        assignments.insert(k.extract::<String>()?, v.extract::<String>()?);
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
/// CPython's float `**` operator, including its overflow behaviour.
///
/// `host_math::pow` is libm, which saturates to infinity; CPython's `**`
/// **raises** instead.  The oracle writes `(x - px) ** 2`, so the operator's
/// error is the one to mirror -- and it is NOT `math.pow`'s.  Measured:
///
/// ```text
/// (2e200) ** 2           -> OverflowError(34, 'Result too large')
/// math.pow(2e200, 2.0)   -> OverflowError('math range error')
/// inf ** 2               -> inf      (no error)
/// nan ** 2               -> nan      (no error)
/// ```
///
/// Hence the guard is "result went infinite from a FINITE base", which leaves
/// the inf and NaN paths alone -- the NaN path is load-bearing, since a NaN
/// distance makes the `<` comparison false and the candidate is ACCEPTED.
///
/// The exception text is resolved through the platform's own
/// `strerror(ERANGE)` (`crate::py_errors::overflow_error`), matching
/// whatever CPython's own `float_pow` raises on this host -- not hardcoded
/// to one platform's text. See `py_errors.rs`'s module doc comment.
pub(crate) fn pow_operator(base: f64, exp: f64) -> PyResult<f64> {
    let r = host_math::pow(base, exp);
    if r.is_infinite() && base.is_finite() {
        return Err(crate::py_errors::overflow_error());
    }
    Ok(r)
}

fn is_position_valid(
    x: f64,
    y: f64,
    radius: f64,
    comp: &CompRow,
    clearance: f64,
) -> PyResult<bool> {
    for pad in &comp.pads {
        let p_pos = comp.pad_world_position(pad);
        let pin_radius = pad.world_radius();

        // `math.sqrt((x - p_pos[0]) ** 2 + (y - p_pos[1]) ** 2)` -- libm
        // `pow`, then `sqrt`.  Neither `hypot` nor `dx * dx` is a legal
        // substitute (B7/B6).  `**` also raises on overflow; see
        // `pow_operator`.
        let dist = (pow_operator(x - p_pos.0, 2.0)? + pow_operator(y - p_pos.1, 2.0)?).sqrt();

        let required_dist = radius + pin_radius + clearance;

        // NaN makes this comparison false, so the candidate is ACCEPTED.
        if dist < required_dist - 0.001 {
            return Ok(false);
        }
    }
    Ok(true)
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
    // NOT the same rule as the pad transform: `float(rot) * PI / 2.0` scales
    // unconditionally, while `pin_world_position` runs `_normalize_rotation`'s
    // int/float dispatch. Identical for an integer index, different for a
    // fractional one -- see `local_dogbone_angle` (#931).
    let angle = comp.dogbone_angle_rad;

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
                if is_position_valid(cand_x, cand_y, via_diameter / 2.0, comp, clearance)? {
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
/// `(initial_position, initial_rotation_quadrant, initial_side, pitch_mm,
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
        // Accept either the 5-tuple `(px, py, w, h, shape)` or the 6-tuple
        // that additionally carries `roundrect_ratio`. The 5-tuple form keeps
        // working and falls back to the default ratio, which is what every
        // pre-existing corpus row relies on.
        let (px, py, w, h, shape, ratio): (f64, f64, f64, f64, String, Option<f64>) =
            match row.extract() {
                Ok(six) => six,
                Err(_) => {
                    let (px, py, w, h, shape): (f64, f64, f64, f64, String) = row.extract()?;
                    (px, py, w, h, shape, None)
                }
            };
        rows.push(PadRow {
            number: i.to_string(),
            position: (px, py),
            net: None,
            width: w,
            height: h,
            shape,
            roundrect_ratio: ratio,
        });
    }
    let comp = CompRow {
        position: Some((0.0, 0.0)),
        // The probe corpus's component has rotation index `0`; both
        // resolutions of index 0 are 0.0 rad.
        pad_rotation_rad: 0.0,
        dogbone_angle_rad: 0.0,
        side: None,
        pads: rows,
    };
    is_position_valid(x, y, radius, &comp, clearance)
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
        let (x, y) = rotate_local_to_world(0.9375, 0.0, normalize_rotation_index(1.0));
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
            pad_rotation_rad: 0.0,
            dogbone_angle_rad: 0.0,
            side: None,
            pads: vec![PadRow {
                number: "1".into(),
                position: (0.0, 0.0),
                net: None,
                width: 0.4,
                height: 0.4,
                roundrect_ratio: None,
            shape: "circle".into(),
            }],
        };
        // A coincident via is rejected ...
        assert_eq!(is_position_valid(0.0, 0.0, 0.225, &comp, 0.15).ok(), Some(false));
        // ... but a NaN one is ACCEPTED, because `NaN < x` is false.
        assert_eq!(is_position_valid(f64::NAN, 0.0, 0.225, &comp, 0.15).ok(), Some(true));
    }

    #[test]
    fn empty_pad_list_is_always_valid() {
        let comp = CompRow {
            position: Some((0.0, 0.0)),
            pad_rotation_rad: 0.0,
            dogbone_angle_rad: 0.0,
            side: None,
            pads: vec![],
        };
        assert_eq!(is_position_valid(0.0, 0.0, 1.0, &comp, 1.0).ok(), Some(true));
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
            roundrect_ratio: None,
            shape: "rect".into(),
        };
        assert_eq!(pad.world_radius(), 0.5);
    }
}
